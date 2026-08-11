"""Safety post-check cho chat stream."""
from __future__ import annotations

import re

from ..schemas import UserInput

# ── Liều lượng cụ thể trong câu trả lời (port từ guardrails._apply_medication_safety)
#
# Đây là luật DUY NHẤT được giữ lại từ tầng post_check cũ. Lý do: cổng đầu vào
# (medication_safety_refusal) chỉ thấy thứ NGƯỜI DÙNG nhắc tới. Nó không thấy
# được model tự sinh ra một liều cụ thể mà người dùng chưa hề hỏi:
#
#   User: "mụn viêm đỏ khắp hai má, em nên làm gì"
#   Model: "...uống doxycycline 100mg mỗi ngày trong 8 tuần..."
#
# Người dùng không nhắc tên thuốc nào, cổng đầu vào thấy sạch và cho qua.
# Đây là mẫu nguy hiểm nhất mà một model fine-tune trên tài liệu y khoa sẽ sinh
# ra, vì tài liệu huấn luyện đầy liều lượng.
_DOSE_RE = re.compile(
    r"(?:isotretinoin|tretinoin|adapalene|tazarotene|doxycycline|"
    r"minocycline|tetracycline|lymecycline|clindamycin|erythromycin|"
    r"spironolactone|corticoid|prednisone|prednisolone)"
    r"[^\n]{0,90}\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|mcg|%|viên|lần/ngày|ngày|tuần)",
    re.IGNORECASE | re.UNICODE,
)
_SELF_USE_RE = re.compile(
    r"(?:tự\s*(?:mua|dùng|uống|bôi)|mua\s+về\s+dùng)[^\n]{0,80}"
    r"(?:isotretinoin|kháng\s*sinh|antibiotic|doxycycline|minocycline|"
    r"tetracycline|clindamycin|erythromycin)",
    re.IGNORECASE | re.UNICODE,
)
_DOSE_WARNING = (
    "\n\n⚠️ Lưu ý: câu trả lời trên có nhắc tới liều lượng thuốc cụ thể. "
    "Liều dùng của thuốc kê đơn phải do bác sĩ da liễu chỉ định sau khi thăm khám "
    "và theo dõi tác dụng phụ — đừng tự áp dụng con số nào ở đây."
)
_DOSE_ANCHOR = (
    "do bác sĩ chỉ định", "do bac si chi dinh",
    "bác sĩ da liễu chỉ định", "phải do bác sĩ",
    "đừng tự áp dụng",
)


def _mentions_specific_dose(text: str) -> bool:
    return bool(_DOSE_RE.search(text) or _SELF_USE_RE.search(text))

_RETINOID_TERMS = (
    "isotretinoin", "tretinoin", "adapalene", "retinol",
    "retinoid", "tazarotene", "vitamin a",
)

_RX_TERMS = (
    "isotretinoin", "doxycycline", "minocycline", "tetracycline",
    "clindamycin", "erythromycin", "spironolactone",
)

_RX_RECOMMEND_CONTEXT = (
    "nen dung", "co the dung",
    "su dung", "dung ", "uong",
    "boi", "bat dau", "ke don",
    "lieu", "mg", "%", "apply", "use ", "take ",
)

_RX_RECOMMEND_CONTEXT_UNI = (
    "nên dùng", "có thể dùng",
    "sử dụng", "dùng ", "uống",
    "bôi", "bắt đầu", "kê đơn",
    "liều", "mg", "%", "apply", "use ", "take ",
)

_NEGATION_CONTEXT = (
    "khong nen", "khong duoc", "khong dung", "khong su dung",
    "tranh", "cam", "chong chi dinh",
    "khong khuyen nghi",
    "loai bo", "bo qua", "khong bao gom",
    "avoid", "do not use", "contraindicated",
)

_NEGATION_CONTEXT_UNI = (
    "không nên", "không được", "không dùng", "không sử dụng",
    "tránh", "cấm", "chống chỉ định",
    "không khuyến nghị",
    "loại bỏ", "bỏ qua", "không bao gồm",
    "avoid", "do not use", "contraindicated",
)

_ALL_NEGATION = _NEGATION_CONTEXT + _NEGATION_CONTEXT_UNI
_ALL_RX_CONTEXT = _RX_RECOMMEND_CONTEXT + _RX_RECOMMEND_CONTEXT_UNI

