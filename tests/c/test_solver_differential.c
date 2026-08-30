#define _POSIX_C_SOURCE 200809L

#include "wang/solver.h"

#include "wang/tile.h"
#include "wang/verify.h"
#include "wang/yang_zhang.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef WangSolveStatus (*SolveFunction)(
    const Region *,
    const WangSolverOptions *,
    WangSolveResult *
);

static void activate_all(Region *region)
{
    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            assert(region_set_active(region, x, y, true));
        }
    }
}

static void assert_sat_witness(
    const Region *region,
    const WangSolveResult *result
)
{
    assert(result->domains != NULL);
    assert(result->domain_count == region->cell_count);
    assert(result->conflict_cell == SIZE_MAX);

    TileId *tiles = malloc(result->domain_count * sizeof(*tiles));
    assert(tiles != NULL);

    size_t active_count = 0;
    for (size_t i = 0; i < result->domain_count; ++i) {
        uint32_t domain = result->domains[i];
        if (!region->cells[i].active) {
            assert(domain == 0);
            tiles[i] = TILE_NONE;
            continue;
        }

        ++active_count;
        assert(domain != 0 && (domain & (domain - UINT32_C(1))) == 0);
        TileId tile = 0;
        while ((domain & UINT32_C(1)) == 0) {
            domain >>= 1;
            ++tile;
        }
        assert(tile < TILE_COUNT);
        tiles[i] = tile;
    }

    assert(result->resolved_count == active_count);
    assert(wang_verify_tiling(
        region,
        tiles,
        result->domain_count
    ) == WANG_VERIFY_VALID);
    free(tiles);
}

static void assert_unsat_result(
    const Region *region,
    const WangSolverOptions *options,
    const WangSolveResult *result
)
{
    const bool capture = options != NULL &&
        (options->flags & WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT) != 0;
    const bool trace = options != NULL &&
        (options->flags & WANG_SOLVE_TRACE_FAILED_LEAVES) != 0;

    assert(result->conflict_cell < region->cell_count);
    assert(region->cells[result->conflict_cell].active);
    if (capture) {
        assert(result->domains != NULL);
        assert(result->domain_count == region->cell_count);
        assert(result->domains[result->conflict_cell] == 0);
    } else {
        assert(result->domains == NULL);
        assert(result->domain_count == 0);
    }
    if (trace) {
        assert(result->traced_leaf_count > 0);
        assert(result->traced_leaf_count <= options->failed_leaf_capacity);
    } else {
        assert(result->traced_leaf_count == 0);
        assert(!result->trace_truncated);
    }
    if (options != NULL &&
        (options->flags & WANG_SOLVE_COLLECT_METRICS) != 0) {
        assert(result->metrics.sat_result_copy_bytes == 0);
    }
}

static void assert_semantic_pair(
    const Region *region,
    const WangSolverOptions *reference_options,
    const WangSolverOptions *optimized_options,
    WangSolveStatus expected,
    WangSolverMetrics *out_reference_metrics,
    WangSolverMetrics *out_optimized_metrics
)
{
    const size_t region_bytes =
        region->cell_count * sizeof(*region->cells);
    RegionCell *original = malloc(region_bytes);
    assert(original != NULL);
    memcpy(original, region->cells, region_bytes);

    WangSolveResult reference = {0};
    WangSolveResult optimized = {0};
    const WangSolveStatus reference_status = wang_solve_serial(
        region,
        reference_options,
        &reference
    );
    assert(memcmp(original, region->cells, region_bytes) == 0);

    const WangSolveStatus optimized_status = wang_solve_optimized(
        region,
        optimized_options,
        &optimized
    );
    assert(memcmp(original, region->cells, region_bytes) == 0);
    assert(reference_status == expected);
    assert(optimized_status == expected);

    const WangSolverMetrics zero_metrics = {0};
    if (reference_options == NULL ||
        (reference_options->flags & WANG_SOLVE_COLLECT_METRICS) == 0) {
        assert(memcmp(
            &reference.metrics,
            &zero_metrics,
            sizeof(zero_metrics)
        ) == 0);
    }
    if (optimized_options == NULL ||
        (optimized_options->flags & WANG_SOLVE_COLLECT_METRICS) == 0) {
        assert(memcmp(
            &optimized.metrics,
            &zero_metrics,
            sizeof(zero_metrics)
        ) == 0);
    }

    if (expected == WANG_SOLVE_SAT) {
        assert_sat_witness(region, &reference);
        assert_sat_witness(region, &optimized);
    } else {
        assert(expected == WANG_SOLVE_UNSAT);
        assert_unsat_result(region, reference_options, &reference);
        assert_unsat_result(region, optimized_options, &optimized);
    }

    if (out_reference_metrics != NULL) {
        *out_reference_metrics = reference.metrics;
    }
    if (out_optimized_metrics != NULL) {
        *out_optimized_metrics = optimized.metrics;
    }

    wang_solve_result_destroy(&reference);
    wang_solve_result_destroy(&optimized);
    free(original);
}

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

