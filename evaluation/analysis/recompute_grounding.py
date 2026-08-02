"""Recompute grounding on an immutable legacy D1 artifact into a new run dir."""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.analysis.report import _grounding_summary  # noqa: E402
from evaluation.common import (  # noqa: E402
    REPORTS_DIR,
    ROOT,
    build_run_meta,
    corpus_versions,
    ensure_repo_importable,
    read_jsonl,
    sha256_file,
    write_jsonl,
)
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.deterministic import evaluate_record  # noqa: E402
from evaluation.metrics.grounding import GroundingScorer  # noqa: E402

ensure_repo_importable()


def reconstruct_contexts(record: dict, chunk_text: dict[str, str]) -> dict:
    rebuilt = deepcopy(record)
    trace = dict(rebuilt.get("trace") or {})
    trace["context_chunks"] = [
        {"chunk_id": chunk_id, "text": chunk_text[chunk_id]}
        for chunk_id in rebuilt.get("used_chunks") or []
        if chunk_id in chunk_text
    ]
    rebuilt["trace"] = trace
    return rebuilt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact", default="evaluation/reports/main_2x2_t3/s3.results.jsonl"
    )
    parser.add_argument(
        "--dataset", default="evaluation/datasets/v1/dev_tuning.jsonl"
    )
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    artifact = (ROOT / args.artifact).resolve()
    dataset_path = (ROOT / args.dataset).resolve()
    if dataset_path.name != "dev_tuning.jsonl":
        parser.error("legacy grounding recompute is restricted to D1")

    source_meta_path = artifact.parent / "run_meta.json"
    source_meta = json.loads(source_meta_path.read_text(encoding="utf-8"))
    current_bm25_hash = corpus_versions().get("bm25_sha256")
    source_bm25_hash = source_meta.get("bm25_sha256")
    if not source_bm25_hash or source_bm25_hash != current_bm25_hash:
        raise RuntimeError(
            "Cannot reconstruct legacy contexts: BM25 corpus hash does not match"
        )

    with (ROOT / "data" / "bm25_index.pkl").open("rb") as handle:
        index = pickle.load(handle)  # noqa: S301 - trusted, hash-verified repo artifact
    chunk_text = dict(zip(index["chunk_ids"], index["texts"]))
    records = [reconstruct_contexts(row, chunk_text) for row in read_jsonl(artifact)]
    samples = {
        sample["sample_id"]: sample for sample in load_dataset(dataset_path)
    }

    from acne_llm.config import settings
    from acne_llm.rag.embedder import Embedder

    scorer = GroundingScorer(embedder=Embedder(
        model_name=settings.embedding_model,
        device=settings.device,
        lazy=True,
    ))
    deterministic: list[dict] = []
    for record in records:
        if not record.get("ok") or record.get("sample_id") not in samples:
            continue
        record["grounding"] = scorer.score_record(record)
        deterministic.append(evaluate_record(record, samples[record["sample_id"]]))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPORTS_DIR / f"round2_legacy_grounding_d1_{timestamp}"
    )
    out_dir.mkdir(parents=True, exist_ok=False)
    output_results = out_dir / artifact.name
    write_jsonl(output_results, records)
    report = {
        "source_artifact": args.artifact,
        "source_artifact_sha256": sha256_file(artifact),
        "source_run_meta": str(source_meta_path.relative_to(ROOT)).replace("\\", "/"),
        "dataset": args.dataset,
        "split": "D1",
        "context_reconstruction": "used_chunks -> hash-matched current BM25 texts",
        "source_bm25_sha256": source_bm25_hash,
        **_grounding_summary(deterministic),
        "n_records": len(records),
        "run_meta": build_run_meta({"recomputed_from": args.artifact}),
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
