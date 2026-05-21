"""Unified pre-LLM intake for chat entrypoints.

This module owns the deterministic steps before generation:
preprocess -> normalize -> fold session facts -> guardrails/scope ->
completeness -> clinical plan -> effective mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from loguru import logger
from ..guardrails.runner import GuardrailRunner
from ..schemas import AcneClinicalInput, AdviseOutput, UserInput
from ..schemas.clinical import ClinicalQueryPlan
from .completeness import CompletenessResult, check_completeness
from .intent_router import RouteDecision, route_intent
from .normalizer import normalize_chat_message
from .preprocess import preprocess_user_text
from .session import (
    ConversationTurn,
    NormalizedSnapshot,
    fold_history_facts,
    get_session_store,
    snapshot_from_user,
)

if TYPE_CHECKING:
    from ..di import Container


ScopeDecision = Literal["in_scope", "refuse_hard", "pass_to_llm_soft"]
EffectiveMode = Literal["hybrid", "llm_only", "refuse", "clarify"]


_COMPLAINT_TERMS = (
    # Chê câu trả lời — không dấu
    "may tuoi", "tu van vay", "tu van the",
    "tra loi vay", "tra loi the",
    "khong hieu", "hoi lai", "hoi roi",
    "noi roi", "biet roi", "hoi hoai", "lap lai",
    "tu van kieu gi", "cau tra loi vo nghia",
    "khong giup duoc gi", "toan hoi lai",
    "vo ich", "khong dung", "tra loi sai",
    "te qua", "chan qua", "hieu gi dau",
    "tra loi linh tinh", "khong chinh xac",
    "bot vo dung", "bot do", "tra loi lan",
    "khong ro rang", "kho hieu", "khong thuc te",
    "co biet gi dau", "biet gi ma tu van",
    "tra loi cu", "tra loi nhu nhau",
    "vong vo", "dai dong", "khong truong hop",
    # unicode
    "mấy tuổi",
    "tư vấn vậy", "tư vấn thế",
    "trả lời vậy", "trả lời thế",
    "không hiểu", "hỏi lại", "hỏi rồi",
    "nói rồi", "biết rồi", "hỏi hoài", "lặp lại",
    "tư vấn kiểu gì", "câu trả lời vô nghĩa",
    "không giúp được gì", "toàn hỏi lại",
    "vô ích", "không đúng", "trả lời sai",
    "tệ quá", "chán quá", "hiểu gì đâu",
    "trả lời linh tinh", "không chính xác",
    "bot vô dụng", "bot dở", "trả lời lan",
    "không rõ ràng", "khó hiểu", "không thực tế",
    "có biết gì đâu", "biết gì mà tư vấn",
    "trả lời cũ", "trả lời như nhau",
    "vòng vo", "dài dòng", "không đúng trường hợp",
    "hỏi mãi", "hỏi nhiều quá", "tại sao hỏi nhiều",
    "hỏi lắm vậy", "hỏi hoài không tư vấn",
    "sao cứ hỏi", "chỉ hỏi không trả lời",
)

_KNOWLEDGE_QUESTION_TERMS = (
    # Dạng câu hỏi trực tiếp — KHÔNG dùng "?" vì quá broad (followup cũng có dấu hỏi)
    "la gi", "tai sao", "vi sao",
    "nguyen nhan", "cach", "lam sao",
    "the nao", "nhu nao", "co nen",
    "nen dung", "dung gi", "san pham nao",
    "loai nao", "bao nhieu tuoi",
    "non-comedogenic", "oil-free",
    # Đánh giá / so sánh sản phẩm
    "co tot khong", "hieu qua khong", "tot khong",
    "review", "so sanh", "khac gi", "nen chon",
    "co an toan khong", "co dung duoc khong",
    "mua o dau", "gia bao nhieu", "bao nhieu tien",
    # Thời gian điều trị
    "bao lau", "may tuan", "may thang",
    "bao nhieu tuan", "bao nhieu thang",
    "khi nao het", "khi nao khoi",
    # Câu hỏi đánh giá / lo ngại — không dấu
    "co binh thuong khong", "co nguy hiem khong",
    "co sao khong", "co dang lo khong",
    "co can kham khong", "co can gap bac si khong",
    "co anh huong gi khong", "co kham khong",
    "mun loai nay co sao khong", "loai mun nay",
    "nen lam gi", "phai lam sao", "lam gi bay gio",
    "xu ly the nao", "giai quyet the nao",
    "dieu tri the nao", "cach tri", "cach chua",
    "co tu khoi khong", "co tu het khong",
    "co can dieu tri khong", "can lam gi",
    "co phai di kham khong", "nen di kham khong",
    "mun co tu het khong", "co het duoc khong",
    "co lan sang khong", "co lay khong",
    "nguyen nhan do dau", "do dau ma bi",
    # unicode
    "là gì", "tại sao", "vì sao",
    "nguyên nhân", "cách", "làm sao",
    "thế nào", "như nào", "có nên",
    "nên dùng", "dùng gì", "sản phẩm nào",
    "loại nào", "bao nhiêu tuổi",
    "không gây bít tắc",
    "có tốt không", "hiệu quả không", "tốt không",
    "so sánh", "khác gì", "nên chọn",
    "có an toàn không", "có dùng được không",
    "mua ở đâu", "giá bao nhiêu",
    "bao lâu", "mấy tuần", "mấy tháng",
    "khi nào hết", "khi nào khỏi",
    "nên dùng gì", "dùng cái gì",
    "có hiệu quả không", "có tác dụng không",
    # Câu hỏi đánh giá / lo ngại — có dấu
    "có bình thường không", "có nguy hiểm không",
    "có sao không", "có đáng lo không",
    "có cần khám không", "có cần gặp bác sĩ không",
    "có ảnh hưởng gì không", "có khám không",
    "mụn loại này có sao không", "loại mụn này",
    "nên làm gì", "phải làm sao", "làm gì bây giờ",
    "xử lý thế nào", "giải quyết thế nào",
    "điều trị thế nào", "cách trị", "cách chữa",
    "có tự khỏi không", "có tự hết không",
    "có cần điều trị không", "cần làm gì",
    "có phải đi khám không", "nên đi khám không",
    "mụn có tự hết không", "có hết được không",
    "có lan sang không", "có lây không",
    "nguyên nhân do đâu", "do đâu mà bị",
    "tại sao bị", "vì sao nổi",
    "mụn này là gì", "đây là mụn gì",
    "tình trạng này là gì", "loại da này",
    "có ổn không", "có nặng không", "nặng không",
    "nghe có vẻ nặng không", "tình trạng tôi",
    "tình trạng của tôi", "tình trạng mình",
    "có cần lo không", "cần lo không",
)

_CASE_INTAKE_TERMS = (
    # ── Chủ ngữ + bị/nổi ──────────────────────────────────────────────────────
    "toi bi", "minh bi", "em bi", "ban than bi", "chau bi", "con bi",
    "minh dang bi", "toi dang bi", "em dang bi",
    "bi mun", "mun o", "noi mun", "noi o",
    "mun xuat hien", "mun moi noi",
    # ── Loại tổn thương — không dấu ───────────────────────────────────────────
    "co sung", "sung do", "dau den", "dau trang",
    "mun boc", "mun viem", "mun mu", "mun nan", "mun nang",
    "mun dau den", "mun dau trang", "mun li ti",
    "hat li ti", "hat nho", "mun kho", "mun an",
    "mun sam", "mun cam", "mun than",
    # ── Vị trí + chủ sở hữu — không dấu ──────────────────────────────────────
    "da toi", "mat toi", "lung toi", "co toi", "nguoi toi",
    "da minh", "mat minh", "lung minh",
    "mat em", "lung em", "cam em", "tran em",
    "tren mat", "o mat", "o lung", "o co", "o vai",
    "o tran", "o cam", "o ma", "o mui", "o hang",
    # ── Thời gian / diễn biến — không dấu ────────────────────────────────────
    "hay bi", "thuong bi", "gan day", "dao nay", "tuan nay",
    "hom nay noi", "moi noi", "tu nhien noi", "tu nhien bi",
    "noi nhieu", "bi nhieu", "bi nang", "bi lau",
    "khong het", "mai khong het", "khong khoi",
    "keo dai", "lau roi", "bao lau roi",
    "ngay cang nhieu", "ngay cang nang",
    "lan ra", "lan xuong", "lan sang",
    # ── Diễn biến đặc biệt ────────────────────────────────────────────────────
    "bot o mat lai noi o", "giam o mat nhung",
    "het tren mat roi noi", "chuyen xuong",

    # ── Unicode ───────────────────────────────────────────────────────────────
    "tôi bị", "mình bị", "em bị", "bản thân bị", "cháu bị", "con bị",
    "mình đang bị", "tôi đang bị", "em đang bị",
    "bị mụn", "mụn ở", "nổi mụn", "nổi ở",
    "mụn xuất hiện", "mụn mới nổi",
    "có sưng", "sưng đỏ", "đầu đen", "đầu trắng",
    "mụn bọc", "mụn viêm", "mụn mủ", "mụn nang",
    "mụn đầu đen", "mụn đầu trắng", "mụn li ti",
    "hạt li ti", "hạt nhỏ", "mụn khô", "mụn ẩn",
    "mụn cám", "mụn thâm",
    "da tôi", "mặt tôi", "lưng tôi", "cổ tôi", "người tôi",
    "da mình", "mặt mình", "lưng mình",
    "mặt em", "lưng em", "cằm em", "trán em",
    "trên mặt", "ở mặt", "ở lưng", "ở cổ", "ở vai",
    "ở trán", "ở cằm", "ở má", "ở mũi",
    "hay bị", "thường bị", "gần đây", "dạo này", "tuần này",
    "hôm nay nổi", "mới nổi", "tự nhiên nổi", "tự nhiên bị",
    "nổi nhiều", "bị nhiều", "bị nặng", "bị lâu",
    "không hết", "mãi không hết", "không khỏi",
    "kéo dài", "lâu rồi", "bao lâu rồi",
    "ngày càng nhiều", "ngày càng nặng",
    "lan ra", "lan xuống", "lan sang",
    "bớt ở mặt lại nổi ở", "giảm ở mặt nhưng",
    "hết trên mặt rồi nổi", "chuyển xuống",
    "mụn lan", "lan từ", "từ mặt xuống",
)


@dataclass
class IntakeResult:
    raw_message: str
    clean_text: str
    user: UserInput
    turn_snapshot: NormalizedSnapshot
    history: list[ConversationTurn]
    effective_mode: EffectiveMode
    scope_decision: ScopeDecision
    scope_refusal: AdviseOutput | None = None
    completeness: CompletenessResult | None = None
    clinical_plan: ClinicalQueryPlan | None = None
    route_decision: RouteDecision | None = None
    session_id: str | None = None

    @property
    def is_acne_signal(self) -> bool:
        return self.scope_decision == "in_scope"


def _is_acne_scope(message: str) -> bool:
    return GuardrailRunner.is_acne_scope_text(message)


def _is_genital_scope(message: str) -> bool:
    return GuardrailRunner.is_genital_scope(message)


def _is_knowledge_question(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in _KNOWLEDGE_QUESTION_TERMS)


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

    if any(term in lowered for term in _CASE_INTAKE_TERMS):
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
    """True neu tin nhan la complaint / negative feedback ve cau tra loi truoc."""
    if len(message.split()) > 12:
        return False
    lowered = message.lower()
    return any(term in lowered for term in _COMPLAINT_TERMS)


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
    sid_short = (session_id or "no-session")[:8]
    logger.info("[{}] ① INPUT ({}c): {!r}", sid_short, len(message), message[:120])

    raw_message = message
    clean_text = preprocess_user_text(raw_message)
    # Dùng container session store (SQLite/JSONL) — không dùng in-memory singleton
    # để đảm bảo intake và runtime đọc/ghi cùng một store (history không bị mất sau restart).
    store = getattr(c, "session_store", None) or get_session_store()
    history = store.get_history(session_id)
    mode = _resolve_mode(mode_request, c, clean_text=clean_text, history=history)
    base_user = normalize_chat_message(raw_message, mode=mode, clean_text=clean_text)
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

    # Lưu clinical snapshot trước khi fold — intent_router dùng để tránh
    # session carry-over làm has_case_signal luôn True.
    import copy as _copy
    base_user._current_clinical = _copy.copy(base_user.clinical)
    user = fold_history_facts(base_user, history)
    # S2-B: sync merged context ngược vào session store để các component khác
    # (metrics, audit) có thể query user_context mà không cần fold lại.
    if session_id:
        ctx_dict = {
            k: v for k, v in user.context.model_dump(exclude_none=True).items()
            if v is not None
        }
        if ctx_dict:
            store.merge_user_context(session_id, ctx_dict)
    _folded_cl = user.clinical
    logger.info(
        "[{}] ③ SESSION FOLD: history={} turns, asked={} | after_fold → age={} lesions={} dist={} inflam={}",
        sid_short,
        len(history),
        store.get_asked_fields(session_id),
        user.context.age,
        (_folded_cl.lesion_types if _folded_cl else []),
        (_folded_cl.lesion_distribution if _folded_cl else []),
        (_folded_cl.inflammation_level if _folded_cl else None),
    )

    c.guardrails.pre_check(user)

    # Genital / out-of-scope body region check — phải làm trước OOD để tránh
    # embedding similarity cao do "vùng da" khớp với acne centroid.
    if _is_genital_scope(clean_text):
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
            mode=user.mode,
            model_name="",
            latency_ms=0,
        )
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=user,
            turn_snapshot=turn_snapshot,
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
        )

    # Compute has_acne_history once — reused by scope_check and OOD downgrade below.
    has_acne_history = any(
        GuardrailRunner.is_acne_scope_text(t.content)
        for t in history
        if t.role == "user"
    )
    scope_refusal = (
        c.guardrails.scope_check(user, has_acne_history=has_acne_history)
        if hasattr(c.guardrails, "scope_check")
        else None
    )
    acne_signal = _is_acne_scope(clean_text)
    logger.info(
        "[{}] ④ GUARDRAILS: acne_signal={} genital=False refused={} scope={}",
        sid_short,
        acne_signal,
        scope_refusal is not None,
        "in_scope" if acne_signal else "pass_to_llm_soft",
    )

    if scope_refusal is not None:
        logger.info("[{}] → REFUSE (out-of-scope)", sid_short)
        return IntakeResult(
            raw_message=raw_message,
            clean_text=clean_text,
            user=user,
            turn_snapshot=turn_snapshot,
            history=history,
            effective_mode="refuse",
            scope_decision="refuse_hard",
            scope_refusal=scope_refusal,
            route_decision=RouteDecision(
                primary_intent="reject",
                confidence=1.0,
                turn_type="reject",
                route_flags=["out_of_scope"],
                reason_code="scope_hard_reject",
            ),
            session_id=session_id,
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
            user=user,
            turn_snapshot=turn_snapshot,
            history=history,
            effective_mode="clarify",
            scope_decision=scope_decision,
            route_decision=RouteDecision(
                primary_intent="clarify",
                confidence=0.95,
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
        )

    route_decision = route_intent(
        clean_text,
        user,
        history,
        settings=getattr(c, "settings", None),
        classifier=getattr(c, "intent_classifier", None),
    )
    logger.info(
        "[{}] ⑤ ROUTE: intent={} conf={:.2f} flags={} source={} reason={}",
        sid_short,
        route_decision.primary_intent,
        route_decision.confidence,
        route_decision.route_flags,
        route_decision.source,
        route_decision.reason_code,
    )

    # Lay asked_fields tu session de completeness checker khong hoi lai
    asked_fields = store.get_asked_fields(session_id)
    completeness = (
        check_completeness(user, history=history, asked_fields=asked_fields)
        if _should_check_completeness(clean_text, user, history, route_decision)
        else None
    )
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
    use_planner = getattr(getattr(c, "settings", None), "chat_use_llm_planner", True)
    _intent_is_knowledge = (
        route_decision is not None and route_decision.primary_intent == "knowledge"
    )
    clinical_plan = (
        planner.plan(user)
        if planner is not None and acne_signal and use_planner and not _intent_is_knowledge
        else None
    )
    logger.info(
        "[{}] ⑦ CLINICAL PLAN: built={} missing={} lang={} query={!r:.80}",
        sid_short,
        clinical_plan is not None,
        clinical_plan.missing_info if clinical_plan else [],
        clinical_plan.detected_language if clinical_plan else "n/a",
        (clinical_plan.rag_queries.query_vi if clinical_plan else ""),
    )
    logger.info("[{}] → {} (scope={} plan={})", sid_short, mode.upper(), scope_decision, clinical_plan is not None)
    return IntakeResult(
        raw_message=raw_message,
        clean_text=clean_text,
        user=user,
        turn_snapshot=turn_snapshot,
        history=history,
        effective_mode=mode,
        scope_decision=scope_decision,
        completeness=completeness,
        clinical_plan=clinical_plan,
        route_decision=route_decision,
        session_id=session_id,
    )
