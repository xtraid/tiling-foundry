---
layout: page
title: Boolean–Wang witness correspondence
permalink: /witness_correspondence/
description: How exact Boolean assignments are extended to Wang tilings and extracted again without coupling the generic solver to reduction semantics.
section: Architecture and correctness
document_kind: Technical design
status: Current implementation
updated: 2026-08-25
nav_order: 30
---

# Boolean–Wang witness correspondence

## 1. Purpose and authoritative scope

This page is the implementation design for exact correspondence between
Boolean assignments and Wang tilings of one concrete Yang–Zhang reduction. It
defines the native bridge, its use of generic initial domains, the Python
lifetime coordinator, and the evidence boundary.

The path has two directions:

```text
specific Boolean assignment -> concrete Wang tiling -> Wang verifier
specific Wang tiling        -> Boolean assignment -> formula checker
```

Decision-level agreement and independent validation of whichever models the
solvers prefer are related but weaker checks. This design connects a specific
assignment to a specific extension without moving Yang–Zhang semantics into
the generic solver.

Exact C declarations live in `wang/solver.h` and
`wang/yang_zhang_witness.h`. The
[serial solver reference]({{ '/serial_solver_implementation_guide/' | relative_url }})
is authoritative for the reusable initial-domain, result-ownership, trace, and
diagnostic contracts.

## 2. Correspondence claim and limits

The implementation distinguishes three claims:

```text
decision agreement:
    independent solvers agree on SAT/UNSAT

witness extension:
    Boolean validity(a) == native Wang SAT with variable pins(a)

witness extraction:
    verified Wang tiling -> decoded assignment -> external Boolean checker
```

Let `F` be a validated Cubic Monotone 1-in-3 SAT formula and `R` the exact
`Region` produced from `F` by `yang_zhang_build()` under the current layout and
canonical `TILESET`. For every well-formed assignment `a` of length
`F.variable_count`:

```text
is_valid_assignment(F, a)
    iff
solve_assignment_extension(F, R, a) returns WANG_SOLVE_SAT.
```

When extension returns SAT, its dense singleton domains must yield a tiling
`t` satisfying:

```text
wang_verify_tiling(R, t) == WANG_VERIFY_VALID
extract(F, R, t) == a
correspond(F, R, a, t) == true.
```

For every verified tiling `t`, extraction returns the value encoded by its
variable gadgets. The caller then applies the independent Boolean checker.
Extraction preserves a decoded value that fails that later check so the pair
remains observable as a reduction counterexample.

Extraction is a left inverse of assignment extension for the tested domain.
This is not a bijection claim. Multiple tilings may encode one satisfying
assignment, and extending an assignment extracted from a tiling need not
reproduce the original tiling byte for byte. Independent solvers also need not
choose the same satisfying model without an explicit assignment restriction.

The claims do not cover OpenMP, square-to-hex translation, rendering, solution
serialization, or unrelated solver optimization.

## 3. Layering and dependency boundary

The implementation has three layers:

| Layer | Responsibility | Boundary |
| --- | --- | --- |
| Generic C solver | Borrow optional dense root domains and solve ordinary Wang constraints through either serial entry point | Knows only `Region`, tile masks, and Wang semantics |
| Native Yang–Zhang bridge | Translate an assignment into variable-cell masks; extract an assignment from a verified tiling; compare the two representations | Alone knows variable-gadget coordinates and tile IDs; reads `reduction.region`, not `reduction.swaps` |
| Python coordinator | Keep one native formula/reduction lifetime open while composing Boolean Z3, bridge calls, native solving, copy-out, and pure checkers | Does not reproduce gadget, routing, clause, or solver logic |

The bridge owns no persistent object. It uses borrowed inputs, temporary dense
arrays, and transactional caller-provided outputs. The generic solver never
calls back into the bridge.

No `SignalPlan`, gadget map, witness-pair model, copied swap trace, or reverse
marshalling is needed. The variable cells already encode the assignment, and
the region boundary plus canonical tileset determine the remaining gadgets.
Occurrence tokens and swaps remain native builder diagnostics and are
destroyed with the reduction.

## 4. Formula/reduction provenance

Every bridge operation requires the reduction to be the successful
`yang_zhang_build()` result for the exact supplied formula, current canonical
tileset, and layout constants. Accepting `YangZhangReduction` rather than an
arbitrary `Region` represents that precondition without adding persistent
provenance metadata.

The bridge still rejects detectable inconsistencies: invalid formula or region
storage, impossible dimensions, wrong dense lengths, and malformed
variable-gadget coordinates. It does not reconstruct the full reduction to
prove the origin of an independently supplied region. A same-sized but
unrelated formula/reduction pair violates the documented precondition.

The production coordinator satisfies provenance structurally. It parses once,
builds from that live native formula, and keeps both objects alive for every
bridge call.

## 5. Generic initial domains

`WangSolverOptions` exposes an optional borrowed dense array:

```c
const uint32_t *initial_domains;
size_t initial_domain_count;
```

