---
layout: page
title: Solver optimization methodology and execution paths
permalink: /solver_performance_scope/
description: Stable correctness boundaries, measurement rules, and current mechanisms for the reference and optimized Wang solver paths.
section: Solver optimization
document_kind: Methodology
status: Current methodology
updated: 2026-08-21
nav_order: 10
---

# Solver performance scope

This document fixes the scope and guardrails for profiling and accelerating the
native Wang solver. It is not an implemented API contract and does not select
data structures before measurement. Public headers and tests remain
authoritative for current behavior.

## Objective

Keep one generic Wang decision procedure and provide two execution paths:

- a reference path that remains serial, direct, deterministic, and easy to
  explain;
- a performance path that may use optimized representations, derived indexes,
  task planning, and OpenMP.

The performance path exists to run the same Wang solver as fast as practical.
It is not a second reduction, a formula solver, or an independently designed
decision engine.

Conceptually:

```text
                         one Wang solver
 Region + TILESET  ------------------------------
                   domains and Wang compatibility
                   domain restriction invariants
                   trail and rollback semantics
                   search and SAT/UNSAT ownership
                   independent witness verification
                                |
                   +------------+------------+
                   |                         |
             reference path          performance path
             linear MRV              measured lazy MRV index
             simple FIFO queue       queue deduplication, if measured
             serial propagation      TaskPlan and OpenMP, if measured
             simple storage          optimized private storage
```

The public entry points are `wang_solve_serial()` for the reference path and
`wang_solve_optimized()` for the performance path. They have the same input,
ownership, diagnostics, and result contract.

## One solver, not two algorithms

Both paths receive only `Region + TILESET` and enforce the same finite Wang
constraints. The solver remains responsible for domains, search state,
rollback, and the SAT/UNSAT decision.

The following semantics must remain common:

- the meaning of every domain bit;
- compatibility derived from the canonical atomic `TILESET`;
- domain changes that only remove candidates;
- trail markers and restoration after backtracking;
- branch conflicts as zero domains;
- SAT only after every active cell is singleton;
- mandatory validation of every SAT witness by the independent verifier.

The performance path may replace mechanisms, not meaning. In particular, it
may change how MRV is indexed, how pending work is represented, how capacity
grows, or how propagation work is scheduled. Derived performance state is
private and never becomes a second source of truth.

## Reference path

The reference path is the executable explanation of the solver. It should keep
the simple baseline structure:

- contiguous bitmask domains;
- linear row-major MRV selection;
- a straightforward FIFO propagation queue;
- iterative DFS;
- a contiguous undo trail;
- serial application of every domain restriction.

It is algorithmically unoptimized but is still compiled with the normal
portable release flags, currently `-O2`. It must not be made artificially slow
to improve comparisons.

Correctness fixes belong first in focused regression tests and in the semantic
solver behavior. The reference path must remain available even when the
performance path is enabled.

## Performance path

The performance path may use, when supported by measurements:

- dynamic or more compact storage;
- ownership transfer that removes redundant copies;
- lazy diagnostic allocations;
- queue deduplication;
- MRV buckets or other derived indexes;
- private caches and precomputed scheduling metadata;
- a `TaskPlan` for propagation work;
- OpenMP;
- later, other scheduling improvements that preserve the same decision
  procedure and correctness boundaries.

OpenMP belongs inside the performance path. It does not create a third solver
and must never leak parallel metadata into `Region` or reduction construction.
Inner-loop dispatch, synchronization, copying, and false sharing are themselves
performance costs and must be measured.

## Forbidden shortcuts

Neither path may decide or guide Wang search using:

- a Boolean assignment from the Cubic Monotone 1-in-3 formula;
- formula variables or clauses as solver primitives;
- the Yang–Zhang swap trace;
- forwarder, anchor, crossover, or other generalized-gadget labels;
- precomputed gadget solutions;
- SAT/UNSAT conclusions produced by an external reduction-specific solver.

The formula, builder metadata, and independent oracles may generate test cases
or expected results. They do not enter the native solver's decision state.

## Required equivalence

The paths require semantic, not byte-for-byte, equivalence:

