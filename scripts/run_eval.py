"""Run evaluation: retrieval metrics + format compliance + safety.

Usage:
    python -m scripts.run_eval --n 20
    python -m scripts.run_eval --n 20 --retrieval-only    # No LLM needed
    python -m scripts.run_eval --n 20 --mode llm_only      # Force llm_only generation
    python -m scripts.run_eval --n 50 --timeout 120
"""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.di import build_container
from acne_llm.schemas import UserInput, UserContext
from acne_llm.eval.metrics import recall_at_k, mrr_at_k, ndcg_at_k, aggregate
from acne_llm.eval.judge import judge_case, latency_summary
from config.settings import settings

app = typer.Typer()


def _load_cases(path: str) -> list[dict]:
    cases: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def _resolve_relevant_ids(case: dict, retriever, label_top_k: int = 5) -> tuple[list[str], str]:
    """Return relevance labels for a case.

    Prefer explicit human labels from the input file. If none exist, fall back
    to a sparse BM25 silver label so retrieval metrics are still computable.
    """
    manual = [cid for cid in case.get("relevant_chunk_ids", []) if cid]
    if manual:
        return manual, "manual"

    retrieval = retriever.retrieve(case["query"], top_k=label_top_k, mode="sparse")
    auto_ids = [ch.chunk_id for ch in retrieval.chunks]
    return auto_ids, f"auto:sparse_top{label_top_k}"


def _build_user_context(raw_ctx: dict) -> UserContext:
    """Normalize loose eval metadata into the strict UserContext schema."""
    ctx = dict(raw_ctx or {})
    if "gender" in ctx and "sex" not in ctx:
        gender = str(ctx["gender"]).strip().lower()
        if gender in {"male", "female", "other"}:
            ctx["sex"] = gender

    allowed = set(UserContext.model_fields)
    filtered = {k: v for k, v in ctx.items() if k in allowed}
    return UserContext(**filtered)


def _check_ollama_health(container) -> bool:
    """Verify Ollama is reachable and the model is loaded."""
    try:
        if not container.llm.health():
            logger.error("Ollama server not reachable")
            return False
        models = container.llm.list_models()
        model_name = container.settings.llm_model
        if not any(m.startswith(model_name) for m in models):
            logger.error(f"Ollama model '{model_name}' not found. Available: {models}")
            return False
        logger.info(f"Ollama ready: model={model_name}")
        return True
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        return False


def _try_generate(container, user: UserInput, mode: str, max_retries: int = 3) -> dict | None:
    """Try generating with fallback chain: hybrid -> llm_only -> fail.

    Returns {output, mode, model_name, latency_ms} or None on total failure.
    """
    strategies = []
    if mode in ("auto", "hybrid"):
        if container.hybrid is not None:
            strategies.append(("hybrid", container.hybrid.run))
        if container.llm_only is not None:
            strategies.append(("llm_only", container.llm_only.run))
    elif mode == "llm_only":
        if container.llm_only is not None:
            strategies.append(("llm_only", container.llm_only.run))
    else:
        # mode="auto" with no specific pipeline — try both
        if container.hybrid is not None:
            strategies.append(("hybrid", container.hybrid.run))
        if container.llm_only is not None:
            strategies.append(("llm_only", container.llm_only.run))

    if not strategies:
        logger.error("No pipeline available for generation")
        return None

    last_error = None
    for strat_name, strat_fn in strategies:
        for attempt in range(max_retries):
            try:
                t0 = time.perf_counter()
                out = strat_fn(user)
                latency = int((time.perf_counter() - t0) * 1000)
                return {
                    "output": out,
                    "mode": strat_name,
                    "model_name": getattr(container.llm, "model", "unknown"),
                    "latency_ms": latency,
                }
            except Exception as e:
                last_error = e
                msg = str(e).lower()
                if "runner process has terminated" in msg:
                    logger.warning(
                        f"Ollama runner terminated on {strat_name} attempt {attempt+1}/{max_retries}; "
                        f"retrying..."
                    )
                    time.sleep(2 * (attempt + 1))  # exponential backoff
                else:
                    logger.warning(f"{strat_name} attempt {attempt+1}/{max_retries} failed: {e}")
                    time.sleep(1)
                    break  # non-runner error, don't retry same strategy

        logger.warning(f"Strategy '{strat_name}' exhausted all retries, trying next...")

    logger.error(f"All generation strategies failed. Last error: {last_error}")
    return None


