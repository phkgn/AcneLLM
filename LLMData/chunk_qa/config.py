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

# ---------------------------------------------------------------------------
# Target distribution — expressed as fractions that sum to 1.0.
# The actual per-case-type quota is computed at runtime by multiplying these
# fractions by the total number of clinical samples written (i.e. it scales
# automatically with however many chunks are available).
# Safety/OOD samples are generated separately by safety_cases.py.
# ---------------------------------------------------------------------------
CASE_TYPE_RATIOS: dict[str, float] = {
    "mild_comedonal":                      0.18,   # 18%
    "moderate_inflammatory":               0.12,   # 12%
    "when_to_see_doctor":                  0.10,   # 10%
    "skincare_routine":                    0.08,   # 8%
    "severe_nodular_scarring":             0.08,   # 8%
    "antibiotic_or_isotretinoin_boundary": 0.08,   # 8%
    "insufficient_info":                   0.08,   # 8%
    "product_qna":                         0.05,   # 5%
    "pregnancy_breastfeeding_safety":      0.05,   # 5%
    "teen_acne":                           0.05,   # 5%
    "diet_lifestyle":                      0.05,   # 5%
    "post_acne_care":                      0.05,   # 5%
    "skincare_irritation":                 0.03,   # 3%
}
# tổng = 0.18+0.12+0.10+0.08*4+0.05*5+0.03 = 1.00
# Sanity-check: ratios should sum to ~1.0 (within floating-point tolerance).
assert abs(sum(CASE_TYPE_RATIOS.values()) - 1.0) < 0.01, (
    f"CASE_TYPE_RATIOS must sum to 1.0, got {sum(CASE_TYPE_RATIOS.values()):.4f}"
)


def compute_budget(total_clinical_target: int) -> dict[str, int]:
    """Convert CASE_TYPE_RATIOS into absolute quotas given a total target.

    The quotas are integer-rounded; any rounding remainder is added to the
    largest bucket (mild_comedonal) so the sum equals total_clinical_target.
    """
    budget = {k: int(v * total_clinical_target) for k, v in CASE_TYPE_RATIOS.items()}
    remainder = total_clinical_target - sum(budget.values())
    if remainder:
        largest = max(budget, key=lambda k: budget[k])
        budget[largest] += remainder
    return budget


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
    cases_per_chunk: int = 1  # 20k run: 1 Q&A per chunk (was 3 for the 60k run)
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
