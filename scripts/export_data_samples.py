"""Export clean, stratified sample slices of AcneLLM datasets for inspection.

Outputs lightweight JSONL files plus SHA256SUMS.txt under ``data_samples/``
without redistributing embeddings, secrets, or full copyrighted texts.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_samples"
SEED = 42
KB_TEXT_MAX_CHARS = 500


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read UTF-8 JSONL lines into a list of dicts."""
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write dicts as compact UTF-8 JSONL."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _stratified_round_robin(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], Any],
    limit: int,
    rng: random.Random,
    priority_keys: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Sample up to ``limit`` items evenly across sorted strata."""
    buckets: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[key_fn(row)].append(row)

    for items in buckets.values():
        rng.shuffle(items)

    ordered_keys = sorted(buckets.keys(), key=str)
    if priority_keys:
        seen = set(priority_keys)
        ordered_keys = [k for k in priority_keys if k in buckets] + [
            k for k in ordered_keys if k not in seen
        ]

    selected: list[dict[str, Any]] = []
    idx_map = {k: 0 for k in ordered_keys}
    while len(selected) < limit:
        progressed = False
        for key in ordered_keys:
            idx = idx_map[key]
            items = buckets[key]
            if idx < len(items):
                selected.append(items[idx])
                idx_map[key] = idx + 1
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
    return selected


def export_kb_chunks(rng: random.Random) -> Path:
    """Export 20 stratified KB chunks without embeddings and with truncated text."""
    src = ROOT / "data" / "raw" / "chunks.jsonl"
    rows = [r for r in _read_jsonl(src) if r.get("source_type") != "unknown"]
    priority = [
        ("aad_guideline", "en"),
        ("nice_guideline", "en"),
        ("clinical_textbook", "vi"),
        ("clinical_textbook", "en"),
        ("vi_medical_site", "vi"),
        ("en_medical_site", "en"),
        ("pubmed_review", "en"),
        ("pubmed_review", "vi"),
        ("blog", "vi"),
        ("blog", "en"),
    ]
    picked = _stratified_round_robin(
        rows,
        key_fn=lambda r: (r.get("source_type"), r.get("language")),
        limit=20,
        rng=rng,
        priority_keys=priority,
    )

    cleaned: list[dict[str, Any]] = []
    for row in picked:
        text = str(row.get("text") or "")
        truncated = len(text) > KB_TEXT_MAX_CHARS
        snippet = text[:KB_TEXT_MAX_CHARS].rstrip() + "..." if truncated else text
        cleaned.append(
            {
                "chunk_id": row.get("chunk_id"),
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "source_name": row.get("source_name"),
                "source_type": row.get("source_type"),
                "trust_level": row.get("trust_level"),
                "language": row.get("language"),
                "categories": row.get("categories"),
                "position": row.get("position"),
                "text_len": row.get("text_len", len(text)),
                "text_truncated": truncated,
                "text": snippet,
            }
        )

    out_path = OUT_DIR / "kb_chunks_sample.jsonl"
    _write_jsonl(out_path, cleaned)
    return out_path


def _extract_intake_intent(row: dict[str, Any]) -> str:
    """Parse target intent from assistant JSON payload in intake records."""
    messages = row.get("messages") or []
    if messages:
        payload = json.loads(messages[-1]["content"])
        if "intent" in payload:
            return str(payload["intent"])
    return "unknown"


def export_intaker_samples(rng: random.Random) -> Path:
    """Export 20 stratified Unified Intaker records across all 4 intents and case types."""
    src = ROOT / "research" / "datagen" / "intakedata" / "output" / "intake" / "intake.records.jsonl"
    rows = _read_jsonl(src)
    by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_intent[_extract_intake_intent(row)].append(row)

    quotas = {"advise": 8, "knowledge": 4, "clarify": 4, "reject": 4}
    priority_cases = [
        "advise_negation_stopped",
        "advise_duration_convert",
        "advise_noaccent",
        "advise_mixed_vi_en",
        "advise_selfreport_rich",
        "advise_selfreport_simple",
        "advise_ambiguous_lowconf",
        "knowledge_product_trap",
        "knowledge_ingredient_compare",
        "knowledge_general",
        "clarify_vague",
        "clarify_followup_multiturn",
        "glue_greeting_thanks",
        "reject_unsafe_rx",
        "reject_ood",
        "reject_jailbreak_meta",
    ]

    picked: list[dict[str, Any]] = []
    for intent, quota in quotas.items():
        picked.extend(
            _stratified_round_robin(
                by_intent[intent],
                key_fn=lambda r: (r.get("meta") or {}).get("case_type", "unknown"),
                limit=quota,
                rng=rng,
                priority_keys=priority_cases,
            )
        )

    cleaned = [
        {
            "id": r.get("id"),
            "messages": r.get("messages"),
            "meta": r.get("meta"),
        }
        for r in picked
    ]
    out_path = OUT_DIR / "intaker_train_sample.jsonl"
    _write_jsonl(out_path, cleaned)
    return out_path


def export_generator_samples(rng: random.Random) -> Path:
    """Export 15 stratified Generator-v2 ShareGPT samples across rule/grounding families."""
    src = ROOT / "research" / "datagen" / "roledatav2" / "output" / "roledata.train.jsonl"
    rows = _read_jsonl(src)
    priority_kinds = [
        "R1_identity",
        "R2_depth_adaptation",
        "R3_nonjudgment",
        "R4_measured_empathy",
        "R5_natural_clarification",
        "R6_role_boundary",
        "R7_conversation_glue",
        "R8_meta_jailbreak",
        "R9_multiturn",
        "R10_special_population",
        "B1_grounded_role",
        "B2_missing_answer",
        "B3_irrelevant_chunk",
        "B4_conflicting_docs",
        "K1_knowledge_anchor",
    ]
    picked = _stratified_round_robin(
        rows,
        key_fn=lambda r: r.get("sample_kind", "unknown"),
        limit=15,
        rng=rng,
        priority_keys=priority_kinds,
    )

    cleaned = [
        {
            "id": r.get("id"),
            "sample_kind": r.get("sample_kind"),
            "input_style": r.get("input_style"),
            "messages": r.get("messages"),
            "gate_results": r.get("gate_results"),
            "gen_model": r.get("gen_model"),
        }
        for r in picked
    ]
    out_path = OUT_DIR / "generator_role_sample.jsonl"
    _write_jsonl(out_path, cleaned)
    return out_path


def export_calibration_samples(rng: random.Random) -> Path:
    """Export 15 human-calibration rows stratified by rating (1..5) and safety flags."""
    src = (
        ROOT
        / "research"
        / "evaluation"
        / "reports"
        / "calibration_rrr"
        / "sheet_rrr145_khang.jsonl"
    )
    rows = _read_jsonl(src)
    priority_strata = [
        (1, True),
        (2, True),
        (3, True),
        (4, False),
        (5, False),
        (1, False),
        (2, False),
        (3, False),
        (4, True),
        (5, True),
    ]
    picked = _stratified_round_robin(
        rows,
        key_fn=lambda r: (
            r.get("human_answer_quality"),
            bool(r.get("human_forbidden_violated"))
            or (r.get("human_incorrect_content") or 0) >= 3,
        ),
        limit=15,
        rng=rng,
        priority_keys=priority_strata,
    )
    picked.sort(key=lambda r: int(r.get("row_id", 0)))

    out_path = OUT_DIR / "eval_calibration_rrr_sample.jsonl"
    _write_jsonl(out_path, picked)
    return out_path


def write_sha256_sums(paths: list[Path]) -> Path:
    """Write SHA256SUMS.txt covering all generated sample JSONL files."""
    lines: list[str] = []
    for path in sorted(paths, key=lambda p: p.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    sums_path = OUT_DIR / "SHA256SUMS.txt"
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sums_path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    generated = [
        export_kb_chunks(rng),
        export_intaker_samples(rng),
        export_generator_samples(rng),
        export_calibration_samples(rng),
    ]
    sums_path = write_sha256_sums(generated)
    print(f"Exported {len(generated)} sample files + {sums_path.name} into {OUT_DIR}")


if __name__ == "__main__":
    main()
