"""Local embedding kNN router for chat intent and soft OOS detection.

Only the stratified *train* split is indexed.  Embeddings are cached in a
plain NumPy archive keyed by the train-file hash and local embedder model so
startup does not repeatedly encode the dataset.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

from loguru import logger
import numpy as np

from .intent_router import PrimaryIntent, RouteDecision


InScopeIntent = Literal["advise", "knowledge", "clarify"]
_IN_SCOPE_INTENTS: tuple[InScopeIntent, ...] = (
    "advise",
    "knowledge",
    "clarify",
)
_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SemanticPrediction:
    """Full classifier diagnostics used by calibration/evaluation."""

    primary_intent: PrimaryIntent
    nearest_similarity: float
    nearest_distance: float
    vote_scores: dict[str, float]
    vote_margin: float
    neighbor_labels: tuple[str, ...]
    neighbor_similarities: tuple[float, ...]
    ambiguity_reason: str | None = None
    neighbor_indices: tuple[int, ...] | None = None

    def route_decision(self) -> RouteDecision:
        """Map nearest cosine similarity into metadata, not a calibrated probability."""
        return RouteDecision(
            primary_intent=self.primary_intent,
            confidence=max(0.0, min(1.0, self.nearest_similarity)),
            source="semantic",
            reason_code="semantic_router",
            ambiguity_reason=self.ambiguity_reason,
        )


class SemanticRouter:
    """Cosine kNN over local sentence embeddings.

    Args:
        embedder: Repository-local ``rag.embedder.Embedder`` compatible object.
        train_path: JSONL containing only ``text`` and one of three in-scope
            ``intent`` labels.  No test/OOS rows are accepted.
        cache_path: NumPy archive for the train embeddings.
        k: Number of nearest train examples used for weighted voting.
        oos_distance_threshold: Reject before voting when nearest cosine
            distance is greater than this threshold.
        ambiguity_margin: Force ``clarify`` when the top two normalised vote
            scores are closer than this margin.
    """

    def __init__(
        self,
        *,
        embedder: Any,
        train_path: str | Path,
        cache_path: str | Path,
        k: int = 9,
        oos_distance_threshold: float = 0.483609,
        ambiguity_margin: float = 0.08,
        eager: bool = True,
    ) -> None:
        if embedder is None:
            raise ValueError("semantic router requires a local embedder")
        if k < 1:
            raise ValueError("k must be positive")
        if not 0.0 <= oos_distance_threshold <= 2.0:
            raise ValueError("oos_distance_threshold must be in [0, 2]")
        if not 0.0 <= ambiguity_margin <= 1.0:
            raise ValueError("ambiguity_margin must be in [0, 1]")
        self.embedder = embedder
        self.train_path = Path(train_path)
        self.cache_path = Path(cache_path)
        self.k = int(k)
        self.oos_distance_threshold = float(oos_distance_threshold)
        self.ambiguity_margin = float(ambiguity_margin)
        self._embeddings: np.ndarray | None = None
        self._labels: np.ndarray | None = None
        self._texts: tuple[str, ...] = ()
        self._train_sha256 = ""
        self._cache_hit = False
        if eager:
            self._ensure_index()

    @property
    def indexed_rows(self) -> int:
        self._ensure_index()
        assert self._labels is not None
        return int(self._labels.shape[0])

    @property
    def train_sha256(self) -> str:
        self._ensure_index()
        return self._train_sha256

    @property
    def cache_hit(self) -> bool:
        self._ensure_index()
        return self._cache_hit

    @property
    def model_name(self) -> str:
        return str(getattr(self.embedder, "model_name", type(self.embedder).__name__))

    def classify(self, text: str) -> RouteDecision:
        """Classify one clean user turn without any network dependency."""
        return self.predict(text).route_decision()

    def predict(
        self,
        text: str,
        *,
        k: int | None = None,
        oos_distance_threshold: float | None = None,
        ambiguity_margin: float | None = None,
    ) -> SemanticPrediction:
        """Return diagnostics, optionally overriding values during calibration."""
        self._ensure_index()
        if not isinstance(text, str) or not text.strip():
            raise ValueError("semantic router text must be non-empty")
        assert self._embeddings is not None
        assert self._labels is not None

        query = np.asarray(self.embedder.embed_query(text), dtype=np.float32).reshape(-1)
        if query.shape[0] != self._embeddings.shape[1]:
            raise ValueError(
                f"query embedding dim={query.shape[0]} does not match "
                f"index dim={self._embeddings.shape[1]}"
            )
        norm = float(np.linalg.norm(query))
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError("semantic router received an invalid query embedding")
        query = query / norm
        similarities = self._embeddings @ query
        if not np.all(np.isfinite(similarities)):
            raise ValueError("semantic router similarity contains non-finite values")

        nearest_index = int(np.argmax(similarities))
        nearest_similarity = float(similarities[nearest_index])
        nearest_distance = 1.0 - nearest_similarity
        threshold = (
            self.oos_distance_threshold
            if oos_distance_threshold is None
            else float(oos_distance_threshold)
        )

        neighbor_count = min(int(k or self.k), len(similarities))
        if neighbor_count < 1:
            raise ValueError("semantic router index is empty")
        # argpartition is O(n), then the tiny k slice is ordered for diagnostics.
        indices = np.argpartition(-similarities, neighbor_count - 1)[:neighbor_count]
        indices = indices[np.argsort(-similarities[indices])]
        neighbor_labels = tuple(str(self._labels[index]) for index in indices)
        neighbor_similarities = tuple(float(similarities[index]) for index in indices)
        neighbor_indices = tuple(int(index) for index in indices)

        if nearest_distance > threshold:
            return SemanticPrediction(
                primary_intent="reject",
                nearest_similarity=nearest_similarity,
                nearest_distance=nearest_distance,
                vote_scores={label: 0.0 for label in _IN_SCOPE_INTENTS},
                vote_margin=0.0,
                neighbor_labels=neighbor_labels,
                neighbor_similarities=neighbor_similarities,
                ambiguity_reason=(
                    f"oos_distance={nearest_distance:.6f}>"
                    f"threshold={threshold:.6f}"
                ),
                neighbor_indices=neighbor_indices,
            )

        raw_votes: dict[str, float] = defaultdict(float)
        for label, similarity in zip(neighbor_labels, neighbor_similarities):
            # Embeddings are cosine-normalised. Squaring positive similarity
            # gives close neighbors more influence without an extra model.
            raw_votes[label] += max(0.0, similarity) ** 2 + 1e-9
        total_vote = sum(raw_votes.values())
        vote_scores = {
            label: (raw_votes.get(label, 0.0) / total_vote if total_vote else 0.0)
            for label in _IN_SCOPE_INTENTS
        }
        ranked = sorted(
            vote_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )
        top_label, top_score = ranked[0]
        second_score = ranked[1][1]
        vote_margin = float(top_score - second_score)
        margin_threshold = (
            self.ambiguity_margin
            if ambiguity_margin is None
            else float(ambiguity_margin)
        )

        ambiguity_reason = None
        primary_intent: PrimaryIntent = top_label  # type: ignore[assignment]
        if top_label != "clarify" and vote_margin < margin_threshold:
            primary_intent = "clarify"
            ambiguity_reason = (
                f"vote_margin={vote_margin:.6f}<"
                f"threshold={margin_threshold:.6f};winner={top_label}"
            )
        return SemanticPrediction(
            primary_intent=primary_intent,
            nearest_similarity=nearest_similarity,
            nearest_distance=nearest_distance,
            vote_scores=vote_scores,
            vote_margin=vote_margin,
            neighbor_labels=neighbor_labels,
            neighbor_similarities=neighbor_similarities,
            ambiguity_reason=ambiguity_reason,
            neighbor_indices=neighbor_indices,
        )

    def _ensure_index(self) -> None:
        if self._embeddings is not None and self._labels is not None:
            return
        rows, train_sha = self._read_train_rows()
        cached = self._load_cache(train_sha)
        if cached is not None:
            embeddings, labels = cached
            self._cache_hit = True
            logger.info(
                "[semantic-router] cache hit: {} rows model={} path={}",
                len(labels),
                self.model_name,
                self.cache_path,
            )
        else:
            texts = [row["text"] for row in rows]
            labels = np.asarray([row["intent"] for row in rows], dtype="<U16")
            embeddings = np.asarray(
                self.embedder.embed_passages(texts),
                dtype=np.float32,
            )
            embeddings = self._validated_normalized_embeddings(
                embeddings,
                expected_rows=len(rows),
            )
            self._save_cache(
                embeddings=embeddings,
                labels=labels,
                train_sha=train_sha,
            )
            self._cache_hit = False
            logger.info(
                "[semantic-router] built index: {} rows dim={} model={} path={}",
                len(labels),
                embeddings.shape[1],
                self.model_name,
                self.cache_path,
            )
        self._embeddings = embeddings
        self._labels = labels
        self._texts = tuple(row["text"] for row in rows)
        self._train_sha256 = train_sha

    def _read_train_rows(self) -> tuple[list[dict[str, str]], str]:
        if not self.train_path.exists():
            raise FileNotFoundError(
                f"semantic router train split not found: {self.train_path}"
            )
        raw = self.train_path.read_bytes()
        train_sha = sha256(raw).hexdigest()
        rows: list[dict[str, str]] = []
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != {"text", "intent"}:
                raise ValueError(
                    f"{self.train_path}:{line_number}: expected exactly "
                    "{'text','intent'}"
                )
            text = row.get("text")
            label = row.get("intent")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"{self.train_path}:{line_number}: text must be non-empty"
                )
            if label not in _IN_SCOPE_INTENTS:
                raise ValueError(
                    f"{self.train_path}:{line_number}: invalid train intent={label!r}"
                )
            rows.append({"text": text.strip(), "intent": str(label)})
        if not rows:
            raise ValueError(f"semantic router train split is empty: {self.train_path}")
        return rows, train_sha

    def _load_cache(
        self,
        train_sha: str,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        if not self.cache_path.exists():
            return None
        try:
            with np.load(self.cache_path, allow_pickle=False) as archive:
                metadata_raw = str(archive["metadata_json"].reshape(-1)[0])
                metadata = json.loads(metadata_raw)
                if metadata != self._cache_metadata(train_sha):
                    logger.info("[semantic-router] cache metadata changed; rebuilding")
                    return None
                embeddings = self._validated_normalized_embeddings(
                    np.asarray(archive["embeddings"], dtype=np.float32),
                    expected_rows=int(metadata["rows"]),
                )
                labels = np.asarray(archive["labels"], dtype="<U16")
                if labels.shape != (embeddings.shape[0],):
                    raise ValueError("cached labels shape does not match embeddings")
                if any(str(label) not in _IN_SCOPE_INTENTS for label in labels):
                    raise ValueError("cached labels contain an invalid intent")
                return embeddings, labels
        except Exception as exc:
            logger.warning(
                "[semantic-router] invalid cache {}; rebuilding ({})",
                self.cache_path,
                exc,
            )
            return None

    def _cache_metadata(self, train_sha: str, rows: int | None = None) -> dict[str, Any]:
        return {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "train_path": str(self.train_path.resolve()),
            "train_sha256": train_sha,
            "model_name": self.model_name,
            "rows": int(rows if rows is not None else self._count_train_rows()),
        }

    def _count_train_rows(self) -> int:
        return sum(
            1
            for line in self.train_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    def _save_cache(
        self,
        *,
        embeddings: np.ndarray,
        labels: np.ndarray,
        train_sha: str,
    ) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = self._cache_metadata(train_sha, rows=len(labels))
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            np.savez_compressed(
                handle,
                embeddings=embeddings,
                labels=labels,
                metadata_json=np.asarray(
                    [json.dumps(metadata, ensure_ascii=False, sort_keys=True)]
                ),
            )
        temporary.replace(self.cache_path)

    @staticmethod
    def _validated_normalized_embeddings(
        embeddings: np.ndarray,
        *,
        expected_rows: int,
    ) -> np.ndarray:
        if embeddings.ndim != 2 or embeddings.shape[0] != expected_rows:
            raise ValueError(
                f"embedding matrix shape={embeddings.shape} does not match "
                f"expected rows={expected_rows}"
            )
        if embeddings.shape[1] < 1 or not np.all(np.isfinite(embeddings)):
            raise ValueError("embedding matrix is empty or non-finite")
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        if np.any(norms <= 0) or not np.all(np.isfinite(norms)):
            raise ValueError("embedding matrix contains a zero/invalid vector")
        return np.ascontiguousarray(embeddings / norms, dtype=np.float32)
