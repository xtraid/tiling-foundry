from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw
import pytest

import wang_trace_render
from wang_explain import (
    EXPLAIN_DECISION_RGB,
    EXPLAIN_PROPAGATION_SOURCE_RGB,
    EXPLAIN_SELECTED_MRV_RGB,
    EXPLAIN_UNRESOLVED_RGB,
)
from wang_hex_port import WangSquareRenderError
from wang_trace import TraceEvent, TraceSnapshot, load_trace_bundle, replay_trace
from wang_trace_render import (
    _active_domain_counts,
    render_trace_assets,
    select_semantic_milestones,
)


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
FIXTURE_DIRECTORY = ROOT / "tests/fixtures/pipeline_sat_solver_trace"
MANIFEST = FIXTURE_DIRECTORY / "manifest.json"


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _rewrite_artifact(copied, manifest, name, document):
    encoded = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    digest = hashlib.sha256(encoded).hexdigest()
    artifact_name = f"{name}-{digest}.json"
    (copied / artifact_name).write_bytes(encoded)
    manifest["artifacts"][name]["path"] = artifact_name
    manifest["artifacts"][name]["sha256"] = digest
    return digest


def _small_trace():
    events = (
        TraceEvent(0, "root", "initial", None, 0, None, 0, None, None, None),
        TraceEvent(
            1,
            "domain_reduction",
            "initial",
            "propagation",
            0,
            0,
            1,
            (1 << 23) - 1,
            3,
            None,
        ),
        TraceEvent(2, "propagation", "initial", None, 0, None, 1, None, None, None),
        TraceEvent(3, "decision", "search", None, 1, 0, 1, 3, 1, None),
        TraceEvent(4, "domain_reduction", "search", "decision", 1, 0, 2, 3, 1, None),
        TraceEvent(5, "backtrack", "search", None, 0, 0, 1, None, None, None),
        TraceEvent(6, "result", None, None, 0, None, 1, None, None, "sat"),
    )
    return TraceSnapshot(
        solver="reference",
        status="sat",
        source_formula_sha256="1" * 64,
        region_sha256="2" * 64,
        solution_sha256="3" * 64,
        width=1,
        height=1,
        event_capacity=len(events),
        observed_event_count=len(events),
        truncated=False,
        checkpoint_interval=0,
        checkpoint_capacity=0,
        checkpoints_truncated=False,
        initial_domains=((1 << 23) - 1,),
        events=events,
        checkpoints=(),
    )


def _display_ink_height(image: Image.Image, box: tuple[int, int, int, int]) -> int:
    display_width = 390
    scale = display_width / image.width
    display = image.resize(
        (display_width, round(image.height * scale)), Image.Resampling.LANCZOS
    )
    display_box = tuple(round(coordinate * scale) for coordinate in box)
    crop = display.crop(display_box)
    ink_rows = [
        y
        for y in range(crop.height)
        if sum(
            max(crop.getpixel((x, y))) < 210 for x in range(crop.width)
        )
        >= 3
    ]
    runs: list[list[int]] = []
    for row in ink_rows:
        if not runs or row != runs[-1][-1] + 1:
            runs.append([row])
        else:
            runs[-1].append(row)
    return max((len(run) for run in runs), default=0)


def _search_story_panel(bundle, event_index, restored=()):
    events = (
        TraceEvent(0, "root", "initial", None, 0, None, 0, None, None, None),
        TraceEvent(1, "decision", "search", None, 2, 492, 3990, 9, 1, None),
        TraceEvent(2, "conflict", "search", None, 2, 614, 4114, None, None, None),
        TraceEvent(3, "backtrack", "search", None, 2, 492, 3990, None, None, None),
        TraceEvent(4, "decision", "search", None, 2, 492, 3990, 9, 8, None),
    )
    trace = replace(
        bundle.trace,
        events=events,
        event_capacity=len(events),
        observed_event_count=len(events),
    )
    story_bundle = replace(bundle, trace=trace)
    image = Image.new("RGB", (1976, 972), (255, 255, 255))
    draw_story = getattr(wang_trace_render, "_draw_search_summary", None)
    assert draw_story is not None
    draw_story(
        ImageDraw.Draw(image),
        story_bundle,
        events[event_index],
        event_index,
        restored,
        top=744,
        width=image.width,
        height=image.height,
    )
    return image


