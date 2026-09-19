---
layout: page
title: Observed-run dossiers and example index
permalink: /run-dossiers/
page_class: reference
description: Opt-in v1 diagnostic reports and v2 multi-engine captures built from hash-bound traces, summaries, witnesses, and raw run metadata.
section: Architecture and correctness
document_kind: Reproduction and report contract
status: Current implementation
updated: 2026-09-01
nav_order: 35
---

# Observed-run dossiers and example index

The named-case generator dispatches closed v1 and v2 case documents to
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
remains the canonical explanation of event semantics, truncation, and replay.
The [reference solver component]({{ '/components/reference-solver/' | relative_url }})
owns the public reference animation. The [static snapshot contract]({{ '/wang-explainability-snapshots/' | relative_url }})
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

### New CM1-in-3 input

Run `make demo-setup` once, then use the installed environments offline:

```sh
make demo INPUT='path/to/new formula.cm13' TIMEOUT=300
```

The input needs a `p cm13 n n` header, followed by `n` clauses. Each clause has
three positive variable indices in `1..n` and ends in `0`. Every variable must
occur exactly three times across all clauses, counting repeated occurrences
within one clause. Lines beginning with `c` are comments. For example:

```text
c Three variables, each with three occurrences
p cm13 3 3
1 1 2 0
1 2 3 0
2 3 3 0
```

No expected result is supplied. The demo copies the original bytes before
parsing, reduces once, and runs reference, optimized, Boolean Z3 and Wang Z3
once each. The dossier and PDF consume that same validated capture. Named
cases below use the same capture producer and retain their configured metadata.

Each invocation creates a separate `build/demo/run-*` directory containing
`input.cm13`, diagnostic `input.json` (original path/name and SHA-256),
`worker.log`, and the completed `dossier/` with `run.json`, source/trace assets,
figures, `report.tex` and `report.pdf`. Input names with spaces or shell/Make
metacharacters are passed literally; quote the command argument as above.
The portable name inside a new dossier is always `input.cm13`.

The command prints real operations as they start. `worker.log` keeps the full
worker output even if a slow terminal or pipe cannot display every message.
`TIMEOUT` defaults to 300
seconds and must be finite and positive. It covers the worker's preflight,
input copy, native/Z3 capture, checks, figures and LaTeX. Timeout or Ctrl-C stops
the worker and its child processes; SIGTERM is also handled. The log and copied
input survive failures, while any staging artifacts remain diagnostic only.
The command prints `dossier=` and `pdf=` only after successful completion.

For explicit output and trace capacity, use the same supervised Python entry:

```sh
python3 tools/demo.py 'path/to/new formula.cm13' \
  --output build/my-demo --timeout 300 --event-capacity 100000
```

The output directory must be new, including when a symlink already occupies
that path. Trace capacity is an integer from 2 to 100000 per native solver;
the default is 100000 and checkpoints are disabled. Exhaustion fails without
rerunning either solver. Missing dependencies require `make demo-setup`; the
demo never builds, installs or downloads them itself.

Malformed input, missing dependencies, UNKNOWN, engine disagreement, incomplete
trace and failed checks produce distinct diagnostic messages. Timeout exits
with 124; handled SIGINT/SIGTERM exits with 130/143. These are process outcomes,
not UNSAT results. GNU Make reports a failed recipe with its own nonzero exit.
UNSAT succeeds only when all four engines agree on that terminal result, and
still carries no independent UNSAT certificate. Arbitrary inputs may exceed the
time or trace limits; neither option promises completion.

Wide regions appear as overview figures in the PDF. Use the PDF viewer's zoom
or the full-resolution PNG frames under `dossier/assets/narrative/` to inspect
individual cells and trace labels; a whole-page view cannot show every detail.

### Named cases

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

The v2 directory contains `run.json`, the copied CM1-in-3 input, two
existing trace-v3 manifests, their content-addressed snapshots, and the two
existing Z3 summary documents. Both native manifests bind the same formula,
tileset, region, and construction-provenance hashes. Agreement means equal
SAT/UNSAT status plus independently valid SAT witnesses; different valid
witnesses are not required to be byte-equal. UNKNOWN, mismatch, a truncated
trace, or a failed checker aborts the capture before installation.

### Result expectation and recorded outcome

The v2 case and run contracts keep `expected_status` required and accept
`"sat"`, `"unsat"`, or `null`. A null value means no expected result was supplied;
it is never filled from a solver result and does not mean UNKNOWN. All four
named engines must first report the same terminal result. A supplied expectation
is then checked as an additional assertion. Witness checks, presentation
applicability, and PDF status follow the observed agreement. For an absent
expectation the PDF says so explicitly.

The standalone narrative manifest adds `case.observed_status` exactly when
`case.expected_status` is null. Known cases retain the existing three-field case
shape. Verification receipts preserve the nullable expectation and use their
four recorded agreement statuses; they need no extra status field. Bundle
loading also binds each native source identity and trace status/completeness,
and each Z3 summary status, to its run record.

Updated readers continue to accept earlier v2 dossiers, and known-case output
and canonical asset identities stay unchanged. Earlier strict readers reject
the new nullable variant. V1 retains its existing contracts. This is an
extension of the existing v2 and narrative contracts, with no new pipeline or
independent UNSAT certificate.

The downstream shared-asset pass then consumes only that validated capture.
Its closed `wang-narrative-assets-v1` manifest names fixed component assets,
not generic stages: Boolean and Wang Z3 encoding order, canonical region
construction, observed reference and optimized traces, the six checker
records, the checked square/generalized/hex witness sequence, the six retained
optimized mechanisms, and the complete pipeline overview. Every GIF record
contains one reduced-motion PNG, contact sheet, caption, alt text, semantic
label, source identity, completeness/selection scope, and all static frame
hashes.

Trace frames use `semantic-milestones-v1`, which selects event and phase
transitions before deterministic gap filling; it is distinct from uniform
sampling and reuses the same single replay as PNG, contact-sheet, and GIF
encoding. For SAT, `run.json` binds the three reserved static presentation
artifacts and their hashes. For UNSAT they remain null, while the asset bundle
records an explicit not-applicable panel and never fabricates a witness or
certificate. The separate example is versioned at
`examples/run-cases-v2/pipeline-unsat-search.json`.

The default v2 command stops after the validated capture and shared assets. It
does not import the LaTeX formatter, invoke a TeX compiler, or produce
`report.tex` and `report.pdf`. With pdfLaTeX available, add `--pdf` when a
static report is wanted:

```sh
make shared
uv run --frozen python tools/generate_run_dossier.py \
  examples/run-cases-v2/pipeline-sat.json \
  build/run-dossiers/pipeline-sat-v2-pdf \
  --pdf
```

The v2 formatter consumes only the validated `run.json` and static PNGs already
named by the asset manifest. It does not solve, invoke Z3, verify, replay, or
render again. SAT reports include the checked witness presentations;
search-UNSAT reports mark witness-only sections not applicable and do not
invent a certificate.

The opt-in compiler uses the same isolated, no-shell-escape execution and
private TeX state as v1. TeX and PDF files are staged with the complete dossier
and installed atomically; compilation failure leaves no partial destination.
The v1 command, formatter, output shape, and `--tex-engine` behavior remain
unchanged.

All v2 durations use one monotonic nanosecond clock and are labelled
`run-specific-observation-not-a-benchmark`. They are raw facts about that
capture, never a performance comparison. SAT-only checker timings are null for
UNSAT rather than fabricated as zero.
