"""Sinh Modelfile cho `qwen25-base-acnesys` = base Qwen2.5-7B + CÙNG SYSTEM/TEMPLATE
với bản finetune (model/V2/Q4/Modelfile) để kiểm soát system-prompt confound (R1).

Đọc trực tiếp Modelfile của bản finetune (không copy tay → không drift), chỉ thay dòng FROM.

Usage:
    python evaluation/scripts/make_base_modelfile.py
    ollama pull qwen2.5:7b
    ollama create qwen25-base-acnesys -f evaluation/modelfiles/qwen25-base-acnesys/Modelfile
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, sha256_text  # noqa: E402

SRC = ROOT / "model" / "V2" / "Q4" / "Modelfile"
DST = ROOT / "evaluation" / "modelfiles" / "qwen25-base-acnesys" / "Modelfile"
# Registry qwen2.5:7b mặc định Q4_K_M — xác nhận trên máy bằng `ollama show qwen2.5:7b`
BASE_REF = "qwen2.5:7b"


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    out, n = re.subn(r"^FROM\s+\S+", f"FROM {BASE_REF}", text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"Không tìm thấy dòng FROM trong {SRC}")
    header = (
        "# AUTO-GENERATED từ model/V2/Q4/Modelfile — KHÔNG sửa tay.\n"
        f"# source_modelfile_sha256: {sha256_text(text)}\n"
        f"# Chạy lại: python evaluation/scripts/make_base_modelfile.py\n\n"
    )
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(header + out, encoding="utf-8")
    print(f"Wrote {DST}")
    print(f"Next: ollama pull {BASE_REF} && "
          f"ollama create qwen25-base-acnesys -f {DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