def test_loads_and_replays_hash_bound_trace_without_solver_imports():
    bundle = load_trace_bundle(MANIFEST)

    assert bundle.trace.solver == "reference"
    assert bundle.trace.status == "sat"
    assert bundle.trace.observed_event_count == 2896
    assert len(bundle.trace.events) == 2896
    assert len(bundle.trace.checkpoints) == 22
    assert bundle.solution is not None
    assert (bundle.trace.width, bundle.trace.height) == (41, 11)
    assert "z3" not in sys.modules
    assert not any(name.startswith("native") for name in sys.modules)


def test_one_composition_chain_is_byte_stable_for_png_sheet_and_gif(tmp_path):
    first = render_trace_assets(MANIFEST, tmp_path / "first", max_frames=10)
    second = render_trace_assets(MANIFEST, tmp_path / "second", max_frames=10)

    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert len(first.frames) == 10
    assert first.fallback.name == "frame-002517.png"
    assert first.animation.name == "trace.gif"
    assert first.contact_sheet.name == "contact-sheet.png"
    with Image.open(first.frames[0]) as frame:
        assert frame.mode == "RGB"
        assert frame.size == (1976, 828)
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 10


def test_presentazione_search_unsat_branch_replays_and_reexports_exactly(tmp_path):
    source = ROOT / "docs/assets/presentazione/search-unsat"
    manifest = source / "reference-manifest.json"
    bundle = load_trace_bundle(manifest)
    trace = bundle.trace
    states = replay_trace(trace)
    assert (trace.solver, trace.status, trace.observed_event_count) == ("reference", "unsat", 4370)
    assert not trace.truncated and bundle.solution is None
    assert trace.events[-1].kind == "result" and trace.events[-1].status == "unsat"

    # One depth-two frame tries 0, fails, restores its full entry state, then tries 3.
    first, rollback, following = (trace.events[i] for i in (3994, 4121, 4122))
    assert (first.kind, first.cell, first.depth, first.old_domain, first.new_domain) == (
        "decision", 492, 2, 9, 1
    )
    assert (rollback.kind, rollback.cell, rollback.depth) == ("backtrack", 492, 2)
    assert (following.kind, following.cell, following.depth, following.new_domain) == (
        "decision", 492, 2, 8
    )
    assert first.change_mark == rollback.change_mark == following.change_mark == 3990
    assert states[3993] == states[4121] == states[4122]
    assert [(states[i][492], states[i][614]) for i in (3993, 3995, 4120, 4121, 4123)] == [
        (9, 320), (1, 320), (1, 0), (9, 320), (8, 320)
    ]
    reductions = [event for event in trace.events[3995:4121] if event.kind == "domain_reduction"]
    assert len(reductions) == 124
    assert len({event.cell for event in reductions}) == 122
    assert trace.events[4120].change_mark == 4114

    # Existing max_frames selects these five; no custom selector or raster path.
    rendered = render_trace_assets(manifest, tmp_path / "rendered", max_frames=20)
    names = {frame.name for frame in rendered.frames}
    for sequence in (3995, 4118, 4120, 4121, 4122):
        name = f"frame-{sequence:06d}.png"
        assert name in names
        assert (tmp_path / "rendered" / name).read_bytes() == (source / name).read_bytes()