Absence is exactly `NULL/0`. Presence requires a non-null pointer and
`initial_domain_count == region->cell_count`. The array is immutable,
row-major, and parallel to `Region.cells`. The solver copies or intersects its
values into private state and never stores, frees, or modifies caller storage.

The low `TILE_COUNT` bits, exposed publicly as `WANG_DOMAIN_ALL`, are the legal
tile universe. Inactive entries are zero. On active cells,
`WANG_DOMAIN_ALL` is unrestricted, a nonzero subset restricts candidates, and
zero is a well-formed contradiction. Bits outside the universe and nonzero
inactive entries are malformed input.

The solver validates the complete pointer/count pair and every mask before it
interprets an active zero as UNSAT. A malformed later entry therefore cannot
be hidden by an earlier contradiction. Active initialization is:

```text
WANG_DOMAIN_ALL
    & optional caller root domain
    & all exposed boundary-color masks
```

Initial domains are root constraints. They do not bypass region validation,
oriented adjacency, propagation, search, final independent verification,
trace handling, or result ownership. A legal contradiction is UNSAT; malformed
input, infrastructure failure, or rejection of an internal SAT candidate is
ERROR. Both public solver entry points implement the same contract.

## 6. Native witness bridge

The public operations are:

- `yang_zhang_solve_assignment_extension()`;
- `yang_zhang_extract_assignment()`;
- `yang_zhang_witnesses_correspond()`.

### 6.1 Assignment extension

A well-formed assignment has exactly `formula.variable_count` Boolean values.
After validating storage and detectable provenance metadata, the bridge
allocates one mask per `RegionCell`:

- inactive cell: `0`;
- unrestricted active cell: `WANG_DOMAIN_ALL`;
- false variable `v`: `(0, 4v)`, `(0, 4v + 1)`, and `(0, 4v + 2)` are fixed
  respectively to `TILE_V0_TOP`, `TILE_V0_MID`, and `TILE_V0_BOTTOM`;
- true variable `v`: the same three cells are fixed to `TILE_V1`.

These are the only reduction-specific restrictions. Forwarders, anchors,
crossovers, redundant rows, and clause gadgets remain consequences of the
region boundary, tileset, propagation, and search.

The bridge does not evaluate the assignment against the formula. A well-formed
but non-satisfying assignment is not an API error. The bridge runs the selected
reference or optimized Wang solver and returns its status. It does not add a
Yang–Zhang mode to `WangSolverOptions`, short-circuit through a Boolean checker,
or return SAT without the generic solve and its mandatory witness verification.

On SAT, extension returns the original `WangSolveResult`. It does not call
extraction or correspondence. The external harness normalizes the singleton
domains, verifies the tiling, extracts the assignment, and checks equality.
This keeps the forward path from confirming itself and preserves a mismatching
SAT result as counterexample data.

### 6.2 Tiling extraction

Extraction accepts a dense tiling aligned with the region. It validates the
length and requires `wang_verify_tiling()` to accept the complete witness
before reading variable cells. Each leftmost-column variable block decodes as:

- exact `V0_TOP`, `V0_MID`, `V0_BOTTOM`: false;
- exact `V1`, `V1`, `V1`: true;
- every other mixture: no decoded witness.

The output contains exactly `formula.variable_count` Boolean values. It is
written only after the complete tiling and every variable block succeed.
Extraction does not evaluate clauses or call the Boolean checker. That checker
later examines all three ordered clause positions, including repeats.

Extraction reads no search history, nonsingleton domains, swap trace, or signal
tokens. It therefore applies to normalized reference-native,
optimized-native, and Wang Z3 tilings.

### 6.3 Representation predicate

`yang_zhang_witnesses_correspond()` verifies the tiling, extracts its value,
and compares that value with the supplied assignment. It is a representation
relation, not a clause-validity check or a comparison with a solver's preferred
model.

Its tri-state result preserves these distinctions:

| Outcome | Meaning |
| --- | --- |
| `ERROR` | Malformed storage, invalid detectable metadata, detectable provenance failure, or allocation failure |
| `NO` | Invalid or undecodable tiling, or two well-formed representations of different assignments |
| `YES` | Verified tiling whose decoded assignment equals the supplied assignment, regardless of later Boolean validity |

No operation error is collapsed into a positive or negative relation. For
extraction, a structurally well-formed tiling rejected by the verifier produces
no assignment. For correspondence, the same rejection is a normal negative
relation rather than an infrastructure error.

## 7. Python lifetime coordinator

The Python path composes existing models and statuses without reverse
marshalling:

```text
.cm13
  |
  v
native parse -----------------------------------------------+
  |                                                         |
  +-> copy immutable Formula -> Boolean Z3 -> assignment    |
  |                                               |         |
  +-> build and retain native YangZhangReduction  |         |
                                                  v         |
                                      native witness bridge  |
                                                  |         |
                                 selected generic solver     |
                                                  |         |
                                      copied dense tiling     |
                                                  |         |
                                  extract and compare <------+
```

