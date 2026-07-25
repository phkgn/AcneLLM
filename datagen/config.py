"""Single source of configuration for the ROLE datagen pipeline.

Only this module reads process environment variables.  The tiny ``.env``
loader mirrors ``LLMData.chunk_qa.config`` and deliberately adds no dependency.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATAGEN_DIR = Path(__file__).resolve().parent
FULL_TARGET = 3500

CASE_TYPE_TARGETS: dict[str, int] = {
    "R1": 250,
    "R2": 450,
    "R3": 350,
    "R4": 300,
    "R5": 300,
    "R6": 250,
    "R7": 200,
    "R8": 150,
    "R9": 250,
    "B1": 500,
    "B2": 200,
    "B3": 150,
    "B4": 80,
    "B5": 70,
}
CASE_TYPE_RATIOS: dict[str, float] = {
    case_id: count / FULL_TARGET for case_id, count in CASE_TYPE_TARGETS.items()
}
assert sum(CASE_TYPE_TARGETS.values()) == FULL_TARGET
assert abs(sum(CASE_TYPE_RATIOS.values()) - 1.0) < 1e-12


def compute_budget(total: int) -> dict[str, int]:
    """Convert taxonomy fractions to integer quotas using largest remainders."""
    if total < 0:
        raise ValueError("total phải >= 0")
    exact = {case_id: ratio * total for case_id, ratio in CASE_TYPE_RATIOS.items()}
    budget = {case_id: int(value) for case_id, value in exact.items()}
    remainder = total - sum(budget.values())
    order = sorted(
        exact,
        key=lambda case_id: (exact[case_id] - budget[case_id], CASE_TYPE_RATIOS[case_id]),
        reverse=True,
    )
    for case_id in order[:remainder]:
        budget[case_id] += 1
    return budget


def _load_dotenv_if_present() -> None:
    """Load simple KEY=VALUE lines from project ``.env`` if not already set."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _float_env(name: str, default: float) -> float:
    raw = _env(name)
    return default if raw is None else float(raw)


_load_dotenv_if_present()


@dataclass
class Config:
    project_root: Path = PROJECT_ROOT
    datagen_dir: Path = DATAGEN_DIR
    taxonomy_path: Path = field(default_factory=lambda: DATAGEN_DIR / "role_taxonomy.yaml")
    style_guide_path: Path = field(default_factory=lambda: DATAGEN_DIR / "role_style_guide.md")
    output_dir: Path = field(default_factory=lambda: DATAGEN_DIR / "output" / "v4_role")
    output_jsonl: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / "v4_role.train.jsonl"
    )
    rejected_jsonl: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / "rejected.audit.jsonl"
    )
    summary_json: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / "generation_summary.json"
    )
    checkpoint_json: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / "limit_checkpoint.json"
    )
    smoke_review_path: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / "SMOKE_REVIEW_V2.md"
    )
    log_dir: Path = field(default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / "logs")
    lock_path: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / ".generator.lock"
    )
    prompt_template_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "config" / "prompts" / "stream_user.j2"
    )
    model_file_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "model" / "V2" / "Q4" / "Modelfile"
    )
    evaluation_dataset_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / "evaluation" / "datasets" / "v1"
    )
    contamination_cache: Path = field(
        default_factory=lambda: DATAGEN_DIR / "output" / "v4_role" / ".v1_8gram.sqlite3"
    )

    api_key: str | None = field(default_factory=lambda: _env("DATAGEN_API_KEY"))
    base_url: str = field(
        default_factory=lambda: _env("DATAGEN_BASE_URL", "https://api.tokenrouter.com/v1") or ""
    )
    model: str = field(
        default_factory=lambda: _env("DATAGEN_MODEL", "z-ai/glm-5.2-free") or ""
    )
    thinking: str = "disabled"
    timeout_s: float = field(default_factory=lambda: _float_env("DATAGEN_TIMEOUT_SECONDS", 900.0))
    max_retries: int = 6
    max_content_attempts: int = 4
    max_output_tokens: int = 16000
    concurrency: int = 3
    batch_size: int = 6
    max_cost_usd: float = 25.0
    input_price_per_million: float = field(
        default_factory=lambda: _float_env("DATAGEN_INPUT_PRICE_PER_MILLION", 0.0)
    )
    output_price_per_million: float = field(
        default_factory=lambda: _float_env("DATAGEN_OUTPUT_PRICE_PER_MILLION", 0.0)
    )

    embedding_model: str = field(
        default_factory=lambda: _env("DATAGEN_EMBEDDING_MODEL", "AITeamVN/Vietnamese_Embedding") or ""
    )
    embedding_device: str = field(default_factory=lambda: _env("DEVICE", "cpu") or "cpu")
    phrase_ngram_size: int = 8
    phrase_max_occurrences: int = 5
    progress_every: int = 10
    topup_max_iters: int = 100

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.api_key:
            problems.append("Thiếu DATAGEN_API_KEY trong .env")
        for label, path in (
            ("taxonomy", self.taxonomy_path),
            ("style guide", self.style_guide_path),
            ("stream_user.j2", self.prompt_template_path),
            ("SYSTEM Modelfile", self.model_file_path),
            ("evaluation v1", self.evaluation_dataset_dir),
        ):
            if not path.exists():
                problems.append(f"Không đọc được {label}: {path}")
        if self.thinking != "disabled":
            problems.append("Datagen production bắt buộc thinking=disabled")
        if self.max_cost_usd <= 0:
            problems.append("max_cost_usd phải > 0")
        return problems
