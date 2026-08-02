"""Sinh seed datasets v1 từ dữ liệu có sẵn trong repo (một lần, rồi duyệt tay).

- retrieval_test.jsonl  ← data/eval_labels/approved_eval_queries.jsonl
    CẢNH BÁO: nhãn gốc suggestion_mode=bm25 → pooling bias (R2 blueprint).
    Mọi row đánh dấu annotation_status="needs_relabel"; phải relabel bằng pooled
    candidates (BM25 ∪ dense ∪ hybrid) trước khi dùng làm qrels chính thức.
- dev_tuning.jsonl    ← data/sample_queries.jsonl (dev only, không báo cáo kết quả)

Usage: python -m evaluation.datasets.build_seeds
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, read_jsonl, write_jsonl  # noqa: E402

V1 = ROOT / "evaluation" / "datasets" / "v1"


def build_qrels_seed() -> None:
    src = ROOT / "data" / "eval_labels" / "approved_eval_queries.jsonl"
    rows = []
    for i, old in enumerate(read_jsonl(src)):
        approved = [str(c) for c in old.get("relevant_chunk_ids", [])]
        suggested = [str(c) for c in old.get("suggested_relevant_chunk_ids", [])]
        rows.append({
            "sample_id": f"d8-{i:04d}",
            "user_query": old["query"],
            "task_type": "retrieval_qrels",
            "split": "qrels",
            "dataset_version": "v1.0-seed",
            "source_provenance": "legacy_approved",
            "user_context": old.get("user_context", {}),
            "relevant_chunk_ids": approved,
            # binary tạm thời: approved=2 (trả lời trực tiếp — cần xem lại), suggested-only=1
            "relevance_grade": {**{c: 1 for c in suggested}, **{c: 2 for c in approved}},
            "annotation_status": "needs_relabel",
            "human_notes": "seed từ nhãn bm25-biased; relabel bằng pooled candidates",
        })
    write_jsonl(V1 / "retrieval_test.jsonl", rows)
    print(f"retrieval_test.jsonl: {len(rows)} rows (TẤT CẢ needs_relabel)")


def build_dev_seed() -> None:
    src = ROOT / "data" / "sample_queries.jsonl"
    rows = []
    for i, old in enumerate(read_jsonl(src)):
        rows.append({
            "sample_id": f"d1-{i:04d}",
            "user_query": old["query"],
            "task_type": "unlabeled",
            "split": "dev",
            "dataset_version": "v1.0-seed",
            "source_provenance": "legacy_sample",
            "user_context": old.get("user_context", {}),
            "annotation_status": "draft",
        })
    write_jsonl(V1 / "dev_tuning.jsonl", rows)
    print(f"dev_tuning.jsonl: {len(rows)} rows")


if __name__ == "__main__":
    V1.mkdir(parents=True, exist_ok=True)
    build_qrels_seed()
    build_dev_seed()
    print("\nD2/D4/D5/D6/D7 cần viết tay/duyệt theo §5 blueprint — tạo file cùng schema rồi "
          "`python -m evaluation.datasets.registry freeze evaluation/datasets/v1`")
