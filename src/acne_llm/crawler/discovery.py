"""URL discovery: sitemap + category (with recursive sub-page crawling)."""
from __future__ import annotations
import re
import asyncio
import unicodedata
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse, unquote
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from typing import Any


# ── Browser-like UA so sites don't immediately block us ─────────────────────
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ── Tracking/UTM params stripped before dedup ───────────────────────────────
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "ref", "source", "_ga", "mc_cid", "mc_eid",
}

# ── Known terminal list-page path segments ───────────────────────────────────
_LIST_PAGE_SEGMENTS = {
    # Vietnamese
    "tin-tuc", "chuyen-muc", "danh-muc", "danh-sach", "the", "chu-de",
    "khuyen-mai", "san-pham", "dich-vu", "hoat-dong", "su-kien",
    "bai-viet",  # can be a list root on some sites
    # English
    "news", "blog", "category", "categories", "tag", "tags", "archive",
    "archives", "forum", "community", "discussion", "label", "index",
    "products", "services",
}

# ── Content-area CSS selectors tried in order ────────────────────────────────
_CONTENT_SELECTORS = [
    "main", "article", "[role='main']",
    "#content", "#main", "#main-content",
    ".content", ".main-content", ".post-list", ".article-list",
    ".news-list", ".entry-content", ".blog-posts", ".cms-body",
    ".list-articles", ".list-news",
]

# ── Minimum article-slug characteristics ─────────────────────────────────────
_MIN_SLUG_LENGTH = 8   # descriptive slugs are rarely shorter


def _sanitize_href(href: str, source_name: str = "") -> str | None:
    """Làm sạch href trước khi urljoin để tránh sinh URL bẩn → 404.

    Trả về href đã được làm sạch, hoặc None nếu href không dùng được.

    Các trường hợp bị reject:
    - href trống, javascript:, mailto:, tel:, #
    - href chứa khoảng trắng thô (sau strip) — dấu hiệu bị bẩn
    - href toàn là ký tự đặc biệt / zero-width chars
    """
    if not href:
        return None

    # Strip leading/trailing whitespace (tab, newline, nbsp, ZWSP...)
    href = href.strip()

    # Bỏ zero-width và control characters (U+200B, U+FEFF, U+200C, v.v.)
    href = "".join(
        ch for ch in href
        if unicodedata.category(ch) not in ("Cf", "Cc") or ch in ("\t", "\n", "\r")
    ).strip()

    if not href:
        return None

    # Reject các scheme không phải HTTP
    lower = href.lower()
    for bad_scheme in ("javascript:", "mailto:", "tel:", "data:", "vbscript:"):
        if lower.startswith(bad_scheme):
            if source_name:
                logger.debug(f"[{source_name}] sanitize_href: rejected bad scheme — {href[:80]}")
            return None

    # Reject fragment-only
    if href.startswith("#"):
        return None

    # Reject nếu sau decode vẫn còn khoảng trắng thô bên trong path
    # (VD: "/benh-ly/mun trung ca/" — dấu hiệu href bị cắt sai)
    try:
        decoded = unquote(href)
        parsed = urlparse(decoded)
        if " " in parsed.path:
            if source_name:
                logger.debug(
                    f"[{source_name}] sanitize_href: rejected raw space in path — {href[:80]}"
                )
            return None
    except Exception:
        pass

    return href


def _normalize_url(url: str) -> str:
    """Canonical form: strip tracking params, sort remaining params, lowercase host."""
    try:
        p = urlparse(url)
        path = p.path.rstrip("/") or "/"
        # RFC 3986: scheme and host are case-insensitive
        netloc = p.netloc.lower()
        if p.query:
            qs = {
                k: v
                for k, v in parse_qs(p.query, keep_blank_values=False).items()
                if k.lower() not in _TRACKING_PARAMS
            }
            # Sort keys → same URL regardless of param order
            query = urlencode(sorted(qs.items()), doseq=True)
        else:
            query = ""
        return urlunparse((p.scheme.lower(), netloc, path, p.params, query, ""))
    except Exception:
        return url


