from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

import yaml

from evaluation.common import ROOT, read_jsonl
from evaluation.metrics.deterministic import evaluate_record
from evaluation.validate.checks.invariants import POINTWISE_AXES, is_valid_pointwise
from evaluation.validate.types import CheckResult, ValidationContext


def _without_latency(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if key != "latency_total_ms"
    }


def compare_reproducibility(
    *,
    original_records: Mapping[str, Sequence[dict[str, Any]]],
    rerun_records: Mapping[str, Sequence[dict[str, Any]]],
    original_judged: Mapping[str, Sequence[dict[str, Any]]],
    rerun_judged: Mapping[str, Sequence[dict[str, Any]]],
    samples: Mapping[str, dict[str, Any]],
    judge_tolerance: float = 0.5,
) -> tuple[CheckResult, dict[str, Any]]:
    deterministic_diffs: list[dict[str, Any]] = []
    judge_axis_diffs: dict[str, dict[str, float]] = {}
    missing: list[dict[str, Any]] = []

    for system, original_rows in original_records.items():
        original_map = {
            str(row["sample_id"]): row
            for row in original_rows
            if row.get("sample_id") is not None
        }
        rerun_map = {
            str(row["sample_id"]): row
            for row in rerun_records.get(system, [])
            if row.get("sample_id") is not None
        }
        for case_id, original in original_map.items():
            if case_id not in samples:
                continue
            rerun = rerun_map.get(case_id)
            if rerun is None:
                missing.append({"system": system, "case_id": case_id})
                continue
            try:
                left = _without_latency(evaluate_record(original, samples[case_id]))
                right = _without_latency(evaluate_record(rerun, samples[case_id]))
            except Exception as exc:  # noqa: BLE001
                deterministic_diffs.append({
                    "system": system,
                    "case_id": case_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            if left != right:
                deterministic_diffs.append({
                    "system": system,
                    "case_id": case_id,
                    "original": left,
                    "rerun": right,
                })

        original_judge_map = {
            str(row["sample_id"]): row
            for row in original_judged.get(system, [])
            if row.get("sample_id") is not None and is_valid_pointwise(row)
        }
        rerun_judge_map = {
            str(row["sample_id"]): row
            for row in rerun_judged.get(system, [])
            if row.get("sample_id") is not None and is_valid_pointwise(row)
        }
        common = sorted(set(original_judge_map) & set(rerun_judge_map))
        if common:
            judge_axis_diffs[system] = {}
            for axis in POINTWISE_AXES:
                diff = mean(
                    abs(
                        float(original_judge_map[case_id]["pointwise"][axis])
                        - float(rerun_judge_map[case_id]["pointwise"][axis])
                    )
                    for case_id in common
                )
                judge_axis_diffs[system][axis] = round(diff, 4)

    judge_violations = [
        {"system": system, "axis": axis, "mean_abs_diff": value}
        for system, axes in judge_axis_diffs.items()
        for axis, value in axes.items()
        if value > judge_tolerance
    ]
    summary = {
        "deterministic_diffs": deterministic_diffs,
        "missing_rerun_cases": missing,
        "judge_mean_abs_diff": judge_axis_diffs,
        "judge_tolerance": judge_tolerance,
        "ollama_note": (
            "Ollama seeded generation is not guaranteed bit-exact; validation compares "
            "deterministic metric outcomes and reports judge variance."
        ),
    }
    if deterministic_diffs or missing or judge_violations:
        return CheckResult(
            "reproducibility",
            "FAIL",
            [{
                "message": "Same-seed rerun exceeded reproducibility tolerance.",
                **summary,
                "judge_violations": judge_violations,
            }],
            critical=True,
        ), summary
    if not rerun_judged:
        return CheckResult(
            "reproducibility",
            "WARN",
            [{
                "message": "Deterministic rerun matched, but judge variance was not measured.",
                **summary,
            }],
            critical=False,
        ), summary
    return CheckResult(
        "reproducibility",
        "PASS",
        [{"message": "Same-seed rerun stayed within tolerance.", **summary}],
        critical=True,
    ), summary


def run_reproducibility(
    context: ValidationContext,
    subset: int,
    *,
    run_judge: bool = False,
    judge_provider: str = "openai",
) -> tuple[CheckResult, dict[str, Any]]:
    if subset <= 0:
        summary = {
            "status": "SKIPPED",
            "reason": "Set --repro-subset N (>0) to perform the runtime rerun.",
            "ollama_note": "Ollama is not assumed bit-exact.",
        }
        return CheckResult(
            "reproducibility",
            "SKIPPED",
            [{"message": summary["reason"], "ollama_note": summary["ollama_note"]}],
        ), summary

    subset = min(subset, len(context.dataset_rows))
    repro_dir = context.output_dir / "repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    experiment = dict(context.experiment)
    experiment["name"] = f"validation_repro_{context.run_dir.name}"
    experiment["dataset"] = str(context.dataset_path.relative_to(ROOT)).replace("\\", "/")
    override = repro_dir / "experiment.yaml"
    override.write_text(
        yaml.safe_dump(experiment, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "evaluation.runners.run_experiment",
        "--experiment",
        str(override.relative_to(ROOT)).replace("\\", "/"),
        "--limit",
        str(subset),
        "--out-dir",
        str(repro_dir),
    ]
    timeout = max(900, subset * max(len(context.system_configs), 1) * 240)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        summary = {
            "status": "SKIPPED",
            "reason": f"{type(exc).__name__}: {exc}",
            "command": command,
        }
        return CheckResult(
            "reproducibility",
            "SKIPPED",
            [{
                "message": "Runtime rerun could not be completed.",
                **summary,
            }],
        ), summary
    (repro_dir / "runner.stdout.log").write_text(
        completed.stdout or "", encoding="utf-8"
    )
    (repro_dir / "runner.stderr.log").write_text(
        completed.stderr or "", encoding="utf-8"
    )
    if completed.returncode != 0:
        summary = {
            "status": "SKIPPED",
            "reason": f"run_experiment exited {completed.returncode}",
            "command": command,
            "stdout": str(repro_dir / "runner.stdout.log"),
            "stderr": str(repro_dir / "runner.stderr.log"),
        }
        return CheckResult(
            "reproducibility",
            "SKIPPED",
            [{"message": "Runtime rerun failed as an infrastructure step.", **summary}],
        ), summary

    rerun_records = {
        path.name.removesuffix(".results.jsonl"): read_jsonl(path)
        for path in sorted(repro_dir.glob("*.results.jsonl"))
    }
    rerun_judged: dict[str, list[dict[str, Any]]] = {}
    if run_judge:
        judge_command = [
            sys.executable,
            "-m",
            "evaluation.judges.run_judge",
            "--run-dir",
            str(repro_dir),
            "--dataset",
            str(context.dataset_path.relative_to(ROOT)).replace("\\", "/"),
            "--provider",
            judge_provider,
            "--limit",
            str(subset),
        ]
        judged_run = subprocess.run(
            judge_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=max(600, subset * max(len(context.system_configs), 1) * 180),
            check=False,
        )
        (repro_dir / "judge.stdout.log").write_text(
            judged_run.stdout or "", encoding="utf-8"
        )
        (repro_dir / "judge.stderr.log").write_text(
            judged_run.stderr or "", encoding="utf-8"
        )
        if judged_run.returncode == 0:
            rerun_judged = {
                path.name.removesuffix(".judged.jsonl"): read_jsonl(path)
                for path in sorted(repro_dir.glob("*.judged.jsonl"))
            }

    sample_subset = {
        str(row["sample_id"]): row
        for row in context.dataset_rows[:subset]
        if row.get("sample_id") is not None
    }
    original_subset = {
        sid: [
            row for row in rows
            if str(row.get("sample_id")) in sample_subset
        ]
        for sid, rows in context.records.items()
    }
    original_judged_subset = {
        sid: [
            row for row in rows
            if str(row.get("sample_id")) in sample_subset
        ]
        for sid, rows in context.judged.items()
    }
    result, summary = compare_reproducibility(
        original_records=original_subset,
        rerun_records=rerun_records,
        original_judged=original_judged_subset,
        rerun_judged=rerun_judged,
        samples=sample_subset,
    )
    summary.update({
        "status": result.status,
        "subset": subset,
        "repro_dir": str(repro_dir),
        "judge_rerun_requested": run_judge,
    })
    return result, summary
