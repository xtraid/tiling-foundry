"""Standard-library validation for the ``wang-solution-v1`` contract."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final


SCHEMA_NAME: Final = "wang-solution-v1"
GEOMETRY: Final = "square"
STATUS: Final = "SAT"
_DIRECTIONS: Final = ("N", "E", "S", "W")
_OFFSETS: Final = ((0, -1), (1, 0), (0, 1), (-1, 0))
_OPPOSITE: Final = (2, 3, 0, 1)
_TOP_LEVEL_FIELDS: Final = frozenset(
    {
        "schema",
        "status",
        "geometry",
        "bounds",
        "tile_table",
        "cells",
        "boundary",
        "metadata",
    }
)
_BOUND_FIELDS: Final = frozenset(
    {
        "min_x_inclusive",
        "min_y_inclusive",
        "max_x_inclusive",
        "max_y_inclusive",
    }
)


class WangSolutionValidationError(ValueError):
    """Raised when a document violates the v1 structure or semantics."""


def _fail(path: str, message: str) -> None:
    raise WangSolutionValidationError(f"{path}: {message}")


def _require_object(value: object, path: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(path, "must be an object")
    return value


def _require_array(value: object, path: str) -> list[object]:
    if type(value) is not list:
        _fail(path, "must be an array")
    return value


def _require_integer(value: object, path: str, *, nonnegative: bool) -> int:
    if type(value) is not int:
        _fail(path, "must be an integer")
    if nonnegative and value < 0:
        _fail(path, "must be nonnegative")
    return value


def _require_exact_fields(
    value: dict[str, object],
    expected: frozenset[str],
    path: str,
) -> None:
    if any(type(key) is not str for key in value):
        _fail(path, "object member names must be strings")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(extra)}")


def _validate_json_value(value: object, path: str) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            _fail(path, "must not contain a non-finite number")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail(path, "object member names must be strings")
            _validate_json_value(item, f"{path}.{key}")
        return
    _fail(path, "must contain only JSON values")


def _validate_edges(
    value: object,
    path: str,
    *,
    optional: bool,
) -> None:
    edges = _require_object(value, path)
    _require_exact_fields(edges, frozenset(_DIRECTIONS), path)
    for direction in _DIRECTIONS:
        color = edges[direction]
        if optional and color is None:
            continue
        _require_integer(color, f"{path}.{direction}", nonnegative=True)


def validate_wang_solution_structure(document: object) -> None:
    """Validate the constraints expressible by the published JSON Schema.

    This stdlib mirror lets consumers reject malformed input without adding a
    JSON Schema implementation. It intentionally does not establish that the
    arrays, identifiers, boundaries, and adjacent tiles describe one tiling.
    """
    root = _require_object(document, "$")
    _require_exact_fields(root, _TOP_LEVEL_FIELDS, "$")

    for field, expected in (
        ("schema", SCHEMA_NAME),
        ("status", STATUS),
        ("geometry", GEOMETRY),
    ):
        if root[field] != expected or type(root[field]) is not str:
            _fail(f"$.{field}", f"must equal {expected!r}")

    bounds = _require_object(root["bounds"], "$.bounds")
    _require_exact_fields(bounds, _BOUND_FIELDS, "$.bounds")
    for field in sorted(_BOUND_FIELDS):
        _require_integer(bounds[field], f"$.bounds.{field}", nonnegative=False)

    tile_table = _require_array(root["tile_table"], "$.tile_table")
    if not tile_table:
        _fail("$.tile_table", "must not be empty")
    for index, raw_tile in enumerate(tile_table):
        path = f"$.tile_table[{index}]"
        tile = _require_object(raw_tile, path)
        _require_exact_fields(tile, frozenset({"tile_id", "edges"}), path)
        _require_integer(tile["tile_id"], f"{path}.tile_id", nonnegative=True)
        _validate_edges(tile["edges"], f"{path}.edges", optional=False)

    cells = _require_array(root["cells"], "$.cells")
    if not cells:
        _fail("$.cells", "must not be empty")
    for index, tile_id in enumerate(cells):
        if tile_id is not None:
            _require_integer(tile_id, f"$.cells[{index}]", nonnegative=True)

    boundary = _require_array(root["boundary"], "$.boundary")
    if not boundary:
        _fail("$.boundary", "must not be empty")
    for index, sides in enumerate(boundary):
        if sides is not None:
            _validate_edges(sides, f"$.boundary[{index}]", optional=True)

    metadata = _require_object(root["metadata"], "$.metadata")
    _validate_json_value(metadata, "$.metadata")


def validate_wang_solution(document: object) -> None:
    """Validate v1 structure and all square-tiling cross-field semantics."""
    validate_wang_solution_structure(document)
    root = _require_object(document, "$")
    bounds = _require_object(root["bounds"], "$.bounds")

    min_x = _require_integer(
        bounds["min_x_inclusive"],
        "$.bounds.min_x_inclusive",
        nonnegative=False,
    )
    min_y = _require_integer(
        bounds["min_y_inclusive"],
        "$.bounds.min_y_inclusive",
        nonnegative=False,
    )
    max_x = _require_integer(
        bounds["max_x_inclusive"],
        "$.bounds.max_x_inclusive",
        nonnegative=False,
    )
    max_y = _require_integer(
        bounds["max_y_inclusive"],
        "$.bounds.max_y_inclusive",
        nonnegative=False,
    )
    if max_x < min_x:
        _fail("$.bounds", "max_x_inclusive must be at least min_x_inclusive")
    if max_y < min_y:
        _fail("$.bounds", "max_y_inclusive must be at least min_y_inclusive")

    width = max_x - min_x + 1
    height = max_y - min_y + 1
    area = width * height
    cells = _require_array(root["cells"], "$.cells")
    boundary = _require_array(root["boundary"], "$.boundary")
    if len(cells) != area:
        _fail("$.cells", f"length must equal inclusive bounds area {area}")
    if len(boundary) != area:
        _fail("$.boundary", f"length must equal inclusive bounds area {area}")

    raw_table = _require_array(root["tile_table"], "$.tile_table")
    tiles: list[tuple[int, int, int, int]] = []
    for expected_id, raw_tile in enumerate(raw_table):
        tile = _require_object(raw_tile, f"$.tile_table[{expected_id}]")
        tile_id = _require_integer(
            tile["tile_id"],
            f"$.tile_table[{expected_id}].tile_id",
            nonnegative=True,
        )
        if tile_id != expected_id:
            _fail(
                f"$.tile_table[{expected_id}].tile_id",
                f"must equal its canonical table position {expected_id}",
            )
        edges = _require_object(
            tile["edges"], f"$.tile_table[{expected_id}].edges"
        )
        tiles.append(
            tuple(
                _require_integer(
                    edges[direction],
                    f"$.tile_table[{expected_id}].edges.{direction}",
                    nonnegative=True,
                )
                for direction in _DIRECTIONS
            )
        )

    for index, tile_id in enumerate(cells):
        sides = boundary[index]
        if tile_id is None:
            if sides is not None:
                _fail(
                    f"$.boundary[{index}]",
                    "must be null because the corresponding cell is a hole",
                )
            continue
        assert type(tile_id) is int
        if tile_id >= len(tiles):
            _fail(
                f"$.cells[{index}]",
                f"references absent tile_id {tile_id}",
            )
        if sides is None:
            _fail(
                f"$.boundary[{index}]",
                "must contain N/E/S/W entries for an active cell",
            )
        assert type(sides) is dict

        x = index % width
        y = index // width
        tile = tiles[tile_id]
        for direction_index, (direction, (dx, dy)) in enumerate(
            zip(_DIRECTIONS, _OFFSETS, strict=True)
        ):
            required_color = sides[direction]
            neighbor_x = x + dx
            neighbor_y = y + dy
            neighbor_is_active = False
            if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                neighbor_index = neighbor_y * width + neighbor_x
                neighbor_is_active = cells[neighbor_index] is not None

            if neighbor_is_active and required_color is not None:
                _fail(
                    f"$.boundary[{index}].{direction}",
                    "must be null on an edge shared by active cells",
                )
            if required_color is not None and required_color != tile[direction_index]:
                _fail(
                    f"$.boundary[{index}].{direction}",
                    "does not match the selected tile edge color",
                )

    for y in range(height):
        for x in range(width):
            index = y * width + x
            tile_id = cells[index]
            if tile_id is None:
                continue
            assert type(tile_id) is int
            tile = tiles[tile_id]
            for direction_index in (1, 2):
                dx, dy = _OFFSETS[direction_index]
                neighbor_x = x + dx
                neighbor_y = y + dy
                if neighbor_x >= width or neighbor_y >= height:
                    continue
                neighbor_index = neighbor_y * width + neighbor_x
                neighbor_id = cells[neighbor_index]
                if neighbor_id is None:
                    continue
                assert type(neighbor_id) is int
                if tile[direction_index] != tiles[neighbor_id][
                    _OPPOSITE[direction_index]
                ]:
                    direction = _DIRECTIONS[direction_index]
                    _fail(
                        f"$.cells[{index}]/{direction}/$.cells[{neighbor_index}]",
                        "adjacent tile edge colors do not match",
                    )


def _reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WangSolutionValidationError(
                f"JSON object contains duplicate member {key!r}"
            )
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise WangSolutionValidationError(
        f"JSON document contains non-finite number {value}"
    )


def load_wang_solution(path: str | Path) -> dict[str, object]:
    """Load strict JSON from *path*, validate it, and return the document."""
    try:
        with Path(path).open(encoding="utf-8") as stream:
            document = json.load(
                stream,
                object_pairs_hook=_reject_duplicate_members,
                parse_constant=_reject_nonfinite_constant,
            )
    except json.JSONDecodeError as error:
        raise WangSolutionValidationError(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}"
        ) from error

    validate_wang_solution(document)
    assert type(document) is dict
    return document
