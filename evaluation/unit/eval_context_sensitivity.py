"""D1-only context sensitivity probes using local Ollama and in-memory context.

No judge API is called and the canary is never inserted into the persistent KB.
Each case compares the same query under correct vs unrelated retrieved context.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.adapters._repo import build_eval_container, normalize_query  # noqa: E402
from evaluation.common import (  # noqa: E402
    REPORTS_DIR,
    ROOT,
    build_run_meta,
    load_yaml,
    read_jsonl,
)
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.grounding import (  # noqa: E402
    contexts_from_record,
    normalize_grounding_text,
)


CANARY_TOKEN = "EVALCANARY-L42"
CANARY_QUERY = (
    "Theo tài liệu giả lập, tên mã của kế hoạch mô phỏng là gì? "
    "Chỉ trả lời tên mã được nêu trong tài liệu."
)
CANARY_TEXT = (
    "Tài liệu giả lập chỉ dùng cho đánh giá độ nhạy ngữ cảnh. "
    f"Tên mã của kế hoạch mô phỏng là {CANARY_TOKEN}. "
    "Đây không phải hoạt chất, sản phẩm hay hướng dẫn dùng trên người."
)
STRICT_GROUNDING_INSTRUCTION = (
    "[YÊU CẦU GROUNDING CHO ABLATION]\n"
    "Chỉ dùng thông tin có trong tài liệu tham khảo bên dưới. "
    "Nếu tài liệu không đề cập, phải nói rõ là tài liệu không đề cập; "
    "không bổ sung kiến thức từ trí nhớ của mô hình."
)


def add_in_memory_canary(retrieval):
    """Return a model copy with one ephemeral chunk; never call a KB write API."""
    from acne_llm.schemas import RetrievedChunk

    canary = RetrievedChunk(
        chunk_id="eval-only-canary",
        source="eval-only",
        text=CANARY_TEXT,
        score=1.0,
        metadata={"title": "Ephemeral context canary", "source": "eval-only"},
    )
    return retrieval.model_copy(update={"chunks": [canary, *retrieval.chunks]})


def char_ngram_similarity(left: str, right: str, n: int = 3) -> float:
    """Symmetric character n-gram Dice similarity."""
    a = normalize_grounding_text(left)
    b = normalize_grounding_text(right)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    def grams(value: str) -> set[str]:
        if len(value) < n:
            return {value}
        return {value[i:i + n] for i in range(len(value) - n + 1)}

    ga, gb = grams(a), grams(b)
    return 2 * len(ga & gb) / max(len(ga) + len(gb), 1)


def _embedding_cosine(embedder, left: str, right: str) -> float:
    a = np.asarray(embedder.embed_query(left), dtype=float)
    b = np.asarray(embedder.embed_query(right), dtype=float)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float((a @ b) / denominator) if denominator else 0.0


def summarize_results(
    cases: list[dict[str, Any]],
    low_sensitivity_threshold: float = 0.15,
) -> dict[str, Any]:
    if not cases:
        return {
            "n_cases": 0,
            "canary_adoption_rate": None,
            "embedding_distance_mean": None,
            "char_ngram_distance_mean": None,
            "context_swap_sensitivity_mean": None,
            "low_context_sensitivity_red_flag": None,
        }
    swap_cases = [
        case for case in cases
        if isinstance(case.get("embedding_cosine"), (int, float))
        and isinstance(case.get("char_ngram_similarity"), (int, float))
    ]
    embedding_distance = [
        1.0 - float(case["embedding_cosine"]) for case in swap_cases
    ]
    ngram_distance = [
        1.0 - float(case["char_ngram_similarity"]) for case in swap_cases
    ]
    sensitivity = [
        (embedding + ngram) / 2
        for embedding, ngram in zip(embedding_distance, ngram_distance)
    ]
    sensitivity_mean = round(mean(sensitivity), 4) if sensitivity else None
    def grounding_rate(key: str) -> float | None:
        eligible = sum(
            int((case.get(key) or {}).get("eligible_sentence_count") or 0)
            for case in cases
        )
        grounded = sum(
            int((case.get(key) or {}).get("grounded_sentence_count") or 0)
            for case in cases
        )
        return grounded / eligible if eligible else None

    return {
        "n_cases": len(cases),
        "canary_adoption_rate": round(
            mean(1.0 if case.get("canary_adopted") else 0.0 for case in cases), 4
        ),
        "strict_canary_adoption_rate": round(
            mean(
                1.0 if case.get("strict_canary_adopted") else 0.0
                for case in cases
            ),
            4,
        ),
        "baseline_grounded_sentence_rate": grounding_rate("baseline_grounding"),
        "strict_grounded_sentence_rate": grounding_rate("strict_grounding"),
        "embedding_distance_mean": (
            round(mean(embedding_distance), 4) if embedding_distance else None
        ),
        "char_ngram_distance_mean": (
            round(mean(ngram_distance), 4) if ngram_distance else None
        ),
        "context_swap_sensitivity_mean": sensitivity_mean,
        "low_context_sensitivity_threshold": low_sensitivity_threshold,
        "low_context_sensitivity_red_flag": (
            sensitivity_mean < low_sensitivity_threshold
            if sensitivity_mean is not None else None
        ),
    }


def _retrieve(container, user, config: dict):
    from acne_llm.utils.chunk_filter import drop_noisy_chunks, drop_query_mismatched_chunks
    from acne_llm.utils.retrieval_query import build_retrieval_query_from_user

    query = build_retrieval_query_from_user(
        user, clean_text_normalized=user.description
    )
    retriever = container.retriever
    if config.get("use_mmr_prefilter", True) and hasattr(retriever, "retrieve_with_mmr"):
        retrieval = retriever.retrieve_with_mmr(
            query,
            top_k=config.get("retrieve_top_k", 15),
            rerank_top_k=config.get("retrieve_top_k", 15),
            mode="hybrid",
            mmr_lambda=config.get("mmr_lambda", 0.6),
        )
    else:
        retrieval = retriever.retrieve(
            query, top_k=config.get("retrieve_top_k", 15), mode="hybrid"
        )
    if container.reranker is not None:
        retrieval = container.reranker.rerank(
            query, retrieval, top_k=config.get("rerank_top_k", 5)
        )
    filtered = drop_query_mismatched_chunks(
        drop_noisy_chunks(retrieval, min_score=0.0), query
    )
    return filtered if filtered is not None and filtered.chunks else retrieval


def _generate(container, user, retrieval, *, strict: bool = False) -> tuple[str, dict]:
    from acne_llm.chat.inline_citations import strip_inline_citations

    system, prompt = container.prompt.build(
        user,
        retrieval,
        template="stream_user.j2",
        inline_citation="off",
    )
    if strict:
        prompt = f"{STRICT_GROUNDING_INSTRUCTION}\n\n{prompt}"
    answer = strip_inline_citations(container.llm.generate_text(system, prompt))
    return answer, {
        "raw": answer,
        "rendered_user_prompt": prompt,
        "prompt_chars": len(system) + len(prompt),
        "strict_grounding_instruction": strict,
        "prompt_contains_inline_citation_instruction": "Đặt [N]" in prompt,
        "prompt_contains_chunk_ref": "chunk_ref=" in prompt,
        "prompt_contains_canary": CANARY_TOKEN in prompt,
    }


def _generate_from_rendered_prompt(
    container, user, rendered_prompt: str, *, strict: bool = False
) -> tuple[str, dict]:
    from acne_llm.chat.inline_citations import strip_inline_citations

    system, _ = container.prompt.build(
        user,
        None,
        template="stream_user.j2",
        inline_citation="off",
    )
    prompt = rendered_prompt
    if strict:
        prompt = f"{STRICT_GROUNDING_INSTRUCTION}\n\n{prompt}"
    answer = strip_inline_citations(container.llm.generate_text(system, prompt))
    return answer, {
        "raw": answer,
        "rendered_user_prompt": prompt,
        "prompt_chars": len(system) + len(prompt),
        "strict_grounding_instruction": strict,
        "reused_baseline_rendered_prompt": True,
        "prompt_contains_canary": CANARY_TOKEN in prompt,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/datasets/v1/d1_dev_seed.jsonl")
    parser.add_argument("--system", default="evaluation/configs/systems/s3.yaml")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument(
        "--baseline-run",
        default=None,
        help=(
            "reuse <system>.results.jsonl answers/rendered prompts and only generate "
            "strict + canary variants"
        ),
    )
    parser.add_argument("--low-sensitivity-threshold", type=float, default=0.15)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10:
        parser.error("--limit must be between 1 and 10 (D1 probe budget)")

    dataset_path = (ROOT / args.dataset).resolve()
    if dataset_path.name != "d1_dev_seed.jsonl":
        parser.error("context sensitivity threshold/probes are restricted to D1")
    config = load_yaml((ROOT / args.system).resolve())
    samples = load_dataset(dataset_path)[:args.limit]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPORTS_DIR / "unit" / "context_sensitivity" / timestamp
    )
    out_dir.mkdir(parents=True, exist_ok=False)

    baseline_records: dict[str, dict[str, Any]] = {}
    if args.baseline_run:
        baseline_path = (ROOT / args.baseline_run / f"{config['id']}.results.jsonl").resolve()
        baseline_records = {
            row["sample_id"]: row for row in read_jsonl(baseline_path)
        }
        missing = [sample["sample_id"] for sample in samples if sample["sample_id"] not in baseline_records]
        if missing:
            parser.error(f"baseline run missing sample ids: {missing}")

    container = build_eval_container(config.get("model"), config.get("sampling"))
    if not container.rag_ready:
        raise RuntimeError("KB is not ready for context sensitivity evaluation")
    cases: list[dict[str, Any]] = []
    try:
        from evaluation.metrics.grounding import GroundingScorer

        grounding_scorer = GroundingScorer(embedder=container.embedder)
        users = [normalize_query(container, sample)[0] for sample in samples]
        contexts = (
            [] if baseline_records
            else [_retrieve(container, user, config) for user in users]
        )
        if baseline_records:
            from acne_llm.schemas import RetrievalOutput

            canary_contexts = [
                RetrievalOutput(query=CANARY_QUERY, chunks=[])
                for _ in users
            ]
        else:
            canary_contexts = contexts
        for index, (sample, user, correct_context) in enumerate(
            zip(samples, users, canary_contexts)
        ):
            if baseline_records:
                baseline_record = baseline_records[sample["sample_id"]]
                rendered_prompt = str(
                    (baseline_record.get("trace") or {}).get("rendered_user_prompt") or ""
                )
                correct_answer = str(baseline_record.get("answer") or "")
                correct_trace = baseline_record.get("trace") or {}
                baseline_grounding = baseline_record.get("grounding") or {}
                context_texts = contexts_from_record(baseline_record)
                swapped_context = None
                swapped_answer = None
                swapped_trace = None
            else:
                baseline_record = {}
                rendered_prompt = ""
                context_texts = [chunk.text for chunk in correct_context.chunks]
                swapped_context = contexts[(index + 1) % len(contexts)]
                if len(contexts) == 1:
                    swapped_context = correct_context.model_copy(update={"chunks": []})

            canary_user = user.model_copy(update={"description": CANARY_QUERY})
            canary_context = add_in_memory_canary(correct_context)
            canary_answer, canary_trace = _generate(
                container, canary_user, canary_context
            )
            strict_canary_answer, strict_canary_trace = _generate(
                container, canary_user, canary_context, strict=True
            )
            if baseline_records:
                if rendered_prompt:
                    strict_answer, strict_trace = _generate_from_rendered_prompt(
                        container, user, rendered_prompt, strict=True
                    )
                    strict_grounding = grounding_scorer.score(
                        strict_answer, context_texts
                    )
                else:
                    strict_answer = correct_answer
                    strict_trace = {
                        "not_applicable": "deterministic response has no model prompt"
                    }
                    strict_grounding = baseline_grounding
                cosine = None
                ngram = None
            else:
                correct_answer, correct_trace = _generate(container, user, correct_context)
                swapped_answer, swapped_trace = _generate(container, user, swapped_context)
                strict_answer, strict_trace = _generate(
                    container, user, correct_context, strict=True
                )
                baseline_grounding = grounding_scorer.score(correct_answer, context_texts)
                strict_grounding = grounding_scorer.score(strict_answer, context_texts)
                cosine = _embedding_cosine(
                    container.embedder, correct_answer, swapped_answer
                )
                ngram = char_ngram_similarity(correct_answer, swapped_answer)
            cases.append({
                "sample_id": sample["sample_id"],
                "query": sample["user_query"],
                "correct_chunk_ids": (
                    list(baseline_record.get("used_chunks") or [])
                    if baseline_records
                    else [chunk.chunk_id for chunk in correct_context.chunks]
                ),
                "swapped_from_sample_id": (
                    None if baseline_records
                    else samples[(index + 1) % len(samples)]["sample_id"]
                ),
                "swapped_chunk_ids": (
                    [] if swapped_context is None
                    else [chunk.chunk_id for chunk in swapped_context.chunks]
                ),
                "canary_token": CANARY_TOKEN,
                "canary_query": CANARY_QUERY,
                "canary_adopted": CANARY_TOKEN.casefold() in canary_answer.casefold(),
                "canary_answer": canary_answer,
                "strict_canary_adopted": (
                    CANARY_TOKEN.casefold() in strict_canary_answer.casefold()
                ),
                "strict_canary_answer": strict_canary_answer,
                "correct_answer": correct_answer,
                "strict_answer": strict_answer,
                "swapped_answer": swapped_answer,
                "baseline_grounding": baseline_grounding,
                "strict_grounding": strict_grounding,
                "embedding_cosine": round(cosine, 4) if cosine is not None else None,
                "char_ngram_similarity": round(ngram, 4) if ngram is not None else None,
                "embedding_distance": round(1.0 - cosine, 4) if cosine is not None else None,
                "char_ngram_distance": round(1.0 - ngram, 4) if ngram is not None else None,
                "traces": {
                    "canary": canary_trace,
                    "strict_canary": strict_canary_trace,
                    "correct": correct_trace,
                    "strict": strict_trace,
                    "swapped": swapped_trace,
                },
            })
            (out_dir / "checkpoint.json").write_text(
                json.dumps({
                    "status": "partial",
                    "completed_cases": len(cases),
                    "system": config["id"],
                    "cases": cases,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    finally:
        try:
            container.llm.close()
        except Exception:
            pass

    report = {
        **summarize_results(cases, args.low_sensitivity_threshold),
        "dataset": args.dataset,
        "split": "D1",
        "model": config.get("model"),
        "in_memory_canary_only": True,
        "canary_design": "fact queried directly; no instruction embedded in retrieved text",
        "strict_grounding_instruction": STRICT_GROUNDING_INSTRUCTION,
        "baseline_run": args.baseline_run,
        "baseline_reused": bool(baseline_records),
        "persistent_kb_write_calls": 0,
        "metric_definition": (
            "mean(1-embedding_cosine, 1-char_3gram_dice) per context swap"
        ),
        "provisional_gate": {
            "canary_adoption_rate": 0.50,
            "context_swap_sensitivity_mean": 0.15,
        },
        "cases": cases,
        "run_meta": build_run_meta({"system_config": args.system}),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(out_dir / "report.json")


if __name__ == "__main__":
    main()
