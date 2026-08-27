---
layout: page
title: Optimized solver queue deduplication
permalink: /solver_queue_dedup_2026-08-20/
description: Evidence for the optimized solver's packed pending-cell index.
section: Solver optimization
document_kind: Benchmark report
status: Accepted mechanism
updated: 2026-08-27
nav_order: 80
---

# Optimized solver queue deduplication — 20 August 2026

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/optimized-mechanisms/frame-05.png' | relative_url }}">
    <img src="{{ '/assets/images/optimized-mechanisms/trace.gif' | relative_url }}" alt="Didactic comparison of the reference solver baseline and the five retained optimized serial mechanisms.">
  </picture>
  <figcaption><strong>Didactic replay.</strong> This shared animation locates queue deduplication among the five isolated mechanisms; the measurements below, not the animation, establish its effect. The <a href="{{ '/assets/images/optimized-mechanisms/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all stages.</figcaption>
</figure>

This accepted mechanism changes only the optimized propagation queue. An
enqueue request for a cell that already has an unconsumed FIFO occurrence is
counted but no longer appended. The reference path retains the original duplicate-accepting
FIFO. Domain meaning, support union, trail and rollback, row-major MRV, DFS
order, diagnostics, SAT ownership, `TaskPlan`, and OpenMP are otherwise
unchanged.

## Reproduction identity

The immutable starting point is Git commit:

```text
308e34a1e67c2e9a298b083724ad80d8bd83685e
Measure optimized solver queue and trail pressure
```

A detached worktree at that commit reproduced benchmark schema v6. Its
portable `-O2` benchmark identity was:

```text
79e39d13cacc46cabb339b603ed8e0e157bdab4d78177d0a1696c99b665a2390
```

The retained comparison uses schema v7 for both binaries. They have the same
sources, compiler flags, link order, public metrics layout, and benchmark
harness, and differ only in the private compile-time mechanism switch
`WANG_OPTIMIZED_QUEUE_DEDUP`:

```text
10f531223e8a70dad164f345618afdea2b883158c59bd9a7d7cd1f1ed700627b  switch=0
3274e7ee7bbf89c8cbfae46fddac44a34afb5ac5e42ce1125e67e534b41a3227  switch=1
```

Final implementation source identities:

```text
8fb48c57139e8374f1415c622f457828d6aa6fc835a2a93440876b17841bac3f  include/wang/solver.h
4d2ae2673c3770e6dbf7d5400e920f65597ab3a1ee0e462cd6b98112f322b161  src/solver/solver_serial.c
bc1b28dd441a4213516730e845856c4f16bde2f1e0ea0f2fca0f1bf09131bc34  benchmarks/c/bench_solver.c
16ade5c35372d4a30848997ec26819a8ce2b432e238b439d99e7da3ef89d5188  tests/c/test_solver.c
1c63c30c48ea0d906e5153e65fda7d3083bdb0b4c87015ebe98278918b3771c0  tests/c/test_solver_differential.c
```

Environment:

```text
Debian GNU/Linux 13
Linux 6.12.101+deb13-amd64 x86_64
AMD Ryzen 5 3600, 6 cores / 12 threads, boost enabled
GCC 14.2.0
Clang 19.1.7
C17, portable -O2; no -march=native or LTO
Valgrind/Callgrind/Cachegrind 3.24.0
```

## Preventive red test

The differential test was changed first to require a nonzero optimized index,
a smaller effective queue peak, and continued re-enqueue after a pop. The
preventive command was:

```sh
make build/tests/c/test_solver_differential
```

It failed with exit status 2 because `WangSolverMetrics` did not contain
`queue_dedup_index_bytes`. The completed test fixes the 4-by-4 backtracking
case at 138 enqueue requests, 31 requests already pending, 323 processed arcs,
a 16-entry effective peak, and an 8-byte index. The 107 accepted appends exceed
the 16 active cells, proving that popped cells become enqueue-able again. The
same fixture has two failed leaves, so it also exercises pending-state cleanup
across conflicts. A metrics-disabled differential run covers the same path and
requires every public metric to remain zero.

Separate exact controls require zero index bytes for both an initial root
conflict and a one-active-cell region with no active adjacency.

## Representation and lifecycle

The optimized state owns one packed `uint64_t` bitset indexed by dense region
cell index. Bit `i` means that cell `i` has one unconsumed queue occurrence.
The storage is:

```text
ceil(cell_count / 64) * 8 bytes
```

A byte-per-cell array would simplify bit access but use eight times as much
memory. The packed representation kept native controls inside the timing gate
and reduced modeled propagation work, so the byte array was not retained.

