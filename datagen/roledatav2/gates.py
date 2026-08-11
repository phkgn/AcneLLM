"""Gates v2 = gates v1 + bốn kiểm tra mới. Không sửa gì của v1.

Thứ tự ưu tiên khi đọc kết quả gate: **ý trước, độ dài sau**. Band độ dài một
mình không tạo ra chất lượng — bằng chứng trong run_full_v3_2: ở arm sản phẩm,
câu càng dài `incorrect_content` càng cao (0.06 -> 0.51 từ tứ phân vị ngắn nhất
tới dài nhất). Nới chỗ mà không bắt phủ ý thì chỉ sinh ra data dài mà rỗng.

Bốn kiểm tra mới:

| check | bắt lỗi gì |
|---|---|
| `context_in_messages` | tài liệu không lọt vào `messages` — chính lỗi làm v1 mất sạch tài liệu |
| `length_band` | câu trả lời ngoài band của case (±`LENGTH_TOLERANCE`) |
| `points_covered` | thiếu số ý bắt buộc, hoặc `points` chỉ là tóm tắt không có trong câu trả lời |
| `has_structure` | case cần gạch đầu dòng mà viết thành một khối văn xuôi |
"""
from __future__ import annotations

import functools
import re
from typing import Any, Mapping

import yaml

from ..roledata.gates import (  # dùng lại nguyên vẹn
    STOPWORDS,
    CorpusGateState,
    GateResult,
    grounded_rate,
    schema_valid,
    vietnamese_only,
)
from ..roledata.gates import _words as _words_v1
from ..roledata.gates import evaluate_record as evaluate_record_v1
from .config import MODULE_ROOT
from .knowledge import context_is_vietnamese

__all__ = [
    "CorpusGateState",
    "GateResult",
    "LENGTH_TOLERANCE",
    "LENGTH_TOLERANCE_HIGH",
    "LENGTH_TOLERANCE_LOW",
    "assistant_turns",
    "evaluate_record",
    "grounded_rate",
    "has_structure",
    "schema_valid",
    "vietnamese_only",
]

# Bất đối xứng, và có lý do đo được: smoke lần đầu loại hai mẫu TỐT (đủ ý, đủ
# cấu trúc) chỉ vì hụt sàn 3 và 29 ký tự — 847 so với sàn 850. Đó là đo nhiễu,
# không phải đo chất lượng. Nới sàn xuống 25% để LLM có chỗ xoay; giữ trần 15%
# vì trần mới là thứ chặn lải nhải, và lải nhải thì `incorrect_content` tăng.
#
# Sàn KHÔNG phải thước chính. Thước chính là `points_covered` + `has_structure`;
# band chỉ chặn hai đầu grossly sai.
LENGTH_TOLERANCE_LOW = 0.25
LENGTH_TOLERANCE_HIGH = 0.15
LENGTH_TOLERANCE = LENGTH_TOLERANCE_HIGH  # giữ tên cũ cho caller ngoài

# Gạch đầu dòng, sao, chấm tròn, hoặc "1." / "1)" ở đầu dòng.
_BULLET_RE = re.compile(r"(?m)^\s*(?:[-*•–]\s+|\d+[.)]\s+)")

_CONTEXT_PROBE_CHARS = 60

