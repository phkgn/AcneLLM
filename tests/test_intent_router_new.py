"""Unit tests for intent router -- new flags and routing logic."""
import pytest
from acne_llm.schemas import UserInput, UserContext, AcneClinicalInput
from acne_llm.chat.intent_router import route_intent, is_repeated_question
from acne_llm.chat.session import ConversationTurn


def _user(description="", clinical=None):
    return UserInput(
        description=description,
        mode="hybrid",
        context=UserContext(),
        clinical=clinical,
    )


def _history(*messages):
    return [ConversationTurn(role="user", content=m) for m in messages]


# ── Knowledge routing ─────────────────────────────────────────────────────────

def test_product_query_routes_knowledge():
    r = route_intent("top 5 kem chong nang cho da dau", _user("top 5 kem chong nang"), [])
    assert r.primary_intent == "knowledge"


def test_mechanism_query_routes_knowledge():
    r = route_intent("retinol la gi va hoat dong nhu the nao", _user("retinol la gi"), [])
    assert r.primary_intent == "knowledge"


def test_food_query_routes_knowledge():
    r = route_intent("an mi cay co bi mun khong", _user("an mi cay"), [])
    assert r.primary_intent == "knowledge"


# ── Advise routing ────────────────────────────────────────────────────────────

def test_personal_case_routes_advise():
    r = route_intent("toi bi mun boc o cam da lau roi", _user("mun boc o cam"), [])
    assert r.primary_intent == "advise"


def test_clinical_signal_routes_advise():
    clinical = AcneClinicalInput(lesion_types=["nodule"], lesion_distribution=["chin"])
    r = route_intent("mun boc cung", _user("mun boc", clinical=clinical), [])
    assert r.primary_intent == "advise"


# ── Flags ─────────────────────────────────────────────────────────────────────

def test_emotional_distress_flag():
    r = route_intent("toi rat buon vi bi mun mat tu tin qua", _user("buon vi mun"), [])
    assert "emotional_distress" in r.route_flags


def test_crisis_signal_flag():
    r = route_intent("toi khong muon song nua vi mun", _user("crisis"), [])
    assert "crisis_signal" in r.route_flags


def test_crisis_routes_safety_clarify():
    r = route_intent("toi khong muon song nua vi mun", _user("crisis"), [])
    assert r.turn_type == "safety_clarify"


def test_urgency_red_flag():
    r = route_intent("mun co mau ri dich lan rong mat", _user("mun ri dich"), [])
    assert "urgency_red_flag" in r.route_flags


def test_product_safety_check_flag():
    r = route_intent("dung retinol ket hop voi aha co duoc khong", _user("retinol + aha"), [])
    assert "product_safety_check" in r.route_flags


def test_multi_condition_flag():
    r = route_intent("toi bi mun va rosacea cung luc", _user("mun rosacea"), [])
    assert "multi_condition" in r.route_flags


def test_progress_followup_flag():
    r = route_intent("mun van khong het sau 2 tuan roi", _user("mun van len"), [])
    assert "progress_followup" in r.route_flags


def test_language_switch_flag():
    history = [ConversationTurn(role="user", content="tôi bị mụn viêm", metadata={"detected_language": "vi"})]
    r = route_intent("my acne is getting worse", _user("acne worse"), history)
    assert "language_switch" in r.route_flags


# ── Repeated question detection ───────────────────────────────────────────────

def test_repeated_question_detected():
    history = _history("mun o cam phai dung gi", "co the tri bang benzoyl peroxide")
    assert is_repeated_question("mun o cam phai dung gi", history) is True


def test_different_question_not_repeated():
    history = _history("mun o cam phai dung gi")
    assert is_repeated_question("mun o lung co khac khong", history) is False


def test_repeated_question_flag_in_route():
    history = [ConversationTurn(role="user", content="mun o cam phai dung gi")]
    r = route_intent("mun o cam phai dung gi", _user("mun o cam"), history)
    assert "repeated_question" in r.route_flags


def test_not_repeated_with_empty_history():
    assert is_repeated_question("mun o cam phai dung gi", []) is False


# ── Confidence and source ─────────────────────────────────────────────────────

def test_knowledge_confidence_reasonable():
    r = route_intent("top 5 kem chong nang", _user("kem chong nang"), [])
    assert r.confidence >= 0.7


def test_advise_with_case_signal_high_confidence():
    clinical = AcneClinicalInput(lesion_types=["pustule"], lesion_distribution=["cheeks"])
    r = route_intent("mun mu o ma phai lam sao", _user("mun mu", clinical=clinical), [])
    assert r.confidence >= 0.8


def test_rule_source_when_classifier_disabled():
    r = route_intent("mun viem o cam", _user("mun viem"), [])
    assert r.source == "rule"
