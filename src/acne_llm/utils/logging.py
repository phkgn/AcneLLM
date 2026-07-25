"""Logging configuration — PowerShell-friendly colours + file sink to data/logs/."""
from collections.abc import Mapping, Sequence
import json
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from loguru import logger


# PowerShell/Windows Terminal compatible format
# ✓ KEEP  → green     ✗ SKIP  → red     ⚠ WARN  → yellow
_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> "
    "| <level>{level: <7}</level> "
    "| {message}"
)

_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{line} | {message}"
)

PIPELINE_STAGES = frozenset({
    "INPUT",
    "PREPROCESS",
    "SAFETY",
    "INTAKE",
    "ROUTE",
    "EXTRACT",
    "RAG",
    "GENERATE",
    "OUTPUT",
})


def _compact_log_value(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(_compact_log_value(item) for item in value) + "]"
    text = " ".join(str(value).split())
    if len(text) > 160:
        text = text[:157] + "..."
    return json.dumps(text, ensure_ascii=False) if any(ch.isspace() for ch in text) else text


def log_pipeline_stage(
    session_id: str | None,
    stage: str,
    started: float,
    *,
    level: str = "INFO",
    **fields: Any,
) -> None:
    """Emit one compact, consistently timed pipeline-stage record."""
    normalized_stage = stage.upper()
    if normalized_stage not in PIPELINE_STAGES:
        raise ValueError(f"unknown pipeline stage: {stage}")
    sid = (session_id or "no-session")[:8]
    elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000)
    details = " ".join(
        f"{key}={_compact_log_value(value)}" for key, value in fields.items()
    ) or "-"
    logger.log(
        level.upper(),
        "[{}] {:<10} {} ({:.0f}ms)",
        sid,
        normalized_stage,
        details,
        elapsed_ms,
    )


def log_runtime_banner(container: Any) -> None:
    """Log the effective DI/runtime topology as one startup record."""
    settings = container.settings
    intake_mode = str(getattr(settings, "intake_mode", "legacy"))
    fallback_chain = "semantic → rule → deterministic"
    lines = [
        "── AcneLLM runtime ─────────────────────────────",
        f"intake_mode : {intake_mode:<9} (fallback: {fallback_chain})",
    ]
    if intake_mode == "unified":
        lines.append(
            "intake 3B   : "
            f"{getattr(settings, 'intake_model', 'unknown')} "
            f"keep_alive={getattr(settings, 'llm_keep_alive', 'default')} "
            f"timeout={getattr(settings, 'intake_timeout', 'default')}s"
        )
    else:
        router_name = (
            getattr(settings, "router_model", "unknown")
            if getattr(settings, "router_mode", "llm") == "llm"
            else "semantic"
        )
        extractor_name = (
            getattr(settings, "extractor_model", "unknown")
            if getattr(settings, "extractor_mode", "llm") == "llm"
            else "rule"
        )
        lines.append(
            "intake legacy: "
            f"router={router_name} "
            f"extractor={extractor_name} "
            f"timeout={getattr(settings, 'router_timeout', 'default')}/"
            f"{getattr(settings, 'extractor_timeout', 'default')}s"
        )
    lines.append(
        "answer 7B   : "
        f"{getattr(settings, 'llm_model', 'unknown')} "
        f"ctx={getattr(settings, 'llm_num_ctx', 'default')} "
        f"keep_alive={getattr(settings, 'llm_keep_alive', 'default')}"
    )
    embedder_name = getattr(
        container.embedder,
        "model_name",
        getattr(settings, "embedding_model", "unavailable"),
    )
    reranker_name = getattr(
        container.reranker,
        "model_name",
        getattr(settings, "reranker_model", "unavailable"),
    )
    lines.append(
        f"embedder    : {embedder_name} ({getattr(settings, 'device', 'unknown')}) "
        f"reranker={reranker_name}"
    )
    if container.rag_ready:
        try:
            vector_count = container.store.count()
        except Exception:
            vector_count = "?"
        chunk_ids = getattr(container.bm25, "chunk_ids", ())
        lines.append(
            f"RAG         : Chroma {vector_count} vectors | BM25 {len(chunk_ids)} chunks"
        )
    else:
        lines.append("RAG         : unavailable (llm_only fallback)")
    drug_checker = getattr(container.guardrails, "_drug_checker", None)
    drug_count = len(getattr(drug_checker, "_db", ())) if drug_checker else 0
    lines.extend([
        f"safety      : substrate always-on | guardrails {drug_count} drugs",
        "────────────────────────────────────────────────",
    ])
    logger.info("\n{}", "\n".join(lines))


def configure_logging(level: str = "INFO", log_dir: str | Path = "data/logs") -> Path:
    """Configure loguru sinks.

    Returns the path to the session log file.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = Path(log_dir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(tempfile.gettempdir()) / "acne_llm_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    session_log = log_dir / f"crawl_{ts}.log"

    logger.remove()

    # ── Console sink (stderr) ─────────────────────────────────────────────────
    logger.add(
        sys.stderr,
        level=level,
        format=_CONSOLE_FORMAT,
        colorize=True,
        enqueue=False,
    )

    # ── File sink — full DEBUG detail ─────────────────────────────────────────
    try:
        logger.add(
            str(session_log),
            level="DEBUG",
            format=_FILE_FORMAT,
            rotation="50 MB",
            retention=10,
            encoding="utf-8",
            enqueue=True,
        )
    except OSError as exc:
        fallback_dir = Path(tempfile.gettempdir()) / "acne_llm_logs"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        session_log = fallback_dir / f"crawl_{ts}.log"
        logger.warning(
            "Cannot open log file in {}; using temp log {} ({})",
            log_dir,
            session_log,
            exc,
        )
        try:
            logger.add(
                str(session_log),
                level="DEBUG",
                format=_FILE_FORMAT,
                rotation="50 MB",
                retention=10,
                encoding="utf-8",
                enqueue=True,
            )
        except OSError as fallback_exc:
            logger.warning("File logging disabled: {}", fallback_exc)

    # ── Errors-only sink (always kept) ────────────────────────────────────────
    try:
        logger.add(
            str(session_log.parent / "errors.log"),
            level="ERROR",
            format=_FILE_FORMAT,
            rotation="10 MB",
            retention=5,
            encoding="utf-8",
            enqueue=True,
        )
    except OSError as exc:
        logger.warning("Errors-only file logging disabled: {}", exc)

    return session_log
