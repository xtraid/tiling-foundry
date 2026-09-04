# Narrative migration checklist

**Status:** frozen inventory and migration map

**Baseline:** `17edabc5c956cb6f00cbb19266b7701a04e30ee2` on 31 August
2026

This checklist applies the
[narrative architecture contract](2026-08-31-narrative-architecture-contract.md)
to every current public page, public Pages asset, dossier/schema contract, and
known excluded documentation source. Unchecked implementation actions belong
to later work; this inventory itself makes no public-site or asset change.

## 1. Baseline audit

- [x] Confirm `origin/main` points to the merged MRV-index squash commit
  `17edabc` and descends directly from `ca8690c`.
- [x] Confirm the merged tree is byte-identical to reviewed feature commit
  `cb33f37`.
- [x] Confirm all ten pull-request checks completed successfully.
- [x] Confirm 27 public technical documents plus `docs/index.md`.
- [x] Confirm all 27 current technical permalinks are unique and retained.
- [x] Confirm five public animation bundles, two public SVG files, one public
  historical PDF, site CSS, and site JavaScript.
- [x] Confirm 12 closed JSON schemas, four v1 run cases, and one v1 dossier
  generator family.
- [x] Confirm canonical SAT source `tests/instances/pipeline_sat.cm13` and
  separate search-UNSAT source `tests/instances/pipeline_unsat_search.cm13`.
- [x] Record their SHA-256 identities in the architecture contract, together
  with the separate `unsat-search` case-file identity.

## 2. Public page inventory

The `Destination` column names the future index or story owner. `Keep route`
is mandatory for every existing permalink.

