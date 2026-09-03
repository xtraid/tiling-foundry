---
layout: story
title: Boolean Z3 oracle
permalink: /components/boolean-z3/
page_class: story
component_id: boolean-z3
pipeline_order: 2
primary_asset: boolean_z3
owned_assets: boolean_z3
description: The independent source-formula oracle and its project-owned constraint construction order.
---

# Boolean Z3 oracle

## What it is

Boolean Z3 is an independent oracle for the canonical Cubic Monotone 1-in-3
SAT formula. It decides the source model directly and returns an assignment
when the result is SAT.

## Why it exists

The oracle supplies a decision path that does not depend on the Yang–Zhang
builder, Wang region, native solver, or renderer. Agreement across that boundary
is stronger evidence than asking one implementation to check itself.

## Inputs and outputs

Input is the immutable canonical formula. Output preserves SAT, UNSAT, or
UNKNOWN and, for SAT, a Boolean assignment copied from the model. A closed
`z3-encoding-summary-v1` document records source identity, project-owned
assertion order, counters, status, and optional assignment.

## Mechanism

The adapter creates one Boolean variable per source variable and adds exactly
one constraint for each three-variable clause in source order. Its fixed Z3
configuration uses one thread and a fixed random seed.

## Primary animation

`boolean_z3` shows only project-owned encoding order and the returned result.

{% include narrative-animation.html asset_id="boolean_z3" animation="/assets/narrative/boolean-z3/trace.gif" fallback="/assets/narrative/boolean-z3/frame-02.png" contact_sheet="/assets/narrative/boolean-z3/contact-sheet.png" alt="Four frames add Boolean variables and source-order exactly-one clauses before showing the copied result." width="940" height="430" label="encoding-order" caption="Project-owned Boolean constraint construction and returned assignment." source="z3-encoding-summary-v1" %}

## Position in the pipeline

This branch starts at the source formula and meets the Wang decision paths only
at the agreement boundary. It is an independent cross-check, not a predecessor
that supplies domains or hints to the native solvers.

## Observed example

For `pipeline_sat.cm13`, Boolean Z3 returns SAT and the independent assignment
checker accepts the copied assignment. The asset is bound to the same formula
hash shown on the [worked example]({{ '/worked-example/' | relative_url }}).

## Trust boundary

The summary establishes which constraints the project asked Z3 to construct
and what result was copied back. It does not expose or stabilize Z3's internal
branching, propagation, proof, or debug trace.

## Artifacts and references

The implementation is in `python/oracles/boolean_solver.py`; encoding summaries
are defined by `schemas/z3-encoding-summary-v1.schema.json`. See the
[comparison protocol]({{ '/solver_comparison_benchmark/' | relative_url }}) and
[verification component]({{ '/components/verification/' | relative_url }}).
