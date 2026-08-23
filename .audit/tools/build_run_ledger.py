"""Build the human checklist for an immutable one-pass capture."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def module_for(path: str) -> str:
    parts = path.split("/")
    if path.startswith("src/acne_llm/chat/routing/"):
        return "src.chat.routing"
    if path.startswith("src/acne_llm/chat/session/"):
        return "src.chat.session"
    if path.startswith("src/acne_llm/"):
        return "src." + (parts[2].split(".")[0] if len(parts) > 2 else "root")
    if path.startswith("research/evaluation/"):
        return "eval." + (parts[2].split(".")[0] if len(parts) > 2 else "root")
    if path.startswith("research/datagen/"):
        return "datagen." + (parts[2].split(".")[0] if len(parts) > 2 else "core")
    if path.startswith("research/LLMData/"):
        return "LLMData"
    return parts[0].split(".")[0] or "root"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    scope = json.loads((run_dir / "scope.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    modules: Counter[str] = Counter()
    lines = [
        f"# Coverage ledger — `{scope['run_id']}`",
        "",
        f"Snapshot HEAD: `{scope['head']}` on `{scope['branch']}`.",
        "Mẫu số: toàn bộ Git-tracked + untracked không bị ignore, trừ `.audit/**` (audit tự sinh).",
        "`[ ]` chưa audit semantic · `[x]` đủ FINDINGS 8 mục · `[skip]` bỏ qua có lý do.",
        "Các dấu `[x]` của coverage cũ không tự carry-forward vì run cũ thiếu fingerprint.",
        "",
        "## VỊ TRÍ ĐANG DỞ",
        "",
        "Capture hoàn tất; semantic audit của run này bắt đầu từ 0.",
        "",
        "## FILE",
        "",
    ]
    for rec in sorted(records, key=lambda item: item["path"].casefold()):
        module = module_for(rec["path"])
        if rec["action"] == "capture":
            modules[module] += 1
            lines.append(
                f"[ ] {rec['path']} — module: {module} — {rec.get('line_count', 0)} LOC — "
                f"sha256:{rec['sha256']} — symbols:{rec.get('symbol_count', 0)}"
            )
        else:
            lines.append(f"[skip] {rec['path']} — lý do: {rec['reason']}")
    lines.extend(["", "## MODULE COUNTS", ""])
    for module, count in sorted(modules.items()):
        lines.append(f"- {module}: {count} file captured")
    lines.append("")
    (run_dir / "coverage.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
