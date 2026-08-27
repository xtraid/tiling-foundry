"""Copy native Wang regions into immutable Python storage."""

from contextlib import contextmanager
from ctypes import (
    CDLL,
    POINTER,
    Structure,
    byref,
    c_bool,
    c_int,
    c_int32,
    c_size_t,
    c_uint32,
    c_uint8,
)
from functools import cache
from typing import Iterator

from model.region import Region
from model.reduction_explanation import (
    GADGET_CLAUSE,
    GADGET_CROSSOVER,
    GADGET_LEFT_FORWARD,
    GADGET_RIGHT_FORWARD,
    GADGET_VARIABLE,
    SIGNAL_REDUNDANT,
    SIGNAL_VARIABLE,
    ReductionExplanation,
    ReductionGadget,
    ReductionSignal,
)
from native._lib import library
from native.formula_adapter import _Cm13Formula


_DIRECTION_COUNT = 4


class _RegionCell(Structure):
    _fields_ = [
        ("active", c_bool),
        ("boundary", c_uint8 * _DIRECTION_COUNT),
    ]


class _Region(Structure):
    _fields_ = [
        ("width", c_int32),
        ("height", c_int32),
        ("cell_count", c_size_t),
        ("cells", POINTER(_RegionCell)),
    ]


class _AdjacentSwap(Structure):
    _fields_ = [("row", c_uint32)]


class _SignalToken(Structure):
    _fields_ = [
        ("kind", c_int),
        ("token_id", c_uint32),
        ("variable", c_uint32),
        ("occurrence", c_uint8),
    ]


class _ReductionGadgetSpan(Structure):
    _fields_ = [
        ("kind", c_int),
        ("ordinal", c_uint32),
        ("x_begin", c_int32),
        ("x_end", c_int32),
        ("y_begin", c_int32),
        ("y_end", c_int32),
        ("swap_row", c_uint32),
    ]


class _ReductionExplanation(Structure):
    _fields_ = [
        ("source_signals", POINTER(_SignalToken)),
        ("target_signals", POINTER(_SignalToken)),
        ("signal_count", c_size_t),
        ("gadgets", POINTER(_ReductionGadgetSpan)),
        ("gadget_count", c_size_t),
    ]


class _YangZhangReduction(Structure):
    _fields_ = [
        ("region", _Region),
        ("swaps", POINTER(_AdjacentSwap)),
        ("swap_count", c_size_t),
    ]


class _YangZhangExplainedReduction(Structure):
    _fields_ = [
        ("reduction", _YangZhangReduction),
        ("explanation", _ReductionExplanation),
    ]


class RegionBuildError(RuntimeError):
    """The native Yang–Zhang builder could not construct a region."""


@cache
def _region_library() -> CDLL:
    lib = library()
    lib.yang_zhang_build.argtypes = [
        POINTER(_Cm13Formula),
        POINTER(_YangZhangReduction),
    ]
    lib.yang_zhang_build.restype = c_bool
    lib.yang_zhang_build_explained.argtypes = [
        POINTER(_Cm13Formula),
        POINTER(_YangZhangExplainedReduction),
    ]
    lib.yang_zhang_build_explained.restype = c_bool
    lib.yang_zhang_reduction_destroy.argtypes = [
        POINTER(_YangZhangReduction)
    ]
    lib.yang_zhang_reduction_destroy.restype = None
    lib.yang_zhang_explained_reduction_destroy.argtypes = [
        POINTER(_YangZhangExplainedReduction)
    ]
    lib.yang_zhang_explained_reduction_destroy.restype = None
    return lib


def _copy_region(native_region: _Region) -> Region:
    width = int(native_region.width)
    height = int(native_region.height)
    cell_count = int(native_region.cell_count)
    if (
        width <= 0
        or height <= 0
        or cell_count != width * height
        or not native_region.cells
    ):
        raise RuntimeError("invalid native region metadata")

    active = tuple(
        bool(native_region.cells[index].active)
        for index in range(cell_count)
    )
    boundary = tuple(
        (
            int(native_region.cells[index].boundary[0]),
            int(native_region.cells[index].boundary[1]),
            int(native_region.cells[index].boundary[2]),
            int(native_region.cells[index].boundary[3]),
        )
        for index in range(cell_count)
    )

    return Region(
        width=width,
        height=height,
        active=active,
        boundary=boundary,
    )


