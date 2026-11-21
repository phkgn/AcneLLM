"""Deterministic routing: mot ham LUON chay + mot duong du phong.

Doc ky truoc khi xoa bat cu thu gi o day -- module nay co HAI vai, va cai ten
"fallback" cu (thu muc nay ten la chat/fallback truoc Phase 7) chi mo ta dung
mot trong hai:

1. ``compute_route_flags`` -- CHAY TREN 100% REQUEST, moi mode, moi router.
   ``UnifiedIntake.classify()`` va ``SemanticRouter`` deu tra ``RouteDecision``
   voi ``route_flags`` rong, nen intake.py:~570 goi ham nay de gan co cho MOI
   duong. Bo no di thi canh bao khan cap (``chat/_safety``) va guidance
   (``prompt_builder``) chet im lang. Day KHONG phai fallback.

2. ``route_intent`` / ``_rule_decision`` -- tier 3 that su: chi chay khi
   llm_router nem exception VA semantic_router cung khong dung duoc. Tuc la
   khi Ollama chet, dung luc tai cao nhat.

Hard guardrail nam ngoai module nay va chay doc lap voi moi router.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re
from typing import Literal

from ...llm.language import detect_language_heuristic
from ...schemas import AcneClinicalInput, UserInput
from ..session import ConversationTurn


PrimaryIntent = Literal["advise", "knowledge", "clarify", "reject"]
IntentSource = Literal["rule", "semantic", "llm"]


@dataclass
class RouteDecision:
    primary_intent: PrimaryIntent
    confidence: float
    source: IntentSource = "rule"
    turn_type: str = "answer"
    route_flags: list[str] = field(default_factory=list)
    detected_language: str = "unknown"
    reason_code: str = "rule_default"
    ambiguity_reason: str | None = None

    def metadata(self) -> dict:
        data = {
            "primary_intent": self.primary_intent,
            "intent_confidence": self.confidence,
            "intent_source": self.source,
            "turn_type": self.turn_type,
            "route_flags": list(self.route_flags),
            "detected_language": self.detected_language,
            "reason_code": self.reason_code,
        }
        if self.ambiguity_reason:
            data["ambiguity_reason"] = self.ambiguity_reason
        return data


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
    "phương pháp điều trị", "phuong phap dieu tri",
    "điều trị tại nhà", "dieu tri tai nha",
    "trị tại nhà", "tri tai nha",
    "kết hợp được không", "ket hop duoc khong",
    "dùng chung được không", "dung chung duoc khong",
)

# ---------------------------------------------------------------------------
# Question / knowledge-signal terms
# Dùng để nhận diện câu hỏi dạng "là gì / tại sao / cách / bao lâu…"
# Cả intent_router (_QUESTION_TERMS) lẫn intake (_KNOWLEDGE_QUESTION_TERMS)
# đều cần tập hợp này — giờ chỉ còn một chỗ duy nhất.
# ---------------------------------------------------------------------------
_QUESTION_TERMS: tuple[str, ...] = (
    # ── Câu hỏi trực tiếp ──────────────────────────────────────────────────
    "là gì", "la gi",
    "tại sao", "tai sao",
    "vì sao", "vi sao",
    "nguyên nhân", "nguyen nhan",
    "cách", "cach",
    "làm sao", "lam sao",
    "thế nào", "the nao",
    "như nào", "nhu nao",
    "có nên", "co nen",
    "hoạt động thế nào", "hoat dong the nao",
    "cơ chế", "co che",
    "tác dụng", "tac dung",
    "có sao không", "co sao khong",
    "có ảnh hưởng", "co anh huong",
    "có tốt không", "co tot khong",
    # ── Sản phẩm / thành phần ──────────────────────────────────────────────
    "nên dùng", "nen dung",
    "dùng gì", "dung gi",
    "sản phẩm nào", "san pham nao",
    "loại nào", "loai nao",
    "nên chọn", "nen chon",
    "có tốt không", "co tot khong",
    "hiệu quả không", "hieu qua khong",
    "có hiệu quả không", "co hieu qua khong",
    "có tác dụng không", "co tac dung khong",
    "có an toàn không", "co an toan khong",
    "có dùng được không", "co dung duoc khong",
    "review", "so sánh", "so sanh",
    "khác gì", "khac gi",
    "oil-free", "non-comedogenic",
    "không gây bít tắc", "khong gay bit tac",
    "mua ở đâu", "mua o dau",
    "giá bao nhiêu", "gia bao nhieu",
    # ── Thời gian / diễn biến ──────────────────────────────────────────────
    "bao lâu", "bao lau",
    "mấy tuần", "may tuan",
    "mấy tháng", "may thang",
    "bao nhiêu tuần", "bao nhieu tuan",
    "bao nhiêu tháng", "bao nhieu thang",
    "khi nào hết", "khi nao het",
    "khi nào khỏi", "khi nao khoi",
    # ── Lo ngại / đánh giá ─────────────────────────────────────────────────
    "có bình thường không", "co binh thuong khong",
    "có nguy hiểm không", "co nguy hiem khong",
    "có đáng lo không", "co dang lo khong",
    "có cần khám không", "co can kham khong",
    "có cần gặp bác sĩ không", "co can gap bac si khong",
    "có ảnh hưởng gì không", "co anh huong gi khong",
    "có cần lo không", "can lo khong",
    "có nặng không", "nặng không", "co nang khong", "nang khong",
    "có ổn không", "co on khong",
    # ── Điều trị ───────────────────────────────────────────────────────────
    "nên làm gì", "nen lam gi",
    "phải làm sao", "phai lam sao",
    "làm gì bây giờ", "lam gi bay gio",
    "xử lý thế nào", "xu ly the nao",
    "giải quyết thế nào", "giai quyet the nao",
    "điều trị thế nào", "dieu tri the nao",
    "cách trị", "cach tri",
    "cách chữa", "cach chua",
    "có tự khỏi không", "co tu khoi khong",
    "có tự hết không", "co tu het khong",
    "có cần điều trị không", "co can dieu tri khong",
    "cần làm gì", "can lam gi",
    "có phải đi khám không", "co phai di kham khong",
    "nên đi khám không", "nen di kham khong",
    "mụn có tự hết không", "mun co tu het khong",
    "có hết được không", "co het duoc khong",
    "có lan sang không", "co lan sang khong",
    "có lây không", "co lay khong",
    # ── Phân loại / định danh ──────────────────────────────────────────────
    "mụn này là gì", "mun nay la gi",
    "đây là mụn gì", "day la mun gi",
    "tình trạng này là gì", "tinh trang nay la gi",
    "loại da này", "loai da nay",
    "tại sao bị", "tai sao bi",
    "vì sao nổi", "vi sao noi",
    "nguyên nhân do đâu", "nguyen nhan do dau",
    "do đâu mà bị", "do dau ma bi",
    "nghe có vẻ nặng không", "nghe co ve nang khong",
)
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
    "ăn", "mì cay", "mi cay", "đồ cay", "do cay",
    "sữa", "sua", "đường", "duong", "whey", "cà phê", "ca phe",
    "nên ăn", "nen an", "kiêng", "kieng",
)
_FOOD_EAT_RE = re.compile(r"(?<!\w)(?:ăn|an)(?!\w)", flags=re.IGNORECASE)
_PERSONAL_TERMS = (
    # Chỉ dùng personal terms có chủ thể rõ ràng
    # KHÔNG dùng "em", "con" standalone vì trùng với từ thông thường ("em ơi", "con đường")
    "tôi", "toi", "mình", "minh",
    "da tôi", "da toi", "mặt tôi", "mat toi", "của tôi", "cua toi",
    "tình trạng tôi", "tinh trang toi",
    "tình trạng của tôi", "tinh trang cua toi",
    "tình trạng mình", "tinh trang minh",
    "đang bị", "dang bi", "tôi bị", "toi bi",
    "mình bị", "minh bi", "em bị", "em bi", "cháu bị", "chau bi",
    "con bị", "con bi", "tớ bị", "to bi", "tao bị", "tao bi",
    "da mình", "da minh", "mặt mình", "mat minh",
    "mặt em", "mat em", "da em",
    "mặt cháu", "mat chau", "da cháu", "da chau",
    "mặt con", "mat con", "da con",
    "mặt tớ", "mat to", "da tớ", "da to",
    "của em", "cua em", "của cháu", "cua chau", "của con", "cua con",
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
_URGENT_EVALUATION_TERMS = (
    "có nguy hiểm không", "co nguy hiem khong",
    "nguy hiểm không", "nguy hiem khong",
    "có đáng lo không", "co dang lo khong",
    "có cần khám không", "co can kham khong",
    "cần khám không", "can kham khong",
    "cần đi khám", "can di kham",
    "nên đi khám", "nen di kham",
    "giờ làm sao", "gio lam sao",
    "bây giờ làm sao", "bay gio lam sao",
)
_EMOTIONAL_TERMS = (
    "tự ti", "tu ti", "xấu hổ", "xau ho", "stress", "buồn", "buon",
    # Dùng cụm đầy đủ để tránh match nhầm chuỗi con:
    #   "chan" đụng "chẳng" (chang), "hoang" đụng "khoảng" (khoang).
    "chán nản", "chan nan", "mất tự tin", "mat tu tin",
    "hoảng loạn", "hoang loan", "hoang mang", "tuyệt vọng", "tuyet vong",
)
_CRISIS_TERMS = (
    # ponytail: bo "tu tu" (khong dau) o Phase 7. No la "tu tu" cua "tự tử"
    # NHUNG cung la "từ từ" viet khong dau -> "tu tu thoi ban" chen nguyen doan
    # an ui khung hoang vao dau cau tra loi ve mun. Cac term con lai khong nhap
    # nhang. Co GIU nguyen co che prefix cung o runtime.py: khung hoang tam ly
    # dung la loai viec khong duoc ha xuong thanh goi y trong prompt.
    "tự tử", "tự sát", "tu sat", "không muốn sống", "khong muon song",
)
_PROGRESS_TERMS = (
    "tuần rồi", "tuan roi", "tháng rồi", "thang roi", "vẫn lên", "van len",
    "không đỡ", "khong do", "đỡ hơn", "do hon", "rát hơn", "rat hon",
    "không hiệu quả", "khong hieu qua", "routine trước", "routine truoc",
)
_URGENCY_TERMS = (
    "đau nhiều", "dau nhieu", "sưng lớn", "sung lon", "mụn mủ", "mun mu",
    "rỉ dịch", "ri dich", "lan rộng", "lan rong", "sốt ", " sốt", " sot ",
    "sẹo", "seo", "nang lớn", "nang lon",
)
_URGENT_CLINICAL_FLAGS = frozenset({
    "infection_signs",
    "widespread",
    "painful_lesions",
    "purulent_lesions",
    "treatment_failure",
})
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


@lru_cache(maxsize=128)
def _terms_regex(terms: tuple[str, ...]) -> re.Pattern[str] | None:
    cleaned = tuple(dict.fromkeys(t.strip().lower() for t in terms if t and t.strip()))
    if not cleaned:
        return None
    pattern = "|".join(re.escape(term) for term in sorted(cleaned, key=len, reverse=True))
    return re.compile(pattern, flags=re.IGNORECASE)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """Fast shared substring matcher for static chat term lists."""
    regex = _terms_regex(tuple(terms))
    return bool(regex and regex.search(text.lower()))


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


def compute_route_flags(
    message: str,
    user: UserInput | None = None,
    history: list[ConversationTurn] | None = None,
) -> list[str]:
    """Cờ tín hiệu văn bản, độc lập với việc router nào chọn intent.

    ``UnifiedIntake.classify()`` và semantic router trả ``RouteDecision`` không
    có ``route_flags``, nên mọi guardrail phụ thuộc cờ (cảnh báo khẩn cấp ở
    ``_safety``, guidance ở ``prompt_builder``) chết im lặng khi chạy hai đường
    đó. Hàm này để ``intake`` gắn cùng bộ cờ cho MỌI đường router.

    Chỉ dùng khớp mẫu trên text + clinical đã có. Không gọi model.
    """
    lowered = message.lower()
    flags: list[str] = []
    if history is not None and is_repeated_question(message, history):
        flags.append("repeated_question")
    if _contains_any(lowered, _EMOTIONAL_TERMS):
        flags.append("emotional_distress")
    if _contains_any(lowered, _CRISIS_TERMS):
        flags.append("crisis_signal")
    has_red_flags = bool(user is not None and user.clinical and user.clinical.red_flags_input)
    if _contains_any(lowered, _URGENCY_TERMS) or has_red_flags:
        flags.append("urgency_red_flag")
    if _contains_any(lowered, _PROGRESS_TERMS):
        flags.append("progress_followup")
    if _contains_any(lowered, _MULTI_CONDITION_TERMS):
        flags.append("multi_condition")
    return flags


def _rule_decision(
    message: str,
    user: UserInput,
    history: list[ConversationTurn],
    current_clinical: AcneClinicalInput | None = None,
) -> RouteDecision:
    lowered = message.lower()
    detected_language = detect_language_heuristic(message)
    flags: list[str] = compute_route_flags(message, user, history)

    def _decision(
        primary_intent: PrimaryIntent,
        confidence: float,
        **kwargs,
    ) -> RouteDecision:
        return RouteDecision(
            primary_intent=primary_intent,
            confidence=confidence,
            **kwargs,
        )

    # I1: Detect follow-up turns in an active session.
    # Không giới hạn cứng 6 từ vì nhiều continuation hợp lệ dài hơn
    # ("vậy với da khô thì dùng gì", "thế còn buổi sáng thì sao").
    # Dùng 10 từ để lọc câu quá dài (câu mới thường > 10 từ khi có context đầy đủ).
    has_use_safety_followup = (
        bool(history)
        and len(message.split()) <= 10
        and _contains_any(lowered, ("được không", "duoc khong", "an toàn không", "an toan khong"))
        and _contains_any(
            lowered,
            ("dùng", "dung", "bôi", "boi", "thoa", "uống", "uong", "ăn", "an "),
        )
    )
    is_short_followup = (
        len(message.split()) <= 10
        and bool(history)
        and (_contains_any(lowered, _FOLLOWUP_SHORT_TERMS) or has_use_safety_followup)
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
    is_food_query = (
        not _contains_any(lowered, ("mụn sữa", "mun sua"))
        and (
            _contains_any(lowered, _FOOD_KNOWLEDGE_TERMS)
            or _FOOD_EAT_RE.search(lowered) is not None
        )
    ) and (
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
    is_urgent_evaluation_question = _contains_any(lowered, _URGENT_EVALUATION_TERMS)
    has_case_terms = _contains_any(lowered, _CASE_TERMS)
    has_personal_terms = _contains_any(lowered, _PERSONAL_TERMS)
    _implicit_personal = has_case_terms and is_advice_question
    # Bug fix: chỉ dùng clinical signals từ message hiện tại (base_user / turn_snapshot),
    # KHÔNG dùng user.clinical đã fold từ history.
    # Lý do: fold nhét dist=['chin'] từ turn 1 vào tất cả các turn sau → has_case_signal
    # luôn True → confidence luôn 0.82 dù message là câu hỏi kiến thức.
    # current_clinical là snapshot trước fold. getattr fallback giữ compat cho caller cũ.
    _current_clinical = current_clinical if current_clinical is not None else getattr(user, "_current_clinical", None)
    if _current_clinical is None and not history:
        _current_clinical = user.clinical
    has_case_signal = _clinical_has_case_signal(_current_clinical)
    current_red_flags = set(_current_clinical.red_flags_input) if _current_clinical else set()
    has_urgent_medical_signal = (
        "urgency_red_flag" in flags
        and bool(current_red_flags & _URGENT_CLINICAL_FLAGS)
    )

    if has_urgent_medical_signal and (
        has_personal_terms
        or _implicit_personal
        or is_advice_question
        or is_urgent_evaluation_question
        or bool(history)
    ):
        urgent_flags = list(dict.fromkeys([*flags, "urgent_personal_case"]))
        return _decision(
            primary_intent="advise",
            confidence=0.92,
            route_flags=urgent_flags,
            detected_language=detected_language,
            reason_code="urgent_personal_case",
        )

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
    _COMPARISON_MARKERS = (
        "hơn", "hon ", " hon", "so với", "so voi", "có phải", "co phai",
        "có đúng", "co dung", "dễ bị", "de bi", "hay hơn", "hay hon",
        "khác với", "khac voi", "khác nhau", "khac nhau", "khác gì", "khac gi",
        "phân biệt", "phan biet", "so sánh", "so sanh",
        "khác ", "khac ", "như thế nào", "nhu the nao",
    )
    is_general_comparison = (
        _contains_any(lowered, _COMPARISON_MARKERS)
        and not has_personal_terms
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


def route_intent(
    message: str,
    user: UserInput,
    history: list[ConversationTurn],
    settings: object | None = None,
    classifier: object | None = None,
    current_clinical: AcneClinicalInput | None = None,
) -> RouteDecision:
    """Legacy rule-based intent routing used on semantic-router failure.

    Toàn bộ quyết định routing dùng luật cứng trong ``_rule_decision``.
    Tham số ``classifier`` được giữ lại cho tương thích ngược (caller cũ truyền
    ``classifier=...``) nhưng KHÔNG còn được dùng — micro-classifier đã gỡ bỏ.
    """
    decision = _rule_decision(message, user, history, current_clinical=current_clinical)

    # Luat degrade an toan: routing duoi nguong tin cay -> clarify thay vi doan.
    # Chi ap cho advise/knowledge (reject/clarify giu nguyen). Khong goi LLM.
    try:
        from ...config import Settings as _S
        _route_min = _S().route_min_confidence
    except Exception:
        _route_min = 0.55
    if (
        decision.primary_intent in ("advise", "knowledge")
        and decision.confidence < _route_min
    ):
        flags = list(getattr(decision, "route_flags", []) or [])
        if "low_route_confidence" not in flags:
            flags.append("low_route_confidence")
        return RouteDecision(
            primary_intent="clarify",
            confidence=decision.confidence,
            route_flags=flags,
            detected_language=getattr(decision, "detected_language", "vi"),
            reason_code="route_confidence_below_threshold",
        )
    return decision
