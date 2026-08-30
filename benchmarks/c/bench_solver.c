#define _POSIX_C_SOURCE 200809L

#include "wang/solver.h"

#include "wang/formula.h"
#include "wang/formula_parser.h"
#include "wang/region.h"
#include "wang/yang_zhang.h"

#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

typedef enum {
    BENCH_GENERIC_FORCED_THIN,
    BENCH_GENERIC_RESULT_COPY,
    BENCH_GENERIC_UNCONSTRAINED,
    BENCH_GENERIC_BACKTRACKING,
    BENCH_GENERIC_ROOT_UNSAT,
    BENCH_YANG_ZHANG_SAT,
    BENCH_YANG_ZHANG_UNSAT,
    BENCH_CM13_FILE
} BenchmarkKind;

typedef enum {
    BENCH_SOLVER_ONLY,
    BENCH_END_TO_END,
    BENCH_FILE_TO_VERIFIED_DECISION
} BenchmarkScope;

typedef enum {
    BENCH_REFERENCE_SOLVER,
    BENCH_OPTIMIZED_SOLVER
} BenchmarkSolver;

typedef struct {
    const char *name;
    BenchmarkKind kind;
    BenchmarkScope scope;
    WangSolveStatus expected_status;
    size_t default_iterations;
    uint32_t variable_count;
    const char *input_path;
} BenchmarkSpec;

typedef struct {
    Region region;
    YangZhangReduction reduction;
    Cm13Formula formula;
    bool owns_region;
    bool owns_reduction;
} BenchmarkFixture;

static const BenchmarkSpec BENCHMARKS[] = {
    {
        .name = "generic_forced_thin_sat",
        .kind = BENCH_GENERIC_FORCED_THIN,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 50,
    },
    {
        .name = "generic_result_copy_sat",
        .kind = BENCH_GENERIC_RESULT_COPY,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 20,
    },
    {
        .name = "generic_unconstrained_sat",
        .kind = BENCH_GENERIC_UNCONSTRAINED,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 5,
    },
    {
        .name = "generic_backtracking_sat",
        .kind = BENCH_GENERIC_BACKTRACKING,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 5000,
    },
    {
        .name = "generic_root_unsat",
        .kind = BENCH_GENERIC_ROOT_UNSAT,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 5,
    },
    {
        .name = "yang_zhang_sat_solver",
        .kind = BENCH_YANG_ZHANG_SAT,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 20,
        .variable_count = 6,
    },
    {
        .name = "yang_zhang_unsat_solver",
        .kind = BENCH_YANG_ZHANG_UNSAT,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 50,
        .variable_count = 6,
    },
    {
        .name = "yang_zhang_sat_end_to_end",
        .kind = BENCH_YANG_ZHANG_SAT,
        .scope = BENCH_END_TO_END,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 20,
        .variable_count = 6,
    },
    {
        .name = "yang_zhang_unsat_end_to_end",
        .kind = BENCH_YANG_ZHANG_UNSAT,
        .scope = BENCH_END_TO_END,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 50,
        .variable_count = 6,
    },
    {
        .name = "yang_zhang_sat_large_solver",
        .kind = BENCH_YANG_ZHANG_SAT,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 5,
        .variable_count = 12,
    },
    {
        .name = "yang_zhang_unsat_large_solver",
        .kind = BENCH_YANG_ZHANG_UNSAT,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 10,
        .variable_count = 12,
    },
    {
        .name = "yang_zhang_sat_large_end_to_end",
        .kind = BENCH_YANG_ZHANG_SAT,
        .scope = BENCH_END_TO_END,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 5,
        .variable_count = 12,
    },
    {
        .name = "yang_zhang_unsat_large_end_to_end",
        .kind = BENCH_YANG_ZHANG_UNSAT,
        .scope = BENCH_END_TO_END,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 10,
        .variable_count = 12,
    },
    {
        .name = "pipeline_sat_solver",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 1,
        .input_path = "tests/instances/pipeline_sat.cm13",
    },
    {
        .name = "pipeline_unsat_solver",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 1,
        .input_path = "tests/instances/pipeline_unsat.cm13",
    },
    {
        .name = "pipeline_sat_file_to_verified_decision",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_FILE_TO_VERIFIED_DECISION,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 1,
        .input_path = "tests/instances/pipeline_sat.cm13",
    },
    {
        .name = "pipeline_unsat_file_to_verified_decision",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_FILE_TO_VERIFIED_DECISION,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 1,
        .input_path = "tests/instances/pipeline_unsat.cm13",
    },
    {
        .name = "yang_zhang_sat_6_file_solver",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_sat_6.cm13",
    },
    {
        .name = "yang_zhang_unsat_6_file_solver",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_unsat_6.cm13",
    },
    {
        .name = "yang_zhang_sat_6_file_to_verified_decision",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_FILE_TO_VERIFIED_DECISION,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_sat_6.cm13",
    },
    {
        .name = "yang_zhang_unsat_6_file_to_verified_decision",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_FILE_TO_VERIFIED_DECISION,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_unsat_6.cm13",
    },
    {
        .name = "yang_zhang_sat_12_file_solver",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_sat_12.cm13",
    },
    {
        .name = "yang_zhang_unsat_12_file_solver",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_SOLVER_ONLY,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_unsat_12.cm13",
    },
    {
        .name = "yang_zhang_sat_12_file_to_verified_decision",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_FILE_TO_VERIFIED_DECISION,
        .expected_status = WANG_SOLVE_SAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_sat_12.cm13",
    },
    {
        .name = "yang_zhang_unsat_12_file_to_verified_decision",
        .kind = BENCH_CM13_FILE,
        .scope = BENCH_FILE_TO_VERIFIED_DECISION,
        .expected_status = WANG_SOLVE_UNSAT,
        .default_iterations = 1,
        .input_path = "benchmarks/instances/yang_zhang_unsat_12.cm13",
    },
};

