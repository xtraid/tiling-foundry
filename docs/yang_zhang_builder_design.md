---
layout: page
title: "Yang–Zhang formula-to-region builder"
permalink: /yang_zhang_builder_design/
description: Data flow, geometry, ownership, and tested invariants of the implemented formula-to-region builder.
section: Yang–Zhang reduction
document_kind: Implementation contract
status: Current implementation
updated: 2026-08-27
nav_order: 20
---

# Yang–Zhang formula-to-region builder

## Purpose and scope

The builder consumes a validated canonical Cubic Monotone 1-in-3 SAT formula.
It constructs the colored simply connected `Region` used by the fixed 23-tile
Yang–Zhang reduction and returns the exact adjacent-swap trace. An opt-in
result preserves immutable construction provenance with a separate explicit
lifetime, without changing the standard reduction ABI.

This is the implementation contract for builder input validation, routing,
coordinates, active geometry, exposed boundary colors, ownership, and
black-box obligations. In the pipeline, it sits after native parsing and
before every generic solver or oracle that consumes the resulting region.

The paper remains authoritative for the mathematical construction and fixed
tileset. Public headers and black-box tests are authoritative for API behavior.
Use the [reduction note]({{ '/reduction_notes/' | relative_url }}) for the
paper/project convention boundary; this page is not an intuitive tutorial.

The complete builder contract is implemented. Solver-level integration checks
SAT and UNSAT reductions against an independent Boolean oracle. Focused tests
cover the atomic forwarder, both anchors, and crossover generalized tiles.
Section 11.4 records the whole-block solver regressions.

Primary source:

- Chao Yang and Zhujun Zhang, *NP-completeness of Tiling Finite Simply
  Connected Regions with a Fixed Set of Wang Tiles*, arXiv:2405.01017v2,
  especially Figures 1--4 and the proof of Theorem 3.

Text parsing, solving, independent verification, scheduling, oracles, solution
transport, and rendering have separate contracts.

<figure class="algorithm-animation">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="{{ '/assets/images/builder-routing/frame-04.png' | relative_url }}">
    <img src="{{ '/assets/images/builder-routing/trace.gif' | relative_url }}" alt="Canonical Yang–Zhang construction with native variable, forwarder, crossover, and clause gadget spans appearing in source order.">
  </picture>
  <figcaption><strong>Canonical construction.</strong> The frames reveal spans from the versioned native construction sidecar; they are not timestamps from an instrumented builder. The <a href="{{ '/assets/images/builder-routing/contact-sheet.png' | relative_url }}">static contact sheet</a> shows all six stages.</figcaption>
</figure>

## 1. Module boundary

`yang_zhang` is a deterministic reduction builder:

```text
validated canonical Cubic Monotone 1-in-3 formula
    -> YangZhangReduction
    -> optional YangZhangExplainedReduction
```

The builder performs these stages:

1. validate that the in-memory formula is inside the mathematical input
   domain required by the reduction;
2. construct the source and target signal sequences;
3. delegate adjacent-swap generation to `permutation.c`;
4. compute the layout dimensions;
5. build the complete active mask;
6. color every exposed unit edge of the region;
7. retain the exact source/target signals and emit the gadget spans from those
   same dimensioned construction stages;
8. return the compact standard result, or the standard result and explanation
   together through the opt-in wrapper, transactionally.

Responsibilities outside the builder are:

- text parsing and normalization;
- SAT or Wang solving and tile selection;
- persistent gadget annotations;
- colors on internal edges between active cells;
- solver domains, assignments, trails, tasks, and Z3 expressions.

Anchor, crossover, and forwarder placement is forced later by the colored
boundary and `TILESET`. It is not stored in `Region`.

## 2. Canonical input representation

The canonical formula types in `include/wang/formula.h` are:

```c
typedef struct {
    /* Canonical 0-based indices in 0 .. variable_count - 1. */
    uint32_t variable_index[3];
} Cm13Clause;

typedef struct {
    uint32_t variable_count;

    Cm13Clause *clauses;
    size_t clause_count;
} Cm13Formula;
```

The parser owns the clause array it allocates until the caller passes the
formula to `cm13_formula_destroy()`. `yang_zhang_build()` borrows the formula
and its clause storage for the duration of the call; it neither modifies nor
frees them.

