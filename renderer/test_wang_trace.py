from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image
import pytest

from wang_hex_port import WangSquareRenderError
from wang_trace import TraceEvent, TraceSnapshot, load_trace_bundle, replay_trace
from wang_trace_render import render_trace_assets


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
FIXTURE_DIRECTORY = ROOT / "tests/fixtures/pipeline_sat_solver_trace"
MANIFEST = FIXTURE_DIRECTORY / "manifest.json"
GOLDENS = ROOT / "docs/assets/images/solver-trace"


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
    first = render_trace_assets(MANIFEST, tmp_path / "first", max_frames=8)
    second = render_trace_assets(MANIFEST, tmp_path / "second", max_frames=8)

    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert _tree_bytes(tmp_path / "first") == _tree_bytes(GOLDENS)
    assert len(first.frames) == 8
    assert first.fallback.name == "frame-002517.png"
    assert first.animation.name == "trace.gif"
    assert first.contact_sheet.name == "contact-sheet.png"
    with Image.open(first.frames[0]) as frame:
        assert frame.mode == "RGB"
        assert frame.size == (988, 414)
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 8


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
