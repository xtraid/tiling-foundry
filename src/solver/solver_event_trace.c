#include "solver_event_trace.h"

#include <stdlib.h>
#include <string.h>

static bool checked_mul_size(size_t a, size_t b, size_t *out)
{
    if (out == NULL || (a != 0 && b > SIZE_MAX / a)) {
        return false;
    }
    *out = a * b;
    return true;
}

bool solver_event_trace_options_are_valid(
    const WangSolveTraceOptions *options
)
{
    if (options == NULL || options->event_capacity < 2) {
        return false;
    }
    const bool checkpoints_disabled = options->checkpoint_interval == 0 &&
        options->checkpoint_capacity == 0;
    const bool checkpoints_enabled = options->checkpoint_interval != 0 &&
        options->checkpoint_capacity != 0;
    return checkpoints_disabled || checkpoints_enabled;
}

bool solver_event_trace_is_destroyed(const WangSolveTrace *trace)
{
    return trace != NULL &&
        trace->initial_domains == NULL &&
        trace->domain_count == 0 &&
        trace->events == NULL &&
        trace->event_count == 0 &&
        trace->observed_event_count == 0 &&
        trace->event_capacity == 0 &&
        !trace->truncated &&
        trace->checkpoints == NULL &&
        trace->checkpoint_domains == NULL &&
        trace->checkpoint_count == 0 &&
        trace->checkpoint_interval == 0 &&
        trace->checkpoint_capacity == 0 &&
        !trace->checkpoints_truncated;
}

void wang_solve_trace_destroy(WangSolveTrace *trace)
{
    if (trace == NULL) {
        return;
    }
    free(trace->checkpoint_domains);
    free(trace->checkpoints);
    free(trace->events);
    free(trace->initial_domains);
    *trace = (WangSolveTrace){0};
}

void wang_traced_solve_result_destroy(WangTracedSolveResult *result)
{
    if (result == NULL) {
        return;
    }
    wang_solve_result_destroy(&result->solve);
    wang_solve_trace_destroy(&result->trace);
}

void solver_event_trace_discard(SolverEventTrace *recorder)
{
    if (recorder == NULL) {
        return;
    }
    wang_solve_trace_destroy(&recorder->trace);
    *recorder = (SolverEventTrace){0};
}

bool solver_event_trace_init(
    SolverEventTrace *recorder,
    const WangSolveTraceOptions *options,
    const uint32_t *initial_domains,
    size_t domain_count
)
{
    size_t domain_bytes;
    size_t event_bytes;
    if (recorder == NULL || !solver_event_trace_options_are_valid(options) ||
        initial_domains == NULL || domain_count == 0 ||
        !checked_mul_size(domain_count, sizeof(*initial_domains), &domain_bytes) ||
        !checked_mul_size(
            options->event_capacity,
            sizeof(WangSolveTraceEvent),
            &event_bytes
        )) {
        return false;
    }

    *recorder = (SolverEventTrace){0};
    WangSolveTrace *trace = &recorder->trace;
    trace->initial_domains = malloc(domain_bytes);
    trace->events = malloc(event_bytes);
    if (trace->initial_domains == NULL || trace->events == NULL) {
        solver_event_trace_discard(recorder);
        return false;
    }

    if (options->checkpoint_capacity != 0) {
        size_t checkpoint_bytes;
        size_t checkpoint_domain_count;
        size_t checkpoint_domain_bytes;
        if (!checked_mul_size(
                options->checkpoint_capacity,
                sizeof(*trace->checkpoints),
                &checkpoint_bytes
            ) ||
            !checked_mul_size(
                options->checkpoint_capacity,
                domain_count,
                &checkpoint_domain_count
            ) ||
            !checked_mul_size(
                checkpoint_domain_count,
                sizeof(*trace->checkpoint_domains),
                &checkpoint_domain_bytes
            )) {
            solver_event_trace_discard(recorder);
            return false;
        }
        trace->checkpoints = malloc(checkpoint_bytes);
        trace->checkpoint_domains = malloc(checkpoint_domain_bytes);
        if (trace->checkpoints == NULL || trace->checkpoint_domains == NULL) {
            solver_event_trace_discard(recorder);
            return false;
        }
    }

    memcpy(trace->initial_domains, initial_domains, domain_bytes);
    trace->domain_count = domain_count;
    trace->event_capacity = options->event_capacity;
    trace->checkpoint_interval = options->checkpoint_interval;
    trace->checkpoint_capacity = options->checkpoint_capacity;
    return true;
}

