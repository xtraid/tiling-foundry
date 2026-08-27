#include "wang/solver_trace.h"

#include "wang/tile.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef WangSolveStatus (*TracedSolveFunction)(
    const Region *,
    const WangSolverOptions *,
    const WangSolveTraceOptions *,
    WangTracedSolveResult *
);

typedef WangSolveStatus (*SolveFunction)(
    const Region *,
    const WangSolverOptions *,
    WangSolveResult *
);

typedef struct {
    size_t cell_index;
    uint32_t old_domain;
} ReplayChange;

static void activate_all(Region *region)
{
    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            assert(region_set_active(region, x, y, true));
        }
    }
}

static void build_backtracking_region(Region *region)
{
    assert(region_init(region, 4, 4));
    activate_all(region);
    assert(region_set_boundary(region, 1, 0, N, COLOR_R));
    assert(region_set_boundary(region, 2, 3, S, COLOR_B));
    assert(region_set_boundary(region, 0, 3, W, COLOR_1));
    assert(region_set_boundary(region, 3, 1, E, COLOR_1));
    assert(region_set_boundary(region, 3, 3, E, COLOR_0));
}

static bool trace_event_equal(
    const WangSolveTraceEvent *left,
    const WangSolveTraceEvent *right
)
{
    return left->sequence == right->sequence &&
        left->kind == right->kind &&
        left->phase == right->phase &&
        left->reason == right->reason &&
        left->depth == right->depth &&
        left->cell_index == right->cell_index &&
        left->change_mark == right->change_mark &&
        left->old_domain == right->old_domain &&
        left->new_domain == right->new_domain &&
        left->status == right->status;
}

static void assert_trace_equal(
    const WangSolveTrace *left,
    const WangSolveTrace *right
)
{
    assert(left->domain_count == right->domain_count);
    assert(left->event_count == right->event_count);
    assert(left->observed_event_count == right->observed_event_count);
    assert(left->event_capacity == right->event_capacity);
    assert(left->truncated == right->truncated);
    assert(left->checkpoint_count == right->checkpoint_count);
    assert(left->checkpoint_interval == right->checkpoint_interval);
    assert(left->checkpoint_capacity == right->checkpoint_capacity);
    assert(left->checkpoints_truncated == right->checkpoints_truncated);
    assert(memcmp(
        left->initial_domains,
        right->initial_domains,
        left->domain_count * sizeof(*left->initial_domains)
    ) == 0);
    for (size_t i = 0; i < left->event_count; ++i) {
        assert(trace_event_equal(&left->events[i], &right->events[i]));
    }
    for (size_t i = 0; i < left->checkpoint_count; ++i) {
        assert(left->checkpoints[i].event_sequence ==
               right->checkpoints[i].event_sequence);
        assert(left->checkpoints[i].change_mark ==
               right->checkpoints[i].change_mark);
    }
    assert(memcmp(
        left->checkpoint_domains,
        right->checkpoint_domains,
        left->checkpoint_count * left->domain_count *
            sizeof(*left->checkpoint_domains)
    ) == 0);
}

