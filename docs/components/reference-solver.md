---
layout: story
title: Reference native solver
permalink: /components/reference-solver/
page_class: story
component_id: reference-solver
pipeline_order: 4
primary_asset: reference_trace
owned_assets: reference_trace
description: The executable native baseline, its observed semantic trace, result ownership, and verification boundary.
---

# Reference native solver

## What it is

The reference solver is the deliberately direct native baseline for finite
Wang regions. It remains executable beside the optimized entry point and uses
the same public status and ownership contracts.

## Why it exists

A readable baseline keeps correctness and performance changes comparable.
Optimizations must match this path on the full corpus rather than replace the
only executable statement of the search semantics.

## Inputs and outputs

Input is an immutable `Region`, a tileset, and optional initial domains. Output
is SAT with a caller-owned dense witness, UNSAT, or ERROR. Optional metrics and
bounded traces are separate caller-owned results; ordinary calls allocate no
trace state.

## Mechanism

The solver applies boundary restrictions and local arc propagation, chooses the
next non-singleton cell by row-major minimum remaining values, and explores
choices with iterative depth-first search and an undo trail. Every SAT result
is checked before publication.

## Primary animation

`reference_trace` selects semantic milestones from one complete observed trace.
Unshown visual frames do not mean skipped solver events.

{% include narrative-animation.html asset_id="reference_trace" animation="/assets/narrative/reference-trace/trace.gif" fallback="/assets/narrative/reference-trace/frame-002517.png" contact_sheet="/assets/narrative/reference-trace/contact-sheet.png" alt="Observed reference domain states at root, propagation, decision, search, and result milestones." width="988" height="414" label="observed" caption="Selected semantic milestones from the complete reference trace." source="wang-explain-manifest-v3" %}

## Position in the pipeline

This solver consumes the native reduction. Its result is compared with the
optimized invocation and Wang Z3, then passed to independent witness checks.
The trace is downstream evidence and never feeds search.

## Observed example

The `pipeline_sat.cm13` reference run reaches SAT with a complete trace and a
checked tiling. A separately identified search-UNSAT run is available through
the [dossier index]({{ '/run-dossiers/' | relative_url }}); it is not part of
the SAT story.

## Trust boundary

The solver establishes only its returned decision under its inputs. A trace is
diagnostic, not an UNSAT certificate. The independent verifier, not the trace
renderer, accepts a SAT tiling.

## Artifacts and references

See the [serial solver reference]({{ '/serial_solver_implementation_guide/' | relative_url }}),
[trace contract]({{ '/wang-solver-trace/' | relative_url }}), and
[reference profile]({{ '/solver_reference_profile_2026-08-17/' | relative_url }}).
