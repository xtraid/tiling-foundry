#!/usr/bin/env python3
"""Run a CM1-in-3 input through the verified PDF pipeline under one deadline."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


class DemoError(RuntimeError):
    """A demo prerequisite or complete-output check failed."""


def _group_alive(pgid: int) -> bool:
    """Inspect Linux group members, excluding zombies that only a parent can reap."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            fields = (process / "stat").read_bytes().rsplit(b")", 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if int(fields[2]) == pgid and fields[0] not in (b"Z", b"X"):
            return True
    return False


def _stop_group(worker: subprocess.Popen, pgid: int) -> None:
    # The leader may already have exited. Its saved PGID still owns the children.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            worker.poll()
            if not _group_alive(pgid):
                break
            time.sleep(0.02)
        if not _group_alive(pgid):
            break
    worker.wait(timeout=1)
    if _group_alive(pgid):
        raise RuntimeError("demo worker group still has live processes after SIGKILL")


def _emit(message: str, *, stream=None) -> None:
    """Best-effort console output: a stalled consumer cannot delay cleanup.

    Use one nonblocking descriptor write with no Python output buffer. A partial
    write or EAGAIN drops only the console copy; worker.log retains every byte.
    In-memory streams used by callers/tests have no descriptor or backpressure.
    """
    stream = sys.stdout if stream is None else stream
    try:
        descriptor = stream.fileno()
    except (AttributeError, io.UnsupportedOperation):
        stream.write(message)
        stream.flush()
        return
    blocking = os.get_blocking(descriptor)
    try:
        os.set_blocking(descriptor, False)
        try:
            os.write(descriptor, message.encode("utf-8", errors="replace"))
        except BlockingIOError:
            pass
    finally:
        os.set_blocking(descriptor, blocking)


def _forward_log(reader, limit: int = 8192) -> None:
    data = reader.read(limit)
    if data:
        _emit(data.decode("utf-8", errors="replace"))


