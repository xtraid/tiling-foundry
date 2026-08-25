"""Tests for the pure square-to-hex port and explicit hex raster mode."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

import wang_square
from wang_hex_port import (
    WangHexPort,
    WangPresentation,
    WangSquareRenderError,
    check_square_to_hex,
    reduce_square_to_hex,
)
from wang_square import (
    BACKGROUND_RGB,
    GRID_RGB,
    HOLE_DARK_RGB,
    HOLE_LIGHT_RGB,
    build_palette,
    load_wang_presentation,
    render_wang_square,
)


RENDERER_DIR = Path(__file__).resolve().parent
ROOT_DIR = RENDERER_DIR.parent
FIXTURE = ROOT_DIR / "tests/fixtures/wang_solution_v1_square_sat.json"
SQUARE_GOLDEN = RENDERER_DIR / "test_data/wang_solution_v1_square_sat.png"
HEX_GOLDEN = RENDERER_DIR / "test_data/wang_solution_v1_hex_sat.png"


def _presentation(
    *,
    edges: tuple[int, int, int, int] = (10, 20, 30, 40),
    cells: tuple[int | None, ...] = (0,),
    width: int = 1,
    height: int = 1,
    min_x: int = -3,
    min_y: int = 5,
    boundary=None,
) -> WangPresentation:
    if boundary is None:
        boundary = tuple(
            None if tile_id is None else (None, None, None, None)
            for tile_id in cells
        )
    return WangPresentation(
        min_x=min_x,
        min_y=min_y,
        max_x=min_x + width - 1,
        max_y=min_y + height - 1,
        tile_edges=(edges,),
        cells=cells,
        boundary=boundary,
    )


def _mutate_tile_edge(
    presentation: WangHexPort, tile_id: int, direction: int, value: int
) -> WangHexPort:
    table = list(presentation.tile_edges)
    edges = list(table[tile_id])
    edges[direction] = value
    table[tile_id] = tuple(edges)
    return replace(presentation, tile_edges=tuple(table))


def test_fixture_port_preserves_coordinates_table_cells_holes_and_boundary():
    square = load_wang_presentation(FIXTURE)
    port = reduce_square_to_hex(square)

    assert (port.min_q, port.min_r, port.max_q, port.max_r) == (-1, 2, 2, 4)
    assert port.fresh_color == 16
    assert len(port.tile_edges) == len(square.tile_edges) == 23
    assert port.tile_edges[0] == (2, 7, 16, 1, 0, 16)
    assert port.cells is square.cells
    assert port.cells.count(None) == 2
    assert port.boundary[0] == (None, None, None, 2, 0, None)
    assert port.boundary[1] == (2, None, None, None, 0, None)
    assert port.boundary[8] == (None, 0, None, 2, None, None)
    assert port.boundary[2] is None
    check_square_to_hex(square, port)


def test_fresh_color_occurs_only_on_opposite_sw_and_ne_edges():
    square = load_wang_presentation(FIXTURE)
    port = reduce_square_to_hex(square)

    assert all(port.fresh_color not in edges for edges in square.tile_edges)
    for square_edges, hex_edges in zip(
        square.tile_edges, port.tile_edges, strict=True
    ):
        assert hex_edges[2] == hex_edges[5] == port.fresh_color
        assert port.fresh_color not in (hex_edges[0], hex_edges[1], *hex_edges[3:5])
        assert (hex_edges[4], hex_edges[0], hex_edges[1], hex_edges[3]) == (
            square_edges
        )


@pytest.mark.parametrize("direction", range(6))
def test_checker_rejects_a_mutation_on_each_hex_side(direction):
    square = load_wang_presentation(FIXTURE)
    port = reduce_square_to_hex(square)
    broken = _mutate_tile_edge(port, 0, direction, 999)

    with pytest.raises(WangSquareRenderError, match="does not implement H"):
        check_square_to_hex(square, broken)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda port: replace(port, min_q=port.min_q - 1), "coordinates"),
        (lambda port: replace(port, cells=(None, *port.cells[1:])), "assignment"),
        (lambda port: replace(port, fresh_color=999), "fresh color"),
        (
            lambda port: replace(port, boundary=port.boundary[:-1]),
            "hex boundary",
        ),
    ],
)
def test_checker_rejects_changed_preserved_state(mutation, message):
    square = load_wang_presentation(FIXTURE)
    port = reduce_square_to_hex(square)

    with pytest.raises(WangSquareRenderError, match=message):
        check_square_to_hex(square, mutation(port))


def test_checker_rejects_added_constraint_on_fresh_boundary_axis():
    square = load_wang_presentation(FIXTURE)
    port = reduce_square_to_hex(square)
    boundary = list(port.boundary)
    first = list(boundary[0])
    first[2] = port.fresh_color
    boundary[0] = tuple(first)

    with pytest.raises(WangSquareRenderError, match="boundary mapping"):
        check_square_to_hex(
            square, replace(port, boundary=tuple(boundary))
        )


def test_reducer_and_checker_reject_type_coercion_and_mutable_storage():
    square = load_wang_presentation(FIXTURE)
    port = reduce_square_to_hex(square)

    with pytest.raises(WangSquareRenderError, match="square tile table.*tuple"):
        reduce_square_to_hex(
            replace(square, tile_edges=list(square.tile_edges))
        )

    with pytest.raises(WangSquareRenderError, match="hex tile table.*tuple"):
        check_square_to_hex(
            square, replace(port, tile_edges=list(port.tile_edges))
        )

    bool_edges = list(port.tile_edges[0])
    bool_edges[3] = True  # Equal to the expected integer 1 without type checks.
    bool_table = (tuple(bool_edges), *port.tile_edges[1:])
    with pytest.raises(WangSquareRenderError, match="invalid edge color"):
        check_square_to_hex(
            square, replace(port, tile_edges=bool_table)
        )

    with pytest.raises(WangSquareRenderError, match="fresh color.*integer"):
        check_square_to_hex(
            square, replace(port, fresh_color=float(port.fresh_color))
        )


def test_port_checker_preserves_invalid_matching_truth_without_becoming_verifier():
    square = WangPresentation(
        min_x=-2,
        min_y=4,
        max_x=-1,
        max_y=4,
        tile_edges=((0, 10, 0, 20),),
        cells=(0, 0),
        boundary=((999, None, None, None), (None, None, None, None)),
    )
    port = reduce_square_to_hex(square)

    # The east/west colors and the north boundary are deliberately invalid.
    # The checker establishes equivalence of those false relations, not SAT.
    check_square_to_hex(square, port)


def test_pure_port_imports_no_raster_solver_or_native_modules(tmp_path):
    script = f"""
