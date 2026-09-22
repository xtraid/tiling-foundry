# Preparing v1.0.0 for the exam

## Goal

Prepare a version that can be cloned, set up, and demonstrated with a new
CM1-in-3 formula using a few commands. The output is a checked dossier with
figures and a PDF that can be opened on the presentation laptop without a
network connection.

## Scope

The release uses the existing serial pipeline: the Yang–Zhang builder,
reference solver, experimental optimized variant, Boolean Z3, Wang Z3,
witness verification, renderer, and dossier generator. Preparation focused
on setup, new inputs, failure handling, and readable demonstration material.

## Demo interface

```sh
make demo-setup
make demo-check
make demo INPUT=path/to/formula.cm13
```

Setup builds the shared library, installs the two locked Python environments,
and checks the compiler, PDF template, Z3, rendering, and fonts. It needs
network access the first time. The suite and demo then run offline.

The demo accepts a formula without an expected result. Both native solvers
and both Z3 checks run once; figures and PDF use the recorded results.
Each invocation saves its input, hash, logs, and outputs in a new directory.
The PDF path is printed only after the complete dossier passes validation.

## What was checked

- **Clean setup:** an isolated Debian clone started with empty home, cache,
  and Python installation directories. The first dossier was then generated
  with networking disabled.
- **New SAT and UNSAT inputs:** two three-variable formulas, checked by
  independent enumeration, produced complete dossiers without an expected
  result supplied to the demo. Input hashes, results, traces, and figures
  were checked, and all 39 PDF pages were reviewed.
- **Malformed input:** the demo and short suite reject inputs outside the
  CM1-in-3 format or constraints.
- **Timeout and Ctrl+C:** cancellation stops the run, preserves diagnostics,
  and allows a later run without overwriting earlier PDFs.
- **Disagreement and incomplete output:** regression checks cover conflicting
  results and incomplete traces. Neither is reported as UNSAT or success.
- **Witness rejection:** the short suite alters a tile and checks that the
  verifier rejects the resulting witness.
- **Offline execution:** the suite and SAT/UNSAT demos ran without networking
  after setup, both in the isolated environment and on the laptop.
- **PDF inspection:** input, results, captions, legends, and routing labels
  were reviewed. After layout fixes, the corrected PDF was inspected on the
  Omarchy presentation laptop at `0215b73` and was readable.
- **Presentation laptop:** setup, all six suite checks, SAT and UNSAT dossiers,
  error handling, timeout, interruption, and restart were exercised on Omarchy.

The renderer suite passed 337 tests, and 87 canonical assets regenerated
identically. Documentation checks covered 41 pages and 929 references, with
browser inspection at desktop and mobile widths.

## Observed runs

These are measurements from preparation runs, not performance guarantees.
Dossier times include figures and PDF generation.

| Environment / run | Time | Output |
| --- | --- | --- |
| Isolated Debian, included SAT case | 36.095 s | 23-page PDF |
| Isolated Debian, new SAT input | 70.316 s | 19-page PDF |
| Isolated Debian, new UNSAT input | 37.702 s | 20-page PDF |
| Isolated environment, short suite (two runs) | 6.274 / 6.275 s | 6/6 checks each |
| Omarchy at `7ea377e`, setup | 28.644 s | Environments ready |
| Omarchy at `7ea377e`, short suite | 12.781 s | 6/6 checks |
| Omarchy at `7ea377e`, SAT dossier | 132.138 s | Complete dossier and PDF |
| Omarchy at `7ea377e`, UNSAT dossier | 69.300 s | Complete dossier and PDF |
| Omarchy at `0215b73`, corrected UNSAT dossier | 66.289 s | PDF inspected on laptop |

## Known limits

- Linux is the supported platform. The core environment needs Python 3.11 or
  newer; the renderer uses Python 3.14.
- Arbitrary instances can take a long time. Wang Z3 dominated the measured
  laptop runs. A timeout never implies UNSAT.
- Trace capacity is finite. A six-variable SAT input exceeded 100,000 events
  per trace during preparation and was rejected before dossier export.
- Wide regions require zoom to inspect individual cells in the PDF.
- UNSAT is supported by agreement between the solvers and checks; the trace
  is not an independent UNSAT certificate.
- This release has no parallel solver.

## Release checkpoint

The preparation runs above identify the tested candidates. Verification of the
published version also requires a fresh clone of `v1.0.0`, setup, and offline
suite and SAT/UNSAT demo runs, followed by inspection of the generated PDFs.
The tag, release commit, environment, and results should be recorded with the
[GitHub Release](https://github.com/xtraid/tiling-foundry/releases/tag/v1.0.0).
This preparation record does not establish completion of that fresh-clone check.

## After v1.0

Further work includes serial cleanup, new baseline measurements, and parallel
execution. New optimizations, larger benchmark campaigns, and Windows/macOS
support are outside this release's scope.

See the [release notes](../../RELEASE_NOTES.md) for installation and compatibility
limits, and the [dossier guide](../run_dossiers.md) for input and output details.
The earlier operational plan remains available in Git history.
