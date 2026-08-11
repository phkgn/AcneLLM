"""In các mẫu đã sinh ra để ĐỌC BẰNG MẮT trước khi chạy full.

Gate offline chỉ bắt được cái đếm được: đủ ý, đủ dài, có gạch đầu dòng, có tài
liệu. Nó không bắt được "câu này đọc như máy", "ý này chung chung", "giọng sai".
Đó là việc của mắt người, và đó là lý do file này tồn tại.

    python -m datagen.roledatav2.show_samples                  # xem file smoke
    python -m datagen.roledatav2.show_samples --full           # in cả prompt user
    python -m datagen.roledatav2.show_samples --case B1_grounded_role
    python -m datagen.roledatav2.show_samples --path <file.jsonl> --out review.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

BAR = "═" * 78


def load(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"Không thấy file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if raw:
                yield json.loads(raw)


def turns(record: dict[str, Any], role: str) -> list[str]:
    return [
        str(message.get("content", ""))
        for message in record.get("messages", [])
        if message.get("role") == role
    ]


def strip_context(user_text: str) -> tuple[str, str]:
    """Tách khối tài liệu ra khỏi câu hỏi để đọc cho gọn."""
    marker = "Tin nhắn hiện tại:"
    if marker not in user_text:
        return "", user_text.strip()
    head, _, tail = user_text.partition(marker)
    return head.strip(), tail.strip()


def render(record: dict[str, Any], full: bool) -> list[str]:
    checks = (record.get("gate_results") or {}).get("checks") or {}
    users = turns(record, "user")
    answers = turns(record, "assistant")
    lines = [BAR, f"{record.get('id')}   [{record.get('sample_kind')}]"]

    meta = [
        f"độ dài: {[len(a) for a in answers]}",
        f"mục tiêu: {record.get('len_target')}",
        f"points: {len(record.get('points') or [])}",
        f"input_style: {record.get('input_style')}",
    ]
    if "grounding_language" in checks:
        judge = checks.get("grounding_judge")
        meta.append(
            f"nguồn: {checks['grounding_language']}"
            + (f" (judge {judge}/5)" if judge is not None else "")
        )
    lines.append("  " + " · ".join(meta))

    source_type = (record.get("generation_meta") or {}).get("source_type")
    if source_type:
        lines.append(f"  source_type: {source_type} · {record.get('synthetic_context_sources')}")

    context, question = strip_context(users[0] if users else "")
    if context:
        preview = context if full else (context[:400] + ("…" if len(context) > 400 else ""))
        lines += ["", "── TÀI LIỆU ĐƯA VÀO PROMPT " + "─" * 50, preview]
    for index, user_text in enumerate(users):
        _, text = strip_context(user_text)
        lines += ["", f"── NGƯỜI DÙNG {index + 1} " + "─" * 60, text]
        if index < len(answers):
            lines += ["", f"── TRỢ LÝ {index + 1} ({len(answers[index])} ký tự) " + "─" * 50, answers[index]]
    for point in record.get("points") or []:
        lines.append(f"   • point: {point}")
    return lines


def main(argv: list[str] | None = None) -> int:
    from .config import Config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, help="mặc định: output/roledata.smoke.jsonl")
    parser.add_argument("--case", help="chỉ in một case")
    parser.add_argument("--full", action="store_true", help="in trọn tài liệu, không cắt")
    parser.add_argument("--out", type=Path, help="ghi ra file thay vì in màn hình")
    args = parser.parse_args(argv)

    cfg = Config(api_key="offline")
    path = args.path or cfg.smoke_path
    records = [r for r in load(path) if not args.case or r.get("sample_kind") == args.case]
    if not records:
        raise SystemExit(f"Không có bản ghi nào trong {path}" + (f" cho case {args.case}" if args.case else ""))

    lines: list[str] = [f"Nguồn: {path}", f"Số bản ghi: {len(records)}"]
    for record in records:
        lines += render(record, args.full)

    # Bảng tổng kết ở cuối để soi nhanh phân bố.
    lines += ["", BAR, "TỔNG KẾT", f"{'case':26}{'lượt':>6}{'độ dài':>18}{'points':>8}{'nguồn':>8}"]
    for record in records:
        answers = turns(record, "assistant")
        checks = (record.get("gate_results") or {}).get("checks") or {}
        lines.append(
            f"{str(record.get('sample_kind')):26}{len(answers):>6}"
            f"{str([len(a) for a in answers]):>18}"
            f"{len(record.get('points') or []):>8}"
            f"{checks.get('grounding_language', '—'):>8}"
        )
    total = [len(a) for r in records for a in turns(r, "assistant")]
    if total:
        lines.append(f"\ntrung vị độ dài: {sorted(total)[len(total) // 2]} ký tự · ngắn nhất {min(total)} · dài nhất {max(total)}")

    text = "\n".join(lines)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Đã ghi {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
