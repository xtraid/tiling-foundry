# GitHub Pages Overview Audit and Deferred Work Plan

**Status:** template foundation in progress; authorial publication deferred

**Baseline:** `ad561eba1292470738cf3f095b6f057fda2d552e` on 25 August
2026. The public legacy Pages deployment was built from `main:/docs` at this
same commit.

> This is an internal, non-normative audit and resumption plan. It records a
> proposed direction, not author-approved copy, public claims, roadmap
> commitments, or a requirement to implement every idea below. Unchecked work
> is not a commitment.

## Executive judgment

The central diagnosis is correct: the current site is a strong technical
documentation portal, but it is not yet the best conceptual introduction to
the project. The change should be an editorial reordering, not a redesign.

The original brief is useful as an analysis, with these qualifications:

- the proposed sequence is a reading goal, not a requirement for seven or more
  visibly separate homepage components;
- no narrative page, CTA, or navigation item should be published before the
  corresponding author-written content exists;
- the existing documentation catalog should remain automated and intact below
  the conceptual overview;
- the current renderer golden is useful development evidence, but it is not a
  suitable prominent example of the complete formula-to-image pipeline;
- social metadata, generated-site checks, and measured accessibility issues are
  justified work; a deployment migration, SEO plugin, component framework, and
  performance rewrite are not;
- sitemap, `robots.txt`, a custom 404 page, and automated public smoke checks
  are optional follow-ups, not prerequisites for the information-architecture
  change.

## Audit baseline

### Public structure

The homepage currently contains:

1. a short hero and documentation CTA;
2. a reading-path explanation that sends the reader to architecture and the
   reduction note;
3. five full technical catalogs containing 21 public documents.

The CTA in `docs/index.md` points to `#documentation`. The primary navigation in
`docs/_includes/header.html` exposes Documentation, Benchmarks, and Repository.
There is no conceptual overview, implemented-pipeline figure, real end-to-end
output, or compact implementation-state layer before the catalog.

The catalog itself is strong and should be preserved:

- `tools/check_pages.py` requires section, type, status, updated date, permalink,
  and navigation order;
- `docs/_includes/document-list.html` presents title, description, type, and
  status;
- reference pages retain breadcrumb, description, structured metadata, return
  navigation, and a generated H2 table of contents;
- completed plans and the post template are excluded from the public build;
- the catalog is derived from Jekyll page metadata rather than copied by hand.

### Deployment

The verified GitHub Pages configuration is:

- build type: legacy;
- source: `main:/docs`;
- HTTPS enforced;
- status: built;
- public commit at audit time: `ad561eba1292470738cf3f095b6f057fda2d552e`;
- both CI and the automatic `pages-build-deployment` run succeeded.

The `documentation` CI job runs `make pages-check` and a real Jekyll Pages
build. It does not deploy; GitHub's legacy branch deployment does. There is no
observed stale deployment at this baseline and no reason to migrate deployment
models.

Representative public routes, all catalog routes, the CSS, Wang JavaScript,
SVG mark, and historical PDF responded successfully during the audit.
`sitemap.xml`, `robots.txt`, and `404.html` were absent. Their absence does not
block the overview work; in particular, no `robots.txt` means there is no local
crawler prohibition.

## Findings

### A. Content architecture

1. **The conceptual layer is missing.** The hero is concise, but the next
   section recommends technical references. Documentation discovery therefore
   still precedes intuitive understanding.
2. **The primary CTA confirms the old hierarchy.** It sends a new reader to the
   documentation catalog rather than to an overview that does not yet exist.
3. **Benchmarks have top-level navigation prominence while conceptual
   explanation has none.** This should change only after a real overview anchor
   exists, so that the site never publishes a dead or empty navigation target.
4. **Reference and evidence are distinguished in metadata but not fully in the
   homepage hierarchy.** Coverage and fuzz reports sit in the broad
   Architecture and correctness catalog. Their type/status labels prevent a
   false claim, but a later evidence layer should make the distinction easier
   to scan.
5. **All homepage catalog sections have similar visual weight.** The catalog is
   consequently the dominant public experience even though its internal
   taxonomy is good.
6. **A separate `/documentation/` route is not required.** The existing
   `/#documentation` target is coherent and is used by breadcrumbs and return
   links. It can remain unless a later, evidence-backed need justifies a new
   route.
7. **A separate narrative page is also not required initially.** The source
   checker currently treats public Markdown pages as cataloged technical
   documents. Homepage sections are the smallest safe introduction; a new page
   type should be added only if the author later wants a durable standalone
   narrative.

