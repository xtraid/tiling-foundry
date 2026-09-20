---
layout: default
title: Tiling Foundry
permalink: /
page_kind: home
page_class: story
owned_assets: home_preview
description: From a CM1-in-3 formula to a region over 23 Wang tiles, checked solutions, and a reproducible PDF dossier.
---

<section class="home-hero layout-reading" data-wang-sections data-content-column>
  <p class="eyebrow">Finite tilings / inspectable decisions</p>

  <h1>Tiling Foundry</h1>

  <p>
    Can a region be tiled using a fixed set of 23 Wang tiles? Tiling Foundry
    turns a Cubic Monotone 1-in-3 SAT formula into such a region using the
    Yang–Zhang construction. Four decision paths compare results, separate
    checkers validate SAT witnesses, and a PDF dossier records the run.
  </p>

  <div class="story-actions">
    <a class="text-link" href="{{ '/run-dossiers/' | relative_url }}">Run the demo</a>
    <a class="text-link" href="{{ '/presentazione/' | relative_url }}">Follow the technical tour</a>
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
    <li>The fixed <a href="{{ '/components/tileset/' | relative_url }}">tile vocabulary</a> contains the 23 tiles used by every Wang solver.</li>
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
    <h2>A checked tiling from one SAT run</h2>
  </div>

  {% include narrative-static.html asset_id="home_preview" image="/assets/narrative/pipeline-overview/home-preview.png" alt="A compact square Wang witness preview for the captured SAT source." width="1520" height="860" label="observed" caption="Selected verified SAT square output for the captured instance." source="wang-solution-v1" %}

  <p class="home-section__prose">
    Independent checkers validated the square tiling shown here. Read
    the <a href="{{ '/worked-example/' | relative_url }}">named example</a> for
    its input and checks, and the
    <a href="{{ '/components/visualization/' | relative_url }}">visualization component</a>
    for the square, generalized, and hex views of that same witness.
  </p>
</section>

<section class="home-section layout-reading" id="reading-path" data-content-column>
  <div class="section-heading">
    <p class="eyebrow">Reading path</p>
    <h2>Story, contracts, evidence</h2>
  </div>

  <p class="home-section__prose">
    Use the <a href="{{ '/pipeline/' | relative_url }}">pipeline story</a> to
    follow the input through each component, the
    <a href="{{ '/reference/' | relative_url }}">reference index</a>
    for specifications and implementation guides, and the
    <a href="{{ '/evidence/' | relative_url }}">evidence index</a> for measurements
    with their dates, inputs, and limits. The
    <a href="{{ '/run-dossiers/' | relative_url }}">dossier guide</a>
    explains how to run your own input and inspect the recorded result.
  </p>
</section>
