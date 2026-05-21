"""Crawl checkpoint — lưu progress để resume khi bị interrupt.

Checkpoint file: data/raw/crawl_checkpoint.json

Persisted state:
  - processed_urls : tất cả URLs đã xử lý (kept + skip + error)
  - source_queues  : queue pending per source {source_name: {url: depth}}
  - seen_ids       : doc_ids đã được ghi vào JSONL
  - docs_kept      : tổng số docs đã ghi
  - started_at     : ISO timestamp của run gốc
  - last_saved     : ISO timestamp lần save cuối

Flow:
  Fresh run:
      ckpt = CrawlCheckpoint()
      ckpt.register_signal_handler()
      autosave_task = asyncio.create_task(ckpt.autosave_loop())
      # ... crawl ...
      ckpt.clear()   # xóa file sau khi hoàn thành

  Resume (--resume flag):
      ckpt = CrawlCheckpoint()
      ckpt.load()
      dedup.load_from_jsonl(out_path)   # rebuild LSH
      # ... crawl (skip processed_urls) ...
      ckpt.clear()
"""
from __future__ import annotations

import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class CrawlCheckpoint:
    """Lưu và load crawl state để hỗ trợ resume."""

    DEFAULT_PATH = Path("data/raw/crawl_checkpoint.json")

    def __init__(self, path: Path | None = None):
        self.path = path or self.DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # ── Persisted fields ──────────────────────────────────────────────────
        self.processed_urls: set[str] = set()
        """Tất cả URLs đã được xử lý (fetch + skip + error) — không crawl lại khi resume."""

        self.source_queues: dict[str, dict[str, int]] = {}
        """Queue pending per source: {source_name: {url: depth}}. Dùng để warm-start queue."""

        self.seen_ids: set[str] = set()
        """doc_ids đã được ghi ra JSONL — để rebuild OnlineDedup khi resume."""

        self.docs_kept: int = 0
        """Tổng số docs đã ghi ra file."""

        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.last_saved: str = ""

        # ── Internal ──────────────────────────────────────────────────────────
        self._dirty: bool = False
        # Lock chỉ dùng cho async_save để tránh concurrent writes
        self._save_lock = asyncio.Lock()

    # ─── Persistence ──────────────────────────────────────────────────────────

    def save(self) -> None:
        """Ghi checkpoint ra disk (synchronous, atomic via temp file)."""
        self.last_saved = datetime.now(timezone.utc).isoformat()
        payload = {
            "started_at": self.started_at,
            "last_saved": self.last_saved,
            "docs_kept": self.docs_kept,
            "processed_urls": list(self.processed_urls),
            "source_queues": {
                name: dict(q) for name, q in self.source_queues.items()
            },
            "seen_ids": list(self.seen_ids),
        }
        # Ghi ra .tmp rồi rename để tránh corrupt nếu crash giữa chừng
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        self._dirty = False

    async def async_save(self) -> None:
        """Async-safe wrapper — tránh 2 coroutine save cùng lúc."""
        async with self._save_lock:
            self.save()

    def load(self) -> bool:
        """Load checkpoint từ disk. Trả về True nếu thành công."""
        if not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.started_at = data.get("started_at", self.started_at)
            self.last_saved = data.get("last_saved", "")
            self.docs_kept = data.get("docs_kept", 0)
            self.processed_urls = set(data.get("processed_urls", []))
            self.source_queues = {
                name: dict(q)
                for name, q in data.get("source_queues", {}).items()
            }
            self.seen_ids = set(data.get("seen_ids", []))
            return True
        except Exception as e:
            from loguru import logger
            logger.warning(f"⚠ Checkpoint load failed ({e}) — starting fresh")
            return False

    def clear(self) -> None:
        """Xóa file checkpoint sau khi crawl hoàn thành thành công."""
        for p in (self.path, self.path.with_suffix(".tmp")):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    def exists(self) -> bool:
        return self.path.exists()

    # ─── URL tracking ─────────────────────────────────────────────────────────
    # Các method này SYNCHRONOUS — asyncio single-threaded nên set/int ops an toàn

    def mark_url_processed(self, url: str) -> None:
        """Đánh dấu URL đã xử lý (kết quả bất kỳ: kept/skip/error)."""
        self.processed_urls.add(url)
        self._dirty = True

    def is_processed(self, url: str) -> bool:
        """Trả về True nếu URL đã được xử lý trong run trước."""
        return url in self.processed_urls

    def record_doc_kept(self, doc_id: str) -> None:
        """Ghi nhận 1 doc đã được lưu vào JSONL."""
        self.seen_ids.add(doc_id)
        self.docs_kept += 1
        self._dirty = True

    def update_source_queue(self, source_name: str, queue: dict[str, int]) -> None:
        """Snapshot queue hiện tại của 1 source (để warm-start khi resume)."""
        self.source_queues[source_name] = dict(queue)
        self._dirty = True

    # ─── Auto-save & Signal handling ──────────────────────────────────────────

    async def autosave_loop(self, interval_seconds: int = 60) -> None:
        """Background coroutine: tự động save mỗi `interval_seconds` giây.

        Chỉ save khi có thay đổi (_dirty=True) để tránh I/O lãng phí.

        Dùng:
            task = asyncio.create_task(ckpt.autosave_loop(60))
            # ... crawl ...
            task.cancel()
        """
        from loguru import logger
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                if self._dirty:
                    await self.async_save()
                    logger.debug(
                        f"🕐 Auto-saved checkpoint "
                        f"({self.docs_kept:,} docs, {len(self.processed_urls):,} URLs)"
                    )
            except asyncio.CancelledError:
                # Task bị cancel (crawl xong) — save lần cuối nếu cần
                if self._dirty:
                    self.save()
                raise

    def register_signal_handler(
        self,
        extra_callback: Callable[[], None] | None = None,
    ) -> None:
        """Đăng ký SIGINT/SIGTERM handler để save checkpoint khi Ctrl+C.

        Args:
            extra_callback: hàm tùy chọn gọi sau khi save (vd: đóng fetcher).
        """
        from loguru import logger

        def _handler(signum, frame):  # type: ignore[type-arg]
            logger.warning(
                f"\n⚡ Signal {signum} received — saving checkpoint before exit..."
            )
            try:
                self.save()
                logger.info(
                    f"✅ Checkpoint saved: {self.docs_kept:,} docs, "
                    f"{len(self.processed_urls):,} URLs processed. "
                    f"Resume với: --resume"
                )
            except Exception as exc:
                logger.error(f"❌ Checkpoint save failed: {exc}")
            if extra_callback:
                try:
                    extra_callback()
                except Exception:
                    pass
            sys.exit(0)

        signal.signal(signal.SIGINT, _handler)
        try:
            signal.signal(signal.SIGTERM, _handler)
        except (OSError, ValueError):
            # SIGTERM không available trên Windows trong một số context
            pass

    # ─── Repr ─────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"CrawlCheckpoint("
            f"docs_kept={self.docs_kept}, "
            f"processed_urls={len(self.processed_urls)}, "
            f"path={self.path})"
        )
