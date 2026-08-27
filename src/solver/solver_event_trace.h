#ifndef WANG_SOLVER_EVENT_TRACE_H
#define WANG_SOLVER_EVENT_TRACE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "wang/solver_trace.h"

typedef struct {
    WangSolveTrace trace;
    uint64_t next_sequence;
    bool frozen;
} SolverEventTrace;

bool solver_event_trace_options_are_valid(
    const WangSolveTraceOptions *options
);

bool solver_event_trace_is_destroyed(const WangSolveTrace *trace);

bool solver_event_trace_init(
    SolverEventTrace *recorder,
    const WangSolveTraceOptions *options,
    const uint32_t *initial_domains,
    size_t domain_count
);

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
);

bool solver_event_trace_finish(
    SolverEventTrace *recorder,
    WangSolveStatus status,
    size_t depth,
    size_t cell_index,
    size_t change_mark,
    const uint32_t *domains,
    WangSolveTrace *out_trace
);

void solver_event_trace_discard(SolverEventTrace *recorder);

#endif /* WANG_SOLVER_EVENT_TRACE_H */
