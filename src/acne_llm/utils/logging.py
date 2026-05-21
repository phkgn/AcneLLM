"""Logging configuration — PowerShell-friendly colours + file sink to data/logs/."""
import sys
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
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
    logger.add(
        str(session_log),
        level="DEBUG",
        format=_FILE_FORMAT,
        rotation="50 MB",
        retention=10,
        encoding="utf-8",
        enqueue=True,
    )

    # ── Errors-only sink (always kept) ────────────────────────────────────────
    logger.add(
        str(log_dir / "errors.log"),
        level="ERROR",
        format=_FILE_FORMAT,
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
    )

    return session_log