### B. Visual and UX

The visual identity does not need replacement. Preserve:

- the dark laboratory palette;
- serif prose and monospace headings/navigation/metadata;
- narrow readable columns;
- the Wang field;
- the understated header and footer;
- the existing catalog, metadata, breadcrumb, TOC, code, and table treatment;
- system fonts and the current responsive philosophy.

Actual defects and follow-up checks are narrower:

1. **The deployed homepage has no semantic H1.** The indented Markdown heading
   in the HTML section is rendered as `<p># Tiling Foundry</p>`. The public page
   therefore begins its heading outline at H2. This is a correctness and
   accessibility defect, not a stylistic preference.
2. **The homepage title is duplicated.** The output is
   `<title>Tiling Foundry · Tiling Foundry</title>` because the generic title
   composition repeats the site name on the home page.
3. **The `--faint` text color is too dim for normal-sized text.** Its measured
   contrast against `#070809` is approximately `2.94:1`. It is used for footer
   text and small metadata. Other primary colors measured comfortably above
   the normal-text threshold. The faint token or its textual uses should be
   adjusted without changing the palette's character.
4. **Rouge comment text is marginal for normal text.** `#6f777a` measures about
   `4.26:1` on the site background, just below the WCAG AA normal-text ratio.
   Link underlines also use a low-contrast rule color, although link text and
   underline shape still distinguish the link. Recheck both in the browser and
   adjust only the affected tokens if necessary.
5. **New figures and status tables need explicit mobile verification.** Existing
   images are responsive and existing tables scroll horizontally; those rules
   should be reused before adding new layout behavior.
6. **Do not apply `home-index` blindly to every proposed layer.** Its large
   padding plus bottom margin is appropriate for catalogs but would make a
   multi-stage narrative unnecessarily long. Add one restrained narrative
   spacing variant rather than cards or a replacement layout system.

### C. Accessibility and performance

Existing accessibility decisions worth retaining:

- the skip link is present and becomes visible on focus;
- keyboard focus has a high-contrast visible outline;
- the Wang canvas is `aria-hidden`, non-interactive, and pointer-transparent;
- reduced motion disables smooth scrolling and displays completed tile growth;
- document metadata uses semantic description lists;
- breadcrumbs and navigation regions have labels;
- images are constrained responsively.

The H1 and faint-text contrast findings above are real issues. The future
pipeline and output figure must use semantic headings, a meaningful figure and
caption relationship, explicit intrinsic dimensions, concise alt text, and no
ARIA where native HTML already expresses the relationship. Because the raster
encodes edge classes primarily through color, its caption, description, or
linked source data must provide a non-color-only way to inspect the result.

No browser audit tool is installed locally at the baseline, so no Lighthouse,
axe, pa11y, or layout-shift score is claimed. Browser-based accessibility,
keyboard, responsive, and performance measurements remain required during
implementation.

The current asset and source measurements do not justify rewriting the Wang
field:

- homepage HTML transferred about 15.9 KiB during the audit;
- `site.css` is 14,767 bytes;
- all site JavaScript source is 36,653 bytes, of which the Wang modules are
  35,934 bytes;
- SVG image source is 1,299 bytes;
- the field caps a plan at 2,400 tiles, caps device pixel ratio at 2, debounces
  rebuilds, schedules scroll work through `requestAnimationFrame`, and draws
  only visible clusters;
- system fonts avoid a remote font request.

These are source-level observations, not a performance score. Leave the Wang
field unchanged unless a repeatable browser measurement identifies a real
problem.

### D. Metadata, links, and deployment checks

Already correct:

- `lang="en"`;
- page-specific description fallback;
- absolute canonical URLs;
- SVG favicon;
- `theme-color` and dark color scheme;
- successful production deployment from the expected commit;
- successful source-level catalog and literal-link checks.

Missing or incomplete:

1. Open Graph and Twitter/X metadata are absent.
2. There is no selected project-specific social preview image.
3. `tools/check_pages.py` checks sources, not the generated HTML. It cannot
   detect the broken home H1, duplicate title, generated link/anchor failures,
   missing output routes, or missing social metadata.
4. CI builds the site but does not run a semantic/link smoke over
   `build/pages` after Jekyll completes.
5. There is no live post-deployment smoke. This is optional while the legacy
   deployment remains demonstrably synchronized.

## Recommended public information flow

The exact number of visual sections remains an implementation choice. The
reader should nevertheless encounter this order:

```text
Hero
  -> question and project scope [author]
  -> how the implemented pipeline works [author + approved diagram concept]
  -> real verified square output [generated artifact + author caption]
  -> correctness and evidence boundaries [author]
  -> current implementation state [verified facts, not roadmap]
  -> technical documentation catalog [existing system]
  -> evidence and measurements [links to canonical reports]
  -> historical material [existing catalog]
```

Question/scope and correctness/evidence may be combined if the final authorial
copy reads better that way. The goal is comprehension before catalog depth, not
a fixed component count.

Do not publish visible filler copy. If layout work must precede authorial copy,
use short HTML comments or unmistakable development-only placeholders and do
not merge them into the public branch.

## Real-output decision

### Existing asset

The existing files
`tests/fixtures/wang_solution_v1_square_sat.json` and
`renderer/test_data/wang_solution_v1_square_sat.png` are deterministic,
schema-checked, semantically checked, and pixel-golden tested. They are useful
for renderer and layout development.

They are not the preferred prominent project result:

- the `Region` and `TilingSolveResult` are constructed manually in
  `tests/python/test_wang_solution_export.py`;
- the fixture metadata explicitly says it is not used to establish tiling
  correctness;
- it does not begin with a `.cm13` formula or exercise the Yang--Zhang builder
  and native solver.

It must not be captioned as an end-to-end formula-to-image result.

### Technically preferred candidate

`tests/instances/pipeline_sat.cm13` already exercises the real parser,
Yang--Zhang builder, native solver, independent native verifier, copied Python
model, independent Python checker, and exporter in tests. The renderer can then
consume the exported `wang-solution-v1` document without loading the core.

The candidate provenance is:

```text
tests/instances/pipeline_sat.cm13
  -> solve_native_tiling(..., optimized=true)
  -> independent native and Python tiling checks
  -> dump_wang_solution(...)
  -> renderer/wang_square.py
  -> checked-in square PNG
```

Before publication, the author must decide whether this small regression input
has suitable scientific and explanatory value. A different input may be
selected, but it must be versioned, pass the same pipeline, and have an
author-approved caption. The paper example is another possible source only if
it is first represented as a reproducible versioned input and verified through
the current pipeline.

### Reproducibility architecture

Prefer a checked-in JSON solution and PNG plus a narrow generation command or
script. Record at least the source path and SHA-256, producer path, solver path,
schema name, renderer lock state, output dimensions, and output SHA-256.

The Pages build should consume the checked-in files. It should not build the C
library, solve a formula, or install Pillow. Regeneration belongs in an explicit
developer command and, if its cost remains small, a focused CI comparison in
the existing root/renderer environments.

Do not create a second schema, a Pages-only renderer, a fake intermediate
diagram, or any implication of hex output.

## Verified implementation-state facts

The homepage may later summarize these facts. Recheck them at the implementation
commit rather than copying this table blindly.

| Capability | Baseline state |
| --- | --- |
| Yang--Zhang formula-to-region construction | Implemented and tested |
| Reference native solver | Implemented |
| Optimized native solver | Implemented with five isolated mechanisms |
| Independent native verifier | Implemented and required before SAT publication |
| Boolean Z3 oracle | Implemented over the copied immutable formula |
| Wang Z3 oracle | Implemented over copied region and canonical tileset |
| Boolean--Wang witness correspondence | Implemented with exhaustive small-instance evidence |
| Verified square export | Implemented as `wang-solution-v1` |
| Square diagnostic rendering | Implemented in the isolated renderer project |
| Square-to-hex translation and verification | Not implemented; placeholder modules are empty |
| Native C JSON | Not implemented; the translation unit is a placeholder |
| `TaskPlan` and native OpenMP solver | Not implemented; only scaffold/placeholders exist |

This is a status summary, not a public roadmap. Empirical evidence must link to
its canonical reports and must not be presented as a proof of the theoretical
result.

## Author input required before publication

The implementation agent must not write these sections on the author's behalf.
The ranges below are planning estimates, not content requirements.

