"""Unified pre-LLM intake for chat entrypoints.

This module owns the deterministic steps before generation:
preprocess -> normalize current turn -> guardrails/scope -> route ->
select recent context -> completeness hint -> effective mode.
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
from .preprocess import prepare_user_text, strip_accents
from .session import (
    ConversationTurn,
    NormalizedSnapshot,
    build_confirmed_profile,
    fold_history_facts,
    get_session_store,
    select_relevant_history,
    snapshot_from_user,
)
from ..guardrails.ood_detector import contains_pii
from ..utils.retrieval_query import build_current_turn_query, extracted_entities_from_user

if TYPE_CHECKING:
    from ..di import Container


ScopeDecision = Literal["in_scope", "refuse_hard", "pass_to_llm_soft"]
EffectiveMode = Literal["hybrid", "llm_only", "refuse", "clarify"]
MAX_MESSAGE_CHARS = 4000
MAX_MESSAGE_WORDS = 500


def _count_words(text: str) -> int:
    return len(text.split())


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
    if not history:
        return False
    last_assistant = next(
        (t for t in reversed(history) if t.role == "assistant"),
        None,
    )
    if last_assistant is None:
        return False
    return last_assistant.mode == "clarify"


def _should_check_completeness(
    message: str,
    user: UserInput,
    history: list[ConversationTurn],
    route_decision: RouteDecision | None = None,
) -> bool:
    if route_decision is not None and route_decision.primary_intent == "knowledge":
        return False
    if _is_intake_reply(message, history):
        return True
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
    mode = (requested_mode or "auto").strip().lower()
    if mode == "llm_only":
        return "llm_only"
    if mode == "hybrid":
        return "hybrid" if c.rag_ready else "llm_only"
    if not c.rag_ready:
        return "llm_only"
    if clean_text and not GuardrailRunner.is_acne_scope_text(clean_text):
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
    include_analytics: bool = False,
) -> IntakeResult:
    """Run the shared pre-generation intake path for SSE, WS, and evaluation."""
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError(f"message is too long (max {MAX_MESSAGE_CHARS} characters)")
    word_count = _count_words(message)
    if word_count > MAX_MESSAGE_WORDS:
        raise ValueError(
            f"Tin nhan qua dai ({word_count} tu). Vui long rut gon xuong toi da {MAX_MESSAGE_WORDS} tu."
        )

    sid_short = (session_id or "no-session")[:8]
    logger.info("[{}] INPUT ({}c): {!r}", sid_short, len(message), message[:120])

    raw_message = message
    prepared = prepare_user_text(raw_message)
    clean_text = prepared.clean_text
    clean_text_no_accent = prepared.clean_text_no_accent
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
    # Early-exit safety_terms: dung base_user (chua fold) cho cac nhanh refuse thoat som.
    # Happy path se re-extract sau fold de bat pregnancy/medication tu session history.
    safety_terms = _extract_safety_terms(clean_text, base_user)
    # The current-turn snapshot is persisted only after routing confirms this
    # is the user's own case. It powers correction-aware structured memory;
    # prompt-visible text history remains separately selected and bounded.
    turn_snapshot = None

    _cl = base_user.clinical
    logger.info(
        "[{}] NORMALIZE: age={} sex={} skin={} lesions={} inflam={} mode={}",
        sid_short,
        base_user.context.age,
        base_user.context.sex,
        base_user.context.skin_type,
        (_cl.lesion_types if _cl else []),
        (_cl.inflammation_level if _cl else None),
        mode,
    )

    current_clinical = (
        base_user.clinical.model_copy(deep=True) if base_user.clinical is not None else None
    )

    try:
        c.guardrails.pre_check(base_user)
    except ValueError as exc:
        logger.info("[{}] REFUSE (pre_check ValueError: {})", sid_short, exc)
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
                query_subject="non_self",
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
        logger.info("[{}] REFUSE (genital/out-of-scope body region)", sid_short)
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
                query_subject="non_self",
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
        logger.info("[{}] MIXED SCOPE: acne region + genital mention", sid_short)

    has_acne_history = any(
        GuardrailRunner.is_acne_scope_text(t.content)
        for t in history
        if t.role == "user"
    )
    scope_refusal = _scope_check_compat(c.guardrails, base_user, has_acne_history)
    logger.info(
        "[{}] GUARDRAILS: acne_signal={} genital={} refused={} scope={}",
        sid_short,
        acne_signal,
        genital_scope,
        scope_refusal is not None,
        "in_scope" if acne_signal else "pass_to_llm_soft",
    )

    if scope_refusal is not None:
        logger.info("[{}] REFUSE (out-of-scope)", sid_short)
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
                query_subject="non_self",
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

    if scope_decision == "pass_to_llm_soft" and mode == "hybrid" and mode_request == "auto":
        if not has_acne_history:
            mode = "llm_only"
            logger.info("[{}] OOD auto-downgrade hybrid -> llm_only", sid_short)
        else:
            logger.info("[{}] OOD soft -- keep hybrid (session has acne history)", sid_short)

    if _is_complaint(clean_text) and history:
        logger.info("[{}] CLARIFY (complaint detected)", sid_short)
        apology_q = (
            "Xin loi vi cau tra loi truoc chua phu hop! "
            "Ban co the mo ta them tinh trang da khong -- "
            "vi du mun o vung nao, co dau/viem khong, bi bao lau roi? "
            "Minh se tu van sat hon ngay."
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
                query_subject="non_self",
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
            normalized_query=build_current_turn_query(clean_text),
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
        "[{}] ROUTE: intent={} subject={} conf={:.2f} flags={} reason={}",
        sid_short,
        route_decision.primary_intent,
        route_decision.query_subject,
        route_decision.confidence,
        route_decision.route_flags,
        route_decision.reason_code,
    )

    if route_decision.primary_intent == "reject":
        logger.info("[{}] REFUSE (intent reject)", sid_short)
        intent_refusal = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Ngoai pham vi tu van mun trung ca"],
            recommendations=[],
            red_flags=[],
            used_chunks=[],
            confidence=0.0,
            disclaimer=(
                "Minh chi ho tro cac cau hoi ve mun trung ca, cham soc da mun "
                "va dieu tri mun an toan."
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

    is_self_case = route_decision.query_subject == "self"
    selected_history = select_relevant_history(
        clean_text,
        route_decision.primary_intent,
        history,
        route_decision.route_flags,
    )
    confirmed_profile: dict = {}
    if is_self_case:
        if session_id and hasattr(store, "get_or_create"):
            store.get_or_create(session_id)
        existing_profile = store.get_user_context(session_id)
        confirmed_profile = build_confirmed_profile(
            existing_profile,
            _extraction_conf,
            clean_text,
            threshold=max(
                0.82,
                float(getattr(getattr(c, "settings", None), "extract_min_field_conf", 0.60)),
            ),
        )
        if session_id and confirmed_profile != existing_profile:
            store.merge_user_context(session_id, confirmed_profile)
        safety_terms = list(dict.fromkeys([
            *_extract_safety_terms(clean_text, base_user),
            *_profile_safety_terms(confirmed_profile),
        ]))
    user = fold_history_facts(base_user, history) if is_self_case else base_user
    turn_snapshot = (
        snapshot_from_user(base_user, clean_text)
        if session_id and is_self_case and route_decision.primary_intent == "advise"
        else None
    )
    _folded_cl = user.clinical
    logger.info(
        "[{}] SESSION FOLD: {} | history={} turns | age={} lesions={} inflam={}",
        sid_short,
        "structured-fold" if is_self_case else "skipped",
        len(selected_history),
        user.context.age,
        (_folded_cl.lesion_types if _folded_cl else []),
        (_folded_cl.inflammation_level if _folded_cl else None),
    )

    medication_refusal = None
    medication_check = getattr(c.guardrails, "medication_safety_refusal", None)
    if callable(medication_check):
        medication_refusal = medication_check(user, safety_terms)
    if isinstance(medication_refusal, AdviseOutput):
        logger.warning("[{}] REFUSE (deterministic medication safety)", sid_short)
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
                query_subject="self",
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

    # Gap fix 2: route override (clarify -> advise) phai xay ra TRUOC check_completeness.
    # Neu override xay ra SAU, completeness duoc tinh voi intent=clarify roi prompt
    # advise nhan completeness=None -- thieu hint du user chua du thong tin.
    if (
        route_decision.primary_intent == "clarify"
        and route_decision.query_subject == "self"
        and not ({"crisis_signal", "urgency_red_flag"} & set(route_decision.route_flags))
    ):
        clarify_count = _session_clarify_count(store, session_id, history)
        clarify_limit = 3 if has_acne_history else 5
        too_many_clarifies = clarify_count >= clarify_limit
        if too_many_clarifies:
            route_decision = _force_advise_route(route_decision, "clarify_loop_hard_stop")
            logger.info("[{}] ROUTE OVERRIDE: clarify -> advise (clarify loop hard stop)", sid_short)
        else:
            _quick_completeness = check_completeness(
                user, history=selected_history,
                asked_fields=store.get_asked_fields(session_id),
                confidence=_extraction_conf,
            )
            if _quick_completeness is not None and _quick_completeness.level == "sufficient":
                route_decision = _force_advise_route(route_decision, "clarify_sufficient_context")
                logger.info("[{}] ROUTE OVERRIDE: clarify -> advise (sufficient self context)", sid_short)

    asked_fields = store.get_asked_fields(session_id)
    completeness = (
        check_completeness(user, history=selected_history, asked_fields=asked_fields, confidence=_extraction_conf)
        if is_self_case and _should_check_completeness(clean_text, user, selected_history, route_decision)
        else None
    )

    logger.info(
        "[{}] COMPLETENESS: checked={} kind={} level={} missing={}",
        sid_short,
        completeness is not None,
        completeness.kind if completeness else "skip",
        completeness.level if completeness else "skip",
        completeness.missing_fields if completeness else [],
    )

    if completeness is not None and completeness.level == "none":
        logger.info("[{}] SOFT HINT missing={}", sid_short, completeness.missing_fields)

    # Planner is analytics-only in schema v2: never drives retrieval or prompt.
    # Chỉ build khi include_analytics (vd /debug/trace) để không phí CPU trên hot path.
    planner = getattr(c, "clinical_planner", None)
    should_build_clinical_plan = (
        route_decision.primary_intent == "advise"
        and route_decision.query_subject == "self"
    )
    has_current_or_history_acne = acne_signal or _has_clinical_data(user.clinical or AcneClinicalInput())
    clinical_plan = (
        planner.plan(user)
        if include_analytics
        and planner is not None and should_build_clinical_plan and has_current_or_history_acne
        else None
    )
    normalized_query = build_current_turn_query(clean_text, selected_history)
    extracted_entities = extracted_entities_from_user(base_user)
    logger.info(
        "[{}] CLINICAL PLAN: built={} lang={} query={!r:.80}",
        sid_short,
        clinical_plan is not None,
        clinical_plan.detected_language if clinical_plan else "n/a",
        (clinical_plan.rag_queries.query_vi if clinical_plan else ""),
    )
    effective_mode: EffectiveMode = "clarify" if route_decision.primary_intent == "clarify" else mode
    logger.info(
        "[{}] -> {} (scope={} plan={} snapshot={})",
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
        history=selected_history,
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
        confirmed_profile=confirmed_profile,
    )
