from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path
import re

from PIL import Image, ImageDraw

import wang_algorithm_animation
from wang_algorithm_animation import (
    main,
    render_builder_assets,
    render_hex_assets,
    render_optimized_assets,
)
from wang_snapshot import load_explainability_bundle


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
BUILDER_MANIFEST = (
    ROOT / "tests/fixtures/pipeline_sat_reduction_explain/manifest.json"
)
SQUARE_SOLUTION = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"
GOLDENS = ROOT / "docs/assets/narrative"
PRIVATE_GOLDENS = RENDERER / "test_data"


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _assert_stable_assets(
    first_directory: Path,
    second_directory: Path,
    golden_directory: Path,
    *,
    frame_count: int,
    fallback_name: str,
) -> None:
    assert _tree_bytes(first_directory) == _tree_bytes(second_directory)
    assert _tree_bytes(first_directory) == _tree_bytes(golden_directory)
    with Image.open(first_directory / "trace.gif") as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == frame_count
    assert (first_directory / fallback_name).is_file()


def test_builder_animation_uses_versioned_provenance_and_is_byte_stable(tmp_path):
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    reduction = bundle.reduction
    assert reduction is not None
    assert tuple(signal.token_id for signal in reduction.source_signals) == (
        0, 1, 2, 9, 3, 4, 5, 10, 6, 7, 8
    )
    assert tuple(signal.token_id for signal in reduction.target_signals) == (
        0, 1, 3, 9, 2, 4, 6, 10, 5, 7, 8
    )
    crossovers = tuple(
        gadget for gadget in reduction.gadgets if gadget.kind == "crossover"
    )
    assert tuple(gadget.swap_row for gadget in crossovers) == (3, 2, 3, 7, 6, 7)
    assert tuple((gadget.x_begin, gadget.x_end) for gadget in crossovers) == (
        (3, 7), (7, 10), (10, 14), (14, 22), (22, 29), (29, 37)
    )

    replay_orders = getattr(wang_algorithm_animation, "_replay_signal_orders", None)
    assert replay_orders is not None
    assert tuple(
        signal.token_id for signal in replay_orders(reduction)[1]
    ) == (0, 1, 2, 3, 9, 4, 5, 10, 6, 7, 8)

    first = render_builder_assets(BUILDER_MANIFEST, tmp_path / "first")
    render_builder_assets(BUILDER_MANIFEST, tmp_path / "second")

    assert first.fallback.name == "frame-05.png"
    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 6
    with Image.open(first.fallback) as fallback:
        assert fallback.size == (1976, 828)

    frame = getattr(wang_algorithm_animation, "_builder_frame")
    source_changed = replace(
        bundle,
        reduction=replace(
            reduction,
            source_signals=tuple(reversed(reduction.source_signals)),
        ),
    )
    target_changed = replace(
        bundle,
        reduction=replace(
            reduction,
            target_signals=tuple(reversed(reduction.target_signals)),
        ),
    )
    crossover_changed = replace(
        bundle,
        reduction=replace(
            reduction,
            gadgets=tuple(
                replace(gadget, swap_row=4)
                if gadget is crossovers[0]
                else gadget
                for gadget in reduction.gadgets
            ),
        ),
    )
    assert frame(bundle, 0).tobytes() != frame(source_changed, 0).tobytes()
    assert frame(bundle, 1).tobytes() != frame(target_changed, 1).tobytes()
    assert frame(bundle, 2).tobytes() != frame(crossover_changed, 2).tobytes()


def _dense_builder_layout():
    """Layout-only fixture with the 23 spans from the new 144x11 SAT capture."""
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    reduction = bundle.reduction
    crossover = next(g for g in reduction.gadgets if g.kind == "crossover")
    edges = (3, 7, 10, 12, 13, 21, 28, 34, 39, 43, 46, 48,
             53, 57, 66, 74, 81, 87, 94, 103, 111, 121, 130, 140)
    rows = (3, 2, 1, 0, 7, 6, 5, 4, 3, 2, 1, 4, 3, 8, 7, 6, 5, 6, 8, 7, 9, 8, 9)
    gadgets = tuple(g for g in reduction.gadgets if g.kind in {"variable", "left_forward"})
    gadgets += tuple(
        replace(crossover, ordinal=i, x_begin=edges[i], x_end=edges[i + 1], swap_row=row)
        for i, row in enumerate(rows)
    )
    region = replace(
        bundle.region, max_x=143, active=(True,) * (144 * 11),
        boundary=((None, None, None, None),) * (144 * 11),
    )
    return replace(bundle, region=region, reduction=replace(reduction, width=144, gadgets=gadgets))


