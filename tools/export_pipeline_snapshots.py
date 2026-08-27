#!/usr/bin/env python3
"""Export static explainability snapshots from one real CM13 reduction."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from formats.pipeline_snapshot import (  # noqa: E402
    dump_pipeline_snapshots,
    dump_reduction_explanation_snapshots,
    load_pipeline_snapshot,
)
from native.reduction_adapter import (  # noqa: E402
    load_formula_and_region,
    load_formula_region_and_explanation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "parse a CM13 formula, build its Yang-Zhang region, and export "
            "hash-bound static snapshots for the isolated renderer"
        )
    )
    parser.add_argument("source", type=Path, help="input .cm13 formula")
    parser.add_argument("manifest", type=Path, help="output manifest JSON")
    parser.add_argument("--origin-x", type=int, default=0)
    parser.add_argument("--origin-y", type=int, default=0)
    parser.add_argument(
        "--reduction-explanation",
        action="store_true",
        help="include native signal, permutation, and gadget provenance",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    if args.reduction_explanation:
        formula, region, explanation = load_formula_region_and_explanation(
            args.source
        )
        manifest_path = dump_reduction_explanation_snapshots(
            args.manifest,
            args.source,
            formula,
            region,
            explanation,
            origin=(args.origin_x, args.origin_y),
        )
    else:
        formula, region = load_formula_and_region(args.source)
        manifest_path = dump_pipeline_snapshots(
            args.manifest,
            args.source,
            formula,
            region,
            origin=(args.origin_x, args.origin_y),
        )
    manifest = load_pipeline_snapshot(manifest_path)
    artifacts = manifest["artifacts"]
    print(f"manifest={manifest_path}")
    artifact_names = ["formula", "tileset", "region"]
    if "reduction" in artifacts:
        artifact_names.append("reduction")
    for name in artifact_names:
        artifact_path = manifest_path.parent / artifacts[name]["path"]
        print(f"{name}={artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
