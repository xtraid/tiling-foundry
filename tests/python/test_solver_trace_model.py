from dataclasses import FrozenInstanceError, replace
import unittest

from model.solver_trace import (
    DOMAIN_ALL,
    SOLVER_REFERENCE,
    TRACE_DECISION,
    TRACE_DOMAIN_REDUCTION,
    TRACE_INITIAL,
    TRACE_PROPAGATION,
    TRACE_REASON_DECISION,
    TRACE_RESULT,
    TRACE_ROOT,
    TRACE_SEARCH,
    SolverTrace,
    SolverTraceCheckpoint,
    SolverTraceEvent,
    replay_solver_trace,
)
from model.tiling import TilingSolveStatus


def _trace() -> SolverTrace:
    events = (
        SolverTraceEvent(
            0,
            TRACE_ROOT,
            TRACE_INITIAL,
            None,
            0,
            None,
            0,
            None,
            None,
            None,
        ),
        SolverTraceEvent(
            1,
            TRACE_DECISION,
            TRACE_SEARCH,
            None,
            1,
            0,
            0,
            DOMAIN_ALL,
            1,
            None,
        ),
        SolverTraceEvent(
            2,
            TRACE_DOMAIN_REDUCTION,
            TRACE_SEARCH,
            TRACE_REASON_DECISION,
            1,
            0,
            1,
            DOMAIN_ALL,
            1,
            None,
        ),
        SolverTraceEvent(
            3,
            TRACE_PROPAGATION,
            TRACE_SEARCH,
            None,
            1,
            0,
            1,
            None,
            None,
            None,
        ),
        SolverTraceEvent(
            4,
            TRACE_RESULT,
            None,
            None,
            1,
            None,
            1,
            None,
            None,
            TilingSolveStatus.SAT,
        ),
    )
    return SolverTrace(
        solver=SOLVER_REFERENCE,
        status=TilingSolveStatus.SAT,
        width=1,
        height=1,
        initial_domains=(DOMAIN_ALL,),
        events=events,
        observed_event_count=5,
        event_capacity=8,
        truncated=False,
        checkpoints=(
            SolverTraceCheckpoint(1, 0, (DOMAIN_ALL,)),
            SolverTraceCheckpoint(3, 1, (1,)),
        ),
        checkpoint_interval=2,
        checkpoint_capacity=2,
        checkpoints_truncated=False,
    )


class SolverTraceModelTests(unittest.TestCase):
    def test_is_immutable_and_replays_ordered_domain_deltas(self) -> None:
        trace = _trace()

        self.assertEqual(replay_solver_trace(trace)[-1], (1,))
        with self.assertRaises(FrozenInstanceError):
            trace.width = 2  # type: ignore[misc]

    def test_rejects_delta_that_does_not_match_replay_state(self) -> None:
        trace = _trace()
        invalid = replace(trace.events[2], old_domain=3)

        with self.assertRaisesRegex(ValueError, "old_domain"):
            replace(trace, events=(*trace.events[:2], invalid, *trace.events[3:]))

    def test_rejects_checkpoint_that_reconstructs_another_state(self) -> None:
        trace = _trace()
        invalid = replace(trace.checkpoints[0], domains=(2,))

        with self.assertRaisesRegex(ValueError, "checkpoint domains"):
            replace(trace, checkpoints=(invalid, trace.checkpoints[1]))

    def test_accepts_a_bounded_prefix_with_a_terminal_sequence_gap(self) -> None:
        trace = _trace()
        terminal = replace(trace.events[-1], sequence=99, change_mark=0)
        bounded = replace(
            trace,
            events=(trace.events[0], terminal),
            observed_event_count=100,
            event_capacity=2,
            truncated=True,
            checkpoints=(),
            checkpoint_interval=0,
            checkpoint_capacity=0,
        )

        self.assertEqual(replay_solver_trace(bounded)[-1], (DOMAIN_ALL,))

    def test_rejects_false_truncation_and_nonsemantic_event_fields(self) -> None:
        trace = _trace()
        with self.assertRaisesRegex(ValueError, "event gap"):
            replace(trace, truncated=True)

        invalid = replace(trace.events[3], reason=TRACE_REASON_DECISION)
        with self.assertRaisesRegex(ValueError, "only domain reduction"):
            replace(trace, events=(*trace.events[:3], invalid, trace.events[4]))


if __name__ == "__main__":
    unittest.main()
