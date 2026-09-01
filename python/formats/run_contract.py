"""Small transport-validation helpers shared by closed dossier versions."""

from pathlib import PurePosixPath
import re

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _require_integer,
    _require_string,
)


def _nonempty_string(value: object, path: str) -> str:
    text = _require_string(value, path)
    if not text or text != text.strip():
        raise PipelineSnapshotError(f"{path}: must be nonempty without edge space")
    return text


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise PipelineSnapshotError(f"{path}: must be a boolean")
    return value


def _nullable_integer(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_integer(value, path, nonnegative=True)


def _relative_path(value: object, path: str, *, prefix: str | None = None) -> str:
    text = _nonempty_string(value, path)
    if "\\" in text or re.fullmatch(r"[A-Za-z0-9._/-]+", text) is None:
        raise PipelineSnapshotError(
            f"{path}: must use only portable POSIX path characters"
        )
    parsed = PurePosixPath(text)
    if parsed.is_absolute() or parsed.as_posix() != text or any(
        part in ("", ".", "..") for part in parsed.parts
    ):
        raise PipelineSnapshotError(f"{path}: must be a normalized relative path")
    if prefix is not None and (not parsed.parts or parsed.parts[0] != prefix):
        raise PipelineSnapshotError(f"{path}: must remain below {prefix}/")
    return text
