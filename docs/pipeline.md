---
layout: story
title: The complete pipeline
permalink: /pipeline/
page_class: story
owned_assets: pipeline_overview
description: Component order, data flow, independence, and trust boundaries from a CM1-in-3 formula to checked Wang presentations.
---

# The complete pipeline

Tiling Foundry keeps construction, decision, verification, and presentation as
separate responsibilities. A result is useful only when its source identity,
component boundary, and independent checks remain visible.

{% include narrative-animation.html asset_id="pipeline_overview" animation="/assets/narrative/pipeline-overview/trace.gif" fallback="/assets/narrative/pipeline-overview/frame-07.png" contact_sheet="/assets/narrative/pipeline-overview/contact-sheet.png" alt="The captured formula moves through Boolean Z3, Yang-Zhang reduction, both native solvers, Wang Z3, verification, and presentation." width="1080" height="620" label="observed" caption="One validated v2 capture in fixed component order." source="wang-run-dossier-v2#named-components" %}

## Data flow

The source formula enters two deliberately different paths. The
[Boolean Z3 component]({{ '/components/boolean-z3/' | relative_url }}) decides
the formula directly. Independently, the
[Yang–Zhang component]({{ '/components/yang-zhang/' | relative_url }}) constructs
a finite region over the fixed [tile vocabulary]({{ '/components/tileset/' | relative_url }}).
The reference solver, optimized solver, and Wang Z3 oracle consume that same
hash-bound region and tileset.

| Step | Input | Output | Relationship |
| --- | --- | --- | --- |
| Boolean Z3 | canonical formula | status and optional assignment | independent source-level decision |
| Yang–Zhang | canonical formula | region, tileset, provenance | semantic construction |
| [Reference solver]({{ '/components/reference-solver/' | relative_url }}) | region and tileset | status and optional tiling | executable baseline |
| [Optimized solver]({{ '/components/optimized-solver/' | relative_url }}) | same region and tileset | status and optional tiling | independent invocation of the shared native core |
| [Wang Z3]({{ '/components/wang-z3/' | relative_url }}) | same region and tileset | status and optional model | independent finite-region oracle |
| [Verification]({{ '/components/verification/' | relative_url }}) | returned witnesses and original inputs | named checker receipts | independent cross-check |
| [Visualization]({{ '/components/visualization/' | relative_url }}) | verified square witness | square, generalized, and checked hex views | presentation-only |

## Independence

The reference path remains executable and understandable. The optimized path
retains the same public semantics while selecting six measured private
mechanisms. Boolean Z3 does not call the reduction, and Wang Z3 does not call a
native solver. Independent checkers consume returned assignments or tilings;
they do not trust a raster.

## Trust boundaries

- `SAT` is accepted only with the applicable witness checks.
- `UNSAT` from a solver is a terminal observation, not a standalone certificate.
- `UNKNOWN` is preserved where an oracle can return it; it is never rewritten as UNSAT.
- Trace replay presents recorded semantic events but does not solve again.
- Generalized and hex views are downstream transformations, not new solvers.

The [worked example]({{ '/worked-example/' | relative_url }}) follows one named
SAT source through these boundaries. Maintained APIs and methods remain in the
[reference index]({{ '/reference/' | relative_url }}); measurements and dated
observations remain in [evidence]({{ '/evidence/' | relative_url }}).
