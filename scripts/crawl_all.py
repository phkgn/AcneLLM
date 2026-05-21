"""Run the full crawl pipeline across all sources in seed_sources.yaml.

Usage:
    python -m scripts.crawl_all
    python -m scripts.crawl_all --source PubMed --max-pages 500
    python -m scripts.crawl_all --resume
    python -m scripts.crawl_all --resume --checkpoint-every 25

Streaming write:
    Moi doc duoc ghi ngay vao documents.jsonl khi duoc accept (khong doi het crawl).
    Dedup duoc thuc hien online (MinHash LSH) -- khong can toan bo corpus trong RAM.

Checkpoint / Resume:
    --resume : load checkpoint tu data/raw/crawl_checkpoint.json, skip processed URLs,
               append vao JSONL cu, rebuild LSH tu file da co.
    Ctrl+C   : tu dong save checkpoint truoc khi exit.
    Checkpoint tu dong clear sau khi crawl hoan thanh thanh cong.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import typer
import yaml
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.crawler.fetcher import AsyncFetcher
from acne_llm.crawler.playwright_fetcher import PlaywrightFetcher
from acne_llm.crawler.sources.generic_html import GenericHtmlSource
from acne_llm.crawler.sources.pubmed import PubMedSource
from acne_llm.crawler.dedup import OnlineDedup
from acne_llm.crawler.checkpoint import CrawlCheckpoint
from acne_llm.crawler.stats import CrawlStats
from acne_llm.utils.logging import configure_logging
from config.settings import settings

_TOPIC_SIGNALS_VI = {
    "mun", "tri-mun", "da-lieu", "trung-ca", "seo-mun",
    "viem-nang", "cham-soc-da", "isotretinoin", "benzoyl",
    "salicylic", "retinoid", "adapalene", "retinol",
}
_TOPIC_SIGNALS_EN = {
    "acne", "pimple", "comedone", "blackhead", "whitehead",
    "isotretinoin", "retinoid", "benzoyl", "salicylic",
    "adapalene", "dermatol", "skincare", "sebaceous",
}

clog = logger.opt(colors=True)
LOG_DIR = ROOT / "data" / "logs"

app = typer.Typer()


def _backup_path_for(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak.{stamp}.{counter}")
        counter += 1
    return backup_path


@app.command()
def run(
    source: str = typer.Option(None, help="Chi chay 1 nguon theo ten"),
    out: str = typer.Option("data/raw/documents.jsonl", help="DocumentRaw output"),
    max_concurrency: int = typer.Option(10, help="So URL fetch dong thoi toan cuc"),
    source_concurrency: int = typer.Option(2, help="So source chay song song"),
    log_level: str = typer.Option("INFO", help="Log level: DEBUG / INFO / WARNING"),
    no_playwright: bool = typer.Option(False, "--no-playwright", help="Tat Playwright fallback"),
    pw_concurrency: int = typer.Option(5, help="So tab Playwright dong thoi"),
    resume: bool = typer.Option(False, "--resume", help="Resume tu checkpoint"),
    checkpoint_every: int = typer.Option(50, "--checkpoint-every", help="Save checkpoint sau N docs"),
    no_checkpoint: bool = typer.Option(False, "--no-checkpoint", help="Tat checkpoint"),
):
    session_log = configure_logging(level=log_level, log_dir=LOG_DIR)
    clog.info(f"Session log -> {session_log}")
    asyncio.run(
        _run(source, out, max_concurrency, source_concurrency,
             no_playwright, pw_concurrency,
             resume, checkpoint_every, no_checkpoint)
    )


async def _run(
    source_filter,
    out_path,
    max_concurrency,
    source_concurrency=2,
    no_playwright=False,
    pw_concurrency=5,
    resume=False,
    checkpoint_every=50,
    no_checkpoint=False,
):
    out_path_p = Path(out_path)
    out_path_p.parent.mkdir(parents=True, exist_ok=True)

    # --- Checkpoint setup ---
    ckpt_path = out_path_p.parent / "crawl_checkpoint.json"
    checkpoint = CrawlCheckpoint(path=ckpt_path)

    if no_checkpoint:
        clog.info("Checkpoint <yellow>disabled</yellow> (--no-checkpoint)")
    else:
        if resume:
            loaded = checkpoint.load()
            if loaded:
                clog.info(
                    f"Resuming from checkpoint: "
                    f"<white>{checkpoint.docs_kept:,}</white> docs already kept, "
                    f"<white>{len(checkpoint.processed_urls):,}</white> URLs already processed"
                )
            else:
                clog.warning("--resume specified but no valid checkpoint found -- starting fresh")
                resume = False
        else:
            clog.info(
                f"Checkpoint enabled -> <cyan>{ckpt_path}</cyan> "
                f"(save every {checkpoint_every} docs + every 60s + on Ctrl+C)"
            )

    # --- Online Dedup ---
    online_dedup = OnlineDedup(threshold=0.88)
    if resume and out_path_p.exists():
        clog.info(f"Rebuilding dedup index from <cyan>{out_path_p}</cyan>...")
        n_loaded = online_dedup.load_from_jsonl(out_path_p)
        clog.info(f"Dedup index rebuilt: <white>{n_loaded:,}</white> docs indexed")

    # --- Output file ---
    if not resume and out_path_p.exists() and out_path_p.stat().st_size > 0:
        backup_path = _backup_path_for(out_path_p)
        out_path_p.rename(backup_path)
        clog.info(f"Backup existing file -> <cyan>{backup_path}</cyan>")

    file_mode = "a" if resume else "w"
    out_file = open(out_path_p, file_mode, encoding="utf-8")
    write_lock = asyncio.Lock()
    clog.info(f"Output -> <cyan>{out_path_p}</cyan> (mode=<white>{file_mode}</white>)")

    # --- Fetchers ---
    seed = yaml.safe_load(Path(settings.seed_sources).read_text(encoding="utf-8"))
    ua = seed.get("user_agent", settings.user_agent)
    rate = float(seed.get("rate_limit_per_domain", settings.crawl_rate_per_sec))
    fetcher = AsyncFetcher(user_agent=ua, rate_per_sec=rate)

    pw_fetcher = None
    if not no_playwright:
        pw_fetcher = PlaywrightFetcher(headless=True, max_concurrent=pw_concurrency)
        clog.info(f"Playwright fallback <green>enabled</green> (max {pw_concurrency} tabs)")
    else:
        clog.info("Playwright fallback <yellow>disabled</yellow> (--no-playwright)")

    global_sem = asyncio.Semaphore(max_concurrency)
    stats = CrawlStats()
    docs_written = 0

    # --- Source list ---
    sources = [
        s for s in seed["sources"]
        if s.get("enabled", True) and (not source_filter or s["name"] == source_filter)
    ]
    if not sources:
        out_file.close()
        await fetcher.close()
        if pw_fetcher:
            await pw_fetcher.close()
        available = ", ".join(s["name"] for s in seed["sources"] if s.get("enabled", True))
        raise RuntimeError(
            f"No enabled sources matched source={source_filter!r}. Available: {available}"
        )

    clog.info(
        f"Starting crawl -- <white>{len(sources)}</white> sources "
        f"| concurrency <white>{max_concurrency}</white>"
    )

    # --- SIGINT handler ---
    if not no_checkpoint:
        def _on_exit():
            try:
                out_file.flush()
                out_file.close()
            except Exception:
                pass
        checkpoint.register_signal_handler(extra_callback=_on_exit)

    # --- Background autosave ---
    autosave_task = None
    if not no_checkpoint:
        autosave_task = asyncio.create_task(checkpoint.autosave_loop(interval_seconds=60))

    # --- Helper: streaming write 1 doc ---
    async def _write_doc(doc_dict: dict) -> bool:
        """Online dedup check + ghi ngay 1 dong vao JSONL.
        Tra ve True neu doc moi (duoc ghi), False neu near-duplicate (skip).
        """
        nonlocal docs_written
        doc_id = doc_dict["doc_id"]
        text   = doc_dict["text"]
        is_new = await online_dedup.add_if_new(doc_id, text)
        if not is_new:
            clog.debug(f"<yellow>NEAR-DUP</yellow> skip  doc_id={doc_id[:24]}...")
            return False
        async with write_lock:
            out_file.write(json.dumps(doc_dict, ensure_ascii=False, default=str) + "\n")
            out_file.flush()
        docs_written += 1
        if not no_checkpoint:
            checkpoint.record_doc_kept(doc_id)
            if checkpoint.docs_kept % checkpoint_every == 0:
                await checkpoint.async_save()
                clog.debug(
                    f"Checkpoint @ {checkpoint.docs_kept:,} docs "
                    f"| {len(checkpoint.processed_urls):,} URLs processed"
                )
        return True

    # --- Per-source runner ---
    async def run_source(s: dict) -> int:
        lang = s.get("language", "vi")
        lang_tag = "VI" if lang == "vi" else "EN"
        kept = 0

        clog.info(
            f"[{s['name']}] {lang_tag} "
            f"trust=<white>{s.get('trust_level','?')}</white>"
        )

        # PubMed path
        if s["domain"] == "pubmed.ncbi.nlm.nih.gov":
            pm = PubMedSource(s)
            pmids = await pm.discover()
            clog.info(f"[{s['name']}] discovered <white>{len(pmids)}</white> PMIDs")
            await stats.set_discovered(s["name"], lang, len(pmids))
            docs = await pm.fetch_all(pmids)
            for d in docs:
                doc_dict = d.model_dump(mode="json")
                if not no_checkpoint:
                    checkpoint.mark_url_processed(getattr(d, "url", d.doc_id))
                wrote = await _write_doc(doc_dict)
                if wrote:
                    kept += 1
                    await stats.record_approved(s["name"], lang)
            clog.info(f"[{s['name']}] {lang_tag} kept {kept}")
            return kept

        # Generic HTML path
        src = GenericHtmlSource(s, fetcher, stats=stats, playwright_fetcher=pw_fetcher)
        urls = await src.discover()

        saved_queue = checkpoint.source_queues.get(s["name"], {}) if resume else {}
        queue = {}

        if saved_queue:
            queue = {u: d for u, d in saved_queue.items() if not checkpoint.is_processed(u)}
            newly_added = 0
            for url in urls:
                if url not in queue and not checkpoint.is_processed(url):
                    queue[url] = 0
                    newly_added += 1
            clog.info(
                f"[{s['name']}] queue warm-start: <white>{len(queue)}</white> URLs pending "
                f"(+new={newly_added})"
            )
        else:
            skipped = 0
            for url in urls:
                if checkpoint.is_processed(url):
                    skipped += 1
                else:
                    queue[url] = 0
            if skipped > 0:
                clog.info(f"[{s['name']}] skipped <white>{skipped:,}</white> already-processed URLs")

        processed_urls = set()
        max_total_urls = s.get("max_pages", 500)
        max_depth = s.get("max_depth", 3)
        topic_signals = _TOPIC_SIGNALS_VI if lang == "vi" else _TOPIC_SIGNALS_EN
        source_exclude_paths = s.get("exclude_paths")

        async def handle(u: str):
            async with global_sem:
                return await src.fetch_one(u)

        while queue and kept < max_total_urls:
            batch_items = []
            for u, dep in list(queue.items())[:max_concurrency * 2]:
                del queue[u]
                processed_urls.add(u)
                batch_items.append((u, dep))

            results = await asyncio.gather(
                *(handle(u) for u, _ in batch_items),
                return_exceptions=True,
            )

            for (url, dep), res in zip(batch_items, results):
                if not no_checkpoint:
                    checkpoint.mark_url_processed(url)
                if isinstance(res, Exception):
                    continue
                d, internal_links = res
                if dep < max_depth:
                    for link in internal_links:
                        if (link not in processed_urls and link not in queue
                                and not checkpoint.is_processed(link)):
                            if source_exclude_paths and any(p in link for p in source_exclude_paths):
                                continue
                            if any(sig in link.lower() for sig in topic_signals):
                                queue[link] = dep + 1
                if d is None:
                    continue
                wrote = await _write_doc(d.model_dump(mode="json"))
                if wrote:
                    kept += 1

            if not no_checkpoint:
                checkpoint.update_source_queue(s["name"], queue)

        clog.info(
            f"[{s['name']}] {lang_tag} kept={kept} "
            f"fetch={src._fetch_count} skip={src._skip_count} err={src._err_count}"
        )
        return kept

    src_sem = asyncio.Semaphore(source_concurrency)

    async def run_source_gated(s: dict):
        async with src_sem:
            try:
                return await run_source(s)
            except Exception as e:
                clog.opt(exception=e).error(
                    f"[{s.get('name', '?')}] source failed; continuing"
                )
                return 0

    # --- Run all sources ---
    try:
        await asyncio.gather(*(run_source_gated(s) for s in sources))
    finally:
        if autosave_task and not autosave_task.done():
            autosave_task.cancel()
            try:
                await autosave_task
            except asyncio.CancelledError:
                pass
        await fetcher.close()
        if pw_fetcher:
            await pw_fetcher.close()
            clog.info("Playwright browser closed")
        out_file.flush()
        out_file.close()

    # --- Final summary ---
    clog.success(
        f"DocumentRaw -> <cyan>{out_path_p}</cyan>  "
        f"(<white>{docs_written:,}</white> docs written this session)"
    )
    if resume and checkpoint.docs_kept > docs_written:
        clog.info(f"Total in file (including previous runs): <white>{checkpoint.docs_kept:,}</white> docs")

    if docs_written == 0 and not resume:
        raise RuntimeError("Crawl produced 0 documents. Existing documents.jsonl was kept untouched.")

    clog.info("Run scripts/build_qa_dataset.py next to generate the fine-tuning dataset.")
    print(stats.console_table())
    stats_path = stats.save(LOG_DIR)
    clog.success(f"Stats JSON -> <cyan>{stats_path}</cyan>")

    if not no_checkpoint:
        checkpoint.clear()
        clog.info("Checkpoint cleared (crawl completed successfully)")


if __name__ == "__main__":
    app()
