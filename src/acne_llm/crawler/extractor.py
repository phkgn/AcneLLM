"""HTML → clean text, dùng trafilatura (ưu tiên) + readability fallback."""
from __future__ import annotations
import trafilatura
from loguru import logger

try:
    from readability import Document as ReadabilityDoc  # readability-lxml
except Exception:
    ReadabilityDoc = None


def extract_main_text(
    html: str, url: str = "", content_selectors: list[str] | None = None
) -> tuple[str | None, str | None]:
    """Return (title, text). None if extraction failed."""
    try:
        extracted = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=False,
            favor_recall=True, output_format="txt",
        )
        metadata = trafilatura.extract_metadata(html, default_url=url)
        title = metadata.title if metadata and metadata.title else None
        if extracted and len(extracted) > 100:   # 200→100: tránh miss trang có content ngắn
            return title, extracted
    except Exception as e:
        logger.debug(f"trafilatura fail {url}: {e}")

    if ReadabilityDoc is not None:
        try:
            doc = ReadabilityDoc(html)
            title = doc.short_title()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(doc.summary(), "lxml")
            text = soup.get_text("\n")
            if text and len(text) > 200:
                return title, text
        except Exception as e:
            logger.debug(f"readability fail {url}: {e}")

    # Fallback 3: generic semantic CSS selectors — dùng khi trafilatura + readability đều fail
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # Chỉ xóa script/style/noscript — KHÔNG xóa header vì nhiều CMS VI (Vinmec, WordPress)
        # dùng <header> để wrap tiêu đề bài, xóa nó sẽ mất content và title
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()

        _DEFAULT_SELECTORS = [
            # Vietnamese hospital/medical CMS (Vinmec, BenhVienDa, DaLieu...)
            ".detail-content", ".detail__content", ".cms-body",
            ".article-detail", ".article-detail-content",
            ".news-detail", ".news-detail-content", ".news-content",
            ".post-detail-content", ".content-detail", ".content-body",
            # Generic WordPress / international
            "main article", "article", ".entry-content", ".post-content",
            ".article-body", ".article-content", "#content .content",
            ".chapter-content", "#main-content", ".document-content",
            ".page-content", ".single-content",
            # Fallback cuối: toàn bộ main
            "main", "#content", ".content",
        ]
        _CONTENT_SELECTORS = list(dict.fromkeys((content_selectors or []) + _DEFAULT_SELECTORS))
        for sel in _CONTENT_SELECTORS:
            node = soup.select_one(sel)
            if node:
                text = node.get_text("\n").strip()
                if len(text) > 150:   # giảm threshold 200→150 cho trang ngắn
                    if not title:
                        h = soup.find(["h1", "h2"])
                        title = h.get_text().strip() if h else None
                    return title, text
    except Exception as e:
        logger.debug(f"bs4 fallback fail {url}: {e}")

    return None, None
