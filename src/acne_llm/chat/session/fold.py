"""Gop du kien tu cac luot truoc vao luot hien tai.

File nguy hiem nhat trong package: `medication_safety_refusal` -- cong tat dinh
DUY NHAT con lai -- doc `is_pregnant`, `is_breastfeeding` va `medications` do
chinh cac ham o day tra ve. Sai o day la tat cong an toan, im lang.

Ca hai loi an toan tim ra o Phase 7 deu nam trong file nay:
  - 17 chuoi keyword tung co quyen set is_pregnant = False (da xoa)
  - `inflammation` giu None -> ValidationError giua stream (da sua)

Xem tests/test_session_fold_branches.py truoc khi sua bat cu dieu gi.
"""
from __future__ import annotations


_STOP_PRODUCT_TERMS = (
    "ngưng", "ngừng", "dừng", "không dùng", "khong dung", "bỏ",
    "không phải", "khong phai", "nói nhầm", "noi nham",
)


def _mentions_stop(clean_text: str, value: str) -> bool:
    """ponytail: CO Y GIU o Phase 7, khac voi cac rule khop chuoi khac.

    No dung la doan ngu nghia, va no co mot lo that: quet 40 ky tu truoc ten
    thuoc nen "bac si bao KHONG DUNG isotretinoin chung voi doxycycline" go
    isotretinoin khoi profile -- tat cong iso+tetra dung tren cau hoi ve chinh
    tuong tac do.

    Nhung xoa han thi te hon: fold_history_facts hop medications theo kieu
    cong don qua moi turn, nen khong con duong nao go thuoc cu ra. Danh sach
    phinh vinh vien -> cong iso+tetra ban nham tren du lieu chet. Doi mot FP
    lay mot FP khac.

    Duong ra dung: intaker phat tin hieu removal co cau truc (vd
    medications_stopped[]), roi ham nay bi xoa. Chua lam duoc chung nao intaker
    chua co truong do. KHONG mo rong ham nay them.
    """
    lowered = clean_text.lower()
    value_lower = value.lower()
    aliases = {
        "salicylic_acid": ("salicylic acid", "bha"),
        "benzoyl_peroxide": ("benzoyl peroxide", "bpo"),
        "adapalene": ("adapalene", "differin"),
    }
    # Intaker canonical hoá ra "salicylic acid" (dấu cách) nhưng aliases lại key
    # bằng "salicylic_acid" -> nhánh alias chưa từng khớp dữ liệu thật, nên
    # "tôi ngưng BHA" không bao giờ gỡ được salicylic acid khỏi profile.
    alias_key = value_lower.replace(" ", "_")
    mentioned = next(
        (term for term in aliases.get(alias_key, (value_lower,)) if term in lowered),
        None,
    )
    if mentioned is None:
        return False
    pos = lowered.find(mentioned)
    before = lowered[max(0, pos - 40):pos]
    return any(term in before for term in _STOP_PRODUCT_TERMS)
