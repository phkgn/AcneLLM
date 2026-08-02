from __future__ import annotations

import json
from pathlib import Path

from evaluation.generate_figures import ARTIFACT_GROUPS, generate_all


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )


def test_generate_all_publishes_one_fresh_snapshot_without_old_figures(
    tmp_path: Path,
) -> None:
    _write_jsonl(
        tmp_path / "data" / "raw" / "chunks.jsonl",
        [
            {
                "chunk_id": "c1",
                "text": "Mụn viêm tuổi dậy thì và benzoyl peroxide.",
                "text_len": 44,
            }
        ],
    )
    output_root = tmp_path / "evaluation" / "reports" / "figures"
    (output_root / "kb").mkdir(parents=True)
    (output_root / "kb" / "old.png").write_bytes(b"old")
    (output_root / "orphan.json").write_text(
        '{"old": true}',
        encoding="utf-8",
    )

    manifest_path = generate_all(
        root=tmp_path,
        output_root=output_root,
        sample=3,
    )
    snapshot = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert snapshot["artifact_policy"] == "fresh_compute_no_figure_reuse"
    assert snapshot["figure_inputs_used"] is False
    assert [group["group"] for group in snapshot["groups"]] == list(
        ARTIFACT_GROUPS
    )
    assert not (output_root / "kb" / "old.png").exists()
    assert not (output_root / "orphan.json").exists()

    generation_ids = set()
    for group in ARTIFACT_GROUPS:
        group_manifest = json.loads(
            (output_root / group / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        generation_ids.add(group_manifest["generation_id"])
        assert (
            group_manifest["artifact_policy"]
            == "fresh_compute_no_figure_reuse"
        )
    assert generation_ids == {snapshot["generation_id"]}