The index is allocated only after region validation and domain initialization,
and only when the optimized mechanism is enabled, no root conflict already
exists, and the active graph contains an arc. Reference solves, root conflicts,
and no-arc regions allocate no index. Allocation failure destroys all private
state and returns `ERROR` without publishing a partial result.

An accepted push sets the bit. A pop clears it before propagation, allowing a
later domain change to enqueue the cell again. Conflict and error exits drain
all unconsumed entries and clear their bits even when metrics are disabled.
The bitset is derived scheduling state: domains remain the only semantic source
of truth, and the state destructor owns the final free.

Schema v7 adds `queue_dedup_index_bytes`. As before, metrics are populated only
with `WANG_SOLVE_COLLECT_METRICS`; otherwise the entire public metrics object is
zero.

## Direct mechanism evidence

`enqueue_attempts` still counts requests, including suppressed requests.
`duplicate_enqueue_attempts` still counts a request made while the same cell is
currently pending. In the optimized candidate, actual appends are therefore
`attempts - duplicates`. Baseline actual appends equal all attempts because its
duplicates are retained. Scheduling changes can alter later requests, so
before and after attempt counts need not be equal.

One metrics-enabled optimized solve per case produced:

| Case | Requests before | Requests after | Pending before | Pending after | Candidate appends | Peak before | Peak after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| generic forced thin SAT | 98,301 | 98,301 | 65,532 | 32,766 | 65,535 | 65,533 | 32,768 |
| generic result-copy SAT | 1 | 1 | 0 | 0 | 1 | 1 | 1 |
| generic unconstrained SAT | 126,314 | 126,314 | 36,289 | 27,265 | 99,049 | 27,265 | 9,216 |
| generic backtracking SAT | 138 | 138 | 43 | 31 | 107 | 34 | 16 |
| generic root UNSAT | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Yang–Zhang SAT, 6 variables | 77,013 | 79,145 | 52,905 | 30,846 | 48,299 | 27,791 | 9,345 |
| Yang–Zhang UNSAT, 6 variables | 19,832 | 20,449 | 14,394 | 8,377 | 12,072 | 7,561 | 2,560 |
| Yang–Zhang SAT, 12 variables | 645,444 | 667,708 | 445,545 | 253,502 | 414,206 | 228,255 | 76,247 |
| Yang–Zhang UNSAT, 12 variables | 159,813 | 165,880 | 118,571 | 67,406 | 98,474 | 60,715 | 20,317 |

The corresponding propagation and storage changes were:

| Case | Arcs before | Arcs after | Byte lookups before | Byte lookups after | Index bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| generic forced thin SAT | 196,599 | 131,067 | 196,599 | 131,067 | 4,096 |
| generic result-copy SAT | 0 | 0 | 0 | 0 | 0 |
| generic unconstrained SAT | 501,298 | 393,000 | 1,358,602 | 1,033,984 | 1,152 |
| generic backtracking SAT | 424 | 323 | 961 | 696 | 8 |
| generic root UNSAT | 0 | 0 | 0 | 0 | 0 |
| Yang–Zhang SAT, 6 variables | 303,875 | 190,569 | 624,206 | 422,017 | 1,176 |
| Yang–Zhang UNSAT, 6 variables | 78,048 | 47,478 | 163,173 | 109,984 | 328 |
| Yang–Zhang SAT, 12 variables | 2,565,295 | 1,646,693 | 5,214,770 | 3,701,701 | 9,536 |
| Yang–Zhang UNSAT, 12 variables | 634,603 | 391,037 | 1,333,794 | 937,209 | 2,544 |

Every optimized effective peak equals `queue_unique_peak`, while reference
metrics reproduce the preceding queue-profile values exactly. DFS decisions,
backtracks, failed leaves, MRV scans, search-trail writes and rewrites, result
status, and witness
or diagnostic contracts remain stable. Some domain-reduction and request
counts change because coalescing pending work changes when the latest domain is
observed; they are work counters, not semantic invariants.

## Acceptance gates and alternating timings

The mechanism was retained only because queue work and propagation-heavy time
improved, reference/optimized semantics remained equivalent, no-arc controls
stayed within approximately 3--5 percent, and the packed index introduced no
unjustified memory regression.

Seven passes alternated the switch-off/switch-on order. Each fresh benchmark
process used the standard per-case iteration count, disabled metrics, and was
pinned to CPU 2. Medians are per solve; ranges show the seven process results.

