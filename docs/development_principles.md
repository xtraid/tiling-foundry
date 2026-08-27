---
layout: page
title: Development principles and architecture boundaries
permalink: /development_principles/
description: How Tiling Foundry separates source data, derived state, native lifetimes, solvers, and independent verification.
section: Architecture and correctness
document_kind: Architecture reference
status: Current implementation
updated: 2026-08-27
nav_order: 10
---

# Development principles and architecture boundaries

This page has two roles. Part A states the engineering principles used to
evaluate changes. Part B is the current ownership and dependency reference for
the implemented modules. Public headers and tests remain authoritative for ABI
and behavior.

The [initial architecture PDF]({{ '/historical_architecture/' | relative_url }})
records the broader starting point. It is design history, not a current
contract.

## Part A — Development principles

### Prefer the smallest sufficient representation

Prefer the smallest representation that preserves the required invariants.

- Give every allocation and mutable datum one clear owner.
- Borrow data by default. Transfer ownership only through an explicit
  contract.
- Compute derived data when needed until profiling justifies a cache.
- Introduce a struct for an object with its own state or lifetime, not merely
  to group temporary outputs.
- Add future metadata only when a concrete consumer exists.

### Keep correctness checks independent

Construction, search, and verification are separate implementations. A solver
produces a candidate witness; it does not define the conditions by which that
witness is accepted. Boolean and Wang Z3 paths are independent oracles over
copied immutable models, not alternate implementations of the native pipeline.

Evidence also retains its limits. Coverage is informational, fuzzing
complements deterministic tests, and host-specific benchmark results remain
host-specific. Optimization does not outrank correctness or module boundaries.

### Make dependency direction visible

Data flows from parsing and construction into generic solving and independent
verification. Adapters copy values across the native/Python boundary. Export
and rendering consume verified results downstream.

A lower layer does not acquire knowledge from a later one merely because that
knowledge could simplify an implementation. In particular, the generic solver
does not receive formula, routing, gadget, exporter, or renderer semantics.

### Add abstractions for demonstrated responsibilities

Add an abstraction when it removes duplicated behavior from real consumers,
enforces an otherwise fragile invariant, or owns a resource with a distinct
lifetime. Do not add one solely because it appears in a target architecture.

Performance state requires a benchmark or profile that can attribute the
benefit. Placeholder files preserve repository continuity but do not establish
an implemented capability or justify a premature public API.

### Define completion by contract and evidence

A module is implemented when it has:

- a small documented public contract, when a public API is needed;
- explicit ownership and failure behavior;
- an implementation included in the relevant build or runtime path;
- focused tests for invariants and invalid input;
- integration coverage with the preceding implemented layer;
- no dependency on unimplemented future layers.

## Part B — Architecture and ownership reference

### Module ownership

