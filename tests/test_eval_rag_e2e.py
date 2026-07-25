from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.eval_rag as ev


def test_parse_judge_response_accepts_clean_json():
    raw = '{"accuracy": 5, "safety": 4, "completeness": 5, "tone": 4, "reasoning": "Good."}'

    parsed = ev._parse_judge_response(raw)

    assert parsed == {
        "accuracy": 5,
        "safety": 4,
        "completeness": 5,
        "tone": 4,
        "reasoning": "Good.",
    }


def test_parse_judge_response_accepts_fenced_json():
    raw = """```json
{"accuracy": 4, "safety": 5, "completeness": 4, "tone": 5, "reasoning": "Safe."}
```"""

    parsed = ev._parse_judge_response(raw)

    assert parsed["accuracy"] == 4
    assert parsed["tone"] == 5


def test_parse_judge_response_rejects_malformed_or_missing_fields():
    assert ev._parse_judge_response("not json") is None
    assert ev._parse_judge_response('{"accuracy": 5, "safety": 5}') is None
    assert ev._parse_judge_response(
        '{"accuracy": 6, "safety": 5, "completeness": 5, "tone": 5, "reasoning": "x"}'
    ) is None


def test_format_chat_answer_from_advise_output_dict():
    payload = {
        "disclaimer": "Thong tin tham khảo.",
        "causes": ["Da dầu có thể góp phần gây mụn."],
        "recommendations": [
            {"action": "Rửa mặt dịu nhẹ.", "rationale": "Giảm kích ứng."},
            {"action": "Gặp bác sĩ nếu mụn nặng."},
        ],
        "red_flags": [{"flag": "Sưng đau lan rộng", "reason": "Có thể nhiễm trùng"}],
    }

    answer = ev._format_chat_answer(payload)

    assert "Thong tin tham khảo." in answer
    assert "Rửa mặt dịu nhẹ. (Giảm kích ứng.)" in answer
    assert "Canh bao: Sưng đau lan rộng (Có thể nhiễm trùng)" in answer


def test_e2e_api_url_targets_current_stream_endpoint():
    assert ev._api_url("http://localhost:8000", "/chat/stream") == (
        "http://localhost:8000/api/v1/chat/stream"
    )
    assert ev._api_url("http://localhost:8000/api/v1", "/chat/stream") == (
        "http://localhost:8000/api/v1/chat/stream"
    )


def test_parse_sse_chat_collects_tokens_and_done():
    raw = "\n\n".join([
        'data: {"event":"token","data":"Xin chào"}',
        'data: {"event":"token","data":" bạn"}',
        'data: {"event":"done","data":{"mode":"hybrid","latency_ms":123,"used_chunks":["c1"]}}',
        "",
    ])

    parsed = ev._parse_sse_chat(raw)

    assert parsed["answer"] == "Xin chào bạn"
    assert parsed["used_chunks"] == ["c1"]
    assert parsed["mode"] == "hybrid"
    assert parsed["latency_ms"] == 123


def test_run_e2e_eval_with_mocked_backend_and_judge(monkeypatch, tmp_path: Path):
    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        "\n".join([
            json.dumps({"query": "mụn viêm ở cằm?", "relevant_chunk_ids": ["c1"]}),
            json.dumps({"query": "mụn đầu đen xử lý sao?", "relevant_chunk_ids": ["c2"]}),
        ]),
        encoding="utf-8",
    )
    out = tmp_path / "report.json"

    def fake_post(api_url: str, query: str, chat_mode: str, timeout: int) -> dict:
        return {
            "disclaimer": "Tham khảo.",
            "causes": [f"Tra loi cho {query}"],
            "recommendations": [{"action": "Không tự ý nặn mụn."}],
            "used_chunks": ["c1"],
            "mode": "hybrid",
            "model_name": "mock-ollama",
        }

    def fake_judge(prompt: str, api_key: str, base_url: str, model: str, **kwargs) -> str:
        return json.dumps({
            "accuracy": 5,
            "safety": 5,
            "completeness": 4,
            "tone": 4,
            "reasoning": "Good enough.",
        })

    monkeypatch.setattr(ev, "_post_chat_api", fake_post)
    monkeypatch.setattr(ev, "_call_deepseek", fake_judge)
    monkeypatch.setattr(ev, "_read_env_credentials", lambda: ("key", "https://api.deepseek.com", "deepseek-chat"))

    args = argparse.Namespace(
        queries=str(queries),
        out=str(out),
        lang=None,
        trust=None,
        api_url="http://localhost:8000",
        chat_mode="hybrid",
        timeout=180,
        no_judge=False,
        deepseek_model="",
        judge_delay=0.0,
    )

    assert ev.run_e2e_eval(args) is True

    report = json.loads(out.read_text(encoding="utf-8"))
    summary = report["summary"]
    assert summary["evaluated"] == 2
    assert summary["chat_succeeded"] == 2
    assert summary["judge_succeeded"] == 2
    assert summary["avg_scores"]["accuracy"] == 5.0
    assert summary["citation_coverage"] == 1.0