def test_observed_mrv_selection_is_row_major_and_deterministic(tmp_path):
    bundle = load_trace_bundle(MANIFEST)
    states = replay_trace(bundle.trace)
    decision_index, event = next(
        (index, event)
        for index, event in enumerate(bundle.trace.events)
        if event.kind == "decision" and event.phase == "search"
    )
    before = states[decision_index - 1]
    region = bundle.explanation.region
    minimum = min(
        domain.bit_count()
        for active, domain in zip(region.active, before, strict=True)
        if active and domain.bit_count() > 1
    )
    candidates = tuple(
        index
        for index, (active, domain) in enumerate(zip(region.active, before))
        if active and domain.bit_count() == minimum
    )

    assert event.cell == min(candidates)

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = render_trace_assets(MANIFEST, first_dir, max_frames=10)
    render_trace_assets(MANIFEST, second_dir, max_frames=10)

    assert _tree_bytes(first_dir) == _tree_bytes(second_dir)
    assert Image.open(first.fallback).size == (1976, 828)


def test_active_domain_counts_exclude_inactive_positions():
    bundle = load_trace_bundle(MANIFEST)
    states = replay_trace(bundle.trace)
    decision_index = next(
        index
        for index, event in enumerate(bundle.trace.events)
        if event.kind == "decision" and event.phase == "search"
    )
    assert _active_domain_counts(
        bundle.explanation.region.active, states[decision_index - 1]
    ) == (74, 0)


def test_mrv_legend_uses_the_unresolved_grid_color(tmp_path):
    rendered = render_trace_assets(MANIFEST, tmp_path / "rendered", max_frames=10)
    with Image.open(rendered.fallback) as fallback:
        assert fallback.getpixel((1548, 304)) == EXPLAIN_UNRESOLVED_RGB


def test_decision_fallback_has_large_focused_mrv_summary_cards(tmp_path):
    rendered = render_trace_assets(MANIFEST, tmp_path / "rendered", max_frames=10)
    with Image.open(rendered.fallback) as fallback:
        assert fallback.getpixel((1630, 660)) == EXPLAIN_SELECTED_MRV_RGB
        assert fallback.getpixel((1804, 660)) == EXPLAIN_DECISION_RGB


def test_sat_selection_keeps_a_decision_restriction_and_its_continuation():
    bundle = load_trace_bundle(MANIFEST)
    selected = select_semantic_milestones(bundle.trace.events, 10)
    # Hand-checked contiguous search events: select cell 0, restrict it,
    # then remove tile 8 from its neighbor cell 1.
    assert {2517, 2518, 2519, 2894, 2895} <= set(selected)
    assert selected == tuple(sorted(set(selected)))


def test_propagation_reason_uses_unique_shared_edge_in_observed_before_state():
    bundle = load_trace_bundle(MANIFEST)
    before = replay_trace(bundle.trace)[2518]
    reason = getattr(wang_trace_render, "_propagation_reason", None)
    assert reason is not None, "the observed reduction needs a derived edge reason"
    assert reason(bundle, bundle.trace.events[2519], before) == (0, "E", "W", (2,))


def test_propagation_frame_marks_the_uniquely_derived_source(tmp_path):
    rendered = render_trace_assets(MANIFEST, tmp_path / "rendered", max_frames=10)
    propagation = tmp_path / "rendered/frame-002519.png"
    assert propagation in rendered.frames
    with Image.open(propagation) as frame:
        assert frame.getpixel((30, 182)) == EXPLAIN_PROPAGATION_SOURCE_RGB


def test_trace_story_facts_remain_readable_at_390_px(tmp_path):
    bundle = load_trace_bundle(MANIFEST)
    rendered = render_trace_assets(MANIFEST, tmp_path / "rendered", max_frames=10)
    propagation = tmp_path / "rendered/frame-002519.png"
    assert propagation in rendered.frames
    with Image.open(propagation) as frame:
        assert _display_ink_height(frame, (52, 676, 1400, 734)) >= 8
        assert _display_ink_height(frame, (52, 726, 1400, 784)) >= 8

    conflict = _search_story_panel(bundle, 2)
    assert _display_ink_height(conflict, (52, 828, 1400, 900)) >= 8

    rollback = _search_story_panel(
        bundle,
        3,
        ((614, 0, 1 << 8), (614, 1 << 8, (1 << 6) | (1 << 8))),
    )
    assert _display_ink_height(rollback, (52, 820, 1400, 884)) >= 8
    assert _display_ink_height(rollback, (52, 880, 1400, 944)) >= 8


