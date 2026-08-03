"""Orchestrator 2 khâu: kiểm tra môi trường → intake → ablation.

    khâu 1  intake    — intaker rút đúng 15 slot không       (không cần judge)
    khâu 2  ablation  — thay từng khâu bằng bản hoàn hảo / tắt hẳn,
                        xem câu trả lời chênh bao nhiêu      (cần judge)

Đánh giá RAG nội tại (nDCG/recall@k trên qrels) đã bỏ: tầm quan trọng của RAG
đo bằng arm trong khâu 2 chứ không cần qrels người gán. Lấy lại bằng
`git show <commit>:evaluation/runners/run_retrieval.py` nếu sau này cần.

Mỗi bước là subprocess độc lập; bước fail không kéo sập bước sau (trừ preflight).

Usage:
    python -m evaluation.full_evaluation                 # đầy đủ
    python -m evaluation.full_evaluation --smoke         # 10 mẫu/bước
    python -m evaluation.full_evaluation --skip intake
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
from evaluation.common import ROOT, REPORTS_DIR, utcnow  # noqa: E402
from evaluation.runners.run_ablation import DEFAULT_ARMS  # noqa: E402

PY = sys.executable
DATASET = "evaluation/datasets/eval_set.jsonl"

STEP_DEFINITIONS = (
    ("preflight", "Kiểm tra môi trường"),
    ("intake", "Khâu 1 — Intaker"),
    ("ablation", "Khâu 2 — Ablation oracle"),
)
TERMINAL_STATUSES = {"ok", "fail", "skipped"}


def _one_line(detail: str) -> str:
    return re.sub(r"\s+", " ", detail).strip()


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Ghi snapshot JSON hoàn chỉnh, không bao giờ lộ document dở."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
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
    step.update(
        status="running", started_at=utcnow(), finished_at=None,
        duration_s=None, detail="",
    )
    summary["current_step"] = step_id
    _atomic_write_json(summary_path, summary)
    print(
        f"[runall] step={_step_number(step_id)}/{len(STEP_DEFINITIONS)} "
        f"id={step_id} status=start",
        flush=True,
    )
    return time.monotonic()


def _finish_step(
    summary: dict, summary_path: Path, step_id: str, status: str,
    started: float, detail: str = "",
) -> None:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"Invalid terminal step status: {status}")
    duration = round(max(time.monotonic() - started, 0.0), 1)
    step = _step(summary, step_id)
    step.update(
        status=status, finished_at=utcnow(), duration_s=duration,
        detail=_one_line(detail),
    )
    summary["current_step"] = None
    _atomic_write_json(summary_path, summary)
    print(
        f"[runall] step={_step_number(step_id)}/{len(STEP_DEFINITIONS)} "
        f"id={step_id} status={status} duration={duration:.1f}s",
        flush=True,
    )


def _skip_step(summary: dict, summary_path: Path, step_id: str, detail: str) -> None:
    started = _start_step(summary, summary_path, step_id)
    _finish_step(summary, summary_path, step_id, "skipped", started, detail)


def sh(label: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 60}\n[{label}] {' '.join(cmd)}\n{'=' * 60}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode == 0


def _has_openai_key() -> bool:
    env = (ROOT / ".env").read_text(encoding="utf-8") if (ROOT / ".env").exists() else ""
    return bool(os.environ.get("OPENAI_API_KEY")) or bool(
        re.search(r"^\s*OPENAI_API_KEY\s*=\s*[^#\s].*$", env, re.MULTILINE)
    )


def preflight(skip: set[str]) -> list[str]:
    problems: list[str] = []
    if not (ROOT / "data" / "chroma_db").exists():
        problems.append("Thiếu data/chroma_db (git lfs pull)")
    if not (ROOT / "data" / "bm25_index.pkl").exists():
        problems.append("Thiếu data/bm25_index.pkl (python scripts/build_kb.py --step bm25)")
    if not (ROOT / DATASET).exists():
        problems.append(f"Thiếu {DATASET}")
    if "ablation" not in skip:
        from acne_llm.config import settings

        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
                raw = {m["name"] for m in json.loads(r.read())["models"]}
            tags = raw | {t.split(":")[0] for t in raw}   # khớp cả có/không tag
        except Exception:
            problems.append("Ollama không chạy tại localhost:11434 (ollama serve)")
            tags = set()
        model = settings.llm_model
        if tags and model not in tags and f"{model}:latest" not in tags:
            problems.append(f"Ollama thiếu model '{model}'")
        if not _has_openai_key():
            problems.append("⚠ Thiếu OPENAI_API_KEY; bước ablation sẽ bị bỏ qua")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="10 mẫu/bước")
    ap.add_argument("--skip", default="", help="intake,ablation")
    ap.add_argument("--limit", type=int, default=0, help="0 = all rows")
    ap.add_argument("--dataset", default=DATASET, help="bộ câu hỏi cho khâu 2")
    ap.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    ap.add_argument("--out", default=None, help="thư mục output của run")
    ap.add_argument("--yes", action="store_true", help="chấp thuận trước bước tốn phí API")
    ap.add_argument("--force", action="store_true", help="chạy tiếp dù preflight lỗi cứng")
    args = ap.parse_args()
    if args.limit < 0:
        ap.error("--limit must be non-negative")
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    unknown = skip - {step_id for step_id, _ in STEP_DEFINITIONS[1:]}
    if unknown:
        ap.error(f"--skip không hợp lệ: {sorted(unknown)}")
    selected_limit = args.limit or (10 if args.smoke else 0)
    limit = ["--limit", str(selected_limit)] if selected_limit else []

    # Artifact ablation gắn với đúng bộ câu hỏi đã chạy (question_fingerprint).
    # Dùng chung thư mục cho smoke 10 mẫu và run đầy đủ 100 mẫu → fingerprint
    # lệch → RuntimeError. Tách sẵn thay vì bắt người dùng tự nhớ --out.
    default_dir = "full_eval_smoke" if args.smoke else "full_eval"
    run_dir = Path(args.out) if args.out else REPORTS_DIR / default_dir
    run_dir = (run_dir if run_dir.is_absolute() else ROOT / run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"
    summary = _new_summary(run_dir)
    _atomic_write_json(summary_path, summary)
    t0 = summary["started_at"]

    # ── Preflight ───────────────────────────────────────────────────────
    step_started = _start_step(summary, summary_path, "preflight")
    problems = preflight(skip)
    hard = [p for p in problems if not p.startswith("⚠")]
    if problems:
        print("PREFLIGHT:")
        for p in problems:
            print(f"  ✗ {p}")
    # Lỗi cứng chặn run: --yes chỉ chấp thuận chi phí, không bỏ qua môi trường hỏng.
    if hard and not args.force:
        _finish_step(summary, summary_path, "preflight", "fail", step_started,
                     "; ".join(hard))
        for pending_id, _ in STEP_DEFINITIONS[1:]:
            _skip_step(summary, summary_path, pending_id, "Preflight failed.")
        summary["finished_at"] = utcnow()
        _atomic_write_json(summary_path, summary)
        raise SystemExit("Sửa các mục trên, hoặc --skip bước tương ứng, hoặc --force.")
    _finish_step(summary, summary_path, "preflight", "ok", step_started,
                 "; ".join(problems) if problems else "")

    # ── Khâu 1 — Intaker ────────────────────────────────────────────────
    if "intake" in skip:
        _skip_step(summary, summary_path, "intake", "--skip intake")
    else:
        step_started = _start_step(summary, summary_path, "intake")
        ok = sh("intake", [
            PY, "-m", "evaluation.runners.run_intake",
            "--output", str(run_dir / "intake" / "report.json"), *limit,
        ])
        _finish_step(summary, summary_path, "intake",
                     "ok" if ok else "fail", step_started,
                     "" if ok else "run_intake exit != 0")

    # ── Khâu 2 — Ablation ───────────────────────────────────────────────
    if "ablation" in skip:
        _skip_step(summary, summary_path, "ablation", "--skip ablation")
    elif not _has_openai_key():
        _skip_step(summary, summary_path, "ablation",
                   "Thiếu OPENAI_API_KEY (judge + arm RRO cần API).")
    elif not (args.yes or _confirm_cost()):
        _skip_step(summary, summary_path, "ablation",
                   "Chưa chấp thuận cost gate; dùng --yes để bỏ qua hỏi lại.")
    else:
        step_started = _start_step(summary, summary_path, "ablation")
        ok = sh("ablation", [
            PY, "-m", "evaluation.runners.run_ablation",
            "--arms", args.arms,
            "--dataset", args.dataset,
            "--output", str(run_dir / "ablation" / "results.json"), *limit,
        ])
        _finish_step(summary, summary_path, "ablation",
                     "ok" if ok else "fail", step_started,
                     "" if ok else "run_ablation exit != 0")

    summary["finished_at"] = utcnow()
    summary["current_step"] = None
    _atomic_write_json(summary_path, summary)

    print(f"\n{'=' * 60}\nFULL EVALUATION — started {t0}\n{'=' * 60}")
    for step in summary["steps"]:
        mark = {"ok": "✓", "fail": "✗", "skipped": "–"}.get(step["status"], "?")
        detail = f" ({step['detail']})" if step["detail"] else ""
        print(f"  {mark} {step['id']}: {step['status']}{detail}")
    print(f"\nOutputs: {run_dir}/")


def _confirm_cost() -> bool:
    try:
        return input(
            "Ablation gọi judge + generator API, có phát sinh chi phí. Tiếp tục? [y/N] "
        ).strip().casefold() in {"y", "yes"}
    except EOFError:
        return False


if __name__ == "__main__":
    main()
