from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.common import ROOT
from evaluation.validate.checks.runtime import normalize_system_prompt


def write_prompt_audit(
    path: Path,
    runtime_snapshot: dict[str, Any],
) -> None:
    prompt_paths = [
        ROOT / "config" / "prompts" / "stream_user.j2",
        ROOT / "config" / "prompts" / "knowledge_user.j2",
        ROOT / "config" / "prompts" / "clarify_user.j2",
    ]
    texts = {
        item.name: item.read_text(encoding="utf-8") if item.exists() else ""
        for item in prompt_paths
    }
    model_hints = {
        name: [
            token for token in ("acnellm", "qwen", "s0", "s1", "s2", "s3")
            if token in text.casefold()
        ]
        for name, text in texts.items()
    }
    system_prompts = runtime_snapshot.get("system_prompts") or {}
    s0_s1_equal = bool(
        system_prompts.get("s0")
        and system_prompts.get("s1")
        and normalize_system_prompt(system_prompts["s0"])
        == normalize_system_prompt(system_prompts["s1"])
    )
    lines = [
        "# Prompt audit",
        "",
        "| Prompt | Contract | Context | Output | Model hint |",
        "|---|---|---|---|---|",
        (
            "| `stream_user.j2` | production data prompt | route/history/retrieved chunks | "
            f"prose | `{model_hints['stream_user.j2'] or 'none'}` |"
        ),
        (
            "| `knowledge_user.j2` | knowledge prompt | user history/retrieved chunks | "
            f"prose | `{model_hints['knowledge_user.j2'] or 'none'}` |"
        ),
        (
            "| `clarify_user.j2` | one-question clarification | current/history | "
            f"prose | `{model_hints['clarify_user.j2'] or 'none'}` |"
        ),
        "",
        "## SYSTEM parity (R1)",
        "",
        f"- S0 vs S1 SYSTEM semantic text equal: **{'PASS' if s0_s1_equal else 'FAIL / unverified'}**",
        "- Evidence sources: Ollama `/api/show` when available; fallback Modelfiles "
        "`evaluation/modelfiles/qwen25-base-acnesys/Modelfile` and `model/V2/Q4/Modelfile`.",
        "",
        "## Semantic findings",
        "",
        "- Safety, scope, language and anti-jailbreak rules live in the Modelfile SYSTEM; "
        "the prose user templates intentionally do not duplicate them.",
        "- T3 and T4 share the same route-selected prose templates. Retrieval remains the "
        "registered RAG independent variable, not a model-specific hint.",
        "- T3 uses non-stream text generation; T4 adds the real HTTP/SSE transport and "
        "stream-time persistence/post-processing.",
        "- No template may mention S0-S4 or a model/checkpoint name. The table above records "
        "the static scan result.",
        "",
        "## Hashes",
        "",
        "```json",
        __import__("json").dumps(
            runtime_snapshot.get("prompt_hashes") or {},
            indent=2,
            ensure_ascii=False,
        ),
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
