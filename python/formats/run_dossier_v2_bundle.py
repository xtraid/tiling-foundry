"""Self-contained loader for an already captured multi-engine v2 dossier."""

from __future__ import annotations

import hashlib
from pathlib import Path

from formats.pipeline_snapshot import (
    DIRECTIONS,
    PipelineSnapshotError,
    _load_json_bytes,
)
from formats.run_dossier_v2 import validate_run_dossier_v2, witness_sha256
from formats.solver_trace_snapshot import load_solver_trace_bundle
from formats.z3_encoding_summary import validate_z3_encoding_summary
from model.formula import Formula
from model.region import Region
from model.tileset import COLOR_NONE, TILESET
from oracles.tiling_check import is_valid_tiling
from oracles.witness_check import is_valid_assignment


def _formula_from_snapshot(document: dict[str, object]) -> Formula:
    clauses = document["clauses"]
    assert isinstance(clauses, list)
    return Formula(
        variable_count=int(document["variable_count"]),
        clauses=tuple(tuple(item["variables"]) for item in clauses),
    )


def _region_from_snapshot(document: dict[str, object]) -> Region:
    bounds = document["bounds"]
    assert isinstance(bounds, dict)
    width = int(bounds["max_x_inclusive"]) - int(bounds["min_x_inclusive"]) + 1
    height = int(bounds["max_y_inclusive"]) - int(bounds["min_y_inclusive"]) + 1
    active = tuple(document["active"])
    raw_boundary = document["boundary"]
    assert isinstance(raw_boundary, list)
    boundary = tuple(
        (COLOR_NONE, COLOR_NONE, COLOR_NONE, COLOR_NONE)
        if sides is None
        else tuple(
            COLOR_NONE if sides[direction] is None else sides[direction]
            for direction in DIRECTIONS
        )
        for sides in raw_boundary
    )
    return Region(width=width, height=height, active=active, boundary=boundary)


