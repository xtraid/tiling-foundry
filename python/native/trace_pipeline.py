"""One-lifetime native formula, reduction, solve, and trace orchestration."""

from model.formula import Formula
from model.reduction_explanation import ReductionExplanation
from model.region import Region
from model.solver_trace import SolverTrace
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import TILESET
from native.formula_adapter import PathLike, _copy_formula, _loaded_formula
from native.region_adapter import (
    _built_explained_reduction,
    _copy_reduction_explanation,
    _copy_region,
)
from native.solver_trace_adapter import _solve_native_traced
from native.witness_adapter import NativeWitnessError
from oracles.tiling_check import is_valid_tiling


def solve_native_pipeline_trace(
    path: PathLike,
    *,
    optimized: bool = False,
    event_capacity: int = 20_000,
    checkpoint_interval: int = 64,
    checkpoint_capacity: int = 64,
) -> tuple[
    Formula,
    Region,
    ReductionExplanation,
    TilingSolveResult,
    SolverTrace,
]:
    """Copy one observed native run before every C lifetime is released."""
    if type(optimized) is not bool:
        raise TypeError("optimized must be a boolean")

    with _loaded_formula(path) as native_formula:
        formula = _copy_formula(native_formula)
        with _built_explained_reduction(native_formula) as native_reduction:
            region = _copy_region(native_reduction.reduction.region)
            explanation = _copy_reduction_explanation(
                native_reduction,
                int(native_formula.variable_count),
            )
            result, trace = _solve_native_traced(
                native_reduction.reduction,
                region,
                optimized=optimized,
                event_capacity=event_capacity,
                checkpoint_interval=checkpoint_interval,
                checkpoint_capacity=checkpoint_capacity,
            )
            if result.status is TilingSolveStatus.SAT:
                if result.tiling is None or not is_valid_tiling(
                    region,
                    TILESET,
                    result.tiling,
                ):
                    raise NativeWitnessError(
                        "traced native SAT tiling was rejected by the Python checker"
                    )
            return formula, region, explanation, result, trace
