"""Near-duplicate detection via MinHash LSH.

Hai che do:
- dedup_documents(): batch dedup cuoi pipeline (giu tuong thich cu)
- OnlineDedup: streaming dedup -- check + insert tung doc khi crawl, khong can toan bo
  corpus trong RAM. Chi luu MinHash signatures (~5 MB / 10k docs).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path


# --- helpers ------------------------------------------------------------------

def _shingles(text: str, k: int = 5) -> set:
    tokens = text.lower().split()
    return {" ".join(tokens[i:i + k]) for i in range(max(len(tokens) - k + 1, 0))}


def _minhash(text: str, num_perm: int = 128):
    from datasketch import MinHash
    m = MinHash(num_perm=num_perm)
    for sh in _shingles(text):
        m.update(sh.encode("utf-8"))
    return m


# --- Batch dedup (backward-compatible) ----------------------------------------

def dedup_documents(
    docs: list,
    threshold: float = 0.85,
    text_key: str = "text",
    id_key: str = "doc_id",
) -> list:
    """Batch near-duplicate filter. Giu nguyen de dung trong cac pipeline khac."""
    from datasketch import MinHashLSH
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    kept = []
    for d in docs:
        mh = _minhash(d[text_key])
        if lsh.query(mh):
            continue
        lsh.insert(d[id_key], mh)
        kept.append(d)
    return kept


# --- Online / Streaming dedup --------------------------------------------------

class OnlineDedup:
    """Streaming near-duplicate filter dung MinHash LSH.

    Asyncio-safe (single-threaded event loop).
    Lock chi dung cho LSH vi datasketch khong thread-safe.

    Cach dung:
        dedup = OnlineDedup()
        dedup.load_from_jsonl(Path("data/raw/documents.jsonl"))

        if await dedup.add_if_new(doc.doc_id, doc.text):
            # doc moi -- ghi file ngay
            ...
    """

    def __init__(self, threshold: float = 0.88, num_perm: int = 128):
        from datasketch import MinHashLSH
        self._threshold = threshold
        self._num_perm = num_perm
        self._lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._seen_ids: set = set()
        self._lock = asyncio.Lock()

    async def add_if_new(self, doc_id: str, text: str) -> bool:
        """Tra ve True va insert neu doc chua tung gap (khong phai near-duplicate).

        Goi truoc khi ghi doc ra file. Safe voi nhieu coroutine goi dong thoi.
        """
        # exact-id check truoc (no lock can -- set access atomic trong asyncio)
        if doc_id in self._seen_ids:
            return False

        mh = _minhash(text, self._num_perm)

        async with self._lock:
            # Re-check sau khi co lock (tranh race giua check va insert)
            if doc_id in self._seen_ids:
                return False
            if self._lsh.query(mh):
                return False
            self._lsh.insert(doc_id, mh)
            self._seen_ids.add(doc_id)
            return True

    def load_from_jsonl(self, path: Path) -> int:
        """Rebuild LSH index tu JSONL file da co (dung khi resume).

        Synchronous -- goi truoc khi bat dau asyncio event loop.
        Tra ve so docs da load.
        """
        if not path.exists():
            return 0
        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    doc_id = d.get("doc_id", "")
                    text = d.get("text", "")
                    if not doc_id or not text:
                        continue
                    if doc_id in self._seen_ids:
                        continue
                    mh = _minhash(text, self._num_perm)
                    self._lsh.insert(doc_id, mh)
                    self._seen_ids.add(doc_id)
                    count += 1
                except Exception:
                    continue
        return count

    @property
    def seen_ids(self) -> set:
        return self._seen_ids

    def __len__(self) -> int:
        return len(self._seen_ids)

    def __contains__(self, doc_id: str) -> bool:
        return doc_id in self._seen_ids
