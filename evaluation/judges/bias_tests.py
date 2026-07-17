"""Bias tests cho judge (§7 blueprint) — BẮT BUỘC pass trước khi judge được coi là
metric hợp lệ. Chạy trên D1 dev (không đụng D2).

  1. Position bias : pairwise 2 chiều trên cặp answer thật → flip rate (mục tiêu <10%)
  2. Length bias   : Spearman(score, độ dài answer) trên pointwise (mục tiêu |ρ|<0.3)
  3. Consistency   : chấm lại N mẫu (cache off) → exact agreement (mục tiêu ≥85%)

Usage:
    python -m evaluation.judges.bias_tests --run-dir evaluation/reports/main_2x2_t3 \
        --dataset evaluation/datasets/v1/d1_dev_seed.jsonl [--n 30]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, REPORTS_DIR, read_jsonl, utcnow  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.judges.clients import (  # noqa: E402
    DEFAULT_JUDGE_PROVIDER,
    DEFAULT_OPENAI_JUDGE_MODEL,
    JudgeClient,
)
from evaluation.judges.run_judge import (  # noqa: E402
    _matches_client,
    is_valid_pointwise_payload,
    judge_pair,
    judge_pointwise,
)
from evaluation.annotations.import_labels import spearman  # noqa: E402

TARGETS = {"position_flip_rate_max": 0.10, "length_spearman_abs_max": 0.30,
           "consistency_min": 0.85}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--provider", default=DEFAULT_JUDGE_PROVIDER,
                    choices=["openai"])
    ap.add_argument("--model", default=None,
                    help=f"OpenAI default: {DEFAULT_OPENAI_JUDGE_MODEL}")
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    samples = {s["sample_id"]: s for s in load_dataset(ROOT / args.dataset)}
    client = JudgeClient(args.provider, args.model)
    rng = random.Random(7)

    results = {p.stem.replace(".results", ""): {r["sample_id"]: r for r in read_jsonl(p)
                                                if r.get("ok")}
               for p in sorted(run_dir.glob("*.results.jsonl"))}
    sys_ids = sorted(results)
    report: dict = {"generated_at": utcnow(),
                    "judge_provider": client.provider,
                    "judge_model": client.model,
                    "dataset": args.dataset,
                    "requested_n": args.n,
                    "targets": TARGETS}

    # 1. Position bias: flip rate giữa forward/backward trên các cặp hệ ngẫu nhiên
    flips, total = 0, 0
    for _ in range(args.n):
        a, b = rng.sample(sys_ids, 2)
        common = list(set(results[a]) & set(results[b]) & set(samples))
        if not common:
            continue
        sid = rng.choice(common)
        v = judge_pair(client, results[a][sid], results[b][sid], samples[sid], rng)
        if v["forward"] in ("A", "B") or v["backward"] in ("A", "B"):
            total += 1
            mapped_back = {"A": "B", "B": "A"}.get(v["backward"], v["backward"])
            if v["forward"] != mapped_back:
                flips += 1
    report["position_bias"] = {
        "flip_rate": round(flips / total, 4) if total else None, "n": total,
        "pass": (flips / total) <= TARGETS["position_flip_rate_max"] if total else None,
    }

    # 2. Length bias: Spearman(correctness, len(answer)) từ judged files có sẵn
    lens, scores = [], []
    for sid_sys in sys_ids:
        judged_path = run_dir / f"{sid_sys}.judged.jsonl"
        if not judged_path.exists():
            continue
        for j in read_jsonl(judged_path):
            if not _matches_client(j, client) or not is_valid_pointwise_payload(
                j.get("pointwise")
            ):
                continue
            pw = j.get("pointwise") or {}
            rec = results.get(sid_sys, {}).get(j["sample_id"])
            if rec and isinstance(pw.get("correctness"), (int, float)):
                lens.append(float(len(rec.get("answer") or "")))
                scores.append(float(pw["correctness"]))
    rho = spearman(scores, lens)
    report["length_bias"] = {
        "spearman_score_vs_length": rho, "n": len(lens),
        "pass": abs(rho) <= TARGETS["length_spearman_abs_max"] if rho is not None else None,
    }

    # 3. Consistency: chấm lại KHÔNG cache, so với điểm đã lưu trong *.judged.jsonl
    agree, total_c = 0, 0
    pool = [(s, sid) for s in sys_ids for sid in (set(results[s]) & set(samples))]
    rng.shuffle(pool)
    for sys_id, sid in pool[: args.n]:
        judged_path = run_dir / f"{sys_id}.judged.jsonl"
        if not judged_path.exists():
            continue
        old = next((
            j for j in read_jsonl(judged_path)
            if j["sample_id"] == sid
            and _matches_client(j, client)
            and is_valid_pointwise_payload(j.get("pointwise"))
        ), None)
        old_pw = (old or {}).get("pointwise") or {}
        if not isinstance(old_pw.get("correctness"), (int, float)):
            continue
        new = judge_pointwise(
            client, results[sys_id][sid], samples[sid], use_cache=False
        ) or {}
        if isinstance(new.get("correctness"), (int, float)):
            total_c += 1
            agree += int(new["correctness"] == old_pw["correctness"])
    report["consistency"] = {
        "exact_agreement": round(agree / total_c, 4) if total_c else None, "n": total_c,
        "pass": (agree / total_c) >= TARGETS["consistency_min"] if total_c else None,
    }

    report["cost_usd"] = round(client.total_cost_usd, 3)
    run_out = run_dir / "judge_bias_tests.json"
    run_out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    out = REPORTS_DIR / "judge_bias_tests.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"-> {run_out}\n-> {out}")


if __name__ == "__main__":
    main()
