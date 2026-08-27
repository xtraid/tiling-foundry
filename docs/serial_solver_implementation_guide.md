---
layout: page
title: Serial Wang solver and independent verification
permalink: /serial_solver_implementation_guide/
description: Domain propagation, deterministic search, ownership, diagnostics, and the independent verifier used by both native solver paths.
section: Architecture and correctness
document_kind: Technical reference
status: Current implementation
updated: 2026-08-27
nav_order: 20
---

# Serial Wang solver and independent verification

The native reference and optimized entry points share one Wang-search core and
the same public status, ownership, diagnostic, and initial-domain contracts.
This page describes that core, the independent verifier applied to every SAT
result, the optional semantic event trace, and the optional failed-leaf
diagnostics. Public headers and regression tests remain authoritative for
exact ABI behavior.

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/solver-trace/frame-002517.png' | relative_url }}">
    <img src="{{ '/assets/images/solver-trace/trace.gif' | relative_url }}" alt="Observed reference solver domains narrowing across root initialization, propagation, decisions, and the final SAT result.">
  </picture>
  <figcaption><strong>Observed state.</strong> An offline consumer replays selected events from one complete 2,896-event reference run; skipped visual frames do not imply skipped solver events. The <a href="{{ '/assets/images/solver-trace/contact-sheet.png' | relative_url }}">static contact sheet</a> shows every rendered frame.</figcaption>
</figure>

## 1. Scope and dependency boundary

The subsystem implements a finite-region Wang decision procedure over the
canonical 23-tile `TILESET`. It combines 32-bit cell domains, boundary
restriction, local arc propagation, row-major MRV selection, iterative DFS,
and an undo trail. The same core supplies a deliberately direct reference path
and a path with measured private optimizations.

The path distinction is limited to these mechanisms:

| Mechanism | Reference path | Optimized path |
| --- | --- | --- |
| Support aggregation | Loop over set tile IDs | Private byte-wise lookup table |
| Pending queue | Duplicate-accepting FIFO | FIFO with a packed pending-cell index |
| Initial propagation trail | Record, then discard the prefix | Omit entries that no rollback can consume |
| DFS stack | Reserve for every active cell | Grow geometrically from a small initial capacity |
| SAT result domains | Copy the verified dense buffer | Transfer the verified private buffer |

Both paths retain the same input validation, domain meaning, search rules,
statuses, result ownership, diagnostics, and mandatory independent SAT
verification.

The solver receives `Region`, solver options, and caller-owned output storage.
It operates over reusable copies of the canonical tiles. The fixed model
permits translation but not rotation or reflection.

Formula clauses, adjacent-swap traces, generalized-gadget labels, Z3,
rendering, and Yang–Zhang construction data do not enter its decision state.

The relevant public boundaries are:

| Header | Public responsibility |
| --- | --- |
| `wang/tile.h` | `TileId`, `TILE_NONE`, directions, colors, `TILESET`, and direct edge matching |
| `wang/region.h` | Validated dense row-major geometry and exposed boundary colors |
| `wang/verify.h` | Independent validation of a complete dense tiling |
| `wang/solver.h` | Domains, options, statuses, result ownership, metrics, and both solve entry points |
| `wang/solver_trace.h` | Opt-in bounded semantic events, checkpoints, traced entry points, and trace ownership |

The implementation lives primarily in `src/verify/verify_tiling.c`,
`src/solver/solver_serial.c`, `src/solver/byte_support_table.c`, and
`src/solver/failed_leaf_trace.c`, and `src/solver/solver_event_trace.c`. It has
no mutable global search state.

## 2. Independent tiling verifier

`wang_verify_tiling()` consumes a validated `Region` and a dense array parallel
to `Region.cells`:

```c
WangVerifyStatus wang_verify_tiling(
    const Region *region,
    const TileId *tiles,
    size_t tile_count
);
```

`TILE_NONE` is defined once in `wang/tile.h`. Active cells contain a tile ID
strictly below `TILE_COUNT`; inactive cells contain `TILE_NONE`. The dense
length equals `region->cell_count`.

The verifier distinguishes invalid arguments, invalid region storage, an
incorrect dense length, incomplete active cells, invalid tile IDs, assignments
to inactive cells, boundary mismatches, and adjacency mismatches.

It reads edges directly from `TILESET`. It checks every exposed boundary color
other than `COLOR_NONE` and visits east and south adjacencies once each. It
does not call the solver or consume its compatibility caches. Successful
verification is therefore independent of the search mechanism that produced
the tiling.

## 3. Public solver API

### 3.1 Tile domains and status

