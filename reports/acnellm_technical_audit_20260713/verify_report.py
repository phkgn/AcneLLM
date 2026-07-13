from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote


REPORT = Path(__file__).with_name("acnellm_technical_audit_20260713.html")


class AuditHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.external_assets: list[str] = []
        self.session_details = 0
        self.matrix_rows = 0
        self.in_matrix_body = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if attr.get("id"):
            self.ids.add(attr["id"] or "")
        if tag == "a" and attr.get("href"):
            self.hrefs.append(attr["href"] or "")
        if tag in {"script", "link", "img"}:
            ref = attr.get("src") or attr.get("href")
            if ref and (ref.startswith("http://") or ref.startswith("https://")):
                self.external_assets.append(ref)
        if tag == "details" and "session-card" in (attr.get("class") or ""):
            self.session_details += 1
        if tag == "tbody" and self.get_starttag_text() and "matrix" in REPORT_TEXT[: REPORT_TEXT.find(self.get_starttag_text())]:
            # Matrix row count is also verified with a bounded source check below.
            pass


REPORT_TEXT = REPORT.read_text(encoding="utf-8")
parser = AuditHTMLParser()
parser.feed(REPORT_TEXT)

required_sections = {
    "executive", "architecture", "pipeline", "runtime", "model", "rag", "method",
    "matrix", "sessions", "scores", "failures", "works", "priority", "verdict", "evidence",
}
missing_sections = sorted(required_sections - parser.ids)
broken_fragments = sorted({href[1:] for href in parser.hrefs if href.startswith("#") and href[1:] not in parser.ids})
missing_local = []
for href in parser.hrefs:
    if href.startswith(("#", "http://", "https://", "mailto:")):
        continue
    target = (REPORT.parent / unquote(href)).resolve()
    if not target.exists():
        missing_local.append(href)

checks = {
    "utf8_title": "AcneLLM Technical Audit · 2026-07-13" in REPORT_TEXT,
    "required_sections": not missing_sections,
    "fragment_links": not broken_fragments,
    "local_links": not missing_local,
    "self_contained": not parser.external_assets,
    "session_cards_12": parser.session_details == 12,
    "session_matrix_rows_12": REPORT_TEXT.count('data-status="') == 12,
    "failure_rows_9": REPORT_TEXT.count('data-severity="') == 9,
    "filter_script": "querySelectorAll('.filters')" in REPORT_TEXT,
    "responsive_css": "@media(max-width:680px)" in REPORT_TEXT,
    "verdict_answers": all(
        phrase in REPORT_TEXT
        for phrase in (
            "Pipeline có hiệu quả không?", "NLP có đáng tin không?", "RAG retrieve đúng tài liệu không?",
            "acnellm-v2-q4 có phải bottleneck chính?", "Maturity?",
        )
    ),
}

for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
if missing_sections:
    print("missing_sections=", missing_sections)
if broken_fragments:
    print("broken_fragments=", broken_fragments)
if missing_local:
    print("missing_local=", missing_local)
if parser.external_assets:
    print("external_assets=", parser.external_assets)

if not all(checks.values()):
    raise SystemExit(1)
print(f"OK bytes={REPORT.stat().st_size} ids={len(parser.ids)} hrefs={len(parser.hrefs)}")