def _record_builder_text(monkeypatch):
    records = []
    original = ImageDraw.ImageDraw.text

    def draw_and_record(draw, xy, text, *args, **kwargs):
        bbox = draw.multiline_textbbox(
            xy, text, font=kwargs.get("font"),
            stroke_width=kwargs.get("stroke_width", 0),
            spacing=kwargs.get("spacing", 4),
        )
        records.append((text, bbox))
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", draw_and_record)
    return records


def test_builder_overflowing_swap_list_reports_count_and_omission_inside_panel(monkeypatch):
    records = _record_builder_text(monkeypatch)
    frame = wang_algorithm_animation._builder_frame(_dense_builder_layout(), 0)
    evidence, bbox = next(
        (text, bbox) for text, bbox in records
        if text.startswith("source signals:") and "adjacent swaps:" in text
    )
    assert bbox[2] <= frame.width - 36
    assert "adjacent swaps: 23" in evidence
    assert "omitted" in evidence


def test_builder_crowded_overview_has_no_colliding_labels_and_keeps_single_swap(monkeypatch):
    records = _record_builder_text(monkeypatch)
    bundle = _dense_builder_layout()
    wang_algorithm_animation._builder_frame(bundle, 3)
    boxes = [bbox for text, bbox in records if re.fullmatch(r"X\d+:s\d+", text)]
    assert all(left[2] <= right[0] for left, right in zip(boxes, boxes[1:]))
    assert any("23 crossover labels omitted" in text for text, _ in records)
    assert any("23 validated adjacent swaps" in text for text, _ in records)
    records.clear()
    wang_algorithm_animation._builder_frame(bundle, 2)
    assert any(text == "X0: swap rows 3/4" for text, _ in records)


def test_builder_fitting_frames_keep_canonical_png_bytes():
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    for stage in range(6):
        frame = wang_algorithm_animation._builder_frame(bundle, stage)
        encoded = io.BytesIO()
        frame.save(encoded, format="PNG", optimize=False, compress_level=9)
        assert encoded.getvalue() == (
            GOLDENS / "region-construction" / f"frame-{stage:02d}.png"
        ).read_bytes()


def test_builder_final_panel_distinguishes_region_and_boundary_states():
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    frame = getattr(wang_algorithm_animation, "_builder_frame")(bundle, 5)
    assert frame.size == (1976, 828)

    # Hand-checked fixture cells: (1, 1) is active with internal edges,
    # (40, 0) is inactive, and the north side of (0, 0) exposes color 0.
    grid_x, grid_y, cell = 36, 348, 30
    assert frame.getpixel((grid_x + cell + 15, grid_y + cell + 15)) == (
        238, 241, 246
    )
    assert frame.getpixel((grid_x + 40 * cell + 10, grid_y + 15)) in {
        (226, 230, 236),
        (190, 197, 207),
    }
    assert frame.getpixel((grid_x + 15, grid_y + 2)) == (81, 237, 39)
    assert frame.getpixel((grid_x + 2 * cell - 1, grid_y + cell + 15)) == (
        174, 181, 193
    )


def test_builder_handles_a_valid_reduction_that_needs_no_crossover():
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    reduction = bundle.reduction
    assert reduction is not None
    no_swap_bundle = replace(
        bundle,
        reduction=replace(
            reduction,
            target_signals=reduction.source_signals,
            gadgets=tuple(
                gadget
                for gadget in reduction.gadgets
                if gadget.kind != "crossover"
            ),
        ),
    )
    frame = getattr(wang_algorithm_animation, "_builder_frame")

    assert frame(no_swap_bundle, 2).size == (1976, 828)
    assert frame(no_swap_bundle, 3).size == (1976, 828)


