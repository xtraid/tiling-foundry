from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dossier import multi_engine
from dossier import narrative_assets as narrative_generator
from dossier.tex_compile import TexCompileError
from formats.pipeline_snapshot import PipelineSnapshotError
from formats.narrative_assets import (
    boolean_z3_source_sha256,
    load_narrative_assets,
    verification_source_sha256,
    wang_z3_source_sha256,
)
from formats.run_case_v2 import (
    CASE_SCHEMA,
    load_run_case_v2,
)
from formats.run_dossier_v2 import (
    RUN_SCHEMA,
    validate_run_dossier_v2,
)
from formats.run_dossier_v2_bundle import load_run_dossier_v2
from formats.run_report_v2_tex import render_run_report_v2_tex
from native import multi_engine_pipeline
from native.multi_engine_pipeline import (
    TraceCaptureOptions,
    capture_multi_engine_native_pipeline,
)
from oracles.witness_check import is_valid_assignment
from tools import generate_run_dossier as public_generator


ROOT = Path(__file__).resolve().parents[2]
SAT_CASE = ROOT / "examples/run-cases-v2/pipeline-sat.json"
UNSAT_CASE = ROOT / "examples/run-cases-v2/pipeline-unsat-search.json"
V2_TEMPLATE = ROOT / "templates/run-report-v2.tex"


class MultiEngineDossierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.sat_directory = cls.root / "sat"
        multi_engine.generate_multi_engine_dossier(SAT_CASE, cls.sat_directory)
        cls.sat_document = load_run_dossier_v2(cls.sat_directory / "run.json")

        cls.unsat_directory = cls.root / "unsat"
        multi_engine.generate_multi_engine_dossier(
            UNSAT_CASE,
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
        self.assertEqual(
            document["presentation"]["square"]["artifact"],
            "square_presentation",
        )
        self.assertEqual(document["reference"]["trace"]["selection"], {
            "performed": True,
            "selected_event_count": 10,
        })
        self.assertEqual(document["optimized"]["trace"]["selection"], {
            "performed": True,
            "selected_event_count": 10,
        })
        narrative = load_narrative_assets(
            self.sat_directory / "assets/narrative/manifest.json",
            document,
        )
        self.assertEqual(narrative["product"], "run-specific")
        for solver in ("reference", "optimized"):
            animation = narrative["animations"][f"{solver}_trace"]
            self.assertEqual(animation["semantic_label"], "observed")
            self.assertEqual(animation["scope"], {
                "complete": True, "selected": True, "truncated": False,
            })
        self.assertEqual(
            narrative["animations"]["optimized_mechanisms"]["semantic_label"],
            "didactic",
        )
        expected_copy = {
            "boolean_z3": (
                "Real source clauses become occurrence-preserving exactly-one sums "
                "before the copied assignment is shown.",
                "Four frames place each source-order clause beside its "
                "occurrence-preserving sum and then show the copied Boolean assignment.",
            ),
            "wang_z3": (
                "A real cell shows its shared term, canonical tile tuple, boundary "
                "equality, and returned model projection.",
                "Five frames show adjacent canonical Wang tiles sharing an internal "
                "edge, one exposed boundary equality, and the copied model projection.",
            ),
            "verification": (
                "Six named checker receipts with concrete tiling rules and the recorded "
                "native extraction beside its source cells.",
                "Six frames show all checker receipts, valid tile IDs, TILE_NONE, "
                "internal and boundary equality, and copied extracted Boolean values "
                "beside variable-gadget cells.",
            ),
        }
        for name, (caption, alt_text) in expected_copy.items():
            self.assertEqual(narrative["animations"][name]["caption"], caption)
            self.assertEqual(narrative["animations"][name]["alt_text"], alt_text)
        self.assertFalse((self.sat_directory / "report.tex").exists())
        self.assertFalse((self.sat_directory / "report.pdf").exists())

    def test_v2_sat_report_follows_pipeline_and_uses_static_milestones(self) -> None:
        narrative = load_narrative_assets(
            self.sat_directory / "assets/narrative/manifest.json",
            self.sat_document,
        )
        tex = render_run_report_v2_tex(
            self.sat_document,
            narrative,
            V2_TEMPLATE.read_text(encoding="utf-8"),
        )
        headings = (
            r"\section{Summary}",
            r"\section{Source instance}",
            r"\section{Boolean Z3}",
            r"\section{Yang--Zhang reduction}",
            r"\section{Reference solver}",
            r"\section{Optimized solver}",
            r"\section{Wang Z3}",
            r"\section{Verification and presentation}",
            r"\section{Reproducibility appendix}",
        )
        offsets = tuple(tex.index(heading) for heading in headings)
        self.assertEqual(offsets, tuple(sorted(offsets)))
        self.assertIn(
            r"\verbatiminput{assets/data/pipeline_sat.cm13}",
            tex,
        )
        for group in (
            "region_construction",
            "reference_trace",
            "optimized_trace",
        ):
            for path in narrative["pdf_milestones"][group]:
                self.assertIn(path, tex)
        self.assertNotIn("contact-sheet.png", tex)
        self.assertNotIn(".gif", tex)
        for name in ("square", "generalized", "hex"):
            path = narrative["statics"][f"{name}_presentation"]["artifact"]["path"]
            self.assertIn(
                r"\includegraphics[width=\textwidth,height=0.48\textheight,keepaspectratio]"
                rf"{{assets/narrative/{path}}}",
                tex,
            )
        sheet_path = narrative["statics"]["generalized_sheet"]["artifact"]["path"]
        self.assertIn(
            r"\includegraphics[width=0.82\textwidth,height=0.64\textheight,keepaspectratio]"
            rf"{{assets/narrative/{sheet_path}}}",
            tex,
        )
        legend_path = narrative["statics"]["atomic_legend"]["artifact"]["path"]
        self.assertEqual(tex.count(f"{{assets/narrative/{legend_path}}}"), 2)
        self.assertIn("viewport=0 2092 1732 4184,clip,width=0.92", tex)
        self.assertIn("viewport=0 0 1732 2092,clip,width=0.92", tex)

    def test_v2_unsat_report_marks_witness_only_content_not_applicable(self) -> None:
        narrative = load_narrative_assets(
            self.unsat_directory / "assets/narrative/manifest.json",
            self.unsat_document,
        )
        tex = render_run_report_v2_tex(
            self.unsat_document,
            narrative,
            V2_TEMPLATE.read_text(encoding="utf-8"),
        )
        self.assertIn("Assignment: not applicable for this UNSAT result", tex)
        self.assertIn("Witness verification: not applicable", tex)
        self.assertIn("Witness presentations: not applicable", tex)
        self.assertIn("No UNSAT certificate is claimed", tex)
        self.assertIn(
            narrative["statics"]["presentation_status"]["artifact"]["path"],
            tex,
        )
        presentation_status = narrative["statics"]["presentation_status"]
        status_path = presentation_status["artifact"]["path"]
        self.assertIn(
            r"\includegraphics[width=0.72\textwidth,height=0.30\textheight,keepaspectratio]"
            rf"{{assets/narrative/{status_path}}}",
            tex,
        )
        self.assertNotIn("contact-sheet.png", tex)
        self.assertNotIn(".gif", tex)
        for name in (
            "home_preview",
            "worked_example",
            "square_presentation",
            "generalized_presentation",
            "hex_presentation",
        ):
            self.assertIsNone(narrative["statics"][name])

    def test_v2_formatter_is_pure_after_caller_validation(self) -> None:
        narrative = load_narrative_assets(
            self.sat_directory / "assets/narrative/manifest.json",
            self.sat_document,
        )
        with patch("builtins.open", side_effect=AssertionError("formatter I/O")), patch(
            "io.open", side_effect=AssertionError("formatter I/O")
        ):
            tex = render_run_report_v2_tex(
                self.sat_document,
                narrative,
                "@@TITLE@@\n@@BODY@@\n",
            )
        self.assertIn(r"\section{Summary}", tex)

    def test_v2_reports_each_oracle_timing_in_its_own_section(self) -> None:
        for directory, document in (
            (self.sat_directory, self.sat_document),
            (self.unsat_directory, self.unsat_document),
        ):
            with self.subTest(status=document["case"]["expected_status"]):
                narrative = load_narrative_assets(
                    directory / "assets/narrative/manifest.json", document
                )
                tex = render_run_report_v2_tex(
                    document, narrative, V2_TEMPLATE.read_text(encoding="utf-8")
                )
                appendix = tex.split(
                    r"\section{Reproducibility appendix}", 1
                )[1]
                for heading, timing_name in (
                    ("Boolean Z3", "boolean_z3_ns"),
                    ("Wang Z3", "wang_z3_ns"),
                ):
                    elapsed_ns = document["timings"][timing_name]
                    expected = (
                        f"{elapsed_ns / 1_000_000:.3f} ms ({elapsed_ns} ns)"
                    )
                    section = tex.split(rf"\section{{{heading}}}", 1)[1].split(
                        r"\section{", 1
                    )[0]
                    self.assertIn(expected, section)
                    self.assertIn("run-specific", section.lower())
                    self.assertIn("not a benchmark", section.lower())
                    self.assertIn(expected, appendix)

    def test_narrative_source_hashes_cover_every_consumed_identity(self) -> None:
        run = self.sat_document
        verification_digest = verification_source_sha256(run)
        for path, replacement in (
            (("source", "sha256"), "0" * 64),
            (("reduction", "formula_sha256"), "1" * 64),
            (("reduction", "tileset_sha256"), "2" * 64),
            (("reduction", "region_sha256"), "3" * 64),
            (("reduction", "provenance_sha256"), "4" * 64),
            (("reference", "solution_sha256"), "5" * 64),
            (("reference", "extracted_assignment"), [True, False, True]),
        ):
            mutated = copy.deepcopy(run)
            mutated[path[0]][path[1]] = replacement
            self.assertNotEqual(
                verification_source_sha256(mutated),
                verification_digest,
                path,
            )

        boolean_digest = boolean_z3_source_sha256("a" * 64, "b" * 64)
        self.assertNotEqual(
            boolean_z3_source_sha256("c" * 64, "b" * 64),
            boolean_digest,
        )
        self.assertNotEqual(
            boolean_z3_source_sha256("a" * 64, "c" * 64),
            boolean_digest,
        )
        wang_digest = wang_z3_source_sha256("a" * 64, "b" * 64, "c" * 64)
        for values in (
            ("d" * 64, "b" * 64, "c" * 64),
            ("a" * 64, "d" * 64, "c" * 64),
            ("a" * 64, "b" * 64, "d" * 64),
        ):
            self.assertNotEqual(wang_z3_source_sha256(*values), wang_digest)

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
        narrative = load_narrative_assets(
            self.unsat_directory / "assets/narrative/manifest.json",
            document,
        )
        self.assertIsNone(narrative["animations"]["witness_presentation"])
        self.assertIsNotNone(narrative["statics"]["presentation_status"])
        self.assertIsNone(narrative["statics"]["home_preview"])
        self.assertEqual(
            narrative["animations"]["boolean_z3"]["caption"],
            "Source clauses retain occurrence-preserving exactly-one sums; "
            "the assignment is not applicable for this UNSAT result.",
        )
        self.assertEqual(
            narrative["animations"]["boolean_z3"]["alt_text"],
            "Four frames show source-order clauses and sums, then mark the "
            "Boolean assignment not applicable because no SAT model was returned.",
        )
        self.assertEqual(
            narrative["animations"]["wang_z3"]["caption"],
            "The encoding is constructed, but cell, tile, boundary, and returned-model "
            "examples are not applicable for this UNSAT result.",
        )
        self.assertEqual(
            narrative["animations"]["wang_z3"]["alt_text"],
            "Five frames end with an UNSAT panel that makes no cell, tile tuple, "
            "boundary, model, witness, or certificate claim.",
        )
        self.assertEqual(
            narrative["animations"]["verification"]["caption"],
            "Six named checker receipts mark every witness check not applicable "
            "because no SAT witness was returned.",
        )
        self.assertEqual(
            narrative["animations"]["verification"]["alt_text"],
            "Six frames mark every witness check not applicable and state that "
            "no SAT witness or certificate is fabricated.",
        )
        for solver, animation_name in (
            ("reference", "reference_trace"),
            ("optimized", "optimized_trace"),
        ):
            trace_path = self.unsat_directory / document["artifacts"][
                f"{solver}_trace"
            ]["path"]
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            all_kinds = {event["kind"] for event in trace["events"]}
            self.assertTrue({"decision", "conflict", "backtrack"} <= all_kinds)
            selected_sequences = {
                int(Path(frame["path"]).stem.removeprefix("frame-"))
                for frame in narrative["animations"][animation_name]["frames"]
            }
            selected_kinds = {
                event["kind"]
                for event in trace["events"]
                if event["sequence"] in selected_sequences
            }
            self.assertTrue(
                {"conflict", "backtrack", "result"} <= selected_kinds,
                (solver, selected_kinds),
            )
            animation = narrative["animations"][animation_name]
            self.assertIn("observed search diagnostic", animation["caption"])
            self.assertIn("not an UNSAT certificate", animation["caption"])
            selected = [
                event for event in trace["events"]
                if event["sequence"] in selected_sequences
            ]
            decision = next(e for e in selected if e["kind"] == "decision")
            reduction = next(e for e in selected if (
                e["kind"] == "domain_reduction" and e["reason"] == "propagation"
                and e["sequence"] > decision["sequence"]
            ))
            empty = next(e for e in selected if (
                e["kind"] == "domain_reduction" and e["new_domain"] == 0
                and e["sequence"] >= reduction["sequence"]
            ))
            conflict = next(e for e in selected if e["kind"] == "conflict")
            rollback = next(e for e in selected if e["kind"] == "backtrack")
            next_branches = [e for e in selected if (
                e["kind"] == "decision" and e["sequence"] > rollback["sequence"]
            )]
            self.assertTrue(next_branches, f"{solver} omits the next branch")
            next_branch = next_branches[0]
            self.assertLess(decision["sequence"], reduction["sequence"])
            self.assertLess(empty["sequence"], conflict["sequence"])
            self.assertLess(conflict["sequence"], rollback["sequence"])
            self.assertLess(rollback["sequence"], next_branch["sequence"])
            self.assertLess(rollback["change_mark"], conflict["change_mark"])

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
        generate_v2.assert_called_once_with(SAT_CASE, v2_expected, include_pdf=False)
        with self.assertRaisesRegex(
            public_generator.DossierGenerationError,
            "v2-only",
        ):
            public_generator.generate_run_dossier(
                v1_case,
                expected,
                tex_engine="pdflatex",
                include_pdf=True,
            )
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

        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import dossier.multi_engine; "
                    "assert 'formats.run_report_v2_tex' not in sys.modules; "
                    "assert 'dossier.tex_compile' not in sys.modules"
                ),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "python"},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_same_compositor_bytes_serve_run_and_canonical_pages(self) -> None:
        destination = self.root / "canonical-pages-assets"
        manifest_path = narrative_generator.generate_narrative_assets(
            self.sat_directory / "run.json",
            destination,
            product="canonical-pages",
        )
        manifest = load_narrative_assets(manifest_path, self.sat_document)
        self.assertEqual(manifest["product"], "canonical-pages")

        run_root = self.sat_directory / "assets/narrative"
        run_files = {
            path.relative_to(run_root): path.read_bytes()
            for path in run_root.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        pages_files = {
            path.relative_to(destination): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        self.assertEqual(run_files, pages_files)
        public_root = ROOT / "docs/assets/narrative"
        public_manifest = load_narrative_assets(
            public_root / "manifest.json", self.sat_document
        )
        self.assertEqual(public_manifest["product"], "canonical-pages")
        public_files = {
            path.relative_to(public_root): path.read_bytes()
            for path in public_root.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        self.assertEqual(pages_files, public_files)

    def test_narrative_manifest_rejects_metadata_and_asset_tampering(self) -> None:
        copied = self.root / "narrative-tampered"
        shutil.copytree(self.sat_directory, copied)
        run = load_run_dossier_v2(copied / "run.json")
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["animations"]["reference_trace"]["semantic_label"] = "didactic"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "semantic_label"):
            load_narrative_assets(manifest_path, run)

        copied = self.root / "narrative-source-tampered"
        shutil.copytree(self.sat_directory, copied)
        run = load_run_dossier_v2(copied / "run.json")
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["statics"]["square_presentation"]["source_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "static source"):
            load_narrative_assets(manifest_path, run)

        copied = self.root / "narrative-scope-tampered"
        shutil.copytree(self.sat_directory, copied)
        run = load_run_dossier_v2(copied / "run.json")
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["animations"]["reference_trace"]["scope"]["selected"] = False
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "selected.*policy"):
            load_narrative_assets(manifest_path, run)

        copied = self.root / "narrative-bytes-tampered"
        shutil.copytree(self.sat_directory, copied)
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame = copied / "assets/narrative" / manifest["animations"][
            "boolean_z3"
        ]["frames"][0]["path"]
        frame.write_bytes(frame.read_bytes() + b"tampered")
        with self.assertRaisesRegex(PipelineSnapshotError, "does not match file"):
            load_run_dossier_v2(copied / "run.json")

        copied = self.root / "narrative-symlinked"
        shutil.copytree(self.sat_directory, copied)
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame = copied / "assets/narrative" / manifest["animations"][
            "boolean_z3"
        ]["frames"][0]["path"]
        alias = frame.with_name("internal-alias.png")
        alias.write_bytes(frame.read_bytes())
        frame.unlink()
        frame.symlink_to(alias.name)
        with self.assertRaisesRegex(PipelineSnapshotError, "symlinks are forbidden"):
            load_run_dossier_v2(copied / "run.json")

        copied = self.root / "narrative-parent-symlinked"
        shutil.copytree(self.sat_directory, copied)
        narrative_directory = copied / "assets/narrative"
        relocated = copied / "relocated-narrative"
        narrative_directory.rename(relocated)
        narrative_directory.symlink_to("../relocated-narrative", target_is_directory=True)
        with self.assertRaisesRegex(PipelineSnapshotError, "may not contain symlinks"):
            load_run_dossier_v2(copied / "run.json")

    def test_narrative_manifest_rejects_toolchain_and_milestone_drift(self) -> None:
        copied = self.root / "narrative-toolchain-tampered"
        shutil.copytree(self.sat_directory, copied)
        run = load_run_dossier_v2(copied / "run.json")
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["animations"]["witness_presentation"]["validator"] = "fake.validator"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "validator"):
            load_narrative_assets(manifest_path, run)

        copied = self.root / "narrative-milestones-tampered"
        shutil.copytree(self.sat_directory, copied)
        run = load_run_dossier_v2(copied / "run.json")
        manifest_path = copied / "assets/narrative/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["pdf_milestones"]["reference_trace"].reverse()
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "shared frame order"):
            load_narrative_assets(manifest_path, run)

    def test_run_loader_rejects_an_unattached_narrative_manifest(self) -> None:
        copied = self.root / "narrative-unattached"
        shutil.copytree(self.sat_directory, copied)
        run_path = copied / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        for solver in ("reference", "optimized"):
            run[solver]["trace"]["selection"] = {
                "performed": False,
                "selected_event_count": None,
            }
        run_path.write_text(json.dumps(run) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineSnapshotError, "performed selection"):
            load_run_dossier_v2(run_path)

    def test_narrative_generation_preserves_existing_destination_and_cleans_failure(self) -> None:
        destination = self.root / "existing-narrative"
        destination.mkdir()
        sentinel = destination / "sentinel"
        sentinel.write_text("keep\n", encoding="utf-8")
        with self.assertRaisesRegex(
            narrative_generator.NarrativeAssetError,
            "already exists",
        ):
            narrative_generator.generate_narrative_assets(
                self.sat_directory / "run.json", destination
            )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

        failed = self.root / "failed-narrative"
        before = set(self.root.glob(".failed-narrative.*"))
        with patch.object(
            narrative_generator,
            "_run_renderer",
            side_effect=narrative_generator.NarrativeAssetError("forced render failure"),
        ):
            with self.assertRaisesRegex(
                narrative_generator.NarrativeAssetError,
                "forced render failure",
            ):
                narrative_generator.generate_narrative_assets(
                    self.sat_directory / "run.json", failed
                )
        self.assertFalse(failed.exists())
        self.assertEqual(set(self.root.glob(".failed-narrative.*")), before)

        with patch.object(
            narrative_generator.shutil,
            "which",
            return_value="/usr/bin/uv",
        ), patch.object(
            narrative_generator.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ):
            with self.assertRaisesRegex(
                narrative_generator.NarrativeAssetError,
                "omitted required output keys: fallback",
            ):
                narrative_generator._run_renderer(
                    ["renderer.py"], required_outputs=("fallback",)
                )

        with self.assertRaisesRegex(
            narrative_generator.NarrativeAssetError,
            "canonical pipeline SAT",
        ):
            narrative_generator.generate_narrative_assets(
                self.unsat_directory / "run.json",
                self.root / "invalid-canonical-pages",
                product="canonical-pages",
            )

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

        narrative_failure = self.root / "narrative-failure"
        before = set(self.root.glob(".narrative-failure.*"))
        with patch.object(
            narrative_generator,
            "generate_narrative_assets",
            side_effect=narrative_generator.NarrativeAssetError(
                "forced narrative failure"
            ),
        ):
            with self.assertRaisesRegex(
                multi_engine.MultiEngineDossierError,
                "shared narrative asset pass failed",
            ):
                multi_engine.generate_multi_engine_dossier(
                    SAT_CASE, narrative_failure
                )
        self.assertFalse(narrative_failure.exists())
        self.assertEqual(
            set(self.root.glob(".narrative-failure.*")), before
        )

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

    def test_v2_pdf_compile_failure_leaves_no_partial_destination(self) -> None:
        destination = self.root / "pdf-compile-failed"
        before = set(self.root.glob(".pdf-compile-failed.*"))
        with patch(
            "dossier.tex_compile.compile_tex_pdf",
            side_effect=TexCompileError("forced controlled compile failure"),
        ):
            with self.assertRaisesRegex(
                multi_engine.MultiEngineDossierError,
                "forced controlled compile failure",
            ):
                multi_engine.generate_multi_engine_dossier(
                    SAT_CASE,
                    destination,
                    include_pdf=True,
                )
        self.assertFalse(destination.exists())
        self.assertEqual(set(self.root.glob(".pdf-compile-failed.*")), before)

    def test_v2_schemas_are_closed_draft_2020_12_documents(self) -> None:
        for name, expected in (
            ("wang-run-case-v2.schema.json", CASE_SCHEMA),
            ("wang-run-dossier-v2.schema.json", RUN_SCHEMA),
            ("wang-narrative-assets-v1.schema.json", "wang-narrative-assets-v1"),
        ):
            with self.subTest(schema=name):
                schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(schema["properties"]["schema"]["const"], expected)
                self.assertFalse(schema["additionalProperties"])
                if name == "wang-narrative-assets-v1.schema.json":
                    owner = re.compile(
                        schema["$defs"]["metadata"]["properties"]["owner"][
                            "pattern"
                        ]
                    )
                    self.assertIsNotNone(owner.fullmatch("/"))
                    self.assertIsNotNone(owner.fullmatch("/components/verification/"))
                    self.assertIsNone(owner.fullmatch("components/verification/"))
                    relative_path = re.compile(schema["$defs"]["path"]["pattern"])
                    self.assertIsNotNone(relative_path.fullmatch("frames/frame-00.png"))
                    for invalid in (
                        "/etc/passwd",
                        "../frame.png",
                        "frames/../frame.png",
                        "frames//frame.png",
                    ):
                        self.assertIsNone(relative_path.fullmatch(invalid))
                    png_path_rules = schema["$defs"]["png_paths"]["items"]["allOf"]
                    self.assertEqual(png_path_rules[0]["$ref"], "#/$defs/path")
                    png_suffix = re.compile(png_path_rules[1]["pattern"])
                    self.assertIsNotNone(png_suffix.search("frames/frame-00.png"))
                    self.assertIsNone(png_suffix.search("frames/frame-00.gif"))


if __name__ == "__main__":
    unittest.main()
