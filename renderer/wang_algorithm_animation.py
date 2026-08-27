"""Canonical/didactic animations for non-trace pipeline algorithms."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from wang_animation import AnimationOutputs, write_animation_assets
from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_explain_heading,
    explain_font,
)
from wang_hex_port import WangSquareRenderError, check_square_to_hex, reduce_square_to_hex
from wang_snapshot import load_explainability_bundle
from wang_square import load_wang_presentation


_GADGET_COLORS = {
    "variable": (75, 137, 201),
    "left_forward": (89, 170, 122),
    "crossover": (234, 168, 61),
    "right_forward": (169, 112, 191),
    "clause": (214, 91, 91),
}
_OPTIMIZATIONS = (
    ("Dynamic DFS stack", "grow from 16 frames instead of reserving all active cells"),
    ("Initial trail omission", "do not store undo entries that search cannot consume"),
    ("SAT ownership transfer", "publish the verified domain buffer without a result copy"),
    ("Byte support table", "aggregate compatible tiles through three byte lookups"),
    ("Queue deduplication", "suppress an enqueue while the cell is already pending"),
)


def _base_frame(title: str, subtitle: str, size: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", size, EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(draw, (18, 16), title=title, subtitle=subtitle)
    return image, draw


def _builder_frame(bundle: object, stage: int) -> Image.Image:
    reduction = bundle.reduction
    assert reduction is not None
    image, draw = _base_frame(
        "Yang-Zhang construction provenance",
        f"canonical-example stage {stage + 1}/6 | actual gadget spans, not a timed builder trace",
        (980, 390),
    )
    origin_x, origin_y, cell = 18, 92, 15
    grid_width = bundle.region.width * cell
    grid_height = bundle.region.height * cell
    for index, active in enumerate(bundle.region.active):
        x = origin_x + (index % bundle.region.width) * cell
        y = origin_y + (index // bundle.region.width) * cell
        fill = (232, 235, 240) if active else (198, 204, 214)
        draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=fill, outline=(187, 193, 203))

    visible_kinds = (
        (),
        ("variable",),
        ("variable", "left_forward"),
        ("variable", "left_forward", "crossover"),
        ("variable", "left_forward", "crossover", "right_forward"),
        tuple(_GADGET_COLORS),
    )[stage]
    for gadget in reduction.gadgets:
        if gadget.kind not in visible_kinds:
            continue
        x0 = origin_x + gadget.x_begin * cell
        y0 = origin_y + gadget.y_begin * cell
        x1 = origin_x + gadget.x_end * cell - 1
        y1 = origin_y + gadget.y_end * cell - 1
        draw.rectangle((x0, y0, x1, y1), outline=_GADGET_COLORS[gadget.kind], width=3)

    legend_x = origin_x + grid_width + 24
    draw.text((legend_x, 92), "Native sidecar spans", font=explain_font(14), fill=EXPLAIN_TEXT_RGB)
    y = 126
    for kind, color in _GADGET_COLORS.items():
        draw.rectangle((legend_x, y, legend_x + 18, y + 18), fill=color)
        count = sum(gadget.kind == kind for gadget in reduction.gadgets)
        draw.text(
            (legend_x + 27, y + 2),
            f"{kind.replace('_', ' ')}: {count}",
            font=explain_font(10),
            fill=EXPLAIN_TEXT_RGB if kind in visible_kinds else EXPLAIN_MUTED_RGB,
        )
        y += 29
    draw.text(
        (legend_x, y + 10),
        f"signals: {len(reduction.source_signals)}\nswaps: "
        f"{sum(g.kind == 'crossover' for g in reduction.gadgets)}",
        font=explain_font(10),
        fill=EXPLAIN_TEXT_RGB,
        spacing=7,
    )
    draw.text(
        (18, 368),
        "The provenance describes construction; Region remains presentation-neutral.",
        font=explain_font(9),
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
        fallback_index=4,
        duration_ms=duration_ms,
    )


def _optimized_frame(stage: int) -> Image.Image:
    image, draw = _base_frame(
        "Optimized serial mechanisms",
        f"didactic stage {stage + 1}/6 | storage/work changes only; search semantics stay shared",
        (960, 430),
    )
    draw.text(
        (18, 82),
        "Reference baseline",
        font=explain_font(14),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.rounded_rectangle(
        (18, 106, 245, 392),
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
    )
    y = 130
    for line in baseline:
        draw.text((34, y), line, font=explain_font(10), fill=EXPLAIN_MUTED_RGB)
        y += 46

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
        (276, 400),
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
    frames = tuple(_optimized_frame(stage) for stage in range(6))
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(6)),
        output_directory,
        fallback_index=5,
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
        f"canonical-example stage {stage + 1}/4 | pure Basire/Culik witness mapping",
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
