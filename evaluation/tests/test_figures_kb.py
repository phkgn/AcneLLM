from __future__ import annotations

import json
from pathlib import Path

from evaluation.analysis.figures_kb import generate


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_figures_kb_uses_fake_data_and_skips_missing_heavy_sources(
    tmp_path: Path,
) -> None:
    _write_jsonl(
        tmp_path / "data" / "raw" / "chunks.jsonl",
        [
            {
                "chunk_id": "c1",
                "text": "Mụn viêm ở tuổi dậy thì điều trị bằng benzoyl peroxide.",
                "text_len": 60,
            },
            {
                "chunk_id": "c2",
                "text": "Mụn đầu đen khi mang thai có thể cân nhắc azelaic acid.",
                "text_len": 58,
            },
            {
                "chunk_id": "c3",
                "text": "Mụn nang và sẹo ở người có PCOS cần bác sĩ da liễu.",
                "text_len": 55,
            },
        ],
    )
    clean_dir = tmp_path / "data" / "finetune" / "clean"
    base_row = {
        "messages": [
            {
                "role": "user",
                "content": (
                    '<normalized_case>{"demographics":{"is_pregnant":false}}'
                    "</normalized_case> prompt"
                ),
            },
            {"role": "assistant", "content": "safe response"},
        ],
        "metadata": {
            "case_type": "mild_comedonal",
            "severity": "mild",
            "safety_flags": ["treatment_failure"],
            "source_chunk_id": "c1",
        },
    }
    for split in ("train", "val", "test"):
        _write_jsonl(
            clean_dir / f"acne_chat_response.{split}.jsonl",
            [base_row],
        )
    _write_json(
        clean_dir / "acne_chat_response.clean_report.json",
        {
            "summary": {"input_records": 2, "kept_records": 1},
            "before": {"case_type": {"mild_comedonal": 2}},
            "after": {"case_type": {"mild_comedonal": 1}},
        },
    )

    output_root = tmp_path / "artifacts"
    stale_dir = output_root / "kb"
    stale_dir.mkdir(parents=True)
    (stale_dir / "obsolete-figure.json").write_text(
        '{"stale": true}',
        encoding="utf-8",
    )

    paths = generate(
        root=tmp_path,
        output_root=output_root,
        sample=3,
    )
    kb_manifest = json.loads(paths["kb"].read_text(encoding="utf-8"))
    finetune_manifest = json.loads(
        paths["finetune"].read_text(encoding="utf-8")
    )
    assert any(
        figure["id"] == "a2_chunk_length"
        and figure["status"] == "ok"
        for figure in kb_manifest["figures"]
    )
    assert any(
        figure["id"] == "a3_kb_umap"
        and figure["status"] == "skipped"
        for figure in kb_manifest["figures"]
    )
    assert sum(
        figure["status"] == "ok"
        for figure in finetune_manifest["figures"]
    ) >= 4
    for manifest in (kb_manifest, finetune_manifest):
        assert manifest["artifact_policy"] == "fresh_compute_no_figure_reuse"
        for figure in manifest["figures"]:
            assert figure["status"] in {"ok", "skipped"}
            assert figure["skip_reason"] is None or isinstance(
                figure["skip_reason"], str
            )
    assert kb_manifest["generation_id"] == finetune_manifest["generation_id"]
    assert not (stale_dir / "obsolete-figure.json").exists()
