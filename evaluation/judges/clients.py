"""Judge clients: DeepSeek (chính) + OpenAI (verify). Temp=0, SQLite cache, cost meter.

Kỷ luật §7 blueprint: log model+timestamp, cache theo hash, JSON output bắt buộc,
parse fail → retry 1 lần → invalid (không đoán).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

from evaluation.common import EVAL_DIR, ROOT, sha256_text, utcnow

CACHE_DB = EVAL_DIR / "reports" / "judge_cache.sqlite"

# USD per 1M tokens (input cache-miss, output) — cập nhật 2026-07 (api-docs.deepseek.com)
# LƯU Ý: deepseek-chat bị deprecate 2026-07-24, route về deepseek-v4-flash.
PRICES = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
    "deepseek-chat": (0.14, 0.28),      # alias → v4-flash
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
}


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
    def __init__(self, provider: str = "deepseek", model: str | None = None):
        if provider == "deepseek":
            self.base_url = _read_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
            self.api_key = _read_env("DEEPSEEK_API_KEY")
            self.model = model or _read_env("DEEPSEEK_MODEL") or "deepseek-chat"
        elif provider == "openai":
            self.base_url = "https://api.openai.com"
            self.api_key = _read_env("OPENAI_API_KEY")
            self.model = model or "gpt-4o-mini"
        else:
            raise ValueError(provider)
        if not self.api_key:
            raise RuntimeError(f"Thiếu API key cho {provider} (.env)")
        self.provider = provider
        self.total_cost_usd = 0.0
        self.calls = 0
        CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(CACHE_DB)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, model TEXT, "
            "response TEXT, usage TEXT, ts TEXT)"
        )

    def judge(self, prompt: str, *, use_cache: bool = True,
              max_retries: int = 2) -> dict | None:
        """Gọi judge, trả dict đã parse từ JSON output; None nếu invalid."""
        key = sha256_text(f"{self.model}::{prompt}")
        if use_cache:
            row = self._db.execute(
                "SELECT response FROM cache WHERE key=?", (key,)
            ).fetchone()
            if row:
                return _extract_json(row[0])
        raw, usage = None, {}
        for attempt in range(max_retries):
            try:
                raw, usage = self._call(prompt)
                if _extract_json(raw) is not None:
                    break
            except Exception as exc:  # noqa: BLE001
                if attempt == max_retries - 1:
                    print(f"[judge] call failed: {exc}")
                    return None
                time.sleep(3 * (attempt + 1))
        if raw is None:
            return None
        self._db.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
            (key, self.model, raw, json.dumps(usage), utcnow()),
        )
        self._db.commit()
        self._track_cost(usage)
        return _extract_json(raw)

    def _call(self, prompt: str) -> tuple[str, dict]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/v1/chat/completions"
            if not self.base_url.endswith("/v1")
            else self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        self.calls += 1
        return body["choices"][0]["message"]["content"], body.get("usage", {})

    def _track_cost(self, usage: dict) -> None:
        pin, pout = PRICES.get(self.model, (0.0, 0.0))
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
