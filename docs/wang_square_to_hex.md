---
layout: page
title: Square-to-hex presentation port
permalink: /wang-square-to-hex/
description: Algebra, coordinate convention, inverse proof, and raster boundary for the verified presentation-only square-to-hex port.
section: Architecture and correctness
document_kind: Technical reference
status: Current specification
updated: 2026-08-27
nav_order: 32
---

# Square-to-hex presentation port

## Scope and attribution

This port turns an already selected square Wang presentation into a pointy-top
hexagonal presentation. It is not a solver, a second solution format, or a new
core geometry. The input remains the square-only
[Wang solution v1 contract]({{ '/wang-solution-v1/' | relative_url }}), and the
hexagonal value exists only in renderer memory.

Section 4 and Figure 13 of Sky Basire's 2022 report describe the construction
principle: transfer the four square edge colors and give the two additional
hexagon sides one common color. The report is available through its
[institutional record](https://ir.canterbury.ac.nz/items/0f6603bb-28d2-4012-a1ec-06e0248d1c92),
[DOI](https://doi.org/10.26021/14719), and
[PDF](https://ir.canterbury.ac.nz/bitstreams/c69151f2-cf3b-4158-9f6b-b4e80013e440/download).
Basire cites Karel Culik II's
[*Small Aperiodic Sets of Triangular and Hexagonal Tiles*](https://link.springer.com/chapter/10.1007/978-3-642-60207-8_27)
for the underlying square-tile simulation result.

The exact edge tuple, coordinate convention, deterministic fresh-color rule,
and finite-region bijection below are Tiling Foundry's formalization of that
construction. They are not attributed to either source's diagram notation.

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/square-to-hex/frame-02.png' | relative_url }}">
    <img src="{{ '/assets/images/square-to-hex/trace.gif' | relative_url }}" alt="Verified square-to-hex transformation preserving four source edges and adding the fresh kappa color.">
  </picture>
  <figcaption><strong>Verified transformation.</strong> The pure renderer-side port and its raster-independent checker produce this mapping; the animation itself is not a proof. The <a href="{{ '/assets/images/square-to-hex/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all four stages.</figcaption>
</figure>

## Project convention

The source stores square edges as `(N,E,S,W)`. Its dense row-major coordinates
increase to the east with `x` and to the south with `y`. The port uses
pointy-top axial coordinates

```text
(q,r) = (x,y)
```

and stores hex edges clockwise as `(E,SE,SW,W,NW,NE)`. The corresponding axial
neighbors are:

| Hex side | Neighbor | Square relation |
| --- | --- | --- |
| `E` | `(q+1,r)` | `(x+1,y)`, square `E` |
| `SE` | `(q,r+1)` | `(x,y+1)`, square `S` |
| `SW` | `(q-1,r+1)` | additional axis |
| `W` | `(q-1,r)` | `(x-1,y)`, square `W` |
| `NW` | `(q,r-1)` | `(x,y-1)`, square `N` |
| `NE` | `(q+1,r-1)` | additional axis |

Let `C` be the finite set of all colors in the square tile table. The table is
nonempty, so the renderer chooses the deterministic fresh color

```text
kappa = max(C) + 1.
```

Nonnegative integer colors are unbounded in the v1 contract. Therefore
`kappa` is defined and is not in `C`. Each square tile maps as

```text
H(N,E,S,W) = (E,S,kappa,W,N,kappa)
               E SE  SW    W NW  NE
```

Tile-table order is unchanged, so `tile_id` remains the positional index. The
boundary tuple maps independently as

```text
B(N,E,S,W) = (E,S,null,W,N,null).
```

A null boundary entry for a hole remains null. No constraint is invented on
the added axis; its tile edges are still both `kappa`.

## Equivalence and inverse

The map has a left inverse on its image:

```text
P(E,SE,SW,W,NW,NE) = (NW,E,SE,W).
```

For every square tile `t`, `P(H(t)) = t`. Thus `H` is injective, preserves the
tile-table cardinality, and introduces no tile choice.

Consider two active source positions. At `(x,y)` and `(x+1,y)`, square
east/west matching is

```text
t(x,y).E = t(x+1,y).W.
```

Those positions become axial east/west neighbors, and `H` puts the same two
colors on hex `E` and `W`. At `(x,y)` and `(x,y+1)`, square south/north
matching becomes hex `SE/NW` matching for the same reason. Every active pair
on the third axial direction compares `kappa` with `kappa`, so that axis adds a
tautology and cannot remove a square witness.

Conversely, take a valid hex tiling whose tile table is exactly the image of
`H`. Project every tile with `P`. Hex `E/W` matching gives square `E/W`
matching; hex `SE/NW` matching gives square `S/N` matching; the remaining axis
contains no projected information. This recovers one and only one square
tiling.

The pointwise maps preserve inclusive coordinates, dense row-major indices,
active cells, holes, boundary values, and selected tile IDs. They therefore
form a bijection between square witnesses and witnesses over the image table
on the corresponding axial region. Existence and nonexistence are preserved,
as is the number of witnesses. The serialized v1 format is SAT-only, so an
UNSAT result has no document or renderer invocation; UNSAT preservation is a
property of the reduction, not a claimed JSON feature.

## Independent port checker

`renderer/wang_hex_port.py` contains the pure reducer and checker. It imports
only the Python standard library. The checker does not call the reducer and
does not use pixel coordinates. Before hex rasterization it checks:

- exact coordinate, table, assignment, hole, and boundary preservation;
- all six edges of every mapped tile and freshness of `kappa`;
- the inverse projection for every positional tile ID;
- equality of square and hex matching truth values on both meaningful axes;
- `kappa/kappa` matching on every active pair along the additional axis;
- equality of boundary-matching truth values after direction mapping.

The truth-value comparison is deliberate. If a structurally present input has
an invalid square adjacency, the corresponding hex adjacency remains invalid;
the checker establishes translation equivalence without turning the renderer
into another solution validator. Contract validation and the independent
tiling verifier remain upstream obligations.

## Raster boundary

The existing `renderer/wang_square.py` command remains the only Wang renderer
command. Without a geometry flag it follows the unchanged square path. With
`--hex`, it reduces and checks the same in-memory presentation before composing
hex pixels:

```sh
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-hex.png \
  --hex
```

For hex mode, `--pixels-per-cell s` is the integer axial raster radius. Centers
use

```text
pixel_x = 2*s*q + s*r
pixel_y = (s + floor(s/2))*r.
```

Integer vertices and a normalized bounding box make negative coordinates and
pixel placement deterministic. The same injective palette is extended with
`kappa`; because `kappa` is greater than every square color, existing logical
colors retain their square RGB assignments. Holes use the neutral checkerboard
inside the same pointy-top mask. The committed fixture golden is RGB 337×177
at the default radius and margin.

The raster consumes the checked result but proves nothing about SAT,
adjacency, boundary validity, or solver behavior. It loads no native library or
Z3 module, writes no intermediate hex serialization, and leaves the root
`python/hex/` placeholders untouched.
