# T98 Visual Documentation, PDF v2 and README Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the existing narrative assets until they explain the real
algorithms clearly, compose readable static figures into a run-specific v2
PDF, and route README readers into the canonical Pages documentation.

**Architecture:** Rework the current named asset bundles in place from the
same validated run artifacts. Keep `wang-narrative-assets-v1`, the existing
owner routes, and the single validator/replay/compositor chain; use focused
observed frames or compact static panels instead of adding a visual framework.
Add a separate pure v2 TeX formatter and template while preserving the v1
dossier exactly.

**Tech Stack:** C17, Python 3.14, Pillow and NumPy through the locked renderer
environment, existing closed JSON contracts, Markdown/Jekyll, Liquid,
HTML/CSS, LaTeX/pdfLaTeX, `uv`, Make, Docker and Playwright.

**Spec:** `docs/plans/2026-08-31-narrative-architecture-contract.md`

## Global Constraints

- Base all work on `origin/main` merge commit `b921e7d` or a verified
  descendant containing the identical T97 tree.
- Preserve the current public permalinks, sitemap, and nine component-page H2
  sections. Do not deepen these editorial conventions into new architecture.
- Keep `tests/instances/pipeline_sat.cm13` as the sole canonical SAT narrative
  and `tests/instances/pipeline_unsat_search.cm13` as a separately named
  search diagnostic.
- Preserve reference and optimized solver behavior, native ABI, traces,
  metrics, ownership and deterministic outputs. T98 changes no solver logic.
- Pages and PDF consume previously validated artifacts. Neither path may solve,
  invoke Z3, rebuild the reduction, or independently verify a witness.
- Keep `wang-narrative-assets-v1`. The planned implementation adds no schema,
  manifest version, generic asset registry, intermediate representation or
  validator layer.
- If a required correctness claim cannot be represented by the current asset
  boundary without a false owner, semantic label or source identity, stop the
  affected task and report the concrete counterexample before changing a
  contract.
- Treat visual requirements as reader outcomes, not a one-to-one list of
  animations, modules or assets. Prefer static panels where time adds no
  information.
- Visual quality is itself an acceptance criterion. Semantic correctness does
  not justify retaining an existing GIF or image that is blurry,
  low-resolution, hard to read, overly compressed or visually weak at its
  actual Pages or PDF display size; regenerate, improve or replace it.
- MRV is the vertical slice that establishes the visual grammar, not the limit
  of the rework. Apply the graphical-explanation requirement to every relevant
  algorithm or technical mechanism, choosing the clearest static figure,
  multi-panel sequence, comparison, observed state or animation. Animated
  flowcharts and boxes that merely light up remain suitable for architecture
  or pipeline views, but are not an adequate primary algorithm explanation
  when the reader needs to see actual state, transformation, decisions or
  data-structure behavior.
- Retain observed reference and optimized traces as evidence, including their
  complete/selected/truncated semantics. A displayed subset never means trace
  events were omitted from the source.
- Preserve the five asset labels: `observed`, `canonical-construction`,
  `encoding-order`, `verified-transformation` and `didactic`.
- Keep the existing renderer modules unless an actual responsibility boundary
  becomes unmanageable during implementation. Do not perform the proposed
  file split mechanically.
- Render important raster figures at 2x source scale; do not enlarge existing
  small bitmaps. Use 3x only after a visual comparison proves a benefit.
- Use `NEAREST` only for intentionally discrete pixel/block content. Use a
  high-quality filter for text-heavy or presentation downsampling.
- Every animation keeps a meaningful static fallback and contact sheet. Every
  important visual keeps adjacent alt text and a useful caption.
- Keep dossier v1 schemas, case semantics, formatter, output layout and CLI
  behavior compatible. V2 remains an additive dispatch path.
- Do not implement profiling, `TaskPlan`, OpenMP, native JSON, another solver
  optimization or a generalized presentation framework.
- Stop when the acceptance story is clear at desktop, 390 px and normal PDF
  zoom. Do not add variants without a concrete consumer.

## Existing Asset Disposition

The implementation reuses these current records instead of adding asset IDs:

| Existing record | T98 role |
|---|---|
| `reference_trace` | Observed MRV, propagation, decision, conflict and rollback states; complete trace remains evidence |
| `optimized_trace` | Observed optimized run using the same visual grammar |
| `optimized_mechanisms` | Compact didactic panels for the six retained mechanisms |
| `region_construction` | Source/target signals, adjacent swaps, one crossover, assembly and boundaries |
| `boolean_z3` | Project-owned formula-to-constraint order only |
| `wang_z3` | Project-owned finite-region edge and tile encoding only |
| `verification` | Receipt summary, tiling checks and witness extraction from already verified artifacts |
| `witness_presentation` | Square to generalized to checked-hex relationship |
| existing statics | Formula, tile vocabulary, worked example and final presentation quality pass |

The current animation `frames`, `fallback`, `contact_sheet` and
`pdf_milestones` fields carry the print-ready panels. A frame remains within
the parent record's owner and semantic label; do not mix didactic content into
an `observed` record unless every displayed fact is derived from the validated
observed state.

---

### Task 1: Freeze the visual grammar with an MRV vertical slice

**Files:**

- Modify: `renderer/wang_explain.py`
- Modify: `renderer/wang_trace_render.py`
- Test: `renderer/test_wang_trace.py`
- Generate only for review: a temporary `reference_trace` bundle outside Git

**Interfaces:**

- Consumes: `TraceBundle`, `TraceEvent` and states returned by
  `replay_trace()` from `tests/fixtures/pipeline_sat_solver_trace/manifest.json`.
- Produces: the existing `render_trace_assets(...) -> AnimationOutputs`
  interface with 2x source frames and an observed MRV decision frame.
- Adds no data model. MRV candidates are derived locally from active replayed
  domains and discarded after composition.

- [ ] **Step 1: Add a failing deterministic MRV test**

  Extend `renderer/test_wang_trace.py` with a test that loads the SAT trace,
  finds the first search decision, computes the minimum unresolved domain size
  from the replayed pre-decision state, and proves that the event cell is the
  lowest row-major member of the tied candidate set. Render twice and assert
  identical trees plus a physical fallback size of `1976 x 828` for the
  logical `988 x 414` display.

  ```python
  candidates = tuple(
      index
      for index, (active, domain) in enumerate(zip(region.active, before))
      if active and domain.bit_count() == minimum
  )
  assert event.cell == min(candidates)
  assert _tree_bytes(first_dir) == _tree_bytes(second_dir)
  assert Image.open(first.fallback).size == (1976, 828)
  ```

- [ ] **Step 2: Prove the new test fails for the current 1x output**

  Run:

  ```bash
  cd renderer
  uv run --locked pytest -q test_wang_trace.py -k 'mrv or deterministic'
  ```

  Expected: the new dimension assertion fails while existing semantic tests
  remain green.

- [ ] **Step 3: Add only the shared primitives needed by the prototype**

  Keep one render-scale constant and consistent treatments for unresolved,
  singleton, selected MRV, propagation source/target, queued, decision,
  conflict, trail mutation and restored state. Scale coordinates, fonts and
  strokes at source; do not render at 1x and resize.

- [ ] **Step 4: Compose the observed MRV explanation**

  In the decision frame show domain sizes, all minimum candidates, the
  row-major winner and the selected cell. The side panel must expose values
  derived from the replayed state, not hard-coded fixture numbers.

- [ ] **Step 5: Verify focused tests and inspect the prototype**

  Run:

  ```bash
  cd renderer
  uv run --locked pytest -q test_wang_trace.py
  ```

  Generate to a `mktemp -d` destination and inspect the fallback and contact
  sheet at original resolution. At intended `988 px` display width, domain
  sizes and the tie-break statement must be readable without zoom.

- [ ] **Step 6: Apply the stop rule**

  If desktop, 390 px and one-column PDF-size previews are readable, freeze the
  grammar. Do not add themes, layout engines, vector backends or alternate MRV
  variants.

- [ ] **Step 7: Commit the vertical slice**

  ```bash
  git add renderer/wang_explain.py renderer/wang_trace_render.py \
    renderer/test_wang_trace.py
  git commit -m "Explain observed MRV selection clearly"
  ```

### Task 2: Complete solver behavior and retain trace evidence

**Files:**

- Modify: `renderer/wang_trace_render.py`
- Test: `renderer/test_wang_trace.py`
- Test: `tests/python/test_multi_engine_dossier.py`
- Modify metadata only when wording changes:
  `python/dossier/narrative_assets.py`

