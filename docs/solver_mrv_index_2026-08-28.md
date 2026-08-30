---
layout: page
title: Optimized solver MRV index
permalink: /solver_mrv_index_2026-08-28/
description: Evidence for the optimized solver's private row-major MRV bucket index.
section: Solver optimization
document_kind: Benchmark report
status: Accepted mechanism
updated: 2026-08-28
nav_order: 85
---

# Optimized solver MRV index — 28 August 2026

This accepted sixth serial mechanism replaces repeated linear MRV scans only
inside `wang_solve_optimized()`. The reference solver retains its explanatory
row-major scan. The optimized path derives 22 private buckets for domain sizes
2 through 23, stores bucket membership in packed cell-index bitsets, and keeps
one cached domain-size byte per dense cell. Selecting the first nonempty size
bucket and then its lowest set cell bit preserves the existing minimum-domain,
row-major tie break.

The index is created lazily only after a root branch propagates successfully
and search must descend to a child. Root conflicts, fully resolved regions,
no-search cases, and UNSAT runs that exhaust only the root frame allocate no
MRV index. Every later domain restriction and rollback moves the cell between
buckets; `domains` remains the semantic source of truth. Queue scheduling,
support aggregation, trail entries, trace events, SAT ownership, `TaskPlan`,
and OpenMP are outside this mechanism.

## Reproduction identity

The accepted base is the observed-run dossier squash commit:

```text
ca8690ce31ae63b922f52bd7cae24c21c65a27eb
Add opt-in observed-run dossiers (#19)
```

Both comparison binaries use benchmark schema v9, the same source tree,
compiler flags, link order, public metric layout, and harness. They differ only
in the private switch `WANG_OPTIMIZED_MRV_INDEX`:

```text
cdc3ff40840e4ef2e75865f6affa27328e15cb180bab6b420ad8b552497ff07c  switch=0
a79d2b78680e38090ef190c62ed87ce5bd064df0649d1f90aa5f36f1f0507722  switch=1
```

Final implementation source identities:

```text
611e60e4b34406318f7106b5a92daef5bc35cbe15775b061c6193c1c75dc6d68  include/wang/solver.h
94b992f6c1d167b91e978ab110eaa8a5aa758b8b7edac194bff8e3aad8145793  src/solver/solver_serial.c
34fcaed4bfb69cc71b37aa77a4d49158d5e10071c2c80be155094cb0e6289463  benchmarks/c/bench_solver.c
53062e8768acdd3cb21204e63c4e7baa721886303ecd8b6c029b8f41a1e754ab  tests/c/test_solver.c
f57fba10f7452b97f3563fb13bec447cb8725a0541aff25294bf81d9951a4510  tests/c/test_solver_differential.c
e61b2be36fc0cd859e2fd1106118d383b223109e37fb2871c99bd64c4d7174ff  python/native/witness_adapter.py
```

Environment:

```text
Debian GNU/Linux 13
Linux 6.12.105+deb13-amd64 x86_64
AMD Ryzen 5 3600, 6 cores / 12 threads, boost enabled
GCC 14.2.0
Clang 19.1.7
C17, portable -O2; no -march=native or LTO
Valgrind/Callgrind/Cachegrind 3.24.0
```

## Preventive red test and lifecycle

The differential test first required optimized MRV storage and probes, lower
cell-scan work, zero reference storage, and correct cleanup through the
existing 4-by-4 backtracking case. Building that test failed because
`WangSolverMetrics` did not yet contain `mrv_index_word_probes` or
`mrv_index_bytes`.

The retained test now observes the same SAT result, ten decisions, two failed
leaves, two backtracks, domain reductions, queue work, trail work, and verified
witness as before. Linear MRV inspects 83 active cells; the lazy indexed path
inspects 22 cells, probes seven packed words, and owns 192 bytes. Separate
controls require zero MRV bytes and probes for initial conflicts, no-arc
solutions, and Yang–Zhang UNSAT runs that never descend below the root frame.
Metrics-disabled differential runs still require the entire public metric
object to be zero.

The storage formula for a search that descends is:

```text
22 * ceil(cell_count / 64) * 8 + cell_count bytes
```

The first term is the 22 packed membership buckets. The second is the cached
domain size. Both live in one zero-initialized allocation owned by the solver
state. Allocation failure returns `ERROR` before a child frame is published;
normal destruction frees the combined allocation once.

## Direct work evidence

One metrics-enabled optimized solve per corpus case produced the following MRV
work. All non-MRV deterministic metrics were identical between the switch-off
and switch-on binaries.