async def discover_from_sitemap(
    sitemap_url: str, filter_path_contains: list[str] | None = None,
    filter_keywords: list[str] | None = None, max_urls: int = 5000,
    exclude_paths: list[str] | None = None,
) -> list[str]:
    urls: list[str] = []
    seen_norm: set[str] = set()
    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True, headers=_BROWSER_HEADERS,
    ) as client:
        stack = [sitemap_url]
        seen: set[str] = set()
        while stack and len(urls) < max_urls:
            sm = stack.pop()
            if sm in seen:
                continue
            seen.add(sm)
            try:
                r = await client.get(sm)
                r.raise_for_status()
            except Exception as e:
                logger.warning(f"sitemap fail {sm}: {e}")
                continue
            soup = BeautifulSoup(r.text, "xml")
            for s in soup.find_all("sitemap"):
                loc = s.find("loc")
                if loc:
                    stack.append(loc.text.strip())
            for u in soup.find_all("url"):
                loc = u.find("loc")
                if not loc:
                    continue
                link = loc.text.strip()
                norm = _normalize_url(link)
                if norm in seen_norm:
                    continue
                if exclude_paths and any(p in link for p in exclude_paths):
                    continue
                if filter_path_contains and not any(p in link for p in filter_path_contains):
                    continue
                if filter_keywords and not any(k.lower() in link.lower() for k in filter_keywords):
                    continue
                seen_norm.add(norm)
                urls.append(link)
                if len(urls) >= max_urls:
                    break
    return urls


async def discover_from_search(
    queries: list[str],
    domain: str | None = None,
    max_results_per_query: int = 50,
    filter_path_contains: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    filter_keywords: list[str] | None = None,
) -> list[str]:
    """Sử dụng duckduckgo-search để lấy kết quả từ tìm kiếm Google/Bing thông qua search engine."""
    urls = []
    seen = set()
    try:
        from ddgs import DDGS
        def run_search(q: str):
            with DDGS() as ddgs:
                # Trả về list dict [{'title': '...', 'href': '...', 'body': '...'}]
                return list(ddgs.text(q, max_results=max_results_per_query))
        
        for q in queries:
            search_q = f"site:{domain} {q}" if domain else q
            # Chạy search api đồng bộ trong thread để không block async event loop
            results = await asyncio.to_thread(run_search, search_q)
            if not results:
                continue
            for r in results:
                link = r.get("href")
                if not link:
                    continue
                norm = _normalize_url(link)
                if norm in seen:
                    continue
                if exclude_paths and any(p in link for p in exclude_paths):
                    continue
                if filter_path_contains and not any(p in link for p in filter_path_contains):
                    continue
                if filter_keywords and not any(k.lower() in link.lower() for k in filter_keywords):
                    continue
                seen.add(norm)
                urls.append(link)
    except ImportError:
        logger.warning("ddgs not installed, skipping search discovery")
    except Exception as e:
        logger.warning(f"search discover fail: {e}")
        
    return urls


def _same_domain(base: str, link: str) -> bool:
    try:
        d1 = urlparse(base).netloc.lower()
        d2 = urlparse(link).netloc.lower()
        if d1 == d2:
            return True
        # Handle www. prefix mismatch (e.g. mediplus.vn vs www.mediplus.vn)
        d1_clean = d1.removeprefix("www.")
        d2_clean = d2.removeprefix("www.")
        return d1_clean == d2_clean
    except Exception:
        return False


