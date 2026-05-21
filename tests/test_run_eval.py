from scripts.run_eval import _resolve_relevant_ids, _build_user_context


class _FakeChunk:
    def __init__(self, chunk_id: str):
        self.chunk_id = chunk_id


class _FakeRetrieval:
    def __init__(self, ids: list[str]):
        self.chunks = [_FakeChunk(cid) for cid in ids]


class _FakeRetriever:
    def retrieve(self, query: str, top_k: int = 5, mode: str = "sparse"):
        return _FakeRetrieval(["c1", "c2", "c3"][:top_k])


def test_resolve_relevant_ids_prefers_manual_labels():
    rel, source = _resolve_relevant_ids(
        {"query": "x", "relevant_chunk_ids": ["a", "", "b"]},
        _FakeRetriever(),
    )
    assert rel == ["a", "b"]
    assert source == "manual"


def test_resolve_relevant_ids_falls_back_to_sparse_hits():
    rel, source = _resolve_relevant_ids({"query": "mụn viêm"}, _FakeRetriever(), label_top_k=2)
    assert rel == ["c1", "c2"]
    assert source == "auto:sparse_top2"


def test_build_user_context_maps_gender_and_ignores_extras():
    ctx = _build_user_context({"age": 22, "gender": "female", "skin_type": "oily", "foo": "bar"})
    assert ctx.age == 22
    assert ctx.sex == "female"
    assert ctx.skin_type == "oily"
