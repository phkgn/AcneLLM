from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.common import read_jsonl
from evaluation.validate.checks.invariants import is_valid_pointwise
from evaluation.validate.types import CheckResult, ValidationContext


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def validate_judge(
    context: ValidationContext,
    *,
    max_bias_age_days: int = 30,
) -> tuple[CheckResult, dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    parser_failures: list[dict[str, Any]] = []
    valid_n = 0
    faithfulness_n = 0
    invalid_faithfulness_context: list[dict[str, Any]] = []

    record_maps = {
        sid: {
            str(row.get("sample_id")): row
            for row in rows
            if row.get("sample_id") is not None
        }
        for sid, rows in context.records.items()
    }
    for sid, rows in context.judged.items():
        for row in rows:
            sample_id = str(row.get("sample_id"))
            if not is_valid_pointwise(row):
                parser_failures.append({
                    "case_id": sample_id,
                    "system": sid,
                    "judge_status": row.get("judge_status"),
                    "pointwise": row.get("pointwise"),
                    "file": f"{sid}.judged.jsonl",
                })
                continue
            valid_n += 1
            faith = row.get("faithfulness")
            if not isinstance(faith, dict):
                continue
            faithfulness_n += 1
            record = record_maps.get(sid, {}).get(sample_id) or {}
            trace = record.get("trace") or {}
            context_chunks = [
                chunk for chunk in trace.get("context_chunks") or []
                if isinstance(chunk, dict) and chunk.get("text")
            ]
            citations = [
                chunk for chunk in trace.get("citations") or []
                if isinstance(chunk, dict) and (chunk.get("snippet") or chunk.get("text"))
            ]
            if not context_chunks and not citations:
                invalid_faithfulness_context.append({
                    "case_id": sample_id,
                    "system": sid,
                    "message": (
                        "Faithfulness was scored without source text in the saved trace; "
                        "this artifact predates the context-trace fix."
                    ),
                    "files": [
                        f"{sid}.results.jsonl",
                        f"{sid}.judged.jsonl",
                        "evaluation/judges/run_judge.py",
                    ],
                })

    if parser_failures:
        explicit = [
            row for row in parser_failures
            if row.get("judge_status") == "invalid" and row.get("pointwise") is None
        ]
        unmarked = [row for row in parser_failures if row not in explicit]
        if unmarked:
            violations.append({
                "message": "Judge parser failures are not explicitly marked invalid.",
                "cases": unmarked[:100],
                "n": len(unmarked),
            })
        if explicit:
            warnings.append({
                "message": "Judge parser failures were excluded and counted separately.",
                "cases": explicit[:100],
                "n": len(explicit),
            })
    if invalid_faithfulness_context:
        violations.append({
            "message": "Saved faithfulness scores are not auditable against real context.",
            "cases": invalid_faithfulness_context[:100],
            "n": len(invalid_faithfulness_context),
        })

    pairwise_summary: dict[str, Any] = {}
    for path in sorted(context.run_dir.glob("pairwise_*_vs_*.jsonl")):
        rows = read_jsonl(path)
        invalid = [
            row for row in rows
            if row.get("forward") not in {"A", "B", "tie"}
            or row.get("backward") not in {"A", "B", "tie"}
            or row.get("verdict") not in {"A", "B", "tie"}
        ]
        pairwise_summary[path.name] = {"n": len(rows), "invalid": len(invalid)}
        if invalid:
            violations.append({
                "message": "Pairwise swap output contains invalid labels.",
                "file": str(path),
                "cases": invalid[:50],
            })

    bias_path = context.root / "evaluation" / "reports" / "judge_bias_tests.json"
    bias: dict[str, Any] = {}
    if not bias_path.exists():
        violations.append({
            "message": "Judge bias calibration artifact is missing.",
            "file": str(bias_path),
        })
    else:
        try:
            loaded = json.loads(bias_path.read_text(encoding="utf-8"))
            bias = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError as exc:
            violations.append({
                "message": "Judge bias calibration artifact is invalid JSON.",
                "detail": str(exc),
                "file": str(bias_path),
            })
        for key in ("position_bias", "length_bias", "consistency"):
            result = bias.get(key)
            if not isinstance(result, dict) or result.get("pass") is not True:
                violations.append({
                    "message": f"Judge bias check {key} is missing or failed.",
                    "result": result,
                    "file": str(bias_path),
                })
        generated = _parse_time(bias.get("generated_at"))
        if generated is None:
            warnings.append({
                "message": "Judge bias artifact has no parseable generated_at timestamp.",
                "file": str(bias_path),
            })
        else:
            age_days = (datetime.now(timezone.utc) - generated).total_seconds() / 86400
            if age_days > max_bias_age_days:
                violations.append({
                    "message": "Judge bias calibration is stale.",
                    "age_days": round(age_days, 2),
                    "max_age_days": max_bias_age_days,
                    "file": str(bias_path),
                })

    if not context.judged:
        warnings.append({
            "message": "No judged artifacts are present; judge-dependent metrics are unavailable.",
            "file": str(context.run_dir),
        })

    stats = {
        "valid_pointwise": valid_n,
        "parser_failures": len(parser_failures),
        "faithfulness_rows": faithfulness_n,
        "invalid_faithfulness_context": len(invalid_faithfulness_context),
        "pairwise": pairwise_summary,
        "bias": bias,
    }
    if violations:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"
    evidence = violations + warnings
    if not evidence:
        evidence = [{
            "message": "Judge payloads, faithfulness evidence, pairwise swap and bias tests are valid.",
            **stats,
        }]
    return CheckResult(
        "judge_validity",
        status,
        evidence,
        critical=bool(violations),
    ), stats
