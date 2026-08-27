---
layout: page
title: Optimized solver dynamic DFS stack
permalink: /solver_dynamic_stack_2026-08-17/
description: Evidence for the optimized solver's geometrically growing DFS stack.
section: Solver optimization
document_kind: Benchmark report
status: Accepted mechanism
updated: 2026-08-27
nav_order: 30
---

# Optimized solver dynamic DFS stack — 17 August 2026

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/optimized-mechanisms/frame-05.png' | relative_url }}">
    <img src="{{ '/assets/images/optimized-mechanisms/trace.gif' | relative_url }}" alt="Didactic comparison of the reference solver baseline and the five retained optimized serial mechanisms.">
  </picture>
  <figcaption><strong>Didactic replay.</strong> This shared animation locates the dynamic stack among the five isolated mechanisms; the measurements below, not the animation, establish its effect. The <a href="{{ '/assets/images/optimized-mechanisms/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all stages.</figcaption>
</figure>

This report evaluates only DFS stack storage. The reference path still
allocates one `SearchFrame` per active cell. The optimized path starts with at
most 16 frames, doubles geometrically, and clamps its final growth to the
active-cell limit. Trail, propagation, queue, MRV, result ownership, search
order, `TaskPlan`, and OpenMP are unchanged.

## Reproduction identity

The measurements used Debian GCC 14.2.0, portable C17 `-O2`, Linux
`6.12.101+deb13-amd64`, and benchmark schema version 2 on the Ryzen 5 3600
host. The parent commit is `1c1d4cb621babe3e00dd429e089f8225ddf825ca`.
Relevant measured-source hashes are recorded to make the revision reproducible:

```text
02de1022053572f422967d8611582071508c52dd7affff7b1eea8344215080ec  Makefile
60f315f834bebb1c6e42581697f8e41366d9b288734cd9f795cc5291e6825065  README.md
51834e0af4e8bb1837506e9c0a09e0a62304d3eaa7492581dc310d423c6258ba  include/wang/solver.h
445aa88ac50b98c4b55b4433df80e7d5031378b96bef5394292bdfb7554be74b  src/solver/solver_serial.c
a579cf399c2645492afe8acf9efdfe1514fd7dfe10aa120680098c48640fcde0  benchmarks/c/bench_solver.c
552c746ee5367cf66c0211cbb765bd9f6d18e283a824add5260bff55c4cb2c11  tests/c/test_solver.c
7b3d6691943f38ec73b3a474fd69bc6010229eb1f11265e6f0458b497341cc56  tests/c/test_solver_differential.c
c26c7d00d20fdf56945fe9a53ac359926b76339bcbc1185cc6a14a5123f58d1a  docs/solver_performance_scope.md
```

Reference remains the benchmark default. Optimized measurements add
`--solver optimized`; direct allocation records additionally add `--metrics`.

## Correctness and failure boundary

Both paths continue to use the same Wang core and independent SAT verifier.
Stack allocation and growth check multiplication overflow, never grow past the
number of active cells, and return `WANG_SOLVE_ERROR` on allocation failure.
The reference path retains its single full-capacity `malloc`; only the
optimized path may call `realloc`.

`WangSolverMetrics` now exposes `dfs_stack_capacity_peak` and
`dfs_stack_bytes_peak`. These measure the allocation directly. Process peak
RSS is still recorded, but it is not an authoritative measure for virtual
pages reserved by `malloc` and never touched.

Differential coverage adds:

- a six-variable satisfiable Yang–Zhang region whose reference stack reserves
  all 9,345 active-cell frames while the optimized stack stays at 16;
- a 9,216-cell unconstrained region whose optimized search reaches depth 9,059
  and grows safely to the full 9,216-frame limit;
- the existing generic, backtracking, diagnostic, invalid-input, SAT/UNSAT,
  brute-force, Boolean-oracle, and independent-witness checks.

## Direct allocation evidence

The portable GCC `-O2` benchmark harness ran each solver once with metrics.
All non-stack work metrics were identical between paths.

| Case | Depth | Reference frames | Optimized frames | Reference bytes | Optimized bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| generic backtracking SAT | 8 | 16 | 16 | 384 | 384 |
| generic forced thin SAT | 0 | 0 | 0 | 0 | 0 |
| generic root UNSAT | 0 | 0 | 0 | 0 | 0 |
| generic unconstrained SAT | 9,059 | 9,216 | 9,216 | 221,184 | 221,184 |
| Yang–Zhang SAT, 6 variables | 4 | 9,345 | 16 | 224,280 | 384 |
| Yang–Zhang UNSAT, 6 variables | 0 | 2,560 | 16 | 61,440 | 384 |
| Yang–Zhang SAT, 12 variables | 8 | 76,247 | 16 | 1,829,928 | 384 |
| Yang–Zhang UNSAT, 12 variables | 0 | 20,317 | 16 | 487,608 | 384 |

The large satisfiable case therefore removes 1,829,544 bytes of unused DFS
stack reservation, a 4,765-fold capacity reduction. The deep unconstrained
counterexample grows to the old limit as required; this optimization does not
assume that every workload is shallow.

Five alternating reference/optimized timing passes used each case's standard
iteration count with metrics disabled:

| Case | Reference median ms | Optimized median ms | Delta |
| --- | ---: | ---: | ---: |
| generic backtracking SAT | 0.024697 | 0.024421 | -1.12% |
| generic forced thin SAT | 4.496257 | 4.472838 | -0.52% |
| generic root UNSAT | 20.640026 | 20.228229 | -2.00% |
| generic unconstrained SAT | 171.536229 | 169.060998 | -1.44% |
| Yang–Zhang SAT, 6 variables | 10.386034 | 10.249726 | -1.31% |
| Yang–Zhang UNSAT, 6 variables | 2.504592 | 2.564347 | +2.39% |
| Yang–Zhang SAT, 12 variables | 77.385314 | 79.358104 | +2.55% |
| Yang–Zhang UNSAT, 12 variables | 20.701713 | 20.484570 | -1.05% |

The large UNSAT row uses a follow-up set of 15 alternating runs because its
first five-run sample showed a noisy +5.78 percent. The follow-up ranges were
19.578--21.424 ms for reference and 19.513--21.427 ms for optimized; their
medians differ by -1.05 percent. No repeated material time regression remains.

Five single-solve RSS passes had overlapping and inconsistent deltas, including
both positive and negative differences. No RSS reduction is claimed. This is
consistent with the full reference allocation reserving address space while
touching only the shallow prefix. The direct allocation counters, correctness
tests, and absence of a timing regression are the acceptance evidence.

## Decision

Retain dynamic DFS storage in `wang_solve_optimized()`. It removes a proven
large unused reservation in shallow propagation-heavy searches, grows safely
for deep generic searches, and stays within the predeclared time-regression
guardrail. Later mechanisms are evaluated independently.
