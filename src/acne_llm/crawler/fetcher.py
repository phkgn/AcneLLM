import asyncio
import httpx
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


class GlobalRateLimiter:
    """Token-bucket global rate limiter — caps total req/sec across ALL domains.

    Prevents IP-level blocks from WAFs/CDNs that track aggregate request rates
    even when per-domain limits are respected.
    """

    def __init__(self, max_rate: float = 5.0):
        self._min_interval = 1.0 / max(max_rate, 0.01)
        self._last: float = 0.0
        self._lock: asyncio.Lock | None = None  # created lazily (event-loop safe)

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self) -> None:
        async with self._get_lock():
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = loop.time()


class DomainRateLimiter:
    """Per-domain rate limiting with independent locks — domains don't block each other."""

    def __init__(self, rate_per_sec: float = 1.0):
        self._min_interval = 1.0 / max(rate_per_sec, 0.01)
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, domain: str) -> asyncio.Lock:
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    async def acquire(self, domain: str) -> None:
        async with self._lock_for(domain):
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._min_interval - (now - self._last.get(domain, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[domain] = loop.time()


class AsyncFetcher:
    def __init__(
        self,
        user_agent: str,
        rate_per_sec: float = 1.0,
        global_max_rate: float = 5.0,
        timeout: float = 20.0,
    ):
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
        )
        self._limiter = DomainRateLimiter(rate_per_sec)
        self._global_limiter = GlobalRateLimiter(global_max_rate)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def fetch(self, url: str, domain: str) -> tuple[str, int]:
        # Global rate limit FIRST (coarse), then per-domain (fine-grained)
        await self._global_limiter.acquire()
        await self._limiter.acquire(domain)
        try:
            resp = await self._client.get(url)

            # Handle 429 explicitly: honour Retry-After before re-raising
            # so tenacity's exponential backoff starts from an informed position.
            if resp.status_code == 429:
                retry_after_raw = resp.headers.get("Retry-After", "10")
                try:
                    retry_after = min(float(retry_after_raw), 120.0)
                except ValueError:
                    retry_after = 10.0
                logger.warning(
                    f"429 rate-limited [{domain}] — sleeping {retry_after:.0f}s "
                    f"before retry | {url}"
                )
                await asyncio.sleep(retry_after)
                # Re-raise as HTTPStatusError so tenacity catches and retries
                raise httpx.HTTPStatusError(
                    "429 Too Many Requests",
                    request=resp.request,
                    response=resp,
                )

            resp.raise_for_status()
            return resp.text, resp.status_code

        except httpx.HTTPStatusError:
            raise  # Let tenacity decide whether to retry
        except Exception as e:
            logger.debug(f"fetch fail {url}: {e}")
            raise

    async def close(self) -> None:
        await self._client.aclose()
