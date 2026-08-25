"""Tests for the presentation-only Wang square renderer."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

import wang_square
from wang_square import (
    BACKGROUND_RGB,
    DEFAULT_MARGIN,
    DEFAULT_PIXELS_PER_CELL,
    GRID_RGB,
    HOLE_DARK_RGB,
    HOLE_LIGHT_RGB,
    WangPresentation,
    WangSquareRenderError,
    build_palette,
    compose_wang_square,
    load_wang_presentation,
    render_wang_square,
)


RENDERER_DIR = Path(__file__).resolve().parent
ROOT_DIR = RENDERER_DIR.parent
FIXTURE = ROOT_DIR / "tests/fixtures/wang_solution_v1_square_sat.json"
GOLDEN = RENDERER_DIR / "test_data/wang_solution_v1_square_sat.png"


def _fixture_document() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write_document(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "solution.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _presentation(
    *,
    edges: tuple[int, int, int, int] = (0, 1, 2, 3),
    cells: tuple[int | None, ...] = (0,),
    width: int = 1,
    height: int = 1,
) -> WangPresentation:
    return WangPresentation(
        min_x=-3,
        min_y=5,
        max_x=-3 + width - 1,
        max_y=5 + height - 1,
        tile_edges=(edges,),
        cells=cells,
    )


def test_loads_representative_fixture_with_negative_origin_and_holes():
    presentation = load_wang_presentation(FIXTURE)

    assert (presentation.min_x, presentation.min_y) == (-1, 2)
    assert (presentation.width, presentation.height) == (4, 3)
    assert len(presentation.tile_edges) == 23
    assert len(presentation.cells) == 12
    assert presentation.cells.count(None) == 2


def test_missing_input_has_descriptive_file_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Wang solution file not found"):
        load_wang_presentation(tmp_path / "missing.json")


def test_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "solution.json"
    path.write_bytes(b"\xff")

    with pytest.raises(WangSquareRenderError, match="not valid UTF-8"):
        load_wang_presentation(path)


def test_rejects_invalid_json(tmp_path):
    path = tmp_path / "solution.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="invalid JSON"):
        load_wang_presentation(path)


def test_rejects_duplicate_members(tmp_path):
    path = tmp_path / "solution.json"
    path.write_text('{"schema": 1, "schema": 2}', encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="duplicate member 'schema'"):
        load_wang_presentation(path)


def test_rejects_nonfinite_numbers(tmp_path):
    path = tmp_path / "solution.json"
    path.write_text('{"value": NaN}', encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="non-finite number NaN"):
        load_wang_presentation(path)


def test_rejects_integer_beyond_python_json_limit(tmp_path):
    path = tmp_path / "solution.json"
    path.write_text('{"value": ' + "9" * 5000 + "}", encoding="utf-8")

    with pytest.raises(WangSquareRenderError, match="invalid JSON value"):
        load_wang_presentation(path)


def test_cli_normalizes_json_value_error_without_traceback(tmp_path, capsys):
    source = tmp_path / "solution.json"
    source.write_text('{"value": ' + "9" * 5000 + "}", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        wang_square.main([str(source), str(tmp_path / "render.png")])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert "invalid JSON value" in captured.err
    assert "Traceback" not in captured.err


def test_normalizes_json_recursion_error(tmp_path, monkeypatch):
    source = tmp_path / "solution.json"
    source.write_text("{}", encoding="utf-8")

    def fail_load(*args, **kwargs):
        raise RecursionError("injected nesting limit")

    monkeypatch.setattr(wang_square.json, "load", fail_load)

    with pytest.raises(WangSquareRenderError, match="injected nesting limit"):
        load_wang_presentation(source)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda document: document.pop("metadata"), "missing fields: metadata"),
        (lambda document: document.update(extra=True), "unknown fields: extra"),
        (lambda document: document.update(schema="v2"), "must equal"),
        (lambda document: document.update(status="UNSAT"), "must equal"),
        (lambda document: document.update(geometry="hex"), "must equal"),
    ],
)
def test_rejects_wrong_top_level_contract(tmp_path, mutation, message):
    document = _fixture_document()
    mutation(document)

    with pytest.raises(WangSquareRenderError, match=message):
        load_wang_presentation(_write_document(tmp_path, document))


def test_rejects_reversed_inclusive_bounds(tmp_path):
    document = _fixture_document()
    document["bounds"]["max_x_inclusive"] = -2

    with pytest.raises(WangSquareRenderError, match="max_x_inclusive"):
        load_wang_presentation(_write_document(tmp_path, document))


def test_rejects_noncanonical_tile_table_position(tmp_path):
    document = _fixture_document()
    document["tile_table"][1]["tile_id"] = 7

    with pytest.raises(WangSquareRenderError, match="canonical table position 1"):
        load_wang_presentation(_write_document(tmp_path, document))


@pytest.mark.parametrize("bad_color", [-1, True, 1.5])
def test_rejects_invalid_tile_edge_color(tmp_path, bad_color):
    document = _fixture_document()
    document["tile_table"][0]["edges"]["N"] = bad_color

    with pytest.raises(WangSquareRenderError, match="edges.N"):
        load_wang_presentation(_write_document(tmp_path, document))


def test_rejects_dense_cell_length_mismatch(tmp_path):
    document = _fixture_document()
    document["cells"].pop()

    with pytest.raises(WangSquareRenderError, match="inclusive bounds area 12"):
        load_wang_presentation(_write_document(tmp_path, document))


def test_rejects_absent_tile_reference(tmp_path):
    document = _fixture_document()
    document["cells"][0] = 23

    with pytest.raises(WangSquareRenderError, match="absent tile_id 23"):
        load_wang_presentation(_write_document(tmp_path, document))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document["boundary"].pop(),
        lambda document: document["boundary"][0].pop("N"),
        lambda document: document["boundary"][0].update(N=-1),
    ],
)
def test_rejects_malformed_boundary_transport_shape(tmp_path, mutation):
    document = _fixture_document()
    mutation(document)

    with pytest.raises(WangSquareRenderError, match="boundary"):
        load_wang_presentation(_write_document(tmp_path, document))


def test_rejects_nonobject_metadata(tmp_path):
    document = _fixture_document()
    document["metadata"] = []

    with pytest.raises(WangSquareRenderError, match="metadata"):
        load_wang_presentation(_write_document(tmp_path, document))


def test_palette_is_deterministic_injective_and_avoids_reserved_colors():
    presentation = WangPresentation(
        min_x=0,
        min_y=0,
        max_x=0,
        max_y=0,
        tile_edges=((100, 3, 42, 3), (999, 100, 0, 42)),
        cells=(0,),
    )

    first = build_palette(presentation)
    second = build_palette(presentation)

    assert first == second
    assert list(first) == [0, 3, 42, 100, 999]
    assert len(set(first.values())) == len(first)
    assert not set(first.values()) & {
        BACKGROUND_RGB,
        GRID_RGB,
        HOLE_LIGHT_RGB,
        HOLE_DARK_RGB,
    }


def test_compose_uses_dynamic_canvas_size_and_rgb_dtype():
    presentation = load_wang_presentation(FIXTURE)

    canvas = compose_wang_square(presentation, pixels_per_cell=10, margin=3)

    assert canvas.shape == (36, 46, 3)
    assert canvas.dtype == np.uint8
    assert tuple(canvas[0, 0]) == BACKGROUND_RGB


def test_tile_raster_uses_nesw_nearest_edge_and_stable_ties():
    presentation = _presentation(edges=(10, 20, 30, 40))
    palette = build_palette(presentation)
    canvas = compose_wang_square(presentation, pixels_per_cell=8, margin=0)

    assert tuple(canvas[1, 4]) == palette[10]
    assert tuple(canvas[4, 6]) == palette[20]
    assert tuple(canvas[6, 4]) == palette[30]
    assert tuple(canvas[4, 1]) == palette[40]
    assert tuple(canvas[3, 3]) == palette[10]
    assert tuple(canvas[0, 4]) == GRID_RGB


def test_holes_use_neutral_checkerboard_not_logical_palette():
    presentation = _presentation(cells=(None, 0), width=2)
    canvas = compose_wang_square(presentation, pixels_per_cell=8, margin=0)
    hole_pixels = {tuple(pixel) for row in canvas[:, :8] for pixel in row}

    assert GRID_RGB in hole_pixels
    assert HOLE_LIGHT_RGB in hole_pixels
    assert HOLE_DARK_RGB in hole_pixels
    assert not hole_pixels & set(build_palette(presentation).values())


def test_boundary_and_metadata_are_pixel_neutral(tmp_path):
    original = _fixture_document()
    changed = copy.deepcopy(original)
    changed["metadata"] = {"display": {"anything": [1, 2, 3]}}
    changed["boundary"] = [None] * len(changed["boundary"])
    for index, tile_id in enumerate(changed["cells"]):
        if tile_id is not None:
            changed["boundary"][index] = {
                "N": 999,
                "E": 998,
                "S": 997,
                "W": 996,
            }

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_text(json.dumps(original), encoding="utf-8")
    second_path.write_text(json.dumps(changed), encoding="utf-8")

    assert np.array_equal(
        compose_wang_square(load_wang_presentation(first_path)),
        compose_wang_square(load_wang_presentation(second_path)),
    )


@pytest.mark.parametrize(
    ("pixels_per_cell", "margin", "message"),
    [
        (7, 0, "pixels_per_cell"),
        (513, 0, "pixels_per_cell"),
        (True, 0, "pixels_per_cell"),
        (8, -1, "margin"),
        (8, 4097, "margin"),
        (8, 1.5, "margin"),
    ],
)
def test_rejects_invalid_render_dimensions(
    pixels_per_cell, margin, message
):
    with pytest.raises(WangSquareRenderError, match=message):
        compose_wang_square(
            _presentation(),
            pixels_per_cell=pixels_per_cell,
            margin=margin,
        )


def test_rejects_oversized_canvas_before_allocation():
    presentation = _presentation(cells=(0,) * 33, width=33)

    with pytest.raises(WangSquareRenderError, match="canvas side exceeds"):
        compose_wang_square(
            presentation,
            pixels_per_cell=512,
            margin=0,
        )


def test_fixture_render_matches_decoded_golden_pixels(tmp_path):
    output = tmp_path / "render.png"
    render_wang_square(FIXTURE, output)

    with Image.open(output) as actual, Image.open(GOLDEN) as expected:
        actual.load()
        expected.load()
        assert actual.mode == expected.mode == "RGB"
        assert actual.size == expected.size == (144, 112)
        assert actual.tobytes() == expected.tobytes()
        assert hashlib.sha256(actual.tobytes()).hexdigest() == (
            "48f0ed543c0c2d91ff26b12db592d2a7ecb737bd5694af4930c4296c99512d6d"
        )


def test_render_installs_complete_png(tmp_path):
    output = tmp_path / "render.png"
    render_wang_square(FIXTURE, output, pixels_per_cell=8, margin=1)

    with Image.open(output) as image:
        image.verify()
    assert not list(tmp_path.glob(".render.png.*.png"))


def test_failed_replace_preserves_output_and_removes_temporary(
    tmp_path, monkeypatch
):
    output = tmp_path / "render.png"
    output.write_bytes(b"previous output")

    def fail_replace(source, destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr(wang_square.os, "replace", fail_replace)

    with pytest.raises(WangSquareRenderError, match="replace failure"):
        render_wang_square(FIXTURE, output)

    assert output.read_bytes() == b"previous output"
    assert not list(tmp_path.glob(".render.png.*.png"))


def test_invalid_input_never_changes_existing_output(tmp_path):
    output = tmp_path / "render.png"
    output.write_bytes(b"previous output")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    with pytest.raises(WangSquareRenderError):
        render_wang_square(invalid, output)

    assert output.read_bytes() == b"previous output"


def test_cli_renders_fixture(tmp_path):
    output = tmp_path / "render.png"
    wang_square.main(
        [str(FIXTURE), str(output), "--pixels-per-cell", "8", "--margin", "0"]
    )

    with Image.open(output) as image:
        assert image.mode == "RGB"
        assert image.size == (32, 24)


def test_cli_reports_invalid_input_without_traceback(tmp_path, capsys):
    output = tmp_path / "render.png"

    with pytest.raises(SystemExit) as error:
        wang_square.main([str(tmp_path / "missing.json"), str(output)])

    assert error.value.code == 2
    assert "Wang solution file not found" in capsys.readouterr().err
    assert not output.exists()


def test_consumer_process_does_not_import_core_z3_or_load_libwang(tmp_path):
    output = tmp_path / "render.png"
    script = f"""
import importlib.util
from pathlib import Path
import sys

module_path = Path({str(RENDERER_DIR / 'wang_square.py')!r})
spec = importlib.util.spec_from_file_location('isolated_wang_square', module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.render_wang_square({str(FIXTURE)!r}, {str(output)!r})
for forbidden in ('z3', 'formats', 'model', 'native', 'oracles'):
    assert forbidden not in sys.modules, forbidden
maps = Path('/proc/self/maps').read_text(encoding='utf-8')
assert 'libwang.so' not in maps
"""

    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.exists()


def test_legacy_modules_are_not_imported_by_wang_backend():
    assert "Palette" not in wang_square.__dict__
    assert "RenderingPipeline" not in wang_square.__dict__
