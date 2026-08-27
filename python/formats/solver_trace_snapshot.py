"""Closed, hash-bound snapshots for one observed native solver run.

This producer owns the v1 semantic trace document and the v3 explainability
manifest.  It deliberately reuses the existing formula, tileset, region,
reduction, and SAT-solution emitters instead of creating parallel formats.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from formats.pipeline_snapshot import (
    FORMULA_SCHEMA,
    REDUCTION_SCHEMA,
    REGION_SCHEMA,
    TILESET_SCHEMA,
    PipelineSnapshotError,
    _encode_document,
    _load_json_bytes,
    _require_artifact_name,
    _require_array,
    _require_exact_fields,
    _require_integer,
    _require_literal,
    _require_object,
    _require_sha256,
    _require_string,
    _validate_base_bundle_identity,
    _validate_reduction_bundle_identity,
    _validate_reference,
    _write_atomic,
    build_formula_snapshot,
    build_reduction_explanation_snapshot,
    build_region_snapshot,
    build_tileset_snapshot,
    validate_formula_snapshot,
    validate_reduction_explanation_snapshot,
    validate_region_snapshot,
    validate_tileset_snapshot,
)
from formats.wang_solution import SCHEMA_NAME as SOLUTION_SCHEMA
from formats.wang_solution import validate_wang_solution
from formats.wang_solution_export import build_wang_solution
from model.formula import Formula
from model.reduction_explanation import ReductionExplanation
from model.region import Region
from model.solver_trace import (
    SOLVERS,
    TRACE_KINDS,
    TRACE_PHASES,
    TRACE_REASONS,
    SolverTrace,
    SolverTraceCheckpoint,
    SolverTraceEvent,
    replay_solver_trace,
)
from model.tiling import TilingSolveResult, TilingSolveStatus


TRACE_SCHEMA: Final = "wang-solver-trace-v1"
TRACE_MANIFEST_SCHEMA: Final = "wang-explain-manifest-v3"
TRACE_STAGE: Final = "solver-trace"
TRACE_SEMANTICS: Final = "observed"
GEOMETRY: Final = "square"
INDEXING: Final = "row-major"
TILE_COUNT: Final = 23
_STATUSES: Final = frozenset({"sat", "unsat"})
_EVENT_FIELDS: Final = frozenset(
    {
        "sequence",
        "kind",
        "phase",
        "reason",
        "depth",
        "cell",
        "change_mark",
        "old_domain",
        "new_domain",
        "status",
    }
)


def _require_optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, path)


def _require_optional_integer(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_integer(value, path, nonnegative=True)


def _require_boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise PipelineSnapshotError(f"{path}: must be a boolean")
    return value


def _require_status(value: object, path: str) -> str:
    status = _require_string(value, path)
    if status not in _STATUSES:
        raise PipelineSnapshotError(f"{path}: must equal 'sat' or 'unsat'")
    return status


def _status_model(value: str) -> TilingSolveStatus:
    return (
        TilingSolveStatus.SAT
        if value == "sat"
        else TilingSolveStatus.UNSAT
    )


def _event_from_document(value: object, path: str) -> SolverTraceEvent:
    event = _require_object(value, path)
    _require_exact_fields(event, _EVENT_FIELDS, path)
    kind = _require_string(event["kind"], f"{path}.kind")
    if kind not in TRACE_KINDS:
        raise PipelineSnapshotError(f"{path}.kind: is not a trace event kind")
    phase = _require_optional_string(event["phase"], f"{path}.phase")
    if phase is not None and phase not in TRACE_PHASES:
        raise PipelineSnapshotError(f"{path}.phase: is not a trace phase")
    reason = _require_optional_string(event["reason"], f"{path}.reason")
    if reason is not None and reason not in TRACE_REASONS:
        raise PipelineSnapshotError(f"{path}.reason: is not a trace reason")
    status_value = _require_optional_string(event["status"], f"{path}.status")
    if status_value is not None:
        status_value = _require_status(status_value, f"{path}.status")
    try:
        return SolverTraceEvent(
            sequence=_require_integer(
                event["sequence"], f"{path}.sequence", nonnegative=True
            ),
            kind=kind,
            phase=phase,
            reason=reason,
            depth=_require_integer(
                event["depth"], f"{path}.depth", nonnegative=True
            ),
            cell=_require_optional_integer(event["cell"], f"{path}.cell"),
            change_mark=_require_integer(
                event["change_mark"],
                f"{path}.change_mark",
                nonnegative=True,
            ),
            old_domain=_require_optional_integer(
                event["old_domain"], f"{path}.old_domain"
            ),
            new_domain=_require_optional_integer(
                event["new_domain"], f"{path}.new_domain"
            ),
            status=(
                None if status_value is None else _status_model(status_value)
            ),
        )
    except (TypeError, ValueError) as error:
        raise PipelineSnapshotError(f"{path}: {error}") from error


def trace_from_document(document: object) -> SolverTrace:
    """Validate and project a trace JSON document to its immutable model."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset(
            {
                "schema",
                "semantics",
                "solver",
                "status",
                "geometry",
                "source_formula_sha256",
                "region_sha256",
                "solution_sha256",
                "layout",
                "capacity",
                "initial_domains",
                "events",
                "checkpoints",
            }
        ),
        "$",
    )
    _require_literal(root["schema"], TRACE_SCHEMA, "$.schema")
    _require_literal(root["semantics"], TRACE_SEMANTICS, "$.semantics")
    _require_literal(root["geometry"], GEOMETRY, "$.geometry")
    _require_sha256(root["source_formula_sha256"], "$.source_formula_sha256")
    _require_sha256(root["region_sha256"], "$.region_sha256")
    if root["solution_sha256"] is not None:
        _require_sha256(root["solution_sha256"], "$.solution_sha256")
    solver = _require_string(root["solver"], "$.solver")
    if solver not in SOLVERS:
        raise PipelineSnapshotError("$.solver: is not a supported native solver")
    status_value = _require_status(root["status"], "$.status")

    layout = _require_object(root["layout"], "$.layout")
    _require_exact_fields(
        layout,
        frozenset({"width", "height", "tile_count", "indexing"}),
        "$.layout",
    )
    width = _require_integer(layout["width"], "$.layout.width", nonnegative=True)
    height = _require_integer(
        layout["height"], "$.layout.height", nonnegative=True
    )
    if width == 0 or height == 0:
        raise PipelineSnapshotError("$.layout: dimensions must be positive")
    if _require_integer(
        layout["tile_count"], "$.layout.tile_count", nonnegative=True
    ) != TILE_COUNT:
        raise PipelineSnapshotError(
            f"$.layout.tile_count: must equal {TILE_COUNT}"
        )
    _require_literal(layout["indexing"], INDEXING, "$.layout.indexing")

    capacity = _require_object(root["capacity"], "$.capacity")
    _require_exact_fields(
        capacity,
        frozenset(
            {
                "event_capacity",
                "observed_event_count",
                "truncated",
                "checkpoint_interval",
                "checkpoint_capacity",
                "checkpoints_truncated",
            }
        ),
        "$.capacity",
    )
    initial = tuple(
        _require_integer(item, f"$.initial_domains[{index}]", nonnegative=True)
        for index, item in enumerate(
            _require_array(root["initial_domains"], "$.initial_domains")
        )
    )
    events = tuple(
        _event_from_document(item, f"$.events[{index}]")
        for index, item in enumerate(_require_array(root["events"], "$.events"))
    )
    checkpoints: list[SolverTraceCheckpoint] = []
    for index, raw_checkpoint in enumerate(
        _require_array(root["checkpoints"], "$.checkpoints")
    ):
        path = f"$.checkpoints[{index}]"
        checkpoint = _require_object(raw_checkpoint, path)
        _require_exact_fields(
            checkpoint,
            frozenset({"event_sequence", "change_mark", "domains"}),
            path,
        )
        try:
            checkpoints.append(
                SolverTraceCheckpoint(
                    event_sequence=_require_integer(
                        checkpoint["event_sequence"],
                        f"{path}.event_sequence",
                        nonnegative=True,
                    ),
                    change_mark=_require_integer(
                        checkpoint["change_mark"],
                        f"{path}.change_mark",
                        nonnegative=True,
                    ),
                    domains=tuple(
                        _require_integer(
                            item,
                            f"{path}.domains[{domain_index}]",
                            nonnegative=True,
                        )
                        for domain_index, item in enumerate(
                            _require_array(checkpoint["domains"], f"{path}.domains")
                        )
                    ),
                )
            )
        except (TypeError, ValueError) as error:
            raise PipelineSnapshotError(f"{path}: {error}") from error

    try:
        trace = SolverTrace(
            solver=solver,
            status=_status_model(status_value),
            width=width,
            height=height,
            initial_domains=initial,
            events=events,
            observed_event_count=_require_integer(
                capacity["observed_event_count"],
                "$.capacity.observed_event_count",
                nonnegative=True,
            ),
            event_capacity=_require_integer(
                capacity["event_capacity"],
                "$.capacity.event_capacity",
                nonnegative=True,
            ),
            truncated=_require_boolean(
                capacity["truncated"], "$.capacity.truncated"
            ),
            checkpoints=tuple(checkpoints),
            checkpoint_interval=_require_integer(
                capacity["checkpoint_interval"],
                "$.capacity.checkpoint_interval",
                nonnegative=True,
            ),
            checkpoint_capacity=_require_integer(
                capacity["checkpoint_capacity"],
                "$.capacity.checkpoint_capacity",
                nonnegative=True,
            ),
            checkpoints_truncated=_require_boolean(
                capacity["checkpoints_truncated"],
                "$.capacity.checkpoints_truncated",
            ),
        )
    except (TypeError, ValueError) as error:
        raise PipelineSnapshotError(f"$: {error}") from error

    expected_sequences = tuple(
        trace.checkpoint_interval * (index + 1) - 1
        for index in range(len(trace.checkpoints))
    )
    if tuple(item.event_sequence for item in trace.checkpoints) != expected_sequences:
        raise PipelineSnapshotError(
            "$.checkpoints: event sequences do not follow checkpoint_interval"
        )
    return trace


