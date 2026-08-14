"""One-command orchestrator for Unified Intake datagen.

The CLI deliberately has no implicit full mode.  A caller must choose exactly
one of ``--smoke``, ``--limit N``, or ``--full``.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import random
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .anchor import anchor_sha256, assert_parity
from .config import CASE_TYPE_TARGETS, Config, compute_budget
from .gates import CorpusGateState, evaluate_record, validate_corpus
from .generator import (
    CaseSpec,
    OpenAIGenerator,
    build_gen_prompt,
    load_taxonomy,
    synthesize_seed,
    to_record,
    user_turn_hash,
)
from .schema import build_json_schema
from .seed import load_relabelled_seeds
from .writer import DatasetWriter, iter_jsonl, write_jsonl

logger = logging.getLogger("datagen.intakedata")


def setup_logging(cfg: Config, verbose: bool = False) -> None:
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(cfg.log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    provider_logger = logging.getLogger("datagen.intakedata.generator")
    provider_logger.handlers.clear()
    provider_logger.setLevel(logger.level)
    provider_logger.propagate = True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _mode_and_targets(args: argparse.Namespace) -> tuple[str, dict[str, int]]:
    if args.smoke:
        return "smoke", {case: 1 for case in CASE_TYPE_TARGETS}
    if args.limit is not None:
        return "limit", compute_budget(args.limit)
    if args.full:
        return "full", dict(CASE_TYPE_TARGETS)
    raise ValueError("Choose one mode: --smoke, --limit N, or --full")


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    messages = record["messages"]
    value = json.loads(messages[-1]["content"])
    if not isinstance(value, dict):
        raise ValueError("assistant payload is not an object")
    return value


def _case_type(record: Mapping[str, Any]) -> str:
    meta = record.get("meta")
    return str(meta.get("case_type")) if isinstance(meta, Mapping) else ""


def _audit_entry(
    *,
    mode: str,
    status: str,
    record: Mapping[str, Any] | None = None,
    reasons: Iterable[str] = (),
    source: str | None = None,
    attempt: int | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "time": _utc_now(),
        "mode": mode,
        "status": status,
        "reasons": list(reasons),
    }
    if record is not None:
        entry["id"] = record.get("id")
        entry["case_type"] = _case_type(record)
        meta = record.get("meta")
        if isinstance(meta, Mapping):
            entry["source"] = meta.get("source")
    elif source is not None:
        entry["source"] = source
    if attempt is not None:
        entry["attempt"] = attempt
    if error is not None:
        entry["error_type"] = type(error).__name__
        entry["error"] = str(error)[:500]
    return entry


def _load_existing_state(
    records: list[dict[str, Any]],
    anchor: str,
    targets: Mapping[str, int],
    evaluation_hashes: set[str] = frozenset(),
) -> tuple[CorpusGateState | None, list[str]]:
    state = CorpusGateState(anchor)
    problems: list[str] = []
    for record in records:
        if _is_eval_overlap(record, evaluation_hashes):
            continue
        result = evaluate_record(record, state)
        if not result.passed:
            problems.append(
                f"existing id={record.get('id')} failed: {','.join(result.reasons)}"
            )
            continue
        payload = _payload(record)
        state.accept(record, payload)
    for case, count in state.case_counts.items():
        target = targets.get(case, 0)
        if count > target:
            problems.append(
                f"existing case {case} has {count} rows, above this mode target {target}"
            )
    return (state if not problems else None), problems


def _accept_record(
    record: dict[str, Any],
    *,
    state: CorpusGateState,
    writer: DatasetWriter,
    mode: str,
    evaluation_hashes: set[str] = frozenset(),
) -> tuple[bool, list[str]]:
    if _is_eval_overlap(record, evaluation_hashes):
        writer.audit(
            _audit_entry(
                mode=mode,
                status="reject",
                record=record,
                reasons=["eval_overlap"],
            )
        )
        return False, ["eval_overlap"]
    result = evaluate_record(record, state)
    if not result.passed:
        writer.audit(
            _audit_entry(
                mode=mode,
                status="reject",
                record=record,
                reasons=result.reasons,
            )
        )
        return False, result.reasons

    record["meta"]["judged"] = True
    record["meta"]["gate_checks"] = result.checks
    if not writer.append(record):
        reasons = ["duplicate_id"]
        writer.audit(
            _audit_entry(
                mode=mode,
                status="reject",
                record=record,
                reasons=reasons,
            )
        )
        return False, reasons
    payload = _payload(record)
    state.accept(record, payload)
    writer.audit(_audit_entry(mode=mode, status="accept", record=record))
    return True, []


async def _generate_slot(
    *,
    case: CaseSpec,
    ordinal: int,
    cfg: Config,
    anchor: str,
    provider: Any,
    writer: DatasetWriter,
    state: CorpusGateState,
    mode: str,
    evaluation_hashes: set[str] = frozenset(),
) -> tuple[bool, int, Counter[str]]:
    rejected = 0
    reject_reasons: Counter[str] = Counter()
    for attempt in range(1, int(cfg.max_content_attempts) + 1):
        rng = random.Random(f"{cfg.seed}:{case.case_type}:{ordinal}:{attempt}")
        seed = synthesize_seed(case.case_type, rng)
        prompt = build_gen_prompt(case, seed)
        try:
            generated = await provider.generate(prompt)
            record = to_record(
                case,
                generated,
                anchor,
                source=f"openai:{cfg.model}",
                seed=seed,
            )
            accepted, reasons = _accept_record(
                record,
                state=state,
                writer=writer,
                mode=mode,
                evaluation_hashes=evaluation_hashes,
            )
            if accepted:
                return True, rejected, reject_reasons
            rejected += 1
            reject_reasons.update(reasons)
            logger.warning(
                "Candidate rejected case=%s ordinal=%d attempt=%d/%d reasons=%s",
                case.case_type,
                ordinal,
                attempt,
                cfg.max_content_attempts,
                ",".join(reasons),
            )
        except Exception as exc:
            rejected += 1
            reason = f"candidate_error:{type(exc).__name__}"
            reject_reasons[reason] += 1
            writer.audit(
                _audit_entry(
                    mode=mode,
                    status="error",
                    source=f"openai:{cfg.model}",
                    reasons=[reason],
                    attempt=attempt,
                    error=exc,
                )
            )
            logger.warning(
                "Candidate error case=%s ordinal=%d attempt=%d/%d type=%s detail=%s",
                case.case_type,
                ordinal,
                attempt,
                cfg.max_content_attempts,
                type(exc).__name__,
                str(exc)[:180],
            )
    return False, rejected, reject_reasons


def _eval_user_hashes(paths: Iterable[Path]) -> set[str]:
    hashes: set[str] = set()
    candidates: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.is_file() and path.suffix == ".jsonl":
            candidates.append(path)
        elif path.is_dir():
            candidates.extend(path.rglob("*.jsonl"))
    for path in candidates:
        try:
            rows = iter_jsonl(path)
            for row in rows:
                for key in ("text", "user_query", "query", "input", "question"):
                    value = row.get(key)
                    if isinstance(value, str) and value.strip():
                        hashes.add(user_turn_hash(value))
                messages = row.get("messages")
                if isinstance(messages, list):
                    for message in messages:
                        if (
                            isinstance(message, Mapping)
                            and message.get("role") == "user"
                            and isinstance(message.get("content"), str)
                        ):
                            hashes.add(user_turn_hash(message["content"]))
        except (OSError, ValueError):
            continue
    return hashes


def _contamination_count(
    records: Iterable[dict[str, Any]], evaluation_hashes: set[str]
) -> int:
    count = 0
    for record in records:
        messages = record.get("messages")
        if not isinstance(messages, list):
            continue
        user_turn = next(
            (
                message.get("content", "")
                for message in reversed(messages[:-1])
                if isinstance(message, Mapping) and message.get("role") == "user"
            ),
            "",
        )
        if isinstance(user_turn, str) and user_turn_hash(user_turn) in evaluation_hashes:
            count += 1
    return count


def _record_user_turn(record: Mapping[str, Any]) -> str:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages[:-1]):
        if isinstance(message, Mapping) and message.get("role") == "user":
            content = message.get("content", "")
            return content if isinstance(content, str) else ""
    return ""


def _is_eval_overlap(record: Mapping[str, Any], evaluation_hashes: set[str]) -> bool:
    if not evaluation_hashes:
        return False
    user_turn = _record_user_turn(record)
    return bool(user_turn) and user_turn_hash(user_turn) in evaluation_hashes


def _purge_contaminated(records_path: Path, evaluation_hashes: set[str]) -> int:
    """One-time cleanup: drop existing records whose user_turn leaks into eval."""
    if not evaluation_hashes or not records_path.is_file():
        return 0
    rows = list(iter_jsonl(records_path))
    clean = [row for row in rows if not _is_eval_overlap(row, evaluation_hashes)]
    purged = len(rows) - len(clean)
    if purged:
        write_jsonl(records_path, clean)
    return purged


def _val_allocations(
    groups: Mapping[str, list[dict[str, Any]]], total_val: int
) -> dict[str, int]:
    total = sum(len(rows) for rows in groups.values())
    if total == 0 or total_val == 0:
        return {case: 0 for case in groups}
    exact = {case: total_val * len(rows) / total for case, rows in groups.items()}
    allocation = {case: min(len(groups[case]), int(value)) for case, value in exact.items()}
    remaining = total_val - sum(allocation.values())
    order = {case: index for index, case in enumerate(CASE_TYPE_TARGETS)}
    ranked = sorted(
        groups,
        key=lambda case: (
            -(exact[case] - allocation[case]),
            order.get(case, len(order)),
        ),
    )
    for case in ranked:
        if remaining <= 0:
            break
        if allocation[case] < len(groups[case]):
            allocation[case] += 1
            remaining -= 1
    return allocation


def split_records(
    records: list[dict[str, Any]], cfg: Config
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic case-aware 90/10 split."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(_case_type(record), []).append(record)
    for rows in groups.values():
        rows.sort(
            key=lambda record: hashlib.sha256(
                f"{cfg.seed}:{record.get('id')}".encode("utf-8")
            ).hexdigest()
        )
    total_val = int(len(records) * 0.1 + 0.5)
    if len(records) > 1:
        total_val = max(1, total_val)
    allocations = _val_allocations(groups, total_val)

    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for case in CASE_TYPE_TARGETS:
        rows = groups.get(case, [])
        val_count = allocations.get(case, 0)
        val.extend(rows[:val_count])
        train.extend(rows[val_count:])
    train.sort(key=lambda record: str(record.get("id")))
    val.sort(key=lambda record: str(record.get("id")))
    return train, val


async def run_pipeline(
    args: argparse.Namespace,
    *,
    cfg: Config | None = None,
    provider_factory: Callable[[Config], Any] = OpenAIGenerator,
) -> int:
    cfg = cfg or Config()
    if getattr(args, "concurrency", None) is not None:
        cfg = replace(cfg, concurrency=args.concurrency)
    setup_logging(cfg, args.verbose)

    if not args.yes:
        logger.error("Refusing to start without --yes.")
        return 2
    if args.limit is not None and args.limit <= 0:
        logger.error("--limit must be greater than zero.")
        return 2
    try:
        mode, targets = _mode_and_targets(args)
    except (TypeError, ValueError) as exc:
        logger.error("%s", exc)
        return 2

    logger.info(
        "Preflight started mode=%s provider=OpenAI model=%s base_url=%s",
        mode,
        cfg.model,
        cfg.base_url,
    )
    problems = cfg.validate(require_api_key=True)
    if problems:
        for problem in problems:
            logger.error("Preflight configuration error: %s", problem)
        return 2
    try:
        anchor = assert_parity(cfg)
        cases = load_taxonomy(cfg)
        schema = build_json_schema()
        if schema.get("additionalProperties") is not False:
            raise ValueError("Constrained schema must forbid extra root properties")
    except Exception as exc:
        logger.error("Preflight invariant failed: %s", exc)
        return 2
    anchor_hash = anchor_sha256(anchor)
    logger.info(
        "Anchor/schema parity OK sha256=%s cases=%d target=%d",
        anchor_hash,
        len(cases),
        sum(targets.values()),
    )

    records_path = cfg.records_path(mode, args.limit)
    evaluation_hashes = _eval_user_hashes(cfg.evaluation_paths or ())
    purged = _purge_contaminated(records_path, evaluation_hashes)
    if purged:
        logger.info(
            "Purged eval-contaminated existing records=%d (will be refilled clean)",
            purged,
        )
    existing = list(iter_jsonl(records_path))
    state, resume_problems = _load_existing_state(
        existing, anchor, targets, evaluation_hashes
    )
    if state is None:
        for problem in resume_problems:
            logger.error("Resume re-audit failed: %s", problem)
        return 2
    assert state is not None
    logger.info(
        "Resume state records=%d remaining=%d",
        len(existing),
        max(0, sum(targets.values()) - len(existing)),
    )

    provider = provider_factory(cfg)
    started = time.monotonic()
    new_accepted = 0
    rejected_attempts = 0
    reject_reasons: Counter[str] = Counter()
    relabel_rejected: Counter[str] = Counter()
    topup_rounds = 0
    try:
        try:
            await provider.probe()
            logger.info("OpenAI provider probe OK model=%s", cfg.model)
        except Exception as exc:
            logger.error("OpenAI provider probe failed: %s: %s", type(exc).__name__, exc)
            return 2

        with DatasetWriter(records_path, cfg.audit_path) as writer:
            use_seed = not args.no_seed and mode != "smoke"
            if use_seed:
                seed_records, relabel_rejected = load_relabelled_seeds(
                    cfg.golden_path, anchor
                )
                logger.info(
                    "Golden relabel ready accepted=%d rejected=%d",
                    len(seed_records),
                    sum(relabel_rejected.values()),
                )
                for record in seed_records:
                    case = _case_type(record)
                    if state.case_counts.get(case, 0) >= targets.get(case, 0):
                        continue
                    accepted, reasons = _accept_record(
                        record,
                        state=state,
                        writer=writer,
                        mode=mode,
                        evaluation_hashes=evaluation_hashes,
                    )
                    if accepted:
                        new_accepted += 1
                    else:
                        rejected_attempts += 1
                        reject_reasons.update(reasons)
                writer.audit(
                    {
                        "time": _utc_now(),
                        "mode": mode,
                        "status": "seed_relabel_summary",
                        "accepted_pool": len(seed_records),
                        "rejected_rows": sum(relabel_rejected.values()),
                        "reject_reasons": dict(relabel_rejected),
                    }
                )
                logger.info(
                    "Seed fill complete corpus=%d/%d",
                    sum(state.case_counts.values()),
                    sum(targets.values()),
                )

            by_case = {case.case_type: case for case in cases}
            for topup_round in range(1, int(cfg.max_topup_rounds) + 1):
                slots: list[tuple[CaseSpec, int]] = []
                for case_type, target in targets.items():
                    current = state.case_counts.get(case_type, 0)
                    for ordinal in range(current + 1, target + 1):
                        slots.append((by_case[case_type], ordinal))
                if not slots:
                    break
                topup_rounds = topup_round
                logger.info(
                    "Generation/top-up round=%d/%d pending=%d corpus=%d target=%d",
                    topup_round,
                    cfg.max_topup_rounds,
                    len(slots),
                    sum(state.case_counts.values()),
                    sum(targets.values()),
                )
                for offset in range(0, len(slots), int(cfg.concurrency)):
                    batch = slots[offset : offset + int(cfg.concurrency)]
                    results = await asyncio.gather(
                        *[
                            _generate_slot(
                                case=case,
                                ordinal=ordinal,
                                cfg=cfg,
                                anchor=anchor,
                                provider=provider,
                                writer=writer,
                                state=state,
                                mode=mode,
                                evaluation_hashes=evaluation_hashes,
                            )
                            for case, ordinal in batch
                        ]
                    )
                    for (case, _), (accepted, rejected, reasons) in zip(batch, results):
                        new_accepted += int(accepted)
                        rejected_attempts += rejected
                        reject_reasons.update(reasons)
                        corpus_count = sum(state.case_counts.values())
                        if (
                            corpus_count % int(cfg.progress_every) == 0
                            or not accepted
                        ):
                            logger.info(
                                "Progress case=%s accept=%d/%d reject=%d elapsed=%.1fs",
                                case.case_type,
                                corpus_count,
                                sum(targets.values()),
                                rejected_attempts,
                                time.monotonic() - started,
                            )
    finally:
        try:
            await provider.close()
        except Exception as exc:  # pragma: no cover - close failure is non-fatal
            logger.warning("Provider close failed: %s", type(exc).__name__)

    records = list(iter_jsonl(records_path))
    validation = validate_corpus(
        records,
        anchor,
        targets,
        enforce_intent_floor=mode == "full",
    )
    exact_targets = all(
        validation["case_counts"].get(case, 0) == target
        for case, target in targets.items()
    )
    complete = (
        exact_targets
        and validation["duplicate_ids"] == 0
        and validation["parity_ok"]
        and not validation["gate_failures"]
        and not validation["case_deficits_below_90pct"]
        and not validation["intent_floor_failures"]
    )

    train, val = split_records(records, cfg)
    write_jsonl(cfg.train_path, train)
    write_jsonl(cfg.val_path, val)
    eval_hashes = evaluation_hashes
    overlaps = _contamination_count(records, eval_hashes)
    if overlaps:
        logger.warning(
            "Evaluation contamination warning: exact_user_turn_overlaps=%d", overlaps
        )
    else:
        logger.info("Evaluation contamination clean: exact_user_turn_overlaps=0")

    summary = {
        "status": "complete" if complete else "incomplete",
        "mode": mode,
        "full_run_performed": mode == "full",
        "target": sum(targets.values()),
        "accepted": len(records),
        "new_accepted": new_accepted,
        "rejected_attempts": rejected_attempts,
        "topup_rounds": topup_rounds,
        "case_targets": targets,
        "case_counts": validation["case_counts"],
        "intent_counts": validation["intent_counts"],
        "reject_reasons": dict(reject_reasons),
        "seed_relabel_reject_reasons": dict(relabel_rejected),
        "anchor_sha256": anchor_hash,
        "schema_version": "unified-intake-v1",
        "validation": validation,
        "split": {"train": len(train), "val": len(val), "ratio": "90/10"},
        "evaluation_user_hashes": len(eval_hashes),
        "evaluation_exact_overlaps": overlaps,
        "records_path": str(records_path),
        "train_path": str(cfg.train_path),
        "val_path": str(cfg.val_path),
        "audit_path": str(cfg.audit_path),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "finished_at": _utc_now(),
    }
    _write_json(cfg.summary_path, summary)
    logger.info(
        "Post-validate status=%s records=%d unique_ids=%d train=%d val=%d "
        "parity=%s anchor_sha256=%s",
        summary["status"],
        validation["records"],
        validation["unique_ids"],
        len(train),
        len(val),
        validation["parity_ok"],
        anchor_hash,
    )
    return 0 if complete else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--smoke", action="store_true", help="Generate one provider record per case"
    )
    mode.add_argument(
        "--limit", type=int, help="Create/resume a bounded N-record corpus"
    )
    mode.add_argument(
        "--full", action="store_true", help="Explicitly create/resume all 4,000 records"
    )
    parser.add_argument("--yes", action="store_true", help="Confirm provider calls")
    parser.add_argument(
        "--no-seed", action="store_true", help="Skip golden relabel before generation"
    )
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_pipeline(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted; append-only output is safe to resume.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