static void fixture_destroy(BenchmarkFixture *fixture)
{
    if (fixture == NULL) {
        return;
    }
    if (fixture->owns_reduction) {
        yang_zhang_reduction_destroy(&fixture->reduction);
    }
    if (fixture->owns_region) {
        region_destroy(&fixture->region);
    }
    cm13_formula_destroy(&fixture->formula);
    *fixture = (BenchmarkFixture){0};
}

static bool activate_all(Region *region)
{
    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            if (!region_set_active(region, x, y, true)) {
                return false;
            }
        }
    }
    return true;
}

static bool build_forced_thin_region(BenchmarkFixture *fixture)
{
    const int32_t width = 32768;
    if (!region_init(&fixture->region, width, 1)) {
        return false;
    }
    fixture->owns_region = true;
    if (!activate_all(&fixture->region)) {
        return false;
    }

    for (int32_t x = 0; x < width; ++x) {
        if (!region_set_boundary(&fixture->region, x, 0, N, COLOR_B) ||
            !region_set_boundary(&fixture->region, x, 0, S, COLOR_B)) {
            return false;
        }
    }
    return region_set_boundary(&fixture->region, 0, 0, W, COLOR_0) &&
        region_set_boundary(&fixture->region, width - 1, 0, E, COLOR_0);
}

static bool build_unconstrained_region(BenchmarkFixture *fixture)
{
    if (!region_init(&fixture->region, 96, 96)) {
        return false;
    }
    fixture->owns_region = true;
    return activate_all(&fixture->region);
}

static bool build_result_copy_region(BenchmarkFixture *fixture)
{
    if (!region_init(&fixture->region, 2048, 1024)) {
        return false;
    }
    fixture->owns_region = true;

    return region_set_active(&fixture->region, 0, 0, true) &&
        region_set_boundary(&fixture->region, 0, 0, N, COLOR_B) &&
        region_set_boundary(&fixture->region, 0, 0, E, COLOR_0) &&
        region_set_boundary(&fixture->region, 0, 0, S, COLOR_B) &&
        region_set_boundary(&fixture->region, 0, 0, W, COLOR_0);
}

static bool build_backtracking_region(BenchmarkFixture *fixture)
{
    if (!region_init(&fixture->region, 4, 4)) {
        return false;
    }
    fixture->owns_region = true;
    if (!activate_all(&fixture->region)) {
        return false;
    }

    return region_set_boundary(&fixture->region, 1, 0, N, COLOR_R) &&
        region_set_boundary(&fixture->region, 2, 3, S, COLOR_B) &&
        region_set_boundary(&fixture->region, 0, 3, W, COLOR_1) &&
        region_set_boundary(&fixture->region, 3, 1, E, COLOR_1) &&
        region_set_boundary(&fixture->region, 3, 3, E, COLOR_0);
}

