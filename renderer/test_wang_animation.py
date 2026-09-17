from __future__ import annotations

import io

from PIL import Image
import pytest

import wang_animation
from wang_animation import write_animation_assets
from wang_explain import EXPLAIN_OUTLINE_RGB


def _frames(size, count):
    return tuple(
        Image.new("RGB", size, (20 * index, 10 * index, 200 - 10 * index))
        for index in range(count)
    )


def _write(frames, destination):
    return write_animation_assets(
        frames, tuple(f"frame-{index}.png" for index in range(len(frames))),
        destination, fallback_index=len(frames) - 1, duration_ms=80,
    )


@pytest.mark.parametrize(
    "size,count,side,pixels,expected_extent",
    [
        ((12, 8), 5, 24, 10000, (24, 10)),  # Width bound.
        ((8, 12), 10, 24, 10000, (12, 24)),  # Height bound.
        ((12, 8), 7, 64, 300, (21, 12)),  # Area bound alone.
        ((12, 8), 7, 24, 144, (15, 9)),  # Both bounds.
        ((20, 1), 4, 30, 30, (15, 2)),  # One-pixel short side still fits area.
    ],
)
def test_only_contact_thumbnails_shrink_within_limits_in_original_order(
    tmp_path, monkeypatch, size, count, side, pixels, expected_extent
):
    frames = _frames(size, count)
    source_pixels = tuple(frame.tobytes() for frame in frames)
    baseline = _write(frames, tmp_path / "full-size")
    monkeypatch.setattr(wang_animation, "MAX_CANVAS_SIDE", side)
    monkeypatch.setattr(wang_animation, "MAX_CANVAS_PIXELS", pixels)

    scaled = _write(frames, tmp_path / "bounded")
    again = _write(frames, tmp_path / "repeated")

    assert tuple(frame.size for frame in frames) == (size,) * count
    assert tuple(frame.tobytes() for frame in frames) == source_pixels
    assert scaled.fallback == scaled.frames[-1]
    for full, bounded in zip(baseline.frames, scaled.frames, strict=True):
        assert full.read_bytes() == bounded.read_bytes()
    assert scaled.animation.read_bytes() == baseline.animation.read_bytes()
    assert scaled.contact_sheet.read_bytes() == again.contact_sheet.read_bytes()

    with Image.open(scaled.contact_sheet) as sheet:
        assert sheet.size == expected_extent
        assert sheet.width <= side and sheet.height <= side
        assert sheet.width * sheet.height <= pixels
        columns = 3
        rows = (count + 2) // 3
        width, height = sheet.width // columns, sheet.height // rows
        # The minor dimension rounds down, but never below one pixel.
        if size[0] >= size[1]:
            assert abs(height - size[1] * width / size[0]) < 1
        else:
            assert abs(width - size[0] * height / size[1]) < 1
        for index, frame in enumerate(frames):
            center = ((index % 3) * width + width // 2, (index // 3) * height + height // 2)
            assert sheet.getpixel(center) == frame.getpixel((0, 0))
        # The final unused cell retains the existing background.
        assert sheet.getpixel((sheet.width - 1, sheet.height - 1)) == EXPLAIN_OUTLINE_RGB


@pytest.mark.parametrize("side,pixels", [(36, 864), (100, 10000)])
def test_fitting_legacy_contact_sheet_keeps_exact_png_bytes(
    tmp_path, monkeypatch, side, pixels
):
    frames = _frames((12, 8), 7)
    # Nonuniform pixels also detect accidental resampling on the legacy branch.
    frames[0].putpixel((1, 2), (255, 0, 71))
    frames[6].putpixel((11, 7), (1, 2, 3))
    expected = Image.new("RGB", (36, 24), EXPLAIN_OUTLINE_RGB)
    positions = ((0, 0), (12, 0), (24, 0), (0, 8), (12, 8), (24, 8), (0, 16))
    for frame, position in zip(frames, positions, strict=True):
        expected.paste(frame, position)
    encoded = io.BytesIO()
    expected.save(encoded, format="PNG", optimize=False, compress_level=9)
    monkeypatch.setattr(wang_animation, "MAX_CANVAS_SIDE", side)
    monkeypatch.setattr(wang_animation, "MAX_CANVAS_PIXELS", pixels)

    result = _write(frames, tmp_path / "legacy")

    assert result.contact_sheet.read_bytes() == encoded.getvalue()
