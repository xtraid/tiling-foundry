"""Closed full-pipeline case and run contracts for multi-engine dossiers."""

from __future__ import annotations

import hashlib
import re
from typing import Final, Sequence

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _encode_document,
    _require_exact_fields,
    _require_integer,
    _require_literal,
    _require_object,
    _require_sha256,
)
from formats.run_case_v2 import _load_trace_configuration
from formats.run_contract import _boolean, _nonempty_string, _relative_path
from model.tileset import TILESET


RUN_SCHEMA: Final = "wang-run-dossier-v2"
STATUSES: Final = frozenset({"sat", "unsat"})
_CASE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_TRACE_FIELDS = frozenset(
    {"event_capacity", "checkpoint_interval", "checkpoint_capacity"}
)
_ARTIFACT_FIELDS = frozenset(
    {
        "path",
        "sha256",
        "media_type",
        "schema",
        "role",
        "semantics",
        "form",
        "source_sha256",
    }
)
_MEDIA_TYPES = frozenset(
    {"application/json", "text/plain", "image/png", "image/gif"}
)
_SEMANTICS = frozenset(
    {
        "observed",
        "canonical-construction",
        "encoding-order",
        "verified-transformation",
        "didactic",
    }
)
_FORMS = frozenset({"data", "static", "animated"})
_JSON_ARTIFACTS = frozenset(
    {
        "formula_snapshot",
        "tileset_snapshot",
        "region_snapshot",
        "provenance_snapshot",
        "boolean_z3_summary",
        "reference_trace_manifest",
        "reference_trace",
        "reference_solution",
        "optimized_trace_manifest",
        "optimized_trace",
        "optimized_solution",
        "wang_z3_summary",
    }
)
ARTIFACT_NAMES: Final = (
    "source_input",
    "formula_snapshot",
    "tileset_snapshot",
    "region_snapshot",
    "provenance_snapshot",
    "boolean_z3_summary",
    "reference_trace_manifest",
    "reference_trace",
    "reference_solution",
    "optimized_trace_manifest",
    "optimized_trace",
    "optimized_solution",
    "wang_z3_summary",
    "square_presentation",
    "generalized_presentation",
    "hex_presentation",
)
_PRESENTATION_ARTIFACTS = frozenset(
    {"square_presentation", "generalized_presentation", "hex_presentation"}
)
_TIMING_FIELDS = frozenset(
    {
        "clock",
        "identity",
        "parse_ns",
        "reduction_ns",
        "boolean_z3_ns",
        "boolean_z3_verify_ns",
        "reference_solve_ns",
        "reference_verify_ns",
        "optimized_solve_ns",
        "optimized_verify_ns",
        "wang_z3_ns",
        "wang_z3_verify_ns",
        "export_ns",
    }
)


