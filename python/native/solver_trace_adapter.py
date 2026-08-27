"""ctypes boundary for opt-in native Wang solver event traces."""

from __future__ import annotations

from ctypes import (
    CDLL,
    POINTER,
    Structure,
    byref,
    c_bool,
    c_int,
    c_size_t,
    c_uint32,
    c_uint64,
)
from functools import cache

from model.region import Region
from model.solver_trace import (
    SOLVER_OPTIMIZED,
    SOLVER_REFERENCE,
    TRACE_BACKTRACK,
    TRACE_CONFLICT,
    TRACE_DECISION,
    TRACE_DOMAIN_REDUCTION,
    TRACE_INITIAL,
    TRACE_PROPAGATION,
    TRACE_REASON_DECISION,
    TRACE_REASON_PROPAGATION,
    TRACE_RESULT,
    TRACE_ROOT,
    TRACE_SEARCH,
    SolverTrace,
    SolverTraceCheckpoint,
    SolverTraceEvent,
    replay_solver_trace,
)
from model.tiling import TilingSolveResult, TilingSolveStatus
from native._lib import library
from native.region_adapter import _Region, _YangZhangReduction
from native.witness_adapter import (
    NativeWitnessError,
    _WangSolveResult,
    _WangSolverOptions,
    _adapt_solve_result,
)


_SIZE_MAX = c_size_t(-1).value
_EVENT_KINDS = {
    0: TRACE_ROOT,
    1: TRACE_PROPAGATION,
    2: TRACE_DECISION,
    3: TRACE_DOMAIN_REDUCTION,
    4: TRACE_CONFLICT,
    5: TRACE_BACKTRACK,
    6: TRACE_RESULT,
}
_PHASES = {0: None, 1: TRACE_INITIAL, 2: TRACE_SEARCH}
_REASONS = {
    0: None,
    1: TRACE_REASON_DECISION,
    2: TRACE_REASON_PROPAGATION,
}
_STATUSES = {
    -1: None,
    0: TilingSolveStatus.UNSAT,
    1: TilingSolveStatus.SAT,
}


class _WangSolveTraceEvent(Structure):
    _fields_ = [
        ("sequence", c_uint64),
        ("kind", c_int),
        ("phase", c_int),
        ("reason", c_int),
        ("depth", c_size_t),
        ("cell_index", c_size_t),
        ("change_mark", c_size_t),
        ("old_domain", c_uint32),
        ("new_domain", c_uint32),
        ("status", c_int),
    ]


class _WangSolveTraceCheckpoint(Structure):
    _fields_ = [
        ("event_sequence", c_uint64),
        ("change_mark", c_size_t),
    ]


class _WangSolveTraceOptions(Structure):
    _fields_ = [
        ("event_capacity", c_size_t),
        ("checkpoint_interval", c_size_t),
        ("checkpoint_capacity", c_size_t),
    ]


class _WangSolveTrace(Structure):
    _fields_ = [
        ("initial_domains", POINTER(c_uint32)),
        ("domain_count", c_size_t),
        ("events", POINTER(_WangSolveTraceEvent)),
        ("event_count", c_size_t),
        ("observed_event_count", c_uint64),
        ("event_capacity", c_size_t),
        ("truncated", c_bool),
        ("checkpoints", POINTER(_WangSolveTraceCheckpoint)),
        ("checkpoint_domains", POINTER(c_uint32)),
        ("checkpoint_count", c_size_t),
        ("checkpoint_interval", c_size_t),
        ("checkpoint_capacity", c_size_t),
        ("checkpoints_truncated", c_bool),
    ]


class _WangTracedSolveResult(Structure):
    _fields_ = [
        ("solve", _WangSolveResult),
        ("trace", _WangSolveTrace),
    ]


@cache
def _trace_library() -> CDLL:
    lib = library()
    arguments = [
        POINTER(_Region),
        POINTER(_WangSolverOptions),
        POINTER(_WangSolveTraceOptions),
        POINTER(_WangTracedSolveResult),
    ]
    lib.wang_solve_serial_traced.argtypes = arguments
    lib.wang_solve_serial_traced.restype = c_int
    lib.wang_solve_optimized_traced.argtypes = arguments
    lib.wang_solve_optimized_traced.restype = c_int
    lib.wang_traced_solve_result_destroy.argtypes = [
        POINTER(_WangTracedSolveResult)
    ]
    lib.wang_traced_solve_result_destroy.restype = None
    return lib


def _enum_value(mapping: dict[int, object], value: int, label: str) -> object:
    try:
        return mapping[value]
    except KeyError as error:
        raise NativeWitnessError(
            f"native solver trace returned unknown {label} {value}"
        ) from error