# Anchors để detect disclaimer đã có trong response (rộng hơn để tránh miss khi model paraphrase)
_GENERIC_DISCLAIMER_ANCHORS = (
    # không dấu
    "chi mang tinh tham khao",
    "khong thay the y kien bac si",
    "tham khao bac si",
    "tham khao y kien",
    "thong tin tham khao",
    "mang tinh tham khao",
    "khong thay the bac si",
    "nen gap bac si",
    "nen den gap bac si",
    # có dấu
    "chỉ mang tính tham khảo",
    "không thay thế ý kiến bác sĩ",
    "tham khảo bác sĩ",
    "tham khảo ý kiến",
    "thông tin tham khảo",
    "mang tính tham khảo",
    "không thay thế bác sĩ",
    "nên gặp bác sĩ",
    "nên đến gặp bác sĩ",
)

_GENERIC_DISCLAIMER_VI = (
    "\n\nLưu ý: Thông tin trên chỉ mang tính tham khảo và không thay thế "
    "ý kiến bác sĩ da liễu. Nếu tình trạng da không cải thiện hoặc có dấu hiệu "
    "nặng hơn, bạn nên đến gặp bác sĩ để được tư vấn trực tiếp."
)


def _mentions_positively(text: str, term: str) -> bool:
    lower = text.lower()
    start = 0
    found_positive = False
    while True:
        idx = lower.find(term, start)
        if idx == -1:
            break
        window_before = lower[max(0, idx - 60):idx]
        if not any(neg in window_before for neg in _ALL_NEGATION):
            found_positive = True
            break
        start = idx + 1
    return found_positive


def _already_has_warning(text: str, anchors: tuple) -> bool:
    lower = text.lower()
    return any(anchor in lower for anchor in anchors)


def _mentions_rx_advice(text: str, term: str) -> bool:
    lower = text.lower()
    start = 0
    while True:
        idx = lower.find(term, start)
        if idx == -1:
            return False
        window = lower[max(0, idx - 80): idx + len(term) + 120]
        if any(ctx in window for ctx in _ALL_RX_CONTEXT):
            return _mentions_positively(text, term)
        start = idx + len(term)


_PREGNANCY_MENTION_TERMS = (
    "mang thai", "có thai", "bầu bí", "thai kỳ", "thai nhi",
    "cho con bú", "cho con bu", "đang bú", "sau sinh",
    "pregnant", "pregnancy", "breastfeed", "lactating", "nursing",
)

# Tự thủ thuật bằng dụng cụ (dao/kim/chích/rạch/cây nặn) để lấy nhân mụn tại nhà —
# tuyệt đối không hướng dẫn. Bắt trên TEXT sinh ra để chặn cả khi model được nhắc
# "nếu vẫn muốn thì dùng dao...". Đây là safety net độc lập với system prompt.
_SELF_PROCEDURE_TERMS = (
    "dùng dao", "dung dao", "dùng kim", "dung kim",
    "cây nặn", "cay nan", "dụng cụ nặn", "dung cu nan", "que nặn", "que nan",
    "tự chích", "tu chich", "tự rạch", "tu rach", "tự lể", "tu le",
    "chích mụn", "chich mun", "rạch mụn", "rach mun",
    "lấy nhân mụn bằng", "lay nhan mun bang",
    "kim tiêm", "kim tiem", "kim vô trùng", "kim vo trung",
    "dao tiệt trùng", "dao tiet trung", "dao chuyên dụng", "dao chuyen dung",
)

_SELF_PROCEDURE_WARNING = (
    "\n\n⚠️ Lưu ý an toàn: Không tự nặn, chích, rạch hay dùng dao/kim/cây nặn "
    "(kể cả đã tiệt trùng) để lấy nhân mụn tại nhà — dễ gây nhiễm trùng, sẹo và "
    "làm mụn lan rộng. Việc lấy nhân mụn nên do bác sĩ hoặc kỹ thuật viên da liễu "
    "thực hiện trong điều kiện vô khuẩn."
)
_SELF_PROCEDURE_ANCHOR = (
    "không tự nặn, chích", "khong tu nan, chich", "trong điều kiện vô khuẩn",
    "trong dieu kien vo khuan",
)


def _advises_self_procedure(text: str) -> bool:
    """True nếu response nhắc đến việc tự dùng dụng cụ để lấy/chích nhân mụn."""
    lower = text.lower()
    return any(term in lower for term in _SELF_PROCEDURE_TERMS)


