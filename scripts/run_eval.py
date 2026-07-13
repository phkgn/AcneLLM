"""Reusable helpers for the repository evaluation CLI."""
from __future__ import annotations

from typing import Any

from acne_llm.schemas import UserContext, UserInput


def _resolve_relevant_ids(case: dict, retriever, label_top_k: int = 5):
    manual = [str(item) for item in case.get("relevant_chunk_ids", []) if str(item).strip()]
    if manual:
        return manual, "manual"
    result = retriever.retrieve(str(case.get("query", "")), top_k=label_top_k, mode="sparse")
    return [chunk.chunk_id for chunk in result.chunks], f"auto:sparse_top{label_top_k}"


def _build_user_context(data: dict) -> UserContext:
    allowed = {
        "age": data.get("age"),
        "sex": data.get("sex", data.get("gender")),
        "skin_type": data.get("skin_type"),
        "is_pregnant": bool(data.get("is_pregnant", False)),
        "is_breastfeeding": bool(data.get("is_breastfeeding", False)),
        "allergies": list(data.get("allergies") or []),
        "current_products": list(data.get("current_products") or []),
        "medications": list(data.get("medications") or []),
        "duration_weeks": data.get("duration_weeks"),
    }
    return UserContext(**allowed)


def _normalize_generation_mode(mode: str) -> str:
    normalized = (mode or "hybrid").lower()
    if normalized == "baseline":
        return "llm_only"
    if normalized == "rag":
        return "hybrid"
    return normalized


def _try_generate(
    container: Any,
    user: UserInput,
    mode: str = "hybrid",
    max_retries: int = 1,
):
    normalized = _normalize_generation_mode(mode)
    pipeline = container.hybrid if normalized == "hybrid" else container.llm_only
    prepared = user.model_copy(update={"mode": normalized})
    for _ in range(max(1, max_retries)):
        try:
            output = pipeline.run(prepared)
            result = output.model_dump()
            result["mode"] = normalized
            return result
        except Exception:
            # An explicitly requested mode must never silently fall back to a
            # different pipeline because that invalidates comparative evals.
            continue
    return None
