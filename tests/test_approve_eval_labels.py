from pathlib import Path

from scripts.approve_eval_labels import _load_jsonl


def test_load_jsonl_reads_rows(tmp_path):
    p = tmp_path / "input.jsonl"
    p.write_text('{"query":"q1"}\n{"query":"q2"}\n', encoding="utf-8")
    rows = _load_jsonl(str(p))
    assert [r["query"] for r in rows] == ["q1", "q2"]
