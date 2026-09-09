"""Isolated, deterministic pdfLaTeX compilation for dossier callers."""

from __future__ import annotations

import calendar
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys


class TexCompileError(RuntimeError):
    """The controlled dossier TeX compilation boundary failed."""


def compile_tex_pdf(
    dossier_root: Path,
    tex_engine: str,
    captured_at: datetime,
) -> None:
    """Compile report.tex twice in an isolated TeX home without shell escape."""
    tex_home = dossier_root / ".tex-home"
    private_home_created = False
    try:
        try:
            executable = shutil.which(tex_engine)
            if executable is None:
                raise TexCompileError(f"TeX engine not found: {tex_engine}")
            tex_home.mkdir()
            private_home_created = True
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
                    detail = getattr(error, "stdout", "") or getattr(
                        error, "stderr", ""
                    )
                    raise TexCompileError(
                        "LaTeX compilation failed without shell escape: "
                        f"{detail.strip()}"
                    ) from error
            pdf = dossier_root / "report.pdf"
            try:
                if pdf.stat().st_size < 100 or not pdf.read_bytes().startswith(
                    b"%PDF-"
                ):
                    raise TexCompileError(
                        "TeX engine did not produce a valid PDF header"
                    )
            except OSError as error:
                raise TexCompileError(f"cannot inspect report.pdf: {error}") from error
            for suffix in ("aux", "log", "out", "toc"):
                auxiliary = dossier_root / f"report.{suffix}"
                try:
                    auxiliary.unlink()
                except FileNotFoundError:
                    pass
        except TexCompileError:
            raise
        except OSError as error:
            raise TexCompileError(
                f"TeX compilation filesystem operation failed: {error}"
            ) from error
    finally:
        if private_home_created:
            primary_error = sys.exception()
            try:
                shutil.rmtree(tex_home)
            except OSError as error:
                if primary_error is None:
                    raise TexCompileError(
                        f"cannot remove private TeX home: {error}"
                    ) from error
