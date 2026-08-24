---
layout: page
title: Architecture and ownership boundaries
permalink: /development_principles/
description: How Tiling Foundry separates source data, derived state, native lifetimes, solvers, and independent verification.
section: Architecture and correctness
document_kind: Architecture reference
status: Current implementation
updated: 2026-08-24
nav_order: 10
---

# Architecture and ownership boundaries

Tiling Foundry separates mathematical construction, native search, independent
verification, Python reference models, and cross-check orchestration. This page
explains those boundaries and the ownership rules that make the resulting
pipeline auditable.

The [initial architecture PDF]({{ '/historical_architecture/' | relative_url }})
records the project’s broader starting point. Public headers and tests remain
authoritative for implemented behavior.

## Core rule

Prefer the smallest representation that preserves the required invariants.

- Every allocation and mutable datum has one clear owner.
- Consumers borrow data unless ownership transfer is explicit.
- Derived data is computed when needed until profiling justifies caching it.
- A new struct represents an object with its own state or lifetime, not a group
  of temporary outputs.
- Future metadata is added only when a concrete consumer exists.
- Correctness and module boundaries take priority over optimization.

## Module boundaries

| Module | Owns or defines | Must not own |
| --- | --- | --- |
| `tile` | Fixed tileset, colors, local matching | Search state |
| `permutation` | Signal tokens and adjacent-swap generation | Region geometry |
| `region` | Active cells and boundary constraints | Solver domains or scheduling |
| `yang_zhang` | Reduction-specific construction and the transferred swap trace | Solver state or duplicated permutation data |
| `verify` | No persistent state; reads a candidate tiling | Search logic |
| `solver` | Domains, trail, assignments, search state | Reduction semantics |
| `crosscheck` | Stateless Boolean/Wang witness translation over a live reduction | Generic solver internals, clause validity, or copied swap data |
| `task_plan` | Future OpenMP dependencies | Region or serial solver ownership |
| `python/model` | Pure immutable Python data contracts | I/O, ctypes, Z3, or native ownership |
| `python/native` | C ABI adaptation, native lifetimes, complete copy-out | Solver logic or leaked native pointers |
| `python/crosscheck` | Scoped orchestration of native adapters, Z3, and independent checkers | Persistent native state or duplicated reduction semantics |
| `python/oracles` | Independent solver or verifier logic over pure models | Parsing, filesystem I/O, or reduction construction |

The renderer and JSON layer remain downstream from construction, solving, and
verification. They do not decide correctness.

## Python ownership and oracle boundaries

The current Python layer contains immutable `Formula`, `Region`, and atomic
tileset models; independent Boolean and Wang witness checkers; implemented
Boolean and Wang Z3 solvers; tested native formula, region, and witness adapters
over `libwang.so`; and a narrow cross-check coordinator. The native consumers
share one private library loader. A reduction context parses once, keeps the
native formula and Yang–Zhang reduction alive for bridge calls, and copies only
fully Python-owned values out.

Dependencies flow in one direction:

```text
                    C parser + Yang–Zhang builder
                                |
                                v
                            libwang.so
                                |
                                v
             native adapters + crosscheck coordinator
                    /              |              \
                   v               v               v
          model/formula.py   witness_adapter   model/region.py
             /        \             |             /       \
            v          v            v            v         v
 boolean_solver  witness_check  native bridge  tiling_solver  tiling_check
```

Forbidden dependencies are equally explicit:

```text
boolean_solver.py  -X-> native/formula_adapter.py, ctypes, filesystem
witness_check.py   -X-> Z3, ctypes, C ABI
tiling_solver.py   -X-> native adapters, ctypes, filesystem, formula semantics
tiling_check.py    -X-> Z3, native adapters, ctypes, C ABI
model/formula.py   -X-> ctypes, CDLL, filesystem, Z3
model/region.py    -X-> ctypes, CDLL, filesystem, Z3
model/tileset.py   -X-> ctypes, CDLL, filesystem, Z3
```

The native adapter is an ownership boundary. It must copy the complete C
formula, including all three ordered positions of every clause, into Python
storage and release the C allocation in a `finally` block. No ctypes pointer
may escape. The C API exposes both `cm13_formula_parse(FILE *, ...)` for native
callers and `cm13_formula_load_path(...)` as the robust external entry point;
the Python adapter must use the latter and never bind a C `FILE *`.

Do not marshal `Formula` back into `Cm13Formula`. The implemented cross-check
coordinator parses once and branches while the native formula and reduction
are alive:

```text
                          .cm13
                            |
                            v
                       C parser
                            |
                       Cm13Formula C
                       /           \
                      /             \
                     v               v
             copy Formula Py    Yang–Zhang builder
                     |               |
                     v               v
             Boolean Z3           Region C
                     |               |
                     v               +------------------+
                assignment                              |
                     |                                  |
                     +------> native witness bridge <---+
                                      |
                                      v
                               native Wang solver
                                      |
                         Region copy + tiling copy
                             /                  \
                            v                    v
                    Python checkers         Wang Z3 oracle
```

The coordinator must use `finally` cleanup to destroy the C reduction and then
the C formula after the required copies and native operations finish.
Both returned Python models are fully Python-owned.

