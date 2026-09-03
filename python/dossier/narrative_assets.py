"""Generate one fixed shared-asset bundle from a validated v2 dossier."""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "renderer"
MECHANISM_SOURCE = RENDERER / "data/optimized-mechanisms-v1.json"

from formats.narrative_assets import (
    ANIMATION_NAMES,
    CANONICAL_PAGES_CASE,
    GENERALIZED_SPECIFICATION_SHA256,
    IDENTITY_NAMES,
    OPTIMIZED_MECHANISMS_SHA256,
    SCHEMA_NAME,
    STATIC_NAMES,
    composite_source_sha256,
    generalized_source_sha256,
    generalized_presentation_source_sha256,
    hex_presentation_source_sha256,
    load_narrative_assets,
    pipeline_source_sha256,
    verification_source_sha256,
    witness_presentation_source_sha256,
)
from formats.pipeline_snapshot import _encode_document, _write_atomic
from formats.run_dossier_v2 import validate_run_dossier_v2
from formats.run_dossier_v2_bundle import load_run_dossier_v2


class NarrativeAssetError(RuntimeError):
    """The downstream shared-asset pass failed before atomic installation."""


def _verification_receipts(run: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "wang-verification-receipts-v1",
        "expected_status": run["case"]["expected_status"],
        "verification": run["verification"],
        "agreement": run["agreement"],
        "source_sha256": verification_source_sha256(run),
    }


