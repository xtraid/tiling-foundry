---
layout: default
title: Tiling Foundry
page_kind: home
description: A research software laboratory for finite Wang tilings and inspectable solver design.
---

<section class="home-hero layout-reading" data-wang-sections data-content-column>
  <p class="eyebrow">Finite tilings / algorithm laboratory</p>

  <h1>Tiling Foundry</h1>

  <p>
    Tiling Foundry turns the Yang–Zhang reduction into an inspectable software
    pipeline. Construction, solving, verification, witness correspondence, and
    measurement remain separate so that each result can be audited rather than
    merely observed.
  </p>

  <a class="text-link" href="#documentation">Explore the documentation</a>
</section>

<section class="home-section layout-reading" id="reading-path" data-content-column>
  <div class="section-heading">
    <p class="eyebrow">Reading path</p>
    <h2>Understand, inspect, verify</h2>
  </div>

  <div class="home-section__prose">
    <p>
      Start with the architecture reference and reduction note to understand the
      pipeline. Use implementation contracts and the data contract when inspecting
      code or integrations. Use methodology pages before interpreting dated
      benchmark, profile, coverage, or fuzzing reports.
    </p>

    <p>
      Each catalog entry shows both its document type and status. Current
      specifications, contracts, references, notes, and designs describe maintained
      behavior within their stated scope. Methodology pages define how evidence is
      collected. Dated reports preserve results for a named source state and date.
      Historical pages preserve earlier decisions and are not current API
      documentation.
    </p>

    <p>
      Completed implementation plans remain versioned under <code>docs/plans/</code>
      for operational history, but are excluded from this public catalog.
    </p>
  </div>
</section>

{% comment %}
Author-approved narrative can be inserted as layout-reading sections. The wide
components below emit no markup until their complete front-matter data exists.
{% endcomment %}
{% if page.pipeline %}
  {% include home-pipeline.html pipeline=page.pipeline %}
{% endif %}
{% if page.featured_output %}
  {% include home-output.html output=page.featured_output %}
{% endif %}
{% if page.evidence %}
  {% include home-evidence.html evidence=page.evidence %}
{% endif %}
{% if page.implementation_status %}
  {% include home-status.html status=page.implementation_status %}
{% endif %}

{% assign architecture = site.pages
  | where: "section", "Architecture and correctness"
  | sort: "nav_order" %}
{% assign reduction = site.pages | where: "section", "Yang–Zhang reduction" | sort: "nav_order" %}
{% assign optimization = site.pages | where: "section", "Solver optimization" | sort: "nav_order" %}
{% assign comparisons = site.pages
  | where: "section", "Cross-engine benchmarks"
  | sort: "nav_order" %}
{% assign historical = site.pages | where: "section", "Historical material" | sort: "nav_order" %}

<section
  class="home-section home-catalog-section layout-presentation"
  id="documentation"
  data-content-column
>
  <div class="section-heading">
    <p class="eyebrow">Start here</p>
    <h2>Architecture and correctness</h2>
  </div>

  <p class="home-section__prose">
    These current references define the software boundaries that keep the
    reduction, solver, independent verification, solution transport, and
    Boolean–Wang witness correspondence auditable.
  </p>

  {% include document-list.html documents=architecture %}
</section>

<section
  class="home-section home-catalog-section layout-presentation"
  id="yang-zhang-reduction"
  data-content-column
>
  <div class="section-heading">
    <p class="eyebrow">Construction</p>
    <h2>Yang–Zhang reduction</h2>
  </div>

  <p class="home-section__prose">
    The technical note distinguishes paper conventions from project conventions.
    The builder page is the implementation contract for region geometry,
    ownership, and black-box obligations. The bibliography records primary
    sources.
  </p>

  {% include document-list.html documents=reduction %}
</section>

<section
  class="home-section home-catalog-section layout-presentation"
  id="solver-optimization"
  data-content-column
>
  <div class="section-heading">
    <p class="eyebrow">Measured mechanisms</p>
    <h2>Solver optimization</h2>
  </div>

  <p class="home-section__prose">
    Read the methodology first. The remaining pages are dated profile or
    benchmark reports that preserve their corpus, environment, work counters,
    timing method, and limitations.
  </p>

  {% include document-list.html documents=optimization %}
</section>

<section
  class="home-section home-catalog-section layout-presentation"
  id="cross-engine-benchmarks"
  data-content-column
>
  <div class="section-heading">
    <p class="eyebrow">Native C / Z3</p>
    <h2>Cross-engine benchmarks</h2>
  </div>

  <p class="home-section__prose">
    The current protocol distinguishes solving the same prepared Wang region
    from end-to-end decisions that begin with the same formula file. Dated
    reports retain the measured source identity and interpretation limits.
  </p>

  {% include document-list.html documents=comparisons %}
</section>

<section
  class="home-section home-catalog-section layout-presentation"
  id="historical-material"
  data-content-column
>
  <div class="section-heading">
    <p class="eyebrow">Design history</p>
    <h2>Historical material</h2>
  </div>

  <p class="home-section__prose">
    Earlier proposals are retained to explain the project’s design trajectory.
    They are not current API contracts.
  </p>

  {% include document-list.html documents=historical %}
</section>
