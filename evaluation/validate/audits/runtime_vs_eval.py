from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.validate.types import ValidationContext


def write_runtime_audit(
    path: Path,
    context: ValidationContext,
    runtime_snapshot: dict[str, Any],
) -> None:
    production = runtime_snapshot.get("production") or {}
    has_t4 = context.tier == "t4"
    lines = [
        "# Runtime production vs evaluation",
        "",
        f"- Run: `{context.run_dir}`",
        f"- Tier artifact: `{context.tier}`",
        f"- Dataset: `{context.dataset_path}`",
        f"- T4 artifact present in this run: **{'yes' if has_t4 else 'no'}**",
        "",
        "| Stage | Production SSE | T4 adapter | T3 batch | Interpretation |",
        "|---|---|---|---|---|",
        (
            "| Request/session | `GET /api/v1/chat/stream`, caller session | "
            "same HTTP route; unique eval session per case | no HTTP/session | "
            "Only T4 observes API and session behavior. |"
        ),
        (
            "| Preprocess/normalize | `prepare_user_text` + `normalize_chat_message` | "
            "same through API | same `prepare_chat_turn` path | "
            "T1/T3 can diagnose extraction but not API behavior. |"
        ),
        (
            "| Guardrails/routing | `pre_check` + rule router + reject/clarify forks | "
            "same through API | same preparation path, no HTTP/session side effects | "
            "T3 can diagnose route/prompt; T4 remains required for transport/session behavior. |"
        ),
        (
            "| Retrieval | production chat top-k/settings | same server path when mode=hybrid | "
            "same `retrieve_for_chat` path | T3 and T4 now share retrieval selection. |"
        ),
        (
            "| Prompt | intent-aware prose templates, chiefly `stream_user.j2` | "
            "same production templates | same route-selected prose templates | "
            "Prompt content is aligned; transport behavior still differs. |"
        ),
        (
            "| Generation/output | `stream_text`, prose + `[N]` | same SSE token stream | "
            "non-stream `generate_text`, prose | T4 is the transport reality check. |"
        ),
        (
            "| Trace | server SSE events + debug trace when queried | adapter stores route/citation/session | "
            "adapter stores normalized input, output and retrieval context | "
            "Missing trace fields invalidate layer attribution. |"
        ),
        "",
        "## Effective production snapshot",
        "",
        "```json",
        __import__("json").dumps(production, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Current interpretation",
        "",
    ]
    if has_t4:
        lines.append(
            "This artifact exercises the production SSE path, subject to the model and "
            "session checks in `summary.json`."
        )
    else:
        lines.append(
            "**No T4 result is present.** This run can validate T3 batch plumbing and relative "
            "S0-S4 diagnostics, but it cannot establish production chat quality."
        )
    if runtime_snapshot.get("warnings"):
        lines.extend(["", "## Confirmed differences / warnings", ""])
        for item in runtime_snapshot["warnings"]:
            lines.append(f"- {item.get('message')} Evidence: `{item.get('files') or item.get('file')}`")
    if runtime_snapshot.get("violations"):
        lines.extend(["", "## Runtime validity failures", ""])
        for item in runtime_snapshot["violations"]:
            lines.append(f"- {item.get('message')} Evidence: `{item.get('files') or item.get('file')}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
