#include "wang/formula.h"
#include "wang/yang_zhang.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ARRAY_COUNT(array) (sizeof(array) / sizeof((array)[0]))

static void test_reduction_destroy_accepts_null_and_empty(void)
{
    YangZhangReduction reduction = {0};

    yang_zhang_reduction_destroy(NULL);
    yang_zhang_reduction_destroy(&reduction);

    assert(reduction.region.width == 0);
    assert(reduction.region.height == 0);
    assert(reduction.region.cell_count == 0);
    assert(reduction.region.cells == NULL);
    assert(reduction.swaps == NULL);
    assert(reduction.swap_count == 0);
    assert(reduction.explanation.source_signals == NULL);
    assert(reduction.explanation.target_signals == NULL);
    assert(reduction.explanation.signal_count == 0);
    assert(reduction.explanation.gadgets == NULL);
    assert(reduction.explanation.gadget_count == 0);
}

static void test_reduction_destroy_releases_and_resets_owned_storage(void)
{
    YangZhangReduction reduction = {0};

    assert(region_init(&reduction.region, 2, 3));

    reduction.swaps = malloc(2 * sizeof(*reduction.swaps));
    assert(reduction.swaps != NULL);
    reduction.swap_count = 2;
    reduction.explanation.source_signals = malloc(
        3 * sizeof(*reduction.explanation.source_signals)
    );
    reduction.explanation.target_signals = malloc(
        3 * sizeof(*reduction.explanation.target_signals)
    );
    reduction.explanation.gadgets = malloc(
        4 * sizeof(*reduction.explanation.gadgets)
    );
    assert(reduction.explanation.source_signals != NULL);
    assert(reduction.explanation.target_signals != NULL);
    assert(reduction.explanation.gadgets != NULL);
    reduction.explanation.signal_count = 3;
    reduction.explanation.gadget_count = 4;

    yang_zhang_reduction_destroy(&reduction);

    assert(reduction.region.width == 0);
    assert(reduction.region.height == 0);
    assert(reduction.region.cell_count == 0);
    assert(reduction.region.cells == NULL);
    assert(reduction.swaps == NULL);
    assert(reduction.swap_count == 0);
    assert(reduction.explanation.source_signals == NULL);
    assert(reduction.explanation.target_signals == NULL);
    assert(reduction.explanation.signal_count == 0);
    assert(reduction.explanation.gadgets == NULL);
    assert(reduction.explanation.gadget_count == 0);

    /* A destroyed reduction can be destroyed repeatedly. */
    yang_zhang_reduction_destroy(&reduction);
}

static Cm13Formula one_variable_formula(Cm13Clause clauses[1])
{
    clauses[0] = (Cm13Clause){ .variable_index = { 0, 0, 0 } };

    return (Cm13Formula){
        .variable_count = 1,
        .clauses = clauses,
        .clause_count = 1
    };
}

static void assert_reduction_destroyed(const YangZhangReduction *reduction)
{
    assert(reduction->region.width == 0);
    assert(reduction->region.height == 0);
    assert(reduction->region.cell_count == 0);
    assert(reduction->region.cells == NULL);
    assert(reduction->swaps == NULL);
    assert(reduction->swap_count == 0);
    assert(reduction->explanation.source_signals == NULL);
    assert(reduction->explanation.target_signals == NULL);
    assert(reduction->explanation.signal_count == 0);
    assert(reduction->explanation.gadgets == NULL);
    assert(reduction->explanation.gadget_count == 0);
}

static ColorId expected_clause_color(int32_t y)
{
    switch (y % 4) {
    case 0:
    case 1:
        return COLOR_0_PRIME;
    case 2:
        return COLOR_1;
    case 3:
        return COLOR_0;
    }

    assert(false);
    return COLOR_NONE;
}

static int32_t expected_last_active_x(const Region *region, int32_t y)
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

    assert(false);
    return -1;
}

static bool expected_active(const Region *region, int32_t x, int32_t y)
{
    return x <= expected_last_active_x(region, y);
}

