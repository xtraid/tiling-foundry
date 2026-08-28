from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from formats.pipeline_snapshot import PipelineSnapshotError
from formats.run_dossier import (
    CLASS_ROOT_CONFLICT,
    build_run_dossier,
    load_run_case,
    load_run_dossier,
    validate_case_outcome,
    validate_run_dossier,
)
from formats.run_report_tex import render_run_report_tex
from native.trace_pipeline import capture_native_pipeline_trace


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "examples/run-cases"
TEMPLATE = ROOT / "templates/run-report.tex"


def _artifacts() -> dict[str, dict[str, str]]:
    specs = {
        "trace_manifest": ("assets/data/manifest.json", "application/json"),
        "formula_view": ("assets/images/formula.png", "image/png"),
        "region_square": ("assets/images/region-square.png", "image/png"),
        "region_hex": ("assets/images/region-hex.png", "image/png"),
        "reduction_view": ("assets/images/reduction.png", "image/png"),
        "trace_contact_sheet": ("assets/images/trace/contact-sheet.png", "image/png"),
        "trace_fallback": ("assets/images/trace/frame-000001.png", "image/png"),
        "trace_animation": ("assets/images/trace/trace.gif", "image/gif"),
    }
    return {
        name: {
            "path": path,
            "sha256": f"{index + 1:064x}",
            "media_type": media_type,
            "role": f"test {name}",
        }
        for index, (name, (path, media_type)) in enumerate(specs.items())
    }


class RunDossierTests(unittest.TestCase):
    def test_versioned_cases_match_distinct_complete_observed_runs(self) -> None:
        summaries: dict[str, tuple[str, int, int]] = {}
        for case_path in sorted(CASES.glob("*.json")):
            with self.subTest(case=case_path.name):
                case = load_run_case(case_path, ROOT)
                overrides = tuple(
                    (item.cell, item.domain)
                    for item in case.initial_domain_overrides
                )
                values, timings = capture_native_pipeline_trace(
                    ROOT / case.source,
                    optimized=case.solver == "optimized",
                    event_capacity=case.event_capacity,
                    checkpoint_interval=case.checkpoint_interval,
                    checkpoint_capacity=case.checkpoint_capacity,
                    initial_domain_overrides=overrides or None,
                )
                trace = values[-1]
                validate_case_outcome(case, trace)
                self.assertFalse(trace.truncated)
                self.assertGreaterEqual(timings.solve_ns, 0)
                summaries[case.identifier] = (
                    trace.status.value,
                    trace.observed_event_count,
                    max(event.depth for event in trace.events),
                )

        self.assertEqual(summaries["unsat-root-conflict"], ("unsat", 3, 0))
        self.assertEqual(summaries["unsat-search"][0], "unsat")
        self.assertGreaterEqual(summaries["unsat-search"][2], 2)
        self.assertEqual(len(summaries), 4)

    def test_builds_closed_raw_run_and_fixed_latex_from_the_same_data(self) -> None:
        case = load_run_case(CASES / "unsat-root-conflict.json", ROOT)
        self.assertEqual(case.classification, CLASS_ROOT_CONFLICT)
        overrides = tuple(
            (item.cell, item.domain) for item in case.initial_domain_overrides
        )
        values, _ = capture_native_pipeline_trace(
            ROOT / case.source,
            optimized=True,
            event_capacity=case.event_capacity,
            checkpoint_interval=case.checkpoint_interval,
            checkpoint_capacity=case.checkpoint_capacity,
            initial_domain_overrides=overrides,
        )
        trace = values[-1]
        timings = {
            "parse": 10,
            "region_build": 20,
            "encoding": None,
            "solve": 30,
            "verify": None,
            "export": 50,
            "render": 60,
        }
        source_digest = hashlib.sha256((ROOT / case.source).read_bytes()).hexdigest()
        document = build_run_dossier(
            case,
            trace,
            source_sha256=source_digest,
            captured_at_utc="2026-08-27T20:00:00Z",
            platform="test-platform",
            python_version="3.14.0",
            git_commit="0" * 40,
            timings_ns=timings,
            artifacts=_artifacts(),
        )

        validate_run_dossier(document)
        tex = render_run_report_tex(document, TEMPLATE.read_text(encoding="utf-8"))
        self.assertIn("UNSAT immediate root conflict", tex)
        self.assertIn("not applicable", tex)
        self.assertIn("not a mathematical UNSAT certificate", tex)
        self.assertNotIn("@@TITLE@@", tex)
        self.assertNotIn("@@BODY@@", tex)
        self.assertNotIn("\\write18", tex)

        with tempfile.TemporaryDirectory() as directory:
            dossier = Path(directory)
            for name, item in document["artifacts"].items():
                asset = dossier / item["path"]
                asset.parent.mkdir(parents=True, exist_ok=True)
                encoded = f"artifact:{name}".encode("ascii")
                asset.write_bytes(encoded)
                item["sha256"] = hashlib.sha256(encoded).hexdigest()
            run_path = dossier / "run.json"
            run_path.write_text(
                json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(load_run_dossier(run_path), document)
            (dossier / document["artifacts"]["formula_view"]["path"]).write_bytes(
                b"tampered"
            )
            with self.assertRaisesRegex(PipelineSnapshotError, "does not match"):
                load_run_dossier(run_path)

            with tempfile.TemporaryDirectory() as outside_directory:
                external = Path(outside_directory) / "formula.png"
                external.write_bytes(b"external artifact")
                formula = dossier / document["artifacts"]["formula_view"]["path"]
                formula.unlink()
                formula.symlink_to(external)
                document["artifacts"]["formula_view"]["sha256"] = hashlib.sha256(
                    external.read_bytes()
                ).hexdigest()
                run_path.write_text(
                    json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(PipelineSnapshotError, "self-contained"):
                    load_run_dossier(run_path)

        invalid = copy.deepcopy(document)
        invalid["artifacts"]["formula_view"]["path"] = "../escape.png"
        with self.assertRaisesRegex(PipelineSnapshotError, "normalized relative"):
            validate_run_dossier(invalid)

        invalid = copy.deepcopy(document)
        invalid["solver"]["trace"]["truncated"] = True
        invalid["solver"]["replay"]["trace_scope"] = "truncated-prefix"
        with self.assertRaisesRegex(PipelineSnapshotError, "complete trace"):
            validate_run_dossier(invalid)

        with self.assertRaisesRegex(PipelineSnapshotError, "solver disagrees"):
            validate_case_outcome(replace(case, solver="reference"), trace)

    def test_case_loader_rejects_duplicate_members_and_wrong_status(self) -> None:
        with self.subTest("status"):
            case_path = CASES / "sat-end-to-end.json"
            encoded = case_path.read_text(encoding="utf-8").replace(
                '"expected_status": "sat"',
                '"expected_status": "unsat"',
            )
            temporary = ROOT / "build/test-invalid-run-case.json"
            temporary.parent.mkdir(exist_ok=True)
            temporary.write_text(encoded, encoding="utf-8")
            try:
                with self.assertRaisesRegex(PipelineSnapshotError, "disagrees"):
                    load_run_case(temporary, ROOT)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
