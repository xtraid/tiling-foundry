#!/usr/bin/env python3
"""Check the Linux demo toolchain before setup, then check its two environments."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PACKAGES = (
    "Debian 13: install build-essential python3 git texlive-latex-base; "
    "Arch/Omarchy: install base-devel python git texlive-latex; "
    "install uv separately. "
    "See the README for the setup commands."
)


class SetupError(RuntimeError):
    """A prerequisite or an installed dependency is not usable."""


def run(command: list[str], *, cwd: Path, purpose: str) -> str:
    try:
        result = subprocess.run(
            command, cwd=cwd, check=True, capture_output=True, text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", "") or getattr(error, "stdout", "")
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        tail = "\n".join((detail or str(error)).strip().splitlines()[-12:])
        raise SetupError(f"{purpose} failed:\n{tail}") from error
    return result.stdout.strip()


def configured_command(variable: str, default: str) -> list[str]:
    try:
        command = shlex.split(os.environ.get(variable, default))
    except ValueError as error:
        raise SetupError(f"Invalid {variable}: {error}") from error
    executable = shutil.which(command[0]) if command else None
    if executable is None:
        raise SetupError(f"Command not found: {shlex.join(command) or default}")
    # Probes change cwd; preserve the detected path and any wrapper symlink name.
    command[0] = str(Path(executable).absolute())
    return command


def preflight() -> None:
    if not sys.platform.startswith("linux"):
        raise SetupError("The demo setup currently supports Linux.")
    if sys.version_info < (3, 11):
        raise SetupError("The setup helper needs Python 3.11 or newer (make PYTHON=...).")
    if os.environ.get("UV_PROJECT_ENVIRONMENT"):
        raise SetupError(
            "Unset UV_PROJECT_ENVIRONMENT: the demo uses separate .venv and "
            "renderer/.venv directories."
        )
    compiler = configured_command("DEMO_SETUP_CC", "cc")
    uv = configured_command("DEMO_SETUP_UV", "uv")
    if shutil.which("uv") is None:
        raise SetupError(
            "uv must also be on PATH: dossier renderer subprocesses invoke it by name."
        )
    if shutil.which("git") is None:
        raise SetupError("git is missing; dossiers record the repository commit.")
    if shutil.which("pdflatex") is None:
        raise SetupError("pdflatex is missing; the demo includes a PDF dossier.")
    print("[1/3] Checking C17, uv and PDF dependencies...", flush=True)
    print(run([*uv, "--version"], cwd=ROOT, purpose="uv"), flush=True)
    with tempfile.TemporaryDirectory(prefix="tiling-demo-setup-") as temporary:
        scratch = Path(temporary)
        source = scratch / "check.c"
        source.write_text(
            "#include <stdint.h>\n#include <stdlib.h>\n"
            "_Static_assert(__STDC_VERSION__ >= 201710L, \"C17 required\");\n"
            "int main(void) { uint32_t value = 17; return value != 17; }\n",
            encoding="utf-8",
        )
        run(
            [*compiler, "-std=c17", str(source), "-o", str(scratch / "check")],
            cwd=scratch, purpose="C17 compilation",
        )
        run([str(scratch / "check")], cwd=scratch, purpose="C17 executable")

        # The real preamble catches missing packages and T1 fonts. Reuse the
        # dossier compiler so user-local TeX files cannot hide missing packages.
        sys.path.insert(0, str(ROOT / "python"))
        from dossier.tex_compile import TexCompileError, compile_tex_pdf

        template = (ROOT / "templates/run-report-v2.tex").read_text(encoding="utf-8")
        body = (
            r"\section{Setup check}" "\n"
            r"Caf\'e, \textbf{bold}, \texttt{monospace}: $x_1 + x_2 = 1$." "\n"
            r"\begin{longtable}{ll}Engine & Status \\ Reference & ready\end{longtable}"
        )
        (scratch / "report.tex").write_text(
            template.replace("@@TITLE@@", "Tiling Foundry setup").replace("@@BODY@@", body),
            encoding="utf-8",
        )
        try:
            compile_tex_pdf(scratch, "pdflatex", datetime(2026, 1, 1, tzinfo=timezone.utc))
        except TexCompileError as error:
            tail = "\n".join(str(error).splitlines()[-12:])
            raise SetupError(f"PDF dependency check failed:\n{tail}") from error
    print("Prerequisites ready; installing the two locked Python environments.", flush=True)


def verify() -> None:
    print("[2/3] Checking Z3 and the native shared library...", flush=True)
    core_python = ROOT / ".venv/bin/python"
    renderer_python = ROOT / "renderer/.venv/bin/python"
    for interpreter in (core_python, renderer_python):
        if not interpreter.is_file():
            raise SetupError(
                f"Missing environment: {interpreter.relative_to(ROOT)}. "
                "Run make demo-setup without a custom UV_PROJECT_ENVIRONMENT."
            )
    print(run(
        [str(core_python), "-c", (
            "import sys; assert sys.version_info >= (3, 11); "
            "sys.path.insert(0, 'python'); import z3; "
            "from native._lib import library; library(); "
            "value = z3.IntVal(1); assert z3.simplify(value + 1).as_long() == 2; "
            "print('Python ' + sys.version.split()[0] + ', Z3 ' + z3.get_version_string() "
            "+ ', libwang.so loaded')"
        )], cwd=ROOT, purpose="Core dependency check",
    ), flush=True)
    print("[3/3] Checking the renderer and its image/font support...", flush=True)
    print(run(
        [str(renderer_python), "-c", (
            "import io, sys; assert sys.version_info >= (3, 14); "
            "import numpy; from PIL import Image, ImageDraw, __version__; "
            "from wang_explain import explain_font; "
            "image = Image.fromarray(numpy.zeros((48, 160, 3), dtype=numpy.uint8)); "
            "ImageDraw.Draw(image).text((0, 0), 'Tiling Foundry', font=explain_font(14)); "
            "output = io.BytesIO(); image.save(output, format='PNG'); "
            "output.seek(0); Image.open(output).verify(); "
            "print('Python ' + sys.version.split()[0] + ', NumPy ' + numpy.__version__ "
            "+ ', Pillow ' + __version__ + ', PNG and font ready')"
        )], cwd=ROOT / "renderer", purpose="Renderer dependency check",
    ), flush=True)
    print("Demo setup complete. The installed environments support offline runs.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "verify"))
    arguments = parser.parse_args()
    try:
        if arguments.phase == "preflight":
            preflight()
        else:
            verify()
    except (SetupError, OSError) as error:
        print(f"demo-setup: {error}", file=sys.stderr)
        if arguments.phase == "preflight":
            print(SYSTEM_PACKAGES, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
