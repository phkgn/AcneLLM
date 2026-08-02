"""Sinh Modelfile cho `acne-generator-base` = base Qwen2.5-7B + CÙNG SYSTEM/TEMPLATE
với bản finetune (model/role_finetune/Modelfile.full) để kiểm soát system-prompt confound (R1).

Đọc trực tiếp Modelfile của bản finetune (không copy tay → không drift), chỉ thay dòng FROM.

Usage:
    python evaluation/scripts/make_base_modelfile.py
    ollama pull qwen2.5:7b
    ollama create acne-generator-base -f evaluation/modelfiles/acne-generator-base/Modelfile
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, sha256_text  # noqa: E402

# Phải trỏ ĐÚNG Modelfile dùng build acne-generator, nếu không base control sẽ lệch
# stop tokens / sampling params so với arm finetune → hỏng kiểm soát R1.
SRC = ROOT / "model" / "role_finetune" / "Modelfile.full"
DST = ROOT / "evaluation" / "modelfiles" / "acne-generator-base" / "Modelfile"
# Registry qwen2.5:7b mặc định Q4_K_M — xác nhận trên máy bằng `ollama show qwen2.5:7b`
BASE_REF = "qcwind/qwen2.5-7B-instruct-Q4_K_M"


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    out, n = re.subn(r"^FROM\s+\S+", f"FROM {BASE_REF}", text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"Không tìm thấy dòng FROM trong {SRC}")
    header = (
        f"# AUTO-GENERATED từ {SRC.relative_to(ROOT).as_posix()} — KHÔNG sửa tay.\n"
        f"# source_modelfile_sha256: {sha256_text(text)}\n"
        f"# Chạy lại: python evaluation/scripts/make_base_modelfile.py\n\n"
    )
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(header + out, encoding="utf-8")
    print(f"Wrote {DST}")
    print(f"Next: ollama pull {BASE_REF} && "
          f"ollama create acne-generator-base -f {DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