def load_run_dossier_v2(path: str | Path) -> dict[str, object]:
    """Verify files, existing bundles, witnesses, and shared identities."""
    run_path = Path(path)
    try:
        document = _load_json_bytes(run_path.read_bytes(), str(run_path))
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot read v2 dossier {run_path!s}: {error}"
        ) from error
    validate_run_dossier_v2(document)
    artifacts = document["artifacts"]
    assert isinstance(artifacts, dict)
    try:
        root = run_path.parent.resolve(strict=True)
    except OSError as error:
        raise PipelineSnapshotError(
            f"cannot resolve v2 dossier root: {error}"
        ) from error
    artifact_paths: dict[str, Path] = {}
    documents: dict[str, dict[str, object]] = {}
    for name, raw in artifacts.items():
        if raw is None:
            continue
        assert isinstance(raw, dict)
        try:
            candidate = (run_path.parent / str(raw["path"])).resolve(strict=True)
            if not candidate.is_relative_to(root) or not candidate.is_file():
                raise PipelineSnapshotError(
                    f"$.artifacts.{name}.path: escapes dossier"
                )
            encoded = candidate.read_bytes()
        except PipelineSnapshotError:
            raise
        except OSError as error:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.path: cannot read artifact: {error}"
            ) from error
        if hashlib.sha256(encoded).hexdigest() != raw["sha256"]:
            raise PipelineSnapshotError(
                f"$.artifacts.{name}.sha256: does not match file"
            )
        artifact_paths[name] = candidate
        if raw["media_type"] == "application/json":
            documents[name] = _load_json_bytes(encoded, str(candidate))

    source_bytes = artifact_paths["source_input"].read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != document["source"]["sha256"]:
        raise PipelineSnapshotError(
            "$.source.sha256: does not match self-contained input"
        )

    reference_manifest, reference_documents = load_solver_trace_bundle(
        artifact_paths["reference_trace_manifest"]
    )
    optimized_manifest, optimized_documents = load_solver_trace_bundle(
        artifact_paths["optimized_trace_manifest"]
    )
    for name in ("formula", "tileset", "region", "reduction"):
        reference_digest = reference_manifest["artifacts"][name]["sha256"]
        optimized_digest = optimized_manifest["artifacts"][name]["sha256"]
        if reference_digest != optimized_digest:
            raise PipelineSnapshotError(
                f"native manifests disagree on shared {name}"
            )
    shared_fields = {
        "formula": "formula_sha256",
        "tileset": "tileset_sha256",
        "region": "region_sha256",
        "reduction": "provenance_sha256",
    }
    for manifest_name, run_name in shared_fields.items():
        manifest_digest = reference_manifest["artifacts"][manifest_name]["sha256"]
        if manifest_digest != document["reduction"][run_name]:
            raise PipelineSnapshotError(
                f"native manifest {manifest_name} identity disagrees with run"
            )
    for solver, manifest in (
        ("reference", reference_manifest),
        ("optimized", optimized_manifest),
    ):
        trace_digest = manifest["artifacts"]["trace"]["sha256"]
        if trace_digest != document[solver]["trace"]["trace_sha256"]:
            raise PipelineSnapshotError(f"{solver} manifest trace identity mismatch")
        solution_reference = manifest["artifacts"]["solution"]
        if document["case"]["expected_status"] == "sat":
            if solution_reference["sha256"] != document[solver]["solution_sha256"]:
                raise PipelineSnapshotError(
                    f"{solver} manifest solution identity mismatch"
                )
        elif solution_reference is not None:
            raise PipelineSnapshotError(
                f"{solver} UNSAT manifest contains a solution"
            )
    if reference_documents["tileset"] != optimized_documents["tileset"]:
        raise PipelineSnapshotError("native manifests disagree on tileset")
    tile_documents = reference_documents["tileset"]["tiles"]
    canonical_tiles = tuple(
        tuple(tile["edges"][direction] for direction in DIRECTIONS)
        for tile in tile_documents
    )
    if canonical_tiles != TILESET:
        raise PipelineSnapshotError(
            "native manifests do not bind the canonical tileset"
        )

    boolean_summary = documents["boolean_z3_summary"]
    wang_summary = documents["wang_z3_summary"]
    validate_z3_encoding_summary(boolean_summary)
    validate_z3_encoding_summary(wang_summary)
    source_sha256 = document["source"]["sha256"]
    region_sha256 = document["reduction"]["region_sha256"]
    if boolean_summary["source_formula_sha256"] != source_sha256:
        raise PipelineSnapshotError("Boolean Z3 source identity mismatch")
    if (
        wang_summary["source_formula_sha256"] != source_sha256
        or wang_summary["region_sha256"] != region_sha256
    ):
        raise PipelineSnapshotError("Wang Z3 source or region identity mismatch")

    formula = _formula_from_snapshot(reference_documents["formula"])
    region = _region_from_snapshot(reference_documents["region"])
    if document["case"]["expected_status"] == "sat":
        boolean_assignment = tuple(boolean_summary["model"]["assignment"])
        wang_cells = tuple(wang_summary["model"]["cells"])
        if not is_valid_assignment(formula, boolean_assignment):
            raise PipelineSnapshotError(
                "Boolean Z3 assignment failed independent check"
            )
        if not is_valid_tiling(region, TILESET, wang_cells):
            raise PipelineSnapshotError("Wang Z3 tiling failed independent check")
        for solver, bundle in (
            ("reference", reference_documents),
            ("optimized", optimized_documents),
        ):
            cells = tuple(bundle["solution"]["cells"])
            if not is_valid_tiling(region, TILESET, cells):
                raise PipelineSnapshotError(
                    f"{solver} tiling failed independent check"
                )
            if document[solver]["witness_sha256"] != witness_sha256(cells):
                raise PipelineSnapshotError(f"{solver} witness digest mismatch")
            assignment = tuple(document[solver]["extracted_assignment"])
            if not is_valid_assignment(formula, assignment):
                raise PipelineSnapshotError(
                    f"{solver} assignment failed independent check"
                )
        if document["boolean_z3"]["witness_sha256"] != witness_sha256(
            boolean_assignment
        ):
            raise PipelineSnapshotError("Boolean Z3 witness digest mismatch")
        if document["wang_z3"]["witness_sha256"] != witness_sha256(wang_cells):
            raise PipelineSnapshotError("Wang Z3 witness digest mismatch")
    narrative_path = run_path.parent / "assets/narrative/manifest.json"
    narrative_expected = any(
        document[solver]["trace"]["selection"]["performed"]
        for solver in ("reference", "optimized")
    ) or any(
        document["artifacts"][f"{name}_presentation"] is not None
        for name in ("square", "generalized", "hex")
    )
    if narrative_expected and not narrative_path.is_file():
        raise PipelineSnapshotError(
            "selected narrative assets require assets/narrative/manifest.json"
        )
    if narrative_path.is_file():
        cursor = run_path.parent
        for component in Path("assets/narrative/manifest.json").parts:
            cursor /= component
            if cursor.is_symlink():
                raise PipelineSnapshotError(
                    "assets/narrative and its manifest may not contain symlinks"
                )
        try:
            resolved_narrative = narrative_path.resolve(strict=True)
        except OSError as error:
            raise PipelineSnapshotError(
                f"cannot resolve narrative manifest: {error}"
            ) from error
        if not resolved_narrative.is_relative_to(root):
            raise PipelineSnapshotError("narrative manifest escapes dossier")
        from formats.narrative_assets import load_narrative_assets

        narrative = load_narrative_assets(resolved_narrative, document)
        if narrative["product"] != "run-specific":
            raise PipelineSnapshotError(
                "a dossier may contain only a run-specific narrative manifest"
            )
        for solver, animation_name in (
            ("reference", "reference_trace"),
            ("optimized", "optimized_trace"),
        ):
            selection = document[solver]["trace"]["selection"]
            selected = len(narrative["animations"][animation_name]["frames"])
            if not selection["performed"]:
                raise PipelineSnapshotError(
                    f"{solver} narrative manifest requires a performed selection"
                )
            if selection["selected_event_count"] != selected:
                raise PipelineSnapshotError(
                    f"{solver} selected event count disagrees with narrative manifest"
                )
        if document["case"]["expected_status"] == "sat" and any(
            document["artifacts"][f"{name}_presentation"] is None
            for name in ("square", "generalized", "hex")
        ):
            raise PipelineSnapshotError(
                "SAT narrative manifest requires all presentation artifacts"
            )
    return document
