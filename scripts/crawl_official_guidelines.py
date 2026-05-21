"""Crawl selected official acne guideline pages into DocumentRaw JSONL.

This is intentionally narrow: it fetches four high-trust AAD/NICE URLs and
merges them into data/raw/documents.jsonl using stable doc_ids.

Usage:
    python -m scripts.crawl_official_guidelines
    python -m scripts.crawl_official_guidelines --force
    python -m scripts.crawl_official_guidelines --dry-run
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.crawler.extractor import extract_main_text
from acne_llm.crawler.quality_filter import score_quality
from acne_llm.schemas.kb import DocumentRaw, SourceMeta


DEFAULT_DOCS_PATH = ROOT / "data" / "raw" / "documents.jsonl"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class GuidelineTarget:
    doc_id: str
    url: str
    source_name: str
    quality_score: float
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    summary: str
    content_selectors: tuple[str, ...] = ()


TARGETS: tuple[GuidelineTarget, ...] = (
    GuidelineTarget(
        doc_id="official_guideline_aad_2024_acne_update",
        url="https://www.aad.org/news/updated-guidelines-acne-management",
        source_name="American Academy of Dermatology",
        quality_score=0.9,
        categories=("acne", "guidelines", "clinical-update"),
        tags=("aad-2024", "english", "guidelines", "high-trust"),
        summary="AAD 2024 acne guideline update summary.",
        content_selectors=(".content",),
    ),
    GuidelineTarget(
        doc_id="official_guideline_aad_acne_page",
        url="https://www.aad.org/member/clinical-quality/guidelines/acne",
        source_name="American Academy of Dermatology",
        quality_score=0.95,
        categories=("acne", "guidelines"),
        tags=("aad", "english", "guidelines", "high-trust"),
        summary="AAD acne clinical guideline page.",
        content_selectors=(".content", "main"),
    ),
    GuidelineTarget(
        doc_id="official_guideline_nice_ng198_recommendations",
        url="https://www.nice.org.uk/guidance/ng198/chapter/recommendations",
        source_name="NICE NG198",
        quality_score=1.0,
        categories=("acne", "guidelines", "recommendations"),
        tags=("nice-ng198", "english", "guidelines", "evidence-based", "high-trust"),
        summary="NICE NG198 acne vulgaris management recommendations.",
        content_selectors=("#ng198-recommendations",),
    ),
    GuidelineTarget(
        doc_id="official_guideline_nice_ng198_ncbi_bookshelf",
        url="https://www.ncbi.nlm.nih.gov/books/NBK573056/",
        source_name="NCBI Bookshelf / NICE NG198",
        quality_score=0.95,
        categories=("acne", "guidelines", "evidence-review"),
        tags=("nice-ng198", "ncbi-bookshelf", "english", "guidelines", "high-trust"),
        summary="NCBI Bookshelf copy of NICE NG198 acne vulgaris guidance.",
        content_selectors=("#maincontent", "main", ".book"),
    ),
)


app = typer.Typer(add_completion=False)


def _load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fetch_html(url: str, timeout_seconds: float) -> str:
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _extract_with_preferred_selectors(
    html: str,
    *,
    selectors: tuple[str, ...],
) -> tuple[str | None, str | None]:
    if not selectors:
        return None, None

    try:
        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    except Exception:
        return None, None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    title_node = soup.find("h1") or soup.find("title")
    title = title_node.get_text(" ", strip=True) if title_node else None

    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        for tag in node.find_all(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = node.get_text("\n", strip=True)
        text = _normalize_text(text)
        if len(text) >= 400:
            return title, text

    return None, None


def _document_from_target(target: GuidelineTarget, timeout_seconds: float) -> DocumentRaw:
    html = _fetch_html(target.url, timeout_seconds)
    title, text = extract_main_text(html, url=target.url)
    selector_title, selector_text = _extract_with_preferred_selectors(
        html,
        selectors=target.content_selectors,
    )
    if selector_text:
        title = selector_title or title
        text = selector_text
    if not text:
        raise RuntimeError(f"Could not extract main text from {target.url}")

    text = _normalize_text(text)
    if len(text) < 400:
        raise RuntimeError(f"Extracted text is too short ({len(text)} chars): {target.url}")

    domain = urlparse(target.url).netloc
    extracted_score = score_quality(text, lang="en")
    quality_score = max(target.quality_score, round(extracted_score, 3))
    quality_score = min(1.0, quality_score)

    return DocumentRaw(
        doc_id=target.doc_id,
        url=target.url,
        title=title or target.summary,
        text=text,
        html_len=len(html),
        text_len=len(text),
        source=SourceMeta(
            domain=domain,
            source_name=target.source_name,
            trust_level="high",
            language="en",
            crawled_at=datetime.now(),
            robots_allowed=True,
            license=None,
        ),
        categories=list(target.categories),
        tags=list(target.tags),
        summary=target.summary,
        quality_score=quality_score,
    )


def _merge_documents(
    docs_path: Path,
    docs: list[DocumentRaw],
    *,
    force: bool,
) -> int:
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    existing_records = _load_jsonl(docs_path)
    doc_ids = {doc.doc_id for doc in docs}

    if force:
        kept_existing = [
            record for record in existing_records
            if record.get("doc_id") not in doc_ids
        ]
        docs_to_write = docs
    else:
        existing_ids = {record.get("doc_id") for record in existing_records}
        kept_existing = existing_records
        docs_to_write = [doc for doc in docs if doc.doc_id not in existing_ids]

    tmp_path = docs_path.with_name(f"{docs_path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for record in kept_existing:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        for doc in docs_to_write:
            f.write(doc.model_dump_json() + "\n")
    tmp_path.replace(docs_path)

    return len(docs_to_write)


@app.command()
def run(
    docs_path: Path = typer.Option(DEFAULT_DOCS_PATH, help="Target DocumentRaw JSONL path"),
    force: bool = typer.Option(False, "--force", help="Replace existing official guideline docs"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and validate without writing"),
    timeout_seconds: float = typer.Option(60.0, help="HTTP timeout per URL"),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--fail-fast",
        help="Continue crawling remaining URLs if one URL fails",
    ),
) -> None:
    docs: list[DocumentRaw] = []
    failures: list[str] = []

    for target in TARGETS:
        try:
            doc = _document_from_target(target, timeout_seconds)
            docs.append(doc)
            logger.success(
                "Crawled {} | chars={} | quality={}",
                target.doc_id,
                doc.text_len,
                doc.quality_score,
            )
        except Exception as exc:
            failures.append(f"{target.url}: {exc}")
            logger.error("Failed {} | {}", target.url, exc)
            if not continue_on_error:
                raise typer.Exit(code=1) from exc

    if not docs:
        raise typer.Exit(code=1)

    if dry_run:
        logger.info("Dry run complete: validated {} docs; no files written.", len(docs))
    else:
        written = _merge_documents(docs_path, docs, force=force)
        logger.success("Merged official guidelines: written={} target={}", written, docs_path)
        if not force and written == 0:
            logger.info("All official guideline doc_ids already exist. Use --force to replace them.")

    if failures:
        logger.warning("Completed with {} failure(s):", len(failures))
        for failure in failures:
            logger.warning("  {}", failure)


if __name__ == "__main__":
    app()
