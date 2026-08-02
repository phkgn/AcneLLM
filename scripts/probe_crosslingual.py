"""Do rieng tung tang xem tang nao lam mat tai lieu tieng Anh.

Truy van tieng Viet + KB 40% tieng Anh. Trace thuc te cho thay chunk guideline
tieng Anh bi cham 0.004-0.182 trong khi chunk web tieng Viet dat 0.906-0.997.
Cau hoi: tang nao gay ra -- EMBEDDER (khong tim ra) hay RERANKER (tim ra nhung
cham thap)? Hai nguyen nhan can hai cach sua khac han nhau.

Script lay CUNG mot bo chunk ung vien roi cham bang ca hai tang:
  A. Embedder  -- cosine(query, chunk).  Quyet dinh chunk co duoc LAY VE khong.
  B. Reranker  -- xac suat lien quan.    Quyet dinh chunk co duoc GIU khong.

Doc ket qua:
  * Reranker cham chunk EN cao (>0.8) nhung embedder xep chung cuoi bang
      -> nut that o EMBEDDER. Doi sang BGE-M3 (ban goc da ngon ngu) la dung huong.
  * Ca hai tang deu xep chunk EN cuoi bang
      -> khong tang nao bac duoc cau ngon ngu. Doi embedder cung vo ich; phai
         dich truy van sang tieng Anh hoac chap nhan KB tieng Viet.

Chay:
    python scripts/probe_crosslingual.py
    python scripts/probe_crosslingual.py --query "..." --include "referral|chuyen tuyen"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CHUNKS = ROOT / "data" / "raw" / "chunks.jsonl"

# Mac dinh: cau hoi ma KB CO dap an ro rang o ca hai ngon ngu.
DEFAULT_QUERY = "Khi nào thì cần đi khám bác sĩ da liễu thay vì tự điều trị mụn tại nhà?"
# Bat NGON NGU KHUYEN CAO, khong bat ten chu de. Pattern rong kieu "dermatolog"
# se vo phai muc luc, bang protocol, phan danh gia bang chung -- nhung doan nhac
# tu khoa nhieu lan nhung KHONG tra loi cau hoi. Do la loi cua lan chay dau:
# ca 18 ung vien deu bi reranker cham < 0.07 vi khong cai nao lien quan that.
DEFAULT_INCLUDE = (
    r"urgent referral|standard referral|refer(?:red|ral)?\s+(?:to a|on the same day|within)|"
    r"should be referred|seek medical|see a dermatologist|"
    r"nên đi khám|cần đi khám|nên đến gặp bác sĩ|khi nào (?:nên|cần)"
)
_VI_MARKS = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")


def is_vi(text: str) -> bool:
    words = re.findall(r"[^\W\d_]{2,}", text.lower())
    if not words:
        return True
    return sum(1 for w in words if set(w) & _VI_MARKS) / len(words) > 0.15


def pick_candidates(include: str, per_group: int) -> list[dict]:
    """Chunk khop keyword NHIEU NHAT trong tung nhom (ngon ngu x guideline/web).

    Phai xep theo so lan khop chu khong lay 5 cai dau: lay dau se vo phai bai
    ngau nhien co dung mot chu "dermatolog", trong khi ta can chunk THUC SU noi
    ve chu de -- neu khong thi diem thap la do chon mau te, khong phai do ngon ngu.
    """
    pat = re.compile(include, re.I)
    groups: dict[tuple, list[tuple[int, dict]]] = {}
    for line in CHUNKS.open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        n = len(pat.findall(row["text"]))
        if not n:
            continue
        is_guide = str(row.get("doc_id", "")).startswith("guideline:")
        key = ("vi" if is_vi(row["text"]) else "en", "guideline" if is_guide else "web")
        groups.setdefault(key, []).append((n, row))
    out: list[dict] = []
    for scored in groups.values():
        scored.sort(key=lambda t: -t[0])
        out.extend(row for _, row in scored[:per_group])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--include", default=DEFAULT_INCLUDE)
    ap.add_argument("--per-group", type=int, default=5)
    args = ap.parse_args()

    if not CHUNKS.exists():
        sys.exit(f"Chua co {CHUNKS.relative_to(ROOT)}")

    cands = pick_candidates(args.include, args.per_group)
    if not cands:
        sys.exit(f"Khong chunk nao khop --include {args.include!r}")

    from acne_llm.config import settings
    from acne_llm.rag.embedder import Embedder
    from acne_llm.rag.reranker import Reranker

    print(f"Truy van : {args.query}")
    print(f"Ung vien : {len(cands)} chunk\n")

    emb = Embedder(model_name=settings.embedding_model, device=settings.device)
    qv = emb.embed_query(args.query)
    dv = emb.embed_passages([c["text"] for c in cands])
    # embed_query/passages da chuan hoa L2 -> dot product = cosine
    cos = [float(sum(a * b for a, b in zip(qv, row))) for row in dv]

    rr = Reranker(model_name=settings.reranker_model, device=settings.device)
    # Goi thang CrossEncoder de lay TOAN BO diem; rerank() cat top_k va loc nguong.
    probs = [float(p) for p in rr._load().predict(
        [(args.query, c["text"]) for c in cands], show_progress_bar=False
    )]

    rows = sorted(zip(cands, cos, probs), key=lambda t: -t[2])

    print(f"{'#':>2} {'RERANK':>7} {'COSINE':>7} {'ng':>3} {'source_type':<18} nguon")
    print("-" * 92)
    for i, (c, cs, pr) in enumerate(rows, 1):
        lang = "vi" if is_vi(c["text"]) else "en"
        print(f"{i:>2} {pr:>7.4f} {cs:>7.4f} {lang:>3} "
              f"{str(c.get('source_type'))[:18]:<18} {str(c.get('title'))[:34]}")

    en = [(cs, pr) for c, cs, pr in rows if not is_vi(c["text"])]
    vi = [(cs, pr) for c, cs, pr in rows if is_vi(c["text"])]
    print("-" * 92)
    for lab, grp in (("tieng Viet", vi), ("tieng Anh ", en)):
        if not grp:
            continue
        print(f"{lab}: n={len(grp):<3} rerank tb={sum(p for _, p in grp)/len(grp):.4f}  "
              f"max={max(p for _, p in grp):.4f}  |  cosine tb={sum(c for c, _ in grp)/len(grp):.4f}")
    if not (en and vi):
        print("\n(!) Thieu mot trong hai nhom -- khong so sanh duoc.")
        return

    best_en, best_vi = max(p for _, p in en), max(p for _, p in vi)
    print()
    print(f"Chenh lech EN so voi VI (cao nhat moi ben):  "
          f"rerank {best_en - best_vi:+.4f}   "
          f"cosine {max(c for c, _ in en) - max(c for c, _ in vi):+.4f}")
    print()

    # DOI CHUNG BAT BUOC: neu KHONG nhom nao co chunk that su lien quan thi mau
    # qua te, moi so sanh deu vo nghia. Lan chay dau tien mac dung loi nay --
    # ca 18 chunk deu < 0.07 va script van phan "ca hai tang xep tieng Anh thap".
    if max(best_en, best_vi) < 0.50:
        print("=> KHONG KET LUAN DUOC. Khong nhom nao co chunk dat 0.50 --")
        print(f"   cao nhat chi {max(best_en, best_vi):.4f}. Mau khong chua cau tra loi,")
        print("   nen diem thap la do CHON MAU chu khong phai do ngon ngu.")
        print("   -> doi --include sang cum tu xuat hien trong CAU TRA LOI that,")
        print("      hoac tang --per-group de mo rong vung tim.")
    elif best_en >= 0.80:
        print("=> RERANKER cham chunk tieng Anh CAO. Nut that nam o EMBEDDER:")
        print("   chunk tot khong bao gio duoc lay ve de reranker nhin thay.")
        print("   -> thu BGE-M3 goc (da ngon ngu) thay cho ban fine-tune tieng Viet.")
    elif best_vi >= 0.80:
        print("=> Chi nhom tieng Viet co chunk that su lien quan; ban tieng Anh khong.")
        print("   Kiem tra noi dung nhom EN truoc khi ket luan: co the tai lieu tieng")
        print("   Anh trong KB thien ve evidence review chu khong chua khuyen cao gon.")
    else:
        print("=> Ca hai nhom deu duoi 0.80 nhung tren 0.50 -- lien quan mo ho.")
        print("   Can mau tot hon truoc khi ket luan ve ngon ngu.")


if __name__ == "__main__":
    main()
