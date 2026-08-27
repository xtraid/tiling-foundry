from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image
import pytest

from wang_hex_port import WangSquareRenderError
from wang_trace import load_trace_bundle
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
