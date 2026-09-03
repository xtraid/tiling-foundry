---
layout: page
title: Static pipeline snapshots and explainable Wang views
permalink: /wang-explainability-snapshots/
page_class: reference
description: Versioned formula, tileset, and unassigned-region snapshots consumed by the isolated Wang renderer.
section: Architecture and correctness
document_kind: Data and rendering contract
status: Current implementation
updated: 2026-08-26
nav_order: 33
---

# Static pipeline snapshots and explainable Wang views

The pipeline can export its state after parsing and region construction without
running a solver. The isolated renderer turns that state into three diagnostic
views: the parsed formula, the canonical tile sheet, and the unassigned region
with the formula beside it. A verified solution can additionally be rendered
with colored edge bands, tile IDs, emphasized boundary constraints, and a
palette legend.

These views explain data that already exists at a module boundary. They do not
add presentation fields to `Formula` or `Region`, expose native pointers, or
make a PNG part of the correctness argument.

## Contracts and identity

The exporter writes four closed JSON documents:

| Schema | Meaning |
| --- | --- |
| `cm13-formula-snapshot-v1` | Source basename and digest, ordered clauses, and all three variable positions, including repeats |
| `wang-tileset-snapshot-v1` | Canonical positional tile IDs and their square `N,E,S,W` colors |
| `wang-region-snapshot-v1` | Inclusive bounds, dense active mask, exposed boundary constraints, and no assignment |
| `wang-explain-manifest-v1` | Stage identity plus a basename, schema, and full SHA-256 digest for each artifact |

The manifest is installed atomically only after its content-addressed artifacts
have been installed. Both the producer and the renderer reject duplicate JSON
members, non-finite numbers, unknown fields, invalid types, path traversal,
hash drift, mismatched formula identity, and region colors absent from the
referenced tileset.

The committed example was produced from `tests/instances/pipeline_sat.cm13` and
lives in `tests/fixtures/pipeline_sat_explain/`. It is data, not a hand-edited
diagram.

## Export from the real construction pipeline

Build the shared native library, then parse and reduce one formula:

```sh
make shared
uv run --frozen python tools/export_pipeline_snapshots.py \
  tests/instances/pipeline_sat.cm13 \
  /tmp/pipeline-sat-explain/manifest.json
```

The command loads the formula and constructs the real Yang–Zhang `Region`
through the scoped native adapter. It prints the manifest and three generated
artifact paths. It performs no solving.

## Render each static stage

From `renderer/`, pass the manifest to the existing Wang command and select a
view:

```sh
uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/formula.png --view formula

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/tileset-square.png --view tileset

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/region-square.png --view region
```

The tile sheet and region also accept the explicit `--hex` flag. Their hex
data is not stored in JSON: the renderer applies the same pure Basire/Culik
port and raster-independent checker used for verified solutions.

```sh
uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/tileset-hex.png --view tileset --hex

uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_explain/manifest.json \
  output/region-hex.png --view region --hex
```

The region view deliberately contains no tiles: pale cells are active
positions, crossed cells are outside the region, and colored bands are exposed
boundary constraints. The adjacent formula panel states exactly which parsed
formula the region simulates.

## Render the final verified witness

The default solution image remains byte-for-byte compatible. Explainability is
opt-in:

```sh
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/solution-explain.png --explain

uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/solution-explain-hex.png --explain --hex
```

Every tile shows its positional ID. Each logical edge color has a deterministic
RGB band, exposed constraints receive a heavier outer stroke, and the legend
retains the numeric color identity. The hex view also labels the fresh
presentation color `kappa = max(C) + 1`.

## Correctness and current scope

The static contracts stop at the constructed region. They contain neither
solver events nor a partial assignment. Deterministic event traces, replayed
partial states, and algorithm-specific ordering require a separate trace
contract because native DFS and Z3 do not expose the same kind of step.

The next construction boundary is implemented separately by the
[reduction explanation contract]({{ '/wang-reduction-explanation/' | relative_url }}).
Its opt-in manifest v2 adds native-produced signals, adjacent-swap replay, and
gadget spans while leaving this manifest v1 and the generic `Region` unchanged.

The producer is standard-library-only and depends on copied immutable models.
The renderer independently consumes the JSON without importing `libwang.so`,
native adapters, or Z3. Golden PNGs cover all five static geometry/view pairs
and both explainable final-solution modes. The old square and hex solution
goldens remain unchanged when `--explain` is absent.

Rendering still does not prove SAT, region validity, or witness validity. Those
obligations remain with construction tests, the independent verifier, the
solution exporter, and the square-to-hex checker described by their respective
contracts.
