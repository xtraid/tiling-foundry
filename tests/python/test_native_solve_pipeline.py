import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from formats.wang_solution import load_wang_solution, validate_wang_solution
from formats.wang_solution_export import (
    WangSolutionExportError,
    build_wang_solution,
)
from model.tiling import TilingSolveStatus
from model.tileset import TILESET
from native.solve_pipeline import solve_native_tiling
from native.witness_adapter import NativeWitnessError
from oracles.tiling_check import is_valid_tiling


ROOT = Path(__file__).resolve().parents[2]
SAT_PATH = ROOT / "tests/instances/pipeline_sat.cm13"
UNSAT_PATH = ROOT / "tests/instances/pipeline_unsat.cm13"


class NativeSolvePipelineTests(unittest.TestCase):
    def test_real_native_results_export_without_z3_oracles(self) -> None:
        for optimized in (False, True):
            with self.subTest(optimized=optimized, expected="SAT"):
                region, result = solve_native_tiling(
                    SAT_PATH,
                    optimized=optimized,
                )
                self.assertIs(result.status, TilingSolveStatus.SAT)
                self.assertIsNotNone(result.tiling)
                self.assertTrue(is_valid_tiling(region, TILESET, result.tiling))
                validate_wang_solution(
                    build_wang_solution(region, result, origin=(0, 0))
                )

            with self.subTest(optimized=optimized, expected="UNSAT"):
                region, result = solve_native_tiling(
                    UNSAT_PATH,
                    optimized=optimized,
                )
                self.assertIs(result.status, TilingSolveStatus.UNSAT)
                self.assertIsNone(result.tiling)
                with self.assertRaises(WangSolutionExportError):
                    build_wang_solution(region, result, origin=(0, 0))

    def test_sat_result_must_pass_the_independent_python_checker(self) -> None:
        with patch(
            "native.solve_pipeline.is_valid_tiling",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                NativeWitnessError,
                "rejected by the Python checker",
            ):
                solve_native_tiling(SAT_PATH)

    def test_optimized_selector_is_strictly_boolean(self) -> None:
        with self.assertRaisesRegex(TypeError, "optimized must be a boolean"):
            solve_native_tiling(SAT_PATH, optimized=1)

    def test_native_export_runs_without_site_packages_or_z3(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            from pathlib import Path

            from formats.wang_solution_export import dump_wang_solution
            from model.tiling import TilingSolveStatus
            from native.solve_pipeline import solve_native_tiling

            source = Path(sys.argv[1])
            destination = Path(sys.argv[2])
            region, result = solve_native_tiling(source, optimized=True)
            assert result.status is TilingSolveStatus.SAT
            dump_wang_solution(
                destination,
                region,
                result,
                origin=(0, 0),
                metadata={"producer": "native-optimized"},
            )
            assert "z3" not in sys.modules
            """
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "python")
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "native-solution.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    "-c",
                    script,
                    str(SAT_PATH),
                    str(destination),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                load_wang_solution(destination)["metadata"],
                {"producer": "native-optimized"},
            )

    def test_stdlib_consumer_loads_the_fixture_without_native_or_z3(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            from formats.wang_solution import load_wang_solution

            document = load_wang_solution(sys.argv[1])
            assert document["status"] == "SAT"
            assert "native._lib" not in sys.modules
            assert "z3" not in sys.modules
            """
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "python")
        completed = subprocess.run(
            [
                sys.executable,
                "-S",
                "-B",
                "-c",
                script,
                str(ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"),
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
