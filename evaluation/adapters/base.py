"""SystemAdapter interface (§12 blueprint). Mọi condition S0–S4 implement cùng interface."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class SystemAdapter(ABC):
    """Interface chung: prepare() → run(sample) per sample → cleanup().

    run() trả về record chuẩn:
    {
      "sample_id", "system_id", "ok": bool, "error": str|None,
      "answer": str,                # text người dùng thấy (prose hoặc JSON-flatten)
      "structured": dict|None,      # AdviseOutput dump (batch path) nếu có
      "used_chunks": [chunk_id],
      "model_name": str|None,       # model THỰC trả lời (assert chống fallback R4)
      "timings_ms": {"retrieval": .., "generation": .., "total": ..},
      "trace": {...}                # đủ để error attribution §10
    }
    """

    def __init__(self, config: dict):
        self.config = config
        self.system_id = config["id"]
        self._trace: dict[str, Any] = {}

    @abstractmethod
    def prepare(self) -> None: ...

    def retrieve(self, sample: dict) -> dict | None:
        """Trả {"chunks": [...], "query": str} hoặc None nếu condition không retrieval."""
        return None

    @abstractmethod
    def generate(self, sample: dict, context: dict | None) -> dict: ...

    def run(self, sample: dict) -> dict:
        self._trace = {}
        t0 = time.perf_counter()
        record: dict[str, Any] = {
            "sample_id": sample["sample_id"],
            "system_id": self.system_id,
            "ok": False, "error": None, "answer": "", "structured": None,
            "used_chunks": [], "model_name": None, "timings_ms": {},
        }
        try:
            tr0 = time.perf_counter()
            context = self.retrieve(sample) if self.config.get("retrieval") else None
            record["timings_ms"]["retrieval"] = int((time.perf_counter() - tr0) * 1000)
            tg0 = time.perf_counter()
            gen = self.generate(sample, context)
            record["timings_ms"]["generation"] = int((time.perf_counter() - tg0) * 1000)
            record.update(gen)
            record["ok"] = True
        except Exception as exc:  # noqa: BLE001 — eval không được crash giữa run
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["timings_ms"]["total"] = int((time.perf_counter() - t0) * 1000)
        record["trace"] = self.collect_trace()
        return record

    def collect_trace(self) -> dict:
        return dict(self._trace)

    def cleanup(self) -> None:
        pass


def build_adapter(config: dict, experiment: dict) -> SystemAdapter:
    kind = config["adapter"] if experiment.get("tier", "t3") == "t3" else "sse_api"
    if kind == "ollama_batch":
        from .ollama_batch import OllamaBatchAdapter
        return OllamaBatchAdapter(config)
    if kind == "extractive":
        from .extractive import ExtractiveAdapter
        return ExtractiveAdapter(config)
    if kind == "sse_api":
        if config["adapter"] == "extractive":
            from .extractive import ExtractiveAdapter
            return ExtractiveAdapter(config)   # S4 không có SSE path
        from .sse_api import SseApiAdapter
        return SseApiAdapter(config, experiment)
    raise ValueError(f"Unknown adapter: {kind}")
