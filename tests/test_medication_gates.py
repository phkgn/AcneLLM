"""Bon cong thuoc con lai sau khi xoa DrugChecker (Phase 5).

Ba luat duoi day TUNG do DrugChecker + drugs_acne.yaml lo; gio viet thang trong
medication_safety_refusal. Test nay la ly do duy nhat biet chung con song.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from acne_llm.guardrails.runner import GuardrailRunner
from acne_llm.schemas import UserContext, UserInput

CFG = str(Path(__file__).resolve().parents[1] / "config" / "guardrails.yaml")


@pytest.fixture(scope="module")
def g() -> GuardrailRunner:
    return GuardrailRunner(CFG)


def _u(**ctx) -> UserInput:
    return UserInput(description="tu van mun", context=UserContext(**ctx))


def test_thai_ky_cong_retinoid_bi_chan(g):
    out = g.medication_safety_refusal(_u(is_pregnant=True, medications=["tretinoin"]))
    assert out is not None
    assert "thai kỳ" in out.disclaimer


def test_isotretinoin_cong_tetracycline_bi_chan(g):
    """Cap nay TUNG do DrugChecker.interactions_triggered bat, khong phai code inline."""
    out = g.medication_safety_refusal(_u(medications=["isotretinoin", "doxycycline"]))
    assert out is not None
    assert "áp lực nội sọ" in out.disclaimer


def test_tetracycline_duoi_8_tuoi_bi_chan(g):
    out = g.medication_safety_refusal(_u(age=6, medications=["doxycycline"]))
    assert out is not None
    assert "men răng" in out.disclaimer


def test_isotretinoin_duoi_12_tuoi_bi_chan(g):
    out = g.medication_safety_refusal(_u(age=10, medications=["isotretinoin"]))
    assert out is not None
    assert "dưới 12 tuổi" in out.disclaimer


def test_spironolactone_cho_nam_bi_chan(g):
    out = g.medication_safety_refusal(_u(sex="male", medications=["spironolactone"]))
    assert out is not None
    assert "nữ hoá" in out.disclaimer


def test_khong_chan_truong_hop_binh_thuong(g):
    """Nu 25 tuoi dung adapalene don thuan -- khong co ly do nao de tu choi."""
    assert g.medication_safety_refusal(_u(age=25, sex="female", medications=["adapalene"])) is None


@pytest.mark.parametrize("text", [
    "em không mang thai, dùng tretinoin được không",
    "em chưa mang thai bao giờ, bôi adapalene ok chứ",
    "chị tôi đang mang thai, còn tôi dùng tretinoin được không",
    "isotretinoin có nguy hiểm khi mang thai không",
])
def test_nhac_toi_thai_ky_khong_dong_nghia_dang_mang_thai(g, text):
    """Cong doc trang thai tu intaker, khong tu chuoi con trong van ban.

    Ban cu coi `"pregnancy" in mentioned_terms` la bang chung -- ma danh sach do
    khop chuoi con tho, khong kiem phu dinh. Ket qua: 4/5 cau duoi day bi chan sai.
    """
    from acne_llm.chat.intake import _extract_safety_terms

    u = _u(medications=["tretinoin", "adapalene", "isotretinoin"])
    assert g.medication_safety_refusal(u, _extract_safety_terms(text, u)) is None


def test_van_chan_khi_intaker_xac_nhan_dang_mang_thai(g):
    from acne_llm.chat.intake import _extract_safety_terms

    text = "em đang mang thai, dùng tretinoin được không"
    u = _u(is_pregnant=True, medications=["tretinoin"])
    assert g.medication_safety_refusal(u, _extract_safety_terms(text, u)) is not None


def test_khong_chan_bpo_cong_tretinoin(g):
    """DrugChecker cu liet cap nay la `interactions` va coi la dieu kien CHAN,
    nen phac do chuan sang BPO / toi tretinoin bi tu choi tu van. Xoa no sua
    luon loi over-block do."""
    assert g.medication_safety_refusal(
        _u(age=25, sex="female", medications=["benzoyl peroxide", "tretinoin"])
    ) is None
