"""Load and enforce the canonical AcneLLM SYSTEM anchor."""
from __future__ import annotations

import hashlib
import re

from .config import Config

_SYSTEM_RE = re.compile(r'\bSYSTEM\s+"""(.*?)"""', re.DOTALL)


def load_anchor(cfg: Config) -> str:
    source = cfg.anchor_path.read_text(encoding="utf-8-sig")
    match = _SYSTEM_RE.search(source)
    if not match:
        raise ValueError(f'Cannot find SYSTEM """...""" in {cfg.anchor_path}')
    return match.group(1)


def assert_parity(cfg: Config) -> str:
    anchor = load_anchor(cfg)
    canonical = cfg.canonical_path.read_text(encoding="utf-8-sig").strip()
    if anchor != canonical:
        raise ValueError(
            "Anchor parity failure: model/Modelfile SYSTEM is not byte-identical "
            "to model/system_prompt.canonical.txt after canonical outer trim."
        )
    return anchor


def anchor_sha256(anchor: str) -> str:
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()
