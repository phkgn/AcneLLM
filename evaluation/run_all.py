"""ALL-IN-ONE orchestrator: preflight → T1 unit → T2 retrieval → T3 generation
→ judge → report → gate. Mỗi bước là subprocess độc lập, fail không kéo sập bước sau
(trừ preflight). T4 (SSE e2e) không auto vì cần restart backend giữa các condition.

Usage:
    python -m evaluation.run_all                        # full (T1+T2+T3+judge+report)
    python -m evaluation.run_all --smoke                # 10 mẫu/bước, kiểm tra ống nước
    python -m evaluation.run_all --skip t1,judge        # bỏ bước
    python -m evaluation.run_all --dataset evaluation/datasets/v1/d1_dev_seed.jsonl
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.common import ROOT, REPORTS_DIR, load_yaml, utcnow  # noqa: E402

PY = sys.executable
EXPERIMENT = "evaluation/configs/experiments/main_2x2.yaml"
QRELS = "evaluation/datasets/v1/d8_qrels_seed.jsonl"
T1_INTENT = "evaluation/datasets/v1/t1_intent_seed.jsonl"
T1_GUARD = "evaluation/datasets/v1/t1_guardrails_seed.jsonl"


def sh(step: str, cmd: list[str], results: dict) -> bool:
    print(f"\n{'=' * 60}\n[{step}] {' '.join(cmd)}\n{'=' * 60}")
    proc = subprocess.run(cmd, cwd=ROOT)
    results[step] = "OK" if proc.returncode == 0 else f"FAIL({proc.returncode})"
    return proc.returncode == 0


def preflight(experiment_cfg: dict, skip: set[str]) -> list[str]:
    problems: list[str] = []
    # KB artifacts
    if not (ROOT / "data" / "chroma_db").exists():
        problems.append("Thiếu data/chroma_db (git lfs pull)")
    if not (ROOT / "data" / "bm25_index.pkl").exists():
        problems.append("Thiếu data/bm25_index.pkl (python scripts/build_kb.py --step bm25)")
    # Ollama + models (cần cho T3)
    if "t3" not in skip:
        needed = set()
        for sys_path in experiment_cfg["systems"]:
            cfg = load_yaml(ROOT / sys_path)
            if cfg.get("model"):
                needed.add(cfg["model"])
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
                raw = {m["name"] for m in json.loads(r.read())["models"]}
            tags = raw | {t.split(":")[0] for t in raw}   # khớp cả có/không tag
        except Exception:
            problems.append("Ollama không chạy tại localhost:11434 (ollama serve)")
            tags = set()
        for model in needed:
            if tags and model not in tags and f"{model}:latest" not in tags:
                problems.append(
                    f"Ollama thiếu model '{model}'"
                    + (" — chạy: python evaluation/scripts/make_base_modelfile.py && "
                       "ollama create qwen25-base-acnesys -f "
                       "evaluation/modelfiles/qwen25-base-acnesys/Modelfile"
                       if model == "qwen25-base-acnesys" else "")
                )
    # Datasets
    for p in (T1_INTENT, T1_GUARD, QRELS):
        if not (ROOT / p).exists():
            problems.append(f"Thiếu {p} (python -m evaluation.datasets.build_seeds)")
    # Judge key
    if "judge" not in skip:
        env = (ROOT / ".env").read_text(encoding="utf-8") if (ROOT / ".env").exists() else ""
        if "DEEPSEEK_API_KEY=" not in env:
            problems.append("Thiếu DEEPSEEK_API_KEY trong .env (hoặc --skip judge)")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="10 mẫu/bước")
    ap.add_argument("--skip", default="", help="t1,t2,t3,judge,report,gate")
    ap.add_argument("--dataset", default=None,
                    help="override dataset T3 (mặc định lấy từ experiment yaml)")
    ap.add_argument("--experiment", default=EXPERIMENT)
    ap.add_argument("--yes", action="store_true", help="bỏ confirm khi có warning")
    args = ap.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    limit = ["--limit", "10"] if args.smoke else []

    experiment_cfg = load_yaml(ROOT / args.experiment)
    if args.dataset:
        experiment_cfg["dataset"] = args.dataset
    run_dir = REPORTS_DIR / experiment_cfg["name"]

    # ── Preflight ───────────────────────────────────────────────────────
    problems = preflight(experiment_cfg, skip)
    dataset_path = ROOT / experiment_cfg["dataset"]
    if not dataset_path.exists():
        problems.append(f"Dataset T3 chưa tồn tại: {experiment_cfg['dataset']} "
                        "(D2 phải viết theo blueprint §5; smoke test dùng "
                        "--dataset evaluation/datasets/v1/d1_dev_seed.jsonl)")
    hard = [p for p in problems if not p.startswith("⚠")]
    if problems:
        print("PREFLIGHT:")
        for p in problems:
            print(f"  ✗ {p}")
        if hard and not args.yes:
            raise SystemExit("Sửa các mục trên hoặc --skip bước tương ứng.")

    results: dict[str, str] = {}
    t0 = utcnow()

    # ── T1 unit ─────────────────────────────────────────────────────────
    if "t1" not in skip:
        sh("t1.normalizer", [PY, "-m", "evaluation.unit.eval_normalizer"], results)
        sh("t1.intent", [PY, "-m", "evaluation.unit.eval_intent_router",
                         "--dataset", T1_INTENT, *limit], results)
        sh("t1.planner", [PY, "-m", "evaluation.unit.eval_query_planner",
                          "--dataset", T1_INTENT, *limit], results)
        sh("t1.guardrails", [PY, "-m", "evaluation.unit.eval_guardrails",
                             "--dataset", T1_GUARD, *limit], results)

    # ── T2 retrieval + ablations ────────────────────────────────────────
    if "t2" not in skip:
        sh("t2.retrieval", [PY, "-m", "evaluation.runners.run_retrieval",
                            "--dataset", QRELS, *limit], results)
        sh("t2.raw_query_ablation", [PY, "-m", "evaluation.runners.run_retrieval",
                                     "--dataset", QRELS, "--modes", "hybrid_mmr_rerank",
                                     "--raw-query", *limit], results)

    # ── T3 generation S0-S4 ─────────────────────────────────────────────
    if "t3" not in skip and dataset_path.exists():
        cmd = [PY, "-m", "evaluation.runners.run_experiment",
               "--experiment", args.experiment, "--resume", *limit]
        if args.dataset:
            # run_experiment đọc dataset từ yaml → ghi yaml tạm khi override
            tmp = run_dir / "_experiment_override.yaml"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            import yaml
            tmp.write_text(yaml.safe_dump(experiment_cfg, allow_unicode=True),
                           encoding="utf-8")
            cmd = [PY, "-m", "evaluation.runners.run_experiment",
                   "--experiment", str(tmp.relative_to(ROOT)), "--resume", *limit]
        sh("t3.generation", cmd, results)

    # ── Judge ───────────────────────────────────────────────────────────
    if "judge" not in skip and run_dir.exists():
        pairs = ",".join(":".join(p) for p in experiment_cfg.get("comparisons", []))
        sh("judge", [PY, "-m", "evaluation.judges.run_judge",
                     "--run-dir", str(run_dir),
                     "--dataset", experiment_cfg["dataset"],
                     *(["--pairs", pairs] if pairs else []), *limit], results)

    # ── Report ──────────────────────────────────────────────────────────
    if "report" not in skip and run_dir.exists():
        pairs = ",".join(":".join(p) for p in experiment_cfg.get("comparisons", []))
        sh("report", [PY, "-m", "evaluation.analysis.report",
                      "--run-dir", str(run_dir),
                      "--dataset", experiment_cfg["dataset"],
                      *(["--comparisons", pairs] if pairs else [])], results)

    # ── Regression gate ─────────────────────────────────────────────────
    if "gate" not in skip:
        sh("gate", [PY, "-m", "evaluation.analysis.check_gate",
                    "--run-dir", str(run_dir)], results)

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}\nRUN ALL — started {t0}\n{'=' * 60}")
    for step, status in results.items():
        mark = "✓" if status == "OK" else "✗"
        print(f"  {mark} {step}: {status}")
    print(f"\nOutputs: {REPORTS_DIR}/unit/, {REPORTS_DIR}/retrieval/, {run_dir}/")
    print("Bước KHÔNG auto: T4 e2e (cần restart backend — xem "
          "evaluation/configs/experiments/e2e_sse.yaml), human annotation "
          "(export_blind → chấm → import_labels), relabel qrels D8.")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "run_all_last.json").write_text(
        json.dumps({"started": t0, "finished": utcnow(), "results": results},
                   indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
