"""Rerun the paired VI/EN retrieval probe without overwriting prior evidence."""
from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "reports" / "acnellm_technical_audit_20260713" / "run_retrieval_probes.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("acnellm_prior_retrieval_probe", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load prior probe: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = HERE / "retrieval_recheck.json"
    module.main()
    print(module.OUT)


if __name__ == "__main__":
    main()
