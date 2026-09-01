"""Tests for exact 14-to-23 generalized Wang presentation."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

import wang_square
from wang_generalized import (
    CANONICAL_ATOMIC_TILE_EDGES,
    COLOR_NAMES,
    GENERALIZED_TILES,
    GeneralizedInstance,
    GeneralizedTileError,
    check_canonical_atomic_tileset,
    check_generalized_instances,
    recognize_generalized_tiles,
)
from wang_generalized_render import render_generalized_view
from wang_hex_port import WangSquareRenderError
from wang_snapshot import load_explainability_bundle
from wang_square import load_wang_presentation, render_wang_square


RENDERER_DIR = Path(__file__).resolve().parent
ROOT = RENDERER_DIR.parent
MANIFEST = ROOT / "tests/fixtures/pipeline_sat_explain/manifest.json"
SOLUTION = (
    ROOT
    / "tests/fixtures/pipeline_sat_solver_trace"
    / "solution-2273f58cda026dca73c0dfa25c960e01296ac1e34ae6accbddf5be29034d156a.json"
)
GOLDENS = {
    "generalized-sheet": RENDERER_DIR
    / "test_data/pipeline_sat_generalized_sheet.png",
    "atomic-legend": RENDERER_DIR
    / "test_data/pipeline_sat_atomic_semantic_legend.png",
    "generalized-overlay": RENDERER_DIR
    / "test_data/pipeline_sat_generalized_overlay.png",
}


def _recognize(cells, *, width=1, height=None):
    if height is None:
        height = len(cells) // width
    return recognize_generalized_tiles(
        CANONICAL_ATOMIC_TILE_EDGES,
        tuple(cells),
        min_x=0,
        min_y=0,
        max_x=width - 1,
        max_y=height - 1,
    )


def test_fixed_generalized_table_partitions_all_23_atomic_ids_exactly():
    assert len(GENERALIZED_TILES) == 14
    assert len(CANONICAL_ATOMIC_TILE_EDGES) == 23
    assert COLOR_NAMES == (
        "b",
        "v",
        "0",
        "1",
        "0-prime",
        "l",
        "r",
        "V0:a",
        "V0:b",
        "C1",
        "R0",
        "R1",
        "X00",
        "X01",
        "X10",
        "X11",
    )
    parts = [part.tile_id for tile in GENERALIZED_TILES for part in tile.parts]
    assert sorted(parts) == list(range(23))
    assert len(parts) == len(set(parts))

    by_name = {tile.name: tile for tile in GENERALIZED_TILES}
    assert tuple(part.tile_id for part in by_name["R0"].parts) == (11, 12)
    assert tuple((part.dx, part.dy) for part in by_name["R0"].parts) == (
        (0, 0),
        (1, 0),
    )
    assert tuple(part.tile_id for part in by_name["R1"].parts) == (13, 14)

    expected = (
        ("V0", ((0, 0, 0, "top"), (1, 0, 1, "middle"), (2, 0, 2, "bottom"))),
        ("V1", ((3, 0, 0, "copy"),)),
        ("C0", ((4, 0, 0, "single"),)),
        ("C1", ((5, 0, 0, "top"), (6, 0, 1, "bottom"))),
        ("F0", ((7, 0, 0, "single"),)),
        ("F1", ((8, 0, 0, "single"),)),
        ("L0", ((9, 0, 0, "single"),)),
        ("L1", ((10, 0, 0, "single"),)),
        ("R0", ((11, 0, 0, "left"), (12, 1, 0, "right"))),
        ("R1", ((13, 0, 0, "left"), (14, 1, 0, "right"))),
        ("X00", ((15, 0, 0, "top"), (16, 0, 1, "bottom"))),
        ("X01", ((17, 0, 0, "top"), (18, 0, 1, "bottom"))),
        ("X10", ((19, 0, 0, "top"), (20, 0, 1, "bottom"))),
        ("X11", ((21, 0, 0, "top"), (22, 0, 1, "bottom"))),
    )
    actual = tuple(
        (
            tile.name,
            tuple(
                (part.tile_id, part.dx, part.dy, part.label)
                for part in tile.parts
            ),
        )
        for tile in GENERALIZED_TILES
    )
    assert actual == expected

    for tile in GENERALIZED_TILES:
        cells = [None] * (tile.width * tile.height)
        for part in tile.parts:
            cells[part.dy * tile.width + part.dx] = part.tile_id
        assert _recognize(cells, width=tile.width, height=tile.height) == (
            GeneralizedInstance(tile.name, 0, 0),
        )


def test_recognizer_checks_composition_not_wang_solution_correctness():
    # F0 east is 0 while F1 west is 1.  Grouping remains presentation-only;
    # verification of adjacency and boundary is an upstream precondition.
    assert _recognize((7, 8), width=2) == (
        GeneralizedInstance("F0", 0, 0),
        GeneralizedInstance("F1", 1, 0),
    )


def test_guard_accepts_only_the_exact_canonical_positional_table():
    bundle = load_explainability_bundle(MANIFEST)
    check_canonical_atomic_tileset(bundle.tileset.tile_edges)
    assert bundle.tileset.tile_edges == CANONICAL_ATOMIC_TILE_EDGES

    reordered = list(CANONICAL_ATOMIC_TILE_EDGES)
    reordered[11], reordered[12] = reordered[12], reordered[11]
    with pytest.raises(GeneralizedTileError, match="atomic tile 11"):
        check_canonical_atomic_tileset(tuple(reordered))

    reoriented = list(CANONICAL_ATOMIC_TILE_EDGES)
    north, east, south, west = reoriented[13]
    reoriented[13] = (west, north, east, south)
    with pytest.raises(GeneralizedTileError, match="N/E/S/W orientation"):
        check_canonical_atomic_tileset(tuple(reoriented))


def test_canonical_witness_has_one_exact_nonoverlapping_partition():
    presentation = load_wang_presentation(SOLUTION)
    instances = recognize_generalized_tiles(
        presentation.tile_edges,
        presentation.cells,
        min_x=presentation.min_x,
        min_y=presentation.min_y,
        max_x=presentation.max_x,
        max_y=presentation.max_y,
    )

    assert len(instances) == 403
    assert Counter(instance.kind for instance in instances) == {
        "V0": 2,
        "V1": 3,
        "C0": 3,
        "C1": 3,
        "F0": 241,
        "F1": 91,
        "L0": 20,
        "L1": 6,
        "R0": 20,
        "R1": 8,
        "X00": 2,
        "X01": 2,
        "X10": 2,
    }
    check_generalized_instances(
        presentation.tile_edges,
        presentation.cells,
        min_x=presentation.min_x,
        min_y=presentation.min_y,
        max_x=presentation.max_x,
        max_y=presentation.max_y,
        instances=instances,
    )


def test_three_stacked_atomic_tile_3_cells_remain_three_v1_occurrences():
    presentation = load_wang_presentation(SOLUTION)
    instances = recognize_generalized_tiles(
        presentation.tile_edges,
        presentation.cells,
        min_x=presentation.min_x,
        min_y=presentation.min_y,
        max_x=presentation.max_x,
        max_y=presentation.max_y,
    )

    assert [
        (instance.origin_x, instance.origin_y)
        for instance in instances
        if instance.kind == "V1"
    ] == [(0, 4), (0, 5), (0, 6)]


@pytest.mark.parametrize(
    ("cells", "width", "message"),
    (
        ((0, 1, None), 1, "incomplete or misoriented V0"),
        ((2, 1, 0), 1, "incomplete or misoriented V0"),
        ((11, None, 12), 3, "incomplete or misoriented R0"),
        ((12, 11), 2, "incomplete or misoriented R0"),
    ),
)
def test_recognition_rejects_missing_parts_wrong_order_and_orientation(
    cells, width, message
):
    with pytest.raises(GeneralizedTileError, match=message):
        _recognize(cells, width=width)


def test_explicit_partition_checker_rejects_overlap_and_uncovered_cells():
    duplicate = (
        GeneralizedInstance("F0", 0, 0),
        GeneralizedInstance("F0", 0, 0),
    )
    with pytest.raises(GeneralizedTileError, match=r"overlap at \(0,0\)"):
        check_generalized_instances(
            CANONICAL_ATOMIC_TILE_EDGES,
            (7,),
            min_x=0,
            min_y=0,
            max_x=0,
            max_y=0,
            instances=duplicate,
        )

    with pytest.raises(GeneralizedTileError, match="uncovered"):
        check_generalized_instances(
            CANONICAL_ATOMIC_TILE_EDGES,
            (7,),
            min_x=0,
            min_y=0,
            max_x=0,
            max_y=0,
            instances=(),
        )


@pytest.mark.parametrize("view", GOLDENS)
def test_generalized_views_match_separate_pixel_stable_goldens(tmp_path, view):
    source = SOLUTION if view == "generalized-overlay" else MANIFEST
    output = tmp_path / f"{view}.png"

    render_generalized_view(source, output, view=view)

    assert output.read_bytes() == GOLDENS[view].read_bytes()
    with Image.open(output) as image:
        assert image.mode == "RGB"


def test_cli_dispatches_all_three_generalized_views(tmp_path):
    for view in GOLDENS:
        source = SOLUTION if view == "generalized-overlay" else MANIFEST
        output = tmp_path / f"{view}.png"
        wang_square.main([str(source), str(output), "--view", view])
        assert output.read_bytes() == GOLDENS[view].read_bytes()


@pytest.mark.parametrize("view", GOLDENS)
def test_generalized_views_are_square_only(tmp_path, view):
    source = SOLUTION if view == "generalized-overlay" else MANIFEST
    with pytest.raises(WangSquareRenderError, match="not meaningful"):
        render_generalized_view(
            source,
            tmp_path / "output.png",
            view=view,
            hex_mode=True,
        )


def test_invalid_atomic_table_preserves_existing_overlay_output(tmp_path):
    document = json.loads(SOLUTION.read_text(encoding="utf-8"))
    document["tile_table"][11]["edges"], document["tile_table"][12]["edges"] = (
        document["tile_table"][12]["edges"],
        document["tile_table"][11]["edges"],
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "overlay.png"
    output.write_bytes(b"previous output")

    with pytest.raises(WangSquareRenderError, match="atomic tile 11"):
        render_generalized_view(invalid, output, view="generalized-overlay")

    assert output.read_bytes() == b"previous output"
    assert not list(tmp_path.glob(".overlay.png.*.png"))


def test_existing_square_and_hex_outputs_remain_byte_identical(tmp_path):
    expected = {
        False: RENDERER_DIR / "test_data/wang_solution_v1_square_sat.png",
        True: RENDERER_DIR / "test_data/wang_solution_v1_hex_sat.png",
    }
    legacy_solution = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"
    for hex_mode in (False, True):
        output = tmp_path / f"legacy-{hex_mode}.png"
        render_wang_square(legacy_solution, output, hex_mode=hex_mode)
        assert output.read_bytes() == expected[hex_mode].read_bytes()


def test_pure_semantic_module_imports_no_raster_or_project_code():
    script = f"""
import importlib.util
from pathlib import Path
import sys
module_path = Path({str(RENDERER_DIR / 'wang_generalized.py')!r})
spec = importlib.util.spec_from_file_location('isolated_wang_generalized', module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert len(module.GENERALIZED_TILES) == 14
for forbidden in ('numpy', 'PIL', 'z3', 'formats', 'model', 'native'):
    assert forbidden not in sys.modules, forbidden
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        cwd=RENDERER_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_generalized_overlay_consumer_loads_no_solver_z3_or_libwang(tmp_path):
    output = tmp_path / "overlay.png"
    script = f"""
from pathlib import Path
import sys
sys.path.insert(0, {str(RENDERER_DIR)!r})
from wang_generalized_render import render_generalized_view
render_generalized_view(
    Path({str(SOLUTION)!r}),
    Path({str(output)!r}),
    view='generalized-overlay',
)
for forbidden in ('z3', 'formats', 'model', 'native'):
    assert forbidden not in sys.modules, forbidden
maps = Path('/proc/self/maps').read_text(encoding='utf-8')
assert 'libwang.so' not in maps
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        cwd=RENDERER_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert output.exists()