static ColorId expected_boundary(
    const Region *region,
    const bool *top_is_r,
    const bool *bottom_is_l,
    int32_t x,
    int32_t y,
    Dir dir
)
{
    static const int32_t dx[DIR_COUNT] = { 0, 1, 0, -1 };
    static const int32_t dy[DIR_COUNT] = { -1, 0, 1, 0 };
    const int32_t neighbor_x = x + dx[dir];
    const int32_t neighbor_y = y + dy[dir];
    const bool exposed = neighbor_x < 0 || neighbor_x >= region->width ||
        neighbor_y < 0 || neighbor_y >= region->height ||
        !expected_active(region, neighbor_x, neighbor_y);

    ColorId color = exposed ? COLOR_B : COLOR_NONE;
    if (dir == N && y == 0 && top_is_r[x]) {
        color = COLOR_R;
    } else if (dir == S && y == region->height - 1 && bottom_is_l[x]) {
        color = COLOR_L;
    } else if (dir == W && x == 0) {
        color = y % 4 == 3 ? COLOR_0 : COLOR_V;
    } else if (dir == E && x == expected_last_active_x(region, y)) {
        color = expected_clause_color(y);
    }

    return color;
}

static void assert_region_encoding(
    const Region *region,
    const bool *top_is_r,
    const bool *bottom_is_l
)
{
    assert(region_validate(region));

    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            const RegionCell *cell = region_cell_const(region, x, y);
            assert(cell != NULL);
            assert(cell->active == expected_active(region, x, y));

            for (Dir dir = N; dir < DIR_COUNT; ++dir) {
                const ColorId expected = cell->active
                    ? expected_boundary(
                        region,
                        top_is_r,
                        bottom_is_l,
                        x,
                        y,
                        dir
                    )
                    : COLOR_NONE;
                assert(cell->boundary[dir] == expected);
            }
        }
    }
}

static SignalToken variable_token(uint32_t variable, uint8_t occurrence)
{
    return (SignalToken){
        .kind = SIGNAL_VARIABLE,
        .token_id = 3u * variable + occurrence,
        .variable = variable,
        .occurrence = occurrence
    };
}

static SignalToken redundant_token(uint32_t variable_count, uint32_t index)
{
    return (SignalToken){
        .kind = SIGNAL_REDUNDANT,
        .token_id = 3u * variable_count + index
    };
}

static bool tokens_equal(const SignalToken *left, const SignalToken *right)
{
    return left->kind == right->kind &&
        left->token_id == right->token_id &&
        (left->kind == SIGNAL_REDUNDANT ||
         (left->variable == right->variable &&
          left->occurrence == right->occurrence));
}

static void assert_gadget_span(
    const ReductionGadgetSpan *gadget,
    ReductionGadgetKind kind,
    uint32_t ordinal,
    int32_t x_begin,
    int32_t x_end,
    int32_t y_begin,
    int32_t y_end,
    uint32_t swap_row
)
{
    assert(gadget->kind == kind);
    assert(gadget->ordinal == ordinal);
    assert(gadget->x_begin == x_begin);
    assert(gadget->x_end == x_end);
    assert(gadget->y_begin == y_begin);
    assert(gadget->y_end == y_end);
    assert(gadget->swap_row == swap_row);
}

static void assert_build_rejected(const Cm13Formula *formula)
{
    YangZhangReduction reduction = {0};

    assert(!yang_zhang_build(formula, &reduction));
    assert_reduction_destroyed(&reduction);
}

static void test_build_rejects_null_arguments(void)
{
    Cm13Clause clauses[1];
    Cm13Formula formula = one_variable_formula(clauses);
    YangZhangReduction reduction = {0};

    assert(!yang_zhang_build(NULL, &reduction));
    assert_reduction_destroyed(&reduction);
    assert(!yang_zhang_build(&formula, NULL));
}

