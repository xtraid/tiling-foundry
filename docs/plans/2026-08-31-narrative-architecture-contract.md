# Narrative architecture contract

**Status:** frozen for the narrative and multi-model dossier phase

**Audited baseline:** `17edabc5c956cb6f00cbb19266b7701a04e30ee2`
(`Add lazy optimized MRV indexing (#20)`) on 31 August 2026

**Scope:** editorial architecture, content ownership, asset semantics, and the
shared vocabulary between GitHub Pages and the future full-pipeline dossier.
This document does not change public pages, schemas, generators, algorithms,
or generated assets.

This is the normative input to the remaining narrative work. The companion
[migration checklist](2026-08-31-narrative-migration-checklist.md) records the
disposition of every current public page and asset.

## 1. Product boundary

GitHub Pages and the PDF dossier have different jobs:

- **Pages** explains the project, its stable components, their relationships,
  and their trust boundaries. Its prose is authored and reviewed Markdown.
- **A v2 dossier** records one named formula moving through the implemented
  components in one captured run. Its prose scaffolding is fixed, and its
  facts and static figures come from that run's validated manifest.
- **The v1 dossier** remains a diagnostic report for one configured native
  solve. It is not reinterpreted as a multi-model report.

Both downstream products may consume the same validated contracts and raster
outputs. They must not share generated prose, navigation, a database, or a
generic stage engine. The dependency direction remains:

```text
native core and independent oracles
  -> immutable Python models and existing closed JSON contracts
  -> one validator / replay / compositor chain
  -> authored Pages or an opt-in static PDF
```

Deleting Pages, LaTeX, dossier formatters, and renderer presentation modules
must leave parsing, reduction, native solving, both Z3 oracles, independent
verification, and ordinary square-solution export functional.

## 2. Content taxonomy

Every public Markdown document has exactly one editorial class:

| Class | Meaning | May make current general claims? | Typical destination |
| --- | --- | --- | --- |
| `story` | Human-first explanation of the pipeline or one clearly named example | Yes, when backed by current references and artifacts | Home, pipeline, worked example, and component pages |
| `reference` | Maintained contract, methodology, implementation reference, or bibliography | Yes, within its explicit scope | `/reference/` index and unchanged canonical route |
| `evidence` | Dated, source-bound, corpus-bound, or environment-bound observation | No universal claim; limitations stay adjacent to results | `/evidence/` index and unchanged canonical route |
| `history` | Superseded or context-only design retained for provenance | No current implementation claim | History group in `/reference/` and unchanged route |

The taxonomy is editorial metadata, not a new semantic schema for solver data.
Plans, authoring templates, and empty post placeholders remain excluded from
the public catalog and do not receive one of these public classes.

## 3. Canonical examples

### 3.1 SAT end-to-end example

`tests/instances/pipeline_sat.cm13` is the sole canonical SAT example for the
homepage, pipeline page, worked example, component examples, full-pipeline v2
capture, and v2 PDF. Its frozen source SHA-256 is
`3caaa6b29ac988fb4f51cc7071202d83ea1591ba6170e683b6da449cb3641542`.

The full-pipeline capture must not apply initial-domain overrides. Boolean Z3,
the native Yang–Zhang reduction, native reference, native optimized, Wang Z3,
the independent verifier, square export, generalized presentation, and the
checked square-to-hex port all refer to this one formula and its hash-bound
derived artifacts. An engine disagreement is an error, not an alternate story.

### 3.2 UNSAT search example

`tests/instances/pipeline_unsat_search.cm13`, configured by
`examples/run-cases/unsat-search.json`, is the separate example for conflict
and backtracking. The formula SHA-256 is
`ea2b8feb6eb8f4e722f1ec9021445c84858120c8567d42528631bdfb77400a94`;
the case-file SHA-256 is
`e81fe884ebbcdb8b25bbd32c0ca92577fd7a1fc9400a0b6296410ac7683bbcbb`.
It is an unconstrained optimized run with no initial-domain overrides and an
observed complete depth-two search.

It must always be named as a different formula and run. Its trace, frames,
timings, status, and artifact hashes must never be presented as later stages of
the SAT example. Root-conflict and propagation-contradiction v1 cases remain
diagnostic examples in the v1 dossier index; they are not part of the canonical
full-pipeline story.

## 4. Frozen sitemap

The following routes are additive. Existing routes listed in the migration
checklist remain valid.

