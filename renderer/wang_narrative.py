"""Fixed narrative compositions built from already validated pipeline outputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from wang_animation import AnimationOutputs, write_animation_assets
from wang_explain import (
    EXPLAIN_ACTIVE_RGB,
    EXPLAIN_MUTED_RGB,
    EXPLAIN_PANEL_RGB,
    EXPLAIN_TEXT_RGB,
    draw_explain_heading,
    explain_font,
    square_inactive_tile,
    square_explain_tile,
)
from wang_generalized_render import (
    compose_atomic_semantic_legend,
    compose_generalized_overlay,
    compose_generalized_sheet,
)
from wang_generalized import generalized_specification_sha256
from wang_hex_port import WangSquareRenderError, check_square_to_hex, reduce_square_to_hex
from wang_snapshot import ExplainabilityBundle, load_explainability_bundle
from wang_square import (
    _build_palette_from_edges,
    _compose_wang_hex_explain,
    _compose_wang_square_explain,
    _save_png_atomic,
    load_wang_presentation,
)


_PIPELINE_LABELS = (
    "CM1-in-3 formula",
    "Boolean Z3",
    "Yang-Zhang reduction",
    "Reference solver",
    "Optimized solver",
    "Wang Z3",
    "Independent verification",
    "Square / generalized / hex",
)
_CHECKS = (
    (
        "boolean_z3_assignment",
        "Boolean assignment",
        "oracles.witness_check.is_valid_assignment",
    ),
    ("reference_tiling", "Reference tiling", "oracles.tiling_check.is_valid_tiling"),
    (
        "reference_assignment",
        "Reference assignment",
        "oracles.witness_check.is_valid_assignment",
    ),
    ("optimized_tiling", "Optimized tiling", "oracles.tiling_check.is_valid_tiling"),
    (
        "optimized_assignment",
        "Optimized assignment",
        "oracles.witness_check.is_valid_assignment",
    ),
    ("wang_z3_tiling", "Wang Z3 tiling", "oracles.tiling_check.is_valid_tiling"),
)


@dataclass(frozen=True, slots=True)
class WitnessOutputs:
    square: Path
    generalized: Path
    hex: Path
    animation: AnimationOutputs


@dataclass(frozen=True, slots=True)
class GeneralizedOutputs:
    sheet: Path
    legend: Path


@dataclass(frozen=True, slots=True)
class OverviewOutputs:
    animation: AnimationOutputs
    home_preview: Path | None
    worked_example: Path | None


def _save_image(image: Image.Image, path: Path) -> None:
    if image.mode != "RGB":
        raise WangSquareRenderError("narrative output must be RGB")
    _save_png_atomic(np.asarray(image, dtype=np.uint8), path)


def _load_image(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            source.load()
            return source.convert("RGB")
    except (OSError, ValueError) as error:
        raise WangSquareRenderError(
            f"cannot load narrative source image {path!s}: {error}"
        ) from error


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = image.copy()
    fitted.thumbnail(size, resample=Image.Resampling.LANCZOS)
    return fitted


def _encoded(document: dict[str, object]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")


def _manifest_context(
    path: str | Path,
) -> tuple[ExplainabilityBundle, dict[str, str | None]]:
    source = Path(path)
    bundle = load_explainability_bundle(source)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WangSquareRenderError(
            f"cannot load explainability identity manifest {source!s}: {error}"
        ) from error
    artifacts = document.get("artifacts") if type(document) is dict else None
    if type(artifacts) is not dict or not {
        "formula", "tileset", "region", "reduction", "solution"
    } <= set(artifacts):
        raise WangSquareRenderError(
            "verification requires an explainability manifest with reduction and solution identities"
        )
    identities: dict[str, str | None] = {
        "source_formula": bundle.source_formula_sha256,
    }
    for target, artifact_name in (
        ("formula_snapshot", "formula"),
        ("tileset", "tileset"),
        ("region", "region"),
        ("provenance", "reduction"),
        ("reference_solution", "solution"),
    ):
        reference = artifacts[artifact_name]
        if reference is None:
            identities[target] = None
            continue
        if type(reference) is not dict or set(reference) != {"path", "sha256", "schema"}:
            raise WangSquareRenderError(
                f"verification manifest {artifact_name} reference must be closed"
            )
        digest = reference["sha256"]
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise WangSquareRenderError(
                f"verification manifest {artifact_name} identity is invalid"
            )
        identities[target] = digest
    return bundle, identities


def _bind_solution(
    bundle: ExplainabilityBundle,
    identities: dict[str, str | None],
    path: str | Path,
):
    source = Path(path)
    try:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as error:
        raise WangSquareRenderError(f"cannot read verification solution: {error}") from error
    if digest != identities["reference_solution"]:
        raise WangSquareRenderError(
            "verification solution identity disagrees with explainability manifest"
        )
    presentation = load_wang_presentation(source)
    region = bundle.region
    if (
        (presentation.min_x, presentation.min_y, presentation.max_x, presentation.max_y)
        != (region.min_x, region.min_y, region.max_x, region.max_y)
        or presentation.tile_edges != bundle.tileset.tile_edges
        or any(
            (tile_id is None) == active
            for tile_id, active in zip(
                presentation.cells, region.active, strict=True
            )
        )
    ):
        raise WangSquareRenderError(
            "verification solution structure disagrees with explainability bundle"
        )
    return presentation


def _tiling_evidence_lines(
    bundle: ExplainabilityBundle, presentation
) -> tuple[str, str, str, str]:
    region = bundle.region
    active_index = next(
        index
        for index, active in enumerate(region.active)
        if active
        and index % region.width + 1 < region.width
        and region.active[index + 1]
        and region.boundary[index] is not None
        and region.boundary[index][0] is not None
    )
    inactive_index = next(
        index for index, active in enumerate(region.active) if not active
    )
    right_index = active_index + 1
    tile_id = presentation.cells[active_index]
    right_id = presentation.cells[right_index]
    if tile_id is None or right_id is None:
        raise WangSquareRenderError("verification evidence selected an inactive tile")
    tile = presentation.tile_edges[tile_id]
    right = presentation.tile_edges[right_id]
    required = region.boundary[active_index][0]
    if tile[1] != right[3] or tile[0] != required:
        raise WangSquareRenderError(
            "verification evidence does not match the recorded checker result"
        )
    return (
        f"active[{active_index}] = tile #{tile_id}; valid IDs are 0..{len(presentation.tile_edges) - 1}",
        f"inactive[{inactive_index}] = TILE_NONE (JSON null; native 255)",
        f"internal: tile #{tile_id} E={tile[1]} = tile #{right_id} W={right[3]}",
        f"boundary: tile #{tile_id} N={tile[0]} = required N={required}",
    )


def _extraction_lines(
    bundle: ExplainabilityBundle,
    presentation,
    extracted_assignment: tuple[bool, ...],
) -> tuple[str, ...]:
    reduction = bundle.reduction
    if reduction is None or len(extracted_assignment) != bundle.formula.variable_count:
        raise WangSquareRenderError(
            "verification extraction inputs do not match the formula"
        )
    gadgets = tuple(
        sorted(
            (gadget for gadget in reduction.gadgets if gadget.kind == "variable"),
            key=lambda gadget: gadget.ordinal,
        )
    )
    if len(gadgets) != len(extracted_assignment):
        raise WangSquareRenderError(
            "verification extraction requires one recorded variable gadget per value"
        )
    lines: list[str] = []
    for variable, (gadget, value) in enumerate(
        zip(gadgets, extracted_assignment, strict=True)
    ):
        rows = tuple(range(gadget.y_begin, min(gadget.y_begin + 3, gadget.y_end)))
        if len(rows) != 3:
            raise WangSquareRenderError(
                "verification extraction gadget does not expose three source cells"
            )
        tile_ids: list[int] = []
        for y in rows:
            index = (y - presentation.min_y) * presentation.width + (
                gadget.x_begin - presentation.min_x
            )
            tile_id = presentation.cells[index]
            if tile_id is None:
                raise WangSquareRenderError(
                    "verification extraction selected an inactive source cell"
                )
            tile_ids.append(tile_id)
        return_value = "true" if value else "false"
        lines.append(
            f"x{variable} | gadget cells y={rows[0]}..{rows[-1]}: "
            + ", ".join(f"#{tile_id}" for tile_id in tile_ids)
            + f" | recorded {return_value}"
        )
    return tuple(lines)


def _assignment_sha256(values: tuple[bool, ...]) -> str:
    return hashlib.sha256(_encoded({"witness": list(values)})).hexdigest()


def _bounded_variable_indices(variable_count: int) -> tuple[int, ...]:
    if variable_count <= 3:
        return tuple(range(variable_count))
    return (0, 1, variable_count - 1)


def _load_verification(
    path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    solution_path: str | Path | None = None,
    extracted_assignment: tuple[bool, ...] | None = None,
) -> tuple[
    str,
    tuple[dict[str, object], ...],
    ExplainabilityBundle | None,
    object | None,
    tuple[bool, ...] | None,
]:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WangSquareRenderError(
            f"cannot load verification receipt snapshot {source!s}: {error}"
        ) from error
    if type(document) is not dict or set(document) != {
        "schema",
        "expected_status",
        "verification",
        "agreement",
        "source_sha256",
    }:
        raise WangSquareRenderError("verification receipt snapshot must be closed")
    if document["schema"] != "wang-verification-receipts-v1":
        raise WangSquareRenderError("verification receipt schema is unsupported")
    status = document["expected_status"]
    if type(status) is not str or status not in {"sat", "unsat"}:
        raise WangSquareRenderError("verification receipt status is unsupported")
    verification = document["verification"]
    agreement = document["agreement"]
    if type(verification) is not dict or set(verification) != {
        name for name, _, _ in _CHECKS
    }:
        raise WangSquareRenderError("verification receipt record must be closed")
    agreement_fields = {
        "expected_status",
        "boolean_z3_status",
        "reference_status",
        "optimized_status",
        "wang_z3_status",
        "all_status_equal",
        "sat_witnesses_valid",
        "passed",
    }
    if type(agreement) is not dict or set(agreement) != agreement_fields:
        raise WangSquareRenderError("verification agreement must be closed")
    if (
        agreement["expected_status"] != status
        or any(
            agreement[name] != status
            for name in (
                "boolean_z3_status",
                "reference_status",
                "optimized_status",
                "wang_z3_status",
            )
        )
        or agreement["all_status_equal"] is not True
        or agreement["passed"] is not True
        or agreement["sat_witnesses_valid"] is not (True if status == "sat" else None)
    ):
        raise WangSquareRenderError("verification agreement is inconsistent")
    records: list[dict[str, object]] = []
    for name, _, checker in _CHECKS:
        record = verification[name]
        if type(record) is not dict or set(record) != {
            "checker",
            "performed",
            "passed",
            "witness_sha256",
        }:
            raise WangSquareRenderError(f"verification record {name} must be closed")
        if record["checker"] != checker:
            raise WangSquareRenderError(f"verification record {name} checker drifted")
        if status == "sat":
            digest = record["witness_sha256"]
            valid = (
                record["performed"] is True
                and record["passed"] is True
                and type(digest) is str
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
            )
        else:
            valid = (
                record["performed"] is False
                and record["passed"] is None
                and record["witness_sha256"] is None
            )
        if not valid:
            raise WangSquareRenderError(f"verification record {name} is inconsistent")
        records.append(record)
    bundle: ExplainabilityBundle | None = None
    presentation = None
    source_payload: dict[str, object] = {
        "verification": verification,
        "agreement": agreement,
    }
    if manifest_path is not None:
        bundle, identities = _manifest_context(manifest_path)
        if status == "sat":
            if solution_path is None or extracted_assignment is None:
                raise WangSquareRenderError(
                    "SAT verification explanation requires solution and copied assignment"
                )
            presentation = _bind_solution(bundle, identities, solution_path)
            assignment_record = verification["reference_assignment"]
            if _assignment_sha256(extracted_assignment) != assignment_record[
                "witness_sha256"
            ]:
                raise WangSquareRenderError(
                    "verification assignment identity disagrees with checker receipt"
                )
        elif solution_path is not None or extracted_assignment is not None:
            raise WangSquareRenderError(
                "UNSAT verification must not receive solution or assignment data"
            )
        if (status == "sat") != (identities["reference_solution"] is not None):
            raise WangSquareRenderError(
                "verification solution applicability disagrees with explainability manifest"
            )
        source_payload.update(identities)
        source_payload["reference_assignment"] = (
            None
            if extracted_assignment is None
            else list(extracted_assignment)
        )
    elif status == "sat":
        raise WangSquareRenderError(
            "SAT verification explanation requires explainability context"
        )
    encoded_source = _encoded(source_payload)
    source_sha256 = document["source_sha256"]
    if (
        type(source_sha256) is not str
        or hashlib.sha256(encoded_source).hexdigest() != source_sha256
    ):
        raise WangSquareRenderError("verification receipt source hash drifted")
    return status, tuple(records), bundle, presentation, extracted_assignment


def _verification_frame(
    status: str,
    records: tuple[dict[str, object], ...],
    stage: int,
    bundle: ExplainabilityBundle | None,
    presentation,
    extracted_assignment: tuple[bool, ...] | None,
) -> Image.Image:
    image = Image.new("RGB", (1920, 1040), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw.text(
        (30, 16),
        "Independent verification receipts",
        font=explain_font(52),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (30, 78),
        f"Receipt {stage + 1}/6 | {status.upper()} | display only; no verifier rerun",
        font=explain_font(34),
        fill=EXPLAIN_MUTED_RGB,
    )
    for index, ((_, label, expected_prefix), record) in enumerate(
        zip(_CHECKS, records, strict=True)
    ):
        x = 30 + (index % 3) * 630
        y = 118 + (index // 3) * 130
        visible = index <= stage
        performed = record.get("performed") is True
        passed = record.get("passed") is True
        checker = str(record.get("checker", ""))
        if performed and passed and checker.startswith(expected_prefix):
            state = "performed / passed"
            fill = (213, 237, 224)
        elif status == "unsat" and not performed and record.get("passed") is None:
            state = "not applicable: no SAT witness"
            fill = (235, 238, 243)
        else:
            raise WangSquareRenderError(
                f"verification record {_CHECKS[index][0]} is inconsistent"
            )
        draw.rounded_rectangle(
            (x, y, x + 600, y + 110),
            radius=12,
            fill=fill if visible else (242, 244, 247),
            outline=(53, 144, 93) if index == stage else (181, 188, 199),
            width=4 if index == stage else 2,
        )
        draw.text(
            (x + 16, y + 16),
            label,
            font=explain_font(40),
            fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB,
        )
        draw.text(
            (x + 16, y + 66),
            state,
            font=explain_font(32),
            fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB,
        )
    if status == "unsat":
        draw.rounded_rectangle((170, 330, 1750, 850), radius=24, fill=(239, 242, 246), outline=(181, 188, 199), width=3)
        draw.text((490, 470), "No SAT witness was returned", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
        draw.text((360, 565), "Six witness checks are not applicable; no certificate is fabricated.", font=explain_font(34), fill=EXPLAIN_MUTED_RGB)
        draw.text((460, 650), "Observed search traces remain diagnostics only.", font=explain_font(34), fill=EXPLAIN_MUTED_RGB)
        return image

    if bundle is None or presentation is None or extracted_assignment is None:
        raise WangSquareRenderError("SAT verification frame lacks validated context")
    palette = _build_palette_from_edges(presentation.tile_edges)
    evidence = _tiling_evidence_lines(bundle, presentation)
    draw.rounded_rectangle((30, 390, 930, 982), radius=18, fill=EXPLAIN_ACTIVE_RGB, outline=(181, 188, 199), width=2)
    draw.text((62, 416), "Tiling checker coverage", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)

    active_index = next(index for index, active in enumerate(bundle.region.active) if active and index % bundle.region.width + 1 < bundle.region.width and bundle.region.active[index + 1] and bundle.region.boundary[index] is not None and bundle.region.boundary[index][0] is not None)
    inactive_index = next(
        index for index, active in enumerate(bundle.region.active) if not active
    )
    tile_id = presentation.cells[active_index]
    right_id = presentation.cells[active_index + 1]
    assert tile_id is not None and right_id is not None
    tile_size = 180
    image.paste(square_explain_tile(presentation.tile_edges[tile_id], palette, tile_size, tile_id=tile_id, edge_labels=True), (92, 500))
    image.paste(square_explain_tile(presentation.tile_edges[right_id], palette, tile_size, tile_id=right_id, edge_labels=True), (318, 500))
    draw.text((92, 696), f"internal: #{tile_id} E{presentation.tile_edges[tile_id][1]} = #{right_id} W{presentation.tile_edges[right_id][3]}", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)
    required = bundle.region.boundary[active_index][0]
    draw.text((92, 756), f"boundary: #{tile_id} N{presentation.tile_edges[tile_id][0]} = required N{required}", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)
    image.paste(square_inactive_tile(118), (100, 822))
    draw.text((248, 838), "TILE_NONE", font=explain_font(46), fill=EXPLAIN_TEXT_RGB)
    draw.text((248, 894), f"inactive[{inactive_index}] = null = native 255", font=explain_font(40), fill=EXPLAIN_TEXT_RGB)
    draw.text((560, 538), f"active[{active_index}] = tile #{tile_id}", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)
    draw.text((560, 606), f"valid IDs: 0..{len(presentation.tile_edges) - 1}", font=explain_font(42), fill=EXPLAIN_TEXT_RGB)

    draw.rounded_rectangle((960, 390, 1890, 982), radius=18, fill=EXPLAIN_ACTIVE_RGB, outline=(181, 188, 199), width=2)
    draw.text((992, 416), "Source cells -> recorded value", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
    extraction = _extraction_lines(bundle, presentation, extracted_assignment)
    gadgets = tuple(sorted((gadget for gadget in bundle.reduction.gadgets if gadget.kind == "variable"), key=lambda gadget: gadget.ordinal))
    selected_indices = _bounded_variable_indices(len(gadgets))
    selected_extraction = tuple(
        (variable, (gadgets[variable], extraction[variable]))
        for variable in selected_indices
    )
    if len(gadgets) > len(selected_indices):
        draw.text((1530, 432), f"{len(gadgets) - 3} omitted", font=explain_font(32), fill=EXPLAIN_MUTED_RGB)
    for row, (variable, (gadget, _)) in enumerate(selected_extraction):
        y = 500 + row * 145
        draw.text((994, y + 34), f"x{variable}", font=explain_font(48), fill=EXPLAIN_TEXT_RGB)
        for offset in range(3):
            cell_index = (gadget.y_begin + offset - presentation.min_y) * presentation.width + (gadget.x_begin - presentation.min_x)
            source_tile = presentation.cells[cell_index]
            assert source_tile is not None
            image.paste(square_explain_tile(presentation.tile_edges[source_tile], palette, 112, tile_id=source_tile, edge_labels=False), (1080 + offset * 124, y))
        draw.text((1470, y + 6), f"recorded {'true' if extracted_assignment[variable] else 'false'}", font=explain_font(46), fill=(30, 112, 70))
        draw.text((1470, y + 68), "checker passed", font=explain_font(36), fill=EXPLAIN_MUTED_RGB)
    draw.text((994, 946), "Displayed cells only; decoding happened upstream.", font=explain_font(32), fill=EXPLAIN_MUTED_RGB)
    return image


def render_verification_assets(
    run_path: str | Path,
    output_directory: str | Path,
    *,
    manifest_path: str | Path | None = None,
    solution_path: str | Path | None = None,
    extracted_assignment: tuple[bool, ...] | None = None,
    duration_ms: int = 750,
) -> AnimationOutputs:
    status, records, bundle, presentation, extracted_assignment = _load_verification(
        run_path,
        manifest_path=manifest_path,
        solution_path=solution_path,
        extracted_assignment=extracted_assignment,
    )
    frames = tuple(
        _verification_frame(
            status,
            records,
            stage,
            bundle,
            presentation,
            extracted_assignment,
        )
        for stage in range(len(_CHECKS))
    )
    return write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(len(frames))),
        output_directory,
        fallback_index=len(frames) - 1,
        duration_ms=duration_ms,
    )


def _presentation_frame(
    square: Image.Image,
    generalized: Image.Image,
    hex_image: Image.Image,
    stage: int,
) -> Image.Image:
    image = Image.new("RGB", (1920, 1040), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    labels = (
        "verified square witness",
        "exact generalized recognition",
        "pure Basire/Culik port",
        "checked hex presentation",
    )
    draw.text(
        (36, 16),
        "Verified witness presentation",
        font=explain_font(56),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (36, 82),
        f"Stage {stage + 1}/4 | {labels[stage]}",
        font=explain_font(40),
        fill=EXPLAIN_MUTED_RGB,
    )
    sources = (square, generalized, generalized, hex_image)
    fitted = _fit(sources[stage], (1840, 760))
    image.paste(
        fitted,
        ((1920 - fitted.width) // 2, 152 + (760 - fitted.height) // 2),
    )
    if stage == 2:
        draw.rounded_rectangle(
            (300, 844, 1620, 926),
            radius=14,
            fill=(239, 242, 246),
            outline=(55, 126, 168),
            width=4,
        )
        draw.text(
            (350, 864),
            "H(N,E,S,W) = (E,S,kappa,W,N,kappa); inverse and matching checked",
            font=explain_font(34),
            fill=EXPLAIN_TEXT_RGB,
        )
    draw.text(
        (36, 944),
        "Pure 1:1 view of the already verified square witness.",
        font=explain_font(40),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (36, 992),
        "The checker validates the transform; the pixels are presentation only.",
        font=explain_font(34),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_witness_assets(
    solution_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 850,
) -> WitnessOutputs:
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    presentation = load_wang_presentation(solution_path)
    port = reduce_square_to_hex(presentation)
    check_square_to_hex(presentation, port)
    square = Image.fromarray(_compose_wang_square_explain(presentation), mode="RGB")
    generalized = Image.fromarray(compose_generalized_overlay(presentation), mode="RGB")
    hex_image = Image.fromarray(_compose_wang_hex_explain(presentation), mode="RGB")
    square_path = destination / "square.png"
    generalized_path = destination / "generalized.png"
    hex_path = destination / "hex.png"
    _save_image(square, square_path)
    _save_image(generalized, generalized_path)
    _save_image(hex_image, hex_path)
    animation = write_animation_assets(
        tuple(
            _presentation_frame(square, generalized, hex_image, stage)
            for stage in range(4)
        ),
        tuple(f"frame-{stage:02d}.png" for stage in range(4)),
        destination,
        fallback_index=3,
        duration_ms=duration_ms,
    )
    return WitnessOutputs(square_path, generalized_path, hex_path, animation)


def render_generalized_assets(
    manifest_path: str | Path,
    output_directory: str | Path,
) -> GeneralizedOutputs:
    bundle = load_explainability_bundle(manifest_path)
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    sheet = destination / "sheet.png"
    legend = destination / "atomic-legend.png"
    _save_png_atomic(compose_generalized_sheet(bundle.tileset.tile_edges), sheet)
    _save_image(_compose_atomic_legend(bundle.tileset.tile_edges), legend)
    return GeneralizedOutputs(sheet, legend)


def _compose_atomic_legend(
    tile_edges: tuple[tuple[int, int, int, int], ...],
) -> Image.Image:
    """Append local matching examples to the checked atomic vocabulary."""
    scale = 2
    vocabulary = Image.fromarray(
        compose_atomic_semantic_legend(tile_edges, scale=scale), mode="RGB"
    )
    panel_height = 310 * scale
    image = Image.new(
        "RGB",
        (vocabulary.width, vocabulary.height + panel_height),
        EXPLAIN_PANEL_RGB,
    )
    image.paste(vocabulary, (0, 0))
    draw = ImageDraw.Draw(image)
    panel_y = vocabulary.height
    draw.line(
        (24 * scale, panel_y, image.width - 24 * scale, panel_y),
        fill=(181, 188, 199),
        width=2 * scale,
    )
    draw.text(
        (24 * scale, panel_y + 18 * scale),
        "Local Wang compatibility uses the shared edge only",
        font=explain_font(32 * scale),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (24 * scale, panel_y + 57 * scale),
        "Canonical IDs: equal shared colors = valid; unequal = invalid.",
        font=explain_font(28 * scale),
        fill=EXPLAIN_MUTED_RGB,
    )

    palette = _build_palette_from_edges(tile_edges)
    examples = (
        ("VALID", 0, 4, 24 * scale, (213, 237, 224), (52, 145, 94)),
        ("INVALID", 0, 3, 447 * scale, (248, 226, 226), (190, 62, 62)),
    )
    tile_size = 72 * scale
    tile_y = panel_y + 132 * scale
    for label, left_id, right_id, card_x, fill, outline in examples:
        draw.rounded_rectangle(
            (
                card_x,
                panel_y + 88 * scale,
                card_x + 399 * scale,
                panel_y + 290 * scale,
            ),
            radius=10 * scale,
            fill=fill,
            outline=outline,
            width=3 * scale,
        )
        draw.text(
            (card_x + 16 * scale, panel_y + 98 * scale),
            label,
            font=explain_font(28 * scale),
            fill=EXPLAIN_TEXT_RGB,
        )
        left_x = card_x + 18 * scale
        right_x = card_x + 100 * scale
        image.paste(
            square_explain_tile(
                tile_edges[left_id],
                palette,
                tile_size,
                tile_id=left_id,
                edge_labels=True,
            ),
            (left_x, tile_y),
        )
        image.paste(
            square_explain_tile(
                tile_edges[right_id],
                palette,
                tile_size,
                tile_id=right_id,
                edge_labels=True,
            ),
            (right_x, tile_y),
        )
        left_color = tile_edges[left_id][1]
        right_color = tile_edges[right_id][3]
        relation = "=" if left_color == right_color else "!="
        draw.text(
            (card_x + 190 * scale, panel_y + 145 * scale),
            f"#{left_id} E = {left_color}",
            font=explain_font(20 * scale),
            fill=EXPLAIN_TEXT_RGB,
        )
        draw.text(
            (card_x + 190 * scale, panel_y + 184 * scale),
            f"{relation}  #{right_id} W = {right_color}",
            font=explain_font(20 * scale),
            fill=EXPLAIN_TEXT_RGB,
        )
        draw.text(
            (card_x + 190 * scale, panel_y + 230 * scale),
            "shared colors agree" if relation == "=" else "shared colors differ",
            font=explain_font(18 * scale),
            fill=outline,
        )
    return image


def render_presentation_status(status: str, output_path: str | Path) -> Path:
    if status != "unsat":
        raise WangSquareRenderError("presentation status is only valid for UNSAT")
    image = Image.new("RGB", (960, 500), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (18, 16),
        title="Witness presentation",
        subtitle="observed | UNSAT | square, generalized overlay, and hex are not applicable",
    )
    draw.rounded_rectangle(
        (145, 142, 815, 350),
        radius=10,
        fill=(239, 242, 246),
        outline=(181, 188, 199),
    )
    draw.text(
        (257, 188),
        "No SAT witness was returned",
        font=explain_font(20),
        fill=EXPLAIN_TEXT_RGB,
    )
    draw.text(
        (213, 242),
        "No square, generalized, or hex witness is fabricated.",
        font=explain_font(13),
        fill=EXPLAIN_MUTED_RGB,
    )
    draw.text(
        (226, 285),
        "The trace records search; it is not an UNSAT certificate.",
        font=explain_font(12),
        fill=EXPLAIN_MUTED_RGB,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _save_image(image, destination)
    return destination


def _pipeline_frame(sources: tuple[Image.Image, ...], stage: int) -> Image.Image:
    image = Image.new("RGB", (1080, 620), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (18, 16),
        title="One captured v2 pipeline run",
        subtitle=(
            f"observed milestone {stage + 1}/8 | {_PIPELINE_LABELS[stage]} | "
            "component order, not a timing scale"
        ),
    )
    node_width = 126
    for index, label in enumerate(_PIPELINE_LABELS):
        x = 18 + index * 130
        active = index <= stage
        draw.rounded_rectangle(
            (x, 88, x + node_width - 8, 144),
            radius=6,
            fill=(213, 237, 224) if active else (240, 242, 246),
            outline=(52, 145, 94) if index == stage else (181, 188, 199),
            width=2 if index == stage else 1,
        )
        words = label.replace(" / ", "/").split()
        draw.text(
            (x + 7, 96),
            "\n".join(words[:3]),
            font=explain_font(8),
            fill=EXPLAIN_TEXT_RGB if active else EXPLAIN_MUTED_RGB,
            spacing=2,
        )
        if index < len(_PIPELINE_LABELS) - 1:
            draw.line((x + 118, 116, x + 130, 116), fill=(129, 139, 153), width=2)
    fitted = _fit(sources[stage], (1020, 400))
    image.paste(
        fitted,
        ((1080 - fitted.width) // 2, 166 + (400 - fitted.height) // 2),
    )
    draw.text(
        (18, 594),
        "All facts come from one validated v2 run; independent checks remain separate from rendering.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def _home_preview(square: Image.Image) -> Image.Image:
    image = Image.new("RGB", (760, 430), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (18, 16),
        title="Verified SAT witness",
        subtitle="observed | captured SAT source | square presentation",
    )
    fitted = _fit(square, (720, 320))
    image.paste(fitted, ((760 - fitted.width) // 2, 82))
    draw.text(
        (18, 407),
        "Preview only; the worked example retains the full source and trust boundary.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def _worked_example(sources: tuple[Image.Image, ...]) -> Image.Image:
    image = Image.new("RGB", (1080, 940), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (18, 16),
        title="Captured SAT semantic milestones",
        subtitle="observed | fixed component order | static reduced-motion sequence",
    )
    card_width, card_height = 510, 195
    for index, (label, source) in enumerate(zip(_PIPELINE_LABELS, sources, strict=True)):
        column = index % 2
        row = index // 2
        x = 18 + column * 528
        y = 82 + row * 210
        draw.rounded_rectangle(
            (x, y, x + card_width, y + card_height),
            radius=7,
            fill=EXPLAIN_ACTIVE_RGB,
            outline=(181, 188, 199),
        )
        draw.text((x + 10, y + 8), f"t{index}  {label}", font=explain_font(11), fill=EXPLAIN_TEXT_RGB)
        fitted = _fit(source, (card_width - 20, card_height - 42))
        image.paste(fitted, (x + (card_width - fitted.width) // 2, y + 35))
    draw.text(
        (18, 918),
        "Milestones are semantic selections, not uniformly sampled time points.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_overview_assets(
    source_paths: tuple[str | Path, ...],
    home_source: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 900,
    include_sat_story: bool = True,
) -> OverviewOutputs:
    if len(source_paths) != len(_PIPELINE_LABELS):
        raise WangSquareRenderError("pipeline overview requires eight named sources")
    sources = tuple(_load_image(Path(path)) for path in source_paths)
    home_image = _load_image(Path(home_source)) if include_sat_story else None
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    frames = tuple(_pipeline_frame(sources, stage) for stage in range(len(sources)))
    animation = write_animation_assets(
        frames,
        tuple(f"frame-{stage:02d}.png" for stage in range(len(frames))),
        destination,
        fallback_index=len(frames) - 1,
        duration_ms=duration_ms,
    )
    home_preview: Path | None = None
    worked_example: Path | None = None
    if home_image is not None:
        home_preview = destination / "home-preview.png"
        worked_example = destination / "worked-example.png"
        _save_image(_home_preview(home_image), home_preview)
        _save_image(_worked_example(sources), worked_example)
    return OverviewOutputs(animation, home_preview, worked_example)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="compose fixed narrative assets from validated pipeline outputs"
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)
    verification = subparsers.add_parser("verification")
    verification.add_argument("run", type=Path)
    verification.add_argument("output_directory", type=Path)
    verification.add_argument("--manifest", type=Path)
    verification.add_argument("--solution", type=Path)
    verification.add_argument("--assignment-json")
    witness = subparsers.add_parser("witness")
    witness.add_argument("solution", type=Path)
    witness.add_argument("output_directory", type=Path)
    generalized = subparsers.add_parser("generalized")
    generalized.add_argument("manifest", type=Path)
    generalized.add_argument("output_directory", type=Path)
    status = subparsers.add_parser("status")
    status.add_argument("status", choices=("unsat",))
    status.add_argument("output", type=Path)
    overview = subparsers.add_parser("overview")
    overview.add_argument("output_directory", type=Path)
    overview.add_argument("sources", nargs=8, type=Path)
    overview.add_argument("--home-source", required=True, type=Path)
    overview.add_argument("--omit-sat-story", action="store_true")
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        if args.mode == "verification":
            assignment = None
            if args.assignment_json is not None:
                try:
                    raw_assignment = json.loads(args.assignment_json)
                except json.JSONDecodeError as error:
                    raise WangSquareRenderError(
                        f"verification assignment JSON is invalid: {error.msg}"
                    ) from error
                if type(raw_assignment) is not list or any(
                    type(value) is not bool for value in raw_assignment
                ):
                    raise WangSquareRenderError(
                        "verification assignment JSON must be a Boolean array"
                    )
                assignment = tuple(raw_assignment)
            outputs = render_verification_assets(
                args.run,
                args.output_directory,
                manifest_path=args.manifest,
                solution_path=args.solution,
                extracted_assignment=assignment,
            )
            print(f"animation={outputs.animation}")
            print(f"contact_sheet={outputs.contact_sheet}")
            print(f"fallback={outputs.fallback}")
        elif args.mode == "witness":
            outputs = render_witness_assets(args.solution, args.output_directory)
            print(f"square={outputs.square}")
            print(f"generalized={outputs.generalized}")
            print(f"hex={outputs.hex}")
            print(f"animation={outputs.animation.animation}")
            print(f"contact_sheet={outputs.animation.contact_sheet}")
            print(f"fallback={outputs.animation.fallback}")
        elif args.mode == "generalized":
            outputs = render_generalized_assets(args.manifest, args.output_directory)
            print(f"sheet={outputs.sheet}")
            print(f"legend={outputs.legend}")
            print(f"spec_sha256={generalized_specification_sha256()}")
        elif args.mode == "status":
            print(f"status={render_presentation_status(args.status, args.output)}")
        else:
            outputs = render_overview_assets(
                tuple(args.sources),
                args.home_source,
                args.output_directory,
                include_sat_story=not args.omit_sat_story,
            )
            print(f"animation={outputs.animation.animation}")
            print(f"contact_sheet={outputs.animation.contact_sheet}")
            print(f"fallback={outputs.animation.fallback}")
            if outputs.home_preview is not None:
                print(f"home_preview={outputs.home_preview}")
            if outputs.worked_example is not None:
                print(f"worked_example={outputs.worked_example}")
    except (FileNotFoundError, WangSquareRenderError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
