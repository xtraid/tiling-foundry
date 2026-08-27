#include "wang/yang_zhang.h"

#include <stdlib.h>

static bool reduction_is_destroyed(const YangZhangReduction *reduction)
{
    return reduction != NULL
        && reduction->region.width == 0
        && reduction->region.height == 0
        && reduction->region.cell_count == 0
        && reduction->region.cells == NULL
        && reduction->swaps == NULL
        && reduction->swap_count == 0
        && reduction->explanation.source_signals == NULL
        && reduction->explanation.target_signals == NULL
        && reduction->explanation.signal_count == 0
        && reduction->explanation.gadgets == NULL
        && reduction->explanation.gadget_count == 0;
}

static bool build_reduction_explanation(
    const Cm13Formula *formula,
    SignalToken *source,
    SignalToken *target,
    size_t signal_count,
    const AdjacentSwap *swaps,
    size_t swap_count,
    int32_t width,
    int32_t height,
    ReductionExplanation *out_explanation
)
{
    const size_t variable_count = formula->variable_count;

    if (variable_count > (SIZE_MAX - 2u) / 2u) {
        return false;
    }

    const size_t fixed_gadget_count = 2u * variable_count + 2u;
    if (swap_count > SIZE_MAX - fixed_gadget_count) {
        return false;
    }

    const size_t gadget_count = fixed_gadget_count + swap_count;
    if (gadget_count > SIZE_MAX / sizeof(*out_explanation->gadgets)) {
        return false;
    }

    ReductionGadgetSpan *gadgets = malloc(
        gadget_count * sizeof(*gadgets)
    );
    if (gadgets == NULL) {
        return false;
    }

    size_t gadget_index = 0;
    for (uint32_t variable = 0;
         variable < formula->variable_count;
         ++variable) {
        const int32_t first_y = (int32_t)(4u * variable);
        gadgets[gadget_index++] = (ReductionGadgetSpan){
            .kind = REDUCTION_GADGET_VARIABLE,
            .ordinal = variable,
            .x_begin = 0,
            .x_end = (int32_t)YANG_ZHANG_VARIABLE_WIDTH,
            .y_begin = first_y,
            .y_end = first_y + 3,
            .swap_row = REDUCTION_NO_SWAP_ROW
        };
    }

    const int32_t left_begin = (int32_t)YANG_ZHANG_VARIABLE_WIDTH;
    const int32_t crossover_begin = left_begin +
        (int32_t)YANG_ZHANG_LEFT_FORWARD_WIDTH;
    gadgets[gadget_index++] = (ReductionGadgetSpan){
        .kind = REDUCTION_GADGET_LEFT_FORWARD,
        .ordinal = 0,
        .x_begin = left_begin,
        .x_end = crossover_begin,
        .y_begin = 0,
        .y_end = height,
        .swap_row = REDUCTION_NO_SWAP_ROW
    };

    int32_t block_x = crossover_begin;
    for (size_t swap = 0; swap < swap_count; ++swap) {
        const int32_t block_width = (int32_t)swaps[swap].row + 1;
        gadgets[gadget_index++] = (ReductionGadgetSpan){
            .kind = REDUCTION_GADGET_CROSSOVER,
            .ordinal = (uint32_t)swap,
            .x_begin = block_x,
            .x_end = block_x + block_width,
            .y_begin = 0,
            .y_end = height,
            .swap_row = swaps[swap].row
        };
        block_x += block_width;
    }

    const int32_t right_end = block_x +
        (int32_t)YANG_ZHANG_RIGHT_FORWARD_WIDTH;
    gadgets[gadget_index++] = (ReductionGadgetSpan){
        .kind = REDUCTION_GADGET_RIGHT_FORWARD,
        .ordinal = 0,
        .x_begin = block_x,
        .x_end = right_end,
        .y_begin = 0,
        .y_end = height,
        .swap_row = REDUCTION_NO_SWAP_ROW
    };

    for (size_t clause = 0; clause < formula->clause_count; ++clause) {
        const int32_t first_y = (int32_t)(4u * clause);
        const int32_t y_end = clause + 1u < formula->clause_count
            ? first_y + 4
            : height;
        gadgets[gadget_index++] = (ReductionGadgetSpan){
            .kind = REDUCTION_GADGET_CLAUSE,
            .ordinal = (uint32_t)clause,
            .x_begin = right_end,
            .x_end = width,
            .y_begin = first_y,
            .y_end = y_end,
            .swap_row = REDUCTION_NO_SWAP_ROW
        };
    }

    if (gadget_index != gadget_count) {
        free(gadgets);
        return false;
    }

    *out_explanation = (ReductionExplanation){
        .source_signals = source,
        .target_signals = target,
        .signal_count = signal_count,
        .gadgets = gadgets,
        .gadget_count = gadget_count
    };
    return true;
}

