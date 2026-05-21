"""BM25 sparse index with persistence."""
from __future__ import annotations
import hashlib
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi

try:
    from underthesea import word_tokenize as _vi_word_tokenize
except Exception:
    _vi_word_tokenize = None


def tokenize_vi(text: str) -> list[str]:
    if _vi_word_tokenize is not None:
        try:
            return _vi_word_tokenize(text.lower())
        except Exception:
            pass
    return text.lower().split()


class BM25ChecksumError(RuntimeError):
    """Raised when a persisted BM25 pickle cannot be verified."""


def _checksum_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BM25Index:
    def __init__(self):
        self.bm25: BM25Okapi | None = None
        self.chunk_ids: list[str] = []
        self.texts: list[str] = []

    def build(self, chunk_ids: list[str], texts: list[str]) -> None:
        self.chunk_ids = list(chunk_ids)
        self.texts = list(texts)
        tokenized = [tokenize_vi(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized)

    def query(self, query: str, top_k: int = 40) -> list[tuple[str, float]]:
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(tokenize_vi(query))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self.chunk_ids[i], float(s)) for i, s in ranked if s > 0]

    def save(self, path: str) -> None:
        index_path = Path(path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "chunk_ids": self.chunk_ids, "texts": self.texts}, f)
        _checksum_path(index_path).write_text(_sha256_file(index_path), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "BM25Index":
        index_path = Path(path)
        checksum_path = _checksum_path(index_path)
        if not checksum_path.exists():
            raise BM25ChecksumError(
                f"BM25 checksum file is missing: {checksum_path}. Rebuild BM25 before loading."
            )
        expected = checksum_path.read_text(encoding="utf-8").strip().split()[0]
        actual = _sha256_file(index_path)
        if expected != actual:
            raise BM25ChecksumError(
                f"BM25 checksum mismatch for {index_path}. Rebuild BM25 before loading."
            )
        self = cls()
        with open(index_path, "rb") as f:
            d = pickle.load(f)
        self.bm25 = d["bm25"]
        self.chunk_ids = d["chunk_ids"]
        self.texts = d["texts"]
        return self