`variable_count` declares the variable universe independently from the clause
contents. Variable identities are exactly the canonical indices
`0 .. variable_count - 1`; no separate variable object is needed while an ID
would contain no information beyond its index. The builder does not infer,
deduplicate, or renumber this universe from the clauses. Clause entries refer
directly to canonical variable indices, so target-sequence creation and domain
validation remain linear.

Repeated indices inside one clause are valid. For example, the paper clause
`(x1, x1, x3)` is represented after canonicalization as:

```c
{ .variable_index = { 0, 0, 2 } }
```

The parser converts textual identifiers to this canonical representation. No
negation field exists because the source problem is monotone, and the fixed
three-element array encodes clause arity in the type.

### 2.1 Builder-side domain validation

Validation occurs once at the public API boundary. The builder rejects the
input without modifying the output when any of these conditions holds:

- the formula, output, or clauses array is null;
- `variable_count == 0`;
- `variable_count > YANG_ZHANG_MAX_VARIABLES`;
- `clause_count != variable_count`;
- any clause index is outside `0 .. variable_count - 1`;
- any variable index occurs other than exactly three times in the flattened
  clause array;
- any derived count, allocation size, height, or width overflows;
- an allocation fails.

No distinctness check is applied to the three entries of one clause. Cubicity
is about total occurrences across the formula, not distinct variables within a
clause.

The occurrence-count pass also provides the stable occurrence number `0`, `1`,
or `2` used while constructing target signal tokens. Validation rejects a
fourth occurrence before a small counter could wrap.

## 3. Public reduction result and ownership

`include/wang/yang_zhang.h` exposes:

```c
typedef struct {
    Region region;

    AdjacentSwap *swaps;
    size_t swap_count;
} YangZhangReduction;

typedef struct {
    YangZhangReduction reduction;
    ReductionExplanation explanation;
} YangZhangExplainedReduction;

bool yang_zhang_build(
    const Cm13Formula *formula,
    YangZhangReduction *out_reduction
);

bool yang_zhang_build_explained(
    const Cm13Formula *formula,
    YangZhangExplainedReduction *out_reduction
);

void yang_zhang_reduction_destroy(YangZhangReduction *reduction);
void yang_zhang_explained_reduction_destroy(
    YangZhangExplainedReduction *reduction
);
```

The exact array returned by `yang_zhang_permutation_build()` is transferred
into `YangZhangReduction`; it is not copied. It is retained as a diagnostic
trace of the reduction and as possible input to later task-plan preprocessing.
The opt-in wrapper retains the source and target arrays that were actually
passed to that permutation build and records half-open variable, forwarder,
crossover, and clause rectangles. The reference solver and independent
verifier receive only `Region` and do not use this diagnostic provenance. Its
full data contract is the [reduction explanation reference]({{ '/wang-reduction-explanation/' | relative_url }}).

The output starts in the destroyed state:

```c
YangZhangReduction reduction = {0};
```

Both build entry points require a destroyed/zeroed output. The standard call
owns only `region.cells` and `swaps`, retains its original public layout, frees
temporary signals as soon as permutation construction finishes, and does not
allocate provenance. The opt-in call uses a zeroed
`YangZhangExplainedReduction`; its `explanation` owns the retained signals and
gadget spans. On every failure, the selected output remains destroyed.
`yang_zhang_reduction_destroy()` releases the compact result, while
`yang_zhang_explained_reduction_destroy()` releases and zeros both parts of the
opt-in wrapper. Both accept null.

The builder is safe to call concurrently for immutable formulas when each call
uses a distinct output object. It owns no global mutable state.

## 4. Coordinates and orientation

The entire C implementation uses:

```text
(0, 0)       top-left
x increases  to the right
y increases  downward
N/E/S/W      exposed cell sides
```

Signal rows are zero-based. `AdjacentSwap.row == r` swaps signal rows `r` and
`r + 1`. The corresponding paper row and crossover-block width are both:

```text
w = r + 1
```

A right-anchor chain is described in its nominal direction: from the crossover
it travels **up and to the right** until it reaches the top boundary. In
coordinates, each step decreases `y` and increases `x`. Reading the same chain
from its top-boundary seed reverses the traversal, but implementation comments
retain the nominal direction to avoid ambiguity.

A left-anchor chain rises vertically from its `L` seed on the bottom boundary.

## 5. Source and target signal sequences

