"""Chon va render phan hoi thoai duoc dua vao prompt.

Ba ham nay khong phai "session" theo bat ky nghia nao -- chung tra loi cau hoi
"luot nao, dinh dang gi thi di vao prompt". Chung o chung file voi SessionStore
va fold_history_facts suot 714 dong chi vi lich su, va do la ly do ten file cu
noi doi ro nhat: `format_history_block` render chuoi cho prompt builder.

Tach o Phase 7. Doi vi ly do khac han hai file kia: file nay doi khi PROMPT
doi, memory.py doi khi vong doi phien doi, fold.py doi khi luat gop du kien doi.

Phu thuoc mot chieu: view -> fold (build_confirmed_profile dung _mentions_stop)
va view -> models. Khong co chieu nguoc lai.
"""
from __future__ import annotations

from ...schemas import UserInput
from .fold import _mentions_stop
from .models import HISTORY_CHAR_BUDGET, HISTORY_WINDOW_TURNS, ConversationTurn


def select_relevant_history(
    message: str,
    primary_intent: str,
    history: list[ConversationTurn],
    route_flags: list[str] | None = None,
) -> list[ConversationTurn]:
    """Return a recent window of in-scope turns for the answer prompt.

    Không đoán "đây có phải follow-up không" bằng whitelist tiền tố nữa: mọi
    câu trần thuật ("đã thử X rồi vẫn không đỡ") đều trượt whitelist và làm
    prompt mất sạch ngữ cảnh. format_history_block() đã cắt theo
    HISTORY_CHAR_BUDGET nên gửi cả cửa sổ là an toàn.
    """
    del message, route_flags
    window = history[-HISTORY_WINDOW_TURNS:]
    if primary_intent == "knowledge":
        # Knowledge trả lời từ RAG: giữ prose cũ của bot ra ngoài prompt, và chỉ
        # lấy user turn gần nhất để giải đại từ ("loại này") mà không kéo cả
        # case cá nhân vào retrieval query.
        # ponytail: turn cá nhân tự đứng được vẫn lọt vào query, làm loãng match.
        # Cần intaker phát tín hiệu "referential" thay vì đoán bằng keyword.
        previous_user = next(
            (turn for turn in reversed(window) if turn.role == "user"), None
        )
        return [previous_user] if previous_user is not None else []
    return window


# ── Ngưỡng confidence theo nhóm trường ───────────────────────────────────────
#
# Neo theo dải mà system prompt của intaker tự định nghĩa:
#     0.9–1.0 khi nêu rõ | 0.6–0.85 khi suy luận hợp lý | 0.3–0.55 khi mơ hồ
# Đổi hướng dẫn confidence lúc train lại intaker thì đổi hằng số này theo dải mới.
#
# Con số được chọn theo HƯỚNG HỎNG, không theo mức quan trọng của trường:
#
#   Thai kỳ / cho con bú — KHÔNG gác. Cổng thuốc chỉ nổ khi giá trị là True, nên
#   bỏ sót một ca mang thai thật là hướng hỏng nguy hiểm (khuyên retinoid cho
#   thai phụ), còn nhận nhầm chỉ gây chặn oan. Ngưỡng cao đẩy hệ về phía nguy
#   hiểm, nên bỏ ngưỡng. Lỗi quy chủ ngữ ("chị tôi mang thai") không phải việc
#   của ngưỡng — model tốt trả null ở đó, ngưỡng không cứu được.
#
#   Còn lại — 0.6, mép dưới dải "suy luận hợp lý". Đây là ngữ cảnh; nhớ nhiều
#   hơn thì câu trả lời sát hơn, đoán sai thì hơi lệch chứ không hại ai.
#
# Ngưỡng cũ 0.82 nằm giữa dải "suy luận": dữ kiện model đoán ở 0.84 thì lọt, 0.80
# thì rớt — một ranh giới không mang ý nghĩa gì, tàn dư của thang điểm rule cũ.
CONTEXT_FIELD_THRESHOLD: float = 0.60
_UNGATED_FIELDS = frozenset({"is_pregnant", "is_breastfeeding"})


def build_confirmed_profile(
    existing: dict,
    extraction_confidence: object | None,
    clean_text: str,
    threshold: float = CONTEXT_FIELD_THRESHOLD,
) -> dict:
    """Apply explicit, stable facts to the confirmed profile.

    Clinical descriptors intentionally never enter this structure. Latest
    explicit scalar wins; explicit stop phrases remove products/medications.
    """
    profile = dict(existing or {})
    if extraction_confidence is None:
        return profile

    for field_name in ("age", "sex", "is_pregnant", "is_breastfeeding"):
        result = getattr(extraction_confidence, field_name, None)
        if result is not None and getattr(result, "value", None) is not None:
            field_threshold = 0.0 if field_name in _UNGATED_FIELDS else threshold
            if float(getattr(result, "confidence", 0.0)) >= field_threshold:
                profile[field_name] = result.value

    for result_name, profile_name in (
        ("allergies", "allergies"),
        ("products", "current_products"),
        ("medications", "medications"),
    ):
        result = getattr(extraction_confidence, result_name, None)
        current = list(profile.get(profile_name) or [])
        current = [value for value in current if not _mentions_stop(clean_text, str(value))]
        confident = (
            result.confident_values(threshold)
            if result is not None and hasattr(result, "confident_values")
            else []
        )
        for value in confident:
            if not _mentions_stop(clean_text, str(value)) and value not in current:
                current.append(value)
        profile[profile_name] = current
    return profile

# ── Prompt helpers ────────────────────────────────────────────────────────────

def format_history_block(
    turns: list[ConversationTurn],
    char_budget: int = HISTORY_CHAR_BUDGET,
    max_turns: int | None = None,
) -> str:
    """Render only recent selected turns as a compact prompt block.

    Lọc các turn genital/out-of-scope trước khi inject vào prompt để tránh
    session history poisoning (LLM mention "bìu" trong câu hỏi acne tiếp theo).

    Ưu tiên anchor turn đầu tiên của user (tin nhắn gốc mô tả tình trạng):
    - Phần budget còn lại dùng cho các turns gần nhất (newest-first).

    Returns empty string when turns is empty (caller should skip the section).
    """
    if not turns:
        return ""

    # Lọc bỏ các turn (và turn assistant ngay sau) có nội dung genital
    # ponytail: loc turn genital khoi history da bo o Phase 7. No la ban sao
    # thu hai cua bang term o runner.py (va da lech nhau: runner co "truc trang",
    # "am vat"; ban nay khong). Cong genital gio o system prompt, nen loc history
    # chi con cat mach hoi thoai ma khong chan them duoc gi.
    filtered = turns

    if not filtered:
        return ""

    def _fmt(turn: ConversationTurn) -> str:
        role_label = "User" if turn.role == "user" else "Assistant"
        content = turn.content.strip()
        return "[" + role_label + "]: " + content

    # Schema v2 never anchors the first turn. Callers pre-select relevant turns;
    # this final bound prevents accidental history expansion.
    tail_limit = max_turns if max_turns is not None else 2
    tail = filtered[-tail_limit:] if tail_limit else []
    if not char_budget or char_budget <= 0:
        return "\n".join(_fmt(turn) for turn in tail)

    per_turn = max(80, char_budget // max(1, len(tail)))
    selected: list[str] = []
    for turn in tail:
        line = _fmt(turn)
        if len(line) > per_turn:
            line = line[:per_turn].rsplit(" ", 1)[0].strip() + "..."
        selected.append(line)
    return "\n".join(selected)
