import os
import subprocess
import sys
import unittest
from pathlib import Path

from model.solver_trace import (
    SOLVER_OPTIMIZED,
    SOLVER_REFERENCE,
    TRACE_DECISION,
    TRACE_DOMAIN_REDUCTION,
    TRACE_PROPAGATION,
    TRACE_RESULT,
    TRACE_ROOT,
    replay_solver_trace,
)
from model.tiling import TilingSolveStatus
from native.trace_pipeline import solve_native_pipeline_trace


INSTANCE = Path(__file__).resolve().parents[1] / "instances/pipeline_sat.cm13"
ROOT = INSTANCE.parents[2]


class NativeSolverTraceTests(unittest.TestCase):
    def test_reference_and_optimized_runs_are_deterministic_and_complete(self) -> None:
        for optimized, expected_solver in (
            (False, SOLVER_REFERENCE),
            (True, SOLVER_OPTIMIZED),
        ):
            with self.subTest(solver=expected_solver):
                first = solve_native_pipeline_trace(INSTANCE, optimized=optimized)
                second = solve_native_pipeline_trace(INSTANCE, optimized=optimized)
                formula, region, explanation, result, trace = first

                self.assertEqual(first, second)
                self.assertEqual(formula.variable_count, 3)
                self.assertEqual(
                    (explanation.width, explanation.height),
                    (region.width, region.height),
                )
                self.assertEqual(result.status, TilingSolveStatus.SAT)
                self.assertEqual(trace.solver, expected_solver)
                self.assertFalse(trace.truncated)
                self.assertFalse(trace.checkpoints_truncated)
                self.assertGreater(len(trace.checkpoints), 0)
                self.assertEqual(trace.events[0].kind, TRACE_ROOT)
                self.assertEqual(trace.events[-1].kind, TRACE_RESULT)
                kinds = {event.kind for event in trace.events}
                self.assertTrue(
                    {
                        TRACE_PROPAGATION,
                        TRACE_DECISION,
                        TRACE_DOMAIN_REDUCTION,
                    }.issubset(kinds)
                )
                self.assertIsNotNone(result.tiling)
                expected_domains = tuple(
                    0 if tile_id is None else 1 << tile_id
                    for tile_id in result.tiling or ()
                )
                self.assertEqual(replay_solver_trace(trace)[-1], expected_domains)

    def test_pipeline_import_is_z3_free_in_a_fresh_process(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import native.trace_pipeline; "
                    "assert 'z3' not in sys.modules"
                ),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "python"},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_capacity_two_retains_only_root_and_terminal_result(self) -> None:
        *_, trace = solve_native_pipeline_trace(
            INSTANCE,
            event_capacity=2,
            checkpoint_interval=0,
            checkpoint_capacity=0,
        )

        self.assertTrue(trace.truncated)
        self.assertEqual(
            tuple(event.kind for event in trace.events),
            (TRACE_ROOT, TRACE_RESULT),
        )
        self.assertGreater(trace.events[-1].sequence, 1)

    def test_rejects_invalid_trace_capacity_before_native_call(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            solve_native_pipeline_trace(INSTANCE, event_capacity=1)
        with self.assertRaisesRegex(ValueError, "jointly set"):
            solve_native_pipeline_trace(
                INSTANCE,
                checkpoint_interval=2,
                checkpoint_capacity=0,
            )


if __name__ == "__main__":
    unittest.main()
