"""Builder for one successful fixed-engine v2 dossier document."""

from __future__ import annotations

from typing import TYPE_CHECKING

from formats.pipeline_snapshot import PipelineSnapshotError
from formats.run_case_v2 import MultiEngineRunCase, TraceConfiguration
from formats.run_dossier_v2 import (
    ARTIFACT_NAMES,
    RUN_SCHEMA,
    STATUSES,
    _TIMING_FIELDS,
    _validate_assignment,
    _validate_cells,
    validate_run_dossier_v2,
    witness_sha256,
)
from formats.z3_encoding_summary import validate_z3_encoding_summary
from model.tileset import TILESET
from oracles.tiling_check import is_valid_tiling
from oracles.witness_check import is_valid_assignment

if TYPE_CHECKING:
    from native.multi_engine_pipeline import MultiEngineNativeCapture


def _trace_record(
    capture: object,
    configuration: TraceConfiguration,
    manifest_sha256: str,
    trace_sha256: str,
) -> dict[str, object]:
    trace = capture.trace
    result = capture.result
    return {
        "status": result.status.value,
        "configuration": {
            "event_capacity": configuration.event_capacity,
            "checkpoint_interval": configuration.checkpoint_interval,
            "checkpoint_capacity": configuration.checkpoint_capacity,
        },
        "trace": {
            "solver": trace.solver,
            "manifest_sha256": manifest_sha256,
            "trace_sha256": trace_sha256,
            "complete": not trace.truncated,
            "truncated": trace.truncated,
            "event_capacity": trace.event_capacity,
            "observed_event_count": trace.observed_event_count,
            "checkpoint_interval": trace.checkpoint_interval,
            "checkpoint_capacity": trace.checkpoint_capacity,
            "checkpoint_count": len(trace.checkpoints),
            "selection": {
                "performed": False,
                "selected_event_count": None,
            },
        },
        "solution_sha256": None,
        "witness_sha256": witness_sha256(result.tiling),
        "extracted_assignment": (
            None
            if capture.extracted_assignment is None
            else list(capture.extracted_assignment)
        ),
    }


def _check_record(checker: str, digest: str | None) -> dict[str, object]:
    return {
        "checker": checker,
        "performed": digest is not None,
        "passed": True if digest is not None else None,
        "witness_sha256": digest,
    }


