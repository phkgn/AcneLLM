"""Error attribution rules (§10 blueprint) — gán mã lỗi trace-computable.

Các mã cần judge (E11-E20) lấy từ judges/run_judge.py error_classify; file này chỉ
gán các mã suy ra được thuần từ trace + gold, để Pareto lỗi per module.
"""
from __future__ import annotations


def attribute(record: dict, sample: dict, judged: dict | None = None) -> list[str]:
    codes: list[str] = []
    trace = record.get("trace") or {}

    if not record.get("ok"):
        codes.append("E22_infra")
        return codes
    if record.get("model_name") and record.get("structured") \
            and record["structured"].get("model_name") \
            and record["model_name"] != record["structured"]["model_name"]:
        codes.append("E22_fallback")

    # E01 router (chỉ có ở T4/SSE trace)
    gold_intent = sample.get("intent_label")
    if gold_intent and trace.get("primary_intent") \
            and trace["primary_intent"] != gold_intent:
        codes.append("E01_router")

    # E04/E05/E06 retrieval — cần qrels
    grades = sample.get("relevance_grade") or {}
    relevant = {cid for cid, g in grades.items() if g > 0}
    if relevant:
        retrieved = trace.get("retrieved_ids") or []
        final = trace.get("final_ids") or record.get("used_chunks") or []
        if retrieved and not (set(retrieved) & relevant):
            codes.append("E04_retrieval_miss")
        elif final and not (set(final) & relevant):
            if set(retrieved) & relevant:
                codes.append("E06_rerank_or_filter_drop")
            else:
                codes.append("E04_retrieval_miss")
        if final:
            noise = sum(1 for cid in final if grades.get(cid, 0) == 0)
            if noise / len(final) > 0.5:
                codes.append("E05_retrieval_noise")

    # E13 citation mismatch (deterministic — đồng bộ metrics.deterministic)
    from evaluation.metrics.deterministic import citation_valid, parse_success
    if citation_valid(record) is False:
        codes.append("E13_citation_mismatch")
    if parse_success(record) is False:
        codes.append("E21_parse_failure")

    # E15 forbidden claims
    from evaluation.metrics.deterministic import forbidden_claims
    if forbidden_claims(record, sample.get("forbidden_claims")):
        codes.append("E15_unsafe_recommendation")

    # Judge-based codes (nếu đã chạy error_classify)
    if judged:
        codes.extend(judged.get("codes") or [])
    return sorted(set(codes))
