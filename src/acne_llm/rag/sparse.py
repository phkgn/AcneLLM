"""BM25 sparse index with persistence, Vietnamese stopwords, score normalization."""
from __future__ import annotations
import hashlib
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi

try:
    from underthesea import word_tokenize as _vi_word_tokenize
except Exception:
    _vi_word_tokenize = None

# Stopword tiếng Việt — function words không mang nghĩa y khoa
_VI_STOPWORDS: frozenset[str] = frozenset({
    "và", "của", "là", "có", "trong", "được", "với", "các", "những",
    "này", "đó", "một", "để", "cho", "từ", "như", "khi", "nếu",
    "thì", "cũng", "về", "vào", "ra", "đã", "sẽ", "đang", "bị",
    "tại", "trên", "dưới", "sau", "trước", "không", "mà", "hay",
    "hoặc", "nhưng", "tuy", "vì", "do", "nên", "theo", "qua",
    "lại", "còn", "đều", "rất", "quá", "hơn", "nhất", "thêm",
    "chỉ", "cần", "phải", "bằng", "cách", "giữa",
    "tất", "cả", "mọi", "ai", "gì", "nào", "đây", "đấy",
    "i", "ii", "iii", "iv", "v", "a", "b", "c",
})


def tokenize_vi(text: str, remove_stopwords: bool = True) -> list[str]:
    """Tokenize tiếng Việt, tùy chọn loại stopword.

    Với BM25 medical domain: loại stopword giúp tập trung vào thuật ngữ y khoa.
    """
    if _vi_word_tokenize is not None:
        try:
            tokens = _vi_word_tokenize(text.lower())
        except Exception:
            tokens = text.lower().split()
    else:
        tokens = text.lower().split()

    if remove_stopwords:
        tokens = [t for t in tokens if t not in _VI_STOPWORDS and len(t) > 1]
    return tokens


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
        tokenized = [tokenize_vi(t, remove_stopwords=True) for t in texts]
        self.bm25 = BM25Okapi(tokenized)

    def query(self, query: str, top_k: int = 40, normalize: bool = True) -> list[tuple[str, float]]:
        """Query BM25 với optional score normalization.

        normalize=True: chia score cho max_score → [0, 1].
        Giúp BM25 và dense score có cùng scale trong RRF fusion.
        """
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(tokenize_vi(query))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        hits = [(self.chunk_ids[i], float(s)) for i, s in ranked if s > 0]
        if normalize and hits:
            max_score = max(s for _, s in hits)
            if max_score > 0:
                hits = [(cid, s / max_score) for cid, s in hits]
        return hits

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
                f"BM25 checksum file missing: {checksum_path}. Rebuild BM25 before loading."
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
