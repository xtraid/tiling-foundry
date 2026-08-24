---
layout: page
title: Wang Z3 edge-table model
permalink: /wang_z3_edge_table_2026-08-24/
description: Constraint model, correctness evidence, and before/after smoke measurement for the Wang Z3 edge-table oracle.
section: Cross-engine benchmarks
document_kind: Oracle model report
status: Current implementation
updated: 2026-08-24
nav_order: 30
---

# Wang Z3 edge-table model — 24 August 2026

## Scope and outcome

The Python Wang Z3 oracle still consumes only an immutable `Region` and a
generic immutable tileset. It does not parse formulas, rebuild the
Yang–Zhang reduction, call the native solver, or evaluate Boolean clauses.

The refactored model represents tile membership once per active cell and
represents every active internal adjacency as one shared color term. It
replaces the previous per-adjacency support implications without changing the
public `solve_tiling()` result contract. `SAT`, `UNSAT`, `UNKNOWN`, dense
row-major witnesses, inactive cells, boundary colors, and generic tilesets are
preserved.

## Constraint model

The preceding encoding created one integer tile-ID variable per active cell.
For each east or south adjacency and each tile ID it added an implication from
the source tile to an `Or` of compatible neighbor IDs. On the 444-active-cell
SAT smoke region, 832 internal edges therefore produced 19,136 support
implications before boundary and domain constraints were counted.

The current encoding creates `(N,E,S,W)` integer color terms for every active
cell. Row-major construction reuses the south term of the active cell above as
the current north term and the east term of the active cell to the left as the
current west term. An internal edge is consequently one Z3 term, not two terms
plus an equality and not a replicated tile-support table.

Each active cell receives one finite table-membership constraint:

```text
Or(
    And(Nc == N0, Ec == E0, Sc == S0, Wc == W0),
    And(Nc == N1, Ec == E1, Sc == S1, Wc == W1),
    ...
)
```

Every required boundary color is a direct equality on the corresponding edge
term. Inactive cells receive no terms and do not share constraints across a
hole.

The SMT model does not carry a separate tile-ID variable. After `SAT`, the
four model colors are mapped back to the matching positional tileset ID. The
canonical 23-tile set has 23 distinct edge tuples. A generic tileset may
contain duplicate tuples; because such entries are indistinguishable under
Wang constraints, witness reconstruction currently normalizes them internally
to one equivalent positional ID. This remains a valid witness; the public
contract does not select a specific duplicate or satisfying model.

## Correctness evidence

Focused tests now cover:

- exact object identity for every active horizontal and vertical shared edge;
- semantic independence across an inactive cell with opposite forced colors;
- SAT/UNSAT agreement with exhaustive enumeration on small generic tilesets;
- boundary and adjacency contradictions in both orientations;
- valid positional-ID reconstruction for duplicate edge tuples;
- dense witness validation by the independent Python checker;
- propagation of Z3 `UNKNOWN` without requesting a model.

The shared end-to-end SAT and UNSAT fixtures continue through the independent
checker. No native solver, C verifier, tileset definition, region model, or
Yang–Zhang builder code changed.

## Controlled smoke measurement

The before/after comparison used the same smallest SAT input, one fresh sample
per scope, CPU affinity 2, Python 3.13.5, Z3 4.16.0, and the Ryzen 5 3600
benchmark host. The case contains 451 dense positions and 444 active cells.
Both source states derive from commit `2e4d8a3`; the only measured oracle
mechanism change was replacement of adjacency support implications by the
edge-table model.

```sh
taskset -c 2 uv run --frozen python benchmarks/python/compare_solvers.py \
  --case pipeline_sat --engine python-wang-z3 \
  --scope wang-solve-verified \
  --scope file-to-verified-decision \
  --samples 1 --iterations 1 --timeout-seconds 60 \
  --c-flags '-std=c17 -Wall -Wextra -Wpedantic -O2'
```

| Scope | Support-implication model | Edge-table model | Time change | RSS change |
| --- | ---: | ---: | ---: | ---: |
| `wang-solve-verified` | 10.666394831 s / 88,396 KiB | 2.604701225 s / 87,060 KiB | -75.58% | -1.51% |
| `file-to-verified-decision` | 10.560000602 s / 88,580 KiB | 2.620350503 s / 86,984 KiB | -75.19% | -1.80% |

Every measured run returned `SAT`, produced a complete dense tiling, and
passed the independent checker. The result supports retaining the simpler
edge-table encoding: it removes replicated adjacency tables, materially lowers
the smoke time, and does not purchase the speedup with higher process peak RSS.

## Interpretation and limits

This is a single-sample, host-specific mechanism check, not an asymptotic claim
or a CI threshold. It is deliberately comparable to the immediately preceding
single-sample state; the seven-sample historical cross-engine baseline remains
a record of the older encoding, not a current performance promise.

The oracle is still a general Z3 model and remains much slower than the native
solver on this structured region. The measurement covers one small SAT witness
and says nothing about hard UNSAT behavior or larger scaling presets. Those
presets remain opt-in under the
[comparison protocol]({{ '/solver_comparison_benchmark/' | relative_url }}),
and any broader performance conclusion requires fresh repeated samples.
