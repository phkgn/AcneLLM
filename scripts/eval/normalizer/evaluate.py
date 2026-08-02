"""Evaluate the rule-based pipeline normalizer against the gold test-set.

Runs ``acne_llm.chat.fallback.rule_normalizer.normalize_chat_message`` on every raw user
message in the test-set, projects both prediction and gold into a shared
canonical label space (see ``taxonomy.py``), and reports a diverse set of
metrics per field:

  multi-label fields (lesions, distribution, goals, hormonal, red_flags, meds):
      - micro Precision / Recall / F1   (token-level, aggregated over samples)
      - macro F1                        (unweighted mean over labels)
      - mean Jaccard                    (sample-level set overlap)
      - exact-match rate                (whole set identical)
      - per-label support + recall      (find the weak labels)
      - coverage gap                    (gold labels normalizer cannot emit)

  scalar fields (inflammation, sex, skin_type, is_pregnant, is_breastfeeding):
      - accuracy (on samples where gold has signal)
      - confusion matrix

Outputs (default -> scripts/eval/normalizer/reports/):
    report.json         machine-readable full results
    report.md           human-readable summary
    per_sample.csv      one row per sample per field (for slicing)
    worst_cases.jsonl   lowest-agreement samples for manual review

Usage:
    python scripts/eval/normalizer/evaluate.py           # uses testset.jsonl
    python scripts/eval/normalizer/evaluate.py --worst 50
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _write(path: Path, text: str) -> None:
    """Write text and force flush to disk (robust against buffered mounts)."""
    with path.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import taxonomy as tx  # noqa: E402
from acne_llm.chat.fallback.rule_normalizer import normalize_chat_message  # noqa: E402


# --------------------------------------------------------------------------- #
# set metrics
# --------------------------------------------------------------------------- #
def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def jaccard(a: set[str], b: set[str]) -> float | None:
    if not a and not b:
        return None  # no signal either side — exclude from mean
    return len(a & b) / len(a | b) if (a | b) else None


class MultiLabelField:
    """Accumulates micro/macro/jaccard stats for one multi-label field."""

    def __init__(self, name: str):
        self.name = name
        self.tp = self.fp = self.fn = 0
        self.jacc: list[float] = []
        self.exact = 0
        self.scored = 0                       # samples with signal on either side
        self.per_label = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
        self.uncovered = Counter()            # gold labels normalizer can't emit
        self.uncovered_samples = 0

    def add(self, pred: set[str], gold: set[str], uncovered: set[str]) -> float | None:
        if uncovered:
            self.uncovered_samples += 1
            for u in uncovered:
                self.uncovered[u] += 1
        j = jaccard(pred, gold)
        if j is None:
            return None
        self.scored += 1
        self.jacc.append(j)
        if pred == gold:
            self.exact += 1
        self.tp += len(pred & gold)
        self.fp += len(pred - gold)
        self.fn += len(gold - pred)
        for lab in gold & pred:
            self.per_label[lab]["tp"] += 1
        for lab in gold - pred:
            self.per_label[lab]["fn"] += 1
        for lab in pred - gold:
            self.per_label[lab]["fp"] += 1
        return j

    def summary(self) -> dict:
        p, r, f = prf(self.tp, self.fp, self.fn)
        macro = []
        weak = []
        for lab, c in self.per_label.items():
            _, lr, lf = prf(c["tp"], c["fp"], c["fn"])
            macro.append(lf)
            support = c["tp"] + c["fn"]
            if support >= 5:
                weak.append((lab, round(lr, 2), support))
        weak.sort(key=lambda x: x[1])
        mean_j = sum(self.jacc) / len(self.jacc) if self.jacc else 0.0
        return {
            "scored_samples": self.scored,
            "micro_precision": round(p, 3),
            "micro_recall": round(r, 3),
            "micro_f1": round(f, 3),
            "macro_f1": round(sum(macro) / len(macro), 3) if macro else 0.0,
            "mean_jaccard": round(mean_j, 3),
            "exact_match_rate": round(self.exact / self.scored, 3) if self.scored else 0.0,
            "weakest_labels": weak[:8],
            "coverage_gap_samples": self.uncovered_samples,
            "uncovered_gold_labels": dict(self.uncovered.most_common(10)),
        }


class ScalarField:
    def __init__(self, name: str, ignore=("unknown",)):
        self.name = name
        self.ignore = set(ignore)
        self.correct = 0
        self.total = 0
        self.confusion = Counter()  # (gold, pred)

    def add(self, pred: str, gold: str) -> bool | None:
        if gold in self.ignore:
            return None
        self.total += 1
        self.confusion[(gold, pred)] += 1
        ok = pred == gold
        if ok:
            self.correct += 1
        return ok

    def summary(self) -> dict:
        conf = defaultdict(dict)
        for (g, p), n in self.confusion.items():
            conf[g][p] = n
        return {
            "scored_samples": self.total,
            "accuracy": round(self.correct / self.total, 3) if self.total else None,
            "confusion": {g: dict(v) for g, v in conf.items()},
        }


# --------------------------------------------------------------------------- #
# main evaluation loop
# --------------------------------------------------------------------------- #
def evaluate(testset: Path, outdir: Path, worst_k: int) -> dict:
    rows = [json.loads(l) for l in testset.read_text(encoding="utf-8").splitlines() if l.strip()]

    fields = {
        "lesion_strict": MultiLabelField("lesion_strict"),
        "lesion_bucket": MultiLabelField("lesion_bucket"),
        "distribution": MultiLabelField("distribution"),
        "treatment_goals": MultiLabelField("treatment_goals"),
        "hormonal_factors": MultiLabelField("hormonal_factors"),
        "red_flags": MultiLabelField("red_flags"),
        "medications": MultiLabelField("medications"),
    }
    scalars = {
        "inflammation": ScalarField("inflammation"),
        "sex": ScalarField("sex"),
        "skin_type": ScalarField("skin_type"),
        "is_pregnant": ScalarField("is_pregnant", ignore=()),
        "is_breastfeeding": ScalarField("is_breastfeeding", ignore=()),
    }

    per_sample_rows: list[dict] = []
    scored_examples: list[tuple[float, dict]] = []

    for row in rows:
        raw = row["raw"]
        gold = row["gold"]
        gd = gold.get("demographics") or {}
        u = normalize_chat_message(raw)
        cl = u.clinical
        ctx = u.context

        pred = {
            "lesion_types": (cl.lesion_types if cl else []),
            "distribution": (cl.lesion_distribution if cl else []),
            "treatment_goals": (cl.treatment_goals if cl else []),
            "hormonal_factors": (cl.hormonal_factors if cl else []),
            "red_flags": (cl.red_flags_input if cl else []),
            "medications": (cl.medication_history if cl else []),
            "inflammation": (cl.inflammation_level if cl else "unknown"),
        }

        # --- multi-label ---
        gp_les_s, unc_les = tx.canon_lesions(gold.get("lesion_types"), bucket=False)
        pp_les_s, _ = tx.canon_lesions(pred["lesion_types"], bucket=False)
        gp_les_b, _ = tx.canon_lesions(gold.get("lesion_types"), bucket=True)
        pp_les_b, _ = tx.canon_lesions(pred["lesion_types"], bucket=True)
        gp_dist, unc_dist = tx.canon_distribution(gold.get("distribution"), expand=True)
        pp_dist, _ = tx.canon_distribution(pred["distribution"], expand=True)
        gp_goal, unc_goal = tx.canon_goals(gold.get("treatment_goals"))
        pp_goal, _ = tx.canon_goals(pred["treatment_goals"])
        gp_horm, unc_horm = tx.canon_hormonal(gold.get("hormonal_factors"))
        pp_horm, _ = tx.canon_hormonal(pred["hormonal_factors"])
        gp_rf, unc_rf = tx.canon_redflags(gold.get("red_flags"))
        pp_rf, _ = tx.canon_redflags(pred["red_flags"])
        gp_med = tx.canon_ingredients(gold.get("medication_history"))
        pp_med = tx.canon_ingredients(pred["medications"])

        j_ls = fields["lesion_strict"].add(pp_les_s, gp_les_s, unc_les)
        fields["lesion_bucket"].add(pp_les_b, gp_les_b, set())
        j_dist = fields["distribution"].add(pp_dist, gp_dist, unc_dist)
        j_goal = fields["treatment_goals"].add(pp_goal, gp_goal, unc_goal)
        fields["hormonal_factors"].add(pp_horm, gp_horm, unc_horm)
        fields["red_flags"].add(pp_rf, gp_rf, unc_rf)
        j_med = fields["medications"].add(pp_med, gp_med, set())

        # --- scalar ---
        infl_ok = scalars["inflammation"].add(
            tx.canon_inflammation(pred["inflammation"]),
            tx.canon_inflammation(gold.get("inflammation_level")),
        )
        scalars["sex"].add(tx.canon_scalar(ctx.sex), tx.canon_scalar(gd.get("sex")))
        scalars["skin_type"].add(
            tx.canon_scalar(ctx.skin_type), tx.canon_scalar(gd.get("skin_type"))
        )
        scalars["is_pregnant"].add(
            str(bool(ctx.is_pregnant)), str(bool(gd.get("is_pregnant", False)))
        )
        scalars["is_breastfeeding"].add(
            str(bool(ctx.is_breastfeeding)), str(bool(gd.get("is_breastfeeding", False)))
        )

        # --- per-sample record + worst-case ranking ---
        js = [x for x in (j_ls, j_dist, j_goal, j_med) if x is not None]
        agg = sum(js) / len(js) if js else 1.0
        per_sample_rows.append({
            "id": row.get("id"),
            "severity": row.get("severity"),
            "lesion_jacc": j_ls, "dist_jacc": j_dist,
            "goal_jacc": j_goal, "med_jacc": j_med,
            "infl_ok": infl_ok, "agg": round(agg, 3),
        })
        scored_examples.append((agg, {
            "id": row.get("id"),
            "raw": raw,
            "agg_agreement": round(agg, 3),
            "lesion": {"gold": sorted(gp_les_s), "pred": sorted(pp_les_s)},
            "distribution": {"gold": sorted(gp_dist), "pred": sorted(pp_dist)},
            "goals": {"gold": sorted(gp_goal), "pred": sorted(pp_goal)},
            "medications": {"gold": sorted(gp_med), "pred": sorted(pp_med)},
            "inflammation": {"gold": tx.canon_inflammation(gold.get("inflammation_level")),
                             "pred": tx.canon_inflammation(pred["inflammation"])},
        }))

    report = {
        "testset": str(testset),
        "n_samples": len(rows),
        "multi_label": {k: v.summary() for k, v in fields.items()},
        "scalar": {k: v.summary() for k, v in scalars.items()},
        "caveats": [
            "Gold labels are LLM-generated (silver standard), not verified ground truth.",
            "Fields with high coverage_gap use a different taxonomy than the normalizer; "
            "low scores there reflect vocabulary divergence, not necessarily errors.",
        ],
    }

    outdir.mkdir(parents=True, exist_ok=True)
    _write(outdir / "report.json", json.dumps(report, ensure_ascii=False, indent=2))
    _write_markdown(report, outdir / "report.md")
    _write_csv(per_sample_rows, outdir / "per_sample.csv")
    scored_examples.sort(key=lambda x: x[0])
    lines = [json.dumps(ex, ensure_ascii=False) for _, ex in scored_examples[:worst_k]]
    _write(outdir / "worst_cases.jsonl", "\n".join(lines) + "\n")
    return report


def _write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    _write(path, buf.getvalue())


def _write_markdown(report: dict, path: Path) -> None:
    L = [f"# Normalizer evaluation\n",
         f"Test-set: `{report['testset']}` — **{report['n_samples']}** samples\n",
         "## Multi-label fields\n",
         "| field | micro-F1 | P | R | macro-F1 | Jaccard | exact | n | cov-gap |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, s in report["multi_label"].items():
        L.append(
            f"| {name} | {s['micro_f1']} | {s['micro_precision']} | {s['micro_recall']} "
            f"| {s['macro_f1']} | {s['mean_jaccard']} | {s['exact_match_rate']} "
            f"| {s['scored_samples']} | {s['coverage_gap_samples']} |"
        )
    L.append("\n## Scalar fields\n")
    L.append("| field | accuracy | n |")
    L.append("|---|---|---|")
    for name, s in report["scalar"].items():
        L.append(f"| {name} | {s['accuracy']} | {s['scored_samples']} |")

    L.append("\n## Weakest labels (recall, support)\n")
    for name, s in report["multi_label"].items():
        if s["weakest_labels"]:
            weak = ", ".join(f"{lab}={r}(n{n})" for lab, r, n in s["weakest_labels"])
            L.append(f"- **{name}**: {weak}")

    L.append("\n## Coverage gaps (gold labels normalizer cannot emit)\n")
    for name, s in report["multi_label"].items():
        if s["uncovered_gold_labels"]:
            gap = ", ".join(f"{k}({v})" for k, v in s["uncovered_gold_labels"].items())
            L.append(f"- **{name}**: {gap}")

    L.append("\n## Inflammation confusion (gold → pred)\n")
    conf = report["scalar"]["inflammation"]["confusion"]
    for g, preds in conf.items():
        L.append(f"- gold **{g}**: " + ", ".join(f"{p}={n}" for p, n in preds.items()))

    L.append("\n## Caveats\n")
    for c in report["caveats"]:
        L.append(f"- {c}")
    _write(path, "\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", type=Path, default=HERE / "testset.jsonl")
    ap.add_argument("--outdir", type=Path, default=HERE / "reports")
    ap.add_argument("--worst", type=int, default=40, help="worst-case dump size")
    args = ap.parse_args()

    report = evaluate(args.testset, args.outdir, args.worst)

    print(f"\nevaluated {report['n_samples']} samples -> {args.outdir}\n")
    print(f"{'field':22} {'F1':>6} {'P':>6} {'R':>6} {'Jacc':>6} {'n':>5} {'gap':>5}")
    for name, s in report["multi_label"].items():
        print(f"{name:22} {s['micro_f1']:6.3f} {s['micro_precision']:6.3f} "
              f"{s['micro_recall']:6.3f} {s['mean_jaccard']:6.3f} "
              f"{s['scored_samples']:5d} {s['coverage_gap_samples']:5d}")
    print()
    for name, s in report["scalar"].items():
        print(f"{name:22} acc={s['accuracy']} (n={s['scored_samples']})")


if __name__ == "__main__":
    main()
