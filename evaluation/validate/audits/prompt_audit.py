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
        ROOT / "config" / "prompts" / "llm_only_user.j2",
        ROOT / "config" / "prompts" / "hybrid_user.j2",
        ROOT / "config" / "prompts" / "stream_user.j2",
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
            "| `llm_only_user.j2` | data + no-RAG constraints | current/history/safety facts | "
            f"`AdviseOutput` JSON | `{model_hints['llm_only_user.j2'] or 'none'}` |"
        ),
        (
            "| `hybrid_user.j2` | data + grounding/citation contract | retrieved chunks + current/history | "
            f"`AdviseOutput` JSON | `{model_hints['hybrid_user.j2'] or 'none'}` |"
        ),
        (
            "| `stream_user.j2` | production data prompt | route/history/retrieved chunks | "
            f"prose + `[N]` | `{model_hints['stream_user.j2'] or 'none'}` |"
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
        "the three user templates intentionally do not duplicate them.",
        "- `hybrid_user.j2` alone receives retrieved evidence; this is the registered RAG IV, "
        "not a model-specific hint.",
        "- T3 prompts require JSON while production `stream_user.j2` requests prose. This is "
        "a real path difference and must remain explicit in reports.",
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
