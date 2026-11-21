"""Verify a current immutable one-pass audit snapshot with dynamic counts.

Unlike ``verify_and_close_coverage.py`` (the frozen gate for the 2026-08-22
run), this verifier derives every denominator from the selected run's own
scope, manifest and semantic proof.  It never reads live project source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()

    scope = json.loads((run / "scope.json").read_text(encoding="utf-8"))
    manifest = [
        json.loads(line)
        for line in (run / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    inventory = [
        json.loads(line)
        for line in (run / "inventory.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    proof_path = run / "semantic-complete-proof.json"
    if not proof_path.is_file():
        proof_path = run / "semantic-proof.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    warnings: list[str] = []
    actions = Counter(record.get("action") for record in manifest)
    captured = [record for record in manifest if record.get("action") == "capture"]
    skipped = [record for record in manifest if record.get("action") == "skip"]
    excluded = [record for record in manifest if record.get("action") == "exclude"]

    if len(manifest) != scope.get("candidate_count"):
        errors.append(
            f"manifest paths {len(manifest)} != scope candidate_count {scope.get('candidate_count')}"
        )
    if len({record.get("path") for record in manifest}) != len(manifest):
        errors.append("manifest contains duplicate paths")
    for action in ("capture", "skip", "exclude"):
        expected = scope.get("counts", {}).get(action, 0)
        if actions[action] != expected:
            errors.append(f"action {action}: manifest {actions[action]} != scope {expected}")
    if any(not record.get("reason") for record in skipped + excluded):
        errors.append("at least one skipped/excluded path has no explicit reason")

    captured_paths = {record["path"] for record in captured}
    inventory_paths = {record["path"] for record in inventory}
    if inventory_paths != captured_paths:
        errors.append(
            "inventory/capture path mismatch: "
            f"missing={len(captured_paths - inventory_paths)}, extra={len(inventory_paths - captured_paths)}"
        )

    missing_snapshots: list[str] = []
    hash_mismatches: list[str] = []
    for record in captured:
        snapshot_rel = record.get("snapshot")
        snapshot = run / snapshot_rel if snapshot_rel else run / "snapshot" / record["path"]
        if not snapshot.is_file():
            missing_snapshots.append(record["path"])
            continue
        if sha256_file(snapshot) != record.get("sha256"):
            hash_mismatches.append(record["path"])
    if missing_snapshots:
        errors.append(f"missing snapshots: {len(missing_snapshots)}")
    if hash_mismatches:
        errors.append(f"snapshot hash mismatches: {len(hash_mismatches)}")

    expected_proof = {
        "snapshot_files_read_once": len(captured),
        "manifest_captured_files": len(captured),
        "blocks": proof.get("blocks"),
        "items_required": int(proof.get("blocks", 0)) * 8,
        "items_filled": int(proof.get("blocks", 0)) * 8,
        "hash_mismatches": 0,
    }
    if proof != expected_proof:
        errors.append(f"semantic proof mismatch: {proof} != {expected_proof}")

    findings_dir = run / "FINDINGS_COMPLETE"
    if not findings_dir.is_dir():
        findings_dir = run / "FINDINGS_AUTO"
    sections: dict[str, str] = {}
    all_text_parts: list[str] = []
    for finding in findings_dir.glob("*.md"):
        if finding.name in {"INDEX.md", "ARCH_SYNTHESIS_EVIDENCE.md"}:
            continue
        text = finding.read_text(encoding="utf-8")
        all_text_parts.append(text)
        matches = list(re.finditer(r"^## `(.+?)`\s*$", text, re.MULTILINE))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            path = match.group(1)
            if path in sections:
                errors.append(f"duplicate finding section: {path}")
            sections[path] = text[match.start():end]

    if set(sections) != captured_paths:
        errors.append(
            "finding/capture path mismatch: "
            f"missing={len(captured_paths - set(sections))}, extra={len(set(sections) - captured_paths)}"
        )

    all_text = "\n".join(all_text_parts)
    block_count = len(re.findall(r"^### \[x\] ", all_text, re.MULTILINE))
    item_counts = Counter(
        int(match.group(1))
        for match in re.finditer(r"^([1-8])\. ", all_text, re.MULTILINE)
    )
    if block_count != proof.get("blocks"):
        errors.append(f"finding blocks {block_count} != proof {proof.get('blocks')}")
    for number in range(1, 9):
        if item_counts[number] != block_count:
            errors.append(f"item {number}: {item_counts[number]} != blocks {block_count}")
    if re.search(r"^### \[ \]|^\[ \]", all_text, re.MULTILINE):
        errors.append("open checkbox remains in final findings")

    parse_errors = [
        (record["path"], record.get("parse_error"))
        for record in inventory
        if record.get("parse_error")
    ]
    non_notebook_errors = [path for path, _ in parse_errors if not path.endswith(".ipynb")]
    if non_notebook_errors:
        errors.append(f"non-notebook parse errors: {len(non_notebook_errors)}")
    if parse_errors and not non_notebook_errors:
        warnings.append(f"notebook parse errors recorded explicitly: {len(parse_errors)}")

    result = "FAIL" if errors else "PASS"
    report = [
        "# Dynamic snapshot completion gate",
        "",
        f"- result: **{result}**",
        f"- run: `{scope.get('run_id')}`",
        f"- HEAD: `{scope.get('head')}`",
        f"- branch: `{scope.get('branch')}`",
        f"- manifest denominator: `{len(manifest)}`",
        f"- captured semantic files: `{len(captured)}`",
        f"- explicit skips: `{len(skipped)}`",
        f"- explicit audit-tool exclusions: `{len(excluded)}`",
        f"- inventory rows: `{len(inventory)}`",
        f"- snapshot files present: `{len(captured) - len(missing_snapshots)}`",
        f"- snapshot hash mismatches: `{len(hash_mismatches)}`",
        f"- finding file sections: `{len(sections)}`",
        f"- audited blocks: `{block_count}`",
        f"- filled 1-8 items: `{sum(item_counts.values())}`",
        f"- non-notebook parse errors: `{len(non_notebook_errors)}`",
        "",
    ]
    if warnings:
        report.extend(["## Warnings", "", *[f"- {item}" for item in warnings], ""])
    if errors:
        report.extend(["## Errors", "", *[f"- {item}" for item in errors], ""])
    else:
        report.extend([
            "The snapshot manifest, immutable copies, semantic findings and dynamic",
            "denominators agree. This gate proves static capture completeness for the",
            "selected checkout; it does not prove dynamic runtime reachability or clinical",
            "correctness.",
            "",
        ])

    output = "\n".join(report)
    (run / "SNAPSHOT_GATE.md").write_text(output, encoding="utf-8", newline="\n")
    print(output)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
