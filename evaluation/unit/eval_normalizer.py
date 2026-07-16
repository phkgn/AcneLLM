"""T1 — Normalizer (extraction) eval: DELEGATE sang harness legacy đã kiểm chứng.

Lý do không viết lại: `scripts/eval/normalizer/` đã có gold testset 1.000 mẫu +
taxonomy projection (label space gold ≠ label space normalizer — so sánh naive sẽ
sai; xem docstring taxonomy.py). Viết lại = nguy cơ drift. File này chỉ:
  1. chạy legacy evaluate.py (subprocess, cwd đúng)
  2. copy report vào evaluation/reports/unit/normalizer/ (chuẩn hóa vị trí output)
  3. trích các metric chính vào summary chuẩn của harness

Usage:
    python -m evaluation.unit.eval_normalizer [--worst 50]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, REPORTS_DIR, utcnow  # noqa: E402

LEGACY_DIR = ROOT / "scripts" / "eval" / "normalizer"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worst", type=int, default=30)
    args = ap.parse_args()

    if not (LEGACY_DIR / "evaluate.py").exists():
        raise SystemExit(f"Không thấy {LEGACY_DIR}/evaluate.py")

    proc = subprocess.run(
        [sys.executable, "evaluate.py", "--worst", str(args.worst)],
        cwd=LEGACY_DIR, capture_output=True, text=True,
    )
    print(proc.stdout[-3000:])
    if proc.returncode != 0:
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"legacy evaluate.py exit {proc.returncode}")

    out = REPORTS_DIR / "unit" / "normalizer"
    out.mkdir(parents=True, exist_ok=True)
    legacy_reports = LEGACY_DIR / "reports"
    copied = []
    for name in ("report.json", "report.md", "per_sample.csv", "worst_cases.jsonl"):
        src = legacy_reports / name
        if src.exists():
            shutil.copy2(src, out / name)
            copied.append(name)

    # Trích metric chính vào summary chuẩn harness
    summary = {"generated_at": utcnow(), "delegated_to": str(LEGACY_DIR),
               "copied": copied}
    report_json = out / "report.json"
    if report_json.exists():
        try:
            legacy = json.loads(report_json.read_text(encoding="utf-8"))
            summary["legacy_top_level_keys"] = sorted(legacy)[:20]
            summary["extract"] = _extract_headline(legacy)
        except Exception as exc:  # noqa: BLE001
            summary["extract_error"] = str(exc)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out} ({', '.join(copied)})")


def _extract_headline(legacy: dict) -> dict:
    """Best-effort: lấy micro_f1/accuracy per field nếu cấu trúc legacy khớp."""
    headline: dict = {}
    for field, val in legacy.items():
        if isinstance(val, dict):
            for key in ("micro_f1", "f1", "accuracy", "mean_jaccard"):
                if isinstance(val.get(key), (int, float)):
                    headline.setdefault(field, {})[key] = val[key]
    return headline


if __name__ == "__main__":
    main()
