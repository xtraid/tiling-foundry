#ifndef WANG_YANG_ZHANG_H
#define WANG_YANG_ZHANG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "wang/formula.h"
#include "wang/permutation.h"
#include "wang/reduction_explanation.h"
#include "wang/region.h"

/*
 * Result of a Yang-Zhang reduction build.
 *
 * On successful construction, the caller owns region.cells and swaps. The
 * explained builder additionally owns the storage borrowed through
 * explanation. Initialize this object to zero before use and release every
 * owned allocation with yang_zhang_reduction_destroy().
 */
typedef struct {
    Region region;

    AdjacentSwap *swaps;
    size_t swap_count;

    ReductionExplanation explanation;
} YangZhangReduction;

/*
 * Build the colored region and adjacent-swap trace for a canonical CM1-in-3
 * formula. The formula is borrowed and is never modified. This standard path
 * leaves explanation destroyed and performs no provenance allocation.
 *
 * The output must be zero-initialized or previously destroyed. Construction
 * is transactional: on failure, the output remains in the destroyed state.
 */
bool yang_zhang_build(
    const Cm13Formula *formula,
    YangZhangReduction *out_reduction
);

/*
 * Build the same region and swap trace while also retaining immutable signal
 * and gadget provenance. Geometry and swap generation share the standard
 * implementation; this opt-in entry point only changes explanation ownership.
 */
bool yang_zhang_build_explained(
    const Cm13Formula *formula,
    YangZhangReduction *out_reduction
);

/* Release all owned storage and reset every field. Accepts NULL. */
void yang_zhang_reduction_destroy(YangZhangReduction *reduction);

/*
 * Yang-Zhang layout conventions used by this project.
 *
 * Paper geometry:
 *   - signal height = 4n - 1
 *   - a paper crossover of width w swaps rows w and w + 1 (1-based)
 *
 * C representation:
 *   AdjacentSwap.row = w - 1
 *   crossover width  = row + 1
 *
 * Project convention:
 *   two forwarder columns are kept before and after the crossover chain.
 *   They are NOT claimed to be mandatory in the paper; they are explicit
 *   neutral signal-propagation bands used to make gadget boundaries and
 *   signal entry/exit points easier to inspect.
 */
#define YANG_ZHANG_MAX_VARIABLES \
    ((uint32_t)((((uint64_t)INT32_MAX) + 1u) / 4u))

#define YANG_ZHANG_VARIABLE_WIDTH       1u
#define YANG_ZHANG_LEFT_FORWARD_WIDTH   2u
#define YANG_ZHANG_RIGHT_FORWARD_WIDTH  2u
#define YANG_ZHANG_CLAUSE_WIDTH         2u

/*
 * Compute the dimensions of the coarse project layout.
 *
 * On success:
 *
 *   height = 4 * variable_count - 1
 *
 *   width =
 *       YANG_ZHANG_VARIABLE_WIDTH
 *     + YANG_ZHANG_LEFT_FORWARD_WIDTH
 *     + sum(swaps[i].row + 1)
 *     + YANG_ZHANG_RIGHT_FORWARD_WIDTH
 *     + YANG_ZHANG_CLAUSE_WIDTH
 *
 * The swap sequence is borrowed for the duration of this call. It is never
 * copied, modified, or released here.
 */
bool yang_zhang_compute_dimensions(
    uint32_t variable_count,
    const AdjacentSwap *swaps,
    size_t swap_count,
    int32_t *out_height,
    int32_t *out_width
);

#endif /* WANG_YANG_ZHANG_H */