def get_safety_suffix(
    full_text: str,
    user: UserInput,
    route_flags: list[str] | None = None,
    skip_generic_disclaimer: bool = False,
    recent_turns: list | None = None,
    current_turn_text: str | None = None,
) -> str:
    """Build safety suffix to append after LLM response.

    Args:
        full_text: The full LLM-generated response text.
        user: Parsed UserInput với context đã fold từ history.
        route_flags: Route flags from intent router (e.g. ["urgency_red_flag"]).
        skip_generic_disclaimer: If True, skip the generic disclaimer.
        recent_turns: Recent conversation turns. Generic disclaimer suppressed
            if already appeared in last 2 assistant turns.
        current_turn_text: Raw text của turn HIỆN TẠI (chưa fold). Dùng để
            phân biệt pregnancy được fold từ history vs user vừa nói trong turn này.
            Khi None, fallback về user.description.
    """
    if not full_text:
        return ""

    # Bug fix: skip generic disclaimer if it already appeared recently.
    if recent_turns and not skip_generic_disclaimer:
        recent_assistant_texts = [
            t.content for t in recent_turns[-4:]
            if t.role == "assistant"
        ][-2:]  # last 2 assistant turns
        if any(
            _already_has_warning(t, _GENERIC_DISCLAIMER_ANCHORS)
            for t in recent_assistant_texts
        ):
            skip_generic_disclaimer = True

    warnings: list[str] = []
    route_flags = route_flags or []

    # Pregnancy/breastfeeding: chỉ trigger warning khi user đã mention trong
    # turn hiện tại HOẶC response text mention retinoid cùng lúc với pregnancy context.
    # Không trigger khi pregnancy chỉ đến từ fold history mà turn hiện tại không
    # liên quan (ví dụ: user hỏi về BPO sau khi đã hỏi về thai kỳ ở turn trước).
    _check_text = (current_turn_text or user.description).lower()
    _current_mentions_pregnancy = any(t in _check_text for t in _PREGNANCY_MENTION_TERMS)

    # pregnancy_known_positive: True khi user.context đã được set (fold hoặc current)
    # nhưng chỉ trigger retinoid warning khi turn hiện tại có liên quan đến pregnancy
    # hoặc response text thực sự đang advice về retinoid trong bối cảnh pregnancy.
    _folded_pregnant = user.context.is_pregnant or user.context.is_breastfeeding
    pregnancy_known_positive = _folded_pregnant and (
        _current_mentions_pregnancy
        or any(t in full_text.lower() for t in _PREGNANCY_MENTION_TERMS)
    )
    pregnancy_unknown = (
        not _folded_pregnant
        and user.context.sex is None
        and not _current_mentions_pregnancy
    )

    # Retinoid warning when pregnant / breastfeeding
    if pregnancy_known_positive:
        if any(_mentions_positively(full_text, t) for t in _RETINOID_TERMS):
            warning = (
                "\n\n⚠️ Lưu ý an toàn quan trọng: Các thành phần retinoid "
                "(isotretinoin, tretinoin, adapalene, retinol, tazarotene) và vitamin A liều cao "
                "chống chỉ định khi mang thai và cho con bú. "
                "Vui lòng tham khảo bác sĩ da liễu để chọn phác đồ an toàn."
            )
            if not _already_has_warning(
                full_text,
                ("chống chỉ định khi mang thai", "retinoid khi mang thai",
                 "chong chi dinh khi mang thai"),
            ):
                warnings.append(warning)
    elif pregnancy_unknown:
        # Sex unknown + retinoid mentioned -> precautionary disclaimer
        if any(_mentions_positively(full_text, t) for t in _RETINOID_TERMS):
            warning = (
                "\n\n⚠️ Lưu ý: Nếu bạn đang mang thai hoặc cho con bú, "
                "các thành phần retinoid (isotretinoin, tretinoin, adapalene, retinol) "
                "và vitamin A liều cao chống chỉ định. "
                "Vui lòng hỏi ý kiến bác sĩ trước khi sử dụng."
            )
            if not _already_has_warning(
                full_text,
                ("nếu bạn đang mang thai", "neu ban dang mang thai", "chống chỉ định"),
            ):
                warnings.append(warning)

    # Prescription drug warning -- only when LLM actively recommends use
    rx_warned = False
    for term in _RX_TERMS:
        if _mentions_rx_advice(full_text, term):
            if not rx_warned:
                warning = (
                    "\n\n⚠️ Một số thuốc được đề cập (như isotretinoin, doxycycline, "
                    "spironolactone...) là thuốc kê đơn -- cần bác sĩ da liễu thăm khám "
                    "và kê đơn trực tiếp. Không tự ý mua hoặc sử dụng."
                )
                if not _already_has_warning(
                    full_text,
                    ("thuốc kê đơn", "thuoc ke don", "cần bác sĩ", "kê đơn trực tiếp"),
                ):
                    warnings.append(warning)
                    rx_warned = True
            break

    # Age < 12: no strong actives
    age = user.context.age
    if age is not None and age < 12:
        warning = (
            "\n\n⚠️ Với trẻ dưới 12 tuổi, không nên tự ý sử dụng các sản phẩm "
            "trị mụn có hoạt chất mạnh (BHA, retinoid, benzoyl peroxide liều cao). "
            "Nên đưa trẻ đến bác sĩ da liễu nhi để được tư vấn phù hợp."
        )
        if not _already_has_warning(
            full_text, ("trẻ dưới 12", "tre duoi 12", "bác sĩ da liễu nhi")
        ):
            warnings.append(warning)

    # Urgency red flag: prompt to seek care.
    # Siết độ nhạy: chỉ bật 🚨 khi có red flag CẤP TÍNH thật sự (nhiễm trùng,
    # mủ, đau, lan rộng) — KHÔNG bật cho cờ mạn tính/nhẹ như treatment_failure
    # hay scarring_risk (tránh cảnh báo khẩn cấp lạm phát).
    _EMERGENCY_FLAGS = {"infection_signs", "purulent_lesions", "painful_lesions", "widespread"}
    _rf = set(getattr(user.clinical, "red_flags_input", []) or []) if user.clinical else set()
    if "urgency_red_flag" in route_flags and ((_rf & _EMERGENCY_FLAGS) or not _rf):
        if not _already_has_warning(
            full_text,
            ("đi khám ngay", "gặp bác sĩ ngay", "cấp cứu", "khám ngay",
             "di kham ngay", "gap bac si ngay",
             "đi khám", "di kham", "bác sĩ da liễu", "bac si da lieu",
             "gặp bác sĩ", "gap bac si", "khám bác sĩ", "kham bac si",
             "cơ sở y tế", "co so y te"),
        ):
            warnings.append(
                "\n\n\U0001f6a8 Nếu tình trạng có dấu hiệu nghiêm trọng (sưng tấy lan rộng, "
                "đau nhiều, sốt, hoặc tổn thương không cải thiện sau 48h), "
                "bạn nên đến cơ sở y tế ngay để được xử lý kịp thời."
            )

    # M6: Multi-condition comorbidity — escalate to dermatologist referral
    # Khi có rosacea, eczema, viêm da tiếp xúc đi kèm mụn → LLM không đủ để tư vấn
    # vì điều trị chồng chéo (BPO/retinoid contraindicated with rosacea/eczema).
    if "multi_condition" in route_flags:
        if not _already_has_warning(
            full_text,
            ("bac si da lieu", "bác sĩ da liễu", "chuyen khoa", "chuyên khoa",
             "kham chuyen khoa", "khám chuyên khoa"),
        ):
            warnings.append(
                "\n\n\u26a0\ufe0f Lưu ý: Khi có nhiều tình trạng da cùng lúc (ví dụ mụn kèm "
                "rosacea, eczema hoặc viêm da), việc tự điều trị có thể làm tình trạng phức tạp "
                "hơn vì các phác đồ có thể xung đột nhau. Bạn nên gặp bác sĩ da liễu để được "
                "đánh giá toàn diện và có phác đồ phù hợp."
            )

    # Self-procedure (dao/kim/chích/rạch) — luôn chèn cảnh báo dù model có nhắc
    # phòng ngừa hay không, vì đây là rủi ro trực tiếp (Critical, S09).
    if _advises_self_procedure(full_text) and not _already_has_warning(
        full_text, _SELF_PROCEDURE_ANCHOR
    ):
        warnings.append(_SELF_PROCEDURE_WARNING)

    # Liều cụ thể trong câu trả lời — xem chú thích ở đầu file.
    if _mentions_specific_dose(full_text) and not _already_has_warning(
        full_text, _DOSE_ANCHOR
    ):
        warnings.append(_DOSE_WARNING)

    # Generic disclaimer: skip for knowledge/product queries
    if not skip_generic_disclaimer and not warnings:
        if len(full_text) > 120 and not _already_has_warning(
            full_text, _GENERIC_DISCLAIMER_ANCHORS
        ):
            warnings.append(_GENERIC_DISCLAIMER_VI)

    return "".join(warnings)
