"""Frontier-model calls, cached on disk, split by role.

Three roles, three models, on purpose — see `roles()` for why they must differ:

    CASE_MODEL    writes the cases: golden slots, evidence, rubric
    ORACLE_MODEL  plays the perfect generator in the `??O` arms
    JUDGE_MODEL   grades every answer

Provider is inferred from the model name (`deepseek*` → DeepSeek, else OpenAI),
so switching a role is one env var and no code.

Cache key = (model, system, user, json_mode). Re-running a stage therefore costs
nothing, which is what makes the 8-arm matrix affordable to iterate on.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path

CACHE = Path(__file__).with_name("runs") / "frontier_cache.sqlite"

# Defaults are a clean three-way split: the cheap tier writes the many cases, the
# strong tier defines the ceiling, a different vendor grades. The oracle must be
# clearly stronger than the local generator under test — if it is not, `??O` is
# not a ceiling and the generator's headroom reads low for the wrong reason.
CASE_MODEL = os.getenv("ABLATION_CASE_MODEL", "deepseek-v4-flash")
ORACLE_MODEL = os.getenv("ABLATION_ORACLE_MODEL", "deepseek-v4-pro")
JUDGE_MODEL = os.getenv("ABLATION_JUDGE_MODEL", "gpt-5.6-luna")
MODEL = ORACLE_MODEL                      # back-compat default for bare ask()

_lock = threading.Lock()
_usage = {"calls": 0, "cached": 0, "in_tok": 0, "out_tok": 0}


def roles() -> list[str]:
    """Warnings for role collisions, worst first. Empty list = clean assignment."""
    out = []
    if ORACLE_MODEL == JUDGE_MODEL:
        out.append(
            f"ORACLE == JUDGE ({ORACLE_MODEL}): the judge grades its own answers in "
            f"the `??O` arms. Self-preference bias inflates generator headroom. Fix this first.")
    if CASE_MODEL == ORACLE_MODEL:
        out.append(
            f"CASE == ORACLE ({CASE_MODEL}): the oracle generator answers cases whose "
            f"rubric it wrote, so it matches the rubric's own phrasing. Milder than the "
            f"above, but still inflates generator headroom.")
    return out


def _client(model: str):
    from openai import OpenAI                # imported late so --dry-run needs no key
    if model.startswith("deepseek"):
        return OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                      base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _db():
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CACHE, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, v TEXT)")
    return con


def ask(system: str, user: str, *, json_mode: bool = False, model: str | None = None) -> str:
    model = model or MODEL
    key = hashlib.sha256(
        json.dumps([model, system, user, json_mode], ensure_ascii=False).encode()
    ).hexdigest()
    with _lock, _db() as con:
        hit = con.execute("SELECT v FROM c WHERE k=?", (key,)).fetchone()
    if hit:
        _usage["cached"] += 1
        return hit[0]

    kw = {"response_format": {"type": "json_object"}} if json_mode else {}
    r = _client(model).chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        **kw,
    )
    text = r.choices[0].message.content or ""
    _usage["calls"] += 1
    if r.usage:
        _usage["in_tok"] += r.usage.prompt_tokens or 0
        _usage["out_tok"] += r.usage.completion_tokens or 0
    with _lock, _db() as con:
        con.execute("INSERT OR REPLACE INTO c VALUES (?,?)", (key, text))
    return text


def ask_json(system: str, user: str, *, model: str | None = None) -> dict:
    """JSON call with one repair retry. Never guesses: raises if still unparsable."""
    raw = ask(system, user, json_mode=True, model=model)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = ask(system, user + "\n\nOutput valid JSON only.",
                    json_mode=True, model=model)
        return json.loads(fixed)


def usage() -> dict:
    return dict(_usage)
