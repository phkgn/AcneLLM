"""Generic HTML source -- sitemap/category discovery + trafilatura extract."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from loguru import logger
from ...schemas.kb import DocumentRaw, SourceMeta, infer_source_type

clog = logger.opt(colors=True)
from ...utils.hashing import doc_id_for
from ..fetcher import AsyncFetcher
from ..discovery import discover_from_sitemap, discover_from_category, discover_from_search, _normalize_url
from ..extractor import extract_main_text
from ..normalizer import normalize_vi_text
from ..quality_filter import passes_quality, score_quality
from ..stats import CrawlStats
from ..playwright_fetcher import JSDetector, PlaywrightFetcher


# --- Log tag constants -------------------------------------------------------
_FETCH = "<blue>FETCH</blue>"
_OK    = "<green>KEEP </green>"
_NO    = "<red>SKIP </red>"
_ERR   = "<yellow>ERR  </yellow>"

_URL_HARD_SIGNALS_VI = [
    "tri-mun", "trung-ca", "mun-trung-ca", "seo-mun",
    "viem-nang-long", "da-mun", "mun-boc", "mun-dau-den",
    "isotretinoin", "benzoyl", "salicylic", "retinoid", "adapalene",
]
_URL_HARD_SIGNALS_EN = [
    "acne", "pimple", "comedone", "blackhead", "whitehead",
    "isotretinoin", "retinoid", "benzoyl", "salicylic", "adapalene",
    "acne-vulgaris", "acneiform",
]
_URL_SOFT_SIGNALS_VI = ["mun", "da-lieu", "lam-dep", "cham-soc-da"]
_URL_SOFT_SIGNALS_EN = ["dermatology", "sebaceous", "skin-condition", "skincare"]


def _url_pre_approve(url: str, lang: str, trust_level: str) -> tuple:
    """Pre-approve high-trust URLs with a hard acne signal (bypasses keyword filter)."""
    if trust_level != "high":
        return False, ""
    url_lower = url.lower()
    hard_signals = _URL_HARD_SIGNALS_VI if lang == "vi" else _URL_HARD_SIGNALS_EN
    for sig in hard_signals:
        if sig in url_lower:
            return True, f"url_hard_signal:{sig}"
    return False, ""


def _url_soft_score_boost(url: str, lang: str) -> bool:
    url_lower = url.lower()
    soft_signals = _URL_SOFT_SIGNALS_VI if lang == "vi" else _URL_SOFT_SIGNALS_EN
    return any(sig in url_lower for sig in soft_signals)


def _short_url(url: str, max_len: int = 80) -> str:
    """Rut gon URL cho log: bo scheme, cat neu qua dai."""
    short = url.replace("https://", "").replace("http://", "")
    if len(short) > max_len:
        short = short[:max_len - 3] + "..."
    return short


class GenericHtmlSource:
    def __init__(
        self,
        cfg: dict,
        fetcher: AsyncFetcher,
        stats: CrawlStats = None,
        playwright_fetcher: PlaywrightFetcher = None,
    ):
        self.cfg = cfg
        self.fetcher = fetcher
        self.name = cfg["name"]
        self.lang = cfg.get("language", "vi")
        self._lang_tag = "VI" if self.lang == "vi" else "EN"
        self._stats = stats
        self._pw = playwright_fetcher

        # Playwright config
        self._js_render: bool = cfg.get("js_render", False)
        self._js_wait_until: str = cfg.get("js_wait_until", "networkidle")
        self._js_wait_selector = cfg.get("js_wait_selector")
        self._js_timeout_ms: int = cfg.get("js_timeout_ms", 30_000)

        # --- Per-URL progress counters (asyncio single-threaded: int ops safe) --
        self._fetch_count: int = 0   # total URLs attempted
        self._kept_count: int = 0    # total URLs KEPT
        self._skip_count: int = 0    # total URLs SKIP
        self._err_count: int = 0     # total URLs ERR
        self._max_pages: int = cfg.get("max_pages", 500)

    def _progress(self) -> str:
        """Render [kept/max] counter tag cho log."""
        return f"[<white>{self._kept_count}</white>/<white>{self._max_pages}</white>]"

    async def discover(self) -> list:
        d = self.cfg.get("discovery", {})
        dtype = d.get("type")
        if dtype == "manual":
            urls = list(dict.fromkeys(
                _normalize_url(u) for u in d.get("start_urls", [])
            ))
        elif dtype == "sitemap":
            urls = await discover_from_sitemap(
                d["sitemap_url"],
                filter_path_contains=d.get("filter_path_contains"),
                filter_keywords=d.get("filter_keywords"),
                max_urls=self.cfg.get("max_pages", 1000),
                exclude_paths=d.get("exclude_paths"),
            )
        elif dtype == "category":
            urls = await discover_from_category(
                d["start_urls"],
                pagination_selector=d.get("pagination_selector"),
                link_selector=d.get("link_selector", "a"),
                max_pagination_pages=d.get(
                    "max_pagination_pages",
                    self.cfg.get("max_pagination_pages", 50),
                ),
                crawl_sub_pages=d.get("crawl_sub_pages", True),
                max_total_urls=self.cfg.get("max_pages", 500),
                crawl_depth=d.get(
                    "crawl_depth",
                    self.cfg.get("max_depth", 2),
                ),
                filter_path_contains=d.get("filter_path_contains"),
                exclude_paths=d.get("exclude_paths"),
                article_path_pattern=d.get("article_path_pattern"),
                js_fetcher=self._pw if self._js_render else None,
                js_wait_until=self._js_wait_until,
                js_timeout_ms=self._js_timeout_ms,
            )
        elif dtype == "search":
            urls = await discover_from_search(
                queries=d.get("queries", []),
                domain=self.cfg.get("domain"),
                max_results_per_query=d.get("max_results_per_query", 50),
                filter_path_contains=d.get("filter_path_contains"),
                exclude_paths=d.get("exclude_paths"),
                filter_keywords=d.get("filter_keywords"),
            )
        else:
            urls = []

        if self._stats:
            await self._stats.set_discovered(self.name, self.lang, len(urls))

        clog.info(
            f"<cyan>[{self.name}]</cyan> {self._lang_tag} "
            f"discovered <white>{len(urls)}</white> URLs"
        )
        return urls

    async def fetch_one(self, url: str) -> tuple:
        """Fetch, extract, filter 1 URL. Log chi tiet tung buoc.

        Log levels:
          DEBUG   - FETCH (truoc khi fetch, tranh spam terminal mac dinh)
          INFO    - KEEP  (URL duoc giu lai)
          INFO    - SKIP  (URL bi loc -- reason ro rang)
          WARNING - ERR   (loi mang / timeout)
        """
        self._fetch_count += 1
        fetch_idx = self._fetch_count
        short = _short_url(url)
        src_tag = f"<cyan>[{self.name}]</cyan>"
        prog = self._progress()

        # Step 0: Log FETCH (DEBUG -- khong spam terminal mac dinh)
        clog.debug(
            f"{_FETCH} {src_tag} {prog} [{fetch_idx}] -> {short}"
        )

        domain = urlparse(url).netloc

        # Step 1: HTTP fetch
        html = ""
        try:
            html, _ = await self.fetcher.fetch(url, domain)
        except Exception as e:
            self._err_count += 1
            if self._stats:
                await self._stats.record_fetch_error(self.name, self.lang)
            clog.warning(
                f"{_ERR} {src_tag} {prog} [{fetch_idx}] -> {short} | "
                f"<yellow>{type(e).__name__}: {str(e)[:80]}</yellow>"
            )
            return None, []

        # Per-source content selectors
        content_selectors = self.cfg.get("content_selectors")
        title, text = extract_main_text(html, url, content_selectors=content_selectors)

        # Step 2: Playwright JS fallback
        if self._pw is not None:
            needs_render = self._js_render or JSDetector.is_js_heavy(html, text or "")
            if needs_render:
                clog.debug(
                    f"<yellow>JS-render fallback</yellow> "
                    f"{src_tag} {self._lang_tag} -- {short}"
                )
                rendered_html = await self._pw.fetch(
                    url,
                    wait_until=self._js_wait_until,
                    wait_selector=self._js_wait_selector,
                    timeout_ms=self._js_timeout_ms,
                )
                if rendered_html:
                    rendered_title, rendered_text = extract_main_text(
                        rendered_html, url, content_selectors=content_selectors
                    )
                    if rendered_text and len(rendered_text) > len(text or ""):
                        html = rendered_html
                        title = rendered_title
                        text = rendered_text
                        clog.debug(
                            f"<green>PW improved</green> {src_tag} "
                            f"len={len(text):,} -- {short}"
                        )

        # Step 3: Extract internal links
        raw_links = []
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin
            from ..discovery import _is_article_link, _normalize_url, _same_domain
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a"):
                href = a.get("href")
                if href:
                    full = urljoin(url, href)
                    if _same_domain(url, full) and _is_article_link(
                        full, self.cfg.get("discovery", {}).get("article_path_pattern")
                    ):
                        raw_links.append(_normalize_url(full))
        except Exception:
            pass

        discovery_cfg = self.cfg.get("discovery", {})
        exclude_paths = discovery_cfg.get("exclude_paths") or self.cfg.get("exclude_paths")
        filter_path_contains = discovery_cfg.get("filter_path_contains")
        internal_links = []
        for link in raw_links:
            if exclude_paths and any(p in link for p in exclude_paths):
                continue
            if filter_path_contains and not any(p in link for p in filter_path_contains):
                continue
            internal_links.append(link)

        # Step 4: Empty content check
        if not text or not title:
            self._skip_count += 1
            if self._stats:
                await self._stats.record_rejected(self.name, self.lang, "empty")

            msg = "empty extract"
            if title and (
                "moment" in title.lower()
                or "cloudflare" in str(title).lower()
                or "attention required" in str(title).lower()
            ):
                msg = f"WAF blocked (title: {title[:40]})"

            clog.info(
                f"{_NO} {src_tag} {prog} [{fetch_idx}] -> {short} | "
                f"<red>{msg}</red>"
            )
            return None, internal_links

        # Step 5: Per-source title rejection
        reject_title_keywords = self.cfg.get("reject_title_keywords")
        if reject_title_keywords and title:
            title_lower = title.lower()
            for kw in reject_title_keywords:
                if kw.lower() in title_lower:
                    self._skip_count += 1
                    if self._stats:
                        await self._stats.record_rejected(
                            self.name, self.lang, f"title_reject:{kw}"
                        )
                    clog.info(
                        f"{_NO} {src_tag} {prog} [{fetch_idx}] -> {short} | "
                        f"<red>title_reject:{kw}</red> | title=\"{title[:55]}\""
                    )
                    return None, internal_links

        text = normalize_vi_text(text)

        if len(text) > 80_000:
            text = text[:80_000]

        # Step 6: Quality filter
        ok, reason = _url_pre_approve(url, self.lang, self.cfg.get("trust_level", ""))
        if not ok:
            ok, reason = passes_quality(text, title, self.lang)

        if not ok:
            self._skip_count += 1
            if self._stats:
                await self._stats.record_rejected(self.name, self.lang, reason)
            clog.info(
                f"{_NO} {src_tag} {prog} [{fetch_idx}] -> {short} | "
                f"<red>{reason}</red> | len=<white>{len(text):,}</white> | "
                f"title=\"{title[:50]}\""
            )
            return None, internal_links

        # Step 7: Build document + log KEEP
        if self._stats:
            await self._stats.record_approved(self.name, self.lang)

        quality_score = score_quality(text, lang=self.lang)
        self._kept_count += 1

        clog.info(
            f"{_OK} {src_tag} {self._progress()} [{fetch_idx}] -> {short} | "
            f"score=<green>{quality_score:.3f}</green> | len=<white>{len(text):,}</white> | "
            f"signal=<green>{reason}</green> | title=\"{title[:50]}\""
        )

        doc = DocumentRaw(
            doc_id=doc_id_for(self.name, url),
            url=url, title=title, text=text,
            html_len=len(html), text_len=len(text),
            source=SourceMeta(
                domain=domain, source_name=self.name,
                source_type=self.cfg.get("source_type") or infer_source_type(
                    source_name=self.name,
                    domain=domain,
                    url=url,
                    tags=self.cfg.get("tags", []),
                    categories=self.cfg.get("categories", []),
                ),
                trust_level=self.cfg.get("trust_level", "medium"),
                language=self.lang,
                crawled_at=datetime.now(timezone.utc),
            ),
            categories=self.cfg.get("categories", []),
            tags=self.cfg.get("tags", []),
            quality_score=quality_score,
        )
        return doc, internal_links
