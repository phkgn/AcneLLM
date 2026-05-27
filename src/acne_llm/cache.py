"""DiskCache layer cho AcneLLM.

Cache 2 tang:
  - embed_query: vinh vien theo (text, model_name) -- vector khong doi tru khi doi model
  - retrieve_for_chat: TTL 1 gio -- fresh khi KB update

Tat ca fallback silent neu cache gap loi (disk full, permission...).
"""
from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

_cache: Optional[Any] = None   # diskcache.Cache instance


def init_cache(cache_dir: str, size_limit_gb: float = 2.0) -> None:
    """Khoi tao DiskCache singleton. Goi trong build_container()."""
    global _cache
    try:
        import diskcache
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        _cache = diskcache.Cache(
            directory=cache_dir,
            size_limit=int(size_limit_gb * 1024 ** 3),
            eviction_policy="least-recently-used",
        )
        logger.info(f"[Cache] DiskCache @ {cache_dir} ({size_limit_gb:.1f}GB limit)")
    except Exception as e:
        logger.warning(f"[Cache] DiskCache init failed ({e}), caching disabled")
        _cache = None


def get_cache():
    return _cache


def _make_key(*parts) -> str:
    raw = json.dumps(parts, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Embed cache ───────────────────────────────────────────────────────────────

EMBED_TAG = "embed_v1"


def cached_embed_query(
    embedder,
    query: str,
) -> Any:
    """Tra ve embedding vector tu cache neu co, else goi embedder._embed_query_raw()."""
    cache = get_cache()
    if cache is None:
        return embedder._embed_query_raw(query)

    key = _make_key(EMBED_TAG, embedder.model_name, query)
    try:
        hit = cache.get(key, default=None)
        if hit is not None:
            return pickle.loads(hit)
    except Exception as e:
        logger.debug(f"[Cache] embed read error: {e}")

    # Goi _embed_query_raw de tranh de quy (embed_query -> cached_embed_query -> embed_query)
    vec = embedder._embed_query_raw(query)
    try:
        cache.set(key, pickle.dumps(vec))   # no TTL -- embed is deterministic
    except Exception as e:
        logger.debug(f"[Cache] embed write error: {e}")
    return vec


# ── Retrieval cache ───────────────────────────────────────────────────────────

RETRIEVE_TTL = 3600   # 1 gio
RETRIEVE_TAG = "retrieve_v1"

# Removed: shadow index (_RETRIEVE_INDEX_KEY) — đã thay bằng diskcache tag.
# Mỗi entry được gán tag=RETRIEVE_TAG khi set; invalidate dùng cache.evict(tag).
# Lợi ích: không còn disk read+write set cho mỗi cache miss.


def cached_retrieve(
    fn: Callable,
    cache_key_parts: tuple,
) -> Any:
    """Wrap mot retrieval call voi cache TTL 1 gio.

    fn phai la callable khong nhan tham so (dung closure de capture args).

    Usage:
        def _do():
            return retrieve_for_chat(c, user, clinical_plan)
        result = cached_retrieve(_do, (query, top_k, rerank_top_k, min_score))
    """
    cache = get_cache()
    if cache is None:
        return fn()

    key = _make_key(RETRIEVE_TAG, *cache_key_parts)
    try:
        hit = cache.get(key, default=None)
        if hit is not None:
            logger.debug("[Cache] retrieve HIT")
            return pickle.loads(hit)
    except Exception as e:
        logger.debug(f"[Cache] retrieve read error: {e}")

    result = fn()
    try:
        # Tag-based: diskcache.Cache.set hỗ trợ tag= để group invalidation.
        # cache.evict(RETRIEVE_TAG) xóa toàn bộ group mà không cần shadow index.
        cache.set(key, pickle.dumps(result), expire=RETRIEVE_TTL, tag=RETRIEVE_TAG)
        logger.debug("[Cache] retrieve MISS -> stored")
    except Exception as e:
        logger.debug(f"[Cache] retrieve write error: {e}")
    return result


def invalidate_retrieve_cache() -> int:
    """Xoa toan bo retrieve cache (goi sau khi rebuild KB).
    Tra ve so entry da xoa.

    Dung diskcache tag-based eviction — nhanh hon shadow index (khong R/W set).
    """
    cache = get_cache()
    if cache is None:
        return 0
    try:
        deleted = cache.evict(RETRIEVE_TAG)
        logger.info(f"[Cache] Invalidated {deleted} retrieve entries (tag={RETRIEVE_TAG})")
        return deleted
    except Exception as e:
        logger.warning(f"[Cache] invalidate error: {e}")
        return 0


def clear_all_caches() -> None:
    """Xoa toan bo cache (embed + retrieve). Dung khi doi model."""
    cache = get_cache()
    if cache is None:
        return
    try:
        cache.clear()
        logger.info("[Cache] All caches cleared")
    except Exception as e:
        logger.warning(f"[Cache] clear error: {e}")
