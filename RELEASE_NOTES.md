# v1.0.0 — Exam Ready

This release packages the serial Yang–Zhang pipeline for a reproducible
demonstration: prepare the environments, check known cases, and turn a new
CM1-in-3 input into a verified dossier with figures and a PDF.

## Run the release

Install the Linux system prerequisites in the [README](README.md#quick-start),
including pdfLaTeX. Debian and Arch/Omarchy commands are provided there.
The first setup needs network access; later demo commands use the installed
environments offline.

```sh
git clone --branch v1.0.0 --depth 1 https://github.com/xtraid/tiling-foundry.git
cd tiling-foundry
make demo-setup
make demo-check
make demo INPUT=tests/instances/demo_sat.cm13
make demo INPUT=tests/instances/pipeline_unsat_search.cm13
```

To demonstrate offline operation, disconnect the network after setup and run
the last three commands. Open the PDF path printed after each successful demo.
Keep the installed environments, managed Python interpreter, and generated
materials available for the presentation. Save presentation copies outside
`build/`, which is removed by `make clean`.

For a new input, use `make demo INPUT='path/to/formula.cm13' TIMEOUT=300`.
The header must be `p cm13 n n`, followed by `n` three-literal clauses;
each declared variable occurs exactly three times, including repeated
occurrences within a clause. The [dossier guide](docs/run_dossiers.md)
describes the full format and output.

## What is included

- `make demo-setup` checks C17, the real PDF template, Z3, rendering and fonts,
  and prepares both locked Python environments.
- `make demo-check` narrates six checks covering parsing, SAT/UNSAT, agreement
  between two native solvers and two Z3 checks, and rejection of a corrupted witness.
- `make demo INPUT=...` accepts an input without an expected result. Reference,
  optimized, Boolean Z3 and Wang Z3 each run once; figures and PDF reuse the
  recorded capture. Input bytes, original name/hash and diagnostics survive.
- SAT witnesses are independently checked. UNSAT records agreement between the solvers and checks
  and marks witness-only sections not applicable. Trace is not an independent
  UNSAT certificate.
- Timeout, UNKNOWN, disagreement, incomplete traces and cancellation are
  failures. They never become UNSAT or a completed dossier. Every invocation
  uses a new directory, preserving earlier successful runs.
- The documentation, figures and PDF support the demonstration, including
  compact-region trace legends and routing labels that fit their boxes.

## Rehearsal evidence and limits

The workflow was exercised on Debian and an Omarchy laptop. On Omarchy, the
initial rehearsal at `7ea377e` measured setup at 28.644 s, the six-check suite
at 12.781 s, SAT/PDF at 132.138 s and UNSAT/PDF at 69.300 s. After the layout
correction, UNSAT/PDF at `0215b73` took 66.289 s. The corrected PDF was
inspected on the presentation laptop and all text was readable. These are observations on that laptop, not timing
guarantees or CI performance thresholds. Published-tag acceptance is recorded
with the GitHub Release and its accompanying evidence.

Linux is the supported platform. The core Python environment requires 3.11
or newer; the renderer uses Python 3.14. NumPy, Pillow and Z3 are locked;
the GPU is not required. Arbitrary inputs can exceed the global timeout or
trace capacity, and wide regions can require zoom to inspect individual cells.
Wang Z3 dominated the observed laptop runtime.

Updated v2 readers accept earlier v2 dossiers. A strict older reader may
reject a new-input dossier whose `expected_status` is null; use the readers
shipped with this release. Dossier v1 and the independent solver/checker
boundaries remain supported. No OpenMP solver or new serial optimization is
introduced here; CI restructuring and serial cleanup follow the exam.
