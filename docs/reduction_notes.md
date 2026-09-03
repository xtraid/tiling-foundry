---
layout: page
title: "Yang–Zhang reduction: geometry and witness correspondence"
permalink: /reduction_notes/
page_class: reference
description: Mathematical conventions, project-specific geometry, and witness-level evidence for the implemented reduction.
section: Yang–Zhang reduction
document_kind: Technical note
status: Current implementation
updated: 2026-08-25
nav_order: 10
---

# Yang–Zhang reduction: geometry and witness correspondence

This technical note connects the mathematical reduction to the concrete
geometry built by Tiling Foundry. It records signal height, indexing, the
paper example, the project's explicit forwarder bands, and witness-level
evidence.

Each section distinguishes conventions inherited from Yang–Zhang from
indexing and geometry choices introduced by this project. Those categories
must not be conflated.

Public headers and tests define implemented behavior. The
[formula-to-region builder]({{ '/yang_zhang_builder_design/' | relative_url }})
describes the software contract, while the
[initial architecture specification]({{ '/historical_architecture/' | relative_url }})
is retained only as design history.

Primary reference:

> Chao Yang, Zhujun Zhang,  
> *NP-completeness of Tiling Finite Simply Connected Regions with a Fixed Set of Wang Tiles*,  
> arXiv:2405.01017v2 (2024).

## 1. Signal height

Signal height fixes the vertical coordinate range used by the routing and
builder formulas below. For `n` variables, the construction has three signal
rows per variable and one redundant row between adjacent variable groups:

```text
height = 3n + (n - 1) = 4n - 1
```

For `n = 3`, the logical height is 11.

## 2. Adjacent-swap indexing

This conversion relates the paper's row numbering to the zero-based swap trace
stored by the implementation. The paper uses 1-based rows.

If a paper crossover has width `w`, it swaps rows `w` and `w + 1`.

The implementation stores:

```text
AdjacentSwap.row = w - 1
```

therefore:

```text
crossover_block_width = AdjacentSwap.row + 1
```

The tests keep this conversion explicit because an off-by-one error changes the
geometry of every crossover gadget.

## 3. Paper example

The paper example provides a fixed cross-check for both indexing and total
crossover width. Its adjacent-transposition sequence is:

```text
swap(8), swap(7), swap(6), swap(5), swap(4), swap(3),
swap(4), swap(5), swap(6),
swap(9), swap(8), swap(7), swap(9), swap(8)
```

The C zero-based sequence is:

```text
7, 6, 5, 4, 3, 2, 3, 4, 5, 8, 7, 6, 8, 7
```

The corresponding crossover widths sum to:

```text
89
```

This sequence is kept as a golden regression test.

## 4. Project convention: explicit forwarder bands

The project keeps:

```text
2 forwarder columns before the crossover chain
2 forwarder columns after the crossover chain
```

The purpose is architectural and diagnostic:

- make the point where variable signals enter the crossover chain explicit;
- make the point where reordered signals leave the chain explicit;
- separate gadget boundaries visually;
- provide a simple neutral propagation band for debugging and rendering.

These `2 + 2` columns are a **project convention**. The paper does not require
those exact standalone bands.

The coarse layout is therefore:

```text
[V] [FF] [ crossover chain ] [FF] [clause area]
 1   2                              2       2
```

and:

```text
width =
    1
  + 2
  + sum(crossover widths)
  + 2
  + 2
```

For the paper example:

```text
width = 1 + 2 + 89 + 2 + 2 = 96
```

## 5. Neutrality of the explicit forwarder bands

The two forwarder bands are an adaptation made by this project, so their
neutrality must follow from the actual 23-tile construction rather than being
attributed to the paper. It follows locally from the edge colors.

For `s` in `{0, 1}`, the atomic forwarder `Fs` has edges

```text
(N, E, S, W) = (B, s, B, s).
```

The internal glue colors make every multi-cell generalized tile indivisible:
an occurrence of one of its atomic parts forces the other parts. In either
explicit band, the north and south boundary colors are `B`, there is no `L` or
`R` boundary seed, and the neighboring completed gadgets expose only signal
colors `0` or `1` at the band interface.  Inspecting the remaining tile
families then excludes them as follows:

- a variable tile requires `V` on its west side, and no tile has `V` on its
  east side, so it can occur only at the west variable boundary;
- a clause tile exposes `0'` on its east side, and no tile has `0'` on its west
  side, so the corresponding generalized tile can occur only at the east
  clause boundary;