| Source and current route | Class | Destination / relationship | Frozen migration action |
| --- | --- | --- | --- |
| `docs/index.md` `/` | `story` | Homepage story owner | Rewrite only after shared assets exist; preserve technical catalog access |
| `docs/development_principles.md` `/development_principles/` | `reference` | `/reference/`; linked from `/pipeline/` | Keep route and current architecture authority |
| `docs/reduction_notes.md` `/reduction_notes/` | `reference` | `/reference/`; linked from Yang–Zhang component | Keep route and mathematical/project convention boundary |
| `docs/references.md` `/references/` | `reference` | `/reference/`; linked from relevant components | Keep route and external-source policy |
| `docs/run_dossiers.md` `/run-dossiers/` | `reference` | Dossier index owner | Keep v1 meaning; add visibly separate v2 links only after v2 exists |
| `docs/serial_solver_implementation_guide.md` `/serial_solver_implementation_guide/` | `reference` | `/reference/`; linked from both native solver components | Keep route; replace embedded trace animation with link to its component owner |
| `docs/solver_comparison_benchmark.md` `/solver_comparison_benchmark/` | `reference` | `/reference/`; linked from pipeline/evidence | Keep route as protocol, not an observed result |
| `docs/solver_performance_scope.md` `/solver_performance_scope/` | `reference` | `/reference/`; linked from optimized component | Keep route as optimization methodology |
| `docs/wang_explainability_snapshots.md` `/wang-explainability-snapshots/` | `reference` | `/reference/`; linked from pipeline and visualization | Keep route and snapshot contract responsibility |
| `docs/wang_reduction_explanation.md` `/wang-reduction-explanation/` | `reference` | `/reference/`; linked from Yang–Zhang component | Keep route and native-provenance contract responsibility |
| `docs/wang_solution_v1.md` `/wang-solution-v1/` | `reference` | `/reference/`; linked from verification/visualization | Keep route and square-solution contract responsibility |
| `docs/wang_solver_trace.md` `/wang-solver-trace/` | `reference` | `/reference/`; linked from native solver components | Keep route; replace embedded reference animation with link to owner |
| `docs/wang_square_to_hex.md` `/wang-square-to-hex/` | `reference` | `/reference/`; linked from visualization | Keep route and proof/checker responsibility; link to owned transformation animation |
| `docs/wang_z3_edge_table_2026-08-24.md` `/wang_z3_edge_table_2026-08-24/` | `reference` | `/reference/`; linked from Wang Z3 component | Keep route as oracle-model reference; move animation ownership to component |
| `docs/yang_zhang_builder_design.md` `/yang_zhang_builder_design/` | `reference` | `/reference/`; linked from Yang–Zhang component | Keep route and builder contract; move animation ownership to component |
| `docs/designs/2026-08-21-witness-extension-design.md` `/witness_correspondence/` | `reference` | `/reference/`; linked from verification | Keep route and witness-correspondence design |
| `docs/coverage_baseline_2026-08-22.md` `/coverage_baseline_2026-08-22/` | `evidence` | `/evidence/` | Keep route, source identity, and no-threshold limitation |
| `docs/parser_fuzz_smoke_2026-08-22.md` `/parser_fuzz_smoke_2026-08-22/` | `evidence` | `/evidence/` | Keep route, corpus, budget, and platform limits |
| `docs/solver_byte_support_2026-08-20.md` `/solver_byte_support_2026-08-20/` | `evidence` | `/evidence/`; linked from optimized component | Keep route; remove duplicate animation embed and link to component owner |
| `docs/solver_comparison_smoke_2026-08-21.md` `/solver_comparison_smoke_2026-08-21/` | `evidence` | `/evidence/` | Keep route and single-environment interpretation limits |
| `docs/solver_dynamic_stack_2026-08-17.md` `/solver_dynamic_stack_2026-08-17/` | `evidence` | `/evidence/`; linked from optimized component | Keep route; remove duplicate animation embed and link to component owner |
| `docs/solver_initial_trail_2026-08-17.md` `/solver_initial_trail_2026-08-17/` | `evidence` | `/evidence/`; linked from optimized component | Keep route; remove duplicate animation embed and link to component owner |
| `docs/solver_mrv_index_2026-08-28.md` `/solver_mrv_index_2026-08-28/` | `evidence` | `/evidence/`; linked from optimized component | Keep route and accepted sixth-mechanism evidence |
| `docs/solver_queue_dedup_2026-08-20.md` `/solver_queue_dedup_2026-08-20/` | `evidence` | `/evidence/`; linked from optimized component | Keep route; remove duplicate animation embed and link to component owner |
| `docs/solver_queue_trail_profile_2026-08-20.md` `/solver_queue_trail_profile_2026-08-20/` | `evidence` | `/evidence/` | Keep route and profiling limits |
| `docs/solver_reference_profile_2026-08-17.md` `/solver_reference_profile_2026-08-17/` | `evidence` | `/evidence/`; linked from reference component | Keep route and baseline limits |
| `docs/solver_sat_ownership_2026-08-20.md` `/solver_sat_ownership_2026-08-20/` | `evidence` | `/evidence/`; linked from optimized component | Keep route; remove duplicate animation embed and link to component owner |
| `docs/historical_architecture.md` `/historical_architecture/` | `history` | History group under `/reference/` | Keep route as sole context/download page for original PDF |

Classification totals are one `story`, 15 `reference`, 11 `evidence`, and one
`history` across the 28 current public page sources.

## 3. New story-page checklist

- [x] Add `/pipeline/` only after its shared composition and source manifest
  are validated.
- [x] Add `/worked-example/` using only `pipeline_sat.cm13`; do not splice in
  `unsat-search` frames or timings.
- [x] Add all eight component routes with the exact frozen section order.
- [x] Add `/reference/` and `/evidence/` as authored indexes, not generated
  prose.
- [x] Keep history visually distinct inside `/reference/`.
- [x] Keep `/run-dossiers/` an index; do not render `run.json` as Markdown.
- [x] Add taxonomy, component-section, primary-owner, semantic-label,
  fallback, caption, alt-text, permalink, and generated-output checks.
- [x] Build Pages without generating any dossier or invoking LaTeX.

