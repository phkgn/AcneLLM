#!/usr/bin/env python3
"""Compare rule extraction with the dedicated LLM extractor.

The LLM mode calls the dedicated ``acne-extractor:1.5b`` adapter directly.  It
does not silently substitute rule predictions on failure, so the reported LLM
field metrics measure the model path itself. Intent metrics are compatibility
diagnostics from the deterministic legacy fallback router; production intent
routing is evaluated separately by ``eval_semantic_router.py`` and never reads
LLM extraction fields.

Usage:
    python scripts/eval_extraction.py --mode rule
    python scripts/eval_extraction.py --mode llm --limit 50
    python scripts/eval_extraction.py --mode both --json-output reports/extractor_eval.json
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acne_llm.chat.extraction_confidence import (  # noqa: E402
    ExtractionConfidence,
    extract_with_confidence,
)
from acne_llm.chat.fallback.intent_router import RouteDecision, route_intent  # noqa: E402
from acne_llm.chat.fallback.llm_extractor import LLMExtractor  # noqa: E402
from acne_llm.chat.normalizer import normalize_chat_message  # noqa: E402
from acne_llm.chat.preprocess import prepare_user_text  # noqa: E402
from acne_llm.config import Settings  # noqa: E402
from acne_llm.llm.ollama_backend import OllamaBackend  # noqa: E402


_SCALAR_FIELDS = (
    "skin_type",
    "sex",
    "age",
    "duration_weeks",
    "is_pregnant",
    "is_breastfeeding",
    "inflammation",
)
_LIST_FIELDS = (
    "lesions",
    "distribution",
    "products",
    "medications",
    "allergies",
    "scarring_signs",
    "hormonal_factors",
    "treatment_goals",
    "red_flags",
)
_SAFETY_FIELDS = (
    "is_pregnant",
    "is_breastfeeding",
    "medications",
    "allergies",
)


def _load(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"WARN: skip invalid JSONL line {line_number}: {exc}", file=sys.stderr)
    return rows


def _set_metrics(name: str, gold_sets: list, pred_sets: list) -> dict:
    """Micro precision/recall/F1 for singleton scalar or list-valued labels."""
    tp = fp = fn = 0
    for gold, pred in zip(gold_sets, pred_sets):
        gold_set = set(gold or [])
        pred_set = set(pred or [])
        tp += len(gold_set & pred_set)
        fp += len(pred_set - gold_set)
        fn += len(gold_set - pred_set)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "field": name,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _scalar_accuracy(gold: list, pred: list) -> float:
    return round(sum(g == p for g, p in zip(gold, pred)) / len(gold), 4) if gold else 0.0


def _norm_inflammation(value):
    return None if value in (None, "none", "unknown") else value


def _norm_lesions(values):
    result = []
    for value in values or []:
        if value == "other":
            continue
        result.append("closed_comedone" if value == "hidden_acne" else value)
    return result


def _drop_other(values):
    return [value for value in (values or []) if value != "other"]


def _scalar_prediction(confidence: ExtractionConfidence, field: str):
    value = getattr(confidence, field).value
    return _norm_inflammation(value) if field == "inflammation" else value


def _list_prediction(confidence: ExtractionConfidence, field: str) -> list:
    confidence_field = "lesion_types" if field == "lesions" else field
    values = list(getattr(confidence, confidence_field).values)
    if field == "lesions":
        return _norm_lesions(values)
    if field == "distribution":
        return _drop_other(values)
    return values


def _gold_scalar(row: dict, field: str):
    value = row.get(field)
    return _norm_inflammation(value) if field == "inflammation" else value


def _gold_list(row: dict, field: str) -> list:
    values = row.get(field, [])
    if field == "lesions":
        return _norm_lesions(values)
    if field == "distribution":
        return _drop_other(values)
    return list(values or [])


def _predict_rule(text: str) -> tuple[ExtractionConfidence, RouteDecision]:
    prepared = prepare_user_text(text)
    user = normalize_chat_message(
        text,
        mode="llm_only",
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )
    confidence = extract_with_confidence(
        text,
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )
    route = route_intent(
        prepared.clean_text,
        user,
        [],
        current_clinical=user.clinical,
    )
    return confidence, route


def _predict_llm(
    text: str,
    extractor: LLMExtractor,
    route_field_threshold: float,
) -> tuple[ExtractionConfidence, RouteDecision]:
    prepared = prepare_user_text(text)
    result = extractor.run(
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
        mode="llm_only",
        history=[],
    )
    # Router-first runtime never feeds LLM fields to routing. Keep this legacy
    # intent diagnostic text-only as well; ``route_field_threshold`` remains in
    # the CLI/report contract for backward compatibility.
    del route_field_threshold
    user_for_routing = normalize_chat_message(
        text,
        mode="llm_only",
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )
    route = route_intent(
        prepared.clean_text,
        user_for_routing,
        [],
        current_clinical=user_for_routing.clinical,
    )
    return result.confidence, route


def _make_llm_extractor(args) -> LLMExtractor:
    settings = Settings()
    model = args.extractor_model or settings.extractor_model
    timeout = args.extractor_timeout or settings.extractor_timeout
    backend = OllamaBackend(
        base_url=settings.ollama_url,
        model=model,
        fallback_model=None,
        num_ctx=min(settings.llm_num_ctx, 4096),
        num_predict=512,
        temperature=0.0,
        top_p=0.9,
        top_k=20,
        repeat_penalty=1.05,
        repeat_last_n=64,
        keep_alive=settings.llm_keep_alive,
        timeout=timeout,
        health_timeout=settings.ollama_health_timeout,
        use_modelfile_system=True,
    )
    return LLMExtractor(backend, model=model, timeout=timeout)


def _evaluate_mode(
    mode: str,
    rows: list[dict],
    *,
    extractor: LLMExtractor | None,
    show_errors: bool,
    progress_every: int,
    workers: int,
    route_field_threshold: float,
) -> dict:
    gold_scalar: dict[str, list] = defaultdict(list)
    pred_scalar: dict[str, list] = defaultdict(list)
    gold_list: dict[str, list] = defaultdict(list)
    pred_list: dict[str, list] = defaultdict(list)
    intent_gold: list[str] = []
    intent_pred: list[str | None] = []
    errors: list[dict] = []
    failures = 0
    started = time.perf_counter()

    def safe_prediction(row: dict) -> tuple[ExtractionConfidence, RouteDecision | None, str | None]:
        text = row.get("text", "")
        try:
            if not text:
                raise ValueError("empty text")
            if mode == "llm":
                if extractor is None:
                    raise RuntimeError("LLM extractor was not initialized")
                confidence, route = _predict_llm(
                    text,
                    extractor,
                    route_field_threshold,
                )
            else:
                confidence, route = _predict_rule(text)
            return confidence, route, None
        except Exception as exc:
            # Deliberately do not substitute rule predictions in LLM eval.
            return ExtractionConfidence(), None, f"{type(exc).__name__}: {exc}"

    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    predictions = executor.map(safe_prediction, rows) if executor else map(safe_prediction, rows)
    try:
        for index, (row, prediction) in enumerate(zip(rows, predictions), 1):
            confidence, route, error = prediction
            if error:
                failures += 1

            for field in _SCALAR_FIELDS:
                gold = _gold_scalar(row, field)
                pred = _scalar_prediction(confidence, field)
                gold_scalar[field].append(gold)
                pred_scalar[field].append(pred)
            for field in _LIST_FIELDS:
                gold = _gold_list(row, field)
                pred = _list_prediction(confidence, field)
                gold_list[field].append(gold)
                pred_list[field].append(pred)

            gold_intent = row.get("intent")
            if gold_intent:
                intent_gold.append(gold_intent)
                intent_pred.append(route.primary_intent if route else None)

            if show_errors and (
                error
                or (gold_intent and (route is None or route.primary_intent != gold_intent))
            ):
                errors.append(
                    {
                        "index": index - 1,
                        "text": row.get("text", "")[:160],
                        "error": error,
                        "gold_intent": gold_intent,
                        "pred_intent": route.primary_intent if route else None,
                    }
                )

            if progress_every and index % progress_every == 0:
                elapsed = time.perf_counter() - started
                print(
                    f"[{mode}] {index}/{len(rows)} rows | failures={failures} | {elapsed:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        if executor is not None:
            executor.shutdown(wait=True)

    scalar_metrics: dict[str, dict] = {}
    for field in _SCALAR_FIELDS:
        singleton_gold = [[value] if value is not None else [] for value in gold_scalar[field]]
        singleton_pred = [[value] if value is not None else [] for value in pred_scalar[field]]
        metric = _set_metrics(field, singleton_gold, singleton_pred)
        metric["accuracy"] = _scalar_accuracy(gold_scalar[field], pred_scalar[field])
        scalar_metrics[field] = metric

    list_metrics = {
        field: _set_metrics(field, gold_list[field], pred_list[field])
        for field in _LIST_FIELDS
    }
    intent_total = len(intent_gold)
    intent_metrics = {
        "primary_intent_accuracy": round(
            sum(gold == pred for gold, pred in zip(intent_gold, intent_pred)) / intent_total,
            4,
        )
        if intent_total
        else 0.0,
        "labeled_primary_intent": intent_total,
    }
    return {
        "mode": mode,
        "rows": len(rows),
        "failures": failures,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "intent_pipeline": (
            "rule_on_confidence_gated_llm_fields" if mode == "llm" else "rule_fields"
        ),
        "route_field_threshold": route_field_threshold,
        "scalar": scalar_metrics,
        "list": list_metrics,
        "intent": intent_metrics,
        "errors": errors[:50],
    }


def _print_mode(result: dict) -> None:
    print("\n" + "=" * 88)
    print(
        f"MODE={result['mode'].upper()} | rows={result['rows']} | "
        f"failures={result['failures']} | elapsed={result['elapsed_seconds']:.2f}s"
    )
    print("=" * 88)
    print("\n-- Scalar: accuracy plus micro P/R/F1 (non-null value labels) --")
    for field, metric in result["scalar"].items():
        print(
            f"  {field:20s} Acc={metric['accuracy']:.3f} "
            f"P={metric['precision']:.3f} R={metric['recall']:.3f} "
            f"F1={metric['f1']:.3f}"
        )
    print("\n-- List: micro P/R/F1 --")
    for field, metric in result["list"].items():
        print(
            f"  {field:20s} P={metric['precision']:.3f} "
            f"R={metric['recall']:.3f} F1={metric['f1']:.3f} "
            f"(tp={metric['tp']} fp={metric['fp']} fn={metric['fn']})"
        )
    intent = result["intent"]
    print("\n-- Intent --")
    print(f"  primary_intent accuracy : {intent['primary_intent_accuracy']:.3f}")
    if result["errors"]:
        print(f"\n  captured error/mismatch examples: {len(result['errors'])}")


def _print_comparison(rule: dict, llm: dict) -> None:
    print("\n" + "=" * 88)
    print("LLM - RULE DELTA")
    print("=" * 88)
    for field in _SCALAR_FIELDS:
        delta = llm["scalar"][field]["f1"] - rule["scalar"][field]["f1"]
        print(f"  {field:20s} F1 delta={delta:+.3f}")
    for field in _LIST_FIELDS:
        delta = llm["list"][field]["f1"] - rule["list"][field]["f1"]
        print(f"  {field:20s} F1 delta={delta:+.3f}")
    print("\n-- Safety-field deltas (must be inspected before trusting rollout) --")
    for field in _SAFETY_FIELDS:
        section = "scalar" if field in _SCALAR_FIELDS else "list"
        delta = llm[section][field]["f1"] - rule[section][field]["f1"]
        print(f"  {field:20s} F1 delta={delta:+.3f}")
    print("\n-- Intent deltas --")
    key = "primary_intent_accuracy"
    delta = llm["intent"][key] - rule["intent"][key]
    print(f"  {key:28s} delta={delta:+.3f}")


def _default_mode() -> str:
    value = os.getenv("EXTRACTOR_MODE", "rule").strip().lower()
    return value if value in {"rule", "llm", "both"} else "rule"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default="data/golden_extraction_gen.jsonl")
    parser.add_argument("--offset", type=int, default=0, help="skip the first N rows")
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows")
    parser.add_argument("--mode", choices=("rule", "llm", "both"), default=_default_mode())
    parser.add_argument("--extractor-model", default="")
    parser.add_argument("--extractor-timeout", type=float, default=0.0)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--workers", type=int, default=1, help="parallel Ollama requests")
    parser.add_argument("--show-errors", action="store_true")
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()

    path = Path(args.golden)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        parser.error(f"golden set not found: {path}")
    rows = _load(path)
    if args.offset:
        rows = rows[max(0, args.offset) :]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        parser.error("golden set is empty")

    modes = ("rule", "llm") if args.mode == "both" else (args.mode,)
    route_field_threshold = Settings().extract_min_field_conf
    extractor = _make_llm_extractor(args) if "llm" in modes else None
    results: dict[str, dict] = {}
    try:
        for mode in modes:
            results[mode] = _evaluate_mode(
                mode,
                rows,
                extractor=extractor,
                show_errors=args.show_errors,
                progress_every=max(0, args.progress_every),
                workers=max(1, args.workers),
                route_field_threshold=route_field_threshold,
            )
            _print_mode(results[mode])
    finally:
        if extractor is not None:
            extractor.close()

    if "rule" in results and "llm" in results:
        _print_comparison(results["rule"], results["llm"])

    if args.json_output:
        output = Path(args.json_output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "golden": str(path),
                    "generated_at_epoch": int(time.time()),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON report: {output}")


if __name__ == "__main__":
    main()
