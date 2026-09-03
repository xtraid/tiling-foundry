"""Frame selection and raster composition for replayed solver traces."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

from wang_animation import AnimationOutputs, write_animation_assets
from wang_explain import (
    EXPLAIN_INACTIVE_DARK_RGB,
    EXPLAIN_INACTIVE_LIGHT_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_explain_heading,
    explain_font,
)
from wang_hex_port import WangSquareRenderError
from wang_square import MAX_CANVAS_PIXELS, MAX_CANVAS_SIDE
from wang_trace import TraceBundle, TraceEvent, load_trace_bundle, replay_trace


_CELL_SIZE: Final = 18
_MARGIN: Final = 14
_HEADER: Final = 76
_LEGEND_WIDTH: Final = 210
_GAP: Final = 12
_UNSAT_RGB: Final = (218, 82, 82)
_SINGLETON_RGB: Final = (83, 166, 116)
_CHANGED_RGB: Final = (245, 178, 60)


def select_semantic_milestones(
    events: tuple[TraceEvent, ...], maximum: int
) -> tuple[int, ...]:
    """Select semantic transitions first, then fill the widest replay gaps.

    This is intentionally different from uniform frame sampling.  The selected
    states still come from the single validated replay performed by the caller.
    """
    if type(maximum) is not int or not 2 <= maximum <= 32:
        raise WangSquareRenderError("max_frames must be in [2, 32]")
    count = len(events)
    if count <= maximum:
        return tuple(range(count))

    priority = [0, count - 1]
    for index in range(1, count):
        if events[index].phase != events[index - 1].phase:
            priority.extend((index - 1, index))
    for kind in (
        "propagation",
        "decision",
        "conflict",
        "backtrack",
        "domain_reduction",
    ):
        matches = [
            index for index, event in enumerate(events) if event.kind == kind
        ]
        if matches:
            priority.extend((matches[0], matches[-1]))
    priority.extend(
        index
        for index, event in enumerate(events)
        if event.kind == "domain_reduction"
        and event.reason in {"decision", "backtrack"}
    )
    deepest_decisions = [
        (event.depth, index)
        for index, event in enumerate(events)
        if event.kind == "decision"
    ]
    if deepest_decisions:
        priority.append(max(deepest_decisions)[1])

    selected = list(dict.fromkeys(priority))[:maximum]
    while len(selected) < maximum:
        candidate = max(
            (index for index in range(count) if index not in selected),
            key=lambda index: (min(abs(index - item) for item in selected), -index),
        )
        selected.append(candidate)
    return tuple(sorted(selected))


def _domain_rgb(domain: int) -> tuple[int, int, int]:
    if domain == 0:
        return _UNSAT_RGB
    count = domain.bit_count()
    if count == 1:
        return _SINGLETON_RGB
    shade = 225 - min(12, count - 2) * 6
    return (128, max(145, shade - 24), shade)


def _compose_frame(
    bundle: TraceBundle,
    event: TraceEvent,
    domains: tuple[int, ...],
) -> Image.Image:
    region = bundle.explanation.region
    grid_width = region.width * _CELL_SIZE
    grid_height = region.height * _CELL_SIZE
    width = 2 * _MARGIN + grid_width + _GAP + _LEGEND_WIDTH
    height = 2 * _MARGIN + _HEADER + max(grid_height, 310)
    if (
        width > MAX_CANVAS_SIDE
        or height > MAX_CANVAS_SIDE
        or width * height > MAX_CANVAS_PIXELS
    ):
        raise WangSquareRenderError("solver trace frame exceeds canvas limits")
    image = Image.new("RGB", (width, height), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    subtitle = (
        f"observed event {event.sequence + 1}/{bundle.trace.observed_event_count}"
        f" | {event.kind.replace('_', ' ')} | depth {event.depth}"
    )
    if (
        bundle.trace.truncated
        and event.kind == "result"
        and event.sequence >= len(bundle.trace.events)
    ):
        subtitle += " | prefix state; omitted events are not reconstructed"
    draw_explain_heading(
        draw,
        (_MARGIN, _MARGIN),
        title=f"Observed {bundle.trace.solver} solver trace",
        subtitle=subtitle,
    )
    top = _MARGIN + _HEADER
    for index, (active, domain) in enumerate(
        zip(region.active, domains, strict=True)
    ):
        x = _MARGIN + (index % region.width) * _CELL_SIZE
        y = top + (index // region.width) * _CELL_SIZE
        box = (x, y, x + _CELL_SIZE - 1, y + _CELL_SIZE - 1)
        if not active:
            fill = (
                EXPLAIN_INACTIVE_LIGHT_RGB
                if (index % region.width + index // region.width) % 2 == 0
                else EXPLAIN_INACTIVE_DARK_RGB
            )
        else:
            fill = _domain_rgb(domain)
        draw.rectangle(box, fill=fill, outline=(178, 184, 194))
        if active and domain != 0 and domain.bit_count() == 1:
            tile_id = domain.bit_length() - 1
            draw.text(
                (x + 4, y + 2),
                str(tile_id),
                font=explain_font(9),
                fill=EXPLAIN_TEXT_RGB,
            )
        if event.cell == index:
            draw.rectangle(box, outline=_CHANGED_RGB, width=3)

    legend_x = _MARGIN + grid_width + _GAP
    legend_y = top + 4
    draw.text(
        (legend_x, legend_y),
        "Domain state",
        font=explain_font(14),
        fill=EXPLAIN_TEXT_RGB,
    )
    entries = (
        (_SINGLETON_RGB, "singleton / selected tile"),
        (_domain_rgb(8), "multiple candidate tiles"),
        (_UNSAT_RGB, "empty domain / conflict"),
        (_CHANGED_RGB, "current event cell"),
    )
    for offset, (color, label) in enumerate(entries, start=1):
        y = legend_y + offset * 28
        draw.rectangle((legend_x, y, legend_x + 18, y + 18), fill=color)
        draw.text(
            (legend_x + 26, y + 2),
            label,
            font=explain_font(10),
            fill=EXPLAIN_TEXT_RGB,
        )
    details = [
        f"phase: {event.phase or '-'}",
        f"reason: {event.reason or '-'}",
        f"change mark: {event.change_mark}",
        f"active: {sum(region.active)}",
        f"fixed: {sum(domain.bit_count() == 1 for domain in domains)}",
        f"empty: {sum(domain == 0 for domain in domains)}",
    ]
    y = legend_y + 142
    for line in details:
        draw.text(
            (legend_x, y),
            line,
            font=explain_font(10),
            fill=EXPLAIN_MUTED_RGB,
        )
        y += 18
    draw.text(
        (legend_x, height - _MARGIN - 15),
        "Rendering is not a correctness proof.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_trace_assets(
    manifest_path: str | Path,
    output_directory: str | Path,
    *,
    max_frames: int = 12,
    duration_ms: int = 500,
) -> AnimationOutputs:
    """Replay once, compose each selected frame once, then encode assets."""
    bundle = load_trace_bundle(manifest_path)
    states = replay_trace(bundle.trace)
    selected = select_semantic_milestones(bundle.trace.events, max_frames)
    frames = tuple(
        _compose_frame(bundle, bundle.trace.events[index], states[index])
        for index in selected
    )
    fallback_index = next(
        (
            index
            for index, selected_index in enumerate(selected)
            if bundle.trace.events[selected_index].kind == "decision"
        ),
        len(frames) - 1,
    )
    return write_animation_assets(
        frames,
        tuple(
            f"frame-{bundle.trace.events[index].sequence:06d}.png"
            for index in selected
        ),
        output_directory,
        fallback_index=fallback_index,
        duration_ms=duration_ms,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="replay a solver-trace v3 bundle and render observed states"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--duration-ms", type=int, default=500)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        outputs = render_trace_assets(
            args.manifest,
            args.output_directory,
            max_frames=args.max_frames,
            duration_ms=args.duration_ms,
        )
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))
    print(f"animation={outputs.animation}")
    print(f"contact_sheet={outputs.contact_sheet}")
    print(f"fallback={outputs.fallback}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