static bool build_root_unsat_region(BenchmarkFixture *fixture)
{
    if (!region_init(&fixture->region, 2048, 1024)) {
        return false;
    }
    fixture->owns_region = true;
    if (!region_set_active(&fixture->region, 0, 0, true)) {
        return false;
    }
    return region_set_boundary(&fixture->region, 0, 0, N, COLOR_V);
}

static bool build_formula(
    BenchmarkFixture *fixture,
    uint32_t variable_count,
    bool satisfiable
)
{
    if (variable_count == 0 ||
        (satisfiable && variable_count % 3u != 0) ||
        (!satisfiable && variable_count % 2u != 0)) {
        return false;
    }

    fixture->formula.clauses = calloc(
        variable_count,
        sizeof(*fixture->formula.clauses)
    );
    if (fixture->formula.clauses == NULL) {
        return false;
    }

    if (satisfiable) {
        for (uint32_t group = 0; group < variable_count / 3u; ++group) {
            const uint32_t first = 3u * group;
            for (uint32_t repeat = 0; repeat < 3u; ++repeat) {
                fixture->formula.clauses[3u * group + repeat] = (Cm13Clause){
                    .variable_index = { first, first + 1u, first + 2u },
                };
            }
        }
    } else {
        for (uint32_t pair = 0; pair < variable_count / 2u; ++pair) {
            const uint32_t first = 2u * pair;
            fixture->formula.clauses[2u * pair] = (Cm13Clause){
                .variable_index = { first, first, first + 1u },
            };
            fixture->formula.clauses[2u * pair + 1u] = (Cm13Clause){
                .variable_index = { first, first + 1u, first + 1u },
            };
        }
    }

    fixture->formula.variable_count = variable_count;
    fixture->formula.clause_count = variable_count;
    return true;
}

static bool prepare_fixture(
    const BenchmarkSpec *spec,
    BenchmarkFixture *fixture
)
{
    switch (spec->kind) {
    case BENCH_GENERIC_FORCED_THIN:
        return build_forced_thin_region(fixture);
    case BENCH_GENERIC_RESULT_COPY:
        return build_result_copy_region(fixture);
    case BENCH_GENERIC_UNCONSTRAINED:
        return build_unconstrained_region(fixture);
    case BENCH_GENERIC_BACKTRACKING:
        return build_backtracking_region(fixture);
    case BENCH_GENERIC_ROOT_UNSAT:
        return build_root_unsat_region(fixture);
    case BENCH_YANG_ZHANG_SAT:
    case BENCH_YANG_ZHANG_UNSAT:
        if (!build_formula(
                fixture,
                spec->variable_count,
                spec->kind == BENCH_YANG_ZHANG_SAT
            )) {
            return false;
        }
        if (spec->scope == BENCH_SOLVER_ONLY) {
            if (!yang_zhang_build(&fixture->formula, &fixture->reduction)) {
                return false;
            }
            fixture->owns_reduction = true;
        }
        return true;
    case BENCH_CM13_FILE:
        if (spec->scope == BENCH_FILE_TO_VERIFIED_DECISION) {
            return true;
        }
        if (cm13_formula_load_path(
                spec->input_path,
                &fixture->formula,
                NULL
            ) != CM13_PARSE_OK ||
            !yang_zhang_build(&fixture->formula, &fixture->reduction)) {
            return false;
        }
        fixture->owns_reduction = true;
        return true;
    }
    return false;
}

static const Region *prepared_region(const BenchmarkFixture *fixture)
{
    if (fixture->owns_reduction) {
        return &fixture->reduction.region;
    }
    if (fixture->owns_region) {
        return &fixture->region;
    }
    return NULL;
}

static size_t active_cell_count(const Region *region)
{
    size_t count = 0;
    for (size_t i = 0; i < region->cell_count; ++i) {
        if (region->cells[i].active) {
            ++count;
        }
    }
    return count;
}

