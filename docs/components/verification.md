---
layout: story
title: Independent verification
permalink: /components/verification/
page_class: story
component_id: verification
pipeline_order: 7
primary_asset: verification
owned_assets: verification
description: Named assignment and tiling checks, witness correspondence, and the exact claims those checks establish.
---

# Independent verification

## What it is

Verification is a set of pure, named checks over returned assignments and
tilings. It is separate from solver success paths and from every renderer.

## Why it exists

A solver's SAT status is not enough to publish a witness. Independent checks
re-evaluate the source clauses, tile compatibility, exposed boundary colors,
and Boolean–Wang correspondence without trusting internal solver state.

## Inputs and outputs

Inputs are the canonical formula, shared region and tileset, returned Boolean
assignment or Wang tiling, and the reduction provenance needed by the witness
bridge. Each receipt records checker name, whether it ran, pass/fail, and the
witness identity. Witness-only checks are not applicable for UNSAT.

## Mechanism

The Boolean checker requires exactly one true variable in every source clause.
The tiling checker validates every active cell, internal edge, inactive cell,
and exposed boundary. Native witnesses also pass through the independent
assignment extraction bridge before their assignments are checked.

## Primary animation

`verification` presents the six receipts already captured from the named
checkers. It does not rerun or replace them.

{% include narrative-animation.html asset_id="verification" animation="/assets/narrative/verification/trace.gif" fallback="/assets/narrative/verification/frame-05.png" contact_sheet="/assets/narrative/verification/contact-sheet.png" alt="Six frames report Boolean, native, and Wang Z3 witness checks without rerunning a verifier." width="960" height="500" label="observed" caption="The six named independent checker records from the captured run." source="wang-run-dossier-v2#verification" %}

## Position in the pipeline

Verification follows all four decision results and precedes witness
presentation. It receives semantic artifacts, not PNGs. A failed check aborts
the captured pipeline instead of being presented as an alternate outcome.

## Observed example

The `pipeline_sat.cm13` capture records passing checks for the Boolean Z3
assignment, reference tiling and extracted assignment, optimized tiling and
extracted assignment, and Wang Z3 tiling.

## Trust boundary

Passing receipts establish validity of the named SAT witnesses under their
inputs. They do not prove that every implementation is bug-free, turn an UNSAT
trace into a certificate, or make a raster authoritative.

## Artifacts and references

Read the [witness correspondence]({{ '/witness_correspondence/' | relative_url }}),
[solution contract]({{ '/wang-solution-v1/' | relative_url }}), and
[serial solver reference]({{ '/serial_solver_implementation_guide/' | relative_url }}).
The pure Python checkers live in `python/oracles/witness_check.py` and
`python/oracles/tiling_check.py`.
