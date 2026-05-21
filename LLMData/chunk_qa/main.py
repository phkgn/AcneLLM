"""End-to-end pipeline for the clinical chat-response dataset.

Usage examples (run from project root):

    # Smoke test on 5 chunks (skip rules to inspect raw output):
    python -m LLMData.chunk_qa.main --limit 5 --skip-rules

    # Pilot 50 chunks:
    python -m LLMData.chunk_qa.main --limit 50

    # Generate ONLY safety samples up to a target (for top-up after a long run):
    python -m LLMData.chunk_qa.main --only-safety --safety-target 6400

    # Skip clinical phase, top-up safety to 6400 of EACH split (out-of-scope
    # vs clinical) — auto-balanced 50/50:
    python -m LLMData.chunk_qa.main --only-safety --safety-target 6400 --safety-balance

    # Full run (be careful — many API calls):
    python -m LLMData.chunk_qa.main
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from .config import Config
from .generator import generate_cases_for_chunk, make_deepseek_client
from .loader import iter_filtered_chunks, load_processed_chunk_ids
from .rule_filter import apply_rules
from .safety_cases import (
    CLINICAL_SAFETY_KINDS,
    OUT_OF_SCOPE_KINDS,
    SAFETY_CASE_TYPES,
    build_curated_safety_samples,
    generate_extra_safety_samples,
)
from .writer import DatasetWriter, build_record, load_existing_ids


# ---------------------------------------------------------------------------
# Logging / CLI plumbing
# ---------------------------------------------------------------------------

def _setup_logging(cfg: Config, verbose: bool) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = cfg.log_dir / "chunk_qa.log"
    level = logging.DEBUG if verbose else logging.INFO

    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(fmt))
    root.addHandler(sh)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AcneLLM clinical chat-response dataset generator",
    )
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most N chunks (after filter). Default: all.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output JSONL path. Default: data/finetune/acne_chat_response.jsonl")
    p.add_argument("--concurrency", type=int, default=None,
                   help="Concurrent DeepSeek calls. Default from config (3).")
    p.add_argument("--cases-per-chunk", type=int, default=None,
                   help="Number of clinical cases per chunk. Default from config (3).")
    p.add_argument("--qa-per-chunk", type=int, default=None,
                   dest="qa_per_chunk",
                   help="Alias of --cases-per-chunk (kept for backward compat).")
    p.add_argument("--skip-rules", action="store_true",
                   help="Skip the rule-based safety validator.")
    p.add_argument("--no-resume", action="store_true",
                   help="Ignore existing output file (still appends; just disables skip).")
    p.add_argument("--only-safety", action="store_true",
                   help="Only emit curated/synthetic safety samples (no chunks).")
    p.add_argument("--safety-extra", type=int, default=0,
                   help="Per safety kind, ask DeepSeek for N extra synthetic samples.")
    p.add_argument("--safety-target", type=int, default=0,
                   help=("Top-up safety samples until total >= N (counts ALL safety "
                         "case_types in the existing output, including curated). "
                         "Generates in batches via DeepSeek until target met."))
    p.add_argument("--safety-balance", action="store_true",
                   help=("Split --safety-target 50/50 between out-of-scope kinds "
                         "(out_of_domain/prompt_injection/abuse_extreme/medical_safety) "
                         "and clinical safety kinds."))
    p.add_argument("--safety-batch", type=int, default=10,
                   help="Per-kind batch size when topping up via --safety-target.")
    p.add_argument("--no-safety", action="store_true",
                   help="Skip emitting curated/synthetic safety samples.")
    p.add_argument("--skip-judge", action="store_true",
                   help="No-op (judge layer removed). Kept for backward compat.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _build_config(args: argparse.Namespace) -> Config:
    cfg = Config()
    if args.output is not None:
        cfg.output_jsonl = args.output
    if args.concurrency is not None:
        cfg.concurrency = max(1, args.concurrency)
    if args.cases_per_chunk is not None:
        cfg.cases_per_chunk = max(1, args.cases_per_chunk)
    elif args.qa_per_chunk is not None:
        cfg.cases_per_chunk = max(1, args.qa_per_chunk)
    return cfg


# ---------------------------------------------------------------------------
# Helpers — count existing safety samples in output (for --safety-target)
# ---------------------------------------------------------------------------

def _count_safety_in_output(path: Path) -> dict[str, int]:
    """Returns counts per case_type for safety records already written."""
    counts: dict[str, int] = {k: 0 for k in SAFETY_CASE_TYPES}
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ct = (obj.get("metadata") or {}).get("sample_type") or ""
            # We treat "sample_type" as the safety case_type when it's one
            # of the known SAFETY_CASE_TYPES; clinical_chat_response samples
            # are NOT counted toward the safety target.
            if ct in counts:
                counts[ct] += 1
    return counts


# ---------------------------------------------------------------------------
# Per-chunk worker
# ---------------------------------------------------------------------------


async def _process_one_chunk(
    cfg: Config,
    deepseek_client,
    chunk: dict,
    skip_rules: bool,
    writer: DatasetWriter,
    counters: Counter,
) -> None:
    items = await generate_cases_for_chunk(deepseek_client, cfg, chunk)
    if not items:
        counters["chunks_no_output"] += 1
        return
    counters["chunks_ok"] += 1

    for item in items:
        if skip_rules:
            rule_res = {"passed": True, "reasons": []}
        else:
            rule_res = apply_rules(
                item["assistant_answer"],
                item["raw_user_message"],
                item["normalized_case"],
            )
            if not rule_res["passed"]:
                counters["rule_rejected"] += 1
                for r in rule_res["reasons"]:
                    counters[f"rule_reason::{r}"] += 1
                continue

        record = build_record(
            item,
            sample_type="clinical_chat_response",
            source_chunk=chunk,
            rule_filter={
                "passed": rule_res["passed"],
                "reason": "; ".join(rule_res["reasons"]) if rule_res["reasons"] else "",
            },
        )
        if writer.write(record):
            counters["samples_written"] += 1
            counters[f"severity::{item.get('severity', 'unknown')}"] += 1
            counters[f"case_type::{item.get('case_type', 'general')}"] += 1
        else:
            counters["samples_dedup_skipped"] += 1


async def _run_chunks_phase(
    cfg: Config,
    args: argparse.Namespace,
    writer: DatasetWriter,
    counters: Counter,
) -> None:
    log = logging.getLogger("chunk_qa.main")

    if not args.no_resume:
        processed = load_processed_chunk_ids(cfg.output_jsonl)
        log.info(
            "Resume: %d chunks already produced clinical samples — skipping.",
            len(processed),
        )
    else:
        processed = set()

    deepseek_client = make_deepseek_client(cfg)
    sem = asyncio.Semaphore(cfg.concurrency)

    async def _runner(chunk: dict) -> None:
        async with sem:
            await _process_one_chunk(
                cfg, deepseek_client, chunk,
                skip_rules=args.skip_rules, writer=writer, counters=counters,
            )

    tasks: list[asyncio.Task] = []
    n_seen = 0
    for chunk in iter_filtered_chunks(cfg, processed_chunk_ids=processed):
        if args.limit is not None and n_seen >= args.limit:
            break
        n_seen += 1
        tasks.append(asyncio.create_task(_runner(chunk)))
        if len(tasks) >= max(50, cfg.concurrency * 4):
            await asyncio.gather(*tasks)
            tasks.clear()
            log.info(
                "Progress: chunks_processed=%d, samples_written=%d, "
                "chunks_no_output=%d, rule_rejected=%d",
                counters["chunks_ok"] + counters["chunks_no_output"],
                counters["samples_written"],
                counters["chunks_no_output"],
                counters["rule_rejected"],
            )
    if tasks:
        await asyncio.gather(*tasks)
    counters["chunks_seen"] = n_seen
    log.info("Chunk phase done: %d chunks attempted.", n_seen)


# ---------------------------------------------------------------------------
# Safety phase
# ---------------------------------------------------------------------------


async def _emit_safety_items(
    items: list[dict],
    args: argparse.Namespace,
    writer: DatasetWriter,
    counters: Counter,
) -> int:
    """Validate + write safety items. Returns # written."""
    written = 0
    for item in items:
        sample_type = item.get("case_type", "safety")
        if not args.skip_rules:
            rule_res = apply_rules(
                item["assistant_answer"],
                item["raw_user_message"],
                item["normalized_case"],
            )
        else:
            rule_res = {"passed": True, "reasons": []}

        if not rule_res["passed"]:
            counters[f"safety_rule_flag::{sample_type}"] += 1
            for r in rule_res["reasons"]:
                counters[f"rule_reason::{r}"] += 1
            continue

        record = build_record(
            item,
            sample_type=sample_type,
            source_chunk=None,
            rule_filter={
                "passed": rule_res["passed"],
                "reason": "; ".join(rule_res["reasons"]) if rule_res["reasons"] else "",
            },
        )
        if writer.write(record):
            written += 1
            counters[f"safety_written::{sample_type}"] += 1
        else:
            counters["samples_dedup_skipped"] += 1
    return written


