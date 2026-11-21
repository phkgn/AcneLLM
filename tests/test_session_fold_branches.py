"""Luoi cho cac nhanh CHUA duoc phu trong fold_history_facts.

Vi sao file nay ton tai: do coverage tren session.py cho 94%, nhung 13/20 dong
chua phu nam gon trong `fold_history_facts` -- ham to nhat, va la ham NUOI
THANG cong thuoc (`medication_safety_refusal` doc `is_pregnant`,
`is_breastfeeding`, `medications` do chinh no tra ve).

Nghia la: neu cat sai o day khi tach file, 496 test van xanh. Hong im lang,
dung cho te nhat. Cac test duoi canh dung nhung dong do:

    L555      fold is_breastfeeding tu history
    L562-565  _mentions_stop go / giu current_products den tu ctx history
    L566-568  nhu tren, cho medications
    L579-582  topic shift trong SNAPSHOT reset lesion_types / distribution
    L613-616  topic shift trong LUOT HIEN TAI ghi de hai truong do

Viet TRUOC khi tach, phai xanh tren code hien tai.
"""
from __future__ import annotations

from acne_llm.chat.session import (
    ConversationTurn,
    NormalizedSnapshot,
    fold_history_facts,
)
from acne_llm.schemas import AcneClinicalInput, UserContext, UserInput


def _turn(clean_text: str, context: dict | None = None, clinical: dict | None = None):
    """User turn mang mot snapshot dung nhu test can.

    Dung NormalizedSnapshot truc tiep thay vi normalize_chat_message: cac nhanh
    duoi phu thuoc vao to hop context/clinical/clean_text cu the ma normalizer
    khong chac sinh ra.
    """
    return ConversationTurn(
        role="user",
        content=clean_text,
        normalized_snapshot=NormalizedSnapshot(
            context=context or {},
            clinical=clinical or {},
            clean_text=clean_text,
        ),
    )


def _current(description: str, clinical: dict | None = None, **ctx):
    return UserInput(
        description=description,
        mode="hybrid",
        context=UserContext(**ctx),
        clinical=AcneClinicalInput(**clinical) if clinical else None,
    )


# ── L553-555: fold cho con bu tu history ─────────────────────────────────────

def test_cho_con_bu_duoc_fold_tu_history_khi_luot_nay_khong_nhac():
    """Cong thuoc doc is_breastfeeding. Neu nhanh nay cat hong, thai phu/me cho
    bu hoi o luot sau se KHONG duoc chan retinoid."""
    history = [_turn("em đang cho con bú", {"is_breastfeeding": True})]

    merged = fold_history_facts(_current("dùng tretinoin được không"), history)

    assert merged.context.is_breastfeeding is True


def test_khong_fold_cho_con_bu_khi_luot_nay_da_nhac_toi():
    """Luot hien tai thang: no da noi 'cho con bú' thi intaker moi la nguon."""
    history = [_turn("em đang cho con bú", {"is_breastfeeding": True})]

    merged = fold_history_facts(
        _current("em không còn cho con bú nữa, dùng tretinoin được không"),
        history,
    )

    assert merged.context.is_breastfeeding is False


def test_thai_ky_fold_tu_history_theo_cung_luat():
    history = [_turn("em đang mang thai", {"is_pregnant": True})]

    merged = fold_history_facts(_current("bôi adapalene ok chứ"), history)

    assert merged.context.is_pregnant is True


# ── L561-565: current_products den tu ctx history ────────────────────────────

def test_san_pham_tu_history_duoc_cong_don():
    history = [_turn("em dùng benzoyl peroxide", {"current_products": ["benzoyl peroxide"]})]

    merged = fold_history_facts(_current("da em vẫn nổi mụn"), history)

    assert "benzoyl peroxide" in merged.context.current_products


def test_san_pham_bi_go_khi_luot_sau_noi_ngung():
    """Hai snapshot: luot cu them, luot moi ngung -> khong con trong ho so."""
    history = [
        _turn("em dùng benzoyl peroxide", {"current_products": ["benzoyl peroxide"]}),
        _turn("em ngưng benzoyl peroxide rồi", {"current_products": ["benzoyl peroxide"]}),
    ]

    merged = fold_history_facts(_current("giờ em nên làm gì"), history)

    assert "benzoyl peroxide" not in merged.context.current_products


# ── L566-568: medications den tu ctx history ─────────────────────────────────

