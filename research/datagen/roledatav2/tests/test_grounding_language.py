"""Nguồn tiếng Anh: chấm bám-nguồn bằng `entities_grounded`, không bằng trùng token
và cũng KHÔNG bằng judge nữa.

Lý do gỡ trùng token (đo trên chính corpus của repo):
  - tầng guideline 100% tiếng Anh: nice 172/172, aad 180/180, textbook 448 en
  - `grounded_rate` là trùng token thô -> câu trả lời tiếng Việt bám nguồn Anh = 0.00
  - chép nguyên nguồn -> 1.00 nhưng `vietnamese_only` chặn
=> hai gate loại trừ nhau, mọi mẫu nguồn guideline bị loại 100%.

Lý do gỡ judge (đo trên 1.264 mẫu context của vòng 1):
  - `grounding_judge`: 1043 điểm 5, 2 điểm 4, 0 điểm <=3
  - `knowledge_accuracy`: 491/491 điểm 5
  - phương sai gần bằng 0 => không phải thước đo, chỉ là chi phí (~1.755 call/run)
  - nguyên nhân: judge dùng CHÍNH model vừa sinh câu trả lời để chấm nó
=> thay bằng phép so tập hợp trên thứ KHÔNG bị dịch: tên thuốc, tên guideline,
   con số phần trăm. Chạy lại trên data vòng 1, nó bắt 192 mẫu mà judge cho 5/5.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from datagen.roledata.gates import grounded_rate, vietnamese_only
from datagen.roledatav2 import pipeline as v2_pipeline
from datagen.roledatav2.gates import entities_grounded, evaluate_record
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
    "- Bạn nên rửa mặt dịu nhẹ và dùng benzoyl peroxide theo khuyến cáo.\n"
    "- Nếu sau khoảng ba tháng không cải thiện thì nên gặp bác sĩ da liễu.\n"
    "- Không tự ý dùng thuốc kê đơn khi chưa có chỉ định của bác sĩ.\n"
)
VI_POINTS = [
    "Bạn nên rửa mặt dịu nhẹ và dùng benzoyl peroxide theo khuyến cáo",
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


# ── entities_grounded: đơn vị ──────────────────────────────────────────────
def test_entities_grounded_accepts_terms_present_in_source() -> None:
    assert entities_grounded(EN_CONTEXT, VI_ANSWER) is True


def test_entities_grounded_rejects_invented_drug() -> None:
    """`isotretinoin` không có trong nguồn -> bịa, dù câu văn nghe rất hợp lý."""
    answer = VI_ANSWER + "Bạn có thể cân nhắc isotretinoin nếu mụn nặng hơn.\n"
    assert entities_grounded(EN_CONTEXT, answer) is False


def test_entities_grounded_rejects_invented_source_name() -> None:
    answer = VI_ANSWER + "Theo một tổng quan trên Cochrane thì hiệu quả tương đương.\n"
    assert entities_grounded(EN_CONTEXT, answer) is False


def test_entities_grounded_accepts_source_label_as_evidence() -> None:
    """Nhãn "Nguồn 1 — NICE NG198" nằm trong lượt user nên nói "theo NICE" là có căn cứ."""
    assert entities_grounded(EN_CONTEXT, VI_ANSWER + "Theo NICE, nên xem lại sau 12 tuần.\n") is True


def test_entities_grounded_rejects_invented_percentage() -> None:
    answer = VI_ANSWER + "Khoảng 85% người dùng cải thiện sau bốn tuần.\n"
    assert entities_grounded(EN_CONTEXT, answer) is False


def test_entities_grounded_ignores_ordered_list_numbers() -> None:
    """"1." / "2." đầu dòng là số thứ tự, không phải khẳng định — không được phạt."""
    answer = "1. Rửa mặt dịu nhẹ.\n2. Dùng benzoyl peroxide.\n3. Gặp bác sĩ nếu không đỡ.\n"
    assert entities_grounded(EN_CONTEXT, answer) is True


def test_entities_grounded_also_runs_on_vietnamese_sources() -> None:
    """Nguồn tiếng Việt vẫn bịa được tên thuốc; `grounded_rate` không bắt được."""
    assert entities_grounded(VI_CONTEXT, VI_ANSWER + "Dùng thêm adapalene nhé.\n") is False


# ── gate v2 trong ngữ cảnh bản ghi đầy đủ ──────────────────────────────────
def _long_vi_answer(target: int) -> str:
    """VI_ANSWER (3 bullet, có `points`) + phần độn KHÔNG lặp cụm dài."""
    return (VI_ANSWER + answer_of_length(max(target - len(VI_ANSWER), 60), salt=" nền"))[:target]


def _record(context, answer: str | None = None):
    return make_record(
        "B1_grounded_role",
        answer or _long_vi_answer(1_300),
        context=context,
        points=VI_POINTS,
    )


def test_english_source_drops_token_gate() -> None:
    checks = evaluate_record(_record(EN_CONTEXT), ANCHOR).checks
    assert checks["grounding_language"] == "en"
    assert "grounded_rate_pass" not in checks
    assert checks["entities_grounded"] is True


def test_no_judge_field_survives_anywhere() -> None:
    """Regression: vòng 2 không được để sót đường nào còn đọc điểm judge."""
    checks = evaluate_record(_record(EN_CONTEXT), ANCHOR).checks
    assert "grounding_judge" not in checks
    assert "grounding_judge_pass" not in checks
    assert "knowledge_accuracy" not in checks


def test_invented_entity_fails_the_full_record() -> None:
    answer = _long_vi_answer(1_200) + "\n- Cân nhắc dùng tretinoin buổi tối.\n"
    result = evaluate_record(_record(EN_CONTEXT, answer), ANCHOR)
    assert result.checks["entities_grounded"] is False
    assert "entities_grounded" in result.reasons


def test_vietnamese_source_keeps_token_gate() -> None:
    checks = evaluate_record(_record(VI_CONTEXT), ANCHOR).checks
    assert checks["grounding_language"] == "vi"
    assert "grounded_rate_pass" in checks
    assert checks["entities_grounded"] is True


# ── pipeline không được gọi judge lần nào ──────────────────────────────────
class _CountingProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.judge_calls = 0

    async def generate(self, messages):
        return self.payload

    async def judge_knowledge(self, context, answer):  # pragma: no cover - phải không được gọi
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


@pytest.mark.parametrize("case_id", ["B1_grounded_role", "K1_knowledge_anchor"])
def test_pipeline_never_calls_the_judge(case_id: str, tmp_path: Path) -> None:
    """Vòng 1 tốn ~1.755 call judge để nhận về một hằng số. Vòng 2 phải là 0."""
    from datagen.roledatav2.gates import CorpusGateState
    from datagen.roledatav2.generator import load_taxonomy, sample_len_target

    cfg = _cfg(tmp_path)
    case = next(item for item in load_taxonomy(cfg) if item.id == case_id)
    context, _, _ = impl.synthesize_context(case, cfg, sequence=0)

    target = sample_len_target(case.id, 1, case.len_chars)
    user = "Mụn viêm nhẹ ở cằm và trán thì nên chăm sóc sao?"
    # Câu trả lời KHÔNG nêu tên thuốc nào: chunk lấy từ pool thật, không biết
    # trước nó chứa hoạt chất gì, mà `entities_grounded` chỉ cho nêu thứ có trong
    # nguồn. Không nêu gì thì luôn hợp lệ — đúng hành vi an toàn.
    neutral = (
        "- Rửa mặt dịu nhẹ hai lần mỗi ngày, tránh chà xát mạnh lên vùng đang viêm.\n"
        "- Giữ ẩm đầy đủ và che chắn khi ra nắng để hạn chế vết thâm sau viêm.\n"
        "- Nếu sau vài tuần không cải thiện thì nên gặp bác sĩ da liễu để được đánh giá.\n"
    )
    # Case bật `echo_user_facts` thì câu trả lời phải nhắc lại dữ kiện người dùng.
    head = "Về mụn viêm nhẹ ở cằm và trán: " if case.echo_user_facts else ""
    body = neutral + answer_of_length(max(target - len(neutral) - len(head), 60), salt=" nền")
    from .helpers import seed_skeleton

    provider = _CountingProvider(
        seed_skeleton(
            cfg,
            case,
            1,
            True,
            {
                "user": user,
                "assistant": (head + body)[:target],
                "points": [line.lstrip("- ").rstrip(".\n") for line in neutral.strip().split("\n")],
                "input_style": "standard",
                "audience": "general",
            },
        )
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
    assert provider.judge_calls == 0, "pipeline vòng 2 không được gọi judge"
    assert writer.records[0]["gate_results"]["checks"]["entities_grounded"] is True