static void test_generic_boundary_matrix_against_brute_force(void)
{
    static const ColorId colors[] = {
        COLOR_0,
        COLOR_1,
        COLOR_V,
        COLOR_0_PRIME,
    };

    bool saw_initial_propagation_conflict = false;
    for (size_t west = 0; west < 4; ++west) {
        for (size_t east = 0; east < 4; ++east) {
            Region region = {0};
            assert(region_init(&region, 2, 1));
            activate_all(&region);
            assert(region_set_boundary(&region, 0, 0, N, COLOR_B));
            assert(region_set_boundary(&region, 1, 0, N, COLOR_B));
            assert(region_set_boundary(&region, 0, 0, S, COLOR_B));
            assert(region_set_boundary(&region, 1, 0, S, COLOR_B));
            assert(region_set_boundary(&region, 0, 0, W, colors[west]));
            assert(region_set_boundary(&region, 1, 0, E, colors[east]));

            const uint32_t domains[2] = {
                WANG_DOMAIN_ALL,
                WANG_DOMAIN_ALL,
            };
            const WangSolveStatus expected = brute_force_two_cells(
                &region,
                domains
            )
                ? WANG_SOLVE_SAT
                : WANG_SOLVE_UNSAT;
            const WangSolverOptions capture = {
                .flags = WANG_SOLVE_COLLECT_METRICS |
                    WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT,
            };
            const WangSolverOptions *options =
                expected == WANG_SOLVE_UNSAT ? &capture : NULL;
            WangSolverMetrics reference_metrics = {0};
            WangSolverMetrics optimized_metrics = {0};
            assert_semantic_pair(
                &region,
                options,
                options,
                expected,
                &reference_metrics,
                &optimized_metrics
            );
            if (expected == WANG_SOLVE_UNSAT &&
                reference_metrics.initial_trail_writes > 0) {
                assert(reference_metrics.dfs_nodes == 0);
                assert(optimized_metrics.dfs_nodes == 0);
                assert(optimized_metrics.initial_trail_writes == 0);
                assert(optimized_metrics.trail_capacity_peak == 0);
                saw_initial_propagation_conflict = true;
            }
            region_destroy(&region);
        }
    }
    assert(saw_initial_propagation_conflict);
}

static void assert_constrained_two_cell_case(
    const Region *region,
    const uint32_t domains[2]
)
{
    uint32_t reference_domains[2];
    uint32_t optimized_domains[2];
    uint32_t original_domains[2];
    memcpy(reference_domains, domains, sizeof(reference_domains));
    memcpy(optimized_domains, domains, sizeof(optimized_domains));
    memcpy(original_domains, domains, sizeof(original_domains));

    const WangSolverOptions reference_options = {
        .initial_domains = reference_domains,
        .initial_domain_count = 2,
    };
    const WangSolverOptions optimized_options = {
        .initial_domains = optimized_domains,
        .initial_domain_count = 2,
    };
    WangSolveResult reference = {0};
    WangSolveResult optimized = {0};
    const WangSolveStatus expected = brute_force_two_cells(region, domains)
        ? WANG_SOLVE_SAT
        : WANG_SOLVE_UNSAT;

    assert(wang_solve_serial(
        region,
        &reference_options,
        &reference
    ) == expected);
    assert(memcmp(
        reference_domains,
        original_domains,
        sizeof(reference_domains)
    ) == 0);
    assert(wang_solve_optimized(
        region,
        &optimized_options,
        &optimized
    ) == expected);
    assert(memcmp(
        optimized_domains,
        original_domains,
        sizeof(optimized_domains)
    ) == 0);

    if (expected == WANG_SOLVE_SAT) {
        assert_sat_witness(region, &reference);
        assert_sat_witness(region, &optimized);
        assert((reference.domains[0] & domains[0]) != 0);
        assert((reference.domains[1] & domains[1]) != 0);
        assert((optimized.domains[0] & domains[0]) != 0);
        assert((optimized.domains[1] & domains[1]) != 0);
    } else {
        assert_unsat_result(region, &reference_options, &reference);
        assert_unsat_result(region, &optimized_options, &optimized);
    }

    wang_solve_result_destroy(&reference);
    wang_solve_result_destroy(&optimized);
}

