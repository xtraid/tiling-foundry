from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from crosscheck import witness_pipeline
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import TILESET
from native import formula_adapter
from native.formula_adapter import FormulaLoadError, FormulaParseStatus
from oracles import boolean_solver, tiling_check, tiling_solver
from oracles.boolean_solver import BooleanSolveResult, BooleanSolveStatus
from tools import demo


ROOT = Path(__file__).resolve().parents[2]


class DemoCheckTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("tools.demo_check"),
            "the narrated demo-check command is missing",
        )
        self.command = importlib.import_module("tools.demo_check")

    def worker(self):
        with tempfile.TemporaryDirectory() as name:
            run = Path(name)
            with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                code = self.command._worker(run)
            marker = run / "complete"
            return code, out.getvalue(), err.getvalue(), marker.read_bytes() if marker.exists() else None

    def test_six_real_checks_reuse_each_engine_result_and_reject_one_changed_tile(self):
        checked = []
        actual_check = tiling_check.is_valid_tiling

        def record_check(region, tileset, tiling):
            valid = actual_check(region, tileset, tiling)
            checked.append((region, tuple(tiling), valid))
            return valid

        with patch.object(witness_pipeline, "solve_native_and_extract", wraps=witness_pipeline.solve_native_and_extract) as native, patch.object(
            boolean_solver, "solve_boolean", wraps=boolean_solver.solve_boolean
        ) as boolean, patch.object(tiling_solver, "solve_tiling", wraps=tiling_solver.solve_tiling) as wang, patch.object(
            tiling_check, "is_valid_tiling", side_effect=record_check
        ):
            code, out, err, marker = self.worker()
        self.assertEqual(code, 0, err)
        self.assertEqual(marker, b"6/6\n")
        self.assertEqual([line.split()[0] for line in out.splitlines() if line.startswith("[")], [f"[{i}/6]" for i in range(1, 7)])
        self.assertEqual(out.count("OK:"), 6)
        self.assertIn("SAT", out)
        self.assertIn("UNSAT", out)
        self.assertIn("rifiut", out.lower())
        self.assertEqual((native.call_count, boolean.call_count, wang.call_count), (4, 2, 2))
        self.assertEqual(
            [(Path(call.args[0]).name, call.kwargs["optimized"]) for call in native.call_args_list],
            [("pipeline_sat.cm13", False), ("pipeline_unsat_search.cm13", False),
             ("pipeline_sat.cm13", True), ("pipeline_unsat_search.cm13", True)],
        )
        rejected = [(region, tiling) for region, tiling, valid in checked if not valid]
        self.assertEqual(len(rejected), 1)
        region, altered = rejected[0]
        original = next(tiling for area, tiling, valid in checked if area == region and valid)
        changes = [i for i, pair in enumerate(zip(original, altered, strict=True)) if pair[0] != pair[1]]
        self.assertEqual(len(changes), 1)
        self.assertTrue(region.active[changes[0]])
        self.assertIn(altered[changes[0]], range(len(TILESET)))
        self.assertTrue(actual_check(region, TILESET, original))

    def test_parser_io_failure_is_not_the_expected_domain_rejection(self):
        actual_load = formula_adapter.load_formula

        def fail_invalid(path):
            if Path(path).name == "malformed_domain.cm13":
                raise FormulaLoadError(str(path), FormulaParseStatus.IO_ERROR, 0, 0)
            return actual_load(path)

        with patch.object(formula_adapter, "load_formula", side_effect=fail_invalid):
            code, out, err, marker = self.worker()
        self.assertEqual(code, 1)
        self.assertIn("IO_ERROR", err)
        self.assertNotIn("[3/6]", out)
        self.assertIsNone(marker)

    def test_unknown_disagreement_engine_error_and_invalid_witness_stop_the_suite(self):
        cases = (
            (BooleanSolveResult(BooleanSolveStatus.UNKNOWN), "UNKNOWN"),
            (BooleanSolveResult(BooleanSolveStatus.UNSAT), "atteso SAT"),
            (RuntimeError("engine failed"), "engine failed"),
            (BooleanSolveResult(BooleanSolveStatus.SAT, (False, False, False)), "witness"),
        )
        for result, message in cases:
            override = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
            with self.subTest(result=result), patch.object(boolean_solver, "solve_boolean", **override):
                code, out, err, marker = self.worker()
            self.assertEqual(code, 1)
            self.assertIn(message, err)
            self.assertNotIn("[6/6]", out)
            self.assertIsNone(marker)

    def test_optimized_disagreement_is_not_hidden_by_reference_success(self):
        actual_native = witness_pipeline.solve_native_and_extract

        def disagree(path, *, optimized):
            formula, region, result, assignment = actual_native(path, optimized=optimized)
            if optimized and Path(path).name == "pipeline_sat.cm13":
                return formula, region, TilingSolveResult(TilingSolveStatus.UNSAT), None
            return formula, region, result, assignment

        with patch.object(witness_pipeline, "solve_native_and_extract", side_effect=disagree):
            code, out, err, marker = self.worker()
        self.assertEqual(code, 1)
        self.assertIn("optimized", err)
        self.assertIn("atteso SAT", err)
        self.assertNotIn("[6/6]", out)
        self.assertIsNone(marker)

    def test_checker_accepting_the_altered_witness_is_a_failure(self):
        with patch.object(tiling_check, "is_valid_tiling", return_value=True):
            code, out, err, marker = self.worker()
        self.assertEqual(code, 1)
        self.assertIn("[6/6]", out)
        self.assertIn("alterat", err.lower())
        self.assertIsNone(marker)

    def test_missing_native_dependency_fails_before_checks_with_setup_guidance(self):
        with patch("native._lib.library", side_effect=OSError("missing library")):
            code, out, err, marker = self.worker()
        self.assertEqual(code, 1)
        self.assertIn("make demo-setup", err)
        self.assertNotIn("[1/6]", out)
        self.assertIsNone(marker)

    def test_missing_installed_python_gives_setup_guidance(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with patch.object(self.command, "ROOT", root), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                code = self.command.main(["--output", str(root / "run")])
            self.assertEqual(code, 1)
            self.assertIn("make demo-setup", err.getvalue())
            self.assertNotIn("Superati 6/6", out.getvalue())

    def test_invalid_timeout_does_not_start_a_worker(self):
        with patch.object(demo, "_supervise", side_effect=AssertionError("unexpected worker")), contextlib.redirect_stderr(io.StringIO()):
            for value in ("nan", "inf", "-inf", "0", "-1", "invalid", ""):
                with self.subTest(timeout=value), self.assertRaises(SystemExit) as stopped:
                    self.command.main(["--timeout=" + value])
                self.assertEqual(stopped.exception.code, 2)

    def test_existing_output_is_preserved_without_starting_worker(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "directory").mkdir()
            (root / "file").write_text("keep")
            (root / "link").symlink_to(root / "missing")
            for output in list(root.iterdir()):
                with self.subTest(output=output), patch.object(demo, "_supervise", side_effect=AssertionError("unexpected worker")), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(self.command.main(["--output", str(output)]), 1)
            self.assertEqual((root / "file").read_text(), "keep")
            self.assertTrue((root / "link").is_symlink())
            self.assertFalse((root / "missing").exists())

    def test_zero_exit_with_missing_or_wrong_completion_marker_is_failure(self):
        for marker in (None, b"5/6\n", b"6/6\nextra"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as name:
                output = Path(name) / "run"

                def incomplete(*args, **kwargs):
                    if marker is not None:
                        (output / "complete").write_bytes(marker)
                    return 0

                with patch.object(demo, "_supervise", side_effect=incomplete), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                    code = self.command.main(["--output", str(output)])
                self.assertEqual(code, 1)
                self.assertNotIn("Superati 6/6", out.getvalue())
                self.assertIn("incomplet", err.getvalue())

    def test_parent_prints_duration_only_after_successful_completed_worker(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "run"

            def complete(*args, **kwargs):
                (output / "complete").write_bytes(b"6/6\n")
                return 0

            with patch.object(demo, "_supervise", side_effect=complete) as supervise, contextlib.redirect_stdout(io.StringIO()) as out:
                code = self.command.main(["--output", str(output), "--timeout", "1.25"])
            self.assertEqual(code, 0)
            self.assertRegex(out.getvalue(), r"Superati 6/6 controlli in [0-9]+\.[0-9]+ s")
            self.assertIn("diagnostics=" + str(output), out.getvalue())
            command = supervise.call_args.args[0]
            options = supervise.call_args.kwargs
            self.assertEqual(command[0], str(ROOT / ".venv/bin/python"))
            self.assertEqual(options["timeout"], 1.25)
            self.assertEqual({key: options["env"][key] for key in ("UV_OFFLINE", "UV_NO_SYNC", "UV_PYTHON_DOWNLOADS")}, {"UV_OFFLINE": "1", "UV_NO_SYNC": "1", "UV_PYTHON_DOWNLOADS": "never"})

    def test_worker_exit_codes_cannot_be_masked_by_a_completion_marker(self):
        for status in (1, 124, 130, 143):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as name:
                output = Path(name) / "run"

                def failed(*args, **kwargs):
                    (output / "complete").write_bytes(b"6/6\n")
                    return status

                with patch.object(demo, "_supervise", side_effect=failed), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                    code = self.command.main(["--output", str(output)])
                self.assertEqual(code, status)
                self.assertNotIn("Superati 6/6", out.getvalue())

    def test_real_entrypoint_timeout_returns_124_and_keeps_diagnostics(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "run"
            completed = subprocess.run(
                ["python3", "tools/demo_check.py", "--output", str(output), "--timeout", "0.001"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(completed.returncode, 124, completed.stdout + completed.stderr)
            self.assertIn("timeout", completed.stderr)
            self.assertNotIn("Superati 6/6", completed.stdout)
            self.assertTrue((output / "worker.log").is_file())

    def test_make_passes_raw_timeout_without_evaluating_make_or_shell_code(self):
        with tempfile.TemporaryDirectory() as name:
            marker = Path(name) / "expanded"
            completed = subprocess.run(
                ["make", "--no-print-directory", "demo-check", "TIMEOUT=$(shell touch " + str(marker) + ")"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("finite and positive", completed.stderr)
            self.assertNotIn("diagnostics=", completed.stdout)
            self.assertFalse(marker.exists())

    def test_make_defaults_to_300_seconds_for_both_demo_commands(self):
        # Exercise Make's actual export and each CLI's argparse conversion;
        # stop only at supervision so this regression needs no PDF generation.
        with tempfile.TemporaryDirectory() as name:
            wrapper = Path(name) / "capture_timeout.py"
            wrapper.write_text(
                "import importlib, pathlib, sys\n"
                "sys.path.insert(0, str(pathlib.Path.cwd()))\n"
                "from tools import demo\n"
                "entry = pathlib.Path(sys.argv[1]).stem\n"
                "command = importlib.import_module('tools.' + entry)\n"
                "def capture(*args, **kwargs):\n"
                "    print('captured-timeout=' + str(kwargs['timeout']), flush=True)\n"
                "    return 73\n"
                "demo._supervise = capture\n"
                "output = pathlib.Path(__file__).parent / (entry + '-run')\n"
                "raise SystemExit(command.main(['--output', str(output)]))\n"
            )
            environment = os.environ.copy()
            for key in ("TIMEOUT", "TILING_DEMO_TIMEOUT", "INPUT", "TILING_DEMO_INPUT", "MAKEFLAGS", "MAKEOVERRIDES"):
                environment.pop(key, None)
            for target in ("demo", "demo-check"):
                with self.subTest(target=target):
                    completed = subprocess.run(
                        ["make", "--no-print-directory", target,
                         "INPUT=" + str(ROOT / "tests/instances/pipeline_sat.cm13"),
                         "PYTHON=" + shlex.join([sys.executable, str(wrapper)])],
                        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10,
                    )
                    self.assertIn("captured-timeout=300.0", completed.stdout, completed.stdout + completed.stderr)
                    self.assertIn("Error 73", completed.stderr)

    def test_make_rejects_explicit_empty_timeout_for_both_demo_commands(self):
        for target in ("demo", "demo-check"):
            with self.subTest(target=target):
                completed = subprocess.run(
                    ["make", "--no-print-directory", target,
                     "INPUT=" + str(ROOT / "tests/instances/pipeline_sat.cm13"), "TIMEOUT="],
                    cwd=ROOT, capture_output=True, text=True, timeout=10,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("finite and positive", completed.stderr)
                self.assertNotIn("diagnostics=", completed.stdout)


if __name__ == "__main__":
    unittest.main()
