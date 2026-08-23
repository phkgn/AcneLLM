"""Independent completion gate for the immutable architecture audit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
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
    if path.startswith("research/dashboards/"):
        return "dashboards"
    if path.startswith("research/dataset_viz/"):
        return "dataset_viz"
    if path.startswith("research/guideline_docs/") or path.startswith("guideline_docs/"):
        return "guideline_docs"
    return (parts[0].split(".")[0] or "root").replace(" ", "_")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    audit = run.parents[1]
    root = audit.parent
    findings_dir = run / "FINDINGS_COMPLETE"
    errors: list[str] = []

    manifest = [json.loads(line) for line in (run / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    inventory = [json.loads(line) for line in (run / "inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    proof = json.loads((run / "semantic-complete-proof.json").read_text(encoding="utf-8"))
    captured = [rec for rec in manifest if rec["action"] == "capture"]
    skipped = [rec for rec in manifest if rec["action"] == "skip"]
    if len(manifest) != 783 or len(captured) != 581 or len(skipped) != 202:
        fail(errors, f"scope mismatch manifest={len(manifest)} captured={len(captured)} skipped={len(skipped)}")
    if len({rec["path"] for rec in manifest}) != len(manifest):
        fail(errors, "manifest contains duplicate paths")
    if any(not rec.get("reason") for rec in skipped):
        fail(errors, "a skipped path has no reason")
    if proof != {
        "snapshot_files_read_once": 581,
        "manifest_captured_files": 581,
        "blocks": 10403,
        "items_required": 83224,
        "items_filled": 83224,
        "hash_mismatches": 0,
    }:
        fail(errors, f"semantic proof differs: {proof}")

    module_text: dict[str, str] = {}
    all_text = ""
    for finding in findings_dir.glob("*.md"):
        text = finding.read_text(encoding="utf-8")
        all_text += "\n" + text
        if finding.name not in {"INDEX.md", "ARCH_SYNTHESIS_EVIDENCE.md"}:
            module_text[finding.stem] = text

    sections: dict[str, str] = {}
    for module, text in module_text.items():
        matches = list(re.finditer(r"^## `(.+?)`\s*$", text, re.MULTILINE))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            path = match.group(1)
            if path in sections:
                fail(errors, f"duplicate file section: {path}")
            sections[path] = text[match.start():end]
    captured_paths = {rec["path"] for rec in captured}
    if set(sections) != captured_paths:
        missing = sorted(captured_paths - set(sections))
        extra = sorted(set(sections) - captured_paths)
        fail(errors, f"file sections mismatch missing={missing[:10]} extra={extra[:10]}")

    blocks = list(re.finditer(r"^### \[x\] ", all_text, re.MULTILINE))
    item_counts = Counter(int(match.group(1)) for match in re.finditer(r"^([1-8])\. ", all_text, re.MULTILINE))
    if len(blocks) != 10403:
        fail(errors, f"block count={len(blocks)}")
    for number in range(1, 9):
        if item_counts[number] != len(blocks):
            fail(errors, f"item {number} count={item_counts[number]} blocks={len(blocks)}")
    if re.search(r"^### \[ \]|^\[ \]", all_text, re.MULTILINE):
        fail(errors, "open checkbox in final findings")

    parse_errors: list[tuple[str, str]] = []
    for path, section in sections.items():
        match = re.search(r"parse_error: `(.+?)`", section)
        if match and match.group(1) != "không":
            parse_errors.append((path, match.group(1)))
    bad_parse = [path for path, _ in parse_errors if not path.endswith(".ipynb")]
    if bad_parse:
        fail(errors, f"non-notebook parse errors: {bad_parse}")

    surface_missing: list[str] = []
    for item in inventory:
        path = item["path"]
        section = sections.get(path, "")
        for symbol in item.get("symbols", []):
            name = symbol.get("qualified_name") or symbol.get("name")
            public = symbol.get("public", True)
            kind = symbol.get("kind", "")
            if not public and kind not in {"function", "async_function", "class"}:
                continue
            if name and f"`{name}`" not in section:
                surface_missing.append(f"{path} symbol {name}")
        for env in item.get("env_refs", []):
            if f"env:{env}@" not in section:
                surface_missing.append(f"{path} env {env}")
        for key in item.get("config_keys", []):
            key_name = key.get("key") if isinstance(key, dict) else str(key)
            if key_name and f"config:{key_name}@" not in section and f"`{key_name}`" not in section:
                surface_missing.append(f"{path} config {key_name}")
        for route in item.get("routes", []):
            if route["method"] not in section or route["path"] not in section:
                surface_missing.append(f"{path} route {route['method']} {route['path']}")
    if surface_missing:
        fail(errors, "surface missing: " + "; ".join(surface_missing[:30]))

    todo = (audit / "todo.md").read_text(encoding="utf-8")
    actions = re.findall(r"^⚠? ?\[[ABC]\] `[^`]+:Q-\d+`", todo, re.MULTILINE)
    closed_section = todo.split("## Q đã đóng/đính chính — không đưa vào patch", 1)[-1].split("## Doc mồ côi", 1)[0]
    closed = re.findall(r"^- `[^`]+:Q-\d+`", closed_section, re.MULTILINE)
    if len(actions) + len(closed) != 108:
        fail(errors, f"todo Q accounting={len(actions)}+{len(closed)}")
    for heading in ("RỔ A", "RỔ B", "RỔ C", "Doc mồ côi", "Hành vi quan trọng chưa được mô tả"):
        if heading not in todo:
            fail(errors, f"todo missing {heading}")

    patch_results: dict[str, str] = {}
    for name in ("A-docs.patch", "B-comments.patch", "C-code.patch"):
        patch = audit / "patches" / name
        if not patch.exists() or patch.stat().st_size == 0:
            fail(errors, f"missing patch {name}")
            continue
        proc = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "apply", "--check", "--whitespace=error-all", str(patch)],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        patch_results[name] = "pass" if proc.returncode == 0 else proc.stdout.strip()
        if proc.returncode != 0:
            fail(errors, f"patch {name} does not apply: {proc.stdout.strip()}")

    architecture = (audit / "ARCHITECTURE.md").read_text(encoding="utf-8")
    expected_tail = "baseline_commit = 585333cc68d6e29b666337bdf366c99e00abc9b7"
    if not architecture.rstrip().endswith(expected_tail):
        fail(errors, "ARCHITECTURE.md missing final baseline_commit")
    if "baseline_snapshot_run = 20260822T152307Z" not in architecture:
        fail(errors, "ARCHITECTURE.md missing snapshot run")

    report = [
        "# Completion gate", "", f"- result: {'FAIL' if errors else 'PASS'}",
        f"- manifest paths: {len(manifest)} / 783",
        f"- captured semantic files: {len(captured)} / 581",
        f"- explicit skips: {len(skipped)} / 202",
        f"- file sections: {len(sections)} / 581",
        f"- audited blocks: {len(blocks)} / 10403",
        f"- 1-8 items: {sum(item_counts.values())} / 83224",
        f"- public-surface misses: {len(surface_missing)}",
        f"- non-notebook parse errors: {len(bad_parse)}",
        f"- todo Q accounting: {len(actions)} action + {len(closed)} closed = {len(actions) + len(closed)} / 108",
        f"- patch checks: {patch_results}", "",
    ]
    if errors:
        report.extend(["## Errors", "", *[f"- {error}" for error in errors], ""])
    else:
        coverage_path = run / "coverage.md"
        coverage = coverage_path.read_text(encoding="utf-8")
        coverage = re.sub(r"^\[ \] ", "[x] ", coverage, flags=re.MULTILINE)
        coverage = coverage.replace("Capture hoàn tất; semantic audit của run này bắt đầu từ 0.", "Semantic audit và completion gate đã hoàn tất: 581 done, 202 skip, 0 open.")
        coverage_path.write_text(coverage, encoding="utf-8", newline="\n")
        report.extend(["All gates passed; coverage was closed mechanically.", ""])
    (run / "COMPLETION_GATE.md").write_text("\n".join(report), encoding="utf-8", newline="\n")
    print("\n".join(report))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