## 4. Public asset inventory

Each directory row covers every file currently present in that directory.
"Later action" does not authorize changes in this contract-freeze work.

| Current asset(s) | Current producer/source | Frozen owner | Later action |
| --- | --- | --- | --- |
| `docs/assets/images/builder-routing/{trace.gif,contact-sheet.png,frame-00.png...frame-05.png}` | `render_builder_assets`; reduction v2 manifest and native gadget spans for `pipeline_sat.cm13` | `/components/yang-zhang/` | Relabel `canonical-construction`; retain or replace once; old reference links to owner |
| `docs/assets/images/optimized-mechanisms/{trace.gif,contact-sheet.png,frame-00.png...frame-05.png}` | `render_optimized_assets`; synthetic five-mechanism list | `/components/optimized-solver/` | Replace with six mechanisms including MRV; label `didactic`; all evidence pages link |
| `docs/assets/images/solver-trace/{trace.gif,contact-sheet.png,frame-000000.png,frame-000413.png,frame-000827.png,frame-001240.png,frame-001654.png,frame-002516.png,frame-002517.png,frame-002895.png}` | `render_trace_assets`; complete 2,896-event reference v3 bundle for `pipeline_sat.cm13` | `/components/reference-solver/` | Label `observed`; retain or replace once; contract and serial guide link |
| `docs/assets/images/square-to-hex/{trace.gif,contact-sheet.png,frame-00.png...frame-03.png}` | `render_hex_assets`; checked `tests/fixtures/wang_solution_v1_square_sat.json` | `/components/visualization/` | Replace with canonical SAT witness; label `verified-transformation`; old proof page links |
| `docs/assets/images/z3-encoding/{trace.gif,contact-sheet.png,frame-00.png...frame-04.png}` | Wang `z3-encoding-summary-v1` fixture for `pipeline_sat.cm13` | `/components/wang-z3/` | Label `encoding-order`; retain or replace once; oracle reference links |
| `docs/assets/images/wang-edge-convention.svg` | hand-authored square edge convention, currently referenced only by excluded post template | `/components/tileset/` | Treat as `didactic`; either adopt there or remove only after no source references remain |
| `docs/assets/images/tile-mark.svg` and `docs/_includes/tile-mark.html` | hand-authored site identity | site shell (`docs/_layouts/default.html`) | Retain as chrome; narrative semantic labels do not apply |
| `docs/Wang23_C_OpenMP_Architecture_Spec_Merged.pdf` | original Italian architecture document | `/historical_architecture/` | Retain bytes and sole contextual owner |
| `docs/assets/css/site.css` | site presentation | site shell | Reuse; add only narrative styles justified by final pages |
| `docs/assets/js/document-toc.js` | technical-page TOC enhancement | `docs/_layouts/page.html` | Retain; no dossier dependency |
| all ten modules under `docs/assets/js/wang/` | decorative background field | `docs/_layouts/default.html` | Retain; no semantic or pipeline claim |

No public bundle may be copied under a second route. If a replacement changes
filenames, update all source links in the same migration and let generated-site
checks prove the old files are unreferenced before deletion.

## 5. Non-public raster and fixture sources

- [x] Record `renderer/test_data/pipeline_sat_formula.png`,
  `pipeline_sat_reduction.png`, `pipeline_sat_region_square.png`,
  `pipeline_sat_region_hex.png`, `pipeline_sat_tileset_square.png`, and
  `pipeline_sat_tileset_hex.png` as renderer goldens, not public narrative
  ownership.
- [x] Record `renderer/test_data/wang_solution_v1_*` images as renderer
  goldens, not proof or public story assets.
- [x] Record legacy renderer input/output PNGs and `renderer/project_python.pdf`
  as imported renderer-project material, outside the narrative migration.
- [x] Record `tests/fixtures/pipeline_sat_explain/`,
  `pipeline_sat_reduction_explain/`, `pipeline_sat_solver_trace/`, and
  `pipeline_sat_z3/` as versioned semantic sources for later shared assets.
