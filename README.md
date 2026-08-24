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

## What is interesting today

The optimized solver still uses the same Wang semantics and independent witness
verification as the reference path. It currently differs in five isolated
mechanisms: a geometrically growing DFS stack, omission of undo entries during
initial propagation before rollback can be requested, transfer of the already
verified SAT domain buffer, and a private byte-wise table for aggregating tile
support during propagation, plus a packed private pending-cell index that
suppresses duplicate optimized-queue entries. The reference path retains its
duplicate-accepting FIFO, baseline tile loop, full initial trail,
fixed-capacity stack, and dense result copy.

For the first three mechanisms, five alternating runs of the versioned
12-variable Yang–Zhang SAT benchmark on a Ryzen 5 3600 measured:

| Metric | Reference | Optimized | Change |
| --- | ---: | ---: | ---: |
| Solver median | 80.033 ms | 73.150 ms | -8.60% |
| Peak resident set | 14,952 KiB | 7,964 KiB | -6,988 KiB |
| Reserved DFS stack | 1,829,928 bytes | 384 bytes | -99.98% |
| Reserved undo trail | 8 MiB | 1 MiB | -87.5% |
| Initial undo writes | 510,665 | 0 | -100% |
| Final SAT result copy | 305,124 bytes | 0 bytes | -100% |

With those mechanisms present in both comparison binaries, seven alternating
runs isolated the byte-wise table at 91.146 ms before and 20.701 ms after on
the same large SAT case (-77.29%). The corresponding support aggregation fell
from 13,058,856 candidate-tile visits to 5,214,770 nonzero-byte lookups. The
no-arc result-copy and root-UNSAT controls stayed within +0.60% and +3.36%.

These are host-specific measurements, not universal performance claims. The
full corpus, commands, environment, raw interpretation rules, counterexamples,
and mechanism-by-mechanism reports are versioned under [`benchmarks/`](benchmarks/)
and [`docs/`](docs/). In particular, the unconstrained deep-search case keeps
its required 2 MiB search trail and showed no material timing change (-0.40%).

Seven alternating runs isolated queue deduplication at 23.463 ms before and
19.659 ms after on large Yang–Zhang SAT (-16.21%), and at 4.857 versus 3.912 ms
on large UNSAT (-19.46%). Processed arcs fell by 35.8--39.2 percent; the packed
index occupied 9,536 bytes on large SAT and was not allocated for root-conflict
or no-arc controls. The unconstrained control remained MRV-bound at +0.09%.

The first seven-sample cross-engine smoke baseline, pinned to one Ryzen 5 3600
logical CPU, measured the complete-file SAT medians at 0.549 ms for C reference,
0.187 ms for C optimized, 6.988 ms for direct Boolean Z3, and 10.787 s for Wang
Z3. In the prepared-Region view the corresponding native medians were 0.504 and
0.142 ms, while Wang Z3 took 10.794 s. These are host-specific smoke results;
Boolean Z3 solves the original formula rather than the Wang region, so its row
is not a speedup claim. The much faster UNSAT rows use deliberately shallow
contradictions, not hard UNSAT search.

The Wang Z3 oracle now models one finite edge-tuple relation per active cell
and shares a single color term across each internal edge. A controlled
single-sample SAT comparison on the same CPU reduced the prepared-Region path
from 10.666 s to 2.605 s and the complete-file path from 10.560 s to 2.620 s,
while peak process RSS decreased slightly. The model, duplicate-tile semantics,
test evidence, command, and measurement limits are recorded in the
[edge-table report](docs/wang_z3_edge_table_2026-08-24.md).

## Goal

The intended end-to-end pipeline is:

```text
Cubic Monotone 1-in-3 SAT formula
        |
        v
Yang–Zhang finite Wang region
        |
        +-------------------+
        |                   |
        v                   v
native C solver       Z3 reference paths
        |                   |
        +---------+---------+
                  |
                  v
       independent verifier
                  |
                  +--> exact witness extension/extraction
                       between Boolean assignments and Wang tilings
                  |
                  v
      square-to-hex translation
                  |
                  v
       hex verifier and renderer
```

The native solver, Z3 models, verifier, and renderer are deliberately separate.
The renderer is downstream from correctness-critical logic and never decides
tileability.

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
- OpenMP is introduced only after the serial path is correct and measurable.
- Project conventions must be distinguished from claims inherited from the
  Yang–Zhang paper.

## Current status

Implemented and tested as of 25 August 2026:

- canonical static definition of the 23 atomic Wang tiles;
- generalized-tile family metadata kept outside solver semantics;
- oriented local edge matching;
- Yang–Zhang signal tokens and deterministic adjacent-swap routing;
- application and validation of adjacent-swap sequences;
- minimal canonical in-memory Cubic Monotone 1-in-3 SAT representation using
  `variable_count` and clauses, with builder-side domain validation;
- strict `p cm13` parser with caller-owned `FILE *` and a path-based external
  loader, precise error locations, transactional output, and explicit formula
  destruction;
- transactional Yang–Zhang formula-to-region construction, including exact
  swap-trace ownership, dimensions, the paper-shaped simply connected active
  mask, and all exposed boundary colors;
- minimal dense row-major `Region` storage, access, and boundary constraints;
- independent verification of complete dense tilings, including region,
  boundary, inactive-cell, tile-ID, and adjacency validation;
- deterministic native serial solver with private compatibility masks,
  bitmask domains, propagation, MRV search, an undo trail, and mandatory
  independent validation of every SAT witness;
