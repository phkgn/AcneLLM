"""Chính sách chọn nguồn v2: guideline trước, bù xuống khi thiếu, không trần 512."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from datagen.roledatav2.config import CASE_TYPE_TARGETS, KNOWLEDGE_SOURCE_PRIORITY, Config
from datagen.roledatav2.generator import load_taxonomy, synthesize_context
from collections import Counter

from datagen.roledatav2.knowledge import (
    CONTEXT_CASE_ORDER,
    GUIDELINE_SOURCE_TYPES,
    case_offsets,
    chunk_pool,
    pool_report,
    usable_chunk,
)


def _fake_chunks(tmp_path: Path) -> Path:
    """Corpus giả có đủ 6 source_type để kiểm thứ tự ưu tiên mà không đọc 38 MB."""
    body = "Mụn trứng cá cần chăm sóc da đúng cách và dùng benzoyl peroxide hợp lý. " * 4
    rows = []
    for source_type, count in (
        ("vi_medical_site", 5),
        ("nice_guideline", 2),
        ("blog", 4),
        ("aad_guideline", 2),
        ("pubmed_review", 3),
        ("clinical_textbook", 2),
        ("en_medical_site", 2),
    ):
        for index in range(count):
            rows.append(
                {
                    "chunk_id": f"{source_type}-{index:03d}",
                    "source_type": source_type,
                    "source_name": source_type,
                    "text": body,
                }
            )
    rows.append({"chunk_id": "too-short", "source_type": "nice_guideline", "text": "Mụn."})
    rows.append(
        {"chunk_id": "off-topic", "source_type": "nice_guideline", "text": "Thời tiết hôm nay. " * 20}
    )
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return path


def _cfg(tmp_path: Path) -> Config:
    return Config(api_key="offline-test", knowledge_chunks_path=_fake_chunks(tmp_path))


def test_usable_chunk_filters_short_and_offtopic() -> None:
    assert usable_chunk({"text": "Mụn trứng cá " * 40})
    assert not usable_chunk({"text": "Mụn."})
    assert not usable_chunk({"text": "Thời tiết hôm nay rất đẹp. " * 40})


def test_guideline_tier_comes_first(tmp_path: Path) -> None:
    pool = chunk_pool(_cfg(tmp_path))
    types = [item["source_type"] for item in pool]
    guideline_count = sum(1 for name in types if name in GUIDELINE_SOURCE_TYPES)
    assert guideline_count == 6, types
    assert all(name in GUIDELINE_SOURCE_TYPES for name in types[:guideline_count])


def test_priority_order_is_respected(tmp_path: Path) -> None:
    types = [item["source_type"] for item in chunk_pool(_cfg(tmp_path))]
    ranks = [KNOWLEDGE_SOURCE_PRIORITY.index(name) for name in types]
    assert ranks == sorted(ranks), types


def test_blog_is_excluded(tmp_path: Path) -> None:
    assert "blog" not in {item["source_type"] for item in chunk_pool(_cfg(tmp_path))}
    assert "blog" not in KNOWLEDGE_SOURCE_PRIORITY


def test_pool_is_deterministic(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    assert [item["chunk_id"] for item in chunk_pool(cfg)] == [
        item["chunk_id"] for item in chunk_pool(cfg)
    ]


def test_embedding_is_dropped(tmp_path: Path) -> None:
    """Chunk thật có field `embedding`; giữ lại thì pool phình vô ích."""
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        json.dumps(
            {
                "chunk_id": "c1",
                "source_type": "nice_guideline",
                "text": "Mụn trứng cá cần chăm sóc đúng cách với benzoyl peroxide. " * 4,
                "embedding": [0.1] * 1024,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    pool = chunk_pool(Config(api_key="offline-test", knowledge_chunks_path=path))
    assert "embedding" not in pool[0]


def test_b5_pair_shares_one_source(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    case = next(item for item in load_taxonomy(cfg) if item.id == "B5_depth_anchor")
    _, first_sources, first_meta = synthesize_context(case, cfg, sequence=0)
    _, second_sources, second_meta = synthesize_context(case, cfg, sequence=1)
    assert first_sources == second_sources
    assert {first_meta["depth"], second_meta["depth"]} == {"beginner", "advanced"}


def test_b4_uses_two_distinct_sources(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    case = next(item for item in load_taxonomy(cfg) if item.id == "B4_conflicting_docs")
    context, sources, _ = synthesize_context(case, cfg, sequence=0)
    assert len(sources) == 2 and sources[0] != sources[1]
    assert [item["label"] for item in context] == ["Nguồn 1", "Nguồn 2"]


def test_no_context_for_non_context_case(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    case = next(item for item in load_taxonomy(cfg) if item.id == "R1_identity")
    assert synthesize_context(case, cfg, sequence=0) == (None, [], {})


# ── kiểm trên corpus THẬT: chỉ chạy khi có file ───────────────────────────
REAL_CHUNKS = Config(api_key="offline-test").knowledge_chunks_path


@pytest.mark.skipif(not REAL_CHUNKS.is_file(), reason="chưa có data/raw/chunks.jsonl")
def test_real_pool_is_large_enough_and_guideline_first() -> None:
    cfg = Config(api_key="offline-test")
    needed = sum(
        CASE_TYPE_TARGETS[case]
        for case in ("B1_grounded_role", "B2_missing_answer", "B3_irrelevant_chunk",
                     "B4_conflicting_docs", "B5_depth_anchor", "K1_knowledge_anchor")
    )
    report = pool_report(cfg, needed)
    assert report["guideline_chunks"] >= 700, report
    assert report["pool_size"] >= needed, (
        f"pool {report['pool_size']} < {needed} mẫu cần nguồn -> mọi chunk phải dùng lại"
    )
    pool = chunk_pool(cfg)
    head = [item["source_type"] for item in pool[: report["guideline_chunks"]]]
    assert all(name in GUIDELINE_SOURCE_TYPES for name in head)


@pytest.mark.skipif(not REAL_CHUNKS.is_file(), reason="chưa có data/raw/chunks.jsonl")
def test_v2_pool_beats_v1_512_cap() -> None:
    """v1 dừng ở 512 chunk đầu file; v2 không có trần đó."""
    assert len(chunk_pool(Config(api_key="offline-test"))) > 512


# ── dải chunk riêng cho từng case ─────────────────────────────────────────
def test_case_offsets_do_not_overlap() -> None:
    offsets = case_offsets(tuple(CASE_TYPE_TARGETS.items()))
    assert set(offsets) == set(CONTEXT_CASE_ORDER)
    spans = []
    for case_id in CONTEXT_CASE_ORDER:
        count = CASE_TYPE_TARGETS[case_id]
        width = (count + 1) // 2 if case_id == "B5_depth_anchor" else count
        spans.append((offsets[case_id], offsets[case_id] + width))
    for (start, end), (next_start, _) in zip(spans, spans[1:]):
        assert end <= next_start, (start, end, next_start)


def test_k1_and_b1_get_the_guideline_head() -> None:
    """Hai case cần thẩm quyền nhất phải đứng đầu dải guideline."""
    offsets = case_offsets(tuple(CASE_TYPE_TARGETS.items()))
    assert offsets["K1_knowledge_anchor"] == 0
    assert offsets["B1_grounded_role"] == CASE_TYPE_TARGETS["K1_knowledge_anchor"]


@pytest.mark.skipif(not REAL_CHUNKS.is_file(), reason="chưa có data/raw/chunks.jsonl")
def test_no_chunk_is_reused_across_the_whole_run() -> None:
    """Chạy khô toàn bộ 1.570 mẫu cần nguồn, đếm chunk trùng."""
    cfg = Config(api_key="offline-test")
    seen: Counter[str] = Counter()
    for case in load_taxonomy(cfg):
        if not case.context:
            continue
        for ordinal in range(1, case.count + 1):
            _, sources, _ = synthesize_context(case, cfg, sequence=ordinal - 1)
            seen[sources[0]] += 1
    b5_pairs = (CASE_TYPE_TARGETS["B5_depth_anchor"] + 1) // 2
    over_used = {sid: n for sid, n in seen.items() if n > 2}
    assert not over_used, f"chunk bị dùng quá 2 lần: {list(over_used.items())[:5]}"
    assert sum(1 for n in seen.values() if n == 2) <= b5_pairs, "chỉ B5 được phép dùng đôi"
