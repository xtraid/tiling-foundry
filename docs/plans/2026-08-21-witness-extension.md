# Witness Extension Implementation Plan

**Status:** completed and verified on 21 August 2026

Use one responsible implementation agent per task when practical and an
independent reviewer for the complete diff. The unchecked boxes below preserve
the original execution plan; they are not the current completion record. The
status above and the verification evidence in the canonical project documents
are authoritative. No particular agent framework or optional skill is a
prerequisite for executing this plan.

**Goal:** Compute and verify the correspondence between each Boolean assignment and the Wang tilings that extend it, while keeping the generic Wang solver independent from Yang–Zhang semantics.

**Architecture:** Add optional borrowed dense initial domains to the shared native solver core. Build a stateless C bridge over `Cm13Formula + YangZhangReduction` that pins only variable-gadget tiles, verifies/extracts Wang witnesses, and never evaluates Boolean clauses or reads the swap trace. Add a narrow Python cross-check coordinator that keeps native lifetimes scoped while connecting Boolean Z3, the native bridge, and the existing independent Python checkers.

**Tech Stack:** C17, canonical 23-tile bitmask domains, native reference and optimized solvers, Python 3.13, ctypes, Z3, `uv`, Make, GCC/Clang, sanitizers, GCC analyzer, Valgrind.

**Spec:** `docs/designs/2026-08-21-witness-extension-design.md`

## Global Constraints

- Read `/home/manuel/AGENTS.md`, this plan, the spec, `README.md`, and `docs/development_principles.md` before editing.
- Preserve all pre-existing user work. Stop and reassess if the worktree differs from the documented clean `67ff34f` baseline except for this task's spec and plan.
- Do not commit or push without explicit user authorization. Every commit step below is conditional and otherwise leaves the reviewed changes uncommitted.
- Keep `wang_solve_serial()` and `wang_solve_optimized()` generic: no formula, assignment, signal, gadget, crossover, or Yang–Zhang knowledge may enter `solver.h` or `solver_serial.c`.
- Initial-domain inputs are borrowed and immutable. Malformed masks are `WANG_SOLVE_ERROR`; legal contradictory masks are `WANG_SOLVE_UNSAT`.
- The bridge borrows `YangZhangReduction`, uses only `reduction.region`, and never reads or copies `reduction.swaps`.
- Extension never calls a Boolean checker. Extraction verifies the Wang tiling and decodes variable gadgets but never decides whether the decoded assignment satisfies the formula.
- External tests alone assert `is_valid_assignment(F, a) == (extension_status == SAT)` and retain any mismatch as a counterexample.
- Do not add `SignalPlan`, provenance metadata, reverse marshalling, a copied swap trace, or new persistent formula/region/assignment/tiling models.
- Preserve distinct ERROR, UNSAT, SAT, and Boolean UNKNOWN outcomes and all existing result ownership and cleanup behavior.
- Use TDD for every task: observe the focused test fail for the expected reason before adding production behavior.

## File Map

- Modify `include/wang/solver.h`: public all-tiles mask and optional borrowed initial-domain fields.
- Modify `src/solver/solver_serial.c`: complete initial-domain validation and shared initialization intersection.
- Modify `tests/c/test_solver.c`: focused public-contract tests for initial domains.
- Modify `tests/c/test_solver_differential.c`: reference/optimized/brute-force parity under restrictions.
- Create `include/wang/yang_zhang_witness.h`: stateless extension, extraction, and correspondence contracts.
- Create `src/crosscheck/yang_zhang_witness.c`: assignment-to-domain translation and Wang-witness decoding above the solver and verifier modules.
- Create `tests/c/test_yang_zhang_witness.c`: focused bridge tests and exhaustive witness equivalence.
- Modify `Makefile`: compile the new native bridge source through serial and shared builds.
- Modify `python/native/region_adapter.py`: scoped native-reduction lifetime helper reused by coordinators.
- Create `python/native/witness_adapter.py`: ctypes-only bridge/result adaptation; no Z3 or clause logic.
- Create `python/crosscheck/witness_pipeline.py`: Boolean Z3/native Wang orchestration and independent checks.
- Create `tests/python/test_witness_pipeline.py`: forward and reverse end-to-end witness paths and lifetime failures.
- Modify `README.md`, `docs/development_principles.md`, `docs/serial_solver_implementation_guide.md`, and `docs/reduction_notes.md`: implemented boundary, contracts, evidence, and limitations.

