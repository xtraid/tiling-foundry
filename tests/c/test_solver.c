#define _POSIX_C_SOURCE 200809L

#include "wang/solver.h"

#include "wang/tile.h"
#include "wang/verify.h"

#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>

typedef WangSolveStatus (*SolveFunction)(
    const Region *,
    const WangSolverOptions *,
    WangSolveResult *
);

static bool metrics_are_zero(const WangSolverMetrics *metrics)
{
    return metrics->dfs_nodes == 0 &&
        metrics->decisions == 0 &&
        metrics->backtracks == 0 &&
        metrics->failed_leaves == 0 &&
        metrics->domain_reductions == 0 &&
        metrics->propagated_arcs == 0 &&
        metrics->support_tile_visits == 0 &&
        metrics->support_byte_lookups == 0 &&
        metrics->support_table_bytes == 0 &&
        metrics->mrv_cells_scanned == 0 &&
        metrics->mrv_index_word_probes == 0 &&
        metrics->mrv_index_bytes == 0 &&
        metrics->initial_trail_writes == 0 &&
        metrics->search_trail_writes == 0 &&
        metrics->enqueue_attempts == 0 &&
        metrics->duplicate_enqueue_attempts == 0 &&
        metrics->queue_dedup_index_bytes == 0 &&
        metrics->initial_trail_rewrites == 0 &&
        metrics->search_trail_rewrites == 0 &&
        metrics->trail_peak == 0 &&
        metrics->trail_capacity_peak == 0 &&
        metrics->trail_bytes_peak == 0 &&
        metrics->queue_peak == 0 &&
        metrics->queue_unique_peak == 0 &&
        metrics->dfs_stack_capacity_peak == 0 &&
        metrics->dfs_stack_bytes_peak == 0 &&
        metrics->max_depth == 0 &&
        metrics->sat_result_copy_bytes == 0;
}

static uint64_t read_u64_le(const unsigned char *source)
{
    uint64_t value = 0;
    for (unsigned byte = 0; byte < 8; ++byte) {
        value |= (uint64_t)source[byte] << (8u * byte);
    }
    return value;
}

static uint32_t read_u32_le(const unsigned char *source)
{
    uint32_t value = 0;
    for (unsigned byte = 0; byte < 4; ++byte) {
        value |= (uint32_t)source[byte] << (8u * byte);
    }
    return value;
}

static void activate_all(Region *region)
{
    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            assert(region_set_active(region, x, y, true));
        }
    }
}

static void assert_sat_snapshot(
    const Region *region,
    const WangSolveResult *result
)
{
    const size_t cell_count =
        (size_t)region->width * (size_t)region->height;
    TileId *tiles = malloc(cell_count * sizeof(*tiles));
    assert(tiles != NULL);

    for (size_t i = 0; i < cell_count; ++i) {
        if (!region->cells[i].active) {
            assert(result->domains[i] == 0);
            tiles[i] = TILE_NONE;
            continue;
        }

        const uint32_t domain = result->domains[i];
        assert(domain != 0 && (domain & (domain - 1u)) == 0);
        TileId tile = 0;
        uint32_t copy = domain;
        while ((copy & 1u) == 0) {
            copy >>= 1;
            ++tile;
        }
        tiles[i] = tile;
    }

    assert(wang_verify_tiling(region, tiles, cell_count) == WANG_VERIFY_VALID);
    free(tiles);
}

