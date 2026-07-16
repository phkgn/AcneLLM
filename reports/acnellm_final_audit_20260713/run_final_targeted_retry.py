"""Repeat the exact clean retry cases used by the immediately prior audit."""
from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "reports" / "acnellm_fix_verification_20260713" / "run_targeted_clean_retry.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("acnellm_prior_clean_retry", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load prior retry: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.main()


if __name__ == "__main__":
    main()
