"""Inline citation compatibility helpers.

The production default does not expose numeric ``[N]`` markers.  Source cards
still travel through their independent SSE ``citation`` events.  ``model`` mode
keeps the historical prompt/output contract for rollback experiments.
"""
from __future__ import annotations

import re
from typing import Any


_INLINE_CITATION_RE = re.compile(r"\[\s*\d{1,3}\s*\]")
_POSSIBLE_PREFIX_RE = re.compile(r"\[\s*\d{0,3}\s*$")


def strip_inline_citations(text: str) -> str:
    """Remove only bracketed numeric markers; preserve numbers and named tags."""
    return _INLINE_CITATION_RE.sub("", text or "")


def strip_inline_citations_value(value: Any) -> Any:
    """Recursively clean structured model output without changing its shape."""
    if isinstance(value, str):
        return strip_inline_citations(value)
    if isinstance(value, list):
        return [strip_inline_citations_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(strip_inline_citations_value(item) for item in value)
    if isinstance(value, dict):
        return {
            key: strip_inline_citations_value(item) for key, item in value.items()
        }
    return value


class InlineCitationStripper:
    """Stateful numeric marker stripper safe for arbitrary stream token splits."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        data = self._pending + (text or "")
        self._pending = ""
        output: list[str] = []
        cursor = 0

        while cursor < len(data):
            start = data.find("[", cursor)
            if start < 0:
                output.append(data[cursor:])
                break
            output.append(data[cursor:start])
            end = data.find("]", start + 1)
            if end < 0:
                suffix = data[start:]
                if _POSSIBLE_PREFIX_RE.fullmatch(suffix):
                    self._pending = suffix
                else:
                    output.append(suffix)
                break

            candidate = data[start:end + 1]
            if not _INLINE_CITATION_RE.fullmatch(candidate):
                output.append(candidate)
            cursor = end + 1

        return "".join(output)

    def finish(self) -> str:
        pending, self._pending = self._pending, ""
        return pending
