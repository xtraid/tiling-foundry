---
layout: page
title: Serial solver reference profile
permalink: /solver_reference_profile_2026-08-17/
page_class: evidence
description: Reproducible reference measurements for the serial Wang solver.
section: Solver optimization
document_kind: Benchmark report
status: Recorded baseline
updated: 2026-08-17
nav_order: 20
---

# Serial solver reference profile — 17 August 2026

This report profiles the existing serial Wang solver after making the dense
UNSAT best-failed-leaf snapshot explicitly opt-in. It does not profile an
optimized solver, `TaskPlan`, or OpenMP implementation; none exists yet.

The results answer which mechanisms dominate the current reference path. They
do not by themselves freeze the optimized representation.

## Reproduction identity

Baseline parent Git commit:

```text
a00ec08a8fd2ddcd69c542af6787fb3e88049aaa
```

The measured source did not correspond to a commit. The relevant file
identities are therefore included explicitly:

```text
1d171d2e54bd5a742e183def7da22bce4c5bb1ca50ee8d02f6c2f59400ea71bc  include/wang/solver.h
23682d8ef5aa305394e9b3dd0997f13e3a49e2854c013334972b048485505173  src/solver/solver_serial.c
5d12e9260cb3028c2507bcd950256b658942393a4babde03acbca13aba32f917  benchmarks/c/bench_solver.c
490ff46c867c066e4d91a97306009aaedb30361932feb9132ebb51c0d7d6b140  benchmarks/run_reference_profile.sh
8fbd23195b4baf6b8f4877e8faedbdc5b16f6460e254e8237b98f3a99bfa6395  Makefile
```

Environment:

```text
Debian GNU/Linux 13
Linux 6.12.101+deb13-amd64 x86_64
AMD Ryzen 5 3600, 6 cores / 12 threads, boost enabled
CPU governor: schedutil
GCC 14.2.0
C17, -O2, portable build; no -march=native or LTO
Valgrind/Callgrind/Cachegrind 3.24.0
```

The five timing passes ran with a light but non-isolated host load. CPU
frequency was not pinned. Medians are authoritative for this baseline; min/max
show the observed noise and are not confidence intervals.

## Harness and measurement method

Build and run the complete reference profile with:

```sh
make benchmark
```

The harness prints one key-value record per execution. It separates:

1. repeated solves without metrics, used for elapsed time;
2. one solve without metrics, used for per-process peak RSS;
3. one solve with `WANG_SOLVE_COLLECT_METRICS`, used for deterministic work
   counts rather than timing;
4. default and `WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT` modes for the large root
   conflict.

Each case runs in a distinct process. Solver-only cases construct `Region`
before starting the timer. End-to-end Yang–Zhang cases include region building,
native solving, the solver's mandatory witness verification, and destruction.
Peak RSS is `getrusage(RUSAGE_SELF).ru_maxrss` on a single solve so allocator
retention across repeated solves does not inflate the memory result.

Five complete passes produced identical SAT/UNSAT results and identical metric
records in every case.

## Corpus v1

| Case | Scope | Expected | Cells | Active | Timing iterations |
| --- | --- | ---: | ---: | ---: | ---: |
| `generic_backtracking_sat` | solver-only | SAT | 16 | 16 | 5,000 |
| `generic_forced_thin_sat` | solver-only | SAT | 32,768 | 32,768 | 50 |
| `generic_root_unsat` | solver-only | UNSAT | 2,097,152 | 1 | 5 |
| `generic_unconstrained_sat` | solver-only | SAT | 9,216 | 9,216 | 5 |
| `yang_zhang_sat_solver` | solver-only | SAT | 9,361 | 9,345 | 20 |
| `yang_zhang_unsat_solver` | solver-only | UNSAT | 2,576 | 2,560 | 50 |
| `yang_zhang_sat_large_solver` | solver-only | SAT | 76,281 | 76,247 | 5 |
| `yang_zhang_unsat_large_solver` | solver-only | UNSAT | 20,351 | 20,317 | 10 |
| matching `*_end_to_end` cases | builder + solver | same | same | same | same |

The six-variable satisfiable formula contains `(0,1,2)` three times and
`(3,4,5)` three times. The twelve-variable family repeats the same construction
over four disjoint triples. Each variable occurs exactly three times and each
triple admits exactly-one assignments.

The UNSAT family uses disjoint pairs with clauses `(a,a,b)` and `(a,b,b)`.
Each variable again occurs exactly three times, while the pair requires both
`2a+b=1` and `a+2b=1`, which no Boolean assignment satisfies.