The public domain containing every atomic tile ID is declared in
`wang/solver.h`:

```c
#define WANG_DOMAIN_ALL \
    ((UINT32_C(1) << TILE_COUNT) - UINT32_C(1))
```

For an active cell, a set bit permits the corresponding `TILESET` entry, a
singleton is a resolved placement, and zero is a conflict. Inactive cells use
zero as their normal dense-domain value.

The status enum keeps malformed or failed execution separate from a valid
negative decision:

```c
typedef enum {
    WANG_SOLVE_ERROR = -1,
    WANG_SOLVE_UNSAT = 0,
    WANG_SOLVE_SAT = 1
} WangSolveStatus;
```

An invalid region, invalid option, allocation failure, trace failure, or
rejected internal SAT witness produces `WANG_SOLVE_ERROR`. A well-formed root
restriction or propagated/search branch that has no extension produces
`WANG_SOLVE_UNSAT`.

### 3.2 Options

`WangSolverOptions` contains flags, optional failed-leaf trace configuration,
and optional borrowed initial domains:

```c
enum {
    WANG_SOLVE_COLLECT_METRICS = UINT32_C(1) << 0,
    WANG_SOLVE_TRACE_FAILED_LEAVES = UINT32_C(1) << 1,
    WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT = UINT32_C(1) << 2
};

typedef struct {
    uint32_t flags;
    const char *failed_leaf_path;
    size_t failed_leaf_capacity;
    const uint32_t *initial_domains;
    size_t initial_domain_count;
} WangSolverOptions;
```

A null options pointer has the same meaning as a zero-initialized options
object. Unknown flag bits are invalid. Trace capture requires a nonempty path
and a positive capacity.

Initial domains are absent exactly as `NULL/0`. When present, the pointer is
borrowed and immutable for the call, and the count equals
`region->cell_count`. Inactive entries are zero.

Active entries use only bits in `WANG_DOMAIN_ALL`. The full mask adds no
restriction, a nonzero subset restricts candidates, and zero is a well-formed
contradictory constraint. Complete validation of the dense array precedes
interpretation of any active zero. A malformed later entry therefore produces
`ERROR` rather than being hidden by an earlier contradiction.

### 3.3 Entry points

Both public functions have the same input, validation, diagnostic, and result
contract:

```c
WangSolveStatus wang_solve_serial(
    const Region *region,
    const WangSolverOptions *options,
    WangSolveResult *out_result
);

WangSolveStatus wang_solve_optimized(
    const Region *region,
    const WangSolverOptions *options,
    WangSolveResult *out_result
);

void wang_solve_result_destroy(WangSolveResult *result);
```

`out_result` is zero-initialized or previously passed to
`wang_solve_result_destroy()`. A conforming output remains destroyed on
`ERROR`. Passing a result that already owns domains is an API violation; it is
rejected unchanged rather than overwritten or leaked. Destruction accepts
`NULL`, frees an owned domain array, and resets every field.

### 3.4 Result ownership

`WangSolveResult` publishes dense domains, best-leaf metadata, trace metadata,
and optional metrics. Domain ownership depends on the successful status and
snapshot flag:

| Result | `domains` | `domain_count` | Ownership |
| --- | --- | ---: | --- |
| `SAT` | Complete singleton domains for active cells; zero for inactive cells | `region->cell_count` | Caller-owned |
| `UNSAT` with `WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT` | Dense best failed leaf | `region->cell_count` | Caller-owned |
| `UNSAT` without snapshot capture | `NULL` | `0` | No domain allocation is returned |
| `ERROR` with conforming output | `NULL` | `0` | Output remains destroyed |

`conflict_cell` is `SIZE_MAX` for SAT and identifies the zero-domain active
cell selected for the best failed leaf on UNSAT. `resolved_count` and
`decision_depth` describe that selected leaf even when no dense UNSAT snapshot
was requested. A region with no active cells is SAT and returns a dense array
of zeros.

## 4. Compatibility tables and domain initialization

The shared core derives two private tables from the canonical tileset:

```c
edge_mask[d][color] |= UINT32_C(1) << tile_id;

compat[d][tile_id] =
    edge_mask[opposite(d)][TILESET[tile_id].edge[d]];
```

`edge_mask[d][c]` contains tiles exposing color `c` in direction `d`.
`compat[d][t]` contains tiles allowed in the neighbor located in direction `d`
from tile `t`. An exhaustive regression compares every cached relation with
`wang_tiles_match()`, which keeps the cache derived rather than authoritative.

