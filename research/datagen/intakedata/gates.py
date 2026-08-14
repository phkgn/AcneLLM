"""Deterministic inline and corpus-level quality gates for Unified Intake."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .generator import user_turn_hash
from .schema import (
    DISTRIBUTION,
    INFLAMMATION,
    INTENT,
    LESION,
    SEX,
    SKIN,
    validate_intake_record,
)

_STOPPED_SEGMENT = re.compile(
    r"(?:không\s+dùng(?:\s+nữa)?|đã\s+(?:ngưng|ngừng)|bỏ\s+rồi|nghỉ\s+dùng|"
    r"khong\s+dung(?:\s+nua)?|da\s+(?:ngung|nghi))\s+([^,.!?;]{1,100})",
    re.IGNORECASE,
)
_SEGMENT_STOP = re.compile(
    r"\b(?:nhưng|còn|hiện|bây giờ|giờ thì|sau đó|but|now)\b", re.IGNORECASE
)
_ALIASES = {
    "bha": "salicylic acid",
    "salicylic acid": "salicylic acid",
    "bpo": "benzoyl peroxide",
    "benzoyl peroxide": "benzoyl peroxide",
    "differin": "adapalene",
    "adapalene": "adapalene",
    "tretinoin": "tretinoin",
    "retin-a": "tretinoin",
    "retinol": "retinol",
    "niacinamide": "niacinamide",
    "azelaic acid": "azelaic acid",
    "isotretinoin": "isotretinoin",
    "doxycycline": "doxycycline",
    "clindamycin": "clindamycin",
}
_VI_DIACRITICS = set(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
_JAILBREAK_MARKERS = (
    "dan",
    "bỏ qua mọi hướng dẫn",
    "bỏ qua hướng dẫn",
    "tiết lộ system prompt",
    "system prompt",
    "lộ prompt",
    "prompt hệ thống",
    "prompt gốc",
    "đóng vai bác sĩ",
    "bỏ qua kiểm duyệt",
    "không kiểm duyệt",
    "bỏ kiểm duyệt",
    "phớt lờ chính sách",
    "bộ lọc",
    "không giới hạn",
    "giới hạn an toàn",
    "vô hiệu hóa",
    "ràng buộc",
    "quy tắc",
    "chỉ thị",
    "chỉ dẫn hệ thống",
    "tin nhắn hệ thống",
    "cấu hình ẩn",
    "câu lệnh gốc",
    "chế độ nhà phát triển",
    "jailbreak",
    "ai tự do",
    "không phải trợ lý",
    "trái luật",
)
_GLUE_SELFREPORT = re.compile(
    r"\b(?:\d{1,3}\s*tuổi|da\s+(?:dầu|khô|hỗn\s*hợp|nhạy\s*cảm)|mụn|"
    r"đang\s+(?:dùng|bôi|uống)|tretinoin|adapalene|bha|bpo|niacinamide)\b",
    re.IGNORECASE,
)
_ACTIVE_USE = (
    "đang dùng",
    "đang sử dụng",
    "đang bôi",
    "đang thoa",
    "hiện dùng",
    "hiện sử dụng",
    "hiện đang dùng",
    "hiện đang sử dụng",
    "hien dung",
    "hien su dung",
    "dang dung",
    "dang su dung",
    "dang boi",
    "dang thoa",
)


@dataclass(slots=True)
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool | int | float | str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
        }


class CorpusGateState:
    """Accepted-corpus state; rejected candidates never mutate it."""

    def __init__(self, anchor: str) -> None:
        self.anchor = anchor
        self.user_hashes: set[str] = set()
        self.case_counts: Counter[str] = Counter()
        self.intent_counts: Counter[str] = Counter()

    def duplicate_user(self, user_turn: str) -> bool:
        return user_turn_hash(user_turn) in self.user_hashes

    def accept(self, record: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        user_turn = _current_user_turn(record)
        self.user_hashes.add(user_turn_hash(user_turn))
        meta = record.get("meta")
        case_type = str(meta.get("case_type")) if isinstance(meta, Mapping) else ""
        self.case_counts[case_type] += 1
        self.intent_counts[str(payload.get("intent"))] += 1


def _current_user_turn(record: Mapping[str, Any]) -> str:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages[:-1]):
        if isinstance(message, Mapping) and message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def _parse_payload(record: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        return None, "record_messages"
    last = messages[-1]
    if not isinstance(last, Mapping) or last.get("role") != "assistant":
        return None, "record_last_assistant"
    content = last.get("content")
    if not isinstance(content, str):
        return None, "record_assistant_content"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None, "json_parse"
    if not isinstance(payload, dict):
        return None, "root_object"
    return payload, None


def _record_shape_valid(record: Mapping[str, Any]) -> bool:
    record_id = record.get("id")
    messages = record.get("messages")
    meta = record.get("meta")
    if not isinstance(record_id, str) or not record_id:
        return False
    if not isinstance(meta, Mapping) or not isinstance(meta.get("case_type"), str):
        return False
    if not isinstance(messages, list) or len(messages) < 3:
        return False
    if not isinstance(messages[0], Mapping) or messages[0].get("role") != "system":
        return False
    if not isinstance(messages[-1], Mapping) or messages[-1].get("role") != "assistant":
        return False
    expected = "user"
    for message in messages[1:]:
        if not isinstance(message, Mapping):
            return False
        if message.get("role") != expected:
            return False
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return False
        expected = "assistant" if expected == "user" else "user"
    return expected == "user"


def _nested_confidences(value: Any, *, root: bool = True) -> list[float]:
    found: list[float] = []
    if isinstance(value, Mapping):
        if not root and set(value) == {"value", "confidence"}:
            confidence = value.get("confidence")
            if (
                isinstance(confidence, (int, float))
                and not isinstance(confidence, bool)
                and math.isfinite(float(confidence))
            ):
                found.append(float(confidence))
        else:
            for child in value.values():
                found.extend(_nested_confidences(child, root=False))
    elif isinstance(value, list):
        for child in value:
            found.extend(_nested_confidences(child, root=False))
    return found


def _enum_valid(payload: Mapping[str, Any]) -> bool:
    if payload.get("intent") not in INTENT:
        return False
    context = payload.get("context")
    if isinstance(context, Mapping):
        for key, allowed in (("sex", SEX), ("skin_type", SKIN)):
            node = context.get(key)
            if isinstance(node, Mapping) and node.get("value") not in allowed:
                return False
    clinical = payload.get("clinical")
    if isinstance(clinical, Mapping):
        scalar = clinical.get("inflammation_level")
        if not isinstance(scalar, Mapping) or scalar.get("value") not in INFLAMMATION:
            return False
        for key, allowed in (
            ("lesion_types", LESION),
            ("lesion_distribution", DISTRIBUTION),
        ):
            values = clinical.get(key)
            if not isinstance(values, list) or any(
                not isinstance(node, Mapping) or node.get("value") not in allowed
                for node in values
            ):
                return False
    return True


def _listed_entities(payload: Mapping[str, Any]) -> set[str]:
    context = payload.get("context")
    if not isinstance(context, Mapping):
        return set()
    values: set[str] = set()
    for key in ("current_products", "medications"):
        nodes = context.get(key)
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, Mapping) or not isinstance(node.get("value"), str):
                continue
            raw = " ".join(node["value"].casefold().split())
            values.add(_ALIASES.get(raw, raw))
    return values


def _context_scalar(payload: Mapping[str, Any], key: str) -> Any:
    context = payload.get("context")
    if not isinstance(context, Mapping):
        return None
    node = context.get(key)
    return node.get("value") if isinstance(node, Mapping) else None


def _context_confidence(payload: Mapping[str, Any], key: str) -> float | None:
    context = payload.get("context")
    if not isinstance(context, Mapping):
        return None
    node = context.get(key)
    confidence = node.get("confidence") if isinstance(node, Mapping) else None
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        return float(confidence)
    return None


def _context_values(payload: Mapping[str, Any], key: str) -> set[str]:
    context = payload.get("context")
    if not isinstance(context, Mapping):
        return set()
    nodes = context.get(key)
    if not isinstance(nodes, list):
        return set()
    values: set[str] = set()
    for node in nodes:
        if isinstance(node, Mapping) and isinstance(node.get("value"), str):
            raw = " ".join(node["value"].casefold().split())
            values.add(_ALIASES.get(raw, raw))
    return values


def _clinical_values(payload: Mapping[str, Any], key: str) -> set[str]:
    clinical = payload.get("clinical")
    if not isinstance(clinical, Mapping):
        return set()
    nodes = clinical.get(key)
    if not isinstance(nodes, list):
        return set()
    return {
        str(node.get("value"))
        for node in nodes
        if isinstance(node, Mapping) and isinstance(node.get("value"), str)
    }


def _stopped_entities(user_turn: str) -> set[str]:
    stopped: set[str] = set()
    for match in _STOPPED_SEGMENT.finditer(user_turn.casefold()):
        segment = _SEGMENT_STOP.split(match.group(1), maxsplit=1)[0]
        for alias, canonical in _ALIASES.items():
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", segment):
                stopped.add(canonical)
    return stopped


def _expected_intent(case_type: str, actual: Any) -> bool:
    if case_type.startswith("advise_"):
        return actual == "advise"
    if case_type.startswith("knowledge_"):
        return actual == "knowledge"
    if case_type.startswith("clarify_"):
        return actual == "clarify"
    if case_type.startswith("reject_"):
        return actual == "reject"
    if case_type == "glue_greeting_thanks":
        return actual in {"clarify", "advise"}
    return False


def _required_cue_present(cue: str, user_turn: str) -> bool:
    folded = user_turn.casefold()
    expected = cue.casefold()
    if expected in folded:
        return True
    for prefix in ("đang dùng ", "dang dung "):
        if expected.startswith(prefix):
            product = expected[len(prefix) :]
            if product not in folded:
                return False
            product_index = folded.find(product)
            nearby = folded[max(0, product_index - 70) : product_index]
            return any(active in nearby for active in _ACTIVE_USE)
    for prefix in ("ở ", "o "):
        if expected.startswith(prefix):
            return expected[len(prefix) :] in folded
    skin_markers = {
        "da dầu": ("dầu",),
        "da khô": ("khô",),
        "da hỗn hợp": ("hỗn hợp",),
        "da nhạy cảm": ("nhạy cảm",),
        "da thường": ("da thường", "da bình thường"),
        "da dau": ("dau",),
        "da kho": ("kho",),
        "da hon hop": ("hon hop",),
        "da nhay cam": ("nhay cam",),
        "da thuong": ("da thuong", "da binh thuong"),
    }
    if expected in skin_markers:
        return any(marker in folded for marker in skin_markers[expected])
    return False


def _provider_case_contract(
    case_type: str,
    user_turn: str,
    payload: Mapping[str, Any],
    seed: Mapping[str, Any],
    history_text: str,
) -> list[str]:
    """Validate provider-only case semantics encoded by ``synthesize_seed``."""
    failures: list[str] = []
    folded = user_turn.casefold()
    required_cues = seed.get("required_user_cues")
    if case_type.startswith("advise_"):
        if not isinstance(required_cues, list) or not required_cues:
            failures.append("input_required_cues_missing")
        else:
            for cue in required_cues:
                if not isinstance(cue, str) or not _required_cue_present(
                    cue, user_turn
                ):
                    failures.append(f"input_required_cue:{cue}")

    if case_type == "advise_noaccent" and any(
        char in _VI_DIACRITICS for char in folded
    ):
        failures.append("input_noaccent")
    if case_type == "advise_mixed_vi_en":
        phrase = str(seed.get("english_phrase") or "").casefold()
        if not phrase or phrase not in folded:
            failures.append("input_mixed_phrase")
    if case_type == "advise_negation_stopped" and not _stopped_entities(user_turn):
        failures.append("input_stopped_cue_entity")
    if case_type == "advise_ambiguous_lowconf":
        phrase = str(seed.get("ambiguous_phrase") or "").casefold()
        if not phrase or phrase not in folded:
            failures.append("input_ambiguous_phrase")
    if case_type == "reject_jailbreak_meta" and not any(
        marker in folded for marker in _JAILBREAK_MARKERS
    ):
        failures.append("input_jailbreak_marker")
    if case_type == "reject_unsafe_rx":
        drug = str(seed.get("drug") or "").casefold()
        if not drug or drug not in folded or not any(
            cue in folded for cue in ("liều", "kê", "tự dùng", "tự uống")
        ):
            failures.append("input_unsafe_rx")
    if case_type == "glue_greeting_thanks":
        if len(user_turn.split()) > 18 or _GLUE_SELFREPORT.search(user_turn):
            failures.append("input_glue_only")
    if case_type == "clarify_followup_multiturn":
        followup = str(seed.get("followup") or "").rstrip("?.! ").casefold()
        if not followup or followup not in folded:
            failures.append("input_followup")
        history_topic = str(seed.get("history_topic") or "")
        history_cue = f"đang dùng {history_topic}".casefold()
        if not history_topic or history_cue not in history_text.casefold():
            failures.append("input_followup_history")

    age = seed.get("age")
    skin = seed.get("skin_type")
    lesion = seed.get("lesion")
    distribution = seed.get("distribution")
    lesions = _clinical_values(payload, "lesion_types")
    distributions = _clinical_values(payload, "lesion_distribution")
    def require_common(*, require_product: str | None = None) -> None:
        if age is not None and _context_scalar(payload, "age") != age:
            failures.append("seed.age")
        if skin is not None and _context_scalar(payload, "skin_type") != skin:
            failures.append("seed.skin_type")
        if lesion is not None and lesion not in lesions:
            failures.append("seed.lesion")
        if distribution is not None and distribution not in distributions:
            failures.append("seed.distribution")
        if require_product:
            canonical = _ALIASES.get(require_product.casefold(), require_product.casefold())
            expected_products = {canonical}
            if _context_values(payload, "current_products") != expected_products:
                failures.append("seed.product")
            if _context_values(payload, "medications"):
                failures.append("seed.unexpected_medications")
        if _context_values(payload, "allergies"):
            failures.append("seed.unexpected_allergies")
        for key in ("is_pregnant", "is_breastfeeding"):
            if _context_scalar(payload, key) is not None:
                failures.append(f"seed.unexpected_{key}")

    if case_type == "advise_selfreport_simple":
        include = str(seed.get("include") or "")
        if "age" in include and _context_scalar(payload, "age") != age:
            failures.append("seed.age")
        if "skin_type" in include and _context_scalar(payload, "skin_type") != skin:
            failures.append("seed.skin_type")
        if "lesion" in include and lesion not in lesions:
            failures.append("seed.lesion")
        if "distribution" in include and distribution not in distributions:
            failures.append("seed.distribution")
        if "age" not in include and _context_scalar(payload, "age") is not None:
            failures.append("seed.unexpected_age")
        if "skin_type" not in include and _context_scalar(payload, "skin_type") is not None:
            failures.append("seed.unexpected_skin_type")
        if _context_scalar(payload, "sex") is not None:
            failures.append("seed.unexpected_sex")
        if _context_scalar(payload, "duration_weeks") is not None:
            failures.append("seed.unexpected_duration_weeks")
        if any(
            _context_values(payload, key)
            for key in ("allergies", "current_products", "medications")
        ):
            failures.append("seed.unexpected_context_list")
        expected_lesions = {str(lesion)} if "lesion" in include else set()
        expected_distributions = (
            {str(distribution)} if "distribution" in include else set()
        )
        if lesions != expected_lesions:
            failures.append("seed.unexpected_lesion")
        if distributions != expected_distributions:
            failures.append("seed.unexpected_distribution")
        if not expected_lesions and not expected_distributions and payload.get(
            "clinical"
        ) is not None:
            failures.append("seed.unexpected_clinical")
    elif case_type == "advise_selfreport_rich":
        require_common(require_product=str(seed.get("product") or ""))
        if _context_scalar(payload, "sex") != seed.get("sex"):
            failures.append("seed.sex")
        expected_lesions = {str(lesion), str(seed.get("second_lesion"))}
        expected_distributions = {
            str(distribution),
            str(seed.get("second_distribution")),
        }
        if lesions != expected_lesions:
            failures.append("seed.second_lesion")
        if distributions != expected_distributions:
            failures.append("seed.second_distribution")
        if _context_scalar(payload, "duration_weeks") != seed.get("duration_weeks"):
            failures.append("seed.duration_weeks")
    elif case_type == "advise_negation_stopped":
        require_common(require_product=str(seed.get("current_product") or ""))
        if lesions != {str(lesion)} or distributions != {str(distribution)}:
            failures.append("seed.unexpected_clinical")
        if _context_scalar(payload, "sex") is not None:
            failures.append("seed.unexpected_sex")
        if _context_scalar(payload, "duration_weeks") is not None:
            failures.append("seed.unexpected_duration_weeks")
    elif case_type == "advise_duration_convert":
        require_common(require_product=str(seed.get("product") or ""))
        if lesions != {str(lesion)} or distributions != {str(distribution)}:
            failures.append("seed.unexpected_clinical")
        if _context_scalar(payload, "duration_weeks") != seed.get(
            "expected_duration_weeks"
        ):
            failures.append("seed.duration_weeks")
        if _context_scalar(payload, "sex") is not None:
            failures.append("seed.unexpected_sex")
    elif case_type == "advise_noaccent":
        require_common(require_product=str(seed.get("product") or ""))
        if lesions != {str(lesion)} or distributions != {str(distribution)}:
            failures.append("seed.unexpected_clinical")
        if _context_scalar(payload, "sex") is not None:
            failures.append("seed.unexpected_sex")
        if _context_scalar(payload, "duration_weeks") is not None:
            failures.append("seed.unexpected_duration_weeks")
    elif case_type == "advise_mixed_vi_en":
        require_common(
            require_product=str(
                seed.get("expected_canonical_product")
                or seed.get("ingredient_alias")
                or seed.get("product")
                or ""
            )
        )
        if lesions != {str(lesion)} or distributions != {str(distribution)}:
            failures.append("seed.unexpected_clinical")
        if _context_scalar(payload, "sex") is not None:
            failures.append("seed.unexpected_sex")
        if _context_scalar(payload, "duration_weeks") is not None:
            failures.append("seed.unexpected_duration_weeks")
    elif case_type == "advise_ambiguous_lowconf":
        expected_field = str(seed.get("ambiguous_field") or "")
        expected_value = seed.get("ambiguous_value")
        if _context_scalar(payload, expected_field) != expected_value:
            failures.append("seed.ambiguous_value")
        confidence = _context_confidence(payload, expected_field)
        if confidence is None or confidence > float(
            seed.get("required_confidence_max") or 0.55
        ):
            failures.append("seed.ambiguous_confidence")
        for key in (
            "age",
            "sex",
            "skin_type",
            "is_pregnant",
            "is_breastfeeding",
            "duration_weeks",
        ):
            if key != expected_field and _context_scalar(payload, key) is not None:
                failures.append(f"seed.unexpected_{key}")
        if any(
            _context_values(payload, key)
            for key in ("allergies", "current_products", "medications")
        ):
            failures.append("seed.unexpected_context_list")
        if lesions != {str(lesion)} or distributions != {str(distribution)}:
            failures.append("seed.unexpected_clinical")
    elif case_type == "clarify_vague":
        vague = str(seed.get("vague_turn") or "").rstrip("?.! ").casefold()
        if not vague or vague not in folded:
            failures.append("input_vague")
        if payload.get("context") != {} or payload.get("clinical") is not None:
            failures.append("seed.unexpected_vague_extraction")
    elif case_type == "clarify_followup_multiturn":
        history_topic = str(seed.get("history_topic") or "")
        expected_product = _ALIASES.get(history_topic.casefold(), history_topic.casefold())
        if _context_values(payload, "current_products") != {expected_product}:
            failures.append("seed.followup_product")
        if _context_values(payload, "allergies") or _context_values(
            payload, "medications"
        ):
            failures.append("seed.unexpected_context_list")
        if any(
            _context_scalar(payload, key) is not None
            for key in (
                "age",
                "sex",
                "skin_type",
                "is_pregnant",
                "is_breastfeeding",
                "duration_weeks",
            )
        ):
            failures.append("seed.unexpected_followup_scalar")
        if payload.get("clinical") is not None:
            failures.append("seed.unexpected_followup_clinical")

    return failures


def evaluate_record(
    record: dict[str, Any],
    state: CorpusGateState | None = None,
    *,
    anchor: str | None = None,
) -> GateResult:
    """Evaluate a candidate without mutating corpus state."""
    reasons: list[str] = []
    checks: dict[str, bool | int | float | str] = {}
    expected_anchor = anchor if anchor is not None else state.anchor if state else None

    checks["record_schema"] = _record_shape_valid(record)
    if not checks["record_schema"]:
        return GateResult(False, ["record_schema"], checks)

    payload, parse_error = _parse_payload(record)
    checks["json_parse"] = parse_error is None
    if payload is None:
        return GateResult(False, [parse_error or "json_parse"], checks)

    schema_ok, schema_reasons = validate_intake_record(payload)
    checks["schema_valid"] = schema_ok
    if not schema_ok:
        reasons.extend(f"schema:{reason}" for reason in schema_reasons)

    messages = record["messages"]
    checks["system_parity"] = (
        expected_anchor is not None and messages[0].get("content") == expected_anchor
    )
    if not checks["system_parity"]:
        reasons.append("system_parity")

    checks["enum_valid"] = _enum_valid(payload)
    if not checks["enum_valid"]:
        reasons.append("enum_valid")

    all_confidences = [payload.get("confidence")] + _nested_confidences(payload)
    checks["confidence_range"] = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0 <= float(value) <= 1
        for value in all_confidences
    )
    if not checks["confidence_range"]:
        reasons.append("confidence_range")

    user_turn = _current_user_turn(record)
    checks["description_matches_user"] = payload.get("description") == user_turn
    if not checks["description_matches_user"]:
        reasons.append("description_matches_user")

    meta = record.get("meta") or {}
    case_type = str(meta.get("case_type") or "")
    checks["intent_case_match"] = _expected_intent(case_type, payload.get("intent"))
    if not checks["intent_case_match"]:
        reasons.append("intent_case_match")

    if case_type == "advise_negation_stopped":
        leaked = _stopped_entities(user_turn) & _listed_entities(payload)
        checks["negation_leak"] = not leaked
        if leaked:
            reasons.append("negation_leak:" + ",".join(sorted(leaked)))
    else:
        checks["negation_leak"] = True

    if (
        case_type.startswith(("knowledge_", "reject_"))
        or case_type == "glue_greeting_thanks"
    ):
        checks["empty_discipline"] = (
            payload.get("context") == {} and payload.get("clinical") is None
        )
        if not checks["empty_discipline"]:
            reasons.append("empty_discipline")
    else:
        checks["empty_discipline"] = True

    if case_type == "advise_ambiguous_lowconf":
        nested = _nested_confidences(payload)
        checks["ambiguous_lowconf"] = any(value < 0.6 for value in nested)
        if not checks["ambiguous_lowconf"]:
            reasons.append("ambiguous_lowconf")
    else:
        checks["ambiguous_lowconf"] = True

    duplicate = state.duplicate_user(user_turn) if state is not None else False
    checks["dedupe"] = not duplicate
    if duplicate:
        reasons.append("dedupe")

    source = str(meta.get("source") or "")
    if source.startswith("openai:"):
        seed = meta.get("seed")
        messages = record.get("messages")
        history_text = ""
        if isinstance(messages, list) and len(messages) > 3:
            history_text = "\n".join(
                str(message.get("content") or "")
                for message in messages[1:-2]
                if isinstance(message, Mapping)
            )
        provider_failures = _provider_case_contract(
            case_type,
            user_turn,
            payload,
            seed if isinstance(seed, Mapping) else {},
            history_text,
        )
        checks["case_input_contract"] = not any(
            reason.startswith("input_") for reason in provider_failures
        )
        checks["seed_consistency"] = not any(
            reason.startswith("seed.") for reason in provider_failures
        )
        reasons.extend(provider_failures)
    else:
        checks["case_input_contract"] = True
        checks["seed_consistency"] = True

    return GateResult(not reasons, reasons, checks)


def validate_corpus(
    records: Iterable[dict[str, Any]],
    anchor: str,
    expected_targets: Mapping[str, int],
    *,
    enforce_intent_floor: bool,
) -> dict[str, Any]:
    state = CorpusGateState(anchor)
    failures: list[dict[str, Any]] = []
    ids: list[str] = []
    for record in records:
        ids.append(str(record.get("id") or ""))
        result = evaluate_record(record, state)
        if result.passed:
            payload, _ = _parse_payload(record)
            assert payload is not None
            state.accept(record, payload)
        else:
            failures.append({"id": record.get("id"), "reasons": result.reasons})

    case_minimums = {
        case: math.ceil(target * 0.9)
        for case, target in expected_targets.items()
        if target > 0
    }
    case_deficits = {
        case: minimum - state.case_counts.get(case, 0)
        for case, minimum in case_minimums.items()
        if state.case_counts.get(case, 0) < minimum
    }
    total = sum(state.intent_counts.values())
    intent_floor_failures: dict[str, float] = {}
    if enforce_intent_floor and total:
        for intent in ("clarify", "reject"):
            ratio = state.intent_counts.get(intent, 0) / total
            if ratio < 0.1:
                intent_floor_failures[intent] = round(ratio, 6)

    return {
        "records": len(ids),
        "unique_ids": len(set(ids)),
        "duplicate_ids": len(ids) - len(set(ids)),
        "gate_failures": failures,
        "case_counts": dict(state.case_counts),
        "intent_counts": dict(state.intent_counts),
        "case_deficits_below_90pct": case_deficits,
        "intent_floor_failures": intent_floor_failures,
        "parity_ok": all(
            record.get("messages", [{}])[0].get("content") == anchor
            for record in records
        )
        if isinstance(records, list)
        else not failures,
    }