static uint32_t next_random(uint32_t *state)
{
    *state = *state * UINT32_C(1664525) + UINT32_C(1013904223);
    return *state;
}

static void test_initial_domains_against_brute_force(void)
{
    Region region = {0};
    assert(region_init(&region, 2, 1));
    activate_all(&region);

    static const uint32_t deterministic[][2] = {
        {
            UINT32_C(1) << TILE_F0,
            UINT32_C(1) << TILE_F0,
        },
        {
            UINT32_C(1) << TILE_F0,
            UINT32_C(1) << TILE_F1,
        },
        {
            (UINT32_C(1) << TILE_F0) | (UINT32_C(1) << TILE_F1),
            UINT32_C(1) << TILE_F1,
        },
        { 0, WANG_DOMAIN_ALL },
        { WANG_DOMAIN_ALL, WANG_DOMAIN_ALL },
    };
    for (size_t i = 0;
         i < sizeof(deterministic) / sizeof(deterministic[0]);
         ++i) {
        assert_constrained_two_cell_case(&region, deterministic[i]);
    }

    uint32_t random_state = UINT32_C(0x6d2b79f5);
    for (size_t sample = 0; sample < 256; ++sample) {
        uint32_t domains[2];
        for (size_t cell = 0; cell < 2; ++cell) {
            const uint32_t first = next_random(&random_state) % TILE_COUNT;
            const uint32_t second = next_random(&random_state) % TILE_COUNT;
            domains[cell] = (UINT32_C(1) << first) |
                (UINT32_C(1) << second);
            if ((sample + cell) % 17u == 0) {
                domains[cell] = 0;
            } else if ((sample + cell) % 13u == 0) {
                domains[cell] = WANG_DOMAIN_ALL;
            }
        }
        assert_constrained_two_cell_case(&region, domains);
    }

    region_destroy(&region);
}