static void maybe_record_checkpoint(
    SolverEventTrace *recorder,
    const WangSolveTraceEvent *event,
    const uint32_t *domains
)
{
    WangSolveTrace *trace = &recorder->trace;
    if (trace->checkpoint_interval == 0 ||
        trace->event_count % trace->checkpoint_interval != 0) {
        return;
    }
    if (trace->checkpoint_count == trace->checkpoint_capacity) {
        trace->checkpoints_truncated = true;
        return;
    }

    const size_t checkpoint = trace->checkpoint_count++;
    trace->checkpoints[checkpoint] = (WangSolveTraceCheckpoint){
        .event_sequence = event->sequence,
        .change_mark = event->change_mark,
    };
    memcpy(
        &trace->checkpoint_domains[checkpoint * trace->domain_count],
        domains,
        trace->domain_count * sizeof(*domains)
    );
}

void solver_event_trace_record(
    SolverEventTrace *recorder,
    WangSolveTraceEventKind kind,
    WangSolveTracePhase phase,
    WangSolveTraceReason reason,
    size_t depth,
    size_t cell_index,
    size_t change_mark,
    uint32_t old_domain,
    uint32_t new_domain,
    WangSolveStatus status,
    const uint32_t *domains
)
{
    if (recorder == NULL || recorder->trace.events == NULL) {
        return;
    }

    const uint64_t sequence = recorder->next_sequence++;
    WangSolveTrace *trace = &recorder->trace;
    if (recorder->frozen || trace->event_count + 1 >= trace->event_capacity) {
        recorder->frozen = true;
        trace->truncated = true;
        return;
    }

    WangSolveTraceEvent *event = &trace->events[trace->event_count++];
    *event = (WangSolveTraceEvent){
        .sequence = sequence,
        .kind = kind,
        .phase = phase,
        .reason = reason,
        .depth = depth,
        .cell_index = cell_index,
        .change_mark = change_mark,
        .old_domain = old_domain,
        .new_domain = new_domain,
        .status = status,
    };
    maybe_record_checkpoint(recorder, event, domains);
}

bool solver_event_trace_finish(
    SolverEventTrace *recorder,
    WangSolveStatus status,
    size_t depth,
    size_t cell_index,
    size_t change_mark,
    const uint32_t *domains,
    WangSolveTrace *out_trace
)
{
    if (recorder == NULL || out_trace == NULL ||
        !solver_event_trace_is_destroyed(out_trace) ||
        recorder->trace.events == NULL ||
        domains == NULL ||
        recorder->trace.event_count >= recorder->trace.event_capacity ||
        (status != WANG_SOLVE_SAT && status != WANG_SOLVE_UNSAT)) {
        return false;
    }

    WangSolveTraceEvent *event =
        &recorder->trace.events[recorder->trace.event_count++];
    *event = (WangSolveTraceEvent){
        .sequence = recorder->next_sequence++,
        .kind = WANG_TRACE_EVENT_RESULT,
        .phase = WANG_TRACE_PHASE_NONE,
        .reason = WANG_TRACE_REASON_NONE,
        .depth = depth,
        .cell_index = cell_index,
        .change_mark = change_mark,
        .status = status,
    };
    if (!recorder->trace.truncated) {
        maybe_record_checkpoint(recorder, event, domains);
    }
    recorder->trace.observed_event_count = recorder->next_sequence;
    *out_trace = recorder->trace;
    *recorder = (SolverEventTrace){0};
    return true;
}