**Interfaces:**

- Consumes: the existing complete SAT reference/optimized traces and the
  separately captured `examples/run-cases-v2/pipeline-unsat-search.json` run.
- Produces: focused observed sequences within `reference_trace` and
  `optimized_trace`; the manifest shape and trace sources remain unchanged.

- [ ] **Step 1: Add failing sequence-selection tests**

  Test that the SAT selection contains a real restriction, decision and
  continuation, and that the separate search-UNSAT selection contains a
  decision, propagation reduction, empty-domain conflict and reverse rollback
  in source-event order. Assert the run-specific UNSAT manifest caption names
  it an `observed search diagnostic` and states that it is
  `not an UNSAT certificate`.

- [ ] **Step 2: Run the focused tests and confirm the missing story**

  ```bash
  cd renderer
  uv run --locked pytest -q test_wang_trace.py
  ```

  Expected: new story assertions fail against the current generic milestone
  composition.

- [ ] **Step 3: Make propagation causal rather than decorative**

  For a real domain-reduction event show the restricted source, inspected
  neighbor, removed candidate domain bits, shared-edge support reason and
  resulting state. Use existing tile/domain data; do not introduce another
  compatibility implementation. Do not present queue order as observed because
  the current trace contract does not record it; queue behavior belongs to the
  didactic optimized-mechanism bundle.

- [ ] **Step 4: Make DFS and rollback visible in the same observed grammar**

  Show selected cell, candidate branch, depth, conflict, trail mark, reverse
  restoration and next branch. Keep the grid primary and use only a compact
  search-tree inset.

- [ ] **Step 5: Preserve evidence semantics**

  Keep the original event sequence, complete trace identity and selected-frame
  semantics. Assert generated manifests retain `semantic_label: observed`,
  `complete: true`, `selected: true` and `truncated: false` for the canonical
  trace bundles.

- [ ] **Step 6: Run solver-renderer and dossier tests**

  ```bash
  cd renderer
  uv run --locked pytest -q test_wang_trace.py
  cd ..
  PYTHONPATH="$PWD/python" uv run --frozen python -m unittest \
    tests.python.test_multi_engine_dossier
  ```

- [ ] **Step 7: Commit the focused observed trace story**

  ```bash
  git add renderer/wang_trace_render.py renderer/test_wang_trace.py \
    python/dossier/narrative_assets.py \
    tests/python/test_multi_engine_dossier.py
  git commit -m "Explain propagation and rollback from observed traces"
  ```

### Task 3: Explain the reduction and local tile compatibility

**Files:**

- Modify: `renderer/wang_algorithm_animation.py`
- Modify: `renderer/wang_narrative.py`
- Test: `renderer/test_wang_algorithm_animation.py`
- Test: `renderer/test_wang_narrative.py`

**Interfaces:**

- Consumes: the validated reduction provenance already exposed by
  `load_explainability_bundle()` and the canonical tile table.
- Produces: the existing `region_construction` frame sequence plus an improved
  `atomic_legend`; no new asset record is added.

- [ ] **Step 1: Add failing construction-content tests**

  Assert that rendered stages are byte-stable and sourced from the fixture's
  exact `source_signals`, `target_signals`, adjacent-swap provenance and one
  actual crossover. Assert the final construction panel distinguishes active,
  inactive, exposed-boundary and internal edges.

- [ ] **Step 2: Add a failing local-compatibility test**

  Render one valid and one invalid adjacency using actual canonical tile IDs.
  Assert the shared colors agree in the valid example and differ in the
  invalid example before checking output bytes and dimensions.

- [ ] **Step 3: Implement the smallest coherent construction sequence**

  Use a few frames to show source versus target order, actual adjacent swaps,
  one crossover, final region assembly and boundaries. Keep the existing
  gadget-span view as provenance support rather than adding a second bundle.

- [ ] **Step 4: Fold tile compatibility into the current vocabulary output**

  Add the valid/invalid adjacency panel to `atomic_legend` or the current tile
  sheet, whichever remains readable at normal width. Do not create a new
  manifest entry for it.

- [ ] **Step 5: Run focused renderer tests**

  ```bash
  cd renderer
  uv run --locked pytest -q \
    test_wang_algorithm_animation.py test_wang_narrative.py
  ```

