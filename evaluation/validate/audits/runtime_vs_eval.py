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
            "same through API | same functions through `adapters/_repo.py` | "
            "T1/T3 can diagnose extraction but not API behavior. |"
        ),
        (
            "| Guardrails/routing | `pre_check` + rule router + reject/clarify forks | "
            "same through API | bypassed by `pipeline/hybrid.py` / `llm_only.py` | "
            "Router and guardrail conclusions require T4/T1, not T3. |"
        ),
        (
            "| Retrieval | production chat top-k/settings | same server path when mode=hybrid | "
            "batch config top-15 then rerank top-5 | Retrieval depth is a known T3/T4 difference. |"
        ),
        (
            "| Prompt | intent-aware prose templates, chiefly `stream_user.j2` | "
            "same production templates | `llm_only_user.j2` / `hybrid_user.j2` JSON contract | "
            "T3 format/content quality cannot be presented as user-visible production output. |"
        ),
        (
            "| Generation/output | `stream_text`, prose + `[N]` | same SSE token stream | "
            "`generate_json`, `AdviseOutput` | T4 is the primary reality check. |"
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
