"""Lightweight intent routing for chat intake.

The router is intentionally conservative: deterministic rules make the primary
decision, while an optional micro-classifier can help only when rules are weak
or ambiguous. Hard guardrails live outside this module and must run first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Literal, Protocol
import unicodedata

from loguru import logger

from ..schemas import AcneClinicalInput, UserInput
from .session import ConversationTurn
from ..llm.query_expander import detect_language_heuristic
from ._terms import QUESTION_TERMS


PrimaryIntent = Literal["advise", "knowledge", "clarify", "reject"]
IntentSource = Literal["rule", "micro_model", "hybrid"]
QuerySubject = Literal["self", "other", "general"]


@dataclass
class ClassifierResult:
    primary_intent: PrimaryIntent
    scores: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    is_ambiguous: bool = False
    reason_code: str = ""


@dataclass
class RouteDecision:
    primary_intent: PrimaryIntent
    confidence: float
    query_subject: QuerySubject = "self"
    source: IntentSource = "rule"
    classifier_used: bool = False
    turn_type: str = "answer"
    route_flags: list[str] = field(default_factory=list)
    detected_language: str = "unknown"
    reason_code: str = "rule_default"
    ambiguity_reason: str | None = None

    def metadata(self) -> dict:
        data = {
            "primary_intent": self.primary_intent,
            "query_subject": self.query_subject,
            "intent_confidence": self.confidence,
            "intent_source": self.source,
            "classifier_used": self.classifier_used,
            "turn_type": self.turn_type if self.turn_type != "answer" else self.primary_intent,
            "route_flags": list(self.route_flags),
            "detected_language": self.detected_language,
            "reason_code": self.reason_code,
        }
        if self.ambiguity_reason:
            data["ambiguity_reason"] = self.ambiguity_reason
        return data


class IntentClassifier(Protocol):
    def classify(self, message: str, signals: dict) -> ClassifierResult | None:
        ...


_FOLLOWUP_SHORT_TERMS = (
    # Câu follow-up điển hình trong session acne — không có acne keyword
    # nhưng rõ ràng là tiếp nối cuộc hội thoại.
    "còn gì nữa", "con gi nua", "còn nữa không", "con nua khong",
    "có gì khác", "co gi khac", "còn phương pháp", "con phuong phap",
    "sao vậy", "sao vay", "vậy thì sao", "vay thi sao",
    "tiếp theo", "tiep theo", "bước tiếp theo", "buoc tiep theo",
    "thế còn", "the con", "vậy ah", "vay ah", "à vậy", "a vay",
    "dùng bao lâu", "dung bao lau", "mất bao lâu", "mat bao lau",
    "bao lâu thì", "bao lau thi",
    "còn ban đêm", "con ban dem", "còn ban ngày", "con ban ngay",
    "oke", "ok hiểu", "hiểu rồi", "hieu roi", "biết rồi", "biet roi",
    "oke vậy", "vậy thôi", "vay thoi",
    "thêm gì nữa", "them gi nua", "có thêm", "co them",
    # Follow-up context dài hơn 6 từ — continuation rõ ràng trong session
    "vậy với da", "vay voi da", "thế với da", "the voi da",
    "còn buổi sáng", "con buoi sang", "còn buổi tối", "con buoi toi",
    "còn ban ngày thì", "con ban ngay thi",
    "vậy nếu dùng", "vay neu dung", "thế nếu dùng", "the neu dung",
    "vậy thì dùng gì", "vay thi dung gi",
    "còn loại khác", "con loai khac", "có loại nào khác", "co loai nao khac",
    "vậy mình nên", "vay minh nen", "thế mình nên", "the minh nen",
    "vậy tôi nên", "vay toi nen",
    "với da dầu thì", "voi da dau thi", "với da khô thì", "voi da kho thi",
    "với da nhạy cảm", "voi da nhay cam",
    "kết hợp được không", "ket hop duoc khong",
    "dùng chung được không", "dung chung duoc khong",
)

# _QUESTION_TERMS đã chuyển sang ._terms.QUESTION_TERMS (shared với intake.py)
_QUESTION_TERMS = QUESTION_TERMS
# Knowledge-only markers: câu hỏi dạng liệt kê/ranking/nguyên nhân chung
# → luôn là knowledge question bất kể có clinical terms hay không
_KNOWLEDGE_RANKING_TERMS = (
    "top 10", "top10", "top 5", "top5", "top 3", "top3",
    "top những", "top các", "top cac",
    "danh sách", "danh sach", "liệt kê", "liet ke",
    "nguyên nhân", "nguyen nhan",
    "nguyên nhân chính", "nguyen nhan chinh",
    "các nguyên nhân", "cac nguyen nhan",
    "những nguyên nhân", "nhung nguyen nhan",
    "giải thích", "giai thich", "cơ chế", "co che",
    "lý do", "ly do", "vì sao", "vi sao", "tại sao", "tai sao",
    "là gì", "la gi",
)
_PRODUCT_QUERY_TERMS = (
    "kem chống nắng", "kem chong nang", "sunscreen", "spf",
    "sản phẩm", "san pham", "loại nào", "loai nao",
    "gợi ý", "goi y", "recommend",
    "oil-free", "non-comedogenic", "không gây bít tắc", "khong gay bit tac",
)
_FOOD_KNOWLEDGE_TERMS = (
    "ăn", "an ", "mì cay", "mi cay", "đồ cay", "do cay",
    "sữa", "sua", "đường", "duong", "whey", "cà phê", "ca phe",
    "nên ăn", "nen an", "kiêng", "kieng",
)
_PERSONAL_TERMS = (
    # Chỉ dùng personal terms có chủ thể rõ ràng
    # KHÔNG dùng "em", "con" standalone vì trùng với từ thông thường ("em ơi", "con đường")
    "tôi", "toi", "mình", "minh",
    "da tôi", "da toi", "mặt tôi", "mat toi", "của tôi", "cua toi",
    "tình trạng tôi", "tinh trang toi",
    "đang bị", "dang bi", "tôi bị", "toi bi",
    "mình bị", "minh bi", "em bị", "em bi", "cháu bị", "chau bi",
    "da mình", "da minh", "mặt mình", "mat minh",
)
_OTHER_SUBJECT_TERMS = (
    "bạn tôi", "ban toi",
    "bạn mình", "ban minh",
    "bạn em", "ban em",
    "bạn của tôi", "ban cua toi",
    "bạn của mình", "ban cua minh",
    "người khác", "nguoi khac",
    "người quen", "nguoi quen",
    "cho người quen", "cho nguoi quen",
    "người yêu", "nguoi yeu",
    "em trai", "chị gái", "anh trai",
    "em gai", "chi gai", "anh trai",
)
_SELF_SUBJECT_TERMS = (
    "tôi", "toi", "mình", "minh",
    "da tôi", "da toi", "mặt tôi", "mat toi",
    "da mình", "da minh", "mặt mình", "mat minh",
    "tôi bị", "toi bi", "mình bị", "minh bi",
    "em bị", "em bi", "cháu bị", "chau bi",
    "của tôi", "cua toi", "của mình", "cua minh",
    "tình trạng tôi", "tinh trang toi",
    "tình trạng của tôi", "tinh trang cua toi",
    "tình trạng mình", "tinh trang minh",
)
_CASE_TERMS = (
    # Chỉ giữ các terms có chủ thể cá nhân rõ ràng (tôi/mình/em bị...)
    # KHÔNG dùng tên loại mụn đơn thuần vì chúng xuất hiện trong knowledge questions
    "tôi bị", "toi bi", "mình bị", "minh bi", "em bị", "em bi",
    "bị mụn", "bi mun", "nổi mụn", "noi mun",
    "mụn đau", "mun dau", "mụn sưng", "mun sung",
    "da mình", "da minh", "da tôi", "da toi", "da em",
    "mặt mình", "mat minh", "mặt tôi", "mat toi",
)
_ADVICE_QUESTION_TERMS = (
    "phải làm sao", "phai lam sao", "làm gì", "lam gi",
    "nên làm gì", "nen lam gi", "nên dùng gì", "nen dung gi",
    "dùng gì", "dung gi", "xử lý", "xu ly", "trị", "tri ",
)
_EMOTIONAL_TERMS = (
    "tự ti", "tu ti", "xấu hổ", "xau ho", "stress", "buồn", "buon",
    "chán", "chan", "mất tự tin", "mat tu tin", "hoảng", "hoang",
)
_CRISIS_TERMS = (
    "tự tử", "tu tu", "tự sát", "tu sat", "không muốn sống", "khong muon song",
)
_PROGRESS_TERMS = (
    "tuần rồi", "tuan roi", "tháng rồi", "thang roi", "vẫn lên", "van len",
    "không đỡ", "khong do", "đỡ hơn", "do hon", "rát hơn", "rat hon",
    "không hiệu quả", "khong hieu qua", "routine trước", "routine truoc",
)
_SAFETY_PRODUCT_TERMS = (
    "retinol", "retinoid", "tretinoin", "adapalene", "isotretinoin",
    "benzoyl peroxide", "bpo", "aha", "bha", "salicylic", "azelaic",
    "dùng chung", "dung chung", "kết hợp", "ket hop", "+",
)
_URGENCY_TERMS = (
    "đau nhiều", "dau nhieu", "sưng lớn", "sung lon", "mụn mủ", "mun mu",
    "rỉ dịch", "ri dich", "lan rộng", "lan rong", "sốt ", " sốt", " sot ",
    "sẹo", "seo", "nang lớn", "nang lon",
)
_MULTI_CONDITION_TERMS = (
    "rosacea", "eczema", "viêm da", "viem da", "kích ứng", "kich ung",
    "viêm quanh miệng", "viem quanh mieng", "dị ứng", "di ung",
)

_STOP_REPEAT_CHARS_RE = re.compile(r"\s+")


def normalize_for_repeat(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"[^\w\s%+]", " ", lowered, flags=re.UNICODE)
    return _STOP_REPEAT_CHARS_RE.sub(" ", lowered).strip()


def is_repeated_question(message: str, history: list[ConversationTurn], recent_user_turns: int = 6) -> bool:
    current = normalize_for_repeat(message)
    if not current:
        return False
    seen = 0
    for turn in reversed(history):
        if turn.role != "user":
            continue
        seen += 1
        if normalize_for_repeat(turn.content) == current:
            return True
        if seen >= recent_user_turns:
            break
    return False


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")


def _subject_signals(text: str) -> tuple[bool, bool]:
    lowered = text.lower()
    no_accent = _strip_accents(lowered)
    has_other = _contains_any(lowered, _OTHER_SUBJECT_TERMS) or _contains_any(
        no_accent,
        _OTHER_SUBJECT_TERMS,
    )
    has_self = _contains_any(lowered, _SELF_SUBJECT_TERMS) or _contains_any(
        no_accent,
        _SELF_SUBJECT_TERMS,
    )
    return has_other, has_self


def _query_subject_for_intent(
    primary_intent: PrimaryIntent,
    has_other_subject: bool,
    has_self_subject: bool,
) -> QuerySubject:
    if has_other_subject:
        return "other"
    if has_self_subject:
        return "self"
    if primary_intent == "advise":
        return "self"
    return "general"


def _clinical_has_case_signal(clinical: AcneClinicalInput | None) -> bool:
    if clinical is None:
        return False
    lesion_types = [x for x in clinical.lesion_types if x != "other"]
    meaningful_inflammation = (
        clinical.inflammation_level in {"moderate", "severe"}
        or (
            clinical.inflammation_level == "mild"
            and bool(lesion_types or clinical.lesion_distribution)
        )
    )
    return bool(
        lesion_types
        or clinical.lesion_distribution
        or meaningful_inflammation
        or clinical.scarring_signs
        or clinical.red_flags_input
    )


def _has_any_clinical_fact(user: UserInput) -> bool:
    clinical = user.clinical
    return bool(
        user.context.age is not None
        or user.context.sex
        or user.context.skin_type
        or user.context.current_products
        or user.context.medications
        or user.context.duration_weeks is not None
        or (clinical is not None and any((
            clinical.lesion_types,
            clinical.lesion_distribution,
            clinical.inflammation_level,
            clinical.medication_history,
            clinical.skincare_products,
            clinical.treatment_goals,
            clinical.red_flags_input,
        )))
    )


def _rule_decision(message: str, user: UserInput, history: list[ConversationTurn]) -> RouteDecision:
    lowered = message.lower()
    detected_language = detect_language_heuristic(message)
    has_other_subject, has_self_subject = _subject_signals(lowered)
    flags: list[str] = []

    def _decision(
        primary_intent: PrimaryIntent,
        confidence: float,
        **kwargs,
    ) -> RouteDecision:
        return RouteDecision(
            primary_intent=primary_intent,
            confidence=confidence,
            query_subject=_query_subject_for_intent(
                primary_intent,
                has_other_subject,
                has_self_subject,
            ),
            **kwargs,
        )

    if is_repeated_question(message, history):
        flags.append("repeated_question")
    if _contains_any(lowered, _EMOTIONAL_TERMS):
        flags.append("emotional_distress")
    if _contains_any(lowered, _CRISIS_TERMS):
        flags.append("crisis_signal")
    if _contains_any(lowered, _SAFETY_PRODUCT_TERMS):
        flags.append("product_safety_check")
    if _contains_any(lowered, _URGENCY_TERMS) or (user.clinical and user.clinical.red_flags_input):
        flags.append("urgency_red_flag")
    if _contains_any(lowered, _PROGRESS_TERMS):
        flags.append("progress_followup")
    if _contains_any(lowered, _MULTI_CONDITION_TERMS):
        flags.append("multi_condition")

    # I1: Detect follow-up turns in an active session.
    # Không giới hạn cứng 6 từ vì nhiều continuation hợp lệ dài hơn
    # ("vậy với da khô thì dùng gì", "thế còn buổi sáng thì sao").
    # Dùng 10 từ để lọc câu quá dài (câu mới thường > 10 từ khi có context đầy đủ).
    is_short_followup = (
        len(message.split()) <= 10
        and bool(history)
        and _contains_any(lowered, _FOLLOWUP_SHORT_TERMS)
    )
    if is_short_followup:
        flags.append("progress_followup")
        return _decision(
            primary_intent="advise",
            confidence=0.75,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="short_followup_in_session",
        )

    is_product_query = _contains_any(lowered, _PRODUCT_QUERY_TERMS)
    is_food_query = _contains_any(lowered, _FOOD_KNOWLEDGE_TERMS) and (
        _contains_any(lowered, _QUESTION_TERMS)
        or "?" in message
        or "không" in lowered
        or "khong" in lowered
    )
    is_mechanism_query = _contains_any(lowered, _QUESTION_TERMS) and any(
        term in lowered for term in ("vì sao", "vi sao", "tại sao", "tai sao", "là gì", "la gi", "hoạt động", "hoat dong")
    )
    # Knowledge ranking: "top 10 nguyên nhân...", "liệt kê...", "giải thích..."
    # → Đây luôn là knowledge question, kể cả khi có clinical terms trong câu.
    # Lý do: normalizer sẽ trích clinical terms từ câu hỏi chung (vd: "mụn bọc" → nodule)
    # nhưng user không đang mô tả case của họ.
    is_knowledge_ranking = _contains_any(lowered, _KNOWLEDGE_RANKING_TERMS)
    is_advice_question = _contains_any(lowered, _ADVICE_QUESTION_TERMS)
    has_case_terms = _contains_any(lowered, _CASE_TERMS)
    has_personal_terms = _contains_any(lowered, _PERSONAL_TERMS)
    # Bug fix: chỉ dùng clinical signals từ message hiện tại (base_user / turn_snapshot),
    # KHÔNG dùng user.clinical đã fold từ history.
    # Lý do: fold nhét dist=['chin'] từ turn 1 vào tất cả các turn sau → has_case_signal
    # luôn True → confidence luôn 0.82 dù message là câu hỏi kiến thức.
    # user._current_clinical là snapshot trước fold, nếu không có thì fallback = False.
    _current_clinical = getattr(user, "_current_clinical", None)
    if _current_clinical is None and not history:
        _current_clinical = user.clinical
    has_case_signal = _clinical_has_case_signal(_current_clinical)

    # Priority 1: Knowledge ranking/explanation questions — route knowledge
    # kể cả khi có case terms ("bị mụn", "nổi mụn") nếu không có personal pronoun rõ ràng.
    # Lý do: "top 5 lí do bị mụn" có "bị mụn" nhưng không có "tôi/mình/mặt tôi"
    # → đây là câu hỏi chung, không phải case cá nhân.
    # Chỉ override sang advise khi có personal pronoun ("tôi", "mình", "mặt tôi"...)
    if is_knowledge_ranking and not has_personal_terms:
        return _decision(
            primary_intent="knowledge",
            confidence=0.90,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="knowledge_ranking_or_explanation",
        )

    # Priority 2: Product/food/mechanism questions without a concrete personal case
    if (is_product_query or is_food_query or is_mechanism_query) and not (has_case_terms and has_case_signal):
        return _decision(
            primary_intent="knowledge",
            confidence=0.86,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="general_knowledge_or_product_query",
        )

    # Priority 2b: So sánh / đánh giá tổng quát không có personal pronoun rõ ràng.
    # Ví dụ: "da dầu có dễ bị mụn hơn da khô không", "có phải da dầu nhiều mụn hơn không"
    # → có "bị mụn" hoặc "mụn" nhưng không có "tôi/mình" → đây là câu hỏi kiến thức.
    _COMPARISON_MARKERS = ("hơn", "hon ", " hon", "so với", "so voi", "có phải", "co phai",
                           "có đúng", "co dung", "dễ bị", "de bi", "hay hơn", "hay hon")
    is_general_comparison = (
        _contains_any(lowered, _COMPARISON_MARKERS)
        and ("không" in lowered or "khong" in lowered or "?" in message)
        and not has_personal_terms
        and not has_case_signal
    )
    if is_general_comparison:
        return _decision(
            primary_intent="knowledge",
            confidence=0.84,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="general_comparison_question",
        )

    if "crisis_signal" in flags:
        return _decision(
            primary_intent="clarify",
            confidence=0.80,
            turn_type="safety_clarify",
            route_flags=flags,
            detected_language=detected_language,
            reason_code="crisis_signal",
        )

    # Route advise khi:
    # - có personal pronoun rõ ràng (tôi/mình/da tôi...), hoặc
    # - có case_signal từ current message (clinical facts trong tin nhắn này), hoặc
    # - có case_terms + advice question ("bị mụn nên dùng gì", "mụn đau phải làm sao")
    #   → implicit personal case, cần tư vấn cụ thể
    # KHÔNG route advise chỉ vì has_case_terms đơn thuần (bị mụn trong câu so sánh)
    _strong_personal_signal = has_personal_terms or has_case_signal
    _implicit_personal = has_case_terms and is_advice_question
    if _strong_personal_signal or _implicit_personal:
        if is_advice_question and not has_case_signal:
            flags.append("partial_advise")
        elif has_case_signal and (is_advice_question or len(message.split()) <= 8):
            flags.append("partial_advise")
        return _decision(
            primary_intent="advise",
            confidence=0.82 if has_case_signal else 0.70,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="personal_acne_case",
        )

    if _has_any_clinical_fact(user) and is_advice_question:
        flags.append("partial_advise")
        return _decision(
            primary_intent="advise",
            confidence=0.68,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="contextual_personal_advice",
            ambiguity_reason="history_or_context_facts_with_advice_question",
        )

    if _contains_any(lowered, _QUESTION_TERMS) or "?" in message:
        return _decision(
            primary_intent="knowledge",
            confidence=0.72,
            route_flags=flags,
            detected_language=detected_language,
            reason_code="question_without_case_signal",
        )

    # Fallback: chỉ dùng has_case_signal từ current message, không từ folded user.
    # _has_any_clinical_fact(user) sẽ luôn True sau fold → mọi thứ thành advise.
    return _decision(
        primary_intent="advise" if has_case_signal else "knowledge",
        confidence=0.58,
        route_flags=flags + ["ambiguous_intent"],
        detected_language=detected_language,
        reason_code="low_signal_default",
        ambiguity_reason="rule_confidence_low",
    )


def _accept_classifier(
    rule: RouteDecision,
    classifier_result: ClassifierResult,
    min_confidence: float,
    tie_margin: float,
) -> RouteDecision:
    scores = classifier_result.scores or {}
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ambiguous = classifier_result.is_ambiguous
    if len(ordered) >= 2 and ordered[0][1] - ordered[1][1] < tie_margin:
        ambiguous = True

    if classifier_result.confidence < min_confidence:
        out = rule
        out.classifier_used = True
        out.source = "hybrid"
        out.reason_code = f"{rule.reason_code}|classifier_low_confidence"
        return out

    if ambiguous:
        flags = list(dict.fromkeys([*rule.route_flags, "ambiguous_intent"]))
        return RouteDecision(
            primary_intent=rule.primary_intent,
            confidence=rule.confidence,
            query_subject=rule.query_subject,
            source="hybrid",
            classifier_used=True,
            turn_type=rule.turn_type,
            route_flags=flags,
            detected_language=rule.detected_language,
            reason_code=f"{rule.reason_code}|classifier_tie",
            ambiguity_reason=classifier_result.reason_code or "classifier_tie",
        )

    flags = list(rule.route_flags)
    return RouteDecision(
        primary_intent=classifier_result.primary_intent,
        confidence=classifier_result.confidence,
        query_subject=rule.query_subject,
        source="micro_model",
        classifier_used=True,
        turn_type="answer" if classifier_result.primary_intent in {"advise", "knowledge"} else classifier_result.primary_intent,
        route_flags=flags,
        detected_language=rule.detected_language,
        reason_code=classifier_result.reason_code or "classifier_override",
        ambiguity_reason=rule.ambiguity_reason,
    )


def route_intent(
    message: str,
    user: UserInput,
    history: list[ConversationTurn],
    settings: object | None = None,
    classifier: IntentClassifier | None = None,
) -> RouteDecision:
    import concurrent.futures

    rule = _rule_decision(message, user, history)
    min_confidence = float(getattr(settings, "intent_router_min_confidence", 0.80))
    tie_margin = float(getattr(settings, "intent_router_tie_margin", 0.10))
    enabled = bool(getattr(settings, "intent_router_enabled", False))
    # Timeout cho classifier call — default 15s (tăng từ 5s để tránh false timeout
    # khi main model đang warm-up trên GPU cùng lúc với micro-classifier).
    classifier_timeout = float(getattr(settings, "intent_router_timeout_seconds", 15.0))

    # Hard-rule cases: không cần classifier, rule đã chắc chắn.
    _hard_rule_cases = {
        "crisis_signal",
        "short_followup_in_session",
        "genital_scope_hard_reject",
        "scope_hard_reject",
        "complaint",
    }
    should_call_classifier = (
        enabled
        and classifier is not None
        and rule.reason_code not in _hard_rule_cases
    )
    if not should_call_classifier:
        return rule

    signals = {
        "previous_assistant_turn_type": next(
            (t.mode for t in reversed(history) if t.role == "assistant"),
            "",
        ),
        "last_primary_intent": next(
            ((t.metadata or {}).get("primary_intent") for t in reversed(history) if t.role == "user"),
            "",
        ),
        "previous_bot_asked_clarify": any(
            t.role == "assistant" and t.mode == "clarify" for t in history[-2:]
        ),
        "has_clinical_facts": _has_any_clinical_fact(user),
        "rule_primary_intent": rule.primary_intent,
        "rule_flags": list(rule.route_flags),
    }

    # Chạy classifier trong thread riêng với timeout cứng.
    # Nếu Ollama bị queue (GPU đang bận với main model), pipeline không bị block.
    # Rule result được dùng ngay; classifier chỉ enhance nếu trả về kịp.
    model_result: ClassifierResult | None = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(classifier.classify, message, signals)
            try:
                model_result = future.result(timeout=classifier_timeout)
            except concurrent.futures.TimeoutError:
                logger.debug(
                    "[intent_router] classifier timed out after {:.0f}s, using rule result",
                    classifier_timeout,
                )
                future.cancel()
    except Exception as exc:
        logger.debug(f"[intent_router] classifier failed, using rule result: {exc}")

    if model_result is None:
        rule.classifier_used = True
        rule.source = "hybrid"
        rule.reason_code = f"{rule.reason_code}|classifier_error"
        return rule

    return _accept_classifier(rule, model_result, min_confidence, tie_margin)


class OllamaIntentClassifier:
    """Tiny Ollama-backed JSON classifier.

    Constructed only when INTENT_ROUTER_ENABLED=true. The model name is config,
    not code policy.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 5.0,
        num_ctx: int = 1024,
        num_predict: int = 128,
    ) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def classify(self, message: str, signals: dict) -> ClassifierResult | None:
        system = (
            "Classify Vietnamese/English acne-chat user intent. "
            "Return ONLY strict JSON: {\"primary_intent\": <label>, \"scores\": {<label>: <0-1>}, "
            "\"confidence\": <0-1>, \"is_ambiguous\": <bool>, \"reason_code\": <string>}. "
            "Labels:\n"
            "  advise   = user is describing a personal skin/acne situation and wants specific advice "
            "(subject may be themselves OR someone else they mention explicitly)\n"
            "  knowledge = user is asking a general/factual question about acne, ingredients, or skincare — "
            "NOT about their own specific case\n"
            "  clarify  = message is too vague for the SYSTEM to give useful advice "
            "(e.g. just 'mụn' with no context); NOT a label for user asking a clarifying question\n"
            "  reject   = completely off-topic (not related to acne/skin)\n"
            "Rules: presence of 'tôi/mình/em bị' → advise. "
            "Ranking/list/why questions without personal pronoun → knowledge. "
            "Mixed-language (Vietnamese + English) follows the same rules.\n"
            "Examples:\n"
            "- \"mình bị mụn bọc ở cằm\" -> advise (personal self)\n"
            "- \"bạn tôi bị mụn nang, nên làm gì\" -> advise (personal other)\n"
            "- \"em gái mình hay nổi mụn ở lưng\" -> advise (personal other)\n"
            "- \"tại sao bị mụn bọc\" -> knowledge (general why, no personal pronoun)\n"
            "- \"top 10 nguyên nhân gây mụn\" -> knowledge (list/ranking)\n"
            "- \"da dầu có dễ bị mụn hơn da khô không\" -> knowledge (comparison)\n"
            "- \"mình nên dùng gì cho da mụn\" -> advise (personal advice request)\n"
            "- \"benzoyl peroxide là gì\" -> knowledge (ingredient)\n"
            "- \"mình bị mụn bọc đau, nên làm gì\" -> advise (personal + advice)\n"
            "- \"liệt kê các loại mụn\" -> knowledge (list)\n"
            "- \"my skin keeps breaking out on my chin\" -> advise (English personal)\n"
            "- \"what causes hormonal acne\" -> knowledge (English general)\n"
            "- \"I have oily skin and acne, what should I use\" -> advise (English personal advice)\n"
            "- \"mụn\" -> clarify (too vague, system cannot advise)\n"
            "- \"em bị mụn nhưng không biết loại gì\" -> advise (personal, type unknown — still advise not clarify)\n"
        )
        user_payload = json.dumps(
            {"message": message, "context": {
                "last_intent": signals.get("last_primary_intent", ""),
                "has_clinical_facts": signals.get("has_clinical_facts", False),
            }},
            ensure_ascii=False,
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_payload},
            ],
            "format": "json",
            "options": {
                "temperature": 0.0,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            "stream": False,
        }
        response = self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        content = (response.json().get("message") or {}).get("content") or ""
        data = json.loads(content)
        label = str(data.get("primary_intent") or "").strip()
        if label not in {"advise", "knowledge", "clarify", "reject"}:
            return None
        scores = {
            key: float(value)
            for key, value in (data.get("scores") or {}).items()
            if key in {"advise", "knowledge", "clarify", "reject"}
        }
        confidence = float(data.get("confidence", scores.get(label, 0.0)))
        return ClassifierResult(
            primary_intent=label,  # type: ignore[arg-type]
            scores=scores,
            confidence=max(0.0, min(1.0, confidence)),
            is_ambiguous=bool(data.get("is_ambiguous", False)),
            reason_code=str(data.get("reason_code") or "micro_model"),
        )

    def close(self) -> None:
        self._client.close()
