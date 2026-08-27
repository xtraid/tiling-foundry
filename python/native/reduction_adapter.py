"""Coordinate one native parse into Python formula and region models."""

from model.formula import Formula
from model.reduction_explanation import ReductionExplanation
from model.region import Region
from native.formula_adapter import PathLike, _copy_formula, _loaded_formula
from native.region_adapter import _build_region, _build_region_and_explanation


def load_formula_and_region(path: PathLike) -> tuple[Formula, Region]:
    """Parse once, build the Yang–Zhang region, and copy both results."""

    with _loaded_formula(path) as native_formula:
        formula = _copy_formula(native_formula)
        region = _build_region(native_formula)
        return formula, region


def load_formula_region_and_explanation(
    path: PathLike,
) -> tuple[Formula, Region, ReductionExplanation]:
    """Parse once and copy the native region with its actual provenance."""

    with _loaded_formula(path) as native_formula:
        formula = _copy_formula(native_formula)
        region, explanation = _build_region_and_explanation(native_formula)
        return formula, region, explanation