static void test_empty_active_mask_is_sat(void)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 3, 2));

    assert(wang_solve_serial(&region, NULL, &result) == WANG_SOLVE_SAT);
    assert(result.domain_count == 6);
    assert(result.conflict_cell == SIZE_MAX);
    assert(result.resolved_count == 0);
    assert(metrics_are_zero(&result.metrics));
    assert_sat_snapshot(&region, &result);

    wang_solve_result_destroy(&result);
    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_forced_single_cell_sat(void)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_B));
    assert(region_set_boundary(&region, 0, 0, E, COLOR_0));
    assert(region_set_boundary(&region, 0, 0, S, COLOR_B));
    assert(region_set_boundary(&region, 0, 0, W, COLOR_0));

    assert(wang_solve_serial(&region, NULL, &result) == WANG_SOLVE_SAT);
    assert(result.domains[0] == (UINT32_C(1) << TILE_F0));
    assert(result.resolved_count == 1);
    assert_sat_snapshot(&region, &result);

    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_impossible_boundary_unsat_with_metrics(void)
{
    Region region = {0};
    WangSolveResult result = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };

    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_V));

    assert(wang_solve_serial(&region, &options, &result) == WANG_SOLVE_UNSAT);
    assert(result.domain_count == 0);
    assert(result.domains == NULL);
    assert(result.conflict_cell == 0);
    assert(result.metrics.failed_leaves == 1);

    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_unsat_snapshot_is_opt_in(void)
{
    Region region = {0};
    WangSolveResult result = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT,
    };

    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_V));

    assert(wang_solve_serial(&region, &options, &result) == WANG_SOLVE_UNSAT);
    assert(result.domain_count == 1);
    assert(result.domains != NULL);
    assert(result.domains[0] == 0);
    assert(result.conflict_cell == 0);

    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_deterministic_unconstrained_region(void)
{
    Region region = {0};
    WangSolveResult first = {0};
    WangSolveResult second = {0};
    assert(region_init(&region, 2, 2));
    activate_all(&region);

    assert(wang_solve_serial(&region, NULL, &first) == WANG_SOLVE_SAT);
    assert(wang_solve_serial(&region, NULL, &second) == WANG_SOLVE_SAT);
    assert(first.domain_count == second.domain_count);
    assert(memcmp(
        first.domains,
        second.domains,
        first.domain_count * sizeof(*first.domains)
    ) == 0);
    assert_sat_snapshot(&region, &first);

    wang_solve_result_destroy(&first);
    wang_solve_result_destroy(&second);
    region_destroy(&region);
}

