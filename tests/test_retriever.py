from acne_llm.rag.retriever import rrf_fusion
from acne_llm.rag.sparse import BM25Index, tokenize_vi
from acne_llm.eval.metrics import recall_at_k, mrr_at_k, ndcg_at_k


def test_rrf_fusion_basic():
    a = ["x", "y", "z"]
    b = ["y", "z", "x"]
    fused = rrf_fusion([a, b])
    assert fused["y"] > fused["x"]  # y ranked 2nd and 1st → higher


def test_bm25_roundtrip(tmp_path):
    ids = ["c1", "c2", "c3"]
    texts = [
        "mụn viêm ở cằm do vi khuẩn",
        "benzoyl peroxide điều trị mụn",
        "chế độ ăn uống và da",
    ]
    idx = BM25Index()
    idx.build(ids, texts)
    hits = idx.query("mụn viêm", top_k=3)
    assert hits[0][0] == "c1"

    p = tmp_path / "bm25.pkl"
    idx.save(str(p))
    loaded = BM25Index.load(str(p))
    assert loaded.chunk_ids == ids


def test_metrics():
    retrieved = ["a", "b", "c", "d"]
    rel = {"b", "d"}
    assert recall_at_k(retrieved, rel, 4) == 1.0
    assert recall_at_k(retrieved, rel, 1) == 0.0
    assert mrr_at_k(retrieved, rel, 4) == 0.5  # b at rank 2
    assert 0 < ndcg_at_k(retrieved, rel, 4) <= 1.0


def test_tokenize_fallback():
    # even if underthesea fails, tokenize_vi returns a list
    toks = tokenize_vi("Mụn viêm ở cằm")
    assert len(toks) >= 3
