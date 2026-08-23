"""Create an immutable, one-open-per-source audit capture.

The product/research files are opened exactly once by this process.  The bytes
from that open are used for hashing, line counting, static inventory, and the
immutable snapshot.  Later audit stages must read only the snapshot for the
selected run_id, never the live source tree.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".xlsx", ".xls", ".sqlite", ".sqlite3", ".pkl", ".pyc", ".woff",
    ".woff2", ".ttf", ".mp3", ".mp4", ".drawio",
}
DATA_SUFFIXES = {".jsonl", ".csv", ".tsv", ".log", ".fingerprint", ".done", ".sha256"}
LOCK_NAMES = {"uv.lock", "package-lock.json", "tsconfig.tsbuildinfo"}
SOURCE_SUFFIXES = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".ps1", ".sh", ".bat",
    ".j2", ".html", ".css", ".yaml", ".yml", ".toml", ".json", ".md",
    ".ipynb", ".txt", ".example", ".baseline", ".gitattributes",
    ".gitignore", ".dockerignore",
}
SPECIAL_TEXT_NAMES = {"Dockerfile", "tasks.sh", "requirements.txt", "requirements-dev.txt"}

ENV_RE = re.compile(
    r"(?:os\.(?:getenv|environ\.get)|getenv|environ\.get)\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"
    r"|process\.env\.([A-Za-z_][A-Za-z0-9_]*)|\$env:([A-Za-z_][A-Za-z0-9_]*)"
)
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|deprecated|ponytail)\b", re.IGNORECASE)
ROUTE_RE = re.compile(r"@(?:\w+\.)?(get|post|put|patch|delete|websocket)\(\s*['\"]([^'\"]+)")
CONFIG_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]", re.MULTILINE)
JS_SYMBOL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:(class)\s+([A-Za-z_$][\w$]*)|function\s+([A-Za-z_$][\w$]*)\s*\(|"
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=)",
    re.MULTILINE,
)
SHELL_SYMBOL_RE = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_-]*)\s*(?:\(\))?\s*\{", re.MULTILINE)
PS_SYMBOL_RE = re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_-]*)", re.MULTILINE | re.IGNORECASE)


def run_git(root: Path, *args: str) -> bytes:
    cmd = [
        "git", "-c", f"safe.directory={root.as_posix()}",
        "-c", "core.quotepath=false", "-c", "filter.lfs.process=",
        "-c", "filter.lfs.required=false", *args,
    ]
    return subprocess.check_output(cmd, cwd=root)


def git_paths(root: Path, *args: str) -> list[str]:
    raw = run_git(root, *args, "-z")
    return [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]


def classify(path: str) -> tuple[str, str]:
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if path.startswith(".audit/"):
        return "exclude", "audit tooling; excluded to prevent self-recursive scope"
    if name in LOCK_NAMES or name.endswith(".lock"):
        return "skip", "generated dependency/build lock artifact"
    if suffix in BINARY_SUFFIXES:
        return "skip", f"binary/asset ({suffix or 'no suffix'})"
    if suffix in DATA_SUFFIXES:
        return "skip", f"data/runtime artifact ({suffix})"
    if name in SPECIAL_TEXT_NAMES or suffix in SOURCE_SUFFIXES or not suffix:
        return "capture", "text/code/config/doc"
    return "skip", f"non-source artifact ({suffix or 'unknown type'})"


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def python_inventory(text: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    calls: Counter[str] = Counter()
    parse_error: str | None = None
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        tree = None
        parse_error = f"{exc.msg} at {exc.lineno}:{exc.offset}"

    if tree is not None:
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parent = parents.get(node)
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    owner = getattr(parent, "name", "<nested>")
                else:
                    owner = None
                kind = "class" if isinstance(node, ast.ClassDef) else (
                    "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                )
                signature = None
                if not isinstance(node, ast.ClassDef):
                    try:
                        signature = ast.unparse(node.args)
                    except Exception:
                        signature = None
                symbols.append({
                    "name": node.name,
                    "qualified_name": f"{owner}.{node.name}" if owner else node.name,
                    "kind": kind,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "owner": owner,
                    "public": not node.name.startswith("_"),
                    "signature": signature,
                    "decorators": [ast.unparse(d) for d in node.decorator_list],
                    "returns": ast.unparse(node.returns) if getattr(node, "returns", None) else None,
                    "has_docstring": bool(ast.get_docstring(node, clean=False)),
                })
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(parents.get(node), ast.Module):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name_node in ast.walk(target):
                        if isinstance(name_node, ast.Name):
                            symbols.append({
                                "name": name_node.id,
                                "qualified_name": name_node.id,
                                "kind": "constant" if name_node.id.isupper() else "module_variable",
                                "line": node.lineno,
                                "end_line": getattr(node, "end_lineno", node.lineno),
                                "owner": None,
                                "public": not name_node.id.startswith("_"),
                            })
            elif isinstance(node, ast.Import):
                imports.extend({"module": a.name, "line": node.lineno} for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append({"module": "." * node.level + (node.module or ""), "line": node.lineno})
            elif isinstance(node, ast.Call):
                try:
                    calls[ast.unparse(node.func)] += 1
                except Exception:
                    pass
    symbols.sort(key=lambda item: (item["line"], item["qualified_name"]))
    return {
        "symbols": symbols,
        "imports": imports,
        "calls": [{"target": name, "count": count} for name, count in calls.most_common()],
        "parse_error": parse_error,
    }


def generic_inventory(path: str, text: str) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    symbols: list[dict[str, Any]] = []
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for match in JS_SYMBOL_RE.finditer(text):
            name = match.group(2) or match.group(3) or match.group(4)
            symbols.append({"name": name, "kind": "class" if match.group(1) else "binding", "line": line_of(text, match.start())})
    elif suffix == ".ps1":
        for match in PS_SYMBOL_RE.finditer(text):
            symbols.append({"name": match.group(1), "kind": "function", "line": line_of(text, match.start())})
    elif suffix == ".sh" or Path(path).name == "tasks.sh":
        for match in SHELL_SYMBOL_RE.finditer(text):
            symbols.append({"name": match.group(1), "kind": "function", "line": line_of(text, match.start())})

    config_keys = []
    if suffix in {".yaml", ".yml", ".toml", ".json", ".example", ".baseline"} or Path(path).name.startswith(".env"):
        config_keys = [{"key": m.group(1), "line": line_of(text, m.start())} for m in CONFIG_KEY_RE.finditer(text)]
    return {"symbols": symbols, "imports": [], "calls": [], "config_keys": config_keys, "parse_error": None}


def inventory(path: str, text: str) -> dict[str, Any]:
    result = python_inventory(text) if Path(path).suffix.lower() == ".py" else generic_inventory(path, text)
    result["env_refs"] = sorted({next(value for value in match.groups() if value) for match in ENV_RE.finditer(text)})
    result["routes"] = [
        {"method": match.group(1).upper(), "path": match.group(2), "line": line_of(text, match.start())}
        for match in ROUTE_RE.finditer(text)
    ]
    result["debt_markers"] = [
        {"marker": match.group(1), "line": line_of(text, match.start())}
        for match in TODO_RE.finditer(text)
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    root = args.root.resolve()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / ".audit" / "runs" / run_id
    if run_dir.exists():
        raise SystemExit(f"run already exists: {run_dir}")
    snapshot_dir = run_dir / "snapshot"
    snapshot_dir.mkdir(parents=True)

    tracked = git_paths(root, "ls-files")
    untracked = git_paths(root, "ls-files", "--others", "--exclude-standard")
    candidates = [(path, "tracked") for path in tracked]
    candidates.extend((path, "untracked") for path in untracked if not path.startswith(".audit/"))
    seen: set[str] = set()
    candidates = [(p, origin) for p, origin in candidates if not (p in seen or seen.add(p))]

    manifest_path = run_dir / "manifest.jsonl"
    inventory_path = run_dir / "inventory.jsonl"
    errors: list[str] = []
    counts: Counter[str] = Counter()
    origins: Counter[str] = Counter()
    suffixes: Counter[str] = Counter()
    modules: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0, "symbols": 0})

    with manifest_path.open("w", encoding="utf-8", newline="\n") as manifest_out, inventory_path.open("w", encoding="utf-8", newline="\n") as inventory_out:
        for rel, origin in candidates:
            action, reason = classify(rel)
            source = root / Path(rel)
            record: dict[str, Any] = {"path": rel, "origin": origin, "action": action, "reason": reason}
            origins[origin] += 1
            suffixes[Path(rel).suffix.lower() or "<none>"] += 1
            if not source.exists():
                record.update({"action": "skip", "reason": "tracked path absent from working tree", "exists": False})
                counts["skip"] += 1
                manifest_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue
            record["exists"] = True
            record["size_bytes"] = source.stat().st_size
            if action != "capture":
                counts[action] += 1
                manifest_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            # The only open/read of this live source path in the entire run.
            with source.open("rb") as source_file:
                raw = source_file.read()
            digest = hashlib.sha256(raw).hexdigest()
            try:
                text = raw.decode("utf-8-sig")
                encoding = "utf-8"
            except UnicodeDecodeError:
                try:
                    text = raw.decode("cp1252")
                    encoding = "cp1252"
                except UnicodeDecodeError as exc:
                    record.update({"action": "skip", "reason": f"text decode failed: {exc}", "sha256": digest})
                    counts["skip"] += 1
                    manifest_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    continue

            dest = snapshot_dir / Path(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as snapshot_file:
                snapshot_file.write(raw)
            facts = inventory(rel, text)
            line_count = len(text.splitlines())
            module = rel.split("/", 1)[0]
            symbol_count = len(facts.get("symbols", []))
            record.update({
                "sha256": digest,
                "encoding": encoding,
                "line_count": line_count,
                "snapshot": dest.relative_to(run_dir).as_posix(),
                "symbol_count": symbol_count,
            })
            manifest_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            inventory_out.write(json.dumps({"path": rel, **facts}, ensure_ascii=False) + "\n")
            counts["capture"] += 1
            modules[module]["files"] += 1
            modules[module]["lines"] += line_count
            modules[module]["symbols"] += symbol_count

    head = run_git(root, "rev-parse", "HEAD").decode().strip()
    branch = run_git(root, "branch", "--show-current").decode().strip()
    status = run_git(root, "status", "--short", "--untracked-files=all").decode("utf-8", "replace")
    (run_dir / "git-status.txt").write_text(status, encoding="utf-8", newline="\n")
    scope = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "head": head,
        "branch": branch,
        "tracked_count": len(tracked),
        "untracked_non_audit_count": len([p for p in untracked if not p.startswith(".audit/")]),
        "candidate_count": len(candidates),
        "counts": dict(counts),
        "origins": dict(origins),
        "suffixes": dict(suffixes),
        "modules": dict(sorted(modules.items())),
        "errors": errors,
        "scope_rule": "all git-tracked paths plus non-ignored untracked paths outside .audit/",
        "source_read_rule": "each captured live source path opened exactly once; later work reads snapshot only",
    }
    (run_dir / "scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / ".audit" / "CURRENT_RUN").write_text(run_id + "\n", encoding="ascii", newline="\n")

    summary = [
        f"# One-pass audit capture `{run_id}`",
        "",
        f"- HEAD: `{head}`",
        f"- Branch: `{branch}`",
        f"- Scope: {scope['scope_rule']}",
        f"- Candidates: {len(candidates)} ({len(tracked)} tracked + {scope['untracked_non_audit_count']} untracked non-audit)",
        f"- Captured once: {counts['capture']}",
        f"- Explicitly skipped: {counts['skip']}",
        f"- Excluded: {counts['exclude']}",
        "- `.audit/**` is excluded by construction because it is audit tooling, not repository product/research source.",
        "- Invariant: every captured live source was opened once; all later audit reads must target this run's `snapshot/`.",
        "",
        "## Captured top-level areas",
        "",
        "| Area | Files | Lines | Static symbols |",
        "|---|---:|---:|---:|",
    ]
    for module, values in sorted(modules.items()):
        summary.append(f"| `{module}` | {values['files']} | {values['lines']} | {values['symbols']} |")
    summary.extend(["", "## Dirty state at capture", "", "```text", status.rstrip(), "```", ""])
    (run_dir / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8", newline="\n")
    print(json.dumps(scope, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
