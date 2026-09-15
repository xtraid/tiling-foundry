# Tiling Foundry

[![CI](https://github.com/xtraid/tiling-foundry/actions/workflows/ci.yml/badge.svg)](https://github.com/xtraid/tiling-foundry/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Can a fixed set of just 23 Wang tiles encode an NP-complete problem? Tiling
Foundry turns the Yang--Zhang construction into an inspectable, tested software
pipeline: a formula becomes a finite simply connected region, independent
engines decide it, and separate checkers validate every published SAT witness.

This is a research implementation, not a general-purpose tiling library. Its
main concern is keeping the mathematical reduction, search, verification, and
presentation boundaries visible enough to audit and measure. The previous
experimental codebase remains frozen under `legacy/`.

**Read:** [Documentation](https://xtraid.github.io/tiling-foundry/) ·
[Pipeline](https://xtraid.github.io/tiling-foundry/pipeline/) ·
[Worked example](https://xtraid.github.io/tiling-foundry/worked-example/) ·
[Reference](https://xtraid.github.io/tiling-foundry/reference/) ·
[Evidence](https://xtraid.github.io/tiling-foundry/evidence/) ·
[Run dossiers](https://xtraid.github.io/tiling-foundry/run-dossiers/)

## Why this repository exists

The 2024 Yang--Zhang result proves NP-completeness for tiling finite simply
connected regions with one fixed set of 23 Wang tiles. Turning that compact
proof into software exposes practical questions: which representation owns a
claim, how the reduction is checked apart from search, how independent engines
are compared, and what evidence is needed before parallelism.

Tiling Foundry answers those questions with explicit ownership, an executable
reference solver, differential tests, independent oracles and verifiers, and
reproducible captures.

## Quick start

The supported development and execution platform is Linux on a POSIX
userspace. The toolchain uses Linux/POSIX facilities including `mmap`, `/proc`,
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

If `uv` is not installed, download and inspect the standalone installer before
running it. The version used for the setup check is 0.12.1:

```sh
curl -LsSf https://astral.sh/uv/0.12.1/install.sh -o /tmp/uv-install.sh
cat /tmp/uv-install.sh
sh /tmp/uv-install.sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

Clone and prepare the project:

```sh
git clone https://github.com/xtraid/tiling-foundry.git
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

Open `build/first-dossier/report.pdf`; on a headless machine, copy that file
to your computer. The output directory must be new for each run. `UV_OFFLINE=1`
also reaches the renderer subprocesses, so this command needs no downloads
after setup. It runs the four engines and checks the recorded results before
producing the figures and PDF.

This first run uses a known case with an expected result. Direct input through
`make demo INPUT=...` and the narrated `make demo-check` suite are the next
steps in the [Exam Ready plan](docs/plans/2026-09-15-exam-ready-v1.0.md).

## Current status

The complete serial square pipeline is implemented from `.cm13` input through
four decision paths, independently checked witnesses, versioned solution and
trace artifacts, and square/generalized/hex presentations. Full-pipeline v2
captures and their shared narrative assets are available, with a static PDF as
an explicit opt-in. Parallel solving remains future work.

| Capability | Status |
| --- | --- |
| Yang--Zhang formula-to-region construction | Implemented and tested |
| Reference and optimized serial solvers | Implemented; the optimized path retains six isolated mechanisms |
| Boolean Z3 and Wang Z3 oracles | Implemented with fixed, recorded construction order |
| Independent verification | Required before SAT publication |
| Boolean--Wang witness correspondence | Implemented with exhaustive small-formula evidence |
| Versioned solutions, snapshots, provenance, and traces | Implemented as separate hash-bound contracts |
| Square, generalized, and checked hex presentations | Implemented downstream of verification |
| v1 observed-run dossiers | Implemented for four distinct SAT/UNSAT execution shapes |
| v2 multi-engine capture, shared assets, and static PDF | Implemented; capture is atomic and PDF is opt-in |
| Native C JSON layer | Not implemented; `src/io/json.c` remains a placeholder |
| `TaskPlan` and native OpenMP solver | Not implemented; only the build scaffold exists |

Optimization claims remain tied to isolated mechanisms and dated evidence; no
host-specific timing threshold is a general correctness claim. The
[optimization methodology](docs/solver_performance_scope.md) defines that
boundary.

## Architecture

The source formula follows two independent routes. Boolean Z3 decides the
formula directly. The native Yang--Zhang builder constructs one region and
fixed tileset shared by the reference solver, optimized solver, and Wang Z3.
Applicable returned witnesses then pass through independent checks before any
presentation is published.

```text
                         +--> Boolean Z3 --> assignment check
.cm13 --> parser --> Formula
                         +--> Yang--Zhang --> Region + TILESET
                                                |--> reference solver --+
                                                |--> optimized solver --+--> witness checks
                                                +--> Wang Z3 -----------+          |
                                                                                  v
                                                                square --> generalized / hex
```

The [pipeline story](https://xtraid.github.io/tiling-foundry/pipeline/) explains
the data flow and component boundaries. The
[worked example](https://xtraid.github.io/tiling-foundry/worked-example/)
follows one named SAT source through the same contracts and checks.

## Correctness boundaries and limitations

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
- Project conventions are distinguished from claims inherited from the
  Yang--Zhang paper.
- Parallel search is deferred until the cleaned serial baseline has new
  evidence and explicit ownership tests.

## Next milestones

The visual documentation and Presentazione tour are integrated. The next
milestone is **v1.0.0 Exam Ready**: a clean-clone setup, a simple command that
turns a new supported formula into a verified dossier and PDF, a short narrated
test suite, and clearer documentation. `make demo-setup` prepares the full
environment; the direct-input command and narrated suite are planned work.

**Release checkpoint:** publish the tag and GitHub Release, then verify the
documented commands from a fresh clone of that tag and open the resulting
dossier on the presentation computer. A local freeze or merged PR alone does
not complete this milestone.

The [Exam Ready plan](docs/plans/2026-09-15-exam-ready-v1.0.md) records the six
sessions and acceptance criteria. After the release and project defense, work
resumes in this order:

1. T99: split fast, integration, and evidence verification into reusable CI
   levels;
2. T100: perform a behavior-preserving structural cleanup of the serial
   solver;
3. collect a new serial baseline, hard-UNSAT evidence, and the public option
   matrix;
4. introduce a minimal `TaskPlan` with an equivalent serial executor;
5. add and measure real OpenMP execution only after those gates pass.

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

With pdfLaTeX available, add `--pdf` to request the additive static v2 report. The
[run dossier guide](https://xtraid.github.io/tiling-foundry/run-dossiers/)
documents v1 and v2 case semantics, atomic output, static input reuse, and the
SAT/UNSAT evidence boundary.

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
legacy/          frozen experimental code
```

The C parser is canonical for native input. Python adapters copy data across
the ABI and do not expose C pointers. The cross-check layer coordinates
Boolean/Wang witness relations without moving oracle concepts into the core.

## Documentation

GitHub Pages is the canonical long-form narrative. It separates the
[pipeline](https://xtraid.github.io/tiling-foundry/pipeline/),
[component stories](https://xtraid.github.io/tiling-foundry/components/tileset/),
[maintained reference](https://xtraid.github.io/tiling-foundry/reference/),
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