static void test_build_rejects_invalid_formula_domain(void)
{
    Cm13Clause clauses[2] = {
        { .variable_index = { 0, 0, 0 } },
        { .variable_index = { 1, 1, 1 } }
    };
    Cm13Formula formula = {
        .variable_count = 2,
        .clauses = clauses,
        .clause_count = 2
    };

    formula.variable_count = 0;
    assert_build_rejected(&formula);
    formula.variable_count = 2;

    formula.clauses = NULL;
    assert_build_rejected(&formula);
    formula.clauses = clauses;

    formula.clause_count = 1;
    assert_build_rejected(&formula);
    formula.clause_count = 2;

    clauses[1].variable_index[2] = 2;
    assert_build_rejected(&formula);
    clauses[1].variable_index[2] = 1;

    clauses[0].variable_index[2] = 1;
    assert_build_rejected(&formula);
    clauses[0].variable_index[2] = 0;

    clauses[1].variable_index[0] = 0;
    assert_build_rejected(&formula);
}

static void test_build_rejects_variable_count_overflow(void)
{
    Cm13Clause clause = { .variable_index = { 0, 0, 0 } };
    const Cm13Formula formula = {
        .variable_count = YANG_ZHANG_MAX_VARIABLES + 1u,
        .clauses = &clause,
        .clause_count = (size_t)YANG_ZHANG_MAX_VARIABLES + 1u
    };

    assert_build_rejected(&formula);
}

static void test_failed_build_does_not_modify_formula_storage(void)
{
    Cm13Clause clauses[2] = {
        { .variable_index = { 0, 0, 0 } },
        { .variable_index = { 1, 1, 0 } }
    };
    const Cm13Clause clauses_before[2] = {
        { .variable_index = { 0, 0, 0 } },
        { .variable_index = { 1, 1, 0 } }
    };
    const Cm13Formula formula = {
        .variable_count = 2,
        .clauses = clauses,
        .clause_count = 2
    };

    assert_build_rejected(&formula);
    assert(memcmp(clauses, clauses_before, sizeof(clauses)) == 0);
}

static void test_build_rejects_non_destroyed_output(void)
{
    Cm13Clause clauses[1];
    Cm13Formula formula = one_variable_formula(clauses);
    YangZhangReduction reduction = {
        .region = { .width = 1, .height = 0, .cells = NULL },
        .swaps = NULL,
        .swap_count = 0
    };

    assert(!yang_zhang_build(&formula, &reduction));
    assert(reduction.region.width == 1);
}

static void test_build_minimal_valid_formula_with_explanation(void)
{
    Cm13Clause clauses[1];
    Cm13Formula formula = one_variable_formula(clauses);
    const Cm13Clause clauses_before[1] = { clauses[0] };
    YangZhangReduction reduction = {0};
    const bool top_is_r[7] = {false};
    const bool bottom_is_l[7] = {false};

    assert(yang_zhang_build_explained(&formula, &reduction));
    assert(reduction.region.width == 7);
    assert(reduction.region.height == 3);
    assert(reduction.swaps == NULL);
    assert(reduction.swap_count == 0);
    assert(reduction.explanation.signal_count == 3);
    assert(reduction.explanation.source_signals != NULL);
    assert(reduction.explanation.target_signals != NULL);
    for (uint8_t occurrence = 0; occurrence < 3; ++occurrence) {
        const SignalToken expected = variable_token(0, occurrence);
        assert(tokens_equal(
            &reduction.explanation.source_signals[occurrence],
            &expected
        ));
        assert(tokens_equal(
            &reduction.explanation.target_signals[occurrence],
            &expected
        ));
    }
    assert(reduction.explanation.gadget_count == 4);
    assert_gadget_span(
        &reduction.explanation.gadgets[0],
        REDUCTION_GADGET_VARIABLE,
        0,
        0,
        1,
        0,
        3,
        REDUCTION_NO_SWAP_ROW
    );
    assert_gadget_span(
        &reduction.explanation.gadgets[1],
        REDUCTION_GADGET_LEFT_FORWARD,
        0,
        1,
        3,
        0,
        3,
        REDUCTION_NO_SWAP_ROW
    );
    assert_gadget_span(
        &reduction.explanation.gadgets[2],
        REDUCTION_GADGET_RIGHT_FORWARD,
        0,
        3,
        5,
        0,
        3,
        REDUCTION_NO_SWAP_ROW
    );
    assert_gadget_span(
        &reduction.explanation.gadgets[3],
        REDUCTION_GADGET_CLAUSE,
        0,
        5,
        7,
        0,
        3,
        REDUCTION_NO_SWAP_ROW
    );
    assert_region_encoding(&reduction.region, top_is_r, bottom_is_l);
    assert(memcmp(clauses, clauses_before, sizeof(clauses)) == 0);

    yang_zhang_reduction_destroy(&reduction);
    assert_reduction_destroyed(&reduction);
}