## Elapsed-time baseline

Times are milliseconds per iteration from the repeated, metrics-disabled run.

| Case | Mode | Median | Min | Max |
| --- | --- | ---: | ---: | ---: |
| `generic_backtracking_sat` | default | 0.032 | 0.032 | 0.033 |
| `generic_forced_thin_sat` | default | 4.398 | 4.334 | 4.628 |
| `generic_root_unsat` | default | 19.034 | 18.732 | 19.608 |
| `generic_root_unsat` | snapshot | 22.109 | 21.298 | 23.021 |
| `generic_unconstrained_sat` | default | 180.174 | 178.340 | 181.319 |
| `yang_zhang_sat_solver` | default | 12.191 | 11.911 | 12.559 |
| `yang_zhang_sat_end_to_end` | default | 12.305 | 12.162 | 12.365 |
| `yang_zhang_unsat_solver` | default | 3.069 | 3.001 | 3.178 |
| `yang_zhang_unsat_end_to_end` | default | 3.111 | 3.000 | 3.150 |
| `yang_zhang_sat_large_solver` | default | 95.255 | 94.239 | 95.898 |
| `yang_zhang_sat_large_end_to_end` | default | 96.101 | 95.788 | 96.353 |
| `yang_zhang_unsat_large_solver` | default | 24.211 | 23.588 | 25.496 |
| `yang_zhang_unsat_large_end_to_end` | default | 25.257 | 24.654 | 25.677 |

For these formula families, builder cost is small relative to solving: the
end-to-end median overhead is approximately 0.9 percent for medium SAT,
1.4 percent for medium UNSAT, 0.9 percent for large SAT, and 4.3 percent for
large UNSAT. These runs do not support subtracting the two numbers as a precise
builder measurement because the difference is small relative to process noise.

Enabling the dense UNSAT snapshot on the 2,097,152-cell root conflict adds
about 16.2 percent to the median time. This diagnostic comparison is not an
optimization gate for normal solving because the feature is disabled by
default.

## Single-solve peak RSS

| Case | Mode | Median KiB | Observed range KiB |
| --- | --- | ---: | ---: |
| `generic_backtracking_sat` | default | 1,588 | 1,468--1,600 |
| `generic_forced_thin_sat` | default | 3,580 | 3,484--3,632 |
| `generic_root_unsat` | default | 21,664 | 21,616--21,788 |
| `generic_root_unsat` | snapshot | 30,024 | 29,788--30,140 |
| `generic_unconstrained_sat` | default | 3,248 | 3,096--3,352 |
| `yang_zhang_sat_solver` | default | 2,976 | 2,920--3,152 |
| `yang_zhang_unsat_solver` | default | 1,956 | 1,932--2,024 |
| `yang_zhang_sat_large_solver` | default | 14,832 | 14,748--16,668 |
| `yang_zhang_unsat_large_solver` | default | 4,896 | 4,760--4,944 |

The diagnostic snapshot increases median RSS by 8,360 KiB. The theoretical
dense array is 2,097,152 cells times four bytes, or exactly 8,192 KiB; the
168-KiB difference is within process-level measurement noise. This confirms
that the new default avoids the intended allocation.

## Deterministic solver metrics

End-to-end and solver-only variants have identical solver metrics, so only the
solver-only rows are shown.

| Case | Decisions | Backtracks | Reductions | Arcs | MRV scanned | Trail peak | Queue peak | Depth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `generic_backtracking_sat` | 10 | 2 | 129 | 424 | 83 | 51 | 34 | 8 |
| `generic_forced_thin_sat` | 0 | 0 | 131,071 | 196,599 | 0 | 65,533 | 65,533 | 0 |
| `generic_root_unsat` | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| `generic_unconstrained_sat` | 9,059 | 0 | 117,098 | 501,298 | 43,897,478 | 80,808 | 27,265 | 9,059 |
| `yang_zhang_sat_solver` | 4 | 0 | 68,548 | 303,875 | 10,708 | 60,290 | 27,791 | 4 |
| `yang_zhang_unsat_solver` | 2 | 2 | 17,564 | 78,048 | 1 | 16,265 | 7,561 | 0 |
| `yang_zhang_sat_large_solver` | 8 | 0 | 572,581 | 2,565,295 | 241,688 | 510,665 | 228,255 | 8 |
| `yang_zhang_unsat_large_solver` | 2 | 2 | 140,502 | 634,603 | 1 | 135,600 | 60,715 | 0 |

