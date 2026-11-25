"""Chọn chunk nguồn cho case B*/K1 — thay chính sách chọn nguồn của v1.

v1 (`roledata/generator._load_chunks`) đọc `data/raw/chunks.jsonl` tuần tự, lọc
theo từ khoá, **dừng ở 512 chunk đầu**. Hệ quả: 1.150 mẫu B*/K1 của v1 chia nhau
512 nguồn, và 512 nguồn đó chỉ là những dòng đầu file — phần lớn là
`vi_medical_site` vì nó chiếm 12.359/24.393.

v2 xếp theo `KNOWLEDGE_SOURCE_PRIORITY`: vét sạch tầng guideline trước
(nice + aad + clinical_textbook = 776 chunk dùng được), rồi mới bù xuống
pubmed/en/vi cho đủ số mẫu. Không có trần 512.
"""
from __future__ import annotations

import functools
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import KNOWLEDGE_SOURCE_PRIORITY, Config

__all__ = [
    "CONTEXT_CASE_ORDER",
    "case_offsets",
    "GUIDELINE_SOURCE_TYPES",
    "chunk_pool",
    "context_is_vietnamese",
    "pool_report",
    "usable_chunk",
]

GUIDELINE_SOURCE_TYPES = frozenset({"nice_guideline", "aad_guideline", "clinical_textbook"})

_KEYWORDS = ("mụn", "trứng cá", "acne", "retinoid", "benzoyl", "salicylic")
_MIN_TEXT_LEN = 180

_VI_DIACRITICS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")


def context_is_vietnamese(context: list[dict[str, str]] | None) -> bool:
    """Nguồn có phải tiếng Việt không — quyết định dùng gate nào để chấm bám nguồn.

    `grounded_rate` của v1 đo TRÙNG TOKEN giữa câu trả lời và nguồn. Anchor lại bắt
    trả lời 100% tiếng Việt kể cả khi tài liệu là tiếng Anh. Hai điều đó loại trừ
    nhau: câu trả lời Việt bám nguồn Anh cho `grounded_rate = 0.00`, chép nguyên
    nguồn thì `vietnamese_only` chặn. Toàn bộ tầng guideline (nice 172, aad 180,
    textbook 448) là tiếng Anh, nên phải đổi thước — xem `context.md` §1e:
    "không đo bằng từ vựng".

    Đo bằng dấu tiếng Việt thay vì trường `language` của chunk: nhãn đó do crawler
    gán và có 207 chunk `vi_medical_site` bị gắn `en`.
    """
    if not context:
        return True
    text = " ".join(
        str(item.get("text", "")) for item in context if item.get("label") != "Nguồn nhiễu"
    )
    if not text:
        return True
    marked = sum(1 for char in text if char in _VI_DIACRITICS)
    return marked / max(len(text), 1) >= 0.02


def usable_chunk(item: dict[str, Any]) -> bool:
    """Cùng tiêu chí v1: đủ dài và thực sự nói về mụn."""
    text = str(item.get("text") or "").strip()
    return len(text) >= _MIN_TEXT_LEN and any(token in text.casefold() for token in _KEYWORDS)


@functools.lru_cache(maxsize=4)
def _load(path_str: str, priority: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    path = Path(path_str)
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in priority}
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            source_type = str(item.get("source_type") or "unknown")
            if source_type in buckets and usable_chunk(item):
                # `embedding` nặng và không dùng tới; bỏ để pool không phình RAM.
                buckets[source_type].append({k: v for k, v in item.items() if k != "embedding"})
    ordered: list[dict[str, Any]] = []
    for name in priority:
        ordered.extend(sorted(buckets[name], key=lambda row: str(row.get("chunk_id"))))
    if not ordered:
        raise ValueError(f"Không tìm thấy chunk mụn dùng được trong {path}")
    return tuple(ordered)


def chunk_pool(cfg: Config) -> tuple[dict[str, Any], ...]:
    """Pool đã xếp ưu tiên; guideline đứng đầu, deterministic theo `chunk_id`."""
    return _load(str(cfg.knowledge_chunks_path), tuple(KNOWLEDGE_SOURCE_PRIORITY))


# Thứ tự ăn chunk guideline. Case nào cần thẩm quyền khuyến cáo nhất thì đứng
# trước: K1 (giữ kiến thức nền) rồi B1 (trả lời bám nguồn). B2 xếp cuối vì nó
# dạy TỪ CHỐI khi nguồn thiếu — chất lượng nguồn ít quan trọng nhất ở đó.
CONTEXT_CASE_ORDER: tuple[str, ...] = (
    "K1_knowledge_anchor",
    "B1_grounded_role",
    "B5_depth_anchor",
    "B4_conflicting_docs",
    "B3_irrelevant_chunk",
    "B2_missing_answer",
)


@functools.lru_cache(maxsize=1)
def case_offsets(targets: tuple[tuple[str, int], ...]) -> dict[str, int]:
    """Mỗi case một dải chunk RIÊNG, không chồng lấn.

    Không có bước này thì mọi case đều bắt đầu ở `sequence = 0` nên cùng ăn các
    chunk đầu pool: chunk số 0 bị 6 case dùng lại, còn phần đuôi pool không ai
    chạm. Trùng nguồn kéo theo trùng câu chữ và `phrase_frequency` loại hàng loạt.
    """
    counts = dict(targets)
    offsets: dict[str, int] = {}
    cursor = 0
    for case_id in CONTEXT_CASE_ORDER:
        offsets[case_id] = cursor
        # B5 phát theo cặp trên cùng nguồn -> chỉ tốn nửa số chunk.
        needed = counts.get(case_id, 0)
        cursor += (needed + 1) // 2 if case_id == "B5_depth_anchor" else needed
    return offsets


def pool_report(cfg: Config, needed: int) -> dict[str, Any]:
    """Số liệu để preflight in ra trước khi tiêu tiền: đủ nguồn hay phải dùng lại."""
    pool = chunk_pool(cfg)
    by_type = Counter(str(item.get("source_type")) for item in pool)
    guideline = sum(by_type[name] for name in GUIDELINE_SOURCE_TYPES)
    return {
        "pool_size": len(pool),
        "guideline_chunks": guideline,
        "records_needing_context": needed,
        "guideline_covers": min(guideline, needed),
        "reuse_factor": round(needed / len(pool), 2) if pool else 0.0,
        "by_source_type": dict(by_type.most_common()),
    }