static bool metrics_equal(
    const WangSolverMetrics *left,
    const WangSolverMetrics *right
)
{
    return left->dfs_nodes == right->dfs_nodes &&
        left->decisions == right->decisions &&
        left->backtracks == right->backtracks &&
        left->failed_leaves == right->failed_leaves &&
        left->domain_reductions == right->domain_reductions &&
        left->propagated_arcs == right->propagated_arcs &&
        left->support_tile_visits == right->support_tile_visits &&
        left->support_byte_lookups == right->support_byte_lookups &&
        left->support_table_bytes == right->support_table_bytes &&
        left->mrv_cells_scanned == right->mrv_cells_scanned &&
        left->mrv_index_word_probes == right->mrv_index_word_probes &&
        left->mrv_index_bytes == right->mrv_index_bytes &&
        left->initial_trail_writes == right->initial_trail_writes &&
        left->search_trail_writes == right->search_trail_writes &&
        left->initial_trail_rewrites == right->initial_trail_rewrites &&
        left->search_trail_rewrites == right->search_trail_rewrites &&
        left->trail_peak == right->trail_peak &&
        left->trail_capacity_peak == right->trail_capacity_peak &&
        left->trail_bytes_peak == right->trail_bytes_peak &&
        left->enqueue_attempts == right->enqueue_attempts &&
        left->duplicate_enqueue_attempts ==
            right->duplicate_enqueue_attempts &&
        left->queue_dedup_index_bytes ==
            right->queue_dedup_index_bytes &&
        left->queue_peak == right->queue_peak &&
        left->queue_unique_peak == right->queue_unique_peak &&
        left->dfs_stack_capacity_peak == right->dfs_stack_capacity_peak &&
        left->dfs_stack_bytes_peak == right->dfs_stack_bytes_peak &&
        left->max_depth == right->max_depth &&
        left->sat_result_copy_bytes == right->sat_result_copy_bytes;
}

static bool result_matches_contract(
    const Region *region,
    WangSolveStatus expected,
    bool capture_unsat,
    const WangSolveResult *result
)
{
    if (region == NULL) {
        return false;
    }

    if (expected == WANG_SOLVE_SAT) {
        return result->domains != NULL &&
            result->domain_count == region->cell_count &&
            result->conflict_cell == SIZE_MAX;
    }

    if (result->conflict_cell >= region->cell_count ||
        !region->cells[result->conflict_cell].active) {
        return false;
    }
    if (capture_unsat) {
        return result->domains != NULL &&
            result->domain_count == region->cell_count &&
            result->domains[result->conflict_cell] == 0;
    }
    return result->domains == NULL && result->domain_count == 0;
}

static bool parse_iterations(const char *text, size_t *out_iterations)
{
    if (text == NULL || text[0] == '\0' || text[0] == '-') {
        return false;
    }
    errno = 0;
    char *end = NULL;
    const uintmax_t value = strtoumax(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        value == 0 || value > SIZE_MAX) {
        return false;
    }
    *out_iterations = (size_t)value;
    return true;
}

static bool elapsed_nanoseconds(
    const struct timespec *start,
    const struct timespec *end,
    uint64_t *out_elapsed
)
{
    if (end->tv_sec < start->tv_sec ||
        (end->tv_sec == start->tv_sec && end->tv_nsec < start->tv_nsec)) {
        return false;
    }

    uint64_t seconds = (uint64_t)(end->tv_sec - start->tv_sec);
    int64_t nanoseconds = end->tv_nsec - start->tv_nsec;
    if (nanoseconds < 0) {
        --seconds;
        nanoseconds += INT64_C(1000000000);
    }
    if (seconds > (UINT64_MAX - (uint64_t)nanoseconds) /
            UINT64_C(1000000000)) {
        return false;
    }
    *out_elapsed = seconds * UINT64_C(1000000000) +
        (uint64_t)nanoseconds;
    return true;
}

static long process_peak_rss_kib(
    const struct rusage *usage,
    const char **out_source
)
{
    FILE *status = fopen("/proc/self/status", "r");
    if (status != NULL) {
        char line[256];
        while (fgets(line, sizeof(line), status) != NULL) {
            long value = 0;
            if (sscanf(line, "VmHWM: %ld kB", &value) == 1 && value >= 0) {
                fclose(status);
                *out_source = "proc-vmhwm";
                return value;
            }
        }
        fclose(status);
    }

#if defined(__APPLE__)
    *out_source = "getrusage-macos-normalized";
    return usage->ru_maxrss / 1024;
#else
    *out_source = "getrusage";
    return usage->ru_maxrss;
#endif
}