- [x] Do not promote a renderer golden to Pages merely because it is
  deterministic; it must have the canonical instance, semantic label, owner,
  validator chain, caption, alt text, and fallback required by the contract.

## 6. Closed-contract inventory

| Contract | Current canonical documentation | Narrative disposition |
| --- | --- | --- |
| `cm13-formula-snapshot-v1` | `/wang-explainability-snapshots/` | Retain unchanged; bind formula identity into v2 by hash |
| `wang-tileset-snapshot-v1` | `/wang-explainability-snapshots/` | Retain unchanged; source for atomic/generalized presentation |
| `wang-region-snapshot-v1` | `/wang-explainability-snapshots/` | Retain unchanged; source for reduction and region views |
| `wang-reduction-explanation-v1` | `/wang-reduction-explanation/` | Retain unchanged; source for native construction provenance |
| `wang-solution-v1` | `/wang-solution-v1/` | Retain unchanged; sole square witness transport |
| `wang-solver-trace-v1` | `/wang-solver-trace/` | Retain unchanged; sole native event/replay source |
| `z3-encoding-summary-v1` | `/wang_z3_edge_table_2026-08-24/` and snapshot docs | Retain unchanged; distinguish project encoding order from Z3 internals |
| `wang-explain-manifest-v1` | `/wang-explainability-snapshots/` | Retain static-stage meaning |
| `wang-explain-manifest-v2` | `/wang-reduction-explanation/` | Retain provenance-stage meaning |
| `wang-explain-manifest-v3` | `/wang-solver-trace/` | Retain trace-stage meaning |
| `wang-run-case-v1` | `/run-dossiers/` | Preserve exact diagnostic case meaning and initial-domain override support |
| `wang-run-dossier-v1` | `/run-dossiers/` | Preserve exact single-native-run report meaning and output shape |
| `wang-narrative-assets-v1` | `/run-dossiers/` and `renderer/README.md` | Closed downstream record for fixed component assets, accessibility metadata, source identities, semantic milestones, and static PDF inputs |

- [x] Add separate closed v2 case and dossier contracts; do not extend or
  loosen either v1 schema.
- [x] Name Boolean Z3, reduction, reference, optimized, Wang Z3, verification,
  presentation, timings, and artifacts explicitly; do not use a generic stage
  array or plugin registry.
- [x] Require one formula/region/tileset/provenance identity across all named
  native and Z3 components.
- [x] Forbid initial-domain overrides in full-pipeline v2 cases.
- [x] Capture each engine once and reuse its result; do not solve during
  validation, rendering, Pages build, or PDF formatting.

## 7. Dossier v1 preservation checklist

- [x] Four current v1 cases remain:
  `sat-end-to-end`, `unsat-root-conflict`, `unsat-propagation`, and
  `unsat-search`.
- [x] `sat-end-to-end` and `unsat-search` have no initial-domain overrides;
  the two constrained diagnostic cases remain explicitly configured Wang
  solves rather than claims about the unconstrained formula.
- [ ] Keep v1 schema bytes/meaning and current cases compatible through every
  v2 change.
- [ ] Keep v1 formatter/template isolated from v2; share only focused helpers
  behind thin dispatch.
- [ ] Keep v1 atomic destination install, isolated pdfLaTeX, no-shell-escape,
  run-specific timing identity, and diagnostic-UNSAT boundary.
- [ ] Run the existing SAT and all three UNSAT v1 dossier tests after each v2
  contract, asset, and PDF change.

## 8. Shared-asset migration order

1. [x] Freeze and test the exact generalized 14-to-23 mapping without changing
   the atomic tileset or standard square/hex output.
2. [x] Capture the explicit v2 multi-engine fields once per engine and bind all
   component identities by SHA-256.
3. [x] Produce shared assets through the existing validators, replay, and
   compositor, including static semantic milestones.
