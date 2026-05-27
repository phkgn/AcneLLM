from acne_llm.chat.normalizer import normalize_chat_message
from acne_llm.chat.preprocess import prepare_user_text
from acne_llm.utils.retrieval_query import build_retrieval_query_from_user


def test_retrieval_query_uses_normalized_text_not_raw_slang():
    prepared = prepare_user_text("mụn bọc ở cằm vs BHA 2% k dc dùng sáng tối")
    user = normalize_chat_message(
        "mụn bọc ở cằm vs BHA 2% k dc dùng sáng tối",
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )

    query = build_retrieval_query_from_user(user, clean_text_normalized=prepared.clean_text)

    assert " vs " not in f" {query} "
    assert " k " not in f" {query} "
    assert "không được" in query
    assert "salicylic_acid" in query
    assert "twice_daily" in query
    assert "0.02" in query