def build_run_dossier_v2(
    case: MultiEngineRunCase,
    capture: "MultiEngineNativeCapture",
    *,
    source_sha256: str,
    captured_at_utc: str,
    platform: str,
    python_version: str,
    git_commit: str,
    boolean_summary: dict[str, object],
    wang_summary: dict[str, object],
    timings_ns: dict[str, int | None],
    artifacts: dict[str, dict[str, object] | None],
) -> dict[str, object]:
    """Build one successful named-engine capture; mismatches are fatal."""
    if not isinstance(case, MultiEngineRunCase):
        raise TypeError("case must be a MultiEngineRunCase")
    validate_z3_encoding_summary(boolean_summary)
    validate_z3_encoding_summary(wang_summary)
    statuses = {
        "boolean_z3": boolean_summary["status"],
        "reference": capture.reference.result.status.value,
        "optimized": capture.optimized.result.status.value,
        "wang_z3": wang_summary["status"],
    }
    if any(status not in STATUSES for status in statuses.values()):
        raise PipelineSnapshotError("full-pipeline dossier forbids UNKNOWN results")
    if any(status != case.expected_status for status in statuses.values()):
        raise PipelineSnapshotError("engine status mismatch")
    if capture.reference.trace.truncated or capture.optimized.trace.truncated:
        raise PipelineSnapshotError("full-pipeline dossier requires complete traces")

    boolean_assignment = _validate_assignment(
        boolean_summary["model"]["assignment"],
        "boolean_summary.model.assignment",
    )
    wang_cells = _validate_cells(
        wang_summary["model"]["cells"], "wang_summary.model.cells"
    )
    if case.expected_status == "sat":
        if boolean_assignment is None or not is_valid_assignment(
            capture.formula, boolean_assignment
        ):
            raise PipelineSnapshotError(
                "Boolean Z3 assignment failed independent check"
            )
        if wang_cells is None or not is_valid_tiling(
            capture.region, TILESET, wang_cells
        ):
            raise PipelineSnapshotError("Wang Z3 tiling failed independent check")

    required_timing_names = _TIMING_FIELDS - {"clock", "identity"}
    if frozenset(timings_ns) != required_timing_names:
        raise PipelineSnapshotError("timings do not match the fixed v2 contract")
    if frozenset(artifacts) != frozenset(ARTIFACT_NAMES):
        raise PipelineSnapshotError("artifacts do not match the fixed v2 contract")

    reference = _trace_record(
        capture.reference,
        case.reference_trace,
        artifacts["reference_trace_manifest"]["sha256"],
        artifacts["reference_trace"]["sha256"],
    )
    optimized = _trace_record(
        capture.optimized,
        case.optimized_trace,
        artifacts["optimized_trace_manifest"]["sha256"],
        artifacts["optimized_trace"]["sha256"],
    )
    if case.expected_status == "sat":
        reference["solution_sha256"] = artifacts["reference_solution"]["sha256"]
        optimized["solution_sha256"] = artifacts["optimized_solution"]["sha256"]

    boolean_digest = witness_sha256(boolean_assignment)
    wang_digest = witness_sha256(wang_cells)
    reference_digest = reference["witness_sha256"]
    optimized_digest = optimized["witness_sha256"]
    document: dict[str, object] = {
        "schema": RUN_SCHEMA,
        "case": {
            "id": case.identifier,
            "title": case.title,
            "purpose": case.purpose,
            "expected_status": case.expected_status,
        },
        "source": {"path": case.source, "sha256": source_sha256},
        "environment": {
            "captured_at_utc": captured_at_utc,
            "platform": platform,
            "python": python_version,
            "git_commit": git_commit,
        },
        "boolean_z3": {
            "status": statuses["boolean_z3"],
            "configuration": {"random_seed": 0, "threads": 1},
            "encoding_summary_sha256": artifacts["boolean_z3_summary"]["sha256"],
            "assignment": (
                None if boolean_assignment is None else list(boolean_assignment)
            ),
            "witness_sha256": boolean_digest,
        },
        "reduction": {
            "formula_sha256": artifacts["formula_snapshot"]["sha256"],
            "tileset_sha256": artifacts["tileset_snapshot"]["sha256"],
            "region_sha256": artifacts["region_snapshot"]["sha256"],
            "provenance_sha256": artifacts["provenance_snapshot"]["sha256"],
        },
        "reference": reference,
        "optimized": optimized,
        "wang_z3": {
            "status": statuses["wang_z3"],
            "configuration": {"random_seed": 0, "threads": 1},
            "encoding_summary_sha256": artifacts["wang_z3_summary"]["sha256"],
            "cells": None if wang_cells is None else list(wang_cells),
            "witness_sha256": wang_digest,
        },
        "verification": {
            "boolean_z3_assignment": _check_record(
                "oracles.witness_check.is_valid_assignment", boolean_digest
            ),
            "reference_tiling": _check_record(
                "oracles.tiling_check.is_valid_tiling", reference_digest
            ),
            "reference_assignment": _check_record(
                "oracles.witness_check.is_valid_assignment",
                witness_sha256(capture.reference.extracted_assignment),
            ),
            "optimized_tiling": _check_record(
                "oracles.tiling_check.is_valid_tiling", optimized_digest
            ),
            "optimized_assignment": _check_record(
                "oracles.witness_check.is_valid_assignment",
                witness_sha256(capture.optimized.extracted_assignment),
            ),
            "wang_z3_tiling": _check_record(
                "oracles.tiling_check.is_valid_tiling", wang_digest
            ),
        },
        "agreement": {
            "expected_status": case.expected_status,
            "boolean_z3_status": statuses["boolean_z3"],
            "reference_status": statuses["reference"],
            "optimized_status": statuses["optimized"],
            "wang_z3_status": statuses["wang_z3"],
            "all_status_equal": True,
            "sat_witnesses_valid": (
                True if case.expected_status == "sat" else None
            ),
            "passed": True,
        },
        "presentation": {
            "square": {
                "relationship": "verified-wang-solution",
                "applicable": case.expected_status == "sat",
                "artifact": None,
            },
            "generalized": {
                "relationship": "exact-14-to-23-presentation",
                "applicable": case.expected_status == "sat",
                "artifact": None,
            },
            "hex": {
                "relationship": "checked-square-to-hex-transformation",
                "applicable": case.expected_status == "sat",
                "artifact": None,
            },
        },
        "timings": {
            "clock": "monotonic-perf-counter-ns",
            "identity": "run-specific-observation-not-a-benchmark",
            **timings_ns,
        },
        "artifacts": artifacts,
    }
    validate_run_dossier_v2(document)
    return document
