"""Phase 1 — sinh SƯỜN: lời người dùng + ý mong đợi. Không sinh câu trả lời.

Vì sao tách khỏi phase 2
------------------------
Ở bản một-phase, `points` và `assistant` do CÙNG một lời gọi API sinh ra. Gate
`points_covered` vì thế chỉ chứng minh model tự nhất quán với chính nó — đúng
cùng một lỗi self-preference đã khiến `judge_knowledge` cho 1043 điểm 5 trên
1.045 mẫu và bị gỡ ở vòng 2. Tách đôi thì `points` là ràng buộc từ bên ngoài, và
`points_covered` trở thành phép đo thật.

Ba cái lợi kèm theo, đều đo được:
  * khử trùng lặp làm trên CÂU HỎI, trước khi tiêu tiền sinh câu trả lời — rẻ hơn
    nhiều so với khử trên câu trả lời, và đánh trúng gốc của `phrase_frequency`
    (4.851/7.650 lần loại ở vòng trước);
  * câu trả lời hỏng thì sinh lại câu trả lời, không vứt cả câu hỏi;
  * bộ sườn đông lạnh cho phép so sánh hai teacher theo cặp trên cùng đề bài.

Prompt phase 1 KHÔNG mang anchor và style guide (chúng chi phối giọng assistant,
mà phase này không viết assistant) nên rẻ hơn phase 2 đáng kể.

Chạy
----
    python -m datagen.roledatav2.phase1 --smoke --yes
    python -m datagen.roledatav2.phase1 --limit 200 --yes
    python -m datagen.roledatav2.phase1 --yes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..roledata.gates import _words
from .config import CASE_TYPE_TARGETS, Config
from .gates import anchor_variants, looks_english
from .generator import (
    CaseSpec,
    OpenAIGenerator,
    load_taxonomy,
    opening_moves,
    planned_anchor_variant,
    planned_opening_move,
    sample_len_target,
)
from .pipeline import impl

logger = logging.getLogger(__name__)

# Trùng câu hỏi thì trùng câu trả lời, và `phrase_frequency` sẽ loại ở phase 2 —
# tức trả tiền sinh đáp án rồi mới vứt. Chặn ngay ở đây rẻ hơn.
#
# NHƯNG "trùng MỘT 6-gram" không phải trùng lặp — đó là tiếng Việt bình thường.
# Bản đầu dùng luật đó và R1/R6/R7/R8 chết hàng loạt: không gian câu hỏi của case
# vai/ranh giới vốn hẹp ("bạn là ai", "chẩn đoán giúp mình"), nên gần như mọi mẫu
# đều chia ít nhất một cụm 6 từ với mẫu trước. R1_identity-000002 đốt đủ 4/4 lượt
# rồi bỏ cuộc. Đo TỈ LỆ trùng thay vì sự tồn tại, và bỏ qua câu quá ngắn — dưới
# ngưỡng đó thì không đủ dữ liệu để nói trùng hay không.
_DEDUP_NGRAM = 6
_DEDUP_MIN_WORDS = 14
_DEDUP_MAX_OVERLAP = 0.6


def _user_ngrams(text: str) -> set[tuple[str, ...]]:
    words = _words(text)
    if len(words) < _DEDUP_MIN_WORDS:
        return set()
    return {tuple(words[i : i + _DEDUP_NGRAM]) for i in range(max(0, len(words) - _DEDUP_NGRAM + 1))}


def _is_duplicate(grams: set[tuple[str, ...]], seen: set[tuple[str, ...]]) -> bool:
    """Trùng = PHẦN LỚN cụm đã thấy, không phải có một cụm đã thấy."""
    if not grams:
        return False
    return len(grams & seen) / len(grams) > _DEDUP_MAX_OVERLAP


def iter_skeletons(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_skeleton_index(path: Path) -> dict[str, dict[str, Any]]:
    """`record_id -> sườn`. Phase 2 tra bằng đúng khoá này."""
    return {str(item["record_id"]): item for item in iter_skeletons(path)}


async def _skeleton_one(
    *,
    case: CaseSpec,
    ordinal: int,
    smoke: bool,
    cfg: Config,
    style_guide: str,
    provider,
    seen: set[tuple[str, ...]],
) -> dict[str, Any] | None:
    record_id = impl._record_id(case.id, ordinal, smoke)
    requested_input_style = impl.planned_input_style(case.id, ordinal)
    variants = anchor_variants()
    record_anchor = planned_anchor_variant(case.id, ordinal, variants) if variants else ""
    move_name, move_text = planned_opening_move(
        case.id, ordinal, opening_moves(str(cfg.taxonomy_path))
    )
    len_target = sample_len_target(case.id, ordinal, case.len_chars)
    last_turn_len_target = (
        sample_len_target(f"{case.id}:last", ordinal, case.last_turn_len_chars)
        if case.last_turn_len_chars
        else None
    )

    for attempt in range(1, cfg.max_content_attempts + 1):
        context, sources, context_meta = impl.synthesize_context(case, cfg, sequence=ordinal - 1)
        prompt_case: dict[str, Any] = {
            "id": case.id,
            "sample_kind": case.sample_kind,
            "behavior": case.behavior,
            "context": case.context,
            "synthetic_context": context,
            # Template của B2/B4/B5/K1 đọc `generation_meta.missing_topic`,
            # `.depth`, `.knowledge_topic`. Thiếu nó thì StrictUndefined raise.
            "generation_meta": context_meta,
            "requested_input_style": requested_input_style,
            "len_chars": case.len_chars,
            "len_target": len_target,
            "last_turn_len_target": last_turn_len_target,
            "min_points": case.min_points,
            "require_structure": case.require_structure,
            "echo_user_facts": case.echo_user_facts,
            "user_turns": case.user_turns,
        }
        messages = impl.build_gen_prompt(prompt_case, cfg, "", style_guide, phase=1)
        try:
            generated = await provider.generate(messages)
            # KHÔNG loại vì nhãn `input_style` lệch. Lịch augmentation là tất định
            # và `to_record` vẫn dùng `requested_input_style` làm nguồn sự thật,
            # nên nhãn model trả về không đi đâu cả. Phép kiểm này chỉ xác nhận
            # model CHÉP LẠI đúng nhãn, không xác nhận nó đã BIẾN ĐỔI văn phong —
            # tức bắt oan mà không mua được gì. R8 trượt liên tục vì lý do này.
            if generated.get("input_style") != requested_input_style:
                logger.debug(
                    "input_style teacher trả %r, dùng lịch %r",
                    generated.get("input_style"),
                    requested_input_style,
                )

            if case.id == "R9_multiturn":
                turns = generated.get("user_turns")
                if not isinstance(turns, list) or not turns:
                    raise ValueError("R9 thiếu user_turns")
                user_turns = [str(item).strip() for item in turns if str(item).strip()]
                # Bắt ĐÚNG 3, không phải ">=2". Với 2 lượt thì chỉ có một lượt
                # assistant cuối gánh toàn bộ lời khuyên và nó tràn band (32/93
                # lần loại ở lần chạy 200 mẫu là `turn1` vượt trần 1.610).
                if len(user_turns) != 3:
                    raise ValueError(f"R9 cần đúng 3 lượt user, nhận {len(user_turns)}")
                user_text = "\n".join(user_turns)
                user_value: Any = None
            else:
                user = generated.get("user")
                if not isinstance(user, str) or not user.strip():
                    raise ValueError("thiếu khoá user dạng chuỗi")
                user_turns = None
                user_value = user.strip()
                user_text = user_value

            points = generated.get("points") or []
            if not isinstance(points, list):
                raise ValueError("points không phải list")
            points = [str(item).strip() for item in points if str(item).strip()]
            if case.min_points and len(points) < case.min_points:
                raise ValueError(f"cần >={case.min_points} points, nhận {len(points)}")

            # Tài liệu nguồn phần lớn tiếng Anh và teacher chép thẳng ngôn ngữ đó
            # sang. Smoke bắt được cả hai kiểu: lượt user tiếng Anh (B1) và points
            # tiếng Anh (K1 — "People with mild to moderate acne could be..."),
            # mà đáp án thì luôn tiếng Việt, nên `user_facts_echoed` và
            # `points_covered` đối chiếu token đều bằng 0 và trượt sạch 4/4 lượt.
            # Chỉ dẫn trong prompt là chưa đủ, phải có cổng chặn.
            if looks_english(user_text):
                raise ValueError(f"lời người dùng bằng tiếng Anh: {user_text[:60]!r}")
            for point in points:
                if looks_english(point):
                    raise ValueError(f"points bằng tiếng Anh: {point[:60]!r}")

            grams = _user_ngrams(user_text)
            if _is_duplicate(grams, seen):
                raise ValueError("lời người dùng trùng phần lớn với sườn đã nhận")
            seen |= grams

            return {
                "record_id": record_id,
                "case_id": case.id,
                "ordinal": ordinal,
                "user": user_value,
                "user_turns": user_turns,
                "points": points,
                "input_style": requested_input_style,
                "audience": str(generated.get("audience") or "general"),
                "synthetic_context": context,
                "synthetic_context_sources": sources,
                "context_meta": context_meta,
                "len_target": len_target,
                "last_turn_len_target": last_turn_len_target,
                "opening_move": move_name,
                "opening_move_text": move_text,
                "anchor_variant": variants.index(record_anchor) if variants else 0,
                "gen_model": cfg.model,
            }
        except Exception as exc:
            impl.append_audit(
                cfg.rejected_path,
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "phase": 1,
                    "id": record_id,
                    "case": case.id,
                    "attempt": attempt,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
            logger.warning(
                "Phase1 loại case=%s id=%s lần=%d/%d: %s",
                case.id,
                record_id,
                attempt,
                cfg.max_content_attempts,
                str(exc)[:160],
            )
    return None


async def run_phase1(args: argparse.Namespace) -> int:
    cfg = Config()
    impl.setup_logging(cfg, args.verbose)
    if not args.yes:
        logger.error("Không chạy khi thiếu --yes.")
        return 2
    if args.smoke and args.limit is not None:
        logger.error("Chọn --smoke HOẶC --limit, không dùng cả hai.")
        return 2

    problems = cfg.validate()
    if problems:
        for problem in problems:
            logger.error("Preflight: %s", problem)
        return 2

    cases = load_taxonomy(cfg)
    if {case.id: case.count for case in cases} != CASE_TYPE_TARGETS:
        logger.error("taxonomy không khớp CASE_TYPE_TARGETS")
        return 2
    if args.only_case:
        if args.only_case not in {case.id for case in cases}:
            logger.error("--only-case %s không có trong taxonomy", args.only_case)
            return 2
        cases = [case for case in cases if case.id == args.only_case]

    path = cfg.skeleton_smoke_path if args.smoke else cfg.skeleton_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.no_resume and path.exists():
        if args.only_case:
            # Chỉ bỏ sườn của case đang sinh lại; xoá cả file thì mất luôn phần
            # đã trả tiền cho 15 case kia.
            keep = [item for item in iter_skeletons(path) if item["case_id"] != args.only_case]
            path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in keep),
                encoding="utf-8",
            )
            logger.info("Giữ %d sườn của case khác, sinh lại %s", len(keep), args.only_case)
        else:
            path.unlink()

    existing = list(iter_skeletons(path))
    done: dict[str, set[int]] = {}
    seen: set[tuple[str, ...]] = set()
    for item in existing:
        done.setdefault(str(item["case_id"]), set()).add(int(item["ordinal"]))
        text = item.get("user") or "\n".join(item.get("user_turns") or [])
        seen |= _user_ngrams(str(text))

    if args.smoke:
        targets = {case.id: 1 for case in cases}
    elif args.limit is not None:
        targets = impl._checkpoint_targets(
            cfg, {k: len(v) for k, v in done.items()}, args.limit, {case.id for case in cases}
        )
    else:
        targets = {case.id: CASE_TYPE_TARGETS[case.id] for case in cases}

    slots: list[tuple[CaseSpec, int]] = [
        (case, ordinal)
        for case in cases
        for ordinal in range(1, targets.get(case.id, 0) + 1)
        if ordinal not in done.get(case.id, set())
    ]
    logger.info("Phase 1 bắt đầu: đã có %d sườn, cần thêm %d", len(existing), len(slots))

    provider = OpenAIGenerator(cfg)
    try:
        await provider.probe()
    except Exception as exc:
        logger.error("Probe provider hỏng: %s: %s", type(exc).__name__, exc)
        await provider.close()
        return 2

    style_guide = cfg.style_guide_path.read_text(encoding="utf-8")
    written = 0
    started = time.monotonic()
    with path.open("a", encoding="utf-8") as handle:
        for offset in range(0, len(slots), cfg.concurrency):
            batch = slots[offset : offset + cfg.concurrency]
            results = await asyncio.gather(
                *[
                    _skeleton_one(
                        case=case,
                        ordinal=ordinal,
                        smoke=args.smoke,
                        cfg=cfg,
                        style_guide=style_guide,
                        provider=provider,
                        seen=seen,
                    )
                    for case, ordinal in batch
                ]
            )
            for item in results:
                if item is not None:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                    written += 1
            handle.flush()
            logger.info("Phase 1 tiến độ: %d/%d sườn", written, len(slots))

    await provider.close()
    total = len(existing) + written
    logger.info(
        "Phase 1 xong: %d sườn trong %s (%.1f phút). Chạy phase 2: "
        "python -m datagen.roledatav2.pipeline --yes",
        total,
        path,
        (time.monotonic() - started) / 60,
    )
    return 0 if written == len(slots) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 1 — sinh sườn cho roledatav2")
    parser.add_argument("--yes", action="store_true", help="xác nhận chạy thật")
    parser.add_argument("--smoke", action="store_true", help="một sườn mỗi case")
    parser.add_argument("--limit", type=int, default=None, help="giới hạn tổng số sườn")
    parser.add_argument("--no-resume", action="store_true", help="xoá sườn cũ rồi làm lại")
    parser.add_argument("--only-case", default=None, help="chỉ sinh sườn cho một case")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_phase1(args))
    except KeyboardInterrupt:
        logger.warning("Dừng giữa chừng; file sườn append-only nên resume được.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
