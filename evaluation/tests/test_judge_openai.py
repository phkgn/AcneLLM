from __future__ import annotations

import json
import urllib.error
from types import SimpleNamespace

import pytest

from evaluation.judges import clients
from evaluation.judges.clients import (
    DEFAULT_JUDGE_WORKERS,
    DEFAULT_OPENAI_JUDGE_MODEL,
    JudgeAPIError,
    JudgeClient,
)
from evaluation.judges.run_judge import _prepare_resume, judge_pointwise


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> JudgeClient:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(clients, "CACHE_DB", tmp_path / "judge-cache.sqlite")
    return JudgeClient()


def test_openai_snapshot_is_the_default(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.provider == "openai"
    assert client.model == DEFAULT_OPENAI_JUDGE_MODEL
    assert DEFAULT_JUDGE_WORKERS == 4


def test_judge_rejects_deepseek_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(clients, "CACHE_DB", tmp_path / "judge-cache.sqlite")
    with pytest.raises(ValueError, match="provider=openai"):
        JudgeClient("deepseek")


def test_openai_gpt5_request_uses_json_mode_and_minimal_reasoning(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse({
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        })

    monkeypatch.setattr(clients.urllib.request, "urlopen", fake_urlopen)
    assert client.judge("Return a JSON object", use_cache=False) == {"ok": True}
    assert captured["payload"]["reasoning_effort"] == "minimal"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert "temperature" not in captured["payload"]
    assert client.calls == 1
    assert client.total_cost_usd > 0


def test_non_retryable_api_error_fails_fast(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    attempts = 0

    def payment_required(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise urllib.error.HTTPError(
            "https://api.openai.com/v1/chat/completions",
            402,
            "Payment Required",
            {},
            None,
        )

    monkeypatch.setattr(clients.urllib.request, "urlopen", payment_required)
    with pytest.raises(JudgeAPIError, match="HTTP 402"):
        client.judge("Return JSON", use_cache=False)
    assert attempts == 1


def test_resume_retries_invalid_rows_and_keeps_valid_rows(tmp_path):
    model = DEFAULT_OPENAI_JUDGE_MODEL
    path = tmp_path / "s1.judged.jsonl"
    valid_scores = {
        "correctness": 4,
        "completeness": 4,
        "safety": 5,
        "relevance": 4,
        "fluency": 4,
        "instruction_following": 4,
    }
    rows = [
        {
            "sample_id": "valid",
            "judge_provider": "openai",
            "judge_model": model,
            "judge_status": "valid",
            "pointwise": valid_scores,
        },
        {
            "sample_id": "retry",
            "judge_provider": "openai",
            "judge_model": model,
            "judge_status": "invalid",
            "pointwise": None,
        },
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    client = SimpleNamespace(provider="openai", model=model)
    assert _prepare_resume(path, client, pairwise=False) == {"valid"}
    remaining = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["sample_id"] for row in remaining] == ["valid"]


def test_resume_rejects_mixed_judge_provenance(tmp_path):
    path = tmp_path / "s1.judged.jsonl"
    path.write_text(
        json.dumps({
            "sample_id": "old",
            "judge_model": "deepseek-chat",
            "judge_status": "invalid",
            "pointwise": None,
        }) + "\n",
        encoding="utf-8",
    )
    client = SimpleNamespace(provider="openai", model=DEFAULT_OPENAI_JUDGE_MODEL)
    with pytest.raises(RuntimeError, match="run directory mới"):
        _prepare_resume(path, client, pairwise=False)


def test_pointwise_schema_violation_gets_one_uncached_repair():
    valid = {
        "correctness": 1,
        "completeness": 2,
        "safety": 3,
        "relevance": 4,
        "fluency": 5,
        "instruction_following": 4,
    }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def judge(self, prompt, *, use_cache=True):
            self.calls.append((prompt, use_cache))
            return {**valid, "correctness": 0} if len(self.calls) == 1 else valid

    client = FakeClient()
    result = judge_pointwise(
        client,
        {"answer": "Một câu trả lời", "trace": {}},
        {"user_query": "Tôi nên làm gì?"},
    )
    assert result == valid
    assert len(client.calls) == 2
    assert client.calls[1][1] is False
    assert "Không bao giờ dùng 0" in client.calls[1][0]
