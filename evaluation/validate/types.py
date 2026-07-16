from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

CheckStatus = Literal["PASS", "FAIL", "WARN", "SKIPPED"]


@dataclass(slots=True)
class CheckResult:
    name: str
    status: CheckStatus
    evidence: list[dict[str, Any]] = field(default_factory=list)
    critical: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "evidence": self.evidence,
            "critical": self.critical,
        }


@dataclass(slots=True)
class ValidationContext:
    root: Path
    run_dir: Path
    dataset_path: Path
    output_dir: Path
    experiment: dict[str, Any]
    system_configs: dict[str, dict[str, Any]]
    system_config_paths: dict[str, Path]
    gate: dict[str, Any]
    run_meta: dict[str, Any]
    report: dict[str, Any]
    dataset_rows: list[dict[str, Any]]
    records: dict[str, list[dict[str, Any]]]
    judged: dict[str, list[dict[str, Any]]]

    @property
    def tier(self) -> str:
        return str(self.experiment.get("tier") or "t3").lower()

    @property
    def dataset_ids(self) -> set[str]:
        return {
            str(row["sample_id"])
            for row in self.dataset_rows
            if row.get("sample_id") is not None
        }
