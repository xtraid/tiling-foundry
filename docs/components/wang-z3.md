---
layout: story
title: Wang Z3 oracle
permalink: /components/wang-z3/
page_class: story
component_id: wang-z3
pipeline_order: 6
primary_asset: wang_z3
owned_assets: wang_z3
description: The independent finite-region oracle and its project-owned edge-term construction order.
---

# Wang Z3 oracle

## What it is

Wang Z3 is an independent Python oracle for a finite `Region` and immutable
tileset. It returns a dense row-major tiling model when the region is SAT.

## Why it exists

This oracle checks the native decision paths with a different implementation
and constraint engine. It neither parses the source formula nor rebuilds the
Yang–Zhang reduction, so the shared region identity is an explicit boundary.

## Inputs and outputs

Input is the hash-bound region and tileset produced once by the native
construction. Output preserves SAT, UNSAT, or UNKNOWN and an optional dense
model. `z3-encoding-summary-v1` records project-owned term and assertion order,
counts, identity, status, and copied model.

## Mechanism

The model creates `(N,E,S,W)` edge-color terms in row-major order, shares terms
across active internal adjacencies, restricts each cell to a canonical tile
tuple, and applies exposed boundary colors. Its fixed configuration uses one
thread and a fixed random seed.

## Primary animation

`wang_z3` shows the project's edge-term construction and returned result, not
the solver engine's internal search.

{% include narrative-animation.html asset_id="wang_z3" animation="/assets/narrative/wang-z3/trace.gif" fallback="/assets/narrative/wang-z3/frame-03.png" contact_sheet="/assets/narrative/wang-z3/contact-sheet.png" alt="Five frames add edge terms, shared internal edges, tile relations, boundaries, and the copied result." width="940" height="430" label="encoding-order" caption="Project-owned Wang edge-term construction and returned model." source="z3-encoding-summary-v1" %}

## Position in the pipeline

Wang Z3 consumes the same constructed region as both native solvers and joins
them at agreement. It is an independent cross-check, not a fallback or a
producer of hints for either native path.

## Observed example

For `pipeline_sat.cm13`, the oracle returns SAT over the same region and tile
identities as the native runs, and its dense model passes the pure Python
tiling checker.

## Trust boundary

The summary stabilizes project construction order and the copied result only.
It does not claim to expose Z3 branching, propagation, proof search, or debug
events. A rendered frame is not the tiling checker.

## Artifacts and references

See the [Wang Z3 model reference]({{ '/wang_z3_edge_table_2026-08-24/' | relative_url }}),
[comparison protocol]({{ '/solver_comparison_benchmark/' | relative_url }}),
and `python/oracles/tiling_solver.py`.
