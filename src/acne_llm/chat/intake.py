"""Unified pre-LLM intake for chat entrypoints.

This module owns the deterministic steps before generation:
preprocess -> normalize -> fold session facts -> guardrails/scope ->
completeness -> clinical plan -> effective mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from loguru import logger
from ..guardrails.runner import GuardrailRunner
from ..schemas import AcneClinicalInput, AdviseOutput, UserInput
from ._terms import CASE_INTAKE_TERMS, COMPLAINT_TERMS, QUESTION_TERMS, contains_any
from ..schemas.clinical import ClinicalQueryPlan
from .completeness import CompletenessResult, check_completeness
from .intent_router import RouteDecision, route_intent
from .normalizer import normalize_chat_message
from .extraction_confidence import extract_with_confidence, ExtractionConfidence
from .preprocess import prepare_user_text
from .session import (
    ConversationTurn,
    NormalizedSnapshot,
    fold_history_facts,
    get_session_store,
    snapshot_from_user,
)
from ..guardrails.ood_detector import contains_pii
from ..utils.retrieval_query import build_retrieval_query_from_user, extracted_entities_from_user

if TYPE_CHECKING:
    from ..di import Container


ScopeDecision = Literal["in_scope", "refuse_hard", "pass_to_llm_soft"]
EffectiveMode = Literal["hybrid", "llm_only", "refuse", "clarify"]
MAX_MESSAGE_CHARS = 4000   # hard chars fallback (giữ để tương thích)
MAX_MESSAGE_WORDS = 500    # giới hạn từ thực sự — ~850 tokens tiếng Việt


def _count_words(text: str) -> int:
    """Đếm số từ đơn giản: split theo whitespace."""
    return len(text.split())


# _KNOWLEDGE_QUESTION_TERMS đã chuyển sang ._terms.QUESTION_TERMS (shared với intent_router.py)
_KNOWLEDGE_QUESTION_TERMS = QUESTION_TERMS
_COMPLAINT_TERMS = COMPLAINT_TERMS
_CASE_INTAKE_TERMS = CASE_INTAKE_TERMS


@dataclass
class IntakeResult:
    raw_message: str
    clean_text: str
    user: UserInput
    turn_snapshot: NormalizedSnapshot | None
    history: list[ConversationTurn]
    effective_mode: EffectiveMode
    scope_decision: ScopeDecision
    scope_refusal: AdviseOutput | None = None
    completeness: CompletenessResult | None = None
    clinical_plan: ClinicalQueryPlan | None = None
    route_decision: RouteDecision | None = None
    session_id: str | None = None
    clean_text_no_accent: str = ""
    normalized_query: str = ""
    safety_terms: list[str] = field(default_factory=list)
    extracted_entities: dict = field(default_factory=dict)
    pii_detected: bool = False
    teencode_replaced: list[str] = field(default_factory=list)
    extraction_confidence: ExtractionConfidence | None = None  # Kênh phụ cho prompt hedging

    @property
    def is_acne_signal(self) -> bool:
        return self.scope_decision == "in_scope"


def _is_acne_scope(message: str) -> bool:
    return GuardrailRunner.is_acne_scope_text(message)


def _is_genital_scope(message: str) -> bool:
    return GuardrailRunner.is_genital_scope(message)


_ALLOWED_ACNE_REGION_TERMS = (
    "mặt", "mat", "trán", "tran", "má", "ma", "cằm", "cam", "mũi", "mui",
    "quai hàm", "quai ham", "hàm", "ham", "miệng", "mieng",
    "lưng", "lung", "ngực", "nguc", "vai", "cổ", "co", "gáy", "gay",
)

_SAFETY_SIGNAL_TERMS = (
    "mang thai", "pregnant", "pregnancy",
    "cho con bú", "cho con bu", "breastfeeding", "lactation",
    "isotretinoin", "retinoid", "retinol", "tretinoin", "adapalene", "tazarotene",
    "doxycycline", "minocycline", "tetracycline", "kháng sinh", "khang sinh", "antibiotic",
)


def _has_allowed_acne_region(message: str) -> bool:
    return contains_any(message, _ALLOWED_ACNE_REGION_TERMS)


def _extract_safety_terms(message: str, user: UserInput) -> list[str]:
    lowered = message.lower()
    terms = [term for term in _SAFETY_SIGNAL_TERMS if term in lowered]
    if user.context.is_pregnant:
        terms.append("pregnancy")
    if user.context.is_breastfeeding:
        terms.append("breastfeeding")
    for medication in user.context.medications or []:
        med = str(medication).lower()
        if any(term in med for term in _SAFETY_SIGNAL_TERMS):
            terms.append(med)
    if user.clinical:
        for ingredient in user.clinical.canonical_ingredients or []:
            ing = str(ingredient).lower()
            if any(term in ing for term in _SAFETY_SIGNAL_TERMS):
                terms.append(ing)
        for medication in user.clinical.medication_history or []:
            med = str(medication).lower()
            if any(term in med for term in _SAFETY_SIGNAL_TERMS):
                terms.append(med)
    return list(dict.fromkeys(term.strip() for term in terms if term and term.strip()))


def _is_knowledge_question(message: str) -> bool:
    lowered = message.lower()
    return contains_any(lowered, _KNOWLEDGE_QUESTION_TERMS)


def _has_clinical_data(clinical: AcneClinicalInput) -> bool:
    return any(
        (
            clinical.lesion_types,
            clinical.lesion_distribution,
            clinical.inflammation_level,
            clinical.scarring_signs,
            clinical.medication_history,
            clinical.hormonal_factors,
            clinical.skincare_products,
            clinical.treatment_goals,
            clinical.red_flags_input,
        )
    )


def _snapshot_has_values(snapshot: NormalizedSnapshot | None) -> bool:
    """True when a snapshot contains facts worth folding into future turns."""
    if snapshot is None:
        return False
    ctx = snapshot.context or {}
    clinical = snapshot.clinical or {}
    meaningful_context = any(
        (
            ctx.get("age") is not None,
            bool(ctx.get("sex")),
            bool(ctx.get("skin_type")),
            ctx.get("duration_weeks") is not None,
            bool(ctx.get("is_pregnant")),
            bool(ctx.get("is_breastfeeding")),
            bool(ctx.get("allergies")),
            bool(ctx.get("current_products")),
            bool(ctx.get("medications")),
        )
    )
    meaningful_clinical = any(
        value not in (None, "", [], {}, "unknown", "none")
        for value in clinical.values()
    )
    return bool(meaningful_context or meaningful_clinical)


def _scope_check_compat(
    guardrails: object,
    user: UserInput,
    has_acne_history: bool,
) -> AdviseOutput | None:
    if not hasattr(guardrails, "scope_check"):
        return None
    try:
        return guardrails.scope_check(user, has_acne_history=has_acne_history)
    except TypeError:
        return guardrails.scope_check(user)


def _history_clarify_count(history: list[ConversationTurn]) -> int:
    return sum(1 for turn in history if turn.role == "assistant" and turn.mode == "clarify")


def _session_clarify_count(store: object, session_id: str | None, history: list[ConversationTurn]) -> int:
    history_count = _history_clarify_count(history)
    if not session_id or not hasattr(store, "get_or_create"):
        return history_count
    try:
        session = store.get_or_create(session_id)
    except Exception:
        return history_count
    return max(history_count, int(getattr(session, "total_clarify_count", 0) or 0))


def _force_advise_route(route_decision: RouteDecision, reason: str) -> RouteDecision:
    """Return a partial-advise copy once self-context is enough."""
    return replace(
        route_decision,
        primary_intent="advise",
        turn_type="answer",
        confidence=max(route_decision.confidence, 0.72),
        reason_code=f"{route_decision.reason_code}|{reason}",
        route_flags=list(dict.fromkeys([
            *route_decision.route_flags,
            "partial_advise",
            "clarify_loop_break",
        ])),
    )


def _is_intake_reply(message: str, history: list[ConversationTurn]) -> bool:
    """True nếu message là reply ngắn cho câu hỏi intake của bot.

    Ví dụ: bot hỏi "mụn ở vùng nào?" → user trả lời "ở má", "lưng", "mặt"
    → không có acne scope term nhưng vẫn phải check completeness.
    """
    if not history:
        return False
    # Tìm turn assistant cuối cùng
    last_assistant = next(
        (t for t in reversed(history) if t.role == "assistant"),
        None,
    )
    if last_assistant is None:
        return False
    # Nếu turn cuối của bot là câu hỏi clarify (mode clarify)
    if last_assistant.mode == "clarify":
        return True
    return False


def _should_check_completeness(
    message: str,
    user: UserInput,
    history: list[ConversationTurn],
    route_decision: RouteDecision | None = None,
) -> bool:
    # Câu hỏi kiến thức / sản phẩm / cơ chế chung → không cần intake.
    # Đây phải dựa trên message hiện tại, không để clinical facts đã fold từ
    # history kéo user vào completeness flow.
    if route_decision is not None and route_decision.primary_intent == "knowledge":
        return False

    # Reply ngắn cho câu hỏi intake của bot → phải check dù không có acne term
    if _is_intake_reply(message, history):
        return True

    # Không phải acne scope và không phải intake reply → skip
    if not _is_acne_scope(message):
        return False

    lowered = message.lower()
    if route_decision is not None and route_decision.primary_intent == "advise":
        return True

    if contains_any(lowered, _CASE_INTAKE_TERMS):
        return True

    clinical = user.clinical or AcneClinicalInput()
    if _has_clinical_data(clinical):
        return True

    has_prior_acne_context = any(
        turn.role == "user" and _is_acne_scope(turn.content)
        for turn in history
    )
    return has_prior_acne_context and bool(message.strip())


def _is_complaint(message: str) -> bool:
    """True neu tin nhan la complaint / negative feedback ve cau tra loi truoc.

    Nguong 20 tu thay vi 12 de bat complaint co giai thich dai hon,
    vi du: "bot nay tra loi khong dung truong hop cua toi chut nao, toi da noi la da dau roi".
    """
    if len(message.split()) > 20:
        return False
    lowered = message.lower()
    return contains_any(lowered, _COMPLAINT_TERMS)


def _resolve_mode(
    requested_mode: str,
    c: "Container",
    clean_text: str = "",
    history: list | None = None,
) -> Literal["hybrid", "llm_only"]:
    """Resolve mode tu request string + RAG availability + acne signal."""
    mode = (requested_mode or "auto").strip().lower()
    if mode == "llm_only":
        return "llm_only"
    if mode == "hybrid":
        return "hybrid" if c.rag_ready else "llm_only"
    # auto: hybrid khi RAG san sang VA (co acne signal HOAC da co history acne)
    if not c.rag_ready:
        return "llm_only"
    if clean_text and not GuardrailRunner.is_acne_scope_text(clean_text):
        # Follow-up question trong session acne → vẫn dùng hybrid
        has_acne_history = any(
            GuardrailRunner.is_acne_scope_text(t.content)
            for t in (history or [])
            if t.role == "user"
        )
        if not has_acne_history:
            return "llm_only"
    return "hybrid"


def run_intake(
    c: "Container",
    message: str,
    session_id: str | None = None,
    mode_request: str = "auto",
) -> IntakeResult:
    """Run the shared pre-generation intake path for POST, SSE and WS."""
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError(f"message is too long (max {MAX_MESSAGE_CHARS} characters)")
    word_count = _count_words(message)
    if word_count > MAX_MESSAGE_WORDS:
        raise ValueError(
            f"Tin nhắn quá dài ({word_count} từ). Vui lòng rút gọn xuống tối đa {MAX_MESSAGE_WORDS} từ."
        )

    sid_short = (session_id or "no-session")[:8]
    logger.info("[{}] ① INPUT ({}c): {!r}", sid_short, len(message), message[:120])

    raw_message = message
    prepared = prepare_user_text(raw_message)
    clean_text = prepared.clean_text
    clean_text_no_accent = prepared.clean_text_no_accent
    # Dùng container session store (SQLite/JSONL) — không dùng in-memory singleton
    # để đảm bảo intake và runtime đọc/ghi cùng một store (history không bị mất sau restart).
    store = getattr(c, "session_store", None) or get_session_store()
    history = store.get_history(session_id)
    mode = _resolve_mode(mode_request, c, clean_text=clean_text, history=history)
    base_user = normalize_chat_message(
        raw_message,
        mode=mode,
        clean_text=clean_text,
        clean_text_no_accent=clean_text_no_accent,
    )
    _extraction_conf = extract_with_confidence(
        raw_message,
        clean_text=clean_text,
        clean_text_no_accent=clean_text_no_accent,
    )
    safety_terms = _extract_safety_terms(clean_text, base_user)
    turn_snapshot = snapshot_from_user(base_user, clean_text=clean_text)

    _cl = base_user.clinical
    logger.info(
        "[{}] ② NORMALIZE: age={} sex={} skin={} lesions={} dist={} inflam={} "
        "hormonal={} products={} meds={} goals={} red_flags={} mode={}",
        sid_short,
        base_user.context.age,
        base_user.context.sex,
        base_user.context.skin_type,
        (_cl.lesion_types if _cl else []),
        (_cl.lesion_distribution if _cl else []),
        (_cl.inflammation_level if _cl else None),
        (_cl.hormonal_factors if _cl else []),
        (base_user.context.current_products or []),
        (base_user.context.medications or []),
        (_cl.treatment_goals if _cl else []),
        (_cl.red_flags_input if _cl else []),
        mode,
    )

    # Lưu clinical snapshot của turn hiện tại — intent_router dùng để tránh
    # session carry-over làm has_case_signal luôn True, không set side-channel
    # attribute lên Pydantic model.
    current_clinical = (
        base_user.clinical.model_copy(deep=True) if base_user.clinical is not None else None
    )

    try:
        c.guardrails.pre_check(base_user)
    except ValueError as exc:
        logger.info("[{}] → REFUSE (pre_check ValueError: {})", sid_short, exc)
        precheck_refusal = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Yêu cầu không hợp lệ hoặc vi phạm chính sách an toàn"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Mình không thể xử lý tin nhắn này. Vui lòng diễn đạt lại "
                "câu hỏi về tình trạng mụn của bạn để mình có thể hỗ trợ."
            ),
            mode=base_user.mode,
            model_name="",
            latency_ms=0,
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=precheck_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                query_subject="general",
                turn_type="reject",
                route_flags=["pre_check_invalid"],
                reason_code="pre_check_invalid",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )

    # Genital / out-of-scope body region check — phải làm trước OOD để tránh
    # embedding similarity cao do "vùng da" khớp với acne centroid.
    acne_signal = _is_acne_scope(clean_text)
    genital_scope = _is_genital_scope(clean_text)
    mixed_genital_scope = genital_scope and acne_signal and _has_allowed_acne_region(clean_text)
    if genital_scope and not mixed_genital_scope:
        logger.info("[{}] → REFUSE (genital/out-of-scope body region)", sid_short)
        genital_refusal = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Vùng sinh dục và hậu môn ngoài phạm vi tư vấn"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Mình chỉ tư vấn về mụn trứng cá và các vấn đề da mặt/lưng/ngực thông thường. "
                "Mụn hoặc tổn thương ở vùng sinh dục/hậu môn cần được bác sĩ da liễu hoặc "
                "bác sĩ chuyên khoa kiểm tra trực tiếp — có thể liên quan đến bệnh lây truyền "
                "qua đường tình dục hoặc tình trạng đặc biệt cần chẩn đoán chuyên khoa."
            ),
            mode=base_user.mode,
            model_name="",
            latency_ms=0,
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=genital_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                query_subject="general",
                turn_type="reject",
                route_flags=["genital_scope"],
                reason_code="genital_scope_hard_reject",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )
    if mixed_genital_scope:
        logger.info("[{}] ④ MIXED SCOPE: acne region + genital mention", sid_short)

    # Compute has_acne_history once — reused by scope_check and OOD downgrade below.
    has_acne_history = any(
        GuardrailRunner.is_acne_scope_text(t.content)
        for t in history
        if t.role == "user"
    )
    scope_refusal = _scope_check_compat(c.guardrails, base_user, has_acne_history)
    logger.info(
        "[{}] ④ GUARDRAILS: acne_signal={} genital={} refused={} scope={}",
        sid_short,
        acne_signal,
        genital_scope,
        scope_refusal is not None,
        "in_scope" if acne_signal else "pass_to_llm_soft",
    )

    if scope_refusal is not None:
        logger.info("[{}] → REFUSE (out-of-scope)", sid_short)
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=scope_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                query_subject="general",
                turn_type="reject",
                route_flags=["out_of_scope"],
                reason_code="scope_hard_reject",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )

    scope_decision: ScopeDecision = "in_scope" if acne_signal else "pass_to_llm_soft"

    # Auto-downgrade: nếu OOD (pass_to_llm_soft) và mode đang là hybrid
    # → chuyển về llm_only để không chạy RAG và display_mode đúng.
    # Chỉ downgrade khi mode_request == "auto"; nếu user force hybrid thì giữ nguyên.
    # Bug fix: không downgrade nếu session đã có acne turns trước đó —
    # follow-up ngắn ("còn gì nữa k") trong session acne vẫn cần RAG.
    if scope_decision == "pass_to_llm_soft" and mode == "hybrid" and mode_request == "auto":
        # has_acne_history đã được tính ở trên (scope_check), dùng lại để tránh lặp.
        if not has_acne_history:
            mode = "llm_only"
            logger.info("[{}] ④ OOD — auto-downgrade hybrid → llm_only (no acne history)", sid_short)
        else:
            logger.info("[{}] ④ OOD soft — giữ hybrid vì session đã có acne history", sid_short)

    # Complaint / negative-feedback detection
    if _is_complaint(clean_text) and history:
        logger.info("[{}] → CLARIFY (complaint detected)", sid_short)
        apology_q = (
            "Xin lỗi vì câu trả lời trước chưa phù hợp! "
            "Bạn có thể mô tả thêm tình trạng da không — "
            "ví dụ mụn ở vùng nào, có đau/viêm không, bị bao lâu rồi? "
            "Mình sẽ tư vấn sát hơn ngay."
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="clarify",
            scope_decision=scope_decision,
            route_decision=RouteDecision(
                primary_intent="clarify",
                confidence=0.95,
                query_subject="general",
                turn_type="clarify",
                route_flags=[],
                reason_code="complaint",
            ),
            completeness=CompletenessResult(
                kind="too_short",
                question=apology_q,
                clarify_reason="complaint",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            normalized_query=build_retrieval_query_from_user(
                base_user,
                clean_text_normalized=clean_text,
            ),
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )

    route_decision = route_intent(
        clean_text,
        base_user,
        history,
        settings=getattr(c, "settings", None),
        current_clinical=current_clinical,
    )
    if mixed_genital_scope:
        route_decision = replace(
            route_decision,
            route_flags=list(dict.fromkeys([
                *route_decision.route_flags,
                "mixed_genital_scope",
            ])),
            reason_code=f"{route_decision.reason_code}|mixed_genital_scope",
        )
    logger.info(
        "[{}] ⑤ ROUTE: intent={} subject={} conf={:.2f} flags={} source={} reason={}",
        sid_short,
        route_decision.primary_intent,
        route_decision.query_subject,
        route_decision.confidence,
        route_decision.route_flags,
        route_decision.source,
        route_decision.reason_code,
    )

    if route_decision.primary_intent == "reject":
        logger.info("[{}] → REFUSE (intent reject)", sid_short)
        intent_refusal = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Ngoài phạm vi tư vấn mụn trứng cá"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Mình chỉ hỗ trợ các câu hỏi về mụn trứng cá, chăm sóc da mụn "
                "và điều trị mụn an toàn."
            ),
            mode=base_user.mode,
            model_name="",
            latency_ms=0,
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=intent_refusal,
            route_decision=route_decision,
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )

    should_fold_clinical = route_decision.query_subject == "self"
    user = fold_history_facts(base_user, history) if should_fold_clinical else base_user
    turn_snapshot = (
        turn_snapshot
        if should_fold_clinical and _snapshot_has_values(turn_snapshot)
        else None
    )

    # S2-B: chỉ sync merged context cho subject=self. Knowledge/general/other
    # turns không được ghi vào hồ sơ lâm sàng của người dùng.
    if session_id and should_fold_clinical:
        ctx_dict = {
            k: v for k, v in user.context.model_dump(exclude_none=True).items()
            if v is not None
        }
        if ctx_dict:
            store.merge_user_context(session_id, ctx_dict)
    _folded_cl = user.clinical
    logger.info(
        "[{}] ③ SESSION FOLD: {} | history={} turns, asked={} | after_fold → age={} lesions={} dist={} inflam={}",
        sid_short,
        "applied" if should_fold_clinical else "skipped",
        len(history),
        store.get_asked_fields(session_id),
        user.context.age,
        (_folded_cl.lesion_types if _folded_cl else []),
        (_folded_cl.lesion_distribution if _folded_cl else []),
        (_folded_cl.inflammation_level if _folded_cl else None),
    )

    # Lay asked_fields tu session de completeness checker khong hoi lai
    asked_fields = store.get_asked_fields(session_id)
    completeness = (
        check_completeness(user, history=history, asked_fields=asked_fields, confidence=_extraction_conf)
        if should_fold_clinical and _should_check_completeness(clean_text, user, history, route_decision)
        else None
    )

    if route_decision.primary_intent == "clarify" and route_decision.query_subject == "self":
        enough_context = completeness is not None and completeness.level == "sufficient"
        clarify_count = _session_clarify_count(store, session_id, history)
        clarify_limit = 3 if has_acne_history else 5
        too_many_clarifies = clarify_count >= clarify_limit
        if too_many_clarifies:
            route_decision = _force_advise_route(route_decision, "clarify_loop_hard_stop")
            logger.info("[{}] ⑤b ROUTE OVERRIDE: clarify → advise (clarify loop hard stop)", sid_short)
        elif enough_context:
            route_decision = _force_advise_route(route_decision, "clarify_sufficient_context")
            logger.info("[{}] ⑤b ROUTE OVERRIDE: clarify → advise (sufficient self context)", sid_short)

    logger.info(
        "[{}] ⑥ COMPLETENESS: checked={} kind={} level={} missing={} q={!r:.60}",
        sid_short,
        completeness is not None,
        completeness.kind if completeness else "skip",
        completeness.level if completeness else "skip",
        completeness.missing_fields if completeness else [],
        (completeness.question or "") if completeness else "",
    )

    # Completeness gate đã được chuyển sang soft hint (runtime.py).
    # Không block LLM ở đây nữa — chỉ log để debug.
    # completeness hint sẽ được inject vào prompt thay vì trả hardcoded string.
    if completeness is not None and completeness.level == "none":
        logger.info(
            "[{}] → SOFT HINT (missing: {}) — LLM sẽ hỏi tự nhiên",
            sid_short,
            completeness.missing_fields,
        )

    planner = getattr(c, "clinical_planner", None)
    should_build_clinical_plan = (
        route_decision.primary_intent == "advise"
        and route_decision.query_subject == "self"
    )
    has_current_or_history_acne = acne_signal or has_acne_history or _has_clinical_data(
        user.clinical or AcneClinicalInput()
    )
    clinical_plan = (
        planner.plan(user)
        if planner is not None and should_build_clinical_plan and has_current_or_history_acne
        else None
    )
    query_user = user if should_fold_clinical else base_user
    normalized_query = build_retrieval_query_from_user(
        query_user,
        clean_text_normalized=clean_text,
    )
    if clinical_plan is not None and normalized_query:
        clinical_plan.rag_queries.query_vi = normalized_query
    extracted_entities = extracted_entities_from_user(query_user)
    logger.info(
        "[{}] ⑦ CLINICAL PLAN: built={} missing={} lang={} query={!r:.80}",
        sid_short,
        clinical_plan is not None,
        clinical_plan.missing_info if clinical_plan else [],
        clinical_plan.detected_language if clinical_plan else "n/a",
        (clinical_plan.rag_queries.query_vi if clinical_plan else ""),
    )
    effective_mode: EffectiveMode = "clarify" if route_decision.primary_intent == "clarify" else mode
    logger.info(
        "[{}] → {} (scope={} plan={} snapshot={})",
        sid_short,
        effective_mode.upper(),
        scope_decision,
        clinical_plan is not None,
        turn_snapshot is not None,
    )
    return IntakeResult(
        raw_message=raw_message,
        clean_text=clean_text,
        user=user,
        turn_snapshot=turn_snapshot,
        history=history,
        effective_mode=effective_mode,
        scope_decision=scope_decision,
        completeness=completeness,
        clinical_plan=clinical_plan,
        route_decision=route_decision,
        session_id=session_id,
        clean_text_no_accent=clean_text_no_accent,
        normalized_query=normalized_query,
        safety_terms=safety_terms,
        extracted_entities=extracted_entities,
        pii_detected=contains_pii(clean_text),
        teencode_replaced=prepared.teencode_replaced,
        extraction_confidence=_extraction_conf,
    )
