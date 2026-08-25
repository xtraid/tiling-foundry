"""Scoped ctypes adaptation for native Boolean/Wang witness operations."""

from collections.abc import Sequence
from ctypes import (
    CDLL,
    POINTER,
    Structure,
    byref,
    c_bool,
    c_char_p,
    c_int,
    c_size_t,
    c_uint8,
    c_uint32,
    c_uint64,
)
from enum import IntEnum
from functools import cache

from model.region import Region
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import TILE_COUNT
from native._lib import library
from native.formula_adapter import _Cm13Formula
from native.region_adapter import _Region, _YangZhangReduction


_TILE_NONE = 255


class NativeWitnessError(RuntimeError):
    """The native witness bridge or solver violated its public contract."""


class _WangSolveStatus(IntEnum):
    ERROR = -1
    UNSAT = 0
    SAT = 1


class _YangZhangWitnessStatus(IntEnum):
    ERROR = -1
    NO = 0
    YES = 1


class _YangZhangExtensionSolver(IntEnum):
    REFERENCE = 0
    OPTIMIZED = 1


class _WangSolverMetrics(Structure):
    _fields_ = [
        ("dfs_nodes", c_uint64),
        ("decisions", c_uint64),
        ("backtracks", c_uint64),
        ("failed_leaves", c_uint64),
        ("domain_reductions", c_uint64),
        ("propagated_arcs", c_uint64),
        ("support_tile_visits", c_uint64),
        ("support_byte_lookups", c_uint64),
        ("support_table_bytes", c_size_t),
        ("mrv_cells_scanned", c_uint64),
        ("initial_trail_writes", c_uint64),
        ("search_trail_writes", c_uint64),
        ("initial_trail_rewrites", c_uint64),
        ("search_trail_rewrites", c_uint64),
        ("trail_peak", c_size_t),
        ("trail_capacity_peak", c_size_t),
        ("trail_bytes_peak", c_size_t),
        ("enqueue_attempts", c_uint64),
        ("duplicate_enqueue_attempts", c_uint64),
        ("queue_dedup_index_bytes", c_size_t),
        ("queue_peak", c_size_t),
        ("queue_unique_peak", c_size_t),
        ("dfs_stack_capacity_peak", c_size_t),
        ("dfs_stack_bytes_peak", c_size_t),
        ("max_depth", c_size_t),
        ("sat_result_copy_bytes", c_size_t),
    ]


class _WangSolverOptions(Structure):
    _fields_ = [
        ("flags", c_uint32),
        ("failed_leaf_path", c_char_p),
        ("failed_leaf_capacity", c_size_t),
        ("initial_domains", POINTER(c_uint32)),
        ("initial_domain_count", c_size_t),
    ]


class _WangSolveResult(Structure):
    _fields_ = [
        ("domains", POINTER(c_uint32)),
        ("domain_count", c_size_t),
        ("conflict_cell", c_size_t),
        ("resolved_count", c_size_t),
        ("decision_depth", c_size_t),
        ("traced_leaf_count", c_size_t),
        ("trace_truncated", c_bool),
        ("metrics", _WangSolverMetrics),
    ]


@cache
def _witness_library() -> CDLL:
    lib = library()

    lib.yang_zhang_solve_assignment_extension.argtypes = [
        POINTER(_Cm13Formula),
        POINTER(_YangZhangReduction),
        POINTER(c_bool),
        c_size_t,
        c_int,
        POINTER(_WangSolveResult),
    ]
    lib.yang_zhang_solve_assignment_extension.restype = c_int
    lib.yang_zhang_extract_assignment.argtypes = [
        POINTER(_Cm13Formula),
        POINTER(_YangZhangReduction),
        POINTER(c_uint8),
        c_size_t,
        POINTER(c_bool),
        c_size_t,
    ]
    lib.yang_zhang_extract_assignment.restype = c_int
    lib.yang_zhang_witnesses_correspond.argtypes = [
        POINTER(_Cm13Formula),
        POINTER(_YangZhangReduction),
        POINTER(c_bool),
        c_size_t,
        POINTER(c_uint8),
        c_size_t,
    ]
    lib.yang_zhang_witnesses_correspond.restype = c_int
    solver_arguments = [
        POINTER(_Region),
        POINTER(_WangSolverOptions),
        POINTER(_WangSolveResult),
    ]
    lib.wang_solve_serial.argtypes = solver_arguments
    lib.wang_solve_serial.restype = c_int
    lib.wang_solve_optimized.argtypes = solver_arguments
    lib.wang_solve_optimized.restype = c_int
    lib.wang_solve_result_destroy.argtypes = [POINTER(_WangSolveResult)]
    lib.wang_solve_result_destroy.restype = None
    return lib


def _native_assignment(
    native_formula: _Cm13Formula,
    assignment: Sequence[bool],
) -> tuple[tuple[bool, ...], object]:
    try:
        copied = tuple(assignment)
    except TypeError as error:
        raise ValueError("assignment must be a finite Boolean sequence") from error
    if len(copied) != int(native_formula.variable_count):
        raise ValueError("assignment length must match the native formula")
    if any(type(value) is not bool for value in copied):
        raise ValueError("assignment must contain only booleans")
    return copied, (c_bool * len(copied))(*copied)


def _native_tiling(
    region: Region,
    tiling: Sequence[int | None],
) -> tuple[tuple[int | None, ...], object]:
    try:
        copied = tuple(tiling)
    except TypeError as error:
        raise ValueError("tiling must be a finite dense sequence") from error
    if len(copied) != len(region.active):
        raise ValueError("tiling length must match the region area")

    encoded: list[int] = []
    for active, tile_id in zip(region.active, copied, strict=True):
        if not active:
            if tile_id is not None:
                raise ValueError("inactive cells must contain None")
            encoded.append(_TILE_NONE)
            continue
        if type(tile_id) is not int or not 0 <= tile_id < TILE_COUNT:
            raise ValueError("active cells must contain a valid integer tile ID")
        encoded.append(tile_id)
    return copied, (c_uint8 * len(encoded))(*encoded)