def _run_renderer(
    arguments: list[str], *, required_outputs: tuple[str, ...] = ()
) -> dict[str, Path]:
    uv = shutil.which("uv")
    if uv is None:
        raise NarrativeAssetError("uv is required to run the isolated renderer")
    try:
        completed = subprocess.run(
            [uv, "run", "--locked", "python", *arguments],
            cwd=RENDERER,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", "") or getattr(error, "stdout", "") or str(error)
        raise NarrativeAssetError(f"narrative renderer failed: {detail.strip()}") from error
    outputs: dict[str, Path] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        outputs[name] = Path(value)
    missing = tuple(name for name in required_outputs if name not in outputs)
    if missing:
        raise NarrativeAssetError(
            "narrative renderer omitted required output keys: " + ", ".join(missing)
        )
    return outputs


def _artifact(root: Path, path: Path, media_type: str) -> dict[str, str]:
    try:
        encoded = path.read_bytes()
        relative = path.relative_to(root).as_posix()
    except (OSError, ValueError) as error:
        raise NarrativeAssetError(f"cannot bind narrative artifact {path!s}: {error}") from error
    return {
        "path": relative,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "media_type": media_type,
    }


def _metadata(
    *,
    owner: str,
    semantic_label: str,
    caption: str,
    alt_text: str,
    source_contract: str,
    source_sha256: str,
    producer: str,
    validator: str,
    compositor: str,
) -> dict[str, str]:
    return {
        "owner": owner,
        "semantic_label": semantic_label,
        "caption": caption,
        "alt_text": alt_text,
        "source_contract": source_contract,
        "source_sha256": source_sha256,
        "producer": producer,
        "validator": validator,
        "compositor": compositor,
    }


def _animation_record(
    root: Path,
    directory: Path,
    fallback: Path,
    metadata: dict[str, str],
    *,
    complete: bool,
    selected: bool,
) -> dict[str, object]:
    frames = tuple(sorted(directory.glob("frame-*.png")))
    if not frames or fallback not in frames:
        raise NarrativeAssetError("renderer did not publish a selected fallback frame")
    animation = directory / "trace.gif"
    contact_sheet = directory / "contact-sheet.png"
    return {
        **metadata,
        "scope": {
            "complete": complete,
            "selected": selected,
            "truncated": False,
        },
        "animation": _artifact(root, animation, "image/gif"),
        "fallback": _artifact(root, fallback, "image/png"),
        "contact_sheet": _artifact(root, contact_sheet, "image/png"),
        "frames": [_artifact(root, frame, "image/png") for frame in frames],
    }


def _static_record(
    root: Path,
    path: Path,
    metadata: dict[str, str],
) -> dict[str, object]:
    return {**metadata, "artifact": _artifact(root, path, "image/png")}


def _run_artifact(
    run_root: Path, run: dict[str, object], name: str
) -> Path | None:
    record = run["artifacts"][name]
    if record is None:
        return None
    return run_root / record["path"]


def _identities(run: dict[str, object]) -> dict[str, str | None]:
    identities: dict[str, str | None] = {
        "source_formula": run["source"]["sha256"],
        "formula_snapshot": run["reduction"]["formula_sha256"],
        "tileset": run["reduction"]["tileset_sha256"],
        "region": run["reduction"]["region_sha256"],
        "provenance": run["reduction"]["provenance_sha256"],
        "boolean_z3_summary": run["boolean_z3"]["encoding_summary_sha256"],
        "reference_trace_manifest": run["reference"]["trace"]["manifest_sha256"],
        "reference_trace": run["reference"]["trace"]["trace_sha256"],
        "reference_solution": run["reference"]["solution_sha256"],
        "optimized_trace_manifest": run["optimized"]["trace"]["manifest_sha256"],
        "optimized_trace": run["optimized"]["trace"]["trace_sha256"],
        "optimized_solution": run["optimized"]["solution_sha256"],
        "wang_z3_summary": run["wang_z3"]["encoding_summary_sha256"],
    }
    if tuple(identities) != IDENTITY_NAMES:
        raise NarrativeAssetError("narrative identity order diverged from contract")
    return identities


def _animation_metadata(
    identities: dict[str, str | None],
    run: dict[str, object],
) -> dict[str, dict[str, str]]:
    pipeline_digest = pipeline_source_sha256(identities, run)
    mechanism_digest = hashlib.sha256(MECHANISM_SOURCE.read_bytes()).hexdigest()
    if mechanism_digest != OPTIMIZED_MECHANISMS_SHA256:
        raise NarrativeAssetError(
            "optimized mechanism source changed without a narrative contract version"
        )
    return {
        "pipeline_overview": _metadata(
            owner="/pipeline/",
            semantic_label="observed",
            caption="One validated v2 capture in fixed component order.",
            alt_text="The captured formula moves through Boolean Z3, Yang-Zhang reduction, both native solvers, Wang Z3, verification, and presentation.",
            source_contract="wang-run-dossier-v2#named-components",
            source_sha256=pipeline_digest,
            producer="dossier.narrative_assets",
            validator="formats.run_dossier_v2_bundle.load_run_dossier_v2",
            compositor="renderer.wang_narrative.render_overview_assets",
        ),
        "boolean_z3": _metadata(
            owner="/components/boolean-z3/",
            semantic_label="encoding-order",
            caption="Project-owned Boolean constraint construction and returned assignment.",
            alt_text="Four frames add Boolean variables and source-order exactly-one clauses before showing the copied result.",
            source_contract="z3-encoding-summary-v1",
            source_sha256=str(identities["boolean_z3_summary"]),
            producer="formats.z3_encoding_summary.build_boolean_z3_summary",
            validator="renderer.wang_z3_summary.load_z3_encoding_summary",
            compositor="renderer.wang_z3_summary.render_boolean_z3_assets",
        ),
        "region_construction": _metadata(
            owner="/components/yang-zhang/",
            semantic_label="canonical-construction",
            caption="Native Yang-Zhang gadget spans accumulated over the observed region.",
            alt_text="Six frames reveal variable, forwarding, crossover, and clause gadget spans on the same region.",
            source_contract="wang-reduction-explanation-v1",
            source_sha256=str(identities["provenance"]),
            producer="formats.solver_trace_snapshot.dump_solver_trace_bundle",
            validator="renderer.wang_snapshot.load_explainability_bundle",
            compositor="renderer.wang_algorithm_animation.render_builder_assets",
        ),
        "reference_trace": _metadata(
            owner="/components/reference-solver/",
            semantic_label="observed",
            caption="Selected semantic milestones from the complete reference trace.",
            alt_text="Observed reference domain states at root, propagation, decision, search, and result milestones.",
            source_contract="wang-explain-manifest-v3",
            source_sha256=str(identities["reference_trace_manifest"]),
            producer="formats.solver_trace_snapshot.dump_solver_trace_bundle",
            validator="renderer.wang_trace.load_trace_bundle",
            compositor="renderer.wang_trace_render.render_trace_assets",
        ),
        "optimized_trace": _metadata(
            owner="/components/optimized-solver/",
            semantic_label="observed",
            caption="Selected semantic milestones from the complete optimized trace.",
            alt_text="Observed optimized domain states at root, propagation, decision, search, and result milestones.",
            source_contract="wang-explain-manifest-v3",
            source_sha256=str(identities["optimized_trace_manifest"]),
            producer="formats.solver_trace_snapshot.dump_solver_trace_bundle",
            validator="renderer.wang_trace.load_trace_bundle",
            compositor="renderer.wang_trace_render.render_trace_assets",
        ),
        "wang_z3": _metadata(
            owner="/components/wang-z3/",
            semantic_label="encoding-order",
            caption="Project-owned Wang edge-term construction and returned model.",
            alt_text="Five frames add edge terms, shared internal edges, tile relations, boundaries, and the copied result.",
            source_contract="z3-encoding-summary-v1",
            source_sha256=str(identities["wang_z3_summary"]),
            producer="formats.z3_encoding_summary.build_wang_z3_summary",
            validator="renderer.wang_z3_summary.load_z3_encoding_summary",
            compositor="renderer.wang_z3_summary.render_wang_z3_assets",
        ),
        "verification": _metadata(
            owner="/components/verification/",
            semantic_label="observed",
            caption="The six named independent checker records from the captured run.",
            alt_text="Six frames report Boolean, native, and Wang Z3 witness checks without rerunning a verifier.",
            source_contract="wang-run-dossier-v2#verification",
            source_sha256=verification_source_sha256(run),
            producer="formats.run_dossier_v2_builder.build_run_dossier_v2",
            validator="formats.run_dossier_v2.validate_run_dossier_v2+renderer.wang_narrative._load_verification",
            compositor="renderer.wang_narrative.render_verification_assets",
        ),
        "witness_presentation": _metadata(
            owner="/components/visualization/",
            semantic_label="verified-transformation",
            caption="Verified square witness, exact generalized overlay, and checked hex port.",
            alt_text="Four frames move from the verified square witness through generalized recognition to the checked hex presentation.",
            source_contract="wang-solution-v1+wang-generalized-tiles-v1+checked-square-to-hex",
            source_sha256=witness_presentation_source_sha256(
                str(identities["reference_solution"])
            ),
            producer="formats.solver_trace_snapshot.dump_solver_trace_bundle",
            validator="renderer.wang_square.load_wang_presentation+renderer.wang_generalized.recognize_generalized_tiles+renderer.wang_hex_port.check_square_to_hex",
            compositor="renderer.wang_narrative.render_witness_assets",
        ),
        "optimized_mechanisms": _metadata(
            owner="/components/optimized-solver/",
            semantic_label="didactic",
            caption="The six retained serial mechanisms, including the lazy MRV index.",
            alt_text="Seven didactic frames contrast the reference baseline with six measured optimized mechanisms.",
            source_contract="wang-optimized-mechanisms-v1",
            source_sha256=mechanism_digest,
            producer="renderer/data/optimized-mechanisms-v1.json",
            validator="renderer.wang_algorithm_animation._load_optimizations",
            compositor="renderer.wang_algorithm_animation.render_optimized_assets",
        ),
    }


def _static_metadata(
    identities: dict[str, str | None],
    run: dict[str, object],
) -> dict[str, dict[str, str]]:
    generalized_digest = generalized_source_sha256(str(identities["tileset"]))
    solution_digest = str(identities["reference_solution"])
    common = {"producer": "dossier.narrative_assets"}
    return {
        "home_preview": _metadata(
            owner="/",
            semantic_label="observed",
            caption="Selected verified SAT square output for the captured instance.",
            alt_text="A compact square Wang witness preview for the captured SAT source.",
            source_contract="wang-solution-v1",
            source_sha256=solution_digest,
            validator="formats.run_dossier_v2_bundle.load_run_dossier_v2",
            compositor="renderer.wang_narrative.render_overview_assets",
            **common,
        ),
        "worked_example": _metadata(
            owner="/worked-example/",
            semantic_label="observed",
            caption="Static t0 through tn component milestones for one SAT run.",
            alt_text="Eight static panels follow the captured source from formula to checked presentation.",
            source_contract="wang-run-dossier-v2#named-components",
            source_sha256=pipeline_source_sha256(identities, run),
            validator="formats.run_dossier_v2_bundle.load_run_dossier_v2",
            compositor="renderer.wang_narrative.render_overview_assets",
            **common,
        ),
        "formula": _metadata(
            owner="/worked-example/",
            semantic_label="observed",
            caption="Parsed formula snapshot for the named canonical source.",
            alt_text="The parsed CM1-in-3 formula and its source-order clauses.",
            source_contract="cm13-formula-snapshot-v1",
            source_sha256=str(identities["formula_snapshot"]),
            validator="renderer.wang_snapshot.load_explainability_bundle",
            compositor="renderer.wang_snapshot.render_pipeline_snapshot",
            **common,
        ),
        "generalized_sheet": _metadata(
            owner="/components/tileset/",
            semantic_label="canonical-construction",
            caption="The exact 14 generalized tiles decomposed into 23 positional atomic IDs.",
            alt_text="A sheet of fourteen Yang-Zhang generalized tiles with internal seams and atomic identifiers.",
            source_contract="wang-generalized-tiles-v1+wang-tileset-snapshot-v1",
            source_sha256=generalized_digest,
            validator="renderer.wang_snapshot.load_explainability_bundle+renderer.wang_generalized.check_canonical_atomic_tileset",
            compositor="renderer.wang_narrative.render_generalized_assets",
            **common,
        ),
        "atomic_legend": _metadata(
            owner="/components/tileset/",
            semantic_label="canonical-construction",
            caption="All 23 atomic IDs with symbolic paper colors and generalized roles.",
            alt_text="A semantic legend for twenty-three positional Wang tiles and their edge colors.",
            source_contract="wang-generalized-tiles-v1+wang-tileset-snapshot-v1",
            source_sha256=generalized_digest,
            validator="renderer.wang_snapshot.load_explainability_bundle+renderer.wang_generalized.check_canonical_atomic_tileset",
            compositor="renderer.wang_narrative.render_generalized_assets",
            **common,
        ),
        "square_presentation": _metadata(
            owner="/components/visualization/",
            semantic_label="observed",
            caption="The independently verified square witness with atomic IDs and boundaries.",
            alt_text="The complete square Wang witness for the captured SAT source.",
            source_contract="wang-solution-v1",
            source_sha256=solution_digest,
            validator="renderer.wang_square.load_wang_presentation",
            compositor="renderer.wang_narrative.render_witness_assets",
            **common,
        ),
        "generalized_presentation": _metadata(
            owner="/components/visualization/",
            semantic_label="canonical-construction",
            caption="Exact generalized contours over the same verified square witness.",
            alt_text="The square witness grouped into exact Yang-Zhang generalized tile occurrences.",
            source_contract="wang-solution-v1+wang-generalized-tiles-v1",
            source_sha256=generalized_presentation_source_sha256(solution_digest),
            validator="renderer.wang_square.load_wang_presentation+renderer.wang_generalized.recognize_generalized_tiles",
            compositor="renderer.wang_narrative.render_witness_assets",
            **common,
        ),
        "hex_presentation": _metadata(
            owner="/components/visualization/",
            semantic_label="verified-transformation",
            caption="The checked Basire/Culik square-to-hex port of the same witness.",
            alt_text="A pointy-top hex presentation preserving the square witness cells, edges, and boundary.",
            source_contract="wang-solution-v1+checked-square-to-hex",
            source_sha256=hex_presentation_source_sha256(solution_digest),
            validator="renderer.wang_square.load_wang_presentation+renderer.wang_hex_port.check_square_to_hex",
            compositor="renderer.wang_narrative.render_witness_assets",
            **common,
        ),
        "presentation_status": _metadata(
            owner="/run-dossiers/",
            semantic_label="observed",
            caption="UNSAT has no witness-only presentation artifacts.",
            alt_text="A notice that square, generalized, and hex witness views are not applicable to the UNSAT run.",
            source_contract="wang-run-dossier-v2#agreement",
            source_sha256=verification_source_sha256(run),
            validator="formats.run_dossier_v2_bundle.load_run_dossier_v2",
            compositor="renderer.wang_narrative.render_presentation_status",
            **common,
        ),
    }


def _install_directory(staging: Path, destination: Path) -> None:
    os.replace(staging, destination)


def attach_narrative_assets(
    run: dict[str, object],
    dossier_root: str | Path,
    manifest_path: str | Path,
) -> dict[str, object]:
    """Bind selected milestones and the three reserved static presentations."""
    updated = copy.deepcopy(run)
    root = Path(dossier_root).resolve()
    manifest_file = Path(manifest_path).resolve()
    manifest = load_narrative_assets(manifest_file, updated)
    if manifest["product"] != "run-specific":
        raise NarrativeAssetError("only run-specific assets can be attached to run.json")
    for solver, animation_name in (
        ("reference", "reference_trace"),
        ("optimized", "optimized_trace"),
    ):
        selected = len(manifest["animations"][animation_name]["frames"])
        updated[solver]["trace"]["selection"] = {
            "performed": True,
            "selected_event_count": selected,
        }

    if updated["case"]["expected_status"] == "sat":
        specifications = {
            "square": (
                "observed verified square witness presentation",
                "observed",
            ),
            "generalized": (
                "exact generalized overlay on the verified square witness",
                "canonical-construction",
            ),
            "hex": (
                "checked square-to-hex witness presentation",
                "verified-transformation",
            ),
        }
        for name, (role, semantics) in specifications.items():
            static = manifest["statics"][f"{name}_presentation"]["artifact"]
            absolute = manifest_file.parent / static["path"]
            try:
                relative = absolute.relative_to(root).as_posix()
            except ValueError as error:
                raise NarrativeAssetError(
                    f"{name} presentation lies outside dossier"
                ) from error
            artifact_name = f"{name}_presentation"
            updated["artifacts"][artifact_name] = {
                "path": relative,
                "sha256": static["sha256"],
                "media_type": "image/png",
                "schema": None,
                "role": role,
                "semantics": semantics,
                "form": "static",
                "source_sha256": updated["source"]["sha256"],
            }
            updated["presentation"][name]["artifact"] = artifact_name
    validate_run_dossier_v2(updated)
    return updated


def generate_narrative_assets(
    run_path: str | Path,
    output_directory: str | Path,
    *,
    product: str = "run-specific",
) -> Path:
    """Render one fixed asset pass and atomically install its closed manifest."""
    run_file = Path(run_path).resolve()
    run = load_run_dossier_v2(run_file)
    if product not in {"run-specific", "canonical-pages"}:
        raise NarrativeAssetError(f"unsupported asset product: {product}")
    if product == "canonical-pages" and {
        "id": run["case"]["id"],
        "expected_status": run["case"]["expected_status"],
        "source_sha256": run["source"]["sha256"],
    } != CANONICAL_PAGES_CASE:
        raise NarrativeAssetError(
            "canonical-pages is reserved for the canonical pipeline SAT case"
        )
    destination = Path(output_directory).resolve()
    if destination.exists():
        raise NarrativeAssetError(f"output directory already exists: {destination!s}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        run_root = run_file.parent
        reference_manifest = _run_artifact(run_root, run, "reference_trace_manifest")
        optimized_manifest = _run_artifact(run_root, run, "optimized_trace_manifest")
        boolean_summary = _run_artifact(run_root, run, "boolean_z3_summary")
        wang_summary = _run_artifact(run_root, run, "wang_z3_summary")
        if None in (reference_manifest, optimized_manifest, boolean_summary, wang_summary):
            raise NarrativeAssetError("v2 run is missing a required narrative source")

        formula_path = staging / "formula.png"
        _run_renderer(
            ["wang_square.py", str(reference_manifest), str(formula_path), "--view", "formula"]
        )
        boolean_outputs = _run_renderer(
            ["wang_z3_summary.py", str(boolean_summary), str(staging / "boolean-z3")],
            required_outputs=("fallback",),
        )
        region_outputs = _run_renderer(
            [
                "wang_algorithm_animation.py",
                "builder",
                str(reference_manifest),
                str(staging / "region-construction"),
            ],
            required_outputs=("fallback",),
        )
        reference_outputs = _run_renderer(
            [
                "wang_trace_render.py",
                str(reference_manifest),
                str(staging / "reference-trace"),
                "--max-frames",
                "10",
            ],
            required_outputs=("fallback",),
        )
        optimized_outputs = _run_renderer(
            [
                "wang_trace_render.py",
                str(optimized_manifest),
                str(staging / "optimized-trace"),
                "--max-frames",
                "10",
            ],
            required_outputs=("fallback",),
        )
        wang_outputs = _run_renderer(
            ["wang_z3_summary.py", str(wang_summary), str(staging / "wang-z3")],
            required_outputs=("fallback",),
        )
        verification_receipts = staging / ".verification-receipts.json"
        _write_atomic(
            verification_receipts,
            _encode_document(_verification_receipts(run)),
        )
        verification_outputs = _run_renderer(
            [
                "wang_narrative.py",
                "verification",
                str(verification_receipts),
                str(staging / "verification"),
            ],
            required_outputs=("fallback",),
        )
        verification_receipts.unlink()
        mechanism_outputs = _run_renderer(
            ["wang_algorithm_animation.py", "optimized", str(staging / "optimized-mechanisms")],
            required_outputs=("fallback",),
        )
        generalized_outputs = _run_renderer(
            [
                "wang_narrative.py",
                "generalized",
                str(reference_manifest),
                str(staging / "generalized-tiles"),
            ],
            required_outputs=("spec_sha256",),
        )
        if str(generalized_outputs.get("spec_sha256", "")) != GENERALIZED_SPECIFICATION_SHA256:
            raise NarrativeAssetError(
                "renderer generalized specification disagrees with the narrative contract"
            )

        status = run["case"]["expected_status"]
        witness_outputs: dict[str, Path] | None = None
        if status == "sat":
            solution = _run_artifact(run_root, run, "reference_solution")
            if solution is None:
                raise NarrativeAssetError("SAT narrative assets require a reference solution")
            witness_outputs = _run_renderer(
                ["wang_narrative.py", "witness", str(solution), str(staging / "presentation")],
                required_outputs=("square", "generalized", "hex", "fallback"),
            )
            presentation_source = witness_outputs["hex"]
            home_source = witness_outputs["square"]
        else:
            presentation_source = staging / "presentation-status.png"
            _run_renderer(
                ["wang_narrative.py", "status", "unsat", str(presentation_source)]
            )
            home_source = presentation_source

        overview_arguments = [
            "wang_narrative.py",
            "overview",
            str(staging / "pipeline-overview"),
            str(formula_path),
            str(boolean_outputs["fallback"]),
            str(region_outputs["fallback"]),
            str(reference_outputs["fallback"]),
            str(optimized_outputs["fallback"]),
            str(wang_outputs["fallback"]),
            str(verification_outputs["fallback"]),
            str(presentation_source),
            "--home-source",
            str(home_source),
        ]
        if status == "unsat":
            overview_arguments.append("--omit-sat-story")
        overview_required = ("fallback",)
        if status == "sat":
            overview_required += ("home_preview", "worked_example")
        overview_outputs = _run_renderer(
            overview_arguments, required_outputs=overview_required
        )

        identities = _identities(run)
        animation_metadata = _animation_metadata(identities, run)
        animation_directories = {
            "pipeline_overview": (staging / "pipeline-overview", overview_outputs),
            "boolean_z3": (staging / "boolean-z3", boolean_outputs),
            "region_construction": (staging / "region-construction", region_outputs),
            "reference_trace": (staging / "reference-trace", reference_outputs),
            "optimized_trace": (staging / "optimized-trace", optimized_outputs),
            "wang_z3": (staging / "wang-z3", wang_outputs),
            "verification": (staging / "verification", verification_outputs),
            "witness_presentation": (
                None if witness_outputs is None else staging / "presentation",
                witness_outputs,
            ),
            "optimized_mechanisms": (staging / "optimized-mechanisms", mechanism_outputs),
        }
        animations: dict[str, dict[str, object] | None] = {}
        for name in ANIMATION_NAMES:
            directory, outputs = animation_directories[name]
            if directory is None or outputs is None:
                animations[name] = None
                continue
            animations[name] = _animation_record(
                staging,
                directory,
                outputs["fallback"],
                animation_metadata[name],
                complete=True,
                selected=name
                in {
                    "pipeline_overview",
                    "region_construction",
                    "reference_trace",
                    "optimized_trace",
                },
            )

        static_metadata = _static_metadata(identities, run)
        static_paths: dict[str, Path | None] = {
            "home_preview": overview_outputs.get("home_preview"),
            "worked_example": overview_outputs.get("worked_example"),
            "formula": formula_path,
            "generalized_sheet": staging / "generalized-tiles/sheet.png",
            "atomic_legend": staging / "generalized-tiles/atomic-legend.png",
            "square_presentation": None if witness_outputs is None else witness_outputs["square"],
            "generalized_presentation": None
            if witness_outputs is None
            else witness_outputs["generalized"],
            "hex_presentation": None if witness_outputs is None else witness_outputs["hex"],
            "presentation_status": presentation_source if status == "unsat" else None,
        }
        statics: dict[str, dict[str, object] | None] = {
            name: None
            if static_paths[name] is None
            else _static_record(staging, static_paths[name], static_metadata[name])
            for name in STATIC_NAMES
        }
        manifest = {
            "schema": SCHEMA_NAME,
            "product": product,
            "case": {
                "id": run["case"]["id"],
                "expected_status": status,
                "source_sha256": run["source"]["sha256"],
            },
            "identities": identities,
            "animations": animations,
            "statics": statics,
            "pdf_milestones": {
                "selector": "semantic-milestones-v1",
                "region_construction": [
                    item["path"] for item in animations["region_construction"]["frames"]
                ],
                "reference_trace": [
                    item["path"] for item in animations["reference_trace"]["frames"]
                ],
                "optimized_trace": [
                    item["path"] for item in animations["optimized_trace"]["frames"]
                ],
                "end_to_end": [
                    item["path"] for item in animations["pipeline_overview"]["frames"]
                ],
            },
        }
        manifest_path = staging / "manifest.json"
        _write_atomic(manifest_path, _encode_document(manifest))
        load_narrative_assets(manifest_path, run)
        _install_directory(staging, destination)
        return destination / "manifest.json"
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="generate one closed shared narrative asset bundle from a v2 run"
    )
    parser.add_argument("run", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument(
        "--product",
        choices=("run-specific", "canonical-pages"),
        default="run-specific",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        manifest = generate_narrative_assets(
            args.run, args.output_directory, product=args.product
        )
    except (NarrativeAssetError, OSError, ValueError) as error:
        parser.error(str(error))
    print(f"manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
