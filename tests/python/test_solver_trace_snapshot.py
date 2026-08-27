import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from formats.pipeline_snapshot import PipelineSnapshotError
from formats.solver_trace_snapshot import (
    TRACE_MANIFEST_SCHEMA,
    TRACE_SCHEMA,
    build_solver_trace_snapshot,
    dump_solver_trace_bundle,
    load_solver_trace_bundle,
    validate_solver_trace_manifest,
    validate_solver_trace_snapshot,
)
from native.trace_pipeline import solve_native_pipeline_trace


ROOT = Path(__file__).resolve().parents[2]
INSTANCE = ROOT / "tests/instances/pipeline_sat.cm13"
COMMITTED = ROOT / "tests/fixtures/pipeline_sat_solver_trace"


class SolverTraceSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.values = solve_native_pipeline_trace(
            INSTANCE,
            event_capacity=4096,
            checkpoint_interval=128,
            checkpoint_capacity=32,
        )

    def test_builds_closed_replayable_trace(self) -> None:
        formula, region, explanation, result, trace = self.values
        del formula, explanation
        document = build_solver_trace_snapshot(
            trace,
            source_formula_sha256="1" * 64,
            region_sha256="2" * 64,
            solution_sha256="3" * 64,
        )

        validate_solver_trace_snapshot(document)
        self.assertEqual(document["schema"], TRACE_SCHEMA)
        self.assertEqual(document["semantics"], "observed")
        self.assertEqual(document["solver"], "reference")
        self.assertEqual(document["layout"]["width"], region.width)
        self.assertEqual(document["status"], result.status.value)

        corrupted = copy.deepcopy(document)
        event = next(
            item
            for item in corrupted["events"]
            if item["kind"] == "domain_reduction"
        )
        event["old_domain"] ^= 1
        with self.assertRaisesRegex(PipelineSnapshotError, "old_domain"):
            validate_solver_trace_snapshot(corrupted)

    def test_dump_is_deterministic_hash_bound_and_cross_checked(self) -> None:
        generated: list[dict[str, bytes]] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                manifest_path = dump_solver_trace_bundle(
                    Path(directory) / "manifest.json",
                    INSTANCE,
                    *self.values,
                )
                manifest, documents = load_solver_trace_bundle(manifest_path)
                validate_solver_trace_manifest(manifest)
                generated.append(
                    {
                        path.name: path.read_bytes()
                        for path in manifest_path.parent.iterdir()
                    }
                )
                self.assertEqual(manifest["schema"], TRACE_MANIFEST_SCHEMA)
                self.assertEqual(set(documents), {
                    "formula",
                    "tileset",
                    "region",
                    "reduction",
                    "trace",
                    "solution",
                })
                for reference in manifest["artifacts"].values():
                    if reference is None:
                        continue
                    encoded = (manifest_path.parent / reference["path"]).read_bytes()
                    self.assertEqual(
                        hashlib.sha256(encoded).hexdigest(),
                        reference["sha256"],
                    )
        self.assertEqual(generated[0], generated[1])
        committed = {
            path.name: path.read_bytes() for path in COMMITTED.iterdir()
        }
        self.assertEqual(generated[0], committed)

    def test_loader_rejects_a_changed_trace_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_solver_trace_bundle(
                Path(directory) / "manifest.json",
                INSTANCE,
                *self.values,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            trace_path = manifest_path.parent / manifest["artifacts"]["trace"]["path"]
            trace_path.write_bytes(trace_path.read_bytes() + b" ")
            with self.assertRaisesRegex(PipelineSnapshotError, "sha256"):
                load_solver_trace_bundle(manifest_path)

    def test_loader_rejects_trace_state_on_an_inactive_region_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = dump_solver_trace_bundle(
                Path(directory) / "manifest.json",
                INSTANCE,
                *self.values,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            region_path = (
                manifest_path.parent / manifest["artifacts"]["region"]["path"]
            )
            trace_path = (
                manifest_path.parent / manifest["artifacts"]["trace"]["path"]
            )
            region = json.loads(region_path.read_text(encoding="utf-8"))
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            inactive = region["active"].index(False)
            trace["initial_domains"][inactive] = 1
            for checkpoint in trace["checkpoints"]:
                checkpoint["domains"][inactive] = 1
            encoded = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
            trace_path.write_bytes(encoded)
            manifest["artifacts"]["trace"]["sha256"] = hashlib.sha256(
                encoded
            ).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(PipelineSnapshotError, "inactive cell"):
                load_solver_trace_bundle(manifest_path)

    def test_publishes_closed_draft_2020_12_schemas(self) -> None:
        for contract in (TRACE_SCHEMA, TRACE_MANIFEST_SCHEMA):
            with self.subTest(contract=contract):
                schema = json.loads(
                    (ROOT / "schemas" / f"{contract}.schema.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(schema["properties"]["schema"]["const"], contract)
                self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
