"""Fixed one-lifetime native capture for the full-pipeline v2 dossier."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
from typing import Callable

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
from native.witness_adapter import NativeWitnessError, _extract_assignment
from oracles.tiling_check import is_valid_tiling
from oracles.witness_check import is_valid_assignment


@dataclass(frozen=True, slots=True)
class TraceCaptureOptions:
    """Closed traced-solver options for one named native engine."""

    event_capacity: int
    checkpoint_interval: int
    checkpoint_capacity: int

    def __post_init__(self) -> None:
        for name in (
            "event_capacity",
            "checkpoint_interval",
            "checkpoint_capacity",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.event_capacity < 2:
            raise ValueError("event_capacity must be at least two")
        if (self.checkpoint_interval == 0) != (self.checkpoint_capacity == 0):
            raise ValueError(
                "checkpoint_interval and checkpoint_capacity must be jointly set"
            )


@dataclass(frozen=True, slots=True)
class NativeEngineCapture:
    """Fully copied result, trace, and decoded assignment for one solver."""

    result: TilingSolveResult
    trace: SolverTrace
    extracted_assignment: tuple[bool, ...] | None


@dataclass(frozen=True, slots=True)
class MultiEngineNativeTimings:
    """Run-specific monotonic durations for the fixed native capture."""

    parse_ns: int
    reduction_ns: int
    reference_solve_ns: int
    reference_verify_ns: int | None
    optimized_solve_ns: int
    optimized_verify_ns: int | None

    def __post_init__(self) -> None:
        for name in (
            "parse_ns",
            "reduction_ns",
            "reference_solve_ns",
            "optimized_solve_ns",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in ("reference_verify_ns", "optimized_verify_ns"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be null or a nonnegative integer")


@dataclass(frozen=True, slots=True)
class MultiEngineNativeCapture:
    """All Python-owned values copied before the shared C lifetime ends."""

    formula: Formula
    region: Region
    explanation: ReductionExplanation
    reference: NativeEngineCapture
    optimized: NativeEngineCapture
    timings: MultiEngineNativeTimings


def _elapsed_ns(clock_ns: Callable[[], int], started: int) -> int:
    finished = clock_ns()
    if type(started) is not int or type(finished) is not int or finished < started:
        raise RuntimeError("monotonic clock returned an invalid interval")
    return finished - started


def _verify_and_extract(
    native_formula: object,
    native_reduction: object,
    formula: Formula,
    region: Region,
    result: TilingSolveResult,
) -> tuple[bool, ...] | None:
    if result.status is TilingSolveStatus.UNSAT:
        return None
    if result.status is not TilingSolveStatus.SAT or result.tiling is None:
        raise NativeWitnessError("native dossier solve returned an unsupported result")
    if not is_valid_tiling(region, TILESET, result.tiling):
        raise NativeWitnessError(
            "native dossier SAT tiling was rejected by the Python checker"
        )
    assignment = _extract_assignment(
        native_formula,
        native_reduction,
        region,
        result.tiling,
    )
    if assignment is None or not is_valid_assignment(formula, assignment):
        raise NativeWitnessError(
            "native dossier SAT tiling did not decode to a valid assignment"
        )
    return assignment


def capture_multi_engine_native_pipeline(
    path: PathLike,
    *,
    reference_options: TraceCaptureOptions,
    optimized_options: TraceCaptureOptions,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> MultiEngineNativeCapture:
    """Parse and reduce once, then capture reference and optimized exactly once."""
    if not isinstance(reference_options, TraceCaptureOptions):
        raise TypeError("reference_options must be TraceCaptureOptions")
    if not isinstance(optimized_options, TraceCaptureOptions):
        raise TypeError("optimized_options must be TraceCaptureOptions")
    if not callable(clock_ns):
        raise TypeError("clock_ns must be callable")

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
            reduction_ns = _elapsed_ns(clock_ns, started)

            captures: dict[str, NativeEngineCapture] = {}
            solve_timings: dict[str, int] = {}
            verify_timings: dict[str, int | None] = {}
            for name, optimized, options in (
                ("reference", False, reference_options),
                ("optimized", True, optimized_options),
            ):
                started = clock_ns()
                result, trace = _solve_native_traced(
                    native_reduction.reduction,
                    region,
                    optimized=optimized,
                    event_capacity=options.event_capacity,
                    checkpoint_interval=options.checkpoint_interval,
                    checkpoint_capacity=options.checkpoint_capacity,
                )
                solve_timings[name] = _elapsed_ns(clock_ns, started)

                if result.status is TilingSolveStatus.SAT:
                    started = clock_ns()
                    assignment = _verify_and_extract(
                        native_formula,
                        native_reduction.reduction,
                        formula,
                        region,
                        result,
                    )
                    verify_timings[name] = _elapsed_ns(clock_ns, started)
                else:
                    assignment = _verify_and_extract(
                        native_formula,
                        native_reduction.reduction,
                        formula,
                        region,
                        result,
                    )
                    verify_timings[name] = None
                captures[name] = NativeEngineCapture(result, trace, assignment)

    return MultiEngineNativeCapture(
        formula=formula,
        region=region,
        explanation=explanation,
        reference=captures["reference"],
        optimized=captures["optimized"],
        timings=MultiEngineNativeTimings(
            parse_ns=parse_ns,
            reduction_ns=reduction_ns,
            reference_solve_ns=solve_timings["reference"],
            reference_verify_ns=verify_timings["reference"],
            optimized_solve_ns=solve_timings["optimized"],
            optimized_verify_ns=verify_timings["optimized"],
        ),
    )