def test_ambiguous_propagation_source_is_not_presented_as_observed():
    bundle = load_trace_bundle(MANIFEST)
    before = list(replay_trace(bundle.trace)[2518])
    # Both west cell 0 and east cell 2 now independently imply {7,8}->{7}.
    before[2] = 128
    reason = getattr(wang_trace_render, "_propagation_reason", None)
    assert reason is not None, "ambiguous sources must remain unidentified"
    assert reason(bundle, bundle.trace.events[2519], tuple(before)) is None


def test_rollback_focus_restores_repeated_changes_in_reverse_trail_order():
    trace = _small_trace()
    events = trace.events[:5] + (
        TraceEvent(
            5, "domain_reduction", "search", "propagation", 1, 1, 3, 3, 2, None
        ),
        TraceEvent(
            6, "domain_reduction", "search", "propagation", 1, 1, 4, 2, 0, None
        ),
        TraceEvent(7, "conflict", "search", None, 1, 1, 4, None, None, None),
        TraceEvent(8, "backtrack", "search", None, 1, 0, 1, None, None, None),
        TraceEvent(9, "result", None, None, 0, 1, 1, None, None, "unsat"),
    )
    trace = replace(
        trace,
        width=2,
        initial_domains=((1 << 23) - 1, 3),
        events=events,
        status="unsat",
        solution_sha256=None,
        event_capacity=10,
        observed_event_count=10,
    )
    assert replay_trace(trace)[8] == (3, 3)
    restore = getattr(wang_trace_render, "_restored_changes", None)
    assert restore is not None, "rollback focus needs the reversed observed deltas"
    assert restore(events, 8) == ((1, 0, 2), (1, 2, 3), (0, 1, 3))


def test_tall_search_grid_retains_room_for_the_rollback_story():
    frame_height = getattr(wang_trace_render, "_frame_height", None)
    assert frame_height is not None, "tall traces need a visible story panel"
    assert frame_height(15 * 18 * 2) == 972


def test_rejects_hash_tampering_before_parsing_trace(tmp_path):
    copied = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    manifest = json.loads((copied / "manifest.json").read_text(encoding="utf-8"))
    trace_path = copied / manifest["artifacts"]["trace"]["path"]
    trace_path.write_bytes(trace_path.read_bytes() + b" ")

    with pytest.raises(WangSquareRenderError, match="sha256"):
        load_trace_bundle(copied / "manifest.json")


