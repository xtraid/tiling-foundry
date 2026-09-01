"""Deterministic square-only rasters for generalized Wang presentation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Final

import numpy as np
from PIL import Image, ImageDraw

from wang_explain import (
    EXPLAIN_MUTED_RGB,
    EXPLAIN_OUTLINE_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_explain_heading,
    explain_font,
    square_explain_tile,
    square_inactive_tile,
)
from wang_generalized import (
    COLOR_NAMES,
    GENERALIZED_TILES,
    GeneralizedInstance,
    GeneralizedTile,
    GeneralizedTileError,
    atomic_semantic_label,
    check_canonical_atomic_tileset,
    color_label,
    generalized_tile,
    recognize_generalized_tiles,
)
from wang_hex_port import WangPresentation, WangSquareRenderError
from wang_square import (
    DEFAULT_MARGIN,
    DEFAULT_PIXELS_PER_CELL,
    MAX_MARGIN,
    MAX_PIXELS_PER_CELL,
    MIN_PIXELS_PER_CELL,
    _build_palette_from_edges,
    _check_canvas_limits,
    _render_integer,
    _save_png_atomic,
    load_wang_presentation,
)


_HEADER_HEIGHT: Final = 62
_PANEL_GAP: Final = 18
_INTERNAL_SEAM_RGB: Final = (184, 191, 202)
_GROUP_COLORS: Final[tuple[tuple[int, int, int], ...]] = (
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (99, 99, 99),
    (188, 189, 34),
    (23, 190, 207),
    (57, 106, 177),
    (218, 124, 48),
    (62, 150, 81),
    (204, 37, 41),
)
_GROUP_RGB: Final = {
    tile.name: _GROUP_COLORS[index]
    for index, tile in enumerate(GENERALIZED_TILES)
}


def _as_render_error(error: GeneralizedTileError) -> WangSquareRenderError:
    return WangSquareRenderError(f"generalized Wang presentation: {error}")


def _checked_dimensions(
    pixels_per_cell: int,
    margin: int,
) -> tuple[int, int]:
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
    return ppc, checked_margin


def _draw_group_outline(
    draw: ImageDraw.ImageDraw,
    tile: GeneralizedTile,
    origin: tuple[int, int],
    cell_size: int,
    *,
    color: tuple[int, int, int],
) -> None:
    x, y = origin
    width = max(2, cell_size // 16)
    draw.rectangle(
        (
            x,
            y,
            x + tile.width * cell_size - 1,
            y + tile.height * cell_size - 1,
        ),
        outline=color,
        width=width,
    )

    coordinates = {(part.dx, part.dy) for part in tile.parts}
    seam_width = max(3, cell_size // 14)
    for dx, dy in coordinates:
        if (dx + 1, dy) in coordinates:
            seam_x = x + (dx + 1) * cell_size
            draw.line(
                (
                    seam_x,
                    y + dy * cell_size + width,
                    seam_x,
                    y + (dy + 1) * cell_size - width - 1,
                ),
                fill=_INTERNAL_SEAM_RGB,
                width=seam_width,
            )
        if (dx, dy + 1) in coordinates:
            seam_y = y + (dy + 1) * cell_size
            draw.line(
                (
                    x + dx * cell_size + width,
                    seam_y,
                    x + (dx + 1) * cell_size - width - 1,
                    seam_y,
                ),
                fill=_INTERNAL_SEAM_RGB,
                width=seam_width,
            )


def _draw_color_vocabulary(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    palette: dict[int, tuple[int, int, int]],
) -> int:
    x, y = origin
    draw.text(
        (x, y),
        "Paper colors",
        font=explain_font(15),
        fill=EXPLAIN_TEXT_RGB,
    )
    y += 25
    font = explain_font(12)
    for color_id in range(7):
        draw.rectangle(
            (x, y + 2, x + 16, y + 16),
            fill=palette[color_id],
            outline=EXPLAIN_OUTLINE_RGB,
        )
        draw.text(
            (x + 24, y),
            color_label(color_id),
            font=font,
            fill=EXPLAIN_TEXT_RGB,
        )
        y += 22
    y += 9
    draw.text(
        (x, y),
        "Internal glues",
        font=explain_font(15),
        fill=EXPLAIN_TEXT_RGB,
    )
    y += 25
    for color_id in range(7, len(COLOR_NAMES)):
        draw.rectangle(
            (x, y + 2, x + 16, y + 16),
            fill=palette[color_id],
            outline=EXPLAIN_OUTLINE_RGB,
        )
        draw.text(
            (x + 24, y),
            color_label(color_id),
            font=font,
            fill=EXPLAIN_TEXT_RGB,
        )
        y += 22
    return y


def compose_generalized_sheet(
    tile_edges: tuple[tuple[int, int, int, int], ...],
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Compose the fixed 14-tile sheet from an exact canonical atomic table."""
    try:
        check_canonical_atomic_tileset(tile_edges)
    except GeneralizedTileError as error:
        raise _as_render_error(error) from error
    ppc, checked_margin = _checked_dimensions(pixels_per_cell, margin)
    cell_size = max(58, ppc * 2)
    columns = 4
    rows = (len(GENERALIZED_TILES) + columns - 1) // columns
    card_width = 2 * cell_size + 34
    card_height = 3 * cell_size + 66
    gap = 12
    grid_width = columns * card_width + (columns - 1) * gap
    grid_height = rows * card_height + (rows - 1) * gap
    vocabulary_width = 190
    width = 2 * checked_margin + grid_width + _PANEL_GAP + vocabulary_width
    height = 2 * checked_margin + _HEADER_HEIGHT + grid_height
    _check_canvas_limits(width, height)

    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Yang-Zhang generalized tile sheet - 14 from 23",
        subtitle=(
            "outer contour is semantic; muted seams are forced internal glues; "
            "center numbers are atomic IDs"
        ),
    )
    palette = _build_palette_from_edges(tile_edges)
    grid_y = checked_margin + _HEADER_HEIGHT
    for tile_index, tile in enumerate(GENERALIZED_TILES):
        column = tile_index % columns
        row = tile_index // columns
        card_x = checked_margin + column * (card_width + gap)
        card_y = grid_y + row * (card_height + gap)
        draw.rounded_rectangle(
            (
                card_x,
                card_y,
                card_x + card_width - 1,
                card_y + card_height - 1,
            ),
            radius=8,
            fill=(249, 250, 252),
            outline=(214, 219, 227),
        )
        draw.text(
            (card_x + 10, card_y + 8),
            tile.name,
            font=explain_font(17),
            fill=_GROUP_RGB[tile.name],
        )
        shape_x = card_x + (card_width - tile.width * cell_size) // 2
        shape_y = card_y + 34
        for part in tile.parts:
            asset = square_explain_tile(
                tile_edges[part.tile_id],
                palette,
                cell_size,
                tile_id=part.tile_id,
                edge_labels=True,
            )
            canvas.paste(
                asset,
                (shape_x + part.dx * cell_size, shape_y + part.dy * cell_size),
            )
        _draw_group_outline(
            draw,
            tile,
            (shape_x, shape_y),
            cell_size,
            color=_GROUP_RGB[tile.name],
        )
        ids = "|".join(str(part.tile_id) for part in tile.parts)
        draw.text(
            (card_x + 10, card_y + card_height - 24),
            f"atomic IDs {ids}",
            font=explain_font(11),
            fill=EXPLAIN_MUTED_RGB,
        )
    _draw_color_vocabulary(
        draw,
        (checked_margin + grid_width + _PANEL_GAP, grid_y),
        palette,
    )
    return np.asarray(canvas, dtype=np.uint8)