For `n = variable_count`, the signal height is:

```text
h = 3n + (n - 1) = 4n - 1
```

There are three unique occurrence tokens for every variable and one unique
redundant token between consecutive variable/clause groups.

### 5.1 Source order

The source order is built directly from the canonical range declared by
`variable_count`:

```text
x0^0 x0^1 x0^2 z0 x1^0 x1^1 x1^2 z1 ... x(n-1)^0 x(n-1)^1 x(n-1)^2
```

One deterministic token-ID scheme is:

```text
variable occurrence: token_id = 3 * variable_index + occurrence
redundant token:      token_id = 3 * n + redundant_index
```

### 5.2 Target order

Scan clauses from first to last and each clause from row 0 to row 2. Maintain a
counter for every variable. When `variable_index == v` is encountered, append
the unique token `(v, occurrence_counter[v])`, then increment the counter.
Append redundant token `zc` after clause `c`, except after the last clause.

Because validation established cubicity, each variable counter finishes at
exactly three and target is a permutation of source even when a clause repeats
a variable.

### 5.3 Swap generation

The builder passes source and target to `yang_zhang_permutation_build()`;
`yang_zhang.c` does not duplicate its sorting algorithm.

The existing algorithm fixes the target prefix from top to bottom. For target
position `i`, if the required token is currently at `j`, it emits:

```text
swap(j - 1), swap(j - 2), ..., swap(i)
```

The permutation regression verifies that applying every returned swap to
source produces target exactly.

Source, target, and occurrence counters are temporary build storage and are
released on both success and failure. Only the swap array is transferred to
the public reduction result.

## 6. Coarse layout

The project layout remains:

```text
[variables][left forwarders][crossover chain][right forwarders][clauses]
     1              2           variable               2           2
```

The two forwarder columns on each side are an explicit project convention, not
a width required by the paper.

For swaps `s[0..k)`, dimensions are:

```text
height = 4n - 1

width =
    YANG_ZHANG_VARIABLE_WIDTH
  + YANG_ZHANG_LEFT_FORWARD_WIDTH
  + sum(s[i].row + 1)
  + YANG_ZHANG_RIGHT_FORWARD_WIDTH
  + YANG_ZHANG_CLAUSE_WIDTH
```

`yang_zhang_compute_dimensions()` is the single implementation of this
arithmetic.

`width` and `height` describe a dense bounding box, not a filled rectangle.
The clause area gives the right edge the staircase shape shown in Figures 2
and 3 of the paper. Let `clause_x = width - 2`, the first of the two clause
columns. The last active column of row `y` is:

| `y % 4` | Role | Last active column |
| --- | --- | --- |
| `0` | first clause signal | `clause_x` |
| `1` | second clause signal | `width - 1` |
| `2` | third clause signal | `width - 1` |
| `3` | redundant separator | `clause_x - 1` |

The final row always has role `2`, because `height = 4n - 1`. Every cell from
column zero through the last active column belongs to the region; later cells
in the bounding box remain inactive. This mask is simply connected and leaves
exactly the one-, two-, two-cell clause shape required to move a true signal
down by zero, one, or two rows.

## 7. Crossover blocks

Let `block_x` be the first column of one crossover block and let:

```text
r = swap.row
w = r + 1
```

The block occupies the full signal height and the half-open horizontal range:

```text
[block_x, block_x + w)
```

Its top and bottom boundary colors, from left to right, are:

```text
top:    B^(w-1) R
bottom: L B^(w-1)
```

With cell-side notation, after the complete active mask exists:

```c
region_set_boundary(region, block_x + w - 1, 0, N, COLOR_R);
region_set_boundary(region, block_x, height - 1, S, COLOR_L);
```

All other top and bottom sides of this block remain `COLOR_B`.

The `L` seed creates a vertical left-anchor chain. The forced crossover lies
on rows `r` and `r + 1`. From that crossover, the right-anchor chain rises to
the right and reaches the `R` seed at the block's top-right corner.

After one block:

```c
block_x += w;
```

The next block begins immediately. "Immediately" refers to adjacent horizontal
intervals, not adjacent crossover tiles. Anchor locations vary with `r`; the
remaining cells between and around anchor chains are forced to be forwarders,
forming the triangular forwarder areas visible in the paper. The builder does
not annotate or pre-place those forwarders.