static bool formula_is_in_reduction_domain(const Cm13Formula *formula)
{
    if (formula == NULL ||
        formula->clauses == NULL ||
        formula->variable_count == 0 ||
        formula->variable_count > YANG_ZHANG_MAX_VARIABLES ||
        formula->clause_count != (size_t)formula->variable_count) {
        return false;
    }

    uint8_t *occurrence_counts = calloc(
        (size_t)formula->variable_count,
        sizeof(*occurrence_counts)
    );
    if (occurrence_counts == NULL) {
        return false;
    }

    bool valid = true;

    for (size_t clause_index = 0;
         clause_index < formula->clause_count && valid;
         ++clause_index) {
        for (size_t row = 0; row < 3; ++row) {
            const uint32_t variable_index =
                formula->clauses[clause_index].variable_index[row];

            if (variable_index >= formula->variable_count ||
                occurrence_counts[variable_index] == 3) {
                valid = false;
                break;
            }

            ++occurrence_counts[variable_index];
        }
    }

    for (uint32_t i = 0; i < formula->variable_count && valid; ++i) {
        if (occurrence_counts[i] != 3) {
            valid = false;
        }
    }

    free(occurrence_counts);
    return valid;
}

static bool build_signal_sequences(
    const Cm13Formula *formula,
    SignalToken **out_source,
    SignalToken **out_target,
    size_t *out_signal_count
)
{
    const size_t variable_count = formula->variable_count;
    const size_t signal_count = 4u * variable_count - 1u;
    SignalToken *source = NULL;
    SignalToken *target = NULL;
    uint8_t *next_occurrence = NULL;

    if (signal_count > SIZE_MAX / sizeof(*source)) {
        return false;
    }

    source = malloc(signal_count * sizeof(*source));
    target = malloc(signal_count * sizeof(*target));
    next_occurrence = calloc(variable_count, sizeof(*next_occurrence));
    if (source == NULL || target == NULL || next_occurrence == NULL) {
        goto fail;
    }

    size_t source_index = 0;
    for (uint32_t variable = 0;
         variable < formula->variable_count;
         ++variable) {
        for (uint8_t occurrence = 0; occurrence < 3; ++occurrence) {
            source[source_index++] = (SignalToken){
                .kind = SIGNAL_VARIABLE,
                .token_id = 3u * variable + occurrence,
                .variable = variable,
                .occurrence = occurrence
            };
        }
        if (variable + 1u < formula->variable_count) {
            source[source_index++] = (SignalToken){
                .kind = SIGNAL_REDUNDANT,
                .token_id = 3u * formula->variable_count + variable
            };
        }
    }

    size_t target_index = 0;
    for (size_t clause = 0; clause < formula->clause_count; ++clause) {
        for (size_t row = 0; row < 3; ++row) {
            const uint32_t variable =
                formula->clauses[clause].variable_index[row];
            const uint8_t occurrence = next_occurrence[variable]++;

            target[target_index++] = (SignalToken){
                .kind = SIGNAL_VARIABLE,
                .token_id = 3u * variable + occurrence,
                .variable = variable,
                .occurrence = occurrence
            };
        }
        if (clause + 1u < formula->clause_count) {
            target[target_index++] = (SignalToken){
                .kind = SIGNAL_REDUNDANT,
                .token_id = 3u * formula->variable_count + (uint32_t)clause
            };
        }
    }

    free(next_occurrence);
    *out_source = source;
    *out_target = target;
    *out_signal_count = signal_count;
    return true;

fail:
    free(next_occurrence);
    free(target);
    free(source);
    return false;
}

/*
 * The paper's clause area contains one, two, two, then zero cells in each
 * four-row group. The returned column includes every band to its left.
 */