---

### Task 1: Generic Borrowed Initial Domains

**Files:**
- Modify: `include/wang/solver.h`
- Modify: `src/solver/solver_serial.c`
- Modify: `tests/c/test_solver.c`
- Modify: `tests/c/test_solver_differential.c`

**Interfaces:**
- Consumes: existing `Region`, `TILE_COUNT`, `WangSolverOptions`, `wang_solve_serial()`, and `wang_solve_optimized()`.
- Produces: public `WANG_DOMAIN_ALL`; `WangSolverOptions.initial_domains`; `WangSolverOptions.initial_domain_count`; identical constrained semantics through both solver entry points.

- [ ] **Step 1: Add focused failing public-contract tests**

Add a `SolveFunction` helper in `tests/c/test_solver.c` and run every case through both public entry points. The tests must exercise these exact masks and outcomes:

```c
static void assert_initial_domain_contract(SolveFunction solve)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 2, 1));
    assert(region_set_active(&region, 0, 0, true));

    uint32_t domains[] = {
        UINT32_C(1) << TILE_F0,
        0,
    };
    const WangSolverOptions constrained = {
        .initial_domains = domains,
        .initial_domain_count = 2,
    };
    assert(solve(&region, &constrained, &result) == WANG_SOLVE_SAT);
    assert(result.domains[0] == (UINT32_C(1) << TILE_F0));
    assert(domains[0] == (UINT32_C(1) << TILE_F0));
    assert(domains[1] == 0);
    wang_solve_result_destroy(&result);

    domains[0] = 0;
    assert(solve(&region, &constrained, &result) == WANG_SOLVE_UNSAT);
    wang_solve_result_destroy(&result);

    domains[0] = WANG_DOMAIN_ALL;
    domains[1] = UINT32_C(1) << TILE_F0;
    assert(solve(&region, &constrained, &result) == WANG_SOLVE_ERROR);
    assert(result.domains == NULL && result.domain_count == 0);

    region_destroy(&region);
}
```

Add separate assertions for `(NULL, nonzero)`, `(nonnull, 0)`, a count unequal to `region.cell_count`, a bit above `WANG_DOMAIN_ALL`, a later malformed mask following an earlier active zero, boundary incompatibility as UNSAT, an isolated cell restricted by a multi-bit mask, empty active mask plus all-zero dense input, root trace/snapshot behavior, and unchanged unconstrained deterministic output.

- [ ] **Step 2: Run the focused test and confirm the red state**

Run:

```sh
make build/tests/c/test_solver
```

Expected: compilation fails because `WANG_DOMAIN_ALL`, `initial_domains`, and `initial_domain_count` are not public yet. No production source should have been changed before observing this failure.

- [ ] **Step 3: Expose the minimal generic API**

In `include/wang/solver.h`, move the canonical domain mask out of the private implementation and extend the existing options without a new flag:

```c
#define WANG_DOMAIN_ALL \
    ((UINT32_C(1) << TILE_COUNT) - UINT32_C(1))

typedef struct {
    uint32_t flags;
    const char *failed_leaf_path;
    size_t failed_leaf_capacity;

    /* Optional borrowed dense row-major root domains. */
    const uint32_t *initial_domains;
    size_t initial_domain_count;
} WangSolverOptions;
```

Document the exact absent/present pairs, dense alignment, valid bits, inactive-zero invariant, active-zero UNSAT semantics, and borrowed lifetime. Remove the duplicate private macro from `solver_serial.c`.

- [ ] **Step 4: Validate the complete domain array before solving**

Add a shared helper in `solver_serial.c` after `region_validate()` and before solver-state allocation:

```c
static bool initial_domains_are_valid(
    const Region *region,
    const WangSolverOptions *options
)
{
    if (options == NULL) {
        return true;
    }
    if (options->initial_domains == NULL) {
        return options->initial_domain_count == 0;
    }
    if (options->initial_domain_count != region->cell_count) {
        return false;
    }
    for (size_t i = 0; i < region->cell_count; ++i) {
        const uint32_t mask = options->initial_domains[i];
        if ((mask & ~WANG_DOMAIN_ALL) != 0 ||
            (!region->cells[i].active && mask != 0)) {
            return false;
        }
    }
    return true;
}
```

Pass the borrowed pointer into initialization without storing it after the solve. For each active cell initialize with the supplied mask when present, otherwise `WANG_DOMAIN_ALL`, then apply boundary masks exactly as today. Count one effective initial restriction in `domain_reductions`; do not create trail entries. Preserve inactive result domain zero and the isolated-cell lowest-allowed-tile rule.

- [ ] **Step 5: Run focused solver tests and confirm green behavior**

Run:

```sh
make build/tests/c/test_solver
build/tests/c/test_solver
```

Expected: `test_solver: OK`. Existing unconstrained snapshots and metric assertions remain unchanged; all new contract cases pass through both entry points.

- [ ] **Step 6: Add constrained brute-force and differential tests**

Change the two-cell brute-force helper in `tests/c/test_solver_differential.c` to reject tile IDs excluded by each initial mask before calling `wang_verify_tiling()`:

```c
static bool brute_force_two_cells(
    const Region *region,
    const uint32_t domains[2]
)
{
    TileId tiles[2];
    for (tiles[0] = 0; tiles[0] < TILE_COUNT; ++tiles[0]) {
        if ((domains[0] & (UINT32_C(1) << tiles[0])) == 0) {
            continue;
        }
        for (tiles[1] = 0; tiles[1] < TILE_COUNT; ++tiles[1]) {
            if ((domains[1] & (UINT32_C(1) << tiles[1])) == 0) {
                continue;
            }
            if (wang_verify_tiling(region, tiles, 2) == WANG_VERIFY_VALID) {
                return true;
            }
        }
    }
    return false;
}
```

Enumerate deterministic singleton, multi-bit, zero, and pseudo-random legal masks. Give reference and optimized solvers distinct options structs pointing to identical mask values, assert both statuses equal brute force, verify every SAT witness, and `memcmp` the borrowed arrays before/after each call.

- [ ] **Step 7: Run the complete native semantic gate for Task 1**

Run:

```sh
make c-check
make strict-check
```

Expected: every C test prints `OK`; strict build completes without warnings. Re-run `git diff --check` and confirm no build output is tracked.

- [ ] **Step 8: Conditional local commit gate**

If and only if the user explicitly authorizes a local commit:

```sh
git add include/wang/solver.h src/solver/solver_serial.c \
  tests/c/test_solver.c tests/c/test_solver_differential.c
git commit -m "Add generic initial domains to Wang solving"
```

Otherwise record Task 1 as locally verified and continue without committing.

---

### Task 2: Stateless Yang–Zhang Witness Bridge

**Files:**
- Create: `include/wang/yang_zhang_witness.h`
- Create: `src/crosscheck/yang_zhang_witness.c`
- Create: `tests/c/test_yang_zhang_witness.c`
- Modify: `Makefile`

**Interfaces:**
- Consumes: Task 1's `WANG_DOMAIN_ALL` and initial-domain options; `Cm13Formula`; `YangZhangReduction`; canonical tile IDs; both native solver entry points; `wang_verify_tiling()`.
- Produces: `YangZhangWitnessStatus`; `YangZhangExtensionSolver`; `yang_zhang_solve_assignment_extension()` returning `WangSolveStatus`; `yang_zhang_extract_assignment()` and `yang_zhang_witnesses_correspond()` returning tri-state witness status.

- [ ] **Step 1: Write failing focused bridge tests against the public contract**

Create `tests/c/test_yang_zhang_witness.c` and include the not-yet-existing header. Begin with one SAT formula, one satisfying assignment, and one invalid assignment:

```c
static void test_extension_extracts_the_requested_assignment(void)
{
    Cm13Clause clauses[] = {
        { .variable_index = { 0, 0, 1 } },
        { .variable_index = { 0, 1, 2 } },
        { .variable_index = { 1, 2, 2 } },
    };
    Cm13Formula formula = {
        .variable_count = 3,
        .clauses = clauses,
        .clause_count = 3,
    };
    const bool satisfying[] = { false, true, false };
    const bool invalid[] = { false, false, false };
    YangZhangReduction reduction = {0};
    WangSolveResult result = {0};

    assert(yang_zhang_build(&formula, &reduction));
    assert(yang_zhang_solve_assignment_extension(
        &formula, &reduction, satisfying, 3,
        YANG_ZHANG_EXTENSION_REFERENCE, &result
    ) == WANG_SOLVE_SAT);
    wang_solve_result_destroy(&result);
    assert(yang_zhang_solve_assignment_extension(
        &formula, &reduction, invalid, 3,
        YANG_ZHANG_EXTENSION_REFERENCE, &result
    ) == WANG_SOLVE_UNSAT);
    wang_solve_result_destroy(&result);
    yang_zhang_reduction_destroy(&reduction);
}
```

Add tests for assignment length, destroyed/malformed reduction, untouched extraction output on NO/ERROR, exact V0/V1 atomic patterns, invalid tiling, mismatched valid assignment, both solver selectors, and proof that `reduction.swaps` is neither required nor modified.

- [ ] **Step 2: Run the bridge test and confirm the red state**

Run:

```sh
make build/tests/c/test_yang_zhang_witness
```

Expected: compilation fails because `wang/yang_zhang_witness.h` and its symbols do not exist.

- [ ] **Step 3: Define the small public bridge API**

Create `include/wang/yang_zhang_witness.h` with no owned persistent object:

```c
typedef enum {
    YANG_ZHANG_WITNESS_ERROR = -1,
    YANG_ZHANG_WITNESS_NO = 0,
    YANG_ZHANG_WITNESS_YES = 1
} YangZhangWitnessStatus;

typedef enum {
    YANG_ZHANG_EXTENSION_REFERENCE = 0,
    YANG_ZHANG_EXTENSION_OPTIMIZED = 1
} YangZhangExtensionSolver;

WangSolveStatus yang_zhang_solve_assignment_extension(
    const Cm13Formula *formula,
    const YangZhangReduction *reduction,
    const bool *assignment,
    size_t assignment_count,
    YangZhangExtensionSolver solver,
    WangSolveResult *out_result
);

YangZhangWitnessStatus yang_zhang_extract_assignment(
    const Cm13Formula *formula,
    const YangZhangReduction *reduction,
    const TileId *tiling,
    size_t tiling_count,
    bool *out_assignment,
    size_t assignment_count
);

YangZhangWitnessStatus yang_zhang_witnesses_correspond(
    const Cm13Formula *formula,
    const YangZhangReduction *reduction,
    const bool *assignment,
    size_t assignment_count,
    const TileId *tiling,
    size_t tiling_count
);
```

Document that the formula/reduction provenance is a precondition, `swaps` is ignored, extension never evaluates clauses, extraction never evaluates clauses, and NO remains distinct from ERROR.

- [ ] **Step 4: Implement assignment masks and extension minimally**

In `src/crosscheck/yang_zhang_witness.c`, validate only safe storage and detectable layout metadata, allocate `region.cell_count` masks, write zero for inactive cells and `WANG_DOMAIN_ALL` for other active cells, then replace the three variable entries with singleton masks:

```c
const TileId false_tiles[3] = {
    TILE_V0_TOP, TILE_V0_MID, TILE_V0_BOTTOM
};
for (uint32_t v = 0; v < formula->variable_count; ++v) {
    for (int32_t row = 0; row < 3; ++row) {
        const size_t index = region_index(&reduction->region, 0,
            (int32_t)(4u * v) + row);
        const TileId tile = assignment[v] ? TILE_V1 : false_tiles[row];
        domains[index] = UINT32_C(1) << tile;
    }
}
```

