from acne_llm.schemas import RetrievedChunk, RetrievalOutput
from acne_llm.utils.chunk_filter import (
    drop_acne_boils_mismatched_chunks,
    drop_query_mismatched_chunks,
)


def _chunk(chunk_id, text, score=0.8):
    return RetrievedChunk(
        chunk_id=chunk_id,
        source="src",
        text=text,
        score=score,
        metadata={},
    )


def test_concrete_sunscreen_query_drops_unrelated_chunk():
    retrieval = RetrievalOutput(
        query="top 5 kem chống nắng cho da dầu",
        chunks=[
            _chunk("good", "Kem chống nắng oil-free phù hợp da dầu mụn."),
            _chunk("bad", "Nghiên cứu về impulsivity và tâm lý bệnh nhân mụn."),
        ],
    )

    filtered = drop_query_mismatched_chunks(retrieval, retrieval.query)

    assert [chunk.chunk_id for chunk in filtered.chunks] == ["good"]


def test_generic_acne_query_keeps_semantic_retrieval_unchanged():
    retrieval = RetrievalOutput(
        query="mụn viêm",
        chunks=[_chunk("c1", "Inflammatory acne overview.")],
    )

    assert drop_query_mismatched_chunks(retrieval, retrieval.query) is retrieval


def test_domain_acne_terms_are_not_removed_for_concrete_filtering():
    retrieval = RetrievalOutput(
        query="retinol cho mụn viêm có an toàn không",
        chunks=[
            _chunk("good", "Retinol và acne có thể gây kích ứng trong điều trị mụn viêm."),
            _chunk("bad", "Kem chống nắng phổ rộng phù hợp đi biển."),
        ],
    )

    filtered = drop_query_mismatched_chunks(retrieval, retrieval.query)

    assert [chunk.chunk_id for chunk in filtered.chunks] == ["good"]


# ponytail: 2 test cua drop_body_region_mismatched_chunks da xoa o Phase 7
# cung ham no test. Xem chunk_filter.py de biet ly do.

def test_acne_nodule_query_drops_boil_only_chunk():
    retrieval = RetrievalOutput(
        query="mụn đầu đen khác với mụn bọc",
        chunks=[
            _chunk("nodule", "Nodular acne and cystic acne are deep inflammatory acne lesions."),
            _chunk("boil", "Mụn nhọt là furuncle do nhiễm trùng tạo skin abscess."),
        ],
    )

    filtered = drop_acne_boils_mismatched_chunks(retrieval, retrieval.query)

    assert [chunk.chunk_id for chunk in filtered.chunks] == ["nodule"]
