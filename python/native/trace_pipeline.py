"""One-lifetime native formula, reduction, solve, and trace orchestration."""

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Callable

from model.formula import Formula
from model.reduction_explanation import ReductionExplanation
from model.region import Region
from model.solver_trace import DOMAIN_ALL, SolverTrace
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


@dataclass(frozen=True, slots=True)
class NativeTraceTimings:
    """Raw monotonic durations for the native stages of one observed run."""

    parse_ns: int
    region_build_ns: int
    solve_ns: int
    verify_ns: int

    def __post_init__(self) -> None:
        for name in ("parse_ns", "region_build_ns", "solve_ns", "verify_ns"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


NativeTraceValues = tuple[
    Formula,
    Region,
    ReductionExplanation,
    TilingSolveResult,
    SolverTrace,
]


def _elapsed_ns(clock_ns: Callable[[], int], started: int) -> int:
    finished = clock_ns()
    if type(started) is not int or type(finished) is not int or finished < started:
        raise RuntimeError("monotonic clock returned an invalid interval")
    return finished - started


def capture_native_pipeline_trace(
    path: PathLike,
    *,
    optimized: bool = False,
    event_capacity: int = 20_000,
    checkpoint_interval: int = 64,
    checkpoint_capacity: int = 64,
    initial_domains: Sequence[int] | None = None,
    initial_domain_overrides: Sequence[tuple[int, int]] | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> tuple[NativeTraceValues, NativeTraceTimings]:
    """Capture one traced run plus raw stage durations from a monotonic clock."""
    if type(optimized) is not bool:
        raise TypeError("optimized must be a boolean")
    if not callable(clock_ns):
        raise TypeError("clock_ns must be callable")
    if initial_domains is not None and initial_domain_overrides is not None:
        raise ValueError(
            "initial_domains and initial_domain_overrides are mutually exclusive"
        )

    started = clock_ns()
    with _loaded_formula(path) as native_formula:
        formula = _copy_formula(native_formula)
        parse_ns = _elapsed_ns(clock_ns, started)

        started = clock_ns()
        with _built_explained_reduction(native_formula) as native_reduction:
            region = _copy_region(native_reduction.reduction.region)
            explanation = _copy_reduction_explanation(
                native_reduction,
                int(native_formula.variable_count),
            )
            region_build_ns = _elapsed_ns(clock_ns, started)

            started = clock_ns()
            configured_domains = initial_domains
            if initial_domain_overrides is not None:
                configured = [DOMAIN_ALL if active else 0 for active in region.active]
                previous_cell = -1
                for index, override in enumerate(initial_domain_overrides):
                    if type(override) is not tuple or len(override) != 2:
                        raise ValueError(
                            f"initial_domain_overrides[{index}] must be a cell/domain pair"
                        )
                    cell, domain = override
                    if type(cell) is not int or cell <= previous_cell:
                        raise ValueError(
                            "initial_domain_overrides must use unique sorted cells"
                        )
                    if cell >= len(configured) or not region.active[cell]:
                        raise ValueError(
                            f"initial_domain_overrides[{index}] targets no active cell"
                        )
                    if type(domain) is not int or not 0 <= domain <= DOMAIN_ALL:
                        raise ValueError(
                            f"initial_domain_overrides[{index}] is not a Wang domain"
                        )
                    configured[cell] = domain
                    previous_cell = cell
                configured_domains = tuple(configured)
            result, trace = _solve_native_traced(
                native_reduction.reduction,
                region,
                optimized=optimized,
                event_capacity=event_capacity,
                checkpoint_interval=checkpoint_interval,
                checkpoint_capacity=checkpoint_capacity,
                initial_domains=configured_domains,
            )
            solve_ns = _elapsed_ns(clock_ns, started)

            started = clock_ns()
            if result.status is TilingSolveStatus.SAT:
                if result.tiling is None or not is_valid_tiling(
                    region,
                    TILESET,
                    result.tiling,
                ):
                    raise NativeWitnessError(
                        "traced native SAT tiling was rejected by the Python checker"
                    )
            verify_ns = _elapsed_ns(clock_ns, started)

    values: NativeTraceValues = (formula, region, explanation, result, trace)
    timings = NativeTraceTimings(
        parse_ns=parse_ns,
        region_build_ns=region_build_ns,
        solve_ns=solve_ns,
        verify_ns=verify_ns,
    )
    return values, timings


def solve_native_pipeline_trace(
    path: PathLike,
    *,
    optimized: bool = False,
    event_capacity: int = 20_000,
    checkpoint_interval: int = 64,
    checkpoint_capacity: int = 64,
    initial_domains: Sequence[int] | None = None,
    initial_domain_overrides: Sequence[tuple[int, int]] | None = None,
) -> NativeTraceValues:
    """Copy one observed native run before every C lifetime is released."""
    values, _ = capture_native_pipeline_trace(
        path,
        optimized=optimized,
        event_capacity=event_capacity,
        checkpoint_interval=checkpoint_interval,
        checkpoint_capacity=checkpoint_capacity,
        initial_domains=initial_domains,
        initial_domain_overrides=initial_domain_overrides,
    )
    return values