static void test_generic_backtracking_case(void)
{
    Region region = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    assert(region_init(&region, 4, 4));
    activate_all(&region);
    assert(region_set_boundary(&region, 1, 0, N, COLOR_R));
    assert(region_set_boundary(&region, 2, 3, S, COLOR_B));
    assert(region_set_boundary(&region, 0, 3, W, COLOR_1));
    assert(region_set_boundary(&region, 3, 1, E, COLOR_1));
    assert(region_set_boundary(&region, 3, 3, E, COLOR_0));

    assert_semantic_pair(
        &region,
        NULL,
        NULL,
        WANG_SOLVE_SAT,
        NULL,
        NULL
    );

    WangSolverMetrics reference_metrics = {0};
    WangSolverMetrics optimized_metrics = {0};
    assert_semantic_pair(
        &region,
        &options,
        &options,
        WANG_SOLVE_SAT,
        &reference_metrics,
        &optimized_metrics
    );
    assert(reference_metrics.backtracks > 0);
    assert(optimized_metrics.backtracks == reference_metrics.backtracks);
    assert(reference_metrics.mrv_index_word_probes == 0);
    assert(reference_metrics.mrv_index_bytes == 0);
    assert(reference_metrics.mrv_cells_scanned == 83);
    assert(optimized_metrics.mrv_index_word_probes == 7);
    assert(optimized_metrics.mrv_index_bytes == 192);
    assert(optimized_metrics.mrv_cells_scanned == 22);
    assert(reference_metrics.initial_trail_writes > 0);
    assert(optimized_metrics.initial_trail_writes == 0);
    assert(reference_metrics.search_trail_writes > 0);
    assert(optimized_metrics.search_trail_writes ==
           reference_metrics.search_trail_writes);
    assert(optimized_metrics.domain_reductions ==
           reference_metrics.domain_reductions);
    assert(reference_metrics.enqueue_attempts == 138);
    assert(optimized_metrics.enqueue_attempts ==
           reference_metrics.enqueue_attempts);
    assert(reference_metrics.duplicate_enqueue_attempts == 43);
    assert(optimized_metrics.duplicate_enqueue_attempts == 31);
    assert(reference_metrics.queue_unique_peak == 16);
    assert(reference_metrics.queue_dedup_index_bytes == 0);
    assert(optimized_metrics.queue_dedup_index_bytes ==
           ((region.cell_count + 63u) / 64u) * sizeof(uint64_t));
    assert(optimized_metrics.queue_peak ==
           optimized_metrics.queue_unique_peak);
    assert(optimized_metrics.queue_peak < reference_metrics.queue_peak);
    assert(optimized_metrics.propagated_arcs == 323);
    assert(optimized_metrics.propagated_arcs <
           reference_metrics.propagated_arcs);
    assert(optimized_metrics.enqueue_attempts -
           optimized_metrics.duplicate_enqueue_attempts >
           region.cell_count);
    assert(reference_metrics.initial_trail_rewrites == 31);
    assert(optimized_metrics.initial_trail_rewrites == 0);
    assert(reference_metrics.search_trail_rewrites == 13);
    assert(optimized_metrics.search_trail_rewrites ==
           reference_metrics.search_trail_rewrites);
    assert(reference_metrics.sat_result_copy_bytes ==
           region.cell_count * sizeof(uint32_t));
    assert(optimized_metrics.sat_result_copy_bytes == 0);

    char reference_path[] = "/tmp/wang-reference-sat-ownership-XXXXXX";
    char optimized_path[] = "/tmp/wang-optimized-sat-ownership-XXXXXX";
    int fd = mkstemp(reference_path);
    assert(fd >= 0);
    assert(close(fd) == 0);
    assert(unlink(reference_path) == 0);
    fd = mkstemp(optimized_path);
    assert(fd >= 0);
    assert(close(fd) == 0);
    assert(unlink(optimized_path) == 0);

    const WangSolverOptions reference_diagnostics = {
        .flags = WANG_SOLVE_COLLECT_METRICS |
            WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT |
            WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = reference_path,
        .failed_leaf_capacity = 4,
    };
    const WangSolverOptions optimized_diagnostics = {
        .flags = WANG_SOLVE_COLLECT_METRICS |
            WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT |
            WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = optimized_path,
        .failed_leaf_capacity = 4,
    };
    reference_metrics = (WangSolverMetrics){0};
    optimized_metrics = (WangSolverMetrics){0};
    assert_semantic_pair(
        &region,
        &reference_diagnostics,
        &optimized_diagnostics,
        WANG_SOLVE_SAT,
        &reference_metrics,
        &optimized_metrics
    );
    assert(reference_metrics.failed_leaves > 0);
    assert(optimized_metrics.failed_leaves == reference_metrics.failed_leaves);
    assert(reference_metrics.sat_result_copy_bytes ==
           region.cell_count * sizeof(uint32_t));
    assert(optimized_metrics.sat_result_copy_bytes == 0);
    assert(access(reference_path, F_OK) == 0);
    assert(access(optimized_path, F_OK) == 0);
    assert(unlink(reference_path) == 0);
    assert(unlink(optimized_path) == 0);
    region_destroy(&region);
}

static bool boolean_oracle(const Cm13Formula *formula)
{
    const uint32_t assignment_count =
        UINT32_C(1) << formula->variable_count;
    for (uint32_t assignment = 0;
         assignment < assignment_count;
         ++assignment) {
        bool valid = true;
        for (size_t clause = 0; clause < formula->clause_count; ++clause) {
            unsigned true_count = 0;
            for (size_t position = 0; position < 3; ++position) {
                const uint32_t variable =
                    formula->clauses[clause].variable_index[position];
                true_count += (assignment >> variable) & UINT32_C(1);
            }
            if (true_count != 1) {
                valid = false;
                break;
            }
        }
        if (valid) {
            return true;
        }
    }
    return false;
}

