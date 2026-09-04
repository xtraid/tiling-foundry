---
layout: story
title: Worked SAT example
permalink: /worked-example/
page_class: story
owned_assets: worked_example, formula
description: One named pipeline_sat.cm13 instance followed from source bytes to independently checked square and hex presentations.
---

# Worked SAT example

This page follows only `tests/instances/pipeline_sat.cm13`. Its SHA-256 is
`3caaa6b29ac988fb4f51cc7071202d83ea1591ba6170e683b6da449cb3641542`.
No initial-domain override is applied. The separate search-UNSAT example is
not spliced into this run.

{% include narrative-static.html asset_id="worked_example" image="/assets/narrative/pipeline-overview/worked-example.png" alt="Eight static panels follow the captured source from formula to checked presentation." width="1080" height="940" label="observed" caption="Static t0 through tn component milestones for one SAT run." source="wang-run-dossier-v2#named-components" %}

## Source formula

The parser reads a canonical Cubic Monotone 1-in-3 SAT document with three
variables and three source-order clauses. The snapshot below is bound to those
source bytes; it is not reconstructed from a later tiling.

{% include narrative-static.html asset_id="formula" image="/assets/narrative/formula.png" alt="The parsed CM1-in-3 formula and its source-order clauses." width="796" height="394" label="observed" caption="Parsed formula snapshot for the named canonical source." source="cm13-formula-snapshot-v1" %}

## Decisions and construction

Boolean Z3 returns SAT with a checked assignment. The native builder constructs
one region, one fixed tileset snapshot, and explicit construction provenance.
Reference, optimized, and Wang Z3 solves then report SAT over those shared
identities. Agreement means equal terminal status and independently valid
witnesses; different valid witnesses need not be byte-identical.

## Verification and presentation

Six named checker records cover the Boolean assignment, both native tilings,
the assignments extracted through the witness correspondence, and the Wang Z3
tiling. Only after those checks does the presentation layer render the square
witness, recognize exact generalized contours, and apply the independently
checked square-to-hex mapping.

Raw durations belong to this capture and environment. They are not a benchmark
or a performance ranking. The [run dossier index]({{ '/run-dossiers/' | relative_url }})
documents the immutable capture boundary, while the
[pipeline page]({{ '/pipeline/' | relative_url }}) separates the general
architecture from this one observed example.