async def _run_safety_phase(
    cfg: Config,
    args: argparse.Namespace,
    writer: DatasetWriter,
    counters: Counter,
) -> None:
    log = logging.getLogger("chunk_qa.main")

    # --- Step 1: curated seeds (always emit, dedup handles re-runs).
    curated_written = 0
    if not args.no_safety:
        curated = build_curated_safety_samples()
        curated_written = await _emit_safety_items(curated, args, writer, counters)
        log.info("Curated safety samples written: %d", curated_written)

    # --- Step 2: simple --safety-extra mode (per-kind fixed batch).
    if args.safety_extra > 0 and not args.no_safety:
        try:
            client = make_deepseek_client(cfg)
            extras = await generate_extra_safety_samples(
                client, cfg, n_per_kind=args.safety_extra,
            )
            extras_written = await _emit_safety_items(extras, args, writer, counters)
            log.info("DeepSeek-augmented safety (%d kinds × %d) written: %d",
                     len(SAFETY_CASE_TYPES), args.safety_extra, extras_written)
        except Exception as e:
            log.warning("Safety augmentation skipped: %s", e)

    # --- Step 3: --safety-target top-up loop.
    if args.safety_target > 0 and not args.no_safety:
        await _safety_target_topup(cfg, args, writer, counters)