def compose_atomic_semantic_legend(
    tile_edges: tuple[tuple[int, int, int, int], ...],
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Compose all 23 atomic IDs with generalized part and symbolic edges."""
    try:
        check_canonical_atomic_tileset(tile_edges)
    except GeneralizedTileError as error:
        raise _as_render_error(error) from error
    ppc, checked_margin = _checked_dimensions(pixels_per_cell, margin)
    cell_size = max(58, ppc * 2)
    columns = 3
    rows = (len(tile_edges) + columns - 1) // columns
    card_width = 420
    card_height = cell_size + 24
    gap = 10
    width = 2 * checked_margin + columns * card_width + (columns - 1) * gap
    height = 2 * checked_margin + _HEADER_HEIGHT + rows * card_height
    _check_canvas_limits(width, height)

    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Atomic Wang legend - 23 positional IDs",
        subtitle=(
            "generalized role and symbolic color are primary; numeric IDs in "
            "brackets preserve the transport vocabulary"
        ),
    )
    palette = _build_palette_from_edges(tile_edges)
    grid_y = checked_margin + _HEADER_HEIGHT
    for tile_id, edges in enumerate(tile_edges):
        column = tile_id % columns
        row = tile_id // columns
        x = checked_margin + column * (card_width + gap)
        y = grid_y + row * card_height
        draw.rounded_rectangle(
            (x, y, x + card_width - 1, y + card_height - 8),
            radius=7,
            fill=(249, 250, 252),
            outline=(214, 219, 227),
        )
        asset = square_explain_tile(
            edges,
            palette,
            cell_size,
            tile_id=tile_id,
            edge_labels=False,
        )
        canvas.paste(asset, (x + 8, y + 8))
        text_x = x + cell_size + 20
        draw.text(
            (text_x, y + 9),
            f"{atomic_semantic_label(tile_id)}  -  atomic #{tile_id}",
            font=explain_font(14),
            fill=EXPLAIN_TEXT_RGB,
        )
        draw.text(
            (text_x, y + 33),
            f"N {color_label(edges[0])}    E {color_label(edges[1])}",
            font=explain_font(11),
            fill=EXPLAIN_TEXT_RGB,
        )
        draw.text(
            (text_x, y + 53),
            f"S {color_label(edges[2])}    W {color_label(edges[3])}",
            font=explain_font(11),
            fill=EXPLAIN_TEXT_RGB,
        )
    return np.asarray(canvas, dtype=np.uint8)


def _overlay_side_panel(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    instances: tuple[GeneralizedInstance, ...],
    active_count: int,
) -> None:
    x, y = origin
    counts = Counter(instance.kind for instance in instances)
    draw.text(
        (x, y),
        "Exact recognized partition",
        font=explain_font(15),
        fill=EXPLAIN_TEXT_RGB,
    )
    y += 27
    font = explain_font(11)
    for index, tile in enumerate(GENERALIZED_TILES):
        column = index // 7
        row = index % 7
        item_x = x + column * 126
        item_y = y + row * 25
        draw.rectangle(
            (item_x, item_y + 2, item_x + 16, item_y + 16),
            fill=_GROUP_RGB[tile.name],
            outline=EXPLAIN_OUTLINE_RGB,
        )
        draw.text(
            (item_x + 23, item_y),
            f"{tile.name}: {counts[tile.name]}",
            font=font,
            fill=EXPLAIN_TEXT_RGB,
        )
    y += 7 * 25 + 12
    draw.text(
        (x, y),
        f"{len(instances)} generalized occurrences",
        font=explain_font(12),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (x, y + 20),
        f"{active_count} atomic cells, no overlap",
        font=explain_font(12),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (x, y + 50),
        "V1 remains one cell per occurrence.",
        font=explain_font(11),
        fill=EXPLAIN_MUTED_RGB,
    )
    draw.text(
        (x, y + 68),
        "Adjacent V1 copies are never merged.",
        font=explain_font(11),
        fill=EXPLAIN_MUTED_RGB,
    )


def compose_generalized_overlay(
    presentation: WangPresentation,
    *,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
) -> np.ndarray:
    """Overlay the exact generalized partition on one square atomic witness."""
    if not isinstance(presentation, WangPresentation):
        raise TypeError("presentation must be a WangPresentation")
    try:
        instances = recognize_generalized_tiles(
            presentation.tile_edges,
            presentation.cells,
            min_x=presentation.min_x,
            min_y=presentation.min_y,
            max_x=presentation.max_x,
            max_y=presentation.max_y,
        )
    except GeneralizedTileError as error:
        raise _as_render_error(error) from error
    ppc, checked_margin = _checked_dimensions(pixels_per_cell, margin)
    grid_width = presentation.width * ppc
    grid_height = presentation.height * ppc
    side_width = 270
    width = 2 * checked_margin + grid_width + _PANEL_GAP + side_width
    height = max(
        2 * checked_margin + _HEADER_HEIGHT + grid_height,
        2 * checked_margin + _HEADER_HEIGHT + 300,
    )
    _check_canvas_limits(width, height)

    canvas = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(canvas)
    draw_explain_heading(
        draw,
        (checked_margin, checked_margin),
        title="Square solution presentation - generalized overlay",
        subtitle=(
            "upstream verification is a precondition; contours group exact "
            "atomic compositions and IDs remain visible"
        ),
    )
    grid_x = checked_margin
    grid_y = checked_margin + _HEADER_HEIGHT
    palette = _build_palette_from_edges(presentation.tile_edges)
    inactive = square_inactive_tile(ppc)
    assets: dict[int, Image.Image] = {}
    for index, tile_id in enumerate(presentation.cells):
        x = grid_x + (index % presentation.width) * ppc
        y = grid_y + (index // presentation.width) * ppc
        if tile_id is None:
            canvas.paste(inactive, (x, y))
            continue
        asset = assets.get(tile_id)
        if asset is None:
            asset = square_explain_tile(
                presentation.tile_edges[tile_id],
                palette,
                ppc,
                tile_id=tile_id,
                edge_labels=False,
            )
            assets[tile_id] = asset
        canvas.paste(asset, (x, y))

    draw = ImageDraw.Draw(canvas)
    for instance in instances:
        tile = generalized_tile(instance.kind)
        origin_x = grid_x + (instance.origin_x - presentation.min_x) * ppc
        origin_y = grid_y + (instance.origin_y - presentation.min_y) * ppc
        _draw_group_outline(
            draw,
            tile,
            (origin_x, origin_y),
            ppc,
            color=_GROUP_RGB[tile.name],
        )
    _overlay_side_panel(
        draw,
        (grid_x + grid_width + _PANEL_GAP, grid_y),
        instances,
        sum(tile_id is not None for tile_id in presentation.cells),
    )
    return np.asarray(canvas, dtype=np.uint8)


def render_generalized_view(
    input_path: str | Path,
    output_path: str | Path,
    *,
    view: str,
    pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    margin: int = DEFAULT_MARGIN,
    hex_mode: bool = False,
) -> None:
    """Render one explicit generalized square view and atomically install it."""
    if hex_mode:
        raise WangSquareRenderError(
            "--hex is not meaningful for generalized square grouping"
        )
    if view == "generalized-overlay":
        presentation = load_wang_presentation(input_path)
        canvas = compose_generalized_overlay(
            presentation,
            pixels_per_cell=pixels_per_cell,
            margin=margin,
        )
    elif view in {"generalized-sheet", "atomic-legend"}:
        from wang_snapshot import load_explainability_bundle

        bundle = load_explainability_bundle(input_path)
        if view == "generalized-sheet":
            canvas = compose_generalized_sheet(
                bundle.tileset.tile_edges,
                pixels_per_cell=pixels_per_cell,
                margin=margin,
            )
        else:
            canvas = compose_atomic_semantic_legend(
                bundle.tileset.tile_edges,
                pixels_per_cell=pixels_per_cell,
                margin=margin,
            )
    else:
        raise WangSquareRenderError(
            "generalized view must be generalized-sheet, atomic-legend, "
            "or generalized-overlay"
        )
    _save_png_atomic(canvas, output_path)