Call the selected generic solver with these masks and always free the temporary
mask storage before returning. Preserve the solver's SAT/UNSAT result and its
existing ownership contract. Do not call extraction or correspondence inside
the extension operation: the external proof harness must independently
normalize, verify, extract, and compare the returned SAT witness so any
mismatch remains available as a counterexample instead of being destroyed and
collapsed into ERROR.

- [ ] **Step 5: Implement extraction and correspondence without Boolean validity**

Extraction first requires `wang_verify_tiling()` to accept the dense tiling. Decode only these exact triples:

```c
if (top == TILE_V0_TOP && middle == TILE_V0_MID &&
    bottom == TILE_V0_BOTTOM) {
    decoded[v] = false;
} else if (top == TILE_V1 && middle == TILE_V1 &&
           bottom == TILE_V1) {
    decoded[v] = true;
} else {
    return YANG_ZHANG_WITNESS_NO;
}
```

Use a temporary Boolean array and copy into `out_assignment` only after the complete tiling and all variable blocks pass. Do not inspect clauses. Correspondence calls extraction into temporary storage and compares bits; it returns YES for equal representations even if an external Boolean checker would reject that assignment.

- [ ] **Step 6: Add the bridge source to every native build**

Add `src/crosscheck/yang_zhang_witness.c` to `SERIAL_SOURCES` in `Makefile`. Because PIC and serial object lists derive from this variable, the bridge must appear in both `libwang.a` and `libwang.so` without a second source list. Keeping it outside `src/verify` preserves the independent verifier's one-way dependency boundary.

- [ ] **Step 7: Run focused bridge tests and confirm green behavior**

Run:

```sh
make build/tests/c/test_yang_zhang_witness
build/tests/c/test_yang_zhang_witness
```

Expected: `test_yang_zhang_witness: OK`, including both solver selectors and negative tri-state cases.

- [ ] **Step 8: Add exhaustive witness equivalence**

Reuse the existing canonical formula generator through three variables. Replace the existential Boolean oracle with a per-assignment checker that counts all three clause positions:

```c
static bool assignment_is_valid(
    const Cm13Formula *formula,
    uint32_t bits
)
{
    for (size_t c = 0; c < formula->clause_count; ++c) {
        unsigned true_count = 0;
        for (size_t p = 0; p < 3; ++p) {
            const uint32_t v = formula->clauses[c].variable_index[p];
            true_count += (bits >> v) & UINT32_C(1);
        }
        if (true_count != 1) {
            return false;
        }
    }
    return true;
}
```

For all 1,701 generated formulas, materialize every one of the `2^n` assignments, run both extension selectors, and assert direct validity equals SAT. For SAT, verify the tiling, extract exact equality, and require correspondence YES. Keep corrupted gadget-pattern and different-valid-assignment checks on focused fixtures outside the exhaustive inner loop.

If a SAT postcondition fails, print or otherwise retain the complete formula,
requested assignment bits, solver selector, and dense returned tiling before
destroying the result. A generic ERROR without the witness is not sufficient
counterexample evidence.

- [ ] **Step 9: Run and time the native exhaustive gate**

Run:

```sh
/usr/bin/time -f 'elapsed=%E maxrss=%MKiB' \
  build/tests/c/test_yang_zhang_witness
make c-check
```

Expected: all 1,701 formulas and assignments pass for reference and optimized solvers; the full C suite remains practical. If runtime under instrumentation is material, preserve the full normal gate and document a focused instrumentation subset instead of silently reducing logical coverage.

- [ ] **Step 10: Conditional local commit gate**

If and only if the user explicitly authorizes a local commit:

```sh
git add include/wang/yang_zhang_witness.h \
  src/crosscheck/yang_zhang_witness.c tests/c/test_yang_zhang_witness.c Makefile
git commit -m "Connect Boolean and Wang witnesses"
```

Otherwise record Task 2 as locally verified and continue without committing.

---

### Task 3: Python Z3-to-Native Witness Pipeline

**Files:**
- Modify: `python/native/region_adapter.py`
- Create: `python/native/witness_adapter.py`
- Create: `python/crosscheck/witness_pipeline.py`
- Create: `tests/python/test_witness_pipeline.py`