def test_builder_preserves_noncanonical_region_capture_scope():
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    wide_region = replace(
        bundle.region,
        max_x=399,
        max_y=0,
        active=(False,) * 400,
        boundary=(None,) * 400,
    )
    wide_bundle = replace(bundle, region=wide_region)

    assert getattr(wang_algorithm_animation, "_builder_frame")(
        wide_bundle, 5
    ).size == (1976, 828)


def test_builder_fits_all_labels_at_the_fifteen_signal_boundary(monkeypatch):
    from wang_trace import load_trace_bundle

    bundle = load_trace_bundle(
        ROOT / "docs/assets/presentazione/search-unsat/reference-manifest.json"
    )
    signals = bundle.explanation.reduction.source_signals
    assert len(signals) == 15
    labels = []
    original_centered_text = wang_algorithm_animation.centered_text

    def check_label(draw, box, text, **kwargs):
        bounds = draw.textbbox((0, 0), text, font=kwargs["font"])
        assert bounds[2] - bounds[0] <= box[2] - box[0], text
        assert bounds[3] - bounds[1] <= box[3] - box[1], text
        labels.append(text)
        return original_centered_text(draw, box, text, **kwargs)

    monkeypatch.setattr(wang_algorithm_animation, "centered_text", check_label)
    image = Image.new("RGB", (1976, 828), "white")
    wang_algorithm_animation._draw_signal_order(
        ImageDraw.Draw(image), y=140, label="source", signals=signals
    )
    assert len(labels) == 15
    assert {"r #12", "r #13", "r #14"}.issubset(labels)


