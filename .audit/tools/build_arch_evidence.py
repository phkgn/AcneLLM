"""Build synthesis inputs from retained one-pass inventory without reading source."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def area(path: str) -> str:
    parts = path.split("/")
    if path.startswith("src/acne_llm/"):
        if len(parts) >= 4 and parts[2] == "chat" and parts[3] in {"routing", "session"}:
            return "src." + parts[2] + "." + parts[3]
        return "src." + (parts[2].split(".")[0] if len(parts) > 2 else "root")
    if path.startswith("research/evaluation/"):
        return "evaluation." + (parts[2].split(".")[0] if len(parts) > 2 else "root")
    if path.startswith("research/datagen/"):
        return "datagen." + (parts[2].split(".")[0] if len(parts) > 2 else "core")
    if path.startswith("research/LLMData/"):
        return "LLMData"
    if path.startswith("research/dashboards/"):
        return "dashboards"
    if path.startswith("research/dataset_viz/"):
        return "dataset_viz"
    return parts[0].split(".")[0] or "root"


def import_area(name: str) -> str | None:
    clean = name.lstrip(".")
    if clean.startswith("acne_llm."):
        bits = clean.split(".")
        if len(bits) >= 4 and bits[1] == "chat" and bits[2] in {"routing", "session"}:
            return "src.chat." + bits[2]
        return "src." + (bits[1] if len(bits) > 1 else "root")
    first = clean.split(".", 1)[0]
    local = {
        "chat": "src.chat", "llm": "src.llm", "rag": "src.rag",
        "db": "src.db", "schemas": "src.schemas", "guardrails": "src.guardrails",
        "utils": "src.utils", "cache": "src.cache", "config": "src.config",
    }
    return local.get(first)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--findings-name")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    inventory = [json.loads(line) for line in (run / "inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    manifest = {rec["path"]: rec for rec in (json.loads(line) for line in (run / "manifest.jsonl").read_text(encoding="utf-8").splitlines())}
    modules: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "loc": 0, "symbols": 0})
    edges: Counter[tuple[str, str]] = Counter()
    externals: defaultdict[str, Counter[str]] = defaultdict(Counter)
    routes: list[tuple[str, str, str, int]] = []
    envs: defaultdict[str, set[str]] = defaultdict(set)
    debts: list[tuple[str, str, int]] = []
    calls: defaultdict[str, list[tuple[str, int]]] = defaultdict(list)
    for item in inventory:
        path = item["path"]
        src = area(path)
        rec = manifest[path]
        modules[src]["files"] += 1
        modules[src]["loc"] += int(rec.get("line_count", 0))
        modules[src]["symbols"] += len(item.get("symbols", []))
        for imp in item.get("imports", []):
            name = imp.get("module", "") if isinstance(imp, dict) else str(imp)
            dst = import_area(name)
            if dst and dst != src:
                edges[(src, dst)] += 1
            elif name and not name.startswith("."):
                externals[src][name.split(".", 1)[0]] += 1
        for route in item.get("routes", []):
            routes.append((route["method"], route["path"], path, route["line"]))
        for env in item.get("env_refs", []):
            envs[env].add(path)
        for debt in item.get("debt_markers", []):
            debts.append((debt["marker"], path, debt["line"]))
        for call in item.get("calls", []):
            calls[call["target"].rsplit(".", 1)[-1]].append((path, call["count"]))

    lines = ["# Architecture synthesis evidence", "", "Generated only from retained one-pass inventory; no source file was reopened.", "", "## Module inventory", "", "| Module | Files | LOC | Symbols |", "|---|---:|---:|---:|"]
    for name, values in sorted(modules.items()):
        lines.append(f"| `{name}` | {values['files']} | {values['loc']} | {values['symbols']} |")
    lines.extend(["", "## Internal dependency edges", "", "| From | To | Import sites |", "|---|---|---:|"])
    for (src, dst), count in sorted(edges.items()):
        lines.append(f"| `{src}` | `{dst}` | {count} |")
    lines.extend(["", "## External dependency families", ""])
    for src, names in sorted(externals.items()):
        lines.append(f"- `{src}`: " + ", ".join(f"`{name}`({count})" for name, count in names.most_common()))
    lines.extend(["", "## HTTP/WebSocket routes", "", "| Method | Path | Evidence |", "|---|---|---|"])
    for method, route, path, line in sorted(routes):
        lines.append(f"| `{method}` | `{route}` | `{path}:{line}` |")
    lines.extend(["", "## Environment references", ""])
    for env, paths in sorted(envs.items()):
        lines.append(f"- `{env}`: " + ", ".join(f"`{path}`" for path in sorted(paths)))
    lines.extend(["", "## Debt markers", ""])
    for marker, path, line in sorted(debts, key=lambda row: (row[1], row[2])):
        lines.append(f"- `{path}:{line}` — `{marker}`")
    lines.extend(["", "## Key call-site candidates", ""])
    for target in ["build_container", "prepare_chat_turn", "run_intake", "retrieve", "build", "generate", "stream_chat_sse", "close", "main"]:
        sites = calls.get(target, [])
        lines.append(f"- `{target}`: " + (", ".join(f"`{path}`({count})" for path, count in sorted(sites)) if sites else "không có exact-name call"))
    lines.append("")
    if args.findings_name:
        findings_dir = run / args.findings_name
    elif (run / "FINDINGS_COMPLETE").is_dir():
        findings_dir = run / "FINDINGS_COMPLETE"
    else:
        findings_dir = run / "FINDINGS_AUTO"
    findings_dir.mkdir(parents=True, exist_ok=True)
    target = findings_dir / "ARCH_SYNTHESIS_EVIDENCE.md"
    target.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(target)


if __name__ == "__main__":
    main()
