"""Báo cáo phân tầng mức độ ở khâu 1.

Vì sao tách khỏi accuracy chung: `clinical.inflammation_level` = 0.9105 trên tập
val, nhưng 85,5% đáp án là None/unknown — chỉ cần trả unknown là đã ~0.855. Con
số đó KHÔNG trả lời được "model phân biệt được nhẹ/vừa/nặng không". Test này giữ
cho bảng riêng nói đúng sự thật đó.
"""
from __future__ import annotations

from evaluation.runners.run_intake import _severity_metrics


def test_bo_qua_dong_khong_co_nhan_bac():
    """Dòng unknown/None ở ĐÁP ÁN không được tính — chúng là thứ thổi phồng 0.91."""
    out = _severity_metrics(
        ["unknown", None, "mild", "severe"],
        ["unknown", None, "mild", "severe"],
    )
    assert out["n_co_nhan_bac"] == 2
    assert out["accuracy_tren_dong_co_bac"] == 1.0


def test_ha_bac_dem_rieng_va_co_chi_tiet():
    out = _severity_metrics(
        ["severe", "severe", "moderate", "mild"],
        ["mild", "severe", "severe", "mild"],   # 1 hạ bậc, 1 nâng bậc
    )
    assert out["ha_bac"] == 1
    assert out["ty_le_ha_bac"] == 0.25
    assert out["ha_bac_chi_tiet"] == {"severe->mild": 1}
    # Nâng bậc (moderate->severe) thừa nhưng không nguy -> KHÔNG vào ha_bac.
    assert "moderate->severe" not in out["ha_bac_chi_tiet"]


def test_tra_unknown_la_bo_trong_chu_khong_phai_ha_bac():
    """'Tôi không rõ' khác hẳn 'nhẹ thôi'. Gộp hai cái là che mất một loại lỗi."""
    out = _severity_metrics(["severe", "moderate"], ["unknown", None])
    assert out["bo_trong"] == 2
    assert out["ha_bac"] == 0
    assert out["accuracy_tren_dong_co_bac"] == 0.0


def test_canh_bao_thieu_mau():
    ít = _severity_metrics(["mild"] * 9 + ["severe"] * 17, ["mild"] * 26)
    assert ít["du_co_mau"] is False          # đúng tình trạng tập val hiện tại

    đủ = _severity_metrics(
        [lv for lv in ("none", "mild", "moderate", "severe") for _ in range(30)],
        [lv for lv in ("none", "mild", "moderate", "severe") for _ in range(30)],
    )
    assert đủ["du_co_mau"] is True


def test_tap_khong_co_nhan_bac_nao_thi_noi_thang():
    out = _severity_metrics(["unknown", None], ["unknown", None])
    assert out["n_co_nhan_bac"] == 0
    assert "ghi_chu" in out                  # không trả accuracy giả 1.0


def test_phan_bo_nhan_de_doc_ngay_cho_lech():
    out = _severity_metrics(["mild", "mild", "severe"], ["mild"] * 3)
    assert out["phan_bo_nhan"] == {"mild": 2, "severe": 1}
