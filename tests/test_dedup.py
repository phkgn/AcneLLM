import pytest

datasketch = pytest.importorskip("datasketch")
from acne_llm.crawler.dedup import dedup_documents  # noqa: E402


def test_dedup_keeps_distinct():
    docs = [
        {"doc_id": "a", "text": "mụn viêm là do vi khuẩn xâm nhập vào nang lông bị bít tắc"},
        {"doc_id": "b", "text": "benzoyl peroxide có tác dụng diệt khuẩn và bong lớp sừng"},
        {"doc_id": "c", "text": "mụn viêm là do vi khuẩn xâm nhập vào nang lông bị bít tắc lại"},
    ]
    kept = dedup_documents(docs, threshold=0.8)
    ids = {d["doc_id"] for d in kept}
    # c is near-dup of a → drop one of them
    assert len(kept) == 2
    assert "b" in ids
