"""Regression contracts for the one-command ROLE datagen pipeline."""
from __future__ import annotations

import json

from datagen.config import CASE_TYPE_RATIOS, compute_budget
from datagen.gates import (
    PhraseFrequencyGuard,
    input_naturalness_check,
    standard_code_switch_check,
    output_language_quality_check,
    case_behavior_check,
    scenario_constraint_check,
    validate_b5_pairs,
    vocative_consistency_check,
)
from datagen.main import _pick_target_case_type, _prepare_limit_checkpoint
from datagen.writer import DatasetWriter, load_existing_ids


def test_case_type_ratios_and_integer_budget_are_exact() -> None:
    assert abs(sum(CASE_TYPE_RATIOS.values()) - 1.0) < 1e-9
    budget = compute_budget(3500)
    assert sum(budget.values()) == 3500
    assert budget["B5"] == 70
    assert budget["R2"] == 450


def test_budget_dispatch_picks_largest_relative_deficit() -> None:
    targets = {"R1": 2, "R2": 4, "B1": 4}
    existing = {"R1": 2, "R2": 1, "B1": 3}
    assert _pick_target_case_type(targets, existing) == "R2"


def test_writer_appends_once_and_loads_existing_ids(tmp_path) -> None:
    output = tmp_path / "data.jsonl"
    row = {"id": "role-r1-000001", "sample_kind": "R1_identity"}
    with DatasetWriter(output) as writer:
        assert writer.write(row)
        assert not writer.write(row)
    assert load_existing_ids(output) == {"role-r1-000001"}
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_parent_vocative_rejects_co_oi_then_minh() -> None:
    result = vocative_consistency_check(
        "Chào em, con gái cô bị mụn.",
        "Cô ơi, mình hiểu cô lo. Cô cho mình biết thêm nhé.",
    )
    assert not result["passed"]
    assert "parent_vocative_mixed_with_minh" in result["reasons"]


def test_bac_si_is_not_misread_as_parent_vocative() -> None:
    result = vocative_consistency_check(
        "Bạn có phải bác sĩ da liễu không?",
        "Mình không phải bác sĩ, nhưng mình có thể hỗ trợ thông tin chung.",
    )
    assert result["passed"]


def test_mixed_ban_em_address_is_rejected() -> None:
    result = vocative_consistency_check(
        "Em đang dùng sữa rửa mặt này ạ.",
        "Bạn cho mình biết thêm, và em đang dùng loại nào?",
    )
    assert not result["passed"]
    assert "mixed_user_address_ban_em" in result["reasons"]


def test_unprompted_chu_address_is_rejected() -> None:
    result = vocative_consistency_check(
        "Mình lỡ nặn mụn hôm qua.",
        "Chú đang có vùng da sưng đỏ, chú cho mình biết thêm nhé.",
    )
    assert not result["passed"]
    assert "unprompted_parent_vocative" in result["reasons"]


def test_assistant_must_not_adopt_co_role() -> None:
    result = vocative_consistency_check(
        "Con bị mụn, cô giúp con với.",
        "Cô hiểu con đang lo, cô cháu mình xem nhé.",
    )
    assert not result["passed"]
    assert "assistant_self_as_honorific" in result["reasons"]


def test_standard_style_rejects_stray_english_word() -> None:
    result = standard_code_switch_check(
        "Da mình mostly ổn, chỉ còn vài nốt mụn.",
        input_style="standard",
    )
    assert not result["passed"]
    assert any(reason.startswith("unexpected_english:") for reason in result["reasons"])


def test_standard_style_rejects_cjk_fragment() -> None:
    result = standard_code_switch_check("Thuốc này 不见好转 nên làm sao?", input_style="standard")
    assert not result["passed"]
    assert "unexpected_cjk" in result["reasons"]


def test_standard_style_rejects_cyrillic_fragment() -> None:
    result = standard_code_switch_check("Mụn đỡ быстрее không?", input_style="standard")
    assert not result["passed"]
    assert "unexpected_cyrillic" in result["reasons"]


