from __future__ import annotations

import json
from pathlib import Path

from evaluation.analysis.figures_eval import _latest_report_run, generate


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _assert_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert {
        "generated_at",
        "generation_id",
        "generator",
        "artifact_policy",
        "group",
        "figures",
    } == set(manifest)
    assert manifest["artifact_policy"] == "fresh_compute_no_figure_reuse"
    assert manifest["figures"]
    for figure in manifest["figures"]:
        assert {
            "id",
            "title",
            "kind",
            "file",
            "chart_type",
            "caption",
            "source_data",
            "status",
            "skip_reason",
        } <= set(figure)
        assert figure["status"] in {"ok", "skipped"}
    return manifest


def test_figures_eval_generates_schema_and_skips_missing_optional_data(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "evaluation" / "reports" / "smoke"
    systems = ["s0", "s1", "s2", "s3", "s4"]
    _write_json(
        run_dir / "report.json",
        {"systems": {system: {"n": 2} for system in systems}},
    )
    for system_index, system in enumerate(systems):
        judged = []
        results = []
        for sample_index, sample_id in enumerate(("case-1", "case-2")):
            correctness = min(5, 1 + system_index + sample_index)
            judged.append(
                {
                    "sample_id": sample_id,
                    "system_id": system,
                    "pointwise": {
                        "correctness": correctness,
                        "completeness": correctness,
                        "safety": min(5, correctness + 1),
                        "relevance": correctness,
                        "fluency": 4,
                        "instruction_following": 4,
                        "violated_criteria": (
                            ["correctness"] if correctness <= 2 else []
                        ),
                    },
                    "faithfulness": {
                        "faithfulness": 0.25 + system_index * 0.1,
                    },
                }
            )
            results.append(
                {
                    "sample_id": sample_id,
                    "system_id": system,
                    "answer": "sample answer",
                    "timings_ms": {
                        "retrieval": 10 * system_index,
                        "generation": 100 + 10 * system_index,
                        "total": 110 + 20 * system_index,
                    },
                }
            )
        _write_jsonl(run_dir / f"{system}.judged.jsonl", judged)
        _write_jsonl(run_dir / f"{system}.results.jsonl", results)

    _write_jsonl(
        tmp_path / "evaluation" / "datasets" / "v1" / "d1.jsonl",
        [
            {"sample_id": "case-1", "task_type": "knowledge"},
            {"sample_id": "case-2", "task_type": "safety"},
        ],
    )
    _write_json(
        tmp_path
        / "evaluation"
        / "reports"
        / "retrieval"
        / "latest"
        / "summary.json",
        {
            "modes": {
                "sparse": {
                    "hit@1": 0.4,
                    "recall@1": 0.2,
                    "hit@5": 0.8,
                    "recall@5": 0.6,
                }
            }
        },
    )
    _write_json(
        tmp_path
        / "evaluation"
        / "reports"
        / "unit"
        / "normalizer"
        / "report.json",
        {
            "multi_label": {
                "lesions": {"micro_f1": 0.8, "macro_f1": 0.75},
            }
        },
    )
    _write_json(
        tmp_path
        / "evaluation"
        / "reports"
        / "unit"
        / "intent_router"
        / "report.json",
        {"confusion": {"advise": {"advise": 2, "knowledge": 1}}},
    )

    output_root = tmp_path / "artifacts"
    stale_dir = output_root / "eval"
    stale_dir.mkdir(parents=True)
    (stale_dir / "obsolete-figure.png").write_bytes(b"stale")

    paths = generate(
        root=tmp_path,
        run_dir=run_dir,
        output_root=output_root,
    )
    eval_manifest = _assert_manifest(paths["eval"])
    model_manifest = _assert_manifest(paths["model"])
    assert sum(
        figure["status"] == "ok" for figure in eval_manifest["figures"]
    ) >= 8
    assert any(
        figure["id"] == "f8_judge_human"
        and figure["status"] == "skipped"
        for figure in eval_manifest["figures"]
    )
    assert any(
        figure["id"] == "c1_loss_curve"
        and figure["status"] == "skipped"
        for figure in model_manifest["figures"]
    )
    assert eval_manifest["generation_id"] == model_manifest["generation_id"]
    assert not (stale_dir / "obsolete-figure.png").exists()


def test_latest_report_prefers_newest_run_at_maximum_system_coverage(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "evaluation" / "reports"
    full = reports / "full"
    smoke = reports / "smoke"
    _write_json(
        full / "report.json",
        {"systems": {f"s{index}": {"n": 10} for index in range(5)}},
    )
    _write_json(
        smoke / "report.json",
        {"systems": {"s1": {"n": 1}}},
    )
    full_report = full / "report.json"
    smoke_report = smoke / "report.json"
    full_report.touch()
    smoke_report.touch()
    assert smoke_report.stat().st_mtime_ns >= full_report.stat().st_mtime_ns
    assert _latest_report_run(tmp_path) == full
