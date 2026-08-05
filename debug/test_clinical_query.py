"""Viết lại truy vấn sang ngôn ngữ lâm sàng có nâng điểm đoạn khuyến cáo không?

Giả thuyết: guideline bị chấm 0.03-0.35 vì câu hỏi viết bằng tiếng Việt đời
thường, còn NICE/AAD viết bằng thuật ngữ lâm sàng. Intaker ĐÃ rút ra sẵn enum
lâm sàng (papule, nodule, jawline, moderate...) nhưng build_query_from_user gói
chúng vào nhãn tiếng Việt không dấu rồi trộn vào câu hỏi gốc.

So hai cách dựng truy vấn, TRÊN CÙNG slot mà intaker rút được:

  V1  hiện tại   build_query_from_user()  — câu hỏi VN + "loai mun papule..."
  V2  lâm sàng   dựng thuần từ enum       — "moderate inflammatory acne..."

Cả hai chạy qua retrieve_safety_pass (rổ khuyến cáo) rồi rerank, so điểm.

Không đổi setting nào của production. Chạy:
    python debug/test_clinical_query.py           # 30 câu
    python debug/test_clinical_query.py 60
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DATASET = ROOT / "evaluation/datasets/eval_set.jsonl"

# enum của intaker -> cách nói của khuyến cáo lâm sàng
LESION = {
    "comedone": "comedonal", "whitehead": "closed comedones",
    "blackhead": "open comedones", "closed_comedone": "closed comedones",
    "papule": "inflammatory papules", "pustule": "pustules",
    "nodule": "nodules", "cyst": "cysts",
    "scar": "acne scarring",
    "post_inflammatory_hyperpigmentation": "post-inflammatory hyperpigmentation",
}
SITE = {
    "chin": "chin", "jawline": "mandibular", "cheeks": "malar",
    "forehead": "forehead", "nose": "nasal", "t_zone": "T-zone",
    "around_mouth": "perioral", "back": "truncal back",
    "chest": "truncal chest", "shoulders": "shoulders", "neck": "neck",
}
GRADE = {"mild": "mild acne vulgaris", "moderate": "moderate acne vulgaris",
         "severe": "severe acne vulgaris"}
SKIN = {"oily": "seborrhoeic oily skin", "dry": "dry skin",
        "sensitive": "sensitive skin", "combination": "combination skin"}


def clinical_query(user) -> str:
    """V2 — thuần thuật ngữ, KHÔNG kèm câu hỏi tiếng Việt."""
    bits: list[str] = []
    cl = getattr(user, "clinical", None)
    types = list(getattr(cl, "lesion_types", []) or []) if cl else []
    grade = getattr(cl, "inflammation_level", None) if cl else None
    sites = list(getattr(cl, "lesion_distribution", []) or []) if cl else []

    if grade in GRADE:
        bits.append(GRADE[grade])
    elif types:
        bits.append("acne vulgaris")

    # nodule+cyst là cụm mà guideline luôn viết liền
    if {"nodule", "cyst"} & set(types):
        bits.append("nodulocystic acne")
    named = [LESION[t] for t in types if t in LESION]
    if named:
        bits.append(" and ".join(dict.fromkeys(named)))
    if sites:
        bits.append(" ".join(dict.fromkeys(SITE[s] for s in sites if s in SITE))
                    + " distribution")

    c = getattr(user, "context", None)
    if c is not None:
        if getattr(c, "is_pregnant", False):
            bits.append("acne in pregnancy, teratogenic risk")
        if getattr(c, "is_breastfeeding", False):
            bits.append("acne during breastfeeding")
        if getattr(c, "skin_type", None) in SKIN:
            bits.append(SKIN[c.skin_type])
        if getattr(c, "age", None):
            bits.append("adolescent" if c.age < 20 else "adult acne")
        if getattr(c, "duration_weeks", None):
            bits.append("persistent acne" if c.duration_weeks >= 8 else "recent onset")
        for m in (getattr(c, "medications", None) or [])[:3]:
            bits.append(str(m))
    if not bits:
        bits.append("acne vulgaris management")
    return ", ".join(bits) + ", treatment recommendation"


def main() -> None:
    n_q = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    from acne_llm.config import settings
    from acne_llm.di import build_container
    from acne_llm.chat._retrieval import build_query_from_user
    from evaluation.adapters._repo import normalize_query

    c = build_container(settings)
    if not c.rag_ready or c.reranker is None:
        raise SystemExit("RAG hoặc reranker chưa sẵn sàng")
    GTYPES = getattr(c.retriever, "GUIDELINE_SOURCE_TYPES",
                     ("nice_guideline", "aad_guideline", "clinical_textbook"))

    rows = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    rows = [r for r in rows if r.get("relevant_chunk_ids")][:n_q]

    def guideline_run(query: str) -> tuple[list[float], tuple[str, ...]]:
        """Trả điểm VÀ danh tính chunk — cần cả hai để bắt lỗi 'trùng kết quả'."""
        out = c.retriever.retrieve_safety_pass(
            query, safety_terms=None, top_k=5, source_types=GTYPES)
        if not out.chunks:
            return [], ()
        kept = c.reranker.rerank(query, out, top_k=5).chunks
        return (sorted((ch.score for ch in kept), reverse=True),
                tuple(sorted(ch.chunk_id for ch in kept)))

    VARIANTS = ("V1 câu hỏi gốc", "V2 chỉ enum", "V3 gốc + enum")
    scores = {v: [] for v in VARIANTS}
    top1 = {v: [] for v in VARIANTS}
    fingerprints = {v: [] for v in VARIANTS}
    filled = 0
    print(f"{len(rows)} câu · rổ khuyến cáo {GTYPES}\n")
    for i, r in enumerate(rows, 1):
        user, _ = normalize_query(c, r)
        cl = getattr(user, "clinical", None)
        filled += bool(cl and (getattr(cl, "lesion_types", None)
                               or getattr(cl, "lesion_distribution", None)
                               or getattr(cl, "inflammation_level", "unknown") != "unknown"))
        q1 = build_query_from_user(user)
        q2 = clinical_query(user)
        q3 = f"{q1}\n{q2}"            # giữ câu hỏi gốc, NỐI THÊM enum
        for name, q in zip(VARIANTS, (q1, q2, q3)):
            s, fp = guideline_run(q)
            scores[name] += s
            fingerprints[name].append(fp)
            if s:
                top1[name].append(s[0])
        if i == 1:
            print(f"  ── mẫu 1\n     V3: {q3[:200]!r}\n")
        print(f"\r  {i}/{len(rows)}", end="", flush=True)
    print("\n")

    print(f"  câu có slot lâm sàng: {filled}/{len(rows)} "
          f"({'ĐỦ' if filled >= len(rows)*0.5 else '⚠ QUÁ ÍT'})\n")
    print(f"{'':16}{'n':>5}{'trung bình':>12}{'trung vị':>10}{'>0.5':>7}"
          f"{'top1 TB':>10}{'bộ KQ khác nhau':>18}")
    base = None
    for name in VARIANTS:
        v = scores[name]
        if not v:
            print(f"{name:16}   không lấy được đoạn nào"); continue
        uniq = len({fp for fp in fingerprints[name] if fp})
        t1 = st.mean(top1[name]) if top1[name] else float("nan")
        if base is None:
            base = t1
        print(f"{name:16}{len(v):>5}{st.mean(v):>12.3f}{st.median(v):>10.3f}"
              f"{sum(1 for x in v if x > .5):>7}{t1:>10.3f}"
              f"{f'{uniq}/{len(rows)}':>18}")
    print(f"\n  Cột cuối là chỗ quan trọng: bao nhiêu câu hỏi nhận được bộ tài liệu")
    print(f"  KHÁC NHAU. Gần {len(rows)}/{len(rows)} là tốt. Thấp nghĩa là nhiều câu hỏi")
    print(f"  khác nhau bị rút gọn thành cùng một truy vấn -> lấy về cùng một xấp.")
    print(f"  Điểm cao mà cột này thấp thì đó là 'đúng chủ đề, không trả lời câu hỏi'.")


if __name__ == "__main__":
    main()