static void assert_trace_replays(
    const WangSolveTrace *trace,
    const WangSolveResult *solve
)
{
    assert(!trace->truncated);
    assert(trace->event_count == trace->observed_event_count);
    assert(trace->event_count >= 2);
    assert(trace->events[0].kind == WANG_TRACE_EVENT_ROOT);
    assert(trace->events[trace->event_count - 1].kind ==
           WANG_TRACE_EVENT_RESULT);

    uint32_t *domains = malloc(
        trace->domain_count * sizeof(*domains)
    );
    ReplayChange *changes = malloc(
        trace->observed_event_count * sizeof(*changes)
    );
    assert(domains != NULL);
    assert(changes != NULL);
    memcpy(
        domains,
        trace->initial_domains,
        trace->domain_count * sizeof(*domains)
    );

    bool kinds[WANG_TRACE_EVENT_RESULT + 1] = {false};
    size_t change_count = 0;
    size_t checkpoint = 0;
    for (size_t i = 0; i < trace->event_count; ++i) {
        const WangSolveTraceEvent *event = &trace->events[i];
        assert(event->sequence == i);
        assert(event->kind <= WANG_TRACE_EVENT_RESULT);
        kinds[event->kind] = true;
        if (event->kind == WANG_TRACE_EVENT_DOMAIN_REDUCTION) {
            assert(event->cell_index < trace->domain_count);
            assert(domains[event->cell_index] == event->old_domain);
            assert((event->new_domain & ~event->old_domain) == 0);
            assert(event->new_domain != event->old_domain);
            changes[change_count++] = (ReplayChange){
                .cell_index = event->cell_index,
                .old_domain = event->old_domain,
            };
            domains[event->cell_index] = event->new_domain;
            assert(event->change_mark == change_count);
        } else if (event->kind == WANG_TRACE_EVENT_BACKTRACK) {
            assert(event->change_mark <= change_count);
            while (change_count > event->change_mark) {
                const ReplayChange change = changes[--change_count];
                domains[change.cell_index] = change.old_domain;
            }
        } else {
            assert(event->change_mark == change_count);
        }

        if (checkpoint < trace->checkpoint_count &&
            trace->checkpoints[checkpoint].event_sequence == event->sequence) {
            assert(trace->checkpoints[checkpoint].change_mark == change_count);
            assert(memcmp(
                domains,
                &trace->checkpoint_domains[
                    checkpoint * trace->domain_count
                ],
                trace->domain_count * sizeof(*domains)
            ) == 0);
            ++checkpoint;
        }
    }
    assert(checkpoint == trace->checkpoint_count);
    assert(kinds[WANG_TRACE_EVENT_ROOT]);
    assert(kinds[WANG_TRACE_EVENT_PROPAGATION]);
    assert(kinds[WANG_TRACE_EVENT_DECISION]);
    assert(kinds[WANG_TRACE_EVENT_DOMAIN_REDUCTION]);
    assert(kinds[WANG_TRACE_EVENT_CONFLICT]);
    assert(kinds[WANG_TRACE_EVENT_BACKTRACK]);
    assert(kinds[WANG_TRACE_EVENT_RESULT]);
    assert(trace->events[trace->event_count - 1].status == WANG_SOLVE_SAT);
    assert(solve->domain_count == trace->domain_count);
    assert(memcmp(
        domains,
        solve->domains,
        trace->domain_count * sizeof(*domains)
    ) == 0);

    free(changes);
    free(domains);
}

static void assert_traced_path(
    SolveFunction plain_solve,
    TracedSolveFunction traced_solve
)
{
    Region region = {0};
    build_backtracking_region(&region);
    const WangSolverOptions solver_options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
    };
    const WangSolveTraceOptions trace_options = {
        .event_capacity = 4096,
        .checkpoint_interval = 7,
        .checkpoint_capacity = 64,
    };
    WangSolveResult plain = {0};
    WangTracedSolveResult first = {0};
    WangTracedSolveResult second = {0};

    assert(plain_solve(&region, &solver_options, &plain) == WANG_SOLVE_SAT);
    assert(traced_solve(
        &region,
        &solver_options,
        &trace_options,
        &first
    ) == WANG_SOLVE_SAT);
    assert(traced_solve(
        &region,
        &solver_options,
        &trace_options,
        &second
    ) == WANG_SOLVE_SAT);

    assert(plain.domain_count == first.solve.domain_count);
    assert(memcmp(
        plain.domains,
        first.solve.domains,
        plain.domain_count * sizeof(*plain.domains)
    ) == 0);
    assert(memcmp(
        &plain.metrics,
        &first.solve.metrics,
        sizeof(plain.metrics)
    ) == 0);
    assert_trace_equal(&first.trace, &second.trace);
    assert_trace_replays(&first.trace, &first.solve);
    assert(!first.trace.checkpoints_truncated);
    assert(first.trace.checkpoint_count > 0);

    wang_solve_result_destroy(&plain);
    wang_traced_solve_result_destroy(&first);
    wang_traced_solve_result_destroy(&first);
    wang_traced_solve_result_destroy(&second);
    region_destroy(&region);
}