@app.command()
def run(queries: str = "data/sample_queries.jsonl", n: int = 20,
        out_dir: str = "data/eval_reports",
        retrieval_only: bool = typer.Option(False, "--retrieval-only", help="Only compute retrieval metrics (no LLM)"),
        mode: str = typer.Option("auto", help="Generation mode: auto/hybrid/llm_only"),
        timeout: int = typer.Option(180, help="Ollama timeout per request in seconds"),
        skip_health_check: bool = typer.Option(False, "--skip-health-check", help="Skip Ollama health check")):
    if not Path(queries).exists():
        logger.error(f"queries not found: {queries}")
        raise typer.Exit(1)

    cases = _load_cases(queries)
    cases = cases[:n]
    logger.info(f"Loaded {len(cases)} cases")

    c = build_container(settings)
    if c.retriever is None:
        raise RuntimeError(
            "RAG retriever is not available. Build the KB first so eval can compute retrieval metrics."
        )

    # Health check (unless skipped or retrieval-only)
    ollama_ok = True
    if not retrieval_only and not skip_health_check:
        ollama_ok = _check_ollama_health(c)
        if not ollama_ok:
            logger.warning(
                "Ollama not ready — LLM generation will be skipped. "
                "Use --retrieval-only for retrieval metrics only, "
                "or ensure Ollama is running with the correct model."
            )

    # Override LLM timeout from settings
    c.llm._client.timeout = timeout

    recalls, mrrs, ndcgs, latencies = [], [], [], []
    format_ok = 0
    safety_ok = 0
    severity_checked = 0
    severity_ok = 0
    citation_checked = 0
    citation_ok = 0
    gen_attempted = 0
    gen_succeeded = 0
    mode_counts: dict[str, int] = {}
    per_case = []
    manual_label_cases = 0
    auto_label_cases = 0

    for i, case in enumerate(cases):
        q = case["query"]
        rel_ids, label_source = _resolve_relevant_ids(case, c.retriever)
        rel = set(rel_ids)
        if label_source == "manual":
            manual_label_cases += 1
        else:
            auto_label_cases += 1
        user_ctx = _build_user_context(case.get("user_context", {}))

        retrieval = c.retriever.retrieve(q, top_k=20)
        retrieved_ids = [ch.chunk_id for ch in retrieval.chunks]
        r = recall_at_k(retrieved_ids, rel, 10)
        m = mrr_at_k(retrieved_ids, rel, 10)
        n_ = ndcg_at_k(retrieved_ids, rel, 10)
        recalls.append(r)
        mrrs.append(m)
        ndcgs.append(n_)

        case_result = {
            "query": q[:80],
            "recall@10": r, "mrr@10": m, "ndcg@10": n_,
            "label_source": label_source,
            "relevant_chunk_count": len(rel_ids),
        }

        if retrieval_only or not ollama_ok:
            case_result["generation"] = "skipped"
            case_result["error"] = "retrieval_only" if retrieval_only else "ollama_unavailable"
            per_case.append(case_result)
            continue

        gen_attempted += 1
        user = UserInput(description=q, context=user_ctx, mode="hybrid")
        gen_result = _try_generate(c, user, mode=mode)

        if gen_result is None:
            case_result["generation"] = "failed"
            case_result["error"] = "all_strategies_exhausted"
            per_case.append(case_result)
            continue

        gen_succeeded += 1
        out = gen_result["output"]
        used_mode = gen_result["mode"]
        latency = gen_result["latency_ms"]
        mode_counts[used_mode] = mode_counts.get(used_mode, 0) + 1

        format_ok += 1
        latencies.append(latency)

        judged = judge_case(
            out,
            expected_severity=case.get("expected_severity") or case.get("severity"),
            is_pregnant=user_ctx.is_pregnant,
            available_chunk_ids=set(retrieved_ids),
        )
        if judged["safety_ok"]:
            safety_ok += 1
        if judged["severity_ok"] is not None:
            severity_checked += 1
            if judged["severity_ok"]:
                severity_ok += 1
        if judged["citation_ok"] is not None:
            citation_checked += 1
            if judged["citation_ok"]:
                citation_ok += 1

        case_result.update({
            "severity": out.severity,
            "latency_ms": latency,
            "mode_used": used_mode,
            "model_name": gen_result["model_name"],
            "generation": "ok",
            "judge": judged,
        })
        per_case.append(case_result)

        if (i + 1) % 5 == 0:
            logger.info(f"Progress: {i+1}/{len(cases)} cases...")

    # ── Build report ──────────────────────────────────────────────────────────
    gen_mode_display = "retrieval_only" if retrieval_only else mode
    gen_compliance = round(gen_succeeded / gen_attempted, 3) if gen_attempted else "N/A"
    fmt_compliance = round(format_ok / gen_attempted, 3) if gen_attempted else "N/A"
    safe_compliance = round(safety_ok / gen_succeeded, 3) if gen_succeeded else "N/A"
    severity_compliance = (
        round(severity_ok / severity_checked, 3) if severity_checked else "N/A"
    )
    citation_compliance = (
        round(citation_ok / citation_checked, 3) if citation_checked else "N/A"
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(cases),
        "settings": {
            "gen_mode": gen_mode_display,
            "retrieval_only": retrieval_only,
            "ollama_healthy": ollama_ok,
            "timeout": timeout,
        },
        "labels": {
            "manual_cases": manual_label_cases,
            "auto_cases": auto_label_cases,
            "mode": "manual" if auto_label_cases == 0 else f"auto:sparse_top5 ({auto_label_cases} cases)",
        },
        "retrieval": {
            "recall@10": aggregate(recalls),
            "mrr@10": aggregate(mrrs),
            "ndcg@10": aggregate(ndcgs),
        },
        "generation": {
            "attempted": gen_attempted,
            "succeeded": gen_succeeded,
            "compliance_rate": gen_compliance,
            "format_compliance": fmt_compliance,
            "safety_compliance": safe_compliance,
            "severity_accuracy": severity_compliance,
            "severity_checked": severity_checked,
            "citation_correctness": citation_compliance,
            "citation_checked": citation_checked,
            "mode_breakdown": mode_counts,
        },
        "latency_ms": latency_summary(latencies),
        "cases": per_case,
    }

    out_p = Path(out_dir) / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_p.mkdir(parents=True, exist_ok=True)
    (out_p / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── Summary markdown ──────────────────────────────────────────────────────
    rec = report["retrieval"]
    gen = report["generation"]
    lat = report["latency_ms"]
    summary = (
        f"# Eval report — {report['timestamp']}\n\n"
        f"## Settings\n"
        f"- Mode: **{gen_mode_display}** | Retrieval-only: {retrieval_only}\n"
        f"- Ollama healthy: {ollama_ok} | Timeout: {timeout}s\n"
        f"- Labels: {report['labels']['mode']}\n\n"
        f"## Retrieval Metrics\n"
        f"- Recall@10: **{rec['recall@10']['mean']}** (min={rec['recall@10']['min']}, max={rec['recall@10']['max']})\n"
        f"- MRR@10: **{rec['mrr@10']['mean']}**\n"
        f"- NDCG@10: **{rec['ndcg@10']['mean']}**\n\n"
        f"## Generation\n"
        f"- Attempted: {gen['attempted']} | Succeeded: {gen['succeeded']} ({gen['compliance_rate']})\n"
        f"- Format compliance: **{gen['format_compliance']}**\n"
        f"- Safety compliance: **{gen['safety_compliance']}**\n"
        f"- Severity accuracy: **{gen['severity_accuracy']}** (checked={gen['severity_checked']})\n"
        f"- Citation correctness: **{gen['citation_correctness']}** (checked={gen['citation_checked']})\n"
        f"- Mode breakdown: {gen['mode_breakdown']}\n"
        f"- Latency: mean=**{lat.get('mean', 'N/A')}ms**, "
        f"p50=**{lat.get('p50', 'N/A')}ms**, p95=**{lat.get('p95', 'N/A')}ms** "
        f"(n={lat.get('n', 0)})\n"
    )
    (out_p / "summary.md").write_text(summary, encoding="utf-8")
    logger.success(f"Report written to {out_p}")
    logger.info(summary)


if __name__ == "__main__":
    app()
