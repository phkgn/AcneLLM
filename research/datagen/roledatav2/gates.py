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
import unicodedata
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
from .config import ANCHOR_VARIANT_PATHS, MODULE_ROOT
from .knowledge import context_is_vietnamese

__all__ = [
    "CorpusGateState",
    "GateResult",
    "LENGTH_TOLERANCE",
    "LENGTH_TOLERANCE_HIGH",
    "LENGTH_TOLERANCE_LOW",
    "anchor_variants",
    "assistant_turns",
    "entities_grounded",
    "evaluate_record",
    "grounded_rate",
    "has_structure",
    "looks_english",
    "schema_valid",
    "user_facts_echoed",
    "vietnamese_only",
]


@functools.lru_cache(maxsize=1)
def anchor_variants() -> tuple[str, ...]:
    """Các system prompt hợp lệ, đọc từ `ANCHOR_VARIANT_PATHS`.

    Biến thể A (phần tử đầu) là bản đem đi phục vụ. B và C mã hoá cùng bộ luật
    nhưng khác hành văn — có mặt để model học luật thay vì học chuỗi ký tự.
    """
    return tuple(
        path.read_text(encoding="utf-8-sig").strip()
        for path in ANCHOR_VARIANT_PATHS
        if path.is_file()
    )

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

# ─────────────────────────────────────────────────────────────────────────────
# entities_grounded — thay `grounding_judge`
#
# Vòng 1 gỡ `grounded_rate` cho nguồn tiếng Anh (đúng: trùng token EN-VI luôn = 0)
# rồi thay bằng điểm judge. Judge đó cho 1043 điểm 5 / 2 điểm 4 / 0 điểm <=3 trên
# 1.045 mẫu — phương sai gần bằng không, tức không phải thước đo. Nguyên nhân:
# `roledata/generator.py::judge_knowledge` dùng CHÍNH model vừa sinh ra câu trả
# lời để chấm nó, ở temperature 0, với prompt hai dòng. Self-preference bias.
#
# Thay bằng phép so tập hợp: tên thuốc, tên guideline và con số phần trăm KHÔNG
# bị dịch, nên so trực tiếp được giữa nguồn tiếng Anh và đáp án tiếng Việt.
# Chạy thử trên 1.264 mẫu context của vòng 1: bắt 192 mẫu bịa entity/số mà judge
# cho 5/5 hết. Miễn phí, tất định, và chặt hơn 1.755 lời gọi API.
# ─────────────────────────────────────────────────────────────────────────────
_GROUNDED_TERMS: tuple[str, ...] = (
    "isotretinoin", "tretinoin", "adapalene", "tazarotene", "trifarotene",
    "doxycycline", "minocycline", "tetracycline", "lymecycline", "sarecycline",
    "clindamycin", "erythromycin", "benzoyl peroxide", "salicylic", "azelaic",
    "niacinamide", "retinoid", "spironolactone", "dapsone", "hydroquinone",
    "nice", "aad", "ng198", "pubmed", "cochrane", "fda", "ema",
    "cutibacterium", "propionibacterium",
)
# Chỉ bắt phần trăm và số thập phân — số nguyên trần dễ trùng với số thứ tự
# gạch đầu dòng ("1.", "2.") nên đo nó là đo nhiễu.
_NUMERIC_CLAIM = re.compile(r"\d+(?:[.,]\d+)?\s*%")


def entities_grounded(context: list[dict[str, str]] | None, answer: str) -> bool:
    """Tên thuốc/nguồn/số % trong câu trả lời đều phải có mặt trong tài liệu.

    So cả `source_name` chứ không chỉ `text`: nhãn "Nguồn 1 — PubMed" nằm trong
    lượt user nên assistant nói "theo PubMed" là có căn cứ. Bỏ qua nhãn này thì
    tỉ lệ báo động giả nhảy từ 9% lên 27%.
    """
    if not context:
        return True
    source = " ".join(
        f"{item.get('text', '')} {item.get('source_name', '')}"
        for item in context
        if isinstance(item, dict)
    ).casefold()
    folded = answer.casefold()
    if any(term in folded and term not in source for term in _GROUNDED_TERMS):
        return False
    squeezed = source.replace(" ", "")
    return all(
        claim.strip().replace(" ", "") in squeezed for claim in _NUMERIC_CLAIM.findall(folded)
    )


