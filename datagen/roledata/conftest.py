from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture(name="tmp_path")
def workspace_tmp_path() -> Path:
    """Keep pytest scratch files inside the writable roledata module."""
    root = Path(__file__).resolve().parent / "tests" / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
