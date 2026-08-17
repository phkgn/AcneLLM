#!/usr/bin/env python3
"""Evaluate unified intake on held-out, single-turn chat records.

The model path is measured directly: the evaluator never reads the runtime
cache and never substitutes a router/extractor fallback after an inference
failure.  The default validation split is kept separate from the generated
training split by an exact-text overlap guard.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
import json
import math
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acne_llm.chat._intake_parse import (  # noqa: E402
    _DISTRIBUTION,
    _INFLAMMATION,
    _INTENT,
    _LESION,
    _SEX,
    _SKIN,
)
from acne_llm.chat.preprocess import prepare_user_text  # noqa: E402
from acne_llm.chat.unified_intake import UnifiedIntake  # noqa: E402
from acne_llm.config import Settings  # noqa: E402
from acne_llm.llm.ollama_backend import OllamaBackend  # noqa: E402
from acne_llm.utils.fuzzy_match import best_match  # noqa: E402
from evaluation.metrics.intake import (  # noqa: E402
    canonicalization_hit,
    enum_validity,
    expected_calibration_error,
    list_prf,
    negation_leak,
)


# Bộ đề RIÊNG cho khâu intake, đặt hàng theo độ phủ lâm sàng.
# Bộ cũ `intake.val.jsonl` bị bỏ vì có 0 dòng `is_pregnant=True` trên 400 dòng —
# field quyết định chống chỉ định isotretinoin mà chưa từng được kiểm. Sinh bằng
# `python -m evaluation.datasets.make_intake_set --yes`.
DEFAULT_EVAL = ROOT / "research/evaluation/datasets/intake_eval.v1.jsonl"
DEFAULT_TRAIN = ROOT / "research/datagen/intakedata/output/intake/intake.train.jsonl"
DEFAULT_OUTPUT = ROOT / "research/evaluation/reports/intake_eval/report.json"
CONTEXT_SCALARS = (
    "age",
    "sex",
    "skin_type",
    "is_pregnant",
    "is_breastfeeding",
    "duration_weeks",
)
CONTEXT_LISTS = ("allergies", "current_products", "medications")
CLINICAL_SCALARS = ("inflammation_level",)
CLINICAL_LISTS = ("lesion_types", "lesion_distribution")
INTENT_LABELS = ("advise", "knowledge", "clarify", "reject")
FUZZY_FIELDS = {"context.current_products", "context.medications"}
FUZZY_THRESHOLD = 0.8


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _valid_confidence(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _validate_node(
    node: Any,
    *,
    value_type: type | tuple[type, ...],
    allowed: set[str] | frozenset[str] | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> bool:
    if node is None:
        return True
    if not isinstance(node, Mapping) or set(node) != {"value", "confidence"}:
        return False
    value = node.get("value")
    if value is None or isinstance(value, bool) != (value_type is bool):
        return False
    if not isinstance(value, value_type) or not _valid_confidence(node.get("confidence")):
        return False
    if allowed is not None and value not in allowed:
        return False
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def _validate_list_node(
    value: Any,
    *,
    allowed: set[str] | frozenset[str] | None = None,
) -> bool:
    return isinstance(value, list) and all(
        _validate_node(item, value_type=str, allowed=allowed) for item in value
    )


def validate_payload_schema(payload: Any, expected_description: str) -> list[str]:
    """Validate the generated wire payload without importing a second schema package."""
    violations: list[str] = []
    if not isinstance(payload, Mapping):
        return ["root must be an object"]
    root_keys = {"intent", "confidence", "description", "context", "clinical"}
    if set(payload) != root_keys:
        violations.append("root keys")
    if payload.get("intent") not in INTENT_LABELS:
        violations.append("intent")
    if not _valid_confidence(payload.get("confidence")):
        violations.append("confidence")
    description = payload.get("description")
    if (
        not isinstance(description, str)
        or not 1 <= len(description) <= 4_000
        or description != expected_description
    ):
        violations.append("description")

    context = payload.get("context")
    context_keys = set(CONTEXT_SCALARS) | set(CONTEXT_LISTS)
    if not isinstance(context, Mapping) or not set(context).issubset(context_keys):
        violations.append("context")
        context = {}
    scalar_rules = {
        "age": (int, None, 0, 120),
        "sex": (str, _SEX, None, None),
        "skin_type": (str, _SKIN, None, None),
        "is_pregnant": (bool, None, None, None),
        "is_breastfeeding": (bool, None, None, None),
        "duration_weeks": (int, None, 0, None),
    }
    for key, (kind, allowed, minimum, maximum) in scalar_rules.items():
        if key in context and not _validate_node(
            context[key],
            value_type=kind,
            allowed=allowed,
            minimum=minimum,
            maximum=maximum,
        ):
            violations.append(f"context.{key}")
    for key in CONTEXT_LISTS:
        if key in context and not _validate_list_node(context[key]):
            violations.append(f"context.{key}")

    clinical = payload.get("clinical")
    clinical_keys = {"lesion_types", "inflammation_level", "lesion_distribution"}
    if clinical is not None:
        if not isinstance(clinical, Mapping) or set(clinical) != clinical_keys:
            violations.append("clinical")
            clinical = {}
        if "lesion_types" in clinical and not _validate_list_node(
            clinical["lesion_types"], allowed=_LESION
        ):
            violations.append("clinical.lesion_types")
        if "inflammation_level" in clinical and not _validate_node(
            clinical["inflammation_level"], value_type=str, allowed=_INFLAMMATION
        ):
            violations.append("clinical.inflammation_level")
        if "lesion_distribution" in clinical and not _validate_list_node(
            clinical["lesion_distribution"], allowed=_DISTRIBUTION
        ):
            violations.append("clinical.lesion_distribution")
    return violations


def _is_parse_failure(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, json.JSONDecodeError):
            return True
        message = str(current).casefold()
        if "does not contain a json object" in message or "empty non-text" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    interpolated = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(interpolated, 2)


def _matched_list_counts(
    gold: Sequence[str], pred: Sequence[str], *, fuzzy: bool
) -> tuple[int, int, int]:
    unmatched = list(gold)
    true_positive = 0
    for predicted in pred:
        match_index: int | None = None
        if predicted in unmatched:
            match_index = unmatched.index(predicted)
        elif fuzzy and unmatched:
            hit = best_match(predicted, tuple(unmatched))
            if hit is not None and hit.similarity >= FUZZY_THRESHOLD:
                match_index = unmatched.index(hit.canonical)
        if match_index is not None:
            true_positive += 1
            unmatched.pop(match_index)
    return true_positive, len(pred) - true_positive, len(unmatched)


_EMPTY = (None, "unknown", "", "none_specified")


def _is_empty(value: Any) -> bool:
    """'Không khai' — gộp null, chuỗi rỗng, 'unknown' và list rỗng làm một."""
    if isinstance(value, (list, tuple, set)):
        return not value
    return value in _EMPTY


def _accuracy_one(gold: Sequence[Any], pred: Sequence[Any]) -> dict[str, Any]:
    """Accuracy một field, KÈM mốc so sánh để biết con số đó có nghĩa không.

    Vì sao không in accuracy trần: tập val lệch rất nặng về "không khai".
    `context.is_pregnant` có 96,0% đáp án rỗng, nên một model luôn trả null đã
    được 0.960; model thật được 0.9632. Toàn bộ năng lực thật của nó ở field này
    là +0.003 — mà đây là field quyết định chống chỉ định isotretinoin.

    Bốn con số dưới đây tách được điều đó:
      `baseline_luon_doan_pho_bien`  đoán mãi một giá trị phổ biến nhất thì được
                                     bao nhiêu. Đây là sàn, không phải 0.
      `lift`                         accuracy trừ sàn = phần model thật sự kiếm.
      `accuracy_khi_co_khai`         chỉ tính các dòng người dùng CÓ khai. Đây
                                     mới là "trích đúng không".
      `bo_trong`                     có khai mà model trả rỗng. Khác hẳn trích sai.
    """
    pairs = [(g, p) for g, p in zip(gold, pred)]
    n = len(pairs)
    if not n:
        return {"n": 0}

    def eq(g: Any, p: Any) -> bool:
        if isinstance(g, (list, tuple, set)) or isinstance(p, (list, tuple, set)):
            try:
                return set(map(str, g or ())) == set(map(str, p or ()))
            except TypeError:
                return False
        return g == p

    correct = sum(eq(g, p) for g, p in pairs)
    # Sàn: luôn đoán một giá trị cố định. Dùng chính giá trị phổ biến nhất trong
    # đáp án — sàn cao nhất mà một model rỗng tuếch có thể đạt.
    freq = Counter(
        "∅" if _is_empty(g) else str(g) for g, _ in pairs
    )
    baseline = freq.most_common(1)[0][1] / n

    khai = [(g, p) for g, p in pairs if not _is_empty(g)]
    accuracy = round(correct / n, 4)
    return {
        "n": n,
        "accuracy": accuracy,
        "ty_le_khong_khai": round(1 - len(khai) / n, 4),
        "baseline_luon_doan_pho_bien": round(baseline, 4),
        "lift": round(accuracy - baseline, 4),
        "n_co_khai": len(khai),
        "accuracy_khi_co_khai": (
            round(sum(eq(g, p) for g, p in khai) / len(khai), 4) if khai else None
        ),
        "bo_trong": sum(1 for g, p in khai if _is_empty(p)),
        # Dưới 30 dòng có khai thì khoảng tin cậy rộng tới mức không phân biệt
        # nổi model tốt với model tung đồng xu — xem lại chính lý do bộ probe
        # mức độ ra đời. In cờ này để không ai trích số ra ngoài mà quên.
        "du_co_mau": len(khai) >= 30,
    }


def _field_accuracy(
    scalar_gold: Mapping[str, list[Any]],
    scalar_pred: Mapping[str, list[Any]],
    list_gold: Mapping[str, list[Any]],
    list_pred: Mapping[str, list[Any]],
) -> dict[str, Any]:
    """Bảng accuracy cho MỌI field, scalar lẫn list, cùng một cách đọc.

    `list_prf` cũ chỉ có P/R/F1 theo phần tử nên không trả lời được "trích đúng
    trọn cả list bao nhiêu lần". Ở đây list dùng khớp TẬP: đúng hết mới tính đúng.
    """
    out: dict[str, Any] = {}
    for field, values in scalar_gold.items():
        out[field] = {"kieu": "scalar", **_accuracy_one(values, scalar_pred.get(field, []))}
    for field, values in list_gold.items():
        out[field] = {"kieu": "list", **_accuracy_one(values, list_pred.get(field, []))}
    return out


def _severity_metrics(
    gold: Sequence[Any], pred: Sequence[Any]
) -> dict[str, Any]:
    """Phân tầng mức độ — con số RIÊNG, vì accuracy chung đang nói dối.

    `clinical.inflammation_level` accuracy 0.9105 nghe rất tốt, nhưng 85,5% đáp
    án trong tập val là None/unknown: chỉ cần biết im lặng là đã ~0.855. Năng lực
    phân biệt nhẹ/vừa/nặng thật ra đo trên vài chục dòng và bị chôn trong con số
    chung.

    Nên ở đây tính RIÊNG trên các dòng CÓ nhãn bậc thật, cộng thêm hai thứ mà
    accuracy không thấy:

      `ha_bac`  — đoán nhẹ hơn thực tế. Sai một chiều và nguy hiểm: hạ một ca
                  severe xuống mild là bỏ lỡ chỉ định đi khám. Nâng bậc chỉ thừa.
      `bo_trong`— có nhãn thật nhưng model trả unknown/None. Không sai nhưng
                  cũng không dùng được, và nó chính là thứ đang thổi phồng 0.91.
    """
    from evaluation.severity import ORDER, is_downgrade

    graded = [(g, p) for g, p in zip(gold, pred) if g in ORDER]
    if not graded:
        return {"n_co_nhan_bac": 0, "ghi_chu": "tập không có dòng nào gán bậc thật"}

    downgrades = [(g, p) for g, p in graded if is_downgrade(g, p)]
    return {
        "n_co_nhan_bac": len(graded),
        "accuracy_tren_dong_co_bac": round(
            sum(g == p for g, p in graded) / len(graded), 4
        ),
        "ha_bac": len(downgrades),
        "ty_le_ha_bac": round(len(downgrades) / len(graded), 4),
        "ha_bac_chi_tiet": dict(
            sorted(Counter(f"{g}->{p}" for g, p in downgrades).items())
        ),
        "bo_trong": sum(1 for g, p in graded if p not in ORDER),
        "phan_bo_nhan": dict(sorted(Counter(g for g, _ in graded).items())),
        # Dưới 30 dòng mỗi bậc thì mọi kết luận về phân tầng chỉ là giai thoại.
        "du_co_mau": all(
            Counter(g for g, _ in graded).get(level, 0) >= 30 for level in ORDER
        ),
    }


def _per_value_metrics(
    scalar_gold: Mapping[str, Sequence[Any]],
    scalar_pred: Mapping[str, Sequence[Any]],
    list_gold: Mapping[str, Sequence[Sequence[str]]],
    list_pred: Mapping[str, Sequence[Sequence[str]]],
) -> dict[str, Any]:
    """PRF cho TỪNG GIÁ TRỊ enum, không chỉ từng field.

    Vì sao cần: `skin_type` được F1 0.72 không cho biết nên sửa gì. Có thể model
    nhận ra "da dầu" rất tốt nhưng mù với "da hỗn hợp" — hai chẩn đoán khác nhau,
    hai cách sửa khác nhau. Chỉ số theo field gộp chúng lại thành một con số.

    `support` là số lần giá trị đó XUẤT HIỆN TRONG ĐÁP ÁN. Support nhỏ thì F1
    không đọc được — 1 mẫu mà trúng là 1.0, trượt là 0.0.
    """
    out: dict[str, Any] = {}

    def add(field: str, pairs: list[tuple[Any, Any]]) -> None:
        # Model hỏng có thể trả list ở chỗ đáng lẽ là scalar -> unhashable, vỡ
        # set(). Chỉ gom giá trị enum hợp lệ; dự đoán dị dạng vẫn được đếm là
        # SAI qua nhánh fp/fn bên dưới, không bị bỏ qua lặng lẽ.
        values = {v for g, p in pairs for v in (g, p)
                  if isinstance(v, (str, int, float, bool))}
        if not values:
            return
        rows = {}
        for value in sorted(values, key=str):
            tp = sum(1 for g, p in pairs if g == value and p == value)
            fp = sum(1 for g, p in pairs if g != value and p == value)
            fn = sum(1 for g, p in pairs if g == value and p != value)
            rows[str(value)] = {"support": tp + fn, **_prf(tp, fp, fn)}
        out[field] = rows

    for field, gold_values in scalar_gold.items():
        add(field, list(zip(gold_values, scalar_pred[field])))

    for field, gold_rows in list_gold.items():
        # List: mỗi giá trị enum là một bài toán nhị phân "có mặt / không có mặt".
        pairs: list[tuple[Any, Any]] = []
        for gold, pred in zip(gold_rows, list_pred[field]):
            gset, pset = set(gold or []), set(pred or [])
            for value in gset | pset:
                pairs.append((value if value in gset else None,
                              value if value in pset else None))
        add(field, pairs)
    return out


def _extraction_metrics(
    scalar_gold: Mapping[str, Sequence[Any]],
    scalar_pred: Mapping[str, Sequence[Any]],
    list_gold: Mapping[str, Sequence[Sequence[str]]],
    list_pred: Mapping[str, Sequence[Sequence[str]]],
) -> dict[str, Any]:
    per_field: dict[str, dict[str, Any]] = {}
    total_tp = total_fp = total_fn = 0
    hallucinated_fields = predicted_fields = 0

    for field, gold_values in scalar_gold.items():
        tp = fp = fn = 0
        for gold, pred in zip(gold_values, scalar_pred[field]):
            if pred is not None:
                predicted_fields += 1
                hallucinated_fields += gold is None
            if gold is None and pred is None:
                continue
            if gold == pred:
                tp += 1
            else:
                fp += pred is not None
                fn += gold is not None
        per_field[field] = {"match": "exact", **_prf(tp, fp, fn)}
        total_tp += tp
        total_fp += fp
        total_fn += fn

    for field, gold_rows in list_gold.items():
        tp = fp = fn = 0
        fuzzy = field in FUZZY_FIELDS
        for gold, pred in zip(gold_rows, list_pred[field]):
            if pred:
                predicted_fields += 1
                hallucinated_fields += not gold
            row_tp, row_fp, row_fn = _matched_list_counts(gold, pred, fuzzy=fuzzy)
            tp += row_tp
            fp += row_fp
            fn += row_fn
        per_field[field] = {"match": "fuzzy" if fuzzy else "exact", **_prf(tp, fp, fn)}
        total_tp += tp
        total_fp += fp
        total_fn += fn

    macro = {
        metric: round(
            sum(float(values[metric]) for values in per_field.values()) / len(per_field),
            4,
        )
        for metric in ("precision", "recall", "f1")
    }
    return {
        "per_field": per_field,
        "micro": _prf(total_tp, total_fp, total_fn),
        "macro": macro,
        "hallucinated_field_rate": _ratio(hallucinated_fields, predicted_fields),
        "hallucinated_fields": hallucinated_fields,
        "predicted_fields": predicted_fields,
        "fuzzy_threshold": FUZZY_THRESHOLD,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no rows")
    return rows


def _current_text(record: Mapping[str, Any]) -> str:
    messages = record.get("messages")
    if isinstance(messages, list):
        users = [
            item.get("content")
            for item in messages
            if isinstance(item, Mapping) and item.get("role") == "user"
        ]
        if users and isinstance(users[-1], str):
            return users[-1].strip()
    text = record.get("text")
    return text.strip() if isinstance(text, str) else ""


def _gold_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("held-out row must use chat messages with a gold assistant payload")
    users = [item for item in messages if isinstance(item, Mapping) and item.get("role") == "user"]
    if len(users) != 1:
        raise ValueError("not a single-turn row")
    assistants = [
        item for item in messages if isinstance(item, Mapping) and item.get("role") == "assistant"
    ]
    if not assistants or not isinstance(assistants[-1].get("content"), str):
        raise ValueError("missing gold assistant payload")
    payload = json.loads(assistants[-1]["content"])
    if not isinstance(payload, dict):
        raise ValueError("gold assistant payload must be an object")
    return payload


def _normalized_texts(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {text.casefold() for row in rows if (text := _current_text(row))}


def enforce_no_train_overlap(
    eval_rows: Sequence[Mapping[str, Any]],
    train_rows: Sequence[Mapping[str, Any]],
) -> None:
    overlap = _normalized_texts(eval_rows) & _normalized_texts(train_rows)
    if overlap:
        examples = sorted(overlap)[:3]
        raise RuntimeError(
            f"eval/train exact-text overlap detected: {len(overlap)} row(s); "
            f"examples={examples}"
        )


def _section(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _node_value(section: Mapping[str, Any], key: str) -> Any:
    node = section.get(key)
    return node.get("value") if isinstance(node, Mapping) else node


def _node_confidence(node: Any) -> float | None:
    value = node.get("confidence") if isinstance(node, Mapping) else None
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    ):
        return float(value)
    return None


def _enum_value(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _list_values(section: Mapping[str, Any], key: str) -> list[str]:
    raw = section.get(key)
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        value = item.get("value") if isinstance(item, Mapping) else item
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _metric_set(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        "precision": metric["micro_precision"],
        "recall": metric["micro_recall"],
        "f1": metric["micro_f1"],
        "mean_jaccard": metric["mean_jaccard"],
        "exact_match": metric["exact_match"],
        "n": metric["n"],
    }


def _intent_metrics(gold: Sequence[str], pred: Sequence[str]) -> dict[str, Any]:
    per_class: dict[str, dict[str, Any]] = {}
    matrix = {
        label: {predicted: 0 for predicted in (*INTENT_LABELS, "__failure__")}
        for label in INTENT_LABELS
    }
    for expected, actual in zip(gold, pred):
        if expected in matrix:
            matrix[expected][actual if actual in INTENT_LABELS else "__failure__"] += 1
    for label in INTENT_LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        per_class[label] = {**_prf(tp, fp, fn), "support": tp + fn}
    return {
        "accuracy": _ratio(sum(g == p for g, p in zip(gold, pred)), len(gold)),
        "macro_f1": round(
            sum(float(per_class[label]["f1"]) for label in INTENT_LABELS)
            / len(INTENT_LABELS),
            4,
        ),
        "reject_recall": per_class["reject"]["recall"],
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def evaluate_rows(
    rows: Sequence[dict[str, Any]],
    infer: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    excluded_multiturn = 0
    failures = 0
    gold_intents: list[str] = []
    pred_intents: list[str] = []
    scalar_gold: dict[str, list[Any]] = defaultdict(list)
    scalar_pred: dict[str, list[Any]] = defaultdict(list)
    list_gold: dict[str, list[list[str]]] = defaultdict(list)
    list_pred: dict[str, list[list[str]]] = defaultdict(list)
    root_confidences: list[float] = []
    root_correct: list[bool] = []
    field_confidences: list[float] = []
    field_correct: list[bool] = []
    enum_predictions: dict[str, list[str | None]] = defaultdict(list)
    negation_pairs: list[tuple[set[str], set[str]]] = []
    canonical_pairs: list[tuple[str, str | None]] = []
    latencies_ms: list[float] = []
    schema_valid = 0
    parse_failures = 0
    schema_violations = 0
    started = time.perf_counter()

    for record in rows:
        text = _current_text(record)
        try:
            gold = _gold_payload(record)
        except ValueError as exc:
            if str(exc) == "not a single-turn row":
                excluded_multiturn += 1
                continue
            raise

        sample_id = str(record.get("id") or f"row-{len(samples) + 1}")
        error: str | None = None
        format_error: str | None = None
        inference_started = time.perf_counter()
        try:
            predicted = infer(text)
            if not isinstance(predicted, dict):
                raise TypeError("inference did not return an object")
            violations = validate_payload_schema(predicted, text)
            if violations:
                schema_violations += 1
                format_error = ", ".join(violations)
            else:
                schema_valid += 1
        except Exception as exc:
            predicted = {}
            failures += 1
            error = f"{type(exc).__name__}: {exc}"
            if _is_parse_failure(exc):
                parse_failures += 1
                format_error = "parse failure"
            else:
                schema_violations += 1
                format_error = "inference/schema failure"
        finally:
            latencies_ms.append((time.perf_counter() - inference_started) * 1_000)

        gold_intent = str(gold.get("intent") or "__missing__")
        pred_intent = str(predicted.get("intent") or "__failure__")
        gold_intents.append(gold_intent)
        pred_intents.append(pred_intent)
        enum_predictions["intent"].append(_enum_value(predicted.get("intent")))

        root_confidence = predicted.get("confidence")
        if (
            isinstance(root_confidence, (int, float))
            and not isinstance(root_confidence, bool)
            and math.isfinite(float(root_confidence))
            and 0.0 <= float(root_confidence) <= 1.0
        ):
            root_confidences.append(float(root_confidence))
            root_correct.append(pred_intent == gold_intent)

        gold_context = _section(gold, "context")
        pred_context = _section(predicted, "context")
        gold_clinical = _section(gold, "clinical")
        pred_clinical = _section(predicted, "clinical")

        for prefix, fields, gold_section, pred_section in (
            ("context", CONTEXT_SCALARS, gold_context, pred_context),
            ("clinical", CLINICAL_SCALARS, gold_clinical, pred_clinical),
        ):
            for field in fields:
                key = f"{prefix}.{field}"
                expected = _node_value(gold_section, field)
                actual = _node_value(pred_section, field)
                scalar_gold[key].append(expected)
                scalar_pred[key].append(actual)
                confidence = _node_confidence(pred_section.get(field))
                if confidence is not None:
                    field_confidences.append(confidence)
                    field_correct.append(actual == expected)

        for prefix, fields, gold_section, pred_section in (
            ("context", CONTEXT_LISTS, gold_context, pred_context),
            ("clinical", CLINICAL_LISTS, gold_clinical, pred_clinical),
        ):
            for field in fields:
                key = f"{prefix}.{field}"
                expected_values = _list_values(gold_section, field)
                actual_values = _list_values(pred_section, field)
                list_gold[key].append(expected_values)
                list_pred[key].append(actual_values)
                expected_set = set(expected_values)
                raw_nodes = pred_section.get(field)
                if isinstance(raw_nodes, list):
                    for node in raw_nodes:
                        confidence = _node_confidence(node)
                        value = node.get("value") if isinstance(node, Mapping) else node
                        if confidence is not None:
                            field_confidences.append(confidence)
                            field_correct.append(value in expected_set)

        enum_predictions["context.sex"].append(
            _enum_value(_node_value(pred_context, "sex"))
        )
        enum_predictions["context.skin_type"].append(
            _enum_value(_node_value(pred_context, "skin_type"))
        )
        enum_predictions["clinical.inflammation_level"].append(
            _enum_value(_node_value(pred_clinical, "inflammation_level"))
        )
        enum_predictions["clinical.lesion_types"].extend(
            _list_values(pred_clinical, "lesion_types")
        )
        enum_predictions["clinical.lesion_distribution"].extend(
            _list_values(pred_clinical, "lesion_distribution")
        )

        meta = record.get("meta") if isinstance(record.get("meta"), Mapping) else {}
        seed = meta.get("seed") if isinstance(meta.get("seed"), Mapping) else {}
        predicted_entities = {
            *_list_values(pred_context, "allergies"),
            *_list_values(pred_context, "current_products"),
            *_list_values(pred_context, "medications"),
        }
        stopped = seed.get("stopped_product")
        if isinstance(stopped, str) and stopped:
            negation_pairs.append(({stopped}, predicted_entities))
        canonical = seed.get("expected_canonical_product")
        if isinstance(canonical, str) and canonical:
            products = _list_values(pred_context, "current_products")
            canonical_pairs.append((canonical, canonical if canonical in products else (products[0] if products else None)))

        samples.append(
            {
                "sample_id": sample_id,
                "case_type": meta.get("case_type"),
                "ok": error is None,
                "error": error,
                "schema_valid": format_error is None,
                "format_error": format_error,
                "gold_intent": gold_intent,
                "pred_intent": pred_intent,
            }
        )

    if not samples:
        raise ValueError("no single-turn rows to evaluate")

    enum_allowed = {
        "intent": _INTENT,
        "context.sex": _SEX,
        "context.skin_type": _SKIN,
        "clinical.inflammation_level": _INFLAMMATION,
        "clinical.lesion_types": _LESION,
        "clinical.lesion_distribution": _DISTRIBUTION,
    }
    fallback_rate = round(failures / len(samples), 4)
    intake_intent = _intent_metrics(gold_intents, pred_intents)
    extraction = _extraction_metrics(
        scalar_gold,
        scalar_pred,
        list_gold,
        list_pred,
    )
    extraction["per_value"] = _per_value_metrics(
        scalar_gold, scalar_pred, list_gold, list_pred
    )
    extraction["field_accuracy"] = _field_accuracy(
        scalar_gold, scalar_pred, list_gold, list_pred
    )
    extraction["severity"] = _severity_metrics(
        scalar_gold.get("clinical.inflammation_level") or [],
        scalar_pred.get("clinical.inflammation_level") or [],
    )
    return {
        "rows_input": len(rows),
        "rows_evaluated": len(samples),
        "excluded_multiturn": excluded_multiturn,
        "failures": failures,
        "fallback_rate": fallback_rate,
        "fallback_executed": False,
        "clean_measurement": fallback_rate == 0.0,
        "alert": (
            None
            if fallback_rate == 0.0
            else "FALLBACK_RATE > 0: model-path measurement is not clean"
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "metrics": {
            "format": {
                "schema_valid_rate": _ratio(schema_valid, len(samples)),
                "parse_fail_rate": _ratio(parse_failures, len(samples)),
                "schema_violation_rate": _ratio(schema_violations, len(samples)),
                "schema_valid": schema_valid,
                "parse_failures": parse_failures,
                "schema_violations": schema_violations,
                "n": len(samples),
            },
            "intent": intake_intent,
            "extraction": extraction,
            "latency": {
                "p50_ms": _percentile(latencies_ms, 0.50),
                "p95_ms": _percentile(latencies_ms, 0.95),
                "n": len(latencies_ms),
            },
            "scalar_accuracy": {
                field: round(sum(g == p for g, p in zip(values, scalar_pred[field])) / len(values), 4)
                for field, values in scalar_gold.items()
            },
            "list_prf": {
                field: _metric_set(list_prf(values, list_pred[field]))
                for field, values in list_gold.items()
            },
            "enum_validity": {
                field: enum_validity(enum_predictions[field], allowed)
                for field, allowed in enum_allowed.items()
            },
            "intent_ece": expected_calibration_error(root_confidences, root_correct),
            "field_ece": expected_calibration_error(field_confidences, field_correct),
            "negation_leak": negation_leak(negation_pairs),
            "canonicalization_hit": canonicalization_hit(canonical_pairs),
        },
        "samples": samples,
    }


def _build_model_infer(settings: Settings) -> tuple[Callable[[str], dict[str, Any]], Callable[[], None]]:
    backend = OllamaBackend(
        base_url=settings.ollama_url,
        model=settings.intake_model,
        fallback_model=None,
        num_ctx=min(settings.llm_num_ctx, 4096),
        num_predict=768,
        temperature=0.0,
        top_p=1.0,
        top_k=20,
        repeat_penalty=1.0,
        repeat_last_n=64,
        keep_alive=settings.llm_keep_alive,
        timeout=settings.intake_timeout,
        health_timeout=settings.ollama_health_timeout,
        use_modelfile_system=True,
    )
    intake = UnifiedIntake(
        backend,
        model=settings.intake_model,
        timeout=settings.intake_timeout,
    )

    def infer(text: str) -> dict[str, Any]:
        # Explicitly invalidate the production one-turn cache before every row.
        intake._cache_key = None
        intake._cache_value = None
        prepared = prepare_user_text(text)
        return intake._infer(prepared.clean_text, [])

    return infer, intake.close


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DEFAULT_EVAL))
    parser.add_argument("--train", default=str(DEFAULT_TRAIN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=0, help="0 = all held-out rows")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    return args


def _print_tables(report: Mapping[str, Any]) -> None:
    """In bảng đọc ngay, khỏi mở JSON."""
    metrics = report.get("metrics") or {}
    intent = metrics.get("intent") or {}
    extraction = metrics.get("extraction") or {}

    print(f"\n{'INTENT':22}{'P':>8}{'R':>8}{'F1':>8}{'support':>9}")
    for label, values in sorted((intent.get("per_label") or {}).items()):
        print(f"  {label:20}{values.get('precision', 0):>8.3f}"
              f"{values.get('recall', 0):>8.3f}{values.get('f1', 0):>8.3f}"
              f"{values.get('support', 0):>9}")
    print(f"  {'macro-F1':20}{'':>8}{'':>8}{intent.get('macro_f1', 0):>8.3f}")
    if intent.get("reject_recall") is not None:
        print(f"  {'reject_recall':20}{'':>8}{intent['reject_recall']:>8.3f}")

    fields = extraction.get("field_accuracy") or {}
    if fields:
        print(f"\n{'FIELD':32}{'acc':>7}{'sàn':>7}{'lift':>7}"
              f"{'khi có khai':>13}{'n khai':>8}{'trống':>7}")
        for name, data in sorted(fields.items(), key=lambda kv: kv[1].get("lift", 0)):
            khi = data.get("accuracy_khi_co_khai")
            flag = "" if data.get("du_co_mau") else "  ⚠ ít mẫu"
            print(f"  {name:30}{data.get('accuracy', 0):>7.3f}"
                  f"{data.get('baseline_luon_doan_pho_bien', 0):>7.3f}"
                  f"{data.get('lift', 0):>+7.3f}"
                  f"{(f'{khi:.3f}' if khi is not None else '—'):>13}"
                  f"{data.get('n_co_khai', 0):>8}{data.get('bo_trong', 0):>7}{flag}")
        print("\n  sàn = luôn đoán một giá trị phổ biến nhất. lift = acc − sàn.")
        print("  lift gần 0 nghĩa là accuracy đến từ việc đoán 'không khai', "
              "không phải từ năng lực trích.")

    sev = extraction.get("severity") or {}
    if sev.get("n_co_nhan_bac"):
        print(f"\nPHÂN TẦNG MỨC ĐỘ  ({sev['n_co_nhan_bac']} dòng có bậc thật)")
        print(f"  accuracy          {sev.get('accuracy_tren_dong_co_bac', 0):.3f}")
        print(f"  hạ bậc            {sev.get('ha_bac', 0)} "
              f"({sev.get('ty_le_ha_bac', 0):.1%})  ← đoán NHẸ hơn thực tế")
        for pair, count in (sev.get("ha_bac_chi_tiet") or {}).items():
            print(f"      {pair:24}{count}")
        print(f"  bỏ trống          {sev.get('bo_trong', 0)}")
        print(f"  phân bố nhãn      {sev.get('phan_bo_nhan')}")
        if not sev.get("du_co_mau"):
            print("  ⚠ chưa đủ 30 dòng mỗi bậc — khoảng tin cậy quá rộng để kết luận")

    print(f"\n{'FIELD':30}{'khớp':>7}{'P':>8}{'R':>8}{'F1':>8}")
    for field, values in sorted((extraction.get("per_field") or {}).items()):
        print(f"  {field:28}{str(values.get('match', '')):>7}"
              f"{values.get('precision', 0):>8.3f}"
              f"{values.get('recall', 0):>8.3f}{values.get('f1', 0):>8.3f}")
    macro = extraction.get("macro") or {}
    micro = extraction.get("micro") or {}
    print(f"  {'macro':28}{'':>7}{macro.get('precision', 0):>8.3f}"
          f"{macro.get('recall', 0):>8.3f}{macro.get('f1', 0):>8.3f}")
    print(f"  {'micro':28}{'':>7}{micro.get('precision', 0):>8.3f}"
          f"{micro.get('recall', 0):>8.3f}{micro.get('f1', 0):>8.3f}")

    per_value = extraction.get("per_value") or {}
    if not per_value:
        return
    print("\nTỪNG GIÁ TRỊ ENUM   support = số lần xuất hiện trong ĐÁP ÁN;")
    print("                    support < 5 thì F1 chỉ để tham khảo")
    for field, values in sorted(per_value.items()):
        usable = [(v, m) for v, m in values.items() if m["support"]]
        if not usable:
            continue
        print(f"\n  {field}")
        for value, m in sorted(usable, key=lambda kv: -kv[1]["support"]):
            warn = "" if m["support"] >= 5 else "   ← ít mẫu"
            print(f"    {value:32}{m['support']:>5}{m['precision']:>8.3f}"
                  f"{m['recall']:>8.3f}{m['f1']:>8.3f}{warn}")


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    dataset_path = _path(args.dataset).resolve()
    train_path = _path(args.train).resolve()
    output_path = _path(args.output).resolve()
    rows = _read_jsonl(dataset_path)
    train_rows = _read_jsonl(train_path)
    enforce_no_train_overlap(rows, train_rows)
    if args.limit:
        rows = rows[: args.limit]

    settings = Settings()
    infer, close = _build_model_infer(settings)
    try:
        result = evaluate_rows(rows, infer)
    finally:
        close()
    report = {
        "schema_version": 1,
        "mode": "single_turn_no_cache_no_fallback",
        "model": settings.intake_model,
        "dataset": str(dataset_path.relative_to(ROOT)),
        "train_overlap_guard": str(train_path.relative_to(ROOT)),
        "generated_at_epoch": int(time.time()),
        **result,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _print_tables(report)
    if report["alert"]:
        print("\n" + "!" * 88)
        print(report["alert"])
        print("!" * 88)
    print(
        json.dumps(
            {
                "model": report["model"],
                "rows_evaluated": report["rows_evaluated"],
                "excluded_multiturn": report["excluded_multiturn"],
                "fallback_rate": report["fallback_rate"],
                "intent_macro_f1": report["metrics"]["intent"]["macro_f1"],
                "output": str(output_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    main()
