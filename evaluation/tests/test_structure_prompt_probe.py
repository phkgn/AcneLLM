from evaluation.unit.eval_structure_prompt_probe import (
    append_probe_instruction,
    core_content_status,
    summarize_rows,
)


def test_probe_instruction_is_bounded_and_eval_labeled() -> None:
    prompt = "<task>Trả JSON.</task>"

    rendered = append_probe_instruction(prompt, "Không để hai mảng cùng rỗng.")

    assert prompt in rendered
    assert "<eval_contract_probe>" in rendered
    assert "Không để hai mảng cùng rỗng." in rendered


def test_core_content_status_distinguishes_disclaimer_only() -> None:
    assert core_content_status({
        "causes": [],
        "recommendations": [],
        "disclaimer": "Thông tin tham khảo.",
    }) == {
        "empty_core_fields": True,
        "content_in_disclaimer_only": True,
    }
    assert core_content_status({
        "causes": ["bít tắc"],
        "recommendations": [],
        "disclaimer": "",
    })["empty_core_fields"] is False


def test_probe_summary_keeps_denominators_explicit() -> None:
    summary = summarize_rows([
        {"parse_success": True, "empty_core_fields": False},
        {"parse_success": True, "empty_core_fields": True},
        {"parse_success": False, "empty_core_fields": False},
    ])

    assert summary == {
        "n_attempted": 3,
        "n_parse_success": 2,
        "parse_success_rate": 0.6667,
        "empty_core_fields_count": 1,
        "empty_core_fields_rate": 0.3333,
    }