The coordinator:

1. loads the native formula once and copies the immutable Python `Formula`;
2. builds the reduction from that same live formula;
3. copies the immutable Python `Region` when a Python consumer needs it;
4. calls Boolean Z3 and, on SAT, passes the exact Boolean tuple to the bridge;
5. selects reference or optimized native solving explicitly;
6. copies active tile IDs and inactive `None` values into the existing dense
   Python tiling convention;
7. applies the independent Python Boolean and Wang checkers;
8. destroys the reduction and then the formula through `finally` cleanup.

No ctypes pointer escapes. Narrow adapters return existing enums and immutable
tuples rather than a persistent aggregate model. They do not copy swaps,
reconstruct tokens, calculate gadget coordinates, or implement clause
semantics.

Boolean UNKNOWN is propagated with no tiling and no native extension call.
Native ERROR and UNSAT remain distinct from each other and from Boolean
UNKNOWN. The reverse path extracts from a normalized native or Wang Z3 tiling
under the same provenance lifetime; it does not ask Boolean Z3 to rediscover an
assignment.

## 8. Ownership and status summary

- Assignment, tiling, formula, reduction, and caller initial-domain inputs are
  borrowed and immutable.
- Temporary bridge masks and decoded arrays are freed before return.
- Extension preserves the generic `WangSolveResult` ownership contract.
- Native result buffers are destroyed after complete Python copy-out, including
  every error path.
- A non-satisfying assignment or legal restriction with no extension is
  UNSAT. Invalid lengths, masks, regions, tiling storage, allocations, or
  internal SAT postconditions are errors.
- Extraction output is transactional. Boolean validity is checked later and
  never suppresses a decoded counterexample.
- A valid tiling representing another assignment is a normal negative
  correspondence result.
- Python cleanup always releases the reduction before the formula.

## 9. Verification evidence

### 9.1 Generic solver contract

Both `wang_solve_serial()` and `wang_solve_optimized()` are tested with absent,
singleton, multi-bit, zero, and malformed initial domains. Tests cover strict
pointer/count pairs, illegal high bits, inactive entries, complete validation
before UNSAT interpretation, boundary and neighbor contradictions, empty
regions, diagnostics, result ownership, and unchanged borrowed storage.

Randomized small generic regions compare both solvers with brute force under
the same legal masks. Every SAT result passes the independent verifier. The
[serial solver reference]({{ '/serial_solver_implementation_guide/' | relative_url }})
contains the exhaustive public-contract catalogue.

### 9.2 Exhaustive small witness equivalence

The primary witness-level evidence enumerates all 1,701 canonical formulas
through three variables and all `2^n` assignments for each formula. Both
native solver entry points are exercised, for 27,044 constrained solves.

For each assignment and solver, the suite:

1. computes direct Boolean witness validity;
2. requires extension to be SAT exactly for a valid assignment and UNSAT
   otherwise;
3. normalizes and independently verifies every SAT tiling;
4. extracts the assignment and requires exact equality with the input;
5. requires the representation predicate to return YES.

Focused fixtures corrupt every variable-block pattern and require
transactional rejection. Multi-witness fixtures pair a tiling with a different
valid assignment and require a normal negative correspondence result. Any
failed SAT postcondition retains the formula, requested assignment, solver
selector, and returned tiling before cleanup.

This is computational evidence for the tested domain, not a general proof.
It is stronger than one decision comparison per formula and avoids ambiguity
from independently chosen models.

### 9.3 End-to-end and regression gates

End-to-end tests cover:

- Boolean Z3 SAT assignment through reference and optimized native extension,
  C verification, Python tiling checking, exact extraction, and Python Boolean
  checking;
- unconstrained reference and optimized native tilings through extraction and
  the Boolean checker;
- Wang Z3 tilings through native extraction and the Boolean checker;
- shared UNSAT fixtures without witnesses;
- Boolean UNKNOWN without a native extension call;
- parser, bridge, solver, copy-out, and verifier failures with both native
  lifetimes released;
- positional counting of repeated variables such as `(x, x, y)`.

The implementation passed the C and Python suites, strict GCC and Clang,
sanitizers, static analysis, Memcheck, and relevant Cachegrind and differential
gates. The standard comparison benchmark measures decisions and performance;
witness-extension timing is outside its published baselines.

## 10. Related authoritative documents

- The [architecture reference]({{ '/development_principles/' | relative_url }})
  defines module ownership and dependency direction.
- The [serial solver reference]({{ '/serial_solver_implementation_guide/' | relative_url }})
  defines initial domains, statuses, diagnostics, and result ownership.
- The [reduction note]({{ '/reduction_notes/' | relative_url }}) records the
  mathematical/project convention boundary and witness-level evidence.
- This page defines the bridge and coordinator contract.

The Yang–Zhang paper is authoritative for the reduction. The
[initial architecture specification]({{ '/historical_architecture/' | relative_url }})
is retained as design history rather than current API documentation.