def validate_solver_trace_snapshot(document: object) -> None:
    """Validate the closed v1 trace syntax and replay semantics."""
    trace_from_document(document)


def build_solver_trace_snapshot(
    trace: SolverTrace,
    *,
    source_formula_sha256: str,
    region_sha256: str,
    solution_sha256: str | None,
) -> dict[str, object]:
    """Build one presentation-neutral observed trace document."""
    if not isinstance(trace, SolverTrace):
        raise TypeError("trace must be a SolverTrace")
    _require_sha256(source_formula_sha256, "source_formula_sha256")
    _require_sha256(region_sha256, "region_sha256")
    if solution_sha256 is not None:
        _require_sha256(solution_sha256, "solution_sha256")
    if (trace.status is TilingSolveStatus.SAT) != (solution_sha256 is not None):
        raise PipelineSnapshotError(
            "SAT traces require a solution digest and UNSAT traces forbid one"
        )

    document: dict[str, object] = {
        "schema": TRACE_SCHEMA,
        "semantics": TRACE_SEMANTICS,
        "solver": trace.solver,
        "status": trace.status.value,
        "geometry": GEOMETRY,
        "source_formula_sha256": source_formula_sha256,
        "region_sha256": region_sha256,
        "solution_sha256": solution_sha256,
        "layout": {
            "width": trace.width,
            "height": trace.height,
            "tile_count": TILE_COUNT,
            "indexing": INDEXING,
        },
        "capacity": {
            "event_capacity": trace.event_capacity,
            "observed_event_count": trace.observed_event_count,
            "truncated": trace.truncated,
            "checkpoint_interval": trace.checkpoint_interval,
            "checkpoint_capacity": trace.checkpoint_capacity,
            "checkpoints_truncated": trace.checkpoints_truncated,
        },
        "initial_domains": list(trace.initial_domains),
        "events": [
            {
                "sequence": event.sequence,
                "kind": event.kind,
                "phase": event.phase,
                "reason": event.reason,
                "depth": event.depth,
                "cell": event.cell,
                "change_mark": event.change_mark,
                "old_domain": event.old_domain,
                "new_domain": event.new_domain,
                "status": None if event.status is None else event.status.value,
            }
            for event in trace.events
        ],
        "checkpoints": [
            {
                "event_sequence": checkpoint.event_sequence,
                "change_mark": checkpoint.change_mark,
                "domains": list(checkpoint.domains),
            }
            for checkpoint in trace.checkpoints
        ],
    }
    validate_solver_trace_snapshot(document)
    return document


