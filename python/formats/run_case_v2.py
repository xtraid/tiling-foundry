"""Closed full-pipeline case contract for multi-engine dossiers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Final

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _load_json_bytes,
    _require_exact_fields,
    _require_integer,
    _require_literal,
    _require_object,
)
from formats.run_contract import _nonempty_string, _relative_path


CASE_SCHEMA: Final = "wang-run-case-v2"
_STATUSES: Final = frozenset({"sat", "unsat"})
_CASE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_TRACE_FIELDS = frozenset(
    {"event_capacity", "checkpoint_interval", "checkpoint_capacity"}
)


@dataclass(frozen=True, slots=True)
class TraceConfiguration:
    event_capacity: int
    checkpoint_interval: int
    checkpoint_capacity: int


@dataclass(frozen=True, slots=True)
class MultiEngineRunCase:
    identifier: str
    title: str
    purpose: str
    source: str
    expected_status: str
    reference_trace: TraceConfiguration
    optimized_trace: TraceConfiguration


def _load_trace_configuration(value: object, path: str) -> TraceConfiguration:
    trace = _require_object(value, path)
    _require_exact_fields(trace, _TRACE_FIELDS, path)
    event_capacity = _require_integer(
        trace["event_capacity"], f"{path}.event_capacity", nonnegative=True
    )
    checkpoint_interval = _require_integer(
        trace["checkpoint_interval"],
        f"{path}.checkpoint_interval",
        nonnegative=True,
    )
    checkpoint_capacity = _require_integer(
        trace["checkpoint_capacity"],
        f"{path}.checkpoint_capacity",
        nonnegative=True,
    )
    if not 2 <= event_capacity <= 100_000:
        raise PipelineSnapshotError(
            f"{path}.event_capacity: must be in [2, 100000]"
        )
    if (checkpoint_interval == 0) != (checkpoint_capacity == 0):
        raise PipelineSnapshotError(
            f"{path}: checkpoint interval and capacity must be jointly set"
        )
    return TraceConfiguration(
        event_capacity=event_capacity,
        checkpoint_interval=checkpoint_interval,
        checkpoint_capacity=checkpoint_capacity,
    )


def load_run_case_v2(
    path: str | Path,
    repository_root: str | Path,
) -> MultiEngineRunCase:
    """Load one strict full-pipeline case; overrides are not in its vocabulary."""
    case_path = Path(path)
    try:
        document = _load_json_bytes(case_path.read_bytes(), str(case_path))
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot read v2 case {case_path!s}: {error}"
        ) from error
    _require_exact_fields(
        document,
        frozenset(
            {
                "schema",
                "id",
                "title",
                "purpose",
                "source",
                "expected_status",
                "reference_trace",
                "optimized_trace",
            }
        ),
        "$",
    )
    _require_literal(document["schema"], CASE_SCHEMA, "$.schema")
    identifier = _nonempty_string(document["id"], "$.id")
    if _CASE_ID.fullmatch(identifier) is None:
        raise PipelineSnapshotError(
            "$.id: must be a lowercase hyphenated identifier"
        )
    title = _nonempty_string(document["title"], "$.title")
    purpose = _nonempty_string(document["purpose"], "$.purpose")
    source = _relative_path(document["source"], "$.source")
    if not source.endswith(".cm13"):
        raise PipelineSnapshotError("$.source: must name a .cm13 input")
    if not (Path(repository_root) / source).is_file():
        raise PipelineSnapshotError(
            f"$.source: repository input does not exist: {source}"
        )
    expected_status = _nonempty_string(
        document["expected_status"], "$.expected_status"
    )
    if expected_status not in _STATUSES:
        raise PipelineSnapshotError("$.expected_status: must equal sat or unsat")
    return MultiEngineRunCase(
        identifier=identifier,
        title=title,
        purpose=purpose,
        source=source,
        expected_status=expected_status,
        reference_trace=_load_trace_configuration(
            document["reference_trace"], "$.reference_trace"
        ),
        optimized_trace=_load_trace_configuration(
            document["optimized_trace"], "$.optimized_trace"
        ),
    )