| Case | Cells scanned off | Cells scanned on | Packed-word probes | Index bytes |
| --- | ---: | ---: | ---: | ---: |
| generic forced thin SAT | 0 | 0 | 0 | 0 |
| generic result-copy SAT | 0 | 0 | 0 | 0 |
| generic unconstrained SAT | 43,897,478 | 18,274 | 663,473 | 34,560 |
| generic backtracking SAT | 83 | 22 | 7 | 192 |
| generic root UNSAT | 0 | 0 | 0 | 0 |
| Yang–Zhang SAT, 6 variables | 10,708 | 4 | 169 | 35,233 |
| Yang–Zhang UNSAT, 6 variables | 1 | 1 | 0 | 0 |
| Yang–Zhang SAT, 12 variables | 241,688 | 8 | 3,781 | 286,073 |
| Yang–Zhang UNSAT, 12 variables | 1 | 1 | 0 | 0 |

Solver-only and end-to-end variants have identical solver metrics. The target
unconstrained case reduces direct cell inspection by 99.96 percent. The first
root selection remains linear because the index is deliberately lazy; later
selections use the buckets. The SAT Yang–Zhang rows also reduce scans, but
their shallow search means propagation and index maintenance still dominate
elapsed time.

## Alternating native timings

Seven passes alternated switch-off/switch-on order. Every process was pinned to
CPU 2; metrics were disabled; each case used its standard iteration count.
Medians are milliseconds per solve and ranges contain the seven process
results.

| Case | Off ms (range) | On ms (range) | Delta |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 3.793595 (3.716627–3.871777) | 3.800794 (3.747187–4.039952) | +0.19% |
| generic result-copy SAT | 30.110315 (29.398272–30.172475) | 29.899809 (29.757931–30.110611) | −0.70% |
| generic unconstrained SAT | 149.782460 (148.374775–153.990558) | 5.792362 (5.742785–5.852633) | −96.13% |
| generic backtracking SAT | 0.015253 (0.015157–0.016194) | 0.015368 (0.014856–0.015613) | +0.75% |
| generic root UNSAT | 17.852612 (17.536820–18.509080) | 17.854586 (17.113958–18.215488) | +0.01% |
| Yang–Zhang SAT, 6 variables, solver | 2.813235 (2.784532–3.008656) | 2.871883 (2.817281–2.904339) | +2.08% |
| Yang–Zhang UNSAT, 6 variables, solver | 0.619917 (0.617603–0.627671) | 0.633805 (0.617902–0.648096) | +2.24% |
| Yang–Zhang SAT, 6 variables, end-to-end | 3.012863 (2.965086–3.067994) | 3.013121 (3.007202–3.270830) | +0.01% |
| Yang–Zhang UNSAT, 6 variables, end-to-end | 0.672688 (0.668433–0.693132) | 0.676430 (0.667295–0.691344) | +0.56% |
| Yang–Zhang SAT, 12 variables, solver | 23.720687 (23.585753–25.196313) | 23.888030 (23.728251–24.338521) | +0.71% |
| Yang–Zhang UNSAT, 12 variables, solver | 5.008624 (4.899301–5.039353) | 4.967982 (4.894292–4.990429) | −0.81% |
| Yang–Zhang SAT, 12 variables, end-to-end | 25.404906 (25.181259–25.547235) | 25.407636 (25.120834–25.629196) | +0.01% |
| Yang–Zhang UNSAT, 12 variables, end-to-end | 5.311455 (5.270625–5.420725) | 5.341665 (5.264354–5.392123) | +0.57% |

The intended weakly constrained case improves by 96.13 percent. The largest
observed median regression is 2.24 percent, inside the predeclared approximate
3–5 percent corpus guardrail. The Yang–Zhang results support no speedup claim:
they remain controls showing that the index does not materially harm shallow
search.

## Resident memory

Seven alternating single-solve processes produced these peak-RSS medians and
ranges. Allocator granularity and process noise are larger than most index
allocations.

| Case | Off KiB (range) | On KiB (range) |
| --- | ---: | ---: |
| generic unconstrained SAT | 3,204 (3,116–3,308) | 3,144 (3,064–3,180) |
| generic result-copy SAT | 23,832 (23,784–24,000) | 23,896 (23,864–23,960) |
| generic root UNSAT | 21,756 (21,732–21,876) | 21,804 (21,780–21,896) |
| Yang–Zhang SAT, 12 variables | 5,964 (5,812–5,996) | 5,980 (5,940–6,088) |
| Yang–Zhang UNSAT, 12 variables | 2,264 (2,224–2,440) | 2,296 (2,240–2,380) |

There is no material process-level RSS regression. The direct metric remains
the authoritative storage evidence: 34,560 bytes on unconstrained SAT,
286,073 bytes on large SAT, and zero on the root-only UNSAT controls.

## Callgrind and Cachegrind

Metrics-disabled whole-process Callgrind runs recorded:

| Case | Instructions off | Instructions on | Delta |
| --- | ---: | ---: | ---: |
| generic unconstrained SAT | 1,920,147,624 | 73,933,241 | −96.15% |
| Yang–Zhang SAT, 12 variables | 307,034,463 | 309,228,803 | +0.71% |

Before the index, `select_mrv_cell()` accounts for 1,861,178,682 instructions,
96.93 percent of the unconstrained process. Afterward, propagation is the
largest named self cost at 44.97 percent; MRV selection no longer reaches the
0.1 percent annotation threshold. Large Yang–Zhang propagation instructions
remain identical, while index construction and maintenance explain the small
whole-process increase.

