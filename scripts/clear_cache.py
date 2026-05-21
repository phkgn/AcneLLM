"""Xoa disk cache -- goi sau khi rebuild KB de dam bao retrieval cache khong stale.

Usage:
    python scripts/clear_cache.py            # xoa retrieval cache (giu embed cache)
    python scripts/clear_cache.py --all      # xoa toan bo (embed + retrieval)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from acne_llm.config import settings
from acne_llm.cache import init_cache, invalidate_retrieve_cache, clear_all_caches

cache_dir = getattr(settings, "cache_dir", "./data/cache")
cache_size = getattr(settings, "cache_size_gb", 2.0)

if cache_size <= 0:
    print("Cache disabled (CACHE_SIZE_GB=0). Nothing to clear.")
    sys.exit(0)

init_cache(cache_dir, size_limit_gb=cache_size)

if "--all" in sys.argv:
    clear_all_caches()
    print("Cleared ALL cache entries (embed + retrieval).")
else:
    n = invalidate_retrieve_cache()
    print(f"Cleared retrieval cache ({n} entries). Embed cache preserved.")
