from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from datagen.roledata.config import Config
from datagen.roledata.finalize.export import export
from datagen.roledata.writer import iter_jsonl


def _config(tmp_path: Path) -> tuple[Config, str]:
    anchor = "Bạn là AcneLLM, trợ lý tư vấn da mụn bằng tiếng Việt."
    modelfile = tmp_path / "Modelfile"
    canonical = tmp_path / "canonical.txt"
    modelfile.write_text(f'FROM test\nSYSTEM """{anchor}"""\n', encoding="utf-8")
    canonical.write_text(anchor + "\n", encoding="utf-8")
    return (
        Config(
            api_key="offline-test",
            anchor_path=modelfile,
            canonical_path=canonical,
            output_dir=tmp_path / "output",
        ),
        anchor,
    )


def _record(record_id: str, anchor: str) -> dict:
    return {
        "id": record_id,
        "sample_kind": "R1_identity",
        "messages": [
            {"role": "system", "content": anchor},
            {"role": "user", "content": "Bạn là ai?"},
            {"role": "assistant", "content": "Mình là AcneLLM, hỗ trợ tư vấn sơ bộ về mụn."},
        ],
    }


def _write_train(cfg: Config, records: list[dict]) -> None:
    cfg.train_split_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.train_split_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_export_schema_parity_card_and_checksum(tmp_path: Path) -> None:
    cfg, anchor = _config(tmp_path)
    _write_train(cfg, [_record("one", anchor), _record("two", anchor)])

    summary = export(cfg)
    rows = list(iter_jsonl(cfg.export_path))
    assert summary["records"] == 2
    assert all(set(row) == {"id", "messages"} for row in rows)
    assert all(row["messages"][0]["content"] == anchor for row in rows)
    assert hashlib.sha256(cfg.export_path.read_bytes()).hexdigest() == summary["checksum_sha256"]
    assert summary["checksum_sha256"] in cfg.checksum_path.read_text(encoding="ascii")
    assert summary["anchor_sha256"] in cfg.dataset_card_path.read_text(encoding="utf-8")
    dataset_info = json.loads(cfg.dataset_info_path.read_text(encoding="utf-8"))
    assert dataset_info["acnellm_role_lora"]["formatting"] == "sharegpt"


def test_export_rejects_system_drift(tmp_path: Path) -> None:
    cfg, anchor = _config(tmp_path)
    drifted = _record("drifted", anchor)
    drifted["messages"][0]["content"] = "not-canonical"
    _write_train(cfg, [drifted])
    with pytest.raises(ValueError, match="parity"):
        export(cfg)
