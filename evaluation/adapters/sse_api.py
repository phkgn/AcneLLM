"""Tier T4 — e2e qua SSE API thật (routing + intake + retrieval + generation + safety).

Backend phải chạy với LLM_MODEL = model của condition; adapter verify qua /health trước
khi chạy (không tự đổi model được → runner dừng chờ bạn restart backend giữa conditions).
Mỗi sample dùng session mới (R8). SSE parse mirror scripts/eval_rag.py (đã kiểm chứng).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import uuid

from .base import SystemAdapter


class SseApiAdapter(SystemAdapter):
    def __init__(self, config: dict, experiment: dict):
        super().__init__(config)
        self.api_url = experiment.get("api_url", "http://localhost:8000").rstrip("/")
        self.chat_mode = experiment.get("chat_mode", "auto")
        self.timeout = experiment.get("request_timeout_s", 300)

    def _url(self, path: str, params: dict | None = None) -> str:
        base = self.api_url
        if not base.endswith("/api/v1"):
            base += "/api/v1"
        return base + path + ("?" + urllib.parse.urlencode(params) if params else "")

    def prepare(self) -> None:
        expected = self.config["model"]
        try:
            with urllib.request.urlopen(self._url("/health"), timeout=10) as resp:
                health = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Backend không phản hồi tại {self.api_url}: {exc}") from exc
        served = _find_model_name(health)
        if served and expected and served != expected:
            raise RuntimeError(
                f"Backend đang serve '{served}' nhưng condition {self.system_id} cần "
                f"'{expected}'. Đổi LLM_MODEL trong .env, restart backend rồi chạy lại."
            )
        if served is None:
            # health không expose model — ghi nhận, kiểm tra lại per-response nếu có
            self._health_model_unverified = True
        else:
            self._health_model_unverified = False

    def _request_payload(self, message: str, session_id: str, mode: str) -> dict:
        params = {"message": message, "mode": mode, "session_id": session_id}
        req = urllib.request.Request(
            self._url("/chat/stream", params),
            headers={"Accept": "text/event-stream"}, method="GET",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return _parse_sse(resp.read().decode("utf-8"))

    def generate(self, sample: dict, context: dict | None) -> dict:
        # R8: mỗi case có session riêng; mọi turn trong cùng scenario dùng cùng session.
        session_id = (
            f"eval-{self.system_id}-{sample['sample_id']}-{uuid.uuid4().hex[:10]}"
        )
        # T4 vẫn đi qua production routing/guardrails, nhưng ép đúng IV retrieval của S0–S3.
        mode = "hybrid" if self.config.get("retrieval") else "llm_only"
        history = sample.get("conversation_history") or []
        replayed = 0
        for turn in history:
            if not isinstance(turn, dict) or turn.get("role") != "user":
                continue
            history_payload = self._request_payload(
                str(turn.get("content") or ""), session_id, mode
            )
            if history_payload["errors"]:
                raise RuntimeError(
                    "history replay failed: " + "; ".join(history_payload["errors"])
                )
            replayed += 1

        payload = self._request_payload(sample["user_query"], session_id, mode)
        if payload["errors"]:
            raise RuntimeError("; ".join(payload["errors"]))
        returned_session = payload.get("session_id")
        if returned_session and returned_session != session_id:
            raise RuntimeError(
                f"Session mismatch: requested={session_id} returned={returned_session}"
            )
        self._trace.update({
            "primary_intent": payload.get("primary_intent"),
            "route_flags": payload.get("route_flags"),
            "mode": payload.get("mode"),
            "session_id": returned_session or session_id,
            "session_id_requested": session_id,
            "history_user_turns_replayed": replayed,
            "history_turns_expected": len(history),
            "history_replay_mode": (
                "user_turns_regenerated_in_same_session" if history else "none"
            ),
            "requested_mode": mode,
            "health_model_unverified": getattr(
                self, "_health_model_unverified", False
            ),
            "server_latency_ms": payload.get("latency_ms"),
        })
        return {
            "answer": payload["answer"],
            "structured": None,
            "used_chunks": payload["used_chunks"],
            "model_name": self.config["model"],  # verified ở prepare() qua /health
        }


def _find_model_name(obj) -> str | None:
    """Tìm đệ quy field giống model name trong /health payload (schema không cố định)."""
    if isinstance(obj, dict):
        for key in ("llm_model", "model", "model_name"):
            v = obj.get(key)
            if isinstance(v, str) and v:
                return v
        for v in obj.values():
            found = _find_model_name(v)
            if found:
                return found
    return None


def _parse_sse(raw: str) -> dict:
    tokens: list[str] = []
    done: dict = {}
    errors: list[str] = []
    for block in raw.split("\n\n"):
        data_lines = [ln.removeprefix("data:").strip()
                      for ln in block.splitlines() if ln.startswith("data:")]
        if not data_lines:
            continue
        try:
            event = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        name, data = event.get("event"), event.get("data")
        if name == "token":
            tokens.append(str(data))
        elif name == "done" and isinstance(data, dict):
            done = data
        elif name == "error":
            errors.append(str(data))
    used = done.get("used_chunks") or []
    return {
        "answer": "".join(tokens).strip(), "used_chunks": used,
        "mode": done.get("mode", ""), "latency_ms": done.get("latency_ms", 0),
        "session_id": done.get("session_id"),
        "primary_intent": done.get("primary_intent"),
        "route_flags": done.get("route_flags", []),
        "errors": errors,
    }
