from __future__ import annotations


def test_grounding_summary_uses_sentence_denominator_not_record_average():
    from evaluation.analysis.report import _grounding_summary

    summary = _grounding_summary([
        {
            "grounded_sentence_rate": 1.0,
            "grounding_eligible_sentence_count": 1,
            "grounding_grounded_sentence_count": 1,
            "unsupported_sentences": [],
        },
        {
            "grounded_sentence_rate": 0.5,
            "grounding_eligible_sentence_count": 4,
            "grounding_grounded_sentence_count": 2,
            "unsupported_sentences": ["u1", "u2"],
        },
    ])

    assert summary == {
        "grounded_sentence_rate": 0.6,
        "grounding_counts": {
            "records_applicable": 2,
            "eligible_sentences": 5,
            "grounded_sentences": 3,
            "unsupported_sentences": 2,
        },
    }


def test_gate_config_uses_grounding_threshold():
    from evaluation.common import EVAL_DIR, load_yaml

    generation = load_yaml(EVAL_DIR / "configs" / "gate.yaml")["generation"]

    assert generation["grounded_sentence_rate"] == 0.50
    assert "parse_success_rate" not in generation


def test_new_prose_report_has_no_structured_contract_columns(tmp_path):
    from evaluation.analysis.report import _write_markdown

    path = tmp_path / "report.md"
    _write_markdown(path, {
        "generated_at": "now",
        "systems": {},
        "comparisons": {},
        "holm_correction": {},
    })
    markdown = path.read_text(encoding="utf-8")
    assert "parse" not in markdown.casefold()
    assert "empty_core_fields" not in markdown
    assert "legacy_cite" not in markdown


def test_report_excludes_invalid_faithfulness_and_recomputes_claim_ratio():
    from evaluation.analysis.report import _faithfulness_score

    valid = {
        "n_claims": 2,
        "faithfulness": 0.9,
        "claims": [
            {"text": "a", "verdict": "supported"},
            {"text": "b", "verdict": "not_found"},
        ],
    }
    invalid = {
        "n_claims": 1,
        "faithfulness": 0.0,
        "claims": [{"text": "a", "verdict": "invalid"}],
    }
    assert _faithfulness_score(valid) == 0.5
    assert _faithfulness_score(invalid) is None


def test_extractive_snippet_uses_sentence_boundary_when_available():
    from evaluation.adapters.extractive import _truncate_snippet

    text = (
        "Câu đầu tiên đủ dài để trở thành một câu hoàn chỉnh trong đoạn trích. "
        "Câu thứ hai không được phép bị cắt giữa một khuyến nghị y khoa quan trọng."
    )
    snippet = _truncate_snippet(text, 88)
    assert snippet == "Câu đầu tiên đủ dài để trở thành một câu hoàn chỉnh trong đoạn trích."


def test_extractive_answer_uses_source_headings_without_inline_markers():
    from types import SimpleNamespace

    from evaluation.adapters.extractive import ExtractiveAdapter

    adapter = ExtractiveAdapter({"id": "s4", "max_snippet_chars": 700})
    chunk = SimpleNamespace(
        chunk_id="chunk-1",
        source="nguon-thu",
        text="Đây là câu trích nguyên văn.",
        metadata={"title": "Bài thử"},
    )

    result = adapter.generate({}, {"chunks": [chunk]})

    assert "Nguồn 1" in result["answer"]
    assert "[1]" not in result["answer"]


def test_faithfulness_context_prefers_exact_context_captured_from_prompt():
    from evaluation.adapters.ollama_batch import _extract_retrieved_context
    from evaluation.judges.run_judge import _context_text

    prompt = (
        "<retrieved_context>\nNguồn 1 — Tiêu đề\n"
        "Đây là đoạn thực sự model đã thấy.\n"
        "</retrieved_context>\n<current_message>Hoi</current_message>"
    )
    exact = _extract_retrieved_context(prompt)
    assert exact == (
        "Nguồn 1 — Tiêu đề\n"
        "Đây là đoạn thực sự model đã thấy."
    )
    record = {
        "trace": {
            "faithfulness_context": exact,
            "context_chunks": [{"chunk_id": "chunk-a", "text": "text rộng hơn"}],
        }
    }
    assert _context_text(record) == exact


def test_faithfulness_rejects_blank_claim_after_one_schema_repair():
    from evaluation.judges.run_judge import judge_faithfulness

    class FakeClient:
        def __init__(self):
            self.calls: list[tuple[str, bool]] = []

        def judge(self, prompt: str, *, use_cache: bool = True):
            self.calls.append((prompt, use_cache))
            return {"claims": [{"id": 1, "text": "   ", "type": "fact"}]}

    client = FakeClient()
    result = judge_faithfulness(client, {
        "answer": "Một câu trả lời.",
        "trace": {"faithfulness_context": "Tài liệu thật."},
    })
    assert result == {
        "n_claims": 0,
        "faithfulness": None,
        "contradiction_rate": None,
        "claims": [],
        "valid": False,
        "error": "claim_schema_failure",
    }
    assert len(client.calls) == 2
    assert client.calls[1][1] is False
