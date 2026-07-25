"""Embedding-based Out-of-Domain (OOD) detector cho AcneLLM.

Thay vì chỉ dùng keyword list (có thể miss câu hỏi rất ngắn / biến thể lạ),
OOD detector embed query rồi so sánh cosine similarity với centroid của
"acne domain" đã pre-computed từ finetune dataset câu hỏi.

Pipeline:
1. Lúc init: load centroid từ file (nếu có) hoặc compute từ seed queries.
2. Lúc runtime: embed query → cosine_sim(query, centroid).
3. Nếu sim < ood_threshold → out-of-domain → trigger scope refusal.

Thiết kế fall-back an toàn:
- Nếu embedder chưa load (cold start / lỗi) → skip OOD check, để keyword
  guardrail xử lý (không block sai).
- Threshold mặc định 0.25 — conservative để tránh false positive trên câu
  hỏi da liễu ngắn.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import numpy as np
from loguru import logger


# ─── PII patterns ──────────────────────────────────────────────────────────
# Các mẫu PII cần mask trước khi log / lưu vào DB.
# KHÔNG dùng để từ chối câu hỏi — chỉ mask trong log.

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # CMND / CCCD: 9 hoặc 12 chữ số
    (re.compile(r"\b\d{9}\b|\b\d{12}\b"), "[ID_MASKED]"),
    # Số điện thoại VN: 03x, 07x, 08x, 09x, 0[2-9]x (10 số) hoặc +84...
    (re.compile(r"\b(?:\+84|0)(?:[3-9]\d{8}|[1-9]\d{8})\b"), "[PHONE_MASKED]"),
    # Email
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[EMAIL_MASKED]"),
    # Địa chỉ: số nhà + tên đường (heuristic)
    (re.compile(
        r"\b\d{1,4}[/\-]?\d{0,4}\s+"
        r"(?:đường|phố|ngõ|hẻm|quận|phường|xã|huyện|tỉnh|tp\.?|thành phố)\b",
        re.IGNORECASE | re.UNICODE,
    ), "[ADDRESS_MASKED]"),
    # Số tài khoản ngân hàng (12–19 chữ số liên tiếp)
    (re.compile(r"\b\d{12,19}\b"), "[ACCOUNT_MASKED]"),
]


def mask_pii(text: str) -> str:
    """Trả về text đã mask PII. Dùng khi ghi log, KHÔNG dùng để từ chối."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def contains_pii(text: str) -> bool:
    """Kiểm tra nhanh text có PII không (để log cảnh báo)."""
    return any(p.search(text) for p, _ in _PII_PATTERNS)


# ─── OOD Detector ──────────────────────────────────────────────────────────

# Seed queries đại diện "acne domain" — dùng để build centroid khi không
# có file centroid sẵn.
_ACNE_SEED_QUERIES: list[str] = [
    # ── Câu hỏi dài về acne (domain anchors) ──────────────────────────────────
    "mụn trứng cá nguyên nhân và cách điều trị",
    "mụn viêm ở mặt làm sao hết",
    "benzoyl peroxide trị mụn hiệu quả không",
    "isotretinoin có an toàn không",
    "salicylic acid bha cho da mụn",
    "retinol adapalene khác nhau thế nào",
    "mụn bọc mụn nang điều trị",
    "thâm sau mụn làm mờ như thế nào",
    "sẹo rỗ sau mụn có chữa được không",
    "da nhờn dễ bị mụn hơn không",
    "kem chống nắng cho da mụn chọn loại nào",
    "chế độ ăn ảnh hưởng đến mụn",
    "mụn nội tiết ở phụ nữ xử lý thế nào",
    "niacinamide azelaic acid tốt cho da mụn",
    "mụn mủ viêm ở lưng điều trị",
    "có bầu bị mụn dùng thuốc gì an toàn",
    "acne vulgaris treatment options",
    "hormonal acne chin jawline causes",
    "cystic nodular acne medication",
    "post inflammatory hyperpigmentation treatment",
    # ── Câu follow-up ngắn điển hình trong session acne ───────────────────────
    # Những câu này không có acne keyword nên OOD dễ nhầm → cần đưa vào centroid.
    "còn gì nữa không",
    "có cách nào khác không",
    "vậy thì sao",
    "tiếp theo là gì",
    "sao vậy",
    "bao lâu thì thấy hiệu quả",
    "còn phương pháp nào khác",
    "oke hiểu rồi vậy làm sao",
    "mụn lưng tôi bị vậy",
    "da mình như vậy thì sao",
    "dùng bao lâu",
    "có hiệu quả không",
    "thế còn ban ngày thì sao",
    "còn ban đêm dùng gì",
]