def _copy_trace(
    native: _WangSolveTrace,
    region: Region,
    solver: str,
    status: TilingSolveStatus,
) -> SolverTrace:
    area = region.width * region.height
    domain_count = int(native.domain_count)
    event_count = int(native.event_count)
    checkpoint_count = int(native.checkpoint_count)
    if domain_count != area or not native.initial_domains:
        raise NativeWitnessError("native solver trace returned malformed root state")
    if event_count < 2 or event_count > int(native.event_capacity) or not native.events:
        raise NativeWitnessError("native solver trace returned malformed event storage")
    if checkpoint_count > int(native.checkpoint_capacity):
        raise NativeWitnessError("native solver trace exceeded checkpoint capacity")
    if checkpoint_count and (
        not native.checkpoints or not native.checkpoint_domains
    ):
        raise NativeWitnessError("native solver trace returned malformed checkpoints")

    initial_domains = tuple(
        int(native.initial_domains[index]) for index in range(domain_count)
    )
    events: list[SolverTraceEvent] = []
    for index in range(event_count):
        item = native.events[index]
        kind = _enum_value(_EVENT_KINDS, int(item.kind), "event kind")
        assert type(kind) is str
        phase = _enum_value(_PHASES, int(item.phase), "phase")
        reason = _enum_value(_REASONS, int(item.reason), "reason")
        event_status = _enum_value(_STATUSES, int(item.status), "status")
        cell_index = int(item.cell_index)
        cell = None if cell_index == _SIZE_MAX else cell_index
        carries_domains = kind in (TRACE_DECISION, TRACE_DOMAIN_REDUCTION)
        events.append(
            SolverTraceEvent(
                sequence=int(item.sequence),
                kind=kind,
                phase=phase if type(phase) is str else None,
                reason=reason if type(reason) is str else None,
                depth=int(item.depth),
                cell=cell,
                change_mark=int(item.change_mark),
                old_domain=int(item.old_domain) if carries_domains else None,
                new_domain=int(item.new_domain) if carries_domains else None,
                status=(
                    event_status
                    if type(event_status) is TilingSolveStatus
                    else None
                ),
            )
        )

    checkpoints = tuple(
        SolverTraceCheckpoint(
            event_sequence=int(native.checkpoints[index].event_sequence),
            change_mark=int(native.checkpoints[index].change_mark),
            domains=tuple(
                int(native.checkpoint_domains[index * domain_count + cell])
                for cell in range(domain_count)
            ),
        )
        for index in range(checkpoint_count)
    )
    return SolverTrace(
        solver=solver,
        status=status,
        width=region.width,
        height=region.height,
        initial_domains=initial_domains,
        events=tuple(events),
        observed_event_count=int(native.observed_event_count),
        event_capacity=int(native.event_capacity),
        truncated=bool(native.truncated),
        checkpoints=checkpoints,
        checkpoint_interval=int(native.checkpoint_interval),
        checkpoint_capacity=int(native.checkpoint_capacity),
        checkpoints_truncated=bool(native.checkpoints_truncated),
    )


def _solve_native_traced(
    native_reduction: _YangZhangReduction,
    region: Region,
    *,
    optimized: bool,
    event_capacity: int,
    checkpoint_interval: int,
    checkpoint_capacity: int,
) -> tuple[TilingSolveResult, SolverTrace]:
    """Run one traced solve and copy all caller-owned native storage."""
    for name, value in (
        ("event_capacity", event_capacity),
        ("checkpoint_interval", checkpoint_interval),
        ("checkpoint_capacity", checkpoint_capacity),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if event_capacity < 2:
        raise ValueError("event_capacity must be at least two")
    if (checkpoint_interval == 0) != (checkpoint_capacity == 0):
        raise ValueError(
            "checkpoint_interval and checkpoint_capacity must be jointly set"
        )

    native_options = _WangSolveTraceOptions(
        event_capacity=event_capacity,
        checkpoint_interval=checkpoint_interval,
        checkpoint_capacity=checkpoint_capacity,
    )
    lib = _trace_library()
    solve = (
        lib.wang_solve_optimized_traced
        if optimized
        else lib.wang_solve_serial_traced
    )
    solver = SOLVER_OPTIMIZED if optimized else SOLVER_REFERENCE
    native_result = _WangTracedSolveResult()
    try:
        status_code = solve(
            byref(native_reduction.region),
            None,
            byref(native_options),
            byref(native_result),
        )
        result = _adapt_solve_result(
            status_code,
            native_result.solve,
            region,
            "traced native Wang solve",
        )
        trace = _copy_trace(native_result.trace, region, solver, result.status)
        if result.status is TilingSolveStatus.SAT and not trace.truncated:
            assert result.tiling is not None
            expected = tuple(
                0 if tile_id is None else 1 << tile_id
                for tile_id in result.tiling
            )
            if replay_solver_trace(trace)[-1] != expected:
                raise NativeWitnessError(
                    "native solver trace does not replay to its SAT witness"
                )
        return result, trace
    finally:
        lib.wang_traced_solve_result_destroy(byref(native_result))
