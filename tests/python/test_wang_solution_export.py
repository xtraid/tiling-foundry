import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from formats.wang_solution import load_wang_solution
from formats.wang_solution_export import (
    WangSolutionExportError,
    build_wang_solution,
    dump_wang_solution,
)
from model.region import Region
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import COLOR_NONE, TILE_COUNT


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"


def _golden_region() -> Region:
    none = COLOR_NONE
    return Region(
        width=4,
        height=3,
        active=(
            True,
            True,
            False,
            True,
            True,
            True,
            False,
            True,
            True,
            True,
            True,
            True,
        ),
        boundary=(
            (0, none, none, 2),
            (0, 2, none, none),
            (none, none, none, none),
            (0, 2, none, 2),
            (none, none, none, 2),
            (none, 2, none, none),
            (none, none, none, none),
            (none, 2, none, 2),
            (none, none, 0, 2),
            (none, none, 0, none),
            (0, none, 0, none),
            (none, 2, 0, none),
        ),
    )


def _golden_result() -> TilingSolveResult:
    return TilingSolveResult(
        TilingSolveStatus.SAT,
        (7, 7, None, 7, 7, 7, None, 7, 7, 7, 7, 7),
    )


class TilingSolveResultModelTests(unittest.TestCase):
    def test_rejects_non_enum_status_and_mutable_storage(self) -> None:
        with self.assertRaisesRegex(TypeError, "status must be"):
            TilingSolveResult("sat")
        with self.assertRaisesRegex(TypeError, "immutable tuple"):
            TilingSolveResult(TilingSolveStatus.SAT, [7])


class WangSolutionBuildTests(unittest.TestCase):
    def test_builds_the_existing_golden_fixture_from_models(self) -> None:
        with FIXTURE.open(encoding="utf-8") as stream:
            expected = json.load(stream)

        document = build_wang_solution(
            _golden_region(),
            _golden_result(),
            origin=(-1, 2),
            metadata={
                "fixture": "canonical-tileset-square-with-holes",
                "note": "This object is not used to establish tiling correctness.",
            },
        )

        self.assertEqual(document, expected)

    def test_copies_and_recursively_orders_metadata(self) -> None:
        metadata = {
            "z": {"second": [2, {"z": 0, "a": 1}], "first": True},
            "a": "first",
        }
        document = build_wang_solution(
            _golden_region(),
            _golden_result(),
            origin=(0, 0),
            metadata=metadata,
        )
        copied = document["metadata"]
        assert type(copied) is dict

        self.assertEqual(list(copied), ["a", "z"])
        nested = copied["z"]
        assert type(nested) is dict
        self.assertEqual(list(nested), ["first", "second"])
        metadata["z"]["second"][1]["a"] = 99
        self.assertEqual(nested["second"][1]["a"], 1)

    def test_rejects_non_sat_results_and_invalid_origins(self) -> None:
        for status in (TilingSolveStatus.UNSAT, TilingSolveStatus.UNKNOWN):
            with self.subTest(status=status):
                with self.assertRaisesRegex(
                    WangSolutionExportError,
                    "only a SAT result",
                ):
                    build_wang_solution(
                        _golden_region(),
                        TilingSolveResult(status),
                        origin=(0, 0),
                    )

        for origin in ((0, False), [0, 0], (0,), (0, 0, 0)):
            with self.subTest(origin=origin):
                with self.assertRaisesRegex(
                    WangSolutionExportError,
                    "origin must be",
                ):
                    build_wang_solution(
                        _golden_region(),
                        _golden_result(),
                        origin=origin,
                    )

    def test_rejects_wrong_dimensions_inactive_values_and_tile_ids(self) -> None:
        valid = list(_golden_result().tiling)
        mutations = {
            "short dimensions": valid[:-1],
            "inactive assignment": valid[:2] + [7] + valid[3:],
            "active None": [None] + valid[1:],
            "boolean tile ID": [True] + valid[1:],
            "negative tile ID": [-1] + valid[1:],
            "absent tile ID": [TILE_COUNT] + valid[1:],
        }

        for name, tiling in mutations.items():
            with self.subTest(name=name):
                with self.assertRaises(WangSolutionExportError):
                    build_wang_solution(
                        _golden_region(),
                        TilingSolveResult(
                            TilingSolveStatus.SAT,
                            tuple(tiling),
                        ),
                        origin=(0, 0),
                    )

    def test_rejects_boundary_and_adjacency_violations(self) -> None:
        none = COLOR_NONE
        boundary_mismatch = Region(
            width=1,
            height=1,
            active=(True,),
            boundary=((1, none, none, none),),
        )
        adjacency_mismatch = Region(
            width=2,
            height=1,
            active=(True, True),
            boundary=((none,) * 4, (none,) * 4),
        )
        invalid = (
            (
                boundary_mismatch,
                TilingSolveResult(TilingSolveStatus.SAT, (7,)),
            ),
            (
                adjacency_mismatch,
                TilingSolveResult(TilingSolveStatus.SAT, (7, 8)),
            ),
        )

        for region, result in invalid:
            with self.subTest(region=region):
                with self.assertRaisesRegex(
                    WangSolutionExportError,
                    "boundary and adjacency",
                ):
                    build_wang_solution(region, result, origin=(0, 0))

    def test_rejects_metadata_outside_strict_json(self) -> None:
        cyclic: dict[str, object] = {}
        cyclic["self"] = cyclic
        invalid = (
            [],
            {1: "integer key"},
            {"tuple": (1, 2)},
            {"nan": float("nan")},
            {"infinity": float("inf")},
            {"surrogate": "\ud800"},
            cyclic,
        )
        for metadata in invalid:
            with self.subTest(metadata=metadata):
                with self.assertRaises(WangSolutionExportError):
                    build_wang_solution(
                        _golden_region(),
                        _golden_result(),
                        origin=(0, 0),
                        metadata=metadata,
                    )


class WangSolutionDumpTests(unittest.TestCase):
    def test_dump_is_deterministic_and_round_trips_through_the_strict_loader(
        self,
    ) -> None:
        first_metadata = {
            "z": {"z": 2, "a": 1},
            "a": "ordered",
        }
        second_metadata = {
            "a": "ordered",
            "z": {"a": 1, "z": 2},
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first.json"
            second = Path(temporary_directory) / "second.json"
            dump_wang_solution(
                first,
                _golden_region(),
                _golden_result(),
                origin=(-1, 2),
                metadata=first_metadata,
            )
            dump_wang_solution(
                second,
                _golden_region(),
                _golden_result(),
                origin=(-1, 2),
                metadata=second_metadata,
            )

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertTrue(first.read_bytes().endswith(b"\n"))
            self.assertEqual(
                load_wang_solution(first),
                load_wang_solution(second),
            )

    def test_invalid_input_does_not_replace_an_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "solution.json"
            destination.write_text("preserve me\n", encoding="utf-8")

            with self.assertRaises(WangSolutionExportError):
                dump_wang_solution(
                    destination,
                    _golden_region(),
                    TilingSolveResult(TilingSolveStatus.UNSAT),
                    origin=(0, 0),
                )

            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "preserve me\n",
            )

    def test_write_failure_preserves_existing_output_and_removes_temporary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "solution.json"
            destination.write_text("preserve me\n", encoding="utf-8")

            with patch(
                "formats.wang_solution_export.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    dump_wang_solution(
                        destination,
                        _golden_region(),
                        _golden_result(),
                        origin=(0, 0),
                    )

            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "preserve me\n",
            )
            self.assertEqual(list(Path(temporary_directory).iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
