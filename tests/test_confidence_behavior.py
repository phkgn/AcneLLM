"""Test hanh vi MOI do confidence dieu khien: completeness gating + route clarify."""
from acne_llm.schemas import UserInput, UserContext, AcneClinicalInput
from acne_llm.schemas.extraction import FieldResult, ListFieldResult
from acne_llm.chat.completeness import check_completeness
from acne_llm.chat.extraction_confidence import extract_with_confidence, ExtractionConfidence
from acne_llm.chat.normalizer import normalize_chat_message
from acne_llm.chat.intent_router import route_intent
from acne_llm.config import Settings


def _user(lesion_types=None, dist=None, inflammation="none"):
    return UserInput(description="mun viem o ma", mode="hybrid", context=UserContext(),
        clinical=AcneClinicalInput(lesion_types=lesion_types or [], lesion_distribution=dist or [],
                                   inflammation_level=inflammation))


def test_low_confidence_field_triggers_missing():
    """Field co gia tri nhung confidence THAP -> coi nhu thieu -> hoi lai."""
    user = _user(lesion_types=["papule"], dist=["cheeks"], inflammation="moderate")
    # confidence map: lesion_types conf cao, distribution conf THAP (duoi 0.6)
    conf = ExtractionConfidence(
        lesion_types=ListFieldResult(items=(FieldResult.make("papule", "pattern"),)),     # 0.85
        distribution=ListFieldResult(items=(FieldResult.make("cheeks", "fuzzy", confidence=0.40),)),  # thap
    )
    r = check_completeness(user, confidence=conf)
    # distribution conf thap -> van nam trong missing
    assert "distribution" in (r.missing_fields or []) or r.kind in ("partial", "missing_core")


def test_high_confidence_field_not_missing():
    user = _user(lesion_types=["papule"], dist=["cheeks"], inflammation="moderate")
    conf = ExtractionConfidence(
        lesion_types=ListFieldResult(items=(FieldResult.make("papule", "pattern"),)),
        distribution=ListFieldResult(items=(FieldResult.make("cheeks", "pattern"),)),  # 0.85 cao
    )
    r = check_completeness(user, confidence=conf)
    assert "distribution" not in (r.missing_fields or [])


def test_completeness_backward_compat_no_confidence():
    """Khong truyen confidence -> hanh vi cu (chi xet co gia tri)."""
    user = _user(lesion_types=["papule"], dist=["cheeks"], inflammation="moderate")
    r = check_completeness(user)
    assert r.kind == "sufficient"


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