| Module | Owns or defines | Excluded responsibility |
| --- | --- | --- |
| `tile` | Fixed tileset, colors, and local matching | Search state |
| `permutation` | Signal tokens and adjacent-swap generation | Region geometry |
| `region` | Active cells and exposed boundary constraints | Solver domains and scheduling |
| `yang_zhang` | Reduction construction, transferred swap trace, and immutable signal/gadget provenance | Solver state and presentation metadata |
| `solver` | Domains, trail, assignments, and search state | Formula and reduction semantics |
| `solver_trace` | Opt-in bounded semantic events, full initial state, checkpoints, and their owned lifetime | Solving policy, raster composition, and Z3 internals |
| `verify` | Stateless validation of a candidate tiling | Search logic and solver caches |
| `crosscheck` | Stateless Boolean/Wang witness translation over a live reduction | Generic solver internals, clause validity, and copied swap data |
| `task_plan` | Future derived scheduling data | `Region` or serial-solver ownership |
| `python/model` | Pure immutable formula, region, tiling, reduction-explanation, and solver-trace contracts | I/O, ctypes, Z3, and native ownership |
| `python/native` | C ABI adaptation, scoped native lifetimes, and complete result/trace copy-out | Solver logic and escaping native pointers |
| `python/crosscheck` | Scoped composition of adapters, Z3, and independent checkers | Persistent native state and duplicated reduction semantics |
| `python/oracles` | Independent solvers and checkers over pure models | Parsing, filesystem I/O, and reduction construction |
| `python/formats` | Solution, static-stage, reduction-provenance, observed-trace, and Z3 encoding-summary validation/export | Native lifetimes, solving, and presentation |
| `renderer/wang_hex_port.py` | Pure square-to-hex mapping, inverse checks, and matching-equivalence checks | Raster geometry, semantic verification, and solver access |
| `renderer/wang_snapshot.py` | Strict hash-bound formula, tile-sheet, region, and recorded reduction-provenance views | Native access, solving, and geometry reconstruction |
| `renderer/wang_trace.py` | Strict hash-bound trace loading and independent ordered-delta replay | Native access, frame composition, and solving |
| `renderer/wang_animation.py` | Deterministic atomic PNG, contact-sheet, and GIF encoding from already composed frames | State reconstruction and correctness claims |
| `renderer/wang_square.py` | One CLI for solution and static views, with square/default or hex/explicit rasterization | Semantic verification and solver access |

`include/wang/task_plan.h`, `src/parallel/solver_openmp.c`, and the two modules
under `python/hex/` are placeholders. `src/io/json.c` is also a placeholder;
the implemented solution contract and exporter are Python modules under
`python/formats/`.

### Native and Python ownership flow

The C parser, Yang–Zhang builder, and opt-in traced solver calls own native
allocations. The adapters copy complete values into immutable Python `Formula`,
`Region`, `ReductionExplanation`, solver trace, tileset, and tiling models. No
ctypes pointer reaches those models or their consumers.

```text
                    C parser + Yang–Zhang builder
                                |
                                v
                            libwang.so
                                |
                  +-------------+-------------+
                  |                           |
                  v                           v
          native adapters              native witness bridge
                  |                           |
                  v                           v
       immutable Python models       generic native solver
          /              \
         v                v
   Python oracles    checkers / exporter --> Wang renderer
                                             |       \
                               trace replay -+        +--> pure hex port/check
                                             v                    |
                                      PNG/GIF views               v
                                                            hex PNG
```

The formula adapter uses `cm13_formula_load_path(...)`, the path-based external
C entry point. It does not bind a C `FILE *`. It copies all three ordered
positions of every clause and releases the native formula in a `finally`
block.

The reduction coordinator parses once. While the native formula is live, it
builds either the compact `YangZhangReduction` or the separate opt-in
`YangZhangExplainedReduction`, then copies only the Python views selected by
that path. Cleanup uses the matching destructor before releasing the formula.
The explanation adapter copies the exact source/target signals, swap-bound
gadget spans, and region extent before cleanup. Python models are not
reverse-marshalled into `Cm13Formula` or `Region`.

`native/_lib.py` centralizes lazy `libwang.so` loading.
`native/reduction_adapter.py` provides the copy-only formula/region path.
`crosscheck/witness_pipeline.py` keeps the same lifetime open for bridge calls,
and `native/solve_pipeline.py` supplies copied, independently checked native
tilings to producers without importing Z3.

The trace coordinator similarly parses and reduces once, copies the ordinary
result plus every semantic event and checkpoint before native destruction, and
checks any SAT tiling independently. Its JSON producer reuses the existing
formula, tileset, region, reduction, and solution formats. The renderer performs
one offline replay and passes already composed frames to the shared image
encoder; it never reconstructs solver state from pixels.

### Oracle and verifier contracts

