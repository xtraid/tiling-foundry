"""Tests for static snapshots and opt-in explainability raster modes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
import pytest

import wang_square
import wang_snapshot
from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_OUTLINE_RGB,
    draw_boundary_side,
    hex_explain_tile,
    square_explain_tile,
    square_region_tile,
)
from wang_hex_port import WangSquareRenderError
from wang_snapshot import (
    FORMULA_SCHEMA,
    MANIFEST_SCHEMA,
    REDUCTION_MANIFEST_SCHEMA,
    REDUCTION_SCHEMA,
    REGION_SCHEMA,
    TILESET_SCHEMA,
    load_explainability_bundle,
    render_pipeline_snapshot,
)
from wang_square import (
    _build_palette_from_edges,
    _hex_vertices,
    render_wang_square,
)


RENDERER_DIR = Path(__file__).resolve().parent
ROOT = RENDERER_DIR.parent
SOLUTION = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"
SNAPSHOT_DIRECTORY = ROOT / "tests/fixtures/pipeline_sat_explain"
MANIFEST = SNAPSHOT_DIRECTORY / "manifest.json"
REDUCTION_SNAPSHOT_DIRECTORY = (
    ROOT / "tests/fixtures/pipeline_sat_reduction_explain"
)
REDUCTION_MANIFEST = REDUCTION_SNAPSHOT_DIRECTORY / "manifest.json"
TRACE_MANIFEST = ROOT / "tests/fixtures/pipeline_sat_solver_trace/manifest.json"
REDUCTION_GOLDEN = RENDERER_DIR / "test_data/pipeline_sat_reduction.png"
GOLDENS = {
    ("formula", False): RENDERER_DIR / "test_data/pipeline_sat_formula.png",
    ("tileset", False): RENDERER_DIR / "test_data/pipeline_sat_tileset_square.png",
    ("tileset", True): RENDERER_DIR / "test_data/pipeline_sat_tileset_hex.png",
    ("region", False): RENDERER_DIR / "test_data/pipeline_sat_region_square.png",
    ("region", True): RENDERER_DIR / "test_data/pipeline_sat_region_hex.png",
}
SOLUTION_GOLDENS = {
    False: RENDERER_DIR / "test_data/wang_solution_v1_square_explain.png",
    True: RENDERER_DIR / "test_data/wang_solution_v1_hex_explain.png",
}


def test_loads_hash_bound_bundle_without_native_or_solver_imports():
    bundle = load_explainability_bundle(MANIFEST)

    assert bundle.formula.source_name == "pipeline_sat.cm13"
    assert bundle.formula.variable_count == 3
    assert bundle.formula.clauses == ((0, 0, 1), (0, 1, 2), (1, 2, 2))
    assert len(bundle.tileset.tile_edges) == 23
    assert bundle.tileset.colors == tuple(range(16))
    assert (bundle.region.width, bundle.region.height) == (41, 11)
    assert sum(bundle.region.active) == 444
    assert bundle.region.active.count(False) == 7
    assert "z3" not in sys.modules
    assert "native._lib" not in sys.modules


def test_versioned_fixture_manifest_references_expected_closed_contracts():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema"] == MANIFEST_SCHEMA
    assert manifest["stage"] == "region"
    assert manifest["artifacts"]["formula"]["schema"] == FORMULA_SCHEMA
    assert manifest["artifacts"]["tileset"]["schema"] == TILESET_SCHEMA
    assert manifest["artifacts"]["region"]["schema"] == REGION_SCHEMA
    for reference in manifest["artifacts"].values():
        encoded = (SNAPSHOT_DIRECTORY / reference["path"]).read_bytes()
        assert hashlib.sha256(encoded).hexdigest() == reference["sha256"]


def test_loads_native_reduction_provenance_without_native_imports():
    bundle = load_explainability_bundle(REDUCTION_MANIFEST)

    assert bundle.reduction is not None
    assert bundle.reduction.variable_count == 3
    assert (bundle.reduction.width, bundle.reduction.height) == (41, 11)
    assert tuple(
        signal.token_id for signal in bundle.reduction.source_signals
    ) == (0, 1, 2, 9, 3, 4, 5, 10, 6, 7, 8)
    assert tuple(
        gadget.swap_row
        for gadget in bundle.reduction.gadgets
        if gadget.kind == "crossover"
    ) == (3, 2, 3, 7, 6, 7)
    assert "native._lib" not in sys.modules


def test_v2_manifest_references_the_closed_reduction_contract():
    manifest = json.loads(REDUCTION_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema"] == REDUCTION_MANIFEST_SCHEMA
    assert manifest["stage"] == "reduction"
    assert manifest["artifacts"]["reduction"]["schema"] == REDUCTION_SCHEMA
    for reference in manifest["artifacts"].values():
        encoded = (REDUCTION_SNAPSHOT_DIRECTORY / reference["path"]).read_bytes()
        assert hashlib.sha256(encoded).hexdigest() == reference["sha256"]


@pytest.mark.parametrize("view", ["tileset", "region"])
def test_hex_snapshot_views_require_the_independent_port_checker(
    tmp_path,
    monkeypatch,
    view,
):
    def reject_port(_square, _candidate):
        raise WangSquareRenderError("independent checker rejected candidate")

    monkeypatch.setattr(wang_snapshot, "check_square_to_hex", reject_port)

    with pytest.raises(
        WangSquareRenderError,
        match="independent checker rejected candidate",
    ):
        render_pipeline_snapshot(
            MANIFEST,
            tmp_path / f"{view}.png",
            view=view,
            hex_mode=True,
        )


def test_square_explain_asset_puts_each_logical_color_on_its_edge():
    edges = (10, 20, 30, 40)
    palette = _build_palette_from_edges((edges,))
    asset = np.asarray(
        square_explain_tile(
            edges,
            palette,
            64,
            tile_id=3,
            edge_labels=False,
        )
    )

    assert tuple(asset[1, 32]) == palette[10]
    assert tuple(asset[32, 62]) == palette[20]
    assert tuple(asset[62, 32]) == palette[30]
    assert tuple(asset[32, 1]) == palette[40]


def test_hex_explain_asset_puts_eswwnwne_colors_on_sides():
    edges = (10, 20, 30, 40, 50, 60)
    palette = _build_palette_from_edges((edges,))
    radius = 32
    vertices = _hex_vertices(radius, radius // 2)
    asset = np.asarray(
        hex_explain_tile(
            edges,
            palette,
            radius,
            vertices,
            tile_id=4,
            edge_labels=False,
        )
    )
    midpoints = tuple(
        (
            (vertices[(direction + 1) % 6][0] + vertices[(direction + 2) % 6][0])
            // 2,
            (vertices[(direction + 1) % 6][1] + vertices[(direction + 2) % 6][1])
            // 2,
        )
        for direction in range(6)
    )

    for direction, (x, y) in enumerate(midpoints):
        assert tuple(asset[y, x]) == palette[edges[direction]]


def test_unassigned_region_asset_colors_only_constrained_edges():
    palette = _build_palette_from_edges(((10, 20, 30, 40),))
    asset = np.asarray(
        square_region_tile(32, (10, None, 30, None), palette)
    )

    assert tuple(asset[1, 16]) == palette[10]
    assert tuple(asset[30, 16]) == palette[30]
    assert tuple(asset[16, 16]) == EXPLAIN_ACTIVE_RGB


def test_boundary_emphasis_keeps_a_colored_core_and_dark_backing():
    image = Image.new("RGB", (24, 24), (255, 255, 255))
    color = (10, 80, 190)
    draw_boundary_side(
        ImageDraw.Draw(image),
        (3, 12),
        (20, 12),
        color,
        width=2,
    )
    pixels = np.asarray(image)

    assert tuple(pixels[12, 12]) == color
    assert tuple(pixels[10, 12]) == EXPLAIN_OUTLINE_RGB


@pytest.mark.parametrize(("view", "hex_mode"), GOLDENS)
def test_snapshot_views_match_pixel_stable_goldens(tmp_path, view, hex_mode):
    output = tmp_path / "render.png"

    render_pipeline_snapshot(
        MANIFEST,
        output,
        view=view,
        hex_mode=hex_mode,
    )

    assert output.read_bytes() == GOLDENS[(view, hex_mode)].read_bytes()


def test_reduction_view_matches_native_provenance_golden(tmp_path):
    output = tmp_path / "reduction.png"

    render_pipeline_snapshot(
        REDUCTION_MANIFEST,
        output,
        view="reduction",
    )

    assert output.read_bytes() == REDUCTION_GOLDEN.read_bytes()
    with Image.open(output) as image:
        assert image.mode == "RGB"


@pytest.mark.parametrize(
    ("view", "golden"),
    (
        ("formula", GOLDENS[("formula", False)]),
        ("region", GOLDENS[("region", False)]),
        ("reduction", REDUCTION_GOLDEN),
    ),
)
def test_v3_trace_manifest_reuses_static_snapshot_views(tmp_path, view, golden):
    output = tmp_path / f"{view}.png"

    render_pipeline_snapshot(TRACE_MANIFEST, output, view=view)

    assert output.read_bytes() == golden.read_bytes()
    assert "native._lib" not in sys.modules


def test_v3_static_projection_does_not_import_or_replay_trace_consumer():
    sys.modules.pop("wang_trace", None)

    bundle = load_explainability_bundle(TRACE_MANIFEST)

    assert bundle.reduction is not None
    assert "wang_trace" not in sys.modules


@pytest.mark.parametrize("hex_mode", (False, True))
def test_solution_explain_views_match_separate_goldens(tmp_path, hex_mode):
    output = tmp_path / "render.png"

    render_wang_square(SOLUTION, output, explain=True, hex_mode=hex_mode)

    assert output.read_bytes() == SOLUTION_GOLDENS[hex_mode].read_bytes()
    with Image.open(output) as image:
        assert image.mode == "RGB"


def test_default_solution_paths_remain_byte_identical_to_legacy_goldens(tmp_path):
    expected = {
        False: RENDERER_DIR / "test_data/wang_solution_v1_square_sat.png",
        True: RENDERER_DIR / "test_data/wang_solution_v1_hex_sat.png",
    }
    for hex_mode in (False, True):
        output = tmp_path / f"render-{hex_mode}.png"
        render_wang_square(SOLUTION, output, hex_mode=hex_mode)
        assert output.read_bytes() == expected[hex_mode].read_bytes()


def test_manifest_hash_failure_preserves_existing_output(tmp_path):
    copied = tmp_path / "bundle"
    shutil.copytree(SNAPSHOT_DIRECTORY, copied)
    manifest = copied / "manifest.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    formula = copied / document["artifacts"]["formula"]["path"]
    formula.write_bytes(formula.read_bytes() + b" ")
    output = tmp_path / "render.png"
    output.write_bytes(b"previous output")

    with pytest.raises(WangSquareRenderError, match="does not match"):
        render_pipeline_snapshot(manifest, output, view="formula")

    assert output.read_bytes() == b"previous output"
    assert not list(tmp_path.glob(".render.png.*.png"))


def test_manifest_rejects_parent_path_and_duplicate_json_members(tmp_path):
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["artifacts"]["formula"]["path"] = "../formula.json"
    traversal = tmp_path / "traversal.json"
    traversal.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="artifact basename"):
        load_explainability_bundle(traversal)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema":"wang-explain-manifest-v1","schema":"duplicate"}',
        encoding="utf-8",
    )
    with pytest.raises(WangSquareRenderError, match="duplicate member"):
        load_explainability_bundle(duplicate)


def test_formula_view_rejects_hex_and_unknown_snapshot_view(tmp_path):
    with pytest.raises(WangSquareRenderError, match="not meaningful"):
        render_pipeline_snapshot(
            MANIFEST,
            tmp_path / "formula.png",
            view="formula",
            hex_mode=True,
        )
    with pytest.raises(WangSquareRenderError, match="must be one of"):
        render_pipeline_snapshot(
            MANIFEST,
            tmp_path / "unknown.png",
            view="unknown",
        )


def test_reduction_view_requires_v2_and_rejects_hex(tmp_path):
    with pytest.raises(WangSquareRenderError, match="requires a.*v2"):
        render_pipeline_snapshot(
            MANIFEST,
            tmp_path / "reduction.png",
            view="reduction",
        )
    with pytest.raises(WangSquareRenderError, match="not meaningful"):
        render_pipeline_snapshot(
            REDUCTION_MANIFEST,
            tmp_path / "reduction-hex.png",
            view="reduction",
            hex_mode=True,
        )


def test_cli_dispatches_snapshot_view_and_explain_solution(tmp_path):
    snapshot_output = tmp_path / "snapshot.png"
    wang_square.main(
        [str(MANIFEST), str(snapshot_output), "--view", "tileset", "--hex"]
    )
    assert snapshot_output.read_bytes() == GOLDENS[("tileset", True)].read_bytes()

    solution_output = tmp_path / "solution.png"
    wang_square.main([str(SOLUTION), str(solution_output), "--explain"])
    assert solution_output.read_bytes() == SOLUTION_GOLDENS[False].read_bytes()

    reduction_output = tmp_path / "reduction.png"
    wang_square.main(
        [str(REDUCTION_MANIFEST), str(reduction_output), "--view", "reduction"]
    )
    assert reduction_output.read_bytes() == REDUCTION_GOLDEN.read_bytes()


def test_snapshot_consumer_imports_in_isolated_renderer_process():
    script = f"""
import importlib.util
import sys
from pathlib import Path

renderer = Path({str(RENDERER_DIR)!r})
sys.path.insert(0, str(renderer))
module_path = renderer / 'wang_snapshot.py'
spec = importlib.util.spec_from_file_location('isolated_wang_snapshot', module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
bundle = module.load_explainability_bundle(Path({str(MANIFEST)!r}))
assert len(bundle.tileset.tile_edges) == 23
assert 'z3' not in sys.modules
assert 'native._lib' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        cwd=RENDERER_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
