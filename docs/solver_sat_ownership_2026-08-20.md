---
layout: page
title: Optimized solver SAT ownership transfer
permalink: /solver_sat_ownership_2026-08-20/
description: Evidence for transferring the verified SAT domain buffer without a redundant final copy.
section: Solver optimization
document_kind: Benchmark report
status: Accepted mechanism
updated: 2026-08-27
nav_order: 50
---

# Optimized solver SAT ownership transfer — 20 August 2026

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/optimized-mechanisms/frame-05.png' | relative_url }}">
    <img src="{{ '/assets/images/optimized-mechanisms/trace.gif' | relative_url }}" alt="Didactic comparison of the reference solver baseline and the five retained optimized serial mechanisms.">
  </picture>
  <figcaption><strong>Didactic replay.</strong> This shared animation locates SAT ownership transfer among the five isolated mechanisms; the measurements below, not the animation, establish its effect. The <a href="{{ '/assets/images/optimized-mechanisms/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all stages.</figcaption>
</figure>

This report evaluates only construction of a successful solver result. The
reference path retains the baseline behavior: after independent SAT
verification it ensures that a separate dense snapshot exists, allocating it
when absent, and copies every cell domain. The optimized path returns the
already verified private domain buffer and detaches it from solver state before
cleanup. Stack, trail, propagation, MRV, search order, UNSAT behavior,
`TaskPlan`, and OpenMP are unchanged.

## Reproduction identity

Measurements used Debian GCC 14.2.0, portable C17 `-O2`, Linux
`6.12.101+deb13-amd64`, benchmark schema version 4, and CPU 2 affinity on the
Ryzen 5 3600 host. The source snapshot is based on parent commit
`0836a84ce095458349ffb83c1f1062fe7796846b`; the binary hashes below identify
the measured revisions.

The comparable before/after binaries use the same schema-v4 benchmark source,
public metrics layout, compiler, flags, and link order. They differ only in
whether the optimized SAT path copies or transfers the result domains:

```text
e81058d34495fe95915a4e019defb0d422e29f9f69f0695fc43b282286de6227  comparable copy baseline
58da1ce7319052a4893d9780a95fd3bc460337664407abafcc8ac571e29f40a6  ownership-transfer build
```

An earlier comparison against schema v3 was rejected because changing the
benchmark executable's text layout produced large, matching noise in SAT and
UNSAT cases. Rebuilding the copy baseline with the identical v4 harness
removed that confounder.

## Lifetime and failure boundary

Both paths first require a complete singleton assignment and acceptance by
the independent tiling verifier. The optimized buffer is transferred only
after the failed-leaf writer has finalized successfully, which is the last
fallible operation before result publication. A late writer error therefore
still destroys all private state and leaves the public result empty.

The SAT backtracking regression runs both solvers with metrics, opt-in UNSAT
snapshot capture, and a capped failed-leaf trace. This deliberately creates a
diagnostic best-leaf allocation before the eventual SAT result. The optimized
path returns the live verified domains, frees the separate diagnostic
snapshot, and leaves one caller-owned allocation. Differential witness checks,
Memcheck, sanitizers, and result destruction cover double-free and leak risks.

The new `sat_result_copy_bytes` metric counts only bytes copied to construct a
final SAT result. With metrics enabled it is `cell_count * sizeof(uint32_t)`
for reference SAT, zero for optimized SAT, and zero for both UNSAT paths.
Without metrics every field remains zero.

## Direct copy evidence

Each solver-only case ran once with metrics enabled. Results and all semantic
work counters remained consistent between paths.

| Case | Cells | Reference bytes | Optimized bytes |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 32,768 | 131,072 | 0 |
| generic result-copy SAT | 2,097,152 | 8,388,608 | 0 |
| generic unconstrained SAT | 9,216 | 36,864 | 0 |
| generic backtracking SAT | 16 | 64 | 0 |
| generic root UNSAT | 2,097,152 | 0 | 0 |
| Yang–Zhang SAT, 6 variables | 9,361 | 37,444 | 0 |
| Yang–Zhang UNSAT, 6 variables | 2,576 | 0 | 0 |
| Yang–Zhang SAT, 12 variables | 76,281 | 305,124 | 0 |
| Yang–Zhang UNSAT, 12 variables | 20,351 | 0 | 0 |

