"""Generate model/latency (C) and evaluation-result (F) figure artifacts."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from evaluation.analysis.figures_common import (
    ManifestBuilder,
    configure_matplotlib,
    fresh_figure_generation,
    iter_jsonl,
    read_json,
)
from evaluation.analysis.stats import paired_bootstrap

SYSTEM_ORDER = ["s0", "s1", "s2", "s3", "s4"]
JUDGE_AXES = [
    "correctness",
    "completeness",
    "safety",
    "relevance",
    "fluency",
    "instruction_following",
]
PREREGISTERED = [("s0", "s1"), ("s0", "s2"), ("s1", "s3"), ("s2", "s3")]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _source(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _latest_report_run(root: Path) -> Path | None:
    candidates: list[tuple[int, float, Path]] = []
    reports = root / "evaluation" / "reports"
    if not reports.exists():
        return None
    for path in reports.rglob("report.json"):
        if "figures" in path.parts:
            continue
        payload = read_json(path, {})
        systems = payload.get("systems") if isinstance(payload, dict) else None
        if isinstance(systems, dict) and systems:
            candidates.append((len(systems), path.stat().st_mtime, path.parent))
    if not candidates:
        return None
    max_system_coverage = max(candidate[0] for candidate in candidates)
    complete = [
        candidate
        for candidate in candidates
        if candidate[0] == max_system_coverage
    ]
    return max(complete, key=lambda candidate: candidate[1])[2]


def _load_run(run_dir: Path | None) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    if run_dir is None:
        return {}, {}, {}
    report = read_json(run_dir / "report.json", {}) or {}
    judged: dict[str, list[dict[str, Any]]] = {}
    results: dict[str, list[dict[str, Any]]] = {}
    for system in SYSTEM_ORDER:
        judged[system] = list(iter_jsonl(run_dir / f"{system}.judged.jsonl"))
        results[system] = list(iter_jsonl(run_dir / f"{system}.results.jsonl"))
    return report, judged, results


def _attempt(
    builder: ManifestBuilder,
    *,
    figure_id: str,
    title: str,
    caption: str,
    source_data: str,
    chart_type: str,
    kind: str,
    function: Callable[[], None],
) -> None:
    try:
        function()
    except Exception as exc:  # Each figure is independently best-effort.
        builder.skip(
            figure_id=figure_id,
            title=title,
            reason=f"{type(exc).__name__}: {exc}",
            caption=caption,
            source_data=source_data,
            chart_type=chart_type,
            kind=kind,
        )


def _pointwise_rows(judged: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, dict[str, float]]]:
    out: dict[str, dict[str, dict[str, float]]] = {}
    for system, rows in judged.items():
        by_sample: dict[str, dict[str, float]] = {}
        for row in rows:
            sample_id = str(row.get("sample_id") or "")
            pointwise = row.get("pointwise")
            if not sample_id or not isinstance(pointwise, dict):
                continue
            by_sample[sample_id] = {
                axis: float(pointwise[axis])
                for axis in JUDGE_AXES
                if isinstance(pointwise.get(axis), (int, float))
            }
        out[system] = by_sample
    return out


def _f1_judge_axes(
    builder: ManifestBuilder,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    pointwise = _pointwise_rows(judged)
    rows: list[dict[str, Any]] = []
    for system in SYSTEM_ORDER:
        system_row: dict[str, Any] = {"system": system.upper()}
        for axis in JUDGE_AXES:
            values = [
                scores[axis]
                for scores in pointwise.get(system, {}).values()
                if axis in scores
            ]
            if values:
                stats = paired_bootstrap(
                    values,
                    [0.0] * len(values),
                    n_resamples=2_000,
                    seed=42,
                )
                value = float(stats["mean_diff"])
                low, high = stats["ci95"]
                system_row[axis] = value
                system_row[f"{axis}_error"] = [
                    round(value - float(low), 6),
                    round(float(high) - value, 6),
                ]
        rows.append(system_row)
    if not any(any(axis in row for axis in JUDGE_AXES) for row in rows):
        raise ValueError("No pointwise judge scores found.")
    builder.add_chart(
        figure_id="f1_judge_axes",
        title="S0–S4 judge axes with bootstrap CI",
        chart_type="bar",
        payload={
            "data": rows,
            "x_key": "system",
            "x_label": "System",
            "y_label": "Judge score (1–5)",
            "domain": [0, 5],
            "series": [
                {
                    "key": axis,
                    "label": axis.replace("_", " ").title(),
                    "error_key": f"{axis}_error",
                }
                for axis in JUDGE_AXES
            ],
        },
        caption="Mean pointwise judge score; error bars are 95% bootstrap confidence intervals.",
        source_data="*.judged.jsonl",
    )


def _f2_forest(
    builder: ManifestBuilder,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    pointwise = _pointwise_rows(judged)
    estimates: list[tuple[str, float, float, float]] = []
    for left, right in PREREGISTERED:
        left_rows = pointwise.get(left, {})
        right_rows = pointwise.get(right, {})
        common = sorted(set(left_rows) & set(right_rows))
        a = [left_rows[sample]["correctness"] for sample in common if "correctness" in left_rows[sample] and "correctness" in right_rows[sample]]
        b = [right_rows[sample]["correctness"] for sample in common if "correctness" in left_rows[sample] and "correctness" in right_rows[sample]]
        if not a:
            continue
        stats = paired_bootstrap(b, a, n_resamples=5_000, seed=42)
        estimates.append(
            (
                f"{right.upper()} − {left.upper()}",
                float(stats["mean_diff"]),
                float(stats["ci95"][0]),
                float(stats["ci95"][1]),
            )
        )
    if not estimates:
        raise ValueError("No paired correctness scores for pre-registered comparisons.")
    plt = configure_matplotlib()
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    positions = list(range(len(estimates)))
    values = [item[1] for item in estimates]
    low = [item[1] - item[2] for item in estimates]
    high = [item[3] - item[1] for item in estimates]
    ax.errorbar(values, positions, xerr=[low, high], fmt="o", capsize=4)
    ax.axvline(0, color="#666666", linewidth=1)
    ax.set_yticks(positions, [item[0] for item in estimates])
    ax.set_xlabel("Δ mean correctness (95% bootstrap CI)")
    ax.set_title("Pre-registered paired comparisons")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    builder.add_png(
        figure_id="f2_preregistered_forest",
        title="Pre-registered correctness effects",
        fig=fig,
        caption="Positive values favor the system shown first in each contrast.",
        source_data="*.judged.jsonl",
        chart_type="forest",
    )


def _latest_retrieval_summary(root: Path) -> Path | None:
    paths = list((root / "evaluation" / "reports" / "retrieval").glob("*/summary.json"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def _f3_retrieval_curves(builder: ManifestBuilder, root: Path) -> None:
    summary_path = _latest_retrieval_summary(root)
    if summary_path is None:
        raise ValueError("No retrieval summary.json found.")
    summary = read_json(summary_path, {}) or {}
    modes = summary.get("modes")
    if not isinstance(modes, dict) or not modes:
        raise ValueError("Retrieval summary has no modes.")
    ks = sorted(
        {
            int(match.group(1))
            for metrics in modes.values()
            if isinstance(metrics, dict)
            for key in metrics
            if (match := re.fullmatch(r"(?:hit|recall)@(\d+)", str(key)))
        }
    )
    rows: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    for k in ks:
        row: dict[str, Any] = {"k": k}
        for mode, metrics in modes.items():
            if not isinstance(metrics, dict):
                continue
            for metric in ("hit", "recall"):
                key = f"{mode}_{metric}"
                value = metrics.get(f"{metric}@{k}")
                if isinstance(value, (int, float)):
                    row[key] = float(value)
        rows.append(row)
    for mode in modes:
        for metric in ("hit", "recall"):
            key = f"{mode}_{metric}"
            if any(key in row for row in rows):
                series.append(
                    {
                        "key": key,
                        "label": f"{mode} {metric}@k",
                    }
                )
    if not rows or not series:
        raise ValueError("No hit@k or recall@k metrics found.")
    builder.add_chart(
        figure_id="f3_retrieval_curves",
        title="Retrieval hit@k and recall@k",
        chart_type="line",
        payload={
            "data": rows,
            "x_key": "k",
            "x_label": "k",
            "y_label": "Rate",
            "domain": [0, 1],
            "series": series,
        },
        caption="Latest T2 retrieval summary, separated by retrieval mode.",
        source_data=_source(root, summary_path),
    )


def _task_type_map(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    datasets = root / "evaluation" / "datasets" / "v1"
    for path in datasets.glob("*.jsonl"):
        for row in iter_jsonl(path):
            sample_id = str(row.get("sample_id") or "")
            task_type = str(
                row.get("task_type")
                or row.get("case_type")
                or row.get("risk_level")
                or "unknown"
            )
            if sample_id:
                mapping.setdefault(sample_id, task_type)
    return mapping


def _f4_task_heatmap(
    builder: ManifestBuilder,
    root: Path,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    task_types = _task_type_map(root)
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for system, rows in judged.items():
        for row in rows:
            sample_id = str(row.get("sample_id") or "")
            pointwise = row.get("pointwise")
            if not isinstance(pointwise, dict) or not isinstance(pointwise.get("correctness"), (int, float)):
                continue
            buckets[(task_types.get(sample_id, "unknown"), system)].append(
                float(pointwise["correctness"])
            )
    task_order = sorted({task for task, _ in buckets})
    systems = [system for system in SYSTEM_ORDER if any((task, system) in buckets for task in task_order)]
    if not task_order or not systems:
        raise ValueError("No task_type × system correctness data.")
    cells = [
        {
            "row": task,
            "column": system.upper(),
            "value": round(mean(buckets[(task, system)]), 4),
            "n": len(buckets[(task, system)]),
        }
        for task in task_order
        for system in systems
        if buckets[(task, system)]
    ]
    builder.add_chart(
        figure_id="f4_task_system_heatmap",
        title="Correctness by task type and system",
        chart_type="heatmap",
        payload={
            "rows": task_order,
            "columns": [system.upper() for system in systems],
            "cells": cells,
            "value_label": "Mean correctness",
            "domain": [1, 5],
        },
        caption="Mean judge correctness for each task-type/system cell.",
        source_data="evaluation/datasets/v1/*.jsonl + *.judged.jsonl",
    )


def _f5_error_pareto(
    builder: ManifestBuilder,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    counts: dict[str, Counter[str]] = {system: Counter() for system in SYSTEM_ORDER}
    for system, rows in judged.items():
        for row in rows:
            error_class = row.get("error_class")
            codes: list[str] = []
            if isinstance(error_class, dict):
                raw_codes = error_class.get("codes")
                if isinstance(raw_codes, list):
                    codes.extend(str(code) for code in raw_codes if code)
                elif error_class.get("primary_code"):
                    codes.append(str(error_class["primary_code"]))
            if not codes:
                pointwise = row.get("pointwise")
                if isinstance(pointwise, dict) and isinstance(pointwise.get("violated_criteria"), list):
                    codes.extend(
                        f"judge:{value}"
                        for value in pointwise["violated_criteria"]
                        if value
                    )
            counts[system].update(codes)
    totals = Counter(
        {
            code: sum(counts[system][code] for system in SYSTEM_ORDER)
            for code in {code for counter in counts.values() for code in counter}
        }
    )
    top_codes = [code for code, _ in totals.most_common(15)]
    if not top_codes:
        raise ValueError("No error codes or violated criteria found.")
    data = [
        {
            "error": code,
            **{system: counts[system][code] for system in SYSTEM_ORDER},
            "total": totals[code],
        }
        for code in top_codes
    ]
    builder.add_chart(
        figure_id="f5_error_pareto",
        title="Error Pareto by system",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "error",
            "x_label": "Error code / violated criterion",
            "y_label": "Cases",
            "series": [
                {"key": system, "label": system.upper(), "stack": "systems"}
                for system in SYSTEM_ORDER
                if any(row.get(system) for row in data)
            ],
        },
        caption="Top error categories, stacked by system and ordered by total frequency.",
        source_data="*.judged.jsonl",
    )


def _f6_normalizer(builder: ManifestBuilder, root: Path) -> None:
    path = root / "evaluation" / "reports" / "unit" / "normalizer" / "report.json"
    report = read_json(path, {}) or {}
    multi = report.get("multi_label")
    if not isinstance(multi, dict):
        raise ValueError("Normalizer report has no multi_label section.")
    data = [
        {
            "field": str(field),
            "f1": float(metrics["micro_f1"]),
            "macro_f1": float(metrics.get("macro_f1") or 0),
        }
        for field, metrics in multi.items()
        if isinstance(metrics, dict) and isinstance(metrics.get("micro_f1"), (int, float))
    ]
    if not data:
        raise ValueError("No normalizer F1 metrics found.")
    builder.add_chart(
        figure_id="f6_normalizer_f1",
        title="Normalizer per-field F1",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "field",
            "x_label": "Field",
            "y_label": "F1",
            "domain": [0, 1],
            "series": [
                {"key": "f1", "label": "Micro F1"},
                {"key": "macro_f1", "label": "Macro F1"},
            ],
        },
        caption="Field-level normalizer performance from the latest unit report.",
        source_data=_source(root, path),
    )


def _f7_intent_confusion(builder: ManifestBuilder, root: Path) -> None:
    path = root / "evaluation" / "reports" / "unit" / "intent_router" / "report.json"
    report = read_json(path, {}) or {}
    confusion = report.get("confusion")
    if not isinstance(confusion, dict) or not confusion:
        raise ValueError("Intent report has no confusion matrix.")
    rows = sorted(str(value) for value in confusion)
    columns = sorted(
        {
            str(predicted)
            for values in confusion.values()
            if isinstance(values, dict)
            for predicted in values
        }
    )
    cells = [
        {
            "row": actual,
            "column": predicted,
            "value": int(
                (confusion.get(actual) or {}).get(predicted, 0)
                if isinstance(confusion.get(actual), dict)
                else 0
            ),
        }
        for actual in rows
        for predicted in columns
    ]
    builder.add_chart(
        figure_id="f7_intent_confusion",
        title="Intent router confusion matrix",
        chart_type="heatmap",
        payload={
            "rows": rows,
            "columns": columns,
            "cells": cells,
            "value_label": "Cases",
        },
        caption="Gold intent on rows, predicted intent on columns.",
        source_data=_source(root, path),
    )


def _find_human_labels(root: Path) -> Path | None:
    candidates = [
        root / "evaluation" / "annotations" / "human_labels.jsonl",
        root / "annotation" / "human_labels.jsonl",
    ]
    return next((path for path in candidates if path.exists()), None)


def _human_correctness(row: dict[str, Any]) -> float | None:
    for key in ("correctness", "human_correctness", "score", "human_score"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    scores = row.get("scores")
    if isinstance(scores, dict) and isinstance(scores.get("correctness"), (int, float)):
        return float(scores["correctness"])
    return None


def _f8_human_scatter(
    builder: ManifestBuilder,
    root: Path,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    path = _find_human_labels(root)
    if path is None:
        raise ValueError("annotation/human_labels.jsonl is not available.")
    judge_lookup = {
        (system, str(row.get("sample_id") or "")): float(row["pointwise"]["correctness"])
        for system, rows in judged.items()
        for row in rows
        if isinstance(row.get("pointwise"), dict)
        and isinstance(row["pointwise"].get("correctness"), (int, float))
    }
    data: list[dict[str, Any]] = []
    for row in iter_jsonl(path):
        system = str(row.get("system_id") or row.get("system") or "")
        sample_id = str(row.get("sample_id") or "")
        human = _human_correctness(row)
        judge = judge_lookup.get((system, sample_id))
        if human is not None and judge is not None:
            data.append(
                {
                    "sample_id": sample_id,
                    "system": system.upper(),
                    "human": human,
                    "judge": judge,
                }
            )
    if len(data) < 3:
        raise ValueError("Fewer than 3 joined human/judge labels.")
    try:
        from scipy.stats import spearmanr

        rho = float(spearmanr([row["human"] for row in data], [row["judge"] for row in data]).statistic)
    except Exception:
        rho = 0.0
    builder.add_chart(
        figure_id="f8_judge_human",
        title="Judge vs human correctness",
        chart_type="scatter",
        payload={
            "data": data,
            "x_data_key": "human",
            "y_data_key": "judge",
            "group_key": "system",
            "x_label": "Human score",
            "y_label": "Judge score",
            "annotation": f"Spearman ρ = {rho:.3f}",
        },
        caption=f"Joined blind human labels and judge scores; Spearman ρ={rho:.3f}.",
        source_data=_source(root, path),
    )


def _result_lookup(results: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (system, str(row.get("sample_id") or "")): row
        for system, rows in results.items()
        for row in rows
        if row.get("sample_id")
    }


def _f9_correctness_latency(
    builder: ManifestBuilder,
    judged: dict[str, list[dict[str, Any]]],
    results: dict[str, list[dict[str, Any]]],
) -> None:
    lookup = _result_lookup(results)
    data: list[dict[str, Any]] = []
    for system, rows in judged.items():
        for row in rows:
            sample_id = str(row.get("sample_id") or "")
            pointwise = row.get("pointwise")
            result = lookup.get((system, sample_id))
            if not isinstance(pointwise, dict) or not isinstance(result, dict):
                continue
            correctness = pointwise.get("correctness")
            timings = result.get("timings_ms")
            if not isinstance(correctness, (int, float)) or not isinstance(timings, dict):
                continue
            latency = timings.get("total")
            if not isinstance(latency, (int, float)):
                continue
            answer = str(result.get("answer") or "")
            data.append(
                {
                    "sample_id": sample_id,
                    "system": system.upper(),
                    "latency_ms": float(latency),
                    "correctness": float(correctness),
                    "size": max(10, min(80, len(answer) / 20)),
                }
            )
    if not data:
        raise ValueError("No joined correctness/latency records.")
    builder.add_chart(
        figure_id="f9_correctness_latency",
        title="Correctness vs latency",
        chart_type="scatter",
        payload={
            "data": data,
            "x_data_key": "latency_ms",
            "y_data_key": "correctness",
            "group_key": "system",
            "x_label": "Total latency (ms)",
            "y_label": "Correctness",
            "size_key": "size",
        },
        caption="Each bubble is a judged case; bubble size approximates answer length.",
        source_data="*.results.jsonl + *.judged.jsonl",
    )


def _f10_distribution(
    builder: ManifestBuilder,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    values: list[list[float]] = []
    labels: list[str] = []
    for system in SYSTEM_ORDER:
        system_values = [
            float(row["pointwise"]["correctness"])
            for row in judged.get(system, [])
            if isinstance(row.get("pointwise"), dict)
            and isinstance(row["pointwise"].get("correctness"), (int, float))
        ]
        if system_values:
            values.append(system_values)
            labels.append(system.upper())
    if not values:
        raise ValueError("No correctness distributions found.")
    plt = configure_matplotlib()
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    violin = ax.violinplot(values, showmeans=False, showmedians=False, showextrema=False)
    for body in violin["bodies"]:
        body.set_alpha(0.45)
    ax.boxplot(values, widths=0.18, showfliers=True)
    ax.set_xticks(range(1, len(labels) + 1), labels)
    ax.set_ylim(0.5, 5.5)
    ax.set_ylabel("Judge correctness")
    ax.set_title("Correctness distribution by system")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    builder.add_png(
        figure_id="f10_correctness_distribution",
        title="Judge correctness distribution",
        fig=fig,
        caption="Violin density with an overlaid box plot for each system.",
        source_data="*.judged.jsonl",
        chart_type="violin",
    )


def _f11_faithfulness_correctness(
    builder: ManifestBuilder,
    judged: dict[str, list[dict[str, Any]]],
) -> None:
    data: list[dict[str, Any]] = []
    for system, rows in judged.items():
        for row in rows:
            pointwise = row.get("pointwise")
            faithfulness = row.get("faithfulness")
            if not isinstance(pointwise, dict) or not isinstance(faithfulness, dict):
                continue
            correctness = pointwise.get("correctness")
            faith = faithfulness.get("faithfulness")
            if isinstance(correctness, (int, float)) and isinstance(faith, (int, float)):
                data.append(
                    {
                        "sample_id": str(row.get("sample_id") or ""),
                        "system": system.upper(),
                        "correctness": float(correctness),
                        "faithfulness": float(faith),
                        "correct_but_unfaithful": float(correctness) >= 4 and float(faith) < 0.6,
                    }
                )
    if not data:
        raise ValueError("No cases contain both faithfulness and correctness.")
    builder.add_chart(
        figure_id="f11_faithfulness_correctness",
        title="Faithfulness vs correctness",
        chart_type="scatter",
        payload={
            "data": data,
            "x_data_key": "faithfulness",
            "y_data_key": "correctness",
            "group_key": "system",
            "x_label": "Faithfulness",
            "y_label": "Correctness",
            "domain": {"x": [0, 1], "y": [1, 5]},
            "highlight_region": {
                "x_max": 0.6,
                "y_min": 4,
                "label": "Correct but unfaithful",
            },
        },
        caption="The upper-left region flags answers judged correct despite weak grounding.",
        source_data="*.judged.jsonl",
    )


def _c3_latency_breakdown(
    builder: ManifestBuilder,
    results: dict[str, list[dict[str, Any]]],
) -> None:
    data: list[dict[str, Any]] = []
    for system in SYSTEM_ORDER:
        retrieval: list[float] = []
        generation: list[float] = []
        other: list[float] = []
        for row in results.get(system, []):
            timings = row.get("timings_ms")
            if not isinstance(timings, dict):
                continue
            retr = float(timings.get("retrieval") or 0)
            gen = float(timings.get("generation") or 0)
            total = float(timings.get("total") or retr + gen)
            retrieval.append(retr)
            generation.append(gen)
            other.append(max(0.0, total - retr - gen))
        if retrieval:
            data.append(
                {
                    "system": system.upper(),
                    "retrieval": round(mean(retrieval), 3),
                    "generation": round(mean(generation), 3),
                    "other": round(mean(other), 3),
                }
            )
    if not data:
        raise ValueError("No timings_ms records found.")
    builder.add_chart(
        figure_id="c3_latency_breakdown",
        title="Latency breakdown by system",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "system",
            "x_label": "System",
            "y_label": "Mean latency (ms)",
            "series": [
                {"key": "retrieval", "label": "Retrieval", "stack": "latency"},
                {"key": "generation", "label": "Generation", "stack": "latency"},
                {"key": "other", "label": "Other", "stack": "latency"},
            ],
        },
        caption="Mean retrieval, generation and residual time from results.jsonl.",
        source_data="*.results.jsonl",
    )


def _notebook_loss_points(root: Path) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?:train(?:ing)?[_ ]?loss|loss)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    step_pattern = re.compile(r"(?:step|epoch)\s*[:=]?\s*(\d+)", re.IGNORECASE)
    for notebook in sorted((root / "notebooks").glob("*.ipynb")):
        payload = read_json(notebook, {}) or {}
        cells = payload.get("cells")
        if not isinstance(cells, list):
            continue
        local_index = 0
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            outputs = cell.get("outputs")
            if not isinstance(outputs, list):
                continue
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                chunks: list[str] = []
                text = output.get("text")
                if isinstance(text, list):
                    chunks.extend(str(value) for value in text)
                elif isinstance(text, str):
                    chunks.append(text)
                data = output.get("data")
                if isinstance(data, dict):
                    plain = data.get("text/plain")
                    if isinstance(plain, list):
                        chunks.extend(str(value) for value in plain)
                    elif isinstance(plain, str):
                        chunks.append(plain)
                for chunk in chunks:
                    for match in pattern.finditer(chunk):
                        prefix = chunk[max(0, match.start() - 80):match.start()]
                        step_match = step_pattern.search(prefix)
                        local_index += 1
                        points.append(
                            {
                                "notebook": notebook.name,
                                "step": int(step_match.group(1)) if step_match else local_index,
                                "loss": float(match.group(1)),
                            }
                        )
    return points


def _c1_loss_curve(builder: ManifestBuilder, root: Path) -> None:
    points = _notebook_loss_points(root)
    if len(points) < 2:
        raise ValueError("No parseable loss log was found in notebook outputs.")
    by_notebook: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        by_notebook[point["notebook"]].append(point)
    selected_name, selected = max(by_notebook.items(), key=lambda item: len(item[1]))
    selected.sort(key=lambda row: row["step"])
    builder.add_chart(
        figure_id="c1_loss_curve",
        title="Finetuning loss curve",
        chart_type="line",
        payload={
            "data": selected,
            "x_key": "step",
            "x_label": "Step / epoch",
            "y_label": "Loss",
            "series": [{"key": "loss", "label": "Training loss"}],
        },
        caption=f"Best-effort parse from notebook output: {selected_name}.",
        source_data=f"notebooks/{selected_name}",
    )


@fresh_figure_generation(("model", "eval"))
def generate(
    *,
    root: Path | None = None,
    run_dir: Path | str | None = None,
    output_root: Path | None = None,
    pdf: bool = False,
    generation_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Path]:
    root = (root or _repo_root()).resolve()
    resolved_run = _resolve(root, run_dir).resolve() if run_dir else _latest_report_run(root)
    output_root = output_root or root / "evaluation" / "reports" / "figures"
    model = ManifestBuilder(
        "model",
        output_root / "model",
        pdf=pdf,
        generation_id=generation_id or "",
        generated_at=generated_at or "",
        generator="evaluation.analysis.figures_eval",
    )
    evaluation = ManifestBuilder(
        "eval",
        output_root / "eval",
        pdf=pdf,
        generation_id=generation_id or "",
        generated_at=generated_at or "",
        generator="evaluation.analysis.figures_eval",
    )
    report, judged, results = _load_run(resolved_run)
    run_source = _source(root, resolved_run) if resolved_run else "evaluation/reports"

    if resolved_run is None:
        run_reason = "No report.json run directory was found."
        for figure_id, title, chart_type, kind in [
            ("f1_judge_axes", "S0–S4 judge axes with bootstrap CI", "bar", "chart"),
            ("f2_preregistered_forest", "Pre-registered correctness effects", "forest", "png"),
            ("f4_task_system_heatmap", "Correctness by task type and system", "heatmap", "chart"),
            ("f5_error_pareto", "Error Pareto by system", "bar", "chart"),
            ("f8_judge_human", "Judge vs human correctness", "scatter", "chart"),
            ("f9_correctness_latency", "Correctness vs latency", "scatter", "chart"),
            ("f10_correctness_distribution", "Judge correctness distribution", "violin", "png"),
            ("f11_faithfulness_correctness", "Faithfulness vs correctness", "scatter", "chart"),
        ]:
            evaluation.skip(
                figure_id=figure_id,
                title=title,
                reason=run_reason,
                caption="Requires a completed evaluation run.",
                source_data=run_source,
                chart_type=chart_type,
                kind=kind,
            )
        model.skip(
            figure_id="c3_latency_breakdown",
            title="Latency breakdown by system",
            reason=run_reason,
            caption="Requires results.jsonl with timings_ms.",
            source_data=run_source,
            chart_type="bar",
        )
    else:
        _attempt(
            evaluation,
            figure_id="f1_judge_axes",
            title="S0–S4 judge axes with bootstrap CI",
            caption="Mean judge scores with confidence intervals.",
            source_data=run_source,
            chart_type="bar",
            kind="chart",
            function=lambda: _f1_judge_axes(evaluation, judged),
        )
        _attempt(
            evaluation,
            figure_id="f2_preregistered_forest",
            title="Pre-registered correctness effects",
            caption="Paired effects for the four pre-registered comparisons.",
            source_data=run_source,
            chart_type="forest",
            kind="png",
            function=lambda: _f2_forest(evaluation, judged),
        )
        _attempt(
            evaluation,
            figure_id="f4_task_system_heatmap",
            title="Correctness by task type and system",
            caption="Task-level correctness matrix.",
            source_data=run_source,
            chart_type="heatmap",
            kind="chart",
            function=lambda: _f4_task_heatmap(evaluation, root, judged),
        )
        _attempt(
            evaluation,
            figure_id="f5_error_pareto",
            title="Error Pareto by system",
            caption="Error categories stacked by system.",
            source_data=run_source,
            chart_type="bar",
            kind="chart",
            function=lambda: _f5_error_pareto(evaluation, judged),
        )
        _attempt(
            evaluation,
            figure_id="f8_judge_human",
            title="Judge vs human correctness",
            caption="Human calibration scatter.",
            source_data="evaluation/annotations/human_labels.jsonl",
            chart_type="scatter",
            kind="chart",
            function=lambda: _f8_human_scatter(evaluation, root, judged),
        )
        _attempt(
            evaluation,
            figure_id="f9_correctness_latency",
            title="Correctness vs latency",
            caption="Case-level quality/latency trade-off.",
            source_data=run_source,
            chart_type="scatter",
            kind="chart",
            function=lambda: _f9_correctness_latency(evaluation, judged, results),
        )
        _attempt(
            evaluation,
            figure_id="f10_correctness_distribution",
            title="Judge correctness distribution",
            caption="Distribution of correctness scores.",
            source_data=run_source,
            chart_type="violin",
            kind="png",
            function=lambda: _f10_distribution(evaluation, judged),
        )
        _attempt(
            evaluation,
            figure_id="f11_faithfulness_correctness",
            title="Faithfulness vs correctness",
            caption="Grounding-quality relationship.",
            source_data=run_source,
            chart_type="scatter",
            kind="chart",
            function=lambda: _f11_faithfulness_correctness(evaluation, judged),
        )
        _attempt(
            model,
            figure_id="c3_latency_breakdown",
            title="Latency breakdown by system",
            caption="Mean retrieval and generation latency.",
            source_data=run_source,
            chart_type="bar",
            kind="chart",
            function=lambda: _c3_latency_breakdown(model, results),
        )

    _attempt(
        evaluation,
        figure_id="f3_retrieval_curves",
        title="Retrieval hit@k and recall@k",
        caption="Latest T2 retrieval curves.",
        source_data="evaluation/reports/retrieval/*/summary.json",
        chart_type="line",
        kind="chart",
        function=lambda: _f3_retrieval_curves(evaluation, root),
    )
    _attempt(
        evaluation,
        figure_id="f6_normalizer_f1",
        title="Normalizer per-field F1",
        caption="Latest normalizer unit metrics.",
        source_data="evaluation/reports/unit/normalizer/report.json",
        chart_type="bar",
        kind="chart",
        function=lambda: _f6_normalizer(evaluation, root),
    )
    _attempt(
        evaluation,
        figure_id="f7_intent_confusion",
        title="Intent router confusion matrix",
        caption="Gold-vs-predicted intent matrix.",
        source_data="evaluation/reports/unit/intent_router/report.json",
        chart_type="heatmap",
        kind="chart",
        function=lambda: _f7_intent_confusion(evaluation, root),
    )
    _attempt(
        model,
        figure_id="c1_loss_curve",
        title="Finetuning loss curve",
        caption="Best-effort notebook-output parser.",
        source_data="notebooks/*.ipynb",
        chart_type="line",
        kind="chart",
        function=lambda: _c1_loss_curve(model, root),
    )

    paths = {"model": model.finish(), "eval": evaluation.finish()}
    ok = sum(
        figure["status"] == "ok"
        for builder in (model, evaluation)
        for figure in builder.figures
    )
    skipped = sum(
        figure["status"] == "skipped"
        for builder in (model, evaluation)
        for figure in builder.figures
    )
    print(
        f"[figures_eval] run={run_source} ok={ok} skipped={skipped} "
        f"manifests={paths['model']}, {paths['eval']}",
        flush=True,
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Evaluation run directory; defaults to newest directory with report.json.",
    )
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    generate(run_dir=args.run_dir, pdf=args.pdf)


if __name__ == "__main__":
    main()
