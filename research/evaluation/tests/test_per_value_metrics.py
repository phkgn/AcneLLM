"""PRF theo TỪNG GIÁ TRỊ enum ở khâu 1.

Vì sao cần test: "skin_type F1=0.72" không cho biết nên sửa gì. Bảng theo giá
trị mới nói được model giỏi 'da dầu' nhưng mù 'da hỗn hợp'. Nếu bảng đó sai thì
nó dẫn người đọc đi sai hướng, tệ hơn là không có.
"""
from __future__ import annotations

from evaluation.runners.run_intake import _per_value_metrics


def test_scalar_tach_duoc_gia_tri_gioi_va_gia_tri_dot():
    gold = {"context.skin_type": ["oily", "oily", "oily", "combination"]}
    pred = {"context.skin_type": ["oily", "oily", "oily", "oily"]}
    out = _per_value_metrics(gold, pred, {}, {})["context.skin_type"]

    assert out["oily"]["recall"] == 1.0          # bắt hết ca oily
    assert out["oily"]["precision"] == 0.75      # nhưng nhận nhầm 1 ca
    assert out["combination"]["support"] == 1
    assert out["combination"]["recall"] == 0.0   # mù hoàn toàn với combination


def test_support_dem_theo_DAP_AN_khong_theo_du_doan():
    gold = {"f": ["a", "a", None]}
    pred = {"f": ["a", "b", "b"]}
    out = _per_value_metrics(gold, pred, {}, {})["f"]
    assert out["a"]["support"] == 2      # 'a' xuất hiện 2 lần trong đáp án
    assert out["b"]["support"] == 0      # 'b' chưa từng là đáp án -> F1 vô nghĩa


def test_list_field_tinh_theo_tung_phan_tu():
    gold = {"clinical.lesion_types": [["papule", "nodule"], ["cyst"]]}
    pred = {"clinical.lesion_types": [["papule"], ["cyst", "papule"]]}
    out = _per_value_metrics({}, {}, gold, pred)["clinical.lesion_types"]

    assert out["cyst"]["f1"] == 1.0                 # đúng hoàn toàn
    assert out["nodule"]["recall"] == 0.0           # bỏ sót
    assert out["papule"]["precision"] == 0.5        # 1 lần thừa ở dòng 2


def test_du_doan_di_dang_van_bi_dem_la_SAI():
    """Model hỏng trả list ở chỗ scalar. Trước đây vỡ set(); giờ phải đếm là
    trượt chứ KHÔNG được bỏ qua lặng lẽ — bỏ qua thì điểm cao giả."""
    out = _per_value_metrics({"f": ["oily", "dry"]},
                             {"f": [["list", "dị"], "oily"]}, {}, {})["f"]
    assert out["oily"]["recall"] == 0.0
    assert out["dry"]["recall"] == 0.0


def test_khong_co_gia_tri_hop_le_thi_bo_qua_field():
    out = _per_value_metrics({"f": [None, None]}, {"f": [None, None]}, {}, {})
    assert "f" not in out
