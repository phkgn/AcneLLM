"""Turn completed deep-audit Q sections into the three-basket remediation ledger."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


Q_RE = re.compile(r"^\*\*Q-(\d+)(.*)$")
REF_RE = re.compile(r"`?([A-Za-z0-9_./-]+\.(?:py|md|j2|yaml|yml|json|tsx?|ps1|sh))(?::|:~)(\d+)")


def sections(path: Path) -> list[tuple[int, str, str, int]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    starts: list[tuple[int, int, int, str, str]] = []
    for index, line in enumerate(lines):
        match = Q_RE.match(line)
        if match:
            number = int(match.group(1))
            rest = match.group(2)
            title_parts: list[str] = []
            inline_body = ""
            end_index = index
            while True:
                if "**" in rest:
                    before, after = rest.split("**", 1)
                    title_parts.append(before)
                    inline_body = after.strip()
                    break
                title_parts.append(rest)
                end_index += 1
                if end_index >= len(lines):
                    break
                rest = lines[end_index]
            title = " ".join(part.strip(" —.*") for part in title_parts if part.strip(" —.*")).strip()
            starts.append((index, end_index, number, title, inline_body))
    out = []
    for pos, (index, title_end, number, title, inline_body) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        body_lines = ([inline_body] if inline_body else []) + lines[title_end + 1:end]
        while body_lines and (not body_lines[-1].strip() or body_lines[-1].startswith("---") or body_lines[-1].startswith("## BƯỚC")):
            body_lines.pop()
        out.append((number, title, "\n".join(body_lines).strip(), index + 1))
    return out


def disposition(title: str, body: str) -> str:
    text = title + "\n" + body
    for line in body.splitlines():
        if line.strip().startswith("→"):
            return line.strip().lstrip("→ ")
    for marker in ("Đề xuất:", "Sửa:", "Cách vá rẻ nhất:", "Cần quyết:"):
        if marker in text:
            tail = text.split(marker, 1)[1].strip().splitlines()[0]
            return tail
    if "không có caller" in text.lower() or "0 caller" in text.lower() or "code chết" in text.lower():
        return "Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng."
    if "docstring" in text.lower() or "comment" in text.lower() or "lời khai" in text.lower():
        return "Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch."
    if "cần đo" in text.lower() or "đáng đo" in text.lower() or "nên kiểm" in text.lower():
        return "Đo/kiểm bằng artifact được nêu trước; chỉ sửa logic nếu phép đo xác nhận tác động."
    return "Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu."


def bucket(title: str, body: str) -> str:
    text = (title + "\n" + body).lower()
    doc_tokens = ("readme", "docs/", ".md", "báo cáo", "khoá luận", "tài liệu")
    comment_tokens = ("docstring", "comment", "lời khai", "banner", "log message")
    if any(token in text for token in doc_tokens) and not any(token in text for token in ("regex", "schema", "runtime", "raise", "return")):
        return "A"
    if any(token in text for token in comment_tokens) and any(token in text for token in ("sai", "lệch", "không tồn tại", "nói", "mô tả", "trỏ")):
        return "B"
    return "C"


def resolved(module: str, number: int, title: str, body: str) -> bool:
    text = title + "\n" + body
    if "ĐÍNH CHÍNH" in text or "ĐÃ TRẢ LỜI — không phải lỗi" in text:
        return True
    return (module, number) in {("src.rag", 8)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_dir", type=Path)
    args = parser.parse_args()
    audit = args.audit_dir.resolve()
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    closed: list[str] = []
    for finding in sorted((audit / "FINDINGS").glob("*.md")):
        module = finding.stem
        for number, title, body, finding_line in sections(finding):
            qid = f"{module}:Q-{number:02d}"
            if resolved(module, number, title, body):
                closed.append(f"- `{qid}` — {title}")
                continue
            basket = bucket(title, body)
            refs = [f"{name}:{line}" for name, line in REF_RE.findall(title + "\n" + body)]
            explicit = "→" in body or "ĐÃ SỬA" in title or "ĐÃ TRẢ LỜI" in title
            grouped[basket].append({
                "qid": qid, "module": module, "title": title, "body": body,
                "finding": f".audit/FINDINGS/{finding.name}:{finding_line}",
                "refs": list(dict.fromkeys(refs)), "desired": disposition(title, body),
                "silent": not explicit,
            })
    lines = [
        "# TODO — truth-of-architecture remediation", "",
        "Nguồn duy nhất: FINDINGS đã hoàn tất. File này không apply thay đổi.",
        "⚠ = mặc định audit được dùng vì user không phản đối câu hỏi; phải review trước khi apply.",
        "", "## RỔ A — sửa `.md` và doc", "",
    ]
    risk = {
        "A": "Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.",
        "B": "Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.",
        "C": "Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.",
    }
    labels = {"A": "RỔ A — sửa `.md` và doc", "B": "RỔ B — sửa comment/docstring trong code", "C": "RỔ C — sửa code"}
    for basket in ("A", "B", "C"):
        if basket != "A":
            lines.extend(["", f"## {labels[basket]}", ""])
        by_module: dict[str, list[dict[str, object]]] = defaultdict(list)
        for item in grouped[basket]:
            by_module[str(item["module"])].append(item)
        for module, items in sorted(by_module.items()):
            lines.extend([f"### `{module}`", ""])
            for item in items:
                warning = "⚠ " if item["silent"] else ""
                body = str(item["body"]) or str(item["title"])
                basis = ", ".join(f"`{ref}`" for ref in item["refs"]) if item["refs"] else f"`{item['finding']}`"
                lines.extend([
                    f"{warning}[{basket}] `{item['qid']}` · {module}",
                    f"  hiện tại: {item['title']}",
                    "",
                    *["  " + line for line in body.splitlines()],
                    "",
                    f"  phải thành: {item['desired']}",
                    f"  căn cứ: {basis}",
                    f"  rủi ro nếu sửa sai: {risk[basket]}",
                    "",
                ])
    lines.extend(["## Q đã đóng/đính chính — không đưa vào patch", "", *closed, "", "## Doc mồ côi", "", "- `src/acne_llm/utils/text_cleaning.py` tự mô tả cleaning nhưng 0 caller và cũ hơn `src/acne_llm/rag/cleaning.py`: đề xuất xóa code ở Rổ C và xóa/sửa mọi doc trỏ tới nó.", "- Các report/evaluation `.md` mô tả schema/run cũ phải đối chiếu fingerprint hiện tại; report không có dataset/question fingerprint nên được gắn historical, không dùng làm runtime truth.", "- `src/acne_llm/schemas/kb.py` tự mô tả toàn file là KB trong khi chứa cả schema fine-tune: viết lại module docstring hoặc tách miền.", "", "## Hành vi quan trọng chưa được mô tả", "", "- Audit DB fallback sang temp directory khi path chính không mở được.", "- Rebuild KB không tự invalidate retrieval cache.", "- Unified intake production chỉ populate một phần clinical schema; nhiều field legacy luôn rỗng.", "- SSE runtime có CJK normalization/safety suffix/persistence mà non-streaming eval path không có.", "- `RetrievedChunk.score` có nhiều scale theo provenance; metadata `source_type` có thể được suy ra và mutate lúc chạy.", "- Semantic-router/RAG/reranker degrade độc lập; `rag_ready` không đồng nghĩa reranker hoặc semantic router ready.", "", "## Patch artifacts", "", "- `patches/A-docs.patch`", "- `patches/B-comments.patch`", "- `patches/C-code.patch`", "", "Ba patch độc lập và chưa apply. Rổ C không được commit chung A/B.", ""])
    (audit / "todo.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print({basket: len(items) for basket, items in grouped.items()}, "closed", len(closed))


if __name__ == "__main__":
    main()
