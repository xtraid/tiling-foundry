from dataclasses import FrozenInstanceError, replace
import unittest

from model.reduction_explanation import (
    GADGET_CLAUSE,
    GADGET_CROSSOVER,
    GADGET_LEFT_FORWARD,
    GADGET_RIGHT_FORWARD,
    GADGET_VARIABLE,
    SIGNAL_VARIABLE,
    ReductionExplanation,
    ReductionGadget,
    ReductionSignal,
)


def _signal(row: int, occurrence: int) -> ReductionSignal:
    return ReductionSignal(
        row=row,
        kind=SIGNAL_VARIABLE,
        token_id=occurrence,
        variable=0,
        occurrence=occurrence,
    )


def _explanation(*, crossover: bool = False) -> ReductionExplanation:
    source = tuple(_signal(row, row) for row in range(3))
    if crossover:
        target = (
            _signal(0, 1),
            _signal(1, 0),
            _signal(2, 2),
        )
        crossover_gadgets = (
            ReductionGadget(
                kind=GADGET_CROSSOVER,
                ordinal=0,
                x_begin=3,
                x_end=4,
                y_begin=0,
                y_end=3,
                swap_row=0,
            ),
        )
        right_begin = 4
    else:
        target = source
        crossover_gadgets = ()
        right_begin = 3
    gadgets = (
        ReductionGadget(GADGET_VARIABLE, 0, 0, 1, 0, 3, None),
        ReductionGadget(GADGET_LEFT_FORWARD, 0, 1, 3, 0, 3, None),
        *crossover_gadgets,
        ReductionGadget(
            GADGET_RIGHT_FORWARD,
            0,
            right_begin,
            right_begin + 2,
            0,
            3,
            None,
        ),
        ReductionGadget(
            GADGET_CLAUSE,
            0,
            right_begin + 2,
            right_begin + 4,
            0,
            3,
            None,
        ),
    )
    return ReductionExplanation(
        variable_count=1,
        width=right_begin + 4,
        height=3,
        source_signals=source,
        target_signals=target,
        gadgets=gadgets,
    )


class ReductionExplanationModelTests(unittest.TestCase):
    def test_is_immutable_and_replays_the_recorded_crossover(self) -> None:
        explanation = _explanation(crossover=True)

        self.assertEqual(explanation.target_signals[0].occurrence, 1)
        with self.assertRaises(FrozenInstanceError):
            explanation.width = 99  # type: ignore[misc]

    def test_rejects_target_not_produced_by_the_crossover_program(self) -> None:
        explanation = _explanation()
        target = (
            _signal(0, 1),
            _signal(1, 0),
            _signal(2, 2),
        )

        with self.assertRaisesRegex(ValueError, "does not produce target"):
            replace(explanation, target_signals=target)

    def test_requires_half_open_gadget_bounds_inside_the_region(self) -> None:
        with self.assertRaisesRegex(ValueError, "x interval"):
            ReductionGadget(GADGET_VARIABLE, 0, 1, 1, 0, 3, None)

        explanation = _explanation()
        invalid = replace(explanation.gadgets[0], x_end=explanation.width + 1)
        with self.assertRaisesRegex(ValueError, "inside the region"):
            replace(explanation, gadgets=(invalid, *explanation.gadgets[1:]))

    def test_crossover_width_is_bound_to_its_swap_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "width must equal"):
            ReductionGadget(GADGET_CROSSOVER, 0, 3, 5, 0, 3, 0)

    def test_rejects_missing_semantic_gadget_populations(self) -> None:
        explanation = _explanation()
        without_clause = tuple(
            gadget
            for gadget in explanation.gadgets
            if gadget.kind != GADGET_CLAUSE
        )

        with self.assertRaisesRegex(ValueError, "expected 1 clause"):
            replace(explanation, gadgets=without_clause)

    def test_rejects_bool_where_an_integer_is_required(self) -> None:
        with self.assertRaises(ValueError):
            ReductionSignal(True, SIGNAL_VARIABLE, 0, 0, 0)

    def test_requires_unique_token_ids_and_all_three_occurrences(self) -> None:
        explanation = _explanation()
        duplicate_id = replace(explanation.source_signals[1], token_id=0)
        with self.assertRaisesRegex(ValueError, "token IDs must be unique"):
            replace(
                explanation,
                source_signals=(
                    explanation.source_signals[0],
                    duplicate_id,
                    explanation.source_signals[2],
                ),
            )

        repeated_occurrence = replace(
            explanation.source_signals[1],
            occurrence=0,
        )
        with self.assertRaisesRegex(ValueError, "occurrences 0, 1, and 2"):
            replace(
                explanation,
                source_signals=(
                    explanation.source_signals[0],
                    repeated_occurrence,
                    explanation.source_signals[2],
                ),
            )


if __name__ == "__main__":
    unittest.main()
