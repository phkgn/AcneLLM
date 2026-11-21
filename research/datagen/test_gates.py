"""Focused tests for ROLE dataset gates.

Usage:
    python -m pytest -q datagen/test_gates.py
"""
from __future__ import annotations

from datagen.gates import (
    DuplicateGuard,
    EvaluationNgramIndex,
    conflict_rule_check,
    knowledge_leak_check,
    load_drug_terms,
    missing_answer_rule_check,
    scenario_constraint_check,
    validate_record,
)
from datagen.render_context import render_runtime_user


def test_knowledge_leak_catches_drug_and_numeric_regimen() -> None:
    terms = load_drug_terms()
    result = knowledge_leak_check(
        "Bạn có thể dùng isotretinoin 10 mg trong 2 tuần.",
        terms,
    )
    assert not result["pass"]
    assert "isotretinoin" in result["drug_term_hits"]
    assert any("mg" in hit for hit in result["numeric_regimen_hits"])
    assert any("tuan" in hit for hit in result["numeric_regimen_hits"])


def test_knowledge_leak_allows_role_only_answer() -> None:
    result = knowledge_leak_check(
        "Mình có thể hỗ trợ bạn hiểu vấn đề da mụn và chuẩn bị câu hỏi để đi khám.",
        load_drug_terms(),
    )
    assert result["pass"]


def test_duplicate_guard_rejects_accentless_duplicate() -> None:
    guard = DuplicateGuard()
    guard.add("first", "Da mình nổi mụn, mình nên làm gì?")
    hit = guard.check("Da minh noi mun minh nen lam gi")
    assert hit is not None
    assert hit["kind"] == "exact_internal"
    assert hit["matched_sample_id"] == "first"


def test_evaluation_index_reads_user_query_and_accentless_8gram(tmp_path) -> None:
    source = tmp_path / "answer_quality_test.jsonl"
    source.write_text(
        '{"sample_id":"x","user_query":"Da mình nổi nhiều nốt đỏ đau ở vùng cằm mấy hôm nay"}\n',
        encoding="utf-8",
    )
    with EvaluationNgramIndex(tmp_path / "unused.sqlite3", 8) as index:
        stats = index.build([source])
        hits = index.check("Da minh noi nhieu not do dau o vung cam may hom nay")
    assert stats["user_texts"] == 1
    assert stats["unique_ngrams"] > 0
    assert any(hit.mode == "accentless" for hit in hits)


def test_validate_record_accepts_single_pair_contract() -> None:
    system = "SYSTEM production"
    record = {
        "id": "role-r1-000001",
        "sample_kind": "R1_identity",
        "input_style": "standard",
        "synthetic_context": False,
        "knowledge_leak_check": "pass",
        "grounded_sentence_rate": None,
        "gen_model": "z-ai/glm-5.2-free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "[CÂU HỎI HIỆN TẠI]\nBạn là ai?"},
            {"role": "assistant", "content": "Mình là AcneLLM."},
        ],
    }
    assert validate_record(record, system) == []


def test_validate_record_rejects_non_verbatim_system() -> None:
    record = {
        "id": "role-r1-000001",
        "sample_kind": "R1_identity",
        "input_style": "standard",
        "synthetic_context": False,
        "knowledge_leak_check": "pass",
        "grounded_sentence_rate": None,
        "gen_model": "z-ai/glm-5.2-free",
        "messages": [
            {"role": "system", "content": "changed"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ],
    }
    assert "system_prompt_not_verbatim" in validate_record(record, "production")


def test_render_context_uses_production_template_order() -> None:
    rendered = render_runtime_user("Mình cần hiểu điều này.", ["Fact thứ nhất.", "Fact thứ hai."])
    assert rendered == (
        "[TÀI LIỆU Y KHOA THAM KHẢO]\n"
        "Nguồn 1 —\nFact thứ nhất.\n\n"
        "Nguồn 2 —\nFact thứ hai.\n\n"
        "[CÂU HỎI HIỆN TẠI]\nMình cần hiểu điều này."
    )


def test_missing_answer_rule_allows_empathy_and_doctor_direction() -> None:
    result = missing_answer_rule_check(
        (
            "Mình hiểu bạn đang lo. Tài liệu chưa đề cập câu hỏi này. "
            "Mình khuyên bạn hỏi trực tiếp bác sĩ da liễu để được hướng dẫn an toàn."
        ),
        ["Tài liệu chỉ mô tả cách làm sạch da dịu nhẹ."],
        load_drug_terms(),
    )
    assert result["pass"]


def test_b5_scenario_constraint_rejects_causal_smoking_context() -> None:
    result = scenario_constraint_check(
        "B5",
        raw_users=["Hút thuốc có gây mụn không?"],
        contexts=["Hút thuốc lá được cho là làm mụn nặng hơn."],
        answer="Mối liên hệ này chưa chắc chắn.",
        drug_terms=load_drug_terms(),
    )
    assert not result["pass"]
    assert "hut thuoc" in result["banned_causal_topic_hits"]


def test_conflict_rule_excludes_source_comparison_control_sentence() -> None:
    contexts = [
        "Da khô có thể hợp với sản phẩm làm sạch dạng kem dịu nhẹ.",
        "Da dầu có thể hợp với sản phẩm làm sạch dạng gel dịu nhẹ.",
    ]
    answer = (
        "Tài liệu có hai hướng dẫn khác nhau tùy loại da. "
        "Nguồn 1 nói da khô có thể hợp với sản phẩm làm sạch dạng kem dịu nhẹ. "
        "Nguồn 2 nói da dầu có thể hợp với sản phẩm làm sạch dạng gel dịu nhẹ. "
        "Bạn nên hỏi bác sĩ nếu chưa biết loại nào phù hợp."
    )
    assert conflict_rule_check(answer, contexts, load_drug_terms())["pass"]
