# Tiling Foundry

[![CI](https://github.com/xtraid/tiling-foundry/actions/workflows/ci.yml/badge.svg)](https://github.com/xtraid/tiling-foundry/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Can a fixed set of just 23 Wang tiles encode an NP-complete problem? Tiling
Foundry turns the Yang–Zhang construction into an inspectable, tested software
pipeline: a formula becomes a finite simply connected region, a native C solver
tiles it, and an independent verifier checks the witness.

This is a research implementation, not a general-purpose tiling library. Its
main concern is keeping the mathematical reduction, the search procedure, and
the correctness checks separate enough to audit and measure.

The project is being rebuilt from the theory outward. The previous experimental
codebase remains under `legacy/`, but it is not the implementation base of the
new core.

## Why this repository exists

The 2024 Yang–Zhang result proves NP-completeness for tiling finite simply
connected regions using one fixed set of 23 Wang tiles. The proof is compact;
turning it into software exposes engineering questions that are easy to hide in
an all-in-one prototype:

- Which representation is authoritative at each stage?
- How do we test the reduction independently from the solver?
- Can solver optimizations be isolated and measured without changing semantics?
- What evidence is enough before adding parallelism?

Tiling Foundry answers those questions with small ownership boundaries,
differential tests, reproducible benchmark cases, and a deliberately retained
reference solver path.

## Quick start

The supported development and execution platform is Linux on a POSIX userspace.
The current toolchain relies on Linux/POSIX facilities including `mmap`,
`/proc`, Valgrind, and dynamic loading of `libwang.so`. Windows and macOS are
not currently supported; no compatibility backend is implied or planned
without a concrete requirement.

Requirements are a C17 compiler, `make`, OpenMP support, and
[`uv`](https://docs.astral.sh/uv/). Then:

```sh
git clone https://github.com/xtraid/tiling-foundry.git
cd tiling-foundry
make check
```

`make check` builds the serial and shared libraries, runs the C and Python test
suites, builds the OpenMP scaffold, and exercises both solver paths on a small
benchmark case. It does not require a GPU.

## Current status

The implemented components cover the square pipeline from `.cm13` input
through a verified solution document, the default square diagnostic PNG, and
the checked presentation-only square-to-hex view selected by `--hex`. Parallel
solving remains future work.

| Capability | Status |
| --- | --- |
| Yang–Zhang formula-to-region construction | Implemented and tested |
| Reference serial solver | Implemented |
| Optimized serial path | Implemented with five isolated, measured mechanisms |
| Independent native verifier | Implemented and required before SAT publication |
| Boolean Z3 oracle | Implemented over the copied immutable `Formula` |
| Wang Z3 oracle | Implemented over copied `Region + TILESET` |
| Boolean–Wang witness correspondence | Implemented; exhaustive evidence covers all 1,701 canonical formulas through three variables and 27,044 constrained native solves |
| Verified square solution export | Implemented as the closed `wang-solution-v1` contract and deterministic exporter |
| Wang diagnostic renderer | Implemented as one presentation-only CLI with byte-stable square default and explicit `--hex` mode in the isolated `renderer/` project |
| Square-to-hex presentation port | Implemented as a pure in-memory Basire/Culik mapping with a raster-independent checker; no hex solver, schema, or core model |
| Static explainability snapshots | Implemented for parsed formula, canonical tile sheet, and unassigned region, with hash-bound JSON contracts and square/hex diagnostic views |
| Reduction construction provenance | Implemented as a separate opt-in native-owned result with exact signal orders, swap-bound gadget spans, manifest v2, and a square overlay view; the compact standard ABI does not allocate it |
| Native C JSON layer | Not implemented; `src/io/json.c` is a placeholder |
| `TaskPlan` and native OpenMP solver | Not implemented; only the build scaffold exists |

The optimized path preserves the reference path's Wang semantics and public
contract. Its five retained mechanisms are dynamic DFS storage, omission of
non-consumable initial-propagation trail entries, SAT-domain ownership
transfer, byte-wise support aggregation, and queue deduplication. The
[optimization methodology](docs/solver_performance_scope.md) defines their
acceptance boundary. Dated reports preserve the measurements and their
host-specific limitations.

## Implemented pipeline

The implemented paths are:

```text
.cm13 --> C parser --> native Formula
                          |        |\
                          |        | +--> formula snapshot --> formula view
                          |        +----> copied Formula ----> Boolean Z3
                          |                                      |
                          |                                      v
                          |                             Boolean witness checker
                          v
                  Yang–Zhang builder --> Region + ReductionExplanation
                                          |  |  |\
                                          |  |  | +--> v2 manifest --> reduction view
                                          |  |  +----> v1 manifest --> region view
                                          |  |                           + tile sheet
                                          |  +-------> copied Region + TILESET
                                          |                  |
                                          |                  v
                                native reference/       Wang Z3
                                optimized solver           |
                                       |                   v
                                       v             Python tiling checker
                                native verifier
                                       |
                            copied tiling + Python checker
                                       |
                                       v
                            wang-solution-v1 --> square PNG (default/explain)
                                       \
                                        +--> pure hex port/check --> hex PNG (--hex)
```

The witness bridge relates exact Boolean assignments to the variable cells of
the same live Yang–Zhang reduction. Its precise scope and evidence are recorded
in the [witness correspondence design](docs/designs/2026-08-21-witness-extension-design.md).
The square-to-hex branch changes presentation only; it consumes the same
square witness after verification. OpenMP is not part of the implemented
diagram.

## Correctness boundaries

- The solver uses the 23 atomic Wang tiles, with translation only: no rotation
  or reflection.
- The 14 generalized tiles are builder and diagnostic metadata, not solver
  primitives.
- The region depends on the input formula and is built at runtime.
- Search and verification remain independent implementations.
- Z3 is an oracle and cross-check, not a replacement for the native C solver.
- Witness extension pins only the variable-gadget cells; extraction first
  verifies the whole Wang tiling and leaves Boolean clause checking to the
  independent formula checker.
- Witness correspondence does not claim a unique tiling for each assignment or
  that extending an extracted assignment reproduces the original tiling.
- The hex port is a bijection over the image tile table, not a second solver or
  correctness oracle. Its pure checker proves translation equivalence while
  leaving source solution validation upstream.
- OpenMP is introduced only after the serial path is correct and measurable.
- Project conventions must be distinguished from claims inherited from the
  Yang–Zhang paper.

## Next milestones

Planned work remains separated into independently reviewed changes. The new
priority is explainability across the deterministic pipeline:

1. define bounded, deterministic event traces for native DFS and explicit
   encoding summaries for Z3, then render partial states by replay;
2. publish a compact formula-to-final-image gallery and optional technical
   report from versioned examples;
3. resume serial MRV and hard-UNSAT evidence before `TaskPlan` and OpenMP work.

The implementation follows a deliberately small design rule: each datum has one
owner, derived state is computed when needed, and future metadata is not added to
core structures before it has a concrete consumer.

## Build and test

Requirements:

- a C17 compiler;
- OpenMP support for the parallel build target;
- [`uv`](https://docs.astral.sh/uv/) for Python reference-tool tests.

Run the complete current check:

```sh
make clean
make check
```

The imported renderer remains a separate locked Python project. Its Pillow and
NumPy dependencies are not installed by the root project or exercised by
`make check`. Run its 238-test combined suite independently:

```sh
cd renderer
uv run --locked pytest -q
```

CI mirrors that command in a separate read-only Python 3.14 job. Snapshot
provenance and update instructions are recorded in
[`renderer/UPSTREAM.md`](renderer/UPSTREAM.md).

To exercise the Wang renderer on the versioned square solution fixture:

```sh
cd renderer
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-square.png
```

The same command produces the checked pointy-top axial presentation only when
the explicit flag is present:

```sh
uv run --locked python wang_square.py \
  ../tests/fixtures/wang_solution_v1_square_sat.json \
  output/wang-hex.png \
  --hex
```

The [square solution contract](docs/wang_solution_v1.md) includes the producer
API for exporting a verified native result before rendering it. The
[square-to-hex reference](docs/wang_square_to_hex.md) defines the mapping,
inverse proof, checker boundary, and integer axial raster convention.
The [static snapshot contract](docs/wang_explainability_snapshots.md) documents
the real formula-to-region export and the formula, tile-sheet, region, and
opt-in final explainability views.
The [reduction explanation contract](docs/wang_reduction_explanation.md)
defines native signal/gadget provenance, manifest v2, ownership, replay
invariants, and the square-only construction overlay.

Useful individual targets:

```sh
make serial
make shared
make openmp
make c-check
make python-check
make coverage
make parser-fuzz-smoke
make strict-check
make sanitizer-check
make analyzer-check
make valgrind-check
make cachegrind-check
make benchmark
make benchmark-compare-smoke
make benchmark-compare
```

`make coverage` runs the complete C and Python test suites with branch
instrumentation and writes disposable text, XML/JSON, and HTML output below
`build/coverage/`. The baseline is informational: these targets deliberately
set no pass/fail percentage threshold. The dated interpretation is published
in the [coverage baseline](docs/coverage_baseline_2026-08-22.md).

`make parser-fuzz-smoke` builds a Clang libFuzzer harness for the canonical
`.cm13` parser with AddressSanitizer and UndefinedBehaviorSanitizer, copies the
versioned valid and malformed seeds into disposable storage below `build/`, and
runs a deterministic short campaign. The committed corpus is therefore never
modified by fuzzing. For a longer local campaign, use `make parser-fuzz`; its
defaults can be overridden explicitly, for example:

```sh
make parser-fuzz FUZZ_RUNS=1000000 FUZZ_MAX_LEN=16384 FUZZ_TIMEOUT=5
```

Both targets set `allocator_may_return_null=1` only for the fuzz process. This
lets intentionally enormous headers exercise the parser's out-of-memory return
instead of being reported as an AddressSanitizer allocation abort; all other
ASan and UBSan findings remain fatal. LibFuzzer's combined allocation/RSS guard
is disabled so it does not pre-empt that return path; AddressSanitizer instead
enforces a finite 256 MiB hard RSS limit. Maximum input length and per-input
timeout are also bounded, and the artifact directory is recreated for every
campaign below `build/`. The smoke uses fixed seed and run count and runs as a
separate read-only CI job. Its measured result is recorded in the
[parser fuzz smoke report](docs/parser_fuzz_smoke_2026-08-22.md).

Dependabot checks GitHub Actions and the uv lockfile weekly. Every CI action is
pinned to a reviewed full commit SHA with its release version retained in a
comment, and repository checkout does not persist credentials.

`make benchmark` builds the portable `-O2` harness and runs the reference path
over the versioned generic and Yang–Zhang corpus in separate timing,
single-solve RSS, and metrics passes. Individual cases accept
`--solver reference|optimized`; reference is the default. Results are
host-specific evidence, not CI pass/fail thresholds.

`make benchmark-compare` runs seven fresh-process samples over the smallest
shared SAT/UNSAT `.cm13` corpus. It separates the direct Wang-region comparison
from the file-to-verified-decision view so the direct Boolean oracle is not
presented as if it solved a `Region`. The smoke target runs the smallest UNSAT
case once; the extended presets and JSON Lines capture command are documented in
[`docs/solver_comparison_benchmark.md`](docs/solver_comparison_benchmark.md).

## Repository layout

```text
include/wang/    public C APIs
src/core/        tiles and region primitives
src/builder/     Yang–Zhang reduction components
src/crosscheck/  Boolean/Wang witness bridge above solver and verifier
src/solver/      serial solver
src/parallel/    OpenMP build scaffold (solver not implemented)
src/verify/      independent tiling verification
src/io/          formula parsing and native JSON placeholder
python/model/    pure Python data contracts
python/native/   C ABI adapters and ownership boundaries
python/formats/  versioned solution and static-snapshot validation/export
python/crosscheck/ scoped native/Z3 witness orchestration
python/oracles/  independent Z3 oracles and witness checks
python/hex/      deliberately unused empty hex-core placeholders
renderer/        isolated legacy and explainable square/hex Wang rendering
tests/           C, Python, and instance regressions
benchmarks/      fixed reference corpus and profiling runner
docs/            theory and architecture references
legacy/          frozen experimental code
```

The C parser is canonical for native input. Native adapters copy data into
Python-owned models and never expose C pointers. Oracles accept models rather
than paths: the Boolean oracle consumes `Formula`, while the Wang oracle
consumes `Region + TILESET`. Both witness checkers are pure Python and
independent of Z3. The cross-check layer coordinates Boolean/Wang witness
relations, while the smaller native-only solve coordinator supplies verified
tilings to producers without importing either Z3 oracle. Both paths keep
native lifetimes scoped; Python does not duplicate parsing or the Yang–Zhang
reduction.

## Documentation

The [GitHub Pages documentation](https://xtraid.github.io/tiling-foundry/)
organizes the technical material by reader interest:

- **Architecture and correctness** covers module ownership, the serial solver,
  independent verification, Boolean–Wang witness correspondence, the square
  solution data contract, and the presentation-only square-to-hex proof.
- **Yang–Zhang reduction** covers geometry, formula-to-region construction,
  proof obligations, and primary references.
- **Solver optimization** separates the current methodology from dated,
  reproducible mechanism reports.
- **Cross-engine benchmarks** documents the native/Z3 protocol and its recorded
  smoke baseline without treating unlike solver problems as equivalent.
- **Historical material** preserves the initial architecture specification as
  superseded context; current headers, tests, and public pages are authoritative.

Development plans and the post template remain versioned under `docs/` but are
excluded from the published site.

## Legacy policy

The old Pygame, procedural-generation, solver, notes, proof, and asset material
is frozen under `legacy/`. It may be consulted for ideas but is not a formal
specification, proof artifact, or dependency of the new implementation.

## Primary reference

[Chao Yang and Zhujun Zhang, *NP-completeness of Tiling Finite Simply Connected
Regions with a Fixed Set of Wang Tiles*](https://arxiv.org/abs/2405.01017),
arXiv:2405.01017 (2024).

See the [reference bibliography](docs/references.md) for the full source policy.
The [historical architecture page](docs/historical_architecture.md) explains
the original future-facing design document and its current limitations.

## License

See [`LICENSE`](LICENSE).
