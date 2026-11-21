"""CLI split + export cho roledata **v2**.

    python -m datagen.roledatav2.finalize            # split (seed 42) + export
    python -m datagen.roledatav2.finalize --seed 7
    python -m datagen.roledatav2.finalize --split-only

Vì sao cần file này: `datagen/roledata/finalize/split.py::main()` hardcode
`Config()` của **v1**, nên chạy nó sẽ chia dữ liệu v1 chứ không phải v2. Bản thân
`split()`/`export()` đều nhận `cfg`, nên chỉ thiếu đúng một chỗ cắm Config v2.

Đọc  : datagen/roledatav2/output/roledata.train.jsonl
Ghi  : output/splits/{train,val,holdout}.jsonl   — 85 / 8 / 7, phân tầng theo
                                                   `sample_kind`, không rò ID
       output/export/acnellm_role_lora.jsonl     — {id, messages}, sharegpt
       output/export/dataset_info.json
       output/checksum.sha256
"""
from __future__ import annotations

import argparse
import json

from ..config import Config
from ...roledata.finalize import export as _export_module
from ...roledata.finalize.export import export
from ..gates import anchor_variants
from .split import split


def _system_ok_v2(system: str, anchor: str) -> bool:
    """Chấp nhận BẤT KỲ biến thể anchor đã đăng ký, không chỉ biến thể A.

    v2 rải ba biến thể theo lịch (~50/25/25) để model học LUẬT thay vì học chuỗi.
    Phép so một-chuỗi của v1 làm export chết ở bản ghi mang biến thể B hoặc C —
    cùng lỗi đã gặp ở `run_pipeline` khi resume. Vẫn là parity chặt: phải trùng
    đúng một trong ba chuỗi đã đăng ký, không phải "gần giống".
    """
    variants = anchor_variants()
    return system == anchor or (bool(variants) and system in variants)


# Vá TRƯỚC khi gọi `export()`; nó đọc `_system_ok` từ namespace của module.
_export_module._system_ok = _system_ok_v2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datagen.roledatav2.finalize", description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="seed chia split (mặc định 42)")
    parser.add_argument("--split-only", action="store_true", help="bỏ qua bước export")
    args = parser.parse_args(argv)

    cfg = Config()
    if not cfg.train_path.exists():
        parser.error(
            f"Không thấy {cfg.train_path}. Chạy pipeline sinh dữ liệu trước:\n"
            f"  python -m datagen.roledatav2.pipeline --yes"
        )

    result = {"split": split(cfg, seed=args.seed)}
    if not args.split_only:
        result["export"] = export(cfg)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
