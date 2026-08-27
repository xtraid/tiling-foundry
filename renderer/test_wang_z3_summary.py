from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image
import pytest

from wang_hex_port import WangSquareRenderError
from wang_z3_summary import load_z3_encoding_summary, render_wang_z3_assets


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
FIXTURES = ROOT / "tests/fixtures/pipeline_sat_z3"
GOLDENS = ROOT / "docs/assets/images/z3-encoding"


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_loads_both_closed_summaries_without_z3_or_native_imports():
    boolean = load_z3_encoding_summary(FIXTURES / "boolean-z3.json")
    wang = load_z3_encoding_summary(FIXTURES / "wang-z3.json")

    assert boolean.engine == "boolean-z3"
    assert boolean.assignment == (False, True, False)
    assert wang.engine == "wang-z3"
    assert (wang.width, wang.height) == (41, 11)
    assert wang.edge_term_count == 944
    assert wang.shared_internal_edge_count == 832
    assert wang.cells is not None and len(wang.cells) == 451
    assert "z3" not in sys.modules
    assert not any(name.startswith("native") for name in sys.modules)


def test_encoding_order_animation_is_byte_stable_and_matches_goldens(tmp_path):
    source = FIXTURES / "wang-z3.json"
    first = render_wang_z3_assets(source, tmp_path / "first")
    render_wang_z3_assets(source, tmp_path / "second")

    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert _tree_bytes(tmp_path / "first") == _tree_bytes(GOLDENS)
    assert first.fallback.name == "frame-03.png"
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 5


def test_rejects_unknown_fields_and_cross_engine_region_identity(tmp_path):
    source = json.loads(
        (FIXTURES / "boolean-z3.json").read_text(encoding="utf-8")
    )
    source["debug_order"] = []
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="unknown fields"):
        load_z3_encoding_summary(path)

    del source["debug_order"]
    source["region_sha256"] = "0" * 64
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="region_sha256"):
        load_z3_encoding_summary(path)


def test_rejects_inconsistent_wang_model_and_statistics(tmp_path):
    source = json.loads((FIXTURES / "wang-z3.json").read_text(encoding="utf-8"))
    active_index = next(
        index
        for index, tile_id in enumerate(source["model"]["cells"])
        if tile_id is not None
    )
    source["model"]["cells"][active_index] = source["encoding"][
        "unique_tile_tuple_count"
    ]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="canonical tile table"):
        load_z3_encoding_summary(path)

    source = json.loads((FIXTURES / "wang-z3.json").read_text(encoding="utf-8"))
    source["statistics"][1]["value"] += 1
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="project-owned counters"):
        load_z3_encoding_summary(path)
