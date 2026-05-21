"""PubMed E-utilities crawler — ~2000+ abstracts về acne."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

from ...schemas.kb import DocumentRaw, SourceMeta
from ...utils.hashing import doc_id_for

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedSource:
    name = "PubMed"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        d = cfg["discovery"]
        self.query = d["query"]
        self.retmax = int(d.get("retmax", 1000))
        self.batch = 100

    async def discover(self) -> list[str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(ESEARCH, params={
                "db": "pubmed", "term": self.query,
                "retmax": self.retmax, "retmode": "json",
            })
            r.raise_for_status()
            ids = r.json()["esearchresult"].get("idlist", [])
        logger.info(f"PubMed: discovered {len(ids)} PMIDs")
        return ids

    async def fetch_batch(self, pmids: list[str]) -> list[DocumentRaw]:
        if not pmids:
            return []
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(EFETCH, params={
                "db": "pubmed", "id": ",".join(pmids),
                "rettype": "abstract", "retmode": "xml",
            })
            r.raise_for_status()
        docs: list[DocumentRaw] = []
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as e:
            logger.warning(f"PubMed parse error: {e}")
            return []
        for art in root.findall(".//PubmedArticle"):
            try:
                pmid_el = art.find(".//PMID")
                title_el = art.find(".//ArticleTitle")
                abs_els = art.findall(".//Abstract/AbstractText")
                if pmid_el is None or title_el is None or not abs_els:
                    continue
                pmid = pmid_el.text
                title = "".join(title_el.itertext()).strip()
                abstract = "\n\n".join(
                    "".join(a.itertext()).strip() for a in abs_els if a.text or list(a)
                )
                if len(abstract) < 300:
                    continue
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                text = f"{title}\n\n{abstract}"
                docs.append(DocumentRaw(
                    doc_id=doc_id_for("pubmed", url),
                    url=url, title=title, text=text,
                    html_len=len(r.text), text_len=len(text),
                    source=SourceMeta(
                        domain="pubmed.ncbi.nlm.nih.gov", source_name="PubMed",
                        source_type="pubmed_review",
                        trust_level="high", language="en",
                        crawled_at=datetime.now(timezone.utc),
                    ),
                    categories=["pubmed", "research"],
                    tags=["abstract"],
                    quality_score=0.8,
                ))
            except Exception as e:
                logger.debug(f"pubmed article skip: {e}")
        return docs

    async def fetch_all(self, pmids: list[str]) -> list[DocumentRaw]:
        out: list[DocumentRaw] = []
        for i in range(0, len(pmids), self.batch):
            batch = pmids[i:i + self.batch]
            out.extend(await self.fetch_batch(batch))
            await asyncio.sleep(0.4)  # NCBI: 3 req/sec without API key
            logger.info(f"PubMed: fetched {len(out)}/{len(pmids)}")
        return out
