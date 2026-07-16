from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from evaluation.common import sha256_file
from evaluation.metrics.deterministic import evaluate_record
from evaluation.validate.checks.runtime import (
    model_names_equal,
    normalize_model_name,
    normalize_system_prompt,
)
from evaluation.validate.types import CheckResult

POINTWISE_AXES = (
    "correctness",
    "completeness",
    "safety",
    "relevance",
    "fluency",
    "instruction_following",
)


def _ids(rows: Sequence[dict[str, Any]]) -> list[str]:
    return [str(row.get("sample_id")) for row in rows if row.get("sample_id") is not None]


def is_valid_pointwise(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    if row.get("judge_status") == "invalid":
        return False
    pointwise = row.get("pointwise")
    if not isinstance(pointwise, dict):
        return False
    for axis in POINTWISE_AXES:
        value = pointwise.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if float(value) not in {1.0, 2.0, 3.0, 4.0, 5.0}:
            return False
    confidence = pointwise.get("confidence")
    return (
        confidence is None
        or (
            not isinstance(confidence, bool)
            and isinstance(confidence, (int, float))
            and 0.0 <= float(confidence) <= 1.0
        )
    )


def check_case_parity(
    records: Mapping[str, Sequence[dict[str, Any]]],
) -> CheckResult:
    if not records:
        return CheckResult(
            "case_parity",
            "FAIL",
            [{"message": "No system records available."}],
            critical=True,
        )
    evidence: list[dict[str, Any]] = []
    duplicate_failures: dict[str, list[str]] = {}
    id_sets: dict[str, set[str]] = {}
    for sid, rows in records.items():
        ids = _ids(rows)
        counts = Counter(ids)
        duplicates = sorted(sample_id for sample_id, count in counts.items() if count > 1)
        if duplicates:
            duplicate_failures[sid] = duplicates
        id_sets[sid] = set(ids)
    reference_sid = sorted(id_sets)[0]
    reference = id_sets[reference_sid]
    parity_failures: dict[str, dict[str, list[str]]] = {}
    for sid, ids in id_sets.items():
        missing = sorted(reference - ids)
        extra = sorted(ids - reference)
        if missing or extra:
            parity_failures[sid] = {"missing": missing, "extra": extra}
    if duplicate_failures:
        evidence.append({
            "message": "Duplicate sample_id values found inside system outputs.",
            "duplicates": duplicate_failures,
        })
    if parity_failures:
        evidence.append({
            "message": f"System sample sets differ from reference {reference_sid}.",
            "differences": parity_failures,
        })
    if evidence:
        return CheckResult("case_parity", "FAIL", evidence, critical=True)
    return CheckResult(
        "case_parity",
        "PASS",
        [{
            "message": "Every system has the same unique sample_id set.",
            "systems": sorted(id_sets),
            "n_cases": len(reference),
        }],
        critical=True,
    )


def check_non_rag_clean(
    records: Mapping[str, Sequence[dict[str, Any]]],
    system_configs: Mapping[str, dict[str, Any]],
) -> CheckResult:
    violations: list[dict[str, Any]] = []
    checked = 0
    for sid, cfg in system_configs.items():
        if cfg.get("retrieval"):
            continue
        for row in records.get(sid, []):
            checked += 1
            trace = row.get("trace") or {}
            if row.get("used_chunks") or trace.get("context_chunks"):
                violations.append({
                    "case_id": row.get("sample_id"),
                    "system": sid,
                    "file": f"{sid}.results.jsonl",
                    "used_chunks": row.get("used_chunks") or [],
                    "context_chunks_n": len(trace.get("context_chunks") or []),
                })
    if violations:
        return CheckResult(
            "non_rag_clean",
            "FAIL",
            [{
                "message": "Non-RAG systems consumed retrieval context.",
                "cases": violations[:50],
                "n": len(violations),
            }],
            critical=True,
        )
    return CheckResult(
        "non_rag_clean",
        "PASS",
        [{"message": "S0/S1 records contain no chunks or context.", "n_checked": checked}],
        critical=True,
    )


def _valid_rag_trace(row: dict[str, Any], tier: str) -> tuple[bool, str]:
    trace = row.get("trace") or {}
    used = [str(value) for value in row.get("used_chunks") or [] if value]
    retrieved = [str(value) for value in trace.get("retrieved_ids") or [] if value]
    final_ids = [str(value) for value in trace.get("final_ids") or [] if value]
    context_ids = [
        str(chunk.get("chunk_id"))
        for chunk in trace.get("context_chunks") or []
        if isinstance(chunk, dict) and chunk.get("chunk_id")
    ]
    intent = str(trace.get("primary_intent") or "")
    mode = str(trace.get("mode") or "")
    if tier == "t4" and (intent in {"reject", "clarify"} or mode in {"llm_only", "clarify"}):
        if not used:
            return True, "non-retrieval route"
    if not used and not final_ids:
        return False, "no used_chunks/final_ids"
    if final_ids and used and set(final_ids) != set(used):
        return False, "final_ids do not match used_chunks"
    if retrieved and final_ids and not set(final_ids).issubset(set(retrieved)):
        return False, "final_ids are not a subset of retrieved_ids"
    if context_ids and used and not set(used).issubset(set(context_ids)):
        return False, "used_chunks missing from context_chunks"
    if tier == "t3" and used and not (context_ids or (retrieved and final_ids)):
        return False, "used chunks exist but retrieval/context trace is absent"
    if tier == "t4" and used and not (trace.get("citations") or context_ids or final_ids):
        return False, "used chunks exist but SSE citation/retrieval trace is absent"
    return True, "valid"


def check_rag_trace(
    records: Mapping[str, Sequence[dict[str, Any]]],
    system_configs: Mapping[str, dict[str, Any]],
    tier: str,
) -> CheckResult:
    violations: list[dict[str, Any]] = []
    checked = 0
    for sid, cfg in system_configs.items():
        if not cfg.get("retrieval"):
            continue
        for row in records.get(sid, []):
            if not row.get("ok"):
                continue
            checked += 1
            valid, reason = _valid_rag_trace(row, tier)
            if not valid:
                violations.append({
                    "case_id": row.get("sample_id"),
                    "system": sid,
                    "reason": reason,
                    "file": f"{sid}.results.jsonl",
                })
    if violations:
        return CheckResult(
            "rag_trace",
            "FAIL",
            [{
                "message": "RAG records are missing a valid retrieval trace.",
                "cases": violations[:50],
                "n": len(violations),
            }],
            critical=True,
        )
    return CheckResult(
        "rag_trace",
        "PASS",
        [{"message": "Every successful RAG record has a coherent trace.", "n_checked": checked}],
        critical=True,
    )


def check_model_identity(
    records: Mapping[str, Sequence[dict[str, Any]]],
    system_configs: Mapping[str, dict[str, Any]],
    run_meta: dict[str, Any],
) -> CheckResult:
    violations: list[dict[str, Any]] = []
    for sid, rows in records.items():
        cfg = system_configs.get(sid) or {}
        expected = cfg.get("model") if cfg.get("model") else "extractive"
        for row in rows:
            if not row.get("ok"):
                continue
            actual = row.get("model_name")
            if not model_names_equal(actual, expected):
                violations.append({
                    "case_id": row.get("sample_id"),
                    "system": sid,
                    "expected": expected,
                    "actual": actual,
                    "file": f"{sid}.results.jsonl",
                })
            if (
                sid in {"s0", "s2"}
                and normalize_model_name(actual) == "acnellm-v2-q4"
            ):
                violations.append({
                    "case_id": row.get("sample_id"),
                    "system": sid,
                    "message": "Base condition answered with the finetuned model.",
                    "actual": actual,
                    "file": f"{sid}.results.jsonl",
                })
    model_digests = run_meta.get("model_digests")
    digest_missing = not isinstance(model_digests, dict)
    if digest_missing:
        violations.append({
            "message": "run_meta.json does not contain model_digests captured from Ollama.",
            "file": "run_meta.json",
        })
    else:
        expected_models = {
            str(cfg["model"])
            for cfg in system_configs.values()
            if cfg.get("model")
        }
        missing = sorted(model for model in expected_models if not model_digests.get(model))
        if missing:
            violations.append({
                "message": "Some configured models have no stored digest.",
                "models": missing,
                "file": "run_meta.json",
            })
    if violations:
        return CheckResult("model_identity", "FAIL", violations[:100], critical=True)
    return CheckResult(
        "model_identity",
        "PASS",
        [{
            "message": "Record model names and stored Ollama digests match configs.",
            "models": model_digests,
        }],
        critical=True,
    )


def check_fair_comparison(
    system_configs: Mapping[str, dict[str, Any]],
    system_prompts: Mapping[str, str] | None = None,
) -> CheckResult:
    violations: list[dict[str, Any]] = []
    llm_ids = [sid for sid in ("s0", "s1", "s2", "s3") if sid in system_configs]
    samplings = {sid: system_configs[sid].get("sampling") or {} for sid in llm_ids}
    if samplings:
        reference_sid = llm_ids[0]
        reference = samplings[reference_sid]
        for sid, sampling in samplings.items():
            if sampling != reference:
                violations.append({
                    "message": "Sampling parameters differ across factorial systems.",
                    "reference_system": reference_sid,
                    "system": sid,
                    "reference": reference,
                    "actual": sampling,
                })
    expected_templates = {
        "s0": "llm_only_user.j2",
        "s1": "llm_only_user.j2",
        "s2": "hybrid_user.j2",
        "s3": "hybrid_user.j2",
    }
    for sid, expected in expected_templates.items():
        cfg = system_configs.get(sid)
        if cfg and cfg.get("template") != expected:
            violations.append({
                "message": "Prompt template differs from the registered 2x2 design.",
                "system": sid,
                "expected": expected,
                "actual": cfg.get("template"),
            })
    if system_prompts is None:
        return CheckResult(
            "fair_comparison",
            "SKIPPED" if not violations else "FAIL",
            violations or [{
                "message": "SYSTEM prompt equality was not checked because model metadata was unavailable."
            }],
            critical=bool(violations),
        )
    s0_prompt = system_prompts.get("s0")
    s1_prompt = system_prompts.get("s1")
    if not s0_prompt or not s1_prompt:
        violations.append({
            "message": "Could not read SYSTEM prompt for both S0 and S1.",
            "available": sorted(key for key, value in system_prompts.items() if value),
        })
    elif normalize_system_prompt(s0_prompt) != normalize_system_prompt(s1_prompt):
        violations.append({
            "message": "S0 and S1 SYSTEM prompts differ (R1 confound).",
            "s0_chars": len(s0_prompt),
            "s1_chars": len(s1_prompt),
        })
    if violations:
        return CheckResult("fair_comparison", "FAIL", violations, critical=True)
    return CheckResult(
        "fair_comparison",
        "PASS",
        [{
            "message": "Sampling is identical; templates differ only by RAG design; S0/S1 SYSTEM is equal.",
            "systems": llm_ids,
        }],
        critical=True,
    )


def check_score_domain(
    judged: Mapping[str, Sequence[dict[str, Any]]],
) -> CheckResult:
    invalid: list[dict[str, Any]] = []
    valid_n = 0
    judge_failures = 0
    for sid, rows in judged.items():
        for row in rows:
            pointwise = row.get("pointwise")
            if not isinstance(pointwise, dict):
                judge_failures += 1
                if row.get("judge_status") != "invalid":
                    invalid.append({
                        "case_id": row.get("sample_id"),
                        "system": sid,
                        "message": "Missing/invalid pointwise payload is not explicitly marked invalid.",
                        "file": f"{sid}.judged.jsonl",
                    })
                continue
            if not is_valid_pointwise(row):
                invalid.append({
                    "case_id": row.get("sample_id"),
                    "system": sid,
                    "message": "Pointwise score or confidence is outside the declared domain.",
                    "pointwise": pointwise,
                    "file": f"{sid}.judged.jsonl",
                })
                continue
            faith = row.get("faithfulness")
            if faith is not None:
                value = faith.get("faithfulness") if isinstance(faith, dict) else None
                contradiction = faith.get("contradiction_rate") if isinstance(faith, dict) else None
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0.0 <= float(value) <= 1.0
                    or isinstance(contradiction, bool)
                    or not isinstance(contradiction, (int, float))
                    or not 0.0 <= float(contradiction) <= 1.0
                ):
                    invalid.append({
                        "case_id": row.get("sample_id"),
                        "system": sid,
                        "message": "Faithfulness payload is outside [0,1].",
                        "faithfulness": faith,
                        "file": f"{sid}.judged.jsonl",
                    })
                    continue
                for claim in faith.get("claims") or []:
                    confidence = claim.get("confidence") if isinstance(claim, dict) else None
                    if confidence is not None and (
                        isinstance(confidence, bool)
                        or not isinstance(confidence, (int, float))
                        or not 0.0 <= float(confidence) <= 1.0
                    ):
                        invalid.append({
                            "case_id": row.get("sample_id"),
                            "system": sid,
                            "message": "Entailment confidence is outside [0,1].",
                            "claim": claim,
                            "file": f"{sid}.judged.jsonl",
                        })
            valid_n += 1
    if invalid:
        return CheckResult("score_domain", "FAIL", invalid[:100], critical=True)
    if not judged:
        return CheckResult(
            "score_domain",
            "SKIPPED",
            [{"message": "No judged artifacts are present."}],
            critical=False,
        )
    status = "WARN" if judge_failures else "PASS"
    return CheckResult(
        "score_domain",
        status,
        [{
            "message": "Judge score domains are valid; parse failures remain excluded.",
            "valid": valid_n,
            "judge_failures": judge_failures,
        }],
        critical=False,
    )


