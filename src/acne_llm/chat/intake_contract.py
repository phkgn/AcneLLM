"""Shared failure contract for the single runtime intake adapter."""


class RouterFallback(Exception):
    """Signal that routing must continue with semantic, then rule fallback."""


class ExtractorFallback(Exception):
    """Signal that extraction must continue with the deterministic rule fallback."""