- [ ] **Step 6: Commit the reduction explanation**

  ```bash
  git add renderer/wang_algorithm_animation.py renderer/wang_narrative.py \
    renderer/test_wang_algorithm_animation.py renderer/test_wang_narrative.py
  git commit -m "Explain Yang-Zhang routing and tile compatibility"
  ```

### Task 4: Replace the optimized mechanism list with concrete panels

**Files:**

- Modify: `renderer/wang_algorithm_animation.py`
- Modify only if factual copy changes:
  `renderer/data/optimized-mechanisms-v1.json`
- Test: `renderer/test_wang_algorithm_animation.py`
- Modify metadata only when wording changes:
  `python/formats/narrative_assets.py`
  `python/dossier/narrative_assets.py`

**Interfaces:**

- Consumes: the existing six-mechanism source and current implementation
  semantics documented by their evidence pages.
- Produces: the existing `optimized_mechanisms` bundle with concrete didactic
  panels and no benchmark claims.

- [ ] **Step 1: Add failing mechanism-panel tests**

  Assert byte stability and the presence of exactly the six retained mechanism
  IDs. Verify the lazy-MRV panel uses domain-size buckets and reverses one
  bucket update during rollback; verify queue dedup permits a later enqueue
  after dequeue.

- [ ] **Step 2: Implement static comparisons where motion adds nothing**

  Use compact before/after panels for dynamic stack capacity, initial-trail
  omission and SAT ownership transfer. Show the reference behavior beside the
  optimized behavior without performance numbers.

- [ ] **Step 3: Implement the stateful explanations**

  Show actual 23-bit byte-support aggregation, duplicate suppression while a
  cell is pending, and the lazy-MRV bucket/index update and rollback. State
  `domains = semantic source of truth` and `MRV index = private derived state`.

- [ ] **Step 4: Stop at one owned bundle**

  Use frames and its static contact/fallback output; do not create six asset
  records, six renderer modules or a mechanism plugin system.

- [ ] **Step 5: Run focused tests and commit**

  ```bash
  cd renderer
  uv run --locked pytest -q test_wang_algorithm_animation.py
  cd ..
  git add renderer/wang_algorithm_animation.py \
    renderer/data/optimized-mechanisms-v1.json \
    renderer/test_wang_algorithm_animation.py \
    python/formats/narrative_assets.py python/dossier/narrative_assets.py
  git commit -m "Show the optimized serial mechanisms concretely"
  ```

### Task 5: Explain the two encodings, verification and witness extraction

**Files:**

- Modify: `renderer/wang_z3_summary.py`
- Modify: `renderer/wang_narrative.py`
- Modify: `python/dossier/narrative_assets.py`
- Modify: `python/formats/narrative_assets.py`
- Test: `renderer/test_wang_z3_summary.py`
- Test: `renderer/test_wang_narrative.py`
- Test: `tests/python/test_multi_engine_dossier.py`

**Interfaces:**

- Consumes: existing `z3-encoding-summary-v1` documents, the existing
  explainability bundle, verified solution and v2 verification records.
- Produces: reworked existing `boolean_z3`, `wang_z3`, `verification` and
  `witness_presentation` bundles. No renderer imports Z3 or native producers.

- [ ] **Step 1: Add failing oracle-composition tests**

  Boolean frames must show real source clauses becoming `ExactlyOne` terms in
  source order and the copied SAT assignment. Wang frames must show a real
  active cell, shared internal term, canonical tile tuple, exposed boundary
  equality and returned model projection. Both must display that they do not
  expose Z3 internal search.

- [ ] **Step 2: Add failing verifier and extraction tests**

  Validate that the receipt summary names the six existing checks, the tiling
  panel shows valid tile IDs, `TILE_NONE`, internal equality and boundary
  equality, and the extraction view places real variable-gadget cells beside
  the already recorded extracted Boolean assignment and independent checker
  result. The renderer must not recompute or decide that assignment.

- [ ] **Step 3: Rework the Z3 frames from existing summaries**

  Improve geometry and typography without adding fields to
  `z3-encoding-summary-v1` or implying internal Z3 decisions.

- [ ] **Step 4: Rework verification from existing validated inputs**

  Pass the existing explainability manifest/solution alongside the current
  verification receipts when composing the bundle. Reuse its loaders and
  identities; do not create a verification-story JSON contract.