static int32_t last_active_x(const Region *region, int32_t y)
{
    switch (y % 4) {
    case 0:
        return region->width - 2;
    case 1:
    case 2:
        return region->width - 1;
    case 3:
        return region->width - 3;
    }

    return -1;
}

static bool activate_paper_region(Region *region)
{
    for (int32_t y = 0; y < region->height; ++y) {
        const int32_t row_end = last_active_x(region, y);
        for (int32_t x = 0; x <= row_end; ++x) {
            if (!region_set_active(region, x, y, true)) {
                return false;
            }
        }
    }

    return true;
}

static bool paint_exposed_boundary(Region *region)
{
    static const int32_t dx[DIR_COUNT] = { 0, 1, 0, -1 };
    static const int32_t dy[DIR_COUNT] = { -1, 0, 1, 0 };

    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            const RegionCell *cell = region_cell_const(region, x, y);
            if (cell == NULL || !cell->active) {
                continue;
            }

            for (Dir dir = N; dir < DIR_COUNT; ++dir) {
                const RegionCell *neighbor = region_cell_const(
                    region,
                    x + dx[dir],
                    y + dy[dir]
                );
                if ((neighbor == NULL || !neighbor->active) &&
                    !region_set_boundary(region, x, y, dir, COLOR_B)) {
                    return false;
                }
            }
        }
    }

    return true;
}

static bool paint_variable_boundary(
    Region *region,
    uint32_t variable_count
)
{
    for (uint32_t variable = 0; variable < variable_count; ++variable) {
        const int32_t first_y = (int32_t)(4u * variable);

        for (int32_t row = 0; row < 3; ++row) {
            if (!region_set_boundary(
                    region,
                    0,
                    first_y + row,
                    W,
                    COLOR_V
                )) {
                return false;
            }
        }

        if (variable + 1u < variable_count &&
            !region_set_boundary(region, 0, first_y + 3, W, COLOR_0)) {
            return false;
        }
    }

    return true;
}

static bool paint_clause_boundary(Region *region, size_t clause_count)
{
    const int32_t inner_x = region->width - 2;
    const int32_t outer_x = region->width - 1;

    for (size_t clause = 0; clause < clause_count; ++clause) {
        const int32_t first_y = (int32_t)(4u * clause);

        if (!region_set_boundary(
                region,
                inner_x,
                first_y,
                E,
                COLOR_0_PRIME
            ) ||
            !region_set_boundary(
                region,
                outer_x,
                first_y + 1,
                E,
                COLOR_0_PRIME
            ) ||
            !region_set_boundary(
                region,
                outer_x,
                first_y + 2,
                E,
                COLOR_1
            )) {
            return false;
        }

        if (clause + 1u < clause_count &&
            !region_set_boundary(
                region,
                inner_x - 1,
                first_y + 3,
                E,
                COLOR_0
            )) {
            return false;
        }
    }

    return true;
}

static bool paint_crossover_boundaries(
    Region *region,
    int32_t first_x,
    const AdjacentSwap *swaps,
    size_t swap_count
)
{
    int32_t block_x = first_x;

    for (size_t i = 0; i < swap_count; ++i) {
        const int32_t block_width = (int32_t)swaps[i].row + 1;

        if (!region_set_boundary(
                region,
                block_x + block_width - 1,
                0,
                N,
                COLOR_R
            ) ||
            !region_set_boundary(
                region,
                block_x,
                region->height - 1,
                S,
                COLOR_L
            )) {
            return false;
        }

        block_x += block_width;
    }

    return true;
}

