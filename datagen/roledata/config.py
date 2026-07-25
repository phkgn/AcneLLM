"""Single-source configuration for the independent roledata pipeline.

Only this module reads process environment variables or the project ``.env``.
Secrets are never logged or copied into generated records.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = Path(__file__).resolve().parent
FULL_TARGET = 3_500

CASE_TYPE_TARGETS: dict[str, int] = {
    "R1_identity": 200,
    "R2_depth_adaptation": 340,
    "R3_nonjudgment": 270,
    "R4_measured_empathy": 220,
    "R5_natural_clarification": 220,
    "R6_role_boundary": 250,
    "R7_conversation_glue": 150,
    "R8_meta_jailbreak": 150,
    "R9_multiturn": 200,
    "R10_special_population": 150,
    "B1_grounded_role": 380,
    "B2_missing_answer": 200,
    "B3_irrelevant_chunk": 130,
    "B4_conflicting_docs": 70,
    "B5_depth_anchor": 70,
    "K1_knowledge_anchor": 500,
}

if sum(CASE_TYPE_TARGETS.values()) != FULL_TARGET:  # pragma: no cover - import invariant
    raise RuntimeError("CASE_TYPE_TARGETS must sum to FULL_TARGET")


def _read_dotenv(path: Path) -> dict[str, str]:
    """Parse the tiny subset of dotenv syntax needed by this pipeline."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _environment(project_root: Path) -> Mapping[str, str]:
    merged = _read_dotenv(project_root / ".env")
    merged.update(os.environ)
    return merged