- [ ] **Step 5: Update source identity only if the consumed identity set grows**

  If verification frames consume provenance and a verified solution, include
  those existing hashes in `verification_source_sha256()`. Keep the manifest
  field structure and semantic policy unchanged.

- [ ] **Step 6: Run focused tests and import-boundary checks**

  ```bash
  cd renderer
  uv run --locked pytest -q test_wang_z3_summary.py test_wang_narrative.py
  cd ..
  PYTHONPATH="$PWD/python" uv run --frozen python -m unittest \
    tests.python.test_multi_engine_dossier
  ```

- [ ] **Step 7: Commit the oracle and verification explanation**

  ```bash
  git add renderer/wang_z3_summary.py renderer/wang_narrative.py \
    renderer/test_wang_z3_summary.py renderer/test_wang_narrative.py \
    python/dossier/narrative_assets.py python/formats/narrative_assets.py \
    tests/python/test_multi_engine_dossier.py
  git commit -m "Explain oracle encodings and witness verification"
  ```

### Task 6: Compose the additive v2 PDF without another semantic pass

**Files:**

- Create: `python/formats/run_report_v2_tex.py`
- Create: `templates/run-report-v2.tex`
- Create only for the shared TeX security boundary:
  `python/dossier/tex_compile.py`
- Modify: `python/dossier/multi_engine.py`
- Modify: `tools/generate_run_dossier.py`
- Modify: `Makefile`
- Test: `tests/python/test_multi_engine_dossier.py`
- Test: `tests/python/test_run_dossier.py`

**Interfaces:**

- Produces:
  `render_run_report_v2_tex(document: dict[str, object],
  manifest: dict[str, object], template: str) -> str`.
- The v2 formatter validates the existing run and narrative manifest, selects
  only their static artifacts/milestones and returns TeX. It performs no I/O
  other than its caller reading the validated inputs.
- `tex_compile.py` owns the existing `-no-shell-escape`, restricted TeX home,
  `SOURCE_DATE_EPOCH`, two-pass compilation and cleanup behavior. V1 and v2
  callers translate its single controlled error into their existing public
  error types.

- [ ] **Step 1: Freeze v1 behavior with focused tests**

  Add assertions that a v1 case still dispatches to the v1 formatter, keeps
  its filenames/layout, rejects v2-only options and produces deterministic
  TeX/PDF from the existing smoke case.

- [ ] **Step 2: Add failing pure v2 formatter tests**

  For SAT, assert section order is summary, source, Boolean Z3, Yang--Zhang,
  reference, optimized, Wang Z3, verification/presentation, reproducibility.
  For UNSAT, assert witness-only figures are absent and explicitly not
  applicable. Assert no trace contact sheet is used as the primary solver
  figure.

- [ ] **Step 3: Add explicit figure layouts**

  Implement small helpers local to `run_report_v2_tex.py` for wide,
  multi-panel, tall and compact figures. Do not add a generic report layout
  framework. Every helper emits a fixed `\includegraphics` policy appropriate
  to its consumer.

- [ ] **Step 4: Implement the v2 formatter and template**

  Read source text and validated values directly from the existing dossier;
  use `pdf_milestones` and static artifacts for figures. Keep raw timings and
  hashes in the reproducibility appendix and never infer semantic results from
  pixels.

- [ ] **Step 5: Share only the TeX compilation security boundary**

  Move the current isolated compilation behavior without changing v1 output.
  Invoke it inside the v2 staging directory before the atomic install so a
  TeX failure leaves no partial destination.

- [ ] **Step 6: Add and run SAT/UNSAT PDF smoke**

  Add `run-dossier-v2-smoke` rather than making `run-dossier-smoke` silently
  change meaning.

  ```bash
  make run-dossier-smoke
  make run-dossier-v2-smoke
  PYTHONPATH="$PWD/python" uv run --frozen python -m unittest \
    tests.python.test_run_dossier tests.python.test_multi_engine_dossier
  ```

- [ ] **Step 7: Commit the additive v2 report path**

  ```bash
  git add python/formats/run_report_v2_tex.py templates/run-report-v2.tex \
    python/dossier/tex_compile.py python/dossier/multi_engine.py \
    tools/generate_run_dossier.py Makefile tests/python/test_run_dossier.py \
    tests/python/test_multi_engine_dossier.py
  git commit -m "Compose readable static v2 run reports"
  ```

