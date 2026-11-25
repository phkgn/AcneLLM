"""Test hồi quy CHÍNH của v2: tài liệu phải sống sót tới file train.

Lỗi gốc ở v1: `to_record` để tài liệu ở field `synthetic_context` cạnh `messages`,
`finalize/export.py` chỉ ghi `{"id","messages"}` -> 0/2.945 mẫu xuất ra có tài liệu.
Hệ quả đo được ở run_full_v3_2: `RRR - RNR = 0.000`, RAG đóng góp bằng 0.

Nếu một trong các test file này đỏ thì KHÔNG được chạy generate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, meta

from datagen.roledata.generator import to_record as to_record_v1
from datagen.roledatav2.config import Config
from datagen.roledatav2.finalize import export
from datagen.roledatav2.generator import (
    PROMPT_TEMPLATE_VARS,
    RUNTIME_TEMPLATE,
    render_user_message,
)
from datagen.roledatav2.writer import iter_jsonl

from .helpers import ANCHOR, CONTEXT, answer_of_length, case_by_id, make_record

CONTEXT_CASES = (
    "B1_grounded_role",
    "B2_missing_answer",
    "B3_irrelevant_chunk",
    "B4_conflicting_docs",
    "B5_depth_anchor",
    "K1_knowledge_anchor",
)


def _user_text(record: dict) -> str:
    return next(m["content"] for m in record["messages"] if m["role"] == "user")


@pytest.mark.parametrize("case_id", CONTEXT_CASES)
def test_context_lands_inside_messages(case_id: str) -> None:
    record = make_record(case_id, answer_of_length(1_200, bullets=3), context=CONTEXT)
    user_text = _user_text(record)
    assert "Tài liệu tham khảo:" in user_text
    assert CONTEXT[0]["text"][:60] in user_text
    assert "Tin nhắn hiện tại:" in user_text


def test_v1_to_record_still_loses_context() -> None:
    """Chốt lại chẩn đoán. Test này đỏ nghĩa là v1 đã được sửa -> v2 hết lý do tồn tại."""
    case = {"id": "B1_grounded_role", "context": True}
    record = to_record_v1(
        case,
        "Da mình bị mụn",
        "Câu trả lời.",
        ANCHOR,
        {"record_id": "x", "synthetic_context": CONTEXT, "generation_meta": {}},
    )
    assert CONTEXT[0]["text"][:60] not in _user_text(record)


def test_context_survives_export_round_trip(tmp_path: Path) -> None:
    """Export chỉ ghi {"id","messages"} — bài test thật là sau khi qua nó."""
    modelfile = tmp_path / "Modelfile"
    canonical = tmp_path / "canonical.txt"
    modelfile.write_text(f'FROM test\nSYSTEM """{ANCHOR}"""\n', encoding="utf-8")
    canonical.write_text(ANCHOR + "\n", encoding="utf-8")
    cfg = Config(
        api_key="offline-test",
        anchor_path=modelfile,
        canonical_path=canonical,
        output_dir=tmp_path / "output",
    )
    record = make_record("B1_grounded_role", answer_of_length(1_200, bullets=3), context=CONTEXT)
    cfg.splits_dir.mkdir(parents=True, exist_ok=True)
    cfg.train_split_path.write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    export(cfg)

    exported = list(iter_jsonl(cfg.export_path))
    assert len(exported) == 1
    assert set(exported[0]) == {"id", "messages"}, "export vẫn chỉ giữ id + messages"
    assert CONTEXT[0]["text"][:60] in _user_text(exported[0]), "tài liệu bị mất khi export"


def test_no_context_case_has_no_document_block() -> None:
    record = make_record("R1_identity", answer_of_length(300))
    assert "Tài liệu tham khảo:" not in _user_text(record)


def test_multiturn_puts_context_only_on_first_user_turn() -> None:
    """Hiện chưa case nào vừa `context: true` vừa sinh turns, nhưng nếu sau này có
    thì tài liệu phải chỉ nằm ở lượt user ĐẦU — production cũng chỉ có một khối
    "Tài liệu tham khảo" cho lượt hiện tại. Dựng bằng case B1 (context: true)."""
    turns = [
        {"role": "user", "content": "Mình bị mụn ở cằm."},
        {"role": "assistant", "content": answer_of_length(400)},
        {"role": "user", "content": "Da mình hơi dầu."},
        {"role": "assistant", "content": answer_of_length(1_100, bullets=3)},
    ]
    record = make_record("B1_grounded_role", "", turns=turns, context=CONTEXT)
    users = [m["content"] for m in record["messages"] if m["role"] == "user"]
    assert "Tài liệu tham khảo:" in users[0]
    assert "Tài liệu tham khảo:" not in users[1]


def test_r9_has_no_context_by_design() -> None:
    """R9 khai `context: false`, nên không bao giờ có khối tài liệu."""
    turns = [
        {"role": "user", "content": "Mình bị mụn ở cằm."},
        {"role": "assistant", "content": answer_of_length(400)},
    ]
    record = make_record("R9_multiturn", "", turns=turns, context=CONTEXT)
    assert all(
        "Tài liệu tham khảo:" not in m["content"]
        for m in record["messages"]
        if m["role"] == "user"
    )


def test_template_vars_are_all_supplied() -> None:
    """Chặn đúng cái bug đã giết `render_runtime_user` của v1: thiếu `prompt_note`.

    Template thêm biến mới mà quên khai trong PROMPT_TEMPLATE_VARS -> test đỏ,
    thay vì UndefinedError giữa lúc generate 3.500 mẫu.
    """
    cfg = Config(api_key="offline-test")
    env = Environment(loader=FileSystemLoader(str(cfg.project_root / "config" / "prompts")))
    source = env.loader.get_source(env, RUNTIME_TEMPLATE)[0]
    declared = meta.find_undeclared_variables(env.parse(source))
    missing = declared - set(PROMPT_TEMPLATE_VARS)
    assert not missing, f"{RUNTIME_TEMPLATE} khai báo biến chưa được cấp: {sorted(missing)}"


def test_v1_render_helper_is_still_broken() -> None:
    """Ghi lại lý do v2 không import `datagen.render_context.render_runtime_user`."""
    from jinja2 import UndefinedError

    from datagen.render_context import render_runtime_user

    with pytest.raises(UndefinedError):
        render_runtime_user("Da mình bị mụn", ["Đoạn tài liệu."])


def test_render_uses_production_template_order() -> None:
    """Tài liệu đứng trước, tin nhắn hiện tại đứng cuối — đúng thứ tự production."""
    rendered = render_user_message("Câu hỏi của mình.", ["Fact một.", "Fact hai."])
    assert rendered.index("Tài liệu tham khảo:") < rendered.index("Tin nhắn hiện tại:")
    assert "Nguồn 1 —" in rendered and "Nguồn 2 —" in rendered
    assert rendered.rstrip().endswith("Câu hỏi của mình.")


def test_render_rejects_empty_description() -> None:
    with pytest.raises(ValueError):
        render_user_message("   ", ["Fact."])