def _is_article_link(href: str, article_path_pattern: str | None = None) -> bool:
    """Return False for URLs that are clearly not articles.

    Combines negative filters (extension, navigation patterns, list-page segments)
    with a positive slug-quality check and an optional per-domain path pattern.
    """
    ignore_exts = (
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip",
        ".css", ".js", ".xml", ".ico", ".webp", ".mp4", ".mp3",
        ".woff", ".woff2", ".ttf", ".eot",
    )
    lower = href.lower()

    if any(lower.endswith(e) for e in ignore_exts):
        return False
    if "#" in href:
        return False

    # ── Negative: known non-article URL patterns ─────────────────────────────
    nav_patterns = [
        # Pagination (various forms)
        r"/page/\d+",
        r"/trang/\d+",
        r"[?&](paged|pagenumber|page|p)=\d+",
        # Auth / admin
        r"/wp-(admin|login|json)(/|$|\?)",
        # Search result pages
        r"[?&](s|q|search|keyword|tu-khoa)=",
        # Navigation / utility paths that NEVER contain article slugs beneath them
        # (tag pages, category roots, author pages, auth pages, utility pages)
        r"/(tag|tags|category|categories|author|search|login|register"
        r"|cart|contact|about|sitemap|feed|rss)(/|$|\?)",
        r"/(privacy|policy|terms|faq|help|support|cookie|press|media"
        r"|jobs|careers|advertise|subscribe|newsletter)(/|$|\?)",
        # Vietnamese hospital / site utility paths
        r"/(gioi-thieu|tuyen-dung|chuyen-gia|bac-si|doi-ngu|lien-he|thu-vien)(/|$|\?)",
        r"/(lich-kham|dat-kham|bang-gia|co-so-vat-chat|du-an)(/|$|\?)",
        r"/(tin-tuc-su-kien-noi-bo|su-kien-benh-vien|thong-bao)(/|$|\?)",
        # Wikipedia non-article namespaces / edit pages
        r"/wiki/(talk|user|user_talk|wikipedia|template|template_talk"
        r"|help|category_talk|portal|file|module):",
        r"[?&]action=(edit|submit|history|viewsource)",
        # NOTE: /news/, /blog/, /tin-tuc/ etc. can legitimately contain article slugs
        # beneath them (e.g. /news/acne-treatment-guide).  These are blocked at ROOT
        # level only via the _LIST_PAGE_SEGMENTS last-segment check below, NOT here.
    ]
    for p in nav_patterns:
        if re.search(p, lower):
            return False

    # ── Path-segment analysis ────────────────────────────────────────────────
    try:
        path = urlparse(href).path.rstrip("/") or "/"
        segments = [s for s in path.split("/") if s]  # non-empty segments

        if not segments:
            return False  # root URL = homepage, not an article

        last = segments[-1].lower()

        # Block if the final segment is a known list-page name
        if last in _LIST_PAGE_SEGMENTS:
            return False

        # Block if second-to-last is a list-page AND final segment looks like
        # a bare page number or a very short non-alpha token (e.g. /tin-tuc/2)
        if len(segments) >= 2 and segments[-2].lower() in _LIST_PAGE_SEGMENTS:
            if last.isdigit() or (len(last) <= 3 and not last.isalpha()):
                return False

        # ── Positive confirmation: slug should be descriptive ─────────────
        slug = segments[-1]
        # Pure numeric IDs (e.g. /articles/123456) are legitimate article keys
        if not slug.isdigit():
            if len(slug) < _MIN_SLUG_LENGTH and "-" not in slug:
                # Too short and no hyphen → probably a tag / short category code
                return False

    except Exception:
        pass

    # ── Optional per-domain article path pattern (from source YAML config) ──
    if article_path_pattern:
        try:
            path = urlparse(href).path
            if not re.search(article_path_pattern, path, re.IGNORECASE):
                return False
        except Exception:
            pass

    return True