class OodDetector:
    """Embedding-based OOD detector với lazy centroid computation."""

    def __init__(
        self,
        embedder=None,
        centroid_path: str | None = None,
        ood_threshold: float = 0.25,
        seed_queries: list[str] | None = None,
    ):
        self.embedder = embedder
        self.centroid_path = Path(centroid_path) if centroid_path else None
        self.ood_threshold = ood_threshold
        self.seed_queries = seed_queries or _ACNE_SEED_QUERIES
        self._centroid: np.ndarray | None = None
        self._ready = False

        if embedder is not None:
            self._init_centroid()

    # ─── Public API ───────────────────────────────────────────────────────

    def is_out_of_domain(self, query: str) -> bool:
        """True nếu query nằm ngoài acne domain.

        Returns False (không block) khi:
        - embedder chưa sẵn sàng (fail-safe)
        - similarity không tính được
        """
        if not self._ready or self._centroid is None or self.embedder is None:
            return False  # fail-open: để keyword guardrail xử lý
        try:
            q_emb = np.asarray(
                self.embedder.embed_query(query),
                dtype=np.float32,
            ).reshape(-1)
            if not self._centroid_matches(q_emb):
                return False
            sim = float(np.dot(q_emb, self._centroid))
            logger.debug(f"[OOD] query_sim={sim:.3f} threshold={self.ood_threshold}")
            return sim < self.ood_threshold
        except Exception as e:
            logger.warning(f"[OOD] embed error, skipping: {e}")
            return False  # fail-open

    def similarity(self, query: str) -> float | None:
        """Trả cosine similarity của query với centroid. None nếu chưa ready."""
        if not self._ready or self._centroid is None or self.embedder is None:
            return None
        try:
            q_emb = np.asarray(
                self.embedder.embed_query(query),
                dtype=np.float32,
            ).reshape(-1)
            if not self._centroid_matches(q_emb):
                return None
            return float(np.dot(q_emb, self._centroid))
        except Exception:
            return None

    def rebuild_centroid(self, queries: list[str]) -> None:
        """Re-compute centroid từ danh sách queries mới (dùng khi có thêm data)."""
        if self.embedder is None:
            logger.warning("[OOD] No embedder, cannot rebuild centroid")
            return
        try:
            embs = self.embedder.embed_passages(queries)
            centroid = embs.mean(axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            self._centroid = centroid.astype(np.float32)
            self._ready = True
            if self.centroid_path:
                self._save_centroid()
            logger.info(f"[OOD] Rebuilt centroid from {len(queries)} queries")
        except Exception as e:
            logger.error(f"[OOD] Failed to rebuild centroid: {e}")

    # ─── Internal ─────────────────────────────────────────────────────────

    def _init_centroid(self) -> None:
        """Load centroid từ file hoặc compute từ seed queries."""
        if self.centroid_path and self.centroid_path.exists():
            try:
                data = json.loads(self.centroid_path.read_text())
                self._centroid = np.array(data["centroid"], dtype=np.float32)
                expected_dim = getattr(self.embedder, "dim", None)
                if expected_dim is not None and len(self._centroid) != expected_dim:
                    raise ValueError(
                        f"centroid dim={len(self._centroid)} but "
                        f"embedder dim={expected_dim}"
                    )
                self._ready = True
                logger.info(
                    f"[OOD] Loaded centroid from {self.centroid_path} "
                    f"(dim={len(self._centroid)})"
                )
                return
            except Exception as e:
                logger.warning(f"[OOD] Failed to load centroid file: {e}, recomputing")

        # Compute từ seed queries
        self.rebuild_centroid(self.seed_queries)

    def _centroid_matches(self, q_emb: np.ndarray) -> bool:
        """Return False and disable OOD when the cached centroid is stale."""
        if self._centroid is None:
            return False
        if q_emb.shape[0] == self._centroid.shape[0]:
            return True
        logger.warning(
            f"[OOD] centroid dim mismatch: query={q_emb.shape[0]} "
            f"centroid={self._centroid.shape[0]}; skipping OOD check"
        )
        self._ready = False
        return False

    def _save_centroid(self) -> None:
        if self.centroid_path is None or self._centroid is None:
            return
        try:
            self.centroid_path.parent.mkdir(parents=True, exist_ok=True)
            self.centroid_path.write_text(
                json.dumps({"centroid": self._centroid.tolist()})
            )
            logger.info(f"[OOD] Saved centroid to {self.centroid_path}")
        except Exception as e:
            logger.warning(f"[OOD] Failed to save centroid: {e}")
