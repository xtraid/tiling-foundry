from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import demo


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/instances/pipeline_sat.cm13"


class DemoCliTests(unittest.TestCase):
    def main(self, args):
        main = getattr(demo, "main", None)
        self.assertTrue(callable(main), "public demo command is missing")
        return main(args)

    def worker(self, *args):
        worker = getattr(demo, "_worker", None)
        self.assertTrue(callable(worker), "demo worker is missing")
        return worker(*args)

    def test_invalid_arguments_never_start_a_worker(self):
        with patch.object(demo, "_supervise", side_effect=AssertionError("unexpected worker")), contextlib.redirect_stderr(io.StringIO()):
            for timeout in ("nan", "inf", "-inf", "0", "-1", "invalid", ""):
                with self.subTest(timeout=timeout):
                    with self.assertRaises(SystemExit) as stopped:
                        self.main([str(SOURCE), "--timeout=" + timeout])
                    self.assertEqual(stopped.exception.code, 2)
            for capacity in ("1", "100001", "2.0"):
                with self.subTest(capacity=capacity), self.assertRaises(SystemExit):
                    self.main([str(SOURCE), "--event-capacity", capacity])
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
                self.main([])

    def test_existing_output_entries_are_preserved_without_starting_worker(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "directory").mkdir()
            (root / "file").write_text("keep")
            (root / "link").symlink_to(root / "missing")
            for path in root.iterdir():
                with self.subTest(path=path), patch.object(demo, "_supervise", side_effect=AssertionError("unexpected worker")), contextlib.redirect_stderr(io.StringIO()):
                    self.assertNotEqual(self.main([str(SOURCE), "--output", str(path)]), 0)
            self.assertEqual((root / "file").read_text(), "keep")
            self.assertTrue((root / "link").is_symlink())
            self.assertFalse((root / "missing").exists())

    def test_worker_copies_input_and_metadata_before_dependency_failure(self):
        with tempfile.TemporaryDirectory(prefix="input with spaces ") as name:
            root = Path(name)
            source = root / "formula $x `true` ;.cm13"
            content = SOURCE.read_bytes()
            source.write_bytes(content)
            run = root / "run"
            run.mkdir()
            actual_which = demo.shutil.which if hasattr(demo, "shutil") else None

            def missing_pdf(command):
                return None if command == "pdflatex" else actual_which(command)

            self.assertTrue(hasattr(demo, "shutil"), "worker preflight is missing")
            with patch.object(demo.shutil, "which", side_effect=missing_pdf), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
                code = self.worker(source, run, 100000)
            self.assertNotEqual(code, 0)
            self.assertIn("pdflatex", error.getvalue())
            self.assertIn("dependenc", error.getvalue().lower())
            self.assertEqual((run / "input.cm13").read_bytes(), content)
            metadata = json.loads((run / "input.json").read_text())
            self.assertEqual(metadata["original_path"], str(source))
            self.assertEqual(metadata["original_name"], source.name)
            self.assertEqual(metadata["sha256"], hashlib.sha256(content).hexdigest())
            self.assertFalse((run / "dossier").exists())

    def test_zero_exit_without_complete_files_is_failure_and_no_success_is_printed(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "run"
            with patch.object(demo, "_supervise", return_value=0), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
                code = self.main([str(SOURCE), "--output", str(output)])
            self.assertNotEqual(code, 0)
            self.assertNotIn("dossier=", stdout.getvalue())
            self.assertTrue(output.is_dir())

    def test_demo_invocations_have_distinct_diagnostic_directories(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / ".venv/bin").mkdir(parents=True)
            (root / ".venv/bin/python").symlink_to(sys.executable)
            with patch.object(demo, "ROOT", root), patch.object(demo, "_supervise", return_value=1), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.main([str(SOURCE)]), 1)
                self.assertEqual(self.main([str(SOURCE)]), 1)
            self.assertEqual(len(list((root / "build/demo").iterdir())), 2)

    def test_worker_command_uses_installed_python_and_disables_downloads(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "run"
            with patch.object(demo, "_supervise", return_value=124) as supervise, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = self.main([str(SOURCE), "--output", str(output), "--timeout", "1.25", "--event-capacity", "2000"])
            self.assertEqual(code, 124)
            call = supervise.call_args
            self.assertEqual(call.args[0][0], str(ROOT / ".venv/bin/python"))
            self.assertIn(str(SOURCE), call.args[0])
            self.assertEqual(call.kwargs["timeout"], 1.25)
            self.assertEqual({key: call.kwargs["env"][key] for key in ("UV_OFFLINE", "UV_NO_SYNC", "UV_PYTHON_DOWNLOADS")}, {"UV_OFFLINE": "1", "UV_NO_SYNC": "1", "UV_PYTHON_DOWNLOADS": "never"})

    def test_make_passes_raw_metacharacters_and_preserves_malformed_input_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="make demo input ") as name:
            root = Path(name)
            marker = ROOT / ("demo-expanded-" + root.name.replace(" ", "-"))
            source = root / ("literal $(shell touch " + marker.name + ") $x `true`; #.cm13")
            source.write_bytes(b"p cm13 invalid\n")
            completed = subprocess.run(
                ["make", "--no-print-directory", "demo", "INPUT=" + str(source), "TIMEOUT=20"],
                cwd=ROOT, capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("malformed input", (completed.stdout + completed.stderr).lower())
            diagnostic = next((line.removeprefix("diagnostics=") for line in completed.stdout.splitlines() if line.startswith("diagnostics=")), None)
            self.assertIsNotNone(diagnostic, completed.stdout + completed.stderr)
            run = Path(diagnostic)
            self.assertEqual((run / "input.cm13").read_bytes(), source.read_bytes())
            self.assertEqual(json.loads((run / "input.json").read_text())["original_path"], str(source))
            self.assertIn("malformed input", (run / "worker.log").read_text().lower())
            self.assertFalse((run / "dossier").exists())
            self.assertNotIn("dossier=", completed.stdout)
            self.assertFalse(marker.exists())
            invalid_timeout = subprocess.run(
                ["make", "--no-print-directory", "demo", "INPUT=" + str(source),
                 "TIMEOUT=$(shell touch " + marker.name + ")"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(invalid_timeout.returncode, 0)
            self.assertIn("finite and positive", invalid_timeout.stderr)
            self.assertNotIn("diagnostics=", invalid_timeout.stdout)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