static void assert_yang_zhang_pair(Cm13Formula *formula)
{
    YangZhangReduction reduction = {0};
    const WangSolveStatus expected = boolean_oracle(formula)
        ? WANG_SOLVE_SAT
        : WANG_SOLVE_UNSAT;
    assert(yang_zhang_build(formula, &reduction));
    assert_semantic_pair(
        &reduction.region,
        NULL,
        NULL,
        expected,
        NULL,
        NULL
    );

    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    WangSolverMetrics reference_metrics = {0};
    WangSolverMetrics optimized_metrics = {0};
    assert_semantic_pair(
        &reduction.region,
        &options,
        &options,
        expected,
        &reference_metrics,
        &optimized_metrics
    );
    if (expected == WANG_SOLVE_UNSAT &&
        optimized_metrics.dfs_nodes == 1) {
        assert(reference_metrics.mrv_index_word_probes == 0);
        assert(optimized_metrics.mrv_index_word_probes == 0);
        assert(reference_metrics.mrv_index_bytes == 0);
        assert(optimized_metrics.mrv_index_bytes == 0);
    }
    yang_zhang_reduction_destroy(&reduction);
}

static void test_yang_zhang_sat_and_unsat(void)
{
    Cm13Clause unsat_clauses[] = {
        { .variable_index = { 0, 0, 1 } },
        { .variable_index = { 0, 1, 1 } },
    };
    Cm13Formula unsat = {
        .variable_count = 2,
        .clauses = unsat_clauses,
        .clause_count = 2,
    };
    assert_yang_zhang_pair(&unsat);

    Cm13Clause sat_clauses[] = {
        { .variable_index = { 0, 0, 2 } },
        { .variable_index = { 1, 1, 2 } },
        { .variable_index = { 0, 1, 2 } },
    };
    Cm13Formula sat = {
        .variable_count = 3,
        .clauses = sat_clauses,
        .clause_count = 3,
    };
    assert_yang_zhang_pair(&sat);
}

static void test_unsat_diagnostic_modes(void)
{
    Region region = {0};
    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_V));

    assert_semantic_pair(
        &region,
        NULL,
        NULL,
        WANG_SOLVE_UNSAT,
        NULL,
        NULL
    );

    const WangSolverOptions capture = {
        .flags = WANG_SOLVE_COLLECT_METRICS |
            WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT,
    };
    WangSolverMetrics reference_metrics = {0};
    WangSolverMetrics optimized_metrics = {0};
    assert_semantic_pair(
        &region,
        &capture,
        &capture,
        WANG_SOLVE_UNSAT,
        &reference_metrics,
        &optimized_metrics
    );
    assert(reference_metrics.enqueue_attempts == 0);
    assert(optimized_metrics.enqueue_attempts == 0);
    assert(reference_metrics.queue_dedup_index_bytes == 0);
    assert(optimized_metrics.queue_dedup_index_bytes == 0);
    assert(reference_metrics.mrv_index_word_probes == 0);
    assert(optimized_metrics.mrv_index_word_probes == 0);
    assert(reference_metrics.mrv_index_bytes == 0);
    assert(optimized_metrics.mrv_index_bytes == 0);

    char reference_path[] = "/tmp/wang-reference-diff-XXXXXX";
    char optimized_path[] = "/tmp/wang-optimized-diff-XXXXXX";
    int fd = mkstemp(reference_path);
    assert(fd >= 0);
    assert(close(fd) == 0);
    assert(unlink(reference_path) == 0);
    fd = mkstemp(optimized_path);
    assert(fd >= 0);
    assert(close(fd) == 0);
    assert(unlink(optimized_path) == 0);

    const WangSolverOptions reference_trace = {
        .flags = WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = reference_path,
        .failed_leaf_capacity = 1,
    };
    const WangSolverOptions optimized_trace = {
        .flags = WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = optimized_path,
        .failed_leaf_capacity = 1,
    };
    assert_semantic_pair(
        &region,
        &reference_trace,
        &optimized_trace,
        WANG_SOLVE_UNSAT,
        NULL,
        NULL
    );
    assert(access(reference_path, F_OK) == 0);
    assert(access(optimized_path, F_OK) == 0);
    assert(unlink(reference_path) == 0);
    assert(unlink(optimized_path) == 0);
    region_destroy(&region);
}