| Case | Before ms (range) | After ms (range) | Delta |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 3.530236 (3.446866--3.640588) | 3.347574 (3.238446--3.486592) | -5.17% |
| generic result-copy SAT | 29.812347 (29.085126--29.980998) | 29.686457 (28.591326--29.844734) | -0.42% |
| generic unconstrained SAT | 147.879175 (145.276961--148.890121) | 148.016671 (146.063264--148.623800) | +0.09% |
| generic backtracking SAT | 0.015286 (0.015185--0.015825) | 0.014118 (0.014068--0.014768) | -7.64% |
| generic root UNSAT | 18.354972 (17.465451--18.508779) | 18.305773 (16.594280--18.368342) | -0.27% |
| generic root UNSAT, snapshot | 21.784472 (20.849929--22.130852) | 21.505568 (20.381445--22.055361) | -1.28% |
| Yang–Zhang SAT, 6 variables | 2.781600 (2.768318--2.854487) | 2.338926 (2.327775--2.350329) | -15.91% |
| Yang–Zhang UNSAT, 6 variables | 0.625027 (0.620847--0.644530) | 0.504804 (0.501658--0.513317) | -19.23% |
| Yang–Zhang SAT, 12 variables | 23.463269 (23.247084--23.925535) | 19.659130 (19.493488--19.884554) | -16.21% |
| Yang–Zhang UNSAT, 12 variables | 4.856964 (4.839075--4.987223) | 3.912014 (3.894510--3.947926) | -19.46% |

The propagation-heavy cases improve repeatably. Both no-arc modes and the MRV
control remain well inside the guardrail.

Seven separate alternating single-solve RSS processes showed no material
memory regression. Median KiB before/after were 23,864/23,912 for result-copy,
21,840/21,848 for root UNSAT, and 30,032/30,064 for its snapshot mode. The
packed index is smaller than allocator/RSS resolution on those controls and is
not allocated there. Large SAT fell from 7,684 to 5,896 KiB and large UNSAT
from 2,824 to 2,372 KiB as the effective queue shrank.

## Callgrind

One metrics-disabled optimized process per row, with whole-process
denominators:

| Case | Instructions before | Instructions after | Delta | Dominant self before | Dominant self after |
| --- | ---: | ---: | ---: | --- | --- |
| generic forced thin SAT | 63,345,131 | 59,614,922 | -5.89% | `propagate_queue`, 25.92% | fixture `region_cell`, 20.12%; `propagate_queue`, 19.84% |
| generic unconstrained SAT | 1,967,798,805 | 1,961,449,396 | -0.32% | `select_mrv_cell`, 96.81% | `select_mrv_cell`, 97.12% |
| Yang–Zhang SAT, 6 variables | 41,560,725 | 34,898,379 | -16.03% | `propagate_queue`, 55.04% | `propagate_queue`, 44.33% |
| Yang–Zhang SAT, 12 variables | 345,792,100 | 293,859,879 | -15.02% | `propagate_queue`, 55.62% | `propagate_queue`, 45.49% |

As an architecture-inclusive sanity check, the retained totals are also below
the preceding instrumented profile by 3.50 percent on forced propagation, 0.23
percent on unconstrained search, 13.60 percent on medium SAT, and 12.55 percent on
large SAT. Those cross-report values are not a paired same-schema timing gate;
they confirm that common v7 mechanism plumbing does not erase the instruction
reduction measured by the controlled switch comparison.

On large SAT, `queue_push()` rises from 5.97 to 9.01 percent of whole-process
instructions because each request tests the bitset, but the lower propagation
volume more than offsets that cost. The unchanged 1,905,013,160 instructions
in `select_mrv_cell()` keep an MRV index as the next separate candidate for
weakly constrained search.

## Cachegrind

Cache and branch simulation remained metrics-disabled and used the same
whole-process workloads:

| Case | Data refs before/after | D1 misses before/after | LLd misses before/after | Branch mispredicts before/after |
| --- | ---: | ---: | ---: | ---: |
| generic forced thin SAT | 15,849,561 / 15,034,984 | 68,622 / 60,683 | 20,098 / 16,066 | 627,919 / 595,179 |
| generic unconstrained SAT | 190,758,574 / 189,725,863 | 5,635,359 / 5,641,729 | 34,120 / 30,742 | 16,947,270 / 16,884,232 |
| Yang–Zhang SAT, 6 variables | 9,639,808 / 8,542,673 | 42,793 / 36,551 | 14,057 / 10,487 | 314,275 / 229,590 |
| Yang–Zhang SAT, 12 variables | 78,427,053 / 69,977,162 | 387,457 / 356,845 | 103,691 / 74,933 | 2,393,131 / 1,799,893 |