def test_rejects_semantic_delta_tampering_even_with_updated_hash(tmp_path):
    copied = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trace_path = copied / manifest["artifacts"]["trace"]["path"]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    event = next(
        item for item in trace["events"] if item["kind"] == "domain_reduction"
    )
    event["old_domain"] ^= 1
    encoded = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
    trace_path.write_bytes(encoded)
    manifest["artifacts"]["trace"]["sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="old_domain"):
        load_trace_bundle(manifest_path)


def test_replay_rejects_false_decisions_backtracks_and_cells():
    trace = _small_trace()
    assert replay_trace(trace)[-1] == (3,)

    events = list(trace.events)
    events[3] = replace(events[3], new_domain=2)
    with pytest.raises(WangSquareRenderError, match="following domain reduction"):
        replay_trace(replace(trace, events=tuple(events)))

    events = list(trace.events)
    events[5] = replace(events[5], change_mark=0)
    with pytest.raises(WangSquareRenderError, match="backtrack mark"):
        replay_trace(replace(trace, events=tuple(events)))

    for index in (3, 2):
        events = list(trace.events)
        events[index] = replace(events[index], cell=1)
        with pytest.raises(WangSquareRenderError, match="outside layout"):
            replay_trace(replace(trace, events=tuple(events)))


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("tile_table", "tile_table"),
        ("active", "active map"),
        ("boundary", "solution.*boundary"),
        ("bounds", "solution.*bounds"),
    ),
)
def test_rejects_solution_identity_drift(tmp_path, mutation, message):
    copied = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    solution_reference = manifest["artifacts"]["solution"]
    solution = json.loads(
        (copied / solution_reference["path"]).read_text(encoding="utf-8")
    )
    if mutation == "tile_table":
        for tile in solution["tile_table"]:
            for direction in ("N", "E", "S", "W"):
                tile["edges"][direction] += 100
        for sides in solution["boundary"]:
            if sides is None:
                continue
            for direction in ("N", "E", "S", "W"):
                if sides[direction] is not None:
                    sides[direction] += 100
    elif mutation == "active":
        index = next(
            index
            for index, tile_id in enumerate(solution["cells"])
            if tile_id is not None
        )
        solution["cells"][index] = None
        solution["boundary"][index] = None
    elif mutation == "boundary":
        sides = next(
            sides
            for sides in solution["boundary"]
            if sides is not None
            and any(value is not None for value in sides.values())
        )
        direction = next(
            direction
            for direction, value in sides.items()
            if value is not None
        )
        sides[direction] = None
    else:
        for coordinate in ("min_x_inclusive", "max_x_inclusive"):
            solution["bounds"][coordinate] += 1

    solution_digest = _rewrite_artifact(copied, manifest, "solution", solution)
    trace_reference = manifest["artifacts"]["trace"]
    trace = json.loads((copied / trace_reference["path"]).read_text(encoding="utf-8"))
    trace["solution_sha256"] = solution_digest
    _rewrite_artifact(copied, manifest, "trace", trace)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match=message):
        load_trace_bundle(manifest_path)


def test_rejects_inactive_cell_state_even_with_updated_hash(tmp_path):
    copied = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    region_path = copied / manifest["artifacts"]["region"]["path"]
    trace_path = copied / manifest["artifacts"]["trace"]["path"]
    region = json.loads(region_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    inactive = region["active"].index(False)
    trace["initial_domains"][inactive] = 1
    for checkpoint in trace["checkpoints"]:
        checkpoint["domains"][inactive] = 1
    encoded = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
    trace_path.write_bytes(encoded)
    manifest["artifacts"]["trace"]["sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="inactive cell"):
        load_trace_bundle(manifest_path)


def test_rejects_false_truncation_and_nonsemantic_event_fields(tmp_path):
    copied = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trace_path = copied / manifest["artifacts"]["trace"]["path"]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace["capacity"]["truncated"] = True
    encoded = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
    trace_path.write_bytes(encoded)
    manifest["artifacts"]["trace"]["sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="sequence gap"):
        load_trace_bundle(manifest_path)

    trace = json.loads(
        (FIXTURE_DIRECTORY / manifest["artifacts"]["trace"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    propagation = next(item for item in trace["events"] if item["kind"] == "propagation")
    propagation["reason"] = "decision"
    encoded = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
    trace_path.write_bytes(encoded)
    manifest["artifacts"]["trace"]["sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="reserved for reduction"):
        load_trace_bundle(manifest_path)


def test_cli_runs_in_isolated_renderer_process(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "wang_trace_render.py",
            str(MANIFEST),
            str(tmp_path / "rendered"),
            "--max-frames",
            "4",
        ],
        cwd=RENDERER,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "animation=" in completed.stdout
    assert (tmp_path / "rendered/trace.gif").is_file()
    assert (tmp_path / "rendered/contact-sheet.png").is_file()
