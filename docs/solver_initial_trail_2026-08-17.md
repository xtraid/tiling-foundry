---
layout: page
title: Optimized solver initial-trail removal
permalink: /solver_initial_trail_2026-08-17/
description: Evidence for omitting rollback entries during non-rollbackable initial propagation.
section: Solver optimization
document_kind: Benchmark report
status: Accepted mechanism
updated: 2026-08-27
nav_order: 40
---

# Optimized solver initial-trail removal — 17 August 2026

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/optimized-mechanisms/frame-05.png' | relative_url }}">
    <img src="{{ '/assets/images/optimized-mechanisms/trace.gif' | relative_url }}" alt="Didactic comparison of the reference solver baseline and the five retained optimized serial mechanisms.">
  </picture>
  <figcaption><strong>Didactic replay.</strong> This shared animation locates initial-trail omission among the five isolated mechanisms; the measurements below, not the animation, establish its effect. The <a href="{{ '/assets/images/optimized-mechanisms/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all stages.</figcaption>
</figure>

This report evaluates undo-trail recording during initial propagation. The
reference path keeps the baseline behavior. The optimized path applies the
same domain reductions but does not store their old values, because no
rollback can target state before the first DFS decision. Trail recording is
enabled before search begins and remains mandatory for every decision and
search-time propagation reduction.

This is not removal of compatibility memoization. The private Wang
compatibility masks and all propagation semantics are unchanged; only
non-consumable undo records are omitted.

## Reproduction identity

The measurements used Debian GCC 14.2.0, portable C17 `-O2`, Linux
`6.12.101+deb13-amd64`, and benchmark schema version 3 on the Ryzen 5 3600
host. The parent commit is `1c1d4cb621babe3e00dd429e089f8225ddf825ca`.
File hashes for the measured implementation and harness are recorded at the
end of this report.

Reference remains the benchmark default. Optimized measurements add
`--solver optimized`. Timing uses metrics disabled; direct trail records add
`--metrics`.

## Mechanism and correctness boundary

The shared solver core receives a private mechanism policy. For the reference
entry point, domain restriction records trail entries during initial
propagation and DFS. For the optimized entry point, the initial phase performs
only the domain update and resolved-count maintenance. On successful initial
quiescence, the core sets the phase to search and enables trail recording
before entering DFS.

No rollback occurs during initial propagation. If that phase finds a conflict,
the current domains are recorded directly as the failed leaf when requested;
the solver never attempts to restore the pre-propagation state. If it reaches
DFS, every later change is trailed exactly as before and every branch mark
refers only to search-time entries.

`WangSolverMetrics` and benchmark schema v3 add:

- `initial_trail_writes` and `search_trail_writes`, which count actual appended
  undo entries in their respective phases;
- `trail_capacity_peak` and `trail_bytes_peak`, which expose the allocation
  rather than inferring it from live occupancy;
- the existing `trail_peak`, which continues to report maximum simultaneous
  live entries.

Differential coverage now includes an initial-propagation UNSAT conflict with
opt-in snapshot, a generic SAT case with two real backtracks, a shallow
Yang–Zhang SAT case, and the existing brute-force, Boolean-oracle, invalid
input, diagnostic, deep-stack, and independent-witness checks. In the
backtracking case, both paths perform 78 search trail writes and two
backtracks; only the optimized initial write count is zero.

## Direct trail evidence

Each solver-only case ran once with metrics. Search work and solver outcomes
were identical between paths. `Initial writes` counts appended entries, not
boundary setup reductions that were already never rollbackable or trailed.

| Case | Reference initial writes | Optimized initial writes | Search writes, both | Reference trail bytes | Optimized trail bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| generic forced thin SAT | 65,533 | 0 | 0 | 1,048,576 | 0 |
| generic unconstrained SAT | 36,290 | 0 | 80,808 | 2,097,152 | 2,097,152 |
| generic backtracking SAT | 46 | 0 | 78 | 1,024 | 1,024 |
| generic root UNSAT | 0 | 0 | 0 | 0 | 0 |
| Yang–Zhang SAT, 6 variables | 60,290 | 0 | 7,378 | 1,048,576 | 131,072 |
| Yang–Zhang UNSAT, 6 variables | 16,265 | 0 | 1,009 | 262,144 | 16,384 |
| Yang–Zhang SAT, 12 variables | 510,665 | 0 | 58,532 | 8,388,608 | 1,048,576 |
| Yang–Zhang UNSAT, 12 variables | 135,600 | 0 | 3,898 | 4,194,304 | 65,536 |

The large satisfiable Yang–Zhang case therefore avoids 510,665 initial writes
and reduces actual trail capacity from 8 MiB to 1 MiB. The remaining 1 MiB is
not waste: it stores the 58,532 search-time undo entries required by the
current DFS path. The unconstrained case still needs the same 2 MiB capacity
for deep search, demonstrating that this change removes only initial storage
and does not weaken rollback.

