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
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import (  # noqa: E402
    REPORTS_DIR, ROOT, append_jsonl, build_run_meta, load_yaml, read_jsonl,
    sha256_file, utcnow,
)
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.adapters.base import build_adapter  # noqa: E402
from evaluation.validate.checks.runtime import (  # noqa: E402
    capture_versioning_snapshot, system_config_hashes,
)


def validate_output_state(
    out_dir: Path,
    resume: bool,
    expected: dict,
) -> dict | None:
    result_paths = list(out_dir.glob("*.results.jsonl"))
    if result_paths and not resume:
        raise ValueError(
            "Output directory already contains results; choose a new --out-dir "
            "or pass --resume."
        )

    meta_path = out_dir / "run_meta.json"
    if not resume or (not result_paths and not meta_path.exists()):
        return None
    if not meta_path.exists():
        raise ValueError(
            "Cannot resume because run_meta.json is missing; choose a new --out-dir."
        )
    try:
        existing = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot resume from invalid run_meta.json: {exc}") from exc

    mismatches = []
    for key in ("dataset", "dataset_sha256", "experiment_config_sha256"):
        if existing.get(key) != expected.get(key):
            mismatches.append(key)

    existing_hashes = existing.get("system_config_hashes")
    if not isinstance(existing_hashes, dict):
        existing_hashes = {}
    result_systems = {
        path.name.removesuffix(".results.jsonl") for path in result_paths
    }
    for system_id, expected_hash in expected["system_config_hashes"].items():
        existing_hash = existing_hashes.get(system_id)
        if (
            existing_hash is not None
            and existing_hash != expected_hash
        ) or (
            system_id in result_systems
            and existing_hash != expected_hash
        ):
            mismatches.append(f"system_config_hashes.{system_id}")

    if mismatches:
        raise ValueError(
            "Resume metadata mismatch for "
            + ", ".join(sorted(set(mismatches)))
            + "; choose a new --out-dir."
        )
    return existing


def merge_run_meta(existing: dict | None, current: dict) -> dict:
    if not existing:
        return current
    merged = {**existing, **current}
    merged["systems"] = sorted({
        *map(str, existing.get("systems") or []),
        *map(str, current.get("systems") or []),
    })
    for key in ("system_config_hashes", "model_digests"):
        merged[key] = {
            **(existing.get(key) or {}),
            **(current.get(key) or {}),
        }

    existing_prompts = existing.get("prompt_hashes") or {}
    current_prompts = current.get("prompt_hashes") or {}
    merged["prompt_hashes"] = {
        key: {
            **(existing_prompts.get(key) or {}),
            **(current_prompts.get(key) or {}),
        }
        for key in ("templates", "judge_prompts", "system_prompts")
    }
    return merged


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
    if not system_cfgs:
        ap.error("Không có system hợp lệ để chạy.")

    expected_state = {
        "dataset": experiment["dataset"],
        "dataset_sha256": sha256_file(dataset_path),
        "experiment_config_sha256": sha256_file(experiment_path),
        "system_config_hashes": system_config_hashes(system_paths),
    }
    try:
        existing_meta = validate_output_state(
            out_dir,
            args.resume,
            expected_state,
        )
    except ValueError as exc:
        ap.error(str(exc))

    versioning = capture_versioning_snapshot(
        dataset_path,
        experiment_path,
        system_paths,
        {cfg["id"]: cfg for cfg in system_cfgs},
    )
    current_meta = build_run_meta({
        "experiment": experiment,
        "n_samples": len(samples),
        "systems": [c["id"] for c in system_cfgs],
        "dataset": experiment["dataset"],
        **versioning,
    })
    meta = merge_run_meta(existing_meta, current_meta)
    (out_dir / "run_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
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