static void assert_destroyed_result(const WangSolveResult *result)
{
    assert(result->domains == NULL);
    assert(result->domain_count == 0);
    assert(result->conflict_cell == 0);
    assert(result->resolved_count == 0);
    assert(result->decision_depth == 0);
    assert(result->traced_leaf_count == 0);
    assert(!result->trace_truncated);
    assert(metrics_are_zero(&result->metrics));
}

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
    assert_sat_snapshot(&region, &result);
    wang_solve_result_destroy(&result);

    domains[0] = 0;
    assert(solve(&region, &constrained, &result) == WANG_SOLVE_UNSAT);
    assert(result.domains == NULL);
    assert(result.domain_count == 0);
    assert(result.conflict_cell == 0);
    wang_solve_result_destroy(&result);

    domains[0] = WANG_DOMAIN_ALL;
    domains[1] = UINT32_C(1) << TILE_F0;
    assert(solve(&region, &constrained, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    region_destroy(&region);
}

static void assert_initial_domain_validation(SolveFunction solve)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 2, 1));
    assert(region_set_active(&region, 0, 0, true));

    uint32_t domains[] = { WANG_DOMAIN_ALL, 0 };
    WangSolverOptions options = {
        .initial_domains = NULL,
        .initial_domain_count = 1,
    };
    assert(solve(&region, &options, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    options.initial_domains = domains;
    options.initial_domain_count = 0;
    assert(solve(&region, &options, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    options.initial_domain_count = 1;
    assert(solve(&region, &options, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    options.initial_domain_count = 2;
    domains[0] = WANG_DOMAIN_ALL | (UINT32_C(1) << TILE_COUNT);
    assert(solve(&region, &options, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    domains[0] = 0;
    domains[1] = UINT32_C(1) << TILE_COUNT;
    assert(solve(&region, &options, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    domains[1] = UINT32_C(1) << TILE_F0;
    assert(solve(&region, &options, &result) == WANG_SOLVE_ERROR);
    assert_destroyed_result(&result);

    domains[0] = WANG_DOMAIN_ALL;
    domains[1] = 0;
    assert(region_set_boundary(&region, 0, 0, N, COLOR_B));
    assert(region_set_boundary(&region, 0, 0, E, COLOR_0));
    assert(region_set_boundary(&region, 0, 0, S, COLOR_B));
    assert(region_set_boundary(&region, 0, 0, W, COLOR_0));
    domains[0] = UINT32_C(1) << TILE_F1;
    assert(solve(&region, &options, &result) == WANG_SOLVE_UNSAT);
    assert(result.conflict_cell == 0);
    wang_solve_result_destroy(&result);

    region_destroy(&region);
}

static void assert_initial_domain_isolated_choice(SolveFunction solve)
{
    Region region = {0};
    WangSolveResult baseline = {0};
    WangSolveResult absent = {0};
    WangSolveResult restricted = {0};
    assert(region_init(&region, 1, 1));
    assert(region_set_active(&region, 0, 0, true));

    const WangSolverOptions no_initial_domains = {0};
    assert(solve(&region, NULL, &baseline) == WANG_SOLVE_SAT);
    assert(solve(&region, &no_initial_domains, &absent) == WANG_SOLVE_SAT);
    assert(baseline.domain_count == absent.domain_count);
    assert(memcmp(
        baseline.domains,
        absent.domains,
        baseline.domain_count * sizeof(*baseline.domains)
    ) == 0);

    const uint32_t domains[] = {
        (UINT32_C(1) << TILE_F0) | (UINT32_C(1) << TILE_F1),
    };
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
        .initial_domains = domains,
        .initial_domain_count = 1,
    };
    assert(solve(&region, &options, &restricted) == WANG_SOLVE_SAT);
    assert(restricted.domains[0] == (UINT32_C(1) << TILE_F0));
    assert(restricted.metrics.domain_reductions == 2);
    assert(domains[0] ==
           ((UINT32_C(1) << TILE_F0) | (UINT32_C(1) << TILE_F1)));

    wang_solve_result_destroy(&baseline);
    wang_solve_result_destroy(&absent);
    wang_solve_result_destroy(&restricted);
    region_destroy(&region);
}

static void assert_initial_domain_root_diagnostics(SolveFunction solve)
{
    char path[] = "/tmp/wang-initial-domain-root-XXXXXX";
    const int temporary_fd = mkstemp(path);
    assert(temporary_fd >= 0);
    assert(close(temporary_fd) == 0);

    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 2, 1));
    assert(region_set_active(&region, 0, 0, true));

    const uint32_t domains[] = { 0, 0 };
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS |
            WANG_SOLVE_TRACE_FAILED_LEAVES |
            WANG_SOLVE_CAPTURE_UNSAT_SNAPSHOT,
        .failed_leaf_path = path,
        .failed_leaf_capacity = 1,
        .initial_domains = domains,
        .initial_domain_count = 2,
    };
    assert(solve(&region, &options, &result) == WANG_SOLVE_UNSAT);
    assert(result.domains != NULL);
    assert(result.domain_count == 2);
    assert(result.domains[0] == 0);
    assert(result.domains[1] == 0);
    assert(result.conflict_cell == 0);
    assert(result.traced_leaf_count == 1);
    assert(!result.trace_truncated);
    assert(result.metrics.dfs_nodes == 0);
    assert(result.metrics.failed_leaves == 1);
    assert(result.metrics.domain_reductions == 1);
    assert(result.metrics.initial_trail_writes == 0);
    assert(result.metrics.search_trail_writes == 0);
    assert(access(path, F_OK) == 0);
    assert(domains[0] == 0 && domains[1] == 0);

    assert(unlink(path) == 0);
    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void assert_all_zero_dense_empty_region(SolveFunction solve)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 2, 1));

    const uint32_t domains[] = { 0, 0 };
    const WangSolverOptions options = {
        .initial_domains = domains,
        .initial_domain_count = 2,
    };
    assert(solve(&region, &options, &result) == WANG_SOLVE_SAT);
    assert(result.domain_count == 2);
    assert(result.domains[0] == 0 && result.domains[1] == 0);
    assert_sat_snapshot(&region, &result);

    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_initial_domain_contract(void)
{
    const SolveFunction solvers[] = {
        wang_solve_serial,
        wang_solve_optimized,
    };
    for (size_t i = 0; i < sizeof(solvers) / sizeof(solvers[0]); ++i) {
        assert_initial_domain_contract(solvers[i]);
        assert_initial_domain_validation(solvers[i]);
        assert_initial_domain_isolated_choice(solvers[i]);
        assert_initial_domain_root_diagnostics(solvers[i]);
        assert_all_zero_dense_empty_region(solvers[i]);
    }
}

static bool brute_force_two_cells(const Region *region)
{
    TileId tiles[2];
    for (tiles[0] = 0; tiles[0] < TILE_COUNT; ++tiles[0]) {
        for (tiles[1] = 0; tiles[1] < TILE_COUNT; ++tiles[1]) {
            if (wang_verify_tiling(region, tiles, 2) == WANG_VERIFY_VALID) {
                return true;
            }
        }
    }
    return false;
}

static void test_small_regions_against_brute_force(void)
{
    const ColorId colors[] = {
        COLOR_0,
        COLOR_1,
        COLOR_V,
        COLOR_0_PRIME,
    };

    for (size_t west = 0; west < 4; ++west) {
        for (size_t east = 0; east < 4; ++east) {
            Region region = {0};
            WangSolveResult result = {0};
            assert(region_init(&region, 2, 1));
            activate_all(&region);
            assert(region_set_boundary(&region, 0, 0, N, COLOR_B));
            assert(region_set_boundary(&region, 1, 0, N, COLOR_B));
            assert(region_set_boundary(&region, 0, 0, S, COLOR_B));
            assert(region_set_boundary(&region, 1, 0, S, COLOR_B));
            assert(region_set_boundary(&region, 0, 0, W, colors[west]));
            assert(region_set_boundary(&region, 1, 0, E, colors[east]));

            const bool expected_sat = brute_force_two_cells(&region);
            const WangSolveStatus status = wang_solve_serial(
                &region,
                NULL,
                &result
            );
            assert(status == (expected_sat
                ? WANG_SOLVE_SAT
                : WANG_SOLVE_UNSAT));
            if (status == WANG_SOLVE_SAT) {
                assert_sat_snapshot(&region, &result);
            } else {
                assert(result.domains == NULL);
                assert(result.domain_count == 0);
                assert(result.conflict_cell < region.cell_count);
                assert(region.cells[result.conflict_cell].active);
            }

            wang_solve_result_destroy(&result);
            region_destroy(&region);
        }
    }
}

static void build_backtracking_fixture(Region *region)
{
    assert(region_init(region, 4, 4));
    activate_all(region);

    assert(region_set_boundary(region, 1, 0, N, COLOR_R));
    assert(region_set_boundary(region, 2, 3, S, COLOR_B));
    assert(region_set_boundary(region, 0, 3, W, COLOR_1));
    assert(region_set_boundary(region, 3, 1, E, COLOR_1));
    assert(region_set_boundary(region, 3, 3, E, COLOR_0));
}

static void test_backtracking_and_trace_truncation(void)
{
    char path[] = "/tmp/wang-leaf-cap-XXXXXX";
    const int temporary_fd = mkstemp(path);
    assert(temporary_fd >= 0);
    assert(close(temporary_fd) == 0);

    Region region = {0};
    WangSolveResult result = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS |
            WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = path,
        .failed_leaf_capacity = 1,
    };
    build_backtracking_fixture(&region);

    assert(wang_solve_serial(&region, &options, &result) == WANG_SOLVE_SAT);
    assert(result.metrics.failed_leaves == 2);
    assert(result.metrics.backtracks >= 2);
    assert(result.metrics.decisions == 10);
    assert(result.decision_depth == 8);
    /* The queue tail reaches 62, but at most 34 entries are pending. */
    assert(result.metrics.queue_peak == 34);
    assert(result.metrics.enqueue_attempts == 138);
    assert(result.metrics.duplicate_enqueue_attempts == 43);
    assert(result.metrics.queue_dedup_index_bytes == 0);
    assert(result.metrics.queue_unique_peak == 16);
    assert(result.metrics.initial_trail_rewrites == 31);
    assert(result.metrics.search_trail_rewrites == 13);
    assert(result.metrics.duplicate_enqueue_attempts <=
           result.metrics.enqueue_attempts);
    assert(result.metrics.queue_unique_peak <= result.metrics.queue_peak);
    assert(result.metrics.initial_trail_rewrites <=
           result.metrics.initial_trail_writes);
    assert(result.metrics.search_trail_rewrites <=
           result.metrics.search_trail_writes);
    assert(result.traced_leaf_count == 1);
    assert(result.trace_truncated);
    assert_sat_snapshot(&region, &result);

    FILE *file = fopen(path, "rb");
    assert(file != NULL);
    unsigned char header[64];
    assert(fread(header, 1, sizeof(header), file) == sizeof(header));
    assert((read_u32_le(header + 28) & 1u) != 0);
    assert(read_u64_le(header + 32) == 16);
    assert(read_u64_le(header + 40) == 96);
    assert(read_u64_le(header + 48) == 1);
    assert(read_u64_le(header + 56) == 1);
    assert(fclose(file) == 0);

    struct stat info;
    assert(stat(path, &info) == 0);
    assert((uint64_t)info.st_size == 64u + 96u);

    assert(unlink(path) == 0);
    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_mmap_trace_for_root_conflict(void)
{
    char path[] = "/tmp/wang-leaf-trace-XXXXXX";
    const int temporary_fd = mkstemp(path);
    assert(temporary_fd >= 0);
    assert(close(temporary_fd) == 0);

    Region region = {0};
    WangSolveResult result = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = path,
        .failed_leaf_capacity = 2,
    };
    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_V));

    assert(wang_solve_serial(&region, &options, &result) == WANG_SOLVE_UNSAT);
    assert(result.domains == NULL);
    assert(result.domain_count == 0);
    assert(result.traced_leaf_count == 1);
    assert(!result.trace_truncated);

    FILE *file = fopen(path, "rb");
    assert(file != NULL);
    unsigned char header[64];
    assert(fread(header, 1, sizeof(header), file) == sizeof(header));
    assert(memcmp(header, "W23LEAF", 7) == 0);
    assert(read_u64_le(header + 32) == 1);
    assert(read_u64_le(header + 40) == 40);
    assert(read_u64_le(header + 48) == 2);
    assert(read_u64_le(header + 56) == 1);

    unsigned char record[40];
    assert(fread(record, 1, sizeof(record), file) == sizeof(record));
    assert(read_u64_le(record + 8) == 0);
    assert(read_u32_le(record + 32) == 0);
    assert(fclose(file) == 0);

    struct stat info;
    assert(stat(path, &info) == 0);
    assert((uint64_t)info.st_size == 64u + 40u);

    assert(unlink(path) == 0);
    wang_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_trace_cleanup_after_ftruncate_error(void)
{
    char path[] = "/tmp/wang-leaf-error-XXXXXX";
    const int temporary_fd = mkstemp(path);
    assert(temporary_fd >= 0);
    assert(close(temporary_fd) == 0);
    assert(unlink(path) == 0);

    Region region = {0};
    WangSolveResult result = {0};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_TRACE_FAILED_LEAVES,
        .failed_leaf_path = path,
        .failed_leaf_capacity = 1,
    };
    assert(region_init(&region, 1, 1));
    activate_all(&region);

    struct rlimit original_limit;
    assert(getrlimit(RLIMIT_FSIZE, &original_limit) == 0);
    struct rlimit limited = original_limit;
    limited.rlim_cur = 0;

    struct sigaction original_action;
    struct sigaction ignored_action = { .sa_handler = SIG_IGN };
    assert(sigemptyset(&ignored_action.sa_mask) == 0);
    assert(sigaction(SIGXFSZ, &ignored_action, &original_action) == 0);
    assert(setrlimit(RLIMIT_FSIZE, &limited) == 0);

    const WangSolveStatus status = wang_solve_serial(
        &region,
        &options,
        &result
    );

    assert(setrlimit(RLIMIT_FSIZE, &original_limit) == 0);
    assert(sigaction(SIGXFSZ, &original_action, NULL) == 0);

    const bool trace_was_removed = access(path, F_OK) != 0;
    if (!trace_was_removed) {
        assert(unlink(path) == 0);
    }

    wang_solve_result_destroy(&result);
    region_destroy(&region);
    assert(status == WANG_SOLVE_ERROR);
    assert(trace_was_removed);
}

static void test_rejects_invalid_api_inputs(void)
{
    Region region = {0};
    WangSolveResult result = {0};
    assert(region_init(&region, 1, 1));

    assert(wang_solve_serial(NULL, NULL, &result) == WANG_SOLVE_ERROR);
    assert(wang_solve_serial(&region, NULL, NULL) == WANG_SOLVE_ERROR);

    WangSolverOptions unknown = { .flags = UINT32_C(1) << 31 };
    assert(wang_solve_serial(&region, &unknown, &result) == WANG_SOLVE_ERROR);

    WangSolverOptions missing_trace = {
        .flags = WANG_SOLVE_TRACE_FAILED_LEAVES,
    };
    assert(wang_solve_serial(&region, &missing_trace, &result) ==
           WANG_SOLVE_ERROR);

    result.domain_count = 1;
    assert(wang_solve_serial(&region, NULL, &result) == WANG_SOLVE_ERROR);
    result.domain_count = 0;

    region.cells[0].boundary[N] = (ColorId)COLOR_COUNT;
    assert(wang_solve_serial(&region, NULL, &result) == WANG_SOLVE_ERROR);

    region_destroy(&region);
}

int main(void)
{
    test_empty_active_mask_is_sat();
    test_forced_single_cell_sat();
    test_impossible_boundary_unsat_with_metrics();
    test_unsat_snapshot_is_opt_in();
    test_deterministic_unconstrained_region();
    test_initial_domain_contract();
    test_small_regions_against_brute_force();
    test_mmap_trace_for_root_conflict();
    test_backtracking_and_trace_truncation();
    test_trace_cleanup_after_ftruncate_error();
    test_rejects_invalid_api_inputs();

    puts("test_solver: OK");
    return 0;
}