Each adjacent transposition retains its own block rather than being compressed
into consecutive runs of `L` and `R` colors. All anchors share the same
`L`/`R` colors, so such a packing would introduce
interacting, indistinguishable anchor chains. The proven construction isolates
every adjacent transposition in the block above. A compressed construction
would require a separate correctness proof and is out of scope.

No `4n - 1` forwarder padding is required after the last block. The existing
two-column right-forwarder band is retained.

## 8. Complete boundary-color template

A finished Yang–Zhang region has a color on every exposed unit side. No
exposed side remains `COLOR_NONE`. All sides between two active cells remain
unconstrained in `Region`; their colors are determined only by tile matching.

Boundary colors are applied after the complete active mask has been built, in
the order below.

### 8.1 Default exposed boundary

The default pass visits every active cell and sets each side touching the
outside of the bounding box or an inactive cell to `COLOR_B`. Sides shared by
two active cells remain `COLOR_NONE`. At corners and staircase notches, every
exposed unit side is a separate constraint.

### 8.2 Left variable boundary

For variable `v`, its three rows are:

```text
y = 4v, 4v + 1, 4v + 2
```

Set their west sides to `COLOR_V`. If `v` is not the final variable, row
`4v + 3` is redundant; set its west side to `COLOR_0`.

The resulting repeating pattern is:

```text
V V V 0 | V V V 0 | ... | V V V
```

### 8.3 Right clause boundary

For clause `c`, its three rows are:

```text
y = 4c, 4c + 1, 4c + 2
```

Let `clause_x = width - 2`. Set the east boundary at these cells:

```text
(clause_x, y)             -> COLOR_0_PRIME
(width - 1, y + 1)        -> COLOR_0_PRIME
(width - 1, y + 2)        -> COLOR_1
```

If `c` is not the final clause, row `4c + 3` is redundant; set its east side
at `(clause_x - 1, 4c + 3)` to `COLOR_0`. These coordinates are the last
active cells of their rows, so all four assignments are genuine boundary
constraints.

The resulting repeating pattern is:

```text
0' 0' 1 0 | 0' 0' 1 0 | ... | 0' 0' 1
```

### 8.4 Crossover overrides

The crossover-boundary pass follows swap order and overwrites only:

- the top-right side of each block from `COLOR_B` to `COLOR_R`;
- the bottom-left side of each block from `COLOR_B` to `COLOR_L`.

All other exposed sides, including the horizontal sides created by the clause
staircase, remain `COLOR_B`. There are no colors on internal seams between two
active cells, layout bands, or crossover blocks.

## 9. Transactional build sequence

`yang_zhang_build()` follows this order:

1. verify the public pointers and that the output is destroyed;
2. validate the complete formula domain;
3. allocate occurrence counters and source/target signal arrays;
4. build source and target;
5. call `yang_zhang_permutation_build()`;
6. optionally assert in tests/debug builds that applying the swaps transforms
   a source copy into target;
7. call `yang_zhang_compute_dimensions()`;
8. initialize a local temporary `Region`;
9. activate the paper-shaped mask, iterating row-major for locality;
10. set every exposed side to the default `COLOR_B`;
11. overwrite the left variable boundary;
12. overwrite the right clause boundary;
13. walk swaps and overwrite crossover `L/R` markers;
14. free all temporary signal/counter storage;
15. move the temporary region and swap pointer into `out_reduction`.

Construction uses the public `Region` API. The entire active mask is complete
before the first `region_set_boundary()` call because that function accepts
only genuinely exposed sides.

Failure cleanup releases locally owned source, target, counters, and swaps,
destroys the temporary region, leaves `out_reduction` destroyed, and returns
`false`. The public result is populated transactionally only after every stage
succeeds.

## 10. Private decomposition

The implementation keeps the public API small and decomposes construction into
private helpers with one responsibility each:

```c
static bool formula_is_in_reduction_domain(const Cm13Formula *formula);

static bool build_signal_sequences(
    const Cm13Formula *formula,
    SignalToken **out_source,
    SignalToken **out_target,
    size_t *out_signal_count
);

static int32_t last_active_x(const Region *region, int32_t y);

static bool activate_paper_region(Region *region);

static bool paint_exposed_boundary(Region *region);

static bool paint_variable_boundary(
    Region *region,
    uint32_t variable_count
);

static bool paint_clause_boundary(
    Region *region,
    size_t clause_count
);

static bool paint_crossover_boundaries(
    Region *region,
    int32_t first_x,
    const AdjacentSwap *swaps,
    size_t swap_count
);
```