static void test_queue_dedup_index_skips_no_arc_case(void)
{
    Region region = {0};
    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_B));
    assert(region_set_boundary(&region, 0, 0, E, COLOR_0));
    assert(region_set_boundary(&region, 0, 0, S, COLOR_B));
    assert(region_set_boundary(&region, 0, 0, W, COLOR_0));

    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    WangSolverMetrics reference_metrics = {0};
    WangSolverMetrics optimized_metrics = {0};
    assert_semantic_pair(
        &region,
        &options,
        &options,
        WANG_SOLVE_SAT,
        &reference_metrics,
        &optimized_metrics
    );
    assert(reference_metrics.enqueue_attempts == 1);
    assert(optimized_metrics.enqueue_attempts == 1);
    assert(reference_metrics.duplicate_enqueue_attempts == 0);
    assert(optimized_metrics.duplicate_enqueue_attempts == 0);
    assert(reference_metrics.queue_peak == 1);
    assert(optimized_metrics.queue_peak == 1);
    assert(reference_metrics.queue_dedup_index_bytes == 0);
    assert(optimized_metrics.queue_dedup_index_bytes == 0);
    assert(reference_metrics.mrv_index_word_probes == 0);
    assert(optimized_metrics.mrv_index_word_probes == 0);
    assert(reference_metrics.mrv_index_bytes == 0);
    assert(optimized_metrics.mrv_index_bytes == 0);

    region_destroy(&region);
}

static void assert_invalid_contract(SolveFunction solve)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 1, 1));

    assert(solve(NULL, NULL, &result) == WANG_SOLVE_ERROR);
    assert(solve(&region, NULL, NULL) == WANG_SOLVE_ERROR);

    const WangSolverOptions unknown = {
        .flags = UINT32_C(1) << 31,
    };
    assert(solve(&region, &unknown, &result) == WANG_SOLVE_ERROR);

    const WangSolverOptions missing_trace = {
        .flags = WANG_SOLVE_TRACE_FAILED_LEAVES,
    };
    assert(solve(&region, &missing_trace, &result) == WANG_SOLVE_ERROR);

    result.domain_count = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.domain_count = 0;

    result.metrics.sat_result_copy_bytes = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.sat_result_copy_bytes = 0;

    result.metrics.support_tile_visits = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.support_tile_visits = 0;

    result.metrics.support_byte_lookups = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.support_byte_lookups = 0;

    result.metrics.support_table_bytes = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.support_table_bytes = 0;

    result.metrics.mrv_index_word_probes = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.mrv_index_word_probes = 0;

    result.metrics.mrv_index_bytes = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.mrv_index_bytes = 0;

    result.metrics.enqueue_attempts = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.enqueue_attempts = 0;

    result.metrics.duplicate_enqueue_attempts = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.duplicate_enqueue_attempts = 0;

    result.metrics.queue_unique_peak = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.queue_unique_peak = 0;

    result.metrics.queue_dedup_index_bytes = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.queue_dedup_index_bytes = 0;

    result.metrics.initial_trail_rewrites = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.initial_trail_rewrites = 0;

    result.metrics.search_trail_rewrites = 1;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.metrics.search_trail_rewrites = 0;

    region.cells[0].boundary[N] = (ColorId)COLOR_COUNT;
    assert(solve(&region, NULL, &result) == WANG_SOLVE_ERROR);
    region_destroy(&region);
}

static void test_matching_invalid_input_contract(void)
{
    assert_invalid_contract(wang_solve_serial);
    assert_invalid_contract(wang_solve_optimized);
}

static void test_optimized_uses_bytewise_support_lookup(void)
{
    const int32_t width = 128;
    Region region = {0};
    assert(region_init(&region, width, 1));
    activate_all(&region);

    for (int32_t x = 0; x < width; ++x) {
        assert(region_set_boundary(&region, x, 0, N, COLOR_B));
        assert(region_set_boundary(&region, x, 0, S, COLOR_B));
    }
    assert(region_set_boundary(&region, 0, 0, W, COLOR_0));
    assert(region_set_boundary(&region, width - 1, 0, E, COLOR_0));

    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    WangSolverMetrics reference_metrics = {0};
    WangSolverMetrics optimized_metrics = {0};
    assert_semantic_pair(
        &region,
        &options,
        &options,
        WANG_SOLVE_SAT,
        &reference_metrics,
        &optimized_metrics
    );

    assert(reference_metrics.propagated_arcs > 0);
    assert(optimized_metrics.propagated_arcs > 0);
    assert(optimized_metrics.propagated_arcs <
           reference_metrics.propagated_arcs);
    assert(reference_metrics.support_tile_visits > 0);
    assert(reference_metrics.support_byte_lookups == 0);
    assert(reference_metrics.support_table_bytes == 0);
    assert(optimized_metrics.support_tile_visits == 0);
    assert(optimized_metrics.support_byte_lookups > 0);
    assert(optimized_metrics.support_table_bytes ==
           DIR_COUNT * ((TILE_COUNT + 7u) / 8u) *
           (UINT8_MAX + 1u) * sizeof(uint32_t));
    assert(optimized_metrics.support_byte_lookups <
           reference_metrics.support_tile_visits);
    assert(reference_metrics.queue_dedup_index_bytes == 0);
    assert(optimized_metrics.queue_dedup_index_bytes ==
           ((region.cell_count + 63u) / 64u) * sizeof(uint64_t));
    assert(optimized_metrics.queue_peak ==
           optimized_metrics.queue_unique_peak);
    assert(optimized_metrics.queue_peak < reference_metrics.queue_peak);

    region_destroy(&region);
}

