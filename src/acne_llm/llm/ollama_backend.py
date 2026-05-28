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
                 num_ctx: int = 4096, timeout: float = 180.0,
                 health_timeout: float = 5.0,
                 num_predict: int = 1200,
                 temperature: float = 0.35,
                 top_p: float = 0.85,
                 top_k: int = 40,
                 repeat_penalty: float = 1.1,
                 repeat_last_n: int = 128,
                 keep_alive: str | int = -1,
                 use_modelfile_system: bool = False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        # Sampling params — Python là source of truth, KHÔNG set ở Modelfile
        # (Modelfile param sẽ override mọi giá trị gửi qua API). Xem comment ở
        # model/V2/Q4/Modelfile để hiểu quy ước.
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repeat_penalty = repeat_penalty
        self.repeat_last_n = repeat_last_n
        # keep_alive: giữ model warm trong VRAM.
        # Ollama parse như Go duration: int (-1 = vĩnh viễn, 0 = unload ngay)
        # hoặc string có UNIT bắt buộc ("30m", "1h", "300s"). KHÔNG chấp nhận "-1"
        # dạng string — đó là bug 400 "missing unit in duration".
        self.keep_alive = self._normalize_keep_alive(keep_alive)
        # Khi True: không gửi system message qua API — để Modelfile SYSTEM tự xử lý.
        # Dùng khi model đã được fine-tune với system prompt nhúng sẵn trong Modelfile.
        self.use_modelfile_system = use_modelfile_system
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._health_client = httpx.Client(base_url=self.base_url, timeout=health_timeout)

    @staticmethod
    def _normalize_keep_alive(v) -> str | int:
        """Chuyển giá trị keep_alive về dạng Ollama chấp nhận.

        Quy tắc: số nguyên (-1, 0, 300) → giữ nguyên int.
                 string có unit ("30m", "1h") → giữ string.
                 string thuần số ("-1", "300") → convert sang int.
        """
        if isinstance(v, int):
            return v
        s = str(v).strip().lower()
        # Nếu là số (kể cả âm), convert sang int — Ollama coi như seconds.
        if s.lstrip("-").isdigit():
            return int(s)
        # Còn lại phải có unit — Ollama tự validate.
        return s

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

    def show_params(self) -> dict:
        """Đọc params Ollama THỰC SỰ áp dụng (qua /api/show).

        Dùng để verify Modelfile có override Python config không. Gọi lúc boot
        và log ra — nếu thấy num_ctx/temperature ở đây không khớp config.py,
        nghĩa là Modelfile đang nướng param → cần `ollama create` lại.
        """
        try:
            r = self._health_client.post("/api/show", json={"name": self.model})
            r.raise_for_status()
            data = r.json()
            return {
                "parameters": data.get("parameters", ""),
                "template_preview": (data.get("template") or "")[:200],
            }
        except Exception as e:
            logger.warning(f"Ollama /api/show failed: {e}")
            return {}

    def _build_messages(self, system: str, user: str) -> list[dict]:
        """Build messages list.

        Khi use_modelfile_system=True, bỏ qua system message được truyền vào —
        Modelfile SYSTEM sẽ tự inject. Điều này tránh việc 2 system prompt
        chồng lên nhau gây confuse model fine-tune.
        """
        if self.use_modelfile_system:
            return [{"role": "user", "content": user}]
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        return msgs

    def _sampling_options(self, temperature: float | None = None,
                          num_predict: int | None = None) -> dict:
        """Trả về options sampling đồng bộ với Modelfile.

        Caller có thể override temperature và num_predict; các params còn lại
        (top_p, top_k, repeat_penalty, repeat_last_n) lấy từ self để đảm bảo
        nhất quán với PARAMETER trong Modelfile.
        """
        return {
            "temperature":    temperature if temperature is not None else self.temperature,
            "num_ctx":        self.num_ctx,
            "num_predict":    num_predict if num_predict is not None else self.num_predict,
            "top_p":          self.top_p,
            "top_k":          self.top_k,
            "repeat_penalty": self.repeat_penalty,
            "repeat_last_n":  self.repeat_last_n,
        }

    def generate_json(self, system: str, user: str, schema: dict,
                      temperature: float | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": self._build_messages(system, user),
            "format": schema,
            "options": self._sampling_options(temperature=temperature),
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        return self._chat(payload)["message"]["content"]

    def generate_text(self, system: str, user: str,
                      temperature: float | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": self._build_messages(system, user),
            "options": self._sampling_options(temperature=temperature),
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        return self._chat(payload)["message"]["content"]

    def stream_text(self, system: str, user: str,
                    temperature: float | None = None,
                    num_predict: int | None = None) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": self._build_messages(system, user),
            "options": self._sampling_options(temperature=temperature,
                                              num_predict=num_predict),
            "stream": True,
            "keep_alive": self.keep_alive,
        }
        yield from self._chat_stream(payload)

    def close(self):
        self._client.close()
        self._health_client.close()
