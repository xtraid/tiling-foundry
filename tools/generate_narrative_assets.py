#!/usr/bin/env python3
"""CLI for the fixed shared narrative-asset pass."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from dossier.narrative_assets import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
