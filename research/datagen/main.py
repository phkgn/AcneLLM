"""One-command end-to-end ROLE datagen pipeline.

Default usage from the repository root::

    python -m datagen.main

The same command resumes append-only generation by deterministic ID.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from contextlib import AbstractContextManager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from .config import CASE_TYPE_RATIOS, CASE_TYPE_TARGETS, FULL_TARGET, Config
from .gates import (
    DuplicateGuard,
    EvaluationNgramIndex,
    PhraseFrequencyGuard,
    apply_rules,
    configure_grounding_embedder,
    generated_text,
    load_drug_terms,
    semantic_sanity_check,
    validate_b5_pairs,
    validate_record,
)
from .generator import (
    AsyncRoleGenerator,
    BudgetExceededError,
    Slot,
    build_generation_messages,
    extract_production_system,
    load_taxonomy,
    make_slot,
    materialize_record,
    smoke_slots,
    utcnow,
)
from .writer import DatasetWriter, load_existing_ids


LOG = logging.getLogger("datagen.main")


def _setup_logging(cfg: Config, verbose: bool) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    file_handler = logging.FileHandler(cfg.log_dir / "datagen.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


class GeneratorLock(AbstractContextManager["GeneratorLock"]):
    """OS file lock; stale lock files are harmless because the lock is kernel-owned."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None
        self._backend = ""

    def __enter__(self) -> "GeneratorLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        if self.handle.read(1) == b"":
            self.handle.seek(0)
            self.handle.write(b"1")
            self.handle.flush()
        self.handle.seek(0)
        try:
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            self._backend = "msvcrt"
        except ImportError:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._backend = "fcntl"
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError(f"Một generator khác đang giữ lock: {self.path}") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is None:
            return
        self.handle.seek(0)
        try:
            if self._backend == "msvcrt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif self._backend == "fcntl":
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Tối đa N mẫu mới trong invocation này.")
    parser.add_argument("--smoke", action="store_true", help="1 mẫu/case, cặp B5 và 3 augmentation regressions.")
    parser.add_argument("--only-case", "--case", dest="only_case", help="Chỉ sinh một case, ví dụ R3.")
    parser.add_argument("--concurrency", type=int, help="Số API call đồng thời.")
    parser.add_argument("--no-resume", action="store_true", help="Debug: sinh thêm từ ID sau cùng, không dùng quota hiện có làm progress.")
    parser.add_argument("--skip-gates", "--skip-rules", dest="skip_gates", action="store_true", help="Debug: bỏ inline content gates.")
    parser.add_argument("--yes", action="store_true", help="Bỏ qua câu hỏi xác nhận khi throughput/cost vượt cảnh báo.")
    parser.add_argument("--max-cost-usd", type=float, default=25.0)
    parser.add_argument("--max-attempts", type=int, help="Số content retry mỗi slot.")
    parser.add_argument("--batch-size", type=int, help="Số slot tối đa mỗi API call.")
    parser.add_argument("--timeout", type=float, help="Timeout mỗi API call (giây).")
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="In plan, không gọi API.")
    parser.add_argument("--skip-preflight-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--full", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _configure(args: argparse.Namespace) -> Config:
    cfg = Config()
    cfg.max_cost_usd = args.max_cost_usd
    if args.concurrency is not None:
        cfg.concurrency = max(1, args.concurrency)
    if args.max_attempts is not None:
        cfg.max_content_attempts = max(1, args.max_attempts)
    if args.batch_size is not None:
        cfg.batch_size = max(1, args.batch_size)
    if args.timeout is not None:
        cfg.timeout_s = max(1.0, args.timeout)
    if args.max_output_tokens is not None:
        cfg.max_output_tokens = max(32, args.max_output_tokens)
    if args.output is not None:
        cfg.output_jsonl = args.output.resolve()
        cfg.rejected_jsonl = cfg.output_jsonl.with_suffix(".rejected.audit.jsonl")
        cfg.summary_json = cfg.output_jsonl.with_suffix(".generation_summary.json")
        cfg.checkpoint_json = cfg.output_jsonl.with_suffix(".limit_checkpoint.json")
        cfg.lock_path = cfg.output_jsonl.with_suffix(".generator.lock")
    return cfg


def _case_id(record: dict[str, Any]) -> str:
    kind = str(record.get("sample_kind") or "")
    return kind.split("_", 1)[0].upper()


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return records, errors
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line_{line_no}:invalid_json:{exc.msg}")
                continue
            if not isinstance(value, dict):
                errors.append(f"line_{line_no}:not_object")
                continue
            records.append(value)
    return records, errors


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _prepare_limit_checkpoint(
    cfg: Config,
    *,
    limit: int,
    existing_count: int,
) -> tuple[dict[str, Any], int, int, bool]:
    """Create or resume one bounded cohort without silently adding another N rows."""
    previous: dict[str, Any] = {}
    if cfg.checkpoint_json.exists():
        try:
            previous = json.loads(cfg.checkpoint_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}

    resumed = (
        previous.get("status") == "in_progress"
        and int(previous.get("limit") or 0) == limit
        and isinstance(previous.get("target_total"), int)
    )
    if resumed:
        checkpoint = previous
        target_total = int(checkpoint["target_total"])
    else:
        target_total = existing_count + limit
        checkpoint = {
            "status": "in_progress",
            "limit": limit,
            "started_at": utcnow(),
            "start_total": existing_count,
            "target_total": target_total,
            "output": str(cfg.output_jsonl.resolve()),
        }
        _write_json(cfg.checkpoint_json, checkpoint)
    return checkpoint, target_total, max(0, target_total - existing_count), resumed


def _rewrite_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".reaudit.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_audit(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"timestamp": utcnow(), **payload}, ensure_ascii=False) + "\n")


def _recover_false_gate_quarantine(
    cfg: Config,
    records: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, Path]:
    """One-time recovery for records quarantined by v2's initial false vocative rule."""
    marker = cfg.output_dir / ".false_gate_recovery_v2.done"
    if marker.exists() or not cfg.rejected_jsonl.exists():
        return list(records), 0, marker
    current_ids = {str(record.get("id") or "") for record in records}
    recovered: dict[str, dict[str, Any]] = {}
    with cfg.rejected_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                audit = json.loads(line)
            except json.JSONDecodeError:
                continue
            reason = str(audit.get("reason") or "")
            candidate = audit.get("candidate")
            sample_id = str(audit.get("id") or "")
            metadata = (candidate or {}).get("generation_metadata") if isinstance(candidate, dict) else {}
            if (
                sample_id
                and sample_id not in current_ids
                and isinstance(candidate, dict)
                and str((metadata or {}).get("generator_version") or "") == "v4-role-generator-1"
                and reason.startswith("resume_reaudit::")
                and any(token in reason for token in (
                    "vocative_consistency::parent_vocative_mixed_with_minh",
                    "naturalness::augmented_input_missing_verb",
                    "naturalness::teencode_not_in_whitelist",
                ))
            ):
                recovered[sample_id] = candidate
    return [*records, *recovered.values()], len(recovered), marker


def _count_existing(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {case_id: 0 for case_id in CASE_TYPE_TARGETS}
    for record in records:
        case_id = _case_id(record)
        if case_id in counts:
            counts[case_id] += 1
    return counts


def _pick_target_case_type(
    targets: dict[str, int],
    existing: dict[str, int],
    *,
    excluded: set[str] | None = None,
) -> str | None:
    """Pick the case with the largest relative deficit to its target."""
    blocked = excluded or set()
    candidates = {
        case_id: (target - existing.get(case_id, 0)) / max(target, 1)
        for case_id, target in targets.items()
        if case_id not in blocked and existing.get(case_id, 0) < target
    }
    if not candidates:
        return None
    return max(candidates, key=lambda case_id: (candidates[case_id], CASE_TYPE_RATIOS[case_id]))


def _slot_index(sample_id: str) -> int | None:
    match = re.search(r"-(\d{6})$", sample_id)
    return int(match.group(1)) if match else None


def _print_preflight(rows: Sequence[tuple[str, bool, str]]) -> None:
    print("\nPRE-FLIGHT")
    print("=" * 72)
    for label, passed, detail in rows:
        print(f"{'✓' if passed else '✗'} {label:<28} {detail}")


async def _preflight(
    cfg: Config,
    generator: AsyncRoleGenerator,
    *,
    taxonomy: dict[str, Any],
    production_system: str,
    style_guide: str,
    probe_slots: Sequence[Slot],
    remaining_records: int,
    yes: bool,
    skip_probe: bool,
) -> tuple[EvaluationNgramIndex, dict[str, Any]]:
    rows: list[tuple[str, bool, str]] = []
    problems = cfg.validate()
    rows.append(("Cấu hình + DATAGEN_API_KEY", not problems, "; ".join(problems) or "đủ"))
    if problems:
        _print_preflight(rows)
        raise RuntimeError("; ".join(problems))

    models = await generator.list_models()
    model_ok = cfg.model in models
    rows.append(("Model khả dụng", model_ok, cfg.model if model_ok else f"chỉ có: {models}"))
    if not model_ok:
        _print_preflight(rows)
        raise RuntimeError(f"Model {cfg.model!r} không có trên provider")

    completion = await generator.short_completion()
    completion_ok = bool(completion["content"])
    thinking_ok = int(completion["usage"].get("reasoning_tokens") or 0) == 0 and cfg.thinking == "disabled"
    rows.append(("Completion ngắn", completion_ok, f"{completion['elapsed_seconds']:.2f}s"))
    rows.append(("thinking=disabled", thinking_ok, f"reasoning_tokens={completion['usage'].get('reasoning_tokens', 0)}"))
    if not completion_ok or not thinking_ok:
        _print_preflight(rows)
        raise RuntimeError("Provider không tôn trọng completion/thinking contract")

    from acne_llm.rag.embedder import Embedder

    embedder = Embedder(model_name=cfg.embedding_model, device=cfg.embedding_device, lazy=False)
    semantic = semantic_sanity_check(embedder)
    configure_grounding_embedder(embedder)
    rows.append(("Embedding cosine", semantic["passed"], f"semantic_score={semantic['semantic_score']:.4f}"))
    if not semantic["passed"]:
        _print_preflight(rows)
        raise RuntimeError(
            "Embedder không đạt semantic sanity > 0.5; kiểm model AITeamVN/Vietnamese_Embedding/cache/device"
        )

    files_ok = all(path.read_text(encoding="utf-8").strip() for path in (
        cfg.prompt_template_path, cfg.model_file_path, cfg.style_guide_path
    )) and bool(production_system)
    rows.append(("Template + SYSTEM", files_ok, "đọc được" if files_ok else "file rỗng/hỏng"))
    if not files_ok:
        _print_preflight(rows)
        raise RuntimeError("stream_user.j2, SYSTEM Modelfile hoặc style guide không đọc được")

    paths = sorted(cfg.evaluation_dataset_dir.glob("*.jsonl"))
    if not paths:
        raise RuntimeError(f"Không có contamination dataset tại {cfg.evaluation_dataset_dir}")
    contamination = EvaluationNgramIndex(cfg.contamination_cache, 8)
    contamination_stats = contamination.build(paths)
    contamination_ok = int(contamination_stats.get("user_texts") or 0) > 0
    rows.append(("Index contamination", contamination_ok, f"user_texts={contamination_stats.get('user_texts', 0)}"))
    if not contamination_ok:
        _print_preflight(rows)
        raise RuntimeError("Index contamination có 0 user text; cần kiểm schema evaluation v1")

    probe: dict[str, Any] = {"skipped": True, "seconds_per_sample": None, "estimated_hours": None, "estimated_cost_usd": None}
    if not skip_probe and probe_slots:
        messages = build_generation_messages(
            list(probe_slots)[:3],
            style_guide=style_guide,
            production_system=production_system,
            taxonomy=taxonomy,
            feedback={},
            banned_questions=[],
        )
        before_cost = generator.actual_cost_usd
        batch = await generator.generate_batch(messages)
        produced = max(1, min(3, len(batch.candidates)))
        seconds_per_sample = batch.elapsed_seconds / produced
        cost_per_sample = max(0.0, generator.actual_cost_usd - before_cost) / produced
        estimate_hours = seconds_per_sample * max(remaining_records, 0) / 3600
        estimate_cost = cost_per_sample * max(remaining_records, 0)
        probe = {
            "skipped": False,
            "produced_candidates": len(batch.candidates),
            "elapsed_seconds": round(batch.elapsed_seconds, 3),
            "seconds_per_sample": round(seconds_per_sample, 3),
            "estimated_hours": round(estimate_hours, 3),
            "estimated_cost_usd": round(estimate_cost, 6),
        }
        rows.append(("Throughput probe 3 mẫu", len(batch.candidates) >= 3, f"{seconds_per_sample:.2f}s/mẫu; ~{estimate_hours:.2f}h; ~${estimate_cost:.2f}"))
        if len(batch.candidates) < 3:
            _print_preflight(rows)
            raise RuntimeError("Throughput probe không trả đủ 3 mẫu JSON")
        warning = estimate_hours > 12 or estimate_cost > cfg.max_cost_usd
        if warning and not yes:
            _print_preflight(rows)
            try:
                answer = input("Ước tính vượt ngưỡng 12h hoặc budget. Tiếp tục? [y/N]: ").strip().casefold()
            except EOFError as exc:
                raise RuntimeError("Cần truyền --yes để xác nhận trong môi trường non-interactive") from exc
            if answer not in {"y", "yes"}:
                raise RuntimeError("Đã dừng theo lựa chọn người dùng")
    _print_preflight(rows)
    return contamination, {
        "checks": [{"name": label, "passed": passed, "detail": detail} for label, passed, detail in rows],
        "models": models,
        "semantic": semantic,
        "contamination": contamination_stats,
        "throughput": probe,
    }


def _load_guards(
    records: Sequence[dict[str, Any]],
    duplicate_guard: DuplicateGuard,
    phrase_guard: PhraseFrequencyGuard,
) -> None:
    for record in records:
        sample_id = str(record.get("id") or "")
        raw_text = "\n".join(str(value) for value in record.get("raw_user_messages") or [])
        if raw_text:
            duplicate_guard.add(sample_id, raw_text)
        phrase_guard.add(sample_id, generated_text(record))


def _reaudit_existing(
    cfg: Config,
    records: Sequence[dict[str, Any]],
    *,
    production_system: str,
    drug_terms: set[str],
    contamination: EvaluationNgramIndex,
    skip_gates: bool,
    counters: Counter[str],
) -> tuple[list[dict[str, Any]], DuplicateGuard, PhraseFrequencyGuard]:
    duplicate_guard = DuplicateGuard()
    phrase_guard = PhraseFrequencyGuard(cfg.phrase_ngram_size, cfg.phrase_max_occurrences)
    if skip_gates:
        accepted = list(records)
        _load_guards(accepted, duplicate_guard, phrase_guard)
        return accepted, duplicate_guard, phrase_guard

    accepted: list[dict[str, Any]] = []
    for record in records:
        sample_id = str(record.get("id") or "")
        case_id = _case_id(record)
        raw_users = [str(value) for value in record.get("raw_user_messages") or []]
        if case_id not in CASE_TYPE_TARGETS:
            _append_audit(cfg.rejected_jsonl, {"id": sample_id, "attempt": 0, "reason": "resume_reaudit::unknown_case", "candidate": record})
            counters["resume_rejected"] += 1
            continue
        result = apply_rules(
            record,
            case_id=case_id,
            raw_users=raw_users,
            production_system=production_system,
            drug_terms=drug_terms,
            duplicate_guard=duplicate_guard,
            contamination_index=contamination,
            phrase_guard=phrase_guard,
        )
        record["gate_results"] = result
        if result["passed"]:
            accepted.append(record)
            raw_text = "\n".join(raw_users)
            if raw_text:
                duplicate_guard.add(sample_id, raw_text)
            phrase_guard.add(sample_id, generated_text(record))
            counters["resume_accepted"] += 1
        else:
            _append_audit(cfg.rejected_jsonl, {
                "id": sample_id,
                "attempt": 0,
                "reason": "resume_reaudit::" + " | ".join(result["reasons"]),
                "candidate": record,
            })
            counters["resume_rejected"] += 1
            for reason in result["reasons"]:
                counters[f"rule_reason::{reason}"] += 1
    if len(accepted) != len(records):
        _rewrite_jsonl(cfg.output_jsonl, accepted)
    return accepted, duplicate_guard, phrase_guard


class PipelineState:
    def __init__(
        self,
        cfg: Config,
        taxonomy: dict[str, Any],
        records: list[dict[str, Any]],
        duplicate_guard: DuplicateGuard,
        phrase_guard: PhraseFrequencyGuard,
        targets: dict[str, int],
        new_limit: int | None,
        explicit_slots: Sequence[Slot] = (),
    ):
        self.cfg = cfg
        self.taxonomy = taxonomy
        self.records = records
        self.duplicate_guard = duplicate_guard
        self.phrase_guard = phrase_guard
        self.targets = targets
        self.new_limit = new_limit
        self.explicit_slots = {slot.id: slot for slot in explicit_slots}
        self.counts = _count_existing(records)
        self.ids = {str(record.get("id") or "") for record in records}
        self.reserved_ids: set[str] = set()
        self.new_written = 0
        self.attempts: Counter[str] = Counter()
        self.feedback: dict[str, str] = {}
        self.failed_ids: set[str] = set()
        self.lock = asyncio.Lock()

    def remaining_new_capacity(self) -> int:
        if self.new_limit is None:
            return 10**9
        return max(0, self.new_limit - self.new_written - len(self.reserved_ids))

    def done(self) -> bool:
        if self.new_limit is not None and self.new_written >= self.new_limit:
            return True
        return _pick_target_case_type(self.targets, self.counts) is None

    def _anchor_sources(self, case_id: str, index: int) -> tuple[str, ...]:
        if case_id != "B5":
            return ()
        anchor = f"b5-anchor-{(index - 1) // 2 + 1:04d}"
        for record in self.records:
            if record.get("anchor_group") == anchor:
                return tuple(str(value) for value in record.get("synthetic_context_sources") or [])
        return ()

    def _next_missing_index(self, case_id: str) -> int | None:
        target = self.targets[case_id]
        for index in range(1, target + 1):
            sample_id = f"role-{case_id.casefold()}-{index:06d}"
            if sample_id not in self.ids and sample_id not in self.reserved_ids and sample_id not in self.failed_ids:
                return index
        return None

    def _make_slot(self, case_id: str, index: int) -> Slot:
        sample_id = f"role-{case_id.casefold()}-{index:06d}"
        explicit = self.explicit_slots.get(sample_id)
        if explicit is not None:
            anchor_sources = self._anchor_sources(case_id, index)
            if anchor_sources and not explicit.anchor_sources:
                return Slot(**{**asdict(explicit), "anchor_sources": anchor_sources})
            return explicit
        return make_slot(
            case_id,
            index,
            self.taxonomy["groups"][case_id]["sample_kind"],
            anchor_sources=self._anchor_sources(case_id, index),
        )

    async def reserve_batch(self) -> list[Slot]:
        async with self.lock:
            capacity = min(self.cfg.batch_size, self.remaining_new_capacity())
            if capacity <= 0:
                return []
            effective = dict(self.counts)
            for sample_id in self.reserved_ids:
                match = re.match(r"role-([rb]\d)-", sample_id)
                if match:
                    effective[match.group(1).upper()] += 1
            blocked: set[str] = set()
            case_id = _pick_target_case_type(self.targets, effective, excluded=blocked)
            while case_id is not None:
                index = self._next_missing_index(case_id)
                if index is not None:
                    break
                blocked.add(case_id)
                case_id = _pick_target_case_type(self.targets, effective, excluded=blocked)
            if case_id is None:
                return []
            desired = min(capacity, self.targets[case_id] - effective.get(case_id, 0))
            if case_id == "B5":
                desired = min(desired, 2)
                if desired == 1:
                    pair_index = index + 1 if index % 2 else index - 1
                    pair_id = f"role-b5-{pair_index:06d}"
                    if pair_id not in self.ids and capacity < 2:
                        return []
            slots: list[Slot] = []
            while len(slots) < desired:
                next_index = self._next_missing_index(case_id)
                if next_index is None:
                    break
                slot = self._make_slot(case_id, next_index)
                self.reserved_ids.add(slot.id)
                slots.append(slot)
                if case_id == "B5" and len(slots) == 1:
                    counterpart = next_index + 1 if next_index % 2 else next_index - 1
                    counterpart_id = f"role-b5-{counterpart:06d}"
                    if counterpart_id not in self.ids and counterpart_id not in self.reserved_ids and len(slots) < capacity:
                        paired = self._make_slot("B5", counterpart)
                        self.reserved_ids.add(paired.id)
                        slots.append(paired)
                    break
            return slots

    async def release(self, slots: Sequence[Slot]) -> None:
        async with self.lock:
            for slot in slots:
                self.reserved_ids.discard(slot.id)


async def _call_generation_batch(
    generator: AsyncRoleGenerator,
    state: PipelineState,
    slots: Sequence[Slot],
    *,
    style_guide: str,
    production_system: str,
) -> tuple[list[Slot], Any, Exception | None]:
    messages = build_generation_messages(
        slots,
        style_guide=style_guide,
        production_system=production_system,
        taxonomy=state.taxonomy,
        feedback=state.feedback,
        banned_questions=[
            str(value)
            for record in state.records[-30:]
            for value in record.get("raw_user_messages") or []
        ],
    )
    try:
        return list(slots), await generator.generate_batch(messages), None
    except Exception as exc:
        return list(slots), None, exc


def _process_batch_result(
    cfg: Config,
    state: PipelineState,
    slots: Sequence[Slot],
    batch: Any,
    error: Exception | None,
    *,
    production_system: str,
    drug_terms: set[str],
    contamination: EvaluationNgramIndex,
    writer: DatasetWriter,
    counters: Counter[str],
    skip_gates: bool,
) -> int:
    if error is not None:
        reason = f"api_or_parse_error::{type(error).__name__}::{error}"
        for slot in slots:
            state.attempts[slot.id] += 1
            state.feedback[slot.id] = reason
            _append_audit(cfg.rejected_jsonl, {"id": slot.id, "attempt": state.attempts[slot.id], "reason": reason})
            counters["api_failures"] += 1
            if state.attempts[slot.id] >= cfg.max_content_attempts:
                state.failed_ids.add(slot.id)
        return 0

    by_id = {str(candidate.get("slot_id") or ""): candidate for candidate in batch.candidates}
    materialized: dict[str, tuple[dict[str, Any], list[str], list[str]]] = {}
    for slot in slots:
        state.attempts[slot.id] += 1
        candidate = by_id.get(slot.id)
        if candidate is None:
            reason = "missing_slot_in_model_response"
            state.feedback[slot.id] = reason
            _append_audit(cfg.rejected_jsonl, {
                "id": slot.id,
                "attempt": state.attempts[slot.id],
                "reason": reason,
                "returned_slot_ids": sorted(by_id),
            })
            counters["content_rejected"] += 1
            if state.attempts[slot.id] >= cfg.max_content_attempts:
                state.failed_ids.add(slot.id)
            continue
        try:
            materialized[slot.id] = materialize_record(
                slot,
                candidate,
                production_system=production_system,
                model=cfg.model,
                attempt=state.attempts[slot.id],
            )
        except Exception as exc:
            reason = f"materialize_error::{type(exc).__name__}::{exc}"
            state.feedback[slot.id] = reason
            _append_audit(cfg.rejected_jsonl, {"id": slot.id, "attempt": state.attempts[slot.id], "reason": reason, "candidate": candidate})
            counters["content_rejected"] += 1

    # B5 is an atomic pair when both members are generated together.
    b5_new = [value[0] for sample_id, value in materialized.items() if sample_id.startswith("role-b5-")]
    if b5_new:
        affected = {str(record.get("anchor_group") or "") for record in b5_new}
        b5_scope = [record for record in state.records if str(record.get("anchor_group") or "") in affected] + b5_new
        pair_result = validate_b5_pairs(b5_scope)
        if not pair_result["passed"]:
            reason = " | ".join(pair_result["reasons"])
            for slot in slots:
                if slot.id not in materialized or not slot.id.startswith("role-b5-"):
                    continue
                state.feedback[slot.id] = reason
                _append_audit(cfg.rejected_jsonl, {
                    "id": slot.id,
                    "attempt": state.attempts[slot.id],
                    "reason": "b5_pair::" + reason,
                    "candidate": materialized[slot.id][0],
                })
                counters["content_rejected"] += 1
                materialized.pop(slot.id, None)

    written = 0
    for slot in slots:
        value = materialized.get(slot.id)
        if value is None:
            if state.attempts[slot.id] >= cfg.max_content_attempts:
                state.failed_ids.add(slot.id)
            continue
        record, structural_errors, raw_users = value
        if skip_gates:
            result = {"passed": True, "pass": True, "reasons": ["skip_gates_debug"]}
        else:
            result = apply_rules(
                record,
                case_id=slot.case_id,
                raw_users=raw_users,
                production_system=production_system,
                drug_terms=drug_terms,
                duplicate_guard=state.duplicate_guard,
                contamination_index=contamination,
                phrase_guard=state.phrase_guard,
                structural_errors=structural_errors,
            )
        record["gate_results"] = result
        if not result["passed"]:
            reason = " | ".join(result["reasons"])
            phrase_hits = ((result.get("phrase_frequency") or {}).get("hits") or [])
            feedback_reason = reason
            if phrase_hits:
                feedback_reason += " | không được lặp các cụm: " + "; ".join(
                    str(hit.get("phrase") or "") for hit in phrase_hits[:5]
                )
            state.feedback[slot.id] = feedback_reason
            _append_audit(cfg.rejected_jsonl, {
                "id": slot.id,
                "attempt": state.attempts[slot.id],
                "reason": reason,
                "candidate": record,
            })
            counters["rule_rejected"] += 1
            for item in result["reasons"]:
                counters[f"rule_reason::{item}"] += 1
            if state.attempts[slot.id] >= cfg.max_content_attempts:
                state.failed_ids.add(slot.id)
            continue
        if not writer.write(record):
            counters["samples_dedup_skipped"] += 1
            continue
        raw_text = "\n".join(raw_users)
        state.duplicate_guard.add(slot.id, raw_text)
        state.phrase_guard.add(slot.id, generated_text(record))
        state.records.append(record)
        state.ids.add(slot.id)
        state.counts[slot.case_id] += 1
        state.new_written += 1
        state.feedback.pop(slot.id, None)
        state.failed_ids.discard(slot.id)
        counters["samples_written"] += 1
        counters[f"case_type::{slot.case_id}"] += 1
        counters[f"input_style::{slot.input_style}"] += 1
        written += 1
    return written


async def _generation_loop(
    cfg: Config,
    generator: AsyncRoleGenerator,
    state: PipelineState,
    *,
    production_system: str,
    style_guide: str,
    drug_terms: set[str],
    contamination: EvaluationNgramIndex,
    writer: DatasetWriter,
    counters: Counter[str],
    skip_gates: bool,
    topup: bool,
) -> None:
    max_iters = cfg.topup_max_iters if topup else max(1, sum(state.targets.values()))
    for iteration in range(max_iters):
        if state.done():
            break
        batches: list[list[Slot]] = []
        for _ in range(cfg.concurrency):
            slots = await state.reserve_batch()
            if slots:
                batches.append(slots)
        if not batches:
            break
        results = await asyncio.gather(*[
            _call_generation_batch(
                generator,
                state,
                slots,
                style_guide=style_guide,
                production_system=production_system,
            )
            for slots in batches
        ])
        written_this_iter = 0
        for slots, batch, error in results:
            written_this_iter += _process_batch_result(
                cfg,
                state,
                slots,
                batch,
                error,
                production_system=production_system,
                drug_terms=drug_terms,
                contamination=contamination,
                writer=writer,
                counters=counters,
                skip_gates=skip_gates,
            )
            await state.release(slots)
        if counters["samples_written"] and counters["samples_written"] % cfg.progress_every < written_this_iter:
            LOG.info(
                "Progress: new=%d, total=%d, rejected=%d, API failures=%d",
                state.new_written,
                len(state.records),
                counters["rule_rejected"],
                counters["api_failures"],
            )
        if topup and written_this_iter == 0:
            LOG.warning("Top-up iter %d ghi được 0 mẫu; dừng để tránh loop vô hạn.", iteration + 1)
            break


def _post_validate(
    cfg: Config,
    *,
    production_system: str,
    expected_targets: dict[str, int],
    strict_quota: bool,
) -> dict[str, Any]:
    records, read_errors = _read_jsonl(cfg.output_jsonl)
    ids = [str(record.get("id") or "") for record in records]
    schema_errors: list[str] = list(read_errors)
    for record in records:
        for error in validate_record(record, production_system):
            schema_errors.append(f"{record.get('id')}::{error}")
        if not bool((record.get("gate_results") or {}).get("passed", (record.get("gate_results") or {}).get("pass"))):
            schema_errors.append(f"{record.get('id')}::stored_gate_not_passed")
    duplicate_ids = sorted(sample_id for sample_id, count in Counter(ids).items() if sample_id and count > 1)

    phrase_guard = PhraseFrequencyGuard(cfg.phrase_ngram_size, cfg.phrase_max_occurrences)
    for record in records:
        phrase_guard.add(str(record.get("id") or ""), generated_text(record))
    phrase_violations = phrase_guard.violations()
    b5 = validate_b5_pairs(records)
    counts = _count_existing(records)
    quota_deficits = {
        case_id: target - counts.get(case_id, 0)
        for case_id, target in expected_targets.items()
        if counts.get(case_id, 0) < target
    }

    total = max(1, sum(counts.values()))
    distribution_warnings: list[str] = []
    for case_id, ratio in CASE_TYPE_RATIOS.items():
        if case_id not in expected_targets:
            continue
        actual = counts.get(case_id, 0) / total
        if abs(actual - ratio) > 0.10:
            distribution_warnings.append(f"sample_kind {case_id}: actual={actual:.1%}, expected={ratio:.1%}")
    style_counts = Counter(str(record.get("input_style") or "") for record in records)
    augmented = sum(count for style, count in style_counts.items() if style != "standard")
    augmented_ratio = augmented / max(len(records), 1)
    if abs(augmented_ratio - 0.30) > 0.10:
        distribution_warnings.append(f"augmentation: actual={augmented_ratio:.1%}, expected=30.0%")

    passed = not schema_errors and not duplicate_ids and not phrase_violations and b5["passed"]
    if strict_quota:
        passed = passed and not quota_deficits
    return {
        "passed": passed,
        "records": len(records),
        "unique_ids": len(set(ids)),
        "schema_errors": schema_errors,
        "duplicate_ids": duplicate_ids,
        "phrase_frequency_violations": phrase_violations,
        "b5_pairs": b5,
        "case_type_counts": counts,
        "input_style_counts": dict(sorted(style_counts.items())),
        "augmentation_ratio": round(augmented_ratio, 4),
        "quota_deficits": quota_deficits,
        "distribution_warnings": distribution_warnings,
    }


def _write_smoke_review(
    cfg: Config,
    smoke: Sequence[Slot],
    records: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    by_id = {str(record.get("id") or ""): record for record in records}
    selected = [by_id[slot.id] for slot in smoke if slot.id in by_id]
    lines = [
        "# SMOKE REVIEW V2 — AcneLLM ROLE dataset",
        "",
        f"- Records smoke đạt inline gate: **{len(selected)}/{len(smoke)}**",
        f"- Model: `{cfg.model}`; thinking: `{cfg.thinking}`",
        f"- Embedder semantic sanity: **{summary['preflight']['semantic']['semantic_score']:.4f}**",
        f"- Output train/resume: `{cfg.output_jsonl.resolve()}`",
        "- `v4_role.smoke.jsonl` cũ được giữ nguyên; smoke V2 dùng ID train thật.",
        "",
        "## Sáu lỗi smoke cũ",
        "",
        "1. Xưng hô phụ huynh: validator `vocative_consistency` chạy inline.",
        "2. Code-switch standard: validator `code_switch` chạy inline.",
        "3. Teencode/no-accent: validator `naturalness` yêu cầu câu đủ dài, có động từ và shorthand hợp lệ.",
        "4. B5: pair validator yêu cầu cùng docs, hai depth và hai user khác nhau.",
        "5. Grounding: `semantic_score` lấy từ AITeamVN/Vietnamese_Embedding; preflight abort nếu <= 0.5.",
        "6. Phrase frequency: 8-gram tối đa 5 lần trên generated text.",
        "",
        "## Records",
        "",
        "| ID | Case | Style | Gate | Semantic max |",
        "|---|---|---|---:|---:|",
    ]
    for record in selected:
        scores = ((record.get("gate_results") or {}).get("grounding") or {}).get("sentence_scores") or []
        semantic_max = max((float(item.get("semantic_score") or 0) for item in scores), default=0.0)
        lines.append(
            f"| `{record['id']}` | {record['sample_kind']} | {record['input_style']} | "
            f"{'pass' if (record.get('gate_results') or {}).get('passed') else 'fail'} | {semantic_max:.4f} |"
        )
    lines.extend(["", "## Post-run", "", "```json", json.dumps(summary["post_validate"], ensure_ascii=False, indent=2), "```", ""])
    cfg.smoke_review_path.write_text("\n".join(lines), encoding="utf-8")


async def _amain(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        raise RuntimeError("--limit phải > 0")
    cfg = _configure(args)
    _setup_logging(cfg, args.verbose)
    taxonomy = load_taxonomy(cfg)
    only_case = args.only_case.upper() if args.only_case else None
    if only_case and only_case not in CASE_TYPE_TARGETS:
        raise RuntimeError(f"--only-case không hợp lệ: {only_case}")

    if args.smoke:
        planned_smoke = smoke_slots(taxonomy, only_case)
        targets = _count_existing([])
        for slot in planned_smoke:
            targets[slot.case_id] = max(targets[slot.case_id], (_slot_index(slot.id) or 0))
        targets = {case_id: target for case_id, target in targets.items() if target > 0}
        new_limit = args.limit
    else:
        planned_smoke = []
        targets = {
            case_id: count
            for case_id, count in CASE_TYPE_TARGETS.items()
            if only_case is None or case_id == only_case
        }
        new_limit = args.limit

    existing_raw, read_errors = _read_jsonl(cfg.output_jsonl)
    if read_errors:
        raise RuntimeError("Output hiện tại có JSONL hỏng: " + "; ".join(read_errors[:5]))
    existing_raw, recovered_false_gate, recovery_marker = _recover_false_gate_quarantine(cfg, existing_raw)
    if recovered_false_gate:
        LOG.info("Khôi phục %d record từng bị quarantine bởi false vocative/naturalness rule.", recovered_false_gate)
    limit_checkpoint: dict[str, Any] | None = None
    limit_target_total: int | None = None
    if args.limit is not None and not args.smoke and not args.no_resume:
        limit_checkpoint, limit_target_total, new_limit, resumed_limit = _prepare_limit_checkpoint(
            cfg,
            limit=args.limit,
            existing_count=len(existing_raw),
        )
        if resumed_limit:
            LOG.info(
                "Resume bounded run: target_total=%d, current=%d, remaining=%d",
                limit_target_total,
                len(existing_raw),
                new_limit,
            )
    if args.no_resume:
        counts = _count_existing(existing_raw)
        targets = {case_id: counts.get(case_id, 0) + target for case_id, target in targets.items()}

    if args.dry_run:
        print(json.dumps({
            "mode": "smoke" if args.smoke else "full",
            "output": str(cfg.output_jsonl),
            "existing": len(existing_raw),
            "targets": targets,
            "limit_new": new_limit,
            "smoke_slots": [asdict(slot) for slot in planned_smoke],
        }, ensure_ascii=False, indent=2))
        return 0

    started = time.perf_counter()
    counters: Counter[str] = Counter()
    with GeneratorLock(cfg.lock_path):
        production_system = extract_production_system(cfg)
        style_guide = cfg.style_guide_path.read_text(encoding="utf-8")
        generator = AsyncRoleGenerator(cfg)

        if args.smoke:
            existing_ids = {str(record.get("id") or "") for record in existing_raw}
            probe_slots = list(planned_smoke[:3])
            remaining = len([slot for slot in planned_smoke if slot.id not in existing_ids])
        else:
            counts = _count_existing(existing_raw)
            probe_slots = []
            for case_id, target in targets.items():
                for index in range(1, target + 1):
                    sample_id = f"role-{case_id.casefold()}-{index:06d}"
                    if len(probe_slots) < 3:
                        probe_slots.append(make_slot(case_id, index, taxonomy["groups"][case_id]["sample_kind"]))
                    if len(probe_slots) == 3:
                        break
                if len(probe_slots) == 3:
                    break
            remaining = min(
                new_limit if new_limit is not None else 10**9,
                sum(max(0, target - counts.get(case_id, 0)) for case_id, target in targets.items()),
            )
            if remaining and len(probe_slots) < 3:
                used = {slot.id for slot in probe_slots}
                for case_id, target in targets.items():
                    for index in range(1, target + 1):
                        slot = make_slot(case_id, index, taxonomy["groups"][case_id]["sample_kind"])
                        if slot.id not in used:
                            probe_slots.append(slot)
                            used.add(slot.id)
                        if len(probe_slots) == 3:
                            break
                    if len(probe_slots) == 3:
                        break

        contamination, preflight = await _preflight(
            cfg,
            generator,
            taxonomy=taxonomy,
            production_system=production_system,
            style_guide=style_guide,
            probe_slots=probe_slots,
            remaining_records=remaining,
            yes=args.yes,
            skip_probe=args.skip_preflight_probe,
        )
        drug_terms = load_drug_terms()
        accepted, duplicate_guard, phrase_guard = _reaudit_existing(
            cfg,
            existing_raw,
            production_system=production_system,
            drug_terms=drug_terms,
            contamination=contamination,
            skip_gates=args.skip_gates,
            counters=counters,
        )
        if recovered_false_gate:
            recovery_marker.write_text(
                f"recovered={recovered_false_gate}\ncompleted_at={utcnow()}\n",
                encoding="utf-8",
            )
        if limit_target_total is not None:
            new_limit = max(0, limit_target_total - len(accepted))
        if args.smoke:
            smoke_ids = {slot.id for slot in planned_smoke}
            accepted_smoke = {str(record.get("id") or "") for record in accepted if str(record.get("id") or "") in smoke_ids}
            state_targets = dict(targets)
            # IDs, not only counts, define smoke completion; missing early IDs are regenerated.
            for slot in planned_smoke:
                if slot.id not in accepted_smoke:
                    state_targets[slot.case_id] = max(state_targets[slot.case_id], _slot_index(slot.id) or 0)
        else:
            state_targets = targets

        state = PipelineState(
            cfg,
            taxonomy,
            accepted,
            duplicate_guard,
            phrase_guard,
            state_targets,
            new_limit,
            explicit_slots=planned_smoke,
        )
        # Ensure smoke slots use their explicit regression styles.
        if args.smoke:
            # Existing counts may hide a missing smoke ID (e.g. ID 1 absent but ID 2 present).
            state.counts = {case_id: sum(
                str(record.get("id") or "") in {slot.id for slot in planned_smoke if slot.case_id == case_id}
                for record in accepted
            ) for case_id in CASE_TYPE_TARGETS}
            original_make_slot = state._next_missing_index

            def smoke_next(case_id: str) -> int | None:
                candidates = [slot for slot in planned_smoke if slot.case_id == case_id]
                for slot in candidates:
                    if slot.id not in state.ids and slot.id not in state.reserved_ids and slot.id not in state.failed_ids:
                        return _slot_index(slot.id)
                return None

            state._next_missing_index = smoke_next  # type: ignore[method-assign]

        with DatasetWriter(cfg.output_jsonl, dedup_ids=load_existing_ids(cfg.output_jsonl)) as writer:
            await _generation_loop(
                cfg,
                generator,
                state,
                production_system=production_system,
                style_guide=style_guide,
                drug_terms=drug_terms,
                contamination=contamination,
                writer=writer,
                counters=counters,
                skip_gates=args.skip_gates,
                topup=False,
            )
            deficits_before_topup = {
                case_id: target - state.counts.get(case_id, 0)
                for case_id, target in state.targets.items()
                if state.counts.get(case_id, 0) < target
            }
            if deficits_before_topup and (state.new_limit is None or state.new_written < state.new_limit):
                LOG.info("Top-up bắt đầu, còn thiếu: %s", deficits_before_topup)
                state.failed_ids.clear()
                await _generation_loop(
                    cfg,
                    generator,
                    state,
                    production_system=production_system,
                    style_guide=style_guide,
                    drug_terms=drug_terms,
                    contamination=contamination,
                    writer=writer,
                    counters=counters,
                    skip_gates=args.skip_gates,
                    topup=True,
                )

        strict_quota = args.smoke or (args.limit is None and not args.no_resume)
        post = _post_validate(
            cfg,
            production_system=production_system,
            expected_targets=state.targets,
            strict_quota=strict_quota,
        )
        usage = generator.usage_summary()
        elapsed = time.perf_counter() - started
        throughput = preflight.get("throughput") or {}
        seconds_per_sample = throughput.get("seconds_per_sample")
        estimated_full_hours = (seconds_per_sample * FULL_TARGET / 3600) if seconds_per_sample else None
        per_sample_cost = usage["actual_cost_usd"] / max(state.new_written, 1)
        if limit_checkpoint is not None and limit_target_total is not None:
            checkpoint_complete = post["passed"] and post["records"] >= limit_target_total
            limit_checkpoint = {
                **limit_checkpoint,
                "status": "complete" if checkpoint_complete else "in_progress",
                "current_total": post["records"],
                "completed_at": utcnow() if checkpoint_complete else None,
            }

        summary = {
            "version": "v4-role-e2e-2",
            "status": "complete" if post["passed"] else "incomplete",
            "mode": "smoke" if args.smoke else "full" if args.limit is None else f"limit_{args.limit}",
            "generated_at": utcnow(),
            "output": str(cfg.output_jsonl.resolve()),
            "rejected_audit": str(cfg.rejected_jsonl.resolve()),
            "target_total": sum(state.targets.values()),
            "existing_before": len(existing_raw),
            "new_records": state.new_written,
            "total_records": post["records"],
            "model": cfg.model,
            "thinking": cfg.thinking,
            "budget_usd": cfg.max_cost_usd,
            "usage": usage,
            "elapsed_seconds": round(elapsed, 3),
            "estimated_full_hours": round(estimated_full_hours, 3) if estimated_full_hours is not None else None,
            "estimated_full_cost_usd": round(per_sample_cost * FULL_TARGET, 6),
            "preflight": preflight,
            "counters": dict(sorted(counters.items())),
            "post_validate": post,
            "full_run_performed": args.limit is None and not args.smoke,
            "limit_checkpoint": limit_checkpoint,
        }
        _write_json(cfg.summary_json, summary)
        if limit_checkpoint is not None:
            _write_json(cfg.checkpoint_json, limit_checkpoint)
        if args.smoke:
            records, _ = _read_jsonl(cfg.output_jsonl)
            _write_smoke_review(cfg, planned_smoke, records, summary)

        print("\nRUN SUMMARY")
        print("=" * 72)
        print(f"Trạng thái       : {summary['status']}")
        print(f"Mẫu mới          : {state.new_written}")
        print(f"Tổng trong output: {post['records']}")
        print(f"Chi phí ghi nhận : ${usage['actual_cost_usd']:.6f}")
        print(f"Thời gian        : {elapsed:.1f}s")
        print(f"Output           : {cfg.output_jsonl.resolve()}")
        print(f"Summary          : {cfg.summary_json.resolve()}")
        if post["distribution_warnings"]:
            print("Cảnh báo phân phối:")
            for warning in post["distribution_warnings"]:
                print(f"  - {warning}")
        return 0 if summary["status"] == "complete" else 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(_amain(argv))
    except KeyboardInterrupt:
        print("\nĐã dừng an toàn. Chạy lại cùng lệnh để resume, không sinh trùng.", file=sys.stderr)
        return 130
    except BudgetExceededError as exc:
        print(f"LỖI BUDGET: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
