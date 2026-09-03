---
layout: page
title: Native and Z3 solver comparison benchmark
permalink: /solver_comparison_benchmark/
page_class: reference
description: Reproducible protocol for comparing the native and Python Z3 decision paths.
section: Cross-engine benchmarks
document_kind: Benchmark protocol
status: Current protocol
updated: 2026-08-24
nav_order: 10
---

# Native and Z3 solver comparison benchmark

The comparison runner executes every implemented decision path against a fixed
set of versioned Cubic Monotone 1-in-3 SAT files. It records raw samples and
summaries as JSON Lines. It is a measurement tool, not a CI performance gate.

## Compared engines and scopes

The repository currently has four executable serial paths:

| Engine | `wang-solve-verified` | `file-to-verified-decision` |
| --- | --- | --- |
| native C reference | prepared `Region` to verified Wang decision | `.cm13` parse, reduction, and verified Wang decision |
| native C optimized | prepared `Region` to verified Wang decision | `.cm13` parse, reduction, and verified Wang decision |
| Python Boolean Z3 | not applicable | `.cm13` parse and copied formula to verified Boolean decision |
| Python Wang Z3 | copied, prepared `Region` to verified Wang decision | `.cm13` parse, copied formula, reduction, copied region, and verified Wang decision |

`wang-solve-verified` is the direct comparison on the same reduced Wang
problem. Region construction happens before the timer. The Boolean oracle is
absent because it accepts a `Formula`, not a `Region`.

The current public reduction coordinator returns both a Python-owned formula
and region after one native parse. The Wang worker uses that public boundary;
the formula copy is therefore outside the timer in the prepared-Region scope
and inside it in the file scope, even though the Wang oracle itself consumes
only the region.

`file-to-verified-decision` gives all four paths the same input file and checks
the same expected SAT or UNSAT result. It intentionally compares different
pipelines: Boolean Z3 decides the original formula directly, while the other
three paths decide its Yang–Zhang region. Absolute end-to-end measurements are
useful, but a ratio between the Boolean and Wang rows is not a solver speedup
claim.

The OpenMP library is excluded because `src/parallel/solver_openmp.c` remains a
build scaffold, not an independent solver implementation.

## Corpus

The runner exposes three cumulative presets:

| Preset | Cases | Purpose |
| --- | --- | --- |
| `smoke` | `pipeline_sat`, `pipeline_unsat` | smallest shared SAT and UNSAT files |
| `standard` | smoke plus `yang_zhang_sat_6`, `yang_zhang_unsat_6` | extended comparison and timeout evidence |
| `scaling` | standard plus the 12-variable SAT and UNSAT cases | explicit scaling and timeout evidence |

The four files under `benchmarks/instances/` materialize exactly the
deterministic six- and twelve-variable formula families already used by the C
benchmark harness. SAT families repeat each disjoint three-variable clause
three times. UNSAT families use the contradictory pair `(x,x,y)` and
`(x,y,y)` for each disjoint variable pair. The runner hashes every input into
each sample record.

These UNSAT inputs are intentionally shallow propagation controls. The smoke
case `(x,x,x)` is immediately impossible under exact-one position counting;
the larger contradictory pairs are rejected after very shallow Wang search.
They do not stand in for a hard UNSAT family requiring deep backtracking.

## Running it

The routine command uses seven fresh samples per engine on the smallest SAT and
UNSAT files, with a 30-second timeout per sample:

```sh
make benchmark-compare
```

The standard and scaling presets are intentionally opt-in because Wang Z3 may
reach the timeout on the six- and twelve-variable regions:

```sh
make build/benchmarks/c/bench_solver shared
uv run --frozen python benchmarks/python/compare_solvers.py \
  --preset standard --samples 7 --iterations 1 \
  --timeout-seconds 120 \
  --c-flags '-std=c17 -Wall -Wextra -Wpedantic -O2' \
  > build/benchmarks/solver-comparison.jsonl
```

Use `make benchmark-compare-smoke` for a quick correctness exercise. It runs
the smallest UNSAT file once through all applicable engine/scope pairs. CI may
run this smoke target, but it must not impose timing or memory thresholds.

Cases, engines, and scopes can also be selected explicitly with repeatable
`--case`, `--engine`, and `--scope` options. `--iterations` repeats the measured
operation inside one worker; it defaults to one so expensive and timed-out
cases remain visible rather than being amortized away.

## Measurement protocol

Every sample runs in a fresh child process. The controller reverses the full
engine/scope order on alternating samples to reduce fixed ordering bias. There
is no hidden warm-up pass. Python imports, shared-library loading, and process
startup occur before the timer and are therefore excluded from elapsed time.
The timeout is an external wall-clock limit around the entire worker, including
startup and preparation, so it can always terminate a stuck or oversized run.

Within `wang-solve-verified`, parsing and region preparation are also outside
the timer. The timed operation is the solver plus validation of a SAT witness;
UNSAT is checked against the expected result. Within
`file-to-verified-decision`, parsing and every model copy or reduction needed by
that path are inside the timer, followed by solving and result validation.

`process_peak_rss_kib` is the high-water resident set for the entire fresh
worker, not only the timed interval. Linux workers read `VmHWM` from
`/proc/self/status`; the portable fallback is `getrusage`. Runtime overhead,
imports, and prepared inputs therefore remain part of memory consumption even
when they are excluded from elapsed time. Memory rows across C, CPython, and Z3
describe whole-process cost and should be interpreted accordingly.

A timed-out worker produces a `TIMEOUT` sample with null timing and memory.
Timeouts are counted but censored from median, minimum, and maximum calculations;
they must be reported alongside completed samples and never converted into an
invented duration or performance ratio.

## JSON Lines records

The first record is `environment` and contains schema/suite versions, commit
and dirty state, host/runtime/compiler identity, recorded C flags, CPU affinity,
selected cases and scopes, sample count, iterations, and timeout. It is followed
by one `sample` record per execution and one `summary` record per
case/engine/scope group.

Raw samples are the evidence of record. Summaries contain completed/timeout
counts, median/minimum/maximum nanoseconds per iteration, and median process
peak RSS. Host load, CPU frequency, affinity, compiler flags, dependency
versions, commit, corpus hashes, and timeout policy must remain fixed before
two runs are treated as a controlled comparison.

## Recorded baseline

[smoke baseline]({{ '/solver_comparison_smoke_2026-08-21/' | relative_url }})
records the first seven-sample, CPU-pinned smoke baseline, including complete
timing ranges, process RSS, correctness results, the shallow-UNSAT explanation,
and the limits on cross-problem interpretation.

The later
[Wang Z3 edge-table report]({{ '/wang_z3_edge_table_2026-08-24/' | relative_url }})
records the oracle's constraint-model refactor and its directly comparable
single-sample before/after check. It does not rewrite the historical baseline
or introduce a timing threshold.
