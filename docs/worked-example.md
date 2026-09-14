---
layout: story
title: Worked SAT example
permalink: /worked-example/
page_class: story
owned_assets: worked_example, formula
description: One named pipeline_sat.cm13 instance followed from source bytes to independently checked square and hex presentations.
---

# Worked SAT example

This page follows one small three-variable CM1-in-3 SAT instance through the
complete pipeline, from source formula to independently checked presentations.

<details markdown="1">
<summary>Technical provenance</summary>

Source: `tests/instances/pipeline_sat.cm13`. SHA-256:
`3caaa6b29ac988fb4f51cc7071202d83ea1591ba6170e683b6da449cb3641542`.
No initial-domain override is applied. The separate search-UNSAT example is
not spliced into this run.

</details>

{% include narrative-static.html asset_id="worked_example" image="/assets/narrative/pipeline-overview/worked-example.png" alt="An eight-stage overview followed by enlarged Boolean decision, Yang-Zhang construction, six verification receipts, verified square witness, and checked hex presentation panels." width="1080" height="3440" label="observed" caption="Eight-stage overview with readable decision, construction, verification, square-witness, and checked-hex details." source="wang-run-dossier-v2#named-components" %}

[Open the complete worked figure at full size]({{ '/assets/narrative/pipeline-overview/worked-example.png' | relative_url }}).

The opening grid is the component map. The enlarged panels retain the captured
decision, construction, checker interpretation, square witness, and final hex
view at a useful reading size; the component pages own their full explanations.

## Source formula

The parser reads a canonical Cubic Monotone 1-in-3 SAT document with three
variables and three source-order clauses. The snapshot below is bound to those
source bytes; it is not reconstructed from a later tiling.

{% include narrative-static.html asset_id="formula" image="/assets/narrative/formula.png" alt="The parsed CM1-in-3 formula and its source-order clauses." width="796" height="394" label="observed" caption="Parsed formula snapshot for the named canonical source." source="cm13-formula-snapshot-v1" %}

## Decisions and construction

The enlarged decision panel shows the copied Boolean model; the construction
panel shows the source-to-target signal order and final region vocabulary.
The native builder constructs one region, one fixed tileset snapshot, and
explicit construction provenance. Reference, optimized, and Wang Z3 solves
then report SAT over those shared identities. Agreement means equal terminal
status and independently valid witnesses; different valid witnesses need not
be byte-identical.

## Verification and presentation

The enlarged receipt panel distinguishes the six named checks and the copied
native extraction. Only after those checks does the presentation layer render
the enlarged square witness, recognize exact generalized contours, and apply
the checked square-to-hex mapping shown in the final panel.

The milestone sequence links to the owned explanations for the
[tileset]({{ '/components/tileset/' | relative_url }}),
[Boolean Z3]({{ '/components/boolean-z3/' | relative_url }}),
[Yang–Zhang reduction]({{ '/components/yang-zhang/' | relative_url }}),
[reference solver]({{ '/components/reference-solver/' | relative_url }}),
[optimized solver]({{ '/components/optimized-solver/' | relative_url }}),
[Wang Z3]({{ '/components/wang-z3/' | relative_url }}),
[verification]({{ '/components/verification/' | relative_url }}), and
[visualization]({{ '/components/visualization/' | relative_url }}).

Raw durations belong to this capture and environment. They are not a benchmark
or a performance ranking. The [run dossier index]({{ '/run-dossiers/' | relative_url }})
documents the immutable capture boundary, while the
[pipeline page]({{ '/pipeline/' | relative_url }}) separates the general
architecture from this one observed example.
