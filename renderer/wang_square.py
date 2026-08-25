"""Presentation-only renderer for ``wang-solution-v1`` square tilings.

This module deliberately does not verify Wang adjacency or boundary semantics.
It accepts the structural fields needed for presentation, projects away
``boundary`` and ``metadata``, and renders the selected tile edge colors.
Successful rendering is not a correctness claim.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Final

import numpy as np
from PIL import Image


SCHEMA_NAME: Final = "wang-solution-v1"
GEOMETRY: Final = "square"
STATUS: Final = "SAT"
DIRECTIONS: Final = ("N", "E", "S", "W")

DEFAULT_PIXELS_PER_CELL: Final = 32
DEFAULT_MARGIN: Final = 8
MIN_PIXELS_PER_CELL: Final = 8
MAX_PIXELS_PER_CELL: Final = 512
MAX_MARGIN: Final = 4096
MAX_CANVAS_SIDE: Final = 16384
MAX_CANVAS_PIXELS: Final = 64 * 1024 * 1024

BACKGROUND_RGB: Final = (248, 248, 244)
GRID_RGB: Final = (32, 35, 42)
HOLE_LIGHT_RGB: Final = (214, 218, 224)
HOLE_DARK_RGB: Final = (166, 173, 184)
_RESERVED_RGB: Final = frozenset(
    {BACKGROUND_RGB, GRID_RGB, HOLE_LIGHT_RGB, HOLE_DARK_RGB}
)
_RGB_SPACE_SIZE: Final = 1 << 24
_PALETTE_OFFSET: Final = 0x51ED27
_PALETTE_STEP: Final = 0x9E3779  # Odd, hence invertible modulo 2**24.

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


class WangSquareRenderError(ValueError):
    """Raised when an input cannot be presented as a v1 square image."""


@dataclass(frozen=True, slots=True)
class WangPresentation:
    """Immutable projection of only the fields that determine the pixels."""

    min_x: int
    min_y: int
    max_x: int
    max_y: int
    tile_edges: tuple[tuple[int, int, int, int], ...]
    cells: tuple[int | None, ...]

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1


def _fail(path: str, message: str) -> None:
    raise WangSquareRenderError(f"{path}: {message}")


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
    value: dict[str, object], expected: frozenset[str], path: str
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(extra)}")


def _reject_duplicate_members(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WangSquareRenderError(
                f"JSON object contains duplicate member {key!r}"
            )
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise WangSquareRenderError(
        f"JSON document contains non-finite number {value}"
    )


def _validate_optional_edges(value: object, path: str) -> None:
    if value is None:
        return
    edges = _require_object(value, path)
    _require_exact_fields(edges, frozenset(DIRECTIONS), path)
    for direction in DIRECTIONS:
        color = edges[direction]
        if color is not None:
            _require_integer(
                color,
                f"{path}.{direction}",
                nonnegative=True,
            )


def _project_wang_presentation(document: object) -> WangPresentation:
    root = _require_object(document, "$")
    _require_exact_fields(root, _TOP_LEVEL_FIELDS, "$")

    for field, expected in (
        ("schema", SCHEMA_NAME),
        ("status", STATUS),
        ("geometry", GEOMETRY),
    ):
        if type(root[field]) is not str or root[field] != expected:
            _fail(f"$.{field}", f"must equal {expected!r}")

    bounds = _require_object(root["bounds"], "$.bounds")
    _require_exact_fields(bounds, _BOUND_FIELDS, "$.bounds")
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

    raw_table = _require_array(root["tile_table"], "$.tile_table")
    if not raw_table:
        _fail("$.tile_table", "must not be empty")
    tile_edges: list[tuple[int, int, int, int]] = []
    for expected_id, raw_tile in enumerate(raw_table):
        tile_path = f"$.tile_table[{expected_id}]"
        tile = _require_object(raw_tile, tile_path)
        _require_exact_fields(tile, frozenset({"tile_id", "edges"}), tile_path)
        tile_id = _require_integer(
            tile["tile_id"], f"{tile_path}.tile_id", nonnegative=True
        )
        if tile_id != expected_id:
            _fail(
                f"{tile_path}.tile_id",
                f"must equal its canonical table position {expected_id}",
            )
        raw_edges = _require_object(tile["edges"], f"{tile_path}.edges")
        _require_exact_fields(
            raw_edges, frozenset(DIRECTIONS), f"{tile_path}.edges"
        )
        tile_edges.append(
            tuple(
                _require_integer(
                    raw_edges[direction],
                    f"{tile_path}.edges.{direction}",
                    nonnegative=True,
                )
                for direction in DIRECTIONS
            )
        )

    width = max_x - min_x + 1
    height = max_y - min_y + 1
    area = width * height
    raw_cells = _require_array(root["cells"], "$.cells")
    if len(raw_cells) != area:
        _fail("$.cells", f"length must equal inclusive bounds area {area}")
    cells: list[int | None] = []
    for index, value in enumerate(raw_cells):
        if value is None:
            cells.append(None)
            continue
        tile_id = _require_integer(
            value, f"$.cells[{index}]", nonnegative=True
        )
        if tile_id >= len(tile_edges):
            _fail(f"$.cells[{index}]", f"references absent tile_id {tile_id}")
        cells.append(tile_id)

    # Boundary data is checked only for v1 transport shape. It is not compared
    # with cells or edges, and it never reaches the presentation projection.
    boundary = _require_array(root["boundary"], "$.boundary")
    if len(boundary) != area:
        _fail("$.boundary", f"length must equal inclusive bounds area {area}")
    for index, sides in enumerate(boundary):
        _validate_optional_edges(sides, f"$.boundary[{index}]")

    _require_object(root["metadata"], "$.metadata")
    return WangPresentation(
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        tile_edges=tuple(tile_edges),
        cells=tuple(cells),
    )


def load_wang_presentation(path: str | Path) -> WangPresentation:
    """Load strict JSON and return only the fields that determine pixels."""
    source = Path(path)
    try:
        with source.open(encoding="utf-8") as stream:
            document = json.load(
                stream,
                object_pairs_hook=_reject_duplicate_members,
                parse_constant=_reject_nonfinite_constant,
            )
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Wang solution file not found: {source!s}") from error
    except UnicodeDecodeError as error:
        raise WangSquareRenderError(
            f"Wang solution is not valid UTF-8: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise WangSquareRenderError(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}"
        ) from error
    except WangSquareRenderError:
        raise
    except (ValueError, RecursionError) as error:
        raise WangSquareRenderError(
            f"invalid JSON value: {error}"
        ) from error
    except OSError as error:
        raise WangSquareRenderError(
            f"cannot read Wang solution {source!s}: {error}"
        ) from error
    return _project_wang_presentation(document)


def build_palette(
    presentation: WangPresentation,
) -> dict[int, tuple[int, int, int]]:
    """Assign a deterministic, injective RGB color to each logical color."""
    if not isinstance(presentation, WangPresentation):
        raise TypeError("presentation must be a WangPresentation")
    logical_colors = sorted(
        {color for edges in presentation.tile_edges for color in edges}
    )
    available = _RGB_SPACE_SIZE - len(_RESERVED_RGB)
    if len(logical_colors) > available:
        raise WangSquareRenderError(
            f"logical color count exceeds the {available} available RGB values"
        )

    palette: dict[int, tuple[int, int, int]] = {}
    candidate_index = 0
    for logical_color in logical_colors:
        while candidate_index < _RGB_SPACE_SIZE:
            packed = (
                _PALETTE_OFFSET + candidate_index * _PALETTE_STEP
            ) & 0xFFFFFF
            candidate_index += 1
            rgb = (packed >> 16, (packed >> 8) & 0xFF, packed & 0xFF)
            if rgb not in _RESERVED_RGB:
                palette[logical_color] = rgb
                break
        else:  # Defensive: the cardinality check above makes this unreachable.
            raise WangSquareRenderError("RGB palette space exhausted")
    return palette


def _render_integer(
    value: object,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int:
        raise WangSquareRenderError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise WangSquareRenderError(
            f"{name} must be in [{minimum}, {maximum}], got {value}"
        )
    return value


def _canvas_dimensions(
    presentation: WangPresentation,
    pixels_per_cell: object,
    margin: object,
) -> tuple[int, int, int, int]:
    ppc = _render_integer(
        pixels_per_cell,
        "pixels_per_cell",
        minimum=MIN_PIXELS_PER_CELL,
        maximum=MAX_PIXELS_PER_CELL,
    )
    checked_margin = _render_integer(
        margin, "margin", minimum=0, maximum=MAX_MARGIN
    )
    width = presentation.width * ppc + 2 * checked_margin
    height = presentation.height * ppc + 2 * checked_margin
    if width > MAX_CANVAS_SIDE or height > MAX_CANVAS_SIDE:
        raise WangSquareRenderError(
            f"canvas side exceeds limit {MAX_CANVAS_SIDE}: {width}x{height}"
        )
    if width * height > MAX_CANVAS_PIXELS:
        raise WangSquareRenderError(
            f"canvas area exceeds limit {MAX_CANVAS_PIXELS}: {width}x{height}"
        )
    return width, height, ppc, checked_margin


def _tile_asset(
    edges: tuple[int, int, int, int],
    palette: dict[int, tuple[int, int, int]],
    pixels_per_cell: int,
) -> np.ndarray:
    coordinates = np.arange(pixels_per_cell, dtype=np.int32)
    x = np.broadcast_to(coordinates, (pixels_per_cell, pixels_per_cell))
    y = x.T
    last = pixels_per_cell - 1
    distances = np.stack((y, last - x, last - y, x), axis=0)
    # np.argmin uses the first minimum, fixing diagonal/centre ties as N,E,S,W.
    direction = np.argmin(distances, axis=0)
    edge_rgb = np.asarray([palette[color] for color in edges], dtype=np.uint8)
    asset = edge_rgb[direction]
    asset[0, :, :] = GRID_RGB
    asset[-1, :, :] = GRID_RGB
    asset[:, 0, :] = GRID_RGB
    asset[:, -1, :] = GRID_RGB
    return asset


def _hole_asset(pixels_per_cell: int) -> np.ndarray:
    coordinates = np.arange(pixels_per_cell, dtype=np.int32)
    x = np.broadcast_to(coordinates, (pixels_per_cell, pixels_per_cell))
    y = x.T
    checker_size = max(2, pixels_per_cell // 4)
    checker = ((x // checker_size) + (y // checker_size)) % 2
    colors = np.asarray((HOLE_LIGHT_RGB, HOLE_DARK_RGB), dtype=np.uint8)
    asset = colors[checker]
    asset[0, :, :] = GRID_RGB
    asset[-1, :, :] = GRID_RGB
    asset[:, 0, :] = GRID_RGB
    asset[:, -1, :] = GRID_RGB
    return asset


def compose_wang_square(
    presentation: WangPresentation,
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Compose one deterministic RGB canvas without writing it."""
    if not isinstance(presentation, WangPresentation):
        raise TypeError("presentation must be a WangPresentation")
    width, height, ppc, checked_margin = _canvas_dimensions(
        presentation, pixels_per_cell, margin
    )
    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[:, :, :] = BACKGROUND_RGB
    palette = build_palette(presentation)
    tile_assets: dict[int, np.ndarray] = {}
    hole = _hole_asset(ppc)

    for index, tile_id in enumerate(presentation.cells):
        local_x = index % presentation.width
        local_y = index // presentation.width
        x = checked_margin + local_x * ppc
        y = checked_margin + local_y * ppc
        if tile_id is None:
            asset = hole
        else:
            asset = tile_assets.get(tile_id)
            if asset is None:
                asset = _tile_asset(
                    presentation.tile_edges[tile_id], palette, ppc
                )
                tile_assets[tile_id] = asset
        canvas[y : y + ppc, x : x + ppc] = asset
    return canvas


