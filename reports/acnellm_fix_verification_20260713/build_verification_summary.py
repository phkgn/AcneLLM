"""Build compact, reproducible metrics for the post-fix verification report."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR_DIR = ROOT / "reports" / "acnellm_technical_audit_20260713"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    part = position - lower
    return ordered[lower] * (1 - part) + ordered[upper] * part


def turns(data):
    return [(session["id"], turn) for session in data["sessions"] for turn in session["turns"]]


def run_metrics(data, standard_only: bool = False):
    rows = [
        (sid, turn)
        for sid, turn in turns(data)
        if not standard_only or sid.startswith("S")
    ]
    event_errors = [
        (sid, turn["turn"])
        for sid, turn in rows
        if (turn.get("stream", {}).get("event_counts", {}).get("error") or 0) > 0
    ]
    client_errors = [
        (sid, turn["turn"], turn.get("stream_error"))
        for sid, turn in rows
        if turn.get("stream_error")
    ]
    successful_model = [
        turn
        for _, turn in rows
        if (turn.get("stream", {}).get("event_counts", {}).get("token") or 0) > 1
        and (turn.get("stream", {}).get("event_counts", {}).get("error") or 0) == 0
        and not turn.get("stream_error")
    ]
    latencies = [turn["stream"]["wall_time_ms"] / 1000 for turn in successful_model]
    first_tokens = [
        turn["stream"]["first_token_ms"] / 1000
        for turn in successful_model
        if turn["stream"].get("first_token_ms") is not None
    ]
    retrieved = [
        turn
        for _, turn in rows
        if (turn.get("trace", {}).get("stage_7_retrieve", {}).get("num_chunks") or 0) > 0
    ]
    source_types = Counter()
    sources = Counter()
    for turn in retrieved:
        for chunk in turn["trace"]["stage_7_retrieve"].get("chunks", []):
            source_types[chunk.get("source_type") or "unknown"] += 1
            sources[chunk.get("source") or "unknown"] += 1
    return {
        "sessions": len({sid for sid, _ in rows}),
        "turns": len(rows),
        "event_error_count": len(event_errors),
        "event_error_turns": event_errors,
        "client_error_count": len(client_errors),
        "client_error_turns": client_errors,
        "successful_model_turns": len(successful_model),
        "model_latency_median_s": round(median(latencies), 3) if latencies else None,
        "model_latency_p95_s": round(percentile(latencies, 0.95), 3) if latencies else None,
        "first_token_median_s": round(median(first_tokens), 3) if first_tokens else None,
        "first_token_p95_s": round(percentile(first_tokens, 0.95), 3) if first_tokens else None,
        "retrieval_turns": len(retrieved),
        "source_types": dict(source_types),
        "top_sources": dict(sources.most_common(10)),
        "guideline_final_chunks": source_types.get("aad_guideline", 0) + source_types.get("nice_guideline", 0),
    }


prior = load(PRIOR_DIR / "live_e2e_evidence.json")
current = load(HERE / "live_fix_verification_evidence.json")
retry = load(HERE / "targeted_clean_retry.json")
prior_normalizer = load(PRIOR_DIR / "normalizer_evidence" / "report.json")
current_normalizer = load(HERE / "normalizer_evidence" / "report.json")
prior_probe = load(PRIOR_DIR / "retrieval_probes.json")
current_probe = load(HERE / "retrieval_recheck.json")


def field_metric(report, field, kind):
    return report[kind][field]


normalizer_delta = {}
for field in prior_normalizer["multi_label"]:
    before = prior_normalizer["multi_label"][field]["micro_f1"]
    after = current_normalizer["multi_label"][field]["micro_f1"]
    normalizer_delta[field] = {"before": before, "after": after, "delta": round(after - before, 4)}
for field in prior_normalizer["scalar"]:
    before = prior_normalizer["scalar"][field]["accuracy"]
    after = current_normalizer["scalar"][field]["accuracy"]
    normalizer_delta[field] = {"before": before, "after": after, "delta": round(after - before, 4)}


def hybrid_summary(probe):
    result = {}
    for row in probe["queries"]:
        chunks = row["modes"]["hybrid"]["chunks"]
        result[row["name"]] = [
            {
                "rank": index + 1,
                "score": chunk.get("score"),
                "source_type": chunk.get("source_type"),
                "source": chunk.get("source"),
                "title": chunk.get("title"),
            }
            for index, chunk in enumerate(chunks)
        ]
    return result


fixes = [
    {"id": "F01", "issue": "'da khá dầu' → painful_lesions", "status": "Fixed core", "confidence": "Confirmed", "evidence": "S02/T3 and J01/T2: skin=oily, no painful_lesions; skin_type harness 0.748→0.790. Alternate 'da thì khá dầu' still misses skin_type but does not create pain."},
    {"id": "F02", "issue": "Inferred fields labeled confirmed", "status": "Partial", "confidence": "Confirmed", "evidence": "Prompt now tags [user đã nêu] vs [hệ thống suy luận], but both remain under the CONFIRMED heading followed by 'Không được thay đổi...'."},
    {"id": "F03", "issue": "Negated BHA contaminates query", "status": "Fixed core", "confidence": "Confirmed", "evidence": "S04/T3, J02/T2 and R04/T2 omit salicylic alias after stop/negation; BPO still not captured in structured products."},
    {"id": "F04", "issue": "Self-procedure unsafe advice", "status": "Not fixed", "confidence": "Confirmed", "evidence": "S09 exact prompt was safe, but R05/T2 gave five actionable needle/extractor steps and only appended a contradictory warning suffix."},
    {"id": "F05", "issue": "Vietnamese guideline final selection", "status": "Not fixed", "confidence": "Confirmed", "evidence": "R02/R06: 0 final chunks; VI probe still reranks NICE ~0.51 below .58 while equivalent EN scores ~0.65–0.69."},
    {"id": "F06", "issue": "Citation marker-only validation", "status": "Not fixed", "confidence": "Confirmed", "evidence": "runtime.py still checks regex [N] and repairs [1]; R01/T2 says source [N1] then appends [1]."},
    {"id": "F07", "issue": "Duplicate-source final context", "status": "Not fixed", "confidence": "Confirmed", "evidence": "S06/T1 remains 3/3 chunks from the same HelloBacsi document; S01/T2 3/3 Medlatec."},
    {"id": "F08", "issue": "Planner test/runtime contract drift", "status": "Not fixed", "confidence": "Confirmed", "evidence": "Full suite unchanged: 455 passed, 3 failed, 1 xfailed; all three expect planner on hot path."},
    {"id": "F09", "issue": "Runtime system prompt discarded", "status": "Not fixed", "confidence": "Confirmed", "evidence": "OllamaBackend._build_messages still drops runtime system when use_modelfile_system=true."},
    {"id": "F10", "issue": "Model/KB lineage and readiness", "status": "Not fixed", "confidence": "Confirmed", "evidence": "No kb_manifest.json/model lineage added; rag_ready remains object-presence based."},
    {"id": "F11", "issue": "GET URL contains medical text", "status": "Not fixed", "confidence": "Confirmed", "evidence": "Frontend still builds GET /chat/stream?message=... via createStreamUrl."},
    {"id": "F12", "issue": "Stream cancellation / memory resilience", "status": "New blocker", "confidence": "Confirmed", "evidence": "Disconnected clients left Ollama generations queued; recovery run produced 19 streaming failures, 14 fallback retries, system-memory and CUDA OOM errors."},
]


session_statuses = {
    "S01": "Partial", "S02": "Partial", "S03": "Fail", "S04": "Partial",
    "S05": "Pass", "S06": "Pass", "S07": "Partial", "S08": "Fail",
    "S09": "Pass", "S10": "Partial", "S11": "Fail", "S12": "Fail",
}
jitter_statuses = {"J01": "Partial", "J02": "Partial", "J03": "Fail", "J04": "Fail"}

summary = {
    "snapshot": {
        "head": "fc13534ef0755ee4faca4d7dc549fd71b7a067d5",
        "branch": "codex/simplify-chat-pipeline",
        "date": "2026-07-13",
        "jitter_seed": current.get("jitter", {}).get("seed", 20260713),
    },
    "prior": run_metrics(prior, standard_only=True),
    "current_standard": run_metrics(current, standard_only=True),
    "current_with_jitter": run_metrics(current, standard_only=False),
    "targeted_retry": run_metrics(retry, standard_only=False),
    "normalizer_delta": normalizer_delta,
    "retrieval_before": hybrid_summary(prior_probe),
    "retrieval_after": hybrid_summary(current_probe),
    "fixes": fixes,
    "fix_status_counts": dict(Counter(item["status"] for item in fixes)),
    "session_statuses": session_statuses,
    "session_status_counts": dict(Counter(session_statuses.values())),
    "jitter_statuses": jitter_statuses,
    "jitter_status_counts": dict(Counter(jitter_statuses.values())),
    "regression": {
        "backend": "455 passed, 3 failed, 1 xfailed in 37.37s",
        "frontend_lint": "pass",
        "frontend_build": "pass (Next.js 15.5.20, 4 static pages, ~112 kB first load)",
        "backend_log_streaming_failures": 19,
        "backend_log_fallback_retries": 14,
        "backend_log_system_memory_error_mentions": 8,
        "backend_log_cuda_oom_mentions": 4,
    },
}

(HERE / "verification_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(HERE / "verification_summary.json")
print(json.dumps({
    "fix_status_counts": summary["fix_status_counts"],
    "session_status_counts": summary["session_status_counts"],
    "current_standard": summary["current_standard"],
}, ensure_ascii=False, indent=2))
