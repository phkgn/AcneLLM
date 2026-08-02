"""Generate one fresh, repository-wide A–F figure snapshot.

This is the canonical entrypoint for the dashboard. It computes every
data-backed figure from current source data/reports inside an isolated staging
directory, then replaces ``evaluation/reports/figures`` as a single snapshot.
No JSON, PNG, PDF, or manifest from the previous figures tree is used as input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.analysis import figures_eval, figures_kb, figures_usage
from evaluation.analysis.figures_common import (
    ARTIFACT_POLICY,
    FreshSnapshot,
    new_generation_id,
    read_json,
    utcnow,
    write_json,
)

ARTIFACT_GROUPS = ("kb", "finetune", "model", "usage", "eval")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _source_state(root: Path, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": _relative(root, path),
            "exists": False,
        }
    stat = path.stat()
    return {
        "path": _relative(root, path),
        "exists": True,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
    }


def _input_snapshot(root: Path) -> list[dict[str, Any]]:
    paths = [
        root / "data" / "raw" / "chunks.jsonl",
        root / "data" / "chroma_db" / "chroma.sqlite3",
        root / "data" / "bm25_index.pkl",
        root / "data" / "finetune" / "clean" / "acne_chat_response.train.jsonl",
        root / "data" / "finetune" / "clean" / "acne_chat_response.val.jsonl",
        root / "data" / "finetune" / "clean" / "acne_chat_response.test.jsonl",
        root / "data" / "audit.db",
        root / "data" / "sessions.db",
        root / "config" / "ood_centroid.json",
    ]
    return [_source_state(root, path) for path in paths]


def _group_summary(staging_root: Path, group: str) -> dict[str, Any]:
    manifest_path = staging_root / group / "manifest.json"
    manifest = read_json(manifest_path, {}) or {}
    figures = manifest.get("figures")
    figures = figures if isinstance(figures, list) else []
    return {
        "group": group,
        "manifest": f"{group}/manifest.json",
        "ok": sum(
            isinstance(figure, dict) and figure.get("status") == "ok"
            for figure in figures
        ),
        "skipped": sum(
            isinstance(figure, dict) and figure.get("status") == "skipped"
            for figure in figures
        ),
    }


def generate_all(
    *,
    root: Path | None = None,
    output_root: Path | None = None,
    run_dir: Path | str | None = None,
    sample: int = 8_000,
    pdf: bool = False,
) -> Path:
    root = (root or _repo_root()).resolve()
    output_root = (
        output_root
        or root / "evaluation" / "reports" / "figures"
    ).resolve()
    sample = max(3, min(int(sample), 100_000))
    generation_id = new_generation_id()
    generated_at = utcnow()

    print(
        f"[figures_all] generation_id={generation_id} "
        "policy=fresh-compute/no-figure-reuse",
        flush=True,
    )
    with FreshSnapshot(output_root) as staging_root:
        print("[figures_all] 1/3 generating model + eval figures…", flush=True)
        figures_eval.generate(
            root=root,
            run_dir=run_dir,
            output_root=staging_root,
            pdf=pdf,
            generation_id=generation_id,
            generated_at=generated_at,
        )
        print("[figures_all] 2/3 generating KB + finetune figures…", flush=True)
        figures_kb.generate(
            root=root,
            output_root=staging_root,
            sample=sample,
            pdf=pdf,
            generation_id=generation_id,
            generated_at=generated_at,
        )
        print("[figures_all] 3/3 generating anonymized usage figures…", flush=True)
        figures_usage.generate(
            root=root,
            output_root=staging_root,
            pdf=pdf,
            generation_id=generation_id,
            generated_at=generated_at,
        )

        groups = [
            _group_summary(staging_root, group)
            for group in ARTIFACT_GROUPS
        ]
        write_json(
            staging_root / "manifest.json",
            {
                "generated_at": generated_at,
                "generation_id": generation_id,
                "generator": "evaluation.generate_figures",
                "artifact_policy": ARTIFACT_POLICY,
                "figure_inputs_used": False,
                "sample": sample,
                "pdf": pdf,
                "groups": groups,
                "diagrams": {
                    "group": "diagrams",
                    "rendering": "client-side Mermaid from dashboard source",
                },
                "input_snapshot": _input_snapshot(root),
            },
        )

    final_manifest = output_root / "manifest.json"
    summary = read_json(final_manifest, {}) or {}
    groups = summary.get("groups")
    groups = groups if isinstance(groups, list) else []
    ok = sum(
        int(group.get("ok") or 0)
        for group in groups
        if isinstance(group, dict)
    )
    skipped = sum(
        int(group.get("skipped") or 0)
        for group in groups
        if isinstance(group, dict)
    )
    print(
        f"[figures_all] published fresh snapshot: ok={ok} "
        f"skipped={skipped} manifest={final_manifest}",
        flush=True,
    )
    return final_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=8_000)
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Exact evaluation run; default is newest run at maximum system coverage.",
    )
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    generate_all(
        run_dir=args.run_dir,
        sample=args.sample,
        pdf=args.pdf,
    )


if __name__ == "__main__":
    main()
