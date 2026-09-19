"""Canonical/didactic animations for non-trace pipeline algorithms."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import textwrap

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
_OPTIMIZATION_IDS = (
    "dynamic-dfs-stack",
    "initial-trail-omission",
    "sat-ownership-transfer",
    "byte-support-table",
    "queue-deduplication",
    "lazy-mrv-index",
)


@dataclass(frozen=True, slots=True)
class _Optimization:
    identifier: str
    title: str
    description: str
    evidence_route: str


def _load_optimizations() -> tuple[_Optimization, ...]:
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
    result: list[_Optimization] = []
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
        result.append(
            _Optimization(
                identifier=item["id"],
                title=item["title"],
                description=item["description"],
                evidence_route=item["evidence_route"],
            )
        )
    if tuple(identifiers) != _OPTIMIZATION_IDS:
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


def _signal_strip_items(
    signals: tuple[object, ...],
    highlighted_rows: tuple[int, ...],
) -> tuple[tuple[int | None, object | None, int], ...]:
    """Keep bounded endpoint/swap context and account for every hidden row."""
    if len(signals) <= 15:
        return tuple((row, signal, 0) for row, signal in enumerate(signals))

    selected = {0, 1, 2, len(signals) - 3, len(signals) - 2, len(signals) - 1}
    for row in highlighted_rows:
        selected.update(
            candidate
            for candidate in (row - 1, row, row + 1)
            if 0 <= candidate < len(signals)
        )
    ordered = sorted(selected)
    items: list[tuple[int | None, object | None, int]] = []
    previous = -1
    for row in ordered:
        omitted = row - previous - 1
        if omitted:
            items.append((None, None, omitted))
        items.append((row, signals[row], 0))
        previous = row
    trailing = len(signals) - previous - 1
    if trailing:
        items.append((None, None, trailing))
    return tuple(items)


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
    items = _signal_strip_items(signals, highlighted_rows)
    gap = 10
    box_width = min(
        140,
        (1720 - max(0, len(items) - 1) * gap) // len(items),
    )
    for position, (row, signal, omitted) in enumerate(items):
        x = 220 + position * (box_width + gap)
        highlighted = row in highlighted_rows
        draw.rounded_rectangle(
            (x, y, x + box_width, y + 58),
            radius=8,
            fill=(255, 232, 188) if highlighted else (239, 242, 246),
            outline=(217, 119, 6) if highlighted else (181, 188, 199),
            width=4 if highlighted else 2,
        )
        text = (
            f"+{omitted} rows"
            if signal is None
            else _builder_signal_label(signal, compact=box_width < 120)
        )
        font_size = 16 if signal is None else 28
        font = explain_font(font_size * scale)
        if len(signals) > 15:
            inner_width = box_width - 8
            while font_size > 12:
                text_box = draw.textbbox((0, 0), text, font=font)
                if text_box[2] - text_box[0] <= inner_width:
                    break
                font_size -= 1
                font = explain_font(font_size * scale)
        centered_text(
            draw,
            (x + 4, y + 3, x + box_width - 4, y + 55),
            text,
            font=font,
            fill=(
                EXPLAIN_MUTED_RGB
                if muted or signal is None
                else EXPLAIN_TEXT_RGB
            ),
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

    crossover_labels_omitted = False
    if stage == 3:
        previous_right = origin_x
        for gadget in crossovers:
            label_box = draw.textbbox(
                (origin_x + gadget.x_begin * cell + 8,
                 origin_y + gadget.y_begin * cell + 5),
                f"X{gadget.ordinal}:s{gadget.swap_row}",
                font=explain_font(14 * EXPLAIN_RENDER_SCALE),
                stroke_width=3,
            )
            if label_box[0] < previous_right or label_box[2] > origin_x + grid_width:
                crossover_labels_omitted = True
                break
            previous_right = label_box[2]

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
        if gadget.kind == "crossover" and (
            stage == 2 or (stage == 3 and not crossover_labels_omitted)
        ):
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
        evidence_font = explain_font(14 * EXPLAIN_RENDER_SCALE)
        swap_list = "adjacent swaps: " + ", ".join(
            str(gadget.swap_row) for gadget in crossovers
        )
        if draw.textbbox((legend_x, 0), swap_list, font=evidence_font)[2] > image.width - 36:
            swap_list = f"adjacent swaps: {len(crossovers)} (row list omitted)"
        evidence = f"source signals: {len(reduction.source_signals)}\n{swap_list}"
        if crossover_labels_omitted:
            evidence += f"\n{len(crossovers)} crossover labels omitted (overview)"
        draw.text(
            (legend_x, y + 8),
            evidence,
            font=evidence_font,
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


def _byte_support_example() -> dict[str, object]:
    """Return one hand-sized aggregation derived from canonical tile edges."""
    source_tiles = (0, 10, 22)
    source_east_edges = (2, 3, 3)
    canonical_west_edges = (
        1, 1, 1, 1, 2, 3, 2, 2, 3, 2, 3, 2,
        10, 3, 11, 2, 2, 3, 2, 2, 3, 3, 3,
    )
    domain = sum(1 << tile for tile in source_tiles)
    chunks = tuple((domain >> (8 * byte)) & 0xFF for byte in range(3))
    supported_edges = frozenset(source_east_edges)
    supported_tiles = tuple(
        tile
        for tile, west in enumerate(canonical_west_edges)
        if west in supported_edges
    )
    return {
        "domain": domain,
        "chunks": chunks,
        "source_tiles": source_tiles,
        "source_east_edges": source_east_edges,
        "supported_tiles": supported_tiles,
    }


def _queue_dedup_steps() -> tuple[tuple[str, str, tuple[int, ...]], ...]:
    queue: list[int] = []
    pending: set[int] = set()
    steps: list[tuple[str, str, tuple[int, ...]]] = []
    for label, operation in (
        ("enqueue c7", "enqueue"),
        ("enqueue c7 again", "enqueue"),
        ("dequeue c7", "dequeue"),
        ("enqueue c7 later", "enqueue"),
    ):
        if operation == "dequeue":
            queue.pop(0)
            pending.remove(7)
            action = "clear pending"
        elif 7 in pending:
            action = "suppress"
        else:
            queue.append(7)
            pending.add(7)
            action = "append"
        steps.append((label, action, tuple(queue)))
    return tuple(steps)


def _mrv_bucket_steps() -> tuple[
    tuple[
        str,
        tuple[tuple[int, int], ...],
        tuple[tuple[int, tuple[int, ...]], ...],
        int,
    ],
    ...,
]:
    domains = {2: 4, 5: 2, 9: 3}

    def snapshot(label: str) -> tuple[
        str,
        tuple[tuple[int, int], ...],
        tuple[tuple[int, tuple[int, ...]], ...],
        int,
    ]:
        buckets: dict[int, list[int]] = {}
        for cell, size in domains.items():
            if 2 <= size <= 23:
                buckets.setdefault(size, []).append(cell)
        packed = tuple(
            (size, tuple(sorted(cells)))
            for size, cells in sorted(buckets.items())
        )
        selected = packed[0][1][0]
        return label, tuple(sorted(domains.items())), packed, selected

    steps = [snapshot("after lazy build")]
    domains[2] = 2
    steps.append(snapshot("restrict c2: 4 -> 2"))
    domains[2] = 4
    steps.append(snapshot("rollback c2: 2 -> 4"))
    return tuple(steps)


def _optimized_canvas(mechanism: _Optimization, index: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1920, 1040), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (48, 34),
        title=mechanism.title,
        subtitle=(
            f"didactic mechanism {index + 1}/6 | {mechanism.identifier} | "
            "same solver semantics"
        ),
        scale=EXPLAIN_RENDER_SCALE,
    )
    return image, draw


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    *,
    fill: tuple[int, int, int] = (239, 242, 246),
    outline: tuple[int, int, int] = (174, 181, 193),
) -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=3)
    draw.text(
        (box[0] + 28, box[1] + 22),
        title,
        font=explain_font(48),
        fill=EXPLAIN_TEXT_RGB,
    )


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    text: str,
    *,
    width: int,
    size: int = 28,
    fill: tuple[int, int, int] = EXPLAIN_TEXT_RGB,
    spacing: int = 10,
) -> None:
    lines = [
        wrapped
        for paragraph in text.splitlines()
        for wrapped in (textwrap.wrap(paragraph, width=width) or [""])
    ]
    draw.multiline_text(
        origin,
        "\n".join(lines),
        font=explain_font(size),
        fill=fill,
        spacing=spacing,
    )


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: tuple[int, int, int] = (55, 126, 168),
) -> None:
    draw.line((*start, *end), fill=fill, width=7)
    if abs(end[0] - start[0]) >= abs(end[1] - start[1]):
        direction = 1 if end[0] >= start[0] else -1
        head = (
            end,
            (end[0] - direction * 20, end[1] - 13),
            (end[0] - direction * 20, end[1] + 13),
        )
    else:
        direction = 1 if end[1] >= start[1] else -1
        head = (
            end,
            (end[0] - 13, end[1] - direction * 20),
            (end[0] + 13, end[1] - direction * 20),
        )
    draw.polygon(head, fill=fill)


def _draw_stack_frame(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    *,
    capacity: int,
    used: int,
    columns: int,
) -> None:
    cell_width, cell_height, gap = 64, 44, 8
    for slot in range(capacity):
        row, column = divmod(slot, columns)
        left = x + column * (cell_width + gap)
        top = y + row * (cell_height + gap)
        draw.rounded_rectangle(
            (left, top, left + cell_width, top + cell_height),
            radius=5,
            fill=(199, 231, 212) if slot < used else (255, 255, 255),
            outline=(52, 145, 94) if slot < used else (181, 188, 199),
            width=2,
        )
        if slot < used:
            centered_text(
                draw,
                (left, top, left + cell_width, top + cell_height),
                str(slot),
                font=explain_font(32),
            )


def _draw_dynamic_stack(draw: ImageDraw.ImageDraw) -> None:
    _draw_panel(draw, (48, 154, 920, 910), "Reference: reserve active-cell limit")
    _draw_panel(draw, (1000, 154, 1872, 910), "Optimized: grow within the same limit")
    _draw_stack_frame(draw, 100, 270, capacity=40, used=11, columns=8)
    _draw_wrapped(
        draw,
        (100, 565),
        "capacity = active-cell limit (40 shown)\nused frames = 11",
        width=43,
        size=42,
    )
    _draw_stack_frame(draw, 1050, 270, capacity=16, used=11, columns=8)
    _draw_wrapped(
        draw,
        (1050, 430),
        "start capacity = min(16, limit)\nused frames = 11",
        width=43,
        size=42,
    )
    _draw_arrow(draw, (1240, 575), (1510, 575))
    draw.text((1080, 620), "when count reaches 16", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    draw.text((1515, 548), "16 -> 32 -> limit", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)
    _draw_wrapped(
        draw,
        (1050, 730),
        "Only capacity changes. Both stacks hold the same DFS frames in the same order.",
        width=38,
        size=42,
    )


def _draw_initial_trail(draw: ImageDraw.ImageDraw) -> None:
    _draw_panel(draw, (48, 154, 920, 910), "Reference: record initial undo entries")
    _draw_panel(draw, (1000, 154, 1872, 910), "Optimized: omit unusable undo entries")
    for x, label, color in (
        (100, "D[c3]\n23 -> 8", (210, 229, 244)),
        (345, "trail\n(c3, 23)", (246, 216, 232)),
        (590, "trace\nchange", (255, 232, 188)),
    ):
        draw.rounded_rectangle((x, 280, x + 190, 410), radius=12, fill=color, outline=(150, 158, 172), width=3)
        centered_text(draw, (x, 280, x + 190, 410), label, font=explain_font(40))
    _draw_arrow(draw, (292, 345), (332, 345))
    _draw_arrow(draw, (537, 345), (577, 345))
    for x, label, color in (
        (1050, "D[c3]\n23 -> 8", (210, 229, 244)),
        (1295, "no initial\ntrail entry", (239, 242, 246)),
        (1540, "trace\nchange", (255, 232, 188)),
    ):
        draw.rounded_rectangle((x, 280, x + 190, 410), radius=12, fill=color, outline=(150, 158, 172), width=3)
        centered_text(draw, (x, 280, x + 190, 410), label, font=explain_font(40))
    _draw_arrow(draw, (1242, 345), (1282, 345))
    _draw_arrow(draw, (1487, 345), (1527, 345))
    draw.line((100, 590, 820, 590), fill=(55, 126, 168), width=7)
    draw.line((1050, 590, 1770, 590), fill=(55, 126, 168), width=7)
    for x in (100, 1050):
        draw.ellipse((x - 9, 581, x + 9, 599), fill=(55, 126, 168))
        draw.ellipse((x + 711, 581, x + 729, 599), fill=(55, 126, 168))
    draw.text((100, 620), "initial propagation", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    draw.text((570, 620), "clear initial trail", font=explain_font(38), fill=EXPLAIN_TEXT_RGB)
    draw.text((1050, 620), "initial propagation", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    draw.text((1450, 620), "trail already empty", font=explain_font(38), fill=EXPLAIN_TEXT_RGB)
    _draw_wrapped(draw, (100, 730), "Search starts with trail recording enabled.", width=31, size=44)
    _draw_wrapped(draw, (1050, 730), "Search starts with trail recording enabled.", width=31, size=44)


def _draw_sat_ownership(draw: ImageDraw.ImageDraw) -> None:
    _draw_panel(draw, (48, 154, 920, 910), "Reference: copy after verification")
    _draw_panel(draw, (1000, 154, 1872, 910), "Optimized: transfer after verification")
    for origin_x in (100, 1050):
        draw.rounded_rectangle((origin_x, 260, origin_x + 300, 380), radius=12, fill=(210, 229, 244), outline=(75, 151, 202), width=3)
        centered_text(draw, (origin_x, 260, origin_x + 300, 380), "state.domains", font=explain_font(42))
        _draw_arrow(draw, (origin_x + 310, 320), (origin_x + 445, 320))
        draw.rounded_rectangle((origin_x + 455, 260, origin_x + 700, 380), radius=12, fill=(199, 231, 212), outline=(52, 145, 94), width=3)
        centered_text(draw, (origin_x + 455, 260, origin_x + 700, 380), "verify SAT", font=explain_font(42))
    draw.text((240, 415), "verified first", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    draw.text((1190, 415), "verified first", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    _draw_arrow(draw, (450, 510), (450, 630))
    draw.rounded_rectangle((205, 650, 695, 780), radius=12, fill=(246, 216, 232), outline=(203, 107, 151), width=3)
    centered_text(draw, (205, 650, 695, 780), "copy to best_snapshot", font=explain_font(38))
    _draw_arrow(draw, (1400, 510), (1400, 630))
    draw.rounded_rectangle((1155, 650, 1645, 780), radius=12, fill=(246, 216, 232), outline=(203, 107, 151), width=3)
    centered_text(draw, (1155, 650, 1645, 780), "transfer state.domains", font=explain_font(38))
    draw.text((1080, 795), "state.domains = NULL before destroy", font=explain_font(38), fill=EXPLAIN_TEXT_RGB)
    draw.text((275, 815), "caller owns result", font=explain_font(38), fill=EXPLAIN_TEXT_RGB)
    draw.text((1210, 850), "caller owns result", font=explain_font(38), fill=EXPLAIN_TEXT_RGB)


def _draw_byte_support(draw: ImageDraw.ImageDraw) -> None:
    example = _byte_support_example()
    domain = int(example["domain"])
    chunks = example["chunks"]
    source_tiles = example["source_tiles"]
    source_edges = example["source_east_edges"]
    draw.text((48, 145), f"23-bit source domain  0b{domain:023b}", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
    colors = ((210, 229, 244), (255, 232, 188), (246, 216, 232))
    for byte, (chunk, tile, edge, color) in enumerate(zip(chunks, source_tiles, source_edges, colors, strict=True)):
        x = 48 + byte * 430
        draw.rounded_rectangle((x, 235, x + 360, 500), radius=16, fill=color, outline=(124, 133, 149), width=3)
        draw.text((x + 24, 252), f"byte {byte}: 0x{chunk:02X}", font=explain_font(46), fill=EXPLAIN_TEXT_RGB)
        draw.text((x + 24, 325), f"set bit -> tile {tile}", font=explain_font(44), fill=EXPLAIN_TEXT_RGB)
        draw.text((x + 24, 390), f"east edge = {edge}", font=explain_font(44), fill=EXPLAIN_TEXT_RGB)
        draw.text((x + 24, 450), "one table lookup", font=explain_font(42), fill=EXPLAIN_MUTED_RGB)
        _draw_arrow(draw, (x + 360, 367), (x + 405, 367))
    draw.rounded_rectangle((1390, 235, 1872, 500), radius=16, fill=(199, 231, 212), outline=(52, 145, 94), width=3)
    centered_text(draw, (1390, 250, 1872, 330), "OR three support masks", font=explain_font(44))
    _draw_wrapped(
        draw,
        (1420, 345),
        "east {2,3} supports neighbors whose west edge is 2 or 3",
        width=23,
        size=40,
    )
    supported = "  ".join(str(tile) for tile in example["supported_tiles"])
    draw.rounded_rectangle((48, 610, 1872, 820), radius=16, fill=(239, 242, 246), outline=(174, 181, 193), width=3)
    draw.text((80, 635), "supported neighbor tile IDs", font=explain_font(42), fill=EXPLAIN_MUTED_RGB)
    draw.text((80, 705), supported, font=explain_font(44), fill=EXPLAIN_TEXT_RGB)
    draw.text((48, 865), "Zero byte: skip lookup. Unused 24th bit: no tile.", font=explain_font(40), fill=EXPLAIN_MUTED_RGB)


def _draw_queue_dedup(draw: ImageDraw.ImageDraw) -> None:
    steps = _queue_dedup_steps()
    for index, (label, action, queue) in enumerate(steps):
        x = 48 + index * 462
        draw.rounded_rectangle((x, 190, x + 414, 835), radius=18, fill=(239, 242, 246), outline=(174, 181, 193), width=3)
        draw.text((x + 24, 220), f"{index + 1}. {label}", font=explain_font(36), fill=EXPLAIN_TEXT_RGB)
        action_color = (52, 145, 94) if action == "append" else ((214, 91, 91) if action == "suppress" else (55, 126, 168))
        draw.rounded_rectangle((x + 24, 300, x + 390, 390), radius=12, fill=(255, 255, 255), outline=action_color, width=4)
        centered_text(draw, (x + 24, 300, x + 390, 390), action, font=explain_font(46), fill=action_color)
        draw.text((x + 24, 455), "FIFO", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
        draw.rounded_rectangle((x + 24, 505, x + 390, 615), radius=10, fill=(255, 255, 255), outline=(181, 188, 199), width=3)
        if queue:
            draw.rounded_rectangle((x + 45, 525, x + 145, 595), radius=8, fill=(210, 229, 244), outline=(75, 151, 202), width=3)
            centered_text(draw, (x + 45, 525, x + 145, 595), "c7", font=explain_font(42))
        else:
            centered_text(draw, (x + 24, 505, x + 390, 615), "empty", font=explain_font(42), fill=EXPLAIN_MUTED_RGB)
        pending = bool(queue)
        draw.text((x + 24, 680), "pending bit c7", font=explain_font(36), fill=EXPLAIN_MUTED_RGB)
        draw.ellipse((x + 285, 675, x + 345, 735), fill=(52, 145, 94) if pending else (255, 255, 255), outline=(52, 145, 94), width=4)
        centered_text(draw, (x + 285, 675, x + 345, 735), "1" if pending else "0", font=explain_font(40), fill=(255, 255, 255) if pending else EXPLAIN_TEXT_RGB)
    draw.text((48, 875), "Suppress only while an unconsumed c7 is pending.", font=explain_font(40), fill=EXPLAIN_MUTED_RGB)


def _draw_mrv_state(
    draw: ImageDraw.ImageDraw,
    x: int,
    state: tuple[str, tuple[tuple[int, int], ...], tuple[tuple[int, tuple[int, ...]], ...], int],
) -> None:
    label, domains, buckets, selected = state
    draw.rounded_rectangle((x, 300, x + 570, 820), radius=18, fill=(239, 242, 246), outline=(174, 181, 193), width=3)
    draw.text((x + 24, 320), label, font=explain_font(40), fill=EXPLAIN_TEXT_RGB)
    draw.text((x + 24, 390), "domains", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    draw.text((x + 380, 390), f"select c{selected}", font=explain_font(38), fill=(111, 82, 176))
    for index, (cell, size) in enumerate(domains):
        left = x + 24 + index * 170
        fill = (231, 222, 249) if cell == selected else (255, 255, 255)
        draw.rounded_rectangle((left, 445, left + 145, 520), radius=9, fill=fill, outline=(111, 82, 176) if cell == selected else (181, 188, 199), width=3)
        centered_text(draw, (left, 445, left + 145, 520), f"c{cell}: {size}", font=explain_font(52))
    draw.text((x + 24, 555), "buckets: size -> cells", font=explain_font(38), fill=EXPLAIN_MUTED_RGB)
    y = 615
    for size, cells in buckets:
        draw.text((x + 70, y), str(size), font=explain_font(52), fill=EXPLAIN_TEXT_RGB)
        draw.rounded_rectangle((x + 170, y - 7, x + 520, y + 43), radius=7, fill=(255, 255, 255), outline=(181, 188, 199), width=2)
        draw.text((x + 190, y), "  ".join(f"c{cell}" for cell in cells), font=explain_font(50), fill=EXPLAIN_TEXT_RGB)
        y += 58


def _draw_lazy_mrv(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((48, 145, 1872, 255), radius=14, fill=(255, 232, 188), outline=(217, 119, 6), width=3)
    draw.text((78, 166), "Root: row-major scan. Build the private index only after a surviving nonterminal branch.", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)
    for x, state in zip((48, 675, 1302), _mrv_bucket_steps(), strict=True):
        _draw_mrv_state(draw, x, state)
    draw.text((48, 850), "domains = semantic source of truth", font=explain_font(44), fill=EXPLAIN_TEXT_RGB)
    draw.text((1010, 850), "MRV index = private derived state", font=explain_font(44), fill=EXPLAIN_TEXT_RGB)
    _draw_wrapped(
        draw,
        (48, 900),
        "Buckets 2-23; exclude 0, 1, inactive.\nPick lowest size, then lowest row-major cell.",
        width=72,
        size=52,
        fill=EXPLAIN_MUTED_RGB,
        spacing=3,
    )


def _optimized_frame(stage: int) -> Image.Image:
    if not 0 <= stage < len(_OPTIMIZATIONS):
        raise WangSquareRenderError("optimized mechanism stage lies outside panels")
    mechanism = _OPTIMIZATIONS[stage]
    image, draw = _optimized_canvas(mechanism, stage)
    painters = (
        _draw_dynamic_stack,
        _draw_initial_trail,
        _draw_sat_ownership,
        _draw_byte_support,
        _draw_queue_dedup,
        _draw_lazy_mrv,
    )
    painters[stage](draw)
    return image


def _draw_summary_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    mechanism: _Optimization,
    index: int,
) -> None:
    left, top, right, bottom = box
    draw.rounded_rectangle(
        box,
        radius=16,
        fill=(239, 242, 246),
        outline=(174, 181, 193),
        width=3,
    )
    draw.text(
        (left + 24, top + 17),
        mechanism.title,
        font=explain_font(50),
        fill=EXPLAIN_TEXT_RGB,
    )
    center_y = top + 143
    if index == 0:
        for slot in range(8):
            x = left + 30 + slot * 54
            draw.rounded_rectangle(
                (x, center_y - 28, x + 44, center_y + 28),
                radius=5,
                fill=(199, 231, 212) if slot < 5 else (255, 255, 255),
                outline=(52, 145, 94) if slot < 5 else (181, 188, 199),
                width=2,
            )
        _draw_arrow(draw, (left + 482, center_y), (left + 590, center_y))
        draw.text((left + 610, center_y - 28), "grow -> limit", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)
    elif index == 1:
        draw.rounded_rectangle((left + 30, center_y - 40, left + 235, center_y + 40), radius=8, fill=(210, 229, 244), outline=(75, 151, 202), width=3)
        centered_text(draw, (left + 30, center_y - 40, left + 250, center_y + 40), "domain delta", font=explain_font(38))
        _draw_arrow(draw, (left + 265, center_y), (left + 365, center_y))
        draw.rounded_rectangle((left + 380, center_y - 40, left + 555, center_y + 40), radius=8, fill=(255, 232, 188), outline=(217, 119, 6), width=3)
        centered_text(draw, (left + 380, center_y - 40, left + 555, center_y + 40), "trace kept", font=explain_font(36))
        draw.rounded_rectangle((left + 610, center_y - 40, left + 835, center_y + 40), radius=8, fill=(255, 255, 255), outline=(214, 91, 91), width=3)
        centered_text(draw, (left + 620, center_y - 40, left + 790, center_y + 40), "initial\nundo entry", font=explain_font(36), fill=EXPLAIN_TEXT_RGB)
        draw.line((left + 800, center_y - 20, left + 825, center_y + 20), fill=(214, 91, 91), width=5)
        draw.line((left + 825, center_y - 20, left + 800, center_y + 20), fill=(214, 91, 91), width=5)
    elif index == 2:
        draw.rounded_rectangle((left + 30, center_y - 40, left + 245, center_y + 40), radius=8, fill=(199, 231, 212), outline=(52, 145, 94), width=3)
        centered_text(draw, (left + 30, center_y - 40, left + 245, center_y + 40), "verify SAT", font=explain_font(40))
        _draw_arrow(draw, (left + 260, center_y), (left + 390, center_y))
        draw.rounded_rectangle((left + 405, center_y - 40, left + 680, center_y + 40), radius=8, fill=(246, 216, 232), outline=(203, 107, 151), width=3)
        centered_text(draw, (left + 405, center_y - 40, left + 680, center_y + 40), "transfer buffer", font=explain_font(38))
        draw.text((left + 700, center_y - 25), "caller owns", font=explain_font(38), fill=EXPLAIN_TEXT_RGB)
    elif index == 3:
        for byte, label in enumerate(("01", "04", "40")):
            x = left + 30 + byte * 120
            draw.rounded_rectangle((x, center_y - 40, x + 90, center_y + 40), radius=8, fill=((210, 229, 244), (255, 232, 188), (246, 216, 232))[byte], outline=(124, 133, 149), width=3)
            centered_text(draw, (x, center_y - 40, x + 90, center_y + 40), label, font=explain_font(42))
        _draw_arrow(draw, (left + 390, center_y), (left + 520, center_y))
        draw.rounded_rectangle((left + 535, center_y - 40, left + 835, center_y + 40), radius=8, fill=(199, 231, 212), outline=(52, 145, 94), width=3)
        centered_text(draw, (left + 535, center_y - 40, left + 835, center_y + 40), "OR 3 masks", font=explain_font(42))
    elif index == 4:
        labels = (("+ c7", "1"), ("dup x", "1"), ("pop", "0"), ("later +", "1"))
        for step, (event, pending) in enumerate(labels):
            x = left + 30 + step * 205
            draw.text((x, center_y - 35), event, font=explain_font(38), fill=EXPLAIN_TEXT_RGB)
            draw.ellipse((x + 118, center_y - 38, x + 190, center_y + 34), fill=(52, 145, 94) if pending == "1" else (255, 255, 255), outline=(52, 145, 94), width=3)
            centered_text(draw, (x + 118, center_y - 38, x + 190, center_y + 34), pending, font=explain_font(40), fill=(255, 255, 255) if pending == "1" else EXPLAIN_TEXT_RGB)
    else:
        labels = (("bucket 4", "c2"), ("bucket 2", "c2 c5"), ("bucket 4", "c2"))
        for step, (bucket, cells) in enumerate(labels):
            x = left + 30 + step * 275
            draw.rounded_rectangle((x, center_y - 45, x + 225, center_y + 45), radius=8, fill=(231, 222, 249), outline=(111, 82, 176), width=3)
            centered_text(draw, (x, center_y - 45, x + 225, center_y - 3), bucket, font=explain_font(36))
            centered_text(draw, (x, center_y + 1, x + 225, center_y + 45), cells, font=explain_font(38), fill=(111, 82, 176))
            if step < 2:
                _draw_arrow(draw, (x + 232, center_y), (x + 267, center_y))


def _optimized_summary() -> Image.Image:
    image = Image.new("RGB", (1920, 1040), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (48, 34),
        title="Optimized serial mechanisms",
        subtitle="didactic summary | six private storage/work changes; shared search semantics",
        scale=EXPLAIN_RENDER_SCALE,
    )
    for index, mechanism in enumerate(_OPTIMIZATIONS):
        column, row = index % 2, index // 2
        x = 48 + column * 936
        y = 145 + row * 267
        _draw_summary_card(draw, (x, y, x + 888, y + 235), mechanism, index)
    draw.text((48, 950), "Six concrete state changes; full frames retain details.", font=explain_font(34), fill=EXPLAIN_MUTED_RGB)
    return image


def render_optimized_assets(
    output_directory: str | Path,
    *,
    duration_ms: int = 750,
) -> AnimationOutputs:
    mechanism_frames = tuple(_optimized_frame(stage) for stage in range(6))
    frames = (*mechanism_frames, _optimized_summary())
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
