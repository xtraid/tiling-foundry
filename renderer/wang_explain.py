"""Shared drawing primitives for opt-in explainability views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

import numpy as np
from PIL import Image, ImageDraw, ImageFont


EXPLAIN_FACE_RGB: Final = (244, 246, 249)
EXPLAIN_PANEL_RGB: Final = (255, 255, 255)
EXPLAIN_TEXT_RGB: Final = (24, 28, 36)
EXPLAIN_MUTED_RGB: Final = (88, 96, 112)
EXPLAIN_OUTLINE_RGB: Final = (28, 32, 40)
EXPLAIN_INACTIVE_LIGHT_RGB: Final = (226, 230, 236)
EXPLAIN_INACTIVE_DARK_RGB: Final = (190, 197, 207)
EXPLAIN_ACTIVE_RGB: Final = (238, 241, 246)


def explain_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return Pillow's bundled deterministic font at an explicit size."""
    return ImageFont.load_default(size=max(8, size))


def contrasting_text(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Choose black or white text from integer relative luminance."""
    red, green, blue = rgb
    luminance = 299 * red + 587 * green + 114 * blue
    return (20, 22, 28) if luminance >= 145_000 else (250, 250, 250)


def centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int] = EXPLAIN_TEXT_RGB,
) -> None:
    """Draw text centered in an inclusive integer box."""
    left, top, right, bottom = box
    text_box = draw.textbbox((0, 0), text, font=font)
    width = text_box[2] - text_box[0]
    height = text_box[3] - text_box[1]
    x = left + (right - left + 1 - width) // 2 - text_box[0]
    y = top + (bottom - top + 1 - height) // 2 - text_box[1]
    draw.text((x, y), text, font=font, fill=fill)


def draw_explain_heading(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    *,
    title: str,
    subtitle: str,
) -> None:
    """Draw the common two-line heading used by explainability views."""
    x, y = origin
    draw.text((x, y), title, font=explain_font(20), fill=EXPLAIN_TEXT_RGB)
    draw.text(
        (x, y + 28),
        subtitle,
        font=explain_font(12),
        fill=EXPLAIN_MUTED_RGB,
    )


def draw_inactive_key(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
) -> None:
    """Draw the shared legend key for an inactive bounding-box position."""
    x, y = origin
    size = 20
    draw.rectangle(
        (x, y, x + size, y + size),
        fill=EXPLAIN_INACTIVE_LIGHT_RGB,
        outline=EXPLAIN_INACTIVE_DARK_RGB,
    )
    draw.line(
        (x + 2, y + 2, x + size - 2, y + size - 2),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.line(
        (x + size - 2, y + 2, x + 2, y + size - 2),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (x + size + 8, y + 1),
        "inactive / outside region",
        font=explain_font(12),
        fill=EXPLAIN_TEXT_RGB,
    )


def square_explain_tile(
    edges: tuple[int, int, int, int],
    palette: Mapping[int, tuple[int, int, int]],
    size: int,
    *,
    tile_id: int | None,
    edge_labels: bool,
) -> Image.Image:
    """Draw a neutral square face surrounded by four logical-color bands."""
    last = size - 1
    band = max(3, size // 9)
    inner = band
    asset = Image.new("RGB", (size, size), EXPLAIN_FACE_RGB)
    draw = ImageDraw.Draw(asset)
    polygons = (
        ((0, 0), (last, 0), (last - inner, inner), (inner, inner)),
        ((last, 0), (last, last), (last - inner, last - inner), (last - inner, inner)),
        ((last, last), (0, last), (inner, last - inner), (last - inner, last - inner)),
        ((0, last), (0, 0), (inner, inner), (inner, last - inner)),
    )
    for direction, color in enumerate(edges):
        draw.polygon(polygons[direction], fill=palette[color])
    draw.rectangle(
        (inner, inner, last - inner, last - inner),
        outline=EXPLAIN_OUTLINE_RGB,
        width=1,
    )

    if tile_id is not None:
        centered_text(
            draw,
            (inner + 1, inner + 1, last - inner - 1, last - inner - 1),
            str(tile_id),
            font=explain_font(max(9, size // 4)),
        )
    if edge_labels and size >= 56:
        font = explain_font(max(8, size // 9))
        labels = (
            (str(edges[0]), (size // 2, band // 2)),
            (str(edges[1]), (last - band // 2, size // 2)),
            (str(edges[2]), (size // 2, last - band // 2)),
            (str(edges[3]), (band // 2, size // 2)),
        )
        for direction, (label, center) in enumerate(labels):
            text_box = draw.textbbox((0, 0), label, font=font)
            width = text_box[2] - text_box[0]
            height = text_box[3] - text_box[1]
            draw.text(
                (
                    center[0] - width // 2 - text_box[0],
                    center[1] - height // 2 - text_box[1],
                ),
                label,
                font=font,
                fill=contrasting_text(palette[edges[direction]]),
            )
    return asset


def square_inactive_tile(size: int) -> Image.Image:
    """Draw an explicitly inactive bounding-box position."""
    coordinates = np.arange(size, dtype=np.int32)
    x = np.broadcast_to(coordinates, (size, size))
    y = x.T
    checker_size = max(2, size // 6)
    checker = ((x // checker_size) + (y // checker_size)) % 2
    colors = np.asarray(
        (EXPLAIN_INACTIVE_LIGHT_RGB, EXPLAIN_INACTIVE_DARK_RGB),
        dtype=np.uint8,
    )
    asset = Image.fromarray(colors[checker], mode="RGB")
    draw = ImageDraw.Draw(asset)
    draw.rectangle((0, 0, size - 1, size - 1), outline=EXPLAIN_OUTLINE_RGB)
    draw.line((2, 2, size - 3, size - 3), fill=EXPLAIN_OUTLINE_RGB, width=1)
    draw.line((size - 3, 2, 2, size - 3), fill=EXPLAIN_OUTLINE_RGB, width=1)
    return asset


def square_region_tile(
    size: int,
    boundary: tuple[int | None, int | None, int | None, int | None],
    palette: Mapping[int, tuple[int, int, int]],
) -> Image.Image:
    """Draw one unassigned active cell and its exposed boundary constraints."""
    asset = Image.new("RGB", (size, size), EXPLAIN_ACTIVE_RGB)
    draw = ImageDraw.Draw(asset)
    draw.rectangle((0, 0, size - 1, size - 1), outline=(174, 181, 193))
    band = max(3, size // 8)
    sides = (
        (0, 0, size - 1, band - 1),
        (size - band, 0, size - 1, size - 1),
        (0, size - band, size - 1, size - 1),
        (0, 0, band - 1, size - 1),
    )
    for direction, color in enumerate(boundary):
        if color is None:
            continue
        draw.rectangle(sides[direction], fill=palette[color])
        if direction == 0:
            line = (0, 0, size - 1, 0)
        elif direction == 1:
            line = (size - 1, 0, size - 1, size - 1)
        elif direction == 2:
            line = (0, size - 1, size - 1, size - 1)
        else:
            line = (0, 0, 0, size - 1)
        draw.line(line, fill=EXPLAIN_OUTLINE_RGB, width=1)
    return asset


def hex_explain_tile(
    edges: tuple[int, int, int, int, int, int],
    palette: Mapping[int, tuple[int, int, int]],
    radius: int,
    vertices: tuple[tuple[int, int], ...],
    *,
    tile_id: int | None,
    edge_labels: bool,
) -> Image.Image:
    """Draw a pointy-top hex with explicit six-side logical-color bands."""
    size = 2 * radius + 1
    asset = Image.new("RGB", (size, size), EXPLAIN_FACE_RGB)
    draw = ImageDraw.Draw(asset)
    draw.polygon(vertices, fill=EXPLAIN_FACE_RGB)
    width = max(3, radius // 5)
    for direction, color in enumerate(edges):
        first = vertices[(direction + 1) % 6]
        second = vertices[(direction + 2) % 6]
        draw.line((first, second), fill=EXPLAIN_OUTLINE_RGB, width=width + 2)
        draw.line((first, second), fill=palette[color], width=width)
    if tile_id is not None:
        centered_text(
            draw,
            (radius // 2, radius // 2, radius + radius // 2, radius + radius // 2),
            str(tile_id),
            font=explain_font(max(9, radius // 2)),
        )
    if edge_labels and radius >= 28:
        font = explain_font(max(8, radius // 4))
        center = (radius, radius)
        for direction, color in enumerate(edges):
            first = vertices[(direction + 1) % 6]
            second = vertices[(direction + 2) % 6]
            midpoint = ((first[0] + second[0]) // 2, (first[1] + second[1]) // 2)
            label_center = (
                (2 * midpoint[0] + center[0]) // 3,
                (2 * midpoint[1] + center[1]) // 3,
            )
            label = str(color)
            text_box = draw.textbbox((0, 0), label, font=font)
            draw.text(
                (
                    label_center[0] - (text_box[2] - text_box[0]) // 2,
                    label_center[1] - (text_box[3] - text_box[1]) // 2,
                ),
                label,
                font=font,
                fill=EXPLAIN_TEXT_RGB,
            )
    return asset


def draw_boundary_side(
    draw: ImageDraw.ImageDraw,
    first: tuple[int, int],
    second: tuple[int, int],
    color: tuple[int, int, int],
    *,
    width: int,
) -> None:
    """Highlight one exposed constraint with a black-backed colored stroke."""
    draw.line((first, second), fill=EXPLAIN_OUTLINE_RGB, width=width + 4)
    draw.line((first, second), fill=color, width=width)


def draw_palette_legend(
    draw: ImageDraw.ImageDraw,
    palette: Mapping[int, tuple[int, int, int]],
    origin: tuple[int, int],
    *,
    title: str = "Logical edge colors",
    columns: int = 2,
    font_size: int = 14,
) -> tuple[int, int]:
    """Draw a numeric palette legend and return its occupied width/height."""
    font = explain_font(font_size)
    title_font = explain_font(font_size + 2)
    swatch = font_size + 2
    row_height = swatch + 6
    column_width = 82
    colors = sorted(palette)
    rows = (len(colors) + columns - 1) // columns
    x0, y0 = origin
    draw.text((x0, y0), title, font=title_font, fill=EXPLAIN_TEXT_RGB)
    title_box = draw.textbbox((x0, y0), title, font=title_font)
    content_y = title_box[3] + 8
    for index, logical_color in enumerate(colors):
        column = index // rows
        row = index % rows
        x = x0 + column * column_width
        y = content_y + row * row_height
        rgb = palette[logical_color]
        draw.rectangle(
            (x, y, x + swatch, y + swatch),
            fill=rgb,
            outline=EXPLAIN_OUTLINE_RGB,
        )
        draw.text(
            (x + swatch + 6, y),
            str(logical_color),
            font=font,
            fill=EXPLAIN_TEXT_RGB,
        )
    height = content_y - y0 + rows * row_height
    return columns * column_width, height


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Wrap words using measured Pillow widths without locale dependence."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    origin: tuple[int, int],
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int] = EXPLAIN_TEXT_RGB,
    spacing: int = 5,
) -> int:
    """Draw lines and return the first unused y coordinate."""
    x, y = origin
    sample = draw.textbbox((0, 0), "Ag", font=font)
    line_height = sample[3] - sample[1] + spacing
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y
