---
layout: story
title: Yang–Zhang construction
permalink: /components/yang-zhang/
page_class: story
component_id: yang-zhang
pipeline_order: 3
primary_asset: region_construction
owned_assets: region_construction
description: The formula-to-region reduction, generalized routing vocabulary, and native construction provenance.
---

# Yang–Zhang construction

## What it is

The native Yang–Zhang builder transforms a validated Cubic Monotone 1-in-3 SAT
formula into one finite simply connected region over the fixed 23 Wang tiles.

## Why it exists

This component owns the semantic bridge from Boolean clauses to boundary-colored
geometry. Solvers remain generic consumers of a `Region`; they do not know
about variables, clauses, gadgets, or the reduction theorem.

## Inputs and outputs

Input is a canonical formula. Output is a caller-owned reduction containing
the region, adjacent-swap trace, and optional immutable provenance. Snapshot
and explanation contracts bind formula, tileset, region, signal, permutation,
and gadget-span identities.

## Mechanism

Variable signals are routed in source order through forwarders and adjacent
crossovers into clause gadgets. The implementation decomposes generalized
tiles into the fixed atomic IDs and constructs the complete exposed boundary
transactionally.

## Primary animation

`region_construction` is a deterministic construction view, not an instrumented
clock or solver trace.

{% include narrative-animation.html asset_id="region_construction" animation="/assets/narrative/region-construction/trace.gif" fallback="/assets/narrative/region-construction/frame-04.png" contact_sheet="/assets/narrative/region-construction/contact-sheet.png" alt="Six frames reveal variable, forwarding, crossover, and clause gadget spans on the same region." width="980" height="390" label="canonical-construction" caption="Native Yang-Zhang gadget spans accumulated over the observed region." source="wang-reduction-explanation-v1" %}

## Position in the pipeline

The builder follows parsing and supplies the shared region to the reference
solver, optimized solver, and Wang Z3 oracle. Boolean Z3 remains a parallel
source-level cross-check; rendering is a removable downstream consumer.

## Observed example

For `pipeline_sat.cm13`, the capture builds the reduction once and shares its
hash-bound formula, tileset, region, and provenance across both native runs and
the Wang oracle.

## Trust boundary

Provenance explains what the native builder constructed. It is not a second
reduction and does not by itself prove satisfiability. Black-box reduction
tests, Boolean agreement, witness correspondence, and independent tiling
verification establish separate obligations.

## Artifacts and references

Read the [reduction note]({{ '/reduction_notes/' | relative_url }}),
[builder contract]({{ '/yang_zhang_builder_design/' | relative_url }}), and
[provenance contract]({{ '/wang-reduction-explanation/' | relative_url }}).
Public ownership begins in `include/wang/yang_zhang.h`.
