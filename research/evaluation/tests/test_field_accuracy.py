"""Accuracy từng field phải kèm mốc so sánh, nếu không nó nói dối.

Con số thật từ tập val 400 dòng: `context.is_pregnant` có 96,0% đáp án rỗng.
Model đạt accuracy 0.9632 — nghe như gần hoàn hảo. Nhưng một model LUÔN trả null
đạt 0.960. Năng lực thật là +0.003, ở đúng field quyết định chống chỉ định
isotretinoin.

Bảng này tồn tại để con số đó không bao giờ được đọc trần nữa.
"""
from __future__ import annotations

from evaluation.runners.run_intake import _accuracy_one, _field_accuracy, _is_empty


def test_lift_lot_tran_field_toan_null():
    """96 dòng rỗng, 4 dòng có khai, model đúng hết -> accuracy 1.0 nhưng sàn 0.96."""
    gold = [None] * 96 + ["yes", "yes", "no", "no"]
    out = _accuracy_one(gold, list(gold))
    assert out["accuracy"] == 1.0
    assert out["baseline_luon_doan_pho_bien"] == 0.96
    assert out["lift"] == 0.04          # phần thật sự kiếm được
    assert out["n_co_khai"] == 4
    assert out["du_co_mau"] is False    # 4 dòng thì đừng kết luận gì


def test_model_rong_tuech_co_lift_bang_khong():
    """Luôn trả null: accuracy cao chót vót, lift đúng bằng 0."""
    gold = [None] * 96 + ["yes"] * 4
    out = _accuracy_one(gold, [None] * 100)
    assert out["accuracy"] == 0.96
    assert out["lift"] == 0.0
    assert out["accuracy_khi_co_khai"] == 0.0   # trượt sạch phần đáng giá
    assert out["bo_trong"] == 4


def test_bo_trong_khac_tri_sai():
    """Trả 'unknown' khi người ta CÓ khai là một loại lỗi; trích sai là loại khác."""
    trong = _accuracy_one(["oily", "dry"], ["unknown", None])
    sai = _accuracy_one(["oily", "dry"], ["dry", "oily"])
    assert trong["bo_trong"] == 2 and sai["bo_trong"] == 0
    assert trong["accuracy_khi_co_khai"] == sai["accuracy_khi_co_khai"] == 0.0


def test_field_list_khop_theo_TAP_khong_theo_thu_tu():
    gold = [["papule", "nodule"], ["cyst"], []]
    pred = [["nodule", "papule"], ["papule"], []]
    out = _accuracy_one(gold, pred)
    assert out["accuracy"] == round(2 / 3, 4)   # dòng 1 và 3 đúng
    assert out["n_co_khai"] == 2                # list rỗng = không khai


def test_list_rong_tinh_la_khong_khai():
    out = _accuracy_one([[], [], ["cyst"]], [[], [], ["cyst"]])
    assert out["ty_le_khong_khai"] == round(2 / 3, 4)


def test_du_doan_di_dang_bi_tinh_la_SAI_khong_lam_vo():
    """Model hỏng trả list ở chỗ scalar. Phải đếm là trượt, không được ném."""
    out = _accuracy_one(["oily", "dry"], [["list", "dị"], "dry"])
    assert out["accuracy"] == 0.5


def test_gop_ca_scalar_lan_list_vao_mot_bang():
    out = _field_accuracy(
        {"context.age": [22, None]}, {"context.age": [22, None]},
        {"clinical.lesion_types": [["cyst"], []]},
        {"clinical.lesion_types": [["cyst"], []]},
    )
    assert out["context.age"]["kieu"] == "scalar"
    assert out["clinical.lesion_types"]["kieu"] == "list"
    assert all(v["accuracy"] == 1.0 for v in out.values())


def test_field_rong_khong_lam_vo():
    assert _accuracy_one([], []) == {"n": 0}


def test_is_empty_gop_dung_cac_dang_khong_khai():
    for value in (None, "unknown", "", [], ()):
        assert _is_empty(value) is True
    for value in ("oily", 0, 22, ["cyst"], False):
        assert _is_empty(value) is False, value
