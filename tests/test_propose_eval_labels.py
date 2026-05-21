from scripts.propose_eval_labels import build_label_suggestions


class _FakeBM25:
    def query(self, query: str, top_k: int = 8):
        return [("c1", 1.25), ("c2", 0.75)][:top_k]


class _FakeStore:
    def get_by_id(self, chunk_id: str):
        return {
            "documents": [f"{chunk_id} text"],
            "metadatas": [{
                "source": "PubMed",
                "title": f"Title {chunk_id}",
                "url": f"https://example.com/{chunk_id}",
                "trust": "high",
            }],
        }


def test_build_label_suggestions_shape():
    out = build_label_suggestions("mụn viêm", _FakeBM25(), _FakeStore(), top_k=2, max_chars=20)
    assert [x["chunk_id"] for x in out] == ["c1", "c2"]
    assert out[0]["score"] == 1.25
    assert out[0]["snippet"] == "c1 text"
    assert out[0]["source"] == "PubMed"
