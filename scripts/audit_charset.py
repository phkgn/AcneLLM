"""Liệt kê ký tự KHÔNG thuộc bảng chữ tiếng Việt trong text của KB.

    python scripts/audit_charset.py                          # chunks.jsonl
    python scripts/audit_charset.py data/raw/documents.jsonl
    python scripts/audit_charset.py --examples               # kèm ngữ cảnh
    python scripts/audit_charset.py --self-test

Đọc .jsonl (lấy field --field, mặc định "text") hoặc file text thường.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 89 chữ cái tiếng Việt (12 nguyên âm × dấu + phụ âm). f/j/w/z không thuộc bảng
# chữ Việt nhưng có mặt hợp lệ trong tên thuốc, đơn vị đo → cho qua.
_VI = (
    "aàáảãạăằắẳẵặâầấẩẫậbcdđeèéẻẽẹêềếểễệghiìíỉĩịklmnoòóỏõọôồốổỗộơờớởỡợ"
    "pqrstuùúủũụưừứửữựvxyỳýỷỹỵ"
)
ALLOWED = set(_VI + _VI.upper() + "fjwzFJWZ" + "0123456789" + " \n\t\r")
ALLOWED |= set(".,;:!?()[]{}<>\"'`-/\\|@#$%^&*_+=~")

# Ký tự nhìn GIỐNG chữ Việt nhưng là chữ cái khác → hỏng âm thầm, không ai thấy.
SUSPECT = {
    "Ƣ": "Ƣ (OI) — phải là Ư U+01AF",
    "ƣ": "ƣ (oi) — phải là ư U+01B0",
    "ı": "ı (i không chấm) — phải là i",
    "ӏ": "ӏ (Cyrillic) — phải là l",
}
CYRILLIC_LOOKALIKE = set("аеорсухАЕОРСУХ")


def classify(ch: str) -> str:
    cp = ord(ch)
    if ch in SUSPECT:
        return "NHẦM CHỮ VIỆT: " + SUSPECT[ch]
    if 0xE000 <= cp <= 0xF8FF:
        return "PUA — glyph font riêng (Symbol/Wingdings), rác"
    if ch in CYRILLIC_LOOKALIKE:
        return "Cyrillic trông giống Latin"
    cat = unicodedata.category(ch)
    if cat.startswith("Z") or ch in "­​‌‍﻿":
        return "khoảng trắng / ký tự vô hình"
    if cat.startswith("P") or cat.startswith("S"):
        return "dấu câu / ký hiệu"
    return "chữ cái ngoại lai"


def iter_texts(path: Path, field: str):
    if path.suffix == ".jsonl":
        for i, line in enumerate(path.open(encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line).get(field) or ""
            except json.JSONDecodeError:
                continue
    else:
        yield 1, path.read_text(encoding="utf-8")


def scan_dir(folder: Path, field: str) -> None:
    """Một dòng mỗi file: đếm ký tự lạ + liệt kê riêng nhóm chắc chắn lỗi."""
    files = sorted(p for p in folder.rglob("*") if p.suffix in {".txt", ".md", ".jsonl"})
    if not files:
        sys.exit(f"Không có .txt/.md/.jsonl trong {folder}")

    print(f"Thư mục: {folder}   ({len(files)} file)\n")
    print(f"{'FILE':<52} {'LOẠI':>5} {'LẦN':>7}  LỖI CHẮC CHẮN")
    print("-" * 110)
    grand: Counter = Counter()
    dirty = 0
    for p in files:
        counts: Counter = Counter()
        for _, text in iter_texts(p, field):
            counts.update(c for c in text if c not in ALLOWED)
        grand.update(counts)
        bad = {c: n for c, n in counts.items()
               if classify(c).startswith(("NHẦM", "PUA", "Cyrillic"))}
        if bad:
            dirty += 1
        flag = " ".join(f"U+{ord(c):04X}×{n}" for c, n in
                        sorted(bad.items(), key=lambda kv: -kv[1])) or "—"
        print(f"{p.name[:52]:<52} {len(counts):>5} {sum(counts.values()):>7}  {flag}")

    print("-" * 110)
    print(f"{'TỔNG':<52} {len(grand):>5} {sum(grand.values()):>7}  "
          f"{dirty}/{len(files)} file có lỗi chắc chắn")
    print(f"\nChi tiết một file: python scripts/audit_charset.py "
          f"{folder.name}/<file> --examples")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "data/raw/chunks.jsonl"))
    ap.add_argument("--field", default="text")
    ap.add_argument("--examples", action="store_true", help="in ngữ cảnh mỗi ký tự")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        assert classify("ƣ").startswith("NHẦM"), "phải bắt được U+01A3"
        assert classify("").startswith("PUA"), "phải bắt được Private Use Area"
        assert "ư" in ALLOWED and "Ư" in ALLOWED, "ư/Ư hợp lệ phải được cho qua"
        assert "ƣ" not in ALLOWED, "ƣ (OI) không được coi là hợp lệ"
        print("self-test OK")
        return

    path = Path(args.path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        sys.exit(f"Không tìm thấy {path}")

    if path.is_dir():
        scan_dir(path, args.field)
        return

    counts: Counter = Counter()
    lines_hit: defaultdict[str, set] = defaultdict(set)
    example: dict[str, str] = {}
    n_units = 0

    for lineno, text in iter_texts(path, args.field):
        n_units += 1
        for pos, ch in enumerate(text):
            if ch in ALLOWED:
                continue
            counts[ch] += 1
            lines_hit[ch].add(lineno)
            if ch not in example:
                example[ch] = text[max(0, pos - 30):pos + 30].replace("\n", "⏎")

    print(f"File   : {path}")
    print(f"Đơn vị : {n_units}")
    print(f"Ký tự lạ: {len(counts)} loại, {sum(counts.values())} lần\n")

    if not counts:
        print("Sạch — không có ký tự nào ngoài bảng chữ tiếng Việt.")
        return

    print(f"{'SỐ LẦN':>8}  {'DÒNG':>6}  {'CP':<8} {'KÝ TỰ':<6} PHÂN LOẠI / TÊN UNICODE")
    print("-" * 100)
    for ch, n in counts.most_common():
        name = unicodedata.name(ch, "?")
        note = classify(ch)
        shown = repr(ch)[1:-1] if ch.isprintable() else repr(ch)[1:-1]
        print(f"{n:>8}  {len(lines_hit[ch]):>6}  U+{ord(ch):04X}  {shown:<6} {note}  [{name}]")
        if args.examples:
            print(f"{'':>18}… {example[ch]} …")

    bad = {ch: n for ch, n in counts.items() if classify(ch).startswith(("NHẦM", "PUA"))}
    if bad:
        total = sum(bad.values())
        print(f"\n⚠ {len(bad)} ký tự CHẮC CHẮN là lỗi ({total} lần): "
              + " ".join(f"U+{ord(c):04X}" for c in bad))
        print("  → sửa ở src/acne_llm/rag/cleaning.py (PDF_ARTIFACTS) rồi chunk lại.")


if __name__ == "__main__":
    main()