# ─────────────────────────────────────────────────────────────────────────────
# user_facts_echoed — nửa còn lại của "đủ ý"
#
# `points_covered` chỉ kiểm points <-> câu trả lời, mà points do chính model sinh
# ra cùng lúc với câu trả lời, nên nó chỉ xác nhận model tự nhất quán với mình.
# Không gate nào kiểm câu trả lời có DÙNG những gì người dùng vừa kể hay không.
# Đó chính là `missing_content` 2.24/3: câu trả lời đúng nhưng chung chung, dán
# vào ai cũng được. Đo bằng phủ từ nội dung, thô nhưng bắt đúng ca văn mẫu.
# ─────────────────────────────────────────────────────────────────────────────
_ECHO_MIN_RATIO = 0.30
# `stream_user.j2` xếp các khối theo thứ tự: tài liệu → ngữ cảnh → dữ kiện an
# toàn → "Tin nhắn hiện tại:". Chỉ khối cuối mới là lời người dùng.
_CURRENT_MESSAGE = "Tin nhắn hiện tại:"


def _fold_one(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.replace("đ", "d").replace("Đ", "D")


# Dò TIẾNG ANH, không dò tiếng Việt. Hai lần thử trước đều sai vì chọn nhầm chiều:
#
#   `vietnamese_only` (v1) thực chất là bộ dò DẤU — nó trả False cho câu tiếng Việt
#   không dấu hoàn toàn hợp lệ ("Ban nen rua mat diu nhe..."), mà 30% mẫu có
#   `input_style` thuộc {no_accent, teencode, typo, mixed} nên lời người dùng KHÔNG
#   có dấu là đúng thiết kế.
#
#   Đếm từ chức năng TIẾNG VIỆT cũng hỏng: một ý ngắn đặc nội dung như "rửa mặt dịu
#   nhẹ hai lần mỗi ngày giúp giảm bít tắc lỗ chân lông" không chứa từ chức năng nào
#   và bị coi là không phải tiếng Việt.
#
# Chiều đúng là dò tiếng Anh: tiếng Anh dày đặc từ chức năng (the/of/to/is/are/with)
# và chúng gần như không bao giờ xuất hiện trong văn tiếng Việt, kể cả khi câu có
# thuật ngữ y khoa tiếng Anh. Thứ cần chặn chỉ là một thứ: teacher chép nguyên câu
# từ chunk nguồn tiếng Anh.
_EN_FUNCTION_WORDS = frozenset(
    (
        "the", "of", "to", "in", "is", "are", "was", "were", "be", "been", "and",
        "or", "with", "for", "that", "this", "these", "those", "there", "their",
        "have", "has", "had", "can", "could", "should", "would", "may", "might",
        "after", "before", "when", "while", "whether", "which", "who", "from",
        "not", "but", "also", "such", "other", "than", "then", "they", "it",
    )
)


def looks_english(text: str) -> bool:
    """Văn bản có phải tiếng Anh không — dùng để chặn chép từ chunk nguồn.

    Ngưỡng 15% mật độ từ chức năng tiếng Anh. Câu tiếng Việt có lẫn thuật ngữ
    ("Hormonal therapy for acne là bất kỳ loại thuốc nào...") chỉ đạt ~7% nên đi
    qua — đúng ý: thuật ngữ y khoa tiếng Anh là hợp lệ, chép nguyên đoạn thì không.
    """
    words = _words_v1(text)
    if len(words) < 4:
        return False
    return sum(word in _EN_FUNCTION_WORDS for word in words) / len(words) >= 0.15


def _fold_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt, đ -> d.

    BẮT BUỘC cho gate này: 30% mẫu có `input_style` thuộc {no_accent, teencode,
    typo, mixed}, tức lượt user viết "em buon qua, mat day mun hoai" trong khi
    câu trả lời luôn là tiếng Việt chuẩn "nhìn gương thấy mụn mãi không khỏi".
    So thẳng thì "buon" != "buồn" và mẫu TỐT bị loại oan — đo augmentation chứ
    không đo chất lượng. Đã thấy thật khi chạy thử gate trên data vòng 1.
    """
    return _fold_one(text)


# STOPWORDS của v1 có dấu; token đem so đã bỏ dấu nên phải bỏ dấu cả bảng này,
# không thì "được"/"duoc" lọt qua và làm loãng tỉ lệ.
_FOLDED_STOPWORDS = frozenset(_fold_one(word) for word in STOPWORDS)


def user_facts_echoed(user_text: str, answer: str) -> bool:
    """>=30% từ nội dung TRONG LỜI NGƯỜI DÙNG xuất hiện lại trong câu trả lời.

    Phải cắt lấy riêng khối "Tin nhắn hiện tại:", không đo cả lượt user: với case
    có tài liệu thì lượt user chứa nguyên chunk nguồn tiếng Anh, đo cả cụm là đo
    echo của TÀI LIỆU chứ không phải của người dùng — và ngưỡng 30% khi đó không
    bao giờ đạt. Đây đúng là lỗi mà `test_smoke_all_cases[B1_grounded_role]` bắt.
    """
    _, _, current = user_text.rpartition(_CURRENT_MESSAGE)
    tokens = {
        word
        for word in _words_v1(_fold_diacritics(current or user_text))
        if word not in _FOLDED_STOPWORDS and len(word) > 2
    }
    if len(tokens) < 4:  # user nói quá ngắn -> không có gì để echo, không phạt
        return True
    answer_tokens = set(_words_v1(_fold_diacritics(answer)))
    return len(tokens & answer_tokens) / len(tokens) >= _ECHO_MIN_RATIO


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


# ─────────────────────────────────────────────────────────────────────────────
# anchor_leaked — thay bảng chặn chuỗi của `knowledge_leak`
#
# Gate v1 loại câu trả lời chứa "system prompt" / "prompt hệ thống". Nhưng câu TỪ
# CHỐI ĐÚNG buộc phải gọi tên thứ nó từ chối tiết lộ:
#
#   "Mình không thể chia sẻ prompt hệ thống vì đó là thông tin nội bộ."
#
# Đó là đáp án mẫu mực, và nó bị loại. Trên 200 mẫu, phép chặn chuỗi này gây
# 45/150 lần loại — 30% toàn bộ chi phí retry — và loại gần như MỌI mẫu R8.
#
# Rò rỉ thật là chép NỘI DUNG anchor ra ngoài, không phải nhắc tên nó. Đo bằng
# trùng 10-gram với chính anchor: nhắc tên thì không trùng, chép ra thì trùng
# ngay. Cùng kỹ thuật n-gram đã dùng ở `CorpusGateState`, không thêm phụ thuộc.
# ─────────────────────────────────────────────────────────────────────────────
_LEAK_NGRAM = 10


def _ngrams(words: list[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + size]) for i in range(max(0, len(words) - size + 1))}


def anchor_leaked(answer: str, anchor: str) -> bool:
    """Câu trả lời có chép nội dung anchor ra ngoài không.

    10 từ liên tiếp trùng anchor là chép, không phải trùng hợp. Ngưỡng này cho
    phép câu trả lời nói "mình không tiết lộ hướng dẫn nội bộ" — nêu tên thì
    được, đọc nội dung ra thì không.
    """
    answer_words = _words_v1(answer)
    if len(answer_words) < _LEAK_NGRAM:
        return False
    return bool(_ngrams(answer_words, _LEAK_NGRAM) & _ngrams(_words_v1(anchor), _LEAK_NGRAM))


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

    # `knowledge_leak` của v1 là bảng chặn chuỗi và nó loại chính câu từ chối
    # đúng chuẩn ("mình không thể chia sẻ prompt hệ thống"). Thay bằng phép đo
    # rò rỉ thật — trùng 10-gram với anchor. Lý do đầy đủ ở `anchor_leaked`.
    answer_all = "\n".join(assistant_turns(record))
    leaked = anchor_leaked(answer_all, anchor)
    checks["knowledge_leak"] = not leaked
    if not leaked and "knowledge_leak" in reasons:
        reasons.remove("knowledge_leak")
    # `no_prompt_leak` của v1 = `knowledge_leak` AND không chứa tên mục của anchor.
    # Nó được tính TRƯỚC override ở trên nên vẫn mang giá trị cũ; phải tính lại,
    # nếu không thì sửa một gate mà gate phụ thuộc vẫn đỏ. Phần kiểm tên mục
    # ("ưu tiên hệ thống", "chống jailbreak"...) giữ nguyên — đó là tiêu đề có
    # thật trong anchor nên nhắc lại đúng là rò rỉ.
    if "no_prompt_leak" in checks:
        checks["no_prompt_leak"] = not leaked and not _contains_any_folded(
            answer_all, ("ưu tiên hệ thống", "chống jailbreak", "vai trò & phạm vi")
        )
        if checks["no_prompt_leak"] and "no_prompt_leak" in reasons:
            reasons.remove("no_prompt_leak")

    # System prompt: chấp nhận BẤT KỲ biến thể đã đăng ký, không chỉ `anchor`
    # được truyền vào. Cần thế vì `_post_validate` chạy lại toàn bộ file với một
    # anchor duy nhất, trong khi mỗi bản ghi mang biến thể do lịch giao.
    # Vẫn là parity chặt: một trong ba chuỗi đã đăng ký, không phải "gần giống".
    if checks.get("system_parity") is False:
        messages = record.get("messages") or []
        system_text = str(messages[0].get("content", "")) if messages else ""
        if system_text in anchor_variants():
            checks["system_parity"] = True
            if "system_parity" in reasons:
                reasons.remove("system_parity")

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
    # phải là tiếng Việt. Bỏ nó đi và dùng `entities_grounded` — thay cho judge
    # của vòng 1, xem lý do ở khối comment trên đầu file.
    context = record.get("synthetic_context")
    if context:
        answer_all = "\n".join(assistant_turns(record))
        checks["grounding_language"] = "vi" if context_is_vietnamese(context) else "en"
        if checks["grounding_language"] == "en":
            checks.pop("grounded_rate_pass", None)
            if "grounded_rate_pass" in reasons:
                reasons.remove("grounded_rate_pass")
        # Chạy cho CẢ nguồn Việt lẫn Anh: nguồn tiếng Việt vẫn bịa được tên thuốc,
        # và `grounded_rate` là thước trùng-token nên không bắt được chuyện đó.
        checks["entities_grounded"] = entities_grounded(context, answer_all)

    # `knowledge_accuracy` của v1 đọc điểm judge trong generation_meta. Pipeline
    # v2 không gọi judge nữa nên trường đó không tồn tại và gate sẽ luôn đỏ. Gỡ
    # hẳn: `entities_grounded` ở trên là thứ thay thế nó.
    checks.pop("knowledge_accuracy", None)
    if "knowledge_accuracy" in reasons:
        reasons.remove("knowledge_accuracy")

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
            covered = sum(_point_is_present(point, answer) for point in points)
            checks["points_declared"] = len(points)
            checks["points_covered_count"] = covered
            # ĐẾM số ý được phủ, không đòi phủ HẾT. Hợp đồng là "phủ ít nhất
            # min_points ý", nên teacher khai 4 ý mà phủ 3 với min_points=3 là
            # đã đạt — bản cũ dùng `all()` nên phạt chính sự hào phóng đó.
            #
            # Bắt được trên 200 mẫu: R5 khai thêm một ý META về việc CẦN HỎI GÌ
            # ("cần hỏi thêm vị trí mụn và mức độ viêm"). Câu trả lời có hỏi thật,
            # nhưng hỏi thẳng bằng lời khác nên chỉ trùng 0.22-0.50 token. Hành vi
            # hỏi lại đã có gate `clarify_present` lo; `points_covered` không nên
            # phạt lần thứ hai vì cùng một chuyện.
            checks["points_covered"] = len(points) >= min_points and covered >= min_points
        if require_structure:
            checks["has_structure"] = has_structure(turns[-1] if turns else "")
        if case_spec.get("echo_user_facts"):
            checks["user_facts_echoed"] = user_facts_echoed(_first_user_text(record), answer)

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
