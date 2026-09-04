---
layout: default
title: Tiling Foundry
permalink: /
page_kind: home
page_class: story
owned_assets: home_preview
description: A research software laboratory for finite Wang tilings and inspectable solver design.
---

<section class="home-hero layout-reading" data-wang-sections data-content-column>
  <p class="eyebrow">Finite tilings / inspectable decisions</p>

  <h1>Tiling Foundry</h1>

  <p>
    Follow one Cubic Monotone 1-in-3 SAT instance through independent Boolean
    and Wang models, the Yang–Zhang construction, two native solver paths,
    explicit verification, and presentation-only views.
  </p>

  <div class="story-actions">
    <a class="text-link" href="{{ '/pipeline/' | relative_url }}">Explore the pipeline</a>
    <a class="text-link" href="{{ '/worked-example/' | relative_url }}">Inspect the worked example</a>
  </div>
</section>

<section class="home-section layout-presentation" id="project-map" data-content-column>
  <div class="section-heading">
    <p class="eyebrow">Project map</p>
    <h2>One construction, several independent checks</h2>
  </div>

  <ol class="pipeline-links">
    <li>The fixed <a href="{{ '/components/tileset/' | relative_url }}">tile vocabulary</a> supplies one immutable domain.</li>
    <li><a href="{{ '/components/boolean-z3/' | relative_url }}">Boolean Z3</a> checks the source formula.</li>
    <li><a href="{{ '/components/yang-zhang/' | relative_url }}">Yang–Zhang</a> constructs one finite Wang region.</li>
    <li><a href="{{ '/components/reference-solver/' | relative_url }}">Reference</a> and <a href="{{ '/components/optimized-solver/' | relative_url }}">optimized</a> native paths solve the same region.</li>
    <li><a href="{{ '/components/wang-z3/' | relative_url }}">Wang Z3</a> provides a separate finite-region oracle.</li>
    <li><a href="{{ '/components/verification/' | relative_url }}">Independent checkers</a> validate returned witnesses.</li>
    <li><a href="{{ '/components/visualization/' | relative_url }}">Visualization</a> follows verification and changes no decision.</li>
  </ol>
</section>

<section class="home-section layout-presentation" id="verified-output" data-content-column>
  <div class="section-heading">
    <p class="eyebrow">Verified output</p>
    <h2>A selected result, not a visual proof</h2>
  </div>

  {% include narrative-static.html asset_id="home_preview" image="/assets/narrative/pipeline-overview/home-preview.png" alt="A compact square Wang witness preview for the captured SAT source." width="760" height="430" label="observed" caption="Selected verified SAT square output for the captured instance." source="wang-solution-v1" %}

  <p class="home-section__prose">
    The image is downstream of an independently checked square witness. Read
    the <a href="{{ '/worked-example/' | relative_url }}">named example</a> for
    its source identity and the
    <a href="{{ '/components/visualization/' | relative_url }}">visualization component</a>
    for the transformation boundary.
  </p>
</section>

<section class="home-section layout-reading" id="reading-path" data-content-column>
  <div class="section-heading">
    <p class="eyebrow">Reading path</p>
    <h2>Story, contracts, evidence</h2>
  </div>

  <p class="home-section__prose">
    Use the <a href="{{ '/pipeline/' | relative_url }}">pipeline story</a> to
    understand responsibilities, the <a href="{{ '/reference/' | relative_url }}">reference index</a>
    for maintained contracts and history, and the
    <a href="{{ '/evidence/' | relative_url }}">evidence index</a> for dated,
    source-bound measurements. Reproducible captures remain separately indexed
    under <a href="{{ '/run-dossiers/' | relative_url }}">run dossiers</a>.
  </p>
</section>
