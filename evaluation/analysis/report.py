"""Tổng hợp kết quả run → report.md + report.json (bảng chính + so sánh cặp + Pareto lỗi).

Usage:
    python -m evaluation.analysis.report --run-dir evaluation/reports/main_2x2_t3 \
        --dataset evaluation/datasets/v1/answer_quality_test.jsonl \
        [--comparisons s0:s1,s0:s2,s1:s3,s2:s3]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import (  # noqa: E402
    REPORTS_DIR,
    ROOT,
    ensure_repo_importable,
    read_jsonl,
    utcnow,
)
from evaluation.analysis.check_gate import _select_primary_retrieval_summary  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.deterministic import evaluate_record  # noqa: E402
from evaluation.metrics.grounding import GroundingScorer  # noqa: E402
from evaluation.analysis.stats import (  # noqa: E402
    cliffs_delta, holm_bonferroni, mcnemar_exact, paired_bootstrap,
    wilcoxon_signed_rank, win_tie_loss,
)
from evaluation.analysis.error_attribution import attribute  # noqa: E402
from evaluation.validate.checks.invariants import (  # noqa: E402
    aggregate_buckets,
    is_valid_pointwise,
)

AXES = ["correctness", "completeness", "safety", "relevance", "fluency",
        "instruction_following"]

ensure_repo_importable()


def _grounding_summary(det_rows: list[dict]) -> dict:
    applicable = [
        row for row in det_rows
        if isinstance(row.get("grounded_sentence_rate"), (int, float))
        and isinstance(row.get("grounding_eligible_sentence_count"), int)
    ]
    eligible = sum(row["grounding_eligible_sentence_count"] for row in applicable)
    grounded = sum(
        int(row.get("grounding_grounded_sentence_count") or 0)
        for row in applicable
    )
    unsupported = sum(
        len(row.get("unsupported_sentences") or []) for row in applicable
    )
    return {
        "grounded_sentence_rate": (
            round(grounded / eligible, 4) if eligible else None
        ),
        "grounding_counts": {
            "records_applicable": len(applicable),
            "eligible_sentences": eligible,
            "grounded_sentences": grounded,
            "unsupported_sentences": unsupported,
        },
    }


def _faithfulness_score(payload: object) -> float | None:
    """Return a claim-derived score only for an internally valid payload."""
    if not isinstance(payload, dict) or payload.get("valid") is False:
        return None
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return None
    allowed = {"supported", "contradicted", "not_found"}
    if any(
        not isinstance(claim, dict)
        or not isinstance(claim.get("text"), str)
        or not claim["text"].strip()
        or claim.get("verdict") not in allowed
        for claim in claims
    ):
        return None
    if payload.get("n_claims") is not None and payload.get("n_claims") != len(claims):
        return None
    return round(sum(claim["verdict"] == "supported" for claim in claims) / len(claims), 4)


def _refusal_fidelity(records: list[dict], samples: dict[str, dict]) -> float | None:
    """Match reject/non-reject routing per attempted labeled sample.

    A runtime failure or missing ``trace.primary_intent`` is a mismatch instead
    of disappearing from the denominator: this is a merge-blocking safety gate.
    """
    matches: list[bool] = []
    for record in records:
        sample = samples.get(record.get("sample_id"))
        if sample is None or sample.get("intent_label") not in {
            "advise", "knowledge", "clarify", "reject",
        }:
            continue
        expected_reject = sample["intent_label"] == "reject"
        trace = record.get("trace") if isinstance(record.get("trace"), dict) else {}
        actual_reject = trace.get("primary_intent") == "reject"
        matches.append(bool(record.get("ok")) and actual_reject == expected_reject)
    return round(sum(matches) / len(matches), 4) if matches else None


def _judge_scores(run_dir: Path, system_id: str) -> dict[str, dict]:
    path = run_dir / f"{system_id}.judged.jsonl"
    if not path.exists():
        return {}
    return {r["sample_id"]: r for r in read_jsonl(path)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--comparisons", default="s0:s1,s0:s2,s1:s3,s2:s3")
    ap.add_argument(
        "--retrieval-summary",
        default=None,
        help="Qrels-only T2 summary; mặc định chọn run constructed-query mới nhất.",
    )
    ap.add_argument(
        "--recompute-grounding",
        action="store_true",
        help="recompute old artifacts with the configured local embedder",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    samples = {s["sample_id"]: s for s in load_dataset(ROOT / args.dataset)}
    system_rows: dict[str, list[dict]] = {}
    systems: dict[str, dict[str, dict]] = {}
    for path in sorted(run_dir.glob("*.results.jsonl")):
        sid = path.stem.replace(".results", "")
        rows = read_jsonl(path)
        system_rows[sid] = rows
        systems[sid] = {r["sample_id"]: r for r in rows}

    retrieval_path = (
        Path(args.retrieval_summary)
        if args.retrieval_summary
        else _select_primary_retrieval_summary(
            list(REPORTS_DIR.glob("retrieval/*/summary.json"))
        )
    )
    retrieval_report = None
    if retrieval_path is not None and retrieval_path.exists():
        retrieval_payload = json.loads(retrieval_path.read_text(encoding="utf-8"))
        retrieval_report = {
            "artifact": str(retrieval_path),
            "dataset": retrieval_payload.get("dataset"),
            "n_queries": retrieval_payload.get("n_queries"),
            "raw_query": retrieval_payload.get("raw_query"),
            "modes": retrieval_payload.get("modes") or {},
        }
    report: dict = {
        "generated_at": utcnow(),
        "run_dir": str(run_dir),
        "n_systems": len(systems),
        "retrieval": retrieval_report,
        "systems": {},
        "comparisons": {},
        "errors": {},
    }

    grounding_scorer = None
    if args.recompute_grounding:
        from acne_llm.config import settings
        from acne_llm.rag.embedder import Embedder

        grounding_scorer = GroundingScorer(embedder=Embedder(
            model_name=settings.embedding_model,
            device=settings.device,
            lazy=True,
        ))

    # ── Per-system summary ──────────────────────────────────────────────
    for sid, records in systems.items():
        judged = _judge_scores(run_dir, sid)
        buckets, valid_rows = aggregate_buckets(
            system_rows[sid], list(judged.values()), samples
        )
        # Deterministic metrics are valid without a judge. Judge validity only
        # gates judge/faithfulness aggregates and paired comparisons.
        det_rows, latencies, faiths = [], [], []
        for rec in system_rows[sid]:
            sample = samples.get(rec.get("sample_id"))
            if not rec.get("ok") or sample is None:
                continue
            try:
                det = evaluate_record(
                    rec,
                    sample,
                    grounding_scorer=grounding_scorer,
                )
            except Exception:
                continue
            det_rows.append(det)
            if det["latency_total_ms"]:
                latencies.append(det["latency_total_ms"])
        axis_scores: dict[str, list[float]] = defaultdict(list)
        err_counter: Counter = Counter()
        for sample_id, bundle in valid_rows.items():
            rec = bundle["record"]
            j = bundle["judge"]
            pw = j.get("pointwise") or {}
            for axis in AXES:
                if isinstance(pw.get(axis), (int, float)):
                    axis_scores[axis].append(float(pw[axis]))
            f = _faithfulness_score(j.get("faithfulness"))
            if f is not None:
                faiths.append(f)
        for rec in system_rows[sid]:
            sample_id = rec.get("sample_id")
            sample = samples.get(sample_id)
            if sample is None:
                continue
            error_class = (judged.get(sample_id) or {}).get("error_class") or {}
            for code in attribute(rec, sample, error_class):
                err_counter[code] += 1

        def rate(key: str) -> float | None:
            vals = [d[key] for d in det_rows if d.get(key) is not None]
            return round(sum(1 for v in vals if v) / len(vals), 4) if vals else None

        grounding_summary = _grounding_summary(det_rows)
        legacy_structured = any(
            isinstance(record.get("structured"), dict)
            for record in system_rows[sid]
        )
        prose_count = sum(
            not isinstance(record.get("structured"), dict)
            for record in system_rows[sid]
        )
        if legacy_structured and prose_count:
            contract = "mixed_legacy_structured_and_prose"
        elif legacy_structured:
            contract = "legacy_structured_json"
        else:
            contract = "prose"
        system_report = {
            "contract": contract,
            "n": buckets["valid"],
            "n_generation_valid": len(det_rows),
            "n_attempted": len(system_rows[sid]),
            "buckets": buckets,
            "ok_rate": round(mean(1.0 if r.get("ok") else 0.0
                                  for r in system_rows[sid]), 4)
                       if system_rows[sid] else 0,
            **grounding_summary,
            "refusal_fidelity": _refusal_fidelity(system_rows[sid], samples),
            "pregnancy_safety_rate": rate("pregnancy_safety"),
            "forbidden_claim_rate": round(
                sum(1 for d in det_rows if d["forbidden_claims_hit"]) / len(det_rows), 4
            ) if det_rows else None,
            "vietnamese_ratio_mean": round(
                mean(d["vietnamese_ratio"] for d in det_rows), 4
            ) if det_rows else None,
            "answer_chars": {
                "p50": int(median(d["answer_char_count"] for d in det_rows))
                if det_rows else None,
                "mean": int(mean(d["answer_char_count"] for d in det_rows))
                if det_rows else None,
            },
            "judge_means": {a: round(mean(v), 3) for a, v in axis_scores.items() if v},
            "faithfulness_mean": round(mean(faiths), 4) if faiths else None,
            "latency_ms": {"p50": int(median(latencies)) if latencies else None,
                           "mean": int(mean(latencies)) if latencies else None},
            "error_pareto": err_counter.most_common(10),
        }
        if legacy_structured:
            system_report.update({
                "parse_success_rate": rate("parse_success"),
                "vacuous_answer_rate": rate("vacuous_answer"),
                "legacy_structured_metrics": True,
            })
        report["systems"][sid] = system_report

    # ── Paired comparisons (pre-registered, Holm-corrected) ─────────────
    pvals: dict[str, float] = {}
    for pair in args.comparisons.split(","):
        a, b = pair.split(":")
        if a not in systems or b not in systems:
            continue
        judged_a, judged_b = _judge_scores(run_dir, a), _judge_scores(run_dir, b)
        common = sorted(
            sample_id
            for sample_id in set(judged_a) & set(judged_b)
            if is_valid_pointwise(judged_a[sample_id])
            and is_valid_pointwise(judged_b[sample_id])
            and systems[a].get(sample_id, {}).get("ok")
            and systems[b].get(sample_id, {}).get("ok")
        )
        comp: dict = {"n_common": len(common)}
        for axis in ("correctness", "safety"):
            xs = [float(judged_a[s]["pointwise"][axis]) for s in common]
            ys = [float(judged_b[s]["pointwise"][axis]) for s in common]
            if len(xs) >= 10:
                comp[axis] = {
                    "bootstrap": paired_bootstrap(ys, xs),   # dương = b tốt hơn a
                    "wilcoxon": wilcoxon_signed_rank(ys, xs),
                    "cliffs_delta": cliffs_delta(ys, xs),
                    "wtl_b_vs_a": win_tie_loss(ys, xs),
                }
                p = comp[axis]["wilcoxon"].get("p_value")
                if p is not None:
                    pvals[f"{pair}:{axis}"] = p
        # McNemar trên pregnancy_safety (binary)
        recs_a, recs_b = systems[a], systems[b]
        common_ids = sorted(
            sample_id for sample_id in set(recs_a) & set(recs_b)
            if recs_a[sample_id].get("ok") and recs_b[sample_id].get("ok")
        )
        sa, sb = [], []
        for s in common_ids:
            if s not in samples:
                continue
            da = evaluate_record(recs_a[s], samples[s])
            db = evaluate_record(recs_b[s], samples[s])
            if da["pregnancy_safety"] is not None and db["pregnancy_safety"] is not None:
                sa.append(da["pregnancy_safety"])
                sb.append(db["pregnancy_safety"])
        if sa:
            comp["pregnancy_safety_mcnemar"] = mcnemar_exact(sa, sb)
        report["comparisons"][pair] = comp

    report["holm_correction"] = holm_bonferroni(pvals)

    out_json = run_dir / "report.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    _write_markdown(run_dir / "report.md", report)
    print(f"Report: {out_json} + report.md")


def _write_markdown(path: Path, report: dict) -> None:
    lines = [f"# Eval report — {report['generated_at']}", ""]
    retrieval = report.get("retrieval") or {}
    if retrieval:
        lines.append("## Retrieval metrics — qrels only\n")
        lines.append(
            f"> Dataset: `{retrieval.get('dataset')}`; n={retrieval.get('n_queries')}; "
            f"artifact: `{retrieval.get('artifact')}`. Không dùng answer text.\n"
        )
        retrieval_header = [
            "mode", "hit@3", "recall@5", "mrr@10", "ndcg@5",
            "precision@5", "irrelevant@5", "dup_rate", "latency_ms_mean",
        ]
        lines.append("| " + " | ".join(retrieval_header) + " |")
        lines.append("|" + "---|" * len(retrieval_header))
        for mode, metrics in (retrieval.get("modes") or {}).items():
            lines.append("| " + " | ".join(str(value) for value in [
                mode,
                metrics.get("hit@3"),
                metrics.get("recall@5"),
                metrics.get("mrr@10"),
                metrics.get("ndcg@5"),
                metrics.get("precision@5"),
                metrics.get("irrelevant@5"),
                metrics.get("dup_rate"),
                metrics.get("latency_ms_mean"),
            ]) + " |")
        lines.append("")

    lines.append("## Answer metrics — generated responses only\n")
    lines.append(
        "> Grounding dùng mẫu số câu đủ điều kiện; câu hỏi, lời chào và disclaimer "
        "chuẩn được loại. Safety được chấm trực tiếp trên prose.\n"
    )
    header = ["system", "contract", "n_judged", "n_generated", "ok",
              "grounded_sentence_rate", "grounded/eligible", "refusal_fidelity",
              "preg_safety",
              "forbidden_claim_rate", "vi_ratio", "answer_chars_p50",
              "faithful", "judge_correct", "judge_safety", "p50_ms"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for sid, s in report["systems"].items():
        jm = s.get("judge_means") or {}
        lines.append("| " + " | ".join(str(x) for x in [
            sid, s.get("contract", "unknown"), s["n"],
            s.get("n_generation_valid"), s["ok_rate"],
            s.get("grounded_sentence_rate"),
            f"{(s.get('grounding_counts') or {}).get('grounded_sentences')}/"
            f"{(s.get('grounding_counts') or {}).get('eligible_sentences')}",
            s.get("refusal_fidelity"), s["pregnancy_safety_rate"],
            s.get("forbidden_claim_rate"),
            s.get("vietnamese_ratio_mean"),
            (s.get("answer_chars") or {}).get("p50"),
            s["faithfulness_mean"], jm.get("correctness"), jm.get("safety"),
            (s["latency_ms"] or {}).get("p50"),
        ]) + " |")

    legacy_systems = {
        sid: summary for sid, summary in report["systems"].items()
        if summary.get("legacy_structured_metrics")
    }
    if legacy_systems:
        lines.append("\n## LEGACY structured metrics\n")
        lines.append(
            "> Chỉ dùng để đọc artifact JSON cũ; không thuộc contract hoặc gate prose mới.\n"
        )
        legacy_header = ["system", "parse_success", "empty_core_fields_rate"]
        lines.append("| " + " | ".join(legacy_header) + " |")
        lines.append("|" + "---|" * len(legacy_header))
        for sid, summary in legacy_systems.items():
            lines.append("| " + " | ".join(str(value) for value in [
                sid,
                summary.get("parse_success_rate"),
                summary.get("vacuous_answer_rate"),
            ]) + " |")

    lines.append("\n## Pre-registered comparisons\n")
    for pair, comp in (report.get("comparisons") or {}).items():
        lines.append(f"### {pair} (n={comp.get('n_common')})")
        for axis in ("correctness", "safety"):
            c = comp.get(axis)
            if not c:
                continue
            b = c.get("bootstrap") or {}
            w = c.get("wtl_b_vs_a") or {}
            wp = (c.get("wilcoxon") or {}).get("p_value")
            sig = "SIGNIFICANT" if b.get("significant") else "chưa đủ bằng chứng"
            lines.append(
                f"- {axis}: delta_mean={b.get('mean_diff')} CI95={b.get('ci95')} ({sig})"
                f" | W/T/L={w.get('win')}/{w.get('tie')}/{w.get('loss')}"
                f" | wilcoxon_p={wp if wp is not None else 'N/A (n nhỏ)'}"
            )
        mc = comp.get("pregnancy_safety_mcnemar")
        if mc:
            lines.append(f"- pregnancy_safety McNemar: n01={mc['n01']} n10={mc['n10']} "
                         f"p={mc['p_value']}")
    holm = report.get("holm_correction") or {}
    if holm:
        lines.append("\n### Holm-corrected (Wilcoxon)")
        for key, h in holm.items():
            lines.append(f"- `{key}`: p={h['p']} (ngưỡng {h['threshold']}) → "
                         f"{'SIGNIFICANT' if h['significant'] else 'not significant'}")

    lines.append("\n## Error Pareto per system\n")
    for sid, s in report["systems"].items():
        lines.append(f"- **{sid}**: " + ", ".join(
            f"{code}×{cnt}" for code, cnt in (s.get("error_pareto") or [])
        ))
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
