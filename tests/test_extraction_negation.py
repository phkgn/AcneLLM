"""Regression: false-fact promotion in extraction (audit P0 #2).

Covers:
- accent collision "dầu" (oily) must not become "đau" (painful) → red flag.
- negation/discontinuation: "không dùng X nữa", "ngưng/bỏ X" must not extract
  X as a currently-used product or as a canonical ingredient.
- positive controls: genuine current use is still extracted.
"""
from acne_llm.chat.routing import rule_normalizer as N
from acne_llm.chat.routing.rule_extractor import extract_with_confidence
from acne_llm.chat.preprocess import strip_accents


def _products(text: str) -> list[str]:
    return [f.value for f in extract_with_confidence(text).products.items]


def _canonical(text: str) -> list[str]:
    return N._extract_canonical_ingredients([], [], text, strip_accents(text))


# ── accent collision: dầu → đau ────────────────────────────────────────────

def test_oily_skin_not_extracted_as_painful():
    text = "Tôi là nữ 24 tuổi, da khá dầu."
    assert N._extract_red_flags(text) == []
    assert N._extract_red_flags(strip_accents(text)) == []
    r = extract_with_confidence(text)
    assert r.skin_type.value == "oily"
    assert list(r.red_flags.items) == []


def test_genuine_pain_still_flagged():
    assert "painful_lesions" in N._extract_red_flags("mụn sưng đau nhiều lắm")


# ── negation / discontinuation ─────────────────────────────────────────────

def test_discontinued_product_not_extracted():
    for text in ["không dùng BHA nữa", "tôi không dùng BHA nữa",
                 "ngưng BHA rồi", "bỏ salicylic acid", "ngưng dùng salicylic acid"]:
        assert _products(text) == [], f"products leaked for: {text}"
        assert _canonical(text) == [], f"canonical leaked for: {text}"


def test_switch_drops_old_keeps_new():
    text = "tôi không dùng BHA nữa, chuyển sang benzoyl peroxide"
    prods = _products(text)
    assert "BHA" not in prods
    assert "salicylic acid" not in prods
    assert "benzoyl peroxide" in prods
    assert "salicylic_acid" not in _canonical(text)


# ── positive controls ──────────────────────────────────────────────────────

def test_current_use_still_extracted():
    assert "BHA" in _products("đang dùng BHA")
    assert "salicylic_acid" in _canonical("đang dùng BHA")
    assert "salicylic acid" in _products("mình bôi salicylic acid mỗi tối")


def test_negation_not_adjacent_is_still_use():
    # "không" modifies "kích ứng", not "dùng salicylic acid" → still using it.
    text = "không bị kích ứng khi dùng salicylic acid"
    assert "salicylic acid" in _products(text)
    assert "salicylic_acid" in _canonical(text)
