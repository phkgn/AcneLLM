"""Luat lieu luong -- port tu guardrails._apply_medication_safety (Phase 3).

Cong dau vao (medication_safety_refusal) chi thay thu NGUOI DUNG nhac toi.
Luat nay doc thu MODEL vua viet ra.
"""
from __future__ import annotations

from acne_llm.chat._safety import get_safety_suffix
from acne_llm.schemas import UserInput

_LONG = " Ban nen giu thoi quen cham soc da deu dan va kien nhan theo doi. " * 3


def _user() -> UserInput:
    return UserInput(description="mun viem do khap hai ma", mode="hybrid")


def test_lieu_cu_the_bi_gan_canh_bao():
    text = "Voi tinh trang nay, uong doxycycline 100mg mỗi ngày trong 8 tuần." + _LONG
    suffix = get_safety_suffix(text, _user())
    assert "liều lượng thuốc cụ thể" in suffix


def test_lieu_phan_tram_boi_cung_bi_bat():
    text = "Ban co the boi tretinoin 0.05% mỗi tối truoc khi di ngu." + _LONG
    suffix = get_safety_suffix(text, _user())
    assert "liều lượng thuốc cụ thể" in suffix


def test_tu_mua_khang_sinh_bi_bat():
    text = "Neu khong do, ban tự mua kháng sinh o hieu thuoc cung duoc." + _LONG
    suffix = get_safety_suffix(text, _user())
    assert "liều lượng thuốc cụ thể" in suffix


def test_cau_tra_loi_khong_co_lieu_thi_khong_gan():
    text = "Ban nen rua mat hai lan mot ngay va dung kem chong nang." + _LONG
    suffix = get_safety_suffix(text, _user())
    assert "liều lượng thuốc cụ thể" not in suffix


def test_khong_gan_hai_lan_khi_model_da_tu_noi():
    text = (
        "Doxycycline 100mg mỗi ngày la phac do thuong gap, nhung lieu phai "
        "do bác sĩ chỉ định sau khi tham kham." + _LONG
    )
    suffix = get_safety_suffix(text, _user())
    assert "liều lượng thuốc cụ thể" not in suffix