## Timing

Five alternating reference/optimized passes used every solver-only case's
standard iteration count with metrics disabled. These numbers compare the
current performance path, including the already accepted dynamic stack, with
the reference path. The prior dynamic-stack report found no repeated material
timing difference; the direct write counters above isolate the new mechanism.

| Case | Reference median ms | Optimized median ms | Delta |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 4.506532 | 3.495220 | -22.44% |
| generic unconstrained SAT | 170.765704 | 170.089742 | -0.40% |
| generic backtracking SAT | 0.025067 | 0.025275 | +0.83% |
| generic root UNSAT | 20.765696 | 20.574230 | -0.92% |
| Yang–Zhang SAT, 6 variables | 9.976152 | 9.099286 | -8.79% |
| Yang–Zhang UNSAT, 6 variables | 2.468779 | 2.251082 | -8.82% |
| Yang–Zhang SAT, 12 variables | 80.033297 | 73.150064 | -8.60% |
| Yang–Zhang UNSAT, 12 variables | 20.613965 | 18.195170 | -11.73% |

The MRV-bound unconstrained case is effectively unchanged, as expected: it
still pays for its search trail and spends most work in linear MRV selection.
The small backtracking case remains well inside the predeclared 3--5 percent
regression guardrail. Initial-propagation-heavy cases show repeatable gains.

The four Yang–Zhang end-to-end cases were also measured over five alternating
passes:

| Case | Reference median ms | Optimized median ms | Delta |
| --- | ---: | ---: | ---: |
| SAT, 6 variables | 10.363330 | 9.339077 | -9.88% |
| UNSAT, 6 variables | 2.626378 | 2.329768 | -11.29% |
| SAT, 12 variables | 81.992529 | 75.514639 | -7.90% |
| UNSAT, 12 variables | 20.796288 | 19.088215 | -8.21% |

## Resident memory

Five alternating single-solve passes ran in fresh benchmark child processes.
Median `ru_maxrss` values are shown below. Small differences at the process
floor are treated as overlap rather than claimed improvements.

| Case | Reference median KiB | Optimized median KiB | Delta KiB |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 3,668 | 2,612 | -1,056 |
| generic unconstrained SAT | 3,308 | 3,328 | +20 |
| generic backtracking SAT | 1,876 | 1,876 | 0 |
| generic root UNSAT | 21,684 | 21,632 | -52 |
| Yang–Zhang SAT, 6 variables | 3,108 | 2,084 | -1,024 |
| Yang–Zhang UNSAT, 6 variables | 1,956 | 1,876 | -80 |
| Yang–Zhang SAT, 12 variables | 14,952 | 7,964 | -6,988 |
| Yang–Zhang UNSAT, 12 variables | 4,872 | 2,844 | -2,028 |

The large SAT reduction is repeatable and closely follows the 7 MiB direct
trail-capacity reduction. The large UNSAT optimized sample contained one
16,320 KiB outlier; the other four runs were 2,720--2,900 KiB and the median is
reported. Direct capacity counters remain the authoritative allocation
evidence.

## Decision

Retain initial-trail removal in `wang_solve_optimized()`. It eliminates exactly
the undo records that cannot be consumed, reduces trail capacity and resident
memory on propagation-heavy regions, improves their repeated time, and leaves
search-time trail writes and rollback intact. The reference path deliberately
keeps the original behavior. SAT ownership transfer remains the next separate
optimization candidate.

## Final relevant file hashes

```text
02de1022053572f422967d8611582071508c52dd7affff7b1eea8344215080ec  Makefile
9ddd20c6db1394b84b79140f63a81217c1051943bb33e74eb94429576cfa1f34  README.md
ae9f8fc6e142bd0516bfdc85691551ff14b2c1eff54678c0f8f988a2adfc8eb6  benchmarks/c/bench_solver.c
39c3489c28bb7dc3c8b545cdcef7c00ab129c76e88762cda0fffa2b2cd42ffc8  docs/serial_solver_implementation_guide.md
a2e845c8abc27641b0b039895edaf1a6c7cbb1828582c680c7ed1e3b3dd4763f  docs/solver_performance_scope.md
e1d456f1bd9c39d6ec2afcba86450feb54bf260f322a21a4d16839e8108b210c  include/wang/solver.h
b75d401cd4a5a063ce80ff692310ed03460927fc7e9a03396ba7ef28d6130aa7  src/solver/solver_serial.c
974ad627d24ba4700823368489cccc43bc6ce7561ade7104a5c0dd8e3c8ab8a6  tests/c/test_solver.c
3ee9de086ad6e8be58c1b849d48e93e9848f3ac9cfc862d7ef35deb725ac3c1e  tests/c/test_solver_differential.c
```
