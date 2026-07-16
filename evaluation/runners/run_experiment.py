"""Evaluation runner: chạy dataset × systems với resume/trace/run_meta.

Usage:
    python -m evaluation.runners.run_experiment \
        --experiment evaluation/configs/experiments/main_2x2.yaml \
        [--systems s0,s1] [--limit 10] [--resume] [--out-dir evaluation/reports/<name>]

Output per system: <out_dir>/<experiment>/<system_id>.results.jsonl (+ run_meta.json)
Resume: sample_id đã có trong results.jsonl sẽ bỏ qua.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import (  # noqa: E402
    REPORTS_DIR, ROOT, append_jsonl, build_run_meta, load_yaml, read_jsonl, utcnow,
)
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.adapters.base import build_adapter  # noqa: E402
from evaluation.validate.checks.runtime import capture_versioning_snapshot  # noqa: E402


def run_system(sys_cfg: dict, samples: list[dict], experiment: dict,
               out_dir: Path, resume: bool) -> dict:
    system_id = sys_cfg["id"]
    results_path = out_dir / f"{system_id}.results.jsonl"
    done_ids: set[str] = set()
    if resume and results_path.exists():
        done_ids = {r["sample_id"] for r in read_jsonl(results_path) if r.get("ok")}
        print(f"[{system_id}] resume: bỏ qua {len(done_ids)} sample đã xong")

    adapter = build_adapter(sys_cfg, experiment)
    adapter.prepare()

    stats = {"ok": 0, "failed": 0, "skipped": len(done_ids)}
    max_retries = max(1, experiment.get("max_retries", 1))
    try:
        for i, sample in enumerate(samples, 1):
            if sample["sample_id"] in done_ids:
                continue
            record = None
            for attempt in range(max_retries):
                record = adapter.run(sample)
                if record["ok"]:
                    break
                record["retry_attempt"] = attempt + 1
                time.sleep(2)
            record["run_at"] = utcnow()
            append_jsonl(results_path, record)
            stats["ok" if record["ok"] else "failed"] += 1
            if i % 10 == 0 or not record["ok"]:
                tag = "OK" if record["ok"] else f"FAIL({record['error']})"
                print(f"[{system_id}] {i}/{len(samples)} {sample['sample_id']} {tag} "
                      f"{record['timings_ms'].get('total', 0)}ms")
    finally:
        adapter.cleanup()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--systems", default=None, help="lọc theo id, vd: s0,s3")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    experiment_path = (ROOT / args.experiment).resolve()
    experiment = load_yaml(experiment_path)
    dataset_path = (ROOT / experiment["dataset"]).resolve()
    samples = load_dataset(dataset_path)
    if args.limit:
        samples = samples[: args.limit]

    out_dir = Path(args.out_dir) if args.out_dir else REPORTS_DIR / experiment["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    system_entries = [
        ((ROOT / p).resolve(), load_yaml((ROOT / p).resolve()))
        for p in experiment["systems"]
    ]
    if args.systems:
        wanted = set(args.systems.split(","))
        system_entries = [
            (path, cfg) for path, cfg in system_entries if cfg["id"] in wanted
        ]
    system_cfgs = [cfg for _, cfg in system_entries]
    system_paths = {cfg["id"]: path for path, cfg in system_entries}

    versioning = capture_versioning_snapshot(
        dataset_path,
        experiment_path,
        system_paths,
        {cfg["id"]: cfg for cfg in system_cfgs},
    )
    meta = build_run_meta({
        "experiment": experiment,
        "n_samples": len(samples),
        "systems": [c["id"] for c in system_cfgs],
        "dataset": experiment["dataset"],
        **versioning,
    })
    (out_dir / "run_meta.json").write_text(
        __import__("json").dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    tier = experiment.get("tier", "t3")
    for cfg in system_cfgs:
        if tier == "t4" and cfg["id"] != system_cfgs[0]["id"]:
            input(f"\n>>> T4: restart backend với LLM_MODEL={cfg.get('model')} "
                  f"rồi Enter để chạy {cfg['id']}... ")
        print(f"\n===== {cfg['id']} ({cfg['name']}) | tier={tier} | n={len(samples)} =====")
        stats = run_system(cfg, samples, experiment, out_dir, args.resume)
        print(f"[{cfg['id']}] done: {stats}")

    print(f"\nResults: {out_dir}")
    print("Tiếp theo: python -m evaluation.analysis.report --run-dir", out_dir)


if __name__ == "__main__":
    main()