# Tên thuốc mà gate `no_rx` của v1 cấm tuyệt đối trong câu trả lời R10.
_RX_NAMES = (
    "isotretinoin", "tretinoin", "adapalene", "tazarotene",
    "doxycycline", "minocycline", "tetracycline",
)
# Dấu hiệu câu đang CẢNH BÁO về thuốc chứ không phải khuyên dùng.
_NEGATIVE_MARKERS = (
    "không", "tránh", "chống chỉ định", "ngưng", "ngừng", "cấm", "nguy cơ",
    "không an toàn", "không được", "không nên", "gây hại", "dị tật", "kiêng",
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")


def rx_mentions_are_all_warnings(answer: str) -> bool:
    """Tên thuốc kê đơn chỉ được xuất hiện trong câu CẢNH BÁO, không phải khuyên dùng.

    Gate `no_rx` của v1 cấm tuyệt đối 7 tên thuốc này. Nhưng anchor lại BẮT nêu
    chúng ra: "Thai kỳ hoặc cho con bú: không khuyến nghị retinoid (isotretinoin,
    tretinoin, adapalene, tazarotene) hay kháng sinh nhóm cycline (doxycycline,
    minocycline, tetracycline)". Không nêu tên thì cảnh báo thành vô nghĩa.

    Kết quả: smoke thật loại 4/4 mẫu R10 vì `no_rx`, cả 4 đều đủ ý, đủ cấu trúc,
    đúng độ dài — chúng bị loại vì làm ĐÚNG luật an toàn. Cùng loại lỗi với
    grounded_rate-vs-vietnamese_only: hai quy tắc loại trừ nhau.

    Thay bằng: xét từng câu có tên thuốc, câu đó phải mang dấu hiệu phủ định.
    """
    folded = answer.casefold()
    for sentence in _SENTENCE_SPLIT.split(folded):
        if any(name in sentence for name in _RX_NAMES) and not _contains_any_folded(
            sentence, _NEGATIVE_MARKERS
        ):
            return False
    return True


def _contains_any_folded(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)

_TAXONOMY_PATH = MODULE_ROOT / "taxonomy.yaml"


@functools.lru_cache(maxsize=1)
def case_specs() -> dict[str, dict[str, Any]]:
    """Bảng tra case_spec theo `sample_kind`, đọc thẳng từ taxonomy.yaml.

    Tự tra thay vì bắt caller truyền vào: nhờ vậy `_post_validate` của pipeline
    (gọi `evaluate_record` không kèm spec) vẫn được kiểm đầy đủ gate v2. Quên
    truyền spec là đúng cái lỗi đã làm v1 mất tài liệu — không lặp lại kiểu bug
    "đường thứ hai không có kiểm tra".
    """
    payload = yaml.safe_load(_TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {str(group["sample_kind"]): dict(group) for group in payload["groups"]}


def assistant_turns(record: Mapping[str, Any]) -> list[str]:
    return [
        str(message.get("content", ""))
        for message in record.get("messages", [])
        if message.get("role") == "assistant"
    ]


def _first_user_text(record: Mapping[str, Any]) -> str:
    for message in record.get("messages", []):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def has_structure(text: str) -> bool:
    """Có ít nhất hai dòng bắt đầu bằng bullet/số."""
    return len(_BULLET_RE.findall(text)) >= 2


def _context_in_messages(record: Mapping[str, Any]) -> bool:
    """Tài liệu phải nằm TRONG lượt user, không phải ở field anh em.

    Đây là regression guard của cả module v2. Chỉ so đoạn đầu mỗi chunk vì
    `stream_user.j2` chèn nhãn "Nguồn i —" xen vào giữa các chunk.
    """
    context = record.get("synthetic_context")
    if not context:
        return True
    user_text = _first_user_text(record)
    if "Tài liệu tham khảo:" not in user_text:
        return False
    for item in context:
        text = str(item.get("text") if isinstance(item, dict) else item or "").strip()
        if text and text[:_CONTEXT_PROBE_CHARS] not in user_text:
            return False
    return True


def _point_is_present(point: str, answer: str) -> bool:
    """`points` phải trích từ câu trả lời, không phải tóm tắt viết lại.

    Đo bằng phủ token nội dung: >=60% từ có nghĩa của ý xuất hiện trong câu trả
    lời. Thô nhưng đủ bắt trường hợp teacher bịa ra `points` không liên quan.
    """
    tokens = {word for word in _words_v1(point) if word not in STOPWORDS and len(word) > 2}
    if not tokens:
        return False
    answer_tokens = set(_words_v1(answer))
    return len(tokens & answer_tokens) / len(tokens) >= 0.6


def _length_band(case_spec: Mapping[str, Any], is_last_turn: bool) -> tuple[int, int]:
    band = case_spec.get("last_turn_len_chars") if is_last_turn else None
    band = band or case_spec["len_chars"]
    lo, hi = int(band[0]), int(band[1])
    return round(lo * (1 - LENGTH_TOLERANCE_LOW)), round(hi * (1 + LENGTH_TOLERANCE_HIGH))


def evaluate_record(
    record: dict[str, Any],
    anchor: str,
    corpus: CorpusGateState | None = None,
    case_spec: Mapping[str, Any] | None = None,
) -> GateResult:
    """Chạy toàn bộ gate v1 rồi cộng thêm gate v2.

    `case_spec` không truyền thì tự tra theo `record["sample_kind"]`, nên mọi
    đường gọi đều được kiểm như nhau.
    """
    result = evaluate_record_v1(record, anchor, corpus=None)
    if case_spec is None:
        case_spec = case_specs().get(str(record.get("sample_kind")))

    checks = dict(result.checks)
    reasons = list(result.reasons)

    checks["context_in_messages"] = _context_in_messages(record)

    # R10: cho phép nêu tên thuốc kê đơn KHI ĐANG CẢNH BÁO — anchor bắt phải nêu.
    # Vẫn giữ nguyên phần cấm liều lượng của v1 (regex mg/ml/lần một ngày).
    if record.get("sample_kind") == "R10_special_population" and checks.get("no_rx") is False:
        answer_text = "\n".join(assistant_turns(record))
        has_dosage = bool(
            re.search(r"\b\d+(?:[.,]\d+)?\s*(?:mg|ml|g|lần/ngày|lần mỗi ngày)\b", answer_text, re.I)
        )
        if not has_dosage and rx_mentions_are_all_warnings(answer_text):
            checks["no_rx"] = True
            checks["rx_named_as_warning"] = True
            if "no_rx" in reasons:
                reasons.remove("no_rx")

    # Nguồn tiếng Anh: `grounded_rate` (trùng token) vô nghĩa vì câu trả lời buộc
    # phải là tiếng Việt. Bỏ nó đi và dùng điểm judge do pipeline bơm vào
    # `generation_meta["grounding_judge"]`. Không có điểm judge = chưa chấm = trượt.
    context = record.get("synthetic_context")
    if context and not context_is_vietnamese(context):
        checks["grounding_language"] = "en"
        checks.pop("grounded_rate_pass", None)
        if "grounded_rate_pass" in reasons:
            reasons.remove("grounded_rate_pass")
        score = (record.get("generation_meta") or {}).get("grounding_judge")
        checks["grounding_judge"] = score if isinstance(score, (int, float)) else None
        checks["grounding_judge_pass"] = isinstance(score, (int, float)) and score >= 4
    elif context:
        checks["grounding_language"] = "vi"

    if case_spec is not None:
        turns = assistant_turns(record)
        min_points = int(case_spec.get("min_points") or 0)
        require_structure = bool(case_spec.get("require_structure"))

        band_ok = bool(turns)
        for index, turn in enumerate(turns):
            lo, hi = _length_band(case_spec, is_last_turn=index == len(turns) - 1)
            if not lo <= len(turn) <= hi:
                band_ok = False
                checks["length_band_detail"] = f"turn{index}={len(turn)} ngoài [{lo},{hi}]"
                break
        checks["length_band"] = band_ok

        answer = "\n".join(turns)
        if min_points:
            points = [str(item) for item in (record.get("points") or []) if str(item).strip()]
            checks["points_declared"] = len(points)
            checks["points_covered"] = len(points) >= min_points and all(
                _point_is_present(point, answer) for point in points
            )
        if require_structure:
            checks["has_structure"] = has_structure(turns[-1] if turns else "")

    for name, value in checks.items():
        if value is False and name not in reasons:
            reasons.append(name)

    passed = not reasons
    # Chỉ nạp corpus n-gram khi bản ghi ĐÃ qua hết gate, giống v1: ứng viên bị
    # loại không được làm bẩn thống kê lặp cụm.
    if passed and corpus is not None:
        answer_text = "\n".join(assistant_turns(record))
        if not corpus.candidate_ok(answer_text):
            checks["phrase_frequency"] = False
            reasons.append("phrase_frequency")
            passed = False
        else:
            corpus.accept(answer_text)

    return GateResult(passed, reasons, checks)
