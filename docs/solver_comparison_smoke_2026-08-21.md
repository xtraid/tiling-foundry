---
layout: page
title: Native and Z3 solver comparison smoke baseline
permalink: /solver_comparison_smoke_2026-08-21/
page_class: evidence
description: Seven-sample native and Z3 baseline on the smallest shared SAT and UNSAT inputs.
section: Cross-engine benchmarks
document_kind: Benchmark report
status: Recorded evidence
updated: 2026-08-21
nav_order: 20
---

# Native and Z3 solver comparison smoke baseline — 21 August 2026

## Scope

This report records the first run of the
[cross-engine benchmark protocol]({{ '/solver_comparison_benchmark/' | relative_url }}).
It answers two deliberately different questions:

- how the native reference, native optimized, and Wang Z3 paths compare when
  region preparation is outside the timer;
- how all four implemented paths behave from the same `.cm13` file to a
  checked SAT or UNSAT decision.

The second view is not an algorithm-equivalence claim. Boolean Z3 decides the
formula directly; the other engines decide its Yang–Zhang Wang region.

## Environment and identity

The run used the portable project flags and one pinned logical CPU:

```text
host                 local benchmark host
cpu                  AMD Ryzen 5 3600 6-Core Processor
affinity             CPU 2
kernel               6.12.101+deb13-amd64
compiler             GCC 14.2.0
C flags               -std=c17 -Wall -Wextra -Wpedantic -O2
C standard           201710
Python               3.13.5
Z3                   4.16.0
benchmark schema     8
comparison schema    1
base commit          f7f7123336406b046298275f1244646f66421736
source snapshot      modified from base commit; exact hashes recorded below
```

The measured benchmark sources had these identities:

```text
9f5758811a85f55580dedd84fd440c08c15d6a9f1c60d2ea3716ff0afeecc82b  benchmarks/c/bench_solver.c
b2024f84d21b1e726c26cfb07f718abb89fdcbe21586dccd0a43ad119882d990  benchmarks/python/compare_solvers.py
3caaa6b29ac988fb4f51cc7071202d83ea1591ba6170e683b6da449cb3641542  tests/instances/pipeline_sat.cm13
a044340af1b6a40143222e12c3ab49f74895f7edb64f3067e8a540abc2202c20  tests/instances/pipeline_unsat.cm13
```

The exact command was:

```sh
taskset -c 2 uv run --frozen python benchmarks/python/compare_solvers.py \
  --preset smoke --samples 7 --iterations 1 \
  --timeout-seconds 30 \
  --c-flags '-std=c17 -Wall -Wextra -Wpedantic -O2'
```

Every sample used a fresh process. The runner reversed engine and scope order
on alternating samples. There was no hidden warm-up. All 98 samples completed
with the expected status and no timeout. Every SAT witness passed the checker
belonging to its path.

## Prepared-Region results

Region parsing, construction, and Python copying are outside this timer. Times
include solving and result validation. Each range is minimum to maximum over
seven samples; RSS is the median whole-process high-water mark.

| Case | Engine | Median time | Range | Median RSS |
| --- | --- | ---: | ---: | ---: |
| SAT | C reference | 0.504 ms | 0.499–0.577 ms | 1,712 KiB |
| SAT | C optimized | 0.142 ms | 0.139–0.147 ms | 1,648 KiB |
| SAT | Wang Z3 | 10,794.211 ms | 10,714.300–10,814.860 ms | 88,400 KiB |
| UNSAT | C reference | 0.0168 ms | 0.0157–0.0171 ms | 1,620 KiB |
| UNSAT | C optimized | 0.0215 ms | 0.0207–0.0230 ms | 1,572 KiB |
| UNSAT | Wang Z3 | 272.007 ms | 270.057–278.157 ms | 59,664 KiB |

On the small SAT region, the optimized C median is 71.7 percent below the
reference median. The UNSAT region is too small and shallow for the difference
between 0.0168 and 0.0215 ms to characterize either native path.

## File-to-verified-decision results

These timers start before parsing. They include every reduction and Python
model copy used by the selected public path, solving, and result validation.

| Case | Engine | Median time | Range | Median RSS |
| --- | --- | ---: | ---: | ---: |
| SAT | C reference | 0.549 ms | 0.541–0.558 ms | 1,744 KiB |
| SAT | C optimized | 0.187 ms | 0.176–0.194 ms | 1,616 KiB |
| SAT | Boolean Z3 | 6.988 ms | 6.954–7.131 ms | 58,572 KiB |
| SAT | Wang Z3 | 10,787.209 ms | 10,713.832–10,903.297 ms | 88,524 KiB |
| UNSAT | C reference | 0.0523 ms | 0.0399–0.0529 ms | 1,608 KiB |
| UNSAT | C optimized | 0.0487 ms | 0.0455–0.0608 ms | 1,564 KiB |
| UNSAT | Boolean Z3 | 4.347 ms | 4.261–4.411 ms | 53,104 KiB |
| UNSAT | Wang Z3 | 274.654 ms | 271.304–276.515 ms | 59,568 KiB |

The optimized C SAT median is 65.9 percent below the reference median in this
scope. For Wang Z3, parsing and model preparation are lost in the roughly
10.8-second SAT solve. Boolean Z3 is much faster than Wang Z3 because it solves
the original three-variable formula, not the 444-active-cell Wang region; that
ratio is not a speedup on the same solver problem.

The RSS figures describe the complete process. The roughly 50–85 MiB gap
between native and Python rows includes the CPython and Z3 runtimes and must not
be attributed only to solver data structures.

## Why this UNSAT case is faster than SAT

UNSAT does not generally require less work than SAT. These fixtures make the
opposite outcome possible because their contradictions are deliberately
shallow.

The smoke UNSAT formula is the repeated-position clause `(x,x,x)`. Exactly one
of its three positions can never be true: assigning `x=false` makes zero true
positions and assigning `x=true` makes three. In the six- and twelve-variable
UNSAT families, each pair `(x,x,y)` and `(x,y,y)` similarly forces incompatible
values when repeated positions are counted.

The tiling reduction does not expose the Boolean contradiction directly, but
the native metrics confirm a very shallow search on the smoke region:
`dfs_nodes=1`, `decisions=2`, `backtracks=2`, and `max_depth=0`. Propagation
rejects both first choices. SAT instead requires construction and validation of
a complete dense tiling. Wang Z3 therefore takes about 272 ms to refute this
UNSAT region but about 10.79 seconds to construct the SAT witness.

This corpus is useful for correctness, propagation, and witness-cost checks. It
does not represent a hard UNSAT instance whose contradiction appears only after
deep backtracking. A harder UNSAT family therefore requires its own justified
corpus and measurement protocol.

## Scaling pilot and limits

Before fixing the routine preset, one unpinned calibration sample ran the
six-variable SAT case with a 10-second worker timeout. Boolean Z3 completed in
9.90 ms; Wang Z3 timed out in both scopes. Those censored observations are not
part of the tables above. They justify keeping the six- and twelve-variable
presets explicit rather than making routine checks wait through repeated long
timeouts.

This smoke baseline is host-specific and does not replace the larger native
performance corpus. In particular:

- the native UNSAT timings are below a useful scale for optimization claims;
- CPU frequency and unrelated host load were not controlled beyond affinity;
- Python process startup is excluded from elapsed time but included in RSS;
- the timeout encloses the whole worker, while elapsed time follows the scope
  boundaries described above;
- no comparison here establishes asymptotic behavior.
