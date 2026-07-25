"""Canonical system-prompt loading and byte-parity enforcement."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from .config import Config


def load_anchor(cfg: Config) -> str:
    """Load the canonical prompt without normalizing its bytes."""
    raw = cfg.canonical_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    anchor = raw.decode("utf-8")
    if not anchor:
        raise ValueError(f"Canonical system prompt is empty: {cfg.canonical_path}")
    return anchor


def assert_parity(
    cfg: Config, records: Iterable[dict[str, Any]] | None = None
) -> str:
    """Return the anchor and fail if any supplied record differs by one byte."""
    anchor = load_anchor(cfg)
    for index, record in enumerate(records or (), start=1):
        messages = record.get("messages")
        if (
            not isinstance(messages, list)
            or not messages
            or not isinstance(messages[0], dict)
            or messages[0].get("role") != "system"
            or messages[0].get("content") != anchor
        ):
            raise ValueError(
                f"System prompt parity failure at record {index}: "
                "messages[0].content is not byte-identical to the canonical anchor."
            )
    return anchor


def anchor_sha256(anchor_or_cfg: str | Config) -> str:
    anchor = load_anchor(anchor_or_cfg) if isinstance(anchor_or_cfg, Config) else anchor_or_cfg
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()
