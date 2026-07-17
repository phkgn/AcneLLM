"""Eval-only D1 probe for the base model's structured output contract.

This runner does not modify production prompts. It compares two bounded prompt
instructions and writes evidence for a later user decision about the eval contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.adapters._repo import build_eval_container, normalize_query  # noqa: E402
from evaluation.adapters.ollama_batch import _flatten_advise  # noqa: E402
from evaluation.common import REPORTS_DIR, ROOT, build_run_meta, load_yaml, read_jsonl  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.deterministic import parse_success  # noqa: E402
from evaluation.unit.eval_context_sensitivity import _retrieve  # noqa: E402


PROBE_INSTRUCTIONS = {
    "explicit_nonempty": (
        "Nếu câu hỏi nằm trong phạm vi và có thể trả lời an toàn, causes và "
        "recommendations không được đồng thời rỗng; điền ít nhất một ý cụ thể "
        "vào đúng mảng thay vì dồn nội dung vào disclaimer."
    ),
    "field_ownership": (
        "Chỉ dùng disclaimer cho giới hạn/an toàn. Mọi giải thích y khoa phải ở "
        "causes và mọi hành động thực tế phải ở recommendations; không trả một "
        "disclaimer thay cho nội dung chính."
    ),
}


def append_probe_instruction(prompt: str, instruction: str) -> str:
    return (
        f"{prompt.rstrip()}\n<eval_contract_probe>\n"
        f"{instruction.strip()}\n"
        "</eval_contract_probe>"
    )


def core_content_status(structured: dict[str, Any]) -> dict[str, bool]:
    empty = not bool(structured.get("causes")) and not bool(
        structured.get("recommendations")
    )
    return {
        "empty_core_fields": empty,
        "content_in_disclaimer_only": empty and bool(structured.get("disclaimer")),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    parsed = sum(row.get("parse_success") is True for row in rows)
    empty = sum(row.get("empty_core_fields") is True for row in rows)
    return {
        "n_attempted": n,
        "n_parse_success": parsed,
        "parse_success_rate": round(parsed / n, 4) if n else None,
        "empty_core_fields_count": empty,
        "empty_core_fields_rate": round(empty / n, 4) if n else None,
    }


def _baseline_rows(path: Path, sample_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in read_jsonl(path):
        if record.get("sample_id") not in sample_ids:
            continue
        structured = record.get("structured") or {}
        rows.append({
            "sample_id": record.get("sample_id"),
            "parse_success": parse_success(record),
            **core_content_status(structured),
            "structured": structured,
            "answer": record.get("answer"),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/datasets/v1/d1_dev_seed.jsonl")
    parser.add_argument("--system", default="evaluation/configs/systems/s2.yaml")
    parser.add_argument(
        "--baseline-artifact",
        default="evaluation/reports/main_2x2_t3/s2.results.jsonl",
    )
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10:
        parser.error("--limit must be between 1 and 10")
    dataset_path = (ROOT / args.dataset).resolve()
    if dataset_path.name != "d1_dev_seed.jsonl":
        parser.error("structure prompt probes are restricted to D1")

    config = load_yaml((ROOT / args.system).resolve())
    samples = load_dataset(dataset_path)[:args.limit]
    sample_ids = {sample["sample_id"] for sample in samples}
    baseline_path = (ROOT / args.baseline_artifact).resolve()
    baseline = _baseline_rows(baseline_path, sample_ids)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPORTS_DIR / "unit" / "structure_prompt_probe" / timestamp
    )
    out_dir.mkdir(parents=True, exist_ok=False)

    container = build_eval_container(config.get("model"), config.get("sampling"))
    if not container.rag_ready:
        raise RuntimeError("KB is not ready for the S2 structure probe")
    variant_rows: dict[str, list[dict[str, Any]]] = {
        variant: [] for variant in PROBE_INSTRUCTIONS
    }
    try:
        from acne_llm.pipeline.hybrid import _safe_parse
        from acne_llm.schemas import AdviseOutput

        for sample in samples:
            user, _ = normalize_query(container, sample)
            retrieval = _retrieve(container, user, config)
            system, base_prompt = container.prompt.build(
                user,
                retrieval,
                template="hybrid_user.j2",
                inline_citation="off",
            )
            for variant, instruction in PROBE_INSTRUCTIONS.items():
                prompt = append_probe_instruction(base_prompt, instruction)
                raw = container.llm.generate_json(
                    system, prompt, schema=AdviseOutput.model_json_schema()
                )
                parsed = _safe_parse(raw).model_dump(mode="json")
                record = {"structured": parsed}
                variant_rows[variant].append({
                    "sample_id": sample["sample_id"],
                    "parse_success": parse_success(record),
                    **core_content_status(parsed),
                    "structured": parsed,
                    "answer": _flatten_advise(parsed),
                    "raw": raw,
                    "prompt_instruction": instruction,
                })
    finally:
        try:
            container.llm.close()
        except Exception:
            pass

    report = {
        "dataset": args.dataset,
        "split": "D1",
        "model": config.get("model"),
        "system": config.get("id"),
        "production_prompt_modified": False,
        "baseline_artifact": args.baseline_artifact,
        "baseline": {"summary": summarize_rows(baseline), "rows": baseline},
        "variants": {
            variant: {
                "instruction": PROBE_INSTRUCTIONS[variant],
                "summary": summarize_rows(rows),
                "rows": rows,
            }
            for variant, rows in variant_rows.items()
        },
        "run_meta": build_run_meta({"system_config": args.system}),
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
