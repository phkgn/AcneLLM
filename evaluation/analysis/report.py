"""Tổng hợp kết quả run → report.md + report.json (bảng chính + so sánh cặp + Pareto lỗi).

Usage:
    python -m evaluation.analysis.report --run-dir evaluation/reports/main_2x2_t3 \
        --dataset evaluation/datasets/v1/d2_test.jsonl \
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
from evaluation.common import ROOT, read_jsonl, utcnow  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.deterministic import evaluate_record  # noqa: E402
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

    report: dict = {"generated_at": utcnow(), "run_dir": str(run_dir),
                    "n_systems": len(systems), "systems": {}, "comparisons": {},
                    "errors": {}}

    # ── Per-system summary ──────────────────────────────────────────────
    for sid, records in systems.items():
        judged = _judge_scores(run_dir, sid)
        buckets, valid_rows = aggregate_buckets(
            system_rows[sid], list(judged.values()), samples
        )
        det_rows, latencies, faiths = [], [], []
        axis_scores: dict[str, list[float]] = defaultdict(list)
        err_counter: Counter = Counter()
        for sample_id, bundle in valid_rows.items():
            rec = bundle["record"]
            det = bundle["deterministic"]
            det_rows.append(det)
            if det["latency_total_ms"]:
                latencies.append(det["latency_total_ms"])
            j = bundle["judge"]
            pw = j.get("pointwise") or {}
            for axis in AXES:
                if isinstance(pw.get(axis), (int, float)):
                    axis_scores[axis].append(float(pw[axis]))
            f = (j.get("faithfulness") or {}).get("faithfulness")
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

        report["systems"][sid] = {
            "n": buckets["valid"],
            "n_attempted": len(system_rows[sid]),
            "buckets": buckets,
            "ok_rate": round(mean(1.0 if r.get("ok") else 0.0
                                  for r in system_rows[sid]), 4)
                       if system_rows[sid] else 0,
            "parse_success_rate": rate("parse_success"),
            "vacuous_answer_rate": rate("vacuous_answer"),
            "citation_valid_rate": rate("citation_valid"),
            "pregnancy_safety_rate": rate("pregnancy_safety"),
            "forbidden_claim_rate": round(
                sum(1 for d in det_rows if d["forbidden_claims_hit"]) / len(det_rows), 4
            ) if det_rows else None,
            "judge_means": {a: round(mean(v), 3) for a, v in axis_scores.items() if v},
            "faithfulness_mean": round(mean(faiths), 4) if faiths else None,
            "latency_ms": {"p50": int(median(latencies)) if latencies else None,
                           "mean": int(mean(latencies)) if latencies else None},
            "error_pareto": err_counter.most_common(10),
        }

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
    lines.append("## Per-system\n")
    header = ["system", "n", "ok", "parse", "vacuous", "cite_valid", "preg_safety",
              "faithful", "judge_correct", "judge_safety", "p50_ms"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for sid, s in report["systems"].items():
        jm = s.get("judge_means") or {}
        lines.append("| " + " | ".join(str(x) for x in [
            sid, s["n"], s["ok_rate"], s["parse_success_rate"],
            s.get("vacuous_answer_rate"),
            s["citation_valid_rate"], s["pregnancy_safety_rate"],
            s["faithfulness_mean"], jm.get("correctness"), jm.get("safety"),
            (s["latency_ms"] or {}).get("p50"),
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
