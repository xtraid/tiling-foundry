"""Native-only Wang solve orchestration over one reduction lifetime."""

from model.region import Region
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import TILESET
from native.formula_adapter import PathLike, _loaded_formula
from native.region_adapter import _built_reduction, _copy_region
from native.witness_adapter import NativeWitnessError, _solve_native
from oracles.tiling_check import is_valid_tiling


def solve_native_tiling(
    path: PathLike,
    optimized: bool = False,
) -> tuple[Region, TilingSolveResult]:
    """Solve one parsed reduction without importing or invoking Z3.

    Native formula, reduction, and result storage are destroyed before the
    copied Python ``Region`` and ``TilingSolveResult`` reach the caller. Every
    SAT witness also passes the independent pure-Python tiling checker.
    """
    if type(optimized) is not bool:
        raise TypeError("optimized must be a boolean")

    with _loaded_formula(path) as native_formula:
        with _built_reduction(native_formula) as native_reduction:
            region = _copy_region(native_reduction.region)
            result = _solve_native(
                native_reduction,
                region,
                optimized=optimized,
            )
            if result.status is TilingSolveStatus.SAT:
                if result.tiling is None or not is_valid_tiling(
                    region,
                    TILESET,
                    result.tiling,
                ):
                    raise NativeWitnessError(
                        "native SAT tiling was rejected by the Python checker"
                    )
            return region, result
