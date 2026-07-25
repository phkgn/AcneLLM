"""Dashboard-only orchestrator for a provisional D2 evaluation.

This does not implement a second evaluation path. It invokes the same T3,
judge, and report modules used by the regular harness, but isolates artifacts
in a fresh report directory and labels them as synthetic-only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from acne_llm.config import settings  # noqa: E402
from evaluation.common import load_yaml, utcnow  # noqa: E402
from evaluation.judges.clients import (  # noqa: E402
    DEFAULT_JUDGE_WORKERS,
    DEFAULT_OPENAI_FAITHFULNESS_MODEL,
)
from evaluation.run_all import preflight  # noqa: E402

EXPERIMENT = "evaluation/configs/experiments/main_2x2.yaml"
DATASET = "evaluation/datasets/v1/d2_test.jsonl"
SYSTEMS = "s0,s1,s2,s3,s4"
PAIRS = "s0:s1,s0:s2,s1:s3,s2:s3"
REPORTS_ROOT = (ROOT / "evaluation" / "reports").resolve()

NOTICE = """# Preliminary Evaluation Notice

Status: PRELIMINARY_SYNTHETIC_ONLY

Mục đích: so sánh định hướng giữa các system và phát hiện lỗi pipeline.

- D2 hiện là synthetic-only; chưa có independent human verification.
- Chưa có human-written hoặc real-user cases.
- D8 bị loại khỏi run này vì pooled retrieval relabel chưa hoàn tất.
- Regression gate bị loại khỏi run này.
- Pointwise/pairwise dùng judge đã cấu hình; faithfulness dùng GPT-5 nano.
- LLM Judge chưa được calibration với human labels.

Không sử dụng kết quả này làm clinical ground truth, final benchmark,
production-readiness claim hoặc publication claim.
"""


def resolve_output_dir(raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ValueError("Output directory phải là đường dẫn tương đối trong evaluation/reports/.")
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPORTS_ROOT)
    except ValueError as exc:
        raise ValueError(
            "Output directory phải nằm trong evaluation/reports/."
        ) from exc
    return resolved, resolved.relative_to(ROOT).as_posix()


def build_steps(out_dir: str, limit: int) -> list[tuple[str, list[str]]]:
    py = sys.executable
    return [
        (
            "t3.generation",
            [
                py,
                "-m",
                "evaluation.runners.run_experiment",
                "--experiment",
                EXPERIMENT,
                "--systems",
                SYSTEMS,
                "--out-dir",
                out_dir,
                "--limit",
                str(limit),
            ],
        ),
        (
            "judge",
            [
                py,
                "-m",
                "evaluation.judges.run_judge",
                "--run-dir",
                out_dir,
                "--dataset",
                DATASET,
                "--provider",
                settings.judge_provider,
                "--model",
                settings.judge_model,
                "--faithfulness-model",
                DEFAULT_OPENAI_FAITHFULNESS_MODEL,
                "--workers",
                str(DEFAULT_JUDGE_WORKERS),
                "--pairs",
                PAIRS,
                "--limit",
                str(limit),
            ],
        ),
        (
            "report",
            [
                py,
                "-m",
                "evaluation.analysis.report",
                "--run-dir",
                out_dir,
                "--dataset",
                DATASET,
                "--comparisons",
                PAIRS,
            ],
        ),
    ]


def write_summary(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_step(name: str, command: list[str], summary: dict, summary_path: Path) -> bool:
    print(f"\n{'=' * 72}", flush=True)
    print(f"[preliminary:{name}] {' '.join(command)}", flush=True)
    print("=" * 72, flush=True)
    started = utcnow()
    result = subprocess.run(command, cwd=ROOT)
    summary["steps"][name] = {
        "status": "OK" if result.returncode == 0 else f"FAIL({result.returncode})",
        "started": started,
        "finished": utcnow(),
        "command": command,
    }
    write_summary(summary_path, summary)
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--limit", type=int, default=140)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="In các runner chuẩn sẽ được gọi, không tạo artifact.",
    )
    args = parser.parse_args()
    if args.limit < 30 or args.limit > 140:
        parser.error("Quick Run limit phải từ 30 đến 140.")

    try:
        out_dir, out_dir_relative = resolve_output_dir(args.out_dir)
    except ValueError as exc:
        parser.error(str(exc))

    steps = build_steps(out_dir_relative, args.limit)
    if args.dry_run:
        for name, command in steps:
            print(f"{name}: {' '.join(command)}")
        return

    if out_dir.exists() and any(out_dir.iterdir()):
        parser.error(
            "Quick preliminary luôn cần thư mục run mới để không trộn artifact cũ."
        )

    dataset_path = ROOT / DATASET
    if not dataset_path.exists():
        parser.error(f"Thiếu dataset {DATASET}.")

    experiment = load_yaml(ROOT / EXPERIMENT)
    problems = preflight(experiment, {"t1", "t2", "gate"})
    if problems:
        print("PREFLIGHT:", flush=True)
        for problem in problems:
            print(f"  ✗ {problem}", flush=True)
        raise SystemExit(2)

    out_dir.mkdir(parents=True, exist_ok=False)
    notice_path = out_dir / "PROVISIONAL_NOTICE.md"
    notice_path.write_text(NOTICE, encoding="utf-8")
    summary_path = out_dir / "preliminary_run.json"
    summary = {
        "profile": "PRELIMINARY_SYNTHETIC_ONLY",
        "started": utcnow(),
        "finished": None,
        "status": "running",
        "dataset": DATASET,
        "systems": SYSTEMS.split(","),
        "comparisons": PAIRS.split(","),
        "judge_provider": settings.judge_provider,
        "judge_model": settings.judge_model,
        "faithfulness_judge_model": DEFAULT_OPENAI_FAITHFULNESS_MODEL,
        "judge_workers": DEFAULT_JUDGE_WORKERS,
        "limit": args.limit,
        "run_dir": out_dir_relative,
        "notice": notice_path.relative_to(ROOT).as_posix(),
        "excluded": ["t1", "t2_d8", "gate", "judge_calibration"],
        "steps": {},
    }
    write_summary(summary_path, summary)

    generation_name, generation_command = steps[0]
    generation_ok = run_step(
        generation_name,
        generation_command,
        summary,
        summary_path,
    )
    if not generation_ok:
        summary["status"] = "failed"
        summary["finished"] = utcnow()
        summary["message"] = "Generation lỗi; judge và report không được chạy."
        write_summary(summary_path, summary)
        raise SystemExit(1)

    judge_name, judge_command = steps[1]
    judge_ok = run_step(judge_name, judge_command, summary, summary_path)

    report_name, report_command = steps[2]
    report_ok = run_step(report_name, report_command, summary, summary_path)

    summary["finished"] = utcnow()
    summary["status"] = "succeeded" if judge_ok and report_ok else "partial_failed"
    summary["message"] = (
        "Preliminary D2 hoàn tất. Chọn run này trong trang Results."
        if summary["status"] == "succeeded"
        else "Generation đã xong nhưng judge hoặc report lỗi; xem log và artifact."
    )
    write_summary(summary_path, summary)

    print(f"\n[preliminary] Run directory: {out_dir_relative}", flush=True)
    print(f"[preliminary] Notice: {notice_path.relative_to(ROOT).as_posix()}", flush=True)
    print(f"[preliminary] Status: {summary['status']}", flush=True)
    if summary["status"] != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
