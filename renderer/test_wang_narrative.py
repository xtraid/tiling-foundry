from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

from wang_hex_port import WangSquareRenderError
from wang_generalized import generalized_specification_sha256
from wang_narrative import (
    render_generalized_assets,
    render_overview_assets,
    render_presentation_status,
    render_verification_assets,
    render_witness_assets,
)


RENDERER = Path(__file__).resolve().parent
ROOT = RENDERER.parent
MANIFEST = ROOT / "tests/fixtures/pipeline_sat_reduction_explain/manifest.json"
SOLUTION = ROOT / "tests/fixtures/wang_solution_v1_square_sat.json"


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _run_record(status: str) -> dict[str, object]:
    performed = status == "sat"
    checks = {}
    specifications = (
        ("boolean_z3_assignment", "oracles.witness_check.is_valid_assignment"),
        ("reference_tiling", "oracles.tiling_check.is_valid_tiling"),
        ("reference_assignment", "oracles.witness_check.is_valid_assignment"),
        ("optimized_tiling", "oracles.tiling_check.is_valid_tiling"),
        ("optimized_assignment", "oracles.witness_check.is_valid_assignment"),
        ("wang_z3_tiling", "oracles.tiling_check.is_valid_tiling"),
    )
    for name, checker in specifications:
        checks[name] = {
            "checker": checker,
            "performed": performed,
            "passed": True if performed else None,
            "witness_sha256": "1" * 64 if performed else None,
        }
    agreement = {
        "expected_status": status,
        "boolean_z3_status": status,
        "reference_status": status,
        "optimized_status": status,
        "wang_z3_status": status,
        "all_status_equal": True,
        "sat_witnesses_valid": True if status == "sat" else None,
        "passed": True,
    }
    payload = {"verification": checks, "agreement": agreement}
    source_sha256 = hashlib.sha256(
        (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "schema": "wang-verification-receipts-v1",
        "expected_status": status,
        **payload,
        "source_sha256": source_sha256,
    }


def test_verification_composition_is_deterministic_for_sat_and_unsat(tmp_path):
    for status in ("sat", "unsat"):
        run = tmp_path / f"{status}.json"
        run.write_text(json.dumps(_run_record(status)) + "\n", encoding="utf-8")
        first = render_verification_assets(run, tmp_path / f"{status}-first")
        render_verification_assets(run, tmp_path / f"{status}-second")
        assert _tree_bytes(tmp_path / f"{status}-first") == _tree_bytes(
            tmp_path / f"{status}-second"
        )
        assert first.fallback.name == "frame-05.png"
        with Image.open(first.animation) as animation:
            assert animation.n_frames == 6


def test_verification_composition_rejects_partial_or_forged_receipts(tmp_path):
    source = tmp_path / "forged.json"
    document = _run_record("sat")
    del document["agreement"]["reference_status"]
    source.write_text(json.dumps(document) + "\n", encoding="utf-8")
    with pytest.raises(WangSquareRenderError, match="agreement must be closed"):
        render_verification_assets(source, tmp_path / "output")


def test_witness_and_generalized_assets_reuse_checked_presentations(tmp_path):
    first = render_witness_assets(SOLUTION, tmp_path / "witness-first")
    render_witness_assets(SOLUTION, tmp_path / "witness-second")
    assert _tree_bytes(tmp_path / "witness-first") == _tree_bytes(
        tmp_path / "witness-second"
    )
    assert first.animation.fallback.name == "frame-03.png"
    assert first.square.is_file()
    assert first.generalized.is_file()
    assert first.hex.is_file()

    generalized = render_generalized_assets(MANIFEST, tmp_path / "generalized")
    assert generalized.sheet.is_file()
    assert generalized.legend.is_file()
    assert generalized_specification_sha256() == (
        "5e8e6589271f9059b5ed81df00db4e303b338d5243caa475ed09135b129e3cf2"
    )


def test_overview_and_unsat_status_are_static_fallback_safe(tmp_path):
    status = render_presentation_status("unsat", tmp_path / "status.png")
    sources = (status,) * 8
    first = render_overview_assets(
        sources,
        status,
        tmp_path / "overview-first",
        include_sat_story=False,
    )
    render_overview_assets(
        sources,
        status,
        tmp_path / "overview-second",
        include_sat_story=False,
    )
    assert _tree_bytes(tmp_path / "overview-first") == _tree_bytes(
        tmp_path / "overview-second"
    )
    assert first.home_preview is None
    assert first.worked_example is None
    assert first.animation.contact_sheet.is_file()


def test_narrative_module_imports_no_native_or_z3_producer():
    assert "z3" not in sys.modules
    assert not any(name.startswith("native") for name in sys.modules)
