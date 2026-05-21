"""Generate ~6k injection / out-of-scope / abuse / safety cases via DeepSeek
and append to the same `acne_chat_response.jsonl` (cùng format).

Usage examples (run from project root):

    # Smoke test 50 cases:
    python -m LLMData.injection_qa.main --target 50 --concurrency 4

    # Production: top up to 6000 injection cases (counts existing ones in output):
    python -m LLMData.injection_qa.main --target 6000 --concurrency 8

    # Skip rule filter to inspect raw output:
    python -m LLMData.injection_qa.main --target 100 --skip-rules

    # Only emit curated seed bank (no API calls):
    python -m LLMData.injection_qa.main --only-curated

The script:
  1. Counts how many injection-style records already exist in the output file
     (any case_type in INJECTION_CASE_TYPES).
  2. Always emits the curated seed bank first (dedup by id handles re-runs).
  3. Loops DeepSeek calls per kind until the total reaches --target.

All records use:
  - sample_type = "injection_safety"   (separate from "clinical_chat_response")
  - case_type   = the specific injection kind
  - same `messages` shape (system / user / assistant) as clinical samples.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from collections import Counter
from pathlib import Path

from LLMData.chunk_qa.config import Config
from LLMData.chunk_qa.generator import make_deepseek_client
from LLMData.chunk_qa.rule_filter import apply_rules
from LLMData.chunk_qa.writer import DatasetWriter, build_record, load_existing_ids

from .injection_cases import (
    INJECTION_CASE_TYPES,
    OUT_OF_SCOPE_KINDS,
    INJECTION_KINDS,
    ABUSE_KINDS,
    MEDICAL_SAFETY_KINDS,
    HARMFUL_KINDS,
    DATA_EXFIL_KINDS,
    build_curated_injection_samples,
    generate_injection_batch,
)


SAMPLE_TYPE = "injection_safety"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AcneLLM injection / out-of-scope / abuse case generator",
    )
    p.add_argument("--target", type=int, default=6000,
                   help="Total injection samples to have in the output. Default 6000.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output JSONL path. Default: data/finetune/acne_chat_response.jsonl")
    p.add_argument("--concurrency", type=int, default=8,
                   help="Concurrent DeepSeek calls. Default 8.")
    p.add_argument("--batch-size", type=int, default=10,
                   help="Items per DeepSeek call. Default 10.")
    p.add_argument("--max-iters", type=int, default=400,
                   help="Safety cap on outer loop iterations. Default 400.")
    p.add_argument("--skip-rules", action="store_true",
                   help="Skip the rule-based safety validator.")
    p.add_argument("--only-curated", action="store_true",
                   help="Only emit the curated seed bank, no DeepSeek calls.")
    p.add_argument("--no-curated", action="store_true",
                   help="Skip the curated seed bank.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _setup_logging(cfg: Config, verbose: bool) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = cfg.log_dir / "injection_qa.log"
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


def _build_config(args: argparse.Namespace) -> Config:
    cfg = Config()
    if args.output is not None:
        cfg.output_jsonl = args.output
    if args.concurrency is not None:
        cfg.concurrency = max(1, args.concurrency)
    return cfg


# ---------------------------------------------------------------------------
# Output counting
# ---------------------------------------------------------------------------

def _count_injection_in_output(path: Path) -> dict[str, int]:
    """Returns counts per case_type for injection records already written.

    A record counts as 'injection' if its metadata.sample_type == SAMPLE_TYPE
    OR if its metadata.case_type ∈ INJECTION_CASE_TYPES (covers older runs
    without the dedicated sample_type).
    """
    counts: dict[str, int] = {k: 0 for k in INJECTION_CASE_TYPES}
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
            meta = obj.get("metadata") or {}
            ct = meta.get("case_type") or ""
            st = meta.get("sample_type") or ""
            if ct in counts and (st == SAMPLE_TYPE or ct in INJECTION_CASE_TYPES):
                counts[ct] += 1
    return counts


# ---------------------------------------------------------------------------
# Writing helpers
# ---------------------------------------------------------------------------

async def _emit_items(
    items: list[dict],
    args: argparse.Namespace,
    writer: DatasetWriter,
    counters: Counter,
) -> int:
    written = 0
    for item in items:
        case_type = item.get("case_type", "injection_safety")
        if not args.skip_rules:
            rule_res = apply_rules(
                item["assistant_answer"],
                item["raw_user_message"],
                item["normalized_case"],
            )
        else:
            rule_res = {"passed": True, "reasons": []}

        if not rule_res["passed"]:
            counters[f"rule_rejected::{case_type}"] += 1
            for r in rule_res["reasons"]:
                counters[f"rule_reason::{r}"] += 1
            continue

        record = build_record(
            item,
            sample_type=SAMPLE_TYPE,
            source_chunk=None,
            rule_filter={
                "passed": rule_res["passed"],
                "reason": "; ".join(rule_res["reasons"]) if rule_res["reasons"] else "",
            },
        )
        if writer.write(record):
            written += 1
            counters[f"written::{case_type}"] += 1
        else:
            counters["dedup_skipped"] += 1
    return written


# ---------------------------------------------------------------------------
# Top-up loop
# ---------------------------------------------------------------------------

async def _topup_loop(
    cfg: Config,
    args: argparse.Namespace,
    writer: DatasetWriter,
    counters: Counter,
) -> None:
    log = logging.getLogger("injection_qa.main")
    target = args.target
    batch = max(1, args.batch_size)
    max_iters = args.max_iters

    client = make_deepseek_client(cfg)
    sem = asyncio.Semaphore(cfg.concurrency)

    # Round-robin over kinds, weighted lightly so injection / abuse get
    # extra coverage (since they're the highest-risk targets).
    weighted_kinds: list[str] = []
    for k in OUT_OF_SCOPE_KINDS:
        weighted_kinds.extend([k] * 2)
    for k in INJECTION_KINDS:
        weighted_kinds.extend([k] * 3)
    for k in ABUSE_KINDS:
        weighted_kinds.extend([k] * 2)
    for k in MEDICAL_SAFETY_KINDS:
        weighted_kinds.extend([k] * 2)
    for k in HARMFUL_KINDS:
        weighted_kinds.extend([k] * 2)
    for k in DATA_EXFIL_KINDS:
        weighted_kinds.extend([k] * 1)

    async def _runner(kind: str) -> int:
        async with sem:
            items = await generate_injection_batch(client, cfg, kind, batch)
            return await _emit_items(items, args, writer, counters)

    for it in range(max_iters):
        counts = _count_injection_in_output(cfg.output_jsonl)
        current = sum(counts.values())
        if current >= target:
            log.info("Target reached: %d >= %d after %d iterations.",
                     current, target, it)
            return

        remaining = target - current
        # Number of parallel kinds to launch this iteration.
        # We aim to roughly satisfy `remaining` with `batch` items each call,
        # but cap by concurrency * 4 to keep sane backpressure.
        n_calls = min(
            max(1, remaining // batch + 1),
            cfg.concurrency * 4,
        )
        kinds_to_fire = random.sample(
            weighted_kinds,
            k=min(n_calls, len(weighted_kinds)),
        )
        log.info(
            "Iter %d: have=%d, remaining=%d, firing %d calls (batch=%d) — kinds sample: %s",
            it, current, remaining, len(kinds_to_fire), batch,
            list(set(kinds_to_fire))[:8],
        )

        tasks = [asyncio.create_task(_runner(k)) for k in kinds_to_fire]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        wrote_this_iter = 0
        for r in results:
            if isinstance(r, Exception):
                log.warning("  one runner raised: %r", r)
                continue
            wrote_this_iter += int(r or 0)

        log.info("  iter %d wrote %d new samples.", it, wrote_this_iter)
        if wrote_this_iter == 0:
            log.warning("  no new samples this iter — backing off briefly.")
            await asyncio.sleep(3.0)

    log.warning("Hit max_iters=%d without reaching target=%d.", max_iters, target)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _amain() -> int:
    args = parse_args()
    cfg = _build_config(args)
    _setup_logging(cfg, args.verbose)
    log = logging.getLogger("injection_qa.main")

    log.info(
        "Config: output=%s, target=%d, deepseek_model=%s, concurrency=%d, batch=%d",
        cfg.output_jsonl, args.target, cfg.deepseek_model,
        cfg.concurrency, args.batch_size,
    )

    if not args.only_curated:
        problems = cfg.validate()
        # We don't need chunks.jsonl for this script, only the API key.
        fatal = [p for p in problems if p.startswith("DEEPSEEK_API_KEY")]
        if fatal:
            for p in fatal:
                log.error(p)
            return 2

    existing_ids = load_existing_ids(cfg.output_jsonl)
    log.info("Existing samples in output: %d (will dedup by id).", len(existing_ids))

    if cfg.output_jsonl.exists():
        existing_inj = _count_injection_in_output(cfg.output_jsonl)
        total_existing_inj = sum(existing_inj.values())
        log.info("Existing injection samples by case_type: total=%d, %s",
                 total_existing_inj, {k: v for k, v in existing_inj.items() if v})

    counters: Counter = Counter()
    with DatasetWriter(cfg.output_jsonl, dedup_ids=existing_ids) as writer:
        # Step 1: curated seeds
        if not args.no_curated:
            curated = build_curated_injection_samples()
            wrote = await _emit_items(curated, args, writer, counters)
            log.info("Curated seed bank written: %d (dedup may have filtered some).", wrote)

        # Step 2: top-up via DeepSeek
        if not args.only_curated:
            await _topup_loop(cfg, args, writer, counters)

    log.info("=== Run summary ===")
    for k in sorted(counters):
        log.info("  %s = %d", k, counters[k])

    if cfg.output_jsonl.exists():
        final_inj = _count_injection_in_output(cfg.output_jsonl)
        total_final_inj = sum(final_inj.values())
        log.info("Final injection samples by case_type: total=%d", total_final_inj)
        for k, v in sorted(final_inj.items(), key=lambda kv: -kv[1]):
            if v:
                log.info("  %s = %d", k, v)

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