def aggregate_buckets(
    records: Sequence[dict[str, Any]],
    judged: Sequence[dict[str, Any]],
    samples: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    judge_by_id = {
        str(row["sample_id"]): row
        for row in judged
        if row.get("sample_id") is not None
    }
    record_by_id = {
        str(row["sample_id"]): row
        for row in records
        if row.get("sample_id") is not None
    }
    buckets = {
        "valid": 0,
        "runtime_failure": 0,
        "judge_failure": 0,
        "metric_failure": 0,
        "skipped": 0,
    }
    valid_rows: dict[str, dict[str, Any]] = {}
    for sample_id in samples:
        record = record_by_id.get(sample_id)
        if record is None:
            buckets["skipped"] += 1
            continue
        if not record.get("ok"):
            buckets["runtime_failure"] += 1
            continue
        judge = judge_by_id.get(sample_id)
        if not is_valid_pointwise(judge):
            buckets["judge_failure"] += 1
            continue
        try:
            deterministic = evaluate_record(record, samples[sample_id])
        except Exception:
            buckets["metric_failure"] += 1
            continue
        buckets["valid"] += 1
        valid_rows[sample_id] = {
            "record": record,
            "judge": judge,
            "deterministic": deterministic,
        }
    return buckets, valid_rows


def check_clean_aggregate(
    records: Mapping[str, Sequence[dict[str, Any]]],
    judged: Mapping[str, Sequence[dict[str, Any]]],
    dataset_rows: Sequence[dict[str, Any]],
    report: dict[str, Any],
) -> CheckResult:
    samples = {
        str(row["sample_id"]): row
        for row in dataset_rows
        if row.get("sample_id") is not None
    }
    report_systems = report.get("systems") if isinstance(report.get("systems"), dict) else {}
    violations: list[dict[str, Any]] = []
    all_buckets: dict[str, dict[str, int]] = {}
    for sid, rows in records.items():
        buckets, valid_rows = aggregate_buckets(rows, judged.get(sid, []), samples)
        all_buckets[sid] = buckets
        reported = report_systems.get(sid) if isinstance(report_systems, dict) else None
        if not isinstance(reported, dict):
            violations.append({
                "system": sid,
                "message": "report.json has no per-system summary.",
                "file": "report.json",
            })
            continue
        if reported.get("n") != buckets["valid"]:
            violations.append({
                "system": sid,
                "message": "report.json n is not the clean valid bucket.",
                "reported_n": reported.get("n"),
                "expected_valid_n": buckets["valid"],
                "buckets": buckets,
                "file": "report.json",
            })
        reported_buckets = reported.get("buckets")
        if reported_buckets != buckets:
            violations.append({
                "system": sid,
                "message": "report.json does not expose the five required buckets.",
                "reported": reported_buckets,
                "expected": buckets,
                "file": "report.json",
            })
        if valid_rows:
            for axis in POINTWISE_AXES:
                expected = round(mean(
                    float(row["judge"]["pointwise"][axis])
                    for row in valid_rows.values()
                ), 3)
                actual = (reported.get("judge_means") or {}).get(axis)
                if actual is None or abs(float(actual) - expected) > 0.001:
                    violations.append({
                        "system": sid,
                        "message": "Judge aggregate includes invalid/non-clean rows or is stale.",
                        "axis": axis,
                        "reported": actual,
                        "expected": expected,
                        "file": "report.json",
                    })
    if violations:
        return CheckResult(
            "clean_aggregate",
            "FAIL",
            [{
                "message": "Aggregate report is not cleanly bucketed.",
                "buckets": all_buckets,
                "violations": violations[:100],
            }],
            critical=True,
        )
    return CheckResult(
        "clean_aggregate",
        "PASS",
        [{
            "message": "Report uses only ok records with valid judge payloads and exposes all buckets.",
            "buckets": all_buckets,
        }],
        critical=True,
    )


def check_versioning(
    run_meta: dict[str, Any],
    dataset_path: Path,
    expected_prompt_hashes: dict[str, Any],
    expected_system_config_hashes: dict[str, str],
    active_systems: set[str] | None = None,
) -> CheckResult:
    violations: list[dict[str, Any]] = []
    actual_dataset_hash = sha256_file(dataset_path)
    if run_meta.get("dataset_sha256") != actual_dataset_hash:
        violations.append({
            "message": "Dataset SHA-256 is missing or stale in run_meta.json.",
            "expected": actual_dataset_hash,
            "actual": run_meta.get("dataset_sha256"),
            "file": "run_meta.json",
        })
    manifest = dataset_path.parent / "MANIFEST.json"
    if not manifest.exists():
        violations.append({
            "message": "Dataset directory has no MANIFEST.json freeze record.",
            "file": str(manifest),
        })
    else:
        manifest_hash = sha256_file(manifest)
        if run_meta.get("dataset_manifest_sha256") != manifest_hash:
            violations.append({
                "message": "MANIFEST SHA-256 is missing or stale in run_meta.json.",
                "expected": manifest_hash,
                "actual": run_meta.get("dataset_manifest_sha256"),
                "file": "run_meta.json",
            })
    recorded_prompt_hashes = run_meta.get("prompt_hashes")
    recorded_system_config_hashes = run_meta.get("system_config_hashes")
    if active_systems is None:
        prompt_hashes_match = recorded_prompt_hashes == expected_prompt_hashes
        system_config_hashes_match = (
            recorded_system_config_hashes == expected_system_config_hashes
        )
        prompt_mismatches: dict[str, Any] = {}
        config_mismatches: dict[str, Any] = {}
    else:
        active = sorted(active_systems)
        recorded_prompts = (
            recorded_prompt_hashes
            if isinstance(recorded_prompt_hashes, dict)
            else {}
        )
        expected_shared = {
            key: value
            for key, value in expected_prompt_hashes.items()
            if key != "system_prompts"
        }
        recorded_shared = {
            key: value
            for key, value in recorded_prompts.items()
            if key != "system_prompts"
        }
        expected_system_prompts = expected_prompt_hashes.get("system_prompts") or {}
        recorded_system_prompts = recorded_prompts.get("system_prompts") or {}
        prompt_mismatches = {
            sid: {
                "expected": expected_system_prompts.get(sid),
                "actual": recorded_system_prompts.get(sid),
            }
            for sid in active
            if expected_system_prompts.get(sid) != recorded_system_prompts.get(sid)
        }
        prompt_hashes_match = (
            isinstance(recorded_prompt_hashes, dict)
            and recorded_shared == expected_shared
            and not prompt_mismatches
        )

        recorded_configs = (
            recorded_system_config_hashes
            if isinstance(recorded_system_config_hashes, dict)
            else {}
        )
        config_mismatches = {
            sid: {
                "expected": expected_system_config_hashes.get(sid),
                "actual": recorded_configs.get(sid),
            }
            for sid in active
            if (
                sid not in expected_system_config_hashes
                or sid not in recorded_configs
                or expected_system_config_hashes.get(sid) != recorded_configs.get(sid)
            )
        }
        system_config_hashes_match = (
            isinstance(recorded_system_config_hashes, dict)
            and not config_mismatches
        )
    if not prompt_hashes_match:
        evidence: dict[str, Any] = {
            "message": "Prompt hashes are missing or differ from current files.",
            "file": "run_meta.json",
        }
        if active_systems is not None:
            evidence["active_systems"] = sorted(active_systems)
            evidence["system_mismatches"] = prompt_mismatches
        violations.append(evidence)
    if not system_config_hashes_match:
        evidence = {
            "message": "System config hashes are missing or differ from current files.",
            "file": "run_meta.json",
        }
        if active_systems is not None:
            evidence["active_systems"] = sorted(active_systems)
            evidence["system_mismatches"] = config_mismatches
        violations.append(evidence)
    for key in ("bm25_sha256", "chroma_fingerprint"):
        if not run_meta.get(key):
            violations.append({
                "message": f"Corpus version field {key} is absent.",
                "file": "run_meta.json",
            })
    if violations:
        return CheckResult("versioning", "FAIL", violations, critical=True)
    return CheckResult(
        "versioning",
        "PASS",
        [{
            "message": "Dataset, manifest, prompts, configs and corpus hashes are pinned.",
            "dataset_sha256": actual_dataset_hash,
        }],
        critical=True,
    )


def check_session_isolation(
    records: Mapping[str, Sequence[dict[str, Any]]],
    dataset_rows: Sequence[dict[str, Any]],
    tier: str,
) -> CheckResult:
    if tier != "t4":
        return CheckResult(
            "session_isolation",
            "SKIPPED",
            [{"message": "Session isolation applies only to T4 SSE runs.", "tier": tier}],
        )
    samples = {
        str(row["sample_id"]): row
        for row in dataset_rows
        if row.get("sample_id") is not None
    }
    violations: list[dict[str, Any]] = []
    seen: dict[str, tuple[str, str]] = {}
    checked = 0
    for sid, rows in records.items():
        for row in rows:
            if not row.get("ok"):
                continue
            checked += 1
            sample_id = str(row.get("sample_id"))
            trace = row.get("trace") or {}
            session_id = trace.get("session_id")
            if not session_id:
                violations.append({
                    "case_id": sample_id,
                    "system": sid,
                    "message": "T4 record has no session_id trace.",
                    "file": f"{sid}.results.jsonl",
                })
                continue
            if session_id in seen and seen[session_id] != (sid, sample_id):
                violations.append({
                    "case_id": sample_id,
                    "system": sid,
                    "message": "Session ID was reused across cases.",
                    "session_id": session_id,
                    "first_seen": seen[session_id],
                    "file": f"{sid}.results.jsonl",
                })
            seen[str(session_id)] = (sid, sample_id)
            history = (samples.get(sample_id) or {}).get("conversation_history") or []
            if history:
                expected_user_turns = sum(
                    1 for turn in history
                    if isinstance(turn, dict) and turn.get("role") == "user"
                )
                if trace.get("history_user_turns_replayed") != expected_user_turns:
                    violations.append({
                        "case_id": sample_id,
                        "system": sid,
                        "message": "Multi-turn history was not replayed in the same session.",
                        "expected_user_turns": expected_user_turns,
                        "actual": trace.get("history_user_turns_replayed"),
                        "file": f"{sid}.results.jsonl",
                    })
    if violations:
        return CheckResult("session_isolation", "FAIL", violations[:100], critical=True)
    return CheckResult(
        "session_isolation",
        "PASS",
        [{
            "message": "Each T4 case used a unique session and multi-turn user history stayed in-session.",
            "n_checked": checked,
        }],
        critical=True,
    )
