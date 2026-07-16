from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.common import REPORTS_DIR, ROOT, utcnow
from evaluation.validate.audits.dataset_audit import write_dataset_audit
from evaluation.validate.audits.judge_audit import write_judge_audit
from evaluation.validate.audits.metric_audit import write_metric_audit
from evaluation.validate.audits.prompt_audit import write_prompt_audit
from evaluation.validate.audits.runtime_vs_eval import write_runtime_audit
from evaluation.validate.checks.dataset import audit_datasets, default_train_path
from evaluation.validate.checks.invariants import (
    check_case_parity,
    check_clean_aggregate,
    check_fair_comparison,
    check_model_identity,
    check_non_rag_clean,
    check_rag_trace,
    check_score_domain,
    check_session_isolation,
    check_versioning,
)
from evaluation.validate.checks.judge import validate_judge
from evaluation.validate.checks.reproducibility import run_reproducibility
from evaluation.validate.checks.runtime import validate_runtime
from evaluation.validate.conflict import detect_conflicts, write_conflicts
from evaluation.validate.context import load_context
from evaluation.validate.types import CheckResult, ValidationContext


def _timestamp_dir() -> Path:
    value = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / "validation" / value
    suffix = 1
    while path.exists():
        path = REPORTS_DIR / "validation" / f"{value}-{suffix}"
        suffix += 1
    path.mkdir(parents=True, exist_ok=False)
    return path


def _verdict(checks: list[CheckResult]) -> str:
    if any(check.status == "FAIL" and check.critical for check in checks):
        return "NOT_TRUSTWORTHY"
    if any(check.status in {"FAIL", "WARN", "SKIPPED"} for check in checks):
        return "PARTIAL"
    return "TRUSTWORTHY"


def _confidence_notes(
    context: ValidationContext,
    checks: list[CheckResult],
) -> list[str]:
    notes: list[str] = []
    if context.tier != "t4":
        notes.append(
            "No T4 production-SSE result is present; T3 is diagnostic, not the final production verdict."
        )
    n_cases = len(next(iter(context.records.values()), []))
    if n_cases < 30:
        notes.append(
            f"Run has only {n_cases} cases per system; effect estimates are smoke-level and underpowered."
        )
    if context.dataset_path.name.startswith("d1_"):
        notes.append(
            "The run used D1 dev seed rather than the frozen D2 main test set."
        )
    failed = [check.name for check in checks if check.status == "FAIL"]
    if failed:
        notes.append("Failed validity checks: " + ", ".join(failed) + ".")
    skipped = [check.name for check in checks if check.status == "SKIPPED"]
    if skipped:
        notes.append("Unverified checks: " + ", ".join(skipped) + ".")
    return notes