def _validate_trace_region_state(
    trace: SolverTrace,
    region_document: dict[str, object],
) -> None:
    active_raw = _require_array(region_document["active"], "region.active")
    active = tuple(value is True for value in active_raw)
    if len(active) != len(trace.initial_domains):
        raise PipelineSnapshotError(
            "trace.initial_domains: length does not match region active mask"
        )
    for index, is_active in enumerate(active):
        if not is_active and trace.initial_domains[index] != 0:
            raise PipelineSnapshotError(
                f"trace.initial_domains[{index}]: inactive cell must be zero"
            )
    for checkpoint_index, checkpoint in enumerate(trace.checkpoints):
        for cell, is_active in enumerate(active):
            if not is_active and checkpoint.domains[cell] != 0:
                raise PipelineSnapshotError(
                    "trace.checkpoints"
                    f"[{checkpoint_index}].domains[{cell}]: inactive cell must be zero"
                )
    for event_index, event in enumerate(trace.events):
        if event.cell is not None:
            if event.cell >= len(active):
                raise PipelineSnapshotError(
                    f"trace.events[{event_index}].cell: lies outside region"
                )
            if not active[event.cell]:
                raise PipelineSnapshotError(
                    f"trace.events[{event_index}].cell: must identify an active cell"
                )


def validate_solver_trace_manifest(document: object) -> None:
    """Validate the v3 manifest without reading referenced artifacts."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset({"schema", "stage", "source_formula_sha256", "artifacts"}),
        "$",
    )
    _require_literal(root["schema"], TRACE_MANIFEST_SCHEMA, "$.schema")
    _require_literal(root["stage"], TRACE_STAGE, "$.stage")
    _require_sha256(root["source_formula_sha256"], "$.source_formula_sha256")
    artifacts = _require_object(root["artifacts"], "$.artifacts")
    _require_exact_fields(
        artifacts,
        frozenset(
            {"formula", "tileset", "region", "reduction", "trace", "solution"}
        ),
        "$.artifacts",
    )
    for name, schema in (
        ("formula", FORMULA_SCHEMA),
        ("tileset", TILESET_SCHEMA),
        ("region", REGION_SCHEMA),
        ("reduction", REDUCTION_SCHEMA),
        ("trace", TRACE_SCHEMA),
    ):
        _validate_reference(
            artifacts[name], f"$.artifacts.{name}", expected_schema=schema
        )
    if artifacts["solution"] is not None:
        _validate_reference(
            artifacts["solution"],
            "$.artifacts.solution",
            expected_schema=SOLUTION_SCHEMA,
        )


def _reference(
    directory: Path,
    name: str,
    schema: str,
    document: dict[str, object],
    *,
    manifest_name: str,
) -> tuple[dict[str, object], str]:
    encoded = _encode_document(document)
    digest = hashlib.sha256(encoded).hexdigest()
    artifact_name = f"{name}-{digest}.json"
    _require_artifact_name(artifact_name, f"{name} artifact")
    if artifact_name == manifest_name:
        raise PipelineSnapshotError(
            f"manifest filename collides with generated artifact {artifact_name}"
        )
    _write_atomic(directory / artifact_name, encoded)
    return (
        {"path": artifact_name, "sha256": digest, "schema": schema},
        digest,
    )


def _read_referenced(
    manifest_path: Path,
    manifest: dict[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    artifacts = _require_object(manifest["artifacts"], "$.artifacts")
    schemas = {
        "formula": FORMULA_SCHEMA,
        "tileset": TILESET_SCHEMA,
        "region": REGION_SCHEMA,
        "reduction": REDUCTION_SCHEMA,
        "trace": TRACE_SCHEMA,
        "solution": SOLUTION_SCHEMA,
    }
    documents: dict[str, dict[str, object]] = {}
    digests: dict[str, str] = {}
    for name, schema in schemas.items():
        if artifacts[name] is None:
            continue
        reference = _require_object(artifacts[name], f"$.artifacts.{name}")
        artifact_name, expected_digest = _validate_reference(
            reference,
            f"$.artifacts.{name}",
            expected_schema=schema,
        )
        artifact_path = manifest_path.parent / artifact_name
        try:
            encoded = artifact_path.read_bytes()
        except OSError as error:
            raise PipelineSnapshotError(
                f"cannot read {name} artifact {artifact_path!s}: {error}"
            ) from error
        if hashlib.sha256(encoded).hexdigest() != expected_digest:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.sha256: does not match {artifact_name}"
            )
        document = _load_json_bytes(encoded, str(artifact_path))
        if document.get("schema") != schema:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.schema: does not match artifact"
            )
        documents[name] = document
        digests[name] = expected_digest
    return documents, digests


def load_solver_trace_bundle(
    manifest_path: str | Path,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Load and cross-check every v3 artifact, including semantic replay."""
    path = Path(manifest_path)
    try:
        manifest = _load_json_bytes(path.read_bytes(), str(path))
    except OSError as error:
        raise PipelineSnapshotError(f"cannot read manifest {path!s}: {error}") from error
    validate_solver_trace_manifest(manifest)
    documents, digests = _read_referenced(path, manifest)
    validate_formula_snapshot(documents["formula"])
    validate_tileset_snapshot(documents["tileset"])
    validate_region_snapshot(documents["region"])
    validate_reduction_explanation_snapshot(documents["reduction"])
    trace = trace_from_document(documents["trace"])
    _validate_trace_region_state(trace, documents["region"])
    if "solution" in documents:
        validate_wang_solution(documents["solution"])

    source_digest = _validate_base_bundle_identity(manifest, documents)
    _validate_reduction_bundle_identity(manifest, documents, source_digest)
    trace_document = documents["trace"]
    if trace_document["source_formula_sha256"] != source_digest:
        raise PipelineSnapshotError(
            "trace.source_formula_sha256: does not match formula"
        )
    if trace_document["region_sha256"] != digests["region"]:
        raise PipelineSnapshotError("trace.region_sha256: does not match region")
    solution_reference = _require_object(manifest["artifacts"], "$.artifacts")[
        "solution"
    ]
    if solution_reference is None:
        if trace.status is not TilingSolveStatus.UNSAT:
            raise PipelineSnapshotError("SAT trace requires a solution artifact")
        if trace_document["solution_sha256"] is not None:
            raise PipelineSnapshotError("UNSAT trace forbids a solution digest")
    else:
        if trace.status is not TilingSolveStatus.SAT:
            raise PipelineSnapshotError("UNSAT trace forbids a solution artifact")
        if trace_document["solution_sha256"] != digests["solution"]:
            raise PipelineSnapshotError(
                "trace.solution_sha256: does not match solution artifact"
            )
        solution = documents["solution"]
        bounds = _require_object(solution["bounds"], "solution.bounds")
        width = bounds["max_x_inclusive"] - bounds["min_x_inclusive"] + 1
        height = bounds["max_y_inclusive"] - bounds["min_y_inclusive"] + 1
        if (trace.width, trace.height) != (width, height):
            raise PipelineSnapshotError("trace layout does not match solution")
        if not trace.truncated:
            expected = tuple(
                0 if tile_id is None else 1 << tile_id
                for tile_id in _require_array(solution["cells"], "solution.cells")
            )
            if replay_solver_trace(trace)[-1] != expected:
                raise PipelineSnapshotError(
                    "complete trace does not replay to the bound solution"
                )
    return manifest, documents


