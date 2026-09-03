---
layout: story
title: Optimized native solver
permalink: /components/optimized-solver/
page_class: story
component_id: optimized-solver
pipeline_order: 5
primary_asset: optimized_trace
owned_assets: optimized_trace, optimized_mechanisms
description: The semantically equivalent serial path, its observed trace, and six separately measured private mechanisms.
---

# Optimized native solver

## What it is

The optimized solver is a second public native entry point over the same Wang
search core. It selects six private serial mechanisms while retaining the
reference path's inputs, outputs, search meaning, and mandatory verification.

## Why it exists

Performance work needs isolated mechanisms, direct counters, and a stable
baseline. Keeping this path beside the reference solver makes equivalence and
regressions testable without turning measured choices into universal claims.

## Inputs and outputs

The input and public result contracts match the reference path: immutable
region and tileset, optional initial domains, SAT with caller-owned witness,
UNSAT, or ERROR. Optional metrics count direct work and storage; optional trace
records the actual optimized invocation.

## Mechanism

The retained mechanisms are a geometrically growing DFS stack, omission of
non-consumable initial trail entries, transfer of verified SAT domains,
byte-wise support tables, queue deduplication, and a private lazy MRV index.
Each has separate evidence and preserves row-major tie breaking.

## Primary animation

`optimized_trace` is the primary observed asset. `optimized_mechanisms` is a
secondary didactic overview; it makes no timing or speedup claim.

{% include narrative-animation.html asset_id="optimized_trace" animation="/assets/narrative/optimized-trace/trace.gif" fallback="/assets/narrative/optimized-trace/frame-002562.png" contact_sheet="/assets/narrative/optimized-trace/contact-sheet.png" alt="Observed optimized domain states at root, propagation, decision, search, and result milestones." width="988" height="414" label="observed" caption="Selected semantic milestones from the complete optimized trace." source="wang-explain-manifest-v3" %}

{% include narrative-animation.html asset_id="optimized_mechanisms" animation="/assets/narrative/optimized-mechanisms/trace.gif" fallback="/assets/narrative/optimized-mechanisms/frame-06.png" contact_sheet="/assets/narrative/optimized-mechanisms/contact-sheet.png" alt="Seven didactic frames contrast the reference baseline with six measured optimized mechanisms." width="960" height="500" label="didactic" caption="The six retained serial mechanisms, including the lazy MRV index." source="wang-optimized-mechanisms-v1" %}

## Position in the pipeline

This is an independent invocation on the same reduction consumed by the
reference solver and Wang Z3. Its result joins them at agreement and
verification; neither trace nor metrics are used as solver input.

## Observed example

The `pipeline_sat.cm13` optimized run returns a checked SAT witness with a
complete trace. The separately named search-UNSAT capture exercises conflict,
backtrack, and exhaustion without becoming a second canonical story.

## Trust boundary

Correctness comes from status equivalence, checked witnesses, differential
tests, and the independent verifier. The observed trace describes one run;
the didactic mechanism asset does not establish performance. Dated reports
remain scoped to their corpus and environment.

## Artifacts and references

Start with the [optimization methodology]({{ '/solver_performance_scope/' | relative_url }})
and [serial solver reference]({{ '/serial_solver_implementation_guide/' | relative_url }}).
The six accepted reports are collected in the
[evidence index]({{ '/evidence/' | relative_url }}).
