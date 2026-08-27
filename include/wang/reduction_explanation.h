#ifndef WANG_REDUCTION_EXPLANATION_H
#define WANG_REDUCTION_EXPLANATION_H

#include <stddef.h>
#include <stdint.h>

#include "wang/permutation.h"

/*
 * Semantic kinds of the coarse Yang-Zhang gadgets built into a Region.
 * These values describe construction provenance; solvers never consume them.
 */
typedef enum {
    REDUCTION_GADGET_VARIABLE,
    REDUCTION_GADGET_LEFT_FORWARD,
    REDUCTION_GADGET_CROSSOVER,
    REDUCTION_GADGET_RIGHT_FORWARD,
    REDUCTION_GADGET_CLAUSE
} ReductionGadgetKind;

#define REDUCTION_NO_SWAP_ROW UINT32_MAX

/*
 * One half-open rectangle [x_begin, x_end) x [y_begin, y_end).
 *
 * ordinal identifies the variable, clause, or adjacent swap for those gadget
 * kinds. Both forwarder bands use ordinal zero. swap_row is meaningful only
 * for REDUCTION_GADGET_CROSSOVER and otherwise equals
 * REDUCTION_NO_SWAP_ROW.
 */
typedef struct {
    ReductionGadgetKind kind;
    uint32_t ordinal;
    int32_t x_begin;
    int32_t x_end;
    int32_t y_begin;
    int32_t y_end;
    uint32_t swap_row;
} ReductionGadgetSpan;

/*
 * Immutable construction provenance owned by a successful
 * YangZhangExplainedReduction returned by yang_zhang_build_explained().
 *
 * source_signals and target_signals are the exact sequences passed to the
 * permutation builder. Their array index is the zero-based signal row.
 * gadgets records the coarse rectangles actually used to build the Region.
 * Callers borrow every pointer and must not modify or release this storage.
 */
typedef struct {
    SignalToken *source_signals;
    SignalToken *target_signals;
    size_t signal_count;

    ReductionGadgetSpan *gadgets;
    size_t gadget_count;
} ReductionExplanation;

#endif /* WANG_REDUCTION_EXPLANATION_H */
