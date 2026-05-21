from types import SimpleNamespace

from acne_llm.schemas import AdviseOutput, UserInput
from scripts.run_eval import (
    _build_user_context,
    _normalize_generation_mode,
    _resolve_relevant_ids,
    _try_generate,
)


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


def test_normalize_generation_mode_accepts_baseline_and_rag_aliases():
    assert _normalize_generation_mode("baseline") == "llm_only"
    assert _normalize_generation_mode("rag") == "hybrid"
    assert _normalize_generation_mode("hybrid") == "hybrid"


def test_try_generate_explicit_hybrid_does_not_fallback_to_baseline():
    calls: list[str] = []

    def hybrid_run(user: UserInput):
        calls.append(user.mode)
        raise RuntimeError("hybrid failed")

    def llm_run(user: UserInput):
        calls.append(user.mode)
        return AdviseOutput(mode="llm_only")

    container = SimpleNamespace(
        hybrid=SimpleNamespace(run=hybrid_run),
        llm_only=SimpleNamespace(run=llm_run),
        llm=SimpleNamespace(model="mock"),
    )

    result = _try_generate(container, UserInput(description="mụn", mode="hybrid"), mode="rag", max_retries=1)

    assert result is None
    assert calls == ["hybrid"]


def test_try_generate_baseline_sets_user_mode_to_llm_only():
    seen_modes: list[str] = []

    def llm_run(user: UserInput):
        seen_modes.append(user.mode)
        return AdviseOutput(mode="llm_only")

    container = SimpleNamespace(
        hybrid=None,
        llm_only=SimpleNamespace(run=llm_run),
        llm=SimpleNamespace(model="mock"),
    )

    result = _try_generate(container, UserInput(description="mụn", mode="hybrid"), mode="baseline")

    assert result is not None
    assert result["mode"] == "llm_only"
    assert seen_modes == ["llm_only"]
