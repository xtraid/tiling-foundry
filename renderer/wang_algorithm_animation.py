"""Canonical/didactic animations for non-trace pipeline algorithms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from wang_animation import AnimationOutputs, write_animation_assets
from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_INACTIVE_DARK_RGB,
    EXPLAIN_INACTIVE_LIGHT_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_RENDER_SCALE,
    EXPLAIN_TEXT_RGB,
    centered_text,
    draw_explain_heading,
    explain_font,
    square_inactive_tile,
    square_region_tile,
)
from wang_hex_port import WangSquareRenderError, check_square_to_hex, reduce_square_to_hex
from wang_snapshot import ReductionExplanationSnapshot, load_explainability_bundle
from wang_square import _build_palette_from_edges, load_wang_presentation


_GADGET_COLORS = {
    "variable": (75, 137, 201),
    "left_forward": (89, 170, 122),
    "crossover": (234, 168, 61),
    "right_forward": (169, 112, 191),
    "clause": (214, 91, 91),
}
_OPTIMIZATION_SOURCE = Path(__file__).resolve().parent / "data/optimized-mechanisms-v1.json"


def _load_optimizations() -> tuple[tuple[str, str], ...]:
    try:
        document = json.loads(_OPTIMIZATION_SOURCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WangSquareRenderError(
            f"cannot load optimized mechanism source: {error}"
        ) from error
    if type(document) is not dict or set(document) != {"schema", "mechanisms"}:
        raise WangSquareRenderError("optimized mechanism source must be closed")
    if document["schema"] != "wang-optimized-mechanisms-v1":
        raise WangSquareRenderError("optimized mechanism source schema is unsupported")
    mechanisms = document["mechanisms"]
    if type(mechanisms) is not list or len(mechanisms) != 6:
        raise WangSquareRenderError("optimized mechanism source must contain six entries")
    result: list[tuple[str, str]] = []
    identifiers: list[str] = []
    for index, item in enumerate(mechanisms):
        if type(item) is not dict or set(item) != {
            "id",
            "title",
            "description",
            "evidence_route",
        }:
            raise WangSquareRenderError(
                f"optimized mechanism entry {index} must be closed"
            )
        values = tuple(item.values())
        if any(type(value) is not str or not value for value in values):
            raise WangSquareRenderError(
                f"optimized mechanism entry {index} requires nonempty strings"
            )
        if not item["evidence_route"].startswith("/"):
            raise WangSquareRenderError(
                f"optimized mechanism entry {index} has an invalid evidence route"
            )
        identifiers.append(item["id"])
        result.append((item["title"], item["description"]))
    if len(set(identifiers)) != len(identifiers) or identifiers[-1] != "lazy-mrv-index":
        raise WangSquareRenderError("optimized mechanism IDs are invalid or incomplete")
    return tuple(result)


_OPTIMIZATIONS = _load_optimizations()


def _base_frame(title: str, subtitle: str, size: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", size, EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(draw, (18, 16), title=title, subtitle=subtitle)
    return image, draw


def _builder_signal_label(signal: object, *, compact: bool) -> str:
    if signal.kind == "redundant":
        return f"r #{signal.token_id}"
    if compact:
        return f"#{signal.token_id}"
    return f"x{signal.variable}.{signal.occurrence}"


def _replay_signal_orders(
    reduction: ReductionExplanationSnapshot,
) -> tuple[tuple[object, ...], ...]:
    """Project the loader-validated adjacent swaps for presentation."""
    current = list(reduction.source_signals)
    orders = [tuple(current)]
    for crossover in (
        gadget for gadget in reduction.gadgets if gadget.kind == "crossover"
    ):
        assert crossover.swap_row is not None
        row = crossover.swap_row
        current[row], current[row + 1] = current[row + 1], current[row]
        orders.append(tuple(current))
    return tuple(orders)


def _draw_signal_order(
    draw: ImageDraw.ImageDraw,
    *,
    y: int,
    label: str,
    signals: tuple[object, ...],
    highlighted_rows: tuple[int, ...] = (),
    muted: bool = False,
) -> None:
    scale = EXPLAIN_RENDER_SCALE
    draw.text(
        (36, y + 12),
        label,
        font=explain_font(22 * scale),
        fill=EXPLAIN_MUTED_RGB if muted else EXPLAIN_TEXT_RGB,
    )
    gap = 10
    box_width = min(
        140,
        (1720 - max(0, len(signals) - 1) * gap) // len(signals),
    )
    for row, signal in enumerate(signals):
        x = 220 + row * (box_width + gap)
        highlighted = row in highlighted_rows
        draw.rounded_rectangle(
            (x, y, x + box_width, y + 58),
            radius=8,
            fill=(255, 232, 188) if highlighted else (239, 242, 246),
            outline=(217, 119, 6) if highlighted else (181, 188, 199),
            width=4 if highlighted else 2,
        )
        centered_text(
            draw,
            (x + 4, y + 3, x + box_width - 4, y + 55),
            _builder_signal_label(signal, compact=box_width < 120),
            font=explain_font(28 * scale),
            fill=EXPLAIN_MUTED_RGB if muted else EXPLAIN_TEXT_RGB,
        )


def _builder_frame(bundle: object, stage: int) -> Image.Image:
    reduction = bundle.reduction
    assert reduction is not None
    crossovers = tuple(
        gadget for gadget in reduction.gadgets if gadget.kind == "crossover"
    )
    if crossovers:
        first_swap = crossovers[0]
        assert first_swap.swap_row is not None
        first_swap_title = (
            f"crossover X{first_swap.ordinal} swaps adjacent rows "
            f"{first_swap.swap_row} and {first_swap.swap_row + 1}"
        )
        routing_title = (
            f"{len(crossovers)} validated adjacent swaps reach the target order"
        )
    else:
        first_swap_title = "source order already matches the target order"
        routing_title = "routing requires no crossover swaps"
    stage_titles = (
        "source signals leave the variable gadgets",
        "target signals follow clause order",
        first_swap_title,
        routing_title,
        "native gadget spans assemble the final Region",
        "active, inactive, internal-edge, and exposed-boundary states",
    )
    image, draw = _base_frame(
        "Yang-Zhang routing and Region construction",
        f"canonical-construction {stage + 1}/6 | {stage_titles[stage]}",
        (1976, 828),
    )
    # _base_frame uses the legacy 1x heading; redraw the shared heading at 2x.
    draw.rectangle((0, 0, image.width, 126), fill=EXPLAIN_PANEL_RGB)
    draw_explain_heading(
        draw,
        (36, 28),
        title="Yang-Zhang routing and Region construction",
        subtitle=f"canonical-construction {stage + 1}/6 | {stage_titles[stage]}",
        scale=EXPLAIN_RENDER_SCALE,
    )

    replay_orders = _replay_signal_orders(reduction)
    first_swap_row = crossovers[0].swap_row if crossovers else None
    _draw_signal_order(
        draw,
        y=140,
        label="source",
        signals=reduction.source_signals,
        highlighted_rows=(
            (first_swap_row, first_swap_row + 1)
            if stage == 2 and first_swap_row is not None
            else ()
        ),
    )
    if stage == 0:
        _draw_signal_order(
            draw,
            y=216,
            label="target",
            signals=reduction.target_signals,
            muted=True,
        )
    elif stage == 2:
        _draw_signal_order(
            draw,
            y=216,
            label=f"after X{crossovers[0].ordinal}" if crossovers else "target",
            signals=replay_orders[1] if crossovers else reduction.target_signals,
            highlighted_rows=(
                (first_swap_row, first_swap_row + 1)
                if first_swap_row is not None
                else ()
            ),
        )
    else:
        _draw_signal_order(
            draw,
            y=216,
            label="target",
            signals=reduction.target_signals,
        )

    origin_x, origin_y = 36, 348
    cell = max(1, min(
        30,
        1230 // bundle.region.width,
        330 // bundle.region.height,
    ))
    grid_width = bundle.region.width * cell
    grid_height = bundle.region.height * cell
    palette = _build_palette_from_edges(bundle.tileset.tile_edges)
    for index, active in enumerate(bundle.region.active):
        x = origin_x + (index % bundle.region.width) * cell
        y = origin_y + (index // bundle.region.width) * cell
        if stage >= 4:
            if active:
                sides = bundle.region.boundary[index]
                assert sides is not None
                tile = square_region_tile(cell, sides, palette)
            else:
                tile = square_inactive_tile(cell)
            image.paste(tile, (x, y))
        else:
            fill = EXPLAIN_ACTIVE_RGB if active else EXPLAIN_INACTIVE_LIGHT_RGB
            draw.rectangle(
                (x, y, x + cell - 1, y + cell - 1),
                fill=fill,
                outline=(174, 181, 193),
            )

    for gadget in reduction.gadgets:
        visible = (
            (stage == 0 and gadget.kind == "variable")
            or (stage == 1 and gadget.kind in {"variable", "left_forward"})
            or (
                stage == 2
                and (
                    gadget.kind in {"variable", "left_forward"}
                    or (crossovers and gadget is crossovers[0])
                )
            )
            or (stage == 3 and gadget.kind == "crossover")
            or stage == 4
        )
        if not visible:
            continue
        x0 = origin_x + gadget.x_begin * cell
        y0 = origin_y + gadget.y_begin * cell
        x1 = origin_x + gadget.x_end * cell - 1
        y1 = origin_y + gadget.y_end * cell - 1
        width = 7 if stage == 2 and crossovers and gadget is crossovers[0] else 4
        draw.rectangle(
            (x0, y0, x1, y1),
            outline=_GADGET_COLORS[gadget.kind],
            width=width,
        )
        if gadget.kind == "crossover" and stage in {2, 3}:
            crossover_label = (
                f"X{gadget.ordinal}: swap rows "
                f"{gadget.swap_row}/{gadget.swap_row + 1}"
                if stage == 2
                else f"X{gadget.ordinal}:s{gadget.swap_row}"
            )
            draw.text(
                (x0 + 8, y0 + 5),
                crossover_label,
                font=explain_font(14 * EXPLAIN_RENDER_SCALE),
                fill=_GADGET_COLORS["crossover"],
                stroke_width=3,
                stroke_fill=EXPLAIN_PANEL_RGB,
            )

    legend_x = origin_x + grid_width + 24
    if stage == 5:
        draw.text(
            (legend_x, origin_y),
            "Final Region vocabulary",
            font=explain_font(20 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
        )
        key_y = origin_y + 68
        draw.rectangle(
            (legend_x, key_y, legend_x + 36, key_y + 36),
            fill=EXPLAIN_ACTIVE_RGB,
            outline=(174, 181, 193),
        )
        draw.text(
            (legend_x + 54, key_y - 3),
            "active cell",
            font=explain_font(22 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
        )
        key_y += 64
        image.paste(
            square_inactive_tile(36),
            (legend_x, key_y),
        )
        draw.text(
            (legend_x + 54, key_y - 3),
            "inactive / outside",
            font=explain_font(22 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
        )
        key_y += 64
        draw.line(
            (legend_x, key_y + 18, legend_x + 36, key_y + 18),
            fill=(174, 181, 193),
            width=7,
        )
        draw.text(
            (legend_x + 54, key_y - 3),
            "internal edge (no boundary)",
            font=explain_font(22 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
        )
        key_y += 64
        draw.line(
            (legend_x, key_y + 18, legend_x + 36, key_y + 18),
            fill=palette[0],
            width=11,
        )
        draw.text(
            (legend_x + 54, key_y - 3),
            "exposed boundary color",
            font=explain_font(22 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
        )
        draw.text(
            (legend_x, key_y + 70),
            f"{sum(bundle.region.active)} active / "
            f"{bundle.region.active.count(False)} inactive\n"
            "internal sides stay uncolored",
            font=explain_font(16 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_MUTED_RGB,
            spacing=10,
        )
    else:
        draw.text(
            (legend_x, origin_y),
            "Construction evidence",
            font=explain_font(18 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
        )
        y = origin_y + 52
        for kind, color in _GADGET_COLORS.items():
            draw.rectangle((legend_x, y, legend_x + 28, y + 28), fill=color)
            count = sum(gadget.kind == kind for gadget in reduction.gadgets)
            draw.text(
                (legend_x + 42, y),
                f"{kind.replace('_', ' ')}: {count}",
                font=explain_font(14 * EXPLAIN_RENDER_SCALE),
                fill=EXPLAIN_TEXT_RGB,
            )
            y += 42
        draw.text(
            (legend_x, y + 8),
            f"source signals: {len(reduction.source_signals)}\nadjacent swaps: "
            + ", ".join(str(gadget.swap_row) for gadget in crossovers),
            font=explain_font(14 * EXPLAIN_RENDER_SCALE),
            fill=EXPLAIN_TEXT_RGB,
            spacing=12,
        )
    draw.text(
        (36, 794),
        "Spans and swaps are canonical construction provenance; boundary colors are constraints, not tile assignments.",
        font=explain_font(13 * EXPLAIN_RENDER_SCALE),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_builder_assets(
    manifest_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 750,
) -> AnimationOutputs:
    bundle = load_explainability_bundle(manifest_path)
    if bundle.reduction is None:
        raise WangSquareRenderError("builder animation requires reduction provenance")
    frames = tuple(_builder_frame(bundle, stage) for stage in range(6))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(6)),
        output_directory,
        fallback_index=5,
        duration_ms=duration_ms,
    )


def _optimized_frame(stage: int) -> Image.Image:
    image, draw = _base_frame(
        "Optimized serial mechanisms",
        f"didactic stage {stage + 1}/7 | storage/work changes only; search semantics stay shared",
        (960, 500),
    )
    draw.text(
        (18, 82),
        "Reference baseline",
        font=explain_font(14),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.rounded_rectangle(
        (18, 106, 245, 462),
        radius=7,
        fill=(239, 241, 245),
        outline=(170, 177, 190),
    )
    baseline = (
        "direct set-tile support loop",
        "duplicate-accepting FIFO",
        "initial trail entries",
        "full DFS frame reserve",
        "verified SAT result copy",
        "linear MRV scan after the root",
    )
    y = 130
    for line in baseline:
        draw.text((34, y), line, font=explain_font(10), fill=EXPLAIN_MUTED_RGB)
        y += 48

    draw.text((276, 82), "Retained optimized path", font=explain_font(14), fill=EXPLAIN_TEXT_RGB)
    for index, (name, description) in enumerate(_OPTIMIZATIONS):
        y = 106 + index * 57
        active = index < stage
        current = index == stage - 1
        draw.rounded_rectangle(
            (276, y, 928, y + 45),
            radius=6,
            fill=(213, 237, 224) if active else (240, 242, 246),
            outline=(52, 145, 94) if current else (181, 188, 199),
            width=2 if current else 1,
        )
        draw.text(
            (290, y + 6),
            name,
            font=explain_font(11),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
        )
        draw.text(
            (472, y + 8),
            description,
            font=explain_font(9),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
        )
    draw.text(
        (276, 468),
        "Measured reports establish benefit separately; this animation claims no speedup.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_optimized_assets(
    output_directory: str | Path,
    *,
    duration_ms: int = 750,
) -> AnimationOutputs:
    frames = tuple(_optimized_frame(stage) for stage in range(7))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(7)),
        output_directory,
        fallback_index=6,
        duration_ms=duration_ms,
    )


def _draw_square_tile(draw: ImageDraw.ImageDraw, origin: tuple[int, int], edges: tuple[int, ...]) -> None:
    x, y = origin
    draw.rectangle((x, y, x + 122, y + 122), fill=EXPLAIN_ACTIVE_RGB, outline=(35, 39, 47), width=3)
    positions = ((x + 51, y + 6), (x + 105, y + 55), (x + 51, y + 104), (x + 7, y + 55))
    for label, position in zip((f"N={edges[0]}", f"E={edges[1]}", f"S={edges[2]}", f"W={edges[3]}"), positions, strict=True):
        draw.text(position, label, font=explain_font(10), fill=EXPLAIN_TEXT_RGB)


def _draw_hex_tile(draw: ImageDraw.ImageDraw, origin: tuple[int, int], edges: tuple[int, ...]) -> None:
    x, y = origin
    vertices = ((x + 62, y), (x + 122, y + 34), (x + 122, y + 94), (x + 62, y + 128), (x + 2, y + 94), (x + 2, y + 34))
    draw.polygon(vertices, fill=EXPLAIN_ACTIVE_RGB, outline=(35, 39, 47))
    labels = (
        (f"E={edges[0]}", (x + 98, y + 58)),
        (f"SE={edges[1]}", (x + 78, y + 102)),
        (f"SW={edges[2]}", (x + 20, y + 102)),
        (f"W={edges[3]}", (x + 7, y + 58)),
        (f"NW={edges[4]}", (x + 18, y + 18)),
        (f"NE={edges[5]}", (x + 77, y + 18)),
    )
    for label, position in labels:
        draw.text(position, label, font=explain_font(9), fill=EXPLAIN_TEXT_RGB)


def _hex_frame(square: object, port: object, stage: int) -> Image.Image:
    image, draw = _base_frame(
        "Square-to-hex presentation port",
        f"verified-transformation stage {stage + 1}/4 | pure Basire/Culik witness mapping",
        (920, 430),
    )
    source_edges = square.tile_edges[0]
    target_edges = port.tile_edges[0]
    _draw_square_tile(draw, (45, 122), source_edges)
    if stage >= 1:
        draw.line((190, 184, 366, 184), fill=(55, 126, 168), width=4)
        draw.polygon(((366, 184), (350, 174), (350, 194)), fill=(55, 126, 168))
        draw.text(
            (210, 140),
            "H(N,E,S,W) =\n(E,S,kappa,W,N,kappa)",
            font=explain_font(12),
            fill=EXPLAIN_TEXT_RGB,
            spacing=5,
        )
    if stage >= 2:
        _draw_hex_tile(draw, (402, 119), target_edges)
    draw.rounded_rectangle((580, 102, 892, 374), radius=7, fill=(239, 242, 246), outline=(181, 188, 199))
    lines = [
        f"square tiles: {len(square.tile_edges)}",
        f"hex tiles: {len(port.tile_edges)}",
        f"fresh kappa: {port.fresh_color}",
        f"cells preserved: {len(square.cells)}",
        f"holes preserved: {square.cells.count(None)}",
    ]
    if stage == 3:
        lines.extend(("inverse projection: checked", "six-side matching: checked"))
    y = 126
    for line in lines:
        draw.text((600, y), line, font=explain_font(11), fill=EXPLAIN_TEXT_RGB)
        y += 31
    draw.text(
        (18, 400),
        "The port preserves a verified square witness; raster output is not a correctness oracle.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_hex_assets(
    solution_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 850,
) -> AnimationOutputs:
    square = load_wang_presentation(solution_path)
    port = reduce_square_to_hex(square)
    check_square_to_hex(square, port)
    frames = tuple(_hex_frame(square, port, stage) for stage in range(4))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(4)),
        output_directory,
        fallback_index=2,
        duration_ms=duration_ms,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="render canonical algorithm animations")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    builder = subparsers.add_parser("builder")
    builder.add_argument("manifest", type=Path)
    builder.add_argument("output_directory", type=Path)
    optimized = subparsers.add_parser("optimized")
    optimized.add_argument("output_directory", type=Path)
    hex_parser = subparsers.add_parser("hex")
    hex_parser.add_argument("solution", type=Path)
    hex_parser.add_argument("output_directory", type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        if args.mode == "builder":
            outputs = render_builder_assets(args.manifest, args.output_directory)
        elif args.mode == "optimized":
            outputs = render_optimized_assets(args.output_directory)
        else:
            outputs = render_hex_assets(args.solution, args.output_directory)
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))
    print(f"animation={outputs.animation}")
    print(f"fallback={outputs.fallback}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
