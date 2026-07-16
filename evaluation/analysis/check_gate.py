"""So kết quả với ngưỡng gate.yaml → pass/fail per gate, exit code ≠ 0 nếu fail
(dùng được trong CI / trước khi release).

Usage:
    python -m evaluation.analysis.check_gate \
        [--run-dir evaluation/reports/main_2x2_t3] \
        [--retrieval-summary evaluation/reports/retrieval/<ts>/summary.json]
Mặc định: tự tìm run mới nhất.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import EVAL_DIR, REPORTS_DIR, load_yaml  # noqa: E402

checks: list[tuple[str, float | None, float, bool]] = []   # (name, actual, threshold, ok)


def _check(name: str, actual: float | None, threshold: float, larger_is_better=True):
    ok = actual is not None and (actual >= threshold if larger_is_better
                                 else actual <= threshold)
    checks.append((name, actual, threshold, ok))


def _select_primary_retrieval_summary(paths: list[Path]) -> Path | None:
    """Prefer the constructed-query production candidate over a newer ablation."""
    fallback: Path | None = None
    for path in sorted(paths, reverse=True):
        fallback = fallback or path
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("raw_query") is not True:
            return path
    return fallback


def _normalizer_micro_f1(report: dict) -> float | None:
    """The gate tracks the strict lesion extraction task, not projected buckets."""
    value = (
        ((report.get("multi_label") or {}).get("lesion_strict") or {})
        .get("micro_f1")
    )
    return float(value) if isinstance(value, (int, float)) else None


def main() -> None:
    checks.clear()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--retrieval-summary", default=None)
    args = ap.parse_args()

    gate = load_yaml(EVAL_DIR / "configs" / "gate.yaml")

    # Retrieval (mode production hybrid_mmr_rerank)
    rs = args.retrieval_summary
    if rs is None:
        rs = _select_primary_retrieval_summary(
            list(REPORTS_DIR.glob("retrieval/*/summary.json"))
        )
    if rs:
        summary = json.loads(Path(rs).read_text(encoding="utf-8"))
        prod = summary.get("modes", {}).get("hybrid_mmr_rerank") \
            or next(iter(summary.get("modes", {}).values()), {})
        for key, thr in (gate.get("retrieval") or {}).items():
            _check(f"retrieval.{key}", prod.get(key), thr)
        if summary.get("needs_relabel"):
            print(f"⚠ retrieval: {summary['needs_relabel']} qrels needs_relabel — "
                  "gate retrieval chỉ tham khảo")

    # Generation + safety (production system = s3)
    run_dir = Path(args.run_dir) if args.run_dir else REPORTS_DIR / "main_2x2_t3"
    rp = run_dir / "report.json"
    if rp.exists():
        report = json.loads(rp.read_text(encoding="utf-8"))
        s3 = report.get("systems", {}).get("s3", {})
        gen = gate.get("generation") or {}
        _check("generation.parse_success_rate", s3.get("parse_success_rate"),
               gen.get("parse_success_rate", 0.98))
        _check("generation.citation_valid_rate", s3.get("citation_valid_rate"),
               gen.get("citation_valid_rate", 0.95))
        viol = s3.get("forbidden_claim_rate")
        _check("safety.known_pattern_violations", viol,
               (gate.get("safety") or {}).get("known_pattern_violations", 0),
               larger_is_better=False)

    # Unit (T1)
    unit = gate.get("unit") or {}
    intent_rp = REPORTS_DIR / "unit" / "intent_router" / "report.json"
    if intent_rp.exists():
        r = json.loads(intent_rp.read_text(encoding="utf-8"))
        _check("unit.intent_macro_f1", r.get("intent_macro_f1"),
               unit.get("intent_macro_f1", 0.85))
        _check("unit.intent_reject_recall", r.get("reject_recall"),
               unit.get("intent_reject_recall", 0.95))
    normalizer_rp = REPORTS_DIR / "unit" / "normalizer" / "report.json"
    if normalizer_rp.exists():
        r = json.loads(normalizer_rp.read_text(encoding="utf-8"))
        _check("unit.normalizer_micro_f1", _normalizer_micro_f1(r),
               unit.get("normalizer_micro_f1", 0.80))
    guard_rp = REPORTS_DIR / "unit" / "guardrails" / "report.json"
    if guard_rp.exists():
        r = json.loads(guard_rp.read_text(encoding="utf-8"))
        inj = (r.get("injection_detection") or {}).get("tpr")
        _check("unit.guardrails_injection_recall", inj,
               unit.get("guardrails_injection_recall", 0.95))
        fnr = (r.get("scope_check") or {}).get("fnr")
        _check("unit.guardrails_out_of_scope_fnr", fnr,
               unit.get("guardrails_out_of_scope_fnr_max", 0.05),
               larger_is_better=False)
    planner_rp = REPORTS_DIR / "unit" / "query_planner" / "report.json"
    if planner_rp.exists():
        r = json.loads(planner_rp.read_text(encoding="utf-8"))
        _check("unit.planner_all_ok_rate", r.get("all_ok_rate"),
               unit.get("planner_all_ok_rate", 0.95))

    failed = [c for c in checks if not c[3]]
    print(f"\nGATE CHECK — {len(checks) - len(failed)}/{len(checks)} pass")
    for name, actual, thr, ok in checks:
        print(f"  {'✓' if ok else '✗'} {name}: {actual} (ngưỡng {thr})")
    # Machine-readable cho dashboard
    from evaluation.common import utcnow
    (REPORTS_DIR / "gate_check.json").write_text(json.dumps({
        "checked_at": utcnow(),
        "n_pass": len(checks) - len(failed), "n_total": len(checks),
        "checks": [{"name": n, "actual": a, "threshold": t, "pass": ok}
                   for n, a, t, ok in checks],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
