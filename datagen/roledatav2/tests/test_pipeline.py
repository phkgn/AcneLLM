"""Pipeline v2: cách ly khỏi v1, và chạy khô một bản ghi không gọi API."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from datagen.roledata import pipeline as v1_pipeline
from datagen.roledatav2 import pipeline as v2_pipeline
from datagen.roledatav2.config import Config
from datagen.roledatav2.gates import CorpusGateState
from datagen.roledatav2.generator import sample_len_target

from .helpers import ANCHOR, answer_of_length, case_by_id, points_for

impl = v2_pipeline.impl


# ── cách ly ────────────────────────────────────────────────────────────────
def test_impl_is_a_private_copy() -> None:
    assert impl is not v1_pipeline
    assert impl.__name__ == "datagen.roledatav2._pipeline_impl"


def test_v1_pipeline_untouched() -> None:
    """Nạp v2 rồi chạy v1 trong cùng process vẫn phải đúng."""
    assert v1_pipeline.Config.__module__ == "datagen.roledata.config"
    assert v1_pipeline.evaluate_record.__module__ == "datagen.roledata.gates"
    assert v1_pipeline._generate_one.__module__ == "datagen.roledata.pipeline"
    assert v1_pipeline.CASE_TYPE_TARGETS["B1_grounded_role"] == 380


def test_impl_resolves_v2_modules() -> None:
    assert impl.Config.__module__ == "datagen.roledatav2.config"
    assert impl.evaluate_record.__module__ == "datagen.roledatav2.gates"
    assert impl.to_record.__module__ == "datagen.roledatav2.generator"
    assert impl.CASE_TYPE_TARGETS["B1_grounded_role"] == 470
    assert impl._generate_one.__module__ == "datagen.roledatav2.pipeline"


def test_base_pipeline_uses_relative_imports() -> None:
    """Trần chịu đựng của mẹo nạp lại: import tuyệt đối là gãy cách ly.

    Bắt ở đây thay vì phát hiện lúc đang generate 3.500 mẫu bằng tiền thật.
    """
    source = Path(v1_pipeline.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    swappable = {"config", "gates", "generator", "writer", "anchor"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in swappable:
            assert node.level == 1, f"import {node.module} phải là tương đối"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("datagen.roledata"), alias.name


# ── chạy khô một bản ghi ───────────────────────────────────────────────────
class FakeProvider:
    """Đóng vai OpenAI: trả về đúng contract, không đụng mạng."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[list[dict[str, str]]] = []

    async def generate(self, messages):
        self.prompts.append(messages)
        return self.payload

    async def judge_knowledge(self, context, answer):
        return 5


class FakeWriter:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def append(self, record) -> bool:
        self.records.append(record)
        return True


def _cfg(tmp_path: Path) -> Config:
    modelfile = tmp_path / "Modelfile"
    canonical = tmp_path / "canonical.txt"
    modelfile.write_text(f'FROM test\nSYSTEM """{ANCHOR}"""\n', encoding="utf-8")
    canonical.write_text(ANCHOR + "\n", encoding="utf-8")
    return Config(
        api_key="offline-test",
        anchor_path=modelfile,
        canonical_path=canonical,
        output_dir=tmp_path / "output",
        model="fake-model",
    )


def _run(case_id: str, payload: dict, tmp_path: Path, ordinal: int = 1):
    cfg = _cfg(tmp_path)
    provider = FakeProvider(payload)
    writer = FakeWriter()
    accepted, rejected = asyncio.run(
        impl._generate_one(
            case=case_by_id(case_id),
            ordinal=ordinal,
            smoke=True,
            cfg=cfg,
            anchor=ANCHOR,
            style_guide="giọng thân thiện",
            provider=provider,
            writer=writer,
            corpus=CorpusGateState(14, 8),
            skip_gates=False,
        )
    )
    return accepted, rejected, writer, provider


def test_dry_run_accepts_a_valid_record(tmp_path: Path) -> None:
    case = case_by_id("R10_special_population")
    target = sample_len_target(case.id, 1, case.len_chars)
    answer = (
        answer_of_length(target - 120, bullets=3)
        + "\nBạn nên trao đổi với bác sĩ da liễu trước khi dùng bất kỳ sản phẩm nào nhé."
    )
    payload = {
        "user": "Mình đang mang thai, bị mụn nhiều ở cằm thì nên làm sao?",
        "assistant": answer,
        "points": points_for(3),
        "input_style": "standard",
        "audience": "general",
    }
    accepted, rejected, writer, provider = _run("R10_special_population", payload, tmp_path)
    assert accepted is True and rejected == 0
    record = writer.records[0]
    assert record["gate_results"]["passed"] is True
    assert record["points"]
    assert record["len_target"] == target


def test_prompt_carries_length_and_points(tmp_path: Path) -> None:
    payload = {
        "user": "Mình bị mụn.",
        "assistant": answer_of_length(300),
        "input_style": "standard",
        "audience": "general",
    }
    _, _, _, provider = _run("B1_grounded_role", payload, tmp_path)
    prompt = provider.prompts[0][1]["content"]
    case = case_by_id("B1_grounded_role")
    target = sample_len_target(case.id, 1, case.len_chars)
    assert f"khoảng {target} ký tự" in prompt
    assert f"ít nhất {case.min_points} ý riêng biệt" in prompt
    assert "CẤU TRÚC BẮT BUỘC" in prompt
    assert '"points"' in prompt


def test_dry_run_rejects_short_answer_and_audits(tmp_path: Path) -> None:
    payload = {
        "user": "Mình bị mụn.",
        "assistant": "Bạn nên rửa mặt dịu nhẹ nhé.",
        "points": points_for(1),
        "input_style": "standard",
        "audience": "general",
    }
    cfg = _cfg(tmp_path)
    accepted, rejected, writer, _ = _run("B1_grounded_role", payload, tmp_path)
    assert accepted is False
    assert rejected == cfg.max_content_attempts
    assert writer.records == []


def test_dry_run_rejects_flat_prose_without_bullets(tmp_path: Path) -> None:
    case = case_by_id("K1_knowledge_anchor")
    target = sample_len_target(case.id, 1, case.len_chars)
    payload = {
        "user": "Benzoyl peroxide dùng thế nào?",
        "assistant": answer_of_length(target),  # đúng độ dài, KHÔNG có cấu trúc
        "points": points_for(3),
        "input_style": "standard",
        "audience": "general",
    }
    accepted, _, writer, _ = _run("K1_knowledge_anchor", payload, tmp_path)
    assert accepted is False, "độ dài đúng nhưng không có cấu trúc thì vẫn phải trượt"


def test_input_style_mismatch_is_rejected(tmp_path: Path) -> None:
    """Bất biến của v1 phải còn nguyên sau khi thay `_generate_one`."""
    payload = {
        "user": "Mình bị mụn.",
        "assistant": answer_of_length(1_300, bullets=3),
        "points": points_for(3),
        "input_style": "teencode",  # ordinal=1 phải là "standard"
        "audience": "general",
    }
    accepted, rejected, _, _ = _run("B1_grounded_role", payload, tmp_path)
    assert accepted is False and rejected > 0


def test_len_target_is_deterministic_and_in_band() -> None:
    case = case_by_id("K1_knowledge_anchor")
    low, high = case.len_chars
    values = [sample_len_target(case.id, ordinal, case.len_chars) for ordinal in range(1, 200)]
    assert all(low <= value <= high for value in values)
    assert values == [sample_len_target(case.id, o, case.len_chars) for o in range(1, 200)]
    assert len(set(values)) > 50, "phải trải trong band, không dồn về một giá trị"