def test_thuoc_tu_history_duoc_cong_don():
    history = [_turn("em đang uống doxycycline", {"medications": ["doxycycline"]})]

    merged = fold_history_facts(_current("da em vẫn nổi mụn"), history)

    assert "doxycycline" in merged.context.medications


def test_thuoc_bi_go_khi_luot_sau_noi_khong_dung_nua():
    """Nhanh nay quyet dinh dau vao cua cong iso+tetra. Go sai = cong tat."""
    history = [
        _turn("em đang uống doxycycline", {"medications": ["doxycycline"]}),
        _turn("tôi không dùng doxycycline nữa", {"medications": ["doxycycline"]}),
    ]

    merged = fold_history_facts(_current("giờ em nên làm gì"), history)

    assert "doxycycline" not in merged.context.medications


# ── L578-582: topic shift trong SNAPSHOT ─────────────────────────────────────

def test_topic_shift_trong_snapshot_reset_vung_va_loai_ton_thuong():
    """Luot cu noi mun o cam; luot sau 'chuyển sang' lung -> khong duoc gop
    hai vung thanh mot ca tong hop."""
    history = [
        _turn("mụn ở cằm", clinical={"lesion_distribution": ["chin"], "lesion_types": ["papule"]}),
        _turn(
            "giờ chuyển sang lưng",
            clinical={"lesion_distribution": ["back"], "lesion_types": ["nodule"]},
        ),
    ]

    merged = fold_history_facts(_current("nên bôi gì"), history)

    assert merged.clinical is not None
    assert merged.clinical.lesion_distribution == ["back"]
    assert merged.clinical.lesion_types == ["nodule"]


# ── L612-616: topic shift o LUOT HIEN TAI ────────────────────────────────────

def test_topic_shift_o_luot_hien_tai_ghi_de_history():
    history = [
        _turn("mụn ở cằm", clinical={"lesion_distribution": ["chin"], "lesion_types": ["papule"]}),
    ]
    current = _current(
        "không phải ở cằm, câu này tôi hỏi về lưng",
        clinical={"lesion_distribution": ["back"], "lesion_types": ["nodule"]},
    )

    merged = fold_history_facts(current, history)

    assert merged.clinical is not None
    assert merged.clinical.lesion_distribution == ["back"]
    assert merged.clinical.lesion_types == ["nodule"]


# ── Hoi quy: clinical=None ca hai luot ───────────────────────────────────────

def test_hai_luot_khong_co_tin_hieu_lam_sang_khong_lam_no_pydantic():
    """Bug tim ra khi viet luoi nay, truoc khi tach file.

    Intaker khai bao ro: "khong co bat ky tin hieu lam sang nao thi
    clinical=null", va UserInput.clinical default cung la None. Khi ca luot
    hien tai lan moi snapshot deu khong co inflammation_level, bien
    `inflammation` giu None va di thang vao AcneClinicalInput -- truong Literal
    khong nhan None -> ValidationError giua stream.
    """
    prior = UserInput(description="em 22 tuổi", mode="hybrid",
                      context=UserContext(age=22), clinical=None)
    history = [ConversationTurn(
        role="user", content="em 22 tuổi",
        normalized_snapshot=NormalizedSnapshot(
            context={"age": 22}, clinical={}, clean_text="em 22 tuổi"),
    )]
    assert prior.clinical is None

    merged = fold_history_facts(_current("da em vẫn xấu"), history)

    assert merged.context.age == 22
    if merged.clinical is not None:
        assert merged.clinical.inflammation_level == "unknown"


def test_khong_ha_cap_severity_khi_history_nang_hon():
    """Doi chung: `or "unknown"` khong duoc nuot severity that."""
    history = [
        _turn("mụn viêm nặng", clinical={"inflammation_level": "severe"}),
    ]

    merged = fold_history_facts(_current("giờ sao"), history)

    assert merged.clinical is not None
    assert merged.clinical.inflammation_level == "severe"


def test_khong_co_topic_shift_thi_gop_ca_hai_vung():
    """Doi chung cho test tren: khong co tu danh dau thi van la union."""
    history = [
        _turn("mụn ở cằm", clinical={"lesion_distribution": ["chin"]}),
    ]
    current = _current("thêm ở lưng nữa", clinical={"lesion_distribution": ["back"]})

    merged = fold_history_facts(current, history)

    assert merged.clinical is not None
    assert set(merged.clinical.lesion_distribution) == {"chin", "back"}