Cachegrind reported:

| Case | Data refs off/on | D1 misses off/on | LLd misses off/on | Branch mispredicts off/on |
| --- | ---: | ---: | ---: | ---: |
| generic unconstrained SAT | 190,708,286 / 18,342,553 | 5,663,856 / 113,979 | 30,801 / 29,780 | 16,883,851 / 525,650 |
| Yang–Zhang SAT, 12 variables | 74,337,594 / 75,594,598 | 363,273 / 343,120 | 74,993 / 76,439 | 1,802,268 / 1,802,465 |

The target improvement is reduced work volume, not a cache-rate claim. On the
large shallow-search control, data references rise by about 1.7 percent, D1
misses fall, LLd misses rise by about 1.9 percent, and branch mispredicts are
effectively unchanged. Cachegrind is a simulated cache model.

## Decision

Retain the lazy packed MRV index in `wang_solve_optimized()`. It removes the
measured linear-scan bottleneck from the weakly constrained case, preserves the
same deterministic MRV choice and every non-MRV work metric on the complete
corpus, keeps native controls inside the declared timing guardrail, and uses
bounded derived storage that is absent from root-only outcomes. The reference
solver remains the unchanged linear explanation.

This result does not justify trail compaction, `TaskPlan`, OpenMP, structural
scheduling, or any parallel speedup claim. The next separate Phase C change is
the hard-UNSAT/scaling corpus and option-matrix inventory required before
parallel design.

## Limitations

- The benchmark host was not frequency-isolated; timing ranges are descriptive
  host evidence, not confidence intervals.
- The generic unconstrained fixture is deliberately favorable to an MRV index
  and does not represent Yang–Zhang decision depth.
- Packed-word probes and cell inspections are different work units and are
  reported separately rather than summed into a synthetic score.
- `mrv_index_bytes` includes both packed buckets and the dense cached-size
  array; allocator overhead is not included.
- The switch-off binary contains dormant schema-v9 plumbing common to both
  sides. It isolates enabling the index, not historical source changes.
- Callgrind and Cachegrind include fixture construction, verification, and
  teardown; only the native timing table is solver-section elapsed time.

## Reproduction commands

```sh
make clean
make build/benchmarks/c/bench_solver \
  CFLAGS='-std=c17 -Wall -Wextra -Wpedantic -O2 -DWANG_OPTIMIZED_MRV_INDEX=0'
cp build/benchmarks/c/bench_solver /tmp/tiling-foundry-t92-mrv-off

make clean
make build/benchmarks/c/bench_solver
cp build/benchmarks/c/bench_solver /tmp/tiling-foundry-t92-mrv-on

/tmp/tiling-foundry-t92-mrv-on \
  --case generic_unconstrained_sat --solver optimized \
  --iterations 1 --metrics
```

Timing samples should alternate the two binaries and pin both to the same CPU:

```sh
taskset -c 2 /tmp/tiling-foundry-t92-mrv-off \
  --case generic_unconstrained_sat --solver optimized
taskset -c 2 /tmp/tiling-foundry-t92-mrv-on \
  --case generic_unconstrained_sat --solver optimized
```

Profilers use one metrics-disabled solve per output:

```sh
valgrind --tool=callgrind --error-exitcode=1 \
  --callgrind-out-file=/tmp/mrv.callgrind.out \
  /tmp/tiling-foundry-t92-mrv-on \
  --case generic_unconstrained_sat --solver optimized --iterations 1

valgrind --tool=cachegrind --cache-sim=yes --branch-sim=yes \
  --error-exitcode=1 --cachegrind-out-file=/tmp/mrv.cachegrind.out \
  /tmp/tiling-foundry-t92-mrv-on \
  --case generic_unconstrained_sat --solver optimized --iterations 1
```

## Verification status

The focused differential and switch-off/switch-on metrics, timing, RSS,
Callgrind, and Cachegrind comparisons above are complete. On 30 August 2026,
the retained source identities passed the complete local gate set:

- `make check`: all 17 C test binaries, 151 Python tests, 27 technical Pages
  documents plus the index, native benchmark smoke, and the cross-engine
  comparison smoke;
- 262 renderer tests and the real isolated pdfLaTeX dossier smoke;
- strict GCC and Clang, ASan/UBSan/LSan, GCC static analysis, Memcheck, and the
  complete Cachegrind target;
- informational coverage (C: 90.0% lines, 100.0% functions, 80.0% branches;
  Python: 83%) and the deterministic 2,000-run parser fuzz smoke;
- all 25 native benchmark cases in a fresh switch-off/switch-on comparison,
  with identical status and every non-MRV deterministic metric; and
- source hashes, diff whitespace, file modes, secrets, and generated-artifact
  checks.

The GitHub-only Jekyll build and the required protected-branch checks remain
remote publication evidence and must be observed on the pull request before
merge.
