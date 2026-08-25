---
layout: page
title: Wang solution v1 data contract
permalink: /wang-solution-v1/
description: Versioned JSON contract and independent semantic checks for square Wang SAT witnesses.
section: Architecture and correctness
document_kind: Data contract
status: Current specification
updated: 2026-08-25
nav_order: 31
---

# Wang solution v1 data contract

## Scope

`wang-solution-v1` is the boundary between a producer of a verified square
Wang tiling and downstream tools such as a renderer. It is a SAT-only data
contract: `status` is always `SAT`, `geometry` is always `square`, and every
active position selects one tile. UNSAT and UNKNOWN outcomes are not solution
documents.

The format contains no native pointers, solver domains, search traces,
Yang–Zhang swap data, renderer assets, or hexagonal coordinates. A consumer
can validate and inspect the fixture without loading the native library.

The machine-readable structural definition is
`schemas/wang-solution-v1.schema.json`. The dependency-free semantic validator
is `python/formats/wang_solution.py`, and the representative golden document is
`tests/fixtures/wang_solution_v1_square_sat.json`.

## Fields and ordering

The top-level fields are closed and have these meanings:

| Field | Contract |
| --- | --- |
| `schema` | Literal `wang-solution-v1`. |
| `status` | Literal `SAT`; non-SAT results have no v1 solution document. |
| `geometry` | Literal `square`. |
| `bounds` | Inclusive `min_x_inclusive`, `min_y_inclusive`, `max_x_inclusive`, and `max_y_inclusive` coordinates. |
| `tile_table` | Canonical positional table from `tile_id` to the integer colors `N`, `E`, `S`, and `W`. |
| `cells` | Dense row-major tile IDs; JSON `null` marks a hole. |
| `boundary` | Dense row-major boundary constraints; a hole has a null entry, while an active cell has nullable `N`, `E`, `S`, and `W` colors. |
| `metadata` | Arbitrary JSON object that is explicitly non-semantic. |

The inclusive width and height are:

```text
width  = max_x_inclusive - min_x_inclusive + 1
height = max_y_inclusive - min_y_inclusive + 1
```

Both dense arrays therefore have `width * height` entries. Array index `i`
maps to local `(i % width, i // width)` and absolute coordinates
`(min_x_inclusive + i % width, min_y_inclusive + i // width)`. Coordinate
offsets do not change adjacency.

`tile_table[i].tile_id` must equal `i`, so IDs are unique, consecutive, and
canonical. Every active `cells` entry indexes that table. Edge order is always
`(N,E,S,W)` even though JSON stores the four names explicitly.

An active boundary entry always has all four direction names. A null color
means no boundary constraint. Constraints are legal only on an exposed side:
the neighboring coordinate lies outside the inclusive bounds or is a hole.
The color must equal the selected tile edge. Boundary constraints do not
replace ordinary east/west and south/north matching between active cells.

## Structural and semantic guarantees

The JSON Schema establishes only properties local to one JSON value:

- exact top-level and nested member names;
- literal schema, status, and geometry values;
- object and array shapes;
- integer, null, and nonnegative-color types;
- the presence of all four named directions;
- an object, but no correctness meaning, for `metadata`.

JSON Schema alone does not establish relationships between separate fields.
The standard-library validator first mirrors the structural checks and then
establishes the cross-field semantics:

- inclusive minima do not exceed inclusive maxima;
- both dense arrays have exactly the bounds area;
- tile IDs equal their canonical positions and all cell references exist;
- holes and active cells have the corresponding boundary representation;
- constraints occur only on exposed edges and match selected tile colors;
- every active horizontal and vertical adjacency has equal colors.

Passing only the structural schema is not a correctness claim.
`validate_wang_solution()` is transport and contract validation: it establishes
the internal consistency of the serialized witness, but it is neither a solver
nor the independent application verifier. The integration boundary must run
the independent verifier before presenting a solution as correct.

The renderer remains a presentation-only consumer. It must not import this
formats module, replace the independent verifier, or decide correctness from a
successful render. `load_wang_solution()` additionally rejects malformed JSON,
duplicate object members, and non-finite numeric extensions accepted by some
JSON parsers.

## Metadata boundary

`metadata` may carry producer names, display labels, timestamps, or similar
diagnostics. Its contents must never select a tile, change coordinates,
override a boundary color, affect SAT status, or be required to reproduce the
tiling. Semantic validation deliberately ignores the entire object after
checking that it contains JSON values.

## Versioning

V1 is closed: unknown structural fields are rejected. A breaking change to
geometry, coordinate meaning, tile identity, dense ordering, boundary
semantics, or correctness rules requires a new schema name and a separate
validator. Non-semantic producer or presentation data belongs in `metadata`;
placing it there does not expand the correctness contract.

The golden fixture spans inclusive bounds `[-1,2]` through `[2,4]`: twelve
dense positions, ten active cells, and two holes. Its complete 23-entry table
is tested for exact `(N,E,S,W)` parity with the canonical Python `TILESET`, and
targeted mutations exercise every cross-field rejection above.