**Interfaces:**
- Consumes: existing `_loaded_formula()`, `_copy_formula()`, native region copy logic, Boolean Z3 result/checker, Python tiling checker, and Task 2's C bridge.
- Produces: scoped `_built_reduction()`; ctypes-only bridge calls; high-level `solve_boolean_native_extension(path, optimized=False)`, `solve_native_and_extract(path, optimized=False)`, and `extract_wang_assignment(path, tiling)` returning only existing immutable models, enums, tuples, and `None` where their current contracts allow it.

- [ ] **Step 1: Write failing end-to-end Python tests**

Create `tests/python/test_witness_pipeline.py` with the required forward path:

```python
def test_boolean_z3_assignment_extends_through_native_reference(self) -> None:
    formula, region, boolean_result, wang_result = (
        solve_boolean_native_extension(SAT_PATH, optimized=False)
    )
    self.assertEqual(boolean_result.status, BooleanSolveStatus.SAT)
    self.assertIsNotNone(boolean_result.assignment)
    self.assertTrue(is_valid_assignment(formula, boolean_result.assignment))
    self.assertIsNotNone(wang_result)
    self.assertEqual(wang_result.status, TilingSolveStatus.SAT)
    self.assertIsNotNone(wang_result.tiling)
    self.assertTrue(is_valid_tiling(region, TILESET, wang_result.tiling))
    extracted = extract_wang_assignment(SAT_PATH, wang_result.tiling)
    self.assertEqual(extracted, boolean_result.assignment)
```

Add the optimized forward path, direct extraction from reference/optimized native tilings, Wang Z3 tiling extraction, repeated clause positions, UNSAT without witness, a controlled Boolean UNKNOWN that proves native extension is not called, C ERROR propagation, invalid tiling as a negative witness, and cleanup after injected copy/bridge failures.

- [ ] **Step 2: Run the Python test and confirm the red state**

Run:

```sh
make shared
PYTHONPATH=python uv run --frozen python -m unittest discover \
  -s tests/python -p 'test_witness_pipeline.py'
```

Expected: import failure for `crosscheck.witness_pipeline` or missing bridge bindings.

- [ ] **Step 3: Factor a scoped native reduction lifetime**

In `python/native/region_adapter.py`, add a private context manager and make the existing `_build_region()` use it:

```python
@contextmanager
def _built_reduction(
    native_formula: _Cm13Formula,
) -> Iterator[_YangZhangReduction]:
    reduction = _YangZhangReduction()
    lib = _region_library()
    try:
        if not lib.yang_zhang_build(byref(native_formula), byref(reduction)):
            raise RegionBuildError("could not build Yang–Zhang region")
        yield reduction
    finally:
        lib.yang_zhang_reduction_destroy(byref(reduction))
```

No public ctypes object may escape. Retain destruction order reduction then formula.

- [ ] **Step 4: Add ctypes-only witness adaptation**

In `python/native/witness_adapter.py`, declare the exact C enum values and complete ctypes layouts needed for `WangSolveResult`, including all 26 ordered fields of `WangSolverMetrics`, plus the complete `WangSolverOptions` layout used by the unpinned native path; bind the bridge and generic-solver functions with cached `argtypes`/`restype`. Keep all pointer-bearing helpers private. Convert SAT singleton domains into the existing dense Python tiling convention:

```python
tiling = tuple(
    None if not region.active[index]
    else (int(domain).bit_length() - 1)
    for index, domain in enumerate(native_domains)
)
```

Reject zero or non-singleton active SAT domains as an internal native error. Always call `wang_solve_result_destroy()` in `finally`, including native ERROR and malformed-SAT paths. Map native ERROR or an unknown enum value to `NativeWitnessError`, SAT/UNSAT to the existing `TilingSolveStatus`, and preserve absence of a tiling for UNSAT. Witness ERROR likewise raises `NativeWitnessError`; witness NO returns `None` (or `False` for correspondence), and YES returns the copied tuple (or `True`).

For extraction in the opposite direction, first validate the complete Python
sequence and convert active integer tile IDs directly while mapping every
inactive `None` to native `TILE_NONE`. Reject booleans, missing inactive
sentinels, out-of-range IDs, and wrong lengths before calling C. The temporary
native tile array remains scoped to the adapter call.