static void test_standard_build_omits_explanation(void)
{
    Cm13Clause clauses[1];
    Cm13Formula formula = one_variable_formula(clauses);
    YangZhangReduction reduction = {0};

    assert(yang_zhang_build(&formula, &reduction));
    assert(reduction.region.width == 7);
    assert(reduction.region.height == 3);
    assert(reduction.explanation.source_signals == NULL);
    assert(reduction.explanation.target_signals == NULL);
    assert(reduction.explanation.signal_count == 0);
    assert(reduction.explanation.gadgets == NULL);
    assert(reduction.explanation.gadget_count == 0);

    yang_zhang_reduction_destroy(&reduction);
    assert_reduction_destroyed(&reduction);
}

static void test_dimensions_normal(void)
{
    const AdjacentSwap swaps[] = {
        { .row = 7 }, /* paper swap(8), width 8 */
        { .row = 6 }, /* paper swap(7), width 7 */
        { .row = 5 }  /* paper swap(6), width 6 */
    };

    int32_t height = 0;
    int32_t width = 0;

    assert(yang_zhang_compute_dimensions(
        3,
        swaps,
        3,
        &height,
        &width
    ));

    assert(height == 11);

    /*
     * Project convention:
     *
     * variable       = 1
     * left forward   = 2
     * crossover      = 8 + 7 + 6 = 21
     * right forward  = 2
     * clause         = 2
     *
     * total = 28
     */
    assert(width == 28);

    /* The borrowed swap sequence is not modified. */
    assert(swaps[0].row == 7);
    assert(swaps[1].row == 6);
    assert(swaps[2].row == 5);
}

