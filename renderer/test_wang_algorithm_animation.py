from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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


def test_optimized_didactic_animation_is_byte_stable(tmp_path):
    first = render_optimized_assets(tmp_path / "first")
    render_optimized_assets(tmp_path / "second")

    assert first.fallback.name == "frame-06.png"
    _assert_stable_assets(
        tmp_path / "first",
        tmp_path / "second",
        GOLDENS / "optimized-mechanisms",
        frame_count=7,
        fallback_name="frame-06.png",
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
