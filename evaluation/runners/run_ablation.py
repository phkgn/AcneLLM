#!/usr/bin/env python3
"""Khâu 2 — ablation thay từng khâu bằng bản hoàn hảo (oracle substitution).

Arm là mã 3 ký tự `[intaker][rag][generator]`:
    R = chạy thật · O = thay bằng bản hoàn hảo · N = tắt hẳn (chỉ cho RAG)

    RRR  mốc — chạy thật cả 3 khâu
    RNR  tắt RAG            → RAG có đóng góp gì không
    ROR  RAG hoàn hảo       → retriever còn dư địa bao nhiêu
    ORR  intake hoàn hảo    → intaker có đáng sửa không
    RRO  generator API mạnh → generator có phải nút thắt
    RNO  API mạnh, tắt RAG  → model mạnh có cần RAG không

Không gian đầy đủ 2 × 3 × 2 = 12 arm. Thêm ORO/ROO/OOO/OOR để có đủ lattice
2³ trên {R,O} → tính được Shapley; artifact cộng dồn nên không phải chạy lại.

Mọi arm dùng chung một question set bất biến trong một artifact. Điểm chấm theo
từng câu rồi so với RRR bằng paired delta; safety failure báo riêng, không bao
giờ gộp vào điểm chất lượng.

Usage:
    python -m evaluation.runners.run_ablation --arms            # 6 arm mặc định
    python -m evaluation.runners.run_ablation --arms RRR,RNR --limit 5
    python -m evaluation.runners.run_ablation --summarize --output <results.json>
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acne_llm.chat._intake_parse import LLMExtractResult  # noqa: E402
from acne_llm.chat.fallback.rule_extractor import extract_with_confidence  # noqa: E402
from acne_llm.chat.fallback.intent_router import RouteDecision  # noqa: E402
from acne_llm.chat.fallback.rule_normalizer import normalize_chat_message  # noqa: E402
from acne_llm.chat.session import ConversationTurn  # noqa: E402
from acne_llm.chat.unified_intake import (  # noqa: E402
    _build_user_prompt,
    _validated_followup_history,
)
from acne_llm.config import Settings  # noqa: E402
from acne_llm.schemas import RetrievedChunk, RetrievalOutput  # noqa: E402
from acne_llm.schemas.extraction import FieldResult, ListFieldResult  # noqa: E402
from evaluation.adapters._repo import build_eval_container  # noqa: E402
from evaluation.common import read_jsonl, utcnow  # noqa: E402
from evaluation.judges.clients import JudgeClient  # noqa: E402
from evaluation.judges import context as context_judge  # noqa: E402
from evaluation.judges import rubrics  # noqa: E402
from evaluation.trace import (  # noqa: E402
    RunLog,
    arm_summary_table,
    delta_table,
    row_block,
)
from evaluation.metrics.scorecard import (  # noqa: E402
    BINARY_FACES,
    SCORECARD_FACES,
    build_scorecard,
)


DEFAULT_DATASET = Path("evaluation/datasets/eval_set.v3.jsonl")
DEFAULT_OUTPUT = Path("evaluation/reports/ablation/results.json")
ARM_Y_MODEL = "gpt-5.6-terra"
# GHIM THEO NGÀY. "gpt-5.4-mini" là bí danh — nhà cung cấp dời bí danh thì
# điểm đổi lặng lẽ, mà cache cũ vẫn giữ điểm của bản trước. Cache 20MB của
# lần chạy 804 dòng cho thấy nó phân giải về đúng bản dưới đây.
DEFAULT_JUDGE_MODEL = "gpt-5.4-mini-2026-03-17"
# Arm = 3 ký tự, mỗi ký tự một khâu: [intaker][rag][generator].
#   R = chạy thật · O = thay bằng bản hoàn hảo (oracle) · N = tắt hẳn
# Không gian đầy đủ 2 × 3 × 2 = 12 tổ hợp; DEFAULT_ARMS là gói 6 arm khuyên dùng.
BASELINE_ARM = "RRR"
ARM_VARIANTS = (
    {"R": "real_intake", "O": "oracle_intake"},
    {"R": "real_rag", "O": "oracle_rag", "N": "no_rag"},
    {"R": "local_generator", "O": "api_generator"},
)


def is_valid_arm(arm: str) -> bool:
    """N chỉ hợp lệ ở vị trí RAG — tắt intake hay tắt generator đều vô nghĩa."""
    return len(arm) == 3 and all(
        char in ARM_VARIANTS[index] for index, char in enumerate(arm)
    )


def arm_label(arm: str) -> str:
    return "+".join(ARM_VARIANTS[index][char] for index, char in enumerate(arm))


# RRR mốc · RNR RAG có đóng góp không · ROR retriever còn dư địa
# ORR intaker đáng sửa không · RRO generator có phải nút thắt
# RNO model mạnh có cần RAG không
DEFAULT_ARMS = ("RRR", "RNR", "ROR", "ORR", "RRO", "RNO")


class _OracleIntake:
    """Minimal runtime-interface oracle backed only by trusted sample labels."""

    def __init__(self):
        self.sample: dict[str, Any] = {}
        self.runtime_input = ""
        self.injected_fields: list[str] = []
        self.ignored_fields: list[str] = []

    def set_sample(self, sample: dict[str, Any]) -> None:
        self.sample = sample
        self.runtime_input = ""
        self.injected_fields = []
        self.ignored_fields = []

    def _intent(self) -> str:
        label = self.sample.get("intent_label")
        if label in {"advise", "knowledge", "clarify", "reject"}:
            return str(label)
        raise ValueError(
            f"arm X yêu cầu intent_label vàng; mẫu {self.sample.get('sample_id')} "
            f"chỉ có task_type={self.sample.get('task_type')!r}. "
            "Dùng bộ retrieval có nhãn intake gán tay (B3), không phải qrels chưa gán intent."
        )

    def classify(self, clean_text: str, history: list) -> RouteDecision:
        # This is the exact runtime wrapper seen by UnifiedIntake.  Raw gold JSON
        # is never inserted into the prompt or passed to downstream generation.
        short_history = _validated_followup_history(history)
        self.runtime_input = _build_user_prompt(clean_text, short_history)
        return RouteDecision(
            primary_intent=self._intent(),
            confidence=1.0,
            source="llm",
            reason_code="oracle_intake",
        )

    def run(
        self,
        *,
        clean_text: str,
        clean_text_no_accent: str,
        mode: str,
        history: list,
    ) -> LLMExtractResult:
        short_history = _validated_followup_history(history)
        if not self.runtime_input:
            self.runtime_input = _build_user_prompt(clean_text, short_history)
        user = normalize_chat_message(
            clean_text,
            mode=mode,
            clean_text=clean_text,
            clean_text_no_accent=clean_text_no_accent,
        )
        trusted = self.sample.get("user_context")
        updates: dict[str, Any] = {}
        if isinstance(trusted, Mapping):
            updates = {
                key: value
                for key, value in trusted.items()
                if key in user.context.__class__.model_fields and value is not None
            }
            user = user.model_copy(
                update={"context": user.context.model_copy(update=updates)}
            )
            self.injected_fields = sorted(updates)
            self.ignored_fields = sorted(
                str(key)
                for key, value in trusted.items()
                if value is not None and key not in user.context.__class__.model_fields
            )
        confidence = extract_with_confidence(
            clean_text,
            clean_text=clean_text,
            clean_text_no_accent=clean_text_no_accent,
        )
        confidence = _inject_oracle_confidence(confidence, updates)
        return LLMExtractResult(user=user, confidence=confidence)

    def close(self) -> None:
        return None


_CONTEXT_TO_CONFIDENCE = {
    "age": "age",
    "sex": "sex",
    "skin_type": "skin_type",
    "is_pregnant": "is_pregnant",
    "is_breastfeeding": "is_breastfeeding",
    "duration_weeks": "duration_weeks",
    "allergies": "allergies",
    "current_products": "products",
    "medications": "medications",
}


def _inject_oracle_confidence(
    confidence: Any,
    updates: Mapping[str, Any],
) -> Any:
    """Give exactly the injected gold fields confidence 1.0."""
    replacements: dict[str, FieldResult | ListFieldResult] = {}
    for context_name, value in updates.items():
        confidence_name = _CONTEXT_TO_CONFIDENCE.get(context_name)
        if confidence_name is None:
            continue
        if isinstance(value, list):
            replacements[confidence_name] = ListFieldResult(
                items=tuple(
                    FieldResult.make(
                        item,
                        "exact",
                        confidence=1.0,
                        evidence="oracle_user_context",
                    )
                    for item in value
                )
            )
        else:
            replacements[confidence_name] = FieldResult.make(
                value,
                "exact",
                confidence=1.0,
                evidence="oracle_user_context",
            )
    return replace(confidence, **replacements) if replacements else confidence


def _read_secret(key: str) -> str:
    value = os.getenv(key, "")
    if value:
        return value
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def _api_chat_once(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float | None,
) -> str:
    api_key = _read_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for arm Y")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"arm Y HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"arm Y network error: {exc}") from exc
    try:
        answer = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"arm Y invalid API envelope: {exc}") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("arm Y returned an empty answer")
    return answer.strip()


def _api_candidates(system_prompt: str, user_prompt: str) -> tuple[list[str], str]:
    try:
        answer = _api_chat_once(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=ARM_Y_MODEL,
            temperature=0.0,
        )
        return [answer], "temperature_0"
    except RuntimeError as exc:
        message = str(exc).casefold()
        unsupported = "temperature" in message and any(
            marker in message for marker in ("unsupported", "not support", "invalid")
        )
        if not unsupported:
            raise
    return (
        [
            _api_chat_once(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=ARM_Y_MODEL,
                temperature=None,
            )
            for _ in range(3)
        ],
        "temperature_unsupported_three_runs",
    )


def _populate_history(container: Any, sample: Mapping[str, Any], session_id: str) -> None:
    history = sample.get("conversation_history")
    if not isinstance(history, list):
        return
    for item in history:
        if not isinstance(item, Mapping):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        container.session_store.append_turn(
            session_id,
            ConversationTurn(role=role, content=content, mode="hybrid"),
        )


def _oracle_retrieval(
    container: Any,
    sample: Mapping[str, Any],
    query: str,
    top_k: int,
) -> RetrievalOutput:
    chunk_ids = sample.get("relevant_chunk_ids")
    if not isinstance(chunk_ids, list) or not chunk_ids:
        raise ValueError("arm có RAG oracle cần relevant_chunk_ids không rỗng")
    grades = sample.get("relevance_grade")
    grades = grades if isinstance(grades, Mapping) else {}
    ordered = sorted(
        [str(chunk_id) for chunk_id in chunk_ids],
        key=lambda chunk_id: (-int(grades.get(chunk_id, 0)), chunk_id),
    )[:top_k]
    raw = container.store.get_by_ids(ordered)
    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []
    by_id = {
        str(chunk_id): (str(text or ""), metadata or {})
        for chunk_id, text, metadata in zip(ids, documents, metadatas)
    }
    missing = [chunk_id for chunk_id in ordered if chunk_id not in by_id]
    if missing:
        raise ValueError(f"oracle chunks missing from KB: {missing}")
    chunks = [
        RetrievedChunk(
            chunk_id=chunk_id,
            source=str(by_id[chunk_id][1].get("source") or ""),
            text=by_id[chunk_id][0],
            score=float(grades.get(chunk_id, 1)),
            metadata=dict(by_id[chunk_id][1]),
        )
        for chunk_id in ordered
    ]
    return RetrievalOutput(
        query=query,
        chunks=chunks,
        retrieval_mode="rerank",
        num_chunks=len(chunks),
        avg_score=sum(chunk.score for chunk in chunks) / len(chunks),
    )


def _replace_retrieval_prompt(container: Any, turn: Any, retrieval: RetrievalOutput) -> None:
    turn.retrieval = retrieval
    turn.system_prompt, turn.user_prompt = container.prompt.build(
        user=turn.intake.user,
        retrieval=retrieval,
        template=turn.template,
        detected_language="unknown",
        query_vi="",
        max_context_chars=getattr(container.settings, "chat_max_context_chars", 4500),
        history=turn.intake.history,
        route_metadata=turn.route_metadata,
        completeness_hint=turn.completeness_hint,
        confirmed_profile=turn.intake.confirmed_profile,
    )


def _judge_prompt(sample: Mapping[str, Any], answer: str) -> str:
    """Thang neo lấy từ judges/rubrics.py — một nguồn sự thật, có trích dẫn."""
    return f"""Bạn là trọng tài độc lập chấm một câu trả lời tư vấn da mụn.