### Task 7: Publish the improved assets through Pages and README

**Files:**

- Modify: `README.md`
- Modify: `docs/worked-example.md`
- Modify as required by changed figures: `docs/components/*.md`
- Modify only for responsive presentation: `docs/assets/css/site.css`
- Modify only if current includes cannot present the existing fallback cleanly:
  `docs/_includes/narrative-animation.html`
  `docs/_includes/narrative-static.html`
- Modify minimally if asset topology changes:
  `tools/check_pages.py`
  `tools/check_generated_pages.py`
  `tests/python/test_pages_checker.py`
  `tests/python/test_generated_pages.py`
- Regenerate from one canonical capture: `docs/assets/narrative/`

**Interfaces:**

- Consumes: one freshly validated canonical SAT v2 run and the current
  `wang-narrative-assets-v1` generator.
- Produces: byte-identical run-specific/canonical compositor files, authored
  Pages prose and README routing. Pages build remains render-free.

- [ ] **Step 1: Add only tests required by actual integration changes**

  Preserve one primary owner and existing accessibility/link checks. If no
  asset ID or include contract changes, do not add checker abstractions. Add a
  regression only for a concrete failure such as swapped fallback roles,
  missing intrinsic dimensions or horizontal overflow metadata.

- [ ] **Step 2: Regenerate the canonical bundle from one clean capture**

  ```bash
  T98_ASSET_TMP=$(mktemp -d /tmp/tiling-foundry-t98-assets.XXXXXX)
  PYTHONPATH="$PWD/python" uv run --frozen python \
    tools/generate_run_dossier.py \
    examples/run-cases-v2/pipeline-sat.json "$T98_ASSET_TMP/run"
  PYTHONPATH="$PWD/python" uv run --frozen python \
    tools/generate_narrative_assets.py \
    "$T98_ASSET_TMP/run/run.json" "$T98_ASSET_TMP/pages" \
    --product canonical-pages
  rsync -a --delete "$T98_ASSET_TMP/pages/" docs/assets/narrative/
  ```

  Validate the temporary manifest before replacing tracked output. Copy the
  complete generated tree as one unit so file hashes and manifest cannot drift.

- [ ] **Step 3: Place visuals next to the prose they explain**

  Keep the nine H2 sections. Focused visuals appear before the observed trace
  evidence where both are present; avoid appending an asset gallery or
  duplicating component explanations in the worked example.

- [ ] **Step 4: Improve the worked example and final presentations**

  Keep the overview storyboard, but make formula, construction decision,
  verified square witness, interpretation and final presentation readable at
  useful sizes. Improve source resolution/downsampling without redesigning the
  square/generalized/hex relationship.

- [ ] **Step 5: Clean README routing and stale status**

  Add one prominent line linking Documentation, Pipeline, Worked example,
  Reference, Evidence and Run dossiers. Retain project statement, scope,
  quickstart, status, architecture, limitations, reference and license; reduce
  duplicated algorithm narrative and remove rapidly stale exact test counts.

- [ ] **Step 6: Build and validate Pages offline**

  ```bash
  T98_PAGES_BUILD=$(mktemp -d /tmp/tiling-foundry-t98-pages.XXXXXX)
  docker run --rm --network none --user 1000:1000 \
    -e GITHUB_WORKSPACE=/github/workspace \
    -e INPUT_SOURCE=docs -e INPUT_DESTINATION=build/pages \
    -e INPUT_VERBOSE=false -e INPUT_FUTURE=false \
    -e GITHUB_REPOSITORY=xtraid/tiling-foundry \
    -e GITHUB_API_URL=https://api.github.com -e INPUT_TOKEN= \
    -e INPUT_BUILD_REVISION="$(git rev-parse HEAD)" \
    -v "$PWD:/github/workspace:ro" \
    -v "$T98_PAGES_BUILD:/github/workspace/build/pages" \
    ghcr.io/actions/jekyll-build-pages:v1.0.13
  python3 tools/check_generated_pages.py "$T98_PAGES_BUILD"
  ```

- [ ] **Step 7: Perform browser QA with the local Playwright image**

  Serve the external build locally and use
  `mcr.microsoft.com/playwright:v1.62.0-noble` to inspect `/`, `/pipeline/`,
  `/worked-example/` and all eight component routes at desktop and `390 px`.
  Record screenshots outside Git. Check overflow, label readability,
  reduced-motion fallback, stable aspect ratio, captions, focus and links.