static void test_build_paper_example(void)
{
    Cm13Clause clauses[3] = {
        { .variable_index = { 0, 0, 2 } },
        { .variable_index = { 1, 1, 2 } },
        { .variable_index = { 0, 1, 2 } }
    };
    const Cm13Clause clauses_before[3] = {
        { .variable_index = { 0, 0, 2 } },
        { .variable_index = { 1, 1, 2 } },
        { .variable_index = { 0, 1, 2 } }
    };
    const Cm13Formula formula = {
        .variable_count = 3,
        .clauses = clauses,
        .clause_count = 3
    };
    const uint32_t expected_rows[] = {
        7, 6, 5, 4, 3, 2, 3, 4, 5, 8, 7, 6, 8, 7
    };
    SignalToken source[] = {
        variable_token(0, 0), variable_token(0, 1), variable_token(0, 2),
        redundant_token(3, 0),
        variable_token(1, 0), variable_token(1, 1), variable_token(1, 2),
        redundant_token(3, 1),
        variable_token(2, 0), variable_token(2, 1), variable_token(2, 2)
    };
    const SignalToken target[] = {
        variable_token(0, 0), variable_token(0, 1), variable_token(2, 0),
        redundant_token(3, 0),
        variable_token(1, 0), variable_token(1, 1), variable_token(2, 1),
        redundant_token(3, 1),
        variable_token(0, 2), variable_token(1, 2), variable_token(2, 2)
    };
    YangZhangReduction reduction = {0};
    bool top_is_r[96] = {false};
    bool bottom_is_l[96] = {false};

    assert(yang_zhang_build_explained(&formula, &reduction));
    assert(reduction.region.height == 11);
    assert(reduction.region.width == 96);
    assert(reduction.swap_count == ARRAY_COUNT(expected_rows));
    assert(reduction.explanation.signal_count == ARRAY_COUNT(source));
    assert(reduction.explanation.gadget_count ==
           2u * formula.variable_count + 2u + ARRAY_COUNT(expected_rows));
    for (size_t i = 0; i < ARRAY_COUNT(source); ++i) {
        assert(tokens_equal(
            &reduction.explanation.source_signals[i],
            &source[i]
        ));
        assert(tokens_equal(
            &reduction.explanation.target_signals[i],
            &target[i]
        ));
    }
    for (uint32_t variable = 0;
         variable < formula.variable_count;
         ++variable) {
        assert_gadget_span(
            &reduction.explanation.gadgets[variable],
            REDUCTION_GADGET_VARIABLE,
            variable,
            0,
            1,
            (int32_t)(4u * variable),
            (int32_t)(4u * variable + 3u),
            REDUCTION_NO_SWAP_ROW
        );
    }
    assert_gadget_span(
        &reduction.explanation.gadgets[formula.variable_count],
        REDUCTION_GADGET_LEFT_FORWARD,
        0,
        1,
        3,
        0,
        11,
        REDUCTION_NO_SWAP_ROW
    );

    int32_t block_x = (int32_t)(YANG_ZHANG_VARIABLE_WIDTH +
                                YANG_ZHANG_LEFT_FORWARD_WIDTH);
    size_t crossover_width = 0;
    for (size_t i = 0; i < reduction.swap_count; ++i) {
        const uint32_t row = expected_rows[i];
        const int32_t block_width = (int32_t)row + 1;

        assert(reduction.swaps[i].row == row);
        assert_gadget_span(
            &reduction.explanation.gadgets[formula.variable_count + 1u + i],
            REDUCTION_GADGET_CROSSOVER,
            (uint32_t)i,
            block_x,
            block_x + block_width,
            0,
            11,
            row
        );
        top_is_r[block_x + block_width - 1] = true;
        bottom_is_l[block_x] = true;
        block_x += block_width;
        crossover_width += (size_t)block_width;
    }
    assert(crossover_width == 89);
    assert(block_x == 92);

    const size_t right_index =
        formula.variable_count + 1u + ARRAY_COUNT(expected_rows);
    assert_gadget_span(
        &reduction.explanation.gadgets[right_index],
        REDUCTION_GADGET_RIGHT_FORWARD,
        0,
        92,
        94,
        0,
        11,
        REDUCTION_NO_SWAP_ROW
    );
    for (uint32_t clause = 0; clause < formula.clause_count; ++clause) {
        const int32_t first_y = (int32_t)(4u * clause);
        const int32_t y_end = clause + 1u < formula.clause_count
            ? first_y + 4
            : reduction.region.height;
        assert_gadget_span(
            &reduction.explanation.gadgets[right_index + 1u + clause],
            REDUCTION_GADGET_CLAUSE,
            clause,
            94,
            96,
            first_y,
            y_end,
            REDUCTION_NO_SWAP_ROW
        );
    }

    assert(yang_zhang_permutation_apply(
        source,
        ARRAY_COUNT(source),
        reduction.swaps,
        reduction.swap_count
    ));
    for (size_t i = 0; i < ARRAY_COUNT(source); ++i) {
        assert(tokens_equal(&source[i], &target[i]));
    }

    assert_region_encoding(&reduction.region, top_is_r, bottom_is_l);
    assert(memcmp(clauses, clauses_before, sizeof(clauses)) == 0);

    yang_zhang_reduction_destroy(&reduction);
    assert_reduction_destroyed(&reduction);
}

