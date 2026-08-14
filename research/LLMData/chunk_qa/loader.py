"""Load and filter chunks from data/raw/chunks.jsonl.

Filter priorities for the clinical chat-response dataset:

1. Language must be in `cfg.chunk_languages` (default: vi + en).
2. Chunk text must contain at least one acne-related keyword.
3. Length >= `cfg.chunk_min_text_len`.
4. Sources matching `chunk_demoted_source_tokens` (product reviews, spa
   marketing, ...) are skipped entirely.
5. Sources matching `chunk_preferred_source_tokens` (guidelines, hospitals,
   PubMed, AAD, NICE, ...) are yielded FIRST. Other eligible chunks come after.

Public API:
    iter_filtered_chunks(cfg, processed_chunk_ids=None) -> Iterator[dict]
    count_eligible(cfg) -> int
    load_processed_chunk_ids(output_path) -> set[str]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator, Set, Union

from .config import Config

logger = logging.getLogger(__name__)


def _source_tokens(chunk: dict) -> list[str]:
    """Lower-case tokens drawn from source_name + tags + categories."""
    tokens: list[str] = []
    sn = (chunk.get("source_name") or "").lower()
    if sn:
        tokens.append(sn)
        tokens.extend(re_tok for re_tok in sn.replace("_", "-").split("-") if re_tok)
    for key in ("tags", "categories"):
        for v in chunk.get(key) or []:
            v = str(v).lower()
            if v:
                tokens.append(v)
    return tokens


def _is_demoted(chunk: dict, cfg: Config) -> bool:
    if not cfg.chunk_demoted_source_tokens:
        return False
    toks = " ".join(_source_tokens(chunk))
    return any(t.lower() in toks for t in cfg.chunk_demoted_source_tokens)


def _is_preferred(chunk: dict, cfg: Config) -> bool:
    if not cfg.chunk_preferred_source_tokens:
        return False
    if (chunk.get("trust_level") or "").lower() == "high":
        return True
    toks = " ".join(_source_tokens(chunk))
    return any(t.lower() in toks for t in cfg.chunk_preferred_source_tokens)


def _authority_score(chunk: dict) -> int:
    """Small deterministic score used to prioritize guideline/high-trust chunks."""
    score = 0
    trust = (chunk.get("trust_level") or "").lower()
    if trust == "high":
        score += 3
    elif trust == "medium":
        score += 1
    tokens = set(_source_tokens(chunk))
    if {"guidelines", "guideline", "high-trust"} & tokens:
        score += 2
    if any(token in " ".join(tokens) for token in ("nice", "aad", "pubmed", "hospital")):
        score += 1
    return score


def _is_eligible(chunk: dict, cfg: Config) -> bool:
    lang = (chunk.get("language") or "").lower()
    if cfg.chunk_languages and lang not in cfg.chunk_languages:
        return False
    text = chunk.get("text") or ""
    if len(text) < cfg.chunk_min_text_len:
        return False
    if cfg.chunk_acne_keywords:
        text_lower = text.lower()
        if not any(kw.lower() in text_lower for kw in cfg.chunk_acne_keywords):
            return False
    if not chunk.get("chunk_id"):
        return False
    if _is_demoted(chunk, cfg):
        return False
    return True


def iter_filtered_chunks(
    cfg: Config,
    processed_chunk_ids: Set[str] | None = None,
) -> Iterator[dict]:
    """Yield eligible chunks in priority order: preferred first, others after."""
    if processed_chunk_ids is None:
        processed_chunk_ids = set()

    path: Path = cfg.chunks_jsonl
    if not path.exists():
        raise FileNotFoundError(f"chunks file not found: {path}")

    seen = 0
    pref_yielded = 0
    other_yielded = 0
    skipped_processed = 0
    deferred: list[dict] = []

    # First pass: yield preferred eligible chunks immediately, defer others.
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            seen += 1
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Bad JSON on line %d of %s: %s", line_no, path.name, e)
                continue
            if not _is_eligible(chunk, cfg):
                continue
            if chunk["chunk_id"] in processed_chunk_ids:
                skipped_processed += 1
                continue
            if _is_preferred(chunk, cfg):
                pref_yielded += 1
                yield chunk
            else:
                deferred.append(chunk)

    for chunk in deferred:
        other_yielded += 1
        yield chunk

    logger.info(
        "Loader done: seen=%d, preferred=%d, other=%d, skipped_already_processed=%d",
        seen, pref_yielded, other_yielded, skipped_processed,
    )


def count_eligible(cfg: Config) -> int:
    n = 0
    for _ in iter_filtered_chunks(cfg, processed_chunk_ids=set()):
        n += 1
    return n


def load_processed_chunk_ids(output_path: Union[Path, str]) -> Set[str]:
    """Scan an existing output JSONL to collect chunk_ids already processed."""
    ids: Set[str] = set()
    p = Path(output_path)
    if not p.exists():
        return ids
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = (obj.get("metadata") or {}).get("source_chunk_id")
            if cid:
                ids.add(cid)
    return ids
