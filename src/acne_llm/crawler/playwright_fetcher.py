"""
Playwright-based fetcher for JavaScript-heavy / SPA pages.

Architecture
────────────
JSDetector      — static heuristics to decide if a raw httpx HTML response
                  was rendered by a JavaScript framework (React, Vue, Next.js …)
                  and thus likely contains little meaningful text.

PlaywrightFetcher — manages a single shared Chromium browser process
                    (lazy-started on first use).  Each fetch() call opens a
                    fresh BrowserContext (clean cookies/localStorage), navigates,
                    waits for content, returns the fully-rendered HTML, then
                    closes the context.

                    Concurrency is controlled by an asyncio.Semaphore so we
                    never overwhelm the host with too many open tabs.

Usage in source config (seed_sources.yaml)
──────────────────────────────────────────
  js_render: true                    # always use Playwright for this source
  js_wait_until: networkidle         # wait strategy (default: networkidle)
  js_wait_selector: .detail-content  # optional: also wait for this CSS selector
  js_timeout_ms: 30000               # per-page timeout (default: 30 000 ms)

Graceful degradation
────────────────────
If `playwright` is not installed the module still imports cleanly; any call to
PlaywrightFetcher.fetch() will return "" and log a warning, so the caller can
treat it as another empty-text result without crashing the pipeline.
"""
from __future__ import annotations

import asyncio
import re
from loguru import logger

try:
    from playwright.async_api import async_playwright, Browser, Playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning(
        "playwright not installed — JS-render fallback disabled. "
        "Run: pip install playwright && playwright install chromium"
    )


# ── JS-framework detection signals ────────────────────────────────────────────
# These appear in raw HTML when the page shell is an SPA and real content
# is only populated after JS executes.

_SPA_ID_PATTERNS = re.compile(
    r"""id=['"](__next|__nuxt|__app|root|app|vue-app|react-app|angular-app)['"]""",
    re.IGNORECASE,
)
_SPA_DATA_PATTERNS = [
    "__NEXT_DATA__",           # Next.js
    "__NUXT__",                # Nuxt.js
    "window.__INITIAL_STATE__",
    "window._sharedData",
    "data-reactroot",          # React SSR marker
    "ng-version=",             # Angular
    "x-data=",                 # Alpine.js
    "v-cloak",                 # Vue before hydration
    "cf-turnstile",            # Cloudflare Captcha
    "challenge-platform",      # Cloudflare JS
    "Just a moment...",        # Generic WAF Wait
]

# Minimum rendered text length — if we got LESS than this after normal fetch,
# and the HTML is large, suspect JS rendering.
_MIN_MEANINGFUL_TEXT = 200
_MIN_HTML_SIZE_FOR_SPA_SUSPECT = 15_000


class JSDetector:
    """Decide whether a raw HTTP response probably needs JS rendering.

    Designed to be cheap — called per URL, in the hot path.
    """

    @staticmethod
    def is_js_heavy(html: str, extracted_text: str) -> bool:
        """Return True if heuristics suggest the page is JS-rendered.

        Parameters
        ----------
        html:            Raw HTML returned by httpx (before JS execution).
        extracted_text:  Text extracted by trafilatura/readability from that HTML.
        """
        # Fast path: if we already got a good amount of text, no need for Playwright.
        if extracted_text and len(extracted_text.strip()) >= _MIN_MEANINGFUL_TEXT:
            return False

        # Signal 1: well-known SPA root element IDs
        if _SPA_ID_PATTERNS.search(html):
            return True

        # Signal 2: global JS data islands injected by SSR frameworks
        for marker in _SPA_DATA_PATTERNS:
            if marker in html:
                return True

        # Signal 3: very low text-to-HTML ratio on a large page
        # (lots of markup, basically empty body — content loaded by JS)
        if (
            len(html) >= _MIN_HTML_SIZE_FOR_SPA_SUSPECT
            and len((extracted_text or "").strip()) < _MIN_MEANINGFUL_TEXT
        ):
            return True

        return False


