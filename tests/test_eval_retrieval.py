"""Tests cho scripts/eval_retrieval.py — không cần KB hay Ollama."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.eval.metrics import recall_at_k, mrr_at_k, ndcg_at_k, aggregate


# ─── Mock objects ─────────────────────────────────────────────────────────────

class _MockChunk:
    def __init__(self, chunk_id: str):
        self.chunk_id = chunk_id


class _MockRetrieval:
    def __init__(self, ids: list[str]):
        self.chunks = [_MockChunk(cid) for cid in ids]


class _MockRetriever:
    """Trả ids theo thứ tự cố định để test deterministic."""
    def __init__(self, ids: list[str]):
        self._ids = ids

    def retrieve(self, query: str, top_k: int = 10, mode: str = "sparse"):
        return _MockRetrieval(self._ids[:top_k])


# ─── Unit tests cho metrics ───────────────────────────────────────────────────

def test_hit_at_k_found():
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c2"}
    assert recall_at_k(retrieved, relevant, 3) == 1.0


def test_hit_at_k_not_found():
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c9"}
    assert recall_at_k(retrieved, relevant, 3) == 0.0


def test_recall_at_k_partial():
    retrieved = ["c1", "c2", "c3", "c4", "c5"]
    relevant = {"c2", "c5"}
    assert recall_at_k(retrieved, relevant, 3) == 0.5   # chỉ c2 trong top-3
    assert recall_at_k(retrieved, relevant, 5) == 1.0   # cả c2 và c5


def test_mrr_first_rank():
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c1"}
    assert mrr_at_k(retrieved, relevant, 10) == 1.0


def test_mrr_second_rank():
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c2"}
    assert abs(mrr_at_k(retrieved, relevant, 10) - 0.5) < 1e-9


def test_mrr_not_found():
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c9"}
    assert mrr_at_k(retrieved, relevant, 10) == 0.0


def test_ndcg_perfect():
    retrieved = ["c1", "c2"]
    relevant = {"c1", "c2"}
    assert abs(ndcg_at_k(retrieved, relevant, 5) - 1.0) < 1e-9


def test_ndcg_empty_relevant():
    assert ndcg_at_k(["c1", "c2"], set(), 5) == 0.0


def test_aggregate_basic():
    scores = [0.5, 1.0, 0.0]
    agg = aggregate(scores)
    assert abs(agg["mean"] - 0.5) < 1e-9
    assert agg["min"] == 0.0
    assert agg["max"] == 1.0
    assert agg["n"] == 3


def test_aggregate_empty():
    agg = aggregate([])
    assert agg["n"] == 0
    assert agg["mean"] == 0.0


# ─── Integration test: _run_eval với mock retriever ───────────────────────────

def _make_gt_file(cases: list[dict]) -> Path:
    """Tạo JSONL ground truth tạm."""
    p = Path(tempfile.mktemp(suffix=".jsonl"))
    with open(p, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return p


def _patch_build_retriever(monkeypatch, ids: list[str]):
    """Patch _build_retriever trong eval_retrieval để dùng mock."""
    import scripts.eval_retrieval as ev
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(ids))


def test_run_eval_perfect_retrieval(monkeypatch):
    """Khi retriever trả đúng relevant chunks → tất cả metrics = 1.0."""
    import scripts.eval_retrieval as ev
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(["cA", "cB", "cC"]))

    cases = [
        {"query": "mụn viêm", "relevant_chunk_ids": ["cA"]},
        {"query": "salicylic acid", "relevant_chunk_ids": ["cA"]},
    ]
    gt = _make_gt_file(cases)

    result = ev._run_eval(queries_path=str(gt), mode="sparse", top_k=5, verbose=False)
    s = result["summary"]

    assert s["evaluated"] == 2
    assert s["skipped_no_gt"] == 0
    assert s["hit@1"] == 1.0
    assert s["mrr@10"] == 1.0
    assert s["ndcg@5"] == 1.0


def test_run_eval_zero_retrieval(monkeypatch):
    """Khi retriever không trả chunk nào relevant → metrics = 0."""
    import scripts.eval_retrieval as ev
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(["cX", "cY"]))

    cases = [{"query": "mụn bọc", "relevant_chunk_ids": ["cA", "cB"]}]
    gt = _make_gt_file(cases)

    result = ev._run_eval(queries_path=str(gt), mode="sparse", top_k=5, verbose=False)
    s = result["summary"]

    assert s["hit@5"] == 0.0
    assert s["mrr@10"] == 0.0


def test_run_eval_skips_missing_ground_truth(monkeypatch):
    """Case không có relevant_chunk_ids → bị skip, không tính vào metrics."""
    import scripts.eval_retrieval as ev
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(["cA"]))

    cases = [
        {"query": "mụn viêm", "relevant_chunk_ids": []},       # skip
        {"query": "da dầu", "relevant_chunk_ids": ["cA"]},      # evaluate
    ]
    gt = _make_gt_file(cases)

    result = ev._run_eval(queries_path=str(gt), mode="sparse", top_k=5, verbose=False)
    s = result["summary"]

    assert s["evaluated"] == 1
    assert s["skipped_no_gt"] == 1


def test_run_eval_saves_json_report(monkeypatch, tmp_path):
    """Kiểm tra output JSON được ghi đúng."""
    import scripts.eval_retrieval as ev
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(["cA"]))

    cases = [{"query": "mụn", "relevant_chunk_ids": ["cA"]}]
    gt = _make_gt_file(cases)
    out = tmp_path / "report.json"

    ev._run_eval(queries_path=str(gt), mode="sparse", verbose=False, out=str(out))

    assert out.exists()
    data = json.loads(out.read_text())
    assert "summary" in data
    assert "per_query" in data
    assert len(data["per_query"]) == 1
    assert data["per_query"][0]["query"] == "mụn"


def test_run_eval_target_checks(monkeypatch):
    """all_targets_met = True khi retrieval tốt (all metrics trên threshold)."""
    import scripts.eval_retrieval as ev
    # Perfect retriever → tất cả metrics = 1.0 >> mọi threshold
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(["cA", "cB"]))

    cases = [
        {"query": "q1", "relevant_chunk_ids": ["cA"]},
        {"query": "q2", "relevant_chunk_ids": ["cB"]},
    ]
    gt = _make_gt_file(cases)
    result = ev._run_eval(queries_path=str(gt), mode="sparse", verbose=False)

    assert result["summary"]["all_targets_met"] is True


def test_run_eval_n_limits_cases(monkeypatch):
    """--n giới hạn số câu hỏi được evaluate."""
    import scripts.eval_retrieval as ev
    monkeypatch.setattr(ev, "_build_retriever", lambda mode: _MockRetriever(["cA"]))

    cases = [{"query": f"q{i}", "relevant_chunk_ids": ["cA"]} for i in range(10)]
    gt = _make_gt_file(cases)

    result = ev._run_eval(queries_path=str(gt), n=3, mode="sparse", verbose=False)
    assert result["summary"]["evaluated"] == 3
