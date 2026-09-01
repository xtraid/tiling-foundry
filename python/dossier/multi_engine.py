"""Atomic full-pipeline v2 capture over fixed named engines."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform as platform_module
import shutil
import subprocess
import tempfile
from time import perf_counter_ns

from formats.pipeline_snapshot import _encode_document, _write_atomic
from formats.run_case_v2 import (
    MultiEngineRunCase,
    TraceConfiguration,
    load_run_case_v2,
)
from formats.run_dossier_v2 import ARTIFACT_NAMES
from formats.run_dossier_v2_builder import build_run_dossier_v2
from formats.run_dossier_v2_bundle import load_run_dossier_v2
from formats.solver_trace_snapshot import (
    dump_solver_trace_bundle,
    load_solver_trace_bundle,
)
from formats.z3_encoding_summary import (
    build_boolean_z3_summary,
    build_wang_z3_summary,
)
from native.multi_engine_pipeline import (
    TraceCaptureOptions,
    capture_multi_engine_native_pipeline,
)
from oracles.tiling_check import is_valid_tiling
from oracles.witness_check import is_valid_assignment
from model.tileset import TILESET


ROOT = Path(__file__).resolve().parents[2]


class MultiEngineDossierError(RuntimeError):
    """The fixed v2 capture could not be completed atomically."""


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MultiEngineDossierError(
            f"cannot identify repository commit: {error}"
        ) from error
    return completed.stdout.strip()


def _native_options(configuration: TraceConfiguration) -> TraceCaptureOptions:
    return TraceCaptureOptions(
        event_capacity=configuration.event_capacity,
        checkpoint_interval=configuration.checkpoint_interval,
        checkpoint_capacity=configuration.checkpoint_capacity,
    )


def _artifact(
    dossier_root: Path,
    path: Path,
    *,
    source_sha256: str,
    media_type: str,
    schema: str | None,
    role: str,
    semantics: str,
) -> dict[str, object]:
    try:
        encoded = path.read_bytes()
        relative = path.relative_to(dossier_root).as_posix()
    except (OSError, ValueError) as error:
        raise MultiEngineDossierError(f"cannot bind artifact {path!s}: {error}") from error
    return {
        "path": relative,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "media_type": media_type,
        "schema": schema,
        "role": role,
        "semantics": semantics,
        "form": "data",
        "source_sha256": source_sha256,
    }


def _manifest_artifact(
    dossier_root: Path,
    manifest_path: Path,
    manifest: dict[str, object],
    name: str,
    *,
    source_sha256: str,
    role: str,
    semantics: str,
) -> dict[str, object] | None:
    references = manifest["artifacts"]
    assert isinstance(references, dict)
    reference = references[name]
    if reference is None:
        return None
    assert isinstance(reference, dict)
    return _artifact(
        dossier_root,
        manifest_path.parent / str(reference["path"]),
        source_sha256=source_sha256,
        media_type="application/json",
        schema=str(reference["schema"]),
        role=role,
        semantics=semantics,
    )


def _collect_artifacts(
    staging: Path,
    source_copy: Path,
    source_sha256: str,
    reference_manifest_path: Path,
    reference_manifest: dict[str, object],
    optimized_manifest_path: Path,
    optimized_manifest: dict[str, object],
    boolean_summary_path: Path,
    wang_summary_path: Path,
) -> dict[str, dict[str, object] | None]:
    artifacts: dict[str, dict[str, object] | None] = {
        "source_input": _artifact(
            staging,
            source_copy,
            source_sha256=source_sha256,
            media_type="text/plain",
            schema=None,
            role="self-contained CM1-in-3 source input",
            semantics="observed",
        ),
        "formula_snapshot": _manifest_artifact(
            staging,
            reference_manifest_path,
            reference_manifest,
            "formula",
            source_sha256=source_sha256,
            role="parsed formula snapshot shared by all engines",
            semantics="observed",
        ),
        "tileset_snapshot": _manifest_artifact(
            staging,
            reference_manifest_path,
            reference_manifest,
            "tileset",
            source_sha256=source_sha256,
            role="canonical 23-tile table shared by Wang engines",
            semantics="canonical-construction",
        ),
        "region_snapshot": _manifest_artifact(
            staging,
            reference_manifest_path,
            reference_manifest,
            "region",
            source_sha256=source_sha256,
            role="single native reduction region",
            semantics="observed",
        ),
        "provenance_snapshot": _manifest_artifact(
            staging,
            reference_manifest_path,
            reference_manifest,
            "reduction",
            source_sha256=source_sha256,
            role="single native reduction provenance",
            semantics="canonical-construction",
        ),
        "boolean_z3_summary": _artifact(
            staging,
            boolean_summary_path,
            source_sha256=source_sha256,
            media_type="application/json",
            schema="z3-encoding-summary-v1",
            role="Boolean Z3 encoding and returned model summary",
            semantics="encoding-order",
        ),
        "reference_trace_manifest": _artifact(
            staging,
            reference_manifest_path,
            source_sha256=source_sha256,
            media_type="application/json",
            schema="wang-explain-manifest-v3",
            role="reference solver trace manifest",
            semantics="observed",
        ),
        "reference_trace": _manifest_artifact(
            staging,
            reference_manifest_path,
            reference_manifest,
            "trace",
            source_sha256=source_sha256,
            role="complete observed reference trace",
            semantics="observed",
        ),
        "reference_solution": _manifest_artifact(
            staging,
            reference_manifest_path,
            reference_manifest,
            "solution",
            source_sha256=source_sha256,
            role="verified reference square witness",
            semantics="observed",
        ),
        "optimized_trace_manifest": _artifact(
            staging,
            optimized_manifest_path,
            source_sha256=source_sha256,
            media_type="application/json",
            schema="wang-explain-manifest-v3",
            role="optimized solver trace manifest",
            semantics="observed",
        ),
        "optimized_trace": _manifest_artifact(
            staging,
            optimized_manifest_path,
            optimized_manifest,
            "trace",
            source_sha256=source_sha256,
            role="complete observed optimized trace",
            semantics="observed",
        ),
        "optimized_solution": _manifest_artifact(
            staging,
            optimized_manifest_path,
            optimized_manifest,
            "solution",
            source_sha256=source_sha256,
            role="verified optimized square witness",
            semantics="observed",
        ),
        "wang_z3_summary": _artifact(
            staging,
            wang_summary_path,
            source_sha256=source_sha256,
            media_type="application/json",
            schema="z3-encoding-summary-v1",
            role="Wang Z3 encoding and returned model summary",
            semantics="encoding-order",
        ),
        "square_presentation": None,
        "generalized_presentation": None,
        "hex_presentation": None,
    }
    if tuple(artifacts) != ARTIFACT_NAMES:
        raise MultiEngineDossierError("internal artifact order diverged from contract")
    return artifacts


def _install_directory(staging: Path, destination: Path) -> None:
    """Single replace boundary kept injectable for atomic failure tests."""
    os.replace(staging, destination)


def generate_multi_engine_dossier(
    case_path: str | Path,
    output_directory: str | Path,
) -> Path:
    """Capture all named engines once and atomically install the raw v2 dossier."""
    case: MultiEngineRunCase = load_run_case_v2(case_path, ROOT)
    destination = Path(output_directory).resolve()
    if destination.exists():
        raise MultiEngineDossierError(
            f"output directory already exists: {destination!s}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        source_path = ROOT / case.source
        source_bytes = source_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        capture = capture_multi_engine_native_pipeline(
            source_path,
            reference_options=_native_options(case.reference_trace),
            optimized_options=_native_options(case.optimized_trace),
        )

        data = staging / "assets/data"
        data.mkdir(parents=True)
        source_copy = data / source_path.name
        reference_manifest_path = data / "reference-manifest.json"
        optimized_manifest_path = data / "optimized-manifest.json"
        boolean_summary_path = data / "boolean-z3.json"
        wang_summary_path = data / "wang-z3.json"

        started = perf_counter_ns()
        _write_atomic(source_copy, source_bytes)
        dump_solver_trace_bundle(
            reference_manifest_path,
            source_path,
            capture.formula,
            capture.region,
            capture.explanation,
            capture.reference.result,
            capture.reference.trace,
        )
        dump_solver_trace_bundle(
            optimized_manifest_path,
            source_path,
            capture.formula,
            capture.region,
            capture.explanation,
            capture.optimized.result,
            capture.optimized.trace,
        )
        reference_manifest, _ = load_solver_trace_bundle(reference_manifest_path)
        optimized_manifest, _ = load_solver_trace_bundle(optimized_manifest_path)
        export_ns = perf_counter_ns() - started
        region_reference = reference_manifest["artifacts"]["region"]
        assert isinstance(region_reference, dict)
        region_sha256 = str(region_reference["sha256"])

        started = perf_counter_ns()
        boolean_summary = build_boolean_z3_summary(
            capture.formula,
            source_formula_sha256=source_sha256,
        )
        boolean_z3_ns = perf_counter_ns() - started
        boolean_assignment = boolean_summary["model"]["assignment"]
        if boolean_summary["status"] == "sat":
            started = perf_counter_ns()
            if not isinstance(boolean_assignment, list) or not is_valid_assignment(
                capture.formula, boolean_assignment
            ):
                raise MultiEngineDossierError(
                    "Boolean Z3 assignment failed the independent checker"
                )
            boolean_z3_verify_ns: int | None = perf_counter_ns() - started
        else:
            boolean_z3_verify_ns = None

        started = perf_counter_ns()
        wang_summary = build_wang_z3_summary(
            capture.formula,
            capture.region,
            source_formula_sha256=source_sha256,
            region_sha256=region_sha256,
        )
        wang_z3_ns = perf_counter_ns() - started
        wang_cells = wang_summary["model"]["cells"]
        if wang_summary["status"] == "sat":
            started = perf_counter_ns()
            if not isinstance(wang_cells, list) or not is_valid_tiling(
                capture.region, TILESET, wang_cells
            ):
                raise MultiEngineDossierError(
                    "Wang Z3 tiling failed the independent checker"
                )
            wang_z3_verify_ns: int | None = perf_counter_ns() - started
        else:
            wang_z3_verify_ns = None

        started = perf_counter_ns()
        _write_atomic(boolean_summary_path, _encode_document(boolean_summary))
        _write_atomic(wang_summary_path, _encode_document(wang_summary))
        artifacts = _collect_artifacts(
            staging,
            source_copy,
            source_sha256,
            reference_manifest_path,
            reference_manifest,
            optimized_manifest_path,
            optimized_manifest,
            boolean_summary_path,
            wang_summary_path,
        )
        export_ns += perf_counter_ns() - started

        captured_at = datetime.now(timezone.utc).replace(microsecond=0)
        timings_ns: dict[str, int | None] = {
            "parse_ns": capture.timings.parse_ns,
            "reduction_ns": capture.timings.reduction_ns,
            "boolean_z3_ns": boolean_z3_ns,
            "boolean_z3_verify_ns": boolean_z3_verify_ns,
            "reference_solve_ns": capture.timings.reference_solve_ns,
            "reference_verify_ns": capture.timings.reference_verify_ns,
            "optimized_solve_ns": capture.timings.optimized_solve_ns,
            "optimized_verify_ns": capture.timings.optimized_verify_ns,
            "wang_z3_ns": wang_z3_ns,
            "wang_z3_verify_ns": wang_z3_verify_ns,
            "export_ns": export_ns,
        }
        run_document = build_run_dossier_v2(
            case,
            capture,
            source_sha256=source_sha256,
            captured_at_utc=captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            platform=platform_module.platform(),
            python_version=platform_module.python_version(),
            git_commit=_git_commit(),
            boolean_summary=boolean_summary,
            wang_summary=wang_summary,
            timings_ns=timings_ns,
            artifacts=artifacts,
        )
        _write_atomic(staging / "run.json", _encode_document(run_document))
        load_run_dossier_v2(staging / "run.json")
        _install_directory(staging, destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
