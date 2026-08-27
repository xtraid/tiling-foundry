#!/usr/bin/env python3
"""Export one bounded observed native solve as a hash-bound v3 bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from formats.solver_trace_snapshot import (  # noqa: E402
    dump_solver_trace_bundle,
    load_solver_trace_bundle,
)
from native.trace_pipeline import solve_native_pipeline_trace  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "parse and reduce a CM13 formula, run one native solver, and "
            "export its bounded semantic event trace"
        )
    )
    parser.add_argument("source", type=Path, help="input .cm13 formula")
    parser.add_argument("manifest", type=Path, help="output v3 manifest JSON")
    parser.add_argument(
        "--solver",
        choices=("reference", "optimized"),
        default="reference",
    )
    parser.add_argument("--event-capacity", type=int, default=20_000)
    parser.add_argument("--checkpoint-interval", type=int, default=64)
    parser.add_argument("--checkpoint-capacity", type=int, default=64)
    parser.add_argument("--origin-x", type=int, default=0)
    parser.add_argument("--origin-y", type=int, default=0)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    values = solve_native_pipeline_trace(
        args.source,
        optimized=args.solver == "optimized",
        event_capacity=args.event_capacity,
        checkpoint_interval=args.checkpoint_interval,
        checkpoint_capacity=args.checkpoint_capacity,
    )
    manifest_path = dump_solver_trace_bundle(
        args.manifest,
        args.source,
        *values,
        origin=(args.origin_x, args.origin_y),
    )
    manifest, _ = load_solver_trace_bundle(manifest_path)
    print(f"manifest={manifest_path}")
    for name, reference in manifest["artifacts"].items():
        if reference is not None:
            print(f"{name}={manifest_path.parent / reference['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