async def _fetch_page_links(
    client: httpx.AsyncClient,
    url: str,
    base_domain: str,
    link_selector: str = "a",
    sleep_sec: float = 0.4,
    article_path_pattern: str | None = None,
    source_name: str = "",
    js_fetcher: Any = None,
) -> list[str]:
    """Fetch links from one page, preferring content-area over full <body>.

    Improvements vs original:
    - Passes article_path_pattern into _is_article_link for per-domain filtering.
    - Skips <a> tags with very short anchor text (buttons, icons, breadcrumb items)
      that almost certainly point to nav/listing pages rather than articles.
    - Sanitizes href before urljoin to prevent dirty URLs generating 404s.
    """
    await asyncio.sleep(sleep_sec)
    html = ""
    try:
        if js_fetcher:
            html = await js_fetcher.fetch(url, wait_until="networkidle")
        if not html:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception:
        return []
    soup = BeautifulSoup(html, "lxml")

    # Try to scope to a meaningful content container
    container = None
    for sel in _CONTENT_SELECTORS:
        container = soup.select_one(sel)
        if container:
            # FIX: Some sites (HelloBacsi) have <article> as a small widget,
            #      not the main article list. Fallback to soup if too few links.
            if len(container.select("a")) >= 10:
                break
            container = None  # too small, keep searching
    search_root = container if container else soup

    links: list[str] = []
    for a in search_root.select(link_selector if link_selector != "a" else "a"):
        raw_href = a.get("href", "")
        if not raw_href:
            continue
        # Sanitize href trước khi urljoin — tránh URL bẩn
        href = _sanitize_href(raw_href, source_name)
        if href is None:
            continue
        # Skip links whose anchor text is suspiciously short — nav buttons,
        # icon links, pagination arrows, breadcrumb single-word items, etc.
        # Nới lỏng: Cho phép 3 ký tự (VD: "Mụn", "Da") thay vì 5.
        # Nếu URL có dấu hiệu bài viết (chứa gạch ngang), tin tưởng URL hơn.
        anchor_text = a.get_text(strip=True)
        if anchor_text and len(anchor_text) < 3 and "-" not in href:
            continue
        full = urljoin(url, href)
        if _same_domain(f"https://{base_domain}", full) and _is_article_link(
            full, article_path_pattern
        ):
            links.append(_normalize_url(full))
    return links


