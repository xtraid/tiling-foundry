#ifndef WANG_SOLVER_TRACE_H
#define WANG_SOLVER_TRACE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "wang/solver.h"

/* Stable semantic events emitted by the opt-in native solver trace. */
typedef enum {
    WANG_TRACE_EVENT_ROOT,
    WANG_TRACE_EVENT_PROPAGATION,
    WANG_TRACE_EVENT_DECISION,
    WANG_TRACE_EVENT_DOMAIN_REDUCTION,
    WANG_TRACE_EVENT_CONFLICT,
    WANG_TRACE_EVENT_BACKTRACK,
    WANG_TRACE_EVENT_RESULT
} WangSolveTraceEventKind;

typedef enum {
    WANG_TRACE_PHASE_NONE,
    WANG_TRACE_PHASE_INITIAL,
    WANG_TRACE_PHASE_SEARCH
} WangSolveTracePhase;

typedef enum {
    WANG_TRACE_REASON_NONE,
    WANG_TRACE_REASON_DECISION,
    WANG_TRACE_REASON_PROPAGATION
} WangSolveTraceReason;

/*
 * One observed solver event. sequence is the event's ordinal in the complete
 * run, so the final result may follow a gap when the bounded prefix truncated.
 * Non-applicable scalar fields use zero, SIZE_MAX, or WANG_SOLVE_ERROR as
 * described by the event kind. Domains are canonical TILESET bitmasks.
 */
typedef struct {
    uint64_t sequence;
    WangSolveTraceEventKind kind;
    WangSolveTracePhase phase;
    WangSolveTraceReason reason;
    size_t depth;
    size_t cell_index;
    size_t change_mark;
    uint32_t old_domain;
    uint32_t new_domain;
    WangSolveStatus status;
} WangSolveTraceEvent;

/* Full state captured after one recorded event for bounded random access. */
typedef struct {
    uint64_t event_sequence;
    size_t change_mark;
} WangSolveTraceCheckpoint;

typedef struct {
    /* At least two slots: the root event and the reserved terminal result. */
    size_t event_capacity;

    /* Both zero disables checkpoints; otherwise both values must be positive. */
    size_t checkpoint_interval;
    size_t checkpoint_capacity;
} WangSolveTraceOptions;

/*
 * Caller-owned immutable trace published only after a successful solve call.
 * initial_domains is the full state after root-domain initialization and before
 * arc propagation. Each checkpoint owns one dense domain_count-sized row in
 * checkpoint_domains, parallel to checkpoints.
 */
typedef struct {
    uint32_t *initial_domains;
    size_t domain_count;

    WangSolveTraceEvent *events;
    size_t event_count;
    uint64_t observed_event_count;
    size_t event_capacity;
    bool truncated;

    WangSolveTraceCheckpoint *checkpoints;
    uint32_t *checkpoint_domains;
    size_t checkpoint_count;
    size_t checkpoint_interval;
    size_t checkpoint_capacity;
    bool checkpoints_truncated;
} WangSolveTrace;

/* One joint lifetime for the ordinary solve result and its opt-in trace. */
typedef struct {
    WangSolveResult solve;
    WangSolveTrace trace;
} WangTracedSolveResult;

/*
 * Traced entry points share the exact solver implementations used by the
 * standard functions. solver_options may be NULL. trace_options is required.
 * out_result must be zero-initialized or destroyed. ERROR is transactional.
 */
WangSolveStatus wang_solve_serial_traced(
    const Region *region,
    const WangSolverOptions *solver_options,
    const WangSolveTraceOptions *trace_options,
    WangTracedSolveResult *out_result
);

WangSolveStatus wang_solve_optimized_traced(
    const Region *region,
    const WangSolverOptions *solver_options,
    const WangSolveTraceOptions *trace_options,
    WangTracedSolveResult *out_result
);

/* Release every owned trace allocation and reset all fields. Accepts NULL. */
void wang_solve_trace_destroy(WangSolveTrace *trace);

/* Release solve and trace storage and reset all fields. Accepts NULL. */
void wang_traced_solve_result_destroy(WangTracedSolveResult *result);

#endif /* WANG_SOLVER_TRACE_H */