- [ ] **Step 5: Implement the high-level lifetime coordinator**

In `python/crosscheck/witness_pipeline.py`, keep all native work under nested contexts:

```python
with _loaded_formula(path) as native_formula:
    formula = _copy_formula(native_formula)
    with _built_reduction(native_formula) as native_reduction:
        region = _copy_region(native_reduction.region)
        boolean_result = solve_boolean(formula)
        if boolean_result.status is not BooleanSolveStatus.SAT:
            return formula, region, boolean_result, None
        wang_result = _solve_assignment_extension(
            native_formula,
            native_reduction,
            boolean_result.assignment,
            optimized=optimized,
        )
        return formula, region, boolean_result, wang_result
```

The coordinator then runs the existing Python Boolean and tiling checkers but must not use their result to rewrite the C status. A mismatch raises `WitnessCrosscheckError` carrying at least the Boolean assignment, returned tiling, and extracted assignment, so the counterexample is not discarded. The reverse helper rebuilds the same native reduction under the path lifetime, passes the normalized Python tiling to C extraction, copies the decoded tuple, closes native lifetimes, and only then lets callers run `is_valid_assignment()`. `solve_native_and_extract()` calls the selected native solver without initial domains while the same reduction is alive, copies its tiling, invokes the C extraction bridge, and returns `(Formula, Region, TilingSolveResult, tuple[bool, ...] | None)` for the external Python Boolean check. `extract_wang_assignment()` returns `None` only for witness NO; malformed Python storage raises `ValueError` and a native operation error raises `NativeWitnessError`.

- [ ] **Step 6: Run focused and complete Python suites**

Run:

```sh
make shared
PYTHONPATH=python uv run --frozen python -m unittest discover \
  -s tests/python -p 'test_witness_pipeline.py'
make python-check
```

Expected: focused tests pass for Boolean Z3→reference, Boolean Z3→optimized, native/Wang Z3→Boolean extraction, UNKNOWN, UNSAT, error, and cleanup paths; all existing Python tests remain green.

- [ ] **Step 7: Check dependency direction and forbidden marshalling**

Run:

```sh
rg -n 'ctypes|CDLL|POINTER|byref' python/model python/oracles
rg -n 'Cm13Formula|_Cm13Formula|Region\(' python/crosscheck
rg -n '\.swaps|swap_count' python/native/witness_adapter.py python/crosscheck
```

Expected: no ctypes imports in models/oracles, no Python-to-C formula or region construction in the coordinator, and no bridge consumer of the swap trace. The existing `_YangZhangReduction` ctypes layout still declares `swaps` and `swap_count` for ABI fidelity, but witness code never reads or copies them. Native pointer types occur only under `python/native` and scoped private imports used by the coordinator.

- [ ] **Step 8: Conditional local commit gate**

If and only if the user explicitly authorizes a local commit:

```sh
git add python/native/region_adapter.py python/native/witness_adapter.py \
  python/crosscheck/witness_pipeline.py tests/python/test_witness_pipeline.py
git commit -m "Add end-to-end witness cross-validation"
```

Otherwise record Task 3 as locally verified and continue without committing.

---

### Task 4: Canonical Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/development_principles.md`
- Modify: `docs/serial_solver_implementation_guide.md`
- Modify: `docs/reduction_notes.md`
- Retain: `docs/designs/2026-08-21-witness-extension-design.md`
- Retain: `docs/plans/2026-08-21-witness-extension.md`

**Interfaces:**
- Consumes: verified behavior and measured test costs from Tasks 1–3.
- Produces: canonical documentation that distinguishes decision agreement, individual witness validity, witness extension/extraction, non-uniqueness, and remaining OpenMP work.

- [ ] **Step 1: Write documentation assertions that currently fail**

Before editing prose, use searches as executable documentation checks:

```sh
rg -n 'initial_domains|witness extension|extract.*assignment' \
  README.md docs/development_principles.md \
  docs/serial_solver_implementation_guide.md docs/reduction_notes.md
```