async def discover_from_category(
    start_urls: list[str],
    pagination_selector: str | None = None,
    link_selector: str = "a",
    max_pagination_pages: int = 50,
    crawl_sub_pages: bool = True,
    max_total_urls: int = 2000,
    crawl_depth: int = 2,
    filter_path_contains: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    article_path_pattern: str | None = None,
    js_fetcher: Any = None,
    js_wait_until: str = "networkidle",
    js_timeout_ms: int = 30000,
) -> list[str]:
    """
    Two modes:
    - pagination_selector set: follow next-page links (page 1 → 2 → 3 …)
    - otherwise: BFS up to crawl_depth levels from start URLs

    Improvements vs original:
    - max_pagination_pages controls pagination page limit (separate from max_total_urls)
    - crawl_depth controls BFS depth for sub-page mode (default 2)
    - Pagination branch now fetches each page ONCE (was fetching twice).
    - consecutive_empty guard stops pagination after 3 pages with no new links.
    - Passes article_path_pattern throughout for per-domain URL confirmation.
    """
    collected: set[str] = set()
    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True, headers=_BROWSER_HEADERS,
    ) as client:
        for start in start_urls:
            base_domain = urlparse(start).netloc

            if pagination_selector:
                # ── Pagination mode — single fetch per page ──────────────
                page = start
                visited_pages: set[str] = {_normalize_url(start)}
                consecutive_empty = 0

                for _ in range(max_pagination_pages):
                    if len(collected) >= max_total_urls:
                        break

                    await asyncio.sleep(0.5)
                    html = ""
                    try:
                        if js_fetcher:
                            html = await js_fetcher.fetch(
                                page, 
                                wait_until=js_wait_until,
                                timeout_ms=js_timeout_ms
                            )
                        if not html:
                            r = await client.get(page)
                            r.raise_for_status()
                            html = r.text
                    except Exception as e:
                        logger.debug(f"pagination fetch fail {page}: {e}")
                        break

                    soup = BeautifulSoup(html, "lxml")

                    # Extract article links from this page
                    container = None
                    for sel in _CONTENT_SELECTORS:
                        container = soup.select_one(sel)
                        if container and len(container.select("a")) >= 10:
                            break
                        container = None
                    search_root = container if container else soup

                    new_links: list[str] = []
                    for a in search_root.select(
                        link_selector if link_selector != "a" else "a"
                    ):
                        raw_href = a.get("href", "")
                        if not raw_href:
                            continue
                        href = _sanitize_href(raw_href)
                        if href is None:
                            continue
                        anchor_text = a.get_text(strip=True)
                        if anchor_text and len(anchor_text) < 3 and "-" not in href:
                            continue
                        full = urljoin(page, href)
                        if _same_domain(f"https://{base_domain}", full) and _is_article_link(
                            full, article_path_pattern
                        ):
                            norm = _normalize_url(full)
                            if norm not in collected:
                                new_links.append(norm)

                    if new_links:
                        collected.update(new_links)
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            logger.debug(
                                f"pagination stopping after 3 empty pages at {page}"
                            )
                            break

                    # Follow pagination — find next-page link in same HTML
                    # FIX: select_one returns the FIRST match (often page 1 / prev).
                    #      Scan ALL candidates and pick the first UNVISITED one.
                    nxt = None
                    for candidate in soup.select(pagination_selector):
                        raw_href = candidate.get("href", "")
                        href = _sanitize_href(raw_href)
                        if not href:
                            continue
                        cand_url = _normalize_url(urljoin(page, href))
                        if cand_url not in visited_pages:
                            nxt = candidate
                            break
                    if not nxt:
                        logger.debug(f"pagination exhausted at {page}")
                        break
                    nxt_href = _sanitize_href(nxt.get("href", ""))
                    if not nxt_href:
                        break
                    next_page = _normalize_url(urljoin(page, nxt_href))
                    visited_pages.add(next_page)
                    page = next_page

            else:
                # ── Sub-page (category crawl) mode — BFS up to crawl_depth ──
                logger.debug(
                    f"category crawl (sub-page mode, depth={crawl_depth}) from {start}"
                )
                frontier = await _fetch_page_links(
                    client, start, base_domain, link_selector,
                    article_path_pattern=article_path_pattern,
                    js_fetcher=js_fetcher,
                )
                new_links = [u for u in frontier if u not in collected]
                collected.update(new_links)

                if crawl_sub_pages:
                    for _depth in range(1, crawl_depth):
                        if not frontier or len(collected) >= max_total_urls:
                            break
                        sem = asyncio.Semaphore(5)
                        sample = list(dict.fromkeys(frontier))[:max_pagination_pages]

                        async def _get_sub(u: str, _s=sem) -> list[str]:
                            async with _s:
                                return await _fetch_page_links(
                                    client, u, base_domain, link_selector,
                                    article_path_pattern=article_path_pattern,
                                    js_fetcher=js_fetcher,
                                )

                        sub_results = await asyncio.gather(
                            *[_get_sub(u) for u in sample], return_exceptions=True,
                        )
                        next_frontier: list[str] = []
                        for res in sub_results:
                            if not isinstance(res, list):
                                continue
                            for link in res:
                                if link not in collected:
                                    collected.add(link)
                                    next_frontier.append(link)
                                    if len(collected) >= max_total_urls:
                                        break
                            if len(collected) >= max_total_urls:
                                break
                        logger.debug(
                            f"sub-page depth {_depth + 1}: {len(next_frontier)} new links "
                            f"(total {len(collected)})"
                        )
                        frontier = next_frontier

    result = [u for u in collected if _is_article_link(u, article_path_pattern)]
    if exclude_paths:
        result = [u for u in result if not any(p in u for p in exclude_paths)]
    if filter_path_contains:
        result = [u for u in result if any(p in u for p in filter_path_contains)]
    # Final dedup (normalized keys already in set, but guard against stragglers)
    return list(dict.fromkeys(result))[:max_total_urls]