- [ ] **Step 8: Run Pages and renderer regressions, then commit**

  ```bash
  make pages-check
  cd renderer
  uv run --locked pytest -q
  cd ..
  git add README.md docs tools/check_pages.py tools/check_generated_pages.py \
    tests/python/test_pages_checker.py tests/python/test_generated_pages.py
  git commit -m "Route readers through publication-quality documentation"
  ```

### Task 8: Inspect PDFs, run the complete closing gates and freeze T98

**Files:**

- Review: complete `origin/main...HEAD` diff
- Modify only for evidence accuracy:
  `docs/plans/2026-08-31-narrative-migration-checklist.md`
- Record task evidence under: `.superpowers/sdd/2026-09-05-t98-visual-documentation/`

**Interfaces:**

- Consumes: final SAT and search-UNSAT v2 dossiers plus the externally built
  Pages site.
- Produces: reviewed publication output and a frozen presentation phase. It
  does not begin T99, profiling, `TaskPlan` or OpenMP.

- [ ] **Step 1: Inspect SAT and search-UNSAT PDFs at normal reading scale**

  ```bash
  T98_PDF_QA=$(mktemp -d /tmp/tiling-foundry-t98-pdf.XXXXXX)
  pdfinfo build/run-dossier-v2-sat/report.pdf
  pdftoppm -png -r 144 build/run-dossier-v2-sat/report.pdf \
    "$T98_PDF_QA/sat"
  pdfinfo build/run-dossier-v2-unsat-search/report.pdf
  pdftoppm -png -r 144 build/run-dossier-v2-unsat-search/report.pdf \
    "$T98_PDF_QA/unsat"
  ```

  Inspect every rendered page. Reject pixelation, crushed wide figures, tiny
  labels, overflow, broken whitespace, SAT-only witness figures in UNSAT, or
  any description of a failed leaf as a certificate.

- [ ] **Step 2: Run the complete repository closing matrix**

  ```bash
  make check
  make pages-check
  make strict-check CC=gcc
  make strict-check CC=clang
  make sanitizer-check
  make analyzer-check
  make valgrind-check
  make cachegrind-check
  make parser-fuzz-smoke
  make coverage
  make run-dossier-smoke
  make run-dossier-v2-smoke
  cd renderer
  uv run --locked pytest -q
  ```

- [ ] **Step 3: Review documentation ownership and duplication**

  Confirm README answers what the project is and how to enter it; Pages
  explains how it works; reference defines contracts; evidence records
  measurements; each PDF reports one captured run. Consolidate repeated
  multi-paragraph explanations rather than maintaining copies.

- [ ] **Step 4: Perform publication hygiene checks**

  ```bash
  git diff --check origin/main...HEAD
  git status --short --branch
  git diff --summary origin/main...HEAD
  git ls-files build .uv-cache .venv renderer/.venv
  ```

  Confirm no build output, screenshots, caches, credentials, private keys or
  unexpected executable modes are tracked.

- [ ] **Step 5: Obtain independent whole-branch review**

  Review the complete diff against this plan and the primary spec. Resolve all
  Critical and Important findings with a focused test-first correction and a
  scoped re-review.

- [ ] **Step 6: Record the freeze and stop**

  Update only checklist items proven by the final evidence. Record remaining
  minor visual issues separately; do not add another visual merely because it
  is possible. Commit the evidence update with a result-oriented subject.

  ```bash
  git add docs/plans/2026-08-31-narrative-migration-checklist.md \
    .superpowers/sdd/2026-09-05-t98-visual-documentation
  git commit -m "Freeze the verified T98 presentation layer"
  ```

## Definition of Done

T98 is complete only when concrete visuals explain reduction routing, local
tile compatibility, propagation, MRV/tie-breaking, DFS, conflict, rollback,
the six optimized mechanisms, both project-owned Z3 encodings, tiling checks
and Boolean witness extraction; observed traces remain available as evidence;
SAT and search-UNSAT identities remain separate; Pages and PDFs are readable
at their intended sizes; v1 dossier behavior is unchanged; every required gate
is green; and no profiling, `TaskPlan` or OpenMP work has entered the branch.
