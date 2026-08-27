---
layout: page
title: "Yang–Zhang reduction explanation contract"
permalink: /wang-reduction-explanation/
description: Native-produced signal, permutation, and gadget provenance for one formula-to-region construction.
section: Yang–Zhang reduction
document_kind: Data and rendering contract
status: Current implementation
updated: 2026-08-27
nav_order: 25
---

# Yang–Zhang reduction explanation contract

The reduction builder can preserve an immutable explanation of the region it
actually constructed. This result connects formula variables and clause
positions to logical signals, the adjacent-swap program, and the half-open
rectangles occupied by the coarse gadgets. It is diagnostic provenance, not
solver input or a second implementation of the reduction.

`Region` remains the generic square-grid model: active cells and exposed
boundary colors only. The separate `ReductionExplanation` has its own semantic
invariants, native storage, lifetime, copied Python model, JSON contract, and
renderer consumer.

## Native result and ownership

A successful opt-in `yang_zhang_build_explained()` owns three related results:

- the completed `Region`;
- the exact adjacent-swap array used by the construction;
- a `ReductionExplanation` containing the exact source and target signal
  arrays passed to the permutation builder and the gadget spans emitted from
  the same dimensioned build.

The standard `yang_zhang_build()` returns the original compact
`YangZhangReduction`, frees temporary signals immediately after permutation
construction, and performs no provenance allocation. Ordinary solving and
benchmarks therefore do not pay for this diagnostic result, and the public
reduction ABI does not change. The opt-in entry point instead returns a
`YangZhangExplainedReduction` containing that compact result plus the owned
explanation arrays. They remain immutable after construction and
`yang_zhang_explained_reduction_destroy()` releases and zeros both parts.
Failed construction transfers nothing and leaves the output destroyed. The
Python adapter copies every value before that native cleanup; no pointer
escapes into the immutable Python model.

This structure is not a temporary output bundle. It represents a domain object
with independent invariants and an owned lifetime, and it has an immediate
exporter and renderer consumer.

## Signal identity and permutation

Each signal stores its row, kind, unique token ID, and, for variable signals,
the variable and occurrence numbers. The source order has three rows per
variable and one redundant row between variable groups. The target order
follows all three ordered positions of each clause, retaining repeated
variables exactly.

The recorded crossover gadgets are ordered by their swap ordinal. Each one
stores `swap_row`; replaying those adjacent swaps over the source token
identities must produce the target sequence exactly. Validators additionally
bind the source sequence to formula variables and the target sequence to the
referenced clause positions.

## Gadget spans

Every gadget uses a half-open rectangle:

```text
[x_begin, x_end) × [y_begin, y_end)
```

The closed kind set is:

| Kind | Ordinal identifies | Meaning |
| --- | --- | --- |
| `variable` | variable ID | Three-row variable input block |
| `left_forward` | always zero | Project-specific entry forwarder band |
| `crossover` | swap index | One adjacent-swap block; width is `swap_row + 1` |
| `right_forward` | always zero | Project-specific exit forwarder band |
| `clause` | clause ID | Clause-side staircase interval |

All rectangles must lie inside the constructed region extent. Provenance does
not enter `Region`, the generic solver, the verifier, or `TaskPlan`.

## Versioned export

The opt-in export adds two closed Draft 2020-12 contracts:

- `wang-reduction-explanation-v1` contains square bounds, source and target
  signals, gadget spans, the source formula digest, and the exact region
  artifact digest;
- `wang-explain-manifest-v2` references formula, tileset, region, and reduction
  artifacts by basename, schema, and full SHA-256 digest.

Manifest v1 remains unchanged for formula, tile-sheet, and plain region views.
Generate v2 from the real parser and builder with:

```sh
make shared
uv run --frozen python tools/export_pipeline_snapshots.py \
  tests/instances/pipeline_sat.cm13 \
  /tmp/pipeline-sat-reduction/manifest.json \
  --reduction-explanation
```

The manifest is installed last and atomically. Loading verifies all artifact
hashes, formula identity, region identity, dimensions, signal populations,
formula-to-signal correspondence, crossover replay, and gadget bounds.

## Renderer view

The isolated renderer accepts v1 and v2 manifests. The reduction view requires
v2:

```sh
cd renderer
uv run --locked python wang_square.py \
  ../tests/fixtures/pipeline_sat_reduction_explain/manifest.json \
  output/reduction.png \
  --view reduction
```

It overlays semantic gadget colors on the unassigned region, labels every
source row and clause destination, lists the parsed formula, and retains the
logical boundary-color legend. The renderer only displays recorded data; it
does not reconstruct gadget geometry or load native code.

Reduction provenance is square-specific, so this view rejects `--hex` rather
than implying that square gadget intervals have a hex-domain meaning. The
plain region and tileset views retain their separately checked `--hex`
presentation.

## Scope boundary

The explanation records construction, not solving. It contains no tile
assignment, domain, propagation, decision, conflict, backtrack, runtime, or Z3
internal order. Those belong to the separate bounded trace and report packets.
A valid explanation proves that artifacts agree with the recorded builder
output; it does not by itself prove SAT, tiling validity, or the mathematical
correctness of the reduction.
