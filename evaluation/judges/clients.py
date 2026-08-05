"""OpenAI-only LLM judge client.

Kỷ luật §7 blueprint: log model+timestamp, cache theo hash, JSON output bắt buộc,
parse fail → retry 1 lần → invalid (không đoán). Lỗi API/quota/auth phải làm
process fail để dashboard không báo xanh với artifact judge rỗng.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from acne_llm.config import settings
from evaluation.common import EVAL_DIR, ROOT, sha256_text, utcnow

CACHE_DB = EVAL_DIR / "reports" / "judge_cache.sqlite"
DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_OPENAI_JUDGE_MODEL = "gpt-5-mini-2025-08-07"
DEFAULT_OPENAI_FAITHFULNESS_MODEL = "gpt-5-nano-2025-08-07"
DEFAULT_JUDGE_WORKERS = 4

# USD per 1M tokens (input cache-miss, output). OpenAI prices are kept here so
# every successful API attempt, including a malformed response retry, is metered.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-nano-2026-03-17": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-mini-2026-03-17": (0.75, 4.50),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-nano-2025-08-07": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-mini-2025-08-07": (0.25, 2.00),
}


class JudgeAPIError(RuntimeError):
    """API/network failure that must not be converted into an invalid score."""

    def __init__(self, message: str, *, retryable: bool,
                 retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def _read_env(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


class JudgeClient:
    def __init__(self, provider: str | None = None, model: str | None = None):
        provider = provider or getattr(
            settings, "judge_provider", DEFAULT_JUDGE_PROVIDER
        )
        if provider != "openai":
            raise ValueError("Evaluation Judge chỉ hỗ trợ provider=openai")
        self.base_url = "https://api.openai.com"
        self.api_key = _read_env("OPENAI_API_KEY")
        self.model = (
            model
            or getattr(settings, "judge_model", "")
            or DEFAULT_OPENAI_JUDGE_MODEL
        )
        if not self.api_key:
            raise RuntimeError(f"Thiếu API key cho {provider} (.env)")
        self.provider = provider
        self.total_cost_usd = 0.0
        self.calls = 0
        self._lock = threading.RLock()
        CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(CACHE_DB, timeout=30, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, model TEXT, "
            "response TEXT, usage TEXT, ts TEXT)"
        )

    def judge(self, prompt: str, *, use_cache: bool = True,
              max_retries: int = 6) -> dict | None:
        """Return parsed JSON, ``None`` only for malformed model output.

        API, authentication, quota, and network failures raise ``JudgeAPIError``
        after retry policy. They are infrastructure failures, not judge scores.
        """
        if max_retries < 1:
            raise ValueError("max_retries phải >= 1")
        key = sha256_text(f"{self.provider}::{self.model}::{prompt}")
        if use_cache:
            with self._lock:
                row = self._db.execute(
                    "SELECT response FROM cache WHERE key=?", (key,)
                ).fetchone()
            if row:
                return _extract_json(row[0])
        raw, usage = None, {}
        for attempt in range(max_retries):
            try:
                raw, usage = self._call(prompt)
                self._track_cost(usage)
                parsed = _extract_json(raw)
                if parsed is not None:
                    with self._lock:
                        self._db.execute(
                            "INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
                            (key, self.model, raw, json.dumps(usage), utcnow()),
                        )
                        self._db.commit()
                    return parsed
            except JudgeAPIError as exc:
                if not exc.retryable or attempt == max_retries - 1:
                    raise
                time.sleep(exc.retry_after or min(30, 3 * (attempt + 1)))
        return None

    def _call(self, prompt: str) -> tuple[str, dict]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        # temperature=0 cho MỌI model. Trước đây nhánh gpt-5.x bỏ qua nó, nên
        # judge chạy ở nhiệt độ mặc định của nhà cung cấp -> chấm lại cùng một
        # câu có thể ra điểm khác. Với eval thì đó là nhiễu không đo được.
        # Model nào từ chối temperature sẽ raise và lộ ra ngay, không im lặng.
        payload["temperature"] = 0
        if self.model.startswith("gpt-5.4") or self.model.startswith("gpt-5.6"):
            payload["reasoning_effort"] = "none"
        elif self.model.startswith("gpt-5"):
            payload["reasoning_effort"] = "minimal"
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/v1/chat/completions"
            if not self.base_url.endswith("/v1")
            else self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            retryable = status in {408, 409, 425, 429} or status >= 500
            retry_after = None
            if exc.headers:
                try:
                    retry_after = float(exc.headers.get("Retry-After") or 0) or None
                except (TypeError, ValueError):
                    retry_after = None
            if status == 429 and retry_after is None:
                # OpenAI often sends reset hints in custom duration headers
                # instead of Retry-After. A conservative pause prevents a
                # tight retry loop from turning a transient TPM cap into FAIL.
                retry_after = 30.0
            raise JudgeAPIError(
                f"{self.provider}/{self.model} HTTP {status} {exc.reason}",
                retryable=retryable,
                retry_after=retry_after,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise JudgeAPIError(
                f"{self.provider}/{self.model} network error: {exc}",
                retryable=True,
            ) from exc
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise JudgeAPIError(
                f"{self.provider}/{self.model} invalid API envelope: {exc}",
                retryable=True,
            ) from exc
        with self._lock:
            self.calls += 1
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise JudgeAPIError(
                f"{self.provider}/{self.model} missing response content: {exc}",
                retryable=True,
            ) from exc
        return content, body.get("usage", {})

    def _track_cost(self, usage: dict) -> None:
        pin, pout = PRICES.get(self.model, (0.0, 0.0))
        with self._lock:
            self.total_cost_usd += (
                usage.get("prompt_tokens", 0) * pin
                + usage.get("completion_tokens", 0) * pout
            ) / 1e6


def _extract_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                return None
    return None


def load_prompt(name: str, **kwargs) -> str:
    """Load judge prompt từ judges/prompts/<name>.md, thay $var (string.Template —
    an toàn với dấu ngoặc nhọn trong ví dụ JSON)."""
    from string import Template

    path = Path(__file__).parent / "prompts" / f"{name}.md"
    return Template(path.read_text(encoding="utf-8")).safe_substitute(**kwargs)