static bool yang_zhang_build_internal(
    const Cm13Formula *formula,
    YangZhangReduction *out_reduction,
    bool include_explanation
)
{
    SignalToken *source = NULL;
    SignalToken *target = NULL;
    size_t signal_count = 0;
    AdjacentSwap *swaps = NULL;
    size_t swap_count = 0;
    int32_t height = 0;
    int32_t width = 0;
    Region region = {0};
    ReductionExplanation explanation = {0};

    if (!reduction_is_destroyed(out_reduction) ||
        !formula_is_in_reduction_domain(formula)) {
        return false;
    }

    if (!build_signal_sequences(
            formula,
            &source,
            &target,
            &signal_count
        ) ||
        !yang_zhang_permutation_build(
            source,
            target,
            signal_count,
            &swaps,
            &swap_count
        )) {
        free(target);
        free(source);
        return false;
    }

    if (!yang_zhang_compute_dimensions(
            formula->variable_count,
            swaps,
            swap_count,
            &height,
            &width
        ) ||
        !region_init(&region, width, height) ||
        !activate_paper_region(&region) ||
        !paint_exposed_boundary(&region) ||
        !paint_variable_boundary(&region, formula->variable_count) ||
        !paint_clause_boundary(&region, formula->clause_count) ||
        !paint_crossover_boundaries(
            &region,
            (int32_t)(YANG_ZHANG_VARIABLE_WIDTH +
                      YANG_ZHANG_LEFT_FORWARD_WIDTH),
            swaps,
            swap_count
        ) ||
        (include_explanation && !build_reduction_explanation(
            formula,
            source,
            target,
            signal_count,
            swaps,
            swap_count,
            width,
            height,
            &explanation
        ))) {
        region_destroy(&region);
        free(swaps);
        free(target);
        free(source);
        return false;
    }

    out_reduction->region = region;
    out_reduction->swaps = swaps;
    out_reduction->swap_count = swap_count;
    out_reduction->explanation = explanation;
    if (!include_explanation) {
        free(target);
        free(source);
    }
    return true;
}

bool yang_zhang_build(
    const Cm13Formula *formula,
    YangZhangReduction *out_reduction
)
{
    return yang_zhang_build_internal(formula, out_reduction, false);
}

bool yang_zhang_build_explained(
    const Cm13Formula *formula,
    YangZhangReduction *out_reduction
)
{
    return yang_zhang_build_internal(formula, out_reduction, true);
}

void yang_zhang_reduction_destroy(YangZhangReduction *reduction)
{
    if (reduction == NULL) {
        return;
    }

    region_destroy(&reduction->region);
    free(reduction->swaps);
    reduction->swaps = NULL;
    reduction->swap_count = 0;
    free(reduction->explanation.gadgets);
    free(reduction->explanation.target_signals);
    free(reduction->explanation.source_signals);
    reduction->explanation = (ReductionExplanation){0};
}

bool yang_zhang_compute_dimensions(
    uint32_t variable_count,
    const AdjacentSwap *swaps,
    size_t swap_count,
    int32_t *out_height,
    int32_t *out_width
)
{
    if (out_height == NULL || out_width == NULL) {
        return false;
    }

    if (variable_count == 0 ||
        variable_count > YANG_ZHANG_MAX_VARIABLES ||
        (swap_count > 0 && swaps == NULL)) {
        return false;
    }

    const uint64_t height =
        4u * (uint64_t)variable_count - 1u;

    if (height > (uint64_t)INT32_MAX) {
        return false;
    }

    /*
     * Coarse layout used by this project:
     *
     * [V] [FF] [ crossover chain ] [FF] [clauses]
     *
     * The two forwarder bands are a project convention for clearer,
     * explicit signal entry/exit boundaries. They are not presented as
     * a mathematical necessity of the Yang-Zhang construction.
     */
    uint64_t width =
        (uint64_t)YANG_ZHANG_VARIABLE_WIDTH +
        (uint64_t)YANG_ZHANG_LEFT_FORWARD_WIDTH +
        (uint64_t)YANG_ZHANG_RIGHT_FORWARD_WIDTH +
        (uint64_t)YANG_ZHANG_CLAUSE_WIDTH;

    for (size_t i = 0; i < swap_count; ++i) {
        /*
         * row is 0-based and swaps row with row + 1.
         * The final row therefore cannot be used as swap.row.
         */
        if ((uint64_t)swaps[i].row >= height - 1u) {
            return false;
        }

        /*
         * Yang-Zhang paper convention:
         * crossover width w swaps rows w and w + 1 (1-based).
         *
         * C zero-based row = w - 1, hence width = row + 1.
         */
        const uint64_t block_width =
            (uint64_t)swaps[i].row + 1u;

        if (width > (uint64_t)INT32_MAX ||
            block_width > (uint64_t)INT32_MAX - width) {
            return false;
        }

        width += block_width;
    }

    if (width > (uint64_t)INT32_MAX) {
        return false;
    }

    *out_height = (int32_t)height;
    *out_width = (int32_t)width;
    return true;
}
