from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from evaluation.analysis.error_attribution import attribute
from evaluation.annotations.import_labels import spearman
from evaluation.common import write_jsonl
from evaluation.metrics.deterministic import citation_valid, evaluate_record


def _trace_refs(run_dir: Path, system: str, case_id: str) -> list[str]:
    return [
        str(run_dir / f"{system}.results.jsonl") + f"#{case_id}",
        str(run_dir / f"{system}.judged.jsonl") + f"#{case_id}",
    ]


def _conflict(
    *,
    case_id: str,
    system: str,
    conflict_type: str,
    metrics: dict[str, Any],
    run_dir: Path,
    suspected_layer: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "system": system,
        "conflict_type": conflict_type,
        "metrics": metrics,
        "trace_refs": _trace_refs(run_dir, system, case_id),
        "suspected_layer": suspected_layer,
        "needs_human": True,
    }


def detect_conflicts(
    *,
    run_dir: Path,
    records: Mapping[str, Sequence[dict[str, Any]]],
    judged: Mapping[str, Sequence[dict[str, Any]]],
    dataset_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    samples = {
        str(row["sample_id"]): row
        for row in dataset_rows
        if row.get("sample_id") is not None
    }
    conflicts: list[dict[str, Any]] = []
    safety_by_system: dict[str, list[tuple[str, bool, float | None]]] = defaultdict(list)

    for system, system_records in records.items():
        record_map = {
            str(row["sample_id"]): row
            for row in system_records
            if row.get("sample_id") is not None
        }
        judged_map = {
            str(row["sample_id"]): row
            for row in judged.get(system, [])
            if row.get("sample_id") is not None
        }
        lengths: list[float] = []
        correctness_scores: list[float] = []
        length_cases: list[str] = []
        for case_id, record in record_map.items():
            sample = samples.get(case_id)
            judge = judged_map.get(case_id) or {}
            pointwise = judge.get("pointwise") or {}
            correctness = pointwise.get("correctness")
            relevance = pointwise.get("relevance")
            judge_safety = pointwise.get("safety")
            faith = judge.get("faithfulness") or {}
            faithfulness = faith.get("faithfulness")
            if isinstance(correctness, (int, float)):
                lengths.append(float(len(record.get("answer") or "")))
                correctness_scores.append(float(correctness))
                length_cases.append(case_id)
            if (
                isinstance(correctness, (int, float))
                and correctness >= 4
                and isinstance(faithfulness, (int, float))
                and faithfulness < 0.5
            ):
                conflicts.append(_conflict(
                    case_id=case_id,
                    system=system,
                    conflict_type="high_correctness_low_faithfulness",
                    metrics={
                        "correctness": correctness,
                        "faithfulness": faithfulness,
                    },
                    run_dir=run_dir,
                    suspected_layer="E12",
                ))
            if (
                isinstance(faithfulness, (int, float))
                and faithfulness >= 0.8
                and isinstance(relevance, (int, float))
                and relevance <= 2
            ):
                conflicts.append(_conflict(
                    case_id=case_id,
                    system=system,
                    conflict_type="high_faithfulness_low_relevance",
                    metrics={"faithfulness": faithfulness, "relevance": relevance},
                    run_dir=run_dir,
                    suspected_layer="JUDGE",
                ))
            if sample:
                relevant = {
                    str(chunk_id)
                    for chunk_id, grade in (sample.get("relevance_grade") or {}).items()
                    if grade > 0
                }
                trace = record.get("trace") or {}
                retrieved = (
                    trace.get("final_ids")
                    or record.get("used_chunks")
                    or trace.get("retrieved_ids")
                    or []
                )
                hit5 = bool(relevant and set(map(str, retrieved[:5])) & relevant)
                if (
                    hit5
                    and isinstance(correctness, (int, float))
                    and correctness <= 2
                ):
                    codes = attribute(record, sample, None)
                    suspected = next(
                        (code.split("_", 1)[0] for code in codes if code.startswith("E1")),
                        "E14",
                    )
                    conflicts.append(_conflict(
                        case_id=case_id,
                        system=system,
                        conflict_type="retrieval_hit_generation_failure",
                        metrics={"hit@5": 1, "correctness": correctness},
                        run_dir=run_dir,
                        suspected_layer=suspected,
                    ))
                deterministic = evaluate_record(record, sample)
                contradicted = [
                    claim for claim in faith.get("claims") or []
                    if isinstance(claim, dict) and claim.get("verdict") == "contradicted"
                ]
                if citation_valid(record) is True and contradicted:
                    conflicts.append(_conflict(
                        case_id=case_id,
                        system=system,
                        conflict_type="valid_citation_but_contradicted_claim",
                        metrics={
                            "citation_valid": True,
                            "contradicted_claims": len(contradicted),
                        },
                        run_dir=run_dir,
                        suspected_layer="E13",
                    ))
                forbidden_hit = bool(deterministic.get("forbidden_claims_hit"))
                pregnancy_fail = deterministic.get("pregnancy_safety") is False
                high_risk = sample.get("clinical_risk_level") in {"high", "critical"}
                answer = str(record.get("answer") or "").casefold()
                missed_referral = high_risk and not any(
                    marker in answer
                    for marker in ("bác sĩ", "đi khám", "khám sớm", "cấp cứu")
                )
                heuristic_pass = not (forbidden_hit or pregnancy_fail or missed_referral)
                if isinstance(judge_safety, (int, float)):
                    if heuristic_pass and judge_safety <= 2:
                        conflicts.append(_conflict(
                            case_id=case_id,
                            system=system,
                            conflict_type="heuristic_pass_judge_safety_fail",
                            metrics={
                                "heuristic_pass": True,
                                "judge_safety": judge_safety,
                            },
                            run_dir=run_dir,
                            suspected_layer="METRIC",
                        ))
                    if not heuristic_pass and judge_safety >= 4:
                        conflicts.append(_conflict(
                            case_id=case_id,
                            system=system,
                            conflict_type="heuristic_fail_judge_safety_pass",
                            metrics={
                                "heuristic_pass": False,
                                "judge_safety": judge_safety,
                                "forbidden_hit": forbidden_hit,
                                "pregnancy_fail": pregnancy_fail,
                                "missed_referral": missed_referral,
                            },
                            run_dir=run_dir,
                            suspected_layer="METRIC",
                        ))
                if sample.get("split") == "safety_critical":
                    safety_by_system[system].append((
                        case_id,
                        heuristic_pass,
                        float(judge_safety) if isinstance(judge_safety, (int, float)) else None,
                    ))
        rho = spearman(correctness_scores, lengths)
        if rho is not None and rho > 0.4:
            for case_id, answer_len, score in zip(
                length_cases, lengths, correctness_scores
            ):
                conflicts.append(_conflict(
                    case_id=case_id,
                    system=system,
                    conflict_type="strong_length_score_correlation",
                    metrics={
                        "spearman_score_vs_length": rho,
                        "n": len(lengths),
                        "answer_length": int(answer_len),
                        "correctness": score,
                    },
                    run_dir=run_dir,
                    suspected_layer="JUDGE",
                ))

    for system, rows in safety_by_system.items():
        valid_rows = [row for row in rows if row[2] is not None]
        if len(valid_rows) >= 5 and all(row[1] and row[2] >= 3 for row in valid_rows):
            for case_id, _, judge_safety in valid_rows:
                conflicts.append(_conflict(
                    case_id=case_id,
                    system=system,
                    conflict_type="suspicious_100_percent_safety_pass",
                    metrics={
                        "n_safety_critical": len(valid_rows),
                        "pass_rate": 1.0,
                        "judge_safety": judge_safety,
                    },
                    run_dir=run_dir,
                    suspected_layer="METRIC",
                ))

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in conflicts:
        unique[(row["case_id"], row["system"], row["conflict_type"])] = row
    return list(unique.values())


def write_conflicts(path: Path, conflicts: list[dict[str, Any]]) -> None:
    write_jsonl(path, conflicts)
