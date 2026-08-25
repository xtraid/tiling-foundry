"""Deterministic producer for verified ``wang-solution-v1`` documents."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile

from formats.wang_solution import (
    GEOMETRY,
    SCHEMA_NAME,
    STATUS,
    validate_wang_solution,
)
from model.region import Region
from model.tiling import TilingSolveResult, TilingSolveStatus
from model.tileset import COLOR_NONE, TILESET
from oracles.tiling_check import is_valid_tiling


_DIRECTIONS = ("N", "E", "S", "W")


class WangSolutionExportError(ValueError):
    """Raised when producer inputs cannot form a v1 SAT document."""


def _copy_json_string(value: str, path: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise WangSolutionExportError(
            f"{path} must contain valid UTF-8 text"
        ) from error
    return value


def _copy_json_value(
    value: object,
    path: str,
    active_containers: set[int],
) -> object:
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        return _copy_json_string(value, path)
    if type(value) is float:
        if not math.isfinite(value):
            raise WangSolutionExportError(
                f"{path} must not contain a non-finite number"
            )
        return value
    if type(value) is list:
        identity = id(value)
        if identity in active_containers:
            raise WangSolutionExportError(f"{path} must not contain a cycle")
        active_containers.add(identity)
        try:
            return [
                _copy_json_value(
                    item,
                    f"{path}[{index}]",
                    active_containers,
                )
                for index, item in enumerate(value)
            ]
        finally:
            active_containers.remove(identity)
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise WangSolutionExportError(
                f"{path} object member names must be strings"
            )
        identity = id(value)
        if identity in active_containers:
            raise WangSolutionExportError(f"{path} must not contain a cycle")
        active_containers.add(identity)
        try:
            for key in value:
                _copy_json_string(key, f"{path} object member name")
            return {
                key: _copy_json_value(
                    value[key],
                    f"{path}.{key}",
                    active_containers,
                )
                for key in sorted(value)
            }
        finally:
            active_containers.remove(identity)
    raise WangSolutionExportError(f"{path} must contain only JSON values")


def _copy_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    if metadata is None:
        return {}
    if type(metadata) is not dict:
        raise WangSolutionExportError("metadata must be a JSON object")
    copied = _copy_json_value(metadata, "metadata", set())
    assert type(copied) is dict
    return copied


def _validate_origin(origin: tuple[int, int]) -> tuple[int, int]:
    if (
        type(origin) is not tuple
        or len(origin) != 2
        or any(type(coordinate) is not int for coordinate in origin)
    ):
        raise WangSolutionExportError(
            "origin must be an immutable pair of integer coordinates"
        )
    return origin


def _validated_tiling(
    region: Region,
    result: TilingSolveResult,
) -> tuple[int | None, ...]:
    if not isinstance(region, Region):
        raise TypeError("region must be a Region")
    if not isinstance(result, TilingSolveResult):
        raise TypeError("result must be a TilingSolveResult")
    if result.status is not TilingSolveStatus.SAT or result.tiling is None:
        raise WangSolutionExportError("only a SAT result can be exported")

    tiling = result.tiling
    if len(tiling) != region.width * region.height:
        raise WangSolutionExportError(
            "tiling length must match the region dimensions"
        )
    for index, (active, tile_id) in enumerate(
        zip(region.active, tiling, strict=True)
    ):
        if not active:
            if tile_id is not None:
                raise WangSolutionExportError(
                    f"inactive cell {index} must contain None"
                )
            continue
        if type(tile_id) is not int or not 0 <= tile_id < len(TILESET):
            raise WangSolutionExportError(
                f"active cell {index} must contain a canonical tile ID"
            )

    if not is_valid_tiling(region, TILESET, tiling):
        raise WangSolutionExportError(
            "tiling does not satisfy the region boundary and adjacency constraints"
        )
    return tiling


def build_wang_solution(
    region: Region,
    result: TilingSolveResult,
    *,
    origin: tuple[int, int],
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build and validate one self-contained square SAT solution document."""
    min_x, min_y = _validate_origin(origin)
    tiling = _validated_tiling(region, result)
    copied_metadata = _copy_metadata(metadata)

    tile_table = [
        {
            "tile_id": tile_id,
            "edges": {
                direction: tile[direction_index]
                for direction_index, direction in enumerate(_DIRECTIONS)
            },
        }
        for tile_id, tile in enumerate(TILESET)
    ]
    boundary = [
        None
        if not active
        else {
            direction: None if color == COLOR_NONE else color
            for direction, color in zip(
                _DIRECTIONS,
                sides,
                strict=True,
            )
        }
        for active, sides in zip(
            region.active,
            region.boundary,
            strict=True,
        )
    ]
    document: dict[str, object] = {
        "schema": SCHEMA_NAME,
        "status": STATUS,
        "geometry": GEOMETRY,
        "bounds": {
            "min_x_inclusive": min_x,
            "min_y_inclusive": min_y,
            "max_x_inclusive": min_x + region.width - 1,
            "max_y_inclusive": min_y + region.height - 1,
        },
        "tile_table": tile_table,
        "cells": list(tiling),
        "boundary": boundary,
        "metadata": copied_metadata,
    }
    validate_wang_solution(document)
    return document


def dump_wang_solution(
    path: str | Path,
    region: Region,
    result: TilingSolveResult,
    *,
    origin: tuple[int, int],
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and atomically write a deterministic UTF-8 v1 document."""
    document = build_wang_solution(
        region,
        result,
        origin=origin,
        metadata=metadata,
    )
    serialized = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    )
    encoded = f"{serialized}\n".encode("utf-8")
    destination = Path(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
