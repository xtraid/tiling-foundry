from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import shutil
import sys

from PIL import Image
import pytest

import wang_z3_summary
from wang_hex_port import WangSquareRenderError
from wang_z3_summary import (
    load_z3_encoding_summary,
    render_boolean_z3_assets,
    render_wang_z3_assets,
)
from wang_snapshot import load_explainability_bundle


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
FIXTURES = ROOT / "tests/fixtures/pipeline_sat_z3"
GOLDENS = ROOT / "docs/assets/narrative"
MANIFEST = ROOT / "tests/fixtures/pipeline_sat_reduction_explain/manifest.json"


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


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


def test_wang_encoding_uses_real_cell_term_tuple_boundary_and_model(tmp_path):
    source = FIXTURES / "wang-z3.json"
    summary = load_z3_encoding_summary(source)
    bundle = load_explainability_bundle(MANIFEST)

    assert getattr(wang_z3_summary, "_wang_example_lines")(summary, bundle) == (
        "active cell (0,0) -> returned tile #0",
        "canonical tile #0 = (N=0, E=2, S=7, W=1)",
        "shared term edge(0,0,E) = edge(1,0,W) = 2",
        "exposed edge(0,0,N) = required boundary N=0",
    )

    frame = getattr(wang_z3_summary, "_compose_wang_frame")(summary, bundle, 4)
    changed_tile = replace(
        bundle,
        tileset=replace(
            bundle.tileset,
            tile_edges=((0, 2, 9, 1), *bundle.tileset.tile_edges[1:]),
        ),
    )
    assert frame.tobytes() != getattr(wang_z3_summary, "_compose_wang_frame")(
        summary, changed_tile, 4
    ).tobytes()

    first = render_wang_z3_assets(source, MANIFEST, tmp_path / "first")
    render_wang_z3_assets(source, MANIFEST, tmp_path / "second")

    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert first.fallback.name == "frame-04.png"
    with Image.open(first.fallback) as fallback:
        assert fallback.size == (1880, 1040)
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 5


def test_boolean_encoding_uses_source_occurrences_and_copied_assignment(tmp_path):
    source = FIXTURES / "boolean-z3.json"
    summary = load_z3_encoding_summary(source)
    bundle = load_explainability_bundle(MANIFEST)
    assert getattr(wang_z3_summary, "_boolean_clause_lines")(bundle) == (
        ("c0 source positions: x0, x0, x1", "If(x0) + If(x0) + If(x1) = 1"),
        ("c1 source positions: x0, x1, x2", "If(x0) + If(x1) + If(x2) = 1"),
        ("c2 source positions: x1, x2, x2", "If(x1) + If(x2) + If(x2) = 1"),
    )

    frame = getattr(wang_z3_summary, "_compose_boolean_frame")(summary, bundle, 3)
    changed_formula = replace(
        bundle,
        formula=replace(
            bundle.formula,
            clauses=((0, 1, 0), *bundle.formula.clauses[1:]),
        ),
    )
    changed_summary = replace(summary, assignment=(True, False, True))
    assert frame.tobytes() != getattr(wang_z3_summary, "_compose_boolean_frame")(
        summary, changed_formula, 3
    ).tobytes()
    assert frame.tobytes() != getattr(wang_z3_summary, "_compose_boolean_frame")(
        changed_summary, bundle, 3
    ).tobytes()

    first = render_boolean_z3_assets(source, MANIFEST, tmp_path / "first")
    render_boolean_z3_assets(source, MANIFEST, tmp_path / "second")

    assert _tree_bytes(tmp_path / "first") == _tree_bytes(tmp_path / "second")
    assert first.fallback.name == "frame-03.png"
    with Image.open(first.fallback) as fallback:
        assert fallback.size == (1880, 1040)
    with Image.open(first.animation) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 4


def test_oracle_fallback_core_labels_remain_readable_at_390_px():
    bundle = load_explainability_bundle(MANIFEST)
    boolean = load_z3_encoding_summary(FIXTURES / "boolean-z3.json")
    wang = load_z3_encoding_summary(FIXTURES / "wang-z3.json")
    boolean_frame = getattr(wang_z3_summary, "_compose_boolean_frame")(
        boolean, bundle, 3
    )
    wang_frame = getattr(wang_z3_summary, "_compose_wang_frame")(
        wang, bundle, 4
    )

    assert _mobile_ink_height(boolean_frame, (1040, 350, 1800, 430)) >= 8
    assert _mobile_ink_height(boolean_frame, (340, 884, 1540, 940)) >= 8
    assert _mobile_ink_height(wang_frame, (70, 770, 850, 850)) >= 8
    assert _mobile_ink_height(wang_frame, (990, 735, 1770, 860)) >= 9


def test_boolean_fallback_bounds_a_large_source_formula():
    bundle = load_explainability_bundle(MANIFEST)
    clauses = tuple((variable, variable, variable) for variable in range(44))
    large_bundle = replace(
        bundle,
        formula=replace(bundle.formula, variable_count=44, clauses=clauses),
    )
    summary = replace(
        load_z3_encoding_summary(FIXTURES / "boolean-z3.json"),
        variable_count=44,
        assertion_count=44,
        assignment=(False,) * 44,
    )
    frame = getattr(wang_z3_summary, "_compose_boolean_frame")(
        summary, large_bundle, 3
    )
    changed_last = replace(
        large_bundle,
        formula=replace(
            large_bundle.formula,
            clauses=(*clauses[:-1], (43, 42, 43)),
        ),
    )

    assert frame.size == (1880, 1040)
    assert frame.tobytes() != getattr(wang_z3_summary, "_compose_boolean_frame")(
        summary, changed_last, 3
    ).tobytes()
    changed_assignment = replace(
        summary,
        assignment=(*summary.assignment[:-1], True),
    )
    assert frame.tobytes() != getattr(wang_z3_summary, "_compose_boolean_frame")(
        changed_assignment, large_bundle, 3
    ).tobytes()


def test_oracle_composition_rejects_cross_source_substitution(tmp_path):
    source = FIXTURES / "boolean-z3.json"
    copied = tmp_path / "bundle"
    shutil.copytree(MANIFEST.parent, copied)
    path = copied / "manifest.json"
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["source_formula_sha256"] = "0" * 64
    path.write_text(json.dumps(forged) + "\n", encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="source_formula_sha256"):
        render_boolean_z3_assets(source, path, tmp_path / "output")


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
