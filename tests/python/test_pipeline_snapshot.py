import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from formats.pipeline_snapshot import (
    FORMULA_SCHEMA,
    MANIFEST_SCHEMA,
    REDUCTION_MANIFEST_SCHEMA,
    REDUCTION_SCHEMA,
    REGION_SCHEMA,
    TILESET_SCHEMA,
    PipelineSnapshotError,
    build_formula_snapshot,
    build_reduction_explanation_snapshot,
    build_region_snapshot,
    build_tileset_snapshot,
    dump_pipeline_snapshots,
    dump_reduction_explanation_snapshots,
    load_explainability_bundle,
    load_pipeline_snapshot,
    load_reduction_explainability_bundle,
    validate_explain_manifest,
    validate_formula_snapshot,
    validate_reduction_explanation_snapshot,
    validate_region_snapshot,
    validate_tileset_snapshot,
)
from model.tileset import TILESET
from native.reduction_adapter import load_formula_region_and_explanation


ROOT = Path(__file__).resolve().parents[2]
SAT_PATH = ROOT / "tests/instances/pipeline_sat.cm13"
SOURCE_SHA256 = hashlib.sha256(SAT_PATH.read_bytes()).hexdigest()
COMMITTED_MANIFEST = ROOT / "tests/fixtures/pipeline_sat_explain/manifest.json"
SCHEMA_PATHS = {
    FORMULA_SCHEMA: ROOT / "schemas/cm13-formula-snapshot-v1.schema.json",
    TILESET_SCHEMA: ROOT / "schemas/wang-tileset-snapshot-v1.schema.json",
    REGION_SCHEMA: ROOT / "schemas/wang-region-snapshot-v1.schema.json",
    MANIFEST_SCHEMA: ROOT / "schemas/wang-explain-manifest-v1.schema.json",
    REDUCTION_SCHEMA: ROOT / "schemas/wang-reduction-explanation-v1.schema.json",
    REDUCTION_MANIFEST_SCHEMA: ROOT / "schemas/wang-explain-manifest-v2.schema.json",
}


def _snapshot_paths(manifest_path: Path) -> dict[str, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "manifest": manifest_path,
        **{
            name: manifest_path.parent / manifest["artifacts"][name]["path"]
            for name in manifest["artifacts"]
        },
    }


class PipelineSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.formula,
            cls.region,
            cls.explanation,
        ) = load_formula_region_and_explanation(SAT_PATH)

    def test_builders_create_closed_valid_snapshots(self) -> None:
        formula = build_formula_snapshot(
            self.formula,
            source_name=SAT_PATH.name,
            source_sha256=SOURCE_SHA256,
        )
        tileset = build_tileset_snapshot()
        region = build_region_snapshot(
            self.region,
            source_formula_sha256=SOURCE_SHA256,
            origin=(-3, 5),
        )

        validate_formula_snapshot(formula)
        validate_tileset_snapshot(tileset)
        validate_region_snapshot(region)
        self.assertEqual(formula["schema"], FORMULA_SCHEMA)
        self.assertEqual(formula["variable_count"], 3)
        self.assertEqual(len(formula["clauses"]), 3)
        self.assertEqual(tileset["schema"], TILESET_SCHEMA)
        self.assertEqual(len(tileset["tiles"]), len(TILESET))
        self.assertEqual(tileset["colors"], list(range(16)))
        self.assertEqual(region["schema"], REGION_SCHEMA)
        self.assertEqual(region["bounds"]["min_x_inclusive"], -3)
        self.assertEqual(region["bounds"]["min_y_inclusive"], 5)
        self.assertEqual(sum(region["active"]), 444)
        self.assertEqual(region["active"].count(False), 7)

        with self.assertRaisesRegex(TypeError, "immutable N/E/S/W"):
            build_tileset_snapshot(((0, 1),))

    def test_publishes_six_closed_draft_2020_12_schemas(self) -> None:
        for contract, path in SCHEMA_PATHS.items():
            with self.subTest(contract=contract):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(schema["properties"]["schema"]["const"], contract)
                self.assertFalse(schema["additionalProperties"])

    def test_dump_is_deterministic_and_manifest_is_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory:
            first_manifest = dump_pipeline_snapshots(
                Path(first_directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
            )
            first_paths = _snapshot_paths(first_manifest)
            first_bytes = {
                name: path.read_bytes() for name, path in first_paths.items()
            }
            manifest, formula, tileset, region = load_explainability_bundle(
                first_manifest
            )

        with tempfile.TemporaryDirectory() as second_directory:
            second_manifest = dump_pipeline_snapshots(
                Path(second_directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
            )
            second_paths = _snapshot_paths(second_manifest)
            second_bytes = {
                name: path.read_bytes() for name, path in second_paths.items()
            }

        self.assertEqual(first_bytes, second_bytes)
        committed_bytes = {
            name: path.read_bytes()
            for name, path in _snapshot_paths(COMMITTED_MANIFEST).items()
        }
        self.assertEqual(first_bytes, committed_bytes)
        self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
        self.assertEqual(formula["source"]["sha256"], SOURCE_SHA256)
        self.assertEqual(len(tileset["tiles"]), 23)
        self.assertEqual(sum(region["active"]), 444)

    def test_reduction_snapshot_records_native_signals_and_gadgets(self) -> None:
        document = build_reduction_explanation_snapshot(
            self.explanation,
            source_formula_sha256=SOURCE_SHA256,
            region_sha256="0" * 64,
        )

        validate_reduction_explanation_snapshot(document)
        self.assertEqual(document["schema"], REDUCTION_SCHEMA)
        self.assertEqual(document["bounds"]["x_end"], self.region.width)
        self.assertEqual(
            [signal["token_id"] for signal in document["signals"]["target"]],
            [0, 1, 3, 9, 2, 4, 6, 10, 5, 7, 8],
        )
        self.assertEqual(
            [
                gadget["swap_row"]
                for gadget in document["gadgets"]
                if gadget["kind"] == "crossover"
            ],
            [3, 2, 3, 7, 6, 7],
        )

        wrong_target = copy.deepcopy(document)
        first = wrong_target["signals"]["target"][0]
        second = wrong_target["signals"]["target"][1]
        for field in ("kind", "token_id", "variable", "occurrence"):
            first[field], second[field] = second[field], first[field]
        with self.assertRaisesRegex(PipelineSnapshotError, "does not produce target"):
            validate_reduction_explanation_snapshot(wrong_target)

        bool_ordinal = copy.deepcopy(document)
        bool_ordinal["gadgets"][0]["ordinal"] = True
        with self.assertRaisesRegex(PipelineSnapshotError, "must be an integer"):
            validate_reduction_explanation_snapshot(bool_ordinal)

    def test_v2_bundle_is_deterministic_and_cross_stage_hash_bound(self) -> None:
        snapshots: list[dict[str, bytes]] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                manifest_path = dump_reduction_explanation_snapshots(
                    Path(directory) / "pipeline.explain.json",
                    SAT_PATH,
                    self.formula,
                    self.region,
                    self.explanation,
                    origin=(-2, 4),
                )
                snapshots.append(
                    {
                        name: path.read_bytes()
                        for name, path in _snapshot_paths(manifest_path).items()
                    }
                )
                bundle = load_reduction_explainability_bundle(manifest_path)

        self.assertEqual(snapshots[0], snapshots[1])
        manifest, formula, tileset, region, reduction = bundle
        self.assertEqual(manifest["schema"], REDUCTION_MANIFEST_SCHEMA)
        self.assertEqual(formula["source"]["sha256"], SOURCE_SHA256)
        self.assertEqual(len(tileset["tiles"]), 23)
        self.assertEqual(region["bounds"]["min_x_inclusive"], -2)
        self.assertEqual(reduction["variable_count"], 3)

    def test_v2_bundle_rejects_rebound_reduction_with_wrong_region(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_reduction_explanation_snapshots(
                Path(directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
                self.explanation,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            reference = manifest["artifacts"]["reduction"]
            reduction_path = manifest_path.parent / reference["path"]
            reduction = json.loads(reduction_path.read_text(encoding="utf-8"))
            reduction["region_sha256"] = "0" * 64
            serialized = json.dumps(
                reduction,
                ensure_ascii=False,
                indent=2,
            )
            encoded = f"{serialized}\n".encode()
            digest = hashlib.sha256(encoded).hexdigest()
            replacement = manifest_path.parent / f"reduction-{digest}.json"
            replacement.write_bytes(encoded)
            reference["path"] = replacement.name
            reference["sha256"] = digest
            manifest_path.write_text(
                f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                PipelineSnapshotError,
                "does not match the referenced region",
            ):
                load_reduction_explainability_bundle(manifest_path)

    def test_manifest_rejects_changed_artifact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_pipeline_snapshots(
                Path(directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
            )
            paths = _snapshot_paths(manifest_path)
            paths["formula"].write_bytes(paths["formula"].read_bytes() + b" ")
            with self.assertRaisesRegex(PipelineSnapshotError, "does not match"):
                load_explainability_bundle(manifest_path)

    def test_bundle_rejects_cross_stage_formula_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_pipeline_snapshots(
                Path(directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_formula_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                PipelineSnapshotError,
                "does not match formula artifact",
            ):
                load_explainability_bundle(manifest_path)

    def test_formula_rejects_bool_variable_and_noncanonical_clause_id(self) -> None:
        document = build_formula_snapshot(
            self.formula,
            source_name=SAT_PATH.name,
            source_sha256=SOURCE_SHA256,
        )
        bool_variable = copy.deepcopy(document)
        bool_variable["clauses"][0]["variables"][0] = True
        with self.assertRaisesRegex(PipelineSnapshotError, "must be an integer"):
            validate_formula_snapshot(bool_variable)

        wrong_id = copy.deepcopy(document)
        wrong_id["clauses"][1]["clause_id"] = 0
        with self.assertRaisesRegex(PipelineSnapshotError, "canonical position"):
            validate_formula_snapshot(wrong_id)

    def test_tileset_rejects_color_table_or_tile_id_drift(self) -> None:
        document = build_tileset_snapshot()
        colors = copy.deepcopy(document)
        colors["colors"].append(99)
        with self.assertRaisesRegex(PipelineSnapshotError, "colors used"):
            validate_tileset_snapshot(colors)

        wrong_id = copy.deepcopy(document)
        wrong_id["tiles"][2]["tile_id"] = 1
        with self.assertRaisesRegex(PipelineSnapshotError, "canonical table"):
            validate_tileset_snapshot(wrong_id)

    def test_region_rejects_inactive_boundary_and_internal_constraint(self) -> None:
        document = build_region_snapshot(
            self.region,
            source_formula_sha256=SOURCE_SHA256,
        )
        inactive_index = document["active"].index(False)
        inactive = copy.deepcopy(document)
        inactive["boundary"][inactive_index] = {
            "N": None,
            "E": None,
            "S": None,
            "W": None,
        }
        with self.assertRaisesRegex(PipelineSnapshotError, "inactive position"):
            validate_region_snapshot(inactive)

        internal = copy.deepcopy(document)
        internal["boundary"][0]["E"] = 0
        with self.assertRaisesRegex(PipelineSnapshotError, "shared by active"):
            validate_region_snapshot(internal)

    def test_manifest_rejects_parent_path_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_pipeline_snapshots(
                Path(directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
            )
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        traversal = copy.deepcopy(document)
        traversal["artifacts"]["formula"]["path"] = "../formula.json"
        with self.assertRaisesRegex(PipelineSnapshotError, "artifact basename"):
            validate_explain_manifest(traversal)

        extra = copy.deepcopy(document)
        extra["render"] = {}
        with self.assertRaisesRegex(PipelineSnapshotError, "unknown fields"):
            validate_explain_manifest(extra)

    def test_strict_loader_rejects_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(
                '{"schema":"wang-region-snapshot-v1","schema":"duplicate"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PipelineSnapshotError, "duplicate member"):
                load_pipeline_snapshot(path)

            path.write_text('{"schema":[]}', encoding="utf-8")
            with self.assertRaisesRegex(
                PipelineSnapshotError,
                "must be a string",
            ):
                load_pipeline_snapshot(path)

    def test_manifest_replace_failure_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "pipeline.explain.json"
            destination.write_bytes(b"previous manifest")
            real_replace = __import__("os").replace

            def fail_manifest_replace(source, target):
                if Path(target) == destination:
                    raise OSError("injected manifest replace failure")
                real_replace(source, target)

            with patch(
                "formats.pipeline_snapshot.os.replace",
                side_effect=fail_manifest_replace,
            ):
                with self.assertRaisesRegex(
                    PipelineSnapshotError,
                    "injected manifest replace failure",
                ):
                    dump_pipeline_snapshots(
                        destination,
                        SAT_PATH,
                        self.formula,
                        self.region,
                    )
            self.assertEqual(destination.read_bytes(), b"previous manifest")
            self.assertFalse(list(Path(directory).glob(".*.tmp")))

    def test_manifest_name_collision_is_rejected_before_overwrite(self) -> None:
        formula = build_formula_snapshot(
            self.formula,
            source_name=SAT_PATH.name,
            source_sha256=SOURCE_SHA256,
        )
        encoded = f"{json.dumps(formula, ensure_ascii=False, indent=2)}\n".encode()
        digest = hashlib.sha256(encoded).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / f"formula-{digest}.json"
            destination.write_bytes(b"existing manifest")

            with self.assertRaisesRegex(PipelineSnapshotError, "must not collide"):
                dump_pipeline_snapshots(
                    destination,
                    SAT_PATH,
                    self.formula,
                    self.region,
                )

            self.assertEqual(destination.read_bytes(), b"existing manifest")

    def test_exported_bundle_loads_without_site_packages_or_native_library(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_pipeline_snapshots(
                Path(directory) / "pipeline.explain.json",
                SAT_PATH,
                self.formula,
                self.region,
            )
            script = (
                "import sys; "
                "from formats.pipeline_snapshot import load_explainability_bundle; "
                "bundle=load_explainability_bundle(sys.argv[1]); "
                "assert bundle[0]['schema']=='wang-explain-manifest-v1'; "
                "assert 'z3' not in sys.modules and 'native._lib' not in sys.modules"
            )
            environment = {"PYTHONPATH": str(ROOT / "python")}
            completed = subprocess.run(
                [sys.executable, "-S", "-B", "-c", script, str(manifest_path)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_cli_exports_the_real_formula_to_region_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "nested" / "manifest.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/export_pipeline_snapshots.py"),
                    str(SAT_PATH),
                    str(manifest_path),
                    "--origin-x",
                    "-7",
                    "--origin-y",
                    "4",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            bundle = load_explainability_bundle(manifest_path)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"manifest={manifest_path}", completed.stdout)
        self.assertEqual(bundle[1]["source"]["name"], SAT_PATH.name)
        self.assertEqual(bundle[3]["bounds"]["min_x_inclusive"], -7)
        self.assertEqual(bundle[3]["bounds"]["min_y_inclusive"], 4)

    def test_cli_opt_in_exports_native_reduction_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "nested" / "manifest.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/export_pipeline_snapshots.py"),
                    str(SAT_PATH),
                    str(manifest_path),
                    "--reduction-explanation",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            bundle = load_reduction_explainability_bundle(manifest_path)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("reduction=", completed.stdout)
        self.assertEqual(bundle[0]["schema"], REDUCTION_MANIFEST_SCHEMA)
        self.assertEqual(bundle[4]["schema"], REDUCTION_SCHEMA)


if __name__ == "__main__":
    unittest.main()