static void test_paper_dimensions_from_known_swaps(void)
{
    const AdjacentSwap swaps[] = {
        { .row = 7 },
        { .row = 6 },
        { .row = 5 },
        { .row = 4 },
        { .row = 3 },
        { .row = 2 },
        { .row = 3 },
        { .row = 4 },
        { .row = 5 },
        { .row = 8 },
        { .row = 7 },
        { .row = 6 },
        { .row = 8 },
        { .row = 7 }
    };

    int32_t height = 0;
    int32_t width = 0;

    assert(yang_zhang_compute_dimensions(
        3,
        swaps,
        sizeof(swaps) / sizeof(swaps[0]),
        &height,
        &width
    ));

    assert(height == 11);

    /*
     * Paper crossover widths sum to 89.
     *
     * Project coarse width:
     *   1 + 2 + 89 + 2 + 2 = 96
     */
    assert(width == 96);
}

static void test_layout_without_swaps(void)
{
    int32_t height = 0;
    int32_t width = 0;

    assert(yang_zhang_compute_dimensions(
        1,
        NULL,
        0,
        &height,
        &width
    ));

    assert(height == 3);

    /*
     * Even without a crossover block, the project convention retains
     * the two signal-propagation bands.
     *
     * 1 + 2 + 0 + 2 + 2 = 7
     */
    assert(width == 7);
}

static void test_zero_variables_rejected(void)
{
    int32_t height = 11;
    int32_t width = 28;

    assert(!yang_zhang_compute_dimensions(
        0,
        NULL,
        0,
        &height,
        &width
    ));

    assert(height == 11);
    assert(width == 28);
}

static void test_null_swaps_rejected(void)
{
    int32_t height = 0;
    int32_t width = 0;

    assert(!yang_zhang_compute_dimensions(
        2,
        NULL,
        1,
        &height,
        &width
    ));
}

static void test_invalid_swap_row_rejected(void)
{
    /*
     * n = 2 -> height = 7.
     * Valid zero-based swap rows are 0..5.
     */
    const AdjacentSwap swaps[] = {
        { .row = 6 }
    };

    int32_t height = 0;
    int32_t width = 0;

    assert(!yang_zhang_compute_dimensions(
        2,
        swaps,
        1,
        &height,
        &width
    ));
}

static void test_null_outputs_rejected(void)
{
    int32_t height = 0;
    int32_t width = 0;

    assert(!yang_zhang_compute_dimensions(
        1,
        NULL,
        0,
        NULL,
        &width
    ));

    assert(!yang_zhang_compute_dimensions(
        1,
        NULL,
        0,
        &height,
        NULL
    ));
}

static void test_variable_count_overflow_rejected(void)
{
    int32_t height = 0;
    int32_t width = 0;

    assert(!yang_zhang_compute_dimensions(
        YANG_ZHANG_MAX_VARIABLES + 1u,
        NULL,
        0,
        &height,
        &width
    ));
}

static void test_width_overflow_rejected(void)
{
    const AdjacentSwap swaps[] = {
        { .row = (uint32_t)INT32_MAX - 7u }
    };
    int32_t height = 0;
    int32_t width = 0;

    assert(!yang_zhang_compute_dimensions(
        YANG_ZHANG_MAX_VARIABLES,
        swaps,
        1,
        &height,
        &width
    ));
}

static uint32_t fuzz_state = UINT32_C(0x6d2b79f5);

static uint32_t next_fuzz_value(void)
{
    fuzz_state = fuzz_state * UINT32_C(1664525) + UINT32_C(1013904223);
    return fuzz_state;
}

static void shuffle_indices(uint32_t *indices, size_t count)
{
    for (size_t i = count; i > 1; --i) {
        const size_t other = (size_t)next_fuzz_value() % i;
        const uint32_t tmp = indices[i - 1];
        indices[i - 1] = indices[other];
        indices[other] = tmp;
    }
}