def _tier_verdicts(
    context: ValidationContext,
    checks: list[CheckResult],
) -> dict[str, dict[str, str]]:
    by_name = {check.name: check for check in checks}
    unit_root = REPORTS_DIR / "unit"
    t1_present = all(
        (unit_root / name / file).exists()
        for name, file in (
            ("normalizer", "report.json"),
            ("intent_router", "report.json"),
            ("query_planner", "report.json"),
            ("guardrails", "report.json"),
        )
    )
    retrieval_summaries = list((REPORTS_DIR / "retrieval").glob("*/summary.json"))
    critical_t3 = any(
        by_name.get(name) and by_name[name].status == "FAIL"
        for name in (
            "case_parity",
            "non_rag_clean",
            "rag_trace",
            "model_identity",
            "fair_comparison",
            "clean_aggregate",
            "versioning",
        )
    )
    judge = by_name.get("judge_validity")
    data = by_name.get("dataset_validity")
    return {
        "T1": {
            "verdict": "PARTIAL" if t1_present else "NOT_VERIFIED",
            "reason": (
                "Unit artifacts exist, but seed labels/gates still limit conclusions."
                if t1_present else "Required unit artifacts are missing."
            ),
        },
        "T2": {
            "verdict": "PARTIAL" if retrieval_summaries else "NOT_VERIFIED",
            "reason": (
                "Retrieval artifacts exist, but D8 qrels remain needs_relabel/BM25-biased."
                if retrieval_summaries else "No retrieval summary found."
            ),
        },
        "T3": {
            "verdict": "NOT_TRUSTWORTHY" if critical_t3 else "PARTIAL",
            "reason": (
                "Critical T3 artifact invariants failed."
                if critical_t3 else "Batch path validated, but it is not production SSE."
            ),
        },
        "T4": {
            "verdict": "PARTIAL" if context.tier == "t4" else "NOT_VERIFIED",
            "reason": (
                "Production SSE artifact is present; inspect its invariant checks."
                if context.tier == "t4"
                else "This run contains no T4 production-SSE results."
            ),
        },
        "judge": {
            "verdict": (
                "TRUSTWORTHY"
                if judge and judge.status == "PASS"
                else "NOT_TRUSTWORTHY"
                if judge and judge.status == "FAIL"
                else "PARTIAL"
            ),
            "reason": "See judge_validity and judge_audit.md.",
        },
        "data": {
            "verdict": (
                "TRUSTWORTHY"
                if data and data.status == "PASS"
                else "NOT_TRUSTWORTHY"
                if data and data.status == "FAIL"
                else "PARTIAL"
            ),
            "reason": "See dataset_validity and dataset_audit.md.",
        },
    }


