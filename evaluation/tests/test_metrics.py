import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.metrics.retrieval import (
    average_precision, duplicate_rate, evaluate_query, hit_at_k, irrelevant_rate,
    ndcg_at_k_graded, precision_at_k, recall_at_k,
)
from evaluation.metrics.deterministic import (
    citation_valid, forbidden_claims, parse_success, pregnancy_safety,
)


def test_recall_precision_hit():
    retrieved = ["a", "b", "c", "d"]
    relevant = {"b", "x"}
    assert recall_at_k(retrieved, relevant, 4) == 0.5
    assert precision_at_k(retrieved, relevant, 4) == 0.25
    assert hit_at_k(retrieved, relevant, 1) == 0.0
    assert hit_at_k(retrieved, relevant, 2) == 1.0


def test_ndcg_graded_perfect_ranking():
    grades = {"a": 2, "b": 1, "c": 0}
    assert ndcg_at_k_graded(["a", "b", "c"], grades, 3) == 1.0
    assert ndcg_at_k_graded(["c", "b", "a"], grades, 3) < 1.0


def test_map():
    assert average_precision(["a", "x", "b"], {"a", "b"}, 10) == (1.0 + 2 / 3) / 2


def test_irrelevant_and_duplicate():
    assert irrelevant_rate(["a", "b"], {"a": 2}, 2) == 0.5
    assert duplicate_rate(["mụn viêm ở cằm nặng", "mụn viêm ở cằm nặng"]) > 0
    assert duplicate_rate(["hoàn toàn khác nhau", "văn bản riêng biệt xyz"]) == 0.0


def test_evaluate_query_keys():
    out = evaluate_query(["a"], {"a": 2})
    assert out["hit@1"] == 1.0 and "ndcg@5" in out and "map@10" in out


def _rec(structured=None, answer="", used=None):
    return {"structured": structured, "answer": answer, "used_chunks": used or []}


def test_parse_success_detects_fallback_object():
    bad = {"confidence": 0.1, "causes": ["Không thể phân tích phản hồi từ LLM, vui lòng thử lại."]}
    assert parse_success(_rec(structured=bad)) is False
    assert parse_success(_rec(structured={"confidence": 0.8, "causes": ["x"]})) is True
    assert parse_success(_rec()) is None


def test_citation_valid_structured_and_prose():
    s = {"recommendations": [{"action": "x", "source_chunk_id": "c1"}]}
    assert citation_valid(_rec(structured=s, used=["c1", "c2"])) is True
    assert citation_valid(_rec(structured=s, used=["c9"])) is False
    assert citation_valid(_rec(answer="Dùng BP [1] nhé [2].", used=["c1", "c2"])) is True
    assert citation_valid(_rec(answer="Sai nè [5].", used=["c1"])) is False


def test_legacy_trailing_single_one_is_not_a_real_prose_citation():
    from evaluation.metrics.deterministic import citation_present

    record = _rec(answer="Nội dung trả lời chỉ được vá trang trí. [1]", used=["c1"])

    assert citation_present(record, required=True) is False
    assert citation_valid(record) is None


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
