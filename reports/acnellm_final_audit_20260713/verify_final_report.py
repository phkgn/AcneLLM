from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote


REPORT = Path(__file__).with_name("acnellm_final_comprehensive_audit_20260713.html")
TEXT = REPORT.read_text(encoding="utf-8")


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.external_assets: list[str] = []
        self.session_cards = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if attr.get("id"):
            self.ids.add(attr["id"] or "")
        if tag == "a" and attr.get("href"):
            self.hrefs.append(attr["href"] or "")
        if tag == "details" and "session-card" in (attr.get("class") or ""):
            self.session_cards += 1
        if tag in {"script", "link", "img", "iframe"}:
            ref = attr.get("src") or attr.get("href")
            if ref and ref.startswith(("http://", "https://", "//")):
                self.external_assets.append(ref)


def table_body(table_id: str) -> str:
    match = re.search(
        rf'<table id=["\']{re.escape(table_id)}["\']>(.*?)</table>',
        TEXT,
        flags=re.DOTALL,
    )
    return match.group(1) if match else ""


parser = Parser()
parser.feed(TEXT)
required_sections = {
    "summary", "method", "architecture", "delta", "gates", "fixes", "sessions",
    "jitter", "retry", "raw", "normalizer", "retrieval", "persistence", "failures",
    "scores", "priority", "verdict", "evidence",
}
missing_sections = sorted(required_sections - parser.ids)
broken_fragments = sorted(
    {href[1:] for href in parser.hrefs if href.startswith("#") and href[1:] not in parser.ids}
)
missing_local = []
for href in parser.hrefs:
    if href.startswith(("#", "http://", "https://", "mailto:")):
        continue
    if not (REPORT.parent / unquote(href)).resolve().exists():
        missing_local.append(href)

expected_detail_ids = (
    {f"std-s{i:02d}" for i in range(1, 13)}
    | {f"jit-j{i:02d}" for i in range(1, 5)}
    | {f"retry-r{i:02d}" for i in range(1, 7)}
)

checks = {
    "utf8_title": "AcneLLM Final Comprehensive Audit" in TEXT,
    "required_sections": not missing_sections,
    "fragment_links": not broken_fragments,
    "local_links": not missing_local,
    "self_contained": not parser.external_assets,
    "fix_rows_12": len(re.findall(r"<tr data-status=", table_body("fix-table"))) == 12,
    "standard_rows_12": len(re.findall(r"<tr data-status=", table_body("session-table"))) == 12,
    "jitter_rows_4": len(re.findall(r"<tr data-status=", table_body("jitter-table"))) == 4,
    "retry_rows_6": len(re.findall(r"<tr data-status=", table_body("retry-table"))) == 6,
    "new_rows_4": len(re.findall(r"<tr data-severity=", table_body("new-table"))) == 4,
    "detail_cards_22": parser.session_cards == 22 and expected_detail_ids <= parser.ids,
    "filter_script": "querySelectorAll('.filters')" in TEXT,
    "responsive_css": "@media(max-width:680px)" in TEXT,
    "headline_counts": all(
        phrase in TEXT
        for phrase in (
            "3/12 reported issues fixed at core",
            "455 pass · 3 fail · 1 xfail",
            "1,201",
            "0 AAD/NICE final chunks",
            "Strong prototype, not close to production.",
        )
    ),
    "critical_evidence": all(
        phrase in TEXT
        for phrase in (
            "khử trùng kim",
            "request.is_disconnected",
            "--delete",
            "S03/T2 emits 1,201 token events",
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