`native/region_adapter.py` copies `Region C` into a pure Python region,
`native/_lib.py` centralizes lazy loading of the shared `libwang.so`, and
`native/reduction_adapter.py` coordinates the copy-only formula/region path,
while `crosscheck/witness_pipeline.py` keeps the same native lifetime open for
witness calls. The reduction's swap trace remains native-only because no Python
consumer needs it.

There are two distinct oracle contracts:

- Boolean Z3 (implemented): `Formula -> Boolean constraints ->
  SAT/UNSAT/UNKNOWN` and an assignment only for SAT. It performs no parsing,
  I/O, ctypes work, region construction, or reduction.
- Wang Z3 (implemented): `Region + TILESET -> per-cell edge-table constraints
  with shared internal edge terms -> SAT/UNSAT/UNKNOWN` and a dense tiling only
  for SAT. It receives the same concrete region as the native solver and does
  not rebuild Yang–Zhang. For generic duplicate edge tuples, witness recovery
  returns a valid positional tile ID from the constraint-equivalent entries;
  the public contract does not select one duplicate over another.

The Boolean witness checker remains pure Python and counts clause positions,
not unique variables: `(x, x, y)` counts `x` twice. The Wang checker separately
validates dense storage, boundaries, and both adjacency orientations without
importing Z3. Verifiers never depend on the solver they check. Reverse
marshalling and further model layers remain forbidden until concrete consumers
justify them.

## Witness correspondence boundary

The implemented witness path has three deliberately separate claims:

```text
decision agreement:
    independent solvers agree on SAT/UNSAT

witness extension:
    Boolean validity(a) == native Wang SAT with variable pins(a)

witness extraction:
    verified Wang tiling -> decoded assignment -> external Boolean checker
```

The generic solver owns only reusable dense initial domains and never sees a
formula, assignment, gadget, or Yang–Zhang layout. The native cross-check bridge
alone knows the three variable-cell coordinates and V0/V1 tile IDs. It borrows
the exact live builder result, ignores `reduction.swaps`, and neither extension
nor extraction evaluates clauses. Python coordinates the Boolean Z3 result,
native bridge, and pure checkers without reconstructing C models or letting a
ctypes pointer escape.

The correspondence is not a bijection claim. Multiple Wang tilings may encode
the same satisfying assignment, and solving after extraction need not reproduce
the original tiling byte for byte. A mismatch remains a copied counterexample;
it is not rewritten as another solver status.

## Region representation

The implemented `Region` stores only source-of-truth geometry:

- bounding width and height;
- whether each dense row-major cell is active;
- boundary color constraints for active cells.

The representation omits derived or consumer-specific state:

- per-cell `x` and `y`, because they are derived from the row-major index;
- cached neighbor indices, because they are derived from geometry;
- a cached `active_count`;
- `zone_id` or other OpenMP metadata;
- tile domains, assignments, gadget types, or signal plans.

The verifier and solver derive neighbor indices from dense geometry. Scheduling
metadata, if introduced for a concrete parallel executor, belongs to a separate
preprocessing result rather than `Region`.

The generic representation may describe disconnected regions or regions with
holes. The Yang–Zhang builder is responsible for producing the required simply
connected instances, and its tests must verify that property.

## Implemented dependency order

1. Minimal `Region` storage, lifetime, access, and boundary tests (complete).
2. Canonical Cubic Monotone 1-in-3 SAT representation, strict text parser,
   validation, and formula-to-region Yang–Zhang builder (complete).
3. Independent verifier exercised on hand-built regions and tilings
   (complete).
4. Correct deterministic serial solver; every witness passes the verifier
   (complete).
5. Solver-level regression tests for the explicit forwarder bands, atomic
   anchor/crossover gadgets, whole crossover blocks, composed chains,
   deterministic fuzz cases, and large volumes (complete).
6. Z3 Boolean and Wang cross-checks on shared SAT/UNSAT instances, independent
   Python witness checks, and the Python region ownership boundary (complete).
7. Exact Boolean/Wang witness extension and extraction with exhaustive small
   assignment-level equivalence (complete).
8. OpenMP planning only after the serial solver is stable and profiled.
9. Square-to-hex verification, JSON, and rendering after the square core.

Private compatibility masks now have a concrete consumer in the serial solver
and remain derived from `TILESET`. `TaskPlan`, zone ownership, diagnostic IR,
and renderer schemas remain deferred until a preceding module provides a real
use case.

## Module completeness criteria

A module is implemented when it has:

- a small documented public contract, if a public API is needed;
- explicit ownership and failure behavior;
- an implementation included in the build;
- focused unit tests for invariants and invalid input;
- at least one integration test with the preceding implemented module;
- no dependency on unimplemented future layers.

Placeholder files may remain to preserve repository continuity. Their presence
does not imply implementation, and they must not drive premature API design.

## When to add an abstraction

Add an abstraction when it removes duplicated behavior from real consumers,
enforces an otherwise fragile invariant, or owns a resource with a distinct
lifetime. Do not add one solely because it appears in the target architecture.

Performance-oriented state is introduced only with a benchmark or profile that
can show whether the added complexity helps.