static void test_optimized_stack_is_small_for_shallow_search(void)
{
    Cm13Clause clauses[6];
    for (uint32_t group = 0; group < 2; ++group) {
        const uint32_t first = 3u * group;
        for (uint32_t repeat = 0; repeat < 3; ++repeat) {
            clauses[3u * group + repeat] = (Cm13Clause){
                .variable_index = { first, first + 1u, first + 2u },
            };
        }
    }
    Cm13Formula formula = {
        .variable_count = 6,
        .clauses = clauses,
        .clause_count = 6,
    };
    YangZhangReduction reduction = {0};
    assert(yang_zhang_build(&formula, &reduction));

    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    WangSolveResult reference = {0};
    WangSolveResult optimized = {0};
    assert(wang_solve_serial(
        &reduction.region,
        &options,
        &reference
    ) == WANG_SOLVE_SAT);
    assert(wang_solve_optimized(
        &reduction.region,
        &options,
        &optimized
    ) == WANG_SOLVE_SAT);
    assert_sat_witness(&reduction.region, &reference);
    assert_sat_witness(&reduction.region, &optimized);

    size_t active_count = 0;
    for (size_t i = 0; i < reduction.region.cell_count; ++i) {
        active_count += reduction.region.cells[i].active ? 1u : 0u;
    }
    assert(reference.metrics.dfs_stack_capacity_peak == active_count);
    assert(reference.metrics.dfs_stack_bytes_peak > 0);
    assert(optimized.metrics.dfs_stack_capacity_peak <= 16);
    assert(optimized.metrics.dfs_stack_bytes_peak <
           reference.metrics.dfs_stack_bytes_peak);
    assert(reference.metrics.initial_trail_writes > 0);
    assert(optimized.metrics.initial_trail_writes == 0);
    assert(reference.metrics.search_trail_writes > 0);
    assert(optimized.metrics.search_trail_writes ==
           reference.metrics.search_trail_writes);
    assert(reference.metrics.domain_reductions > 0);
    assert(optimized.metrics.domain_reductions > 0);
    assert(optimized.metrics.trail_capacity_peak <
           reference.metrics.trail_capacity_peak);
    assert(optimized.metrics.trail_bytes_peak <
           reference.metrics.trail_bytes_peak);

    wang_solve_result_destroy(&reference);
    wang_solve_result_destroy(&optimized);
    yang_zhang_reduction_destroy(&reduction);
}

static void test_optimized_stack_grows_for_deep_search(void)
{
    const int32_t width = 96;
    const int32_t height = 96;
    Region region = {0};
    WangSolveResult result = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    assert(region_init(&region, width, height));
    activate_all(&region);

    assert(wang_solve_optimized(&region, &options, &result) == WANG_SOLVE_SAT);
    assert(result.metrics.max_depth > 8000);
    assert(result.metrics.dfs_stack_capacity_peak >=
           result.metrics.max_depth);
    assert(result.metrics.dfs_stack_capacity_peak <= region.cell_count);
    assert(result.metrics.dfs_stack_capacity_peak > 16);
    assert_sat_witness(&region, &result);

    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

int main(void)
{
    test_generic_boundary_matrix_against_brute_force();
    test_initial_domains_against_brute_force();
    test_generic_backtracking_case();
    test_yang_zhang_sat_and_unsat();
    test_unsat_diagnostic_modes();
    test_queue_dedup_index_skips_no_arc_case();
    test_matching_invalid_input_contract();
    test_optimized_uses_bytewise_support_lookup();
    test_optimized_stack_is_small_for_shallow_search();
    test_optimized_stack_grows_for_deep_search();

    puts("test_solver_differential: OK");
    return 0;
}