Region validation and complete initial-domain validation happen before solver
state is published. Each active domain begins as the supplied root mask or
`WANG_DOMAIN_ALL`, then intersects all exposed boundary masks:

```text
WANG_DOMAIN_ALL
    & optional caller root domain
    & north/east/south/west exposed-boundary masks
```

The state also records a four-bit active-neighbor mask per cell. Singleton
domains contribute to `resolved_count`. A legal mask that becomes empty after
boundary restriction or propagation is UNSAT; high bits, nonzero inactive
entries, and inconsistent pointer/count pairs are ERROR. Root restrictions and
boundary restrictions establish the search root and therefore do not represent
rollbackable decisions.

Initial propagation begins with all active cells in the queue and continues to
a fixed point before DFS. The reference path records initial propagation in its
trail and then discards that prefix at the fixed point. The optimized path
omits these non-consumable undo entries entirely. Both enter search from the
same domains.

## 5. Propagation

When cell `i` changes, propagation computes the union of compatible neighbor
tiles and intersects it with each active neighbor `j`:

```c
uint32_t supported = 0;
uint32_t candidates = domains[i];

while (candidates != 0) {
    const TileId tile = first_set_tile(candidates);
    supported |= compat[d][tile];
    candidates &= candidates - UINT32_C(1);
}

const uint32_t new_domain = domains[j] & supported;
```

The reference path executes this set-tile loop directly. The optimized path
uses a private `4 x 3 x 256` byte-support table derived from `compat`; its 3,072
`uint32_t` entries occupy 12,288 bytes and produce the same union from the
three bytes of the 23-bit domain.

Both paths use a contiguous FIFO. The reference queue accepts duplicate
pending cells. The optimized queue owns a packed cell-index bitset and
suppresses an enqueue when that cell already has an unconsumed occurrence. A
pop clears the bit before propagation, allowing a later domain change to
enqueue the cell again. Conflict and error exits drain the derived pending
state. Root conflicts and active graphs without arcs allocate no deduplication
index.

Every effective domain reduction updates `resolved_count`. A zero result stays
in the state long enough to identify and record the failed leaf before
rollback.

## 6. Trail, MRV, and iterative DFS

The undo trail is a contiguous vector of `(cell_index, old_domain)` entries.
Each search-time reduction appends the previous value before changing the
domain. Rollback walks entries in reverse to a saved marker and updates
`resolved_count` from the current and restored cardinalities. Multiple entries
for the same cell are intentional because they reproduce every intermediate
state exactly.

MRV selection scans active cells in row-major order and chooses the smallest
nonsingleton domain. Ties retain the lowest dense index, candidates are tried
in ascending tile-ID order, and propagation visits neighbors in `N`, `E`, `S`,
`W` order. These rules make each path deterministic for a fixed mechanism set.

DFS uses a heap-allocated stack rather than the process stack. A frame holds
the chosen cell, remaining candidates, and the trail position before the
parent branch entered the node:

```text
count the root node
if all active cells are singleton: SAT
push the root MRV frame

while a frame exists:
    if its candidates are exhausted:
        pop it, roll back to its entry marker, and continue at the parent
    otherwise:
        take the smallest tile ID
        save the trail marker
        restrict the chosen cell and propagate
        on conflict: record the leaf and roll back
        on complete singleton state: SAT
        otherwise: push the next MRV frame
```

The reference path reserves one frame per active cell. The optimized path
starts with at most 16 frames and grows geometrically up to the active-cell
limit. The storage policy changes allocation, not search semantics.

## 7. Mandatory SAT verification and publication

A SAT candidate is converted into a temporary dense `TileId` array: active
singletons become tile IDs and inactive positions become `TILE_NONE`.
Only a `WANG_VERIFY_VALID` candidate is published. Rejection converts the
internal result to `WANG_SOLVE_ERROR` because it exposes a solver defect rather
than a valid UNSAT decision.

Failed-leaf file finalization is the last fallible operation before ordinary
result publication. After it succeeds, the reference path copies verified
domains into a caller-owned snapshot. The optimized path transfers its
verified private domain buffer and detaches it from private state. Any
diagnostic best-leaf buffer accumulated during a satisfiable run remains
private and is freed.

## 8. UNSAT selection and snapshot policy

Every failed leaf records scalar metadata independently of optional outputs.
The deterministic best-leaf order is:

1. greater `resolved_count`;
2. at equal resolved count, greater decision depth;
3. at a complete tie, the first leaf encountered.

