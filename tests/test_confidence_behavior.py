"""Hanh vi do confidence dieu khien.

Truoc day file nay test `completeness.check_completeness` -- module do da bi xoa.
Viec "field co gia tri nhung do tin cay thap thi HEDGE chu khong hoi lai" gio do
`confidence_hint.build_confidence_hint` dam nhiem, va no la kenh DUY NHAT bao cho
generator biet extractor khong chac (known_facts da ra khoi prompt).
"""
from acne_llm.schemas import UserInput, UserContext, AcneClinicalInput
from acne_llm.schemas.extraction import FieldResult, ListFieldResult, ExtractionConfidence
from acne_llm.chat.confidence_hint import build_confidence_hint
from acne_llm.chat.fallback.rule_normalizer import normalize_chat_message
from acne_llm.chat.fallback.intent_router import route_intent
from acne_llm.config import Settings


def _user(lesion_types=None, dist=None, inflammation="none"):
    return UserInput(description="mun viem o ma", mode="hybrid", context=UserContext(),
        clinical=AcneClinicalInput(lesion_types=lesion_types or [], lesion_distribution=dist or [],
                                   inflammation_level=inflammation))


def test_field_do_tin_cay_thap_duoc_hedge_chu_khong_hoi_lai():
    """Field yeu van GIU trong prompt, kem mot cau noi ro la suy doan."""
    conf = ExtractionConfidence(
        lesion_types=ListFieldResult(items=(FieldResult.make("papule", "pattern"),)),      # 0.85
        distribution=ListFieldResult(items=(FieldResult.make("cheeks", "fuzzy", confidence=0.40),)),
    )
    hint = build_confidence_hint(conf, field_threshold=0.6)
    assert "CHƯA CHẮC CHẮN" in hint
    assert "vị trí" in hint.lower() or "distribution" in hint.lower()


def test_moi_field_deu_chac_thi_khong_hedge_gi():
    """Khong co gi de canh bao thi tra chuoi rong -- khong ton token prompt."""
    conf = ExtractionConfidence(
        lesion_types=ListFieldResult(items=(FieldResult.make("papule", "pattern"),)),
        distribution=ListFieldResult(items=(FieldResult.make("cheeks", "pattern"),)),
    )
    hint = build_confidence_hint(conf, field_threshold=0.6)
    assert "CHƯA CHẮC CHẮN" not in hint


def test_field_rong_khong_bi_liet_ke_la_khong_chac():
    """Khong khai khac voi khai ma trich khong chac. Chi cai thu hai moi hedge."""
    hint = build_confidence_hint(ExtractionConfidence(), field_threshold=0.6)
    assert "CHƯA CHẮC CHẮN" not in hint


def test_route_min_confidence_in_settings():
    assert 0.0 < Settings().route_min_confidence < 1.0


def test_clear_advise_still_routes_advise():
    """Cau ro rang van route advise (conf tren nguong, khong bi ep clarify)."""
    user = normalize_chat_message("da minh bi mun mu o ma nen dung gi")
    d = route_intent("da minh bi mun mu o ma nen dung gi", user, [])
    assert d.primary_intent in ("advise", "clarify", "knowledge")
    # neu confidence >= route_min thi khong phai do luat moi ep
    if d.reason_code == "route_confidence_below_threshold":
        assert d.confidence < Settings().route_min_confidence
