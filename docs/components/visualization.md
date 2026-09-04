---
layout: story
title: Verified visualization
permalink: /components/visualization/
page_class: story
component_id: visualization
pipeline_order: 8
primary_asset: witness_presentation
owned_assets: witness_presentation, square_presentation, generalized_presentation, hex_presentation
description: Square witness rendering, exact generalized overlays, and the checked presentation-only square-to-hex transformation.
---

# Verified visualization

## What it is

Visualization is the removable downstream layer that renders a verified square
Wang witness, recognizes exact generalized shapes, and produces a checked
pointy-top hex presentation.

## Why it exists

Dense solution arrays are precise but difficult to inspect. These views expose
tile IDs, boundaries, generalized gadget structure, and the square-to-hex
correspondence without moving correctness into pixels.

## Inputs and outputs

Input is a validated `wang-solution-v1` square witness and the canonical
generalized specification. Outputs are raster presentations only. The hex view
has a raster-independent inverse check and remains a one-to-one transformation
of the square witness, never a separate solution schema.

## Mechanism

The square renderer draws the stored active cells and edges. Generalized
recognition accepts only exact atomic patterns. The hex port maps `(x,y)` to
pointy-top axial `(q,r)`, preserves the four source edges, and assigns one fresh
color to the two additional axes.

## Primary animation

`witness_presentation` moves from the verified square witness through exact
generalized recognition to the checked hex port.

{% include narrative-animation.html asset_id="witness_presentation" animation="/assets/narrative/presentation/trace.gif" fallback="/assets/narrative/presentation/frame-03.png" contact_sheet="/assets/narrative/presentation/contact-sheet.png" alt="Four frames move from the verified square witness through generalized recognition to the checked hex presentation." width="1080" height="620" label="verified-transformation" caption="Verified square witness, exact generalized overlay, and checked hex port." source="wang-solution-v1+wang-generalized-tiles-v1+checked-square-to-hex" %}

## Position in the pipeline

Presentation follows independent SAT verification. No rendered output is fed
back to a solver, oracle, reduction, or checker. Removing this layer leaves
all semantic decisions and witness validation intact.

## Observed example

All three views below derive from the same checked `pipeline_sat.cm13` square
witness.

{% include narrative-static.html asset_id="square_presentation" image="/assets/narrative/presentation/square.png" alt="The complete square Wang witness for the captured SAT source." width="1538" height="422" label="observed" caption="The independently verified square witness with atomic IDs and boundaries." source="wang-solution-v1" %}

{% include narrative-static.html asset_id="generalized_presentation" image="/assets/narrative/presentation/generalized.png" alt="The square witness grouped into exact Yang-Zhang generalized tile occurrences." width="1616" height="430" label="canonical-construction" caption="Exact generalized contours over the same verified square witness." source="wang-solution-v1+wang-generalized-tiles-v1" %}

{% include narrative-static.html asset_id="hex_presentation" image="/assets/narrative/presentation/hex.png" alt="A pointy-top hex presentation preserving the square witness cells, edges, and boundary." width="3171" height="615" label="verified-transformation" caption="The checked Basire/Culik square-to-hex port of the same witness." source="wang-solution-v1+checked-square-to-hex" %}

## Trust boundary

The square witness contract and independent tiling verifier establish SAT
witness validity. The generalized recognizer and square-to-hex checker establish
their transformation relationships. None of the PNG or GIF files is itself a
proof or an independent solver result.

## Artifacts and references

See the [snapshot views]({{ '/wang-explainability-snapshots/' | relative_url }}),
[square solution contract]({{ '/wang-solution-v1/' | relative_url }}), and
[square-to-hex reference]({{ '/wang-square-to-hex/' | relative_url }}).