- they return the same SAT or UNSAT status for every valid input;
- they have the same input-validation and failure contract;
- every SAT result is a complete witness accepted by the independent verifier;
- small cases are cross-checked against brute force or an independent oracle;
- neither path may report UNSAT because of stale, cancelled, or invalid work.

The selected SAT witness, search order, failed leaf, conflict cell, diagnostic
depth, and scheduling metrics may differ. Deterministic behavior within a path
is desirable for reproducibility, but identical manifests across paths or
thread counts are not a correctness requirement.

## UNSAT diagnostics

The accepted target contract makes the dense best-failed-leaf snapshot an
opt-in diagnostic feature, disabled by default:

- SAT always returns a complete witness;
- UNSAT without the diagnostic flag does not allocate or return a dense failed
  leaf snapshot;
- UNSAT with the diagnostic flag returns the selected best failed leaf;
- failed-leaf tracing and best-snapshot capture remain separate options.

Both `wang_solve_serial()` and `wang_solve_optimized()` implement this contract.
Dense UNSAT snapshot storage is allocated lazily only when explicitly
requested; scalar failed-leaf metadata remains available without it. The
benchmark corpus represents both default and diagnostic modes.

## Profiling before optimization

No performance mechanism is selected before a reproducible baseline exists.
The initial benchmark work must provide:

- fixed, versioned SAT and UNSAT cases;
- small, medium, and large regions;
- Yang–Zhang reductions and generic Wang regions;
- propagation-heavy and backtracking-heavy cases;
- solver-only timing with `Region` construction outside the measured section;
- separate end-to-end timing for builder, solver, and verifier;
- elapsed time, peak resident memory, and the existing solver metrics;
- compiler, flags, commit, host, and repetition metadata.

Authoritative measurements use the portable `-O2` build on the benchmark host.
Host-specific flags such as `-march=native` may be investigated later as a
separate profile, not silently folded into the baseline. Timing thresholds do
not belong in CI; CI may run correctness and benchmark-smoke checks only.

## Acceptance gates

An optimization is retained only when:

- reference and performance paths continue to agree on SAT/UNSAT;
- every SAT witness passes the independent verifier;
- strict builds, sanitizers, static analysis, Memcheck, and relevant regression
  tests remain green;
- the intended time or memory improvement is repeatable on the target cases;
- the overall benchmark corpus has no unexplained material regression;
- the complexity and additional memory are justified by the measured benefit;
- the change is isolated enough to remove without disabling the reference
  path.

As an initial guardrail, a memory optimization should not introduce a repeated
time regression greater than approximately 3--5 percent across the
representative corpus. Exact gates for TaskPlan and OpenMP will be fixed before
those implementations are evaluated, after the serial profile is available.

## TaskPlan and OpenMP boundary

If profiling justifies parallel propagation, `TaskPlan` remains derived and
ephemeral. It schedules the solver's ordinary Wang operations and is never a
new source of constraints.

The initial ownership model is:

- DFS, branch creation, MRV decisions, trail, rollback, and global SAT/UNSAT
  remain controlled by the solver coordinator;
- workers read bounded snapshots of domains and geometry;
- workers produce private candidate-removal deltas;
- workers do not mutate shared domains and do not declare global UNSAT;
- the coordinator validates task freshness and applies live deltas through the
  solver's normal domain-restriction operation;
- work invalidated by rollback contributes nothing.

The first planned executor must be serial and differentially checked against
the reference propagation to quiescence. OpenMP is added only after that
equivalence and the scheduling overhead are measured.

No public `TaskPlan` representation is frozen until a concrete executor needs
it. Zone sizes, dependency encoding, branch epochs, cancellation, thread
counts, and commit ordering remain post-profiling design decisions.

## Streaming

Irreversible rendering and release of solved cells during rollback-capable DFS
is outside the current performance scope. It requires either a proven closure
condition, a complete frontier-state representation, or a correct checkpoint
and reconstruction strategy. A single observed boundary assignment is not in
general enough to preserve all unexplored continuations.

Progressive, invalidatable rendering may be explored separately. It must not
be confused with releasing final solver state.

## Optimization progression

The work progressed from an opt-in UNSAT snapshot contract to a fixed corpus
and reference baseline, then profiled allocation, initialization, propagation,
MRV, trail, rollback, and verification costs. The validated Wang core was
shared before the optimized entry point diverged in private mechanisms.

