"""Presentation-only renderer for ``wang-solution-v1`` square tilings.

This module deliberately does not verify Wang adjacency or boundary semantics.
It accepts the structural fields needed for presentation, projects away
``metadata``, and renders the selected tile edge colors.  The default square
path is unchanged; explicit hex mode applies and checks the pure Basire/Culik
port before rasterization.  Successful rendering is not a correctness claim.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Final

import numpy as np
from PIL import Image, ImageDraw

from wang_explain import (
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_boundary_side,
    draw_explain_heading,
    draw_inactive_key,
    draw_palette_legend,
    explain_font,
    hex_explain_tile,
    square_explain_tile,
    square_inactive_tile,
)
from wang_hex_port import (
    SQUARE_DIRECTIONS,
    WangHexPort,
    WangPresentation,
    WangSquareRenderError,
    check_square_to_hex,
    reduce_square_to_hex,
)


SCHEMA_NAME: Final = "wang-solution-v1"
GEOMETRY: Final = "square"
STATUS: Final = "SAT"
DIRECTIONS: Final = SQUARE_DIRECTIONS

DEFAULT_PIXELS_PER_CELL: Final = 32
DEFAULT_MARGIN: Final = 8
MIN_PIXELS_PER_CELL: Final = 8
MAX_PIXELS_PER_CELL: Final = 512
MAX_MARGIN: Final = 4096
MAX_CANVAS_SIDE: Final = 16384
MAX_CANVAS_PIXELS: Final = 64 * 1024 * 1024
EXPLAIN_HEADER_HEIGHT: Final = 54
EXPLAIN_LEGEND_WIDTH: Final = 190
EXPLAIN_PANEL_GAP: Final = 20

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


def _validate_optional_edges(
    value: object, path: str
) -> tuple[int | None, int | None, int | None, int | None] | None:
    if value is None:
        return None
    edges = _require_object(value, path)
    _require_exact_fields(edges, frozenset(DIRECTIONS), path)
    projected: list[int | None] = []
    for direction in DIRECTIONS:
        color = edges[direction]
        if color is not None:
            color = _require_integer(
                color, f"{path}.{direction}", nonnegative=True
            )
        projected.append(color)
    return tuple(projected)


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

    # Boundary data is checked only for v1 transport shape. It is retained for
    # the pure hex port, but is not compared with cells/edges or used by the
    # square raster.
    boundary = _require_array(root["boundary"], "$.boundary")
    if len(boundary) != area:
        _fail("$.boundary", f"length must equal inclusive bounds area {area}")
    projected_boundary = tuple(
        _validate_optional_edges(sides, f"$.boundary[{index}]")
        for index, sides in enumerate(boundary)
    )

    _require_object(root["metadata"], "$.metadata")
    return WangPresentation(
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        tile_edges=tuple(tile_edges),
        cells=tuple(cells),
        boundary=projected_boundary,
    )


def load_wang_presentation(path: str | Path) -> WangPresentation:
    """Load strict JSON and project metadata away from presentation data."""
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


def _build_palette_from_edges(
    tile_edges: tuple[tuple[int, ...], ...],
) -> dict[int, tuple[int, int, int]]:
    logical_colors = sorted(
        {color for edges in tile_edges for color in edges}
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


def build_palette(
    presentation: WangPresentation,
) -> dict[int, tuple[int, int, int]]:
    """Assign a deterministic, injective RGB color to each logical color."""
    if not isinstance(presentation, WangPresentation):
        raise TypeError("presentation must be a WangPresentation")
    return _build_palette_from_edges(presentation.tile_edges)


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
    _check_canvas_limits(width, height)
    return width, height, ppc, checked_margin


def _check_canvas_limits(width: int, height: int) -> None:
    if width > MAX_CANVAS_SIDE or height > MAX_CANVAS_SIDE:
        raise WangSquareRenderError(
            f"canvas side exceeds limit {MAX_CANVAS_SIDE}: {width}x{height}"
        )
    if width * height > MAX_CANVAS_PIXELS:
        raise WangSquareRenderError(
            f"canvas area exceeds limit {MAX_CANVAS_PIXELS}: {width}x{height}"
        )


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


def _hex_canvas_dimensions(
    presentation: WangHexPort,
    pixels_per_cell: object,
    margin: object,
) -> tuple[int, int, int, int, int]:
    radius = _render_integer(
        pixels_per_cell,
        "pixels_per_cell",
        minimum=MIN_PIXELS_PER_CELL,
        maximum=MAX_PIXELS_PER_CELL,
    )
    checked_margin = _render_integer(
        margin, "margin", minimum=0, maximum=MAX_MARGIN
    )
    shoulder = radius // 2
    width = (
        2 * radius * (presentation.width - 1)
        + radius * (presentation.height - 1)
        + 2 * radius
        + 1
        + 2 * checked_margin
    )
    height = (
        (radius + shoulder) * (presentation.height - 1)
        + 2 * radius
        + 1
        + 2 * checked_margin
    )
    _check_canvas_limits(width, height)
    return width, height, radius, shoulder, checked_margin


def _hex_vertices(radius: int, shoulder: int) -> tuple[tuple[int, int], ...]:
    centre = radius
    far = 2 * radius
    return (
        (centre, 0),
        (far, centre - shoulder),
        (far, centre + shoulder),
        (centre, far),
        (0, centre + shoulder),
        (0, centre - shoulder),
    )


def _hex_mask(radius: int, vertices: tuple[tuple[int, int], ...]) -> Image.Image:
    size = 2 * radius + 1
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(vertices, fill=255)
    return mask


def _hex_tile_asset(
    edges: tuple[int, int, int, int, int, int],
    palette: dict[int, tuple[int, int, int]],
    radius: int,
    vertices: tuple[tuple[int, int], ...],
) -> Image.Image:
    size = 2 * radius + 1
    asset = Image.new("RGB", (size, size), BACKGROUND_RGB)
    draw = ImageDraw.Draw(asset)
    centre = (radius, radius)
    for direction, color in enumerate(edges):
        first_vertex = vertices[(direction + 1) % 6]
        second_vertex = vertices[(direction + 2) % 6]
        draw.polygon(
            (centre, first_vertex, second_vertex),
            fill=palette[color],
        )
    draw.line((*vertices, vertices[0]), fill=GRID_RGB, width=1)
    return asset


def _hex_hole_asset(
    radius: int,
    vertices: tuple[tuple[int, int], ...],
) -> Image.Image:
    size = 2 * radius + 1
    coordinates = np.arange(size, dtype=np.int32)
    x = np.broadcast_to(coordinates, (size, size))
    y = x.T
    checker_size = max(2, radius // 4)
    checker = ((x // checker_size) + (y // checker_size)) % 2
    colors = np.asarray((HOLE_LIGHT_RGB, HOLE_DARK_RGB), dtype=np.uint8)
    asset = Image.fromarray(colors[checker], mode="RGB")
    ImageDraw.Draw(asset).line(
        (*vertices, vertices[0]), fill=GRID_RGB, width=1
    )
    return asset


def _compose_wang_hex(
    square: WangPresentation,
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Port, check, and compose one pointy-top axial hex canvas."""
    presentation = reduce_square_to_hex(square)
    check_square_to_hex(square, presentation)
    width, height, radius, shoulder, checked_margin = _hex_canvas_dimensions(
        presentation, pixels_per_cell, margin
    )
    canvas = Image.new("RGB", (width, height), BACKGROUND_RGB)
    vertices = _hex_vertices(radius, shoulder)
    mask = _hex_mask(radius, vertices)
    hole = _hex_hole_asset(radius, vertices)
    palette = _build_palette_from_edges(presentation.tile_edges)
    tile_assets: dict[int, Image.Image] = {}

    min_center_x = (
        2 * radius * presentation.min_q + radius * presentation.min_r
    )
    min_center_y = (radius + shoulder) * presentation.min_r
    for index, tile_id in enumerate(presentation.cells):
        local_q = index % presentation.width
        local_r = index // presentation.width
        q = presentation.min_q + local_q
        r = presentation.min_r + local_r
        center_x = 2 * radius * q + radius * r
        center_y = (radius + shoulder) * r
        x = checked_margin + center_x - min_center_x
        y = checked_margin + center_y - min_center_y
        if tile_id is None:
            asset = hole
        else:
            asset = tile_assets.get(tile_id)
            if asset is None:
                asset = _hex_tile_asset(
                    presentation.tile_edges[tile_id],
                    palette,
                    radius,
                    vertices,
                )
                tile_assets[tile_id] = asset
        canvas.paste(asset, (x, y), mask)
    return np.asarray(canvas, dtype=np.uint8)


