"""AcneLLM clinical chat-response fine-tuning dataset factory.

Pipeline:
    chunks.jsonl -> patient case -> normalized_case -> final answer -> JSONL

See main.py for CLI entry point.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `acne_llm.*` importable when this package is run from the project root.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
