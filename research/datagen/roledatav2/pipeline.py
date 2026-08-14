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
import importlib.util
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from ..roledata import pipeline as _v1_pipeline
from .config import MODULE_ROOT
from .generator import CaseSpec, sample_len_target
from .knowledge import context_is_vietnamese

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
    """Bản v1 + mục tiêu độ dài và `points`. Phần còn lại giữ nguyên từng dòng."""
    record_id = impl._record_id(case.id, ordinal, smoke)
    requested_input_style = impl.planned_input_style(case.id, ordinal)
    spec = _case_spec_dict(case)
    len_target = sample_len_target(case.id, ordinal, case.len_chars)
    last_turn_len_target = (
        sample_len_target(f"{case.id}:last", ordinal, case.last_turn_len_chars)
        if case.last_turn_len_chars
        else None
    )
    rejected = 0

    for content_attempt in range(1, cfg.max_content_attempts + 1):
        context, sources, context_meta = impl.synthesize_context(case, cfg, sequence=ordinal - 1)
        prompt_case: dict[str, Any] = {
            "id": case.id,
            "sample_kind": case.sample_kind,
            "behavior": case.behavior,
            "context": case.context,
            "synthetic_context": context,
            "generation_meta": context_meta,
            "requested_input_style": requested_input_style,
            "len_chars": case.len_chars,
            "len_target": len_target,
            "last_turn_len_target": last_turn_len_target,
            "min_points": case.min_points,
            "require_structure": case.require_structure,
        }
        messages = impl.build_gen_prompt(prompt_case, cfg, anchor, style_guide)
        try:
            generated = await provider.generate(messages)
            turns = generated.get("turns") if case.id == "R9_multiturn" else None
            user = generated.get("user")
            assistant = generated.get("assistant")
            points = generated.get("points") or []
            if not isinstance(points, list):
                raise ValueError("Generated points is not a list")

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
            generation_meta["len_target"] = len_target
            if last_turn_len_target is not None:
                generation_meta["last_turn_len_target"] = last_turn_len_target
            if generated.get("input_style") != requested_input_style:
                raise ValueError(
                    "Generated input_style does not match deterministic augmentation schedule"
                )
            context_text = "\n".join(item["text"] for item in context or [])
            if case.id == "K1_knowledge_anchor":
                generation_meta["knowledge_accuracy"] = await provider.judge_knowledge(
                    context_text, answer_for_judge
                )
            # Nguồn tiếng Anh: chấm bám-nguồn bằng judge thay vì trùng token
            # (câu trả lời buộc phải là tiếng Việt nên trùng token luôn = 0).
            if context and not context_is_vietnamese(context):
                generation_meta["grounding_judge"] = (
                    generation_meta.get("knowledge_accuracy")
                    if case.id == "K1_knowledge_anchor"
                    else await provider.judge_knowledge(context_text, answer_for_judge)
                )

            record = impl.to_record(
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
                    "points": [str(item) for item in points],
                    "len_target": len_target,
                },
            )
            result = impl.evaluate_record(
                record, anchor, None if skip_gates else corpus, case_spec=spec
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
