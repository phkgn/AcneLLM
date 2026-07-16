from __future__ import annotations

from pathlib import Path
from typing import Any


def write_dataset_audit(
    path: Path,
    report: dict[str, Any],
    human_queue: list[dict[str, Any]],
) -> None:
    lines = [
        "# Dataset audit",
        "",
        f"- Target: `{report.get('target')}`",
        f"- Directory: `{report.get('dataset_dir')}`",
        "",
        "| File | Rows | Schema errors | Approved | Frozen | Exact dup | Near dup | Contradictions |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for name, item in (report.get("files") or {}).items():
        statuses = item.get("annotation_status") or {}
        lines.append(
            f"| `{name}` | {item.get('n', 0)} | {len(item.get('schema_errors') or [])} | "
            f"{statuses.get('approved', 0)} | {'yes' if item.get('frozen') else 'no'} | "
            f"{len(item.get('exact_duplicates') or [])} | "
            f"{len(item.get('near_duplicates') or [])} | "
            f"{len(item.get('contradictory_labels') or [])} |"
        )
    contamination = report.get("contamination") or {}
    lines.extend([
        "",
        "## Train contamination",
        "",
        f"- Status: **{contamination.get('status', 'SKIPPED')}**",
        f"- Train: `{contamination.get('train')}`",
        f"- n-gram / threshold: `{contamination.get('ngram')}` / `{contamination.get('threshold')}`",
    ])
    for name, rows in (contamination.get("files") or {}).items():
        if rows:
            case_ids = ", ".join(str(row.get("case_id")) for row in rows[:30])
            lines.append(f"- `{name}`: {len(rows)} flagged — {case_ids}")
    lines.extend([
        "",
        "## Cross-split leakage",
        "",
    ])
    leakage = report.get("target_leakage") or []
    if leakage:
        for item in leakage[:50]:
            lines.append(f"- `{item.get('query')}` → `{item.get('locations')}`")
    else:
        lines.append("- No verbatim target-query leakage found across v1 files.")
    lines.extend([
        "",
        "## Human review queue",
        "",
    ])
    if human_queue:
        for item in human_queue:
            lines.append(
                f"- `{item.get('case_id')}` — {item.get('reason')} "
                f"Evidence: `{item.get('file')}`"
            )
    else:
        lines.append("- No targeted disagreement cases were generated.")
    lines.extend([
        "",
        "## Interpretation rule",
        "",
        "Synthetic generation provenance is acceptable only after human approval and SHA-256 "
        "freeze. D8 remains a reference-only retrieval set while its labels are "
        "`needs_relabel`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
