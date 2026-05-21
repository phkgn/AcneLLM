from acne_llm.rag.retriever import rrf_fusion
from acne_llm.rag.retriever import HybridRetriever
from acne_llm.rag.sparse import BM25Index, tokenize_vi
from acne_llm.eval.metrics import recall_at_k, mrr_at_k, ndcg_at_k
from acne_llm.schemas import RetrievedChunk, RetrievalOutput


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


def test_expand_context_fetches_neighbors_in_one_batch():
    class Store:
        def __init__(self):
            self.calls = []

        def get_by_ids(self, chunk_ids):
            self.calls.append(list(chunk_ids))
            return {
                "ids": ["prev-1", "next-1"],
                "documents": ["previous text", "next text"],
                "metadatas": [{"source": "A"}, {"source": "B"}],
            }

    store = Store()
    retriever = HybridRetriever(store=store, embedder=None, bm25=None)
    retrieval = RetrievalOutput(
        query="mụn",
        chunks=[
            RetrievedChunk(
                chunk_id="c1",
                source="src",
                text="center",
                score=0.8,
                metadata={"prev_chunk_id": "prev-1", "next_chunk_id": "next-1"},
            )
        ],
    )

    expanded = retriever.expand_context(retrieval)

    assert store.calls == [["prev-1", "next-1"]]
    assert [chunk.chunk_id for chunk in expanded.chunks] == ["c1", "prev-1", "next-1"]
    assert expanded.chunks[1].score == 0.4


def test_retrieve_safety_pass_uses_embed_query_and_guideline_filter():
    class Embedder:
        def __init__(self):
            self.queries = []

        def embed_query(self, query):
            self.queries.append(query)
            return [0.1, 0.2]

    class Store:
        def __init__(self):
            self.filters = []

        def query_with_score_filter(self, qvec, top_k=5, max_distance=0.65, filters=None):
            self.filters.append(filters)
            return {
                "ids": [["g1"]],
                "documents": [["safety text"]],
                "metadatas": [[{"source": "NICE NG198", "tags": "guidelines"}]],
                "distances": [[0.2]],
            }

    embedder = Embedder()
    store = Store()
    retriever = HybridRetriever(store=store, embedder=embedder, bm25=None)

    out = retriever.retrieve_safety_pass("mụn retinol", ["pregnancy"])

    assert "pregnancy" in embedder.queries[0]
    assert store.filters[0]["source_type"]["$in"]
    assert out.retrieval_mode == "hybrid"
    assert out.chunks[0].source == "NICE NG198"
    assert out.chunks[0].metadata["source_type"] == "nice_guideline"
