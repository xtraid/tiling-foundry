"""Closed manifest for shared narrative assets derived from one v2 run."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from formats.pipeline_snapshot import (
    PipelineSnapshotError,
    _encode_document,
    _load_json_bytes,
    _require_exact_fields,
    _require_literal,
    _require_object,
    _require_sha256,
)
from formats.run_contract import _boolean, _nonempty_string, _relative_path
from formats.run_dossier_v2 import validate_run_dossier_v2


SCHEMA_NAME: Final = "wang-narrative-assets-v1"
OPTIMIZED_MECHANISMS_SHA256: Final = (
    "5f0c6e1f80601f6112ae8e358fe8029fa3d94fd260693edf0b37ea474419f212"
)
GENERALIZED_SPECIFICATION_SHA256: Final = (
    "5e8e6589271f9059b5ed81df00db4e303b338d5243caa475ed09135b129e3cf2"
)
HEX_TRANSFORMATION_ID: Final = "basire-culik-square-to-hex-v1"
CANONICAL_PAGES_CASE: Final = {
    "id": "pipeline-sat-v2",
    "expected_status": "sat",
    "source_sha256": "3caaa6b29ac988fb4f51cc7071202d83ea1591ba6170e683b6da449cb3641542",
}
PRODUCTS: Final = frozenset({"run-specific", "canonical-pages"})
SEMANTIC_LABELS: Final = frozenset(
    {
        "observed",
        "canonical-construction",
        "encoding-order",
        "verified-transformation",
        "didactic",
    }
)
ANIMATION_NAMES: Final = (
    "pipeline_overview",
    "boolean_z3",
    "region_construction",
    "reference_trace",
    "optimized_trace",
    "wang_z3",
    "verification",
    "witness_presentation",
    "optimized_mechanisms",
)
STATIC_NAMES: Final = (
    "home_preview",
    "worked_example",
    "formula",
    "generalized_sheet",
    "atomic_legend",
    "square_presentation",
    "generalized_presentation",
    "hex_presentation",
    "presentation_status",
)
IDENTITY_NAMES: Final = (
    "source_formula",
    "formula_snapshot",
    "tileset",
    "region",
    "provenance",
    "boolean_z3_summary",
    "reference_trace_manifest",
    "reference_trace",
    "reference_solution",
    "optimized_trace_manifest",
    "optimized_trace",
    "optimized_solution",
    "wang_z3_summary",
)
_ARTIFACT_FIELDS = frozenset({"path", "sha256", "media_type"})
_ANIMATION_FIELDS = frozenset(
    {
        "owner",
        "semantic_label",
        "caption",
        "alt_text",
        "source_contract",
        "source_sha256",
        "producer",
        "validator",
        "compositor",
        "scope",
        "animation",
        "fallback",
        "contact_sheet",
        "frames",
    }
)
_STATIC_FIELDS = frozenset(
    {
        "owner",
        "semantic_label",
        "caption",
        "alt_text",
        "source_contract",
        "source_sha256",
        "producer",
        "validator",
        "compositor",
        "artifact",
    }
)
_ANIMATION_POLICY: Final = {
    "pipeline_overview": ("/pipeline/", "observed"),
    "boolean_z3": ("/components/boolean-z3/", "encoding-order"),
    "region_construction": ("/components/yang-zhang/", "canonical-construction"),
    "reference_trace": ("/components/reference-solver/", "observed"),
    "optimized_trace": ("/components/optimized-solver/", "observed"),
    "wang_z3": ("/components/wang-z3/", "encoding-order"),
    "verification": ("/components/verification/", "observed"),
    "witness_presentation": (
        "/components/visualization/",
        "verified-transformation",
    ),
    "optimized_mechanisms": ("/components/optimized-solver/", "didactic"),
}
_STATIC_POLICY: Final = {
    "home_preview": ("/", "observed"),
    "worked_example": ("/worked-example/", "observed"),
    "formula": ("/worked-example/", "observed"),
    "generalized_sheet": ("/components/tileset/", "canonical-construction"),
    "atomic_legend": ("/components/tileset/", "canonical-construction"),
    "square_presentation": ("/components/visualization/", "observed"),
    "generalized_presentation": (
        "/components/visualization/",
        "canonical-construction",
    ),
    "hex_presentation": (
        "/components/visualization/",
        "verified-transformation",
    ),
    "presentation_status": ("/run-dossiers/", "observed"),
}
_SELECTED_ANIMATIONS: Final = frozenset(
    {
        "pipeline_overview",
        "region_construction",
        "reference_trace",
        "optimized_trace",
    }
)
_ANIMATION_TOOLCHAIN: Final = {
    "pipeline_overview": (
        "dossier.narrative_assets",
        "formats.run_dossier_v2_bundle.load_run_dossier_v2",
        "renderer.wang_narrative.render_overview_assets",
    ),
    "boolean_z3": (
        "formats.z3_encoding_summary.build_boolean_z3_summary",
        "renderer.wang_z3_summary.load_z3_encoding_summary",
        "renderer.wang_z3_summary.render_boolean_z3_assets",
    ),
    "region_construction": (
        "formats.solver_trace_snapshot.dump_solver_trace_bundle",
        "renderer.wang_snapshot.load_explainability_bundle",
        "renderer.wang_algorithm_animation.render_builder_assets",
    ),
    "reference_trace": (
        "formats.solver_trace_snapshot.dump_solver_trace_bundle",
        "renderer.wang_trace.load_trace_bundle",
        "renderer.wang_trace_render.render_trace_assets",
    ),
    "optimized_trace": (
        "formats.solver_trace_snapshot.dump_solver_trace_bundle",
        "renderer.wang_trace.load_trace_bundle",
        "renderer.wang_trace_render.render_trace_assets",
    ),
    "wang_z3": (
        "formats.z3_encoding_summary.build_wang_z3_summary",
        "renderer.wang_z3_summary.load_z3_encoding_summary",
        "renderer.wang_z3_summary.render_wang_z3_assets",
    ),
    "verification": (
        "formats.run_dossier_v2_builder.build_run_dossier_v2",
        "formats.run_dossier_v2.validate_run_dossier_v2+renderer.wang_narrative._load_verification",
        "renderer.wang_narrative.render_verification_assets",
    ),
    "witness_presentation": (
        "formats.solver_trace_snapshot.dump_solver_trace_bundle",
        "renderer.wang_square.load_wang_presentation+renderer.wang_generalized.recognize_generalized_tiles+renderer.wang_hex_port.check_square_to_hex",
        "renderer.wang_narrative.render_witness_assets",
    ),
    "optimized_mechanisms": (
        "renderer/data/optimized-mechanisms-v1.json",
        "renderer.wang_algorithm_animation._load_optimizations",
        "renderer.wang_algorithm_animation.render_optimized_assets",
    ),
}
_STATIC_TOOLCHAIN: Final = {
    "home_preview": (
        "dossier.narrative_assets",
        "formats.run_dossier_v2_bundle.load_run_dossier_v2",
        "renderer.wang_narrative.render_overview_assets",
    ),
    "worked_example": (
        "dossier.narrative_assets",
        "formats.run_dossier_v2_bundle.load_run_dossier_v2",
        "renderer.wang_narrative.render_overview_assets",
    ),
    "formula": (
        "dossier.narrative_assets",
        "renderer.wang_snapshot.load_explainability_bundle",
        "renderer.wang_snapshot.render_pipeline_snapshot",
    ),
    "generalized_sheet": (
        "dossier.narrative_assets",
        "renderer.wang_snapshot.load_explainability_bundle+renderer.wang_generalized.check_canonical_atomic_tileset",
        "renderer.wang_narrative.render_generalized_assets",
    ),
    "atomic_legend": (
        "dossier.narrative_assets",
        "renderer.wang_snapshot.load_explainability_bundle+renderer.wang_generalized.check_canonical_atomic_tileset",
        "renderer.wang_narrative.render_generalized_assets",
    ),
    "square_presentation": (
        "dossier.narrative_assets",
        "renderer.wang_square.load_wang_presentation",
        "renderer.wang_narrative.render_witness_assets",
    ),
    "generalized_presentation": (
        "dossier.narrative_assets",
        "renderer.wang_square.load_wang_presentation+renderer.wang_generalized.recognize_generalized_tiles",
        "renderer.wang_narrative.render_witness_assets",
    ),
    "hex_presentation": (
        "dossier.narrative_assets",
        "renderer.wang_square.load_wang_presentation+renderer.wang_hex_port.check_square_to_hex",
        "renderer.wang_narrative.render_witness_assets",
    ),
    "presentation_status": (
        "dossier.narrative_assets",
        "formats.run_dossier_v2_bundle.load_run_dossier_v2",
        "renderer.wang_narrative.render_presentation_status",
    ),
}


def verification_source_sha256(run: dict[str, object]) -> str:
    return hashlib.sha256(
        _encode_document(
            {
                "verification": run["verification"],
                "agreement": run["agreement"],
            }
        )
    ).hexdigest()


def composite_source_sha256(values: dict[str, str]) -> str:
    return hashlib.sha256(_encode_document(values)).hexdigest()


def generalized_source_sha256(tileset_sha256: str) -> str:
    return composite_source_sha256(
        {
            "tileset": tileset_sha256,
            "generalized_specification": GENERALIZED_SPECIFICATION_SHA256,
        }
    )


def generalized_presentation_source_sha256(solution_sha256: str) -> str:
    return composite_source_sha256(
        {
            "solution": solution_sha256,
            "generalized_specification": GENERALIZED_SPECIFICATION_SHA256,
        }
    )


def hex_presentation_source_sha256(solution_sha256: str) -> str:
    return composite_source_sha256(
        {
            "solution": solution_sha256,
            "transformation": HEX_TRANSFORMATION_ID,
        }
    )


def witness_presentation_source_sha256(solution_sha256: str) -> str:
    return composite_source_sha256(
        {
            "solution": solution_sha256,
            "generalized_specification": GENERALIZED_SPECIFICATION_SHA256,
            "transformation": HEX_TRANSFORMATION_ID,
        }
    )


def pipeline_source_sha256(
    identities: dict[str, str | None], run: dict[str, object]
) -> str:
    sources = {
        name: digest for name, digest in identities.items() if digest is not None
    }
    sources["verification"] = verification_source_sha256(run)
    sources["generalized_specification"] = GENERALIZED_SPECIFICATION_SHA256
    sources["square_to_hex_transformation"] = HEX_TRANSFORMATION_ID
    return composite_source_sha256(sources)


def _artifact(
    value: object,
    path: str,
    root: Path,
    *,
    media_type: str,
) -> str:
    artifact = _require_object(value, path)
    _require_exact_fields(artifact, _ARTIFACT_FIELDS, path)
    relative = _relative_path(artifact["path"], f"{path}.path")
    _require_sha256(artifact["sha256"], f"{path}.sha256")
    _require_literal(artifact["media_type"], media_type, f"{path}.media_type")
    try:
        unresolved = root / relative
        cursor = root
        for component in Path(relative).parts:
            cursor /= component
            if cursor.is_symlink():
                raise PipelineSnapshotError(f"{path}.path: symlinks are forbidden")
        candidate = unresolved.resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise PipelineSnapshotError(f"{path}.path: escapes asset bundle")
        encoded = candidate.read_bytes()
    except PipelineSnapshotError:
        raise
    except OSError as error:
        raise PipelineSnapshotError(f"{path}.path: cannot read artifact: {error}") from error
    if hashlib.sha256(encoded).hexdigest() != artifact["sha256"]:
        raise PipelineSnapshotError(f"{path}.sha256: does not match file")
    return relative


def _metadata(
    value: dict[str, object],
    path: str,
    policy: tuple[str, str],
    toolchain: tuple[str, str, str],
) -> None:
    owner, semantic_label = policy
    _require_literal(value["owner"], owner, f"{path}.owner")
    label = _nonempty_string(value["semantic_label"], f"{path}.semantic_label")
    if label not in SEMANTIC_LABELS or label != semantic_label:
        raise PipelineSnapshotError(f"{path}.semantic_label: disagrees with policy")
    for name in ("caption", "alt_text", "source_contract"):
        _nonempty_string(value[name], f"{path}.{name}")
    for name, expected in zip(
        ("producer", "validator", "compositor"), toolchain, strict=True
    ):
        _require_literal(value[name], expected, f"{path}.{name}")
    _require_sha256(value["source_sha256"], f"{path}.source_sha256")


def validate_narrative_assets(
    document: object,
    manifest_path: str | Path,
) -> dict[str, set[str]]:
    manifest = _require_object(document, "$")
    _require_exact_fields(
        manifest,
        frozenset(
            {
                "schema",
                "product",
                "case",
                "identities",
                "animations",
                "statics",
                "pdf_milestones",
            }
        ),
        "$",
    )
    _require_literal(manifest["schema"], SCHEMA_NAME, "$.schema")
    product = _nonempty_string(manifest["product"], "$.product")
    if product not in PRODUCTS:
        raise PipelineSnapshotError("$.product: is unsupported")
    case = _require_object(manifest["case"], "$.case")
    _require_exact_fields(
        case, frozenset({"id", "expected_status", "source_sha256"}), "$.case"
    )
    _nonempty_string(case["id"], "$.case.id")
    status = _nonempty_string(case["expected_status"], "$.case.expected_status")
    if status not in {"sat", "unsat"}:
        raise PipelineSnapshotError("$.case.expected_status: is unsupported")
    _require_sha256(case["source_sha256"], "$.case.source_sha256")
    if product == "canonical-pages" and case != CANONICAL_PAGES_CASE:
        raise PipelineSnapshotError(
            "$.case: canonical-pages is reserved for the canonical SAT run"
        )

    identities = _require_object(manifest["identities"], "$.identities")
    _require_exact_fields(identities, frozenset(IDENTITY_NAMES), "$.identities")
    for name in IDENTITY_NAMES:
        value = identities[name]
        if value is None:
            if status == "sat" or not name.endswith("_solution"):
                raise PipelineSnapshotError(f"$.identities.{name}: may not be null")
        else:
            _require_sha256(value, f"$.identities.{name}")

    root = Path(manifest_path).parent.resolve(strict=True)
    animations = _require_object(manifest["animations"], "$.animations")
    _require_exact_fields(animations, frozenset(ANIMATION_NAMES), "$.animations")
    owned_paths: set[str] = set()
    frame_paths: dict[str, tuple[str, ...]] = {}
    for name in ANIMATION_NAMES:
        path = f"$.animations.{name}"
        raw = animations[name]
        if raw is None:
            if name != "witness_presentation" or status != "unsat":
                raise PipelineSnapshotError(f"{path}: is required")
            frame_paths[name] = ()
            continue
        record = _require_object(raw, path)
        _require_exact_fields(record, _ANIMATION_FIELDS, path)
        _metadata(record, path, _ANIMATION_POLICY[name], _ANIMATION_TOOLCHAIN[name])
        scope = _require_object(record["scope"], f"{path}.scope")
        _require_exact_fields(
            scope, frozenset({"complete", "selected", "truncated"}), f"{path}.scope"
        )
        if not _boolean(scope["complete"], f"{path}.scope.complete"):
            raise PipelineSnapshotError(f"{path}.scope.complete: must remain true")
        selected = _boolean(scope["selected"], f"{path}.scope.selected")
        if selected != (name in _SELECTED_ANIMATIONS):
            raise PipelineSnapshotError(f"{path}.scope.selected: disagrees with policy")
        if _boolean(scope["truncated"], f"{path}.scope.truncated"):
            raise PipelineSnapshotError(f"{path}.scope.truncated: must remain false")
        animation_path = _artifact(
            record["animation"], f"{path}.animation", root, media_type="image/gif"
        )
        contact_path = _artifact(
            record["contact_sheet"],
            f"{path}.contact_sheet",
            root,
            media_type="image/png",
        )
        raw_frames = record["frames"]
        if type(raw_frames) is not list or not raw_frames:
            raise PipelineSnapshotError(f"{path}.frames: must be a nonempty array")
        ordered_paths = tuple(
            _artifact(item, f"{path}.frames[{index}]", root, media_type="image/png")
            for index, item in enumerate(raw_frames)
        )
        paths = set(ordered_paths)
        if len(paths) != len(ordered_paths):
            raise PipelineSnapshotError(f"{path}.frames: contains duplicate paths")
        fallback_path = _artifact(
            record["fallback"], f"{path}.fallback", root, media_type="image/png"
        )
        if fallback_path not in paths:
            raise PipelineSnapshotError(f"{path}.fallback: must select one frame")
        newly_owned = paths | {animation_path, contact_path}
        overlap = owned_paths & newly_owned
        if overlap:
            raise PipelineSnapshotError(f"{path}: reuses files owned by another asset")
        owned_paths.update(newly_owned)
        frame_paths[name] = ordered_paths

    statics = _require_object(manifest["statics"], "$.statics")
    _require_exact_fields(statics, frozenset(STATIC_NAMES), "$.statics")
    sat_only = {
        "home_preview",
        "worked_example",
        "square_presentation",
        "generalized_presentation",
        "hex_presentation",
    }
    for name in STATIC_NAMES:
        path = f"$.statics.{name}"
        raw = statics[name]
        if raw is None:
            allowed = (status == "unsat" and name in sat_only) or (
                status == "sat" and name == "presentation_status"
            )
            if not allowed:
                raise PipelineSnapshotError(f"{path}: is required")
            continue
        if (status == "sat" and name == "presentation_status") or (
            status == "unsat" and name in sat_only
        ):
            raise PipelineSnapshotError(f"{path}: disagrees with SAT applicability")
        record = _require_object(raw, path)
        _require_exact_fields(record, _STATIC_FIELDS, path)
        _metadata(record, path, _STATIC_POLICY[name], _STATIC_TOOLCHAIN[name])
        artifact_path = _artifact(
            record["artifact"], f"{path}.artifact", root, media_type="image/png"
        )
        if artifact_path in owned_paths:
            raise PipelineSnapshotError(f"{path}: reuses a file owned by another asset")
        owned_paths.add(artifact_path)

    milestones = _require_object(manifest["pdf_milestones"], "$.pdf_milestones")
    _require_exact_fields(
        milestones,
        frozenset(
            {
                "selector",
                "region_construction",
                "reference_trace",
                "optimized_trace",
                "end_to_end",
            }
        ),
        "$.pdf_milestones",
    )
    _require_literal(
        milestones["selector"], "semantic-milestones-v1", "$.pdf_milestones.selector"
    )
    milestone_sources = {
        "region_construction": "region_construction",
        "reference_trace": "reference_trace",
        "optimized_trace": "optimized_trace",
        "end_to_end": "pipeline_overview",
    }
    for name, animation_name in milestone_sources.items():
        values = milestones[name]
        if type(values) is not list or not values:
            raise PipelineSnapshotError(f"$.pdf_milestones.{name}: must be nonempty")
        if any(type(value) is not str for value in values):
            raise PipelineSnapshotError(f"$.pdf_milestones.{name}: paths must be strings")
        if tuple(values) != frame_paths[animation_name]:
            raise PipelineSnapshotError(
                f"$.pdf_milestones.{name}: must exactly preserve the shared frame order"
            )
        if any(not value.endswith(".png") for value in values):
            raise PipelineSnapshotError(f"$.pdf_milestones.{name}: GIF is forbidden")
    return frame_paths


def load_narrative_assets(
    manifest_path: str | Path,
    run_document: dict[str, object],
) -> dict[str, object]:
    validate_run_dossier_v2(run_document)
    path = Path(manifest_path)
    if path.is_symlink():
        raise PipelineSnapshotError("narrative manifest may not be a symlink")
    try:
        document = _load_json_bytes(path.read_bytes(), str(path))
    except OSError as error:
        raise PipelineSnapshotError(f"cannot read narrative manifest: {error}") from error
    validate_narrative_assets(document, path)
    if document["case"] != {
        "id": run_document["case"]["id"],
        "expected_status": run_document["case"]["expected_status"],
        "source_sha256": run_document["source"]["sha256"],
    }:
        raise PipelineSnapshotError("narrative case identity disagrees with run")
    expected_identities = {
        "source_formula": run_document["source"]["sha256"],
        "formula_snapshot": run_document["reduction"]["formula_sha256"],
        "tileset": run_document["reduction"]["tileset_sha256"],
        "region": run_document["reduction"]["region_sha256"],
        "provenance": run_document["reduction"]["provenance_sha256"],
        "boolean_z3_summary": run_document["boolean_z3"]["encoding_summary_sha256"],
        "reference_trace_manifest": run_document["reference"]["trace"]["manifest_sha256"],
        "reference_trace": run_document["reference"]["trace"]["trace_sha256"],
        "reference_solution": run_document["reference"]["solution_sha256"],
        "optimized_trace_manifest": run_document["optimized"]["trace"]["manifest_sha256"],
        "optimized_trace": run_document["optimized"]["trace"]["trace_sha256"],
        "optimized_solution": run_document["optimized"]["solution_sha256"],
        "wang_z3_summary": run_document["wang_z3"]["encoding_summary_sha256"],
    }
    if document["identities"] != expected_identities:
        raise PipelineSnapshotError("narrative component identities disagree with run")
    animations = document["animations"]
    pipeline_digest = pipeline_source_sha256(expected_identities, run_document)
    generalized_digest = generalized_source_sha256(
        expected_identities["tileset"]
    )
    expected_sources = {
        "pipeline_overview": (
            "wang-run-dossier-v2#named-components",
            pipeline_digest,
        ),
        "boolean_z3": ("z3-encoding-summary-v1", expected_identities["boolean_z3_summary"]),
        "region_construction": (
            "wang-reduction-explanation-v1",
            expected_identities["provenance"],
        ),
        "reference_trace": (
            "wang-explain-manifest-v3",
            expected_identities["reference_trace_manifest"],
        ),
        "optimized_trace": (
            "wang-explain-manifest-v3",
            expected_identities["optimized_trace_manifest"],
        ),
        "wang_z3": ("z3-encoding-summary-v1", expected_identities["wang_z3_summary"]),
        "verification": (
            "wang-run-dossier-v2#verification",
            verification_source_sha256(run_document),
        ),
        "optimized_mechanisms": (
            "wang-optimized-mechanisms-v1",
            OPTIMIZED_MECHANISMS_SHA256,
        ),
    }
    if run_document["case"]["expected_status"] == "sat":
        expected_sources["witness_presentation"] = (
            "wang-solution-v1+wang-generalized-tiles-v1+checked-square-to-hex",
            witness_presentation_source_sha256(
                expected_identities["reference_solution"]
            ),
        )
    for name, (contract, digest) in expected_sources.items():
        record = animations[name]
        if record["source_contract"] != contract or record["source_sha256"] != digest:
            raise PipelineSnapshotError(f"narrative source {name} disagrees with run")

    solution_digest = expected_identities["reference_solution"]
    expected_static_sources = {
        "formula": (
            "cm13-formula-snapshot-v1",
            expected_identities["formula_snapshot"],
        ),
        "generalized_sheet": (
            "wang-generalized-tiles-v1+wang-tileset-snapshot-v1",
            generalized_digest,
        ),
        "atomic_legend": (
            "wang-generalized-tiles-v1+wang-tileset-snapshot-v1",
            generalized_digest,
        ),
    }
    if run_document["case"]["expected_status"] == "sat":
        assert solution_digest is not None
        expected_static_sources.update(
            {
                "home_preview": ("wang-solution-v1", solution_digest),
                "worked_example": (
                    "wang-run-dossier-v2#named-components",
                    pipeline_digest,
                ),
                "square_presentation": ("wang-solution-v1", solution_digest),
                "generalized_presentation": (
                    "wang-solution-v1+wang-generalized-tiles-v1",
                    generalized_presentation_source_sha256(solution_digest),
                ),
                "hex_presentation": (
                    "wang-solution-v1+checked-square-to-hex",
                    hex_presentation_source_sha256(solution_digest),
                ),
            }
        )
    else:
        expected_static_sources["presentation_status"] = (
            "wang-run-dossier-v2#agreement",
            verification_source_sha256(run_document),
        )
    for name, (contract, digest) in expected_static_sources.items():
        record = document["statics"][name]
        if record["source_contract"] != contract or record["source_sha256"] != digest:
            raise PipelineSnapshotError(
                f"narrative static source {name} disagrees with run"
            )
    if (
        document["product"] == "run-specific"
        and run_document["case"]["expected_status"] == "sat"
    ):
        for name in ("square", "generalized", "hex"):
            narrative_artifact = document["statics"][f"{name}_presentation"][
                "artifact"
            ]
            run_artifact = run_document["artifacts"][f"{name}_presentation"]
            expected_run_path = (
                Path("assets/narrative") / narrative_artifact["path"]
            ).as_posix()
            if (
                run_artifact is not None
                and (
                    run_artifact["path"] != expected_run_path
                    or run_artifact["sha256"] != narrative_artifact["sha256"]
                )
            ):
                raise PipelineSnapshotError(
                    f"narrative {name} presentation disagrees with run artifact"
                )
    return document