static void test_deterministic_canonical_formula_fuzz(void)
{
    enum { MAX_VARIABLES = 6, ITERATIONS = 80 };
    Cm13Clause clauses[MAX_VARIABLES];
    Cm13Clause clauses_before[MAX_VARIABLES];
    uint32_t flattened[3 * MAX_VARIABLES];

    for (size_t iteration = 0; iteration < ITERATIONS; ++iteration) {
        const uint32_t variable_count =
            1u + next_fuzz_value() % MAX_VARIABLES;
        const size_t flattened_count = 3u * (size_t)variable_count;

        for (uint32_t variable = 0;
             variable < variable_count;
             ++variable) {
            for (size_t occurrence = 0; occurrence < 3; ++occurrence) {
                flattened[3u * variable + occurrence] = variable;
            }
        }
        shuffle_indices(flattened, flattened_count);

        for (uint32_t clause = 0; clause < variable_count; ++clause) {
            for (size_t row = 0; row < 3; ++row) {
                clauses[clause].variable_index[row] =
                    flattened[3u * clause + row];
            }
        }

        memcpy(
            clauses_before,
            clauses,
            variable_count * sizeof(*clauses)
        );

        const Cm13Formula formula = {
            .variable_count = variable_count,
            .clauses = clauses,
            .clause_count = variable_count
        };
        YangZhangReduction reduction = {0};

        assert(yang_zhang_build(&formula, &reduction));
        assert(reduction.region.height == (int32_t)(4u * variable_count - 1u));

        bool *top_is_r = calloc(
            (size_t)reduction.region.width,
            sizeof(*top_is_r)
        );
        bool *bottom_is_l = calloc(
            (size_t)reduction.region.width,
            sizeof(*bottom_is_l)
        );
        assert(top_is_r != NULL);
        assert(bottom_is_l != NULL);

        int32_t block_x = (int32_t)(YANG_ZHANG_VARIABLE_WIDTH +
                                    YANG_ZHANG_LEFT_FORWARD_WIDTH);
        for (size_t i = 0; i < reduction.swap_count; ++i) {
            const int32_t block_width =
                (int32_t)reduction.swaps[i].row + 1;
            top_is_r[block_x + block_width - 1] = true;
            bottom_is_l[block_x] = true;
            block_x += block_width;
        }

        assert_region_encoding(&reduction.region, top_is_r, bottom_is_l);
        assert(memcmp(
            clauses,
            clauses_before,
            variable_count * sizeof(*clauses)
        ) == 0);

        free(bottom_is_l);
        free(top_is_r);
        yang_zhang_reduction_destroy(&reduction);
        assert_reduction_destroyed(&reduction);

        const uint32_t saved = clauses[0].variable_index[0];
        clauses[0].variable_index[0] = variable_count;
        assert_build_rejected(&formula);
        clauses[0].variable_index[0] = saved;

        if (variable_count > 1) {
            clauses[0].variable_index[0] = (saved + 1u) % variable_count;
            assert_build_rejected(&formula);
            clauses[0].variable_index[0] = saved;
        }
    }
}

int main(void)
{
    test_reduction_destroy_accepts_null_and_empty();
    test_reduction_destroy_releases_and_resets_owned_storage();
    test_build_rejects_null_arguments();
    test_build_rejects_invalid_formula_domain();
    test_build_rejects_variable_count_overflow();
    test_failed_build_does_not_modify_formula_storage();
    test_build_rejects_non_destroyed_output();
    test_build_minimal_valid_formula_with_explanation();
    test_standard_build_omits_explanation();

    test_dimensions_normal();
    test_build_paper_example();
    test_paper_dimensions_from_known_swaps();
    test_layout_without_swaps();

    test_zero_variables_rejected();
    test_null_swaps_rejected();
    test_invalid_swap_row_rejected();
    test_null_outputs_rejected();
    test_variable_count_overflow_rejected();
    test_width_overflow_rejected();
    test_deterministic_canonical_formula_fuzz();

    puts("test_yang_zhang: OK");
    return 0;
}
