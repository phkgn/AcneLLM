"""PDF guideline -> .txt readable, san sang cho VietnameseChunker.

Chay:  python pdf_to_text.py --classify   # xep PDF moi vao text/ hoac scan/
       python pdf_to_text.py             # trich xuat, bo qua .txt da co
       python pdf_to_text.py --force     # ghi de .txt da co
Can:   pip install docling
       PDF trong scan/ can them: tesseract + vie.traineddata

Cau truc thu muc -- THU MUC QUYET DINH ENGINE:
  <lang>_docs/text/*.pdf   co text layer -> doc thang, nhanh
  <lang>_docs/scan/*.pdf   anh chup, 0 ky tu -> OCR Tesseract lang=vie, rat cham
  <lang>_docs/txt/*.txt    dau ra chung cua ca hai nhom

Docling (mo hinh thi giac) thay cho pdfplumber (heuristic duong ke). Ly do doi:
  - pdfplumber nhan bua van xuoi thanh bang: CanTho 212/235 "hang bang" chi 1 cot,
    70% file bi xe thanh cau roi.
  - pdfplumber KHONG bao gio thay bang khong co duong ke: Hue co 6 bang, tim ra 0.
    Doi sang text-strategy thi cat giua tu ("Truo|ng Dai hoc") - te hon.
  - Docling tu bo header/footer lap, tu xu ly thu tu doc layout 2 cot, tu nhan heading.
    Ba viec nay truoc day la 70 dong heuristic tu viet.

Dinh dang dau ra GIU NGUYEN hop dong cu (xem render_table + _check):
mot HANG bang = MOT cau, khong co dau cham ben trong, de chunker khong cat ngang hang.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

OUT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(OUT, "manifest.json")

sys.path.insert(0, os.path.join(os.path.dirname(OUT), "src"))
from acne_llm.rag.cleaning import PDF_ARTIFACTS  # noqa: E402

# TESSDATA_PREFIX phai co trong os.environ vi Docling goi `tesseract` nhu TIEN TRINH
# CON -- no thua huong moi truong cua Python, khong doc .env cua du an.
# Dat thang o day de khoi phu thuoc bien moi truong cua PowerShell (rat de mat khi
# doi cua so, va mat thi 474 trang scan deu fail lang le).
TESSDATA_DIR = os.path.join(os.path.dirname(OUT), "tessdata")
if os.path.exists(os.path.join(TESSDATA_DIR, "vie.traineddata")):
    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR


def render_table(table: list[list], idx: int) -> str:
    """Bang -> cac hang, moi hang la MOT cau tu chua.

    Khong de dau cham ben trong hang: chunker tach cau theo [.!?] nen dau cham
    giua hang se lam hang bi xe doi giua 2 chunk.
    """
    rows = [[(c or "").strip() for c in r] for r in table if any(r)]
    if len(rows) < 2:
        return ""
    header = [re.sub(r"\s+", " ", h) or f"cot{i+1}" for i, h in enumerate(rows[0])]
    out = []
    for r in rows[1:]:
        parts = []
        for i, cell in enumerate(r):
            cell = re.sub(r"\s+", " ", cell).strip(" .;")
            if not cell:
                continue
            # Dau cham/hoi/than trong o -> cham phay, giu hang lien mach (1 hang = 1 cau).
            # CHI chua dung dau cham NAM GIUA hai chu so: "1.5.8", "0.1%".
            # Ban cu dung (?<!\d)\.(?!\d) nen "CHUONG 1. BENH DA" thoat luoi (dau cham
            # dung sau chu so) -> 193 hang bi chunker xe doi. Dau ? trong o cung the.
            cell = re.sub(r"(?<!\d)\.|\.(?!\d)|[!?]", ";", cell)
            parts.append(f"{header[i] if i < len(header) else ''}: {cell}".strip(": "))
        if parts:
            out.append(f"[Bang {idx}] " + " | ".join(parts) + ".")
    return "\n".join(out)


_SEP_ROW = re.compile(r"^[\s|:\-]+$")


def md_tables_to_rows(md: str) -> str:
    """Doi bang Markdown cua Docling -> dinh dang [Bang N], giu nguyen phan con lai.

    Moi khoi dong lien tiep bat dau bang '|' la mot bang. Dong phan cach
    '|---|---|' bi bo. Bang < 2 hang that bi render_table tra ve rong -> bien mat,
    dung y do: mot hang khong phai bang.
    """
    out: list[str] = []
    buf: list[str] = []
    idx = 0

    def flush() -> None:
        nonlocal idx, buf
        if not buf:
            return
        rows = [
            [c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in buf
            if not _SEP_ROW.match(ln)
        ]
        idx += 1
        rendered = render_table(rows, idx)
        if rendered:
            out.append(rendered)
        buf = []

    for line in md.splitlines():
        if line.lstrip().startswith("|"):
            buf.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


# PDF scan khong co text layer -> Docling phai OCR. RapidOCR dung model PP-OCR
# (Trung/Anh), khong co tieng Viet, nen no doan bay tu bang chu da ngon ngu:
# "sẩn mụn mủ" -> "sân mųn mú" (ų Litva), "sẹo" -> "sęo" (ę Ba Lan).
# Nhung chu nay KHONG BAO GIO xuat hien trong van ban tieng Viet that.
#
# Do tren 14 file: file lanh 0.00-0.33 / 1000 tu, file scan hong 10.20 va 36.96.
# Cach nhau 30 lan nen nguong 2.0 an toan ca hai phia.
# (Da thu do "ti le tu co dau" nhung no chan nham file nhieu tieng Anh -- CTUMP
#  53.6% trong khi file hong 43.1%, khoang cach qua hep.)
MAX_OCR_NOISE = 2.0

_FOREIGN = set("ąęųğůāǎūİıēěžőțîûåÅŁłśźżčřďňŕöäüßñçš") - set(
    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
)


def ocr_noise_ratio(text: str) -> float:
    """So chu Latin co dau NGOAI bang chu Viet, tren 1000 tu."""
    words = re.findall(r"[^\W\d_]{2,}", text)
    if not words:
        return 0.0
    return sum(1 for c in text if c in _FOREIGN) / len(words) * 1000


def tesseract_has_vie() -> tuple[bool, str]:
    """Kiem tra TRUOC khi dung scan/: thieu vie thi 474 trang deu fail lang le."""
    import subprocess
    try:
        r = subprocess.run(["tesseract", "--list-langs"],
                           capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return False, "khong tim thay lenh 'tesseract' trong PATH"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    out = (r.stdout or "") + (r.stderr or "")
    if "vie" not in out.split():
        return False, ("tesseract chay duoc nhung thieu 'vie'. "
                       + (out.strip().splitlines()[0] if out.strip() else ""))
    # 'tsv' la FILE CONFIG trong tessdata/configs/, khong phai tham so dong lenh.
    # Thieu no thi tesseract van chay va xuat TEXT THUONG -> Docling doc bang
    # pd.read_csv roi truy cap cot 'text' -> KeyError: 'text' o giua chung.
    # --list-langs khong bat duoc loi nay nen phai kiem rieng.
    tdir = os.environ.get("TESSDATA_PREFIX")
    if tdir and not os.path.exists(os.path.join(tdir, "configs", "tsv")):
        return False, (f"thieu {os.path.join(tdir, 'configs', 'tsv')}. Chep 2 thu muc "
                       f"'configs' va 'tessconfigs' tu tessdata cua ban cai Tesseract sang {tdir}")
    return True, ""


_CONVERTERS: dict[bool, object] = {}


def _converter(ocr_vie: bool = False):
    """Khoi tao mot lan moi che do: lan dau tai model layout + tablestructure.

    ocr_vie=True -> doi engine OCR sang Tesseract lang=vie. Chi can cho PDF SCAN:
    RapidOCR mac dinh dung PP-OCR (Trung/Anh), khong co tieng Viet, nen no doan
    bay va an het dau. PDF co text layer khong dung OCR nen khong anh huong.
    """
    if ocr_vie not in _CONVERTERS:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        if not ocr_vie:
            _CONVERTERS[ocr_vie] = DocumentConverter()
        else:
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions, TesseractCliOcrOptions,
            )
            opts = PdfPipelineOptions()
            opts.do_ocr = True
            opts.ocr_options = TesseractCliOcrOptions(lang=["vie"], force_full_page_ocr=True)
            _CONVERTERS[ocr_vie] = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
            )
    return _CONVERTERS[ocr_vie]


def extract(path: str, ocr_vie: bool = False) -> str:
    md = _converter(ocr_vie).convert(path).document.export_to_markdown()
    # Docling escape HTML: "p<0,0001" -> "p&lt;0,0001".
    md = html.unescape(md)
    # Docling doc text layer nen loi font PDF doi cu van con: u+01A3 thay cho "u",
    # glyph Symbol/Wingdings trong vung Private Use. Xem PDF_ARTIFACTS.
    md = md.translate(PDF_ARTIFACTS)
    text = md_tables_to_rows(md)
    # Bo dau '#' cua heading: chunker tach doan theo dong trong, khong doc Markdown.
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def classify() -> None:
    """Xep PDF chua phan loai vao text/ hoac scan/, cap nhat manifest.

    Tieu chi: 5 trang dau khong co ky tu nao -> anh chup, khong co gi de doc,
    bat buoc OCR. Chay lai duoc, file da xep dung cho thi bo qua.
    """
    import shutil
    import pdfplumber

    docs = json.load(open(MANIFEST, encoding="utf-8"))
    changed = 0
    for d in docs:
        rel = d["file"]
        src = os.path.join(OUT, rel)
        if not rel.lower().endswith(".pdf") or not os.path.exists(src):
            continue
        if os.path.basename(os.path.dirname(src)) in ("text", "scan"):
            continue
        with pdfplumber.open(src) as pdf:
            chars = sum(len(pg.chars) for pg in pdf.pages[:5])
        kind = "scan" if chars == 0 else "text"
        tdir = os.path.join(os.path.dirname(src), kind)
        os.makedirs(tdir, exist_ok=True)
        shutil.move(src, os.path.join(tdir, os.path.basename(src)))
        parent = os.path.basename(os.path.dirname(src))
        d["file"] = f"{parent}/{kind}/{os.path.basename(src)}"
        print(f"{kind.upper():<5} {rel} -> {d['file']}")
        changed += 1
    if changed:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"-> {changed} file da xep, manifest {'da cap nhat' if changed else 'khong doi'}")


def main(force: bool = False) -> None:
    docs = json.load(open(MANIFEST, encoding="utf-8"))
    # text/ truoc, scan/ sau: nhom text nhanh va chac an: neu OCR chet giua chung
    # thi 22 file kia da xong, chay lai chi ton phan scan.
    docs.sort(key=lambda d: "/scan/" in d["file"].replace("\\", "/"))
    ok = skip = fail = 0
    vie_ok: bool | None = None      # kiem tra 1 lan, ngay truoc file scan/ dau tien
    vie_err = ""
    for d in docs:
        src = os.path.join(OUT, d["file"])
        if not src.lower().endswith(".pdf"):
            print(f"[bo qua] {d['file']} (khong phai pdf)"); skip += 1; continue
        # PDF nam o <lang>_docs/{text,scan}/, ket qua ra <lang>_docs/txt/ (chung).
        # Thu muc quyet dinh engine: scan/ = anh chup, bat buoc OCR tieng Viet.
        kind = os.path.basename(os.path.dirname(src))
        if kind not in ("text", "scan"):
            print(f"[CHUA XEP] {d['file']} -> phai nam trong text/ hoac scan/. "
                  f"Chay: python pdf_to_text.py --classify"); fail += 1; continue
        tdir = os.path.join(os.path.dirname(os.path.dirname(src)), "txt")
        os.makedirs(tdir, exist_ok=True)
        dst = os.path.join(tdir, os.path.splitext(os.path.basename(src))[0] + ".txt")
        if os.path.exists(dst) and not force:
            print(f"[da co] {os.path.basename(dst)}"); skip += 1; continue
        if kind == "scan":
            if vie_ok is None:
                vie_ok, vie_err = tesseract_has_vie()
            if not vie_ok:
                print(f"[THIEU OCR] {d['file']} -> {vie_err}\n"
                      f"            Sua: $env:TESSDATA_PREFIX = "
                      f'"E:\\project\\AcneLLM\\tessdata"  (dat trong CUNG cua so nay)')
                fail += 1
                continue
        try:
            text = extract(src, ocr_vie=(kind == "scan"))
            if len(text) < 500:
                print(f"[TRONG] {d['file']} -> {len(text)} ky tu, nhieu kha nang PDF scan, can OCR")
                fail += 1
                continue
            noise = ocr_noise_ratio(text)
            if noise > MAX_OCR_NOISE:
                print(f"[OCR HONG] {d['file']} -> {noise:.1f} chu ngoai lai/1000 tu "
                      f"(nguong {MAX_OCR_NOISE}). PDF scan, OCR khong co model tieng Viet. "
                      f"KHONG ghi file; can OCR lai bang Tesseract lang=vie.")
                fail += 1
                continue
            open(dst, "w", encoding="utf-8").write(text)
            paras = len([p for p in text.split("\n\n") if p.strip()])
            rows = text.count("[Bang ")
            print(f"[ok] {os.path.basename(dst)}  {len(text)} ky tu, {paras} doan, {rows} hang bang")
            ok += 1
        except Exception as e:
            print(f"[LOI] {d['file']}: {type(e).__name__}: {e}"); fail += 1
    print(f"\nXong: {ok} file text moi, {skip} bo qua, {fail} that bai.")


def _check() -> None:
    t = render_table([["Muc do", "Dieu tri", "Nhuoc diem"],
                      ["Any severity", "adapalene 0.1% + BPO. Boi toi.", "Xem muc 1.5.8"]], 1)
    # Bat buoc: khong co [.!?] + khoang trang o GIUA hang. Day dung la bieu thuc
    # VietnameseChunker tach cau -- co no thi hang bi xe doi giua 2 chunk.
    assert not re.search(r"[.!?]\s", t) and t.endswith("."), t
    assert "Muc do: Any severity" in t and "Nhuoc diem:" in t, t
    assert "1.5.8" in t and "0.1%" in t, f"so co dau cham phai giu nguyen: {t!r}"
    # So thu tu ("CHUONG 1. BENH...") va dau ? cung phai bi trung hoa, khong thi
    # chunker xe hang lam doi. Day la 260 hang bi loi o lan chay dau.
    t2 = render_table([["STT", "Ten"], ["CHƯƠNG 1. BỆNH DA", "Co dung khong? Co."]], 2)
    assert not re.search(r"[.!?]\s", t2[:-1]), t2
    assert "CHƯƠNG 1; BỆNH DA" in t2, t2

    # Parser Markdown: bang thanh [Bang N], van xuoi hai ben giu nguyen thu tu.
    md = ("Nhan xet truoc bang\n\n"
          "| Muc do | Dieu tri |\n"
          "| --- | --- |\n"
          "| Nang | isotretinoin 0.5 mg/kg. Uong sau an. |\n\n"
          "Nhan xet sau bang")
    r = md_tables_to_rows(md)
    assert r.startswith("Nhan xet truoc bang"), r
    assert r.rstrip().endswith("Nhan xet sau bang"), r
    assert "[Bang 1] Muc do: Nang | Dieu tri: isotretinoin 0.5 mg/kg; Uong sau an." in r, r
    assert not re.search(r"^\s*\|", r, re.M), f"con sot dong Markdown table: {r!r}"
    # Bang 1 hang (khong co hang du lieu) bi loai -- do la van xuoi bi nhan bua.
    assert md_tables_to_rows("| chi mot hang |\n| --- |").strip() == "", "bang 1 hang phai bien mat"
    # Loi font PDF doi cu phai duoc sua truoc khi ghi ra .txt
    assert "ngƣời".translate(PDF_ARTIFACTS) == "người"

    # Guard OCR: mau that tu mot ban scan bi RapidOCR (khong co model tieng Viet)
    # doc hong, va ban sua tay. Chu Ba Lan/Litva la dau hieu nhan dang.
    bad = "Vài sân mųn mú, Cuc nang sęo, BPO hoąc Ret, Thuőc thoa phi hop, ğ ů ā"
    good = "Vài sẩn mụn mủ, Cục nang sẹo, BPO hoặc Ret, Thuốc thoa phối hợp"
    assert ocr_noise_ratio(bad) > MAX_OCR_NOISE, ocr_noise_ratio(bad)
    assert ocr_noise_ratio(good) == 0, ocr_noise_ratio(good)
    # Van ban tieng Viet lanh co nhieu tieng Anh van phai qua (ca CTUMP 0.00).
    assert ocr_noise_ratio("Acne vulgaris treatment với isotretinoin 0.5 mg/kg") == 0
    print("check ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ghi de .txt da co")
    ap.add_argument("--classify", action="store_true",
                    help="chi xep PDF moi vao text/ hoac scan/ roi thoat")
    a = ap.parse_args()
    _check()
    if a.classify:
        classify()
    else:
        main(force=a.force)
