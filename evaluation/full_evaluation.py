"""Orchestrator: kiểm tra môi trường → Intake → RAG → sinh câu trả lời
→ chấm điểm/báo cáo → phân tích nút thắt → biểu đồ. Mỗi bước là subprocess
độc lập, fail không kéo sập bước sau (trừ kiểm tra môi trường).

Usage:
    python -m evaluation.full_evaluation                        # đánh giá đầy đủ
    python -m evaluation.full_evaluation --smoke                # 10 mẫu/bước, kiểm tra ống nước
    python -m evaluation.full_evaluation --skip generation,scoring
    python -m evaluation.full_evaluation --dataset evaluation/datasets/v1/dev_tuning.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acne_llm.config import settings  # noqa: E402
from evaluation.common import ROOT, REPORTS_DIR, load_yaml, read_jsonl, utcnow  # noqa: E402
from evaluation.judges.clients import (  # noqa: E402
    DEFAULT_JUDGE_WORKERS,
    DEFAULT_OPENAI_FAITHFULNESS_MODEL,
)

PY = sys.executable
EXPERIMENT = "evaluation/configs/experiments/main_2x2.yaml"
QRELS = "evaluation/datasets/v1/retrieval_test.jsonl"

STEP_DEFINITIONS = (
    ("preflight", "Kiểm tra môi trường"),
    ("intake_eval", "Đánh giá Intake"),
    ("rag_eval", "Đánh giá RAG"),
    ("answer_generation", "Sinh câu trả lời"),
    ("scoring_report", "Chấm điểm + báo cáo"),
    ("bottleneck", "Phân tích nút thắt"),
    ("figures", "Biểu đồ"),
)
TERMINAL_STATUSES = {"ok", "fail", "skipped"}


def _one_line(detail: str) -> str:
    return re.sub(r"\s+", " ", detail).strip()


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write a complete JSON snapshot without exposing a partial document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _new_summary(run_dir: Path) -> dict:
    return {
        "run_id": run_dir.name,
        "out_dir": _display_path(run_dir),
        "started_at": utcnow(),
        "finished_at": None,
        "current_step": None,
        "steps": [
            {
                "id": step_id,
                "label": label,
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "duration_s": None,
                "detail": "",
            }
            for step_id, label in STEP_DEFINITIONS
        ],
    }


def _step(summary: dict, step_id: str) -> dict:
    return next(step for step in summary["steps"] if step["id"] == step_id)


def _step_number(step_id: str) -> int:
    return next(
        index
        for index, (candidate, _) in enumerate(STEP_DEFINITIONS, start=1)
        if candidate == step_id
    )


def _start_step(summary: dict, summary_path: Path, step_id: str) -> float:
    step = _step(summary, step_id)
    step["status"] = "running"
    step["started_at"] = utcnow()
    step["finished_at"] = None
    step["duration_s"] = None
    step["detail"] = ""
    summary["current_step"] = step_id
    _atomic_write_json(summary_path, summary)
    print(
        f"[runall] step={_step_number(step_id)}/{len(STEP_DEFINITIONS)} "
        f"id={step_id} status=start",
        flush=True,
    )
    return time.monotonic()


def _finish_step(
    summary: dict,
    summary_path: Path,
    step_id: str,
    status: str,
    started: float,
    detail: str = "",
) -> None:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"Invalid terminal step status: {status}")
    duration = round(max(time.monotonic() - started, 0.0), 1)
    step = _step(summary, step_id)
    step["status"] = status
    step["finished_at"] = utcnow()
    step["duration_s"] = duration
    step["detail"] = _one_line(detail)
    summary["current_step"] = None
    _atomic_write_json(summary_path, summary)
    print(
        f"[runall] step={_step_number(step_id)}/{len(STEP_DEFINITIONS)} "
        f"id={step_id} status={status} duration={duration:.1f}s",
        flush=True,
    )


def _skip_step(
    summary: dict,
    summary_path: Path,
    step_id: str,
    detail: str,
) -> None:
    started = _start_step(summary, summary_path, step_id)
    _finish_step(summary, summary_path, step_id, "skipped", started, detail)


def sh(step: str, cmd: list[str], results: dict) -> bool:
    print(f"\n{'=' * 60}\n[{step}] {' '.join(cmd)}\n{'=' * 60}")
    proc = subprocess.run(cmd, cwd=ROOT)
    results[step] = "OK" if proc.returncode == 0 else f"FAIL({proc.returncode})"
    return proc.returncode == 0


def _has_openai_key() -> bool:
    env = (ROOT / ".env").read_text(encoding="utf-8") if (ROOT / ".env").exists() else ""
    return bool(os.environ.get("OPENAI_API_KEY")) or bool(
        re.search(r"^\s*OPENAI_API_KEY\s*=\s*[^#\s].*$", env, re.MULTILINE)
    )


def _cost_gate(*, needed: bool, assume_yes: bool) -> tuple[bool, str]:
    if not needed:
        return False, "No paid step requested."
    if not _has_openai_key():
        return False, "Thiếu OPENAI_API_KEY; bỏ qua judge và bottleneck có chấm điểm."
    if assume_yes:
        return True, ""
    try:
        accepted = input(
            "Judge và bottleneck có thể phát sinh chi phí API. Tiếp tục? [y/N] "
        ).strip().casefold() in {"y", "yes"}
    except EOFError:
        accepted = False
    return (
        (True, "")
        if accepted
        else (False, "Người dùng chưa chấp thuận cost gate; dùng --yes để bỏ qua hỏi lại.")
    )


def _arm_marker(
    arm: str,
    status: str,
    *,
    duration_s: float | None = None,
) -> None:
    suffix = f" duration={duration_s:.1f}s" if duration_s is not None else ""
    print(
        f"[runall] step=6/7 id=bottleneck_{arm} status={status}{suffix}",
        flush=True,
    )


def _skip_arm(arm: str, reason: str) -> None:
    print(f"[bottleneck.{arm}] SKIPPED: {_one_line(reason)}", flush=True)
    _arm_marker(arm, "skipped")


def preflight(experiment_cfg: dict, skip: set[str]) -> list[str]:
    problems: list[str] = []
    # KB artifacts
    if not (ROOT / "data" / "chroma_db").exists():
        problems.append("Thiếu data/chroma_db (git lfs pull)")
    if not (ROOT / "data" / "bm25_index.pkl").exists():
        problems.append("Thiếu data/bm25_index.pkl (python scripts/build_kb.py --step bm25)")
    # Ollama + models (cần cho bước sinh câu trả lời)
    if "generation" not in skip:
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
                       "ollama create acne-generator-base -f "
                       "evaluation/modelfiles/acne-generator-base/Modelfile"
                       if model == "acne-generator-base" else "")
                )
    # Datasets
    for p in (QRELS,):
        if not (ROOT / p).exists():
            problems.append(f"Thiếu {p} (python -m evaluation.datasets.build_seeds)")
    # Judge key
    if "scoring" not in skip and not _has_openai_key():
        problems.append("⚠ Thiếu OPENAI_API_KEY; bước chấm điểm sẽ được bỏ qua")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="10 mẫu/bước")
    ap.add_argument(
        "--skip",
        default="",
        help="intake,rag,generation,scoring,bottleneck,figures",
    )
    ap.add_argument("--limit", type=int, default=0, help="0 = all rows")
    ap.add_argument("--dataset", default=None,
                    help="override dataset sinh câu trả lời (mặc định lấy từ experiment yaml)")
    ap.add_argument("--experiment", default=EXPERIMENT)
    ap.add_argument("--out", default=None, help="thư mục output của toàn bộ run")
    ap.add_argument("--yes", action="store_true",
                    help="chấp thuận trước các bước tốn phí API (không hỏi lại)")
    ap.add_argument("--force", action="store_true",
                    help="chạy tiếp dù preflight có lỗi cứng (Ollama/model/KB thiếu)")
    args = ap.parse_args()
    if args.limit < 0:
        ap.error("--limit must be non-negative")
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    selected_limit = args.limit or (10 if args.smoke else 0)
    limit = ["--limit", str(selected_limit)] if selected_limit else []

    experiment_cfg = load_yaml(ROOT / args.experiment)
    if args.dataset:
        experiment_cfg["dataset"] = args.dataset
    default_run_dir = REPORTS_DIR / experiment_cfg["name"]
    requested_run_dir = Path(args.out) if args.out else default_run_dir
    run_dir = (
        requested_run_dir
        if requested_run_dir.is_absolute()
        else ROOT / requested_run_dir
    ).resolve()
    run_dir_existed_before = run_dir.exists()
    run_dir.mkdir(parents=True, exist_ok=True)
    run_dir_arg = str(run_dir)
    summary_path = run_dir / "summary.json"
    summary = _new_summary(run_dir)
    _atomic_write_json(summary_path, summary)
    results: dict[str, str] = {}
    t0 = summary["started_at"]

    # ── Preflight ───────────────────────────────────────────────────────
    step_started = _start_step(summary, summary_path, "preflight")
    problems = preflight(experiment_cfg, skip)
    dataset_path = ROOT / experiment_cfg["dataset"]
    if not dataset_path.exists():
        problems.append(f"Dataset sinh câu trả lời chưa tồn tại: {experiment_cfg['dataset']} "
                        "(bộ test chất lượng phải được duyệt; smoke test dùng "
                        "--dataset evaluation/datasets/v1/dev_tuning.jsonl)")
    hard = [p for p in problems if not p.startswith("⚠")]
    if problems:
        print("PREFLIGHT:")
        for p in problems:
            print(f"  ✗ {p}")
        # Lỗi cứng chặn run: --yes chỉ chấp thuận chi phí, không phải bỏ qua môi trường hỏng.
        if hard and not args.force:
            _finish_step(
                summary,
                summary_path,
                "preflight",
                "fail",
                step_started,
                "; ".join(hard),
            )
            for pending_id, _ in STEP_DEFINITIONS[1:]:
                _skip_step(
                    summary,
                    summary_path,
                    pending_id,
                    "Preflight failed.",
                )
            summary["finished_at"] = utcnow()
            _atomic_write_json(summary_path, summary)
            raise SystemExit("Sửa các mục trên hoặc --skip bước tương ứng.")
    _finish_step(
        summary,
        summary_path,
        "preflight",
        "ok",
        step_started,
        "; ".join(problems) if problems else "",
    )

    # ── Unified intake evaluator ────────────────────────────────────────
    if "intake" in skip:
        _skip_step(summary, summary_path, "intake_eval", "--skip intake")
    else:
        step_started = _start_step(summary, summary_path, "intake_eval")
        intake_output = run_dir / "intake_eval" / "report.json"
        step_ok = sh(
            "intake",
            [PY, "scripts/eval_unified_intake.py", "--output", str(intake_output), *limit],
            results,
        )
        _finish_step(
            summary,
            summary_path,
            "intake_eval",
            "ok" if step_ok else "fail",
            step_started,
            "" if step_ok else results["intake"],
        )

    # ── Retrieval + ablations ───────────────────────────────────────────
    if "rag" in skip:
        _skip_step(summary, summary_path, "rag_eval", "--skip rag")
    else:
        step_started = _start_step(summary, summary_path, "rag_eval")
        step_ok = True
        for name, command in (
            (
                "retrieval",
                [PY, "-m", "evaluation.runners.run_retrieval",
                 "--dataset", QRELS, *limit],
            ),
            (
                "raw_query_ablation",
                [PY, "-m", "evaluation.runners.run_retrieval",
                 "--dataset", QRELS, "--modes", "hybrid_mmr_rerank",
                 "--raw-query", *limit],
            ),
        ):
            current_ok = sh(name, command, results)
            step_ok = step_ok and current_ok
        failed = [name for name, value in results.items()
                  if name in {"retrieval", "raw_query_ablation"} and value != "OK"]
        _finish_step(
            summary,
            summary_path,
            "rag_eval",
            "ok" if step_ok else "fail",
            step_started,
            f"Failed: {', '.join(failed)}" if failed else "",
        )

    # ── Answer generation across the configured systems ─────────────────
    generation_attempted = False
    if "generation" in skip:
        _skip_step(summary, summary_path, "answer_generation", "--skip generation")
    elif not dataset_path.exists():
        _skip_step(summary, summary_path, "answer_generation", "Dataset sinh câu trả lời bị thiếu.")
    else:
        step_started = _start_step(summary, summary_path, "answer_generation")
        generation_attempted = True
        cmd = [PY, "-m", "evaluation.runners.run_experiment",
               "--experiment", args.experiment, "--resume",
               "--out-dir", run_dir_arg, *limit]
        if args.dataset:
            # run_experiment đọc dataset từ yaml → ghi yaml tạm khi override
            tmp = run_dir / "_experiment_override.yaml"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            import yaml
            tmp.write_text(yaml.safe_dump(experiment_cfg, allow_unicode=True),
                           encoding="utf-8")
            cmd = [PY, "-m", "evaluation.runners.run_experiment",
                   "--experiment", str(tmp.relative_to(ROOT)), "--resume",
                   "--out-dir", run_dir_arg, *limit]
        step_ok = sh("answer_generation", cmd, results)
        _finish_step(
            summary,
            summary_path,
            "answer_generation",
            "ok" if step_ok else "fail",
            step_started,
            "" if step_ok else results["answer_generation"],
        )

    # ── One shared cost gate for judge and bottleneck ───────────────────
    runnable_artifacts = run_dir_existed_before or generation_attempted
    paid_needed = (
        ("scoring" not in skip and runnable_artifacts)
        or (not args.smoke and "bottleneck" not in skip)
    )
    paid_approved, paid_skip_reason = _cost_gate(
        needed=paid_needed,
        assume_yes=args.yes,
    )

    # ── LLM scoring + report + quality gate ──────────────────────────────
    scoring_report_commands: list[tuple[str, list[str]]] = []
    pairs = ",".join(":".join(p) for p in experiment_cfg.get("comparisons", []))
    scoring_was_requested = "scoring" not in skip and runnable_artifacts
    if scoring_was_requested and paid_approved:
        scoring_report_commands.append((
            "llm_scoring",
            [PY, "-m", "evaluation.judges.run_judge",
             "--run-dir", run_dir_arg,
             "--dataset", experiment_cfg["dataset"],
             "--provider", settings.judge_provider,
             "--model", settings.judge_model,
             "--faithfulness-model", DEFAULT_OPENAI_FAITHFULNESS_MODEL,
             "--workers", str(DEFAULT_JUDGE_WORKERS),
             *(["--pairs", pairs] if pairs else []), *limit],
        ))
    if "scoring" not in skip and runnable_artifacts:
        scoring_report_commands.append((
            "build_report",
            [PY, "-m", "evaluation.analysis.report",
             "--run-dir", run_dir_arg,
             "--dataset", experiment_cfg["dataset"],
             *(["--comparisons", pairs] if pairs else [])],
        ))
    # A 10-row smoke sample is a plumbing check, not a statistically valid
    # regression cohort. Running the production thresholds here creates a
    # predictable false-negative even when generation/judge/report all work.
    if "scoring" not in skip and not args.smoke:
        scoring_report_commands.append((
            "quality_gate",
            [PY, "-m", "evaluation.analysis.check_gate",
             "--run-dir", run_dir_arg],
        ))
    if scoring_was_requested and not paid_approved:
        _skip_step(
            summary,
            summary_path,
            "scoring_report",
            paid_skip_reason,
        )
    elif not scoring_report_commands:
        _skip_step(
            summary,
            summary_path,
            "scoring_report",
            "Chấm điểm, báo cáo và kiểm tra chất lượng đã bị bỏ qua hoặc chưa có artifact.",
        )
    else:
        step_started = _start_step(summary, summary_path, "scoring_report")
        step_ok = True
        for name, command in scoring_report_commands:
            current_ok = sh(name, command, results)
            step_ok = step_ok and current_ok
        failed = [name for name, _ in scoring_report_commands
                  if results.get(name) != "OK"]
        _finish_step(
            summary,
            summary_path,
            "scoring_report",
            "ok" if step_ok else "fail",
            step_started,
            f"Failed: {', '.join(failed)}" if failed else "",
        )

    # ── Bottleneck Z/X/W/Y ───────────────────────────────────────────────
    if args.smoke or "bottleneck" in skip or not paid_approved:
        reason = (
            "Smoke mode."
            if args.smoke
            else "--skip bottleneck"
            if "bottleneck" in skip
            else paid_skip_reason
        )
        _skip_step(summary, summary_path, "bottleneck", reason)
        for arm in ("z", "x", "w", "y"):
            _skip_arm(arm, reason)
    else:
        step_started = _start_step(summary, summary_path, "bottleneck")
        bottleneck_dir = run_dir / "bottleneck"
        bottleneck_output = bottleneck_dir / "results.json"
        selected_qrels = read_jsonl(ROOT / QRELS)
        if selected_limit:
            selected_qrels = selected_qrels[:selected_limit]
        x_missing_labels = [
            str(row.get("sample_id"))
            for row in selected_qrels
            if row.get("intent_label") not in {"advise", "knowledge", "clarify", "reject"}
        ]
        arm_failures: list[str] = []
        z_ok = False
        for arm in ("z", "x", "w", "y"):
            if arm == "x" and x_missing_labels:
                preview = ", ".join(x_missing_labels[:3])
                _skip_arm(
                    arm,
                    f"Thiếu intent_label hợp lệ ({len(x_missing_labels)} mẫu; {preview}).",
                )
                continue
            if arm != "z" and not z_ok:
                _skip_arm(arm, "Arm Z baseline failed.")
                continue
            arm_started = time.monotonic()
            _arm_marker(arm, "start")
            arm_ok = sh(
                f"bottleneck.{arm}",
                [
                    PY,
                    "scripts/eval_bottleneck.py",
                    "--arm",
                    arm,
                    "--dataset",
                    QRELS,
                    "--output",
                    str(bottleneck_output),
                    *limit,
                ],
                results,
            )
            _arm_marker(
                arm,
                "ok" if arm_ok else "fail",
                duration_s=time.monotonic() - arm_started,
            )
            if arm == "z":
                z_ok = arm_ok
            if not arm_ok:
                arm_failures.append(arm)

        summarize_ok = False
        if z_ok:
            summarize_ok = sh(
                "bottleneck.summarize",
                [
                    PY,
                    "scripts/eval_bottleneck.py",
                    "--summarize",
                    "--output",
                    str(bottleneck_output),
                    "--summary-output",
                    str(bottleneck_dir / "summary.json"),
                ],
                results,
            )
            if not summarize_ok:
                arm_failures.append("summarize")
        step_ok = z_ok and not arm_failures and summarize_ok
        _finish_step(
            summary,
            summary_path,
            "bottleneck",
            "ok" if step_ok else "fail",
            step_started,
            f"Failed: {', '.join(arm_failures)}" if arm_failures else "",
        )

    # ── Figures (fail-soft) ─────────────────────────────────────────────
    if args.smoke or "figures" in skip:
        _skip_step(
            summary,
            summary_path,
            "figures",
            "Smoke mode." if args.smoke else "--skip figures",
        )
    else:
        step_started = _start_step(summary, summary_path, "figures")
        figures_ok = sh(
            "figures",
            [PY, "-m", "evaluation.generate_figures", "--run-dir", run_dir_arg],
            results,
        )
        _finish_step(
            summary,
            summary_path,
            "figures",
            "ok" if figures_ok else "fail",
            step_started,
            "" if figures_ok else results["figures"],
        )

    summary["finished_at"] = utcnow()
    summary["current_step"] = None
    _atomic_write_json(summary_path, summary)

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}\nFULL EVALUATION — started {t0}\n{'=' * 60}")
    for step, status in results.items():
        mark = "✓" if status == "OK" else "✗"
        print(f"  {mark} {step}: {status}")
    print(f"\nOutputs: {run_dir}/")
    print("Bước KHÔNG auto: T4 e2e (cần restart backend — xem "
          "evaluation/configs/experiments/e2e_sse.yaml), human annotation "
          "(export_blind → chấm → import_labels), relabel bộ retrieval.")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "full_evaluation_last.json").write_text(
        json.dumps({"started": t0, "finished": utcnow(), "results": results},
                   indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
