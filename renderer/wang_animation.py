"""Shared deterministic PNG/contact-sheet/GIF encoding for renderer frames."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image

from wang_explain import EXPLAIN_OUTLINE_RGB
from wang_hex_port import WangSquareRenderError
from wang_square import MAX_CANVAS_PIXELS, MAX_CANVAS_SIDE, _save_png_atomic


@dataclass(frozen=True, slots=True)
class AnimationOutputs:
    frames: tuple[Path, ...]
    fallback: Path
    contact_sheet: Path
    animation: Path


def _save_gif_atomic(
    frames: tuple[Image.Image, ...],
    path: Path,
    duration_ms: int,
) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        frames[0].save(
            temporary,
            format="GIF",
            save_all=True,
            append_images=list(frames[1:]),
            duration=duration_ms,
            loop=0,
            disposal=2,
            optimize=False,
        )
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def write_animation_assets(
    frames: tuple[Image.Image, ...],
    frame_names: tuple[str, ...],
    output_directory: str | Path,
    *,
    fallback_index: int,
    duration_ms: int,
) -> AnimationOutputs:
    """Encode one composed frame sequence without reconstructing any frame."""
    if not frames or len(frames) != len(frame_names):
        raise WangSquareRenderError("animation frames and names must align")
    if any(frame.mode != "RGB" or frame.size != frames[0].size for frame in frames):
        raise WangSquareRenderError("animation frames must share one RGB extent")
    if len(set(frame_names)) != len(frame_names) or any(
        not name or Path(name).name != name or not name.endswith(".png")
        for name in frame_names
    ):
        raise WangSquareRenderError("animation frame names must be unique PNG basenames")
    if type(fallback_index) is not int or not 0 <= fallback_index < len(frames):
        raise WangSquareRenderError("animation fallback index lies outside frames")
    if type(duration_ms) is not int or not 40 <= duration_ms <= 10_000:
        raise WangSquareRenderError("duration_ms must be in [40, 10000]")

    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for frame, name in zip(frames, frame_names, strict=True):
        path = destination / name
        _save_png_atomic(np.asarray(frame, dtype=np.uint8), path)
        frame_paths.append(path)

    columns = min(3, len(frames))
    rows = (len(frames) + columns - 1) // columns
    frame_width, frame_height = frames[0].size
    sheet_width = columns * frame_width
    sheet_height = rows * frame_height
    if (
        sheet_width > MAX_CANVAS_SIDE
        or sheet_height > MAX_CANVAS_SIDE
        or sheet_width * sheet_height > MAX_CANVAS_PIXELS
    ):
        raise WangSquareRenderError("animation contact sheet exceeds canvas limits")
    sheet = Image.new("RGB", (sheet_width, sheet_height), EXPLAIN_OUTLINE_RGB)
    for index, frame in enumerate(frames):
        sheet.paste(
            frame,
            ((index % columns) * frame_width, (index // columns) * frame_height),
        )
    contact_path = destination / "contact-sheet.png"
    _save_png_atomic(np.asarray(sheet, dtype=np.uint8), contact_path)
    animation_path = destination / "trace.gif"
    _save_gif_atomic(frames, animation_path, duration_ms)
    return AnimationOutputs(
        frames=tuple(frame_paths),
        fallback=frame_paths[fallback_index],
        contact_sheet=contact_path,
        animation=animation_path,
    )
