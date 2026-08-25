import copy
import json
from pathlib import Path
import tempfile
import unittest

from formats.wang_solution import (
    WangSolutionValidationError,
    load_wang_solution,
    validate_wang_solution,
    validate_wang_solution_structure,
)
from model.region import Region
from model.tileset import COLOR_NONE, TILESET
from oracles.tiling_check import is_valid_tiling


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"
SCHEMA = ROOT / "schemas/wang-solution-v1.schema.json"
DIRECTIONS = ("N", "E", "S", "W")


def _fixture() -> dict[str, object]:
    with FIXTURE.open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert type(value) is dict
    return value


def _boundary_sides(document: dict[str, object], index: int) -> dict[str, object]:
    boundary = document["boundary"]
    assert type(boundary) is list
    sides = boundary[index]
    assert type(sides) is dict
    return sides


class WangSolutionSchemaTests(unittest.TestCase):
    def test_publishes_a_closed_draft_2020_12_sat_square_schema(self) -> None:
        with SCHEMA.open(encoding="utf-8") as stream:
            schema = json.load(stream)

        self.assertEqual(
            schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema"]["const"], "wang-solution-v1")
        self.assertEqual(schema["properties"]["status"]["const"], "SAT")
        self.assertEqual(schema["properties"]["geometry"]["const"], "square")

    def test_stdlib_structure_check_rejects_malformed_documents(self) -> None:
        mutations = {
            "wrong status": lambda value: value.__setitem__("status", "UNSAT"),
            "unknown field": lambda value: value.__setitem__("extra", None),
            "boolean tile id": lambda value: value["cells"].__setitem__(0, True),
            "boolean bound": lambda value: value["bounds"].__setitem__(
                "min_x_inclusive", False
            ),
            "boolean color": lambda value: value["tile_table"][0][
                "edges"
            ].__setitem__("N", True),
            "missing edge": lambda value: value["tile_table"][0]["edges"].pop("N"),
            "non-object metadata": lambda value: value.__setitem__("metadata", []),
        }

        for name, mutate in mutations.items():
            with self.subTest(name=name):
                document = _fixture()
                mutate(document)
                with self.assertRaises(WangSolutionValidationError):
                    validate_wang_solution_structure(document)


class WangSolutionSemanticTests(unittest.TestCase):
    def test_loads_the_golden_fixture_and_matches_the_canonical_tileset(self) -> None:
        document = load_wang_solution(FIXTURE)
        table = document["tile_table"]
        assert type(table) is list
        serialized_tileset = tuple(
            tuple(entry["edges"][direction] for direction in DIRECTIONS)
            for entry in table
        )
        bounds = document["bounds"]
        assert type(bounds) is dict
        width = bounds["max_x_inclusive"] - bounds["min_x_inclusive"] + 1
        height = bounds["max_y_inclusive"] - bounds["min_y_inclusive"] + 1
        cells = document["cells"]
        boundary = document["boundary"]
        assert type(cells) is list
        assert type(boundary) is list
        region = Region(
            width=width,
            height=height,
            active=tuple(tile_id is not None for tile_id in cells),
            boundary=tuple(
                (COLOR_NONE,) * 4
                if sides is None
                else tuple(
                    COLOR_NONE if sides[direction] is None else sides[direction]
                    for direction in DIRECTIONS
                )
                for sides in boundary
            ),
        )

        self.assertEqual(bounds["min_x_inclusive"], -1)
        self.assertEqual((width, height), (4, 3))
        self.assertEqual(len(cells), 12)
        self.assertEqual(cells.count(None), 2)
        self.assertEqual(serialized_tileset, TILESET)
        self.assertTrue(
            is_valid_tiling(region, serialized_tileset, tuple(cells))
        )

    def test_metadata_is_ignored_by_semantic_validation(self) -> None:
        document = _fixture()
        document["metadata"] = {
            "producer": "independent-test",
            "nested": [None, True, 1, 1.5, {"label": "display only"}],
        }

        validate_wang_solution(document)

    def test_rejects_cross_field_inconsistencies(self) -> None:
        def inverted_bounds(value: dict[str, object]) -> None:
            value["bounds"]["max_x_inclusive"] = -2

        def short_cells(value: dict[str, object]) -> None:
            value["cells"].pop()

        def short_boundary(value: dict[str, object]) -> None:
            value["boundary"].pop()

        def noncanonical_tile_table(value: dict[str, object]) -> None:
            value["tile_table"][0], value["tile_table"][1] = (
                value["tile_table"][1],
                value["tile_table"][0],
            )

        def absent_tile_reference(value: dict[str, object]) -> None:
            value["cells"][0] = len(value["tile_table"])

        def hole_with_boundary(value: dict[str, object]) -> None:
            value["boundary"][2] = {direction: None for direction in DIRECTIONS}

        def active_without_boundary(value: dict[str, object]) -> None:
            value["boundary"][0] = None

        def internal_boundary(value: dict[str, object]) -> None:
            _boundary_sides(value, 0)["E"] = 2

        def mismatched_boundary(value: dict[str, object]) -> None:
            _boundary_sides(value, 0)["N"] = 1

        def horizontal_mismatch(value: dict[str, object]) -> None:
            value["cells"][1] = 8
            _boundary_sides(value, 1)["E"] = 3

        def vertical_mismatch(value: dict[str, object]) -> None:
            value["cells"][4] = 0
            _boundary_sides(value, 4)["W"] = 1

        mutations = {
            "inverted inclusive bounds": inverted_bounds,
            "cell length versus bounds": short_cells,
            "boundary length versus bounds": short_boundary,
            "noncanonical tile table": noncanonical_tile_table,
            "absent tile reference": absent_tile_reference,
            "hole carrying boundary": hole_with_boundary,
            "active cell missing boundary": active_without_boundary,
            "constraint on internal edge": internal_boundary,
            "boundary versus selected tile": mismatched_boundary,
            "horizontal adjacency": horizontal_mismatch,
            "vertical adjacency": vertical_mismatch,
        }

        for name, mutate in mutations.items():
            with self.subTest(name=name):
                document = _fixture()
                mutate(document)
                with self.assertRaises(WangSolutionValidationError):
                    validate_wang_solution(document)

    def test_strict_loader_rejects_duplicate_members_and_nonfinite_numbers(self) -> None:
        invalid_documents = (
            '{"schema":"wang-solution-v1","schema":"duplicate"}',
            '{"metadata":{"not_json":NaN}}',
        )
        for source in invalid_documents:
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    path = Path(temporary_directory) / "invalid.json"
                    path.write_text(source, encoding="utf-8")
                    with self.assertRaises(WangSolutionValidationError):
                        load_wang_solution(path)

    def test_mutations_do_not_leak_between_cases(self) -> None:
        original = _fixture()
        mutated = copy.deepcopy(original)
        mutated["metadata"]["label"] = "changed"

        self.assertNotEqual(original, mutated)
        validate_wang_solution(original)


if __name__ == "__main__":
    unittest.main()