def _supervise(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout: float,
) -> int:
    """Supervise the fixed worker/toolchain group; retain merged regular-file logs."""
    deadline = time.monotonic() + timeout
    pending_signal = 0
    worker = None
    pgid = None
    outcome = 1

    def cancelled(signum, _frame):
        nonlocal pending_signal
        if not pending_signal:
            pending_signal = signum

    previous = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, cancelled)
        with log_path.open("xb", buffering=0) as log, log_path.open("rb", buffering=0) as reader:
            worker = subprocess.Popen(
                command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            pgid = worker.pid
            while True:
                if pending_signal:
                    _emit(f"demo: cancelled by {signal.Signals(pending_signal).name}\n", stream=sys.stderr)
                    outcome = 128 + pending_signal
                    break
                if time.monotonic() >= deadline:
                    _emit(f"demo: global timeout after {timeout:g} seconds\n", stream=sys.stderr)
                    outcome = 124
                    break
                _forward_log(reader)
                result = worker.poll()
                if result is not None:
                    _forward_log(reader, 65536)
                    if _group_alive(pgid):
                        _emit("demo: worker exited with live child processes\n", stream=sys.stderr)
                        outcome = 1
                    else:
                        outcome = result if result >= 0 else 128 - result
                    break
                time.sleep(0.02)
    finally:
        try:
            if worker is not None and pgid is not None:
                _stop_group(worker, pgid)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return 128 + pending_signal if pending_signal and outcome == 0 else outcome


def _preflight() -> None:
    """Check installed prerequisites without building, syncing or downloading."""
    for command in ("uv", "git", "pdflatex"):
        if shutil.which(command) is None:
            raise DemoError(f"missing dependency: {command}; run make demo-setup")
    renderer_python = ROOT / "renderer/.venv/bin/python"
    if not renderer_python.is_file():
        raise DemoError("missing renderer environment; run make demo-setup")
    try:
        import z3
        from native._lib import library

        library()
        z3.get_version_string()
        subprocess.run(
            [str(renderer_python), "-c", (
                "import numpy; from PIL import Image; "
                "from wang_explain import explain_font; explain_font(14)"
            )],
            cwd=ROOT / "renderer", check=True, capture_output=True, text=True,
            timeout=30,
        )
    except (ImportError, OSError, subprocess.SubprocessError) as error:
        raise DemoError(
            f"installed dependency check failed: {error}; run make demo-setup"
        ) from error


def _worker(input_path: Path, run_root: Path, event_capacity: int) -> int:
    try:
        content = input_path.read_bytes()
        source_copy = run_root / "input.cm13"
        with source_copy.open("xb") as target:
            target.write(content)
        source_copy.chmod(0o444)
        metadata = {
            "original_path": str(input_path),
            "original_name": input_path.name,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        with (run_root / "input.json").open("x", encoding="utf-8") as target:
            json.dump(metadata, target, ensure_ascii=True, indent=2)
            target.write("\n")
        print("input=" + json.dumps(metadata, ensure_ascii=True), flush=True)
        print("Preflight", flush=True)
        sys.path.insert(0, str(ROOT / "python"))
        _preflight()
        from dossier.multi_engine import generate_input_dossier
        from formats.run_dossier_v2_bundle import load_run_dossier_v2
        from native.formula_adapter import FormulaLoadError

        try:
            destination = generate_input_dossier(
                source_copy, run_root / "dossier", include_pdf=True,
                event_capacity=event_capacity,
                progress=lambda label: print(label, flush=True),
            )
        except FormulaLoadError as error:
            raise DemoError(f"malformed input or parser failure: {error}") from error
        run = load_run_dossier_v2(destination / "run.json")
        print(f"Verified result: {run['reference']['status'].upper()}", flush=True)
        return 0
    except Exception as error:
        print(f"demo worker: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1


def _positive_timeout(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be finite and positive") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return seconds


def _event_capacity(value: str) -> int:
    try:
        capacity = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("event capacity must be an integer in [2, 100000]") from error
    if not 2 <= capacity <= 100_000:
        raise argparse.ArgumentTypeError("event capacity must be an integer in [2, 100000]")
    return capacity


def _new_run(output: Path | None) -> Path:
    if output is not None:
        run = output.absolute()
        try:
            run.mkdir(parents=True)
        except FileExistsError as error:
            raise DemoError(f"output already exists: {run}") from error
        return run
    directory = ROOT / "build/demo"
    directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=directory))


def _check_complete_output(run_root: Path) -> Path:
    dossier = run_root / "dossier"
    for name in ("run.json", "report.tex", "report.pdf", "assets/narrative/manifest.json"):
        path = dossier / name
        if not path.is_file() or path.stat().st_size == 0:
            raise DemoError(f"worker did not produce a complete dossier: missing {name}")
    with (dossier / "report.pdf").open("rb") as pdf:
        if pdf.read(5) != b"%PDF-":
            raise DemoError("worker did not produce a valid PDF header")
    return dossier


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", nargs="?", default=os.environ.get("TILING_DEMO_INPUT"),
        help="new CM1-in-3 file",
    )
    parser.add_argument(
        "--output", type=Path,
        help="new diagnostic run directory (default: unique directory in build/demo)",
    )
    parser.add_argument(
        "--timeout", type=_positive_timeout,
        default=os.environ.get("TILING_DEMO_TIMEOUT", "300"),
        help="global timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--event-capacity", type=_event_capacity, default=100_000,
        help="maximum events per native trace, 2..100000 (default: 100000)",
    )
    args = parser.parse_args(arguments)
    if not args.input:
        parser.error("an input file is required: make demo INPUT=path.cm13")
    if not sys.platform.startswith("linux"):
        parser.error("the demo currently supports Linux")
    try:
        run_root = _new_run(args.output)
        _emit(f"diagnostics={run_root}\n")
        environment = os.environ.copy()
        environment.update(UV_OFFLINE="1", UV_NO_SYNC="1", UV_PYTHON_DOWNLOADS="never")
        environment.pop("UV_PROJECT_ENVIRONMENT", None)
        command = [
            str(ROOT / ".venv/bin/python"), "-u", str(Path(__file__).resolve()),
            "--_worker", str(Path(args.input).absolute()), str(run_root), str(args.event_capacity),
        ]
        result = _supervise(
            command, cwd=ROOT, env=environment,
            log_path=run_root / "worker.log", timeout=args.timeout,
        )
        if result:
            _emit(f"demo: no completed dossier; diagnostics retained in {run_root}\n", stream=sys.stderr)
            return result
        destination = _check_complete_output(run_root)
        _emit(f"dossier={destination}\n")
        _emit(f"pdf={destination / 'report.pdf'}\n")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        _emit(f"demo: {error}\n", stream=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--_worker":
        raise SystemExit(_worker(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])))
    raise SystemExit(main())
