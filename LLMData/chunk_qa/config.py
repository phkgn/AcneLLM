"""Configuration for the clinical chat-response dataset pipeline.

Loads from environment (.env at project root) but exposes a single
`Config` dataclass so the rest of the modules don't import os/env directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _load_dotenv_if_present() -> None:
    """Tiny .env loader (no python-dotenv dep). Skips already-set vars."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


_load_dotenv_if_present()


@dataclass
class Config:
    # ---------- Paths ----------
    project_root: Path = PROJECT_ROOT
    chunks_jsonl: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "raw" / "chunks.jsonl"
    )
    output_jsonl: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "finetune" / "acne_chat_response.jsonl"
    )
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "logs")

    # ---------- DeepSeek (generator) ----------
    deepseek_api_key: str | None = field(
        default_factory=lambda: _env("DEEPSEEK_API_KEY")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(
        default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-chat")
    )
    deepseek_temperature: float = 0.6
    deepseek_max_retries: int = 6
    deepseek_timeout_s: int = 120

    # ---------- Generation ----------
    cases_per_chunk: int = 3
    concurrency: int = 10

    # ---------- Chunk filter ----------
    chunk_languages: List[str] = field(default_factory=lambda: ["vi", "en"])
    chunk_min_text_len: int = 200
    chunk_acne_keywords: List[str] = field(
        default_factory=lambda: [
            "mụn", "trứng cá", "acne", "comedone", "comedo",
            "sẩn", "nang lông", "tuyến bã", "viêm da",
            "isotretinoin", "retinoid", "tretinoin", "adapalene",
            "benzoyl peroxide", "salicylic", "azelaic",
            "da liễu", "pimple", "whitehead", "blackhead",
            "papule", "pustule", "nodule", "cyst",
        ]
    )
    # Source/tag tokens that boost a chunk to "preferred" (kept first).
    chunk_preferred_source_tokens: List[str] = field(
        default_factory=lambda: [
            "guideline", "guidelines", "hospital", "authoritative",
            "aad", "nice", "internal-guideline-memo", "pubmed",
            "dalieuhanoi", "medlatec", "youmed", "suckhoedoisong",
        ]
    )
    # Source tokens that suggest marketing/product content; deprioritized.
    chunk_demoted_source_tokens: List[str] = field(
        default_factory=lambda: [
            "review", "spa", "clinic-marketing", "product-review",
            "promo", "ads",
        ]
    )

    # ---------- Sample mix ----------
    safety_mix_ratio: float = 0.15

    # ---------- Backward-compat aliases ----------
    @property
    def qa_per_chunk(self) -> int:
        """Alias kept so older CLI invocations (`--qa-per-chunk`) keep working."""
        return self.cases_per_chunk

    @qa_per_chunk.setter
    def qa_per_chunk(self, value: int) -> None:
        self.cases_per_chunk = value

    def validate(self) -> List[str]:
        problems: List[str] = []
        if not self.deepseek_api_key:
            problems.append(
                "DEEPSEEK_API_KEY is not set (export it or put it in .env)."
            )
        if not self.chunks_jsonl.exists():
            problems.append(f"Chunks file not found: {self.chunks_jsonl}")
        return problems


config = Config()