static bool solve_once(
    const BenchmarkSpec *spec,
    const Region *region,
    const WangSolverOptions *options,
    bool capture_unsat,
    BenchmarkSolver solver,
    WangSolverMetrics *out_metrics
)
{
    WangSolveResult result = {0};
    const WangSolveStatus status = solver == BENCH_REFERENCE_SOLVER
        ? wang_solve_serial(region, options, &result)
        : wang_solve_optimized(region, options, &result);
    const bool valid = status == spec->expected_status &&
        result_matches_contract(
            region,
            spec->expected_status,
            capture_unsat,
            &result
        );
    if (valid) {
        *out_metrics = result.metrics;
    }
    wang_solve_result_destroy(&result);
    return valid;
}

static const char *benchmark_scope_name(BenchmarkScope scope)
{
    switch (scope) {
    case BENCH_SOLVER_ONLY:
        return "solver-only";
    case BENCH_END_TO_END:
        return "end-to-end";
    case BENCH_FILE_TO_VERIFIED_DECISION:
        return "file-to-verified-decision";
    }
    return "unknown";
}

static bool run_benchmark(
    const BenchmarkSpec *spec,
    size_t iterations,
    bool collect_metrics,
    bool capture_unsat,
    BenchmarkSolver solver
)
{
    BenchmarkFixture fixture = {0};
    if (!prepare_fixture(spec, &fixture)) {
        fixture_destroy(&fixture);
        return false;
    }

    WangSolverOptions options = {
        .flags = (collect_metrics ? WANG_SOLVE_COLLECT_METRICS : 0) |
            (capture_unsat ? WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT : 0),
    };
    WangSolverMetrics reference_metrics = {0};
    size_t cell_count = 0;
    size_t active_count = 0;

    const Region *region = prepared_region(&fixture);
    if (region != NULL) {
        cell_count = region->cell_count;
        active_count = active_cell_count(region);
    }

    struct timespec start;
    struct timespec end;
    if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) {
        fixture_destroy(&fixture);
        return false;
    }

    for (size_t iteration = 0; iteration < iterations; ++iteration) {
        WangSolverMetrics metrics = {0};
        YangZhangReduction reduction = {0};
        Cm13Formula iteration_formula = {0};
        bool owns_iteration_formula = false;
        bool owns_iteration_reduction = false;

        if (spec->scope == BENCH_END_TO_END) {
            if (!yang_zhang_build(&fixture.formula, &reduction)) {
                fixture_destroy(&fixture);
                return false;
            }
            region = &reduction.region;
            owns_iteration_reduction = true;
        } else if (spec->scope == BENCH_FILE_TO_VERIFIED_DECISION) {
            if (cm13_formula_load_path(
                    spec->input_path,
                    &iteration_formula,
                    NULL
                ) != CM13_PARSE_OK) {
                fixture_destroy(&fixture);
                return false;
            }
            owns_iteration_formula = true;
            if (!yang_zhang_build(&iteration_formula, &reduction)) {
                cm13_formula_destroy(&iteration_formula);
                fixture_destroy(&fixture);
                return false;
            }
            owns_iteration_reduction = true;
            region = &reduction.region;
        }

        if (iteration == 0 && region != NULL) {
            cell_count = region->cell_count;
            active_count = active_cell_count(region);
        }

        if (region == NULL) {
            if (owns_iteration_reduction) {
                yang_zhang_reduction_destroy(&reduction);
            }
            if (owns_iteration_formula) {
                cm13_formula_destroy(&iteration_formula);
            }
            fixture_destroy(&fixture);
            return false;
        }

        const bool solved = solve_once(
            spec,
            region,
            &options,
            capture_unsat,
            solver,
            &metrics
        );
        if (owns_iteration_reduction) {
            yang_zhang_reduction_destroy(&reduction);
        }
        if (owns_iteration_formula) {
            cm13_formula_destroy(&iteration_formula);
        }
        if (!solved) {
            fixture_destroy(&fixture);
            return false;
        }

        if (iteration == 0) {
            reference_metrics = metrics;
        } else if (!metrics_equal(&reference_metrics, &metrics)) {
            fixture_destroy(&fixture);
            return false;
        }
    }

    if (clock_gettime(CLOCK_MONOTONIC, &end) != 0) {
        fixture_destroy(&fixture);
        return false;
    }

    uint64_t elapsed = 0;
    struct rusage usage;
    if (!elapsed_nanoseconds(&start, &end, &elapsed) ||
        getrusage(RUSAGE_SELF, &usage) != 0) {
        fixture_destroy(&fixture);
        return false;
    }
    const char *peak_rss_source = NULL;
    const long peak_rss_kib = process_peak_rss_kib(
        &usage,
        &peak_rss_source
    );

    printf(
        "benchmark_version=9 case=%s solver=%s scope=%s expected=%s "
        "iterations=%zu metrics=%u capture_unsat=%u "
        "elapsed_ns=%" PRIu64 " ns_per_iteration=%" PRIu64 " "
        "process_peak_rss_kib=%ld peak_rss_source=%s "
        "cells=%zu active=%zu "
        "dfs_nodes=%" PRIu64 " decisions=%" PRIu64 " "
        "backtracks=%" PRIu64 " failed_leaves=%" PRIu64 " "
        "domain_reductions=%" PRIu64 " propagated_arcs=%" PRIu64 " "
        "support_tile_visits=%" PRIu64 " "
        "support_byte_lookups=%" PRIu64 " "
        "support_table_bytes=%zu "
        "mrv_cells_scanned=%" PRIu64 " "
        "mrv_index_word_probes=%" PRIu64 " "
        "mrv_index_bytes=%zu "
        "initial_trail_writes=%" PRIu64 " "
        "search_trail_writes=%" PRIu64 " "
        "initial_trail_rewrites=%" PRIu64 " "
        "search_trail_rewrites=%" PRIu64 " trail_peak=%zu "
        "trail_capacity_peak=%zu trail_bytes_peak=%zu "
        "enqueue_attempts=%" PRIu64 " "
        "duplicate_enqueue_attempts=%" PRIu64 " "
        "queue_dedup_index_bytes=%zu queue_peak=%zu "
        "queue_unique_peak=%zu "
        "dfs_stack_capacity_peak=%zu dfs_stack_bytes_peak=%zu "
        "max_depth=%zu sat_result_copy_bytes=%zu\n",
        spec->name,
        solver == BENCH_REFERENCE_SOLVER ? "reference" : "optimized",
        benchmark_scope_name(spec->scope),
        spec->expected_status == WANG_SOLVE_SAT ? "SAT" : "UNSAT",
        iterations,
        collect_metrics ? 1u : 0u,
        capture_unsat ? 1u : 0u,
        elapsed,
        elapsed / iterations,
        peak_rss_kib,
        peak_rss_source,
        cell_count,
        active_count,
        reference_metrics.dfs_nodes,
        reference_metrics.decisions,
        reference_metrics.backtracks,
        reference_metrics.failed_leaves,
        reference_metrics.domain_reductions,
        reference_metrics.propagated_arcs,
        reference_metrics.support_tile_visits,
        reference_metrics.support_byte_lookups,
        reference_metrics.support_table_bytes,
        reference_metrics.mrv_cells_scanned,
        reference_metrics.mrv_index_word_probes,
        reference_metrics.mrv_index_bytes,
        reference_metrics.initial_trail_writes,
        reference_metrics.search_trail_writes,
        reference_metrics.initial_trail_rewrites,
        reference_metrics.search_trail_rewrites,
        reference_metrics.trail_peak,
        reference_metrics.trail_capacity_peak,
        reference_metrics.trail_bytes_peak,
        reference_metrics.enqueue_attempts,
        reference_metrics.duplicate_enqueue_attempts,
        reference_metrics.queue_dedup_index_bytes,
        reference_metrics.queue_peak,
        reference_metrics.queue_unique_peak,
        reference_metrics.dfs_stack_capacity_peak,
        reference_metrics.dfs_stack_bytes_peak,
        reference_metrics.max_depth,
        reference_metrics.sat_result_copy_bytes
    );

    fixture_destroy(&fixture);
    return true;
}

