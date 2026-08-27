import copy
import hashlib
import json
from pathlib import Path
import unittest

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _encode_document,
    build_region_snapshot,
)
from formats.z3_encoding_summary import (
    SCHEMA_NAME,
    build_boolean_z3_summary,
    build_wang_z3_summary,
    validate_z3_encoding_summary,
)
from native.reduction_adapter import load_formula_and_region


ROOT = Path(__file__).resolve().parents[2]
INSTANCE = ROOT / "tests/instances/pipeline_sat.cm13"
FIXTURES = ROOT / "tests/fixtures/pipeline_sat_z3"


class Z3EncodingSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.formula, cls.region = load_formula_and_region(INSTANCE)
        cls.source_digest = hashlib.sha256(INSTANCE.read_bytes()).hexdigest()
        region = build_region_snapshot(
            cls.region,
            source_formula_sha256=cls.source_digest,
            origin=(0, 0),
        )
        cls.region_digest = hashlib.sha256(_encode_document(region)).hexdigest()

    def _documents(self) -> dict[str, dict[str, object]]:
        return {
            "boolean-z3.json": build_boolean_z3_summary(
                self.formula,
                source_formula_sha256=self.source_digest,
            ),
            "wang-z3.json": build_wang_z3_summary(
                self.formula,
                self.region,
                source_formula_sha256=self.source_digest,
                region_sha256=self.region_digest,
            ),
        }

    def test_summaries_are_deterministic_and_match_committed_examples(self) -> None:
        first = self._documents()
        second = self._documents()
        self.assertEqual(first, second)
        for name, document in first.items():
            with self.subTest(name=name):
                validate_z3_encoding_summary(document)
                committed = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
                self.assertEqual(document, committed)
                self.assertEqual(document["z3"]["parameters"], {
                    "random_seed": 0,
                    "threads": 1,
                })
                self.assertEqual(document["status"], "sat")

    def test_boolean_and_wang_orders_are_explicit_and_distinct(self) -> None:
        documents = self._documents()
        boolean = documents["boolean-z3.json"]
        wang = documents["wang-z3.json"]

        self.assertEqual(boolean["semantics"], "encoding-order")
        self.assertEqual(boolean["encoding"]["assertion_count"], 3)
        self.assertEqual(boolean["model"]["assignment"], [False, True, False])
        self.assertEqual(wang["encoding"]["active_cell_count"], 444)
        self.assertEqual(wang["encoding"]["edge_term_count"], 944)
        self.assertEqual(wang["encoding"]["shared_internal_edge_count"], 832)
        self.assertEqual(wang["encoding"]["assertion_count"], 556)
        self.assertEqual(len(wang["model"]["cells"]), 451)

    def test_rejects_cross_engine_identity_and_unknown_fields(self) -> None:
        boolean = self._documents()["boolean-z3.json"]
        wrong_region = copy.deepcopy(boolean)
        wrong_region["region_sha256"] = "0" * 64
        with self.assertRaisesRegex(PipelineSnapshotError, "region_sha256"):
            validate_z3_encoding_summary(wrong_region)

        extra = copy.deepcopy(boolean)
        extra["debug_trace"] = []
        with self.assertRaisesRegex(PipelineSnapshotError, "unknown fields"):
            validate_z3_encoding_summary(extra)

    def test_rejects_inconsistent_wang_model_and_statistics(self) -> None:
        wang = self._documents()["wang-z3.json"]
        invalid_tile = copy.deepcopy(wang)
        cells = invalid_tile["model"]["cells"]
        active_index = next(
            index for index, tile_id in enumerate(cells) if tile_id is not None
        )
        cells[active_index] = invalid_tile["encoding"]["unique_tile_tuple_count"]
        with self.assertRaisesRegex(PipelineSnapshotError, "canonical tile table"):
            validate_z3_encoding_summary(invalid_tile)

        inconsistent_statistics = copy.deepcopy(wang)
        inconsistent_statistics["statistics"][1]["value"] += 1
        with self.assertRaisesRegex(PipelineSnapshotError, "project-owned counters"):
            validate_z3_encoding_summary(inconsistent_statistics)

    def test_publishes_closed_draft_2020_12_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/z3-encoding-summary-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(schema["properties"]["schema"]["const"], SCHEMA_NAME)
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