def _palette_with_boundary(
    tile_edges: tuple[tuple[int, ...], ...],
    boundary: tuple[tuple[int | None, ...] | None, ...],
) -> dict[int, tuple[int, int, int]]:
    colors = {
        color
        for sides in boundary
        if sides is not None
        for color in sides
        if color is not None
    }
    if colors:
        return _build_palette_from_edges((*tile_edges, tuple(sorted(colors))))
    return _build_palette_from_edges(tile_edges)


def _compose_wang_square_explain(
    presentation: WangPresentation,
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Compose an opt-in square view with explicit colored side bands."""
    ppc = _render_integer(
        pixels_per_cell,
        "pixels_per_cell",
        minimum=MIN_PIXELS_PER_CELL,
        maximum=MAX_PIXELS_PER_CELL,
    )
    checked_margin = _render_integer(
        margin,
        "margin",
        minimum=0,
        maximum=MAX_MARGIN,
    )
    grid_width = presentation.width * ppc
    grid_height = presentation.height * ppc
    canvas_width = (
        2 * checked_margin
        + grid_width
        + EXPLAIN_PANEL_GAP
        + EXPLAIN_LEGEND_WIDTH
    )
    canvas_height = max(
        2 * checked_margin + EXPLAIN_HEADER_HEIGHT + grid_height,
        2 * checked_margin + EXPLAIN_HEADER_HEIGHT + 300,
    )
    _check_canvas_limits(canvas_width, canvas_height)

    canvas = Image.new(
        "RGB",
        (canvas_width, canvas_height),
        EXPLAIN_PANEL_RGB,
    )
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Verified Wang solution - square",
        subtitle="colored N/E/S/W bands; tile ID at each active cell",
    )
    grid_x = checked_margin
    grid_y = checked_margin + EXPLAIN_HEADER_HEIGHT
    palette = _palette_with_boundary(
        presentation.tile_edges,
        presentation.boundary,
    )
    inactive = square_inactive_tile(ppc)
    tile_assets: dict[int, Image.Image] = {}
    overlays: list[
        tuple[
            tuple[int, int],
            tuple[int, int],
            tuple[int, int, int],
        ]
    ] = []

    for index, tile_id in enumerate(presentation.cells):
        local_x = index % presentation.width
        local_y = index // presentation.width
        x = grid_x + local_x * ppc
        y = grid_y + local_y * ppc
        if tile_id is None:
            canvas.paste(inactive, (x, y))
            continue
        asset = tile_assets.get(tile_id)
        if asset is None:
            asset = square_explain_tile(
                presentation.tile_edges[tile_id],
                palette,
                ppc,
                tile_id=tile_id,
                edge_labels=False,
            )
            tile_assets[tile_id] = asset
        canvas.paste(asset, (x, y))
        sides = presentation.boundary[index]
        if sides is None:
            continue
        segments = (
            ((x, y), (x + ppc - 1, y)),
            ((x + ppc - 1, y), (x + ppc - 1, y + ppc - 1)),
            ((x, y + ppc - 1), (x + ppc - 1, y + ppc - 1)),
            ((x, y), (x, y + ppc - 1)),
        )
        for direction, color in enumerate(sides):
            if color is not None:
                overlays.append((*segments[direction], palette[color]))

    draw = ImageDraw.Draw(canvas)
    for first, second, rgb in overlays:
        draw_boundary_side(
            draw,
            first,
            second,
            rgb,
            width=max(2, ppc // 12),
        )
    legend_x = grid_x + grid_width + EXPLAIN_PANEL_GAP
    _, legend_height = draw_palette_legend(
        draw,
        palette,
        (legend_x, grid_y),
        columns=2,
    )
    draw_inactive_key(draw, (legend_x, grid_y + legend_height + 12))
    return np.asarray(canvas, dtype=np.uint8)


def _compose_wang_hex_explain(
    square: WangPresentation,
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Compose an opt-in checked hex view with explicit six-side bands."""
    presentation = reduce_square_to_hex(square)
    check_square_to_hex(square, presentation)
    raw_width, raw_height, radius, shoulder, _ = _hex_canvas_dimensions(
        presentation,
        pixels_per_cell,
        0,
    )
    checked_margin = _render_integer(
        margin,
        "margin",
        minimum=0,
        maximum=MAX_MARGIN,
    )
    canvas_width = (
        2 * checked_margin
        + raw_width
        + EXPLAIN_PANEL_GAP
        + EXPLAIN_LEGEND_WIDTH
    )
    canvas_height = max(
        2 * checked_margin + EXPLAIN_HEADER_HEIGHT + raw_height,
        2 * checked_margin + EXPLAIN_HEADER_HEIGHT + 350,
    )
    _check_canvas_limits(canvas_width, canvas_height)
    canvas = Image.new(
        "RGB",
        (canvas_width, canvas_height),
        EXPLAIN_PANEL_RGB,
    )
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Verified Wang solution - Basire/Culik hex view",
        subtitle="E/SE/SW/W/NW/NE bands; kappa marks the presentation-only axis",
    )
    grid_x = checked_margin
    grid_y = checked_margin + EXPLAIN_HEADER_HEIGHT
    vertices = _hex_vertices(radius, shoulder)
    mask = _hex_mask(radius, vertices)
    inactive = _hex_hole_asset(radius, vertices)
    palette = _palette_with_boundary(
        presentation.tile_edges,
        presentation.boundary,
    )
    tile_assets: dict[int, Image.Image] = {}
    overlays: list[
        tuple[
            tuple[int, int],
            tuple[int, int],
            tuple[int, int, int],
        ]
    ] = []
    min_anchor_x = (
        2 * radius * presentation.min_q + radius * presentation.min_r
    )
    min_anchor_y = (radius + shoulder) * presentation.min_r
    for index, tile_id in enumerate(presentation.cells):
        local_q = index % presentation.width
        local_r = index // presentation.width
        q = presentation.min_q + local_q
        r = presentation.min_r + local_r
        anchor_x = 2 * radius * q + radius * r
        anchor_y = (radius + shoulder) * r
        x = grid_x + anchor_x - min_anchor_x
        y = grid_y + anchor_y - min_anchor_y
        if tile_id is None:
            asset = inactive
        else:
            asset = tile_assets.get(tile_id)
            if asset is None:
                asset = hex_explain_tile(
                    presentation.tile_edges[tile_id],
                    palette,
                    radius,
                    vertices,
                    tile_id=tile_id,
                    edge_labels=False,
                )
                tile_assets[tile_id] = asset
        canvas.paste(asset, (x, y), mask)
        if tile_id is None:
            continue
        sides = presentation.boundary[index]
        if sides is None:
            continue
        for direction, color in enumerate(sides):
            if color is None:
                continue
            first = vertices[(direction + 1) % 6]
            second = vertices[(direction + 2) % 6]
            overlays.append(
                (
                    (x + first[0], y + first[1]),
                    (x + second[0], y + second[1]),
                    palette[color],
                )
            )

    draw = ImageDraw.Draw(canvas)
    for first, second, rgb in overlays:
        draw_boundary_side(
            draw,
            first,
            second,
            rgb,
            width=max(2, radius // 8),
        )
    legend_x = grid_x + raw_width + EXPLAIN_PANEL_GAP
    _, legend_height = draw_palette_legend(
        draw,
        palette,
        (legend_x, grid_y),
        columns=2,
    )
    draw.text(
        (legend_x, grid_y + legend_height + 8),
        f"kappa = {presentation.fresh_color}",
        font=explain_font(13),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw_inactive_key(
        draw,
        (legend_x, grid_y + legend_height + 38),
    )
    return np.asarray(canvas, dtype=np.uint8)


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
    hex_mode: bool = False,
    explain: bool = False,
) -> None:
    """Load a v1 presentation and atomically write square or hex pixels."""
    presentation = load_wang_presentation(input_path)
    if hex_mode and explain:
        canvas = _compose_wang_hex_explain(
            presentation,
            pixels_per_cell=pixels_per_cell,
            margin=margin,
        )
    elif hex_mode:
        canvas = _compose_wang_hex(
            presentation,
            pixels_per_cell=pixels_per_cell,
            margin=margin,
        )
    elif explain:
        canvas = _compose_wang_square_explain(
            presentation,
            pixels_per_cell=pixels_per_cell,
            margin=margin,
        )
    else:
        canvas = compose_wang_square(
            presentation,
            pixels_per_cell=pixels_per_cell,
            margin=margin,
        )
    _save_png_atomic(canvas, output_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render a Wang solution or a static explainability snapshot as PNG"
        )
    )
    parser.add_argument(
        "input",
        help=(
            "path to wang-solution-v1 JSON or a wang-explain-manifest-v1/v2 file"
        ),
    )
    parser.add_argument("output", help="path to the output PNG")
    parser.add_argument(
        "--pixels-per-cell",
        type=int,
        default=DEFAULT_PIXELS_PER_CELL,
        help=(
            "square cell size or hex radius in pixels "
            f"(default: {DEFAULT_PIXELS_PER_CELL})"
        ),
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=DEFAULT_MARGIN,
        help=f"canvas margin in pixels (default: {DEFAULT_MARGIN})",
    )
    parser.add_argument(
        "--hex",
        action="store_true",
        help="port the square witness to pointy-top axial hexagons",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="add colored edge bands, tile IDs, boundary emphasis, and a legend",
    )
    parser.add_argument(
        "--view",
        choices=(
            "solution",
            "formula",
            "tileset",
            "region",
            "reduction",
            "generalized-sheet",
            "atomic-legend",
            "generalized-overlay",
        ),
        default="solution",
        help="input stage to render (default: solution)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.view == "solution":
            render_wang_square(
                args.input,
                args.output,
                pixels_per_cell=args.pixels_per_cell,
                margin=args.margin,
                hex_mode=args.hex,
                explain=args.explain,
            )
        else:
            if args.explain:
                raise WangSquareRenderError(
                    "snapshot views are already explainable; omit --explain"
                )
            if args.view in {
                "generalized-sheet",
                "atomic-legend",
                "generalized-overlay",
            }:
                from wang_generalized_render import render_generalized_view

                render_generalized_view(
                    args.input,
                    args.output,
                    view=args.view,
                    pixels_per_cell=args.pixels_per_cell,
                    margin=args.margin,
                    hex_mode=args.hex,
                )
            else:
                from wang_snapshot import render_pipeline_snapshot

                render_pipeline_snapshot(
                    args.input,
                    args.output,
                    view=args.view,
                    pixels_per_cell=args.pixels_per_cell,
                    margin=args.margin,
                    hex_mode=args.hex,
                )
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