def test_builder_summarizes_a_valid_44_variable_signal_strip():
    bundle = load_explainability_bundle(BUILDER_MANIFEST)
    reduction = bundle.reduction
    assert reduction is not None
    variable = next(
        signal for signal in reduction.source_signals if signal.kind == "variable"
    )
    redundant = next(
        signal for signal in reduction.source_signals if signal.kind == "redundant"
    )
    signals_list = []
    for variable_id in range(44):
        for occurrence in range(3):
            signals_list.append(
                replace(
                    variable,
                    row=len(signals_list),
                    token_id=3 * variable_id + occurrence,
                    variable=variable_id,
                    occurrence=occurrence,
                )
            )
        if variable_id < 43:
            signals_list.append(
                replace(
                    redundant,
                    row=len(signals_list),
                    token_id=132 + variable_id,
                    variable=None,
                    occurrence=None,
                )
            )
    signals = tuple(signals_list)
    assert len(signals) == 4 * 44 - 1
    strip_items = getattr(wang_algorithm_animation, "_signal_strip_items")
    items = strip_items(signals, (86, 87))

    shown_rows = tuple(row for row, signal, _ in items if signal is not None)
    assert shown_rows == (0, 1, 2, 85, 86, 87, 88, 172, 173, 174)
    assert sum(omitted for _, _, omitted in items) == 165
    assert tuple(
        signal.token_id
        for row, signal, _ in items
        if row in {86, 87}
    ) == (65, 153)

    image = Image.new("RGB", (1976, 828), "white")
    getattr(wang_algorithm_animation, "_draw_signal_order")(
        ImageDraw.Draw(image),
        y=140,
        label="source",
        signals=signals,
        highlighted_rows=(86, 87),
    )
    assert image.size == (1976, 828)
    box_width, gap = 134, 10
    for position in range(len(items) - 1):
        gap_x = 220 + position * (box_width + gap) + box_width + gap // 2
        assert all(
            max(image.getpixel((gap_x, pixel_y))) >= 180
            for pixel_y in range(148, 191)
        )

    display = image.resize((390, 164), Image.Resampling.LANCZOS)
    display_scale = 390 / image.width
    for position in range(len(items) - 1):
        gap_x = round(
            (220 + position * (box_width + gap) + box_width + gap // 2)
            * display_scale
        )
        assert all(
            max(display.getpixel((gap_x, pixel_y))) >= 180
            for pixel_y in range(round(148 * display_scale), round(191 * display_scale))
        )


def test_optimized_didactic_animation_is_byte_stable(tmp_path):
    mechanisms = getattr(wang_algorithm_animation, "_load_optimizations")()
    assert tuple(mechanism.identifier for mechanism in mechanisms) == (
        "dynamic-dfs-stack",
        "initial-trail-omission",
        "sat-ownership-transfer",
        "byte-support-table",
        "queue-deduplication",
        "lazy-mrv-index",
    )

    first = render_optimized_assets(tmp_path / "first")
    render_optimized_assets(tmp_path / "second")

    assert first.fallback.name == "frame-06.png"
    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert tuple(path.name for path in first.frames) == tuple(
        f"frame-{index:02d}.png" for index in range(7)
    )
    assert len({path.read_bytes() for path in first.frames}) == 7
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 7
    with Image.open(first.fallback) as fallback:
        assert fallback.size == (1920, 1040)
    with Image.open(first.contact_sheet) as contact_sheet:
        assert contact_sheet.size == (5760, 3120)


def test_byte_support_panel_aggregates_three_bytes_of_a_23_bit_domain():
    example = getattr(wang_algorithm_animation, "_byte_support_example")()

    assert example == {
        "domain": 0x400401,
        "chunks": (0x01, 0x04, 0x40),
        "source_tiles": (0, 10, 22),
        "source_east_edges": (2, 3, 3),
        "supported_tiles": (
            4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 16, 17, 18, 19, 20, 21, 22
        ),
    }


def test_essential_byte_support_and_mrv_labels_survive_mobile_downsampling():
    frame = getattr(wang_algorithm_animation, "_optimized_frame")

    def mobile_ink_height(image: Image.Image, source_box: tuple[int, int, int, int]) -> int:
        scale = 390 / image.width
        preview = image.resize(
            (390, round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
        box = tuple(round(value * scale) for value in source_box)
        crop = preview.crop(box)
        ink_rows = [
            y
            for y in range(crop.height)
            if any(max(crop.getpixel((x, y))) < 140 for x in range(crop.width))
        ]
        return max(ink_rows) - min(ink_rows) + 1 if ink_rows else 0

    byte_support = frame(3)
    assert mobile_ink_height(byte_support, (65, 315, 390, 380)) >= 7
    assert mobile_ink_height(byte_support, (65, 375, 430, 445)) >= 7
    assert mobile_ink_height(byte_support, (65, 435, 370, 495)) >= 7

    lazy_mrv = frame(5)
    assert mobile_ink_height(lazy_mrv, (60, 430, 220, 520)) >= 7
    assert mobile_ink_height(lazy_mrv, (50, 600, 160, 670)) >= 7
    assert mobile_ink_height(lazy_mrv, (40, 900, 1850, 955)) >= 7

    summary = getattr(wang_algorithm_animation, "_optimized_summary")()
    assert mobile_ink_height(summary, (65, 155, 560, 220)) >= 8
    assert mobile_ink_height(summary, (650, 245, 915, 325)) >= 7

    trail = frame(1)
    arrow_corridor = trail.crop((535, 295, 588, 400))
    assert not any(
        max(arrow_corridor.getpixel((x, y))) < 140
        for y in range(arrow_corridor.height)
        for x in range(arrow_corridor.width)
    )

    bucket_row = lazy_mrv.crop((48, 755, 620, 815))
    assert (111, 82, 176) not in bucket_row.get_flattened_data()

    ownership = frame(2)
    for corridor in (
        (60, 275, 99, 365),
        (170, 665, 204, 765),
        (696, 665, 730, 765),
        (1010, 275, 1049, 365),
        (1120, 665, 1154, 765),
        (1646, 665, 1680, 765),
    ):
        outside_box = ownership.crop(corridor)
        assert not any(
            max(outside_box.getpixel((x, y))) < 140
            for y in range(outside_box.height)
            for x in range(outside_box.width)
        )


def test_static_summary_names_the_omitted_initial_undo_entry_positively(monkeypatch):
    labels: list[str] = []
    original_centered_text = wang_algorithm_animation.centered_text

    def record_centered_text(draw, box, text, **kwargs):
        labels.append(text)
        return original_centered_text(draw, box, text, **kwargs)

    monkeypatch.setattr(wang_algorithm_animation, "centered_text", record_centered_text)

    summary = getattr(wang_algorithm_animation, "_optimized_summary")()

    assert "initial undo entry" in (label.replace("\n", " ") for label in labels)
    assert "no undo entry" not in labels
    mobile = summary.resize((390, round(summary.height * 390 / summary.width)), Image.Resampling.LANCZOS)
    label_box = mobile.crop(tuple(round(value * 390 / summary.width) for value in (1604, 248, 1774, 328)))
    ink_rows = [
        y
        for y in range(label_box.height)
        if any(max(label_box.getpixel((x, y))) < 140 for x in range(label_box.width))
    ]
    assert max(ink_rows) - min(ink_rows) + 1 >= 12


def test_static_summary_support_union_stays_out_of_incoming_arrow():
    summary = getattr(wang_algorithm_animation, "_optimized_summary")()

    for width in (1920, 390, 720):
        scale = width / summary.width
        preview = summary.resize(
            (width, round(summary.height * scale)),
            Image.Resampling.LANCZOS,
        )
        arrow_only_corridor = preview.crop(
            tuple(round(value * scale) for value in (1374, 515, 1519, 595))
        )
        assert not any(
            max(arrow_only_corridor.getpixel((x, y))) < 140
            for y in range(arrow_only_corridor.height)
            for x in range(arrow_only_corridor.width)
        )


def test_optimized_ownership_outcome_clears_panel_bottom_border():
    ownership = getattr(wang_algorithm_animation, "_optimized_frame")(2)

    for width in (1920, 390, 720):
        scale = width / ownership.width
        preview = ownership.resize(
            (width, round(ownership.height * scale)),
            Image.Resampling.LANCZOS,
        )
        bottom_safety_band = preview.crop(
            tuple(round(value * scale) for value in (1001, 890, 1872, 910))
        )
        assert not any(
            max(bottom_safety_band.getpixel((x, y))) < 140
            for y in range(bottom_safety_band.height)
            for x in range(bottom_safety_band.width)
        )


def test_queue_panel_suppresses_only_while_a_cell_is_pending():
    assert getattr(wang_algorithm_animation, "_queue_dedup_steps")() == (
        ("enqueue c7", "append", (7,)),
        ("enqueue c7 again", "suppress", (7,)),
        ("dequeue c7", "clear pending", ()),
        ("enqueue c7 later", "append", (7,)),
    )


def test_lazy_mrv_panel_moves_a_domain_bucket_and_reverses_it_on_rollback():
    steps = getattr(wang_algorithm_animation, "_mrv_bucket_steps")()

    assert steps == (
        (
            "after lazy build",
            ((2, 4), (5, 2), (9, 3)),
            ((2, (5,)), (3, (9,)), (4, (2,))),
            5,
        ),
        (
            "restrict c2: 4 -> 2",
            ((2, 2), (5, 2), (9, 3)),
            ((2, (2, 5)), (3, (9,))),
            2,
        ),
        (
            "rollback c2: 2 -> 4",
            ((2, 4), (5, 2), (9, 3)),
            ((2, (5,)), (3, (9,)), (4, (2,))),
            5,
        ),
    )


def test_hex_animation_checks_the_pure_port_and_is_byte_stable(tmp_path):
    first = render_hex_assets(SQUARE_SOLUTION, tmp_path / "first")
    render_hex_assets(SQUARE_SOLUTION, tmp_path / "second")

    assert first.fallback.name == "frame-02.png"
    _assert_stable_assets(
        tmp_path / "first",
        tmp_path / "second",
        PRIVATE_GOLDENS / "square-to-hex-animation",
        frame_count=4,
        fallback_name="frame-02.png",
    )


def test_cli_reports_animation_and_fallback(tmp_path, capsys):
    assert main(["optimized", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"animation={tmp_path / 'trace.gif'}",
        f"fallback={tmp_path / 'frame-06.png'}",
    ]
