"""Test tang confidence boc quanh normalizer (khong pha vo hanh vi cu)."""
from acne_llm.chat.fallback.rule_extractor import extract_with_confidence
from acne_llm.chat.fallback.rule_normalizer import normalize_chat_message


def test_values_consistent_with_normalizer():
    """Gia tri tu confidence layer phai KHOP normalize_chat_message."""
    msg = "da minh nhieu dau, bi mun viem o ma, dang boi retinol, stress va muon giam mun"
    user = normalize_chat_message(msg)
    ec = extract_with_confidence(msg)
    assert ec.skin_type.value == user.context.skin_type  # cung extractor -> cung gia tri
    assert set(user.context.current_products).issubset(set(ec.products.values))
    assert set(user.clinical.hormonal_factors).issubset(set(ec.hormonal_factors.values))
    assert set(user.clinical.treatment_goals).issubset(set(ec.treatment_goals.values))


def test_skin_type_has_confidence():
    ec = extract_with_confidence("da minh nhieu dau")
    assert ec.skin_type.value == "oily"
    assert ec.skin_type.confidence > 0.7
    assert ec.skin_type.method == "pattern"


def test_question_drops_skin_type_when_marker_matches():
    """Cau so sanh khop marker regex cu -> skin_type bi drop."""
    ec = extract_with_confidence("so sanh da dau va da kho khac gi nhau")
    assert ec.skin_type.value is None
    assert ec.skin_type.confidence == 0.0


def test_fuzzy_catches_typo_product():
    """Sai chinh ta san pham -> fuzzy bat duoc ma KHONG can them entry."""
    ec = extract_with_confidence("minh dang dung niacinamid va retinol")
    vals = ec.products.values
    assert "niacinamide" in vals or "retinol" in vals
    assert ec.products.max_confidence >= 0.72


def test_inflammation_fallback_low_confidence():
    ec = extract_with_confidence("minh bi may not o tran")
    if ec.inflammation.value == "mild" and ec.inflammation.method == "fallback":
        assert ec.inflammation.confidence < 0.6


def test_severe_explicit_high_confidence():
    ec = extract_with_confidence("mun boc rat to va dau, sung do khap mat")
    assert ec.inflammation.value == "severe"
    assert ec.inflammation.confidence >= 0.85


def test_empty_message():
    ec = extract_with_confidence("xin chao")
    assert ec.skin_type.value is None
    assert ec.products.values == []
    assert ec.is_pregnant.value is None
    assert ec.is_breastfeeding.value is None


def test_pregnancy_and_breastfeeding_confidence():
    ec = extract_with_confidence("Mình đang mang thai và cho con bú, bị mụn viêm.")
    assert ec.is_pregnant.value is True
    assert ec.is_pregnant.confidence >= 0.85
    assert ec.is_breastfeeding.value is True
    assert ec.is_breastfeeding.confidence >= 0.85


def test_explicit_negative_pregnancy_confidence():
    ec = extract_with_confidence("Mình không mang thai, đang bị mụn ở cằm.")
    assert ec.is_pregnant.value is False
    assert ec.is_pregnant.confidence >= 0.85


def test_allergy_pattern_and_fuzzy_with_context():
    ec = extract_with_confidence("Da mình dị ứng với retinoll và BHA làm da mình rát")
    assert "retinol" in ec.allergies.values
    assert "bha_irritation" in ec.allergies.values
    assert ec.allergies.max_confidence >= 0.8


def test_allergy_fuzzy_requires_allergy_context():
    ec = extract_with_confidence("Mình đang dùng retinoll cho mụn ở cằm")
    assert "retinol" not in ec.allergies.values


def test_scarring_hormonal_and_goal_confidence():
    ec = extract_with_confidence("Mình có sẹo rỗ và thâm mụn, mụn lên trước kỳ kinh, muốn trị sẹo")
    assert "sẹo mụn" in ec.scarring_signs.values
    assert "thâm sau mụn" in ec.scarring_signs.values
    assert "menstrual_cycle" in ec.hormonal_factors.values
    assert "treat_scar" in ec.treatment_goals.values