def test_augmented_naturalness_rejects_smoke_failures() -> None:
    assert not input_naturalness_check("có cần đc ko", "teencode")["passed"]
    assert not input_naturalness_check("em da kem tron", "no_accent")["passed"]
    assert input_naturalness_check(
        "em dung kem tron mot thang roi nen da bi noi mun",
        "no_accent",
    )["passed"]


def test_typo_style_must_not_be_all_no_accent() -> None:
    result = input_naturalness_check(
        "Chao ban minh bi mun o co nen lam gi",
        "typo",
    )
    assert not result["passed"]
    assert "typo_style_is_actually_no_accent" in result["reasons"]


def test_teencode_rejects_repeated_word_and_unknown_shortcut() -> None:
    result = input_naturalness_check(
        "trán e mun mun mọc nhiều h qua nên làm j z ad",
        "teencode",
    )
    assert not result["passed"]
    assert any(reason.startswith("augmented_input_repeated_word") for reason in result["reasons"])
    assert any(reason.startswith("teencode_not_in_whitelist") for reason in result["reasons"])


def test_input_quality_rejects_out_of_scope_body_area() -> None:
    result = input_naturalness_check("tui co nan mun o cai mong a", "no_accent")
    assert not result["passed"]
    assert "input_out_of_scope_body_area" in result["reasons"]


def test_b5_context_requires_all_four_low_risk_facts() -> None:
    incomplete = scenario_constraint_check(
        "B5",
        raw_users=["Mình cần routine cơ bản."],
        contexts=["Nên làm sạch dịu nhẹ và tránh chà xát mạnh."],
        answer="Giữ da sạch nhẹ nhàng.",
        drug_terms=set(),
    )
    assert not incomplete["passed"]
    complete = scenario_constraint_check(
        "B5",
        raw_users=["Mình cần routine cơ bản."],
        contexts=[
            "Làm sạch dịu nhẹ. Dùng dưỡng ẩm không gây bít tắc. "
            "Tránh nặn và cạy mụn."
        ],
        answer="Giữ routine đơn giản.",
        drug_terms=set(),
    )
    assert complete["passed"]


def test_b2_user_must_ask_something_absent_from_safe_context() -> None:
    contexts = ["Làm sạch dịu nhẹ. Dùng dưỡng ẩm không gây bít tắc."]
    answered = scenario_constraint_check(
        "B2",
        raw_users=["Mình nên làm sạch và dưỡng ẩm thế nào?"],
        contexts=contexts,
        answer="Tài liệu chưa đề cập.",
        drug_terms=set(),
    )
    assert not answered["passed"]
    missing = scenario_constraint_check(
        "B2",
        raw_users=["Ăn đồ ngọt có làm mụn nặng hơn không?"],
        contexts=contexts,
        answer="Tài liệu chưa đề cập.",
        drug_terms=set(),
    )
    assert missing["passed"]
    sugar = scenario_constraint_check(
        "B2",
        raw_users=["Ăn nhiều đường có làm mụn nặng hơn không?"],
        contexts=contexts,
        answer="Tài liệu chưa đề cập.",
        drug_terms=set(),
    )
    assert sugar["passed"]


def test_answer_language_quality_rejects_glad_and_broken_spacing() -> None:
    assert not output_language_quality_check("Mình glad bạn thấy ổn hơn.")["passed"]
    assert not output_language_quality_check("Tạo môi trường cho vi khu khuẩn phát triển.")["passed"]
    assert not output_language_quality_check("Điều này có tiềm  năng gây rát.")["passed"]
    assert not output_language_quality_check("Chào em, mình hỗ trợ nhé.")["passed"]
    assert not output_language_quality_check(
        "Minh khong phai bac si nen khong the chi dinh cach tri cu the cho ban luc nay."
    )["passed"]


