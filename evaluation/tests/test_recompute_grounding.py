from evaluation.analysis.recompute_grounding import reconstruct_contexts


def test_reconstruct_contexts_copies_record_and_uses_only_known_chunks() -> None:
    original = {
        "used_chunks": ["c1", "missing"],
        "trace": {"existing": True},
    }

    rebuilt = reconstruct_contexts(original, {"c1": "context one"})

    assert original["trace"] == {"existing": True}
    assert rebuilt["trace"] == {
        "existing": True,
        "context_chunks": [{"chunk_id": "c1", "text": "context one"}],
    }