`generic_result_copy_sat` is an explicit isolation case: a 2,048 by 1,024
dense region with one forced active cell. Search work is negligible while the
public result still contains one domain per cell, so the old 8 MiB allocation
and copy dominate the difference.

## Timing and resident memory

Seven alternating before/after passes used each case's standard iteration
count, metrics disabled, and `taskset -c 2`. Medians are per solve.

| Case | Copy baseline ms | Transfer ms | Delta |
| --- | ---: | ---: | ---: |
| generic result-copy SAT | 38.434273 | 33.769713 | -12.14% |
| generic forced thin SAT | 3.348710 | 3.334935 | -0.41% |
| generic unconstrained SAT | 176.416618 | 177.749401 | +0.76% |
| generic backtracking SAT | 0.030867 | 0.031459 | +1.92% |
| Yang–Zhang SAT, 6 variables | 10.835402 | 10.905642 | +0.65% |
| Yang–Zhang SAT, 12 variables | 86.804561 | 86.946962 | +0.16% |
| generic root UNSAT | 21.066107 | 21.349006 | +1.34% |
| Yang–Zhang UNSAT, 12 variables | 21.358734 | 21.415372 | +0.27% |

All non-isolation cases remain below the predeclared 3--5 percent material
regression guardrail. The two UNSAT controls do not execute the mechanism and
show the remaining measurement floor.

Median process peak RSS for the isolation case falls from 29,912 KiB to
23,744 KiB, a reduction of 6,168 KiB. The allocator does not return a full
8 MiB delta in `ru_maxrss`, so the direct copy counter is authoritative. The
large Yang–Zhang SAT median falls from 10,752 KiB to 10,140 KiB; its 298 KiB
copy is small relative to allocator and process-level noise, so no general RSS
ratio is claimed.

## Correctness and analysis gates

The final implementation passed the base C/Python/OpenMP/shared-library suite,
strict GCC and Clang builds, ASan/UBSan/LeakSanitizer, GCC static analysis,
Memcheck, and Cachegrind. The differential suite covers valid and invalid
inputs, SAT/UNSAT, brute-force and Boolean-oracle equivalence, independent SAT
witnesses, rollback, deep dynamic-stack growth, diagnostics, trace
finalization, and the new ownership metric.

## Decision

Retain SAT domain ownership transfer in `wang_solve_optimized()`. It removes
the normal final allocation and always removes the complete dense final copy,
improves the case that isolates that work, stays timing-neutral on the existing
corpus, and preserves the caller-visible result contract. The reference path
deliberately keeps its copy. Byte-wise support tables remain the next separate
optimization candidate.

## Final relevant file hashes

```text
02de1022053572f422967d8611582071508c52dd7affff7b1eea8344215080ec  Makefile
66bb98c6567d9028fcb95702ed87ec25c8ad9bb7bc705223d2ed8f0a8af3cc66  README.md
c3877d9a5d10ebb009df77f8c1cdc186bbaa6a0018dfa2da22faf22c4fcfb89e  benchmarks/c/bench_solver.c
5a61423da9c98b4d3c5d17c86f2eb8f4915762e1c2c76e752324d776f299ea99  benchmarks/run_reference_profile.sh
1a126b31412696c68ba4ad8f08a60ccef0a33c630169365396bbe7ad7ca009f1  docs/serial_solver_implementation_guide.md
cfcf5823e59e48bbba65308a06bae779f8645b86185cd1b0d9c774cb55dbd244  docs/solver_performance_scope.md
c955845b7271157505634e5bbb84ad1487476df4bba027a4d9f3853e1d9a0e16  include/wang/solver.h
9f31e084216e71c9482bd308d896a24b3d1c6db4acc2c6778af7a5be387d441d  src/solver/solver_serial.c
99c4f141af3dab73104c43387bb5634b6e8d84cc416c207ea89fc6c581762e61  tests/c/test_solver.c
2beedfe49ff5b5e346a6cd2e1f2b3b5994664385900d097377d69305df288f37  tests/c/test_solver_differential.c
```