| Route | Class | Canonical responsibility |
| --- | --- | --- |
| `/` | `story` | Project promise, clickable complete pipeline, selected verified result, and routes into story/reference/evidence |
| `/pipeline/` | `story` | Component order, data flow, independence, and trust boundaries |
| `/worked-example/` | `story` | `pipeline_sat.cm13` from source bytes to verified square and checked hex presentation |
| `/components/tileset/` | `story` | Fixed 23 atomic tiles, 14 generalized tiles, colors, matching, and identifiers |
| `/components/boolean-z3/` | `story` | Boolean CM1-in-3 oracle and project-owned encoding order |
| `/components/yang-zhang/` | `story` | Formula-to-region reduction, generalized decomposition, routing, and native provenance |
| `/components/reference-solver/` | `story` | Explanatory native baseline, observed trace, and result ownership |
| `/components/optimized-solver/` | `story` | Six measured serial mechanisms and an observed optimized trace |
| `/components/wang-z3/` | `story` | Independent finite-region oracle and project-owned encoding order |
| `/components/verification/` | `story` | Independent witness checks and the exact claims they do and do not establish |
| `/components/visualization/` | `story` | Square presentation, generalized overlay, and verified square-to-hex transformation |
| `/reference/` | `story` index | Maintained references plus a visibly separate history group |
| `/evidence/` | `story` index | Dated benchmark, profile, coverage, and fuzz evidence |
| `/run-dossiers/` | `reference` index | Links to v1 diagnostic reports and v2 full-pipeline reports without reproducing either report in Markdown |

`/reference/`, `/evidence/`, and `/run-dossiers/` are authored index pages.
They may derive lists from front matter but may not derive narrative prose from
`run.json`.

## 5. Permalink compatibility

All 27 current technical-document permalinks are frozen. The narrative phase
will not rename, remove, or repurpose any of them. In particular:

- `/run-dossiers/` keeps the v1 contract and gains clearly separated links to
  v2 outputs; it does not silently change the meaning of a v1 report;
- dated evidence routes remain dated evidence routes even when a component
  page summarizes the accepted mechanism;
- `/historical_architecture/` remains the only public context page that links
  the original architecture PDF;
- new component pages become canonical owners of narrative animations, while
  old technical pages retain their contract or evidence role and link to the
  new owner instead of embedding another copy.

Because no current route moves, the planned migration requires no redirects.
If a later phase proposes a move, it must add and test an explicit redirect or
compatibility page before removing the old content; a canonical-link change
alone is not a redirect.

## 6. Component-page template

Every `/components/.../` page uses this H2 sequence. A section may state that
an item is not applicable, but it may not be omitted.

1. **What it is** — one-paragraph role and stable project name.
2. **Why it exists** — the problem solved and why another component does not
   own that responsibility.
3. **Inputs and outputs** — named models/contracts, identities, and status
   behavior, including SAT/UNSAT/UNKNOWN where applicable.
4. **Mechanism** — the algorithm or transformation at the level needed to
   interpret output without duplicating the technical reference.
5. **Primary animation** — one owned asset, its semantic label, source,
   fallback, caption, and limits.
6. **Position in the pipeline** — predecessor, successor, and whether the
   edge is semantic input, independent cross-check, or presentation-only.
7. **Observed example** — the named `pipeline_sat.cm13` run. Solver pages may
   additionally link the separately named `unsat-search` example.
8. **Trust boundary** — what this component establishes, what independently
   checks it, and what it is forbidden to infer.
9. **Artifacts and references** — schemas, fixtures, source modules, current
   technical references, and relevant dated evidence.

Required front matter will identify `page_class: story`,
`component_id`, `pipeline_order`, and the owned primary asset. Exact checker
syntax is deferred to the Pages implementation, but those concepts and the
section sequence are frozen here.

## 7. Asset semantics and records

Every narrative raster or animation declares exactly one of these labels:

| Label | Permitted claim |
| --- | --- |
| `observed` | Data emitted by a named component execution. The record states whether the trace is complete and whether displayed frames are selected. |
| `canonical-construction` | Deterministic construction from versioned canonical inputs or provenance; it is not a clocked execution trace. |
| `encoding-order` | Project-owned order of constraint construction and returned summary/model; never Z3's internal search order. |
| `verified-transformation` | Deterministic transformation whose input/output relationship is checked by the existing transformation checker; the raster is not the checker. |
| `didactic` | Authored or synthetic explanation that makes no claim to record an execution. |

`canonical-example` is retired as an asset label. Existing builder material
maps to `canonical-construction`; the checked square-to-hex material maps to
`verified-transformation`.

Each asset record, whether represented in page front matter or a future closed
manifest, must name:

- one canonical owner route;
- semantic label and plain-language caption;
- source instance or canonical input;
- source contract and its SHA-256 identity when applicable;
- producer, validator/replay, and compositor;
- complete/selected/truncated scope when events are involved;
- GIF, static reduced-motion fallback, contact sheet, and alt text when
  animation is involved;
- whether the artifact is canonical Pages output or run-specific dossier
  output.