def _nullable_nonnegative(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_integer(value, path, nonnegative=True)


def witness_sha256(values: Sequence[bool | int | None] | None) -> str | None:
    """Hash one witness payload without binding it to an engine document."""
    if values is None:
        return None
    return hashlib.sha256(_encode_document({"witness": list(values)})).hexdigest()


def _validate_assignment(value: object, path: str) -> tuple[bool, ...] | None:
    if value is None:
        return None
    if type(value) is not list or any(type(item) is not bool for item in value):
        raise PipelineSnapshotError(f"{path}: must be null or a boolean array")
    return tuple(value)


def _validate_cells(value: object, path: str) -> tuple[int | None, ...] | None:
    if value is None:
        return None
    if type(value) is not list:
        raise PipelineSnapshotError(f"{path}: must be null or a dense cell array")
    cells: list[int | None] = []
    for index, tile_id in enumerate(value):
        if tile_id is None:
            cells.append(None)
            continue
        parsed = _require_integer(tile_id, f"{path}[{index}]", nonnegative=True)
        if parsed >= len(TILESET):
            raise PipelineSnapshotError(
                f"{path}[{index}]: lies outside the canonical tileset"
            )
        cells.append(parsed)
    return tuple(cells)


def _validate_z3_record(value: object, path: str, *, wang: bool) -> str:
    record = _require_object(value, path)
    witness_field = "cells" if wang else "assignment"
    _require_exact_fields(
        record,
        frozenset(
            {
                "status",
                "configuration",
                "encoding_summary_sha256",
                witness_field,
                "witness_sha256",
            }
        ),
        path,
    )
    status = _nonempty_string(record["status"], f"{path}.status")
    if status not in STATUSES:
        raise PipelineSnapshotError(f"{path}.status: must equal sat or unsat")
    configuration = _require_object(record["configuration"], f"{path}.configuration")
    _require_exact_fields(
        configuration, frozenset({"random_seed", "threads"}), f"{path}.configuration"
    )
    if configuration != {"random_seed": 0, "threads": 1}:
        raise PipelineSnapshotError(f"{path}.configuration: must equal the fixed Z3 setup")
    _require_sha256(
        record["encoding_summary_sha256"], f"{path}.encoding_summary_sha256"
    )
    witness = (
        _validate_cells(record[witness_field], f"{path}.{witness_field}")
        if wang
        else _validate_assignment(record[witness_field], f"{path}.{witness_field}")
    )
    digest = record["witness_sha256"]
    if status == "sat":
        if witness is None:
            raise PipelineSnapshotError(f"{path}.{witness_field}: SAT requires a witness")
        _require_sha256(digest, f"{path}.witness_sha256")
        if digest != witness_sha256(witness):
            raise PipelineSnapshotError(f"{path}.witness_sha256: does not match witness")
    elif witness is not None or digest is not None:
        raise PipelineSnapshotError(f"{path}: UNSAT forbids witness data")
    return status


def _validate_native_record(value: object, path: str, solver: str) -> str:
    record = _require_object(value, path)
    _require_exact_fields(
        record,
        frozenset(
            {
                "status",
                "configuration",
                "trace",
                "solution_sha256",
                "witness_sha256",
                "extracted_assignment",
            }
        ),
        path,
    )
    status = _nonempty_string(record["status"], f"{path}.status")
    if status not in STATUSES:
        raise PipelineSnapshotError(f"{path}.status: must equal sat or unsat")
    _load_trace_configuration(record["configuration"], f"{path}.configuration")
    trace = _require_object(record["trace"], f"{path}.trace")
    _require_exact_fields(
        trace,
        frozenset(
            {
                "solver",
                "manifest_sha256",
                "trace_sha256",
                "complete",
                "truncated",
                "event_capacity",
                "observed_event_count",
                "checkpoint_interval",
                "checkpoint_capacity",
                "checkpoint_count",
                "selection",
            }
        ),
        f"{path}.trace",
    )
    _require_literal(trace["solver"], solver, f"{path}.trace.solver")
    _require_sha256(trace["manifest_sha256"], f"{path}.trace.manifest_sha256")
    _require_sha256(trace["trace_sha256"], f"{path}.trace.trace_sha256")
    if not _boolean(trace["complete"], f"{path}.trace.complete"):
        raise PipelineSnapshotError(f"{path}.trace.complete: v2 requires a complete trace")
    if _boolean(trace["truncated"], f"{path}.trace.truncated"):
        raise PipelineSnapshotError(f"{path}.trace.truncated: must remain false")
    event_capacity = _require_integer(
        trace["event_capacity"], f"{path}.trace.event_capacity", nonnegative=True
    )
    observed = _require_integer(
        trace["observed_event_count"],
        f"{path}.trace.observed_event_count",
        nonnegative=True,
    )
    checkpoint_interval = _require_integer(
        trace["checkpoint_interval"],
        f"{path}.trace.checkpoint_interval",
        nonnegative=True,
    )
    checkpoint_capacity = _require_integer(
        trace["checkpoint_capacity"],
        f"{path}.trace.checkpoint_capacity",
        nonnegative=True,
    )
    checkpoint_count = _require_integer(
        trace["checkpoint_count"],
        f"{path}.trace.checkpoint_count",
        nonnegative=True,
    )
    if observed < 2 or observed > event_capacity or checkpoint_count > checkpoint_capacity:
        raise PipelineSnapshotError(f"{path}.trace: inconsistent trace counts")
    if (checkpoint_interval == 0) != (checkpoint_capacity == 0):
        raise PipelineSnapshotError(f"{path}.trace: inconsistent checkpoint setup")
    selection = _require_object(trace["selection"], f"{path}.trace.selection")
    _require_exact_fields(
        selection,
        frozenset({"performed", "selected_event_count"}),
        f"{path}.trace.selection",
    )
    performed = _boolean(selection["performed"], f"{path}.trace.selection.performed")
    selected = _nullable_nonnegative(
        selection["selected_event_count"],
        f"{path}.trace.selection.selected_event_count",
    )
    if performed != (selected is not None) or (selected is not None and selected > observed):
        raise PipelineSnapshotError(f"{path}.trace.selection: is inconsistent")
    configuration = _require_object(record["configuration"], f"{path}.configuration")
    for name in _TRACE_FIELDS:
        if configuration[name] != trace[name]:
            raise PipelineSnapshotError(
                f"{path}.trace.{name}: disagrees with configured capture"
            )
    solution_digest = record["solution_sha256"]
    witness_digest = record["witness_sha256"]
    assignment = _validate_assignment(
        record["extracted_assignment"], f"{path}.extracted_assignment"
    )
    if status == "sat":
        _require_sha256(solution_digest, f"{path}.solution_sha256")
        _require_sha256(witness_digest, f"{path}.witness_sha256")
        if assignment is None:
            raise PipelineSnapshotError(f"{path}: SAT requires an extracted assignment")
    elif solution_digest is not None or witness_digest is not None or assignment is not None:
        raise PipelineSnapshotError(f"{path}: UNSAT forbids witness data")
    return status


def _validate_check(value: object, path: str, *, performed: bool) -> None:
    check = _require_object(value, path)
    _require_exact_fields(
        check,
        frozenset({"checker", "performed", "passed", "witness_sha256"}),
        path,
    )
    _nonempty_string(check["checker"], f"{path}.checker")
    if _boolean(check["performed"], f"{path}.performed") is not performed:
        raise PipelineSnapshotError(f"{path}.performed: disagrees with status")
    if performed:
        if check["passed"] is not True:
            raise PipelineSnapshotError(f"{path}.passed: performed checks must pass")
        _require_sha256(check["witness_sha256"], f"{path}.witness_sha256")
    elif check["passed"] is not None or check["witness_sha256"] is not None:
        raise PipelineSnapshotError(f"{path}: unperformed checks require null results")


def validate_run_dossier_v2(document: object) -> None:
    """Validate the closed transport and all internal named cross-fields."""
    root = _require_object(document, "$")
    _require_exact_fields(
        root,
        frozenset(
            {
                "schema",
                "case",
                "source",
                "environment",
                "boolean_z3",
                "reduction",
                "reference",
                "optimized",
                "wang_z3",
                "verification",
                "agreement",
                "presentation",
                "timings",
                "artifacts",
            }
        ),
        "$",
    )
    _require_literal(root["schema"], RUN_SCHEMA, "$.schema")

    case = _require_object(root["case"], "$.case")
    _require_exact_fields(
        case, frozenset({"id", "title", "purpose", "expected_status"}), "$.case"
    )
    identifier = _nonempty_string(case["id"], "$.case.id")
    if _CASE_ID.fullmatch(identifier) is None:
        raise PipelineSnapshotError("$.case.id: is invalid")
    _nonempty_string(case["title"], "$.case.title")
    _nonempty_string(case["purpose"], "$.case.purpose")
    expected_status = _nonempty_string(
        case["expected_status"], "$.case.expected_status"
    )
    if expected_status not in STATUSES:
        raise PipelineSnapshotError("$.case.expected_status: must equal sat or unsat")

    source = _require_object(root["source"], "$.source")
    _require_exact_fields(source, frozenset({"path", "sha256"}), "$.source")
    if not _relative_path(source["path"], "$.source.path").endswith(".cm13"):
        raise PipelineSnapshotError("$.source.path: must name a .cm13 input")
    source_sha256 = _require_sha256(source["sha256"], "$.source.sha256")

    environment = _require_object(root["environment"], "$.environment")
    _require_exact_fields(
        environment,
        frozenset({"captured_at_utc", "platform", "python", "git_commit"}),
        "$.environment",
    )
    captured = _nonempty_string(
        environment["captured_at_utc"], "$.environment.captured_at_utc"
    )
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", captured) is None:
        raise PipelineSnapshotError(
            "$.environment.captured_at_utc: must be UTC seconds"
        )
    _nonempty_string(environment["platform"], "$.environment.platform")
    _nonempty_string(environment["python"], "$.environment.python")
    commit = _nonempty_string(environment["git_commit"], "$.environment.git_commit")
    if _GIT_COMMIT.fullmatch(commit) is None:
        raise PipelineSnapshotError("$.environment.git_commit: must be a full SHA-1")

    statuses = {
        "boolean_z3": _validate_z3_record(root["boolean_z3"], "$.boolean_z3", wang=False),
        "reference": _validate_native_record(root["reference"], "$.reference", "reference"),
        "optimized": _validate_native_record(root["optimized"], "$.optimized", "optimized"),
        "wang_z3": _validate_z3_record(root["wang_z3"], "$.wang_z3", wang=True),
    }
    if any(status != expected_status for status in statuses.values()):
        raise PipelineSnapshotError("engine status mismatch")

    reduction = _require_object(root["reduction"], "$.reduction")
    _require_exact_fields(
        reduction,
        frozenset(
            {
                "formula_sha256",
                "tileset_sha256",
                "region_sha256",
                "provenance_sha256",
            }
        ),
        "$.reduction",
    )
    for name, digest in reduction.items():
        _require_sha256(digest, f"$.reduction.{name}")

    verification = _require_object(root["verification"], "$.verification")
    check_names = (
        "boolean_z3_assignment",
        "reference_tiling",
        "reference_assignment",
        "optimized_tiling",
        "optimized_assignment",
        "wang_z3_tiling",
    )
    _require_exact_fields(verification, frozenset(check_names), "$.verification")
    for name in check_names:
        _validate_check(
            verification[name],
            f"$.verification.{name}",
            performed=expected_status == "sat",
        )
    if expected_status == "sat":
        expected_check_digests = {
            "boolean_z3_assignment": root["boolean_z3"]["witness_sha256"],
            "reference_tiling": root["reference"]["witness_sha256"],
            "reference_assignment": witness_sha256(
                root["reference"]["extracted_assignment"]
            ),
            "optimized_tiling": root["optimized"]["witness_sha256"],
            "optimized_assignment": witness_sha256(
                root["optimized"]["extracted_assignment"]
            ),
            "wang_z3_tiling": root["wang_z3"]["witness_sha256"],
        }
        for name, digest in expected_check_digests.items():
            if verification[name]["witness_sha256"] != digest:
                raise PipelineSnapshotError(
                    f"$.verification.{name}.witness_sha256: cross-field mismatch"
                )

    agreement = _require_object(root["agreement"], "$.agreement")
    _require_exact_fields(
        agreement,
        frozenset(
            {
                "expected_status",
                "boolean_z3_status",
                "reference_status",
                "optimized_status",
                "wang_z3_status",
                "all_status_equal",
                "sat_witnesses_valid",
                "passed",
            }
        ),
        "$.agreement",
    )
    for name in (
        "expected_status",
        "boolean_z3_status",
        "reference_status",
        "optimized_status",
        "wang_z3_status",
    ):
        if agreement[name] != expected_status:
            raise PipelineSnapshotError(f"$.agreement.{name}: disagrees with case")
    if agreement["all_status_equal"] is not True or agreement["passed"] is not True:
        raise PipelineSnapshotError("$.agreement: engine disagreement is a failure")
    expected_witness_validity = True if expected_status == "sat" else None
    if agreement["sat_witnesses_valid"] is not expected_witness_validity:
        raise PipelineSnapshotError("$.agreement.sat_witnesses_valid: is inconsistent")

    presentation = _require_object(root["presentation"], "$.presentation")
    presentation_specs = {
        "square": "verified-wang-solution",
        "generalized": "exact-14-to-23-presentation",
        "hex": "checked-square-to-hex-transformation",
    }
    _require_exact_fields(presentation, frozenset(presentation_specs), "$.presentation")
    for name, relationship in presentation_specs.items():
        item = _require_object(presentation[name], f"$.presentation.{name}")
        _require_exact_fields(
            item, frozenset({"relationship", "applicable", "artifact"}),
            f"$.presentation.{name}",
        )
        _require_literal(
            item["relationship"], relationship, f"$.presentation.{name}.relationship"
        )
        if _boolean(item["applicable"], f"$.presentation.{name}.applicable") is not (
            expected_status == "sat"
        ):
            raise PipelineSnapshotError(f"$.presentation.{name}.applicable: disagrees")
        expected_artifact = f"{name}_presentation"
        if item["artifact"] not in (None, expected_artifact):
            raise PipelineSnapshotError(f"$.presentation.{name}.artifact: is invalid")

    timings = _require_object(root["timings"], "$.timings")
    _require_exact_fields(timings, _TIMING_FIELDS, "$.timings")
    _require_literal(timings["clock"], "monotonic-perf-counter-ns", "$.timings.clock")
    _require_literal(
        timings["identity"], "run-specific-observation-not-a-benchmark",
        "$.timings.identity",
    )
    nullable = {
        "boolean_z3_verify_ns",
        "reference_verify_ns",
        "optimized_verify_ns",
        "wang_z3_verify_ns",
    }
    for name in _TIMING_FIELDS - {"clock", "identity"}:
        elapsed = _nullable_nonnegative(timings[name], f"$.timings.{name}")
        if name in nullable:
            if (elapsed is None) != (expected_status == "unsat"):
                raise PipelineSnapshotError(
                    f"$.timings.{name}: applicability disagrees"
                )
        elif elapsed is None:
            raise PipelineSnapshotError(f"$.timings.{name}: must be performed")

    artifacts = _require_object(root["artifacts"], "$.artifacts")
    _require_exact_fields(artifacts, frozenset(ARTIFACT_NAMES), "$.artifacts")
    paths: set[str] = set()
    for name in ARTIFACT_NAMES:
        raw = artifacts[name]
        may_be_null = name in _PRESENTATION_ARTIFACTS or name.endswith("_solution")
        if raw is None:
            if not may_be_null:
                raise PipelineSnapshotError(f"$.artifacts.{name}: is required")
            if name.endswith("_solution") and expected_status == "sat":
                raise PipelineSnapshotError(f"$.artifacts.{name}: SAT requires a solution")
            continue
        if name.endswith("_solution") and expected_status == "unsat":
            raise PipelineSnapshotError(f"$.artifacts.{name}: UNSAT forbids a solution")
        item = _require_object(raw, f"$.artifacts.{name}")
        _require_exact_fields(item, _ARTIFACT_FIELDS, f"$.artifacts.{name}")
        relative = _relative_path(
            item["path"], f"$.artifacts.{name}.path", prefix="assets"
        )
        if relative in paths:
            raise PipelineSnapshotError(f"$.artifacts.{name}.path: duplicates another artifact")
        paths.add(relative)
        _require_sha256(item["sha256"], f"$.artifacts.{name}.sha256")
        media_type = _nonempty_string(
            item["media_type"], f"$.artifacts.{name}.media_type"
        )
        if media_type not in _MEDIA_TYPES:
            raise PipelineSnapshotError(f"$.artifacts.{name}.media_type: is unsupported")
        expected_media_type = (
            "text/plain"
            if name == "source_input"
            else "application/json"
            if name in _JSON_ARTIFACTS
            else "image/png"
        )
        if media_type != expected_media_type:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.media_type: must equal {expected_media_type}"
            )
        if item["schema"] is not None:
            _nonempty_string(item["schema"], f"$.artifacts.{name}.schema")
        _nonempty_string(item["role"], f"$.artifacts.{name}.role")
        semantics = _nonempty_string(
            item["semantics"], f"$.artifacts.{name}.semantics"
        )
        if semantics not in _SEMANTICS:
            raise PipelineSnapshotError(f"$.artifacts.{name}.semantics: is unsupported")
        form = _nonempty_string(item["form"], f"$.artifacts.{name}.form")
        if form not in _FORMS:
            raise PipelineSnapshotError(f"$.artifacts.{name}.form: is unsupported")
        if item["source_sha256"] != source_sha256:
            raise PipelineSnapshotError(f"$.artifacts.{name}.source_sha256: disagrees")

    for name, digest in (
        ("formula_snapshot", reduction["formula_sha256"]),
        ("tileset_snapshot", reduction["tileset_sha256"]),
        ("region_snapshot", reduction["region_sha256"]),
        ("provenance_snapshot", reduction["provenance_sha256"]),
        ("boolean_z3_summary", root["boolean_z3"]["encoding_summary_sha256"]),
        ("reference_trace_manifest", root["reference"]["trace"]["manifest_sha256"]),
        ("reference_trace", root["reference"]["trace"]["trace_sha256"]),
        ("optimized_trace_manifest", root["optimized"]["trace"]["manifest_sha256"]),
        ("optimized_trace", root["optimized"]["trace"]["trace_sha256"]),
        ("wang_z3_summary", root["wang_z3"]["encoding_summary_sha256"]),
    ):
        if artifacts[name]["sha256"] != digest:
            raise PipelineSnapshotError(f"$.artifacts.{name}.sha256: cross-field mismatch")
    if artifacts["source_input"]["sha256"] != source_sha256:
        raise PipelineSnapshotError(
            "$.artifacts.source_input.sha256: must match the source identity"
        )
    for solver in ("reference", "optimized"):
        solution = artifacts[f"{solver}_solution"]
        if expected_status == "sat" and solution["sha256"] != root[solver]["solution_sha256"]:
            raise PipelineSnapshotError(
                f"$.artifacts.{solver}_solution.sha256: cross-field mismatch"
            )
    for name in ("square", "generalized", "hex"):
        artifact_name = f"{name}_presentation"
        selected = presentation[name]["artifact"]
        if (selected is None) != (artifacts[artifact_name] is None):
            raise PipelineSnapshotError(
                f"$.presentation.{name}.artifact: disagrees with artifacts"
            )