async def _safety_target_topup(
    cfg: Config,
    args: argparse.Namespace,
    writer: DatasetWriter,
    counters: Counter,
) -> None:
    """Top up safety samples until total in output >= --safety-target.

    With --safety-balance, splits target 50/50 between OUT_OF_SCOPE_KINDS and
    CLINICAL_SAFETY_KINDS, otherwise distributes evenly across all kinds.
    """
    log = logging.getLogger("chunk_qa.main")
    target = args.safety_target
    batch_per_kind = max(1, args.safety_batch)
    max_iters = 200  # safety: avoid infinite loop on persistent failures

    client = make_deepseek_client(cfg)

    if args.safety_balance:
        # Split 50/50 between two pools.
        target_oos = target // 2
        target_clin = target - target_oos
        pools = [
            ("out_of_scope", OUT_OF_SCOPE_KINDS, target_oos),
            ("clinical_safety", CLINICAL_SAFETY_KINDS, target_clin),
        ]
    else:
        pools = [("all_safety", SAFETY_CASE_TYPES, target)]

    for pool_name, kinds, pool_target in pools:
        log.info("Safety pool '%s' target=%d, kinds=%s",
                 pool_name, pool_target, list(kinds))
        for it in range(max_iters):
            counts = _count_safety_in_output(cfg.output_jsonl)
            current_total = sum(counts[k] for k in kinds)
            if current_total >= pool_target:
                log.info("  pool='%s' reached target (%d >= %d) after %d iters.",
                         pool_name, current_total, pool_target, it)
                break
            remaining = pool_target - current_total
            log.info("  pool='%s' iter=%d: have=%d, remaining=%d — generating %d/kind",
                     pool_name, it, current_total, remaining, batch_per_kind)
            try:
                items = await generate_extra_safety_samples(
                    client, cfg,
                    n_per_kind=batch_per_kind,
                    kinds=tuple(kinds),
                )
            except Exception as e:
                log.warning("DeepSeek call failed during safety top-up: %s", e)
                items = []
            if not items:
                log.warning("  no items returned; sleeping briefly and retrying.")
                await asyncio.sleep(5.0)
                continue
            wrote = await _emit_safety_items(items, args, writer, counters)
            counters[f"safety_topup::{pool_name}::iter_{it}"] = wrote
            if wrote == 0:
                # All dedup'd or all rule-rejected. Avoid infinite loop.
                log.warning("  iter produced 0 new samples; stopping pool='%s'.", pool_name)
                break
        else:
            log.warning("  pool='%s' hit max_iters=%d without reaching target.",
                        pool_name, max_iters)


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


async def _amain() -> int:
    args = parse_args()
    cfg = _build_config(args)
    _setup_logging(cfg, args.verbose)
    log = logging.getLogger("chunk_qa.main")

    log.info(
        "Config: chunks=%s, output=%s, deepseek_model=%s, cases_per_chunk=%d",
        cfg.chunks_jsonl, cfg.output_jsonl, cfg.deepseek_model, cfg.cases_per_chunk,
    )

    problems = cfg.validate()
    needs_deepseek = (
        (not args.only_safety)
        or args.safety_extra > 0
        or args.safety_target > 0
    )
    fatal_problems = [
        p for p in problems
        if not (p.startswith("DEEPSEEK_API_KEY") and not needs_deepseek)
    ]
    if fatal_problems:
        for p in fatal_problems:
            log.error(p)
        return 2

    existing = load_existing_ids(cfg.output_jsonl)
    log.info("Existing samples in output: %d (will dedup by id).", len(existing))
    if cfg.output_jsonl.exists():
        existing_safety = _count_safety_in_output(cfg.output_jsonl)
        total_existing_safety = sum(existing_safety.values())
        log.info("Existing safety samples by case_type: total=%d, %s",
                 total_existing_safety, existing_safety)

    counters: Counter = Counter()
    with DatasetWriter(cfg.output_jsonl, dedup_ids=existing) as writer:
        if not args.only_safety:
            await _run_chunks_phase(cfg, args, writer, counters)
        await _run_safety_phase(cfg, args, writer, counters)

    log.info("=== Run summary ===")
    for k in sorted(counters):
        log.info("  %s = %d", k, counters[k])
    log.info("Output: %s", cfg.output_jsonl)
    return 0


def main() -> None:
    try:
        rc = asyncio.run(_amain())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
