# Tiling Foundry

[![CI](https://github.com/xtraid/tiling-foundry/actions/workflows/ci.yml/badge.svg)](https://github.com/xtraid/tiling-foundry/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Tiling Foundry implements the Yang–Zhang reduction from CM1-in-3 SAT to tiling
with a fixed set of 23 Wang tiles. It builds the region, searches for a tiling,
and checks the result against Z3. Each run can produce a dossier containing
the input, results, witnesses, and figures needed to inspect and reproduce it.

The focus is the Yang–Zhang construction itself: building the region, solving
it, and checking that the different views of the instance agree.

**Read:** [Documentation](https://xtraid.github.io/tiling-foundry/) ·
[Presentazione](https://xtraid.github.io/tiling-foundry/presentazione/) ·
[Pipeline](https://xtraid.github.io/tiling-foundry/pipeline/) ·
[Worked example](https://xtraid.github.io/tiling-foundry/worked-example/) ·
[Reference](https://xtraid.github.io/tiling-foundry/reference/) ·
[Evidence](https://xtraid.github.io/tiling-foundry/evidence/) ·
[Run dossiers](https://xtraid.github.io/tiling-foundry/run-dossiers/)

## Why this repository exists

Yang and Zhang proved in 2024 that tiling finite simply connected regions is
NP-complete even with one fixed set of 23 Wang tiles. The paper gives a compact
reduction. This repository is my attempt to make that construction concrete
enough to run, inspect, break, and check on actual CM1-in-3 instances.

I use the reference solver as the baseline. The experimental optimized version
keeps the same search strategy, with six local optimizations. Boolean Z3 and
Wang Z3 provide two further checks. A run records all four results in the same
dossier, so disagreements are visible immediately.

## Quick start

The project currently targets Linux. The toolchain uses Linux/POSIX facilities
including `mmap`, `/proc`,
Valgrind, and dynamic loading of `libwang.so`; Windows and macOS are not
currently supported.

For the full dossier, install a C17 compiler, `make`, Python 3.11 or newer,
Git, [`uv`](https://docs.astral.sh/uv/getting-started/installation/), and
pdfLaTeX. On Debian 13, the system packages are:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends \
  build-essential python3 git ca-certificates curl texlive-latex-base
```

On Arch Linux / Omarchy, install the equivalent prerequisites:

```sh
sudo pacman -Syu --needed base-devel python git ca-certificates curl texlive-latex
```

Arch's [`texlive-latex`](https://archlinux.org/packages/extra/any/texlive-latex/)
pulls in `texlive-basic` and `texlive-bin` and supplies the LaTeX packages used
by the report. If setup reports `pdflatex is missing`, install this package,
check `pdflatex --version`, then rerun `make demo-setup` while online.

If `uv` is not installed, download and inspect the standalone installer before
running it. The version used for the setup check is 0.12.1:

```sh
curl -LsSf https://astral.sh/uv/0.12.1/install.sh -o /tmp/uv-install.sh
cat /tmp/uv-install.sh
sh /tmp/uv-install.sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

Clone the fixed release and prepare the project:

```sh
git clone --branch v1.0.0 --depth 1 https://github.com/xtraid/tiling-foundry.git
cd tiling-foundry
make demo-setup
```

`demo-setup` checks the compiler and compiles a small PDF with the real report
template before installing dependencies. It then builds `libwang.so` and
checks Z3, image rendering, and fonts. A missing prerequisite stops setup with
an error; the target does not install system packages.

The two Python environments stay separate: `.venv` uses Python 3.11 or newer;
`renderer/.venv` uses Python 3.14, selected by `renderer/.python-version`.
Both are installed with `uv sync --locked`. The first setup needs network
access to download packages and, when absent, the renderer's Python. Keep the
environments and uv-managed interpreter installed for offline use. No global
`pip` installation or GPU is needed.

Generate the first complete dossier from the included SAT case:

```sh
UV_OFFLINE=1 uv run --locked python tools/generate_run_dossier.py \
  examples/run-cases-v2/pipeline-sat.json \
  build/first-dossier --pdf
```

Open `build/first-dossier/report.pdf`. The output directory must be new for each
run. `UV_OFFLINE=1` also reaches the renderer subprocesses. The command runs
the native solvers and Z3 checks before producing the figures and PDF.

Run the short, narrated verification suite after setup:

```sh
make demo-check
```

It checks parsing, known SAT and UNSAT cases, agreement between all four
results, and rejection of an altered witness. It stops at the first failure
and prints the measured duration after success. See the
[suite guide](docs/run_dossiers.md#suite-breve-commentata)
for the six checks, diagnostics, and timeout options.

### Run a new input

After `make demo-setup`, give the demo a CM1-in-3 file without an expected result:

```sh
make demo INPUT='path/to/new formula.cm13' TIMEOUT=300
```

The command copies the input, runs both native solvers and both Z3 checks,
and produces the figures and PDF using the installed environments offline. It prints the PDF path only after the complete dossier succeeds.
Each invocation retains its input, original name/hash and log in a new directory
under `build/demo/`.

The demo runs without a time limit by default (`TIMEOUT=none`). Set `TIMEOUT`
to a positive number of seconds to impose a global limit, including capture,
figures and PDF. Ctrl+C cancels an uncapped run.
If the four results disagree, the run fails instead of guessing which one is
right. UNSAT is never inferred from a timeout. Cancellation, UNKNOWN, and an
incomplete trace also stop the run with diagnostics. Some inputs may take a
long time to solve. The [dossier guide](docs/run_dossiers.md#new-cm1-in-3-input)
describes the input format, output and diagnostic options.

The full workflow was tested on Debian and on the Omarchy laptop used for the
presentation, including offline execution after setup.

## Current status

`v1.0.0` is the version prepared and tested for the project defense.

The v1.0 serial pipeline is complete. It takes a `.cm13` formula through the
reduction, search, and checks to a reproducible dossier. For SAT results,
it verifies the witnesses before rendering square, generalized, or hex views.
Each run keeps the input, solver results, witnesses, traces, and rendered
figures together. A PDF report can be generated from the same data.

| Capability | Status |
| --- | --- |
| Yang--Zhang formula-to-region construction | Implemented and tested |
| Reference serial solver | Implemented and tested |
| Experimental optimized variant | Six local optimizations of the reference search |
| Boolean Z3 / Wang Z3 | Both working and included in dossier runs |
| Witness verification | Runs before a SAT result is published |
| Boolean--Wang witness correspondence | Checked exhaustively on small formulas |
| Solutions and traces | Stored as versioned artifacts with hashes |
| Square, generalized, and checked hex presentations | Rendered from verified witnesses |
| v1 observed-run dossiers | Cover four SAT/UNSAT execution cases |
| v2 dossiers | Record all four results, with shared figures and an optional PDF |
| Native C JSON layer | Not implemented; `src/io/json.c` remains a placeholder |

See the [optimization notes](docs/solver_performance_scope.md) for the
experiments and measurements behind the optimized variant.

## Architecture

Boolean Z3 is the direct sanity check: it sees the original CM1-in-3 formula.
Wang Z3 gets no such shortcut. It only sees the region produced by the
Yang–Zhang builder and the fixed tileset, and solves it without calling the
native solver.

The reference solver and its optimized variant search that same region using
the same strategy. Every returned witness is checked before rendering.

```text
                         +--> Boolean Z3 --> result / assignment check
.cm13 --> parser --> Formula
                         +--> Yang--Zhang --> Region + TILESET
                                                |--> reference solver --+
                                                |--> optimized solver --+--> result / witness checks
                                                +--> Wang Z3 -----------+          |
                                                                                  v
                                                                square --> generalized / hex
```

The [pipeline story](https://xtraid.github.io/tiling-foundry/pipeline/) explains
the data flow and component boundaries. The
[worked example](https://xtraid.github.io/tiling-foundry/worked-example/)
follows a SAT instance from its source formula to the checked tiling.

## Small standalone harness

[`harness_wangz3/`](harness_wangz3/) contains a small reimplementation of the
CM1-in-3 → Yang–Zhang → Wang/Z3 pipeline. I kept it separate from the main
framework so the whole reduction can be followed in one small codebase.
The reduction code is reimplemented here, rather than imported from the main
framework.

It covers parsing, region construction, finding a Boolean witness, and encoding
and solving the Wang instance in Z3. It does not try to match the main
framework's features or performance.

Source, locked dependencies, sample inputs, and recorded SAT/UNSAT outputs are
included. The harness is frozen at the version used for these experiments;
[`FREEZE.json`](harness_wangz3/FREEZE.json) records its provenance and file
checksums.

## Limits and checks

The code lets you run and check the construction on concrete instances. The
NP-completeness proof is due to [Yang and Zhang](#primary-reference).

- The solver uses the 23 atomic Wang tiles with translation only; rotation and
  reflection are not allowed.
- The 14 generalized tiles are construction and presentation metadata, not
  solver primitives.
- Search, witness extraction, and verification remain separate
  implementations.
- Boolean Z3 checks the source formula; Wang Z3 checks the constructed region.
  Neither replaces the native solvers.
- A trace records observed events. It is not a standalone UNSAT certificate.
- The square-to-hex port is a checked one-to-one presentation of an already
  verified square witness, not another solver or solution schema.

## Build, test, and reproduce

Run the core checks from the repository root:

```sh
make clean
make check
```

`make check` builds the serial libraries, runs the C and core Python tests,
builds the OpenMP scaffold, and exercises both serial solver paths. The core
checks require a C17 compiler with OpenMP support, `make`, Python and `uv`;
they do not require LaTeX. The full dossier setup above also prepares the
renderer and PDF tools.

The renderer is an isolated locked Python project and has its own suite:

```sh
cd renderer
uv run --locked pytest -q
cd ..
```

Useful focused targets include `make c-check`, `make python-check`,
`make strict-check`, `make sanitizer-check`, `make analyzer-check`,
`make valgrind-check`, `make cachegrind-check`, `make coverage`,
`make parser-fuzz-smoke`, and `make benchmark-compare-smoke`. Dated evidence
pages record the environment and limits for extended fuzzing, profiling, and
benchmarks.

To render the versioned square witness fixture:

```sh
cd renderer
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-square.png
cd ..
```

Add `--hex` and select another output path for the checked pointy-top hex
presentation.

Generate a full-pipeline v2 capture without a TeX dependency:

```sh
make shared
uv run --frozen python tools/generate_run_dossier.py \
  examples/run-cases-v2/pipeline-sat.json \
  build/run-dossiers/pipeline-sat-v2
```

With pdfLaTeX available, add `--pdf` to generate the report. The
[run dossier guide](https://xtraid.github.io/tiling-foundry/run-dossiers/)
explains the v1 and v2 formats, how outputs are saved, and which checks run
for SAT and UNSAT results.

## Repository layout

```text
include/wang/    public C APIs
src/core/        tiles and region primitives
src/builder/     Yang--Zhang reduction
src/crosscheck/  Boolean/Wang witness bridge
src/solver/      reference and optimized serial search
src/parallel/    OpenMP build scaffold
src/verify/      independent native verification
src/io/          formula parser and native JSON placeholder
python/model/    pure Python data contracts
python/native/   C ABI adapters and ownership boundaries
python/formats/  versioned artifact validation and export
python/oracles/  independent Z3 oracles and witness checks
renderer/        isolated explanatory and square/hex rendering
tests/           C, Python, fixtures, and instance regressions
benchmarks/      fixed corpora and profiling tools
docs/            Pages stories, maintained references, and dated evidence
harness_wangz3/  small standalone CM1-in-3 / Yang–Zhang / Wang-Z3 harness
legacy/          frozen experimental code
```

The native code reads formulas through the C parser. Python adapters copy
data across the ABI without exposing C pointers. The code in `src/crosscheck/`
connects Boolean assignments to Wang tilings.

## Documentation

The longer explanations live on GitHub Pages: the
[pipeline](https://xtraid.github.io/tiling-foundry/pipeline/),
[component stories](https://xtraid.github.io/tiling-foundry/components/tileset/),
[reference documentation](https://xtraid.github.io/tiling-foundry/reference/),
and [dated evidence](https://xtraid.github.io/tiling-foundry/evidence/).
Development plans and the post template remain versioned under `docs/` but are
excluded from the published site.

## Legacy policy

The old Pygame, procedural-generation, solver, notes, proof, and asset material
is frozen under `legacy/`. It may be consulted for ideas but is not a formal
specification, proof artifact, or dependency of the current implementation.

## Primary reference

[Chao Yang and Zhujun Zhang, *NP-completeness of Tiling Finite Simply Connected
Regions with a Fixed Set of Wang Tiles*](https://arxiv.org/abs/2405.01017),
arXiv:2405.01017 (2024).

See the [reference bibliography](docs/references.md) for the full source policy.
The [historical architecture page](docs/historical_architecture.md) explains
the original future-facing design document and its current limitations.

## License

See [`LICENSE`](LICENSE).
