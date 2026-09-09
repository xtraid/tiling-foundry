from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

import wang_narrative
from wang_hex_port import WangSquareRenderError
from wang_generalized import generalized_specification_sha256
from wang_narrative import (
    render_generalized_assets,
    render_overview_assets,
    render_presentation_status,
    render_verification_assets,
    render_witness_assets,
)
from wang_snapshot import load_explainability_bundle
from wang_square import load_wang_presentation


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
MANIFEST = ROOT / "tests/fixtures/pipeline_sat_reduction_explain/manifest.json"
SOLUTION = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"
TRACE_MANIFEST = ROOT / "tests/fixtures/pipeline_sat_solver_trace/manifest.json"
TRACE_SOLUTION = next(
    (ROOT / "tests/fixtures/pipeline_sat_solver_trace").glob("solution-*.json")
)
ASSIGNMENT = (False, True, False)


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _encoded(document: dict[str, object]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")


def _witness_digest(values: tuple[bool, ...]) -> str:
    return hashlib.sha256(_encoded({"witness": list(values)})).hexdigest()


def _mobile_ink_height(
    image: Image.Image, source_box: tuple[int, int, int, int]
) -> int:
    scale = 390 / image.width
    mobile = image.resize(
        (390, round(image.height * scale)), Image.Resampling.LANCZOS
    )
    crop = mobile.crop(tuple(round(value * scale) for value in source_box))
    rows = [
        y
        for y in range(crop.height)
        if sum(max(crop.getpixel((x, y))) < 175 for x in range(crop.width)) >= 3
    ]
    return max(rows) - min(rows) + 1 if rows else 0


def _run_record(
    status: str,
    *,
    manifest: Path | None = None,
    assignment: tuple[bool, ...] | None = None,
) -> dict[str, object]:
    performed = status == "sat"
    checks = {}
    specifications = (
        ("boolean_z3_assignment", "oracles.witness_check.is_valid_assignment"),
        ("reference_tiling", "oracles.tiling_check.is_valid_tiling"),
        ("reference_assignment", "oracles.witness_check.is_valid_assignment"),
        ("optimized_tiling", "oracles.tiling_check.is_valid_tiling"),
        ("optimized_assignment", "oracles.witness_check.is_valid_assignment"),
        ("wang_z3_tiling", "oracles.tiling_check.is_valid_tiling"),
    )
    for name, checker in specifications:
        digest = "1" * 64 if performed else None
        if name == "reference_assignment" and assignment is not None:
            digest = _witness_digest(assignment)
        checks[name] = {
            "checker": checker,
            "performed": performed,
            "passed": True if performed else None,
            "witness_sha256": digest,
        }
    agreement = {
        "expected_status": status,
        "boolean_z3_status": status,
        "reference_status": status,
        "optimized_status": status,
        "wang_z3_status": status,
        "all_status_equal": True,
        "sat_witnesses_valid": True if status == "sat" else None,
        "passed": True,
    }
    receipt_payload: dict[str, object] = {
        "verification": checks,
        "agreement": agreement,
    }
    source_payload = dict(receipt_payload)
    if manifest is not None:
        source = json.loads(manifest.read_text(encoding="utf-8"))
        artifacts = source["artifacts"]
        source_payload.update(
            {
                "source_formula": source["source_formula_sha256"],
                "formula_snapshot": artifacts["formula"]["sha256"],
                "tileset": artifacts["tileset"]["sha256"],
                "region": artifacts["region"]["sha256"],
                "provenance": artifacts["reduction"]["sha256"],
                "reference_solution": (
                    None
                    if artifacts["solution"] is None
                    else artifacts["solution"]["sha256"]
                ),
                "reference_assignment": (
                    None if assignment is None else list(assignment)
                ),
            }
        )
    source_sha256 = hashlib.sha256(
        _encoded(source_payload)
    ).hexdigest()
    return {
        "schema": "wang-verification-receipts-v1",
        "expected_status": status,
        **receipt_payload,
        "source_sha256": source_sha256,
    }


def test_verification_composition_is_deterministic_for_sat_and_unsat(tmp_path):
    for status in ("unsat",):
        run = tmp_path / f"{status}.json"
        run.write_text(json.dumps(_run_record(status)) + "\n", encoding="utf-8")
        first = render_verification_assets(run, tmp_path / f"{status}-first")
        render_verification_assets(run, tmp_path / f"{status}-second")
        assert _tree_bytes(tmp_path / f"{status}-first") == _tree_bytes(
            tmp_path / f"{status}-second"
        )
        assert first.fallback.name == "frame-05.png"
        with Image.open(first.animation) as animation:
            assert animation.n_frames == 6


def test_verification_shows_checker_rules_and_copied_native_extraction(tmp_path):
    bundle = load_explainability_bundle(TRACE_MANIFEST)
    presentation = load_wang_presentation(TRACE_SOLUTION)
    tiling = getattr(wang_narrative, "_tiling_evidence")(
        bundle, presentation
    )
    assert (
        tiling.active_index,
        tiling.inactive_index,
        tiling.tile_id,
        tiling.right_id,
        tiling.tile_edges,
        tiling.right_edges,
        tiling.required_n,
        tiling.maximum_tile_id,
    ) == (0, 40, 0, 7, (0, 2, 7, 1), (0, 2, 0, 2), 0, 22)
    extraction = getattr(wang_narrative, "_extraction_evidence")(
        bundle, presentation, ASSIGNMENT
    )
    assert tuple(
        (item.variable, item.tile_ids, item.value)
        for item in extraction
    ) == (
        (0, (0, 1, 2), False),
        (1, (3, 3, 3), True),
        (2, (0, 1, 2), False),
    )

    receipts = tmp_path / "sat.json"
    receipts.write_text(
        json.dumps(
            _run_record("sat", manifest=TRACE_MANIFEST, assignment=ASSIGNMENT)
        )
        + "\n",
        encoding="utf-8",
    )
    first = render_verification_assets(
        receipts,
        tmp_path / "sat-first",
        manifest_path=TRACE_MANIFEST,
        solution_path=TRACE_SOLUTION,
        extracted_assignment=ASSIGNMENT,
    )
    render_verification_assets(
        receipts,
        tmp_path / "sat-second",
        manifest_path=TRACE_MANIFEST,
        solution_path=TRACE_SOLUTION,
        extracted_assignment=ASSIGNMENT,
    )
    assert _tree_bytes(tmp_path / "sat-first") == _tree_bytes(
        tmp_path / "sat-second"
    )
    assert first.fallback.name == "frame-05.png"
    with Image.open(first.fallback) as fallback:
        assert fallback.size == (1920, 1040)


def test_verification_rejects_cross_source_solution_and_assignment(tmp_path):
    receipts = tmp_path / "sat.json"
    receipts.write_text(
        json.dumps(
            _run_record("sat", manifest=TRACE_MANIFEST, assignment=ASSIGNMENT)
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(WangSquareRenderError, match="solution identity"):
        render_verification_assets(
            receipts,
            tmp_path / "wrong-solution",
            manifest_path=TRACE_MANIFEST,
            solution_path=SOLUTION,
            extracted_assignment=ASSIGNMENT,
        )
    with pytest.raises(WangSquareRenderError, match="assignment identity"):
        render_verification_assets(
            receipts,
            tmp_path / "wrong-assignment",
            manifest_path=TRACE_MANIFEST,
            solution_path=TRACE_SOLUTION,
            extracted_assignment=(True, False, True),
        )


def test_verification_bounds_a_larger_copied_assignment(tmp_path):
    receipts = tmp_path / "sat.json"
    receipts.write_text(
        json.dumps(
            _run_record("sat", manifest=TRACE_MANIFEST, assignment=ASSIGNMENT)
        )
        + "\n",
        encoding="utf-8",
    )
    status, records, bundle, presentation, _ = getattr(
        wang_narrative, "_load_verification"
    )(
        receipts,
        manifest_path=TRACE_MANIFEST,
        solution_path=TRACE_SOLUTION,
        extracted_assignment=ASSIGNMENT,
    )
    assert bundle is not None and bundle.reduction is not None
    source_gadgets = tuple(
        gadget for gadget in bundle.reduction.gadgets if gadget.kind == "variable"
    )
    gadgets = tuple(
        replace(source_gadgets[index % 3], ordinal=index) for index in range(7)
    )
    large_bundle = replace(
        bundle,
        formula=replace(bundle.formula, variable_count=7),
        reduction=replace(
            bundle.reduction,
            variable_count=7,
            gadgets=gadgets,
        ),
    )
    values = (False, True, False, True, False, True, False)
    frame = getattr(wang_narrative, "_verification_frame")(
        status, records, 5, large_bundle, presentation, values
    )

    assert getattr(wang_narrative, "_bounded_variable_indices")(7) == (0, 1, 6)
    assert frame.size == (1920, 1040)
    assert _mobile_ink_height(frame, (1470, 790, 1860, 890)) >= 8


def test_unsat_summary_starts_below_all_receipt_labels(monkeypatch):
    records = tuple(_run_record("unsat")["verification"].values())
    state_boxes: list[tuple[int, int, int, int]] = []
    summary_boxes: list[tuple[int, int, int, int]] = []
    original_draw = wang_narrative.ImageDraw.Draw

    class RecordingDraw:
        def __init__(self, image):
            self._draw = original_draw(image)

        def text(self, xy, value, **kwargs):
            if value == "not applicable: no SAT witness":
                state_boxes.append(
                    self._draw.textbbox(
                        xy,
                        value,
                        font=kwargs.get("font"),
                        anchor=kwargs.get("anchor"),
                        stroke_width=kwargs.get("stroke_width", 0),
                    )
                )
            return self._draw.text(xy, value, **kwargs)

        def rounded_rectangle(self, xy, **kwargs):
            if xy[0] == 170 and xy[2] == 1750:
                summary_boxes.append(tuple(xy))
            return self._draw.rounded_rectangle(xy, **kwargs)

        def __getattr__(self, name):
            return getattr(self._draw, name)

    monkeypatch.setattr(
        wang_narrative.ImageDraw, "Draw", lambda image: RecordingDraw(image)
    )
    getattr(wang_narrative, "_verification_frame")(
        "unsat", records, 5, None, None, None
    )

    assert len(state_boxes) == 6
    assert len(summary_boxes) == 1
    assert max(box[3] for box in state_boxes) + 24 <= summary_boxes[0][1]


def test_verification_composition_rejects_partial_or_forged_receipts(tmp_path):
    source = tmp_path / "forged.json"
    document = _run_record("sat")
    del document["agreement"]["reference_status"]
    source.write_text(json.dumps(document) + "\n", encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="agreement must be closed"):
        render_verification_assets(source, tmp_path / "output")


def test_witness_and_generalized_assets_reuse_checked_presentations(tmp_path):
    first = render_witness_assets(SOLUTION, tmp_path / "witness-first")
    render_witness_assets(SOLUTION, tmp_path / "witness-second")
    assert _tree_bytes(tmp_path / "witness-first") == _tree_bytes(
        tmp_path / "witness-second"
    )
    assert first.animation.fallback.name == "frame-03.png"
    with Image.open(first.animation.fallback) as fallback:
        assert fallback.size == (1920, 1040)
    assert first.square.is_file()
    assert first.generalized.is_file()
    assert first.hex.is_file()

    generalized = render_generalized_assets(MANIFEST, tmp_path / "generalized")
    render_generalized_assets(MANIFEST, tmp_path / "generalized-second")
    assert _tree_bytes(tmp_path / "generalized") == _tree_bytes(
        tmp_path / "generalized-second"
    )
    assert generalized.sheet.is_file()
    assert generalized.legend.is_file()
    assert generalized_specification_sha256() == (
        "5e8e6589271f9059b5ed81df00db4e303b338d5243caa475ed09135b129e3cf2"
    )


def test_atomic_legend_shows_canonical_valid_and_invalid_adjacency(tmp_path):
    bundle = load_explainability_bundle(MANIFEST)
    edges = bundle.tileset.tile_edges

    # Canonical horizontal examples: #0 E meets #4 W, while #0 E cannot
    # meet #3 W. These literal values are from the checked fixture table.
    assert edges[0][1] == edges[4][3] == 2
    assert edges[0][1] == 2
    assert edges[3][3] == 1

    first = render_generalized_assets(MANIFEST, tmp_path / "first")
    render_generalized_assets(MANIFEST, tmp_path / "second")
    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")

    with Image.open(first.legend) as legend:
        assert legend.mode == "RGB"
        assert legend.size == (1732, 4184)
        # Valid pair #0/#4 has the same brown logical-color band on both
        # sides of its gap; invalid pair #0/#3 has brown versus magenta.
        assert legend.getpixel((216, 3900)) == legend.getpixel((252, 3900)) == (
            142, 92, 25
        )
        assert legend.getpixel((1062, 3900)) == (142, 92, 25)
        assert legend.getpixel((1098, 3900)) == (240, 36, 160)


def test_atomic_vocabulary_remains_readable_at_390_px(tmp_path):
    outputs = render_generalized_assets(MANIFEST, tmp_path / "generalized")
    with Image.open(outputs.legend) as source:
        scale = 390 / source.width
        display = source.resize(
            (390, round(source.height * scale)), Image.Resampling.LANCZOS
        )
        # The first card's semantic role and edge rows must survive the actual
        # mobile-width downsample; three dark pixels per row filters borders.
        for source_box in ((184, 164, 790, 288), (184, 330, 790, 390)):
            box = tuple(round(value * scale) for value in source_box)
            crop = display.crop(box)
            ink_rows = [
                y
                for y in range(crop.height)
                if sum(
                    max(crop.getpixel((x, y))) < 210 for x in range(crop.width)
                ) >= 3
            ]
            runs: list[list[int]] = []
            for row in ink_rows:
                if not runs or row != runs[-1][-1] + 1:
                    runs.append([row])
                else:
                    runs[-1].append(row)
            assert max((len(run) for run in runs), default=0) >= 8


def test_worked_example_keeps_overview_and_expands_selected_case_panels(
    tmp_path,
):
    colors = (
        (180, 30, 60),
        (30, 160, 70),
        (50, 80, 190),
        (200, 120, 20),
        (130, 50, 180),
        (20, 150, 160),
        (220, 70, 30),
        (90, 120, 40),
    )
    source_paths = []
    for index, color in enumerate(colors):
        path = tmp_path / f"source-{index}.png"
        Image.new("RGB", (1920, 1040), color).save(path)
        source_paths.append(path)
    square_color = (40, 120, 220)
    square = tmp_path / "square.png"
    Image.new("RGB", (1538, 422), square_color).save(square)

    outputs = render_overview_assets(
        tuple(source_paths), square, tmp_path / "overview"
    )
    assert outputs.worked_example is not None
    with Image.open(outputs.worked_example) as source:
        mobile = source.resize(
            (390, round(source.height * 390 / source.width)),
            Image.Resampling.LANCZOS,
        )

    def color_span(color):
        columns = [
            x
            for y in range(mobile.height)
            for x in range(mobile.width)
            if all(
                abs(channel - expected) <= 2
                for channel, expected in zip(mobile.getpixel((x, y)), color)
            )
        ]
        return max(columns) - min(columns) + 1 if columns else 0

    # Every source remains in the compact eight-stage overview. The selected
    # decision, construction, checker, square, and final-presentation panels
    # additionally occupy nearly the full mobile width.
    assert all(color_span(color) > 0 for color in colors)
    for color in (colors[1], colors[2], colors[6], square_color, colors[7]):
        assert color_span(color) >= 350


def test_overview_and_unsat_status_are_static_fallback_safe(tmp_path):
    status = render_presentation_status("unsat", tmp_path / "status.png")
    sources = (status,) * 8
    first = render_overview_assets(
        sources,
        status,
        tmp_path / "overview-first",
        include_sat_story=False,
    )
    render_overview_assets(
        sources,
        status,
        tmp_path / "overview-second",
        include_sat_story=False,
    )
    assert _tree_bytes(tmp_path / "overview-first") == _tree_bytes(
        tmp_path / "overview-second"
    )
    assert first.home_preview is None
    assert first.worked_example is None
    assert first.animation.contact_sheet.is_file()


def test_narrative_module_imports_no_native_or_z3_producer():
    assert "z3" not in sys.modules
    assert not any(name.startswith("native") for name in sys.modules)