| Location / insertion point | Author-provided material | Purpose | Approximate size | Constraints |
| --- | --- | --- | --- | --- |
| `README.md`, opening before Quick start | Final README introduction | Fast repository entry point | 150--300 words | Must remain distinct from the longer Pages narrative |
| `docs/index.md`, after the hero | The question / project overview | Explain why the problem and repository matter | 150--300 words | No slogans, inflated claims, or unexplained proof claim |
| `docs/index.md`, before any result figure | How Tiling Foundry works | Narrative bridge from formula to verified square output | 250--500 words | Keep production stages distinct from independent oracles |
| `docs/index.md`, within or beside How it works | Intuitive Yang--Zhang introduction | Explain the reduction before technical references | 200--450 words | Distinguish theorem, project convention, and implementation |
| `docs/index.md`, correctness/evidence layer | What does Tiling Foundry actually establish? | Bound public claims and evidence | 200--400 words | Empirical tests are not a proof of the theorem |
| Pipeline include or inline figure in `docs/index.md` | Conceptual pipeline design | Define nodes, ordering, branches, and labels | 6--10 named stages plus oracle/future annotations | Z3 paths are independent oracles; hex/OpenMP must be absent or explicitly future |
| `docs/index.md`, real-output figure | Caption and interpretation | Explain what the selected image shows and does not show | 50--120 words plus a short alt-text brief | No fabricated significance and no hex implication |
| README/Pages roadmap location, only if retained | Final public roadmap wording | Authorize any future-facing commitments | 100--200 words or omission | Must not be inferred from internal plans |

Final CTA and navigation wording also require author confirmation after these
sections exist. Until then, keep the current working links.

## Public roadmap statements requiring author review

Do not copy the current README `Next milestones` block onto Pages without
explicit author approval. It presently commits to this order:

1. square-to-hex formalization, implementation, verification, and renderer
   mode;
2. MRV evaluation and a separate hard-UNSAT corpus before parallelism claims;
3. allocation/cleanup hardening before concurrent execution;
4. a minimal serial `TaskPlan` before OpenMP.

The README also says OpenMP is introduced only after the serial path is correct
and measurable. Technical reports contain narrower conditional statements
about these topics; leave those reports intact. The author must decide whether
the README ordering remains a public commitment and whether Pages should expose
any roadmap at all.

## Deferred implementation sequence

Use one documentation staging branch for this work. Do not create a branch per
homepage section. Commit, push, and PR actions still require the authorization
defined by the repository's operating contract.

### Phase 0: author decisions

- [ ] Receive or confirm the authorial sections listed above.
- [ ] Confirm whether How it works is a homepage section or a standalone page.
  Default recommendation: homepage section.
- [ ] Select the real input/artifact and approve its interpretation.
- [ ] Approve the pipeline topology and the distinction between production,
  oracle, evidence, and future stages.
- [ ] Approve final CTA/navigation labels.
- [ ] Approve or omit public roadmap wording.

Do not begin the public information-architecture switch while these decisions
would leave empty primary navigation or invented copy.

### Phase 1: semantic and generated-output guardrails

- [x] Fix the homepage H1 using generated HTML as the acceptance criterion.
- [x] Avoid duplicate site name in the home `<title>` while retaining the
  existing page-title format elsewhere.
- [x] Correct faint text contrast conservatively and remeasure affected uses.
- [ ] Recheck Rouge comments and link-decoration contrast in the browser;
  change only tokens that fail the selected accessibility criterion.
- [x] Add a standard-library generated-site checker that runs after Jekyll and
  verifies representative routes, one H1, title, description, canonical,
  internal `href`/`src` targets, anchors, and expected homepage markers.
- [x] Keep `tools/check_pages.py` focused on source/catalog invariants, extending
  it only where the chosen homepage architecture changes those invariants.

The implementation also establishes explicit 44rem reading, 70rem
presentation, and 78rem shell widths. The current catalog uses the wider
presentation container while its prose remains constrained. Conditional
pipeline, output, evidence, and status includes emit no markup until complete
author-approved data is supplied. Browser verification remains open; no visual
claim is derived from the static CSS review.

### Phase 2: reproducible example

- [ ] Generate candidate JSON and PNG files in a temporary directory from the
  selected versioned input.
- [ ] Verify the native and Python witness checks, schema validation, renderer
  output, dimensions, hashes, and absence of hex semantics.
- [ ] Present candidate images and provenance to the author for selection.
- [ ] Add only the selected checked-in solution/image and the narrow
  regeneration mechanism.
- [ ] Add a focused reproducibility check if it remains cheap and does not make
  the Pages build solve or install renderer dependencies.

### Phase 3: homepage information architecture

- [ ] Insert author-provided question/scope, How it works, reduction, and claim
  material without rewriting it into marketing copy.
- [ ] Implement the approved pipeline visual with semantic HTML/CSS by default;
  use SVG only if relationships cannot remain clear and accessible in HTML.
- [ ] Add the selected real-output figure with author caption and appropriate
  alt text, intrinsic dimensions, and a provenance/source-data link.