These helpers remain private because their responsibility boundaries and
failure behavior are observable through `yang_zhang_build()` and public
`Region` accessors.

## 11. Black-box verification

`tests/c/test_yang_zhang.c` exercises the following fixtures through public
APIs.

### 11.1 Minimal valid instance

The minimal fixture uses one variable and one clause `{0, 0, 0}` and verifies:

- `height == 3`;
- no redundant row;
- no swaps;
- project width `1 + 2 + 0 + 2 + 2 == 7`;
- row lengths `6,7,7`, implementing the one-, two-, two-cell clause area;
- west boundary is `V,V,V`;
- east boundary is `0',0',1`;
- every other exposed side is `B`;
- all non-exposed sides remain `COLOR_NONE`.

This fixture is a valid reduction input even if its Boolean instance is
unsatisfiable. The builder validates the source domain, not satisfiability.

### 11.2 Paper instance

The paper fixture uses variables `0,1,2` and clauses:

```text
(0,0,2)
(1,1,2)
(0,1,2)
```

Its assertions cover:

- `height == 11`;
- the swap rows are exactly
  `7,6,5,4,3,2,3,4,5,8,7,6,8,7`;
- crossover widths sum to `89`;
- total project width is `96`;
- applying the returned swaps to source yields the target ordering;
- every crossover block has `R` at its top-right and `L` at its bottom-left;
- all other north/south sides are `B`;
- left and right boundary patterns match Section 8 exactly;
- the clause staircase matches Section 6, inactive cells have no constraints,
  and there are no boundary constraints between active cells.

### 11.3 Invalid and adversarial input

The invalid-input suite covers:

- null API arguments;
- zero variables;
- a null clause array;
- clause-count mismatch;
- clause index out of range;
- a variable occurring two or four times;
- dimension overflow where representable without dangerous allocation;
- a non-destroyed output object;
- the clause array unchanged after both success and failure;
- output fully destroyed after every failure path.

Deterministic stress and fuzz cases generate small canonical arrays with a
fixed PRNG seed, mutate one invariant at a time, and verify rejection without
output side effects. The same tests run under Memcheck, Cachegrind, ASan, and
UBSan workflows.

### 11.4 Solver-level gadget coverage

The public solver/verifier path checks complete Yang–Zhang reductions against
an independent Boolean oracle. Focused black-box solver tests establish the
local generalized-tile behavior for both signals. Forwarders preserve the
signal, both anchors are forced by their boundary colors, and all four
crossover inputs `(a,b)` force outputs `(b,a)`.

The whole-block regression cuts out the exact width-`w` rectangle. It applies
only the top `B^(w-1)R`, bottom `LB^(w-1)`, and binary interface conditions;
no interior tile or edge is preselected.

At height seven, the test exhaustively checks all binary input/output pairs at
every valid swap row. Exactly the requested adjacent transposition is SAT, and
every other output is UNSAT. Further cases cover every position at larger
valid heights through 31 rows, two- and three-block permutation chains,
deterministic fuzz cases, and large chains up to 31 rows and 96 crossover
blocks.

These are regression checks rather than a general proof. The separate
two-column forwarder bands are justified by the tile-edge exclusion argument
in Section 5 of the
[reduction note]({{ '/reduction_notes/' | relative_url }}).

## 12. Stable design decisions

- `variable_count` explicitly declares the variable universe; it is not
  derived from clauses.
- Variable identities are canonical indices; no separate variable array is
  stored.
- Clause references are canonical variable indices.
- Repeated variables inside a clause are allowed.
- Coordinates are zero-based with `y` increasing downward.
- `R` is described as rising to the right from the crossover.
- One proven rectangular crossover block is emitted per adjacent swap.
- Crossover blocks are adjacent; their implicit forwarder triangles are not
  stored as metadata.
- Two explicit forwarder columns remain before and after the crossover chain.
- The builder colors only exposed region sides, never internal cell edges.
- The produced Yang–Zhang region has the paper's clause staircase and every
  exposed unit side is colored.
- The result owns the exact generated swap array; solver correctness does not
  depend on it.
- Construction is transactional and leaves no partial public output.
