"""Vietnamese-aware recursive chunker voi dedup va micro-chunk filtering."""
from __future__ import annotations
import hashlib
import re
from loguru import logger

try:
    from underthesea import sent_tokenize as _vi_sent_tokenize
except Exception:
    _vi_sent_tokenize = None

_HEADING_RE = re.compile(
    r"^(#{1,4}\s+.+|[A-ZÀÁẢÃẠĂẶÂẦẤĐÊÔƠƯ][^.!?\n]{3,60}:?\s*)$",
    re.MULTILINE,
)

_FOOTER_PATTERNS: list = [re.compile(p, re.IGNORECASE) for p in [
    r"bình luận\s*\(\)",
    r"lựa chọn dịch vụ",
    r"quý khách hàng vui lòng",
    r"để đặt lịch",
    r"\bhotline\b",
    r"tải app",
    r"\bfacebook\b",
    r"\bzalo\b",
    r"bài viết liên quan",
    r"xem thêm",
    r"có thể bạn quan tâm",
    r"đặt hẹn online",
    r"liên hệ ngay",
    r"tư vấn miễn phí",
    r"nhắn tin zalo",
    r"follow us",
    r"share this",
    r"newsletter",
    r"subscribe",
    r"sign\s*up",
    r"\blog\s*in\b",
    r"\bcookies?\b",
    r"cookie policy",
    r"privacy policy",
    r"terms (?:of use|and conditions|& conditions)",
    r"advertisement",
    r"sponsored",
    r"related articles?",
    r"recommended articles?",
    r"all rights reserved",
    r"©\s*\d{4}",
]]
_FOOTER_THRESHOLD_SHORT = 1
_FOOTER_THRESHOLD_LONG  = 3

_FOOD_DOMAIN_RE = re.compile(
    r"trứng cá (hồi|tầm|muối|chiên|sốt|sashimi|caviar)|"
    r"cháo trứng cá|"
    r"món (ăn|ngon).*trứng cá|"
    r"trứng cá.*nấu|"
    r"(phi lê|cá hồi|cá tầm).*trứng",
    re.IGNORECASE,
)

_NEAR_DUP_SHINGLE_N = 4
_NEAR_DUP_THRESHOLD = 0.90


def _shingle_set(text: str, n: int = _NEAR_DUP_SHINGLE_N) -> set:
    norm = re.sub(r"\s+", " ", text.lower().strip())
    return {norm[i:i + n] for i in range(len(norm) - n + 1)}


def _jaccard(s1: set, s2: set) -> float:
    if not s1 or not s2:
        return 0.0
    inter = len(s1 & s2)
    union = len(s1 | s2)
    return inter / union if union else 0.0


def _is_footer_chunk(text: str, word_count: int) -> bool:
    matches = sum(1 for p in _FOOTER_PATTERNS if p.search(text))
    if word_count < 120:
        return matches >= _FOOTER_THRESHOLD_SHORT
    return matches >= _FOOTER_THRESHOLD_LONG


def _is_food_domain(text: str) -> bool:
    return bool(_FOOD_DOMAIN_RE.search(text))


def _sent_tokenize(text: str) -> list:
    if _vi_sent_tokenize is not None:
        try:
            return _vi_sent_tokenize(text)
        except Exception:
            pass
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 120:
        return False
    if re.search(r"[.!?]\s", stripped):
        return False
    return bool(_HEADING_RE.match(stripped))


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class VietnameseChunker:
    def __init__(self, chunk_size=200, overlap=40, min_size=50, dedup=True):
        self.chunk_size = chunk_size
        self.overlap    = overlap
        self.min_size   = min_size
        self.dedup      = dedup

    @staticmethod
    def _tok_len(text: str) -> int:
        return len(text.split())

    def chunk(self, text: str) -> list:
        if not text or not text.strip():
            return []

        raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        paragraphs = []
        pending_heading = ""
        for para in raw_paras:
            if _is_heading(para):
                if pending_heading:
                    paragraphs.append(pending_heading)
                pending_heading = para
            else:
                if pending_heading:
                    para = pending_heading + "\n" + para
                    pending_heading = ""
                paragraphs.append(para)
        if pending_heading:
            paragraphs.append(pending_heading)

        chunks = []
        seen_hashes = set()
        seen_shingles = []

        def _emit(candidate: str) -> None:
            """Validate and register a candidate chunk string."""
            wc = self._tok_len(candidate)
            if wc < self.min_size:
                return
            if _is_footer_chunk(candidate, wc):
                logger.debug(f"[chunker] footer-drop: {candidate[:60]!r}")
                return
            if _is_food_domain(candidate):
                logger.debug(f"[chunker] food-domain-drop: {candidate[:60]!r}")
                return
            if self.dedup:
                h = _content_hash(candidate)
                if h in seen_hashes:
                    logger.debug(f"[chunker] exact-dedup: {candidate[:60]!r}")
                    return
                cand_sh = _shingle_set(candidate)
                for prev_sh in seen_shingles:
                    if _jaccard(cand_sh, prev_sh) >= _NEAR_DUP_THRESHOLD:
                        logger.debug(f"[chunker] near-dedup: {candidate[:60]!r}")
                        return
                seen_hashes.add(h)
                seen_shingles.append(cand_sh)
            chunks.append(candidate)

        for para in paragraphs:
            sentences = _sent_tokenize(para)
            buf: list[str] = []
            buf_len = 0

            for sent in sentences:
                slen = self._tok_len(sent)
                if slen == 0:
                    continue

                # Very long sentence: split by words directly
                if slen > self.chunk_size * 1.5:
                    if buf:
                        _emit(" ".join(buf).strip())
                        buf, buf_len = [], 0
                    words = sent.split()
                    for i in range(0, len(words), self.chunk_size):
                        sub = " ".join(words[i:i + self.chunk_size])
                        _emit(sub)
                    continue

                # Normal sentence: flush when buf would overflow
                if buf_len + slen > self.chunk_size and buf:
                    # Save overlap tail BEFORE flushing
                    ob, ol = [], 0
                    for s in reversed(buf):
                        sl = self._tok_len(s)
                        if ol + sl > self.overlap:
                            break
                        ob.insert(0, s)
                        ol += sl
                    _emit(" ".join(buf).strip())
                    buf     = ob
                    buf_len = ol

                buf.append(sent)
                buf_len += slen

            # End of paragraph: always flush remaining buf
            # (do NOT carry buf across paragraph boundary)
            if buf:
                _emit(" ".join(buf).strip())

        return chunks

    def chunk_with_stats(self, text: str) -> tuple:
        before     = self.dedup
        self.dedup = False
        raw        = self.chunk(text)
        self.dedup = before
        self.dedup = True
        deduped    = self.chunk(text)
        stats = {
            "raw_count":          len(raw),
            "deduped_count":      len(deduped),
            "duplicates_removed": len(raw) - len(deduped),
            "avg_tokens":         sum(self._tok_len(c) for c in deduped) / len(deduped) if deduped else 0,
            "min_tokens":         min((self._tok_len(c) for c in deduped), default=0),
            "max_tokens":         max((self._tok_len(c) for c in deduped), default=0),
        }
        return deduped, stats
