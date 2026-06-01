"""Test hạ tầng FieldResult + fuzzy_match (không đụng pipeline production)."""
from acne_llm.schemas.extraction import FieldResult, ListFieldResult, clamp01
from acne_llm.utils.fuzzy_match import best_match, find_in_text, classify


# ---------------------------------------------------------------- FieldResult

def test_clamp01():
    assert clamp01(-0.5) == 0.0
    assert clamp01(1.5) == 1.0
    assert clamp01(0.42) == 0.42


def test_none_result():
    r = FieldResult.none()
    assert r.value is None
    assert r.confidence == 0.0
    assert r.method == "none"
    assert not r.is_confident(0.0)  # value None → luôn False


def test_make_uses_method_base():
    r = FieldResult.make("oily", "exact")
    assert r.value == "oily"
    assert r.confidence == 0.95


def test_make_explicit_confidence_for_fuzzy():
    r = FieldResult.make("retinol", "fuzzy", confidence=0.86)
    assert r.confidence == 0.86
    assert r.method == "fuzzy"


def test_make_adjust_and_clamp():
    # pattern base 0.85, phủ định −0.15
    r = FieldResult.make("oily", "pattern", adjust=-0.15)
    assert abs(r.confidence - 0.70) < 1e-9
    # cộng quá 1 → kẹp
    r2 = FieldResult.make("oily", "exact", adjust=0.5)
    assert r2.confidence == 1.0


def test_is_confident_threshold():
    r = FieldResult.make("mild", "fallback")  # 0.45
    assert not r.is_confident(0.60)
    assert r.is_confident(0.40)


def test_list_field_result():
    lst = ListFieldResult(items=(
        FieldResult.make("retinol", "exact"),
        FieldResult.make("bha", "fuzzy", confidence=0.78),
    ))
    assert lst.values == ["retinol", "bha"]
    assert lst.max_confidence == 0.95
    assert lst.confident_values(0.80) == ["retinol"]


# ---------------------------------------------------------------- fuzzy_match

CANON = ("retinol", "benzoyl peroxide", "salicylic acid", "differin", "niacinamide")


def test_best_match_exact():
    hit = best_match("retinol", CANON)
    assert hit is not None and hit.canonical == "retinol"
    assert hit.similarity > 0.99


def test_best_match_typo():
    # sai chính tả vẫn khớp — đây là điểm cốt lõi (không cần thêm entry)
    for typo, expect in [("rentinol", "retinol"), ("diferin", "differin"),
                         ("salicilic acid", "salicylic acid")]:
        hit = best_match(typo, CANON)
        assert hit is not None and hit.canonical == expect, (typo, hit)
        assert hit.similarity >= 0.80, (typo, hit.similarity)


def test_find_in_text_multiword():
    text = "minh dang dung benzoyl peroxide va niacinamide buoi toi"
    hits = find_in_text(text, CANON, accept=0.86, review=0.72)
    found = {h.canonical for h in hits}
    assert "benzoyl peroxide" in found
    assert "niacinamide" in found


def test_find_in_text_respects_review_floor():
    text = "toi thich an com va uong nuoc"  # không liên quan
    hits = find_in_text(text, CANON, accept=0.86, review=0.72)
    assert hits == []


def test_classify_single():
    hit = classify("retinoll", CANON)
    assert hit is not None and hit.canonical == "retinol"