- an `L` anchor or the lower part of a crossover forces an `L` path down to an
  `L` boundary seed, which the band does not have;
- an `R` anchor or the upper part of a crossover forces an `R` path up to an
  `R` boundary seed, which the band does not have.

Thus only `F0` and `F1` can occupy a band cell.  If the west edge of a row is
`s`, matching selects `Fs`, whose east edge is again `s`.  Induction over the
band width gives a unique tiling of that row and preserves its signal.  A
redundant row is the special case `s = 0`.

Consequently every tiling without the extra columns has exactly one extension
through either explicit band, and every tiling with a band restricts to the
same interface signals when the band is removed.  Adding the bands therefore
introduces no choice and does not change tileability, hence it cannot change
SAT/UNSAT of the reduced instance.

The concrete `Region` builder has black-box tests for the active mask, boundary
encoding, and exact swap trace. End-to-end serial-solver regressions compare
complete SAT and UNSAT reductions with an independent Boolean oracle. These
are regression checks, not the proof of band neutrality.

Focused tests cover forwarder, anchor, and crossover generalized tiles for
both signal values. Whole-block tests enumerate the binary input/output
relation at every swap position for height seven. They also sweep larger valid
heights through 31 rows, exercise permutation-builder chains, fuzz
deterministic larger chains, and stress up to 31 signal rows and 96 consecutive
crossover blocks.

## 6. Dimension calculator and completed builder

The implementation separates coarse size arithmetic from construction of the
active mask and boundary. `yang_zhang_compute_dimensions()` is the coarse
dimension calculator.

It computes:

- total height;
- total width.

The adjacent-swap sequence remains owned by the permutation layer. The dimension
calculator only reads it for the duration of the call.

The public `yang_zhang_build()` composes this calculator with the remaining
reduction stages:

- validation of the canonical in-memory formula;
- unique occurrence and redundant signal tokens;
- source/target permutation construction;
- a dense bounding box with the paper's simply connected clause staircase as
  its active mask;
- complete colors on every exposed side, including the staircase notches;
- variable, clause, and isolated crossover boundary markers;
- transactional transfer of the exact adjacent-swap trace;
- immutable source/target signal and gadget-span provenance from the same
  construction, as specified by the
  [reduction explanation contract]({{ '/wang-reduction-explanation/' | relative_url }}).

Parsing, solving, tile selection, and persistent gadget annotations belong to
other modules. The
[formula-to-region builder page]({{ '/yang_zhang_builder_design/' | relative_url }})
is the full implementation contract; public headers and black-box tests remain
authoritative for behavior.

## 7. Witness-level correspondence

Decision agreement alone compares only whether independent solvers report SAT
or UNSAT; their preferred satisfying models may be unrelated. The implemented
witness bridge adds two more concrete operations over the exact
`YangZhangReduction` built for a live formula:

```text
Boolean assignment a
    -> fix the three cells (0, 4v), (0, 4v + 1), (0, 4v + 2)
       of every variable v
    -> solve the remaining Wang region
    -> independently verify the complete tiling

verified Wang tiling
    -> decode the exact V0_TOP/V0_MID/V0_BOTTOM or V1/V1/V1 pattern
       in each variable block
    -> pass the decoded assignment to the independent Boolean checker
```

False pins the three atomic V0 tiles in order; true pins `TILE_V1` in all
three positions. Every other active cell begins unrestricted. The region
boundary, canonical tileset, propagation, and search determine forwarders,
anchors, crossovers, redundant rows, and clause gadgets. The bridge neither
reads the adjacent-swap trace nor evaluates formula clauses.

The executable evidence enumerates all 1,701 canonical formulas through three
variables, all `2^n` assignments for each formula, and both native solver entry
points. Across 27,044 constrained solves, direct Boolean witness validity is
equivalent to Wang SAT under the variable pins. Every SAT result passes the
independent Wang verifier, extracts the exact input assignment, and satisfies
the representation correspondence predicate.

This establishes extraction as a left inverse of assignment extension for the
tested domain. It does not establish a bijection. One satisfying assignment
may have multiple tilings, and extending an assignment extracted from a tiling
need not reproduce that tiling byte for byte.

Extraction preserves a decoded assignment even if it later fails Boolean
verification. Such a pair is a reduction counterexample to retain and inspect.
The [witness correspondence design]({{ '/witness_correspondence/' | relative_url }})
defines the bridge, status, and lifetime contracts.