class PlaywrightFetcher:
    """Singleton Chromium browser for fetching JS-rendered pages.

    Parameters
    ----------
    headless:       Run browser without GUI (default True).
    max_concurrent: Maximum simultaneous open tabs (default 3 — Playwright
                    is much heavier than httpx).
    default_timeout_ms:
                    Default page-load timeout in milliseconds (default 30 000).
    """

    def __init__(
        self,
        headless: bool = True,
        max_concurrent: int = 3,
        default_timeout_ms: int = 30_000,
    ) -> None:
        self._headless = headless
        self._sem = asyncio.Semaphore(max_concurrent)
        self._default_timeout_ms = default_timeout_ms

        self._pw: "Playwright | None" = None
        self._browser: "Browser | None" = None
        self._lock = asyncio.Lock()   # guards lazy-start

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def _ensure_started(self) -> None:
        """Lazy-start the Playwright runtime and Chromium browser."""
        if self._browser is not None:
            return
        async with self._lock:
            if self._browser is not None:  # double-checked inside lock
                return
            if not _PLAYWRIGHT_AVAILABLE:
                return
            logger.info("🎭 Starting Playwright Chromium browser …")
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=self._headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    # Reduce fingerprinting and noise
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            logger.info("🎭 Chromium ready")

    async def close(self) -> None:
        """Shut down the browser and Playwright runtime gracefully."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    # ── Core fetch ────────────────────────────────────────────────────────────

    async def fetch(
        self,
        url: str,
        *,
        wait_until: str = "networkidle",
        wait_selector: str | None = None,
        timeout_ms: int | None = None,
    ) -> str:
        """Fetch *url* using a headless Chromium tab and return rendered HTML.

        Parameters
        ----------
        url:            Target URL.
        wait_until:     Playwright load event — "networkidle" (default),
                        "domcontentloaded", or "load".
        wait_selector:  Optional CSS selector; waits for it to appear in DOM
                        after the main navigation event, useful for lazy-loaded
                        content areas.
        timeout_ms:     Per-page timeout; falls back to default_timeout_ms.

        Returns
        -------
        Fully-rendered HTML string, or "" if fetch fails or Playwright is not
        installed.
        """
        if not _PLAYWRIGHT_AVAILABLE:
            return ""

        await self._ensure_started()
        if self._browser is None:
            return ""

        timeout = timeout_ms or self._default_timeout_ms
        # "networkidle" can time out on pages that have polling/WebSocket activity.
        # Fall back gracefully to "domcontentloaded" if that happens.
        async with self._sem:
            return await self._fetch_with_fallback(
                url, wait_until=wait_until, wait_selector=wait_selector,
                timeout=timeout,
            )

    async def _fetch_with_fallback(
        self,
        url: str,
        wait_until: str,
        wait_selector: str | None,
        timeout: int,
    ) -> str:
        """Inner fetch with automatic wait-strategy fallback."""
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="vi-VN",
            java_script_enabled=True,
            # Pretend to be a real viewport so lazy-loading triggers
            viewport={"width": 1280, "height": 900},
            # Mask automation signals
            extra_http_headers={
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        page = await context.new_page()

        # Remove 'navigator.webdriver' flag — detected by many bot-protection systems
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            html = await self._navigate_and_extract(
                page, url,
                wait_until=wait_until,
                wait_selector=wait_selector,
                timeout=timeout,
            )
            if html:
                logger.debug(f"🎭 PW ok (len={len(html):,}) {url}")
            return html

        except Exception as e:
            logger.warning(f"🎭 PW fail [{wait_until}] {url}: {e}")

            # Retry with a lighter wait strategy before giving up
            if wait_until == "networkidle":
                try:
                    logger.debug(f"🎭 PW retry domcontentloaded {url}")
                    html = await self._navigate_and_extract(
                        page, url,
                        wait_until="domcontentloaded",
                        wait_selector=None,
                        timeout=timeout,
                    )
                    if html:
                        logger.debug(f"🎭 PW retry ok (len={len(html):,}) {url}")
                    return html
                except Exception as e2:
                    logger.warning(f"🎭 PW retry also failed {url}: {e2}")
            return ""

        finally:
            await context.close()

    @staticmethod
    async def _navigate_and_extract(
        page,
        url: str,
        wait_until: str,
        wait_selector: str | None,
        timeout: int,
    ) -> str:
        """Navigate to URL, optionally wait for a selector, return page HTML."""
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        
        # Auto scroll to trigger infinite load / lazy load
        try:
            await page.evaluate("""
                async () => {
                    await new Promise((resolve) => {
                        let totalHeight = 0;
                        let distance = 500;
                        let scrolls = 0;
                        let timer = setInterval(() => {
                            let scrollHeight = document.body.scrollHeight;
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            scrolls++;
                            if(totalHeight >= scrollHeight - window.innerHeight || scrolls > 20){
                                clearInterval(timer);
                                resolve();
                            }
                        }, 200);
                    });
                }
            """)
        except Exception:
            pass

        if wait_selector:
            try:
                await page.wait_for_selector(
                    wait_selector, timeout=10_000, state="visible"
                )
            except Exception:
                # Selector not found — page may still have partial content
                logger.debug(f"🎭 wait_selector '{wait_selector}' not found at {url}")

        # Small extra pause to let deferred content (ads, carousels) settle
        await page.wait_for_timeout(800)

        return await page.content()
