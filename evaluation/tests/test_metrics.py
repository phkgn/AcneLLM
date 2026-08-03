import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.metrics.deterministic import (
    evaluate_record, forbidden_claims, parse_success, pregnancy_safety,
    vacuous_answer,
)


def _rec(structured=None, answer="", used=None):
    return {"structured": structured, "answer": answer, "used_chunks": used or []}


def test_parse_success_detects_fallback_object():
    bad = {"confidence": 0.1, "causes": ["Không thể phân tích phản hồi từ LLM, vui lòng thử lại."]}
    assert parse_success(_rec(structured=bad)) is False
    assert parse_success(_rec(structured={"confidence": 0.8, "causes": ["x"]})) is True
    assert parse_success(_rec()) is None


def test_pregnancy_safety():
    assert pregnancy_safety(_rec(answer="Bạn nên dùng tretinoin mỗi tối."), True) is False
    assert pregnancy_safety(
        _rec(answer="Không dùng tretinoin khi mang thai, hãy hỏi bác sĩ."), True) is True
    assert pregnancy_safety(_rec(answer="dùng tretinoin"), False) is None


def test_pregnancy_safety_negation_in_next_sentence():
    # Regression từ smoke run: phủ định ở câu SAU câu chứa term — không được false-positive
    ans = ("Isotretinoin có thể gây dị tật bẩm sinh nghiêm trọng ở thai nhi và ảnh hưởng "
           "đến sự phát triển trí tuệ của trẻ. Do đó, phụ nữ mang thai tuyệt đối không "
           "được sử dụng loại thuốc này.")
    assert pregnancy_safety(_rec(answer=ans), True) is True


def test_vacuous_answer():
    from evaluation.metrics.deterministic import vacuous_answer
    empty = {"severity": "unknown", "causes": [], "recommendations": [],
             "disclaimer": "Thông tin tham khảo."}
    assert vacuous_answer(_rec(structured=empty)) is True
    assert vacuous_answer(_rec(structured={"causes": ["x"]})) is False
    assert vacuous_answer(_rec()) is None


def test_forbidden_claims():
    hits = forbidden_claims(_rec(answer="Bạn có thể tự nặn mụn tại nhà."),
                            ["tự nặn mụn"])
    assert hits == ["tự nặn mụn"]


def test_new_prose_record_omits_legacy_structured_metrics():
    record = _rec(answer="Rửa mặt dịu nhẹ.", used=["chunk-1"])
    record["timings_ms"] = {"total": 123}

    metrics = evaluate_record(record, {"user_context": {}, "forbidden_claims": []})

    assert "parse_success" not in metrics
    assert "vacuous_answer" not in metrics
    assert metrics["answer_char_count"] == len(record["answer"])


def test_legacy_structured_record_keeps_legacy_metrics_reader():
    record = _rec(
        structured={
            "confidence": 0.8,
            "causes": ["x"],
            "recommendations": [{"action": "y"}],
        },
        answer="Nội dung legacy.",
        used=["chunk-1"],
    )

    metrics = evaluate_record(record, {"user_context": {}, "forbidden_claims": []})

    assert metrics["parse_success"] is True
    assert metrics["vacuous_answer"] is False
