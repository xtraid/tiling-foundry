from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dossier import multi_engine
from formats.pipeline_snapshot import PipelineSnapshotError
from formats.run_case_v2 import load_run_case_v2
from formats.run_dossier_v2_bundle import load_run_dossier_v2
from native.formula_adapter import FormulaLoadError
from native import multi_engine_pipeline as native


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "examples/run-cases-v2/pipeline-sat.json"
SOURCE = ROOT / "tests/instances/pipeline_sat.cm13"


class DemoCaptureTests(unittest.TestCase):
    def direct(self, *args, **kwargs):
        producer = getattr(multi_engine, "generate_input_dossier", None)
        self.assertTrue(callable(producer), "direct file producer is missing")
        return producer(*args, **kwargs)

    def test_named_case_copies_before_native_capture_and_preserves_basename(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "legacy-name.cm13"
            content = SOURCE.read_bytes()
            source.write_bytes(content)
            case = replace(load_run_case_v2(CASE, ROOT), source=source.name)

            def inspect_copy(path, **kwargs):
                self.assertNotEqual(path, source)
                self.assertEqual(path.name, source.name)
                self.assertEqual(path.read_bytes(), content)
                source.write_text("changed original")
                self.assertEqual(path.read_bytes(), content)
                raise RuntimeError("stop after copy inspection")

            with patch.object(multi_engine, "ROOT", root), patch.object(
                multi_engine, "load_run_case_v2", return_value=case
            ), patch.object(multi_engine, "capture_multi_engine_native_pipeline", side_effect=inspect_copy):
                with self.assertRaisesRegex(RuntimeError, "stop after copy"):
                    multi_engine.generate_multi_engine_dossier(CASE, root / "out")
            self.assertEqual(sorted(p.name for p in root.iterdir()), [source.name])

    def test_direct_capture_freezes_external_bytes_and_runs_each_engine_once(self):
        with tempfile.TemporaryDirectory(prefix="demo input ") as name:
            root = Path(name)
            source = root / "formula $(touch never) `false` ; #.cm13"
            content = b"c External demo input\n" + SOURCE.read_bytes()
            source.write_bytes(content)
            destination = root / "dossier"
            progress = []
            original_capture = multi_engine.capture_multi_engine_native_pipeline
            original_export = multi_engine.dump_solver_trace_bundle

            def capture_copy(path, **kwargs):
                self.assertEqual(path.name, "input.cm13")
                self.assertNotEqual(path, source)
                source.write_text("malformed after copy")
                self.assertEqual(path.read_bytes(), content)
                return original_capture(path, **kwargs)

            def export_copy(manifest, path, *args, **kwargs):
                self.assertEqual(path.name, "input.cm13")
                self.assertEqual(path.read_bytes(), content)
                return original_export(manifest, path, *args, **kwargs)

            with patch.object(multi_engine, "capture_multi_engine_native_pipeline", side_effect=capture_copy), patch.object(
                multi_engine, "dump_solver_trace_bundle", side_effect=export_copy
            ), patch.object(native, "_loaded_formula", wraps=native._loaded_formula) as parse, patch.object(
                native, "_built_explained_reduction", wraps=native._built_explained_reduction
            ) as reduce, patch.object(native, "_solve_native_traced", wraps=native._solve_native_traced) as solve, patch.object(
                multi_engine, "build_boolean_z3_summary", wraps=multi_engine.build_boolean_z3_summary
            ) as boolean, patch.object(multi_engine, "build_wang_z3_summary", wraps=multi_engine.build_wang_z3_summary) as wang:
                self.direct(source, destination, include_pdf=False, progress=progress.append)
            self.assertEqual((parse.call_count, reduce.call_count, solve.call_count, boolean.call_count, wang.call_count), (1, 1, 2, 1, 1))
            self.assertEqual([call.kwargs["optimized"] for call in solve.call_args_list], [False, True])
            for call in solve.call_args_list:
                self.assertEqual((call.kwargs["event_capacity"], call.kwargs["checkpoint_interval"], call.kwargs["checkpoint_capacity"]), (100000, 0, 0))
            run = load_run_dossier_v2(destination / "run.json")
            self.assertIsNone(run["case"]["expected_status"])
            self.assertEqual({run[engine]["status"] for engine in ("reference", "optimized", "boolean_z3", "wang_z3")}, {"sat"})
            self.assertEqual(run["source"]["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual((destination / run["artifacts"]["source_input"]["path"]).read_bytes(), content)
            self.assertEqual(progress, ["Parsing", "Reduction", "Reference", "Reference verification", "Optimized", "Optimized verification", "Boolean Z3", "Boolean Z3 verification", "Wang Z3", "Wang Z3 verification", "Bundle verification", "Figures", "Final validation"])

    def test_progress_callbacks_precede_real_operations_and_measured_windows(self):
        ticks = 0
        events = []

        def clock():
            nonlocal ticks
            ticks += 10
            return ticks

        def progress(label):
            nonlocal ticks
            ticks += 1000
            events.append(label)

        options = native.TraceCaptureOptions(100000, 0, 0)
        self.assertIn("progress", __import__("inspect").signature(native.capture_multi_engine_native_pipeline).parameters)
        capture = native.capture_multi_engine_native_pipeline(SOURCE, reference_options=options, optimized_options=options, clock_ns=clock, progress=progress)
        self.assertEqual(events, ["Parsing", "Reduction", "Reference", "Reference verification", "Optimized", "Optimized verification"])
        self.assertEqual([getattr(capture.timings, key) for key in capture.timings.__dataclass_fields__], [10] * 6)

    def test_direct_capture_rejects_malformed_input_and_incomplete_trace(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "malformed.cm13"
            source.write_text("p cm13 nope\n")
            with self.assertRaises(FormulaLoadError):
                self.direct(source, root / "bad", include_pdf=False)
            with patch.object(
                multi_engine, "dump_solver_trace_bundle",
                side_effect=AssertionError("incomplete traces must fail before export"),
            ) as export:
                with self.assertRaisesRegex((PipelineSnapshotError, multi_engine.MultiEngineDossierError), "complete|truncat"):
                    self.direct(SOURCE, root / "short", include_pdf=False, event_capacity=2)
                export.assert_not_called()
            self.assertEqual(sorted(p.name for p in root.iterdir()), [source.name])

    def test_direct_trace_capacity_rejected_before_reading_source(self):
        for capacity in (None, True, 1, 100001, 2.0, "2"):
            with self.subTest(capacity=capacity), self.assertRaisesRegex(ValueError, "capacity"):
                self.direct("missing.cm13", "unused", event_capacity=capacity)

    def test_existing_output_including_dangling_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for generate, source in ((multi_engine.generate_multi_engine_dossier, CASE), (self.direct, SOURCE)):
                destination = root / "link"
                destination.symlink_to(root / "missing")
                try:
                    with self.assertRaisesRegex(multi_engine.MultiEngineDossierError, "already exists"):
                        generate(source, destination, include_pdf=False)
                    self.assertTrue(destination.is_symlink())
                    self.assertFalse((root / "missing").exists())
                finally:
                    destination.unlink()

    def test_direct_capture_rejects_unknown_disagreement_and_engine_error(self):
        actual_boolean = multi_engine.build_boolean_z3_summary
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for status, message in (("unknown", "UNKNOWN"), ("unsat", "status mismatch"), ("error", "engine failed")):
                def altered(*args, **kwargs):
                    if status == "error":
                        raise RuntimeError("engine failed")
                    result = actual_boolean(*args, **kwargs)
                    result["status"] = status
                    result["model"]["assignment"] = None
                    result["statistics"][-1]["value"] = 0
                    return result
                with self.subTest(status=status), patch.object(multi_engine, "build_boolean_z3_summary", side_effect=altered):
                    with self.assertRaisesRegex((RuntimeError, ValueError), message):
                        self.direct(SOURCE, root / status, include_pdf=False)
                self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
