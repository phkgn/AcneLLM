"""Ô cứng cho khuyến cáo chính thức trong context.

Vì sao cần: guideline pass đã bơm ~5 đoạn khuyến cáo vào pool ở mọi truy vấn,
nhưng đo trên 152 truy vấn chỉ 16/760 đoạn sống sót ra câu trả lời — cross-encoder
luôn cho đoạn tiếng Việt điểm cao hơn đoạn guideline tiếng Anh cùng chủ đề.
`ensure_guideline_slot` chữa ở tầng rerank. Test này giữ cho nó không hỏng thầm.
"""
from __future__ import annotations

from acne_llm.chat._retrieval import ensure_guideline_slot
from acne_llm.schemas import RetrievalOutput, RetrievedChunk


def _chunk(chunk_id: str, score: float, source_type: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        source=source_type,
        text=f"noi dung {chunk_id}",
        score=score,
        metadata={"source_type": source_type},
    )


def _out(chunks: list[RetrievedChunk]) -> RetrievalOutput:
    return RetrievalOutput(
        query="mun o cam",
        chunks=chunks,
        retrieval_mode="rerank",
        num_chunks=len(chunks),
        avg_score=sum(c.score for c in chunks) / len(chunks) if chunks else 0.0,
    )


def test_thay_o_thap_nhat_khi_top_k_khong_co_guideline():
    top = _out([
        _chunk("a", 0.90, "vi_medical_site"),
        _chunk("b", 0.40, "vi_medical_site"),   # thấp nhất -> bị thay
        _chunk("c", 0.70, "blog"),
    ])
    pool = _out([*top.chunks,
                 _chunk("g1", 0.30, "aad_guideline"),
                 _chunk("g2", 0.50, "nice_guideline")])

    result = ensure_guideline_slot(top, pool, limit=3)
    ids = [c.chunk_id for c in result.chunks]

    assert "b" not in ids                      # ô yếu nhất nhường chỗ
    assert "g2" in ids                         # guideline điểm cao nhất được chọn
    assert ids == ["a", "g2", "c"]             # thay tại chỗ, không xáo thứ tự
    assert result.num_chunks == 3              # không phình quá limit


def test_thu_tu_dao_van_tim_dung_o_yeu_nhat():
    """Bộ lọc phía trước có thể đổi thứ tự — không được giả định đã sắp giảm dần."""
    top = _out([
        _chunk("thap", 0.10, "blog"),          # yếu nhất nhưng đứng ĐẦU
        _chunk("cao", 0.95, "vi_medical_site"),
    ])
    pool = _out([*top.chunks, _chunk("g", 0.20, "aad_guideline")])

    ids = [c.chunk_id for c in ensure_guideline_slot(top, pool, limit=2).chunks]
    assert ids == ["g", "cao"]


def test_da_co_guideline_thi_khong_dong_gi():
    top = _out([_chunk("g", 0.20, "nice_guideline"), _chunk("a", 0.90, "blog")])
    pool = _out([*top.chunks, _chunk("g2", 0.99, "aad_guideline")])

    assert ensure_guideline_slot(top, pool, limit=2) is top


def test_pool_khong_co_guideline_thi_giu_nguyen():
    top = _out([_chunk("a", 0.90, "blog"), _chunk("b", 0.10, "blog")])
    assert ensure_guideline_slot(top, top, limit=2) is top


def test_chua_day_limit_thi_them_chu_khong_thay():
    """Đang có 2/5 ô mà thay thì mất thông tin vô cớ — còn chỗ trống thì bơm thêm."""
    top = _out([_chunk("a", 0.90, "blog"), _chunk("b", 0.80, "blog")])
    pool = _out([*top.chunks, _chunk("g", 0.30, "aad_guideline")])

    result = ensure_guideline_slot(top, pool, limit=5)
    assert [c.chunk_id for c in result.chunks] == ["a", "b", "g"]
    assert result.num_chunks == 3


def test_khong_bom_khi_OOD_guard_da_tra_None():
    """None = không đoạn nào liên quan, câu ngoài phạm vi. Bơm guideline vào lúc
    đó là biến 'tôi không biết' thành 'đây là khuyến cáo lạc đề'."""
    pool = _out([_chunk("g", 0.30, "aad_guideline")])
    assert ensure_guideline_slot(None, pool, limit=5) is None
    assert ensure_guideline_slot(_out([]), pool, limit=5).chunks == []


def test_khong_bom_trung_doan_da_co():
    """Cùng chunk_id đã nằm trong top thì không được đếm là ứng viên."""
    guideline = _chunk("g", 0.30, "clinical_textbook")
    top = _out([guideline, _chunk("a", 0.90, "blog")])
    pool = _out([guideline, _chunk("a", 0.90, "blog")])
    assert ensure_guideline_slot(top, pool, limit=2) is top


def test_clinical_textbook_cung_tinh_la_guideline():
    top = _out([_chunk("a", 0.90, "blog")])
    pool = _out([*top.chunks, _chunk("t", 0.10, "clinical_textbook")])
    assert "t" in [c.chunk_id for c in ensure_guideline_slot(top, pool, limit=1).chunks]