def dump_solver_trace_bundle(
    manifest_path: str | Path,
    source_path: str | Path,
    formula: Formula,
    region: Region,
    explanation: ReductionExplanation,
    result: TilingSolveResult,
    trace: SolverTrace,
    *,
    origin: tuple[int, int] = (0, 0),
) -> Path:
    """Write content-addressed artifacts, then atomically install v3."""
    destination = Path(manifest_path)
    source = Path(source_path)
    try:
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot read formula source {source!s}: {error}"
        ) from error
    if (trace.width, trace.height) != (region.width, region.height):
        raise PipelineSnapshotError("trace dimensions do not match region")
    if trace.status is not result.status:
        raise PipelineSnapshotError("trace status does not match solve result")

    documents: dict[str, tuple[str, dict[str, object]]] = {
        "formula": (
            FORMULA_SCHEMA,
            build_formula_snapshot(
                formula,
                source_name=source.name,
                source_sha256=source_digest,
            ),
        ),
        "tileset": (TILESET_SCHEMA, build_tileset_snapshot()),
        "region": (
            REGION_SCHEMA,
            build_region_snapshot(
                region,
                source_formula_sha256=source_digest,
                origin=origin,
            ),
        ),
    }
    references: dict[str, object] = {}
    digests: dict[str, str] = {}
    for name, (schema, document) in documents.items():
        references[name], digests[name] = _reference(
            destination.parent,
            name,
            schema,
            document,
            manifest_name=destination.name,
        )

    reduction_document = build_reduction_explanation_snapshot(
        explanation,
        source_formula_sha256=source_digest,
        region_sha256=digests["region"],
    )
    references["reduction"], digests["reduction"] = _reference(
        destination.parent,
        "reduction",
        REDUCTION_SCHEMA,
        reduction_document,
        manifest_name=destination.name,
    )

    solution_digest: str | None = None
    if result.status is TilingSolveStatus.SAT:
        solution_document = build_wang_solution(
            region,
            result,
            origin=origin,
            metadata={"solver": trace.solver, "semantics": TRACE_SEMANTICS},
        )
        references["solution"], solution_digest = _reference(
            destination.parent,
            "solution",
            SOLUTION_SCHEMA,
            solution_document,
            manifest_name=destination.name,
        )
    else:
        references["solution"] = None

    trace_document = build_solver_trace_snapshot(
        trace,
        source_formula_sha256=source_digest,
        region_sha256=digests["region"],
        solution_sha256=solution_digest,
    )
    references["trace"], _ = _reference(
        destination.parent,
        "trace",
        TRACE_SCHEMA,
        trace_document,
        manifest_name=destination.name,
    )
    manifest: dict[str, object] = {
        "schema": TRACE_MANIFEST_SCHEMA,
        "stage": TRACE_STAGE,
        "source_formula_sha256": source_digest,
        "artifacts": references,
    }
    validate_solver_trace_manifest(manifest)
    _write_atomic(destination, _encode_document(manifest))
    load_solver_trace_bundle(destination)
    return destination
