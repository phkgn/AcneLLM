from unittest.mock import MagicMock

import httpx

from acne_llm.llm.ollama_backend import OllamaBackend


class _StreamContext:
    def __init__(self, response: httpx.Response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, exc_type, exc, tb):
        return False


def test_generate_json_retries_with_fallback_on_runner_termination():
    backend = OllamaBackend(model="primary", fallback_model="fallback")
    backend._client = MagicMock()

    first = httpx.Response(
        500,
        request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        content=b'{"error":"llama runner process has terminated: %!w(nil)"}',
    )
    second = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        content=b'{"message":{"content":"{\\"ok\\": true}"}}',
    )
    backend._client.post.side_effect = [first, second]

    out = backend.generate_json("sys", "usr", schema={})
    assert out == '{"ok": true}'
    assert backend._client.post.call_count == 2
    assert backend.model == "primary"
    first_payload = backend._client.post.call_args_list[0].kwargs["json"]
    second_payload = backend._client.post.call_args_list[1].kwargs["json"]
    assert first_payload["model"] == "primary"
    assert second_payload["model"] == "fallback"


def test_generate_json_includes_num_predict():
    backend = OllamaBackend(model="m", num_predict=1024)
    backend._client = MagicMock()
    backend._client.post.return_value = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        content=b'{"message":{"content":"{}"}}',
    )
    backend.generate_json("sys", "usr", schema={})
    call_args = backend._client.post.call_args
    payload = call_args.kwargs["json"]
    assert payload["options"]["num_predict"] == 1024


def test_stream_text_retries_with_fallback_without_mutating_model():
    backend = OllamaBackend(model="primary", fallback_model="fallback")
    backend._client = MagicMock()

    first = httpx.Response(
        500,
        request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        content=b'{"error":"llama runner process has terminated: %!w(nil)"}',
    )
    second = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        content=(
            b'{"message":{"content":"xin "},"done":false}\n'
            b'{"message":{"content":"chao"},"done":false}\n'
            b'{"done":true}\n'
        ),
    )
    backend._client.stream.side_effect = [_StreamContext(first), _StreamContext(second)]

    assert list(backend.stream_text("sys", "usr")) == ["xin ", "chao"]
    assert backend.model == "primary"
    first_payload = backend._client.stream.call_args_list[0].kwargs["json"]
    second_payload = backend._client.stream.call_args_list[1].kwargs["json"]
    assert first_payload["model"] == "primary"
    assert second_payload["model"] == "fallback"


def test_health_uses_short_timeout_client():
    backend = OllamaBackend(model="m")
    backend._client = MagicMock()
    backend._health_client = MagicMock()
    backend._health_client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://localhost:11434/api/tags"),
        content=b'{"models":[]}',
    )

    assert backend.health() is True
    backend._health_client.get.assert_called_once_with("/api/tags")
    backend._client.get.assert_not_called()
