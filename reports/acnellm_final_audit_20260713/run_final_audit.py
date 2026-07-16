"""Final replay of the prior S01-S12 + seeded J01-J04 audit protocol."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "reports" / "acnellm_fix_verification_20260713" / "run_fix_verification.py"
OUT = HERE / "live_final_audit_evidence.json"
JITTER_SEED = 2026071321


def main() -> None:
    spec = importlib.util.spec_from_file_location("acnellm_prior_fix_replay", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load prior replay: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    module.JITTER_SEED = JITTER_SEED
    module.main()

    data = json.loads(OUT.read_text(encoding="utf-8"))
    data["immediate_comparison_baseline"] = str(
        ROOT
        / "reports"
        / "acnellm_fix_verification_20260713"
        / "live_fix_verification_evidence.json"
    )
    data["final_audit"] = {
        "jitter_seed": JITTER_SEED,
        "standard_sessions_unchanged": True,
        "source_of_truth": "current HEAD plus staged working-tree changes",
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
