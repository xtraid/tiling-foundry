---
layout: page
title: Native solver event trace and offline replay
permalink: /wang-solver-trace/
description: Bounded semantic events, full-state checkpoints, hash-bound transport, and presentation-only replay for native Wang solves.
section: Architecture and correctness
document_kind: Data and rendering contract
status: Current implementation
updated: 2026-08-27
nav_order: 34
---

# Native solver event trace and offline replay

The reference and optimized native solvers can emit an opt-in sequence of
semantic search events. The sequence records what the selected solver path
actually observed; it is not a reconstructed lesson, a profiler sample, or a
claim about a different engine. Ordinary solve calls retain their original ABI
and allocate no provenance storage.

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/solver-trace/frame-002517.png' | relative_url }}">
    <img src="{{ '/assets/images/solver-trace/trace.gif' | relative_url }}" alt="Observed reference solver domains narrowing from the initial state through propagation and decisions to a verified SAT result.">
  </picture>
  <figcaption><strong>Observed state.</strong> These frames are selected from one complete 2,896-event reference trace. The renderer replays the versioned deltas once; frame selection does not change their order. The <a href="{{ '/assets/images/solver-trace/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all selected states.</figcaption>
</figure>

## Native boundary and ownership

`wang/solver_trace.h` defines separate
`wang_solve_serial_traced()` and `wang_solve_optimized_traced()` entry points.
They call the same exact solver core and mechanism policies as the ordinary
entry points. The caller supplies `WangSolveTraceOptions` and a destroyed
`WangTracedSolveResult`; the combined result owns both the ordinary solve
result and the trace allocations.

The recorder allocates the initial dense state, bounded event array, and any
bounded checkpoint rows before search. An event capacity of at least two
reserves both the root and terminal result. Checkpoints are disabled as
`0/0`; otherwise interval and capacity must both be positive. Validation or
allocation failure transfers nothing. The combined destructor releases every
owned array, resets the structure, accepts null, and is idempotent.

No trace option or field is added to `WangSolverOptions` or `WangSolveResult`.
The ordinary reference and optimized calls therefore preserve their status,
dense witness, metrics, and ownership contracts without allocating trace
state.

### Disabled-path profile control

A deterministic Cachegrind control compared the same metrics-enabled 4-by-4
backtracking smoke against merge base `8616e31`, using GCC 14.2, portable
`-O2`, and trace-disabled ordinary entry points. Search work and every public
metric are exactly equal. The reference executable moved from 487,161 to
490,563 instructions (+0.70%) and from 101,091 to 101,706 data references
(+0.61%); optimized moved from 388,660 to 390,553 instructions (+0.49%) and
from 116,401 to 116,766 data references (+0.31%). Cache-miss rates and hotspot
order remain unchanged. The small dispatch cost is below one percent on this
control and creates no allocation or new search work; it is recorded rather
than presented as an exact zero-overhead claim.

This is one instruction-profile control, not a timing benchmark or a universal
performance bound. The full Cachegrind gate also covers the traced entry points
and the complete native test suite.

## Event semantics

The immutable root state is the dense domain array after root restrictions and
before arc propagation. Ordered events then carry only stable semantic facts:

| Kind | Meaning |
| --- | --- |
| `root` | Establish the full replay base in the initial phase |
| `domain_reduction` | Replace one exact old domain with a strict subset, caused by decision or propagation |
| `propagation` | Mark the end of an initial or search propagation interval |
| `decision` | Record the chosen cell and singleton candidate before its delta |
| `conflict` | Identify an observed empty active-cell domain |
| `backtrack` | Restore the ordered delta stack to an exact change mark |
| `result` | Publish the terminal `sat` or `unsat` status |

Every event has a complete-run sequence number, DFS depth, and change mark;
fields that do not apply are null in JSON. Domains remain canonical 23-bit
tile masks. The event order is deterministic for a fixed solver path and
input, but reference and optimized traces are not required to be byte-equal to
one another.

When capacity is exhausted, the recorder freezes the contiguous prefix and
retains the reserved terminal result. Its sequence number reveals the omitted
event count and `truncated` is true. The state after the gap is intentionally
unknown: replay returns the last reconstructable prefix state for the terminal
frame and never invents the missing deltas.

## Checkpoints and independent replay

Each checkpoint contains the full dense state and change mark immediately
after its configured event interval. Checkpoint capacity is independent from
event capacity; `checkpoints_truncated` reports exhaustion. They provide
bounded random-access anchors and, more importantly, independent replay
assertions.

The immutable Python model and the isolated renderer each validate the event
grammar and replay the same semantic deltas without calling either solver.
They reject widening or no-op reductions, an incorrect old domain, invalid
cell indices, impossible rollback marks, mismatched checkpoint state, a
misplaced terminal event, and a complete SAT state that disagrees with the
hash-bound solution. This is validation of recorded consistency, not a second
proof that the source decision is correct; native and Python tiling checkers
retain that responsibility.

## Closed transport and identity

`wang-solver-trace-v1` is a closed square, row-major document with
`semantics: observed`. It records the solver name, terminal status, formula,
region and optional solution digests, layout, capacity metadata, full initial
domains, events, and checkpoints.

`wang-explain-manifest-v3` binds that trace to the existing versioned formula,
tileset, region, reduction-provenance, and optional solution artifacts through
their exact schemas, basenames, and SHA-256 digests. The manifest is installed
atomically only after all content-addressed artifacts. A SAT trace requires a
solution reference; an UNSAT trace forbids one.

The committed example under `tests/fixtures/pipeline_sat_solver_trace/` comes
from the reference solver on `tests/instances/pipeline_sat.cm13`. It is a
complete 2,896-event run with an event capacity of 4,096 and 22 checkpoints at
interval 128. It records 451 dense positions, 444 of them active.

## Reproduction and presentation

Build the shared library and export one observed run:

```sh
make shared
uv run python tools/export_solver_trace.py \
  tests/instances/pipeline_sat.cm13 \
  build/solver-trace/manifest.json \
  --solver reference \
  --event-capacity 4096 \
  --checkpoint-interval 128 \
  --checkpoint-capacity 32
```

The isolated renderer consumes only the manifest and its JSON artifacts:

```sh
cd renderer
uv run --locked python wang_trace_render.py \
  ../build/solver-trace/manifest.json \
  ../build/solver-trace/rendered
```

`wang_trace.py` owns strict loading and one semantic replay.
`wang_trace_render.py` selects events and composes RGB frames.
`wang_animation.py` writes those same frames as deterministic atomic PNGs, one
contact sheet, and a presentation-only GIF. The renderer imports neither Z3
nor native code, and successful raster output is never treated as correctness
evidence.

Z3 uses a different boundary. Its versioned summaries are explicitly labeled
`encoding-order`, fix version, seed and thread count, and record the
project-defined constraint order, returned result/model, and stable
project-owned counts. They do not expose or infer Z3's internal search order.