Expected: the canonical documents do not yet describe all three implemented contracts.

- [ ] **Step 2: Update canonical project documentation**

Document these exact distinctions:

```text
decision agreement:
    independent solvers agree on SAT/UNSAT

witness extension:
    direct Boolean validity(a) == native Wang SAT under variable pins(a)

witness extraction:
    verified tiling -> decoded assignment -> external Boolean checker

not claimed:
    uniqueness of tilings or extend(extract(t)) == t
```

Add `initial_domains` ownership/status semantics to the solver guide, the bridge and `python/crosscheck` dependency boundaries to development principles, the witness-level reduction evidence to reduction notes, and the completed milestone before OpenMP in README. Do not rewrite the historical architecture PDF.

- [ ] **Step 3: Run formatting, artifact, and secret checks**

Run:

```sh
git diff --check
find . -maxdepth 3 -type f \( -name '*.out' -o -name '*.log' \
  -o -name 'vgcore.*' \) -print
git status --short
```

Expected: no whitespace errors, profiler/log debris, or unexpected tracked files. Inspect the complete diff for secrets, accidental binaries, generated captures, and unrelated edits.

- [ ] **Step 4: Run the complete standard gate from a clean build**

Run:

```sh
make clean
make check
```

Expected: all C tests, OpenMP scaffold build, Python tests, native benchmark smoke, and cross-solver smoke pass.

- [ ] **Step 5: Run compiler and dynamic-analysis gates**

Run each independently, rebuilding as required by the Makefile:

```sh
make strict-check
make clean && make c-check shared openmp \
  CFLAGS='-std=c17 -Wall -Wextra -Wpedantic -Werror -O2' CC=clang
make sanitizer-check
make analyzer-check
make valgrind-check
make cachegrind-check
```

Expected: strict GCC and Clang, ASan/UBSan/LSan, GCC analyzer, Memcheck, and Cachegrind complete without errors. If the full exhaustive witness binary is unreasonably slow under instrumentation, record exact timings and run a documented focused instrumentation case while retaining exhaustive normal execution.

- [ ] **Step 6: Run final proof-harness checks**

Run:

```sh
make build/tests/c/test_yang_zhang_witness shared
build/tests/c/test_yang_zhang_witness
PYTHONPATH=python uv run --frozen python -m unittest discover \
  -s tests/python -p 'test_witness_pipeline.py'
git diff --check
git status --short --branch
```

Expected: exhaustive native witness equivalence and real Z3/native pipelines pass; the worktree contains only reviewed task files and no `build/` is tracked.

- [ ] **Step 7: Request code review and resolve findings**

Assign an independent reviewer over the complete diff, following
`/home/manuel/AGENTS.md`. Review specifically generic-solver purity,
ERROR/UNSAT boundaries, the cross-check bridge's separation from the verifier,
extraction's refusal to evaluate clauses, non-use of swaps, lifetime cleanup,
exhaustive counterexample visibility, and documentation claims. Apply accepted
fixes one at a time and rerun their focused tests plus the final proof-harness
checks.

- [ ] **Step 8: Conditional final local commit gate**

If and only if the user explicitly authorizes local commits, stage the reviewed documentation, spec, plan, and any remaining implementation files not already committed, then commit with a result-oriented public subject:

```sh
git add README.md docs/development_principles.md \
  docs/serial_solver_implementation_guide.md docs/reduction_notes.md \
  docs/designs/2026-08-21-witness-extension-design.md \
  docs/plans/2026-08-21-witness-extension.md include/wang/solver.h \
  include/wang/yang_zhang_witness.h src/solver/solver_serial.c \
  src/crosscheck/yang_zhang_witness.c python/native/region_adapter.py \
  python/native/witness_adapter.py python/crosscheck/witness_pipeline.py \
  tests/c/test_solver.c tests/c/test_solver_differential.c \
  tests/c/test_yang_zhang_witness.c \
  tests/python/test_witness_pipeline.py Makefile
git commit -m "Verify Boolean and Wang witness correspondence"
```

Do not add a coauthor trailer. Do not push, tag, create a release, or open a PR without separate authorization.