| Component | Input | Result | Independence boundary |
| --- | --- | --- | --- |
| Boolean Z3 | immutable `Formula` | `SAT/UNSAT/UNKNOWN`; assignment only for SAT | No parsing, native access, region construction, or Wang semantics |
| Wang Z3 | immutable `Region + TILESET` | `SAT/UNSAT/UNKNOWN`; dense tiling only for SAT | No parsing, native access, formula semantics, or Yang–Zhang reconstruction |
| Boolean checker | `Formula + assignment` | witness validity | Counts clause positions, including repeats; does not import Z3 |
| Wang checker | `Region + TILESET + tiling` | witness validity | Checks dense storage, boundaries, and both adjacency orientations without Z3 or native access |
| Native verifier | `Region + dense TileId array` | `WangVerifyStatus` | Reads `TILESET` directly and does not consume solver caches or search state |

For generic tilesets with duplicate edge tuples, Wang Z3 returns a valid
positional ID from the constraint-equivalent entries. Its public contract does
not choose one duplicate over another.

Both Z3 encoders fix `random_seed=0`, `threads=1`, and their explicit constraint
order. A closed summary records the locked Z3 version, result/model, and stable
project-owned encoding counts. Raw Z3 statistics and internal debug/search
order are deliberately outside the stable contract.

### Witness correspondence boundary

The witness bridge adds exact assignment extension and tiling extraction above
the generic solver. The solver sees only reusable dense initial domains. The
bridge alone knows the three variable-cell coordinates and V0/V1 tile IDs. It
borrows the live reduction, ignores `reduction.swaps`, and does not evaluate
clauses.

Python coordinates the Boolean Z3 result, native bridge, and pure checkers
without reconstructing native models. A mismatch remains a copied
counterexample rather than being rewritten as another solver status. The
correspondence is not a bijection claim: multiple tilings may encode one
satisfying assignment, and extending an extracted assignment need not
reproduce the original tiling byte for byte.

The [witness correspondence design]({{ '/witness_correspondence/' | relative_url }})
is authoritative for extension, extraction, status, and lifetime details.

### Region representation

`Region` stores source-of-truth geometry:

- bounding width and height;
- one dense row-major active flag per position;
- exposed boundary-color constraints for active cells.

Coordinates and neighbor indices are derived from the dense index. The
representation does not cache `active_count`, scheduling zones, tile domains,
assignments, gadget types, or signal plans. If scheduling metadata acquires a
measured consumer, it belongs to a separate preprocessing result.

A generic `Region` may be disconnected or contain holes. The Yang–Zhang
builder owns the stronger obligation to produce the required simply connected
instances, and its tests verify that construction.

### Downstream solution and renderer boundary

Before solving, `python/formats/pipeline_snapshot.py` can project copied
`Formula`, canonical `TILESET`, and unassigned `Region` values into three
closed, versioned documents referenced by a hash-bound manifest. These are
presentation-neutral snapshots: they preserve source identity, ordered formula
positions, positional tile IDs, active cells, bounds, and exposed boundary
constraints without adding fields to the core models. The
[static snapshot contract]({{ '/wang-explainability-snapshots/' | relative_url }})
defines their failure and rendering behavior.

The native-only solve coordinator copies a verified SAT tiling out of native
storage and applies the independent Python Wang checker. The exporter then
produces the closed square-only `wang-solution-v1` document. The
[data contract]({{ '/wang-solution-v1/' | relative_url }}) is authoritative for
schema, semantic validation, deterministic serialization, and metadata rules.

The isolated Wang renderer consumes only that document. Its default path
projects the fields needed for the existing square diagnostic PNG. Explicit
`--hex` mode applies the pure in-memory
[square-to-hex port]({{ '/wang-square-to-hex/' | relative_url }}), runs its
raster-independent checker, and then composes a pointy-top axial PNG. The port
preserves the square table, selected IDs, coordinates, holes, boundary, and
matching truth values; it does not create a hex schema or core model.

Rendering is presentation, not proof. The port checker establishes translation
equivalence but deliberately does not require the source matching relations to
be true, so neither raster path can replace semantic validation or the
independent verifier.