The queue and trail peaks are live entry counts, not direct duplicate counts.
They justify measuring duplicate queue insertions and repeated trail writes but
do not by themselves prove that deduplication is beneficial.

## Callgrind and Cachegrind attribution

Callgrind used one metrics-disabled benchmark process per case. Unlike the
elapsed solver-only timer, its program total also includes fixture setup and
teardown; the percentages below therefore use the stricter whole-process
denominator:

- `generic_unconstrained_sat`: 2,271,892,621 instructions; the self cost of
  `select_mrv_cell()` is 1,905,013,160 instructions, or 83.85 percent;
- `yang_zhang_sat_solver`: 116,325,130 instructions; the self cost of
  `propagate_queue()` is 97,964,477 instructions, or 84.22 percent;
- `yang_zhang_sat_large_solver`: 956,473,594 instructions;
  `propagate_queue()` remains 84.23 percent at 805,589,942 instructions;
- `generic_forced_thin_sat`: 66,080,588 instructions; the serial solver is
  85.41 percent inclusive and `propagate_queue()` alone is 29.40 percent self.

The phase boundary is also visible on Yang–Zhang SAT. For six variables,
`wang_solve_serial()` is 97.41 percent inclusive, the builder is 2.43 percent,
and the independent verifier inside the solver is 3.81 percent. At twelve
variables those figures are 97.59, 2.35, and 3.79 percent respectively.
Inclusive percentages overlap because verifier work is part of the solver.

Cachegrind reports:

- unconstrained: 192,940,808 data references, 2.9 percent D1 miss rate and
  effectively zero aggregate last-level data miss rate;
- six-variable Yang–Zhang SAT: 10,384,328 data references, 0.6 percent D1 and
  0.3 percent LLd miss rates.

The measured cases are primarily paying for work volume and instruction count,
not a high last-level cache miss rate. Cache simulation is deterministic model
evidence, not a substitute for future native hardware-counter measurements.

## Conclusions and next gates

The reference baseline exposes two distinct hot regimes:

1. Linear MRV dominates a large, weakly constrained search. A derived MRV
   index or 24 buckets is justified for the performance path, but it will not
   materially help the profiled Yang–Zhang reductions, which make only 2--8
   decisions.
2. Propagation dominates both medium and large Yang–Zhang SAT cases at about
   84 percent of instructions. This keeps a serial `TaskPlan` and later OpenMP
   propagation in scope, but only after cheaper serial mechanisms and an exact
   executor-equivalence test.
3. The reference DFS reserves one `SearchFrame` per active cell. On the large
   Yang–Zhang SAT case this means capacity for 76,247 frames while observed
   depth is 8. Dynamic performance-path stack capacity is therefore the first
   low-risk memory candidate. The unconstrained case, whose depth is 9,059 of
   9,216 active cells, remains the counterexample that prevents assuming all
   workloads are shallow.
4. Queue and trail pressure scale materially: the large Yang–Zhang SAT case
   reaches 228,255 pending queue entries and 510,665 live trail entries. Add
   direct duplicate/rewrite measurements before implementing `in_queue` or
   trail compaction.
5. Opt-in UNSAT diagnostics work as intended: default root-UNSAT avoids one
   complete dense snapshot without changing SAT/UNSAT or scalar failed-leaf
   metadata.
6. The current 95-ms large Yang–Zhang solve is still small enough that OpenMP
   overhead may dominate. Parallel work requires a predeclared speedup/RSS gate
   and larger scaling cases; no OpenMP conclusion is made from this baseline.

The evidence supports a separate performance execution path with differential
tests and identifies dynamic DFS storage as the lowest-risk first mechanism.
MRV indexing and propagation work remain separate measured tracks. No
reference-path rewrite is justified by this report.

## Verification status

Before recording the profile, the revised solver contract passed:

- `make check`;
- `make strict-check`;
- `make sanitizer-check` with ASan/UBSan/LSan outside the ptrace sandbox;
- `make analyzer-check`;
- `make valgrind-check`;
- `make cachegrind-check`;
- ShellCheck for the profiling runner;
- strict compilation and smoke execution of the benchmark harness.

The first sandboxed LSan attempt failed because LeakSanitizer cannot operate
under ptrace. The same target completed successfully outside that sandbox; it
was an environment limitation, not a sanitizer finding.
