"""Vietnamese-aware recursive chunker."""
from __future__ import annotations
from loguru import logger

try:
    from underthesea import sent_tokenize as _vi_sent_tokenize
except Exception:
    _vi_sent_tokenize = None


def _sent_tokenize(text: str) -> list[str]:
    if _vi_sent_tokenize is not None:
        try:
            return _vi_sent_tokenize(text)
        except Exception:
            pass
    # fallback: split on ".!?"
    import re
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


class VietnameseChunker:
    """Approximate token counting via whitespace split (fast, no model dep).
    For precise BGE tokenization use the `transformers`-backed variant if needed.
    """

    def __init__(self, chunk_size: int = 200, overlap: int = 40, min_size: int = 50):
        # chunk_size measured in whitespace-tokens (roughly 1 token ~= 1 Vietnamese word)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_size = min_size

    @staticmethod
    def _tok_len(text: str) -> int:
        return len(text.split())

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        buf: list[str] = []
        buf_len = 0

        def flush():
            nonlocal buf, buf_len
            if buf_len >= self.min_size:
                chunks.append(" ".join(buf).strip())
            buf, buf_len = [], 0

        for para in paragraphs:
            sentences = _sent_tokenize(para)
            for sent in sentences:
                slen = self._tok_len(sent)
                if slen == 0:
                    continue
                if buf_len + slen > self.chunk_size and buf:
                    chunks.append(" ".join(buf).strip())
                    # overlap tail
                    ob, ol = [], 0
                    for s in reversed(buf):
                        sl = self._tok_len(s)
                        if ol + sl > self.overlap:
                            break
                        ob.insert(0, s)
                        ol += sl
                    buf = ob
                    buf_len = ol
                buf.append(sent)
                buf_len += slen
            # soft boundary at paragraph end
            if buf_len > self.chunk_size * 0.75:
                flush()

        if buf_len >= self.min_size:
            chunks.append(" ".join(buf).strip())
        return chunks
