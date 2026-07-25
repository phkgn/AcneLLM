"""Probe the SemanticRouter with one Vietnamese utterance.

Builds the production embedding router exactly like ``di.build_container``
(cached ``.npz`` index, no rebuild unless the train split changed) and prints
exactly one JSON line on stdout with the full ``SemanticPrediction``
diagnostics plus the effective thresholds used.  Designed for the eval
dashboard "Router Probe" tab; errors are reported as ``{"error": ...}`` on
stdout with a non-zero exit code.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.common import ensure_repo_importable  # noqa: E402

ensure_repo_importable()

INTENTS = ("advise", "knowledge", "clarify", "reject")


def _build_router():
    """Mirror di.build_container (~lines 250-300) for the semantic router."""
    from acne_llm.config import settings
    from acne_llm.chat.fallback.semantic_router import SemanticRouter
    from acne_llm.rag.embedder import Embedder

    emb_model = settings.embedding_model
    embedder = Embedder(model_name=emb_model, device=settings.device)
    return SemanticRouter(
        embedder=embedder,
        train_path=getattr(
            settings,
            "semantic_router_train_path",
            "./data/intent_classify.train.jsonl",
        ),
        cache_path=getattr(
            settings,
            "semantic_router_cache_path",
            "./data/intent_router_index.npz",
        ),
        k=int(getattr(settings, "semantic_router_k", 9)),
        oos_distance_threshold=float(
            getattr(settings, "semantic_router_oos_distance_threshold", 0.483609)
        ),
        ambiguity_margin=float(
            getattr(settings, "semantic_router_ambiguity_margin", 0.08)
        ),
    )


def _read_train_texts(train_path: Path) -> list[str]:
    """Train texts in index order, mirroring SemanticRouter._read_train_rows."""
    texts: list[str] = []
    for line in train_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        texts.append(str(row["text"]).strip())
    return texts


def _label_fallback_neighbors(router, prediction) -> list[dict]:
    """First-unused-row-with-same-label mapping (no index info)."""
    rows: list[tuple[str, str]] = []
    for line in router.train_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append((str(row["text"]).strip(), str(row["intent"])))
    used: set[int] = set()
    neighbors: list[dict] = []
    for rank, (label, similarity) in enumerate(
        zip(prediction.neighbor_labels, prediction.neighbor_similarities), 1
    ):
        text = ""
        for candidate, (candidate_text, candidate_label) in enumerate(rows):
            if candidate in used or candidate_label != label:
                continue
            text = candidate_text
            used.add(candidate)
            break
        neighbors.append(
            {
                "rank": rank,
                "label": label,
                "similarity": round(float(similarity), 6),
                "text": text,
            }
        )
    return neighbors


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evaluation.probe.semantic_probe",
        description="Probe the SemanticRouter with one Vietnamese utterance.",
    )
    parser.add_argument(
        "--text", required=True, help="User utterance (Vietnamese, single line)"
    )
    parser.add_argument("--k", type=int, default=None, help="Override k (1-100)")
    parser.add_argument(
        "--oos",
        type=float,
        default=None,
        help="Override oos_distance_threshold (0-2)",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=None,
        help="Override ambiguity_margin (0-1)",
    )
    parser.add_argument("--expect", choices=INTENTS, default=None)
    parser.add_argument(
        "--neighbors",
        action="store_true",
        help="Include matched train sentences for each neighbor",
    )
    parser.add_argument("--json", action="store_true", help="Kept for CLI clarity")
    args = parser.parse_args(argv)

    try:
        text = args.text.strip()
        if not text:
            raise ValueError("--text phải là câu không rỗng")
        if len(text) > 2000:
            raise ValueError("--text quá dài (tối đa 2000 ký tự)")
        if args.k is not None and not 1 <= args.k <= 100:
            raise ValueError("--k phải nằm trong [1, 100]")
        if args.oos is not None and not 0.0 <= args.oos <= 2.0:
            raise ValueError("--oos phải nằm trong [0, 2]")
        if args.margin is not None and not 0.0 <= args.margin <= 1.0:
            raise ValueError("--margin phải nằm trong [0, 1]")

        router = _build_router()
        prediction = router.predict(
            text,
            k=args.k,
            oos_distance_threshold=args.oos,
            ambiguity_margin=args.margin,
        )

        effective_k = min(int(args.k or router.k), router.indexed_rows)
        effective_oos = (
            router.oos_distance_threshold if args.oos is None else float(args.oos)
        )
        effective_margin = (
            router.ambiguity_margin if args.margin is None else float(args.margin)
        )

        payload = dataclasses.asdict(prediction)
        payload["effective_k"] = effective_k
        payload["effective_oos_threshold"] = effective_oos
        payload["effective_margin"] = effective_margin
        payload["model_name"] = router.model_name
        payload["indexed_rows"] = router.indexed_rows
        payload["cache_hit"] = router.cache_hit
        payload["correct"] = (
            prediction.primary_intent == args.expect
            if args.expect is not None
            else None
        )
        if args.neighbors:
            if getattr(prediction, "neighbor_indices", None) is not None:
                payload["neighbors"] = _exact_neighbors(router, prediction)
            else:
                payload["neighbors"] = _label_fallback_neighbors(router, prediction)

        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - probe must report, not crash
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


def _exact_neighbors(router, prediction) -> list[dict]:
    """Index-exact mapping via SemanticPrediction.neighbor_indices."""
    train_texts = _read_train_texts(router.train_path)
    indices = prediction.neighbor_indices or ()
    neighbors: list[dict] = []
    for rank, (label, similarity) in enumerate(
        zip(prediction.neighbor_labels, prediction.neighbor_similarities), 1
    ):
        row_index = indices[rank - 1] if rank - 1 < len(indices) else None
        text = (
            train_texts[row_index]
            if row_index is not None and 0 <= row_index < len(train_texts)
            else ""
        )
        neighbors.append(
            {
                "rank": rank,
                "label": label,
                "similarity": round(float(similarity), 6),
                "text": text,
            }
        )
    return neighbors


if __name__ == "__main__":
    raise SystemExit(run())
