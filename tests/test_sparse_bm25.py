import pickle

import pytest

from acne_llm.rag.sparse import BM25ChecksumError, BM25Index


def test_bm25_save_writes_checksum_and_loads(tmp_path):
    path = tmp_path / "bm25.pkl"
    index = BM25Index()
    index.build(["c1", "c2"], ["mụn viêm ở cằm", "mụn đầu đen vùng mũi"])

    index.save(str(path))
    loaded = BM25Index.load(str(path))

    assert (tmp_path / "bm25.pkl.sha256").exists()
    assert loaded.chunk_ids == ["c1", "c2"]
    assert loaded.bm25 is not None


def test_bm25_load_rejects_checksum_mismatch_before_pickle(tmp_path, monkeypatch):
    path = tmp_path / "bm25.pkl"
    index = BM25Index()
    index.build(["c1"], ["mụn viêm"])
    index.save(str(path))
    (tmp_path / "bm25.pkl.sha256").write_text("bad", encoding="utf-8")

    def fail_pickle_load(_file):
        raise AssertionError("pickle.load should not be called on checksum mismatch")

    monkeypatch.setattr(pickle, "load", fail_pickle_load)

    with pytest.raises(BM25ChecksumError):
        BM25Index.load(str(path))
