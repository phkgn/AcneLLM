"""Nguồn tiếng Anh: chấm bám-nguồn bằng judge, không bằng trùng token.

Lý do (đo trên chính corpus của repo):
  - tầng guideline 100% tiếng Anh: nice 172/172, aad 180/180, textbook 448 en
  - `grounded_rate` là trùng token thô -> câu trả lời tiếng Việt bám nguồn Anh = 0.00
  - chép nguyên nguồn -> 1.00 nhưng `vietnamese_only` chặn
=> hai gate loại trừ nhau, mọi mẫu nguồn guideline bị loại 100%.
Cùng lý do repo đã gỡ `grounding_support` khỏi eval (`context.md` §1e).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from datagen.roledata.gates import grounded_rate, vietnamese_only
from datagen.roledatav2 import pipeline as v2_pipeline
from datagen.roledatav2.gates import evaluate_record
from datagen.roledatav2.knowledge import context_is_vietnamese

from .helpers import ANCHOR, answer_of_length, make_record

impl = v2_pipeline.impl

EN_CONTEXT = [
    {
        "label": "Nguồn 1",
        "source_id": "nice-001",
        "source_name": "NICE NG198",
        "text": (
            "Offer a 12-week course of topical benzoyl peroxide as monotherapy for mild to "
            "moderate acne. Review treatment at 12 weeks and consider referral if there is "
            "no improvement or if scarring is present."
        ),
    }
]
VI_CONTEXT = [
    {
        "label": "Nguồn 1",
        "source_id": "vi-001",
        "source_name": "Trang y khoa tiếng Việt",
        "text": (
            "Benzoyl peroxide là hoạt chất không kê đơn thường dùng cho mụn viêm mức độ nhẹ "
            "đến trung bình, giúp diệt khuẩn và giảm bít tắc lỗ chân lông trên da."
        ),
    }
]
VI_ANSWER = (
    "- Bạn nên rửa mặt dịu nhẹ và dùng hoạt chất không kê đơn theo khuyến cáo.\n"
    "- Nếu sau khoảng ba tháng không cải thiện thì nên gặp bác sĩ da liễu.\n"
    "- Không tự ý dùng thuốc kê đơn khi chưa có chỉ định của bác sĩ.\n"
)
VI_POINTS = [
    "Bạn nên rửa mặt dịu nhẹ và dùng hoạt chất không kê đơn theo khuyến cáo",
    "Nếu sau khoảng ba tháng không cải thiện thì nên gặp bác sĩ da liễu",
    "Không tự ý dùng thuốc kê đơn khi chưa có chỉ định của bác sĩ",
]


# ── phát hiện ngôn ngữ ─────────────────────────────────────────────────────
def test_language_detection() -> None:
    assert context_is_vietnamese(VI_CONTEXT) is True
    assert context_is_vietnamese(EN_CONTEXT) is False
    assert context_is_vietnamese(None) is True


def test_distractor_does_not_flip_language() -> None:
    """`Nguồn nhiễu` của B3 là tiếng Việt; nó không được che ngôn ngữ nguồn thật."""
    mixed = EN_CONTEXT + [
        {"label": "Nguồn nhiễu", "source_id": "d", "text": "Thời tiết hôm nay có mây và giá điện thoại."}
    ]
    assert context_is_vietnamese(mixed) is False


# ── chứng minh mâu thuẫn gate là có thật ───────────────────────────────────
def test_the_two_v1_gates_are_mutually_exclusive_on_english_sources() -> None:
    source = EN_CONTEXT[0]["text"]
    assert grounded_rate(VI_ANSWER, source) < 0.6
    assert vietnamese_only(VI_ANSWER) is True
    assert grounded_rate(source, source) >= 0.6
    assert vietnamese_only(source) is False


# ── gate v2 ────────────────────────────────────────────────────────────────
def _long_vi_answer(target: int) -> str:
    """VI_ANSWER (3 bullet, có `points`) + phần độn KHÔNG lặp cụm dài."""
    return (VI_ANSWER + answer_of_length(max(target - len(VI_ANSWER), 60), salt=" nền"))[:target]


def _record(context, judge_score=None):
    meta = {} if judge_score is None else {"grounding_judge": judge_score}
    return make_record(
        "B1_grounded_role",
        _long_vi_answer(1_300),
        context=context,
        points=VI_POINTS,
        meta=meta,
    )


def test_english_source_drops_token_gate() -> None:
    checks = evaluate_record(_record(EN_CONTEXT, judge_score=5), ANCHOR).checks
    assert checks["grounding_language"] == "en"
    assert "grounded_rate_pass" not in checks
    assert checks["grounding_judge_pass"] is True


def test_english_source_without_judge_score_fails() -> None:
    """Chưa chấm thì phải trượt, không được mặc định cho qua."""
    result = evaluate_record(_record(EN_CONTEXT, judge_score=None), ANCHOR)
    assert result.checks["grounding_judge_pass"] is False
    assert "grounding_judge_pass" in result.reasons


def test_english_source_low_judge_score_fails() -> None:
    result = evaluate_record(_record(EN_CONTEXT, judge_score=3), ANCHOR)
    assert result.checks["grounding_judge_pass"] is False


def test_vietnamese_source_keeps_token_gate() -> None:
    checks = evaluate_record(_record(VI_CONTEXT), ANCHOR).checks
    assert checks["grounding_language"] == "vi"
    assert "grounded_rate_pass" in checks
    assert "grounding_judge_pass" not in checks


# ── pipeline gọi judge đúng số lần ─────────────────────────────────────────
class _CountingProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.judge_calls = 0

    async def generate(self, messages):
        return self.payload

    async def judge_knowledge(self, context, answer):
        self.judge_calls += 1
        return 5


class _Writer:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def append(self, record) -> bool:
        self.records.append(record)
        return True


def _cfg(tmp_path: Path):
    from datagen.roledatav2.config import Config

    modelfile = tmp_path / "Modelfile"
    canonical = tmp_path / "canonical.txt"
    modelfile.write_text(f'FROM t\nSYSTEM """{ANCHOR}"""\n', encoding="utf-8")
    canonical.write_text(ANCHOR + "\n", encoding="utf-8")
    return Config(
        api_key="offline-test",
        anchor_path=modelfile,
        canonical_path=canonical,
        output_dir=tmp_path / "output",
        model="fake",
    )


@pytest.mark.parametrize(
    ("case_id", "expected_calls"),
    [("B1_grounded_role", 1), ("K1_knowledge_anchor", 1)],
)
def test_k1_does_not_pay_for_two_judge_calls(case_id: str, expected_calls: int, tmp_path: Path) -> None:
    """K1 vốn đã gọi judge cho `knowledge_accuracy`; dùng lại điểm đó, không gọi hai lần."""
    from datagen.roledatav2.gates import CorpusGateState
    from datagen.roledatav2.generator import load_taxonomy, sample_len_target

    cfg = _cfg(tmp_path)
    case = next(item for item in load_taxonomy(cfg) if item.id == case_id)
    context, _, _ = impl.synthesize_context(case, cfg, sequence=0)
    if context_is_vietnamese(context):
        pytest.skip("chunk đầu pool là tiếng Việt; test này chỉ nói về nguồn EN")

    target = sample_len_target(case.id, 1, case.len_chars)
    answer = _long_vi_answer(target)
    provider = _CountingProvider(
        {
            "user": "Mụn viêm nhẹ thì nên dùng gì?",
            "assistant": answer,
            "points": VI_POINTS,
            "input_style": "standard",
            "audience": "general",
        }
    )
    writer = _Writer()
    accepted, _ = asyncio.run(
        impl._generate_one(
            case=case,
            ordinal=1,
            smoke=True,
            cfg=cfg,
            anchor=ANCHOR,
            style_guide="g",
            provider=provider,
            writer=writer,
            corpus=CorpusGateState(14, 8),
            skip_gates=False,
        )
    )
    assert accepted is True, writer.records
    assert provider.judge_calls == expected_calls
    checks = writer.records[0]["gate_results"]["checks"]
    assert checks["grounding_judge_pass"] is True
