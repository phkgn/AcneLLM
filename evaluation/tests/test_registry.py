import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.datasets.registry import freeze_dir, load_dataset, validate_file

GOOD = {
    "sample_id": "t-001", "user_query": "Mụn viêm ở cằm là do đâu?",
    "task_type": "knowledge", "split": "test", "dataset_version": "v1.0",
    "source_provenance": "human_written", "relevance_grade": {"c1": 2},
}


def _write(tmp_path: Path, rows: list[dict], name="d.jsonl") -> Path:
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                 encoding="utf-8")
    return p


def test_valid_file_passes(tmp_path):
    p = _write(tmp_path, [GOOD])
    assert validate_file(p) == []
    rows = load_dataset(p)
    assert rows[0]["conversation_history"] == []          # default filled


def test_missing_required_and_dup_id(tmp_path):
    bad = {k: v for k, v in GOOD.items() if k != "task_type"}
    p = _write(tmp_path, [bad, GOOD, GOOD])
    errs = validate_file(p)
    assert any("task_type" in e for e in errs)
    assert any("trùng" in e for e in errs)


def test_bad_grade(tmp_path):
    p = _write(tmp_path, [{**GOOD, "relevance_grade": {"c1": 5}}])
    assert any("relevance_grade" in e for e in validate_file(p))


def test_openai_synthetic_provenance_is_valid(tmp_path):
    p = _write(tmp_path, [{**GOOD, "source_provenance": "synthetic_openai"}])
    assert validate_file(p) == []


def test_freeze_detects_tampering(tmp_path):
    p = _write(tmp_path, [GOOD])
    freeze_dir(tmp_path)
    load_dataset(p)                                        # OK khi chưa sửa
    p.write_text(p.read_text(encoding="utf-8") + "\n" +
                 json.dumps({**GOOD, "sample_id": "t-002"}, ensure_ascii=False),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="freeze"):
        load_dataset(p)