4. [x] Update the optimized didactic asset to all six accepted mechanisms,
   keeping it secondary to observed trace output.
5. [x] Generate reduced-motion fallback, contact sheet, caption, alt text, and
   semantic record for every GIF.
6. [x] Move public ownership to component pages without duplicating files or
   explanations; update old pages to links in the same change.
7. [x] Prove every remaining public asset has exactly one embedding owner and
   every internal link resolves in generated HTML.

## 9. Pages implementation gates

- [x] Add exactly one public class to every cataloged document and reject
  unknown or missing classes.
- [x] Enforce the nine component sections in order.
- [x] Enforce one primary asset owner per component and uniqueness across
  Pages.
- [x] Enforce the five allowed semantic labels and reject
  `canonical-example`.
- [x] Enforce GIF owner, nonempty alt text, reduced-motion PNG, caption,
  contact sheet, source, and scope.
- [x] Preserve all current permalinks and validate all literal and generated
  links/anchors.
- [x] Distinguish the general pipeline from the named SAT worked example in
  visible copy.
- [x] Keep technical references and dated evidence available without
  duplicating their prose in story pages.
- [x] Build and check the site with no native build, renderer environment,
  dossier generation, or LaTeX installation.

## 10. V2 PDF implementation gates

- [ ] Follow the nine-section order frozen in the architecture contract.
- [ ] Consume the same validated facts and static assets as the captured v2
  run; do not consume Pages HTML or Markdown.
- [ ] Embed no GIF/video and perform no second render or replay.
- [ ] Mark assignment, witness, verification, generalized witness, and hex
  witness not applicable for UNSAT without fabricating a certificate.
- [ ] Keep raw timings in their named component sections and full detail in the
  appendix; make no general performance comparison.
- [ ] Compile with isolated, reproducible, no-shell-escape pdfLaTeX rules.
- [ ] Validate self-containment, hashes, source identity, component agreement,
  static-template inputs, and partial-failure cleanup.
- [ ] Prove v1 cases and output contracts remain compatible.

## 11. Excluded documentation sources

| Source | Status | Migration rule |
| --- | --- | --- |
| `docs/plans/2026-08-21-witness-extension.md` | completed internal plan | Keep excluded as implementation history |
| `docs/plans/2026-08-25-pages-overview-audit.md` | completed internal audit/plan | Keep excluded; this contract supersedes its deferred sitemap choices where they differ |
| `docs/plans/2026-08-31-narrative-architecture-contract.md` | current internal contract | Keep excluded; downstream implementation references it |
| `docs/plans/2026-08-31-narrative-migration-checklist.md` | current internal checklist | Keep excluded; update checkmarks only with evidence |
| `docs/post-template.md` | excluded authoring scaffold | Keep excluded; do not treat its sample SVG as public ownership |
| `docs/_posts/.gitkeep` | empty placeholder | Keep outside taxonomy until an authored post exists |

## 12. Final migration audit

- [x] The public catalog reports the expected counts for story, reference,
  evidence, and history.
- [x] All 27 legacy technical routes and `/` resolve after the migration.
- [x] Every new sitemap route resolves with one H1, description, canonical URL,
  and expected page class.
- [x] Every narrative asset has one owner, one source chain, and one allowed
  semantic label.
- [ ] No GIF is duplicated, embedded by two owners, missing a static fallback,
  or included in a PDF.
- [ ] `pipeline_sat.cm13` identities agree across the worked example, all
  engines, verification, presentation, Pages assets, and v2 dossier.
- [ ] `unsat-search` remains visibly and cryptographically separate.
- [ ] Removing documentation and explainability leaves core build, solve,
  oracles, verifier, and standard export functional.
- [x] Full suites, strict compilers, sanitizer, analyzer, dynamic analysis,
  applicable profiling, renderer tests, Pages/Jekyll, TeX smoke, diff, secret,
  file-mode, and artifact checks are green before publication.
