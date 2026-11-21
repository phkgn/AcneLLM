"""Split v2 — chia theo NGUỒN, không theo từng bản ghi.

Vấn đề của split v1: nó xáo từng bản ghi rồi cắt. Đo trên output vòng 1:
  - 9/40 `anchor_group` của B5 bị tách qua nhiều split — bản beginner nằm ở
    train, bản advanced nằm ở val, trên CÙNG một chunk nguồn;
  - 7 source_id của val và 4 của holdout cũng xuất hiện trong train.

Model gặp nội dung đó lúc train rồi được chấm lại trên đúng nội dung đó ở val =>
val cho điểm cao giả => chọn nhầm checkpoint. Không ảnh hưởng chất lượng data,
ảnh hưởng khả năng biết data tốt hay không.

Sửa: gom bản ghi thành nhóm bất khả phân (anchor_group > source_id > id), xáo
NHÓM rồi phát nguyên nhóm. Kích thước split lệch vài bản ghi so với 85/8/7 —
chấp nhận được, vì `_split_sizes` chỉ dùng để ra hạn mức chứ không có bất biến
nào đòi khớp chính xác.

ponytail: chỉ thay vòng phát; `_split_sizes`, `_allocate_by_case`, `_write_jsonl`
dùng lại nguyên của v1.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from typing import Any

from ...roledata.finalize.split import (
    SAFETY_HOLDOUT_CASES,
    _allocate_by_case,
    _split_sizes,
    _write_jsonl,
)
from ...roledata.writer import iter_jsonl
from ..config import Config


def group_key(record: dict[str, Any]) -> str:
    """Khoá nhóm bất khả phân của một bản ghi.

    Ưu tiên `anchor_group` (cặp B5 phải đi cùng nhau), rồi tới source_id đầu tiên
    (hai bản ghi dùng chung một chunk thì không được nằm hai bên), cuối cùng là
    chính id — bản ghi không có nguồn thì tự nó là một nhóm.
    """
    anchor = record.get("anchor_group")
    if isinstance(anchor, str) and anchor:
        return f"anchor:{anchor}"
    # Bỏ đoạn nhiễu tổng hợp: nó là chuỗi cứng dùng chung cho MỌI mẫu B3, gom
    # theo nó thì cả B3 thành một nhóm khổng lồ và không chia được nữa.
    sources = [
        str(item)
        for item in (record.get("synthetic_context_sources") or [])
        if not str(item).startswith("synthetic-")
    ]
    if sources:
        return f"src:{min(sources)}"
    return f"id:{record.get('id')}"


def split(cfg: Config, seed: int = 42) -> dict[str, Any]:
    records = list(iter_jsonl(cfg.train_path))
    ids = [record.get("id") for record in records]
    if any(not isinstance(record_id, str) or not record_id for record_id in ids):
        raise ValueError("Mọi bản ghi phải có id là chuỗi không rỗng")
    duplicates = [record_id for record_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"id trùng nhau nên không chia an toàn được: {duplicates[:3]}")

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        case = record.get("sample_kind")
        if not isinstance(case, str) or not case:
            raise ValueError(f"Bản ghi {record.get('id')!r} thiếu sample_kind")
        by_case[case].append(record)

    present_safety = sorted(SAFETY_HOLDOUT_CASES & set(by_case))
    sizes = _split_sizes(len(records), len(present_safety))
    counts = {case: len(rows) for case, rows in by_case.items()}
    holdout_quota = _allocate_by_case(counts, sizes["holdout"], required=present_safety)
    remaining = {case: counts[case] - holdout_quota[case] for case in counts}
    val_quota = _allocate_by_case(remaining, sizes["val"])

    rng = random.Random(seed)
    out: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "holdout": []}
    split_groups: dict[str, set[str]] = {"train": set(), "val": set(), "holdout": set()}

    for case in sorted(by_case):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in by_case[case]:
            grouped[group_key(record)].append(record)
        keys = sorted(grouped)
        rng.shuffle(keys)

        # Phát NGUYÊN nhóm, đổi đích khi đã đủ hạn mức. Nhóm cuối có thể làm vượt
        # hạn mức một hai bản ghi — rẻ hơn nhiều so với để lọt cặp qua hai split.
        target = "holdout"
        for key in keys:
            rows = grouped[key]
            if target == "holdout" and len(out["holdout"]) >= sum(
                holdout_quota[item] for item in sorted(by_case) if item <= case
            ):
                target = "val"
            if target == "val" and len(out["val"]) >= sum(
                val_quota[item] for item in sorted(by_case) if item <= case
            ):
                target = "train"
            out[target].extend(rows)
            split_groups[target].add(key)

    for name in out:
        rng.shuffle(out[name])

    id_sets = {name: {str(row["id"]) for row in rows} for name, rows in out.items()}
    if (
        id_sets["train"] & id_sets["val"]
        or id_sets["train"] & id_sets["holdout"]
        or id_sets["val"] & id_sets["holdout"]
        or len(set().union(*id_sets.values())) != len(records)
    ):
        raise RuntimeError("Bất biến chống rò rỉ ID thất bại")
    leaked = (
        (split_groups["train"] & split_groups["val"])
        | (split_groups["train"] & split_groups["holdout"])
        | (split_groups["val"] & split_groups["holdout"])
    )
    if leaked:
        raise RuntimeError(f"Nhóm nguồn bị tách qua nhiều split: {sorted(leaked)[:3]}")

    _write_jsonl(cfg.train_split_path, out["train"])
    _write_jsonl(cfg.val_split_path, out["val"])
    _write_jsonl(cfg.holdout_split_path, out["holdout"])
    return {
        "seed": seed,
        "total": len(records),
        "counts": {name: len(rows) for name, rows in out.items()},
        "groups": {name: len(keys) for name, keys in split_groups.items()},
        "safety_holdout_cases": sorted(
            {str(row["sample_kind"]) for row in out["holdout"]} & SAFETY_HOLDOUT_CASES
        ),
        "leakage": 0,
        "group_leakage": 0,
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - tiện tay
    print(json.dumps(split(Config()), ensure_ascii=False, indent=2))
    return 0
