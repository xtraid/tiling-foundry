---
layout: page
title: Observed-run dossiers and example index
permalink: /run-dossiers/
description: Opt-in v1 diagnostic reports and v2 multi-engine captures built from hash-bound traces, summaries, witnesses, and raw run metadata.
section: Architecture and correctness
document_kind: Reproduction and report contract
status: Current implementation
updated: 2026-09-01
nav_order: 35
---

# Observed-run dossiers and example index

The sole public generator dispatches closed v1 and v2 case documents to
separate implementations. Both are explicitly opt-in and leave parsing,
reduction, ordinary solving, snapshot export, and the default Wang renderer
unchanged.

The v1 path turns one configured native run into a self-contained directory
with `run.json`, `report.tex`, `report.pdf`, and `assets/`. Its four diagnostic
cases, schemas, formatter, template, initial-domain behavior, and output shape
remain unchanged.

`run.json` is the authoritative report input. It records the source and Git
identity, environment, solver options and result, complete trace counters,
initial-domain overrides, raw stage durations, replay scope, and SHA-256 for
every referenced JSON or raster asset. The LaTeX document and PDF are derived
from that one document. They do not recalculate events, witness state, timing,
or provenance.

## Example index

Four strict case documents are versioned. Their classification is checked
against the observed trace rather than trusted as prose.

| Case | Configured result | Required observed shape | Case source |
| --- | --- | --- | --- |
| SAT end to end | SAT | complete trace, independently checked witness, square and checked hex views | [case JSON]({{ site.repository_url }}/blob/main/examples/run-cases/sat-end-to-end.json) |
| Immediate root conflict | UNSAT | three events: root, initial conflict, result; no propagation or search | [case JSON]({{ site.repository_url }}/blob/main/examples/run-cases/unsat-root-conflict.json) |
| Initial propagation contradiction | UNSAT | domain reductions and propagation reach an initial conflict before any decision | [case JSON]({{ site.repository_url }}/blob/main/examples/run-cases/unsat-propagation.json) |
| Non-superficial search | UNSAT | complete depth-two run with four decisions, three conflicts, and four backtracks | [case JSON]({{ site.repository_url }}/blob/main/examples/run-cases/unsat-search.json) |

The first three cases use the same small formula so the observed boundary is
easy to compare. The two constrained UNSAT cases deliberately exercise the
public initial-domain option: their UNSAT status describes that configured
Wang solve, not the unconstrained source formula. The search case uses a
separate cubic monotone input whose unconstrained optimized run reaches depth
two before exhausting all branches.

This page is only an index. The [solver trace contract]({{ '/wang-solver-trace/' | relative_url }})
remains the canonical explanation of event semantics, truncation, replay, and
the existing animation assets. The [static snapshot contract]({{ '/wang-explainability-snapshots/' | relative_url }})
defines formula and region views, while the [square-to-hex reference]({{ '/wang-square-to-hex/' | relative_url }})
defines the presentation-only port. No animation, explanation, or generated
run narrative is copied here.

## Reproduce one dossier

Build the shared native library, provide pdfLaTeX, and run the sole generator:

```sh
make shared
uv run --frozen python tools/generate_run_dossier.py \
  examples/run-cases/sat-end-to-end.json \
  build/run-dossiers/sat-end-to-end \
  --tex-engine pdflatex
```

The destination must not exist. Every intermediate is written below a sibling
staging directory, the trace bundle is validated before rendering, and the
completed directory is installed with one rename. A failed render or TeX
compile leaves no partial destination.

The generator calls the isolated renderer through its locked environment. A
single replay composes the selected frames used for individual PNGs, the
contact sheet, and the optional GIF. The PDF embeds the already-produced
contact sheet and static square/hex PNGs; it never embeds viewer-dependent GIF
or video content. UNSAT reports contain region views rather than inventing a
solution.

pdfLaTeX is invoked directly, never through a shell, with
`-no-shell-escape`, restricted input/output policy, a private TeX home, UTC,
and `SOURCE_DATE_EPOCH` derived from the recorded run time. The CI smoke
installs TeX only inside its disposable runner. TeX is not a runtime or root
Python dependency.

## Timing and evidence boundary

The monotonic durations for parse, region build, solve, export, render, and SAT
witness verification are raw evidence from one environment. They are excluded
from snapshot identity and are not performance gates. The native solver has no
Z3-style encoding stage, so `encoding` is explicitly recorded as not applicable
rather than reported as a fabricated zero-duration operation. Verification is
also explicitly not applicable to UNSAT runs because the trace is diagnostic,
not an independently checked certificate.

Every example requires a complete trace. Selected frames remain a presentation
subset of that trace. For UNSAT, `unsat_certificate` is always false: conflicts
and trail history diagnose what the run observed but do not constitute a
standalone mathematical proof of unsatisfiability.

## Full-pipeline v2 capture

`wang-run-case-v2` deliberately has no initial-domain override field. Its
canonical case follows `tests/instances/pipeline_sat.cm13` through the four
named engines and one shared native reduction:

```sh
make shared
uv run --frozen python tools/generate_run_dossier.py \
  examples/run-cases-v2/pipeline-sat.json \
  build/run-dossiers/pipeline-sat-v2
```

The v2 implementation parses and reduces once, then runs the traced reference
and optimized solvers exactly once while the same native formula and reduction
are alive. It invokes the existing Boolean Z3 and Wang Z3 summary producers
once each. SAT assignments and tilings are checked with the existing pure
Python checkers; native tilings also retain the assignment extracted by the
existing Yang--Zhang witness bridge.

The raw v2 directory contains `run.json`, the copied CM1-in-3 input, two
existing trace-v3 manifests, their content-addressed snapshots, and the two
existing Z3 summary documents. Both native manifests bind the same formula,
tileset, region, and construction-provenance hashes. Agreement means equal
SAT/UNSAT status plus independently valid SAT witnesses; different valid
witnesses are not required to be byte-equal. UNKNOWN, mismatch, a truncated
trace, or a failed checker aborts the capture before installation.

The raw-capture implementation intentionally produces no v2 PDF or narrative
raster. The closed run contract names the square, generalized, and hex
relationships and leaves their artifact references null for the shared-asset
pass. A later PDF formatter will consume those validated static assets without
solving, checking, replaying, or rendering again.

All v2 durations use one monotonic nanosecond clock and are labelled
`run-specific-observation-not-a-benchmark`. They are raw facts about that
capture, never a performance comparison. SAT-only checker timings are null for
UNSAT rather than fabricated as zero.