def test_r5_only_clarifies_without_differential_diagnosis() -> None:
    bad = case_behavior_check(
        "R5",
        "Nốt đỏ này có thể là dị ứng hoặc viêm da. Bạn bị bao lâu rồi?",
    )
    assert not bad["passed"]
    good = case_behavior_check("R5", "Bạn bị bao lâu rồi và các nốt có ngứa không?",)
    assert good["passed"]


def test_r2_adapts_register_without_treatment_advice() -> None:
    bad = case_behavior_check("R2", "Em nên rửa mặt dịu nhẹ và dùng dưỡng ẩm nhé.")
    assert not bad["passed"]
    good = case_behavior_check("R2", "Mình sẽ giải thích ngắn gọn, phù hợp với điều em đang lo.")
    assert good["passed"]


def test_phrase_frequency_rejects_sixth_reuse_of_eight_words() -> None:
    guard = PhraseFrequencyGuard(ngram_size=8, max_occurrences=5)
    text = "mụn đầu trắng mụn mủ hay mụn sưng ở cằm"
    for index in range(5):
        assert guard.check(text)["passed"]
        guard.add(f"r-{index}", text)
    sixth = guard.check(text)
    assert not sixth["passed"]
    assert sixth["reasons"] == ["phrase_frequency_exceeded"]


def test_b5_pair_requires_same_sources_and_different_depth() -> None:
    base = {
        "sample_kind": "B5_depth_anchor",
        "anchor_group": "anchor-1",
        "synthetic_context_sources": ["Nguồn chung."],
    }
    rows = [
        {
            **base,
            "id": "role-b5-000001",
            "anchor_depth": "beginner",
            "raw_user_messages": ["Mình mới chăm da, nói đơn giản giúp mình."],
        },
        {
            **base,
            "id": "role-b5-000002",
            "anchor_depth": "advanced",
            "raw_user_messages": ["Mình hiểu routine cơ bản, giải thích kỹ hơn giúp mình."],
        },
    ]
    assert validate_b5_pairs(rows)["passed"]
    rows[1]["synthetic_context_sources"] = ["Nguồn khác."]
    result = validate_b5_pairs(rows)
    assert not result["passed"]
    assert "b5_anchor_sources_mismatch:anchor-1" in result["reasons"]


def test_b5_pair_rejects_incomplete_anchor() -> None:
    rows = [{
        "id": "role-b5-000001",
        "sample_kind": "B5_depth_anchor",
        "anchor_group": "anchor-1",
        "anchor_depth": "beginner",
        "synthetic_context_sources": ["Nguồn chung."],
        "raw_user_messages": ["Mình mới chăm da."],
    }]
    result = validate_b5_pairs(rows)
    assert not result["passed"]
    assert "b5_anchor_pair_size:anchor-1:1" in result["reasons"]


def test_writer_output_is_valid_jsonl(tmp_path) -> None:
    output = tmp_path / "data.jsonl"
    with DatasetWriter(output) as writer:
        writer.write({"id": "x", "text": "tiếng Việt"})
    assert json.loads(output.read_text(encoding="utf-8"))["text"] == "tiếng Việt"


def test_limit_checkpoint_resumes_same_fixed_target(tmp_path) -> None:
    from datagen.config import Config

    cfg = Config(
        output_jsonl=tmp_path / "train.jsonl",
        checkpoint_json=tmp_path / "limit_checkpoint.json",
    )
    first, target, remaining, resumed = _prepare_limit_checkpoint(
        cfg,
        limit=30,
        existing_count=76,
    )
    assert not resumed
    assert (first["start_total"], target, remaining) == (76, 106, 30)

    second, same_target, remaining, resumed = _prepare_limit_checkpoint(
        cfg,
        limit=30,
        existing_count=83,
    )
    assert resumed
    assert second["started_at"] == first["started_at"]
    assert (same_target, remaining) == (106, 23)