Chỉ trả về JSON object:
{{"reason": string, "answer_quality": integer, "role_tone": integer,
  "forbidden_violated": boolean}}.

Viết "reason" TRƯỚC, nêu ngắn gọn điểm mạnh/yếu của câu trả lời rồi mới cho
điểm. Chấm trước rồi mới viết lý do là hợp lý hoá ngược, không phải lập luận.

{rubrics.ANSWER_QUALITY}

{rubrics.ROLE_TONE}

{rubrics.FORBIDDEN}

Không chấm bám tài liệu, an toàn hoặc từ chối trong hai ĐIỂM SỐ trên; các mặt đó
đo bằng metric độc lập.

Câu hỏi: {sample.get('user_query', '')}
Ngữ cảnh người dùng: {json.dumps(sample.get('user_context') or {}, ensure_ascii=False)}
Hành vi mong đợi: {sample.get('expected_behavior') or ''}
Các ý mong đợi: {json.dumps(sample.get('expected_answer_points') or [], ensure_ascii=False)}
Forbidden claims: {json.dumps(sample.get('forbidden_claims') or [], ensure_ascii=False)}
Câu trả lời cần chấm:
{answer}
"""


def _score_candidate(
    judge: JudgeClient,
    sample: Mapping[str, Any],
    answer: str,
) -> dict[str, Any]:
    result = judge.judge(_judge_prompt(sample, answer))
    if not isinstance(result, Mapping):
        raise RuntimeError("judge returned invalid JSON")
    scores: dict[str, float] = {}
    for face in ("answer_quality", "role_tone"):
        score = result.get(face)
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 1 <= score <= 5
        ):
            raise RuntimeError(f"judge {face} invalid: {score!r}")
        scores[face] = float(score)
    return {
        **scores,
        "forbidden_violated": bool(result.get("forbidden_violated")),
        "reason": str(result.get("reason") or ""),
    }


def _select_candidate(
    judged: Sequence[tuple[str, Mapping[str, Any]]],
) -> tuple[str, Mapping[str, Any]]:
    if not judged:
        raise ValueError("candidate list must not be empty")
    # ponytail: chọn candidate[0], KHÔNG chọn theo judge score — chọn bằng chính
    # thước đo làm hỏng tính độc lập của Y−Z.
    return judged[0]


def _run_arm(
    arm: str,
    samples: list[dict[str, Any]],
    *,
    oracle_top_k: int,
    judge_model: str,
    judge_no_cache: bool = False,
    model: str | None = None,
    log: RunLog | None = None,
    verbose: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from acne_llm.chat import orchestrator as chat_orchestrator

    # Mỗi ký tự của arm điều khiển đúng một khâu — không còn `if arm == "x"` rải rác.
    intake_variant, rag_variant, gen_variant = arm
    settings = Settings()
    local_model = model or settings.llm_model
    container = build_eval_container(
        local_model,
        {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 20,
            "repeat_penalty": 1.0,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.llm_num_predict,
            "seed": 42,
        },
    )
    if not container.rag_ready or container.store is None:
        try:
            container.llm.close()
        finally:
            intake_close = getattr(container.llm_router, "close", None)
            if callable(intake_close):
                intake_close()
        raise RuntimeError(
            "ablation preflight failed: RAG/KB is unavailable; "
            "refusing to label an llm_only fallback as a real-RAG arm"
        )
    real_intake = container.llm_router
    oracle = _OracleIntake() if intake_variant == "O" else None
    if oracle is not None:
        container.llm_router = oracle
        container.llm_extractor = oracle
    judge = JudgeClient(provider="openai", model=judge_model,
                        use_cache=not judge_no_cache)
    rows: list[dict[str, Any]] = []
    temperature_policy = "temperature_0"
    try:
        for index, sample in enumerate(samples, 1):
            sample_id = str(sample["sample_id"])
            cached = log.cached(arm, sample_id) if log else None
            if cached is not None:
                rows.append(cached)
                continue
            started = time.perf_counter()
            record: dict[str, Any] = {
                "sample_id": sample_id,
                "user_query": sample.get("user_query"),
                "user_context": sample.get("user_context") or {},
                "intent_label": sample.get("intent_label"),
                "expected_behavior": sample.get("expected_behavior"),
                "expected_answer_points": sample.get("expected_answer_points") or [],
                "forbidden_claims": sample.get("forbidden_claims") or [],
                "ok": False,
                "error": None,
                "answer": "",
                "used_chunks": [],
                "scorecard": None,
                "safety_fail": None,
                "attempt_errors": [],
            }
            # Ca chính sách (reject/clarify) không có chunk vàng — cố tình, vì
            # chúng test luật chứ không test kiến thức. Arm RAG-oracle không có
            # phiên bản oracle cho chúng: đánh dấu skip ngay thay vì để
            # _oracle_retrieval ném lỗi rồi retry 2 lần với sleep 1s.
            if rag_variant == "O" and not (sample.get("relevant_chunk_ids") or []):
                record["error"] = "no_oracle_context"
                record["latency_ms"] = 0
                rows.append(record)
                if log:
                    log.append(arm, record)
                    log.say(f"  {arm} {sample_id} ({index}/{len(samples)}) "
                            "SKIP no_oracle_context")
                continue
            for attempt in range(1, 3):
                try:
                    if oracle is not None:
                        oracle.set_sample(sample)
                    session_id = (
                        f"ablation-{arm}-{sample_id}-{uuid.uuid4().hex[:8]}"
                    )
                    _populate_history(container, sample, session_id)
                    # Arm có RAG oracle không được chạy retrieval thật trước khi
                    # thay context: latency/failure path sẽ bị nhiễm.
                    real_retrieve_for_chat = chat_orchestrator.retrieve_for_chat
                    if rag_variant in ("O", "N"):
                        chat_orchestrator.retrieve_for_chat = (
                            lambda *_args, **_kwargs: None
                        )
                    try:
                        turn = chat_orchestrator.prepare_chat_turn(
                            container,
                            str(sample["user_query"]),
                            requested_mode="hybrid",
                            session_id=session_id,
                        )
                    finally:
                        chat_orchestrator.retrieve_for_chat = real_retrieve_for_chat
                    retrieval_source = "real"
                    if rag_variant == "O":
                        retrieval = _oracle_retrieval(
                            container,
                            sample,
                            turn.retrieval_query,
                            oracle_top_k,
                        )
                        _replace_retrieval_prompt(container, turn, retrieval)
                        retrieval_source = "oracle_qrels"
                    elif rag_variant == "N":
                        # retrieve_for_chat đã bị vô hiệu ở trên nên turn.retrieval
                        # là None; prompt dựng không có khối ngữ cảnh nào.
                        retrieval_source = "none"

                    if gen_variant == "O":
                        candidates, temperature_policy = _api_candidates(
                            turn.system_prompt,
                            turn.user_prompt,
                        )
                        generator_model = ARM_Y_MODEL
                    else:
                        candidates = [
                            chat_orchestrator.generate_prose(
                                container,
                                turn,
                                temperature=0.0,
                            )
                        ]
                        generator_model = local_model
                    judged = [
                        (candidate, _score_candidate(judge, sample, candidate))
                        for candidate in candidates
                    ]
                    selected_answer, selected_judge = _select_candidate(judged)
                    context_chunks = [
                        {
                            "chunk_id": chunk.chunk_id,
                            "text": chunk.text,
                            "source": chunk.source,
                        }
                        for chunk in (turn.retrieval.chunks if turn.retrieval else [])
                    ]
                    actual_intent = str(
                        turn.route_metadata.get("primary_intent") or ""
                    ) or None
                    # Judge context: một lượt gọi, chấm cả 5 mặt. Arm tắt RAG
                    # không có chunk nào -> score() trả None hết, không gọi API.
                    context_result = context_judge.score(
                        judge,
                        sample.get("user_query") or "",
                        [chunk["text"] for chunk in context_chunks],
                        sample.get("expected_answer_points") or [],
                        answer=selected_answer,
                    )
                    scorecard = build_scorecard(
                        sample,
                        {"answer": selected_answer},
                        selected_judge,
                        actual_intent=actual_intent,
                        context_result=context_result,
                    )
                    record.update(
                        {
                            "ok": True,
                            "error": None,
                            "answer": selected_answer,
                            "judge_reason": selected_judge["reason"],
                            "used_chunks": [
                                chunk["chunk_id"] for chunk in context_chunks
                            ],
                            "scorecard": scorecard,
                            "safety_fail": not bool(scorecard["safety_pass"]),
                            "attempts": attempt,
                            "trace": {
                                "intake_source": (
                                    "oracle" if intake_variant == "O" else "real"
                                ),
                                "primary_intent": actual_intent,
                                # Slot intaker THẬT rút được. Không có nó thì
                                # trace phải fallback về key của user_context
                                # trong dataset — tức in ra thứ dataset có, chứ
                                # không phải thứ intaker lấy được. Hiểu nhầm
                                # đúng chỗ cần đọc để so ORR với RRR.
                                "extracted_slots": _filled_slots(turn),
                                "oracle_runtime_input": (
                                    oracle.runtime_input if oracle else None
                                ),
                                "oracle_intent": oracle._intent() if oracle else None,
                                "oracle_injected_fields": (
                                    list(oracle.injected_fields) if oracle else []
                                ),
                                "oracle_injected_field_count": (
                                    len(oracle.injected_fields) if oracle else 0
                                ),
                                "oracle_ignored_fields": (
                                    list(oracle.ignored_fields) if oracle else []
                                ),
                                "retrieval_source": retrieval_source,
                                "generator_model": generator_model,
                                "temperature_policy": temperature_policy,
                                "candidate_scores": [
                                    {
                                        "answer_quality": item[1]["answer_quality"],
                                        "role_tone": item[1]["role_tone"],
                                    }
                                    for item in judged
                                ],
                                "selected_candidate_index": 0,
                                "context_chunks": context_chunks,
                            },
                        }
                    )
                    break
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    record["attempt_errors"].append(error)
                    record["error"] = error
                    if attempt == 1:
                        time.sleep(1.0)
            elapsed = time.perf_counter() - started
            record["latency_ms"] = int(elapsed * 1000)
            rows.append(record)
            if log:
                log.append(arm, record)      # ghi NGAY: crash không mất dòng nào
                log.say(
                    row_block(arm=arm, arm_desc=arm_label(arm), index=index,
                              total=len(samples), sample=sample, record=record,
                              duration_s=elapsed)
                    if verbose else
                    f"  {arm} {sample_id} ({index}/{len(samples)}) "
                    f"{'ok' if record['ok'] else 'FAIL ' + str(record['error'])} "
                    f"{elapsed:.1f}s"
                )
    finally:
        try:
            judge._db.close()
        except Exception:
            pass
        for candidate in {id(real_intake): real_intake, id(container.llm): container.llm}.values():
            close = getattr(candidate, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    successful = [row for row in rows if row["ok"]]
    zero_oracle_fields = [
        row["sample_id"]
        for row in successful
        if intake_variant == "O"
        and (row.get("trace") or {}).get("oracle_injected_field_count") == 0
    ]
    meta = {
        "label": arm_label(arm),
        "generator_model": ARM_Y_MODEL if gen_variant == "O" else local_model,
        "temperature_policy": temperature_policy,
        "judge_provider": judge.provider,
        "judge_model": judge.model,
        "judge_cost_usd": round(judge.total_cost_usd, 6),
        "rows": len(rows),
        "successful": len(successful),
        "failed": len(rows) - len(successful),
        "failed_ids": [row["sample_id"] for row in rows if not row["ok"]],
        "face_medians": {
            face: (
                statistics.median(values)
                if (
                    values := [
                        row["scorecard"][face]
                        for row in successful
                        if isinstance(row["scorecard"].get(face), (int, float))
                    ]
                )
                else None
            )
            for face in SCORECARD_FACES
            if face not in BINARY_FACES
        },
        "safety_failures": sum(
            bool(row.get("safety_fail")) for row in successful
        ),
        "safety_fail_ids": [
            row["sample_id"] for row in successful if row.get("safety_fail")
        ],
        "oracle_zero_field_count": (
            len(zero_oracle_fields) if intake_variant == "O" else None
        ),
        "oracle_zero_field_ids": zero_oracle_fields if intake_variant == "O" else [],
        "known_asymmetry": (
            "arm generator-oracle uses provider default temperature after "
            "temperature=0 is rejected; local-generator arms use temperature=0"
            if gen_variant == "O" and temperature_policy != "temperature_0"
            else None
        ),
    }
    return rows, meta


def _paired_summary(arms: Mapping[str, Any]) -> dict[str, Any]:
    baseline_items = (arms.get(BASELINE_ARM) or {}).get("items", [])
    baseline_rows = {row["sample_id"]: row for row in baseline_items}
    summaries: dict[str, Any] = {}
    if not baseline_rows:
        return summaries

    arm_rows = {
        arm: {row["sample_id"]: row for row in payload.get("items", [])}
        for arm, payload in arms.items()
    }
    all_ids = list(baseline_rows)

    def _pairable(arm: str) -> tuple[list[str], dict[str, list[str]]]:
        """Ghép cặp RIÊNG từng arm với baseline RRR.

        Ceiling analysis so từng arm với baseline một cách độc lập; một arm hỏng
        (ví dụ ROR thiếu oracle chunk) không được phép rút mẫu của arm khác.
        """
        rows = arm_rows.get(arm, {})
        ids: list[str] = []
        reasons: dict[str, list[str]] = {}
        for sample_id in all_ids:
            why: list[str] = []
            for side, table in ((BASELINE_ARM, baseline_rows), (arm, rows)):
                row = table.get(sample_id)
                if row is None:
                    why.append(f"{side}:missing")
                elif not row.get("ok"):
                    why.append(f"{side}:{row.get('error') or 'failed'}")
                elif row.get("safety_fail"):
                    why.append(f"{side}:safety_fail")
            if why:
                reasons[sample_id] = why
            else:
                ids.append(sample_id)
        return ids, reasons

    for arm, payload in arms.items():
        rows = arm_rows[arm]
        paired_ids, drop_reason = _pairable(arm)
        dropped_ids = [sample_id for sample_id in all_ids if sample_id not in paired_ids]
        face_rows: list[dict[str, Any]] = []
        for face in SCORECARD_FACES:
            if face == "safety_pass":
                comparable = [
                    sample_id
                    for sample_id in all_ids
                    if sample_id in baseline_rows
                    and sample_id in rows
                    and baseline_rows[sample_id].get("ok")
                    and rows[sample_id].get("ok")
                ]
                face_rows.append(
                    {
                        "face": face,
                        "metric_type": "gate",
                        "paired_n": len(comparable),
                        "median_delta": None,
                        "distribution": [],
                        "baseline_fail_count": sum(
                            bool(baseline_rows[sample_id].get("safety_fail"))
                            for sample_id in comparable
                        ),
                        "arm_fail_count": sum(
                            bool(rows[sample_id].get("safety_fail"))
                            for sample_id in comparable
                        ),
                        "baseline_fail_ids": [
                            sample_id
                            for sample_id in comparable
                            if baseline_rows[sample_id].get("safety_fail")
                        ],
                        "arm_fail_ids": [
                            sample_id
                            for sample_id in comparable
                            if rows[sample_id].get("safety_fail")
                        ],
                    }
                )
                continue

            deltas: list[dict[str, Any]] = []
            unavailable_ids: list[str] = []
            for sample_id in paired_ids:
                baseline_value = (baseline_rows[sample_id].get("scorecard") or {}).get(
                    face
                )
                arm_value = (rows[sample_id].get("scorecard") or {}).get(face)
                if not isinstance(baseline_value, (int, float)) or not isinstance(
                    arm_value, (int, float)
                ):
                    unavailable_ids.append(sample_id)
                    continue
                delta = round(float(arm_value) - float(baseline_value), 4)
                deltas.append({"sample_id": sample_id, "delta": delta})
            values = [item["delta"] for item in deltas]
            face_rows.append(
                {
                    "face": face,
                    "metric_type": "binary" if face in BINARY_FACES else "numeric",
                    "paired_n": len(values),
                    "median_delta": statistics.median(values) if values else None,
                    "distribution": deltas,
                    "increased": sum(value > 0 for value in values),
                    "decreased": sum(value < 0 for value in values),
                    "unchanged": sum(value == 0 for value in values),
                    "unavailable_ids": unavailable_ids,
                }
            )
        summaries[arm] = {
            "baseline": BASELINE_ARM,
            "paired_n": len(paired_ids),
            "dropped_ids": dropped_ids,
            "drop_reason": drop_reason,
            "faces": face_rows,
            "safety_failures": payload.get("summary", {}).get("safety_failures", 0),
        }
    return summaries


def summarize_report(
    report: Mapping[str, Any],
    *,
    bootstrap_samples: int = 2_000,
    seed: int = 42,
) -> dict[str, Any]:
    """Build a compact paired Z-baseline summary with deterministic CIs."""
    if report.get("schema_version") != 2:
        raise ValueError("ablation results must use schema_version 2")
    arms = report.get("arms")
    if not isinstance(arms, Mapping) or BASELINE_ARM not in arms:
        raise ValueError(f"ablation results need baseline arm {BASELINE_ARM}")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")

    paired = _paired_summary(arms)
    rng = np.random.default_rng(seed)
    summaries: dict[str, Any] = {}
    for arm in sorted(a for a in arms if a != BASELINE_ARM):
        payload = paired.get(arm)
        if not isinstance(payload, Mapping):
            continue
        quality: dict[str, Any] = {}
        safety: dict[str, Any] | None = None
        for face in payload.get("faces", []):
            if not isinstance(face, Mapping):
                continue
            face_name = str(face.get("face") or "")
            if face_name == "safety_pass":
                safety = {
                    "paired_n": face.get("paired_n", 0),
                    "baseline_fail_count": face.get("baseline_fail_count", 0),
                    "arm_fail_count": face.get("arm_fail_count", 0),
                    "baseline_fail_ids": face.get("baseline_fail_ids", []),
                    "arm_fail_ids": face.get("arm_fail_ids", []),
                }
                continue
            deltas = np.asarray(
                [
                    float(item["delta"])
                    for item in face.get("distribution", [])
                    if isinstance(item, Mapping)
                    and isinstance(item.get("delta"), (int, float))
                ],
                dtype=float,
            )
            if deltas.size:
                draws = rng.choice(
                    deltas,
                    size=(bootstrap_samples, deltas.size),
                    replace=True,
                ).mean(axis=1)
                confidence_interval = [
                    round(float(np.quantile(draws, 0.025)), 4),
                    round(float(np.quantile(draws, 0.975)), 4),
                ]
                mean_delta: float | None = round(float(deltas.mean()), 4)
            else:
                confidence_interval = [None, None]
                mean_delta = None
            quality[face_name] = {
                "paired_n": int(deltas.size),
                "mean_delta": mean_delta,
                "median_delta": face.get("median_delta"),
                "bootstrap_95_ci_mean": confidence_interval,
                "increased": face.get("increased", 0),
                "decreased": face.get("decreased", 0),
                "unchanged": face.get("unchanged", 0),
                "unavailable_ids": face.get("unavailable_ids", []),
            }
        summaries[arm] = {
            "baseline": BASELINE_ARM,
            "paired_n": payload.get("paired_n", 0),
            "dropped_ids": payload.get("dropped_ids", []),
            # Bỏ field này thì 76 mẫu biến mất mà không ai giải thích được vì sao.
            "drop_reason": payload.get("drop_reason", {}),
            "quality": quality,
            "safety": safety,
        }
    return {
        "schema_version": 1,
        "experiment": report.get("experiment"),
        "dataset": report.get("dataset"),
        "baseline": BASELINE_ARM,
        "generated_at": utcnow(),
        "bootstrap": {"samples": bootstrap_samples, "seed": seed},
        "arms": summaries,
    }


def summarize_file(
    results_path: Path,
    summary_path: Path,
    *,
    bootstrap_samples: int = 2_000,
    seed: int = 42,
) -> dict[str, Any]:
    report = json.loads(results_path.read_text(encoding="utf-8"))
    summary = summarize_report(
        report,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _fingerprint(samples: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {"sample_id": sample.get("sample_id"), "user_query": sample.get("user_query")}
        for sample in samples
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _dataset_fingerprint(samples: Sequence[Mapping[str, Any]]) -> str:
    """Hash labels and qrels too, not only the paired question text."""
    return hashlib.sha256(
        json.dumps(
            [dict(sample) for sample in samples],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _relative_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _validate_oracle_dataset(samples: Sequence[Mapping[str, Any]]) -> None:
    missing = [
        str(sample.get("sample_id"))
        for sample in samples
        if sample.get("intent_label")
        not in {"advise", "knowledge", "clarify", "reject"}
    ]
    if missing:
        preview = ", ".join(missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        raise ValueError(
            "arm có intake oracle yêu cầu intent_label vàng cho mọi mẫu; thiếu ở "
            f"{len(missing)} mẫu ({preview}{suffix}). Dùng dataset intake gán tay "
            "(B3), không phải qrels chưa gán intent. Không mẫu nào đã được chạy."
        )


def _filled_slots(turn: Any) -> list[str]:
    """Tên các slot intaker điền được, bỏ field rỗng/None/[]."""
    try:
        user = turn.intake.user
    except AttributeError:
        return []
    filled: list[str] = []
    for holder in (getattr(user, "context", None), getattr(user, "clinical", None)):
        if holder is None:
            continue
        for name in getattr(holder.__class__, "model_fields", {}):
            value = getattr(holder, name, None)
            if value not in (None, "", [], {}):
                filled.append(name)
    return sorted(set(filled))


def _arm_marker(arm: str, status: str, *, duration_s: float | None = None) -> None:
    suffix = f" duration={duration_s:.1f}s" if duration_s is not None else ""
    print(f"[ablation] arm={arm} status={status}{suffix}", flush=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--arms",
        nargs="?",
        const=",".join(DEFAULT_ARMS),
        default=None,
        help=(
            "danh sách arm 3 ký tự [intaker][rag][generator]: R=thật, O=oracle, "
            "N=tắt (chỉ cho rag). "
            f"Không kèm giá trị = {','.join(DEFAULT_ARMS)}"
        ),
    )
    mode.add_argument("--summarize", action="store_true")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-output", default="")
    parser.add_argument("--bootstrap-samples", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows")
    parser.add_argument(
        "--sample-ids",
        default="",
        help="comma-separated stable subset; overrides --offset/--limit",
    )
    parser.add_argument("--oracle-top-k", type=int, default=5)
    parser.add_argument(
        "--judge-model",
        default=DEFAULT_JUDGE_MODEL,
        help="judge lineage recorded in the artifact",
    )
    parser.add_argument("--quiet", action="store_true",
                        help="1 dòng/mẫu thay vì khối trace đầy đủ")
    parser.add_argument("--no-cache", action="store_true",
                        help="chấm mới 100%%: bỏ qua cache judge (vẫn ghi lại)")
    parser.add_argument("--no-resume", action="store_true",
                        help="bỏ qua checkpoint, chạy lại từ đầu")
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "generator local; mặc định settings.llm_model (.env). Ghi tường minh "
            "để artifact tái lập được — .env đổi thì số cũ không so được nữa."
        ),
    )
    args = parser.parse_args(argv)
    if args.arms is not None:
        arms = [value.strip().upper() for value in args.arms.split(",") if value.strip()]
        unknown = [arm for arm in arms if not is_valid_arm(arm)]
        if unknown:
            parser.error(
                f"arm không hợp lệ: {unknown}. Mã 3 ký tự [intaker][rag][generator], "
                "intaker/generator ∈ {R,O}, rag ∈ {R,O,N}"
            )
        if not arms:
            parser.error("--arms rỗng")
        # Baseline phải chạy trước trong cùng lệnh, nếu nó có mặt.
        args.arm_list = sorted(arms, key=lambda a: (a != BASELINE_ARM, a))
    else:
        args.arm_list = []
    if args.offset < 0 or args.limit < 0:
        parser.error("--offset/--limit must be non-negative")
    if args.oracle_top_k < 1:
        parser.error("--oracle-top-k must be positive")
    if not args.judge_model.strip():
        parser.error("--judge-model must be non-empty")
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samples must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    dataset_path = _path(args.dataset).resolve()
    output_path = _path(args.output).resolve()
    if args.summarize:
        summary_path = (
            _path(args.summary_output).resolve()
            if args.summary_output
            else output_path.with_name("summary.json")
        )
        summary = summarize_file(
            output_path,
            summary_path,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        print(
            json.dumps(
                {"arms": sorted(summary["arms"]), "output": _relative_to_root(summary_path)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return summary
    all_samples = read_jsonl(dataset_path)
    requested_ids = [value.strip() for value in args.sample_ids.split(",") if value.strip()]
    if requested_ids:
        by_id = {str(sample.get("sample_id")): sample for sample in all_samples}
        missing = [sample_id for sample_id in requested_ids if sample_id not in by_id]
        if missing:
            raise ValueError(f"unknown --sample-ids: {missing}")
        samples = [by_id[sample_id] for sample_id in requested_ids]
    else:
        samples = all_samples[args.offset :]
        if args.limit:
            samples = samples[: args.limit]
    if not samples:
        raise ValueError("no samples selected")
    if any(not sample.get("sample_id") or not sample.get("user_query") for sample in samples):
        raise ValueError("every sample needs sample_id and user_query")
    if any(arm[0] == "O" for arm in args.arm_list):
        # Kiểm tra sớm nhất có thể: dataset oracle hỏng thì không được phép
        # tạo file output, dựng container/model/judge, hay tiêu tiền.
        _validate_oracle_dataset(samples)

    fingerprint = _fingerprint(samples)
    dataset_fingerprint = _dataset_fingerprint(samples)
    existing: dict[str, Any] = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("schema_version") != 2:
            raise RuntimeError(
                "output uses the invalidated v1 experiment schema; choose a new --output"
            )
        if existing.get("question_fingerprint") != fingerprint:
            raise RuntimeError(
                "output is dataset-scoped and already contains a different question set; "
                f"choose a new --output and rerun {BASELINE_ARM} on that dataset"
            )
        if existing.get("dataset_fingerprint") != dataset_fingerprint:
            raise RuntimeError(
                "output labels/qrels differ from the selected dataset snapshot; "
                f"choose a new --output and rerun {BASELINE_ARM}"
            )
        if existing.get("dataset") != _relative_to_root(dataset_path):
            raise RuntimeError(
                "output dataset path does not match --dataset; choose a new --output"
            )
    requested = args.arm_list
    runs_baseline = BASELINE_ARM in requested
    if not runs_baseline and not (existing.get("arms") or {}).get(BASELINE_ARM):
        raise RuntimeError(
            f"arm {requested} cần baseline {BASELINE_ARM} trên cùng dataset; "
            f"chạy --arms {BASELINE_ARM} với --dataset/--output này trước"
        )

    log = RunLog(output_path.parent, fingerprint, resume=not args.no_resume)
    log.say(f"\n{'=' * 96}\nABLATION  {utcnow()}\n"
            f"  dataset   {_relative_to_root(dataset_path)}  ({len(samples)} câu)\n"
            f"  arms      {', '.join(requested)}\n"
            f"  output    {_relative_to_root(output_path)}\n{'=' * 96}")
    resumed = sum(log.done_count(arm) for arm in requested)
    if resumed:
        log.say(f"↻ checkpoint: {resumed} dòng đã xong, chạy tiếp phần còn lại\n")

    # Baseline mới làm mọi so sánh cũ vô hiệu; không bao giờ ghép RRR mới với
    # generation cũ của arm khác từ một baseline trước đó.
    arms = {} if runs_baseline else dict(existing.get("arms") or {})
    failed_arms: list[str] = []
    baseline_ok = not runs_baseline
    for arm in requested:
        if arm != BASELINE_ARM and not baseline_ok:
            _arm_marker(arm, "skipped")
            print(f"[{arm}] SKIPPED: baseline {BASELINE_ARM} thất bại.", flush=True)
            continue
        started = time.perf_counter()
        _arm_marker(arm, "start")
        done = log.done_count(arm)
        log.say(f"\n{'─' * 96}\n▶ {arm}  {arm_label(arm)}"
                + (f"   ({done}/{len(samples)} đã xong, chạy tiếp)" if done else "")
                + f"\n{'─' * 96}")
        try:
            items, summary = _run_arm(
                arm,
                samples,
                oracle_top_k=args.oracle_top_k,
                judge_model=args.judge_model,
                judge_no_cache=args.no_cache,
                model=args.model,
                log=log,
                verbose=not args.quiet,
            )
        except Exception as exc:
            failed_arms.append(arm)
            _arm_marker(arm, "fail", duration_s=time.perf_counter() - started)
            print(f"[{arm}] FAIL: {type(exc).__name__}: {exc}", flush=True)
            if arm == BASELINE_ARM:
                raise
            continue
        arms[arm] = {"summary": summary, "items": items}
        if arm == BASELINE_ARM:
            baseline_ok = True
        _arm_marker(arm, "ok", duration_s=time.perf_counter() - started)
        log.say("\n" + arm_summary_table({arm: arms[arm]}))

    report = {
        "schema_version": 2,
        "experiment": "paired_ablation",
        "dataset": _relative_to_root(dataset_path),
        "question_fingerprint": fingerprint,
        "dataset_fingerprint": dataset_fingerprint,
        "question_ids": [str(sample["sample_id"]) for sample in samples],
        "updated_at": utcnow(),
        "arms": arms,
        "paired": _paired_summary(arms),
        "protocol": {
            "judge_provider": "openai",
            "judge_model": args.judge_model,
            "judge_cache_read": not args.no_cache,
            "generator_model": args.model or Settings().llm_model,
            "generator_oracle_selection": "candidate_0",
            "generator_oracle_temperature": (
                "temperature_0_or_provider_default_three_runs"
            ),
            "retry_policy": "one_retry_with_1s_backoff",
            "dataset_scope": (
                f"one dataset and its own {BASELINE_ARM} baseline per artifact"
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Summary luôn được sinh lại ngay sau khi arm chạy. Để chạy tay là cách
    # summary.json thành stale so với results.json — đúng lỗi đã xảy ra tháng 7.
    summary_path = (
        _path(args.summary_output).resolve()
        if args.summary_output
        else output_path.with_name("summary.json")
    )
    summarize_file(
        output_path,
        summary_path,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    summary_doc = json.loads(summary_path.read_text(encoding="utf-8"))
    log.say(f"\n{'=' * 96}\nTỔNG KẾT\n{'=' * 96}")
    log.say(arm_summary_table(arms))
    log.say(f"\nSo cặp với {BASELINE_ARM}:")
    log.say(delta_table(summary_doc, BASELINE_ARM))
    log.say(f"\n  results   {_relative_to_root(output_path)}"
            f"\n  summary   {_relative_to_root(summary_path)}"
            f"\n  log       {_relative_to_root(log.log_path)}"
            f"\n  rows      {_relative_to_root(log.rows_path)}  (checkpoint)")
    if failed_arms:
        log.say(f"\n  arm thất bại: {', '.join(failed_arms)}")
    if failed_arms:
        raise SystemExit(f"arm thất bại: {', '.join(failed_arms)}")
    return report


if __name__ == "__main__":
    main()