The conflict cell, depth, and resolved count are always retained. Dense storage
for the best leaf is allocated lazily only when
`WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT` is set. This separates a useful scalar
diagnostic from a potentially large `cell_count * sizeof(uint32_t)` snapshot.
The selected leaf is diagnostic and renderable, not a formal certificate of
unsatisfiability.

## 9. Optional metrics

Every `WangSolverMetrics` field is zero unless
`WANG_SOLVE_COLLECT_METRICS` is present. The counters have these stable
meanings:

| Metric group | Meaning |
| --- | --- |
| `dfs_nodes`, `decisions`, `backtracks`, `failed_leaves`, `max_depth` | Search states, attempted singleton branches, restored failed branches, observed conflicts, and deepest DFS level |
| `domain_reductions`, `propagated_arcs`, `mrv_cells_scanned` | Effective narrowing operations, processed directed neighbor arcs, and active cells inspected by MRV |
| `support_tile_visits`, `support_byte_lookups`, `support_table_bytes` | Reference set-tile work, optimized nonzero-byte work, and optimized table storage |
| `initial_trail_writes`, `search_trail_writes` | Undo entries appended in initial propagation and DFS |
| `initial_trail_rewrites`, `search_trail_rewrites` | Repeated entries for a cell within the initial interval or current branch interval |
| `trail_peak`, `trail_capacity_peak`, `trail_bytes_peak` | Live trail entries and maximum allocated capacity |
| `enqueue_attempts`, `duplicate_enqueue_attempts` | Queue requests and requests made while the cell is already pending |
| `queue_dedup_index_bytes`, `queue_peak`, `queue_unique_peak` | Packed optimized index storage, total pending occurrences, and distinct pending cells |
| `dfs_stack_capacity_peak`, `dfs_stack_bytes_peak` | Maximum allocated DFS stack capacity |
| `sat_result_copy_bytes` | Bytes copied solely to construct the SAT result; zero for UNSAT and optimized ownership transfer |

Metrics-enabled runs are diagnostic work measurements, not timing samples.
Elapsed time and process peak RSS are measured by the benchmark harness outside
the solver result.

## 10. Opt-in semantic event trace

`wang/solver_trace.h` adds traced reference and optimized entry points without
changing `WangSolverOptions`, `WangSolveResult`, or either ordinary entry
point. A caller supplies an event capacity of at least two and may additionally
request bounded full-state checkpoints. Every allocation is performed before
search begins. Disabled ordinary solving allocates no event or checkpoint
storage and publishes the same status, witness, metrics, and ownership as
before.

The trace begins with the full dense domain state after root restriction and
then records stable semantic events in observed order:

1. `root` publishes the initial replay base;
2. `domain_reduction` carries one exact old/new domain delta and its decision
   or propagation reason;
3. `propagation` marks the end of an initial or search propagation interval;
4. `decision`, `conflict`, and `backtrack` expose DFS control points with depth
   and trail change marks;
5. `result` terminates the run with `SAT` or `UNSAT`.

The recorder preserves a prefix and always reserves the final slot for
`result`. If the prefix fills, `truncated` becomes true and the terminal
sequence number exposes the number of omitted observed events; missing deltas
are never invented. Checkpoints contain a full dense domain row after every
configured interval while their independent capacity lasts. The replay model
validates event shapes, monotone domain reductions, exact rollback marks,
checkpoint equality, terminal status, and the complete SAT state when the
trace is not truncated.

`WangTracedSolveResult` jointly owns the ordinary result and trace storage.
Publication is transactional: invalid options, allocation failure, internal
recording failure, or rejected SAT verification leave a conforming output
destroyed. The combined destructor is null-safe and idempotent. The JSON and
raster consumers live downstream in Python and `renderer/`; neither is part of
the solver, and the GIF is presentation rather than a correctness check.

The closed transport is documented in the
[solver event trace contract]({{ '/wang-solver-trace/' | relative_url }}).

## 11. Binary failed-leaf trace

### 11.1 Semantics and format

`WANG_SOLVE_TRACE_FAILED_LEAVES` writes every observed failed leaf up to
`failed_leaf_capacity`. The trace may contain records even when the final
decision is SAT because earlier branches can fail. Once capacity is reached,
later leaves contribute to `metrics.failed_leaves` but are not written, and
`trace_truncated` is set.

Version 1 is explicitly little-endian. Its 64-byte header contains:

```text
magic[8]             "W23LEAF\0"
version              1
header_size          64
width, height
tile_count           23
flags                bit 0 = truncated
cell_count
record_size
record_capacity
record_count
```

Each record begins with four little-endian `uint64_t` values—leaf index,
conflict cell, decision depth, and resolved count—followed by exactly
`cell_count` little-endian `uint32_t` domains. Zero padding aligns the record to
eight bytes:

```text
raw_record_size = 32 + 4 * cell_count
record_size = align_up(raw_record_size, 8)
```

The writer uses explicit offsets and byte helpers, so the file format does not
depend on C struct padding or host `sizeof` results.

### 11.2 Writer lifecycle and failure cleanup

Checked arithmetic establishes the maximum mapping size before file creation.
The writer opens the path with `O_RDWR | O_CREAT | O_TRUNC`, expands it with
`ftruncate`, maps it shared and writable, and initializes a zero-record header.
Finalization writes flags and record count, synchronizes the used range,
unmaps the complete allocation, truncates the file to

```text
64 + record_count * record_size
```

and closes the descriptor.

Setup failures after file creation unlink the path. Finalization also unlinks
the path when synchronization, unmapping, final truncation, or close fails.
Record output itself is a checked write into the mapped range; rejection of an
impossible record bound marks the writer failed, returns an internal
`WANG_SOLVE_ERROR`, and causes finalization to unlink the incomplete trace.

The writer is private to the serial solver module. It is not a general
serialization API and has no shared-writer or multithreaded contract.

## 12. Error handling and lifetimes

Allocation sizes and dense products use checked arithmetic. Private state owns
domains, neighbor masks, byte-support tables, trail storage, queue storage,
pending indexes, DFS frames, best-leaf storage, and temporary verification
arrays. A single cleanup path releases them on validation, allocation,
propagation, verification, or trace failure.

The public result is assembled locally only after solving, independent SAT
verification, and trace finalization succeed. This transactional publication
keeps a conforming output destroyed on every error. Ownership transfer in the
optimized SAT path occurs immediately before private cleanup, preventing both
double frees and leaks on late failures.

## 13. Verification evidence

The verifier regressions cover null and length errors, invalid or incomplete
tile IDs, inactive assignments, boundary mismatches in every direction,
horizontal and vertical adjacency, holes, and corrupted region storage.

The solver suites exercise both public entry points across:

- absent, singleton, multi-bit, zero, and malformed initial domains;
- complete option validation before root UNSAT interpretation;
- empty, forced, contradictory, backtracking, and deep-search regions;
- brute-force equivalence on small deterministic and pseudo-random regions;
- rollback after repeated changes to the same cell;
- independent verification of every SAT witness;
- default scalar-only UNSAT results and opt-in dense snapshots;
- metrics-disabled zeroing and mechanism-specific counters;
- queue suppression, pop/re-enqueue behavior, and conflict cleanup;
- destroyed-output, already-owned-output, and idempotent-destruction cases.

Trace tests check absence without the flag, invalid path/capacity handling,
magic and version fields, record geometry, exact final size, truncation at
capacity, readability after unmap/close, and unlinking after post-creation setup
or finalization failure.

Semantic event-trace tests run the same SAT backtracking region through both
ordinary and traced reference/optimized calls. They require identical statuses,
witness bytes, and public metrics; deterministic event equality; independent
replay of all seven event kinds; bounded-prefix terminal publication;
checkpoint validation; root-conflict UNSAT; invalid-option rejection; and
idempotent cleanup.

Yang–Zhang integration includes shared SAT and UNSAT fixtures, the documented
three-variable satisfying instance, a clause-row regression, and all 1,701
canonical formulas through three variables checked against the independent
Boolean oracle.

## 14. Reproduction and profiling

The standard local gates are:

```sh
make clean
make check
make valgrind-check
make cachegrind-check
```

The benchmark and profiler paths keep metrics runs separate from timings and
measure MRV scans, queue duplication, trail pressure, domain reductions,
support aggregation, SAT-copy bytes, process peak RSS, and instruction/cache
attribution. Dated reports in the
[solver optimization section]({{ '/#solver-optimization' | relative_url }})
record the evidence for each retained optimized mechanism.

## 15. Current guarantees and limits

The implementation returns distinct SAT, UNSAT, and ERROR statuses; verifies
every SAT witness independently; returns dense domains for SAT and only for
explicitly captured UNSAT snapshots; preserves scalar best-leaf metadata
without that allocation; and removes trace output after post-creation setup or
finalization failure. Private caches and optimized storage remain derived from
domains, geometry, and `TILESET` rather than becoming new constraint sources.

The failed-leaf snapshot and both trace forms are diagnostics, not formal
UNSAT certificates. The implemented paths are serial. `TaskPlan`, OpenMP
execution, clause learning, backjumping, persistent memoization, rendering,
and JSON export remain outside this solver contract.