def _update_gate(summary: dict[str, Any], summary_path: Path) -> None:
    gate_path = REPORTS_DIR / "gate_check.json"
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if not isinstance(gate, dict):
            gate = {}
    except (FileNotFoundError, json.JSONDecodeError):
        gate = {}
    existing = [
        check for check in gate.get("checks") or []
        if not str(check.get("name") or "").startswith("validation.")
    ]
    validation_checks = [
        {
            "name": f"validation.{check['name']}",
            "actual": 1 if check["status"] == "PASS" else 0,
            "threshold": 1,
            "pass": check["status"] == "PASS",
            "status": check["status"],
        }
        for check in summary["per_check"]
    ]
    checks = existing + validation_checks
    gate.update({
        "checked_at": utcnow(),
        "n_pass": sum(1 for check in checks if check.get("pass") is True),
        "n_total": len(checks),
        "checks": checks,
        "validation": {
            "verdict": summary["verdict"],
            "summary_path": str(summary_path),
            "conflicts_n": summary["conflicts_n"],
        },
    })
    gate_path.write_text(
        json.dumps(gate, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_summary(
    *,
    context: ValidationContext,
    checks: list[CheckResult],
    conflicts: list[dict[str, Any]],
    human_queue: list[dict[str, Any]],
    extra: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    combined_queue: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in [*human_queue, *conflicts]:
        key = (
            str(item.get("case_id")),
            str(item.get("system") or ""),
            str(item.get("reason") or item.get("conflict_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        combined_queue.append(item)
    summary = {
        "generated_at": utcnow(),
        "run_dir": str(context.run_dir),
        "dataset": str(context.dataset_path),
        "output_dir": str(context.output_dir),
        "verdict": _verdict(checks),
        "per_check": [check.to_dict() for check in checks],
        "conflicts_n": len(conflicts),
        "human_review_queue": combined_queue,
        "confidence_notes": _confidence_notes(context, checks),
        "tier_verdicts": _tier_verdicts(context, checks),
        **extra,
    }
    summary_path = context.output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _update_gate(summary, summary_path)
    return summary, summary_path


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    output_dir = _timestamp_dir()
    context, load_result = load_context(args.run_dir, args.dataset, output_dir)
    checks: list[CheckResult] = [load_result]
    if load_result.status == "FAIL":
        summary, _ = _write_summary(
            context=context,
            checks=checks,
            conflicts=[],
            human_queue=[],
            extra={},
        )
        return summary, 1

    dataset_result, dataset_report, human_queue = audit_datasets(
        context.dataset_path.parent,
        context.dataset_path,
        default_train_path(),
    )
    checks.append(dataset_result)

    runtime_result, runtime_snapshot = validate_runtime(context)
    checks.append(runtime_result)

    checks.extend([
        check_case_parity(context.records),
        check_non_rag_clean(context.records, context.system_configs),
        check_rag_trace(context.records, context.system_configs, context.tier),
        check_model_identity(context.records, context.system_configs, context.run_meta),
        check_fair_comparison(
            context.system_configs,
            runtime_snapshot.get("system_prompts") or None,
        ),
        check_score_domain(context.judged),
        check_clean_aggregate(
            context.records,
            context.judged,
            context.dataset_rows,
            context.report,
        ),
        check_versioning(
            context.run_meta,
            context.dataset_path,
            runtime_snapshot.get("prompt_hashes") or {},
            runtime_snapshot.get("system_config_hashes") or {},
            active_systems=set(context.records),
        ),
        check_session_isolation(context.records, context.dataset_rows, context.tier),
    ])

    judge_result, judge_stats = validate_judge(context)
    checks.append(judge_result)

    conflicts = detect_conflicts(
        run_dir=context.run_dir,
        records=context.records,
        judged=context.judged,
        dataset_rows=context.dataset_rows,
    )
    write_conflicts(output_dir / "conflicts.jsonl", conflicts)

    repro_result, repro_summary = run_reproducibility(
        context,
        args.repro_subset,
        run_judge=args.repro_judge,
        judge_provider=args.judge_provider,
    )
    checks.append(repro_result)
    (output_dir / "reproducibility.json").write_text(
        json.dumps(repro_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    write_runtime_audit(output_dir / "runtime_vs_eval.md", context, runtime_snapshot)
    write_dataset_audit(output_dir / "dataset_audit.md", dataset_report, human_queue)
    write_prompt_audit(output_dir / "prompt_audit.md", runtime_snapshot)
    write_judge_audit(output_dir / "judge_audit.md", judge_stats)
    write_metric_audit(output_dir / "metric_audit.md")

    summary, summary_path = _write_summary(
        context=context,
        checks=checks,
        conflicts=conflicts,
        human_queue=human_queue,
        extra={
            "artifacts": {
                "summary": str(output_dir / "summary.json"),
                "conflicts": str(output_dir / "conflicts.jsonl"),
                "runtime_audit": str(output_dir / "runtime_vs_eval.md"),
                "dataset_audit": str(output_dir / "dataset_audit.md"),
                "prompt_audit": str(output_dir / "prompt_audit.md"),
                "judge_audit": str(output_dir / "judge_audit.md"),
                "metric_audit": str(output_dir / "metric_audit.md"),
                "reproducibility": str(output_dir / "reproducibility.json"),
            }
        },
    )
    critical_fail = any(check.status == "FAIL" and check.critical for check in checks)
    strict_fail = args.strict and any(check.status != "PASS" for check in checks)
    exit_code = 1 if critical_fail or strict_fail else 0
    print(f"\nVALIDATION VERDICT: {summary['verdict']}")
    for check in checks:
        print(f"  [{check.status}] {check.name}")
    print(f"Summary: {summary_path}")
    return summary, exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate that an AcneLLM evaluation run is trustworthy."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--repro-subset",
        type=int,
        default=0,
        help="Rerun N cases with the same seed; 0 safely skips the expensive runtime step.",
    )
    parser.add_argument(
        "--repro-judge",
        action="store_true",
        help="Also rerun the paid judge for the reproducibility subset.",
    )
    parser.add_argument(
        "--judge-provider",
        default="deepseek",
        choices=["deepseek", "openai"],
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.repro_subset < 0:
        raise SystemExit("--repro-subset must be >= 0")
    _, exit_code = run(args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
