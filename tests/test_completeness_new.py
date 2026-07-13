"""Unit tests for completeness checker -- partial advise and edge cases."""
import pytest
from acne_llm.schemas import UserInput, AcneClinicalInput, UserContext
from acne_llm.chat.completeness import check_completeness, CompletenessResult
from acne_llm.chat.session import ConversationTurn


def _user(lesion_types=None, lesion_distribution=None, inflammation_level=None, description="mun viem"):
    return UserInput(
        description=description,
        mode="hybrid",
        context=UserContext(),
        clinical=AcneClinicalInput(
            lesion_types=lesion_types or [],
            lesion_distribution=lesion_distribution or [],
            inflammation_level=inflammation_level or "none",
        ),
    )


def _user_no_clinical(description="xin chao"):
    return UserInput(description=description, mode="hybrid", context=UserContext())


# ── too_short ─────────────────────────────────────────────────────────────────

def test_too_short_no_signal_no_history():
    user = _user_no_clinical("hi")
    result = check_completeness(user)
    assert result.kind == "too_short"
    assert result.level == "none"
    assert result.followup_question is not None


def test_too_short_bypassed_when_has_signal():
    # Short message but has clinical signal -> not too_short
    user = _user(lesion_types=["papule"], description="mun")
    result = check_completeness(user)
    # Has signal so completeness should proceed past too_short
    assert result.kind != "too_short"


def test_too_short_bypassed_in_intake_flow():
    # Bot vừa hỏi clarify -> reply ngắn là hợp lệ
    history = [ConversationTurn(role="assistant", content="Mụn ở vùng nào?", mode="clarify")]
    user = _user_no_clinical("o ma")
    result = check_completeness(user, history=history)
    assert result.kind != "too_short"


# ── partial ───────────────────────────────────────────────────────────────────

def test_partial_when_has_inflammation_but_missing_distribution():
    user = _user(lesion_types=["papule"], inflammation_level="moderate")
    result = check_completeness(user)
    assert result.kind == "partial"
    assert result.partial_advise is True
    assert result.level == "sufficient"  # partial DOES allow LLM to answer
    assert result.followup_question is not None
    assert "distribution" in result.missing_fields


def test_partial_when_has_distribution_but_missing_lesion_types():
    user = _user(lesion_distribution=["cheeks"], inflammation_level="severe")
    result = check_completeness(user)
    # Has distribution + severe -> enough to answer (sufficient or partial)
    assert result.level == "sufficient"


def test_partial_not_shown_if_already_asked():
    user = _user(lesion_types=["papule"], inflammation_level="moderate")
    result = check_completeness(user, asked_fields={"distribution"})
    # distribution already asked -> skip that question
    assert "distribution" not in (result.missing_fields or [])


def test_partial_lesion_types_shown_first_time():
    # Has distribution + mild -> partial, missing lesion_types
    user = _user(lesion_distribution=["forehead"], inflammation_level="mild")
    result = check_completeness(user)
    assert result.kind == "partial"
    assert "lesion_types" in result.missing_fields


def test_partial_not_repeated_if_lesion_types_already_asked():
    user = _user(lesion_distribution=["forehead"], inflammation_level="mild")
    result = check_completeness(user, asked_fields={"lesion_types"})
    # Already asked lesion_types -> skip, move to distribution or sufficient
    assert "lesion_types" not in (result.missing_fields or [])


# ── sufficient ────────────────────────────────────────────────────────────────

def test_sufficient_when_all_core_fields_present():
    user = _user(lesion_types=["papule", "pustule"], lesion_distribution=["cheeks"], inflammation_level="moderate")
    assert check_completeness(user).kind == "sufficient"


def test_sufficient_severe_inflammation_alone():
    # Severe inflammation alone qualifies as "enough to answer"
    user = _user(inflammation_level="severe", description="mun rat nang viem nhieu")
    result = check_completeness(user)
    assert result.level == "sufficient"


def test_sufficient_in_intake_flow_with_signal():
    history = [ConversationTurn(role="assistant", content="Mụn trông thế nào?", mode="clarify")]
    user = _user(lesion_types=["pustule"], description="mun mu co dau")
    result = check_completeness(user, history=history)
    assert result.kind == "sufficient"


# ── missing_core (blocking) ────────────────────────────────────────────────────

def test_missing_core_when_only_acne_signal_no_clinical():
    # Has age signal but no clinical -> has_signal=True but _has_enough=False
    user = UserInput(
        description="toi bi mun nhieu lam bi lau roi khong het",
        mode="hybrid",
        context=UserContext(age=22),
        clinical=AcneClinicalInput(),
    )
    result = check_completeness(user)
    # Should ask for lesion_types or distribution
    assert result.level == "none"
    assert result.kind == "missing_core"


def test_missing_core_skipped_if_both_asked():
    user = UserInput(
        description="toi bi mun nhieu lam",
        mode="hybrid",
        context=UserContext(age=22),
        clinical=AcneClinicalInput(),
    )
    result = check_completeness(
        user,
        asked_fields={"lesion_types", "distribution", "inflammation"},
    )
    # All core fields already asked -> no more questions -> sufficient
    assert result.kind == "sufficient"


# ── level property ────────────────────────────────────────────────────────────

def test_level_property_mapping():
    assert CompletenessResult(kind="sufficient").level == "sufficient"
    assert CompletenessResult(kind="partial").level == "sufficient"
    assert CompletenessResult(kind="missing_core").level == "none"
    assert CompletenessResult(kind="too_short").level == "none"
    assert CompletenessResult(kind="complaint").level == "none"
