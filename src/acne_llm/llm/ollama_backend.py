"""Ollama HTTP backend. Supports JSON-schema constrained decoding."""
from __future__ import annotations
from collections.abc import Iterator
import json

import httpx
from loguru import logger


class OllamaBackend:
    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "qwen2.5:7b",
                 fallback_model: str | None = None,
                 num_ctx: int = 8192, timeout: float = 180.0,
                 health_timeout: float = 5.0,
                 num_predict: int = 2048):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._health_client = httpx.Client(base_url=self.base_url, timeout=health_timeout)

    @staticmethod
    def _is_runner_terminated(err: Exception) -> bool:
        msg = str(err).lower()
        return "runner process has terminated" in msg or "model runner" in msg

    def _post_chat(self, payload: dict, model: str | None = None) -> dict:
        if model is not None:
            payload = dict(payload)
            payload["model"] = model
        r = self._client.post("/api/chat", json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = r.text[:1000]
            raise RuntimeError(f"Ollama chat failed: {e}; body={detail}") from e
        return r.json()

    def _post_chat_stream(self, payload: dict, model: str | None = None) -> Iterator[str]:
        if model is not None:
            payload = dict(payload)
            payload["model"] = model

        with self._client.stream("POST", "/api/chat", json=payload) as r:
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                detail = r.read().decode("utf-8", errors="replace")[:1000]
                raise RuntimeError(f"Ollama stream failed: {e}; body={detail}") from e

            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"Ollama stream returned non-JSON line: {line[:120]}")
                    continue
                if data.get("done"):
                    break
                content = (data.get("message") or {}).get("content") or ""
                if content:
                    yield content

    def _chat(self, payload: dict) -> dict:
        try:
            return self._post_chat(payload, model=self.model)
        except Exception as e:
            if not self.fallback_model or self.model == self.fallback_model or not self._is_runner_terminated(e):
                raise

            logger.warning(
                f"Ollama model '{self.model}' failed with runner termination; "
                f"retrying once with fallback model '{self.fallback_model}'"
            )
            return self._post_chat(payload, model=self.fallback_model)

    def _chat_stream(self, payload: dict) -> Iterator[str]:
        try:
            yield from self._post_chat_stream(payload, model=self.model)
        except Exception as e:
            if not self.fallback_model or self.model == self.fallback_model or not self._is_runner_terminated(e):
                raise

            logger.warning(
                f"Ollama model '{self.model}' failed with runner termination; "
                f"retrying stream once with fallback model '{self.fallback_model}'"
            )
            yield from self._post_chat_stream(payload, model=self.fallback_model)

    def health(self) -> bool:
        try:
            r = self._health_client.get("/api/tags")
            return r.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health fail: {e}")
            return False

    def list_models(self) -> list[str]:
        try:
            r = self._health_client.get("/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    def generate_json(self, system: str, user: str, schema: dict,
                      temperature: float = 0.3) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
            "stream": False,
        }
        return self._chat(payload)["message"]["content"]

    def generate_text(self, system: str, user: str,
                      temperature: float = 0.3) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
            "stream": False,
        }
        return self._chat(payload)["message"]["content"]

    def stream_text(self, system: str, user: str,
                    temperature: float = 0.3) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
            "stream": True,
        }
        yield from self._chat_stream(payload)

    def close(self):
        self._client.close()
        self._health_client.close()
