#!/usr/bin/env python3
"""Evaluate unified intake on held-out, single-turn chat records.

The model path is measured directly: the evaluator never reads the runtime
cache and never substitutes a router/extractor fallback after an inference
failure.  The default validation split is kept separate from the generated
training split by an exact-text overlap guard.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
import json
import math
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
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
from evaluation.metrics.intake import (  # noqa: E402
    canonicalization_hit,
    enum_validity,
    expected_calibration_error,
    intent_prf,
    list_prf,
    negation_leak,
)


DEFAULT_EVAL = Path("datagen/intakedata/output/intake/intake.val.jsonl")
DEFAULT_TRAIN = Path("datagen/intakedata/output/intake/intake.train.jsonl")
DEFAULT_OUTPUT = Path("reports/intake_unified_eval.json")
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
        try:
            predicted = infer(text)
            if not isinstance(predicted, dict):
                raise TypeError("inference did not return an object")
        except Exception as exc:
            predicted = {}
            failures += 1
            error = f"{type(exc).__name__}: {exc}"

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
            "intent": intent_prf(gold_intents, pred_intents),
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
