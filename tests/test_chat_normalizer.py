from unittest.mock import MagicMock

from acne_llm.chat.normalizer import normalize_chat_message
from acne_llm.chat.runtime import decide_chat_mode


def test_normalizer_extracts_core_context_from_free_text():
    user = normalize_chat_message(
        "Em 22 tuổi, da dầu, mụn viêm ở cằm 4 tuần, đang dùng BHA, không mang thai."
    )

    assert user.context.age == 22
    assert user.context.skin_type == "oily"
    assert user.context.duration_weeks == 4
    assert user.context.is_pregnant is False
    assert "bha" in user.context.current_products
    assert user.clinical is not None
    assert "papule" in user.clinical.lesion_types
    assert "chin" in user.clinical.lesion_distribution
    assert user.clinical.inflammation_level == "moderate"


def test_normalizer_extracts_safety_flags():
    user = normalize_chat_message("Mình đang cho con bú, bị mụn mủ ở má và dùng retinol.")

    assert user.context.is_breastfeeding is True
    assert "retinol" in user.context.current_products
    assert user.clinical is not None
    assert "pustule" in user.clinical.lesion_types
    assert "cheeks" in user.clinical.lesion_distribution


def test_auto_mode_routes_meta_directly():
    c = MagicMock()
    c.rag_ready = True

    decision = decide_chat_mode("xin chào", "auto", c)

    assert decision.mode == "meta"
    assert decision.direct_response


def test_auto_mode_prefers_hybrid_when_rag_ready():
    c = MagicMock()
    c.rag_ready = True

    decision = decide_chat_mode("Tôi bị mụn viêm ở cằm", "auto", c)

    assert decision.mode == "hybrid"
    assert decision.direct_response is None


def test_auto_mode_falls_back_to_llm_only_without_rag():
    c = MagicMock()
    c.rag_ready = False

    decision = decide_chat_mode("Tôi bị mụn viêm ở cằm", "auto", c)

    assert decision.mode == "llm_only"
