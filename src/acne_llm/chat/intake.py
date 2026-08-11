"""Unified pre-LLM intake for chat entrypoints.

This module owns the deterministic steps before generation:
preprocess -> normalize current turn -> guardrails/scope -> route ->
select recent context -> effective mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import time
from typing import TYPE_CHECKING, Literal

from ..guardrails.runner import GuardrailRunner
from ..schemas import AcneClinicalInput, AdviseOutput, UserInput
from ._terms import CASE_INTAKE_TERMS, contains_any
from .fallback.intent_router import RouteDecision, compute_route_flags, route_intent
from .fallback.llm_extractor import ExtractorFallback
from .fallback.llm_router import RouterFallback
from ._intent_patch import CLARIFY_DOWNGRADED, repaired_intent
from .fallback.rule_normalizer import normalize_chat_message
from .preprocess import light_normalize
from ..schemas.extraction import ExtractionConfidence
from .fallback.rule_extractor import extract_with_confidence
from .preprocess import prepare_user_text, strip_accents
from .session import (
    CONTEXT_FIELD_THRESHOLD,
    ConversationTurn,
    NormalizedSnapshot,
    build_confirmed_profile,
    fold_history_facts,
    get_session_store,
    select_relevant_history,
    snapshot_from_user,
)
from ..guardrails.pii import contains_pii
from ..utils.logging import log_pipeline_stage
from ..utils.retrieval_query import build_current_turn_query, extracted_entities_from_user

if TYPE_CHECKING:
    from ..di import Container


ScopeDecision = Literal["in_scope", "refuse_hard", "pass_to_llm_soft"]
EffectiveMode = Literal["hybrid", "llm_only", "refuse", "clarify"]
MAX_MESSAGE_CHARS = 4000
MAX_MESSAGE_WORDS = 500


def _count_words(text: str) -> int:
    return len(text.split())


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
    route_decision: RouteDecision | None = None
    session_id: str | None = None
    clean_text_no_accent: str = ""
    normalized_query: str = ""
    safety_terms: list[str] = field(default_factory=list)
    extracted_entities: dict = field(default_factory=dict)
    pii_detected: bool = False
    teencode_replaced: list[str] = field(default_factory=list)
    extraction_confidence: ExtractionConfidence | None = None
    confirmed_profile: dict = field(default_factory=dict)

    @property
    def is_acne_signal(self) -> bool:
        return self.scope_decision == "in_scope"


def _is_acne_scope(message: str) -> bool:
    return GuardrailRunner.is_acne_scope_text(message)


def _is_genital_scope(message: str) -> bool:
    return GuardrailRunner.is_genital_scope(message)


_ALLOWED_ACNE_REGION_TERMS = (
    "mat", "mat", "tran", "tran", "ma", "ma", "cam", "cam", "mui", "mui",
    "quai ham", "quai ham", "ham", "ham", "mieng", "mieng",
    "lung", "lung", "nguc", "nguc", "vai", "co", "co", "gay", "gay",
)

_SAFETY_SIGNAL_TERMS = (
    "mang thai", "pregnant", "pregnancy",
    "cho con bu", "breastfeeding", "lactation",
    "isotretinoin", "retinoid", "retinol", "tretinoin", "adapalene", "tazarotene",
    "doxycycline", "minocycline", "tetracycline", "khang sinh", "antibiotic",
)


def _has_allowed_acne_region(message: str) -> bool:
    return contains_any(strip_accents(message.lower()), _ALLOWED_ACNE_REGION_TERMS)


def _extract_safety_terms(message: str, user: UserInput) -> list[str]:
    lowered = message.lower()
    terms = [term for term in _SAFETY_SIGNAL_TERMS if term in lowered]
    # Danh sách này trả lời câu "văn bản CÓ NHẮC TỚI chủ đề gì" — và chỉ nên được
    # dùng cho retrieval, nơi "có nhắc tới" đúng là tín hiệu cần: câu hỏi kiến
    # thức về isotretinoin và thai kỳ thì nên kéo về đoạn guideline thai kỳ.
    #
    # KHÔNG dùng nó để suy TRẠNG THÁI. Nó khớp chuỗi con, không kiểm phủ định:
    # "em không mang thai" cũng sinh ra "pregnancy". Cổng thuốc từng đọc nó như
    # bằng chứng đang mang thai và chặn nhầm 4/5 câu — nay đã đọc thẳng
    # user.context.is_pregnant do intaker điền. Xem guardrails/runner.py.
    if any(term in lowered for term in ("mang thai", "pregnant", "pregnancy", "co thai", "có thai")):
        terms.append("pregnancy")
    if any(term in lowered for term in ("cho con bu", "cho con bú", "breastfeeding", "lactation")):
        terms.append("breastfeeding")
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


def _profile_safety_terms(profile: dict) -> list[str]:
    terms: list[str] = []
    if profile.get("is_pregnant"):
        terms.append("pregnancy")
    if profile.get("is_breastfeeding"):
        terms.append("breastfeeding")
    for medication in profile.get("medications") or []:
        lowered = str(medication).lower()
        if any(term in lowered for term in _SAFETY_SIGNAL_TERMS):
            terms.append(lowered)
    return terms



def _snapshot_has_values(snapshot: NormalizedSnapshot | None) -> bool:
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


def _has_established_case(history: list[ConversationTurn]) -> bool:
    """True when an earlier user turn already put a real acne case on the table."""
    return any(
        turn.role == "user"
        and (
            _snapshot_has_values(turn.normalized_snapshot)
            or _is_acne_scope(turn.content)
        )
        for turn in history
    )



def _resolve_mode(
    requested_mode: str,
    c: "Container",
    clean_text: str = "",
    history: list | None = None,
) -> Literal["hybrid", "llm_only"]:
    mode = (requested_mode or "auto").strip().lower()
    if mode == "llm_only":
        return "llm_only"
    if mode == "hybrid":
        return "hybrid" if c.rag_ready else "llm_only"
    if not c.rag_ready:
        return "llm_only"
    return "hybrid"


def run_intake(
    c: "Container",
    message: str,
    session_id: str | None = None,
    mode_request: str = "auto",
    include_analytics: bool = False,
) -> IntakeResult:
    """Run the shared pre-generation intake path for SSE, WS, and evaluation."""
    request_started = time.perf_counter()
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError(f"message is too long (max {MAX_MESSAGE_CHARS} characters)")
    word_count = _count_words(message)
    if word_count > MAX_MESSAGE_WORDS:
        raise ValueError(
            f"Tin nhan qua dai ({word_count} tu). Vui long rut gon xuong toi da {MAX_MESSAGE_WORDS} tu."
        )

    log_pipeline_stage(
        session_id,
        "INPUT",
        request_started,
        chars=len(message),
        words=word_count,
        requested_mode=mode_request,
    )

    preprocess_started = time.perf_counter()
    raw_message = message
    prepared = prepare_user_text(raw_message)
    clean_text = prepared.clean_text
    clean_text_no_accent = prepared.clean_text_no_accent
    store = c.session_store
    history = store.get_history(session_id)
    mode = _resolve_mode(mode_request, c, clean_text=clean_text, history=history)
    intake_settings = getattr(c, "settings", None)
    # Extractor rule giờ CHỈ là fallback. Trước đây nó chạy ở đây mọi turn và
    # guardrails phán trên số của nó — nên "ngưng tretinoin rồi" vẫn ra
    # medications=['tretinoin'] và bắn safety trước khi intaker kịp nói.
    # Pre-LLM chỉ cần description cho pre_check.
    def _rule_user() -> UserInput:
        return normalize_chat_message(
            raw_message,
            mode=mode,
            clean_text=clean_text,
            clean_text_no_accent=clean_text_no_accent,
        )

    def _rule_conf() -> ExtractionConfidence:
        return extract_with_confidence(
            raw_message,
            clean_text=clean_text,
            clean_text_no_accent=clean_text_no_accent,
        )

    base_user = UserInput(description=light_normalize(raw_message), mode=mode)
    _extraction_conf: ExtractionConfidence | None = None
    safety_terms = _extract_safety_terms(clean_text, base_user)
    log_pipeline_stage(
        session_id,
        "PREPROCESS",
        preprocess_started,
        mode=mode,
        clean_chars=len(clean_text),
        history_turns=len(history),
    )

    safety_started = time.perf_counter()
    try:
        c.guardrails.pre_check(base_user)
    except ValueError as exc:
        log_pipeline_stage(
            session_id,
            "SAFETY",
            safety_started,
            level="WARNING",
            result="blocked",
            reason="pre_check_invalid",
            error=exc,
        )
        log_pipeline_stage(
            session_id,
            "INTAKE",
            safety_started,
            result="blocked",
            reason="pre_check_invalid",
        )
        log_pipeline_stage(
            session_id,
            "ROUTE",
            safety_started,
            intent="reject",
            source="deterministic",
            reason="pre_check_invalid",
        )
        log_pipeline_stage(
            session_id,
            "EXTRACT",
            safety_started,
            status="skipped",
            reason="pre_check_invalid",
        )
        precheck_refusal = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Yeu cau khong hop le hoac vi pham chinh sach an toan"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Minh khong the xu ly tin nhan nay. Vui long dien dat lai "
                "cau hoi ve tinh trang mun de minh ho tro."
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

    acne_signal = _is_acne_scope(clean_text)
    genital_scope = _is_genital_scope(clean_text)
    mixed_genital_scope = genital_scope and acne_signal and _has_allowed_acne_region(clean_text)
    if genital_scope and not mixed_genital_scope:
        log_pipeline_stage(
            session_id,
            "SAFETY",
            safety_started,
            level="WARNING",
            result="blocked",
            reason="genital_scope_hard_reject",
        )
        log_pipeline_stage(
            session_id,
            "INTAKE",
            safety_started,
            result="blocked",
            reason="genital_scope_hard_reject",
        )
        log_pipeline_stage(
            session_id,
            "ROUTE",
            safety_started,
            intent="reject",
            source="deterministic",
            reason="genital_scope_hard_reject",
        )
        log_pipeline_stage(
            session_id,
            "EXTRACT",
            safety_started,
            status="skipped",
            reason="genital_scope_hard_reject",
        )
        genital_refusal = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Vung sinh duc va hau mon ngoai pham vi tu van"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Minh chi tu van ve mun trung ca va cac van de da mat/lung/nguc thong thuong. "
                "Mun hoac ton thuong o vung sinh duc/hau mon can duoc bac si da lieu kiem tra."
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
        log_pipeline_stage(
            session_id,
            "SAFETY",
            safety_started,
            result="mixed_scope",
            genital=True,
        )

    # Hard current-turn medication/pregnancy refusal must run before semantic
    # routing. A second identical guard remains after advise-only session fold
    # so previously confirmed medications are covered as well.
    medication_check = getattr(c.guardrails, "medication_safety_refusal", None)
    current_medication_refusal = (
        medication_check(base_user, safety_terms)
        if callable(medication_check)
        else None
    )
    if isinstance(current_medication_refusal, AdviseOutput):
        log_pipeline_stage(
            session_id,
            "SAFETY",
            safety_started,
            level="WARNING",
            result="blocked",
            reason="medication_safety_block",
            phase="current_turn",
        )
        log_pipeline_stage(
            session_id,
            "INTAKE",
            safety_started,
            result="blocked",
            reason="medication_safety_block",
        )
        log_pipeline_stage(
            session_id,
            "ROUTE",
            safety_started,
            intent="reject",
            source="deterministic",
            reason="medication_safety_block",
        )
        log_pipeline_stage(
            session_id,
            "EXTRACT",
            safety_started,
            status="skipped",
            reason="medication_safety_block",
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=current_medication_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                turn_type="reject",
                route_flags=["medication_safety_block"],
                reason_code="medication_safety_block",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            normalized_query=build_current_turn_query(clean_text),
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
            extraction_confidence=_extraction_conf,
        )

    log_pipeline_stage(
        session_id,
        "SAFETY",
        safety_started,
        result="pass",
        acne_signal=acne_signal,
        genital=genital_scope,
        soft_oos="semantic_router",
    )
    scope_decision: ScopeDecision = "in_scope"
    intake_started = time.perf_counter()
    log_pipeline_stage(
        session_id,
        "INTAKE",
        intake_started,
        state="routing",
        mode=mode,
        history_turns=len(history),
    )

    route_started = time.perf_counter()
    route_decision = None
    llm_router = getattr(c, "llm_router", None)
    if llm_router is not None:
        try:
            route_decision = llm_router.classify(clean_text, history)
        except RouterFallback as exc:
            log_pipeline_stage(
                session_id,
                "ROUTE",
                route_started,
                level="WARNING",
                fallback="semantic",
                error=exc,
            )
        except Exception as exc:
            log_pipeline_stage(
                session_id,
                "ROUTE",
                route_started,
                level="WARNING",
                fallback="semantic",
                error=f"{type(exc).__name__}: {exc}",
            )
    else:
        log_pipeline_stage(
            session_id,
            "ROUTE",
            route_started,
            fallback="semantic",
            reason="llm_router_unavailable",
        )

    if route_decision is None:
        semantic_router = getattr(c, "semantic_router", None)
        if semantic_router is not None:
            try:
                route_decision = semantic_router.classify(clean_text)
            except Exception as exc:
                log_pipeline_stage(
                    session_id,
                    "ROUTE",
                    route_started,
                    level="WARNING",
                    fallback="rule",
                    error=f"{type(exc).__name__}: {exc}",
                )
        else:
            log_pipeline_stage(
                session_id,
                "ROUTE",
                route_started,
                level="WARNING",
                fallback="rule",
                reason="semantic_router_unavailable",
            )

        if route_decision is None:
            base_user = _rule_user()
            _extraction_conf = _rule_conf()
            route_decision = route_intent(
                clean_text,
                base_user,
                history,
                settings=getattr(c, "settings", None),
                current_clinical=base_user.clinical,
            )
    # Chỉ đường rule sinh route_flags; unified và semantic trả list rỗng, làm
    # chết im lặng cảnh báo khẩn cấp (_safety) và guidance an toàn
    # (prompt_builder). Cờ là tín hiệu văn bản nên không phụ thuộc router nào
    # chọn intent -> gắn chung cho mọi đường. Với đường rule đây là no-op vì
    # cùng nguồn cờ và dict.fromkeys khử trùng.
    _text_flags = compute_route_flags(clean_text, history=history)
    if _text_flags:
        route_decision = replace(
            route_decision,
            route_flags=list(dict.fromkeys([
                *route_decision.route_flags,
                *_text_flags,
            ])),
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
    # Vá cho lỗi DỮ LIỆU, không phải luật nghiệp vụ — xem `_intent_patch.py`
    # để biết bằng chứng, phạm vi, và điều kiện xoá.
    _intent = repaired_intent(
        route_decision.primary_intent, _has_established_case(history)
    )
    if _intent != route_decision.primary_intent:
        route_decision = replace(
            route_decision,
            primary_intent=_intent,
            route_flags=list(dict.fromkeys([
                *route_decision.route_flags,
                CLARIFY_DOWNGRADED,
            ])),
            reason_code=f"{route_decision.reason_code}|established_case",
        )
    route_source = (
        "unified_intake"
        if route_decision.reason_code == "unified_intake"
        else "legacy_llm"
        if route_decision.source == "llm"
        else route_decision.source
    )
    log_pipeline_stage(
        session_id,
        "ROUTE",
        route_started,
        intent=route_decision.primary_intent,
        source=route_source,
        confidence=route_decision.confidence,
        flags=route_decision.route_flags,
        reason=route_decision.reason_code,
    )

    if route_decision.primary_intent == "reject":
        log_pipeline_stage(
            session_id,
            "EXTRACT",
            time.perf_counter(),
            status="skipped",
            reason="soft_reject",
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=UserInput(description=clean_text, mode="llm_only"),
            turn_snapshot=None,
            history=[],
            effective_mode="llm_only",
            scope_decision="pass_to_llm_soft",
            scope_refusal=None,
            route_decision=route_decision,
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            normalized_query=clean_text,
            safety_terms=[],
            extracted_entities={},
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )

    if route_decision.primary_intent == "clarify":
        selected_history = select_relevant_history(
            clean_text,
            route_decision.primary_intent,
            history,
            route_decision.route_flags,
        )
        log_pipeline_stage(
            session_id,
            "EXTRACT",
            time.perf_counter(),
            status="skipped",
            reason="clarify",
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=UserInput(description=clean_text, mode="llm_only"),
            turn_snapshot=None,
            history=selected_history,
            effective_mode="clarify",
            scope_decision="in_scope",
            route_decision=route_decision,
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            normalized_query=build_current_turn_query(clean_text, selected_history),
            safety_terms=safety_terms,
            extracted_entities={},
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
        )

    # Advise/knowledge only: now pay the 1.5B extraction cost. The rule parser
    # above remains the fallback if the model is unavailable or invalid.
    extract_started = time.perf_counter()
    extraction_source = "rule"
    extractor_mode = getattr(intake_settings, "extractor_mode", "rule")
    llm_extractor = getattr(c, "llm_extractor", None)
    if extractor_mode == "llm" and llm_extractor is not None:
        try:
            extracted = llm_extractor.run(
                clean_text=clean_text,
                clean_text_no_accent=clean_text_no_accent,
                mode=mode,
                history=history,
            )
            base_user = extracted.user
            _extraction_conf = extracted.confidence
            extraction_source = (
                "unified_intake"
                if route_decision.reason_code == "unified_intake"
                else "legacy_llm"
            )
        except ExtractorFallback as exc:
            base_user = _rule_user()
            _extraction_conf = _rule_conf()
            log_pipeline_stage(
                session_id,
                "EXTRACT",
                extract_started,
                level="WARNING",
                fallback="rule",
                error=exc,
            )
        except Exception as exc:
            base_user = _rule_user()
            _extraction_conf = _rule_conf()
            log_pipeline_stage(
                session_id,
                "EXTRACT",
                extract_started,
                level="WARNING",
                fallback="rule",
                error=f"{type(exc).__name__}: {exc}",
            )
    else:
        base_user = _rule_user()
        _extraction_conf = _rule_conf()
        if extractor_mode == "llm":
            log_pipeline_stage(
                session_id,
                "EXTRACT",
                extract_started,
                level="WARNING",
                fallback="rule",
                reason="extractor_unavailable",
            )

    _cl = base_user.clinical
    log_pipeline_stage(
        session_id,
        "EXTRACT",
        extract_started,
        source=extraction_source,
        age=base_user.context.age,
        sex=base_user.context.sex,
        skin=base_user.context.skin_type,
        lesions=(_cl.lesion_types if _cl else []),
        inflammation=(_cl.inflammation_level if _cl else None),
    )

    # BUG FIX: compute_route_flags o tren chay TRUOC extract nen khong co `user`,
    # khien nhanh `has_red_flags` trong intent_router luon False -- moi red flag
    # ma intaker trich duoc deu khong bat duoc canh bao khan o _safety.
    # Co nay phu thuoc clinical nen phai gan LAI sau khi da co base_user.clinical.
    if _cl and _cl.red_flags_input and "urgency_red_flag" not in route_decision.route_flags:
        route_decision = replace(
            route_decision,
            route_flags=[*route_decision.route_flags, "urgency_red_flag"],
        )

    # Preserve the full-field hard gates after extraction and before any fold,
    # retrieval, prompt build, or generation.
    c.guardrails.pre_check(base_user)
    safety_terms = list(dict.fromkeys([
        *safety_terms,
        *_extract_safety_terms(clean_text, base_user),
    ]))
    extracted_medication_refusal = (
        medication_check(base_user, safety_terms)
        if callable(medication_check)
        else None
    )
    if isinstance(extracted_medication_refusal, AdviseOutput):
        log_pipeline_stage(
            session_id,
            "SAFETY",
            extract_started,
            level="WARNING",
            result="blocked",
            reason="medication_safety_block",
            phase="post_extract",
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=base_user,
            turn_snapshot=None,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=extracted_medication_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                turn_type="reject",
                route_flags=["medication_safety_block"],
                reason_code="medication_safety_block",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            normalized_query=build_current_turn_query(clean_text),
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
            extraction_confidence=_extraction_conf,
        )

    is_personal_case = route_decision.primary_intent == "advise"
    selected_history = select_relevant_history(
        clean_text,
        route_decision.primary_intent,
        history,
        route_decision.route_flags,
    )
    confirmed_profile: dict = {}
    if is_personal_case:
        if session_id and hasattr(store, "get_or_create"):
            store.get_or_create(session_id)
        existing_profile = store.get_user_context(session_id)
        # Nut vat that su, khong con bi max(0.82, ...) khoa cung. Ban cu khien
        # extract_min_field_conf chi tang duoc, khong giam duoc -- gia tri mac dinh
        # 0.60 chua bao gio co tac dung. Thai ky/cho bu khong di qua nguong nay,
        # xem CONTEXT_FIELD_THRESHOLD trong session.py.
        confirmed_profile = build_confirmed_profile(
            existing_profile,
            _extraction_conf,
            clean_text,
            threshold=float(
                getattr(
                    getattr(c, "settings", None),
                    "extract_min_field_conf",
                    CONTEXT_FIELD_THRESHOLD,
                )
            ),
        )
        if session_id and confirmed_profile != existing_profile:
            store.merge_user_context(session_id, confirmed_profile)
        safety_terms = list(dict.fromkeys([
            *_extract_safety_terms(clean_text, base_user),
            *_profile_safety_terms(confirmed_profile),
        ]))
    user = fold_history_facts(base_user, history) if is_personal_case else base_user
    turn_snapshot = (
        snapshot_from_user(base_user, clean_text)
        if session_id and is_personal_case
        else None
    )
    _folded_cl = user.clinical
    log_pipeline_stage(
        session_id,
        "INTAKE",
        intake_started,
        level="DEBUG",
        fold=("structured" if is_personal_case else "skipped"),
        history_turns=len(selected_history),
        age=user.context.age,
        lesions=(_folded_cl.lesion_types if _folded_cl else []),
        inflammation=(_folded_cl.inflammation_level if _folded_cl else None),
    )

    medication_refusal = None
    if callable(medication_check):
        medication_refusal = medication_check(user, safety_terms)
    if isinstance(medication_refusal, AdviseOutput):
        log_pipeline_stage(
            session_id,
            "SAFETY",
            intake_started,
            level="WARNING",
            result="blocked",
            reason="medication_safety_block",
            phase="session_fold",
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=user,
            turn_snapshot=turn_snapshot,
            history=selected_history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=medication_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                turn_type="reject",
                route_flags=["medication_safety_block"],
                reason_code="medication_safety_block",
            ),
            session_id=session_id,
            clean_text_no_accent=clean_text_no_accent,
            normalized_query=build_current_turn_query(clean_text, selected_history),
            safety_terms=safety_terms,
            extracted_entities=extracted_entities_from_user(base_user),
            pii_detected=contains_pii(clean_text),
            teencode_replaced=prepared.teencode_replaced,
            extraction_confidence=_extraction_conf,
            confirmed_profile=confirmed_profile,
        )

    # Retrieval dùng thẳng query của lượt hiện tại (planner đã gỡ).
    normalized_query = build_current_turn_query(clean_text, selected_history)
    extracted_entities = extracted_entities_from_user(base_user)
    effective_mode: EffectiveMode = "clarify" if route_decision.primary_intent == "clarify" else mode
    log_pipeline_stage(
        session_id,
        "INTAKE",
        intake_started,
        result="ready",
        effective_mode=effective_mode,
        scope=scope_decision,
        snapshot=turn_snapshot is not None,
    )
    return IntakeResult(
        raw_message=raw_message,
        clean_text=clean_text,
        user=user,
        turn_snapshot=turn_snapshot,
        history=selected_history,
        effective_mode=effective_mode,
        scope_decision=scope_decision,
        route_decision=route_decision,
        session_id=session_id,
        clean_text_no_accent=clean_text_no_accent,
        normalized_query=normalized_query,
        safety_terms=safety_terms,
        extracted_entities=extracted_entities,
        pii_detected=contains_pii(clean_text),
        teencode_replaced=prepared.teencode_replaced,
        extraction_confidence=_extraction_conf,
        confirmed_profile=confirmed_profile,
    )