def _copy_signal(native_signal: _SignalToken, row: int) -> ReductionSignal:
    kind = int(native_signal.kind)
    if kind == 0:
        return ReductionSignal(
            row=row,
            kind=SIGNAL_VARIABLE,
            token_id=int(native_signal.token_id),
            variable=int(native_signal.variable),
            occurrence=int(native_signal.occurrence),
        )
    if kind == 1:
        return ReductionSignal(
            row=row,
            kind=SIGNAL_REDUNDANT,
            token_id=int(native_signal.token_id),
            variable=None,
            occurrence=None,
        )
    raise RuntimeError(f"native explanation contains unknown signal kind {kind}")


_GADGET_KINDS = {
    0: GADGET_VARIABLE,
    1: GADGET_LEFT_FORWARD,
    2: GADGET_CROSSOVER,
    3: GADGET_RIGHT_FORWARD,
    4: GADGET_CLAUSE,
}
_NO_SWAP_ROW = 2**32 - 1


def _copy_gadget(native_gadget: _ReductionGadgetSpan) -> ReductionGadget:
    kind_value = int(native_gadget.kind)
    try:
        kind = _GADGET_KINDS[kind_value]
    except KeyError as error:
        raise RuntimeError(
            f"native explanation contains unknown gadget kind {kind_value}"
        ) from error
    swap_row_value = int(native_gadget.swap_row)
    return ReductionGadget(
        kind=kind,
        ordinal=int(native_gadget.ordinal),
        x_begin=int(native_gadget.x_begin),
        x_end=int(native_gadget.x_end),
        y_begin=int(native_gadget.y_begin),
        y_end=int(native_gadget.y_end),
        swap_row=None if swap_row_value == _NO_SWAP_ROW else swap_row_value,
    )


def _copy_reduction_explanation(
    native_reduction: _YangZhangExplainedReduction,
    variable_count: int,
) -> ReductionExplanation:
    native = native_reduction.explanation
    signal_count = int(native.signal_count)
    gadget_count = int(native.gadget_count)
    if signal_count <= 0 or not native.source_signals or not native.target_signals:
        raise RuntimeError("invalid native reduction signal storage")
    if gadget_count <= 0 or not native.gadgets:
        raise RuntimeError("invalid native reduction gadget storage")
    source = tuple(
        _copy_signal(native.source_signals[row], row)
        for row in range(signal_count)
    )
    target = tuple(
        _copy_signal(native.target_signals[row], row)
        for row in range(signal_count)
    )
    gadgets = tuple(
        _copy_gadget(native.gadgets[index])
        for index in range(gadget_count)
    )
    return ReductionExplanation(
        variable_count=variable_count,
        width=int(native_reduction.reduction.region.width),
        height=int(native_reduction.reduction.region.height),
        source_signals=source,
        target_signals=target,
        gadgets=gadgets,
    )


@contextmanager
def _built_reduction(
    native_formula: _Cm13Formula,
) -> Iterator[_YangZhangReduction]:
    native_reduction = _YangZhangReduction()
    lib = _region_library()
    try:
        if not lib.yang_zhang_build(
            byref(native_formula),
            byref(native_reduction),
        ):
            raise RegionBuildError("could not build Yang-Zhang region")
        yield native_reduction
    finally:
        lib.yang_zhang_reduction_destroy(byref(native_reduction))


@contextmanager
def _built_explained_reduction(
    native_formula: _Cm13Formula,
) -> Iterator[_YangZhangExplainedReduction]:
    native_reduction = _YangZhangExplainedReduction()
    lib = _region_library()
    try:
        if not lib.yang_zhang_build_explained(
            byref(native_formula),
            byref(native_reduction),
        ):
            raise RegionBuildError(
                "could not build explained Yang-Zhang region"
            )
        yield native_reduction
    finally:
        lib.yang_zhang_explained_reduction_destroy(byref(native_reduction))


def _build_region(native_formula: _Cm13Formula) -> Region:
    with _built_reduction(native_formula) as native_reduction:
        return _copy_region(native_reduction.region)


def _build_region_and_explanation(
    native_formula: _Cm13Formula,
) -> tuple[Region, ReductionExplanation]:
    with _built_explained_reduction(native_formula) as native_reduction:
        return (
            _copy_region(native_reduction.reduction.region),
            _copy_reduction_explanation(
                native_reduction,
                int(native_formula.variable_count),
            ),
        )
