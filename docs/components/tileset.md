---
layout: story
title: Tile vocabulary
permalink: /components/tileset/
page_class: story
component_id: tileset
pipeline_order: 1
primary_asset: generalized_sheet
owned_assets: generalized_sheet, atomic_legend
description: The fixed 23 atomic Wang tiles, exact 14 generalized tiles, edge colors, matching rule, and stable identifiers.
---

# Tile vocabulary

## What it is

The project uses one fixed table of 23 positional Wang tiles. Fourteen named
generalized tiles describe exact rectangular groupings of those atomic IDs for
explaining the Yang–Zhang construction.

## Why it exists

Solvers need a small, immutable vocabulary with unambiguous edge colors and
identifiers. The generalized view helps people recognize gadgets, but it does
not create a second tileset or change the atomic domain seen by a solver.

## Inputs and outputs

The atomic input is the compiled `TILESET`; its snapshot contract records IDs
and `(N,E,S,W)` colors. The generalized specification maps each of 14 shapes to
an exact arrangement of those 23 IDs. It outputs presentation metadata only,
with no SAT, UNSAT, or UNKNOWN status.

## Mechanism

Two neighboring square tiles match when their touching edge colors are equal.
Rotation and reflection are not allowed. The generalized recognizer checks the
entire atomic pattern before drawing a contour, so a partial resemblance is
never promoted to a generalized occurrence.

## Primary animation

`generalized_sheet` is deliberately static: a tile vocabulary has no execution
timeline to animate. The canonical sheet is the primary reduced-motion-safe
asset, followed by its atomic legend.

{% include narrative-static.html asset_id="generalized_sheet" image="/assets/narrative/generalized-tiles/sheet.png" alt="A sheet of fourteen Yang-Zhang generalized tiles with internal seams and atomic identifiers." width="908" height="1146" label="canonical-construction" caption="The exact 14 generalized tiles decomposed into 23 positional atomic IDs." source="wang-generalized-tiles-v1+wang-tileset-snapshot-v1" %}

{% include narrative-static.html asset_id="atomic_legend" image="/assets/narrative/generalized-tiles/atomic-legend.png" alt="A semantic legend for twenty-three positional Wang tiles and their edge colors." width="1296" height="782" label="canonical-construction" caption="All 23 atomic IDs with symbolic paper colors and generalized roles." source="wang-generalized-tiles-v1+wang-tileset-snapshot-v1" %}

## Position in the pipeline

The vocabulary is an immutable input to region construction and all three Wang
decision paths. Generalized labels flow only to explanation and visualization;
they are not semantic solver input.

## Observed example

The named `pipeline_sat.cm13` capture binds the same tileset identity into the
region, both native trace manifests, Wang Z3 summary, solution, and rendered
views. The displayed sheet is canonical construction data, not an observed
solver trace.

## Trust boundary

The tile table and matching rule define local compatibility. They do not prove
that a region is tileable, that a reduction is correct, or that a rendered
witness is valid. Those claims belong to construction tests, solvers, and the
independent verifier.

## Artifacts and references

See the [static snapshot contract]({{ '/wang-explainability-snapshots/' | relative_url }}),
the [reduction note]({{ '/reduction_notes/' | relative_url }}), and the
[Yang–Zhang builder contract]({{ '/yang_zhang_builder_design/' | relative_url }}).
The public C table is defined in `include/wang/tile.h` and `src/core/tile.c`.