The unconstrained D1 count is effectively flat (+0.11 percent); every other
modeled work count improves. Miss rates remain low, so the benefit is primarily
less scheduling and propagation work rather than a new cache effect.

## Decision

Retain queue deduplication in `wang_solve_optimized()`. The packed index turns
the effective peak into one occurrence per pending cell, removes 35.8--39.2
percent of processed arcs on the medium/large Yang–Zhang corpus, reduces their
native medians by 15.91--19.46 percent, and keeps all controls within the
predeclared regression limit. Its direct storage cost is 9,536 bytes on large
SAT and zero on the no-arc/root-conflict controls.

An MRV index remains a distinct candidate for weakly constrained search. Trail
compaction remains unsupported by the recorded rewrite counts. `TaskPlan`,
OpenMP, ring-buffer compaction, and other propagation scheduling changes remain out of
scope.

## Limitations

- The packed index covers dense `cell_count`, including inactive positions;
  it does not add a second active-cell numbering scheme.
- Queue storage is still the existing contiguous FIFO. Popped cells may be
  appended later, so tail capacity is not identical to effective occupancy;
  a ring buffer would be a separate mechanism.
- Enqueue request counts may rise when the coalesced schedule observes domain
  changes in a different order. Processed arcs and actual candidate appends
  are the relevant direct-work outcomes.
- The same-schema switch-off binary includes dormant v7 mechanism plumbing
  common to both comparison sides. It isolates enabling the packed index; the
  separate comparison with the instrumented baseline covers total integration.
- CPU frequency was not fixed and the host was not isolated. Timing medians
  are descriptive host evidence, not confidence intervals.
- Callgrind and Cachegrind include fixture construction, mandatory witness
  verification, and teardown. Cachegrind is a simulated cache model.
- No conclusion about trail compaction, `TaskPlan`, or OpenMP follows from
  this mechanism evaluation.

## Reproduction commands

Immutable baseline:

```sh
git worktree add --detach /tmp/tiling-foundry-queue-dedup-baseline \
  308e34a1e67c2e9a298b083724ad80d8bd83685e
make -C /tmp/tiling-foundry-queue-dedup-baseline \
  build/benchmarks/c/bench_solver
```

Comparable schema-v7 binaries:

```sh
make clean
make build/benchmarks/c/bench_solver \
  CFLAGS='-std=c17 -Wall -Wextra -Wpedantic -O2 -DWANG_OPTIMIZED_QUEUE_DEDUP=0'
cp build/benchmarks/c/bench_solver /tmp/queue-dedup-bench-baseline

make clean
make build/benchmarks/c/bench_solver
cp build/benchmarks/c/bench_solver /tmp/queue-dedup-bench-enabled
```

Direct metrics and a timing sample:

```sh
/tmp/queue-dedup-bench-enabled --case yang_zhang_sat_large_solver \
  --solver optimized --iterations 1 --metrics
taskset -c 2 /tmp/queue-dedup-bench-enabled \
  --case yang_zhang_sat_large_solver --solver optimized
```

Profilers:

```sh
valgrind --tool=callgrind --error-exitcode=1 \
  --callgrind-out-file=/tmp/queue-dedup-callgrind.out \
  /tmp/queue-dedup-bench-enabled --case yang_zhang_sat_large_solver \
  --solver optimized --iterations 1

valgrind --tool=cachegrind --cache-sim=yes --branch-sim=yes \
  --error-exitcode=1 --cachegrind-out-file=/tmp/queue-dedup-cachegrind.out \
  /tmp/queue-dedup-bench-enabled --case yang_zhang_sat_large_solver \
  --solver optimized --iterations 1
```

## Verification status

The final implementation passed `make check`, strict GCC and Clang builds,
ASan/UBSan/LeakSanitizer, GCC static analysis, the complete Memcheck target,
and the complete Cachegrind target. The first sanitizer attempt stopped at
LeakSanitizer's known ptrace limitation; the same target completed outside the
ptrace sandbox without a finding. Cachegrind emitted its documented brk-segment
growth warning on the very large crossover-block test, which still completed
successfully, and the target returned success. Targeted metrics-disabled
Callgrind and Cachegrind before/after runs also completed for all four profile
workloads. One initial `make check` after the switch-off comparison build used
stale switch-off objects and failed the candidate-only exact metric assertion:
Make does not track changes inside `CFLAGS`. `make clean && make check` rebuilt
the default switch-on candidate and passed. A clean is therefore mandatory
between the two comparable builds and before returning to normal gate runs.
