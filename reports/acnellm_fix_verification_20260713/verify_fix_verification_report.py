from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote


REPORT = Path(__file__).with_name("acnellm_fix_verification_report_20260713.html")
REPORT_TEXT = REPORT.read_text(encoding="utf-8")


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.external_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        element_id = attr.get("id")
        if element_id:
            self.ids.add(element_id)
        href = attr.get("href")
        if tag == "a" and href:
            self.hrefs.append(href)
        if tag in {"script", "link", "img", "iframe"}:
            ref = attr.get("src") or href
            if ref and ref.startswith(("http://", "https://", "//")):
                self.external_assets.append(ref)


def table_body(table_id: str) -> str:
    match = re.search(
        rf'<table id=["\']{re.escape(table_id)}["\']>(.*?)</table>',
        REPORT_TEXT,
        flags=re.DOTALL,
    )
    return match.group(1) if match else ""


parser = ReportParser()
parser.feed(REPORT_TEXT)

required_sections = {
    "summary", "fixes", "architecture", "regression", "incident", "sessions",
    "jitter", "retry", "normalizer", "retrieval", "scores", "failures",
    "priority", "verdict", "evidence",
}
missing_sections = sorted(required_sections - parser.ids)
broken_fragments = sorted(
    {href[1:] for href in parser.hrefs if href.startswith("#") and href[1:] not in parser.ids}
)
missing_local: list[str] = []
for href in parser.hrefs:
    if href.startswith(("#", "http://", "https://", "mailto:")):
        continue
    target = (REPORT.parent / unquote(href)).resolve()
    if not target.exists():
        missing_local.append(href)

fix_table = table_body("fix-table")
session_table = table_body("session-table")
failure_table = table_body("failure-table")
standard_ids = {f"s{i:02d}" for i in range(1, 13)}
jitter_ids = {f"j{i:02d}" for i in range(1, 5)}

checks = {
    "utf8_title": "AcneLLM Fix Verification" in REPORT_TEXT,
    "required_sections": not missing_sections,
    "fragment_links": not broken_fragments,
    "local_links": not missing_local,
    "self_contained": not parser.external_assets,
    "fix_rows_12": len(re.findall(r"<tr data-status=", fix_table)) == 12,
    "session_rows_12": len(re.findall(r"<tr data-status=", session_table)) == 12,
    "session_details_12": standard_ids <= parser.ids,
    "jitter_details_4": jitter_ids <= parser.ids,
    "failure_rows_9": len(re.findall(r"<tr data-severity=", failure_table)) == 9,
    "filter_script": "querySelectorAll('.filters')" in REPORT_TEXT,
    "responsive_css": "@media(max-width:680px)" in REPORT_TEXT,
    "headline_counts": all(
        phrase in REPORT_TEXT
        for phrase in (
            "2/12 issue được fix ở lõi",
            "8/12 chưa fix",
            "455 passed, 3 failed, 1 xfailed",
            "19 streaming failures",
        )
    ),
    "verdict_answers": all(
        phrase in REPORT_TEXT
        for phrase in (
            "Repo đã fix các lỗi report chưa?",
            "RAG guideline tốt hơn chưa?",
            "Model là bottleneck chính?",
            "Strong prototype, chưa gần production.",
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