- [ ] Add a compact implementation-state table from reverified repository facts.
- [ ] Add a concise evidence layer that links to canonical reports and separates
  theorem, implementation claim, verification evidence, and measurement.
- [ ] Move the existing catalog below those layers without weakening metadata,
  section distinctions, breadcrumbs, TOC, or historical context.
- [ ] Change CTA and navigation only after their targets contain final content.

Avoid a generic component library. Likely additions are limited to an
understated narrative section convention, one pipeline include, one figure
treatment, and one compact status/evidence treatment.

### Phase 4: social and document metadata

- [ ] Add escaped Open Graph title, description, canonical URL, type, and site
  name in `docs/_layouts/default.html`.
- [ ] Add equivalent Twitter card metadata.
- [ ] Make the social image conditional on a real selected asset through page
  or site configuration; emit no placeholder URL.
- [ ] Verify page descriptions, canonical paths, favicon, `lang`, title
  hierarchy, and the selected social image on home and representative documents.
- [ ] Consider sitemap only as an optional small follow-up; do not add Ruby
  dependencies or SEO plugins solely for completeness.

### Phase 5: verification

- [x] Run source/catalog and generated-site checks.
- [x] Build Pages with the same GitHub Pages action used by CI.
- [x] Run JavaScript syntax checks; no root or renderer implementation changed.
- [ ] Run browser accessibility checks, keyboard navigation, focus, heading,
  contrast, alt/caption, reduced-motion, and TOC checks.
- [ ] Run browser performance measurements before and after any justified
  performance change. If no Wang-field change is made, report the baseline only.
- [ ] Check large desktop, laptop, tablet, and narrow mobile widths for overflow,
  navigation, pipeline, figure, status table, TOC, code, and metadata.
- [ ] Smoke the deployed homepage, a reference page, an evidence page, and their
  expected markers after authorized publication.
- [ ] Run the complete repository-required CI gate before merge or direct-main
  publication, according to the authorization for that task.

## Expected file map, subject to author decisions

- `docs/index.md`: information order, author copy insertion, output figure,
  status/evidence summaries, unchanged catalog queries.
- `docs/_includes/header.html`: minimal navigation update after targets exist.
- `docs/_layouts/default.html`: home title handling and social metadata.
- `docs/_includes/`: at most one pipeline include and any genuinely reused
  figure/status include.
- `docs/assets/css/site.css`: only styles required by the new narrative,
  pipeline, figure, status/evidence layer, and verified contrast fix.
- `docs/assets/images/`: selected real generated output and possibly its
  author-approved social composition.
- `docs/assets/data/` or another explicit asset location: selected versioned
  solution document if it is useful for provenance/download.
- `tools/`: narrow example generator and generated-site checker if approved.
- `.github/workflows/ci.yml`: invoke generated-site checks after the existing
  Jekyll build; do not migrate deployment.
- `README.md`: only the final introduction supplied or approved by the author
  and clear cross-links; do not duplicate the Pages homepage.

## Verification already performed for this audit

- `make pages-check`: passed for 21 technical documents, the index, five
  sections, and all literal internal links known to the checker.
- `node --check` on the current site JavaScript: passed.
- Public GitHub Pages configuration and recent CI/deployment runs: healthy and
  synchronized at the baseline commit.
- Public URL smoke: catalog routes and representative assets succeeded.
- Live HTML inspection: exposed the missing semantic home H1 and duplicated
  home title.
- Static contrast calculation: exposed the `2.94:1` faint-text token.
- Local tool inventory: Ruby/Jekyll, a browser, Lighthouse, pa11y, and dedicated
  link-checker binaries were not available; no result from those tools is
  claimed.

At audit time, no implementation, artifact generation, full project test run,
browser audit, or deployment mutation was performed. The checklists above now
record the subsequent local template work; no public deployment was mutated.

## Concrete remaining risks

1. Publishing before author copy exists would replace a coherent documentation
   portal with visible scaffolding or invented prose.
2. The small `pipeline_sat.cm13` input may be technically valid but visually or
   scientifically weak; only the author can select its public significance.
3. A social crop/composition can hide cells or imply a different result; it
   requires author review and traceable provenance.
4. The source-only checker has already missed one production heading defect;
   generated HTML checks are required before the homepage grows.
5. New pipeline/status layout may overflow or reorder poorly on mobile; no local
   browser measurement exists yet.
6. The legacy Pages deploy is currently healthy, but CI build success alone
   does not prove that a later live deployment is current. A lightweight live
   smoke becomes worthwhile only if stale publication is observed or the author
   wants that operational guarantee.
