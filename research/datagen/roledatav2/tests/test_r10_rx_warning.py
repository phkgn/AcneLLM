"""R10 được phép NÊU TÊN thuốc kê đơn khi đang cảnh báo — anchor bắt phải nêu.

Gate `no_rx` của v1 cấm tuyệt đối 7 tên thuốc. Anchor lại viết:
"Thai kỳ hoặc cho con bú: không khuyến nghị retinoid (isotretinoin, tretinoin,
adapalene, tazarotene) hay kháng sinh nhóm cycline (doxycycline, minocycline,
tetracycline)". Không nêu tên thì cảnh báo rỗng nghĩa.

Smoke thật loại 4/4 mẫu R10 vì lý do này — cả 4 đều đủ ý, đủ cấu trúc, đúng độ
dài. Chúng bị loại vì làm ĐÚNG luật an toàn.
"""
from __future__ import annotations

import pytest

from datagen.roledatav2.gates import evaluate_record, rx_mentions_are_all_warnings

from .helpers import ANCHOR, answer_of_length, make_record, points_for

WARN = (
    "- Khi mang thai, bạn tuyệt đối không dùng isotretinoin vì nguy cơ gây dị tật thai nhi.\n"
    "- Cũng nên tránh tretinoin và adapalene bôi trong giai đoạn này.\n"
    "- Kháng sinh nhóm cycline như doxycycline chống chỉ định với phụ nữ có thai.\n"
)
PROMOTE = (
    "- Bạn nên dùng isotretinoin để trị mụn nặng nhé.\n"
    "- Kết hợp thêm adapalene bôi buổi tối cho hiệu quả tốt hơn.\n"
    "- Duy trì đều đặn trong vài tháng để thấy kết quả rõ.\n"
)


def _record(answer_head: str, extra: str = "") -> dict:
    body = answer_of_length(900, salt=" r10")
    return make_record(
        "R10_special_population",
        answer_head + extra + "\nBạn nên trao đổi với bác sĩ da liễu trước khi dùng gì.\n" + body,
        user="Em đang mang thai 3 tháng và bị mụn nhiều, nên làm sao ạ?",
        points=points_for(3),
    )


# ── hàm phân biệt cảnh báo / khuyên dùng ──────────────────────────────────
def test_warning_sentences_are_allowed() -> None:
    assert rx_mentions_are_all_warnings(WARN) is True


def test_recommendation_sentences_are_blocked() -> None:
    assert rx_mentions_are_all_warnings(PROMOTE) is False


def test_no_drug_name_is_trivially_fine() -> None:
    assert rx_mentions_are_all_warnings("Bạn nên rửa mặt dịu nhẹ mỗi ngày.") is True


def test_one_bad_sentence_poisons_the_whole_answer() -> None:
    """Cảnh báo đúng ở câu này không xoá được việc khuyên dùng ở câu kia."""
    assert rx_mentions_are_all_warnings(WARN + PROMOTE) is False


@pytest.mark.parametrize(
    "sentence",
    [
        "Tuyệt đối không dùng isotretinoin khi mang thai.",
        "Nên tránh adapalene trong thai kỳ.",
        "Doxycycline chống chỉ định với phụ nữ cho con bú.",
        "Ngưng tretinoin ngay khi biết có thai.",
        "Isotretinoin có nguy cơ gây dị tật thai nhi rất cao.",
    ],
)
def test_common_warning_phrasings(sentence: str) -> None:
    assert rx_mentions_are_all_warnings(sentence) is True


# ── qua gate thật ─────────────────────────────────────────────────────────
def test_gate_accepts_a_correct_pregnancy_warning() -> None:
    result = evaluate_record(_record(WARN), ANCHOR)
    assert result.checks["no_rx"] is True
    assert result.checks["rx_named_as_warning"] is True
    assert "no_rx" not in result.reasons


def test_gate_still_blocks_recommending_a_prescription_drug() -> None:
    result = evaluate_record(_record(PROMOTE), ANCHOR)
    assert result.checks["no_rx"] is False
    assert "no_rx" in result.reasons


def test_dosage_is_still_forbidden_even_inside_a_warning() -> None:
    """Nới cho tên thuốc, KHÔNG nới cho liều lượng. Anchor cấm liều tuyệt đối."""
    with_dose = "- Không dùng isotretinoin 20 mg mỗi ngày khi đang mang thai.\n"
    result = evaluate_record(_record(with_dose), ANCHOR)
    assert result.checks["no_rx"] is False


def test_relaxation_applies_only_to_r10() -> None:
    """Case khác vẫn theo luật v1 — chỉ R10 mới có nhiệm vụ cảnh báo thuốc."""
    record = make_record("R4_measured_empathy", WARN + answer_of_length(700, salt=" r4"), points=points_for(2))
    assert "rx_named_as_warning" not in evaluate_record(record, ANCHOR).checks
