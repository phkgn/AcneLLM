"""Pipeline v2 — dùng lại nguyên bộ điều phối của v1, thay đúng một hàm.

Cách làm: nạp `roledata/pipeline.py` thành MỘT MODULE RIÊNG mang `__package__`
là `datagen.roledatav2`, nên mọi `from .config import ...` / `from .gates import ...`
bên trong nó tự trỏ vào module v2. Không copy 614 dòng, không mutate
`datagen.roledata.pipeline` (chạy v1 sau v2 trong cùng process vẫn đúng —
`test_pipeline.py::test_v1_pipeline_untouched` giữ điều đó).

Sau khi nạp, chỉ `_generate_one` bị thay: nó là chỗ duy nhất cần biết về
`len_target` và `points`. Toàn bộ preflight, checkpoint, resume, budget guard,
post-validate giữ nguyên.

ponytail: cách này gãy nếu `roledata/pipeline.py` đổi sang import tuyệt đối.
`test_pipeline.py::test_base_pipeline_uses_relative_imports` bắt được ngay.
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import importlib.util
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..roledata import pipeline as _v1_pipeline
from .config import MODULE_ROOT
from .gates import anchor_variants
from .generator import CaseSpec

_IMPL_NAME = f"{__package__}._pipeline_impl"


def _load_impl():
    """Nạp bản sao riêng của pipeline v1 với relative import trỏ vào v2."""
    if _IMPL_NAME in sys.modules:
        return sys.modules[_IMPL_NAME]
    source = MODULE_ROOT.parent / "roledata" / "pipeline.py"
    spec = importlib.util.spec_from_file_location(_IMPL_NAME, source)
    if spec is None or spec.loader is None:  # pragma: no cover - đường không xảy ra
        raise RuntimeError(f"Không nạp được {source}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = __package__
    sys.modules[_IMPL_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[_IMPL_NAME]
        raise
    return module


impl = _load_impl()
logger = impl.logger


def _case_spec_dict(case: CaseSpec) -> dict[str, Any]:
    return asdict(case)


@functools.lru_cache(maxsize=2)
def _skeletons_cached(path_str: str) -> dict[str, dict[str, Any]]:
    from .phase1 import load_skeleton_index

    return load_skeleton_index(Path(path_str))


def _skeletons(cfg, smoke: bool) -> dict[str, dict[str, Any]]:
    """Chỉ mục sườn của phase 1. Đọc một lần rồi giữ trong bộ nhớ.

    Import trễ để tránh vòng: `phase1` cần `impl` từ chính module này.
    """
    path = cfg.skeleton_smoke_path if smoke else cfg.skeleton_path
    return _skeletons_cached(str(path))


def _anchor_ok(record: dict[str, Any], anchor: str) -> bool:
    """v2 rải BA biến thể anchor, nên resume phải chấp nhận cả ba.

    Bản v1 so bằng đúng một chuỗi; giữ nguyên nó ở đây thì mọi bản ghi mang biến
    thể B hoặc C bị coi là hỏng và resume chết ngay lần chạy lại đầu tiên.
    """
    system = record.get("messages", [{}])[0].get("content")
    variants = anchor_variants()
    return system == anchor or (bool(variants) and system in variants)


async def _generate_one(
    *,
    case: CaseSpec,
    ordinal: int,
    smoke: bool,
    cfg,
    anchor: str,
    style_guide: str,
    provider,
    writer,
    corpus,
    skip_gates: bool,
) -> tuple[bool, int]:
    """PHASE 2 — chỉ sinh câu trả lời. Đề bài đọc từ sườn của phase 1.

    Lời người dùng, `points`, tài liệu và `input_style` đều đã chốt ở phase 1 và
    KHÔNG được sinh lại ở đây. Nhờ vậy `points_covered` kiểm được điều nó tự nhận
    là kiểm: câu trả lời có phủ những ý mà nó không tự viết ra hay không.

    Retry ở vòng này vì thế rẻ hơn hẳn bản một-phase: trượt gate thì sinh lại mỗi
    câu trả lời, đề bài giữ nguyên.
    """
    record_id = impl._record_id(case.id, ordinal, smoke)
    index = _skeletons(cfg, smoke)
    # Phân biệt hai tình huống rất khác nhau:
    #   - KHÔNG có sườn nào  -> quên chạy phase 1, dừng ngay kèm lệnh cần chạy;
    #   - thiếu ĐÚNG mẫu này -> phase 1 đã bỏ cuộc ở ordinal đó sau 4 lượt (chuyện
    #     bình thường: trùng lặp, không phải tiếng Việt...). Bỏ qua slot và chạy
    #     tiếp. Bản đầu raise cho cả hai và làm sập nguyên mẻ 232 mẫu vì một lỗ.
    if not index:
        raise RuntimeError(
            "Chưa có sườn nào. Chạy phase 1 trước:\n"
            f"    python -m datagen.roledatav2.phase1 {'--smoke ' if smoke else ''}--yes"
        )
    skeleton = index.get(record_id)
    if skeleton is None:
        logger.warning("Bỏ qua %s: phase 1 không sinh được sườn cho ordinal này", record_id)
        return False, 0

    requested_input_style = str(skeleton["input_style"])
    spec = _case_spec_dict(case)
    variants = anchor_variants()
    record_anchor = (
        variants[int(skeleton.get("anchor_variant") or 0)] if variants else anchor
    )
    move_name = str(skeleton.get("opening_move") or "")
    move_text = str(skeleton.get("opening_move_text") or "")
    len_target = int(skeleton["len_target"])
    last_turn_len_target = skeleton.get("last_turn_len_target")
    context = skeleton.get("synthetic_context")
    sources = list(skeleton.get("synthetic_context_sources") or [])
    context_meta = dict(skeleton.get("context_meta") or {})
    skeleton_points = [str(item) for item in (skeleton.get("points") or [])]
    user_turns_in = [str(item) for item in (skeleton.get("user_turns") or [])]
    rejected = 0

    for content_attempt in range(1, cfg.max_content_attempts + 1):
        prompt_case: dict[str, Any] = {
            "id": case.id,
            "sample_kind": case.sample_kind,
            "behavior": case.behavior,
            "context": case.context,
            "synthetic_context": context,
            "generation_meta": context_meta,
            "requested_input_style": requested_input_style,
            "len_chars": case.len_chars,
            "last_turn_len_chars": case.last_turn_len_chars,
            "len_target": len_target,
            "last_turn_len_target": last_turn_len_target,
            "min_points": case.min_points,
            "require_structure": case.require_structure,
            "echo_user_facts": case.echo_user_facts,
            "opening_move_name": move_name,
            "opening_move_text": move_text,
            "user": skeleton.get("user"),
            "user_turns": user_turns_in or None,
            "points": skeleton_points,
        }
        messages = impl.build_gen_prompt(prompt_case, cfg, record_anchor, style_guide, phase=2)
        try:
            generated = await provider.generate(messages)
            # Đề bài lấy từ sườn, KHÔNG lấy từ phản hồi của teacher. Teacher có
            # trả kèm `user` cũng bị bỏ qua — đó là điểm mấu chốt của hai phase.
            points = skeleton_points
            turns = None
            user = skeleton.get("user")
            assistant = None

            if case.id == "R9_multiturn":
                replies = generated.get("assistant_turns")
                if not isinstance(replies, list) or not replies:
                    raise ValueError("R9 thiếu assistant_turns")
                replies = [str(item) for item in replies]
                if len(replies) != len(user_turns_in):
                    raise ValueError(
                        f"R9 cần {len(user_turns_in)} lượt assistant, nhận {len(replies)}"
                    )
                # Ghép xen kẽ bằng CODE, không nhờ model — thứ tự lượt là bất biến
                # cấu trúc, giao cho model là tự chuốc lỗi không cần thiết.
                turns = [
                    turn
                    for pair in zip(user_turns_in, replies)
                    for turn in (
                        {"role": "user", "content": pair[0]},
                        {"role": "assistant", "content": pair[1]},
                    )
                ]
                answer_for_judge = "\n".join(replies)
            else:
                assistant = generated.get("assistant")
                if not isinstance(assistant, str) or not assistant.strip():
                    raise ValueError("Thiếu khoá assistant dạng chuỗi")
                answer_for_judge = assistant

            generation_meta = dict(context_meta)
            generation_meta["audience"] = skeleton.get("audience", "general")
            generation_meta["requested_input_style"] = requested_input_style
            generation_meta["len_target"] = len_target
            if last_turn_len_target is not None:
                generation_meta["last_turn_len_target"] = last_turn_len_target
            # KHÔNG gọi judge nữa. Vòng 1 gọi ~1.755 lần và nhận về một hằng số:
            # 1043 điểm 5 / 2 điểm 4 / 0 điểm <=3 trên `grounding_judge`, và
            # 491/491 điểm 5 trên `knowledge_accuracy`. Nguyên nhân là judge dùng
            # chính model vừa sinh câu trả lời để chấm nó. Thay bằng gate
            # `entities_grounded` — tất định, miễn phí, và bắt được 192 mẫu bịa
            # tên thuốc/số mà judge đã cho 5/5.
            generation_meta["anchor_variant"] = int(skeleton.get("anchor_variant") or 0)
            generation_meta["opening_move"] = move_name
            generation_meta["phase1_gen_model"] = skeleton.get("gen_model")

            record = impl.to_record(
                case,
                user if isinstance(user, str) else None,
                assistant if isinstance(assistant, str) else None,
                record_anchor,
                {
                    "record_id": record_id,
                    "input_style": requested_input_style,
                    "turns": turns,
                    "synthetic_context": context,
                    "synthetic_context_sources": sources,
                    "generation_meta": generation_meta,
                    "gen_model": cfg.model,
                    "points": [str(item) for item in points],
                    "len_target": len_target,
                },
            )
            result = impl.evaluate_record(
                record, record_anchor, None if skip_gates else corpus, case_spec=spec
            )
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
            impl.append_audit(
                cfg.rejected_path,
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "id": record_id,
                    "case": case.id,
                    "content_attempt": content_attempt,
                    "len_target": len_target,
                    "reasons": result.reasons,
                    "checks": {
                        key: value
                        for key, value in result.checks.items()
                        if key.startswith(("length_band", "points", "has_structure", "context_in"))
                    },
                    # Không có hai trường này thì audit vô dụng cho việc chẩn đoán:
                    # `content_attempt` chỉ là SỐ THỨ TỰ lượt, nên trước đây file
                    # audit ghi lý do trượt mà không ghi thứ bị trượt. Muốn biết vì
                    # sao `points_covered` đỏ thì phải so được ý với đáp án.
                    "answer": answer_for_judge[:1500],
                    "points": points,
                },
            )
            logger.warning(
                "Rejected case=%s id=%s attempt=%d/%d len=%d target=%d reasons=%s",
                case.id,
                record_id,
                content_attempt,
                cfg.max_content_attempts,
                len(answer_for_judge),
                len_target,
                ",".join(result.reasons),
            )
        except Exception as exc:
            rejected += 1
            impl.append_audit(
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
                "Candidate error case=%s id=%s attempt=%d/%d type=%s",
                case.id,
                record_id,
                content_attempt,
                cfg.max_content_attempts,
                type(exc).__name__,
            )
    return False, rejected


# Chỉ thay trong BẢN SAO của v2; `datagen.roledata.pipeline` không bị đụng.
impl._generate_one = _generate_one
impl._anchor_ok = _anchor_ok

run_pipeline = impl.run_pipeline
build_parser = impl.build_parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_pipeline(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted; append-only output và checkpoint an toàn để resume.")
        return 130


assert _v1_pipeline is not impl, "pipeline v2 phải là bản sao riêng, không phải module v1"

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