Two products may produce byte-identical files from the same input and
parameters, but they must not share ownership of one public file. A technical
page may link to an owned animation; only its owner embeds and explains it.

## 8. Page-to-asset-to-source ownership

This matrix fixes responsibilities, not final filenames. Assets marked `new`
are produced in the later shared-asset phase from the existing validator,
replay, and compositor chain.

| Canonical owner | Primary asset | Label | Authoritative source | Consumer rule |
| --- | --- | --- | --- | --- |
| `/` | selected verified SAT square output (`new`) | `observed` | v2 `pipeline_sat.cm13` run, `wang-solution-v1` artifact | Small result preview; links to worked example and visualization owner |
| `/pipeline/` | complete component-flow composition (`new`) | `observed` | one validated v2 SAT dossier manifest and its named stage artifacts | Owns pipeline-wide composition; component pages own component detail |
| `/worked-example/` | static end-to-end milestone sequence (`new`) | `observed` | same v2 SAT manifest; one semantic milestone selector | Static sequence only; links to owned component animations |
| `/components/tileset/` | 14 generalized / 23 atomic decomposition sequence, sheet, and legend (`new`) | `canonical-construction` | fixed canonical tile table and exact generalized mapping | Owns tile vocabulary; no solver claim |
| `/components/boolean-z3/` | Boolean constraint construction (`new`) | `encoding-order` | `tests/fixtures/pipeline_sat_z3/boolean-z3.json` or its v2 hash-equivalent capture | Project encoding and model only; no internal Z3 search claim |
| `/components/yang-zhang/` | builder routing plus generalized overlay (replacement) | `canonical-construction` | `pipeline_sat_reduction_explain/manifest.json`, native provenance, generalized mapping | Replaces ownership currently held by the builder reference |
| `/components/reference-solver/` | observed reference trace (current bundle may seed replacement) | `observed` | `pipeline_sat_solver_trace/manifest.json` or v2 reference capture | Complete trace, selected frames; reference page owns explanation |
| `/components/optimized-solver/` | observed optimized trace (`new`) | `observed` | v2 optimized capture for `pipeline_sat.cm13` | Primary asset; complete trace, selected frames |
| `/components/optimized-solver/` | six-mechanism overview (replacement) | `didactic` | measured mechanism list including the MRV index | Secondary asset; dated reports establish performance |
| `/components/wang-z3/` | Wang constraint construction (current bundle may seed replacement) | `encoding-order` | `tests/fixtures/pipeline_sat_z3/wang-z3.json` or v2 capture | Project encoding and returned model only |
| `/components/verification/` | named checker sequence (`new`) | `observed` | v2 verification records over the shared solution/region/tileset identities | Shows checks performed; does not invent an UNSAT certificate |
| `/components/visualization/` | square to generalized to checked hex sequence (`new`) | `verified-transformation` | verified v2 square witness, generalized mapping, and pure square-to-hex checker | Presentation follows verification and never establishes SAT |
| `/run-dossiers/` | none | n/a | v1 and v2 report indexes | Links only; no copied report narrative or animation |
| `/historical_architecture/` | original architecture PDF | n/a | `docs/Wang23_C_OpenMP_Architecture_Spec_Merged.pdf` | Sole public context and download owner |

The unsat-search observed trace is run-specific evidence linked from the two
solver pages and dossier index. It is not a second canonical pipeline asset and
must retain its separate source identity.

## 9. Existing bundle disposition

| Existing Pages bundle | Current source | Frozen target owner | Target label | Required migration |
| --- | --- | --- | --- | --- |
| `assets/images/builder-routing/` | reduction-explanation v2 manifest for `pipeline_sat.cm13` | `/components/yang-zhang/` | `canonical-construction` | Keep one physical bundle or replace it once; old builder reference links to owner |
| `assets/images/optimized-mechanisms/` | hard-coded didactic list of five retained mechanisms | `/components/optimized-solver/` | `didactic` | Replace with six-mechanism version including MRV; all dated reports link to owner |
| `assets/images/solver-trace/` | reference solver-trace v3 manifest for `pipeline_sat.cm13` | `/components/reference-solver/` | `observed` | Keep or replace once from shared pipeline; serial guide and trace contract link to owner |
| `assets/images/square-to-hex/` | checked `wang_solution_v1_square_sat.json` fixture | `/components/visualization/` | `verified-transformation` | Replace with canonical pipeline SAT witness when shared assets are ready |
| `assets/images/z3-encoding/` | Wang `z3-encoding-summary-v1` fixture for `pipeline_sat.cm13` | `/components/wang-z3/` | `encoding-order` | Keep or replace once; old oracle report links to owner |

No bundle is moved, regenerated, or deleted by this contract.

## 10. V2 PDF outline

The v2 PDF follows the pipeline exactly:

1. title, executive summary, instance identity, terminal status, and agreement;
2. readable CM13 input;
3. Boolean Z3 result, assignment when SAT, project encoding summary, and raw
   run timing;
4. Yang–Zhang region, generalized vocabulary, native provenance, and static
   semantic milestones `t0...tn`;
5. reference solver summary, selected observed frames, and raw metrics;
6. optimized solver summary, selected observed frames, six mechanisms, and raw
   metrics;
7. Wang Z3 encoding summary, result, raw timing, and agreement;
8. independent verification and, for SAT only, atomic square, generalized, and
   checked hex witness views;
9. reproducibility appendix containing commit, environment, parameters,
   identities, hashes, manifests, raw timings, and the reproduction boundary.

UNSAT reports retain the same order and explicitly mark assignment, witness,
and witness-only transformations not applicable. They do not fabricate a
solution, verification success, generalized witness, hex witness, or UNSAT
certificate.

The PDF embeds only static PNG milestones already produced by the shared asset
pass. It embeds no GIF/video and invokes no second compositor.

## 11. Fields shared by Pages and PDF

"Shared" means identical validated facts, names, and artifacts. It does not
mean shared prose or a global project-state object.

The future v2 closed contracts must provide named fields for:

- case ID, title, purpose, source path, source SHA-256, and SAT/UNSAT intent;
- repository commit and capture environment;
- formula, region, tileset, provenance, reference trace, optimized trace,
  solution, and Z3-summary schema names and SHA-256 identities;
- Boolean Z3, reference, optimized, and Wang Z3 configurations and terminal
  results;
- agreement among named engines, with mismatch represented as failure;
- independent verification performed/result fields and the verified solution
  identity when SAT;
- named raw timing fields whose identity is explicitly run-specific;
- named artifacts with relative path, SHA-256, media type, role, semantic
  label, source identity, and static/animated form;
- trace completeness, selection, capacity, and truncation facts;
- square, generalized, and hex presentation relationships.

The components are fixed and named. They are not encoded as a generic list of
stages, plugins, nodes, or callbacks. Pages may quote stable identities or
values and embed canonical assets, but all explanatory prose and navigation
remain Markdown. The PDF formatter may consume the fields directly, but it
must not recompute a solve, verification, replay, event count, or timing.

## 12. V1 dossier compatibility

The following are frozen throughout the narrative phase:

- `wang-run-case-v1` and `wang-run-dossier-v1` schema names, closed fields,
  classifications, and validation meaning;
- the four existing v1 case files and their distinction between unconstrained
  and initial-domain-override runs;
- `run.json` as the authoritative v1 report input;
- the v1 generator's single-native-engine scope, output directory shape,
  atomic installation, static/GIF asset behavior, and isolated pdfLaTeX rules;
- the rule that v1 UNSAT traces are diagnostic and not standalone proofs.

V2 uses separate case and dossier schema names, validators, formatter, and
template. It may share focused helpers through a thin CLI dispatch, but it may
not add optional v2 fields to v1 or scatter v2 conditions through the v1
formatter. Full-pipeline v2 cases forbid initial-domain overrides.

## 13. Decision log and non-goals

1. The site gains an authored narrative layer; it is not generated from a run.
2. The PDF records one run; it is not a general documentation mirror.
3. Existing permalinks and the v1 dossier meaning are preserved.
4. Every public animation has one owner; other pages link to it.
5. `pipeline_sat.cm13` is the sole SAT story instance; `unsat-search` is
   explicitly separate.
6. The five asset semantic labels in section 7 are exhaustive.
7. Component pages use the section order in section 6.
8. Existing validators, replay, compositor, exporter, and independent checker
   remain the only semantic implementations.
9. Generalized tiles are a presentation of the exact fixed 23-tile table, not
   a new tileset, solution schema, color model, or solver domain.
10. Raw run timings remain evidence for one environment and never become a
    benchmark claim in Pages or PDF.

Explicit non-goals are: an event bus, workflow/DAG engine, plugin or stage
registry, generated prose, client-side documentation application, a second
verifier, a second replay, a second compositor, a renderer dependency in the
core, new solver events for presentation, a Z3 internal-search trace claim,
GIFs in PDF, changing the standard square/hex CLI behavior, or implementing
any final narrative asset in this contract freeze.

## 14. Exit conditions for the contract freeze

This contract is complete only when:

- every current public page has one classification and an unchanged permalink;
- every current public asset has a current source and one frozen destination;
- every future component and primary asset has one owner;
- Pages, v2 PDF, and v1 dossier responsibilities cannot be confused;
- SAT and UNSAT examples cannot be mistaken for one run;
- downstream work can test semantic labels, component sections, ownership,
  fallbacks, links, and dossier identity without inventing editorial policy.

The companion checklist supplies those inventories and is part of this frozen
contract.