Six isolated mechanisms are now retained: dynamic DFS storage,
initial-propagation trail removal, SAT result ownership transfer, byte-wise
support aggregation, optimized queue deduplication, and a lazy private MRV
index. Each has a dated report with direct-work evidence and corpus-wide
controls.

`TaskPlan` and OpenMP remain conditional on their own evidence gates. Streaming,
cancellation, resource budgets, and speculative scheduling remain outside the
measured serial scope.

## Current implementation status

After the first six isolated performance mechanisms:

- `wang_solve_serial()` and `wang_solve_optimized()` are implemented public
  entry points with the same contract;
- both invoke the same validated Wang core; only the optimized path uses a
  small geometrically growing DFS stack and skips undo-trail recording during
  initial propagation, where rollback cannot occur. The trail is enabled
  before every DFS search restriction; the reference path retains its
  full-capacity stack and initial trail. After SAT verification and successful
  trace finalization, the optimized path transfers its domain buffer to the
  result while the reference path retains the baseline dense snapshot copy.
  During propagation only the optimized path uses a private 12 KiB table to
  union support by nonzero domain byte; the reference retains the baseline
  set-tile loop. The optimized path also uses a packed private pending-cell
  bitset to suppress an enqueue when that cell already has an unconsumed FIFO
  occurrence; the bit is cleared before propagation so later domain changes
  may enqueue the cell again. The reference FIFO continues to accept
  duplicates;
- differential tests cover generic Wang SAT/UNSAT cases checked by brute
  force, backtracking, Yang–Zhang reductions checked by a Boolean oracle,
  independently verified SAT witnesses, UNSAT diagnostics, invalid API inputs,
  shallow-stack reservation, growth beyond 8,000 frames, and SAT ownership
  coexistence with failed-leaf tracing and the opt-in diagnostic snapshot. A
  dedicated test also validates every one of the 4 x 3 x 256 derived support
  entries against compatibility masks rebuilt from `TILESET`;
- `src/parallel/solver_openmp.c` is a placeholder;
- `include/wang/task_plan.h` is empty;
- the shared core captures the UNSAT diagnostic snapshot lazily and only when
  explicitly requested;
- `benchmarks/` contains the fixed generic and Yang–Zhang corpus and a
  reproducible portable `-O2` runner selectable between reference and
  optimized entry points;
- `benchmarks/python/compare_solvers.py` runs native reference, native
  optimized, Boolean Z3, and Wang Z3 workers in fresh processes over versioned
  `.cm13` inputs. It keeps prepared-Region timing separate from the
  file-to-verified-decision view and records raw samples and timeout-aware
  summaries as JSON Lines;
- the [reference profile]({{ '/solver_reference_profile_2026-08-17/' | relative_url }})
  records timing, peak RSS, solver
  metrics, and Callgrind/Cachegrind attribution;
- the [SAT ownership report]({{ '/solver_sat_ownership_2026-08-20/' | relative_url }})
  records direct final-copy bytes,
  allocation/RSS behavior, comparable timing, and lifetime checks;
- the [byte-support report]({{ '/solver_byte_support_2026-08-20/' | relative_url }})
  records direct support-work counters,
  exhaustive table validation, comparable timing, and the rejected runtime
  validation experiment;
- the [queue and trail profile]({{ '/solver_queue_trail_profile_2026-08-20/' | relative_url }})
  records the direct pending queue,
  repeated trail-write, Callgrind, and Cachegrind evidence. It selects queue
  deduplication as its next isolated mechanism, identifies MRV indexing as a
  distinct weakly constrained candidate, and rejects trail compaction for now;
- the [queue-deduplication report]({{ '/solver_queue_dedup_2026-08-20/' | relative_url }})
  records the retained packed pending index,
  direct scheduling work, native timings, memory, and post-change profiler
  attribution;
- the [MRV-index report]({{ '/solver_mrv_index_2026-08-28/' | relative_url }})
  records the retained lazy packed buckets, row-major equivalence, direct scan
  and storage work, corpus controls, memory, and profiler attribution;
- trail compaction, `TaskPlan`, and operational OpenMP are not implemented.

These facts distinguish the implemented serial mechanisms from the still
unimplemented parallel architecture.
