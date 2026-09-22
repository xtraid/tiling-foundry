---
layout: story
title: Worked SAT example
permalink: /worked-example/
page_class: story
owned_assets: worked_example, formula
description: One named pipeline_sat.cm13 instance followed from source bytes to independently checked square and hex presentations.
---

# Worked SAT example

The input `pipeline_sat.cm13` has three variables and three clauses. All four
engines report SAT, and the returned witnesses pass their independent checks.
This page follows that one run from formula to square tiling and hex view.
The [named-case command]({{ '/run-dossiers/#named-cases' | relative_url }})
reproduces the same input through the pipeline.

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

Each clause requires exactly one true occurrence. The clauses are
`(x1,x1,x2)`, `(x1,x2,x3)`, and `(x2,x3,x3)`. The assignment
**x1 = 0, x2 = 1, x3 = 0** satisfies all three: each contains one true `x2`.
The repeated occurrences count separately.

The parser's snapshot below preserves the source clause order and is bound to
the original file's bytes. It is not reconstructed from a later tiling.

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

For the mechanism behind each step, read the component pages for the
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
