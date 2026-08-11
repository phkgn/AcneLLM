"""Phân bố độ dài mà thiết kế v2 sẽ tạo ra, so với v1 đã sinh thật.

Không gọi API: mô phỏng bằng chính `sample_len_target` mà pipeline dùng, nên con
số ở đây là con số sẽ xảy ra thật (sai số duy nhất là teacher lệch trong ±15%).
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import pytest

from datagen.roledatav2.config import Config
from datagen.roledatav2.generator import load_taxonomy, sample_len_target

V1_EXPORT = (
    Path(__file__).resolve().parents[2] / "roledata" / "output" / "export" / "acnellm_role_lora.jsonl"
)


def simulate() -> list[int]:
    cfg = Config(api_key="offline-test")
    lengths: list[int] = []
    for case in load_taxonomy(cfg):
        turns = 3 if case.id == "R9_multiturn" else (2 if case.id == "B5_depth_anchor" else 1)
        for ordinal in range(1, case.count + 1):
            for index in range(turns):
                last = index == turns - 1
                band = case.last_turn_len_chars if (last and case.last_turn_len_chars) else case.len_chars
                key = f"{case.id}:last" if (last and case.last_turn_len_chars) else case.id
                lengths.append(sample_len_target(key, ordinal, band))
    return lengths


def percentile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * q), len(ordered) - 1)]


def test_median_lands_in_the_measured_band() -> None:
    lengths = simulate()
    median = percentile(lengths, 0.50)
    assert 1_000 <= median <= 1_250, f"p50 = {median}, thiết kế nhắm ~1.100"


def test_short_tail_is_preserved() -> None:
    """Phải còn mẫu ngắn: anchor bắt ngắn gọn với ca đơn giản (chào hỏi, từ chối)."""
    lengths = simulate()
    share_short = sum(1 for value in lengths if value < 400) / len(lengths)
    assert 0.15 <= share_short <= 0.35, share_short


def test_no_runaway_long_tail() -> None:
    """Trên ~1.700 ký tự eval không cho thêm điểm mà `incorrect_content` tăng."""
    lengths = simulate()
    assert percentile(lengths, 0.95) <= 1_800
    assert max(lengths) <= 1_800


def test_content_mass_is_where_coverage_happens() -> None:
    lengths = simulate()
    share = sum(1 for value in lengths if 1_100 <= value <= 1_700) / len(lengths)
    assert share >= 0.40, f"chỉ {share:.0%} số lượt nằm trong vùng phủ ý"


@pytest.mark.skipif(not V1_EXPORT.is_file(), reason="chưa có export v1 để so")
def test_v2_is_a_real_shift_from_v1() -> None:
    v1 = [
        len(message["content"])
        for line in V1_EXPORT.open(encoding="utf-8")
        for message in json.loads(line)["messages"]
        if message["role"] == "assistant"
    ]
    v2 = simulate()
    assert percentile(v1, 0.50) < 400, "giả định về v1 đã đổi — đọc lại trước khi tin test này"
    assert percentile(v2, 0.50) > 2.5 * percentile(v1, 0.50)
    assert st.mean(v2) > 2 * st.mean(v1)
