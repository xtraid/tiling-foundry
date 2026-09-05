"""Frame selection and raster composition for replayed solver traces."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

from wang_animation import AnimationOutputs, write_animation_assets
from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_CONFLICT_RGB,
    EXPLAIN_DECISION_RGB,
    EXPLAIN_INACTIVE_DARK_RGB,
    EXPLAIN_INACTIVE_LIGHT_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_PROPAGATION_SOURCE_RGB,
    EXPLAIN_PROPAGATION_TARGET_RGB,
    EXPLAIN_RENDER_SCALE,
    EXPLAIN_RESTORED_RGB,
    EXPLAIN_SELECTED_MRV_RGB,
    EXPLAIN_SINGLETON_RGB,
    EXPLAIN_TEXT_RGB,
    EXPLAIN_TRAIL_MUTATION_RGB,
    EXPLAIN_UNRESOLVED_RGB,
    centered_text,
    draw_explain_heading,
    explain_font,
)
from wang_hex_port import WangSquareRenderError
from wang_square import MAX_CANVAS_PIXELS, MAX_CANVAS_SIDE
from wang_trace import TraceBundle, TraceEvent, load_trace_bundle, replay_trace


_CELL_SIZE: Final = 18 * EXPLAIN_RENDER_SCALE
_MARGIN: Final = 14 * EXPLAIN_RENDER_SCALE
_HEADER: Final = 76 * EXPLAIN_RENDER_SCALE
_LEGEND_WIDTH: Final = 210 * EXPLAIN_RENDER_SCALE
_GAP: Final = 12 * EXPLAIN_RENDER_SCALE
_UNSAT_RGB: Final = EXPLAIN_CONFLICT_RGB
_SINGLETON_RGB: Final = EXPLAIN_SINGLETON_RGB
_CHANGED_RGB: Final = EXPLAIN_DECISION_RGB


def _scaled(value: int) -> int:
    return value * EXPLAIN_RENDER_SCALE


def _frame_height(grid_height: int) -> int:
    return 2 * _MARGIN + _HEADER + max(
        grid_height + _scaled(112),
        _scaled(310),
    )


def _first_index_after(
    events: tuple[TraceEvent, ...],
    start: int,
    *,
    kind: str,
) -> int | None:
    return next(
        (
            index
            for index in range(start + 1, len(events))
            if events[index].kind == kind
        ),
        None,
    )


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
        if events[index].phase == "search" and events[index - 1].phase != "search":
            priority.extend((index - 1, index))

    first_decision = next(
        (
            index
            for index, event in enumerate(events)
            if event.kind == "decision" and event.phase == "search"
        ),
        None,
    )
    if first_decision is not None:
        priority.append(first_decision)
        decision_reduction = next(
            (
                index
                for index in range(first_decision + 1, count)
                if events[index].kind == "domain_reduction"
                and events[index].reason == "decision"
                and events[index].cell == events[first_decision].cell
            ),
            None,
        )
        if decision_reduction is not None:
            priority.append(decision_reduction)
            propagation_reduction = next(
                (
                    index
                    for index in range(decision_reduction + 1, count)
                    if events[index].kind == "domain_reduction"
                    and events[index].reason == "propagation"
                ),
                None,
            )
            if propagation_reduction is not None:
                priority.append(propagation_reduction)

        conflict = _first_index_after(events, first_decision, kind="conflict")
        if conflict is not None:
            empty_reduction = next(
                (
                    index
                    for index in range(conflict - 1, first_decision, -1)
                    if events[index].kind == "domain_reduction"
                    and events[index].new_domain == 0
                ),
                None,
            )
            if empty_reduction is not None:
                priority.append(empty_reduction)
            priority.append(conflict)
            backtrack = _first_index_after(events, conflict, kind="backtrack")
            if backtrack is not None:
                priority.append(backtrack)
                next_decision = _first_index_after(
                    events, backtrack, kind="decision"
                )
                if next_decision is not None:
                    priority.append(next_decision)
        else:
            final_propagation = next(
                (
                    index
                    for index in range(count - 1, first_decision, -1)
                    if events[index].kind == "propagation"
                ),
                None,
            )
            final_reduction = next(
                (
                    index
                    for index in range(count - 1, first_decision, -1)
                    if events[index].kind == "domain_reduction"
                    and events[index].reason == "propagation"
                ),
                None,
            )
            if final_propagation is not None:
                priority.append(final_propagation)
            if final_reduction is not None:
                priority.append(final_reduction)

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


def _domain_tiles(domain: int, tile_count: int) -> tuple[int, ...]:
    return tuple(tile for tile in range(tile_count) if domain & (1 << tile))


def _format_domain(domain: int, tile_count: int) -> str:
    return "{" + ", ".join(map(str, _domain_tiles(domain, tile_count))) + "}"


def _propagation_reason(
    bundle: TraceBundle,
    event: TraceEvent,
    before: tuple[int, ...],
) -> tuple[int, str, str, tuple[int, ...]] | None:
    """Derive one unique adjacent support reason from a validated before-state."""
    if (
        event.kind != "domain_reduction"
        or event.reason != "propagation"
        or event.cell is None
        or event.old_domain is None
        or event.new_domain is None
    ):
        return None
    region = bundle.explanation.region
    target_x = event.cell % region.width
    target_y = event.cell // region.width
    tiles = bundle.explanation.tileset.tile_edges
    relations = (
        (0, -1, "S", 2, "N", 0),
        (1, 0, "W", 3, "E", 1),
        (0, 1, "N", 0, "S", 2),
        (-1, 0, "E", 1, "W", 3),
    )
    candidates: list[tuple[int, str, str, tuple[int, ...]]] = []
    for dx, dy, source_side, source_edge, target_side, target_edge in relations:
        source_x = target_x + dx
        source_y = target_y + dy
        if not (0 <= source_x < region.width and 0 <= source_y < region.height):
            continue
        source_cell = source_y * region.width + source_x
        if not region.active[source_cell]:
            continue
        source_colors = {
            tiles[tile][source_edge]
            for tile in _domain_tiles(before[source_cell], len(tiles))
        }
        supported = sum(
            1 << tile
            for tile in _domain_tiles(event.old_domain, len(tiles))
            if tiles[tile][target_edge] in source_colors
        )
        if supported != event.new_domain:
            continue
        shared_colors = tuple(
            sorted(
                {
                    tiles[tile][target_edge]
                    for tile in _domain_tiles(event.new_domain, len(tiles))
                }
                & source_colors
            )
        )
        candidates.append((source_cell, source_side, target_side, shared_colors))
    return candidates[0] if len(candidates) == 1 else None


def _restored_changes(
    events: tuple[TraceEvent, ...], backtrack_index: int
) -> tuple[tuple[int, int, int], ...]:
    """Return observed deltas restored by one backtrack in reverse trail order."""
    trail: list[tuple[int, int, int]] = []
    for event in events[:backtrack_index]:
        if event.kind == "domain_reduction":
            assert (
                event.cell is not None
                and event.old_domain is not None
                and event.new_domain is not None
            )
            trail.append((event.cell, event.new_domain, event.old_domain))
        elif event.kind == "backtrack":
            del trail[event.change_mark :]
    backtrack = events[backtrack_index]
    if backtrack.kind != "backtrack":
        return ()
    return tuple(reversed(trail[backtrack.change_mark :]))


def _previous_search_event(
    events: tuple[TraceEvent, ...], index: int, kind: str
) -> TraceEvent | None:
    return next(
        (event for event in reversed(events[:index]) if event.kind == kind),
        None,
    )


def _next_search_event(
    events: tuple[TraceEvent, ...], index: int, kind: str
) -> TraceEvent | None:
    return next(
        (event for event in events[index + 1 :] if event.kind == kind),
        None,
    )


def _domain_rgb(domain: int) -> tuple[int, int, int]:
    if domain == 0:
        return _UNSAT_RGB
    count = domain.bit_count()
    if count == 1:
        return _SINGLETON_RGB
    return EXPLAIN_UNRESOLVED_RGB


def _active_domain_counts(
    active: tuple[bool, ...], domains: tuple[int, ...]
) -> tuple[int, int]:
    """Return fixed and empty domains, excluding inactive bounding-box cells."""
    return (
        sum(
            is_active and domain.bit_count() == 1
            for is_active, domain in zip(active, domains, strict=True)
        ),
        sum(
            is_active and domain == 0
            for is_active, domain in zip(active, domains, strict=True)
        ),
    )


def _summary_box(
    draw: ImageDraw.ImageDraw,
    *,
    top: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    box = (_MARGIN, top, width - _MARGIN - 1, height - _MARGIN - 1)
    if box[3] - box[1] < _scaled(82):
        return None
    draw.rectangle(
        box,
        fill=EXPLAIN_ACTIVE_RGB,
        outline=(178, 184, 194),
        width=_scaled(1),
    )
    return box


def _draw_propagation_summary(
    draw: ImageDraw.ImageDraw,
    bundle: TraceBundle,
    event: TraceEvent,
    reason: tuple[int, str, str, tuple[int, ...]],
    *,
    top: int,
    width: int,
    height: int,
) -> None:
    box = _summary_box(draw, top=top, width=width, height=height)
    if box is None:
        return
    assert event.cell is not None
    assert event.old_domain is not None
    assert event.new_domain is not None
    tile_count = len(bundle.explanation.tileset.tile_edges)
    source_cell, source_side, target_side, colors = reason
    removed = event.old_domain & ~event.new_domain
    x = _MARGIN + _scaled(12)
    draw.text(
        (x, top + _scaled(9)),
        f"Propagation: cell {source_cell} {source_side} -> "
        f"cell {event.cell} {target_side}",
        font=explain_font(_scaled(24)),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (x, top + _scaled(39)),
        "Shared edge "
        + ", ".join(map(str, colors))
        + "; unique in observed before-state",
        font=explain_font(_scaled(24)),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (x, top + _scaled(69)),
        f"Domain {_format_domain(event.old_domain, tile_count)} -> "
        f"{_format_domain(event.new_domain, tile_count)}; "
        f"removed {_format_domain(removed, tile_count)}",
        font=explain_font(_scaled(24)),
        fill=EXPLAIN_TEXT_RGB,
    )

    card_width = _scaled(88)
    card_height = _scaled(58)
    card_gap = _scaled(28)
    target_left = width - _MARGIN - card_width
    source_left = target_left - card_gap - card_width
    card_top = top + _scaled(16)
    for left, color, title, cell in (
        (source_left, EXPLAIN_PROPAGATION_SOURCE_RGB, "source", source_cell),
        (target_left, EXPLAIN_PROPAGATION_TARGET_RGB, "restricted", event.cell),
    ):
        draw.rectangle(
            (left, card_top, left + card_width, card_top + card_height),
            fill=color,
            outline=EXPLAIN_TEXT_RGB,
            width=_scaled(1),
        )
        centered_text(
            draw,
            (left, card_top, left + card_width, card_top + card_height),
            f"{title}\ncell {cell}",
            font=explain_font(_scaled(13)),
        )
    arrow_y = card_top + card_height // 2
    draw.line(
        (source_left + card_width, arrow_y, target_left, arrow_y),
        fill=EXPLAIN_TEXT_RGB,
        width=_scaled(2),
    )
    draw.polygon(
        (
            (target_left, arrow_y),
            (target_left - _scaled(7), arrow_y - _scaled(5)),
            (target_left - _scaled(7), arrow_y + _scaled(5)),
        ),
        fill=EXPLAIN_TEXT_RGB,
    )


def _draw_search_summary(
    draw: ImageDraw.ImageDraw,
    bundle: TraceBundle,
    event: TraceEvent,
    event_index: int,
    restored: tuple[tuple[int, int, int], ...],
    *,
    top: int,
    width: int,
    height: int,
) -> None:
    box = _summary_box(draw, top=top, width=width, height=height)
    if box is None:
        return
    events = bundle.trace.events
    decision = _previous_search_event(events, event_index, "decision")
    conflict = (
        event
        if event.kind == "conflict"
        else _previous_search_event(events, event_index, "conflict")
    )
    next_decision = _next_search_event(events, event_index, "decision")
    tile_count = len(bundle.explanation.tileset.tile_edges)
    x = _MARGIN + _scaled(12)
    if decision is not None and decision.cell is not None and decision.new_domain:
        chosen = _format_domain(decision.new_domain, tile_count)
        title = (
            f"DFS conflict d{event.depth}: "
            if event.kind == "conflict"
            else f"Rollback d{event.depth}: "
        )
        title += f"cell {decision.cell} branch {chosen}"
    else:
        title = (
            f"DFS conflict at depth {event.depth}"
            if event.kind == "conflict"
            else f"Rollback at depth {event.depth}"
        )
    draw.text(
        (x, top + _scaled(9)),
        title,
        font=explain_font(_scaled(24)),
        fill=EXPLAIN_TEXT_RGB,
    )
    if event.kind == "conflict":
        draw.text(
            (x, top + _scaled(46)),
            f"Cell {event.cell} -> empty domain; trail {event.change_mark}",
            font=explain_font(_scaled(24)),
            fill=EXPLAIN_TEXT_RGB,
        )
    else:
        conflict_mark = (
            conflict.change_mark if conflict is not None else event.change_mark
        )
        draw.text(
            (x, top + _scaled(40)),
            f"Restore {len(restored)} changes in reverse; "
            f"trail {conflict_mark} -> {event.change_mark}",
            font=explain_font(_scaled(24)),
            fill=EXPLAIN_TEXT_RGB,
        )
        if restored:
            sample = "; ".join(
                f"cell {cell}: {_format_domain(current, tile_count)} -> "
                f"{_format_domain(previous, tile_count)}"
                for cell, current, previous in restored[:2]
            )
            draw.text(
                (x, top + _scaled(70)),
                f"First restores: {sample}",
                font=explain_font(_scaled(24)),
                fill=EXPLAIN_TEXT_RGB,
            )

    card_width = _scaled(82)
    card_height = _scaled(58)
    card_gap = _scaled(10)
    cards_left = width - _MARGIN - 3 * card_width - 2 * card_gap
    card_top = top + _scaled(17)
    next_label = "next\nbranch"
    if (
        next_decision is not None
        and next_decision.cell is not None
        and next_decision.new_domain is not None
    ):
        next_label = (
            "next "
            + _format_domain(next_decision.new_domain, tile_count)
            + f"\ncell {next_decision.cell}"
        )
    elif next_decision is None:
        next_label = "search\nend"
    for offset, color, label in (
        (0, EXPLAIN_DECISION_RGB, "candidate\nbranch"),
        (1, EXPLAIN_CONFLICT_RGB, "empty\ndomain"),
        (2, EXPLAIN_RESTORED_RGB, next_label),
    ):
        left = cards_left + offset * (card_width + card_gap)
        draw.rectangle(
            (left, card_top, left + card_width, card_top + card_height),
            fill=color,
            outline=EXPLAIN_TEXT_RGB,
            width=_scaled(1),
        )
        centered_text(
            draw,
            (left, card_top, left + card_width, card_top + card_height),
            label,
            font=explain_font(_scaled(12)),
        )
        if offset < 2:
            arrow_y = card_top + card_height // 2
            draw.line(
                (left + card_width, arrow_y, left + card_width + card_gap, arrow_y),
                fill=EXPLAIN_TRAIL_MUTATION_RGB,
                width=_scaled(2),
            )


def _compose_frame(
    bundle: TraceBundle,
    event: TraceEvent,
    domains: tuple[int, ...],
    before: tuple[int, ...],
    event_index: int,
) -> Image.Image:
    region = bundle.explanation.region
    fixed_count, empty_count = _active_domain_counts(region.active, domains)
    propagation = _propagation_reason(bundle, event, before)
    restored = (
        _restored_changes(bundle.trace.events, event_index)
        if event.kind == "backtrack"
        else ()
    )
    restored_cells = {cell for cell, _, _ in restored}
    mrv_candidates: tuple[int, ...] = ()
    minimum_domain_size: int | None = None
    if event.kind == "decision":
        unresolved = tuple(
            (index, domain.bit_count())
            for index, (active, domain) in enumerate(
                zip(region.active, domains, strict=True)
            )
            if active and domain.bit_count() > 1
        )
        if unresolved:
            minimum_domain_size = min(count for _, count in unresolved)
            mrv_candidates = tuple(
                index for index, count in unresolved if count == minimum_domain_size
            )
    grid_width = region.width * _CELL_SIZE
    grid_height = region.height * _CELL_SIZE
    width = 2 * _MARGIN + grid_width + _GAP + _LEGEND_WIDTH
    height = _frame_height(grid_height)
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
        scale=EXPLAIN_RENDER_SCALE,
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
        if index in mrv_candidates:
            fill = EXPLAIN_SELECTED_MRV_RGB
        if propagation is not None and index == propagation[0]:
            fill = EXPLAIN_PROPAGATION_SOURCE_RGB
        if propagation is not None and index == event.cell:
            fill = EXPLAIN_PROPAGATION_TARGET_RGB
        if index in restored_cells:
            fill = EXPLAIN_RESTORED_RGB
        draw.rectangle(box, fill=fill, outline=(178, 184, 194), width=_scaled(1))
        if active:
            centered_text(
                draw,
                box,
                str(domain.bit_count()),
                font=explain_font(_scaled(10)),
            )
        if event.cell == index:
            draw.rectangle(box, outline=_CHANGED_RGB, width=_scaled(3))

    legend_x = _MARGIN + grid_width + _GAP
    legend_y = top + _scaled(4)
    draw.text(
        (legend_x, legend_y),
        "Domain state",
        font=explain_font(_scaled(14)),
        fill=EXPLAIN_TEXT_RGB,
    )
    entries = [
        (_SINGLETON_RGB, "singleton / selected tile"),
        (EXPLAIN_UNRESOLVED_RGB, "multiple candidate tiles"),
        (_UNSAT_RGB, "empty domain / conflict"),
        (_CHANGED_RGB, "current event cell"),
    ]
    if propagation is not None:
        entries.extend(
            (
                (EXPLAIN_PROPAGATION_SOURCE_RGB, "derived support source"),
                (EXPLAIN_PROPAGATION_TARGET_RGB, "restricted target"),
            )
        )
    if restored:
        entries.append((EXPLAIN_RESTORED_RGB, "restored by rollback"))
    for offset, (color, label) in enumerate(entries, start=1):
        y = legend_y + offset * _scaled(24)
        draw.rectangle(
            (legend_x, y, legend_x + _scaled(18), y + _scaled(18)), fill=color
        )
        draw.text(
            (legend_x + _scaled(26), y + _scaled(2)),
            label,
            font=explain_font(_scaled(10)),
            fill=EXPLAIN_TEXT_RGB,
        )
    if mrv_candidates:
        y = legend_y + (len(entries) + 1) * _scaled(24)
        draw.rectangle(
            (legend_x, y, legend_x + _scaled(18), y + _scaled(18)),
            fill=EXPLAIN_SELECTED_MRV_RGB,
        )
        draw.text(
            (legend_x + _scaled(26), y + _scaled(2)),
            "minimum-domain candidate",
            font=explain_font(_scaled(10)),
            fill=EXPLAIN_TEXT_RGB,
        )
    if mrv_candidates:
        details = [
            "active: "
            f"{sum(region.active)} | fixed: "
            f"{fixed_count} | empty: {empty_count}",
            "minimum domain: "
            f"{minimum_domain_size}; tied candidates: {len(mrv_candidates)}",
            f"row-major winner: cell {min(mrv_candidates)}",
            f"selected cell: {event.cell}",
            "tie-break: lowest row-major cell",
        ]
    elif propagation is not None:
        source_cell, source_side, target_side, colors = propagation
        details = [
            f"phase: {event.phase or '-'}",
            f"source: cell {source_cell} {source_side}",
            f"target: cell {event.cell} {target_side}",
            "shared edge: " + ", ".join(map(str, colors)),
            "source derived from before-state",
        ]
    elif restored:
        details = [
            f"phase: {event.phase or '-'}",
            f"rollback depth: {event.depth}",
            f"trail mark: {event.change_mark}",
            f"restored changes: {len(restored)}",
            f"restored cells: {len(restored_cells)}",
        ]
    else:
        details = [
            f"phase: {event.phase or '-'}",
            f"reason: {event.reason or '-'}",
            f"change mark: {event.change_mark}",
            f"active: {sum(region.active)}",
            f"fixed: {fixed_count}",
            f"empty: {empty_count}",
        ]
    y = legend_y + _scaled(155 if mrv_candidates else 190 if len(entries) > 4 else 142)
    for line in details:
        draw.text(
            (legend_x, y),
            line,
            font=explain_font(_scaled(10)),
            fill=EXPLAIN_MUTED_RGB,
        )
        y += _scaled(15)
    summary_top = top + grid_height + _scaled(12)
    if mrv_candidates:
        summary_box = (
            _MARGIN,
            summary_top,
            width - _MARGIN - 1,
            height - _MARGIN - 1,
        )
        draw.rectangle(
            summary_box,
            fill=EXPLAIN_ACTIVE_RGB,
            outline=(178, 184, 194),
            width=_scaled(1),
        )
        summary_x = _MARGIN + _scaled(12)
        draw.text(
            (summary_x, summary_top + _scaled(10)),
            f"MRV: minimum domain {minimum_domain_size}",
            font=explain_font(_scaled(26)),
            fill=EXPLAIN_TEXT_RGB,
        )
        draw.text(
            (summary_x, summary_top + _scaled(42)),
            f"{len(mrv_candidates)} ties -> cell {min(mrv_candidates)} wins row-major",
            font=explain_font(_scaled(24)),
            fill=EXPLAIN_TEXT_RGB,
        )
        recorded_domain = _format_domain(
            event.new_domain or 0,
            len(bundle.explanation.tileset.tile_edges),
        )
        draw.text(
            (summary_x, summary_top + _scaled(72)),
            f"Recorded decision: cell {event.cell} -> {recorded_domain}",
            font=explain_font(_scaled(16)),
            fill=EXPLAIN_MUTED_RGB,
        )
        card_width = _scaled(75)
        card_height = _scaled(62)
        card_gap = _scaled(12)
        card_top = summary_top + _scaled(16)
        candidate_left = width - _MARGIN - 2 * card_width - card_gap
        winner_left = candidate_left + card_width + card_gap
        alternate = next(
            (candidate for candidate in mrv_candidates if candidate != event.cell),
            event.cell,
        )
        for left, color, title, cell in (
            (candidate_left, EXPLAIN_SELECTED_MRV_RGB, "tied", alternate),
            (winner_left, _CHANGED_RGB, "winner", event.cell),
        ):
            draw.rectangle(
                (left, card_top, left + card_width, card_top + card_height),
                fill=color,
                outline=EXPLAIN_TEXT_RGB,
                width=_scaled(1),
            )
            centered_text(
                draw,
                (
                    left,
                    card_top + _scaled(6),
                    left + card_width,
                    card_top + card_height,
                ),
                f"{title}\ncell {cell}\ndomain {minimum_domain_size}",
                font=explain_font(_scaled(12)),
            )
    elif propagation is not None:
        _draw_propagation_summary(
            draw,
            bundle,
            event,
            propagation,
            top=summary_top,
            width=width,
            height=height,
        )
    elif event.kind in {"conflict", "backtrack"}:
        _draw_search_summary(
            draw,
            bundle,
            event,
            event_index,
            restored,
            top=summary_top,
            width=width,
            height=height,
        )
    else:
        draw.text(
            (legend_x, height - _MARGIN - _scaled(15)),
            "Rendering is not a correctness proof.",
            font=explain_font(_scaled(9)),
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
        _compose_frame(
            bundle,
            bundle.trace.events[index],
            states[index - 1]
            if bundle.trace.events[index].kind == "decision" and index > 0
            else states[index],
            bundle.trace.initial_domains if index == 0 else states[index - 1],
            index,
        )
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
