"""Offline, deterministic inline validators for roledata records."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
VI_DIACRITICS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
VI_COMMON = {
    "bạn", "mình", "da", "mụn", "và", "là", "có", "không", "nên", "với",
    "khi", "nếu", "để", "của", "trong", "này", "thể", "bác", "sĩ", "cần",
}
EN_COMMON = {
    "the", "and", "you", "your", "is", "are", "this", "that", "with", "for",
    "should", "skin", "acne", "doctor", "treatment", "please", "can", "use",
}
STOPWORDS = VI_COMMON | {
    "một", "những", "các", "được", "từ", "theo", "về", "do", "hơn", "đó",
    "thì", "như", "nhưng", "vì", "hay", "hoặc", "đang", "sẽ", "đã", "rằng",
}


@dataclass(slots=True)
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool | float | int | str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reasons": self.reasons, "checks": self.checks}


class CorpusGateState:
    """Tracks accepted n-grams; rejected candidates never mutate this state."""

    def __init__(self, ngram_size: int = 8, max_occurrences: int = 5) -> None:
        self.ngram_size = ngram_size
        self.max_occurrences = max_occurrences
        self._counts: Counter[tuple[str, ...]] = Counter()

    def candidate_ok(self, text: str) -> bool:
        local = Counter(_ngrams(text, self.ngram_size))
        return all(
            self._counts[gram] + count <= self.max_occurrences
            for gram, count in local.items()
        )

    def accept(self, text: str) -> None:
        self._counts.update(_ngrams(text, self.ngram_size))


def _words(text: str) -> list[str]:
    return [word.lower() for word in WORD_RE.findall(text)]


def _ngrams(text: str, n: int) -> Iterable[tuple[str, ...]]:
    words = _words(text)
    for index in range(max(0, len(words) - n + 1)):
        yield tuple(words[index : index + n])


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(phrase.casefold() in folded for phrase in phrases)


def _assistant_text(record: dict[str, Any]) -> str:
    return "\n".join(
        str(message.get("content", ""))
        for message in record.get("messages", [])
        if message.get("role") == "assistant"
    ).strip()


def _user_text(record: dict[str, Any]) -> str:
    return "\n".join(
        str(message.get("content", ""))
        for message in record.get("messages", [])
        if message.get("role") == "user"
    ).strip()


def _context_text(record: dict[str, Any]) -> str:
    value = record.get("synthetic_context")
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in value
        )
    return str(value)


def schema_valid(record: dict[str, Any]) -> bool:
    if not isinstance(record.get("id"), str) or not record["id"]:
        return False
    if not isinstance(record.get("sample_kind"), str):
        return False
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        return False
    if messages[0].get("role") != "system":
        return False
    if messages[-1].get("role") != "assistant":
        return False
    for message in messages:
        if message.get("role") not in {"system", "user", "assistant"}:
            return False
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            return False
    for previous, current in zip(messages[1:], messages[2:]):
        if previous["role"] == current["role"]:
            return False
    return True


def vietnamese_only(text: str) -> bool:
    words = _words(text)
    if not words:
        return False
    english = sum(word in EN_COMMON for word in words)
    vietnamese_signal = sum(
        word in VI_COMMON or any(char in VI_DIACRITICS for char in word) for word in words
    )
    # Chỉ chặn khi câu trả lời thực sự lệch sang tiếng Anh. Từ y khoa/thuật ngữ
    # (retinoid, BHA, AHA...) là trung tính; vài từ tiếng Anh phổ thông vẫn chấp
    # nhận được miễn tín hiệu tiếng Việt rõ ràng. Nới trần 2% -> 6% để bớt oan.
    return vietnamese_signal > 0 and english / len(words) <= 0.06


def grounded_rate(answer: str, context: str) -> float:
    context_tokens = {word for word in _words(context) if word not in STOPWORDS and len(word) > 2}
    if not context_tokens:
        return 0.0
    claims = [part.strip() for part in SENTENCE_RE.split(answer) if len(_words(part)) >= 3]
    if not claims:
        return 0.0
    grounded = 0
    for claim in claims:
        tokens = {word for word in _words(claim) if word not in STOPWORDS and len(word) > 2}
        if tokens and len(tokens & context_tokens) / len(tokens) >= 0.15:
            grounded += 1
    return grounded / len(claims)


def evaluate_record(
    record: dict[str, Any],
    anchor: str,
    corpus: CorpusGateState | None = None,
) -> GateResult:
    reasons: list[str] = []
    checks: dict[str, bool | float | int | str] = {}

    checks["schema_valid"] = schema_valid(record)
    if not checks["schema_valid"]:
        reasons.append("schema_valid")
        return GateResult(False, reasons, checks)

    messages = record["messages"]
    answer = _assistant_text(record)
    user_text = _user_text(record)
    case = record["sample_kind"]
    metadata = record.get("generation_meta") or {}

    checks["system_parity"] = messages[0]["content"] == anchor
    checks["vietnamese_only"] = vietnamese_only(answer)
    checks["knowledge_leak"] = not _contains_any(
        answer,
        ("system prompt", "prompt hệ thống", "hướng dẫn hệ thống bí mật", "nội dung system"),
    )
    checks["phrase_frequency"] = corpus is None or corpus.candidate_ok(answer)

    for name in ("system_parity", "vietnamese_only", "knowledge_leak", "phrase_frequency"):
        if not checks[name]:
            reasons.append(name)

    if case == "R1_identity":
        folded = answer.casefold()
        states_limit = bool(
            re.search(
                r"(?:không|chưa)\s+(?:thể\s+)?(?:phải|là|thay\s+thế)\s+(?:một\s+)?bác\s+sĩ",
                folded,
            )
        ) or _contains_any(
            answer,
            (
                "tư vấn sơ bộ", "thông tin sơ bộ", "hỗ trợ sơ bộ", "không thay thế",
                "không phải bác sĩ", "không phải chuyên gia", "không chẩn đoán",
                "nên gặp bác sĩ", "gặp bác sĩ da liễu", "tham khảo bác sĩ",
                "chỉ mang tính tham khảo",
            ),
        )
        # Danh tính không cần chuỗi literal "acnellm" ở mọi câu: assistant xưng
        # "mình/trợ lý" là đủ tín hiệu danh tính. Điều thực sự cần là NÊU GIỚI HẠN
        # (không phải bác sĩ / chỉ tham khảo). Nới để bớt reject oan.
        mentions_self = "acnellm" in folded or _contains_any(
            answer, ("mình là", "mình chỉ", "trợ lý", "công cụ hỗ trợ", "mình hỗ trợ")
        )
        checks["identity_rule"] = states_limit and mentions_self
    elif case == "R2_depth_adaptation":
        checks["depth_marker"] = metadata.get("audience") in {
            "teen", "parent", "medical_student"
        } and not _contains_any(answer, ("tôi kê", "liều dùng", "chẩn đoán xác định"))
    elif case == "R3_nonjudgment":
        checks["nonjudgment_rule"] = not _contains_any(
            answer, ("đáng trách", "sao bạn lại", "lười chăm", "tự chuốc", "xấu xí")
        )
    elif case == "R4_measured_empathy":
        checks["empathy_rule"] = _contains_any(
            answer,
            (
                "mình hiểu", "tôi hiểu", "mình biết", "có thể khiến bạn", "khó chịu",
                "lo lắng", "áp lực", "buồn", "mệt mỏi", "đừng lo", "chia sẻ",
                "cảm giác", "tự ti", "hiểu cảm giác", "không sao",
            ),
        ) and len(answer) < 2_200
    elif case == "R5_natural_clarification":
        question_count = answer.count("?")
        checks["clarify_present"] = 1 <= question_count <= 5
    elif case in {"R6_role_boundary", "R8_meta_jailbreak"}:
        checks["refusal_present"] = _contains_any(
            answer,
            (
                "mình không thể",
                "tôi không thể",
                "không thể",
                "không thực hiện",
                "không làm theo",
                "không đáp ứng",
                "không hỗ trợ yêu cầu",
                "không phù hợp",
            ),
        )
        if case == "R8_meta_jailbreak":
            checks["no_prompt_leak"] = checks["knowledge_leak"] and not _contains_any(
                answer, ("ưu tiên hệ thống", "chống jailbreak", "vai trò & phạm vi")
            )
            checks["jailbreak_input"] = _contains_any(
                user_text,
                (
                    "dan",
                    "ignore previous",
                    "bỏ qua hướng dẫn",
                    "bỏ qua mọi chỉ dẫn",
                    "đóng vai bác sĩ",
                    "hãy là bác sĩ",
                    "lộ prompt",
                    "tiết lộ prompt",
                    "system prompt",
                    "prompt hệ thống",
                ),
            )
    elif case == "R7_conversation_glue":
        folded_ans = answer.casefold()
        checks["onscope_redirect"] = ("mụn" in folded_ans or "làn da" in folded_ans) and _contains_any(
            answer,
            ("quay lại", "hỗ trợ", "chia sẻ", "tình trạng", "giúp", "tư vấn", "cho mình biết", "kể thêm"),
        )
    elif case == "R9_multiturn":
        turns = messages[1:]
        # 4-8 messages = 2-4 cặp user/assistant: đều là multiturn hợp lệ. Trần cũ
        # là 6 khiến hội thoại 4 cặp (rất phổ biến từ model) bị reject oan.
        checks["turn_count"] = 4 <= len(turns) <= 8 and len(turns) % 2 == 0
        checks["consistency"] = all(
            left["role"] != right["role"] for left, right in zip(turns, turns[1:])
        ) and not (" em " in f" {answer.casefold()} " and " quý khách " in f" {answer.casefold()} ")
    elif case == "R10_special_population":
        checks["referral_present"] = _contains_any(
            answer, ("bác sĩ da liễu", "bác sĩ nhi", "đưa bé đi khám", "trao đổi với bác sĩ")
        )
        dosage = re.search(r"\b\d+(?:[.,]\d+)?\s*(?:mg|ml|g|lần/ngày|lần mỗi ngày)\b", answer, re.I)
        prescription = _contains_any(
            answer,
            ("isotretinoin", "tretinoin", "adapalene", "tazarotene", "doxycycline", "minocycline"),
        )
        checks["no_rx"] = not dosage and not prescription

    if case in {"B1_grounded_role", "B3_irrelevant_chunk", "B5_depth_anchor", "K1_knowledge_anchor"}:
        score = grounded_rate(answer, _context_text(record))
        checks["grounded_rate"] = round(score, 4)
        checks["grounded_rate_pass"] = score >= 0.6
    if case == "B2_missing_answer":
        checks["abstain_rule"] = _contains_any(
            answer,
            ("tài liệu chưa có", "chưa đủ thông tin", "không đủ dữ kiện", "không thể kết luận"),
        )
    if case == "B3_irrelevant_chunk":
        checks["irrelevant_ignored"] = not _contains_any(answer, ("thời tiết hôm nay", "giá điện thoại"))
    if case == "B4_conflicting_docs":
        checks["conflict_rule"] = (
            _contains_any(answer, ("nguồn 1", "tài liệu 1"))
            and _contains_any(answer, ("nguồn 2", "tài liệu 2"))
            and _contains_any(answer, ("mâu thuẫn", "khác nhau", "chưa thống nhất"))
            and _contains_any(answer, ("bác sĩ", "chuyên gia"))
        )
    if case == "B5_depth_anchor":
        checks["anchor_pair"] = bool(metadata.get("anchor_group")) and metadata.get("depth") in {
            "beginner", "advanced"
        }
    if case == "K1_knowledge_anchor":
        score = metadata.get("knowledge_accuracy", 0)
        checks["knowledge_accuracy"] = isinstance(score, (int, float)) and score >= 4

    for name, value in checks.items():
        if name == "grounded_rate":
            continue
        if value is False and name not in reasons:
            reasons.append(name)

    passed = not reasons
    if passed and corpus is not None:
        corpus.accept(answer)
    return GateResult(passed, reasons, checks)
