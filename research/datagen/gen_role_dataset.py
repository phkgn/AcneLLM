"""Backward-compatible entry point for the refactored one-command pipeline.

Prefer ``python -m datagen.main``.  This wrapper remains so older notes and
scripts fail forward into the same implementation instead of forking behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path


if __package__:
    from .main import main
else:  # ``python datagen/gen_role_dataset.py`` compatibility
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from datagen.main import main


if __name__ == "__main__":
    raise SystemExit(main())
