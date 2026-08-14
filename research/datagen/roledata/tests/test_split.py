from __future__ import annotations

import json
from pathlib import Path

from datagen.roledata.config import Config
from datagen.roledata.finalize.split import SAFETY_HOLDOUT_CASES, split
from datagen.roledata.writer import iter_jsonl


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_split_is_deterministic_stratified_and_has_zero_leakage(tmp_path: Path) -> None:
    cfg = Config(api_key="offline-test", output_dir=tmp_path / "output")
    cases = [
        "R1_identity",
        "R2_depth_adaptation",
        "R8_meta_jailbreak",
        "B1_grounded_role",
        "B2_missing_answer",
        "B4_conflicting_docs",
        "K1_knowledge_anchor",
    ]
    records = [
        {"id": f"record-{index:03d}", "sample_kind": cases[index % len(cases)]}
        for index in range(70)
    ]
    _write_jsonl(cfg.train_path, records)

    summary = split(cfg, seed=42)
    assert summary["counts"] == {"train": 59, "val": 6, "holdout": 5}
    assert set(summary["safety_holdout_cases"]) == SAFETY_HOLDOUT_CASES
    assert summary["leakage"] == 0

    paths = (cfg.train_split_path, cfg.val_split_path, cfg.holdout_split_path)
    ids = [{record["id"] for record in iter_jsonl(path)} for path in paths]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])
    assert len(set().union(*ids)) == len(records)

    first_bytes = [path.read_bytes() for path in paths]
    split(cfg, seed=42)
    assert [path.read_bytes() for path in paths] == first_bytes