def _env_float(values: Mapping[str, str], name: str, default: float) -> float:
    raw = values.get(name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def compute_budget(total: int) -> dict[str, int]:
    """Scale the 3,500-case taxonomy via deterministic largest remainder."""
    if total < 0:
        raise ValueError("total must be non-negative")
    if total == 0:
        return {case: 0 for case in CASE_TYPE_TARGETS}

    exact = {
        case: total * target / FULL_TARGET for case, target in CASE_TYPE_TARGETS.items()
    }
    budget = {case: int(value) for case, value in exact.items()}
    remaining = total - sum(budget.values())
    order = {case: index for index, case in enumerate(CASE_TYPE_TARGETS)}
    ranked = sorted(
        CASE_TYPE_TARGETS,
        key=lambda case: (-(exact[case] - budget[case]), order[case]),
    )
    for case in ranked[:remaining]:
        budget[case] += 1
    return budget


@dataclass(slots=True)
class Config:
    project_root: Path = PROJECT_ROOT
    module_root: Path = MODULE_ROOT

    anchor_path: Path | None = None
    canonical_path: Path | None = None
    taxonomy_path: Path | None = None
    style_guide_path: Path | None = None
    output_dir: Path | None = None
    knowledge_source_dir: Path | None = None
    knowledge_chunks_path: Path | None = None
    evaluation_datasets_dir: Path | None = None

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    thinking: str = "disabled"
    concurrency: int = 12
    batch_size: int = 6
    max_cost_usd: float = 25.0
    max_output_tokens: int = 1_200
    request_timeout_s: float = 120.0
    max_api_retries: int = 5
    max_content_attempts: int = 4
    progress_every: int = 1
    # Gate lặp cụm để NHẸ: chỉ bắt lặp nguyên văn dài, không giết boilerplate ngắn.
    # 14-gram + trần 8 ⇒ chỉ chặn khi ~14 từ liên tiếp lặp >8 lần toàn corpus.
    phrase_ngram_size: int = 14
    phrase_max_occurrences: int = 8
    # Đa dạng do prompt điều khiển: temperature cao hơn để giảm hội tụ khuôn mẫu.
    temperature: float = 0.9
    seed: int = 42
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None

    _env_values: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        root = Path(self.project_root).resolve()
        module = Path(self.module_root).resolve()
        self.project_root = root
        self.module_root = module
        self.anchor_path = Path(self.anchor_path or root / "model" / "Modelfile")
        self.canonical_path = Path(
            self.canonical_path or root / "model" / "system_prompt.canonical.txt"
        )
        self.taxonomy_path = Path(self.taxonomy_path or module / "taxonomy.yaml")
        self.style_guide_path = Path(self.style_guide_path or module / "style_guide.md")
        self.output_dir = Path(self.output_dir or module / "output")
        # PLAN names LLMData/chunk_qa as the knowledge source. That package's
        # source-of-truth corpus is data/raw/chunks.jsonl; both are validated.
        self.knowledge_source_dir = Path(
            self.knowledge_source_dir or root / "LLMData" / "chunk_qa"
        )
        self.knowledge_chunks_path = Path(
            self.knowledge_chunks_path or root / "data" / "raw" / "chunks.jsonl"
        )
        self.evaluation_datasets_dir = Path(
            self.evaluation_datasets_dir or root / "evaluation" / "datasets"
        )

        values = dict(self._env_values or _environment(root))
        self._env_values = values
        self.api_key = self.api_key if self.api_key is not None else values.get("OPENAI_API_KEY")
        self.base_url = self.base_url or values.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        self.model = self.model or values.get("OPENAI_MODEL", "gpt-4o-mini")
        if self.input_price_per_million is None:
            self.input_price_per_million = _env_float(
                values, "OPENAI_INPUT_PRICE_PER_MILLION", 0.15
            )
        if self.output_price_per_million is None:
            self.output_price_per_million = _env_float(
                values, "OPENAI_OUTPUT_PRICE_PER_MILLION", 0.60
            )

    @property
    def train_path(self) -> Path:
        return self.output_dir / "roledata.train.jsonl"

    @property
    def smoke_path(self) -> Path:
        return self.output_dir / "roledata.smoke.jsonl"

    @property
    def rejected_path(self) -> Path:
        return self.output_dir / "rejected.audit.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.output_dir / "generation_summary.json"

    @property
    def checkpoint_path(self) -> Path:
        return self.output_dir / "limit_checkpoint.json"

    @property
    def log_path(self) -> Path:
        return self.output_dir / "logs" / "roledata.log"

    @property
    def splits_dir(self) -> Path:
        return self.output_dir / "splits"

    @property
    def train_split_path(self) -> Path:
        return self.splits_dir / "train.jsonl"

    @property
    def val_split_path(self) -> Path:
        return self.splits_dir / "val.jsonl"

    @property
    def holdout_split_path(self) -> Path:
        return self.splits_dir / "holdout.jsonl"

    @property
    def export_dir(self) -> Path:
        return self.output_dir / "export"

    @property
    def export_path(self) -> Path:
        return self.export_dir / "acnellm_role_lora.jsonl"

    @property
    def dataset_info_path(self) -> Path:
        return self.export_dir / "dataset_info.json"

    @property
    def dataset_card_path(self) -> Path:
        return self.output_dir / "dataset_card.md"

    @property
    def checksum_path(self) -> Path:
        return self.output_dir / "checksum.sha256"

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.api_key:
            problems.append(
                "OPENAI_API_KEY is missing; set it in the project .env or process environment."
            )
        for label, path in (
            ("anchor", self.anchor_path),
            ("canonical anchor", self.canonical_path),
            ("taxonomy", self.taxonomy_path),
            ("style guide", self.style_guide_path),
            ("knowledge source directory", self.knowledge_source_dir),
            ("knowledge chunks", self.knowledge_chunks_path),
        ):
            if not path.exists():
                problems.append(f"Missing {label}: {path}")
        if self.thinking != "disabled":
            problems.append("thinking must be exactly 'disabled'.")
        if self.max_cost_usd <= 0:
            problems.append("max_cost_usd must be greater than zero.")
        if self.concurrency <= 0:
            problems.append("concurrency must be greater than zero.")
        if self.progress_every <= 0:
            problems.append("progress_every must be greater than zero.")
        return problems
