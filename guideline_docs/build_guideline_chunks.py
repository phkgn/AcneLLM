"""Chunk rieng cho guideline PDF, roi nap vao data/raw/chunks.jsonl.

Vi sao tach khoi build_kb.py:
  Filter _is_acne_chunk() cua build_kb duoc thiet ke cho corpus web crawl —
  moi chunk phai tu chung minh bang keyword vi doc nguon co the la blog bat ky.
  Guideline thi nguoc lai: doc da duoc kiem duyet TRUOC khi vao day, nen bat
  tung chunk phai chua chu "acne" se vut mat dung phan can nhat (bang tac dung
  phu, muc "12-week review", tieu chi chuyen tuyen).
  Tach ra de khong phai noi filter chung -> corpus web 16k chunk khong bi dung.

Chay:  python build_guideline_chunks.py            # ghi vao chunks.jsonl
       python build_guideline_chunks.py --dry-run  # chi in thong ke
Can:   chay pdf_to_text.py truoc de co */txt/*.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from acne_llm.rag.chunker import VietnameseChunker  # noqa: E402

CHUNKS_PATH = ROOT / "data" / "raw" / "chunks.jsonl"
GUIDELINE_PATH = ROOT / "data" / "raw" / "chunks_guideline.jsonl"
MANIFEST = HERE / "manifest.json"
DOC_PREFIX = "guideline:"  # de xoa/ghi lai duoc, khong dung cham chunk web

# Doc phu TOAN BO benh da lieu -> van phai loc keyword tung chunk.
# Doc con lai chuyen ve mun -> bo qua buoc do.
GENERAL_DERM = {"BYT-Da-lieu-2015", "AnGiang-phac-do-da-lieu", "Quyết-định-4416-QĐ-BYT"}

# source_type dieu khien boost khi rerank (_SOURCE_TYPE_BOOST trong retriever.py)
# va bo loc cua safety pass (thai ky / thuoc ke don).
SOURCE_TYPE = {
    "NICE-NG198": "nice_guideline",
    "NICE-NG198-referral": "nice_guideline",
    "NICE-primary-care": "nice_guideline",
    "AAD-2024-supplement": "aad_guideline",
}
# Khuyen cao / phac do / dong thuan chinh thuc, khong phai NICE-AAD.
# Phan biet voi nghien cuu goc (AAFP, Corcoran, cac bai tap chi VN) -> pubmed_review.
_TEXTBOOK = ("EuroGuiDerm", "EDF-S3", "BYT-Da-lieu", "AnGiang", "Quyết-định",
             "China-2019", "Singapore-DSS", "PRACT-India", "Hayashi",
             "CMAJ-2016-canada",   # guideline mun cua Canada
             "BMJ-NICE-summary",   # tom tat khuyen cao NICE NG198
             "dong-thuan")         # VJDV: dong thuan chuyen gia


def source_type_of(name: str) -> str:
    if name in SOURCE_TYPE:
        return SOURCE_TYPE[name]
    if any(k in name for k in _TEXTBOOK):
        return "clinical_textbook"
    # Con lai la bai bao tap chi binh duyet (VJDV, VMJ, CTUMP, 108, AAFP, CMAJ...).
    # "pubmed_review" la bucket sat nhat trong SourceType hien co.
    return "pubmed_review"


# -- Chan rac dac thu PDF (build_kb khong co, vi web khong co muc luc) --------
_TOC = re.compile(r"\.{4,}\s*\d+")                        # "3.1 Dac diem ....... 22"
_REFS = re.compile(r"(et al\.|\d{4};\s?\d+\(|\bdoi:|\bpp?\.\s?\d+[-–]\d+)")


def is_junk(text: str) -> str | None:
    if len(_TOC.findall(text)) >= 2:
        return "muc luc"
    if len(_REFS.findall(text)) >= 3:
        return "tai lieu tham khao"
    rows = [l for l in text.splitlines() if l.startswith("[Bang")]
    if rows and sum(l.count("|") for l in rows) / len(rows) < 1:
        return "hang bang rong"
    return None


def load_gates():
    """Muon lai gate 1-4 + off-topic tu build_kb.py, khong copy-paste.

    Doc source va exec dung khoi filter -- import ca module se keo theo
    chromadb/embedder khong can thiet o day.
    """
    src = (ROOT / "scripts" / "build_kb.py").read_text(encoding="utf-8").splitlines()
    i = next(k for k, l in enumerate(src) if l.startswith("# -- Chunk quality filters"))
    j = next(k for k, l in enumerate(src) if l.startswith("def step_chunk"))
    ns: dict = {"re": re, "Path": Path, "ROOT": ROOT}
    exec("\n".join(src[i:j]), ns)
    return ns


# Tin hieu acne MANH — chi dung cho GENERAL_DERM (sach da lieu toan khoa).
#
# _ACNE_SIGNALS_VI cua build_kb.py co ca "viem da", "mu", "da lieu", "nang long".
# Voi corpus web thi du, vi doc nguon da la trang ve mun. Nhung trong sach 474
# trang ve MOI benh da lieu, nhung tu do khop ca chuong thuy dau, choc, zona:
# 40 chunk ngoai pham vi lot qua chi vi co chu "viem da" (24) hoac "mu" (8).
# O day bat buoc phai co tu/thuoc DAC HIEU cho trung ca.
_STRONG_ACNE_VI = re.compile(
    r"trứng cá|mụn(?!\s*(?:nước|cóc|rộp|thịt|cơm|nhọt))|nhân mụn|cồi mụn|"
    r"sẹo mụn|sẹo rỗ|sẹo lõm|comedone|comedo|"
    r"isotretinoin|adapalene|tretinoin|benzoyl|tazarotene|azelaic|spironolacton",
    re.I,
)
_STRONG_ACNE_EN = re.compile(
    r"acne|comedone|comedo|isotretinoin|adapalene|tretinoin|benzoyl|"
    r"tazarotene|azelaic|spironolactone",
    re.I,
)
# Benh NHIN GIONG mun -> can de PHAN BIET, khong phai de dieu tri.
# hard_cases_test co 9 mau va safety_test co 3 mau ve nhom nay, tat ca deu gan
# knowledge/clarify/advise, KHONG mau nao gan reject; expected_behavior doi
# "phan biet mun voi viem da/kich ung", "khong phai moi ton thuong deu la mun".
# Khong co nhom nay trong KB thi model khong co gi de dua vao ma noi "day co the
# khong phai mun". CO Y khong gom zona/thuy dau/herpes/choc/ghe/vay nen/ung thu:
# chung khong bi nham voi trung ca va nam ngoai pham vi tra loi.
_LOOKALIKE = re.compile(
    r"trứng cá đỏ|rosacea|"
    r"viêm da quanh miệng|perioral dermatitis|"
    r"viêm nang lông|folliculitis|malassezia|pityrosporum|"
    r"dày sừng nang lông|keratosis pilaris|"
    r"viêm da tiết bã|seborrh|"
    r"viêm da tiếp xúc|contact dermatitis|kích ứng mỹ phẩm|"
    r"mụn thịt|milia|"
    r"trứng cá do thuốc|acneiform|trứng cá nghề nghiệp",
    re.I,
)
# CO Y bo doxycyclin/minocyclin/clindamycin: chung tri cho, viem nang long, viem
# mo te bao... nen keo 30 chunk nhiem khuan da vao (bang lieu Cephalexin, axit
# fucidic). Bang lieu khang sinh cho trung ca hau nhu luon co chu "trung ca"
# trong cung chunk 200 tu nen khong mat gi dang ke. Spironolacton thi giu:
# trong ngu canh da lieu no gan nhu chi dung cho trung ca noi tiet.


def keep(text: str, lang: str, general: bool, g: dict) -> str | None:
    """None = giu; chuoi = ly do drop."""
    if len(g["_CJK_RE"].findall(text)) / max(len(text), 1) > g["_CJK_THRESHOLD"]:
        return "cjk"
    s = text.strip()
    low = s.lower()
    if g["_BOILERPLATE_RE"].match(s[:120]):
        return "boilerplate"
    if len(s) < 600 and g["_AD_NOISE_RE"].search(low):
        return "ad/nav"
    if g["_repetition_ratio"](text) > 0.72:
        return "lap tu"
    j = is_junk(text)
    if j:
        return j
    if general:
        sig = _STRONG_ACNE_VI if lang == "vi" else _STRONG_ACNE_EN
        if not (sig.search(low) or _LOOKALIKE.search(low)):
            return "khong co acne signal"
    off = g["_OFF_TOPIC_VI"] if lang == "vi" else g["_OFF_TOPIC_EN"]
    if off.search(low):
        return "off-topic"
    return None


def build() -> tuple[list[dict], dict]:
    g = load_gates()
    ch = VietnameseChunker(chunk_size=200, overlap=40, min_size=50, dedup=False)
    docs = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out: list[dict] = []
    stats: dict[str, int] = {}
    seen: set[str] = set()

    for d in docs:
        pdf = Path(d["file"])
        # PDF nam o <lang>_docs/{text,scan}/, .txt thi dung o <lang>_docs/txt/ (chung).
        # Phai bo bot mot cap thu muc, khong thi tro nham vao <lang>_docs/text/txt/.
        lang_dir = pdf.parent.parent if pdf.parent.name in ("text", "scan") else pdf.parent
        txt = HERE / lang_dir / "txt" / (pdf.stem + ".txt")
        if not txt.exists():
            stats["thieu txt"] = stats.get("thieu txt", 0) + 1
            continue
        name, lang = pdf.stem, d["lang"]
        general = name in GENERAL_DERM
        kept: list[str] = []
        for c in ch.chunk(txt.read_text(encoding="utf-8")):
            why = keep(c, lang, general, g)
            if why:
                stats[why] = stats.get(why, 0) + 1
                continue
            norm = re.sub(r"\s+", " ", c.strip())
            if norm in seen:
                stats["trung"] = stats.get("trung", 0) + 1
                continue
            seen.add(norm)
            kept.append(c)

        doc_id = DOC_PREFIX + hashlib.sha1(name.encode()).hexdigest()[:12]
        ids = [f"{doc_id}_{i}" for i in range(len(kept))]
        for i, (cid, text) in enumerate(zip(ids, kept)):
            out.append({
                "chunk_id": cid, "doc_id": doc_id, "text": text, "text_len": len(text),
                "position": i,
                "prev_chunk_id": ids[i - 1] if i else None,
                "next_chunk_id": ids[i + 1] if i + 1 < len(ids) else None,
                "url": d["source_url"], "title": name,
                "source_name": "guideline", "source_type": source_type_of(name),
                "trust_level": "high", "language": lang,
                "categories": [], "tags": ["guideline"], "embedding": None,
            })
    return out, stats


def write(chunks: list[dict]) -> None:
    """Ghi ra file RIENG, KHONG dung vao chunks.jsonl.

    Tach lam 2 buoc de soi duoc truoc khi nap: script nay chi dung
    chunks_guideline.jsonl; muon nhap vao KB thi chay merge_guideline_chunks.py.
    """
    GUIDELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GUIDELINE_PATH.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    os.replace(tmp, GUIDELINE_PATH)
    print(f"-> {GUIDELINE_PATH.relative_to(ROOT)}: {len(chunks)} chunk")
    print("   Nap vao KB: python guideline_docs/merge_guideline_chunks.py")


def _check() -> None:
    assert source_type_of("NICE-NG198") == "nice_guideline"
    assert source_type_of("EuroGuiDerm-2025-long") == "clinical_textbook"
    assert source_type_of("VJDV-minocyclin") == "pubmed_review"       # nghien cuu goc
    assert source_type_of("CMAJ-2016-canada") == "clinical_textbook"  # guideline Canada
    assert source_type_of("VJDV-dong-thuan-duoc-my-pham") == "clinical_textbook"
    assert source_type_of("AAFP-2019") == "pubmed_review"             # tong quan lam sang
    assert source_type_of("Skin Health and Disease - 2023 - Corcoran") == "pubmed_review"
    assert is_junk("3.1 Dac diem chung ....... 22\n3.2 Ket qua ....... 31") == "muc luc"
    assert is_junk("Lancet. 2012;380(9842):660. Janjua S, et al. doi: 10.1/x") == "tai lieu tham khao"
    assert is_junk("Offer a 12-week course of topical adapalene.") is None
    print("check ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="chi in thong ke, khong ghi")
    a = ap.parse_args()
    _check()
    chunks, stats = build()
    print(f"\n{len(chunks)} chunk guideline")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"   drop {k:24} {v}")
    from collections import Counter
    for k, v in Counter(c["source_type"] for c in chunks).most_common():
        print(f"   {k:20} {v}")
    if a.dry_run:
        print("\n--dry-run: khong ghi gi.")
    else:
        write(chunks)
