from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.common import EVAL_DIR, ROOT, load_yaml, read_jsonl
from evaluation.validate.types import CheckResult, ValidationContext


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _experiment_from_artifacts(run_dir: Path, run_meta: dict[str, Any]) -> dict[str, Any]:
    embedded = run_meta.get("experiment")
    if isinstance(embedded, dict):
        return embedded
    override = run_dir / "_experiment_override.yaml"
    if override.exists():
        return load_yaml(override) or {}
    candidate = EVAL_DIR / "configs" / "experiments" / f"{run_dir.name}.yaml"
    if candidate.exists():
        return load_yaml(candidate) or {}
    return {}


def load_context(
    run_dir_value: str | Path,
    dataset_value: str | Path,
    output_dir: Path,
) -> tuple[ValidationContext, CheckResult]:
    run_dir = resolve_repo_path(run_dir_value)
    dataset_path = resolve_repo_path(dataset_value)
    problems: list[dict[str, Any]] = []

    if not run_dir.is_dir():
        problems.append({
            "message": "Run directory does not exist.",
            "file": str(run_dir),
        })
    if not dataset_path.is_file():
        problems.append({
            "message": "Dataset file does not exist.",
            "file": str(dataset_path),
        })
    if problems:
        empty = ValidationContext(
            root=ROOT,
            run_dir=run_dir,
            dataset_path=dataset_path,
            output_dir=output_dir,
            experiment={},
            system_configs={},
            system_config_paths={},
            gate={},
            run_meta={},
            report={},
            dataset_rows=[],
            records={},
            judged={},
        )
        return empty, CheckResult(
            "load_config", "FAIL", problems, critical=True
        )

    run_meta = _read_json(run_dir / "run_meta.json")
    experiment = _experiment_from_artifacts(run_dir, run_meta)
    gate_path = EVAL_DIR / "configs" / "gate.yaml"
    gate = load_yaml(gate_path) if gate_path.exists() else {}

    system_configs: dict[str, dict[str, Any]] = {}
    system_config_paths: dict[str, Path] = {}
    for raw_path in experiment.get("systems") or []:
        cfg_path = resolve_repo_path(str(raw_path))
        if not cfg_path.exists():
            problems.append({
                "message": "System config referenced by experiment is missing.",
                "file": str(cfg_path),
            })
            continue
        cfg = load_yaml(cfg_path) or {}
        sid = str(cfg.get("id") or cfg_path.stem)
        system_configs[sid] = cfg
        system_config_paths[sid] = cfg_path

    records: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(run_dir.glob("*.results.jsonl")):
        sid = path.name.removesuffix(".results.jsonl")
        records[sid] = read_jsonl(path)

    judged: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(run_dir.glob("*.judged.jsonl")):
        sid = path.name.removesuffix(".judged.jsonl")
        judged[sid] = read_jsonl(path)

    dataset_rows = read_jsonl(dataset_path)
    report = _read_json(run_dir / "report.json")
    run_dataset = str(run_meta.get("dataset") or experiment.get("dataset") or "")
    try:
        run_dataset_path = resolve_repo_path(run_dataset) if run_dataset else None
    except Exception:
        run_dataset_path = None
    if run_dataset_path is None or run_dataset_path != dataset_path:
        problems.append({
            "message": "CLI dataset does not match the dataset recorded by the run.",
            "run_dataset": run_dataset or None,
            "cli_dataset": str(dataset_path),
            "file": str(run_dir / "run_meta.json"),
        })
    if not experiment:
        problems.append({
            "message": "Experiment config could not be reconstructed from run artifacts.",
            "file": str(run_dir / "run_meta.json"),
        })
    if not records:
        problems.append({
            "message": "No *.results.jsonl files were found.",
            "file": str(run_dir),
        })

    context = ValidationContext(
        root=ROOT,
        run_dir=run_dir,
        dataset_path=dataset_path,
        output_dir=output_dir,
        experiment=experiment,
        system_configs=system_configs,
        system_config_paths=system_config_paths,
        gate=gate,
        run_meta=run_meta,
        report=report,
        dataset_rows=dataset_rows,
        records=records,
        judged=judged,
    )
    status = "FAIL" if problems else "PASS"
    evidence = problems or [{
        "message": "Run config, system configs, dataset and artifacts loaded.",
        "run_dir": str(run_dir),
        "dataset": str(dataset_path),
        "systems": sorted(records),
        "n_dataset": len(dataset_rows),
    }]
    return context, CheckResult(
        "load_config",
        status,
        evidence,
        critical=bool(problems),
    )