static const BenchmarkSpec *find_benchmark(const char *name)
{
    if (name == NULL) {
        return NULL;
    }
    for (size_t i = 0; i < sizeof(BENCHMARKS) / sizeof(BENCHMARKS[0]); ++i) {
        if (strcmp(BENCHMARKS[i].name, name) == 0) {
            return &BENCHMARKS[i];
        }
    }
    return NULL;
}

static void print_usage(const char *program)
{
    fprintf(
        stderr,
        "Usage: %s --case NAME [--solver reference|optimized] "
        "[--iterations N] [--metrics] [--capture-unsat]\n"
        "       %s --list\n"
        "       %s --environment\n",
        program,
        program,
        program
    );
}

int main(int argc, char **argv)
{
    const char *case_name = NULL;
    size_t iterations = 0;
    bool collect_metrics = false;
    bool capture_unsat = false;
    bool list = false;
    bool environment = false;
    BenchmarkSolver solver = BENCH_REFERENCE_SOLVER;
    bool solver_selected = false;

    for (int argument = 1; argument < argc; ++argument) {
        if (strcmp(argv[argument], "--case") == 0 && argument + 1 < argc) {
            case_name = argv[++argument];
        } else if (strcmp(argv[argument], "--iterations") == 0 &&
                   argument + 1 < argc) {
            if (!parse_iterations(argv[++argument], &iterations)) {
                print_usage(argv[0]);
                return EXIT_FAILURE;
            }
        } else if (strcmp(argv[argument], "--metrics") == 0) {
            collect_metrics = true;
        } else if (strcmp(argv[argument], "--capture-unsat") == 0) {
            capture_unsat = true;
        } else if (strcmp(argv[argument], "--solver") == 0 &&
                   argument + 1 < argc) {
            const char *name = argv[++argument];
            if (solver_selected) {
                print_usage(argv[0]);
                return EXIT_FAILURE;
            }
            solver_selected = true;
            if (strcmp(name, "reference") == 0) {
                solver = BENCH_REFERENCE_SOLVER;
            } else if (strcmp(name, "optimized") == 0) {
                solver = BENCH_OPTIMIZED_SOLVER;
            } else {
                print_usage(argv[0]);
                return EXIT_FAILURE;
            }
        } else if (strcmp(argv[argument], "--list") == 0) {
            list = true;
        } else if (strcmp(argv[argument], "--environment") == 0) {
            environment = true;
        } else {
            print_usage(argv[0]);
            return EXIT_FAILURE;
        }
    }

    if (list) {
        if (case_name != NULL || iterations != 0 || collect_metrics ||
            capture_unsat || environment || solver_selected) {
            print_usage(argv[0]);
            return EXIT_FAILURE;
        }
        for (size_t i = 0;
             i < sizeof(BENCHMARKS) / sizeof(BENCHMARKS[0]);
             ++i) {
            puts(BENCHMARKS[i].name);
        }
        return EXIT_SUCCESS;
    }

    if (environment) {
        if (case_name != NULL || iterations != 0 || collect_metrics ||
            capture_unsat || solver_selected) {
            print_usage(argv[0]);
            return EXIT_FAILURE;
        }
        printf("benchmark_version=9 ");
#if defined(__clang__)
        printf(
            "compiler=clang-%d.%d.%d ",
            __clang_major__,
            __clang_minor__,
            __clang_patchlevel__
        );
#elif defined(__GNUC__)
        printf(
            "compiler=gcc-%d.%d.%d ",
            __GNUC__,
            __GNUC_MINOR__,
            __GNUC_PATCHLEVEL__
        );
#else
        printf("compiler=unknown ");
#endif
        printf("c_standard=%ld\n", (long)__STDC_VERSION__);
        return EXIT_SUCCESS;
    }

    const BenchmarkSpec *spec = find_benchmark(case_name);
    if (spec == NULL) {
        print_usage(argv[0]);
        return EXIT_FAILURE;
    }
    if (iterations == 0) {
        iterations = spec->default_iterations;
    }
    if (!run_benchmark(
            spec,
            iterations,
            collect_metrics,
            capture_unsat,
            solver
        )) {
        fprintf(stderr, "benchmark failed: %s\n", spec->name);
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