- differentially checked optimized entry point sharing the same Wang core,
  with a geometrically growing DFS stack and no undo-trail recording during
  the non-rollbackable initial propagation, ownership transfer of the verified
  SAT domains after every fallible trace operation has completed, and a
  private 12 KiB byte-wise support table derived from the canonical
  compatibility masks, plus a packed private pending-cell bitset that
  suppresses duplicate optimized-queue entries and is omitted when no active
  adjacency can use it;
- optional borrowed dense initial tile domains with identical reference and
  optimized semantics, complete validation before solving, and a strict
  distinction between malformed input (`ERROR`) and a legal contradictory
  restriction (`UNSAT`);
- optional solver metrics, an opt-in renderable best failed leaf for UNSAT,
  and a capped binary failed-leaf trace backed by `mmap`;
- C regression tests, deterministic fuzzing against brute-force and Boolean
  oracles, large-region stress cases, and end-to-end Yang–Zhang SAT/UNSAT
  checks;
- golden coverage of all 23 `(N,E,S,W)` tile tuples and focused solver-level
  tests for forwarder, anchor, atomic crossover, and whole crossover-block
  behavior, including deterministic chain fuzzing and volume stress;
- immutable pure Python formula and dense region data, including canonical
  row-major storage, active masks, color domains, and boundary-placement
  validation;
- an immutable Python copy of all 23 atomic tile edge tuples, checked against
  the native `TILESET` symbol without importing ctypes into models or oracles;
- independent Boolean and Wang witness checkers plus Z3 oracles: the Boolean
  path preserves repeated clause positions, while the Wang path consumes the
  copied `Region`, constrains each active cell to a finite edge-tuple relation,
  shares color terms across active internal edges, enforces boundaries, and
  returns a dense tiling only for SAT;
- a shared `libwang.so` build and tested C-to-Python formula and region
  adapters that copy results into immutable Python storage, report native
  parser status and source locations, and close every native lifetime before
  returning;
- a native reduction coordinator that parses once and branches from the live
  C formula to the Python formula copy and Yang–Zhang region builder;
- a stateless native Yang–Zhang witness bridge that pins only the three
  variable-gadget cells, extends an exact Boolean assignment through either
  generic solver, verifies and decodes dense Wang tilings, and never reads the
  reduction swap trace or evaluates Boolean clauses;
- a scoped Python cross-check coordinator that connects Boolean Z3 to native
  witness extension, extracts assignments from native or Wang-Z3 tilings, and
  retains copied counterexamples across native cleanup;
- exhaustive witness-level evidence over all 1,701 canonical formulas through
  three variables, every one of their `2^n` assignments, and both native solver
  entry points: direct Boolean validity agrees with extension SAT, and every
  SAT tiling independently verifies and extracts the exact requested
  assignment;
- shared SAT/UNSAT `.cm13` fixtures exercised through all implemented
  end-to-end branches: native parser to Yang–Zhang region, serial solver, and
  verifier; native parser to Python formula copy, Boolean Z3, and witness
  checker; and the same copied region through Wang Z3 and its independent
  checker;
- a JSON Lines comparison suite over fixed `.cm13` inputs, with separate
  prepared-Region and file-to-verified-decision scopes for the native
  reference, native optimized, Boolean Z3, and Wang Z3 paths;
- a provenance-pinned PAP Render snapshot under `renderer/`, preserving its
  standalone Python 3.14 project and 144-test suite without coupling its
  graphical dependencies to the native core or Python reference tools;
- C17/OpenMP build scaffold and GitHub Actions CI with strict GCC/Clang,
  ASan, UBSan, GCC static analysis, Memcheck, and Cachegrind paths.

Not implemented yet:

- native OpenMP solver;
- square-to-hex translation and verification;
- JSON export and renderer integration.

## Next milestones

Development proceeds through small, testable modules:

1. continue isolated performance-path changes after the completed dynamic DFS
   storage, initial-trail removal, SAT ownership transfer, and byte-wise
   support table and queue deduplication;
2. evaluate MRV indexing independently for weakly constrained search;
3. evaluate propagation scheduling and OpenMP only after the serial mechanisms
   meet their gates;
4. implement and verify the square-to-hex translation;
5. stabilize JSON and renderer integration last.

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
`make check`. Run its 144 tests independently:

```sh
cd renderer
uv run --locked pytest -q
```

CI mirrors that command in a separate read-only Python 3.14 job. Snapshot
provenance and update instructions are recorded in
[`renderer/UPSTREAM.md`](renderer/UPSTREAM.md).

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
src/parallel/    OpenMP path
src/verify/      independent tiling verification
src/io/          formula parsing and serialization
python/model/    pure Python data contracts
python/native/   C ABI adapters and ownership boundaries
python/crosscheck/ scoped native/Z3 witness orchestration
python/oracles/  independent Z3 oracles and witness checks
python/hex/      square-to-hex translation and verifier
tests/           C, Python, and instance regressions
benchmarks/      fixed reference corpus and profiling runner
docs/            theory and architecture references
legacy/          frozen experimental code
```

The C parser is canonical for native input. Native adapters copy data into
Python-owned models and never expose C pointers. Oracles accept models rather
than paths: the Boolean oracle consumes `Formula`, while the Wang oracle
consumes `Region + TILESET`. Both witness checkers are pure Python and
independent of Z3. The cross-check layer alone coordinates those components
with scoped native lifetimes; Python does not duplicate parsing or the
Yang–Zhang reduction.

## Documentation

The [GitHub Pages documentation](https://xtraid.github.io/tiling-foundry/)
organizes the technical material by reader interest:

- **Architecture and correctness** covers module ownership, the serial solver,
  independent verification, and Boolean–Wang witness correspondence.
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

See the architecture specification for the extended bibliography and future
research directions.

## License

See [`LICENSE`](LICENSE).
