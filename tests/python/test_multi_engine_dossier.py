from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dossier import multi_engine
from formats.pipeline_snapshot import PipelineSnapshotError
from formats.run_case_v2 import (
    CASE_SCHEMA,
    load_run_case_v2,
)
from formats.run_dossier_v2 import (
    RUN_SCHEMA,
    validate_run_dossier_v2,
)
from formats.run_dossier_v2_bundle import load_run_dossier_v2
from native import multi_engine_pipeline
from native.multi_engine_pipeline import (
    TraceCaptureOptions,
    capture_multi_engine_native_pipeline,
)
from oracles.witness_check import is_valid_assignment
from tools import generate_run_dossier as public_generator


ROOT = Path(__file__).resolve().parents[2]
SAT_CASE = ROOT / "examples/run-cases-v2/pipeline-sat.json"


def _unsat_case() -> dict[str, object]:
    return {
        "schema": CASE_SCHEMA,
        "id": "pipeline-unsat-v2",
        "title": "Full-pipeline UNSAT capture test",
        "purpose": "Exercise the closed v2 UNSAT and not-applicable fields.",
        "source": "tests/instances/pipeline_unsat_search.cm13",
        "expected_status": "unsat",
        "reference_trace": {
            "event_capacity": 8192,
            "checkpoint_interval": 128,
            "checkpoint_capacity": 64,
        },
        "optimized_trace": {
            "event_capacity": 8192,
            "checkpoint_interval": 128,
            "checkpoint_capacity": 64,
        },
    }


class MultiEngineDossierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.sat_directory = cls.root / "sat"
        multi_engine.generate_multi_engine_dossier(SAT_CASE, cls.sat_directory)
        cls.sat_document = load_run_dossier_v2(cls.sat_directory / "run.json")

        cls.unsat_case_path = cls.root / "unsat-case.json"
        cls.unsat_case_path.write_text(
            json.dumps(_unsat_case(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        cls.unsat_directory = cls.root / "unsat"
        multi_engine.generate_multi_engine_dossier(
            cls.unsat_case_path,
            cls.unsat_directory,
        )
        cls.unsat_document = load_run_dossier_v2(
            cls.unsat_directory / "run.json"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_native_coordinator_runs_each_solver_once_in_one_capture(self) -> None:
        case = load_run_case_v2(SAT_CASE, ROOT)
        reference = TraceCaptureOptions(
            case.reference_trace.event_capacity,
            case.reference_trace.checkpoint_interval,
            case.reference_trace.checkpoint_capacity,
        )
        optimized = TraceCaptureOptions(
            case.optimized_trace.event_capacity,
            case.optimized_trace.checkpoint_interval,
            case.optimized_trace.checkpoint_capacity,
        )
        actual_solve = multi_engine_pipeline._solve_native_traced
        actual_load = multi_engine_pipeline._loaded_formula
        actual_reduce = multi_engine_pipeline._built_explained_reduction
        with patch.object(
            multi_engine_pipeline,
            "_solve_native_traced",
            wraps=actual_solve,
        ) as solve, patch.object(
            multi_engine_pipeline,
            "_loaded_formula",
            wraps=actual_load,
        ) as load, patch.object(
            multi_engine_pipeline,
            "_built_explained_reduction",
            wraps=actual_reduce,
        ) as reduce:
            capture = capture_multi_engine_native_pipeline(
                ROOT / case.source,
                reference_options=reference,
                optimized_options=optimized,
            )

        self.assertEqual(load.call_count, 1)
        self.assertEqual(reduce.call_count, 1)
        self.assertEqual(solve.call_count, 2)
        self.assertEqual(
            [call.kwargs["optimized"] for call in solve.call_args_list],
            [False, True],
        )
        self.assertEqual(capture.reference.result.status.value, "sat")
        self.assertEqual(capture.optimized.result.status.value, "sat")
        self.assertFalse(capture.reference.trace.truncated)
        self.assertFalse(capture.optimized.trace.truncated)
        self.assertTrue(
            is_valid_assignment(
                capture.formula,
                capture.reference.extracted_assignment or (),
            )
        )
        self.assertTrue(
            is_valid_assignment(
                capture.formula,
                capture.optimized.extracted_assignment or (),
            )
        )

    def test_sat_capture_binds_named_engines_and_shared_native_inputs(self) -> None:
        document = self.sat_document
        self.assertEqual(document["schema"], RUN_SCHEMA)
        self.assertTrue(document["agreement"]["passed"])
        self.assertTrue(document["agreement"]["sat_witnesses_valid"])
        self.assertEqual(
            {
                document[name]["status"]
                for name in ("boolean_z3", "reference", "optimized", "wang_z3")
            },
            {"sat"},
        )
        self.assertNotEqual(
            document["reference"]["trace"]["trace_sha256"],
            document["optimized"]["trace"]["trace_sha256"],
        )
        self.assertEqual(
            document["reduction"]["region_sha256"],
            document["artifacts"]["region_snapshot"]["sha256"],
        )
        self.assertIsNone(document["presentation"]["square"]["artifact"])
        self.assertFalse((self.sat_directory / "report.tex").exists())
        self.assertFalse((self.sat_directory / "report.pdf").exists())

    def test_unsat_capture_has_no_witness_or_fabricated_verification(self) -> None:
        document = self.unsat_document
        self.assertEqual(
            {
                document[name]["status"]
                for name in ("boolean_z3", "reference", "optimized", "wang_z3")
            },
            {"unsat"},
        )
        self.assertIsNone(document["agreement"]["sat_witnesses_valid"])
        self.assertIsNone(document["boolean_z3"]["assignment"])
        self.assertIsNone(document["wang_z3"]["cells"])
        self.assertIsNone(document["artifacts"]["reference_solution"])
        self.assertIsNone(document["artifacts"]["optimized_solution"])
        self.assertIsNone(document["timings"]["reference_verify_ns"])
        self.assertIsNone(document["timings"]["wang_z3_verify_ns"])
        for check in document["verification"].values():
            self.assertFalse(check["performed"])
            self.assertIsNone(check["passed"])
            self.assertIsNone(check["witness_sha256"])
        for presentation in document["presentation"].values():
            self.assertFalse(presentation["applicable"])
            self.assertIsNone(presentation["artifact"])

    def test_case_contract_forbids_initial_domain_overrides(self) -> None:
        invalid = json.loads(SAT_CASE.read_text(encoding="utf-8"))
        invalid["initial_domain_overrides"] = []
        path = self.root / "invalid-overrides.json"
        path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "unknown fields"):
            load_run_case_v2(path, ROOT)

        schema = json.loads(
            (ROOT / "schemas/wang-run-case-v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("initial_domain_overrides", schema["properties"])

    def test_public_generator_dispatch_preserves_the_v1_implementation(self) -> None:
        v1_case = ROOT / "examples/run-cases/sat-end-to-end.json"
        expected = self.root / "mock-v1"
        with patch.object(
            public_generator,
            "_generate_run_dossier_v1",
            return_value=expected,
        ) as generate_v1:
            actual = public_generator.generate_run_dossier(
                v1_case,
                expected,
                tex_engine="pdflatex",
                max_frames=7,
                duration_ms=250,
            )
        self.assertEqual(actual, expected)
        generate_v1.assert_called_once_with(
            v1_case,
            expected,
            tex_engine="pdflatex",
            max_frames=7,
            duration_ms=250,
        )

        v2_expected = self.root / "mock-v2"
        with patch.object(
            multi_engine,
            "generate_multi_engine_dossier",
            return_value=v2_expected,
        ) as generate_v2:
            v2_actual = public_generator.generate_run_dossier(
                SAT_CASE,
                v2_expected,
                tex_engine="pdflatex",
            )
        self.assertEqual(v2_actual, v2_expected)
        generate_v2.assert_called_once_with(SAT_CASE, v2_expected)
        with self.assertRaisesRegex(
            public_generator.DossierGenerationError,
            "v1-only",
        ):
            public_generator.generate_run_dossier(
                SAT_CASE,
                v2_expected,
                tex_engine="xelatex",
            )

    def test_mismatch_and_cross_identity_mutations_are_rejected(self) -> None:
        mismatch = copy.deepcopy(self.sat_document)
        mismatch["wang_z3"]["status"] = "unsat"
        mismatch["wang_z3"]["cells"] = None
        mismatch["wang_z3"]["witness_sha256"] = None
        with self.assertRaisesRegex(PipelineSnapshotError, "status mismatch"):
            validate_run_dossier_v2(mismatch)

        identity = copy.deepcopy(self.sat_document)
        identity["reduction"]["region_sha256"] = "0" * 64
        with self.assertRaisesRegex(PipelineSnapshotError, "cross-field mismatch"):
            validate_run_dossier_v2(identity)

        unknown = copy.deepcopy(self.sat_document)
        unknown["stages"] = []
        with self.assertRaisesRegex(PipelineSnapshotError, "unknown fields"):
            validate_run_dossier_v2(unknown)

    def test_loader_rejects_tampering_and_external_symlinks(self) -> None:
        tampered = self.root / "tampered"
        shutil.copytree(self.sat_directory, tampered)
        source = tampered / self.sat_document["artifacts"]["source_input"]["path"]
        source.write_bytes(b"tampered\n")
        with self.assertRaisesRegex(PipelineSnapshotError, "does not match file"):
            load_run_dossier_v2(tampered / "run.json")

        escaped = self.root / "escaped"
        shutil.copytree(self.sat_directory, escaped)
        run_path = escaped / "run.json"
        document = json.loads(run_path.read_text(encoding="utf-8"))
        formula = escaped / document["artifacts"]["formula_snapshot"]["path"]
        formula.unlink()
        outside = self.root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        formula.symlink_to(outside)
        with self.assertRaisesRegex(PipelineSnapshotError, "escapes dossier"):
            load_run_dossier_v2(run_path)

    def test_bundle_loader_imports_no_capture_or_native_producer(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import formats.run_dossier_v2_bundle; "
                    "assert 'dossier.multi_engine' not in sys.modules; "
                    "assert 'native.multi_engine_pipeline' not in sys.modules"
                ),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "python"},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_failure_cleanup_and_existing_destination_are_safe(self) -> None:
        destination = self.root / "existing"
        destination.mkdir()
        sentinel = destination / "sentinel"
        sentinel.write_text("keep\n", encoding="utf-8")
        with self.assertRaisesRegex(
            multi_engine.MultiEngineDossierError,
            "already exists",
        ):
            multi_engine.generate_multi_engine_dossier(SAT_CASE, destination)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

        failed = self.root / "failed"
        before = set(self.root.glob(".failed.*"))
        with patch.object(
            multi_engine,
            "capture_multi_engine_native_pipeline",
            side_effect=RuntimeError("forced capture failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "forced capture failure"):
                multi_engine.generate_multi_engine_dossier(SAT_CASE, failed)
        self.assertFalse(failed.exists())
        self.assertEqual(set(self.root.glob(".failed.*")), before)

        actual_boolean = multi_engine.build_boolean_z3_summary

        def disagree(*args: object, **kwargs: object) -> dict[str, object]:
            summary = actual_boolean(*args, **kwargs)
            summary["status"] = "unsat"
            summary["model"]["assignment"] = None
            summary["statistics"][-1]["value"] = 0
            return summary

        mismatch = self.root / "mismatch"
        before = set(self.root.glob(".mismatch.*"))
        with patch.object(
            multi_engine,
            "build_boolean_z3_summary",
            side_effect=disagree,
        ):
            with self.assertRaisesRegex(PipelineSnapshotError, "status mismatch"):
                multi_engine.generate_multi_engine_dossier(SAT_CASE, mismatch)
        self.assertFalse(mismatch.exists())
        self.assertEqual(set(self.root.glob(".mismatch.*")), before)

    def test_final_replace_failure_leaves_no_partial_destination(self) -> None:
        destination = self.root / "replace-failed"
        before = set(self.root.glob(".replace-failed.*"))
        actual_boolean = multi_engine.build_boolean_z3_summary
        actual_wang = multi_engine.build_wang_z3_summary
        with patch.object(
            multi_engine,
            "_install_directory",
            side_effect=OSError("forced replace failure"),
        ), patch.object(
            multi_engine,
            "build_boolean_z3_summary",
            wraps=actual_boolean,
        ) as boolean, patch.object(
            multi_engine,
            "build_wang_z3_summary",
            wraps=actual_wang,
        ) as wang:
            with self.assertRaisesRegex(OSError, "forced replace failure"):
                multi_engine.generate_multi_engine_dossier(SAT_CASE, destination)
        self.assertEqual(boolean.call_count, 1)
        self.assertEqual(wang.call_count, 1)
        self.assertFalse(destination.exists())
        self.assertEqual(set(self.root.glob(".replace-failed.*")), before)

    def test_v2_schemas_are_closed_draft_2020_12_documents(self) -> None:
        for name, expected in (
            ("wang-run-case-v2.schema.json", CASE_SCHEMA),
            ("wang-run-dossier-v2.schema.json", RUN_SCHEMA),
        ):
            with self.subTest(schema=name):
                schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(schema["properties"]["schema"]["const"], expected)
                self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
