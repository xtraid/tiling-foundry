---
layout: page
title: C and Python coverage baseline
permalink: /coverage_baseline_2026-08-22/
page_class: evidence
description: Informational line, function, and branch coverage from the complete local test suites.
section: Architecture and correctness
document_kind: Coverage report
status: Informational baseline
updated: 2026-08-22
nav_order: 40
---

# C and Python coverage baseline — 22 August 2026

This is the first measured coverage baseline for the current native and Python
cores. It records evidence, not a quality score: no percentage is a required
gate, and the build contains no `fail-under` option. A future ratchet should be
considered only after the uncovered paths have been classified and exercised
where a representative test is possible.

## Reproduction

The measurement started from commit `dd3a65a` and includes the coverage targets
introduced with this report. Run it from the repository root on the supported
Linux/POSIX environment:

```sh
uv sync --frozen
make coverage
```

The target runs every C test with GCC `-O0 -g --coverage`, then runs all Python
tests through `coverage.py` with branch measurement enabled. Generated data is
disposable and remains below `build/coverage/`:

```text
build/coverage/c/coverage.txt
build/coverage/c/coverage.xml
build/coverage/c/index.html
build/coverage/python/coverage.json
build/coverage/python/html/index.html
```

The C object tree is isolated at `build/coverage/c-build`. The parser path test
still writes its temporary input below its established fixed
`build/tests/c` location, so the target creates that directory before running
the isolated binaries.

Measured environment:

```text
Debian GNU/Linux 13
Linux 6.12.101+deb13-amd64 x86_64
GCC and gcov 14.2.0
Python 3.13.5
coverage.py 7.15.4 with C extension
gcovr 8.6
```

The exhaustive native witness test produces legitimately large execution
counters. Therefore the target disables gcovr's suspicious-hit magnitude
heuristic with `--gcov-suspicious-hits-threshold 0`; it does not discard parse
errors or negative counters.

## Baseline results

The complete C suite passed. Coverage over executable statements in `src/`
was:

| Measure | Covered | Total | Coverage |
| --- | ---: | ---: | ---: |
| Lines | 1,533 | 1,691 | 90.7% |
| Functions | 107 | 107 | 100.0% |
| Branches | 1,090 | 1,328 | 82.1% |

The lowest line percentages among measured native modules were 88% in
`src/solver/solver_serial.c` and `src/builder/yang_zhang.c`, 90% in the
failed-leaf trace writer, and 92% in the formula parser. All measured native
functions were entered at least once.

All 64 Python tests passed in 51.6 seconds. Coverage over `python/` was:

| Measure | Covered | Total | Coverage |
| --- | ---: | ---: | ---: |
| Statements | 565 | 599 | 94.3% |
| Branches | 176 | 198 | 88.9% |
| Combined line and branch opportunities | 741 | 797 | 93.0% |

The immutable region model, tileset, native library loader, reduction and
region adapters, tiling checker, and witness checker reached 100% of their
measured opportunities. This does not establish correctness by itself; their
independent semantic and differential tests remain the relevant evidence.

## Significant uncovered paths

The baseline exposes several useful groups rather than one undifferentiated
percentage:

- Native builder, parser, trace, and solver misses are concentrated in integer
  overflow guards, allocation failures, short reads or writes, `mmap` and
  finalization failures, and cleanup after partially initialized state. These
  need controlled fault injection rather than oversized ordinary fixtures.
- Formula parser misses include out-of-memory, stream I/O, and failed-close
  paths. Its normal syntax and domain rejection cases are already broadly
  exercised; parser fuzzing is a separate kind of evidence and is not claimed
  by this baseline.
- Solver misses include defensive failures while allocating arrays, metrics,
  the byte-support table, deduplication storage, snapshots, and result copies,
  plus verifier and trace-finalization rejection. They align with the need for
  focused ownership and cleanup tests before concurrent execution is added.
- Python misses are concentrated in cross-check assertions for internally
  inconsistent solver/oracle results and in adapter rejection of malformed
  native ABI output or non-sequence inputs. The main immutable models and
  independent tiling validation paths are substantially better covered.

The native percentage includes the serial sources linked into `libwang.a`.
The empty JSON placeholder and the placeholder OpenMP implementation have no
meaningful behavior to measure here. Python source discovery similarly omits
empty square-to-hex placeholders. The baseline must be regenerated when those
modules acquire executable behavior.

Coverage instrumentation changes optimization and runtime behavior, so these
figures are not performance measurements. HTML, XML, JSON, `.gcda`, `.gcno`,
and `.coverage` files are build artifacts and are intentionally not versioned.