def _save_png_atomic(canvas: np.ndarray, output_path: str | Path) -> None:
    destination = Path(output_path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".png",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        Image.fromarray(canvas).save(
            temporary,
            format="PNG",
            optimize=False,
            compress_level=9,
        )
        os.replace(temporary, destination)
        temporary = None
    except (OSError, ValueError) as error:
        raise WangSquareRenderError(
            f"cannot save output PNG to {destination!s}: {error}"
        ) from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def render_wang_square(
    input_path: str | Path,
    output_path: str | Path,
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> None:
    """Load a v1 presentation, compose it, and atomically write one PNG."""
    presentation = load_wang_presentation(input_path)
    canvas = compose_wang_square(
        presentation,
        pixels_per_cell=pixels_per_cell,
        margin=margin,
    )
    _save_png_atomic(canvas, output_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a wang-solution-v1 square tiling as a diagnostic PNG"
    )
    parser.add_argument("input", help="path to a wang-solution-v1 JSON file")
    parser.add_argument("output", help="path to the output PNG")
    parser.add_argument(
        "--pixels-per-cell",
        type=int,
        default=DEFAULT_PIXELS_PER_CELL,
        help=(
            "square cell size in pixels "
            f"(default: {DEFAULT_PIXELS_PER_CELL})"
        ),
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=DEFAULT_MARGIN,
        help=f"canvas margin in pixels (default: {DEFAULT_MARGIN})",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        render_wang_square(
            args.input,
            args.output,
            pixels_per_cell=args.pixels_per_cell,
            margin=args.margin,
        )
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
