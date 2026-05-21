"""Per-source crawl statistics collector — thread-safe (asyncio)."""
from __future__ import annotations
import asyncio
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SourceStats:
    name: str
    language: str
    discovered: int = 0
    fetched: int = 0
    approved: int = 0
    rejected: int = 0
    fetch_errors: int = 0
    reject_reasons: Counter = field(default_factory=Counter)

    @property
    def approve_rate(self) -> float:
        # Use fetched as the denominator so sources with lots of transport
        # errors do not show a misleading 100% approval rate.
        return round(self.approved / self.fetched, 3) if self.fetched else 0.0

    @property
    def keep_rate(self) -> float:
        denom = self.approved + self.rejected
        return round(self.approved / denom, 3) if denom else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "language": self.language,
            "discovered": self.discovered,
            "fetched": self.fetched,
            "approved": self.approved,
            "rejected": self.rejected,
            "fetch_errors": self.fetch_errors,
            "approve_rate": self.approve_rate,
            "keep_rate": self.keep_rate,
            "reject_reasons": dict(self.reject_reasons.most_common()),
        }


class CrawlStats:
    """Async-safe stats collector shared across all sources."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._sources: dict[str, SourceStats] = {}
        self.started_at = datetime.now(timezone.utc)

    def _get(self, name: str, lang: str) -> SourceStats:
        if name not in self._sources:
            self._sources[name] = SourceStats(name=name, language=lang)
        return self._sources[name]

    async def set_discovered(self, name: str, lang: str, n: int) -> None:
        async with self._lock:
            self._get(name, lang).discovered = n

    async def record_approved(self, name: str, lang: str) -> None:
        async with self._lock:
            s = self._get(name, lang)
            s.fetched += 1
            s.approved += 1

    async def record_rejected(self, name: str, lang: str, reason: str) -> None:
        async with self._lock:
            s = self._get(name, lang)
            s.fetched += 1
            s.rejected += 1
            # Normalise reason to top-level bucket for readability
            bucket = _bucket_reason(reason)
            s.reject_reasons[bucket] += 1

    async def record_fetch_error(self, name: str, lang: str) -> None:
        async with self._lock:
            s = self._get(name, lang)
            s.fetched += 1
            s.fetch_errors += 1

    # ─── Reporting ────────────────────────────────────────────────────────────

    def totals(self) -> dict[str, int]:
        vi = [s for s in self._sources.values() if s.language == "vi"]
        en = [s for s in self._sources.values() if s.language == "en"]
        return {
            "total_approved": sum(s.approved for s in self._sources.values()),
            "total_rejected": sum(s.rejected for s in self._sources.values()),
            "total_errors":   sum(s.fetch_errors for s in self._sources.values()),
            "vi_approved":    sum(s.approved for s in vi),
            "vi_rejected":    sum(s.rejected for s in vi),
            "en_approved":    sum(s.approved for s in en),
            "en_rejected":    sum(s.rejected for s in en),
        }

    def console_table(self) -> str:
        """Return a formatted table string for terminal output."""
        rows = sorted(self._sources.values(), key=lambda s: s.approved, reverse=True)
        t = totals = self.totals()
        vi_pct = (
            round(t["vi_approved"] / (t["vi_approved"] + t["en_approved"]) * 100)
            if (t["vi_approved"] + t["en_approved"]) else 0
        )

        # Header
        W = 22
        lines = [
            "",
            "╔" + "═" * 78 + "╗",
            "║  📊  CRAWL STATISTICS                                                       ║",
            "╠" + "═" * 78 + "╣",
            f"║  {'SOURCE':<{W}}  {'LANG':<4}  {'DISC':>5}  {'✓ KEEP':>7}  {'✗ SKIP':>7}  {'⚠ ERR':>5}  {'RATE':>6}  ║",
            "╠" + "─" * 78 + "╣",
        ]
        for s in rows:
            rate_str = f"{s.approve_rate*100:.0f}%"
            tag = "🟢" if s.approve_rate >= 0.4 else ("🟡" if s.approve_rate >= 0.2 else "🔴")
            lang_tag = "🇻🇳" if s.language == "vi" else "🇺🇸"
            lines.append(
                f"║  {s.name:<{W}}  {lang_tag}  {s.discovered:>5}  "
                f"{s.approved:>7}  {s.rejected:>7}  {s.fetch_errors:>5}  {tag}{rate_str:>4}  ║"
            )

        lines += [
            "╠" + "═" * 78 + "╣",
            f"║  {'TOTAL':<{W}}       "
            f"{sum(s.discovered for s in rows):>5}  "
            f"{t['total_approved']:>7}  "
            f"{t['total_rejected']:>7}  "
            f"{t['total_errors']:>5}        ║",
            "╠" + "─" * 78 + "╣",
            f"║  🇻🇳 VI: {t['vi_approved']:,} kept  ({vi_pct}%)   "
            f"🇺🇸 EN: {t['en_approved']:,} kept  ({100-vi_pct}%)"
            + " " * max(0, 78 - len(f"  🇻🇳 VI: {t['vi_approved']:,} kept  ({vi_pct}%)   🇺🇸 EN: {t['en_approved']:,} kept  ({100-vi_pct}%)") - 2)
            + "║",
            "╚" + "═" * 78 + "╝",
        ]
        return "\n".join(lines)

    def save(self, log_dir: Path) -> Path:
        """Save JSON stats to data/logs/ and return path."""
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = self.started_at.strftime("%Y%m%d_%H%M%S")
        out = log_dir / f"crawl_stats_{ts}.json"
        payload = {
            "started_at": self.started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "totals": self.totals(),
            "sources": [s.to_dict() for s in self._sources.values()],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def _bucket_reason(reason: str) -> str:
    """Normalise reject reason string to a readable bucket label."""
    if reason.startswith("strong:") or reason.startswith("medium:"):
        return "passed"  # shouldn't happen
    if "too_short" in reason:
        return "too_short"
    if "too_long" in reason:
        return "too_long"
    if "too_noisy" in reason:
        return "too_noisy"
    if "title_too_short" in reason:
        return "title_too_short"
    if "no_keyword" in reason:
        return "no_keyword"
    if "empty" in reason:
        return "empty"
    return reason
