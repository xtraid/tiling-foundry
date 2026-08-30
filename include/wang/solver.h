#ifndef WANG_SOLVER_H
#define WANG_SOLVER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "wang/region.h"

/* Canonical public domain containing every atomic tile ID. */
#define WANG_DOMAIN_ALL \
    ((UINT32_C(1) << TILE_COUNT) - UINT32_C(1))

typedef enum {
    WANG_SOLVE_ERROR = -1,
    WANG_SOLVE_UNSAT = 0,
    WANG_SOLVE_SAT = 1
} WangSolveStatus;

enum {
    WANG_SOLVE_COLLECT_METRICS = UINT32_C(1) << 0,
    WANG_SOLVE_TRACE_FAILED_LEAVES = UINT32_C(1) << 1,
    WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT = UINT32_C(1) << 2
};

typedef struct {
    uint64_t dfs_nodes;
    uint64_t decisions;
    uint64_t backtracks;
    uint64_t failed_leaves;
    uint64_t domain_reductions;
    uint64_t propagated_arcs;
    uint64_t support_tile_visits;
    uint64_t support_byte_lookups;
    size_t support_table_bytes;
    uint64_t mrv_cells_scanned;
    uint64_t mrv_index_word_probes;
    size_t mrv_index_bytes;
    uint64_t initial_trail_writes;
    uint64_t search_trail_writes;
    uint64_t initial_trail_rewrites;
    uint64_t search_trail_rewrites;
    size_t trail_peak;
    size_t trail_capacity_peak;
    size_t trail_bytes_peak;
    uint64_t enqueue_attempts;
    uint64_t duplicate_enqueue_attempts;
    size_t queue_dedup_index_bytes;
    size_t queue_peak;
    size_t queue_unique_peak;
    size_t dfs_stack_capacity_peak;
    size_t dfs_stack_bytes_peak;
    size_t max_depth;
    size_t sat_result_copy_bytes;
} WangSolverMetrics;

typedef struct {
    uint32_t flags;

    /*
     * Required only with WANG_SOLVE_TRACE_FAILED_LEAVES. Incomplete trace
     * output is removed if the writer fails after creating the path.
     */
    const char *failed_leaf_path;
    size_t failed_leaf_capacity;

    /*
     * Optional borrowed dense row-major root domains, parallel to
     * Region.cells. Absence is exactly NULL/0; presence requires a non-NULL
     * pointer and initial_domain_count == region->cell_count. The solver
     * reads this array only for the duration of the call and never modifies,
     * stores, or frees it.
     *
     * Entries may use only bits in WANG_DOMAIN_ALL. Inactive cells require
     * zero. Active cells accept any subset: zero is a well-formed
     * contradiction (UNSAT), while WANG_DOMAIN_ALL adds no restriction.
     */
    const uint32_t *initial_domains;
    size_t initial_domain_count;
} WangSolverOptions;

typedef struct {
    /*
     * Dense row-major domain snapshot, one uint32_t per RegionCell.
     * SAT always contains singleton domains for every active cell. UNSAT
     * contains the best failed leaf only when
     * WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT was requested; otherwise domains is
     * NULL and domain_count is zero.
     */
    uint32_t *domains;
    size_t domain_count;

    /* SIZE_MAX for SAT; the zero-domain active cell for UNSAT. */
    size_t conflict_cell;
    size_t resolved_count;
    size_t decision_depth;

    size_t traced_leaf_count;
    bool trace_truncated;

    /* Zeroed unless WANG_SOLVE_COLLECT_METRICS was requested. */
    WangSolverMetrics metrics;
} WangSolveResult;

/*
 * Solve a finite Wang region using the canonical TILESET.
 *
 * options may be NULL. out_result must be zero-initialized or destroyed.
 * On SAT, and on UNSAT when snapshot capture was requested, the caller owns
 * out_result->domains. On UNSAT without capture, domains is NULL. With a
 * conforming zero-initialized or destroyed output, ERROR leaves it destroyed;
 * an already-owned output is invalid and is rejected unchanged.
 */
WangSolveStatus wang_solve_serial(
    const Region *region,
    const WangSolverOptions *options,
    WangSolveResult *out_result
);

/*
 * Solve through the performance path.
 *
 * This entry point has the same input, ownership, diagnostics, and result
 * contract as wang_solve_serial(). Optimized mechanisms remain private and
 * must preserve the finite Wang constraints and independent SAT verification.
 */
WangSolveStatus wang_solve_optimized(
    const Region *region,
    const WangSolverOptions *options,
    WangSolveResult *out_result
);

/* Release the owned snapshot and reset every field. Accepts NULL. */
void wang_solve_result_destroy(WangSolveResult *result);

#endif /* WANG_SOLVER_H */