static void test_reference_and_optimized_traces_are_replayable(void)
{
    assert_traced_path(wang_solve_serial, wang_solve_serial_traced);
    assert_traced_path(wang_solve_optimized, wang_solve_optimized_traced);
}

static void test_capacity_keeps_root_and_terminal_result(void)
{
    Region region = {0};
    build_backtracking_region(&region);
    const WangSolveTraceOptions options = { .event_capacity = 2 };
    WangTracedSolveResult result = {0};

    assert(wang_solve_serial_traced(
        &region,
        NULL,
        &options,
        &result
    ) == WANG_SOLVE_SAT);
    assert(result.trace.event_count == 2);
    assert(result.trace.events[0].kind == WANG_TRACE_EVENT_ROOT);
    assert(result.trace.events[1].kind == WANG_TRACE_EVENT_RESULT);
    assert(result.trace.events[1].sequence > 1);
    assert(result.trace.observed_event_count ==
           result.trace.events[1].sequence + 1);
    assert(result.trace.truncated);

    wang_traced_solve_result_destroy(&result);
    region_destroy(&region);
}

static void test_root_conflict_and_contract_rejections(void)
{
    Region region = {0};
    assert(region_init(&region, 1, 1));
    activate_all(&region);
    assert(region_set_boundary(&region, 0, 0, N, COLOR_V));

    const WangSolveTraceOptions options = {
        .event_capacity = 8,
        .checkpoint_interval = 1,
        .checkpoint_capacity = 1,
    };
    WangTracedSolveResult result = {0};
    assert(wang_solve_optimized_traced(
        &region,
        NULL,
        &options,
        &result
    ) == WANG_SOLVE_UNSAT);
    assert(result.trace.event_count == 3);
    assert(result.trace.events[0].kind == WANG_TRACE_EVENT_ROOT);
    assert(result.trace.events[1].kind == WANG_TRACE_EVENT_CONFLICT);
    assert(result.trace.events[1].cell_index == 0);
    assert(result.trace.events[2].kind == WANG_TRACE_EVENT_RESULT);
    assert(result.trace.events[2].status == WANG_SOLVE_UNSAT);
    assert(result.trace.checkpoint_count == 1);
    assert(result.trace.checkpoints_truncated);
    wang_traced_solve_result_destroy(&result);

    const WangSolveTraceOptions terminal_checkpoint = {
        .event_capacity = 8,
        .checkpoint_interval = 3,
        .checkpoint_capacity = 1,
    };
    assert(wang_solve_optimized_traced(
        &region,
        NULL,
        &terminal_checkpoint,
        &result
    ) == WANG_SOLVE_UNSAT);
    assert(result.trace.checkpoint_count == 1);
    assert(result.trace.checkpoints[0].event_sequence == 2);
    assert(!result.trace.checkpoints_truncated);
    wang_traced_solve_result_destroy(&result);

    const WangSolveTraceOptions too_small = { .event_capacity = 1 };
    assert(wang_solve_serial_traced(
        &region,
        NULL,
        &too_small,
        &result
    ) == WANG_SOLVE_ERROR);
    const WangSolveTraceOptions mismatched_checkpoints = {
        .event_capacity = 4,
        .checkpoint_interval = 2,
    };
    assert(wang_solve_serial_traced(
        &region,
        NULL,
        &mismatched_checkpoints,
        &result
    ) == WANG_SOLVE_ERROR);
    result.trace.event_count = 1;
    assert(wang_solve_serial_traced(
        &region,
        NULL,
        &options,
        &result
    ) == WANG_SOLVE_ERROR);
    result.trace.event_count = 0;

    region_destroy(&region);
}

int main(void)
{
    test_reference_and_optimized_traces_are_replayable();
    test_capacity_keeps_root_and_terminal_result();
    test_root_conflict_and_contract_rejections();

    puts("test_solver_event_trace: OK");
    return 0;
}
