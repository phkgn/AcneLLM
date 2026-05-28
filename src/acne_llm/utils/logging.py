"""Logging configuration — PowerShell-friendly colours + file sink to data/logs/."""
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
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