import importlib.util
from pathlib import Path
import sys

module_path = Path({str(RENDERER_DIR / 'wang_hex_port.py')!r})
spec = importlib.util.spec_from_file_location('isolated_wang_hex_port', module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
for forbidden in ('numpy', 'PIL', 'z3', 'formats', 'model', 'native', 'oracles'):
    assert forbidden not in sys.modules, forbidden
"""

    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_hex_canvas_is_dynamic_rgb_and_translation_invariant():
    square = load_wang_presentation(FIXTURE)
    translated = replace(
        square,
        min_x=19,
        min_y=-11,
        max_x=22,
        max_y=-9,
    )

    first = wang_square._compose_wang_hex(
        square, pixels_per_cell=8, margin=3
    )
    second = wang_square._compose_wang_hex(
        translated, pixels_per_cell=8, margin=3
    )

    assert first.shape == (47, 87, 3)
    assert first.dtype == np.uint8
    assert np.array_equal(first, second)
    assert tuple(first[0, 0]) == BACKGROUND_RGB


def test_hex_raster_places_eswwnwne_edge_colors_in_pointy_top_wedges():
    square = _presentation()
    port = reduce_square_to_hex(square)
    palette = wang_square._build_palette_from_edges(port.tile_edges)
    canvas = wang_square._compose_wang_hex(
        square, pixels_per_cell=8, margin=0
    )

    assert tuple(canvas[8, 14]) == palette[20]  # E
    assert tuple(canvas[12, 11]) == palette[30]  # SE
    assert tuple(canvas[12, 5]) == palette[port.fresh_color]  # SW
    assert tuple(canvas[8, 2]) == palette[40]  # W
    assert tuple(canvas[4, 5]) == palette[10]  # NW
    assert tuple(canvas[4, 11]) == palette[port.fresh_color]  # NE
    assert tuple(canvas[8, 16]) == GRID_RGB


def test_hex_hole_uses_neutral_checkerboard_not_logical_palette():
    square = _presentation(cells=(None, 0), width=2)
    canvas = wang_square._compose_wang_hex(
        square, pixels_per_cell=8, margin=0
    )
    hole_pixels = {tuple(pixel) for row in canvas[:, :16] for pixel in row}

    assert HOLE_LIGHT_RGB in hole_pixels
    assert HOLE_DARK_RGB in hole_pixels
    assert not hole_pixels & set(build_palette(square).values())


def test_hex_rejects_oversized_canvas_before_allocation():
    square = _presentation(
        cells=(0,) * 33,
        width=33,
        boundary=((None, None, None, None),) * 33,
    )

    with pytest.raises(WangSquareRenderError, match="canvas side exceeds"):
        wang_square._compose_wang_hex(
            square, pixels_per_cell=512, margin=0
        )


def test_default_mode_remains_byte_identical_and_skips_hex_port(
    tmp_path, monkeypatch
):
    output = tmp_path / "render.png"

    def fail_port(_presentation):
        raise AssertionError("default mode entered hex port")

    monkeypatch.setattr(wang_square, "reduce_square_to_hex", fail_port)
    render_wang_square(FIXTURE, output)

    assert output.read_bytes() == SQUARE_GOLDEN.read_bytes()


def test_hex_checker_failure_preserves_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "render.png"
    output.write_bytes(b"previous output")

    def fail_check(_square, _candidate):
        raise WangSquareRenderError("injected port rejection")

    monkeypatch.setattr(wang_square, "check_square_to_hex", fail_check)
    with pytest.raises(WangSquareRenderError, match="port rejection"):
        render_wang_square(FIXTURE, output, hex_mode=True)

    assert output.read_bytes() == b"previous output"
    assert not list(tmp_path.glob(".render.png.*.png"))


def test_hex_fixture_render_matches_decoded_golden_pixels(tmp_path):
    output = tmp_path / "render.png"
    render_wang_square(FIXTURE, output, hex_mode=True)

    with Image.open(output) as actual, Image.open(HEX_GOLDEN) as expected:
        actual.load()
        expected.load()
        assert actual.mode == expected.mode == "RGB"
        assert actual.size == expected.size == (337, 177)
        assert actual.tobytes() == expected.tobytes()
        assert hashlib.sha256(actual.tobytes()).hexdigest() == (
            "c5d40ce2ec0c124c32da789a21231b336b4c8b6242bb2fd85a579f7257811f04"
        )


def test_cli_hex_flag_renders_same_square_witness_as_hexagons(tmp_path):
    output = tmp_path / "render.png"
    wang_square.main(
        [
            str(FIXTURE),
            str(output),
            "--hex",
            "--pixels-per-cell",
            "8",
            "--margin",
            "0",
        ]
    )

    with Image.open(output) as image:
        assert image.mode == "RGB"
        assert image.size == (81, 41)
