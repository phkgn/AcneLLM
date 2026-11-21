import json
from pathlib import Path

import numpy as np

from acne_llm.chat.routing.semantic_router import SemanticRouter


class _FakeEmbedder:
    model_name = "fake-v1"

    def __init__(self):
        self.passage_calls = 0

    @staticmethod
    def _vector(text: str) -> np.ndarray:
        lowered = text.lower()
        if "advise" in lowered:
            return np.asarray([1.0, 0.0], dtype=np.float32)
        if "knowledge" in lowered:
            return np.asarray([0.0, 1.0], dtype=np.float32)
        if "clarify" in lowered:
            return np.asarray([0.7, 0.7], dtype=np.float32)
        if "ambiguous" in lowered:
            return np.asarray([1.0, 1.0], dtype=np.float32)
        return np.asarray([-1.0, -1.0], dtype=np.float32)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        self.passage_calls += 1
        return np.stack([self._vector(text) for text in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _train_rows() -> list[dict]:
    return [
        {"text": "advise one", "intent": "advise"},
        {"text": "advise two", "intent": "advise"},
        {"text": "knowledge one", "intent": "knowledge"},
        {"text": "knowledge two", "intent": "knowledge"},
        {"text": "clarify one", "intent": "clarify"},
    ]


def test_semantic_router_classifies_and_metadata_has_no_subject(tmp_path: Path):
    train = tmp_path / "train.jsonl"
    cache = tmp_path / "index.npz"
    _write_jsonl(train, _train_rows())
    router = SemanticRouter(
        embedder=_FakeEmbedder(),
        train_path=train,
        cache_path=cache,
        k=1,
        oos_distance_threshold=0.5,
        ambiguity_margin=0.0,
    )

    decision = router.classify("advise query")

    assert decision.primary_intent == "advise"
    assert decision.source == "semantic"
    assert decision.reason_code == "semantic_router"
    assert "query_subject" not in decision.metadata()


def test_semantic_router_applies_oos_before_vote(tmp_path: Path):
    train = tmp_path / "train.jsonl"
    _write_jsonl(train, _train_rows())
    router = SemanticRouter(
        embedder=_FakeEmbedder(),
        train_path=train,
        cache_path=tmp_path / "index.npz",
        k=3,
        oos_distance_threshold=0.2,
        ambiguity_margin=0.0,
    )

    prediction = router.predict("weather outside domain")

    assert prediction.primary_intent == "reject"
    assert prediction.nearest_distance > 0.2
    assert prediction.ambiguity_reason.startswith("oos_distance=")


def test_semantic_router_forces_close_vote_to_clarify(tmp_path: Path):
    train = tmp_path / "train.jsonl"
    _write_jsonl(
        train,
        [
            {"text": "advise one", "intent": "advise"},
            {"text": "knowledge one", "intent": "knowledge"},
        ],
    )
    router = SemanticRouter(
        embedder=_FakeEmbedder(),
        train_path=train,
        cache_path=tmp_path / "index.npz",
        k=2,
        oos_distance_threshold=1.0,
        ambiguity_margin=0.05,
    )

    prediction = router.predict("ambiguous query")

    assert prediction.primary_intent == "clarify"
    assert prediction.vote_margin == 0.0
    assert prediction.ambiguity_reason.startswith("vote_margin=")


def test_semantic_router_reuses_cache_for_same_train_hash(tmp_path: Path):
    train = tmp_path / "train.jsonl"
    cache = tmp_path / "index.npz"
    _write_jsonl(train, _train_rows())
    first_embedder = _FakeEmbedder()
    first = SemanticRouter(
        embedder=first_embedder,
        train_path=train,
        cache_path=cache,
        k=1,
    )
    assert first.indexed_rows == len(_train_rows())
    assert first_embedder.passage_calls == 1
    assert first.cache_hit is False

    second_embedder = _FakeEmbedder()
    second = SemanticRouter(
        embedder=second_embedder,
        train_path=train,
        cache_path=cache,
        k=1,
    )
    assert second.indexed_rows == len(_train_rows())
    assert second_embedder.passage_calls == 0
    assert second.cache_hit is True


def test_semantic_router_rejects_non_train_contract(tmp_path: Path):
    train = tmp_path / "train.jsonl"
    _write_jsonl(
        train,
        [{"text": "advise one", "intent": "advise", "split": "test"}],
    )

    try:
        SemanticRouter(
            embedder=_FakeEmbedder(),
            train_path=train,
            cache_path=tmp_path / "index.npz",
        )
    except ValueError as exc:
        assert "expected exactly" in str(exc)
    else:
        raise AssertionError("router accepted fields outside the train contract")
