---
layout: page
title: Optimized solver byte-wise support tables
permalink: /solver_byte_support_2026-08-20/
description: Evidence for aggregating Wang propagation support by domain byte.
section: Solver optimization
document_kind: Benchmark report
status: Accepted mechanism
updated: 2026-08-27
nav_order: 60
---

# Optimized solver byte-wise support tables — 20 August 2026

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/optimized-mechanisms/frame-05.png' | relative_url }}">
    <img src="{{ '/assets/images/optimized-mechanisms/trace.gif' | relative_url }}" alt="Didactic comparison of the reference solver baseline and the five retained optimized serial mechanisms.">
  </picture>
  <figcaption><strong>Didactic replay.</strong> This shared animation locates byte-wise support aggregation among the five isolated mechanisms; the measurements below, not the animation, establish its effect. The <a href="{{ '/assets/images/optimized-mechanisms/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all stages.</figcaption>
</figure>

This report evaluates only the union of compatible neighbor tiles during
propagation. The reference path retains the baseline loop over every set tile
in the source domain. The optimized path splits the 23-bit domain into three
8-bit chunks and ORs one derived table entry for each nonzero chunk. Queue
behavior, propagation order, domain writes, trail, rollback, MRV, DFS search
order, diagnostics, SAT result ownership, `TaskPlan`, and OpenMP are unchanged.

## Reproduction identity

Measurements used Debian GCC 14.2.0, portable C17 `-O2`, Linux
`6.12.101+deb13-amd64`, benchmark schema version 5, and CPU 2 affinity on the
Ryzen 5 3600 host. The source snapshot is based on parent commit
`01a8dd48ab86761f2629b50c457cfcc0b33a5930`; the binary hashes below identify
the measured revisions.

The comparable binaries use the same schema-v5 source, public metrics layout,
compiler, flags, source list, and link order. They differ only in the private
`use_bytewise_support` mechanism flag:

```text
dc36bede1977af01778379625a531e856d8a19e67963f4315519b2c1a95ee268  set-tile-loop optimized baseline
ecb6e558af0bb11009a9a38a4e2269ccd70b03948daad9014c9a095c49ecdb5e  byte-wise support build
```

The original schema-v4 binary from `01a8dd4` was retained only as preliminary
identity evidence and was not used for the final timing comparison because its
metrics layout and executable text differ.

## Derived table and ownership

`ByteSupportTables` contains `4 x 3 x 256` `uint32_t` masks, exactly 12,288
bytes. For direction `d`, byte position `b`, and value `v`, an entry is the OR
of `compat[d][tile]` for every set bit of `v` whose tile index is valid. The
builder derives every entry from the canonical compatibility masks; it does not
duplicate tileset facts.

The table is allocated, built, owned, and freed only by
`wang_solve_optimized()`. The shared reference invocation neither reserves
stack storage nor allocates heap storage for it. Allocation failure remains
transactional and returns `ERROR` with a destroyed public result.

A first design exhaustively revalidated all 3,072 entries inside every solve.
It was rejected: the small backtracking control regressed by 104.59 percent.
The retained design instead exposes the private builder to a dedicated C test,
which independently reconstructs compatibility with `wang_tiles_match()` and
checks all 4 x 3 x 256 entries. This keeps exhaustive validation outside the
hot path.

## Direct mechanism evidence

Schema v5 adds three counters. `support_tile_visits` counts candidates consumed
by the baseline loop, `support_byte_lookups` counts nonzero chunks consumed by
the optimized union, and `support_table_bytes` reports private table storage.
All fields remain zero when metrics are disabled and are part of the destroyed
result precondition. Reference table bytes are zero; every valid optimized
solve reports 12,288 bytes, including no-arc controls.

Each case ran once with metrics. Semantic work counters, status, and witness or
diagnostic contracts remained unchanged.

| Case | Arcs | Before tile visits | After byte lookups |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 196,599 | 262,132 | 196,599 |
| generic unconstrained SAT | 501,298 | 5,010,215 | 1,358,602 |
| generic backtracking SAT | 424 | 2,915 | 961 |
| Yang–Zhang SAT, 6 variables | 303,875 | 1,559,802 | 624,206 |
| Yang–Zhang UNSAT, 6 variables | 78,048 | 407,244 | 163,173 |
| Yang–Zhang SAT, 12 variables | 2,565,295 | 13,058,856 | 5,214,770 |
| Yang–Zhang UNSAT, 12 variables | 634,603 | 3,392,038 | 1,333,794 |

The optimized rows have zero tile visits, and the reference rows have zero byte
lookups. The result-copy SAT and root-UNSAT controls process zero arcs and
therefore report zero for both work counters.

## Alternating timing gate

Seven passes alternated before/after order, used the standard per-case iteration
count, disabled metrics, and pinned each fresh process to CPU 2. Medians are per
solve.

| Case | Set-tile loop ms | Byte-wise ms | Delta |
| --- | ---: | ---: | ---: |
| generic forced thin SAT | 3.504252 | 3.128253 | -10.73% |
| generic result-copy SAT | 30.699250 | 30.882393 | +0.60% |
| generic unconstrained SAT | 181.117506 | 143.830185 | -20.59% |
| generic backtracking SAT | 0.033622 | 0.014131 | -57.97% |
| generic root UNSAT | 18.606869 | 19.231809 | +3.36% |
| Yang–Zhang SAT, 6 variables | 11.329038 | 2.472650 | -78.17% |
| Yang–Zhang UNSAT, 6 variables | 2.843642 | 0.544352 | -80.86% |
| Yang–Zhang SAT, 12 variables | 91.146419 | 20.700992 | -77.29% |
| Yang–Zhang UNSAT, 12 variables | 22.577116 | 4.206028 | -81.37% |

Every propagation case improves. The two no-arc controls isolate construction
and allocation overhead; both remain inside the predeclared 3--5 percent
material-regression guardrail. Process peak RSS varied from -116 KiB to
+1,164 KiB across cases and is allocator/process noise at this scale, so the
direct 12,288-byte storage counter is authoritative.

## Correctness and analysis gates

The final implementation passed `make check`, strict GCC and Clang builds,
ASan/UBSan/LeakSanitizer outside the ptrace sandbox, GCC static analysis, the
complete Memcheck target, and the complete Cachegrind target. A separate
optimized benchmark smoke also completed under Cachegrind. The differential
suite covers generic SAT/UNSAT, brute-force equivalence, backtracking and
rollback, failed-leaf diagnostics and capture, independent witnesses, deep
stack growth, invalid API contracts, and Yang–Zhang SAT/UNSAT reductions.

## Decision

Retain byte-wise support tables in `wang_solve_optimized()`. They replace the
measured candidate-tile loop with fewer directly counted nonzero-byte lookups,
produce large improvements on the propagation-heavy corpus, improve the small
backtracking case after validation is moved out of the hot path, and keep
no-arc controls within the regression guardrail. Queue deduplication, MRV
indexing, `TaskPlan`, and operational OpenMP remain separate future candidates.
