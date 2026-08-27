from __future__ import annotations

from pathlib import Path

from PIL import Image

from wang_algorithm_animation import (
    main,
    render_builder_assets,
    render_hex_assets,
    render_optimized_assets,
)


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
BUILDER_MANIFEST = (
    ROOT / "tests/fixtures/pipeline_sat_reduction_explain/manifest.json"
)
SQUARE_SOLUTION = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"
GOLDENS = ROOT / "docs/assets/images"


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _assert_stable_assets(
    first_directory: Path,
    second_directory: Path,
    golden_directory: Path,
    *,
    frame_count: int,
    fallback_name: str,
) -> None:
    assert _tree_bytes(first_directory) == _tree_bytes(second_directory)
    assert _tree_bytes(first_directory) == _tree_bytes(golden_directory)
    with Image.open(first_directory / "trace.gif") as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == frame_count
    assert (first_directory / fallback_name).is_file()


def test_builder_animation_uses_versioned_provenance_and_is_byte_stable(tmp_path):
    first = render_builder_assets(BUILDER_MANIFEST, tmp_path / "first")
    render_builder_assets(BUILDER_MANIFEST, tmp_path / "second")

    assert first.fallback.name == "frame-04.png"
    _assert_stable_assets(
        tmp_path / "first",
        tmp_path / "second",
        GOLDENS / "builder-routing",
        frame_count=6,
        fallback_name="frame-04.png",
    )


def test_optimized_didactic_animation_is_byte_stable(tmp_path):
    first = render_optimized_assets(tmp_path / "first")
    render_optimized_assets(tmp_path / "second")

    assert first.fallback.name == "frame-05.png"
    _assert_stable_assets(
        tmp_path / "first",
        tmp_path / "second",
        GOLDENS / "optimized-mechanisms",
        frame_count=6,
        fallback_name="frame-05.png",
    )


def test_hex_animation_checks_the_pure_port_and_is_byte_stable(tmp_path):
    first = render_hex_assets(SQUARE_SOLUTION, tmp_path / "first")
    render_hex_assets(SQUARE_SOLUTION, tmp_path / "second")

    assert first.fallback.name == "frame-02.png"
    _assert_stable_assets(
        tmp_path / "first",
        tmp_path / "second",
        GOLDENS / "square-to-hex",
        frame_count=4,
        fallback_name="frame-02.png",
    )


def test_cli_reports_animation_and_fallback(tmp_path, capsys):
    assert main(["optimized", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"animation={tmp_path / 'trace.gif'}",
        f"fallback={tmp_path / 'frame-05.png'}",
    ]
