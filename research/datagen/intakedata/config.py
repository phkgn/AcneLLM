"""Configuration for the isolated Unified Intake datagen pipeline."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = Path(__file__).resolve().parent

FULL_TARGET = 4_000

CASE_TYPE_TARGETS: dict[str, int] = {
    "advise_selfreport_simple": 500,
    "advise_selfreport_rich": 450,
    "advise_negation_stopped": 350,
    "advise_duration_convert": 200,
    "advise_noaccent": 250,
    "advise_mixed_vi_en": 100,
    "advise_ambiguous_lowconf": 150,
    "knowledge_product_trap": 300,
    "knowledge_general": 300,
    "knowledge_ingredient_compare": 200,
    "clarify_vague": 300,
    "clarify_followup_multiturn": 200,
    "reject_jailbreak_meta": 150,
    "reject_ood": 200,
    "reject_unsafe_rx": 150,
    "glue_greeting_thanks": 200,
}

if sum(CASE_TYPE_TARGETS.values()) != FULL_TARGET:  # pragma: no cover
    raise RuntimeError("CASE_TYPE_TARGETS must sum to FULL_TARGET")


def _read_dotenv(path: Path) -> dict[str, str]:
    """Parse the small dotenv subset needed here without adding a dependency."""
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
    values = _read_dotenv(project_root / ".env")
    values.update(os.environ)
    return values


def _env_int(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(values.get(name, "") or default)
    except ValueError:
        return default


def _env_float(values: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(values.get(name, "") or default)
    except ValueError:
        return default


def compute_budget(total: int) -> dict[str, int]:
    """Scale the taxonomy with deterministic largest-remainder allocation."""
    if isinstance(total, bool) or not isinstance(total, int):
        raise TypeError("total must be an integer")
    if total < 0:
        raise ValueError("total must be non-negative")
    if total == 0:
        return {case: 0 for case in CASE_TYPE_TARGETS}

    exact = {
        case: total * target / FULL_TARGET
        for case, target in CASE_TYPE_TARGETS.items()
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
    canonical_path: Path | None = None
    taxonomy_path: Path | None = None
    golden_path: Path | None = None
    evaluation_paths: tuple[Path, ...] | None = None
    output_root: Path | None = None

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    concurrency: int | None = None
    max_output_tokens: int | None = None
    request_timeout_s: float | None = None
    max_api_retries: int | None = None
    max_content_attempts: int | None = None
    max_topup_rounds: int | None = None
    progress_every: int | None = None
    temperature: float | None = None
    seed: int = 42

    _env_values: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root).resolve()
        self.module_root = Path(self.module_root).resolve()
        self.canonical_path = Path(
            self.canonical_path or self.module_root / "system_prompt.canonical.txt"
        )
        self.taxonomy_path = Path(self.taxonomy_path or self.module_root / "taxonomy.yaml")
        self.golden_path = Path(
            self.golden_path or self.project_root / "data" / "golden_extraction_gen.jsonl"
        )
        if self.evaluation_paths is None:
            self.evaluation_paths = (
                self.project_root / "data" / "intent_classify.test.jsonl",
                self.project_root / "evaluation" / "datasets",
            )
        else:
            self.evaluation_paths = tuple(Path(path) for path in self.evaluation_paths)
        self.output_root = Path(self.output_root or self.module_root / "output")

        values = dict(self._env_values or _environment(self.project_root))
        self._env_values = values
        if self.api_key is None:
            self.api_key = values.get("OPENAI_API_KEY")
        self.base_url = self.base_url or values.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        self.model = self.model or values.get("OPENAI_MODEL", "gpt-4o-mini")
        if self.concurrency is None:
            self.concurrency = _env_int(values, "INTAKEDATA_CONCURRENCY", 6)
        if self.max_output_tokens is None:
            self.max_output_tokens = _env_int(values, "INTAKEDATA_MAX_OUTPUT_TOKENS", 1_600)
        if self.request_timeout_s is None:
            self.request_timeout_s = _env_float(
                values, "INTAKEDATA_REQUEST_TIMEOUT_S", 120.0
            )
        if self.max_api_retries is None:
            self.max_api_retries = _env_int(values, "INTAKEDATA_MAX_API_RETRIES", 4)
        if self.max_content_attempts is None:
            self.max_content_attempts = _env_int(
                values, "INTAKEDATA_MAX_CONTENT_ATTEMPTS", 4
            )
        if self.max_topup_rounds is None:
            self.max_topup_rounds = _env_int(
                values, "INTAKEDATA_MAX_TOPUP_ROUNDS", 2
            )
        if self.progress_every is None:
            self.progress_every = _env_int(values, "INTAKEDATA_PROGRESS_EVERY", 1)
        if self.temperature is None:
            self.temperature = _env_float(values, "INTAKEDATA_TEMPERATURE", 0.75)

    @property
    def intake_dir(self) -> Path:
        return self.output_root / "intake"

    @property
    def audit_path(self) -> Path:
        return self.intake_dir / "audit.jsonl"

    @property
    def train_path(self) -> Path:
        return self.intake_dir / "intake.train.jsonl"

    @property
    def val_path(self) -> Path:
        return self.intake_dir / "intake.val.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.intake_dir / "summary.json"

    @property
    def log_path(self) -> Path:
        return self.output_root / "logs" / "intake.log"

    def records_path(self, mode: str, limit: int | None = None) -> Path:
        if mode == "smoke":
            return self.intake_dir / "intake.smoke.jsonl"
        if mode == "limit":
            if limit is None or limit <= 0:
                raise ValueError("limit mode requires a positive limit")
            return self.intake_dir / f"intake.limit-{limit}.jsonl"
        if mode == "full":
            return self.intake_dir / "intake.records.jsonl"
        raise ValueError(f"Unknown mode: {mode}")

    def validate(self, *, require_api_key: bool = True) -> list[str]:
        problems: list[str] = []
        if require_api_key and not self.api_key:
            problems.append(
                "OPENAI_API_KEY is missing; set it in the project .env or process environment."
            )
        for label, path in (
            ("canonical system prompt", self.canonical_path),
            ("taxonomy", self.taxonomy_path),
            ("golden seed corpus", self.golden_path),
        ):
            if not path.is_file():
                problems.append(f"Missing {label}: {path}")
        for label, value in (
            ("concurrency", self.concurrency),
            ("max_output_tokens", self.max_output_tokens),
            ("max_api_retries", self.max_api_retries),
            ("max_content_attempts", self.max_content_attempts),
            ("max_topup_rounds", self.max_topup_rounds),
            ("progress_every", self.progress_every),
        ):
            if value is None or value <= 0:
                problems.append(f"{label} must be greater than zero.")
        if self.request_timeout_s is None or self.request_timeout_s <= 0:
            problems.append("request_timeout_s must be greater than zero.")
        if self.temperature is None or not 0 <= self.temperature <= 2:
            problems.append("temperature must be in [0,2].")
        return problems
