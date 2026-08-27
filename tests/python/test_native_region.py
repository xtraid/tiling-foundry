from pathlib import Path
import unittest
from unittest.mock import patch

from model.formula import Formula
from model.region import COLOR_NONE
from native.formula_adapter import FormulaParseStatus, _Cm13Formula
from native.region_adapter import (
    RegionBuildError,
    _Region,
    _RegionCell,
    _build_region,
    _copy_region,
)
from native.reduction_adapter import (
    load_formula_and_region,
    load_formula_region_and_explanation,
)


INSTANCE_DIRECTORY = Path(__file__).resolve().parents[1] / "instances"


class NativeRegionCopyTests(unittest.TestCase):
    def test_copies_dense_region_into_python_owned_storage(self) -> None:
        no_boundary = (255, 255, 255, 255)
        cells = (_RegionCell * 3)()
        cells[0].active = True
        cells[0].boundary[:] = (0, 1, 2, 3)
        cells[1].active = False
        cells[1].boundary[:] = no_boundary
        cells[2].active = True
        cells[2].boundary[:] = (4, 5, 6, 7)
        native_region = _Region(
            width=3,
            height=1,
            cell_count=3,
            cells=cells,
        )

        region = _copy_region(native_region)
        cells[0].active = False
        cells[0].boundary[0] = 15

        self.assertEqual((region.width, region.height), (3, 1))
        self.assertEqual(region.active, (True, False, True))
        self.assertEqual(
            region.boundary,
            ((0, 1, 2, 3), no_boundary, (4, 5, 6, 7)),
        )

    def test_loads_formula_and_builds_region_from_one_native_parse(self) -> None:
        formula, region = load_formula_and_region(
            INSTANCE_DIRECTORY / "pipeline_sat.cm13"
        )

        self.assertEqual(formula.variable_count, 3)
        self.assertEqual((region.width, region.height), (41, 11))
        self.assertEqual(len(region.active), region.width * region.height)
        self.assertEqual(sum(region.active), 444)
        self.assertEqual(
            sum(
                color != COLOR_NONE
                for sides in region.boundary
                for color in sides
            ),
            112,
        )

    def test_copies_native_reduction_explanation_before_cleanup(self) -> None:
        formula, region, explanation = load_formula_region_and_explanation(
            INSTANCE_DIRECTORY / "pipeline_sat.cm13"
        )

        self.assertEqual(explanation.variable_count, formula.variable_count)
        self.assertEqual(
            (explanation.width, explanation.height),
            (region.width, region.height),
        )
        self.assertEqual(
            tuple(signal.token_id for signal in explanation.source_signals),
            (0, 1, 2, 9, 3, 4, 5, 10, 6, 7, 8),
        )
        self.assertEqual(
            tuple(signal.token_id for signal in explanation.target_signals),
            (0, 1, 3, 9, 2, 4, 6, 10, 5, 7, 8),
        )
        crossovers = tuple(
            gadget
            for gadget in explanation.gadgets
            if gadget.kind == "crossover"
        )
        self.assertEqual(len(crossovers), 6)
        self.assertEqual(crossovers[0].x_begin, 3)
        self.assertEqual(crossovers[-1].x_end, 37)

    def test_rejects_invalid_native_extent_before_copying(self) -> None:
        cells = (_RegionCell * 1)()
        invalid_regions = (
            _Region(width=2, height=1, cell_count=1, cells=cells),
            _Region(width=1, height=1, cell_count=1, cells=None),
        )

        for native_region in invalid_regions:
            with self.subTest(native_region=native_region):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "invalid native region metadata",
                ):
                    _copy_region(native_region)

    def test_releases_native_reduction_when_python_copy_fails(self) -> None:
        class RecordingLibrary:
            destroyed = False

            @staticmethod
            def yang_zhang_build(formula, reduction):
                return True

            def yang_zhang_reduction_destroy(self, reduction):
                self.destroyed = True

        library = RecordingLibrary()
        with patch(
            "native.region_adapter._region_library",
            return_value=library,
        ), patch(
            "native.region_adapter._copy_region",
            side_effect=RuntimeError("copy failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "copy failed"):
                _build_region(_Cm13Formula())

        self.assertTrue(library.destroyed)

    def test_releases_native_reduction_when_build_fails(self) -> None:
        class RecordingLibrary:
            destroyed = False

            @staticmethod
            def yang_zhang_build(formula, reduction):
                return False

            def yang_zhang_reduction_destroy(self, reduction):
                self.destroyed = True

        library = RecordingLibrary()
        with patch(
            "native.region_adapter._region_library",
            return_value=library,
        ):
            with self.assertRaisesRegex(RegionBuildError, "could not build"):
                _build_region(_Cm13Formula())

        self.assertTrue(library.destroyed)

    def test_coordinator_parses_once_and_releases_formula_on_failure(self) -> None:
        class RecordingLibrary:
            load_count = 0
            destroyed = False

            def cm13_formula_load_path(self, path, formula, location):
                self.load_count += 1
                return FormulaParseStatus.OK

            def cm13_formula_destroy(self, formula):
                self.destroyed = True

        library = RecordingLibrary()
        formula = Formula(variable_count=1, clauses=((0, 0, 0),))
        with patch(
            "native.formula_adapter._formula_library",
            return_value=library,
        ), patch(
            "native.reduction_adapter._copy_formula",
            return_value=formula,
        ), patch(
            "native.reduction_adapter._build_region",
            side_effect=RuntimeError("build failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                load_formula_and_region("ignored.cm13")

        self.assertEqual(library.load_count, 1)
        self.assertTrue(library.destroyed)


if __name__ == "__main__":
    unittest.main()
