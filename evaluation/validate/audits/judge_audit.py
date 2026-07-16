from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.common import ROOT


def write_judge_audit(
    path: Path,
    judge_stats: dict[str, Any],
) -> None:
    prompt_dir = ROOT / "evaluation" / "judges" / "prompts"
    prompt_names = [
        "pointwise",
        "pairwise",
        "claim_extract",
        "entailment",
        "error_classify",
    ]
    scans: dict[str, dict[str, Any]] = {}
    for name in prompt_names:
        prompt_path = prompt_dir / f"{name}.md"
        text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        scans[name] = {
            "exists": prompt_path.exists(),
            "model_name_leak": any(
                token in text.casefold()
                for token in ("acnellm", "qwen25", "deepseek output", "system s")
            ),
            "length_guard": "dài hơn" in text.casefold() or "length" in text.casefold(),
            "evidence_only": (
                "không dùng kiến thức" in text.casefold()
                or "chỉ được dựa" in text.casefold()
            ),
        }
    lines = [
        "# Judge audit",
        "",
        "| Prompt | Exists | Blind model | Length guard | Evidence-only where required |",
        "|---|---|---|---|---|",
    ]
    for name in prompt_names:
        scan = scans[name]
        lines.append(
            f"| `{name}.md` | {'yes' if scan['exists'] else 'no'} | "
            f"{'FAIL' if scan['model_name_leak'] else 'PASS'} | "
            f"{'yes' if scan['length_guard'] else 'no'} | "
            f"{'yes' if scan['evidence_only'] else 'n/a/no'} |"
        )
    lines.extend([
        "",
        "## Rubric risks",
        "",
        "- `pointwise.md` deliberately allows standard medical knowledge for correctness, "
        "while `entailment.md` forbids external knowledge for groundedness. Mixing those "
        "two outputs would be invalid.",
        "- Correctness and completeness partially overlap because expected points affect both; "
        "report them as separate axes and retain per-case evidence.",
        "- Pairwise includes an explicit anti-length-bias instruction and is evaluated in both "
        "A/B orders; disagreement becomes tie.",
        "- Parser contract: malformed JSON returns `None`; the runner must persist "
        "`judge_status=invalid`, never substitute score 0.",
        "",
        "## Artifact validation",
        "",
        "```json",
        __import__("json").dumps(judge_stats, indent=2, ensure_ascii=False),
        "```",
    ])
    if judge_stats.get("invalid_faithfulness_context"):
        lines.extend([
            "",
            "**Faithfulness in this run is not trustworthy:** judged rows exist but source "
            "text is absent from the saved trace. This is an artifact-level validity failure, "
            "even though the current source code contains the context-trace fix.",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
