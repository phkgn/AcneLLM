"""One-command orchestrator for bounded or full ROLE-data generation."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .anchor import anchor_sha256, assert_parity
from .config import CASE_TYPE_TARGETS, FULL_TARGET, Config, compute_budget
from .gates import CorpusGateState, evaluate_record
from .generator import (
    CaseSpec,
    OpenAIGenerator,
    build_gen_prompt,
    load_taxonomy,
    synthesize_context,
    planned_input_style,
    to_record,
)
from .writer import DatasetWriter, append_audit, iter_jsonl

logger = logging.getLogger("datagen.roledata")


def setup_logging(cfg: Config, verbose: bool = False) -> None:
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(cfg.log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Provider retry messages originate below datagen.roledata.generator.
    provider_logger = logging.getLogger("datagen.roledata.generator")
    provider_logger.handlers.clear()
    provider_logger.setLevel(logger.level)
    provider_logger.propagate = True


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _case_counts(records: Iterable[dict[str, Any]]) -> Counter[str]:
    return Counter(str(record.get("sample_kind")) for record in records)


def _extract_eval_user_texts(root: Path) -> list[str]:
    texts: list[str] = []
    if not root.is_dir():
        return texts
    for path in root.rglob("*.jsonl"):
        try:
            lines = path.open("r", encoding="utf-8")
        except OSError:
            continue
        with lines:
            for raw in lines:
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                query = row.get("user_query")
                if isinstance(query, str) and query.strip():
                    texts.append(query)
                history = row.get("conversation_history")
                if isinstance(history, list):
                    for turn in history:
                        if isinstance(turn, dict) and turn.get("role") == "user":
                            content = turn.get("content")
                            if isinstance(content, str) and content.strip():
                                texts.append(content)
                messages = row.get("messages")
                if isinstance(messages, list):
                    for turn in messages:
                        if isinstance(turn, dict) and turn.get("role") == "user":
                            content = turn.get("content")
                            if isinstance(content, str) and content.strip():
                                texts.append(content)
    return texts


def _contamination_stats(cfg: Config) -> tuple[int, int]:
    texts = _extract_eval_user_texts(cfg.evaluation_datasets_dir)
    ngrams: set[str] = set()
    for text in texts:
        words = text.casefold().split()
        for index in range(max(0, len(words) - cfg.phrase_ngram_size + 1)):
            ngrams.add(" ".join(words[index : index + cfg.phrase_ngram_size]))
    return len(texts), len(ngrams)


def _knowledge_sanity(cfg: Config, cases: list[CaseSpec]) -> None:
    grounded_case = next(case for case in cases if case.id == "K1_knowledge_anchor")
    context, sources, _ = synthesize_context(grounded_case, cfg, sequence=0)
    text = " ".join(item["text"] for item in context or [])
    if not sources or len(text) < 180 or not any(token in text.casefold() for token in ("mụn", "acne")):
        raise RuntimeError("Knowledge-source sanity failed: no usable grounded acne passage")


def _estimate_cost(cfg: Config, target: int) -> float:
    # Conservative planning estimate; real billing is provider telemetry's job.
    input_tokens = target * 3_200
    output_tokens = target * 550
    k1_extra = compute_budget(target)["K1_knowledge_anchor"] * 900
    return (
        (input_tokens + k1_extra) * cfg.input_price_per_million
        + output_tokens * cfg.output_price_per_million
    ) / 1_000_000


def _b5_pair_failures(
    records: list[dict[str, Any]], expected_counts: dict[str, int] | None
) -> list[dict[str, Any]]:
    expected = (expected_counts or {}).get("B5_depth_anchor", 0)
    if expected < 2:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record.get("sample_kind") != "B5_depth_anchor":
            continue
        group = str(record.get("anchor_group") or "")
        groups.setdefault(group, []).append(record)
    failures: list[dict[str, Any]] = []
    for group, rows in groups.items():
        depths = {str((row.get("generation_meta") or {}).get("depth")) for row in rows}
        source_sets = {
            tuple(str(value) for value in row.get("synthetic_context_sources") or [])
            for row in rows
        }
        users = {
            tuple(
                str(message.get("content", ""))
                for message in row.get("messages", [])
                if message.get("role") == "user"
            )
            for row in rows
        }
        if (
            not group
            or len(rows) != 2
            or depths != {"beginner", "advanced"}
            or len(source_sets) != 1
            or len(users) != 2
        ):
            failures.append(
                {
                    "id": group or "missing-anchor-group",
                    "reasons": ["anchor_pair_corpus"],
                }
            )
    return failures


def _post_validate(
    path: Path,
    anchor: str,
    cfg: Config,
    expected_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    records = list(iter_jsonl(path))
    ids = [record.get("id") for record in records]
    duplicate_ids = len(ids) - len(set(ids))
    corpus = CorpusGateState(cfg.phrase_ngram_size, cfg.phrase_max_occurrences)
    failures: list[dict[str, Any]] = []
    parity_ok = True
    for record in records:
        result = evaluate_record(record, anchor, corpus)
        if not result.passed:
            failures.append({"id": record.get("id"), "reasons": result.reasons})
        parity_ok = parity_ok and bool(result.checks.get("system_parity"))
    failures.extend(_b5_pair_failures(records, expected_counts))
    return {
        "records": len(records),
        "unique_ids": len(set(ids)),
        "duplicate_ids": duplicate_ids,
        "parity_ok": parity_ok,
        "gate_failures": failures,
    }


def _anchor_ok(record: dict[str, Any], anchor: str) -> bool:
    """System prompt của một bản ghi đã lưu có hợp lệ để resume không.

    Tách thành hàm riêng để v2 override được: v2 rải BA biến thể anchor trong
    cùng một dataset (xem `roledatav2/config.py::ANCHOR_VARIANT_PATHS`), nên phép
    so bằng một chuỗi duy nhất ở đây sẽ từ chối mọi bản ghi mang biến thể B hoặc
    C và làm resume chết. v1 chỉ có một anchor nên hành vi không đổi.
    """
    return record.get("messages", [{}])[0].get("content") == anchor


def _record_id(case_id: str, ordinal: int, smoke: bool) -> str:
    marker = "S" if smoke else ""
    return f"roledata-{case_id}-{marker}{ordinal:06d}"


def _checkpoint_targets(
    cfg: Config,
    existing_counts: Counter[str],
    limit: int,
    allowed_cases: set[str],
) -> dict[str, int]:
    checkpoint = _read_json(cfg.checkpoint_path)
    if checkpoint and checkpoint.get("limit") == limit:
        raw_targets = checkpoint.get("case_targets")
        if isinstance(raw_targets, dict):
            logger.info(
                "Resume checkpoint: limit=%d target_total=%d current=%d remaining=%d",
                limit,
                sum(int(value) for value in raw_targets.values()),
                sum(existing_counts.values()),
                max(0, sum(int(value) for value in raw_targets.values()) - sum(existing_counts.values())),
            )
            return {str(case): int(value) for case, value in raw_targets.items()}

    allocation = compute_budget(limit)
    if allowed_cases != set(CASE_TYPE_TARGETS):
        if len(allowed_cases) != 1:
            raise ValueError("only-case filtering must select exactly one case")
        selected = next(iter(allowed_cases))
        allocation = {case: (limit if case == selected else 0) for case in CASE_TYPE_TARGETS}
    targets = {
        case: existing_counts.get(case, 0) + allocation.get(case, 0)
        for case in CASE_TYPE_TARGETS
        if case in allowed_cases
    }
    _write_json(
        cfg.checkpoint_path,
        {
            "version": 1,
            "limit": limit,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "start_total": sum(existing_counts.values()),
            "target_total": sum(targets.values()),
            "case_targets": targets,
            "status": "running",
        },
    )
    logger.info(
        "Created bounded checkpoint: limit=%d start_total=%d target_total=%d",
        limit,
        sum(existing_counts.values()),
        sum(targets.values()),
    )
    return targets


async def _generate_one(
    *,
    case: CaseSpec,
    ordinal: int,
    smoke: bool,
    cfg: Config,
    anchor: str,
    style_guide: str,
    provider: OpenAIGenerator,
    writer: DatasetWriter,
    corpus: CorpusGateState,
    skip_gates: bool,
) -> tuple[bool, int]:
    record_id = _record_id(case.id, ordinal, smoke)
    requested_input_style = planned_input_style(case.id, ordinal)
    rejected = 0
    for content_attempt in range(1, cfg.max_content_attempts + 1):
        context, sources, context_meta = synthesize_context(case, cfg, sequence=ordinal - 1)
        prompt_case: dict[str, Any] = {
            "id": case.id,
            "sample_kind": case.sample_kind,
            "behavior": case.behavior,
            "context": case.context,
            "synthetic_context": context,
            "generation_meta": context_meta,
            "requested_input_style": requested_input_style,
        }
        messages = build_gen_prompt(prompt_case, cfg, anchor, style_guide)
        try:
            generated = await provider.generate(messages)
            turns = generated.get("turns") if case.id == "R9_multiturn" else None
            user = generated.get("user")
            assistant = generated.get("assistant")
            if turns is not None:
                if not isinstance(turns, list):
                    raise ValueError("R9 turns is not a list")
                answer_for_judge = "\n".join(
                    str(turn.get("content", ""))
                    for turn in turns
                    if isinstance(turn, dict) and turn.get("role") == "assistant"
                )
            else:
                if not isinstance(user, str) or not isinstance(assistant, str):
                    raise ValueError("Generated JSON lacks string user/assistant")
                answer_for_judge = assistant

            generation_meta = dict(context_meta)
            generation_meta["audience"] = generated.get("audience", "general")
            generation_meta["requested_input_style"] = requested_input_style
            if generated.get("input_style") != requested_input_style:
                raise ValueError(
                    "Generated input_style does not match deterministic augmentation schedule"
                )
            if case.id == "K1_knowledge_anchor":
                context_text = "\n".join(item["text"] for item in context or [])
                generation_meta["knowledge_accuracy"] = await provider.judge_knowledge(
                    context_text, answer_for_judge
                )

            record = to_record(
                case,
                user if isinstance(user, str) else None,
                assistant if isinstance(assistant, str) else None,
                anchor,
                {
                    "record_id": record_id,
                    "input_style": requested_input_style,
                    "turns": turns,
                    "synthetic_context": context,
                    "synthetic_context_sources": sources,
                    "generation_meta": generation_meta,
                    "gen_model": cfg.model,
                },
            )
            result = evaluate_record(record, anchor, None if skip_gates else corpus)
            if skip_gates:
                result.passed = True
                result.reasons = []
                result.checks["debug_skip_gates"] = True
            record["gate_results"] = result.as_dict()
            if result.passed:
                if writer.append(record):
                    return True, rejected
                return False, rejected
            rejected += 1
            append_audit(
                cfg.rejected_path,
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "id": record_id,
                    "case": case.id,
                    "content_attempt": content_attempt,
                    "reasons": result.reasons,
                },
            )
            logger.warning(
                "Rejected case=%s id=%s content_attempt=%d/%d reasons=%s",
                case.id,
                record_id,
                content_attempt,
                cfg.max_content_attempts,
                ",".join(result.reasons),
            )
        except Exception as exc:
            rejected += 1
            append_audit(
                cfg.rejected_path,
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "id": record_id,
                    "case": case.id,
                    "content_attempt": content_attempt,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
            logger.warning(
                "Candidate error case=%s id=%s content_attempt=%d/%d type=%s",
                case.id,
                record_id,
                content_attempt,
                cfg.max_content_attempts,
                type(exc).__name__,
            )
    return False, rejected


async def run_pipeline(args: argparse.Namespace) -> int:
    cfg = Config()
    if args.concurrency is not None:
        cfg = replace(cfg, concurrency=args.concurrency)
    if args.max_cost_usd is not None:
        cfg = replace(cfg, max_cost_usd=args.max_cost_usd)
    setup_logging(cfg, args.verbose)

    if not args.yes:
        logger.error("Refusing to start without --yes.")
        return 2
    if args.smoke and args.limit is not None:
        logger.error("Choose either --smoke or --limit, not both.")
        return 2
    if args.limit is not None and args.limit <= 0:
        logger.error("--limit must be greater than zero.")
        return 2

    logger.info("Preflight started provider=OpenAI model=%s base_url=%s", cfg.model, cfg.base_url)
    problems = cfg.validate()
    if problems:
        for problem in problems:
            logger.error("Preflight configuration error: %s", problem)
        return 2
    try:
        anchor = assert_parity(cfg)
        cases = load_taxonomy(cfg)
        if {case.id: case.count for case in cases} != CASE_TYPE_TARGETS:
            raise ValueError("taxonomy counts do not exactly match CASE_TYPE_TARGETS")
        _knowledge_sanity(cfg, cases)
    except Exception as exc:
        logger.error("Preflight invariant failed: %s", exc)
        return 2
    logger.info("Anchor parity OK sha256=%s", anchor_sha256(anchor))
    logger.info("Thinking mode invariant OK: %s", cfg.thinking)
    eval_texts, eval_ngrams = _contamination_stats(cfg)
    logger.info(
        "Contamination index ready: evaluation_user_texts=%d unique_%dgrams=%d",
        eval_texts,
        cfg.phrase_ngram_size,
        eval_ngrams,
    )

    allowed_cases = {case.id for case in cases}
    if args.only_case:
        if args.only_case not in allowed_cases:
            logger.error("Unknown --only-case %s", args.only_case)
            return 2
        allowed_cases = {args.only_case}
        cases = [case for case in cases if case.id == args.only_case]

    if args.smoke:
        target = len(cases)
    elif args.limit is not None:
        target = args.limit
    else:
        target = sum(CASE_TYPE_TARGETS[case] for case in allowed_cases)
    estimate = _estimate_cost(cfg, target)
    logger.info(
        "Budget guard: target=%d estimated_cost_usd=%.4f max_cost_usd=%.2f",
        target,
        estimate,
        cfg.max_cost_usd,
    )
    if not args.smoke and estimate > cfg.max_cost_usd:
        logger.error("Estimated cost exceeds --max-cost-usd; generation stopped.")
        return 2

    output_path = cfg.smoke_path if args.smoke else cfg.train_path
    if args.no_resume and output_path.exists():
        output_path.unlink()
    if args.no_resume and args.limit is not None and cfg.checkpoint_path.exists():
        cfg.checkpoint_path.unlink()
    existing = list(iter_jsonl(output_path))
    if any(not _anchor_ok(record, anchor) for record in existing):
        logger.error("Resume re-audit failed: existing record has non-canonical system anchor.")
        return 2
    counts = _case_counts(existing)

    if args.smoke:
        targets = {case.id: 1 for case in cases}
    elif args.limit is not None:
        targets = _checkpoint_targets(cfg, counts, args.limit, allowed_cases)
    else:
        targets = {case.id: CASE_TYPE_TARGETS[case.id] for case in cases}

    provider = OpenAIGenerator(cfg)
    try:
        await provider.probe()
        logger.info("OpenAI model probe OK: %s", cfg.model)
    except Exception as exc:
        logger.error("OpenAI model preflight failed: %s: %s", type(exc).__name__, exc)
        await provider.close()
        return 2

    style_guide = cfg.style_guide_path.read_text(encoding="utf-8")
    corpus = CorpusGateState(cfg.phrase_ngram_size, cfg.phrase_max_occurrences)
    for record in existing:
        prior = evaluate_record(record, anchor, corpus)
        if not prior.passed:
            logger.error("Resume re-audit failed id=%s reasons=%s", record.get("id"), prior.reasons)
            await provider.close()
            return 2

    slots: list[tuple[CaseSpec, int]] = []
    by_id = {case.id: case for case in cases}
    for case_id, target_count in targets.items():
        if case_id not in by_id:
            continue
        for ordinal in range(counts.get(case_id, 0) + 1, target_count + 1):
            slots.append((by_id[case_id], ordinal))

    accepted = sum(min(counts.get(case.id, 0), targets.get(case.id, 0)) for case in cases)
    target_total = sum(targets.values())
    rejected = 0
    started = time.monotonic()
    logger.info(
        "Generation start mode=%s accepted=%d target=%d pending=%d",
        "smoke" if args.smoke else ("limit" if args.limit is not None else "full"),
        accepted,
        target_total,
        len(slots),
    )

    with DatasetWriter(output_path) as writer:
        for offset in range(0, len(slots), cfg.concurrency):
            batch = slots[offset : offset + cfg.concurrency]
            results = await asyncio.gather(
                *[
                    _generate_one(
                        case=case,
                        ordinal=ordinal,
                        smoke=args.smoke,
                        cfg=cfg,
                        anchor=anchor,
                        style_guide=style_guide,
                        provider=provider,
                        writer=writer,
                        corpus=corpus,
                        skip_gates=args.skip_gates,
                    )
                    for case, ordinal in batch
                ]
            )
            for (case, _), (was_accepted, new_rejects) in zip(batch, results):
                rejected += new_rejects
                accepted += int(was_accepted)
                if accepted % cfg.progress_every == 0 or not was_accepted:
                    logger.info(
                        "Progress case=%s accepted=%d/%d rejected=%d elapsed=%.1fs",
                        case.id,
                        accepted,
                        target_total,
                        rejected,
                        time.monotonic() - started,
                    )
    await provider.close()

    validation = _post_validate(output_path, anchor, cfg, targets)
    complete = (
        accepted == target_total
        and validation["duplicate_ids"] == 0
        and validation["parity_ok"]
        and not validation["gate_failures"]
    )
    summary = {
        "status": "complete" if complete else "incomplete",
        "mode": "smoke" if args.smoke else ("limit" if args.limit is not None else "full"),
        "full_run_performed": not args.smoke and args.limit is None,
        "target": target_total,
        "accepted": accepted,
        "rejected_attempts": rejected,
        "case_counts": dict(_case_counts(iter_jsonl(output_path))),
        "anchor_sha256": anchor_sha256(anchor),
        "validation": validation,
        "output": str(output_path),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(cfg.summary_path, summary)
    if args.limit is not None:
        checkpoint = _read_json(cfg.checkpoint_path) or {}
        checkpoint["status"] = "complete" if complete else "incomplete"
        checkpoint["current_total"] = len(list(iter_jsonl(output_path)))
        checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(cfg.checkpoint_path, checkpoint)

    logger.info(
        "Post-validate status=%s records=%d unique_ids=%d parity=%s anchor_sha256=%s",
        summary["status"],
        validation["records"],
        validation["unique_ids"],
        validation["parity_ok"],
        summary["anchor_sha256"],
    )
    return 0 if complete else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Generate one record per selected case")
    parser.add_argument("--limit", type=int, help="Bounded number of new records with resume checkpoint")
    parser.add_argument("--only-case", help="Generate only one taxonomy case")
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--skip-gates", action="store_true", help="Debug only; retain failed checks")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--yes", action="store_true", help="Confirm generation")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_pipeline(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted; append-only output and checkpoint are safe to resume.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
