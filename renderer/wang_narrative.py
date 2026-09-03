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
)
from wang_generalized_render import (
    compose_atomic_semantic_legend,
    compose_generalized_overlay,
    compose_generalized_sheet,
)
from wang_generalized import generalized_specification_sha256
from wang_hex_port import WangSquareRenderError, check_square_to_hex, reduce_square_to_hex
from wang_snapshot import load_explainability_bundle
from wang_square import (
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
    fitted.thumbnail(size, resample=Image.Resampling.NEAREST)
    return fitted


def _load_verification(path: str | Path) -> tuple[str, tuple[dict[str, object], ...]]:
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
    encoded_source = (
        json.dumps(
            {"verification": verification, "agreement": agreement},
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    source_sha256 = document["source_sha256"]
    if (
        type(source_sha256) is not str
        or hashlib.sha256(encoded_source).hexdigest() != source_sha256
    ):
        raise WangSquareRenderError("verification receipt source hash drifted")
    return status, tuple(records)


def _verification_frame(
    status: str,
    records: tuple[dict[str, object], ...],
    stage: int,
) -> Image.Image:
    image = Image.new("RGB", (960, 500), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    draw_explain_heading(
        draw,
        (18, 16),
        title="Independent verification sequence",
        subtitle=(
            f"observed record {stage + 1}/6 | expected {status.upper()} | "
            "renders checker receipts; does not rerun a verifier"
        ),
    )
    for index, ((_, label, expected_prefix), record) in enumerate(
        zip(_CHECKS, records, strict=True)
    ):
        y = 92 + index * 60
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
            (18, y, 930, y + 46),
            radius=6,
            fill=fill if visible else (242, 244, 247),
            outline=(53, 144, 93) if index == stage else (181, 188, 199),
            width=2 if index == stage else 1,
        )
        draw.text(
            (32, y + 7),
            label,
            font=explain_font(12),
            fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB,
        )
        draw.text(
            (278, y + 8),
            state,
            font=explain_font(11),
            fill=EXPLAIN_TEXT_RGB if visible else EXPLAIN_MUTED_RGB,
        )
        draw.text(
            (548, y + 9),
            checker,
            font=explain_font(9),
            fill=EXPLAIN_MUTED_RGB,
        )
    draw.text(
        (18, 472),
        "SAT checks validate named witnesses independently; UNSAT has no fabricated certificate.",
        font=explain_font(9),
        fill=EXPLAIN_MUTED_RGB,
    )
    return image


def render_verification_assets(
    run_path: str | Path,
    output_directory: str | Path,
    *,
    duration_ms: int = 750,
) -> AnimationOutputs:
    status, records = _load_verification(run_path)
    frames = tuple(
        _verification_frame(status, records, stage) for stage in range(len(_CHECKS))
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
    image = Image.new("RGB", (1080, 620), EXPLAIN_PANEL_RGB)
    draw = ImageDraw.Draw(image)
    labels = (
        "verified square witness",
        "exact generalized recognition",
        "pure Basire/Culik port",
        "checked hex presentation",
    )
    draw_explain_heading(
        draw,
        (18, 16),
        title="Verified witness presentation",
        subtitle=f"verified-transformation stage {stage + 1}/4 | {labels[stage]}",
    )
    sources = (square, generalized, generalized, hex_image)
    fitted = _fit(sources[stage], (1020, 475))
    image.paste(
        fitted,
        ((1080 - fitted.width) // 2, 88 + (475 - fitted.height) // 2),
    )
    if stage == 2:
        draw.rounded_rectangle(
            (246, 508, 834, 565),
            radius=7,
            fill=(239, 242, 246),
            outline=(55, 126, 168),
            width=2,
        )
        draw.text(
            (278, 525),
            "H(N,E,S,W) = (E,S,kappa,W,N,kappa); inverse and matching checked",
            font=explain_font(11),
            fill=EXPLAIN_TEXT_RGB,
        )
    draw.text(
        (18, 594),
        "The independent square witness check precedes presentation; raster output proves nothing by itself.",
        font=explain_font(9),
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
    _save_png_atomic(
        compose_atomic_semantic_legend(bundle.tileset.tile_edges), legend
    )
    return GeneralizedOutputs(sheet, legend)


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
            outputs = render_verification_assets(args.run, args.output_directory)
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