def _solve_status(status_code: int, operation: str) -> _WangSolveStatus:
    try:
        status = _WangSolveStatus(status_code)
    except ValueError as error:
        raise NativeWitnessError(
            f"{operation} returned unknown native status {status_code}"
        ) from error
    if status is _WangSolveStatus.ERROR:
        raise NativeWitnessError(f"{operation} failed in native code")
    return status


def _witness_status(
    status_code: int,
    operation: str,
) -> _YangZhangWitnessStatus:
    try:
        status = _YangZhangWitnessStatus(status_code)
    except ValueError as error:
        raise NativeWitnessError(
            f"{operation} returned unknown native status {status_code}"
        ) from error
    if status is _YangZhangWitnessStatus.ERROR:
        raise NativeWitnessError(f"{operation} failed in native code")
    return status


def _copy_sat_tiling(
    region: Region,
    result: _WangSolveResult,
    operation: str,
) -> tuple[int | None, ...]:
    cell_count = len(region.active)
    if int(result.domain_count) != cell_count or not result.domains:
        raise NativeWitnessError(
            f"{operation} returned malformed SAT domain storage"
        )

    tiling: list[int | None] = []
    for index, active in enumerate(region.active):
        domain = int(result.domains[index])
        if not active:
            if domain != 0:
                raise NativeWitnessError(
                    f"{operation} assigned an inactive cell"
                )
            tiling.append(None)
            continue
        if domain == 0 or domain & (domain - 1):
            raise NativeWitnessError(
                f"{operation} returned a non-singleton active domain"
            )
        tile_id = domain.bit_length() - 1
        if tile_id >= TILE_COUNT:
            raise NativeWitnessError(
                f"{operation} returned a tile outside the canonical tileset"
            )
        tiling.append(tile_id)
    return tuple(tiling)


def _adapt_solve_result(
    status_code: int,
    result: _WangSolveResult,
    region: Region,
    operation: str,
) -> TilingSolveResult:
    status = _solve_status(status_code, operation)
    if status is _WangSolveStatus.UNSAT:
        return TilingSolveResult(TilingSolveStatus.UNSAT)
    return TilingSolveResult(
        TilingSolveStatus.SAT,
        _copy_sat_tiling(region, result, operation),
    )


def _solve_assignment_extension(
    native_formula: _Cm13Formula,
    native_reduction: _YangZhangReduction,
    region: Region,
    assignment: Sequence[bool],
    *,
    optimized: bool,
) -> TilingSolveResult:
    """Copy one native assignment extension result into Python storage."""
    _, native_assignment = _native_assignment(native_formula, assignment)
    solver = (
        _YangZhangExtensionSolver.OPTIMIZED
        if optimized
        else _YangZhangExtensionSolver.REFERENCE
    )
    lib = _witness_library()
    result = _WangSolveResult()
    try:
        status_code = lib.yang_zhang_solve_assignment_extension(
            byref(native_formula),
            byref(native_reduction),
            native_assignment,
            len(native_assignment),
            int(solver),
            byref(result),
        )
        return _adapt_solve_result(
            status_code,
            result,
            region,
            "assignment extension",
        )
    finally:
        lib.wang_solve_result_destroy(byref(result))


def _solve_native(
    native_reduction: _YangZhangReduction,
    region: Region,
    *,
    optimized: bool,
) -> TilingSolveResult:
    """Run one unconstrained native solve and copy its dense witness."""
    lib = _witness_library()
    solve = lib.wang_solve_optimized if optimized else lib.wang_solve_serial
    result = _WangSolveResult()
    try:
        status_code = solve(
            byref(native_reduction.region),
            None,
            byref(result),
        )
        return _adapt_solve_result(
            status_code,
            result,
            region,
            "native Wang solve",
        )
    finally:
        lib.wang_solve_result_destroy(byref(result))


def _extract_assignment(
    native_formula: _Cm13Formula,
    native_reduction: _YangZhangReduction,
    region: Region,
    tiling: Sequence[int | None],
) -> tuple[bool, ...] | None:
    """Validate and copy a decoded assignment without checking its clauses."""
    _, native_tiling = _native_tiling(region, tiling)
    assignment_count = int(native_formula.variable_count)
    native_assignment = (c_bool * assignment_count)()
    status_code = _witness_library().yang_zhang_extract_assignment(
        byref(native_formula),
        byref(native_reduction),
        native_tiling,
        len(native_tiling),
        native_assignment,
        assignment_count,
    )
    status = _witness_status(status_code, "assignment extraction")
    if status is _YangZhangWitnessStatus.NO:
        return None
    return tuple(bool(native_assignment[index]) for index in range(assignment_count))


def _witnesses_correspond(
    native_formula: _Cm13Formula,
    native_reduction: _YangZhangReduction,
    region: Region,
    assignment: Sequence[bool],
    tiling: Sequence[int | None],
) -> bool:
    """Return the native representation relation without clause evaluation."""
    _, native_assignment = _native_assignment(native_formula, assignment)
    _, native_tiling = _native_tiling(region, tiling)
    status_code = _witness_library().yang_zhang_witnesses_correspond(
        byref(native_formula),
        byref(native_reduction),
        native_assignment,
        len(native_assignment),
        native_tiling,
        len(native_tiling),
    )
    status = _witness_status(status_code, "witness correspondence")
    return status is _YangZhangWitnessStatus.YES
