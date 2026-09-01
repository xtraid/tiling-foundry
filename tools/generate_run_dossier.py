#!/usr/bin/env python3
"""Generate one opt-in, self-contained observed-run dossier."""

from __future__ import annotations

import argparse
import calendar
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform as platform_module
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter_ns


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "renderer"
TEMPLATE = ROOT / "templates/run-report.tex"
sys.path.insert(0, str(ROOT / "python"))

from formats.pipeline_snapshot import (  # noqa: E402
    _encode_document,
    _load_json_bytes,
    _write_atomic,
)
from formats.run_dossier import (  # noqa: E402
    RunCase,
    build_run_dossier,
    load_run_case,
    load_run_dossier,
    validate_case_outcome,
)
from formats.run_report_tex import render_run_report_tex  # noqa: E402
from formats.solver_trace_snapshot import (  # noqa: E402
    dump_solver_trace_bundle,
    load_solver_trace_bundle,
)
from native.trace_pipeline import capture_native_pipeline_trace  # noqa: E402


class DossierGenerationError(RuntimeError):
    """The opt-in report pipeline could not complete atomically."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "dispatch one closed v1 or v2 case to its isolated self-contained "
            "dossier implementation"
        )
    )
    parser.add_argument("case", type=Path, help="wang-run-case-v1/v2 JSON")
    parser.add_argument("output_directory", type=Path)
    parser.add_argument(
        "--tex-engine",
        default="pdflatex",
        help="v1 pdfLaTeX executable (default: pdflatex)",
    )
    parser.add_argument("--max-frames", type=int, default=12, help="v1 only")
    parser.add_argument("--duration-ms", type=int, default=500, help="v1 only")
    return parser


def _run_renderer(arguments: list[str]) -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise DossierGenerationError("uv is required to run the isolated renderer")
    command = [uv, "run", "--locked", "python", *arguments]
    try:
        completed = subprocess.run(
            command,
            cwd=RENDERER,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise DossierGenerationError(f"renderer failed: {detail.strip()}") from error
    return completed.stdout


def _render_assets(
    manifest_path: Path,
    manifest: dict[str, object],
    images: Path,
    *,
    max_frames: int,
    duration_ms: int,
) -> Path:
    images.mkdir(parents=True, exist_ok=True)
    trace_directory = images / "trace"
    stdout = _run_renderer(
        [
            "wang_trace_render.py",
            str(manifest_path),
            str(trace_directory),
            "--max-frames",
            str(max_frames),
            "--duration-ms",
            str(duration_ms),
        ]
    )
    fallback: Path | None = None
    for line in stdout.splitlines():
        if line.startswith("fallback="):
            fallback = Path(line.removeprefix("fallback="))
    if fallback is None or not fallback.is_file() or fallback.parent != trace_directory:
        raise DossierGenerationError("trace renderer did not publish a local fallback")

    views = (
        ("formula", "formula.png", False),
        ("region", "region-square.png", False),
        ("region", "region-hex.png", True),
        ("reduction", "reduction.png", False),
    )
    for view, name, hex_mode in views:
        arguments = [
            "wang_square.py",
            str(manifest_path),
            str(images / name),
            "--view",
            view,
        ]
        if hex_mode:
            arguments.append("--hex")
        _run_renderer(arguments)

    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    solution_reference = artifacts["solution"]
    if solution_reference is not None:
        assert isinstance(solution_reference, dict)
        solution_path = manifest_path.parent / str(solution_reference["path"])
        _run_renderer(
            [
                "wang_square.py",
                str(solution_path),
                str(images / "solution-square.png"),
                "--explain",
            ]
        )
        _run_renderer(
            [
                "wang_square.py",
                str(solution_path),
                str(images / "solution-hex.png"),
                "--explain",
                "--hex",
            ]
        )
    return fallback


def _artifact(
    dossier_root: Path,
    path: Path,
    *,
    media_type: str,
    role: str,
) -> dict[str, str]:
    try:
        encoded = path.read_bytes()
        relative = path.relative_to(dossier_root).as_posix()
    except (OSError, ValueError) as error:
        raise DossierGenerationError(f"cannot bind artifact {path!s}: {error}") from error
    return {
        "path": relative,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "media_type": media_type,
        "role": role,
    }


def _collect_artifacts(
    dossier_root: Path,
    manifest_path: Path,
    manifest: dict[str, object],
    fallback: Path,
) -> dict[str, dict[str, str]]:
    artifacts: dict[str, dict[str, str]] = {
        "trace_manifest": _artifact(
            dossier_root,
            manifest_path,
            media_type="application/json",
            role="hash-bound solver trace manifest",
        ),
    }
    references = manifest["artifacts"]
    assert isinstance(references, dict)
    for name, reference in references.items():
        if reference is None:
            continue
        assert isinstance(reference, dict)
        artifacts[f"{name}_snapshot"] = _artifact(
            dossier_root,
            manifest_path.parent / str(reference["path"]),
            media_type="application/json",
            role=f"authoritative {name} document",
        )

    images = dossier_root / "assets/images"
    image_specs = {
        "formula_view": (images / "formula.png", "parsed formula view"),
        "region_square": (images / "region-square.png", "square region view"),
        "region_hex": (images / "region-hex.png", "checked hex region view"),
        "reduction_view": (images / "reduction.png", "native reduction provenance view"),
        "trace_contact_sheet": (
            images / "trace/contact-sheet.png",
            "selected observed trace states",
        ),
        "trace_fallback": (fallback, "accessible static trace fallback"),
        "trace_animation": (
            images / "trace/trace.gif",
            "presentation-only trace animation",
        ),
    }
    if references["solution"] is not None:
        image_specs.update(
            {
                "solution_square": (
                    images / "solution-square.png",
                    "verified square witness view",
                ),
                "solution_hex": (
                    images / "solution-hex.png",
                    "checked hex witness view",
                ),
            }
        )
    for name, (image_path, role) in image_specs.items():
        media_type = "image/gif" if image_path.suffix == ".gif" else "image/png"
        artifacts[name] = _artifact(
            dossier_root,
            image_path,
            media_type=media_type,
            role=role,
        )
    remaining_frames = tuple(
        frame
        for frame in sorted((images / "trace").glob("frame-*.png"))
        if frame != fallback
    )
    for index, frame in enumerate(remaining_frames):
        artifacts[f"trace_frame_{index:03d}"] = _artifact(
            dossier_root,
            frame,
            media_type="image/png",
            role="selected observed trace frame",
        )
    return artifacts


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
        raise DossierGenerationError(f"cannot identify repository commit: {error}") from error
    return completed.stdout.strip()


def _compile_pdf(dossier_root: Path, tex_engine: str, captured_at: datetime) -> None:
    executable = shutil.which(tex_engine)
    if executable is None:
        raise DossierGenerationError(f"TeX engine not found: {tex_engine}")
    tex_home = dossier_root / ".tex-home"
    tex_home.mkdir()
    tex_var = tex_home / "var"
    tex_config = tex_home / "config"
    tex_fonts = tex_var / "fonts"
    tex_var.mkdir()
    tex_config.mkdir()
    tex_fonts.mkdir()
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tex_home),
        "TEXMFHOME": str(tex_home / "texmf"),
        "TEXMFVAR": str(tex_var),
        "TEXMFCONFIG": str(tex_config),
        "VARTEXFONTS": str(tex_fonts),
        "SOURCE_DATE_EPOCH": str(calendar.timegm(captured_at.utctimetuple())),
        "TZ": "UTC",
        "openin_any": "p",
        "openout_any": "p",
    }
    command = [
        executable,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-no-shell-escape",
        "report.tex",
    ]
    for _ in range(2):
        try:
            subprocess.run(
                command,
                cwd=dossier_root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            detail = getattr(error, "stdout", "") or getattr(error, "stderr", "")
            raise DossierGenerationError(
                f"LaTeX compilation failed without shell escape: {detail.strip()}"
            ) from error
    pdf = dossier_root / "report.pdf"
    try:
        if pdf.stat().st_size < 100 or not pdf.read_bytes().startswith(b"%PDF-"):
            raise DossierGenerationError("TeX engine did not produce a valid PDF header")
    except OSError as error:
        raise DossierGenerationError(f"cannot inspect report.pdf: {error}") from error
    for suffix in ("aux", "log", "out", "toc"):
        auxiliary = dossier_root / f"report.{suffix}"
        try:
            auxiliary.unlink()
        except FileNotFoundError:
            pass
    shutil.rmtree(tex_home)


def _generate_run_dossier_v1(
    case_path: str | Path,
    output_directory: str | Path,
    *,
    tex_engine: str,
    max_frames: int = 12,
    duration_ms: int = 500,
) -> Path:
    """Generate all dossier outputs in staging and install the directory once."""
    case: RunCase = load_run_case(case_path, ROOT)
    destination = Path(output_directory).resolve()
    if destination.exists():
        raise DossierGenerationError(f"output directory already exists: {destination!s}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        source_path = ROOT / case.source
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        overrides = tuple(
            (item.cell, item.domain) for item in case.initial_domain_overrides
        )
        values, native_timings = capture_native_pipeline_trace(
            source_path,
            optimized=case.solver == "optimized",
            event_capacity=case.event_capacity,
            checkpoint_interval=case.checkpoint_interval,
            checkpoint_capacity=case.checkpoint_capacity,
            initial_domain_overrides=overrides or None,
        )
        formula, region, explanation, result, trace = values
        validate_case_outcome(case, trace)

        data_directory = staging / "assets/data"
        data_directory.mkdir(parents=True)
        manifest_path = data_directory / "manifest.json"
        started = perf_counter_ns()
        dump_solver_trace_bundle(
            manifest_path,
            source_path,
            formula,
            region,
            explanation,
            result,
            trace,
        )
        export_ns = perf_counter_ns() - started
        manifest, _ = load_solver_trace_bundle(manifest_path)

        started = perf_counter_ns()
        fallback = _render_assets(
            manifest_path,
            manifest,
            staging / "assets/images",
            max_frames=max_frames,
            duration_ms=duration_ms,
        )
        render_ns = perf_counter_ns() - started
        artifacts = _collect_artifacts(staging, manifest_path, manifest, fallback)

        captured_at = datetime.now(timezone.utc).replace(microsecond=0)
        timings_ns = {
            "parse": native_timings.parse_ns,
            "region_build": native_timings.region_build_ns,
            "encoding": None,
            "solve": native_timings.solve_ns,
            "verify": native_timings.verify_ns if result.status.value == "sat" else None,
            "export": export_ns,
            "render": render_ns,
        }
        run_document = build_run_dossier(
            case,
            trace,
            source_sha256=source_digest,
            captured_at_utc=captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            platform=platform_module.platform(),
            python_version=platform_module.python_version(),
            git_commit=_git_commit(),
            timings_ns=timings_ns,
            artifacts=artifacts,
        )
        _write_atomic(staging / "run.json", _encode_document(run_document))
        load_run_dossier(staging / "run.json")
        template = TEMPLATE.read_text(encoding="utf-8")
        report_tex = render_run_report_tex(run_document, template)
        _write_atomic(staging / "report.tex", report_tex.encode("utf-8"))
        _compile_pdf(staging, tex_engine, captured_at)
        os.replace(staging, destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _case_schema(case_path: str | Path) -> str:
    path = Path(case_path)
    try:
        document = _load_json_bytes(path.read_bytes(), str(path))
    except OSError as error:
        raise DossierGenerationError(f"cannot read dossier case {path!s}: {error}") from error
    schema = document.get("schema")
    if type(schema) is not str:
        raise DossierGenerationError("dossier case requires a string schema")
    return schema


def generate_run_dossier(
    case_path: str | Path,
    output_directory: str | Path,
    *,
    tex_engine: str,
    max_frames: int = 12,
    duration_ms: int = 500,
) -> Path:
    """Dispatch the sole public CLI without sharing v1/v2 implementations."""
    schema = _case_schema(case_path)
    if schema == "wang-run-case-v1":
        return _generate_run_dossier_v1(
            case_path,
            output_directory,
            tex_engine=tex_engine,
            max_frames=max_frames,
            duration_ms=duration_ms,
        )
    if schema == "wang-run-case-v2":
        if tex_engine != "pdflatex" or max_frames != 12 or duration_ms != 500:
            raise DossierGenerationError(
                "renderer and TeX options are v1-only until the v2 asset/PDF passes"
            )
        from dossier.multi_engine import (
            MultiEngineDossierError,
            generate_multi_engine_dossier,
        )

        try:
            return generate_multi_engine_dossier(case_path, output_directory)
        except MultiEngineDossierError as error:
            raise DossierGenerationError(str(error)) from error
    raise DossierGenerationError(f"unsupported dossier case schema: {schema}")


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        destination = generate_run_dossier(
            args.case,
            args.output_directory,
            tex_engine=args.tex_engine,
            max_frames=args.max_frames,
            duration_ms=args.duration_ms,
        )
    except (DossierGenerationError, OSError, ValueError) as error:
        parser.error(str(error))
    print(f"dossier={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
