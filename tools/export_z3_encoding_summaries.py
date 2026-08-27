#!/usr/bin/env python3
"""Export explicit Boolean and Wang Z3 encoding summaries for one formula."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from formats.pipeline_snapshot import (  # noqa: E402
    _encode_document,
    _write_atomic,
    build_region_snapshot,
)
from formats.z3_encoding_summary import (  # noqa: E402
    build_boolean_z3_summary,
    build_wang_z3_summary,
    validate_z3_encoding_summary,
)
from native.reduction_adapter import load_formula_and_region  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "run the fixed-parameter Boolean and Wang Z3 oracles and export "
            "their project-owned encoding order, result, model, and stable stats"
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output_directory", type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    formula, region = load_formula_and_region(args.source)
    source_digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    region_document = build_region_snapshot(
        region,
        source_formula_sha256=source_digest,
        origin=(0, 0),
    )
    region_digest = hashlib.sha256(_encode_document(region_document)).hexdigest()
    documents = {
        "boolean-z3.json": build_boolean_z3_summary(
            formula,
            source_formula_sha256=source_digest,
        ),
        "wang-z3.json": build_wang_z3_summary(
            formula,
            region,
            source_formula_sha256=source_digest,
            region_sha256=region_digest,
        ),
    }
    for name, document in documents.items():
        validate_z3_encoding_summary(document)
        destination = args.output_directory / name
        _write_atomic(destination, _encode_document(document))
        print(f"summary={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
