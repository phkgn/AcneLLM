from acne_llm.chat.session import ConversationTurn
from acne_llm.utils.retrieval_query import build_current_turn_query

# test_retrieval_query_uses_normalized_text_not_raw_slang da bi xoa cung voi
# build_retrieval_query_from_user (Phase 1) -- ham do chi con test goi.


def test_danger_query_expands_to_general_red_flags_not_a_body_location():
    query = build_current_turn_query("mụn sao là nguy hiểm")

    assert "severe acne red flags" in query
    assert "lip" not in query


def test_acne_nodule_comparison_expands_precise_terms():
    query = build_current_turn_query("mụn đầu đen khác với mụn bọc như thế nào")

    assert "open comedone blackhead" in query
    assert "nodular acne cystic acne acne nodule" in query
    assert "boil" not in query


def test_explicit_followup_query_adds_only_previous_user_turn():
    history = [
        ConversationTurn(role="user", content="tôi bị mụn viêm ở má"),
        ConversationTurn(role="assistant", content="câu trả lời cũ"),
    ]

    query = build_current_turn_query("còn mụn nào ngoài mụn này?", history)

    assert query.startswith("còn mụn nào ngoài mụn này?")
    assert "tôi bị mụn viêm ở má" in query
    assert "câu trả lời cũ" not in query
