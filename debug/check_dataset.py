"""Kiểm bộ đề bằng ĐÚNG embedder đã dùng để khử trùng — không đếm từ.

Phép kiểm bằng Jaccard chỉ một chiều: tìm thấy trùng thì chắc chắn trùng, nhưng
không tìm thấy thì chẳng chứng minh được gì vì nó mù với bản viết lại. Ở đây
dùng lại chính `semantic_dedup` nên phép kiểm mạnh ngang thứ nó kiểm.

    python debug/check_dataset.py evaluation/datasets/eval_set.v3.jsonl
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else ROOT / "evaluation/datasets/eval_set.v3.jsonl")
    from evaluation.datasets.make_eval_set import NEAR_DUP_COSINE, semantic_dedup
    from evaluation.datasets.registry import validate_file

    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    errors = validate_file(path)
    print(f"{path.name} · {len(rows)} dòng · schema: "
          f"{errors[:3] if errors else 'HỢP LỆ'}\n")

    for field, label in (("intent_label", "NHÃN"),
                         ("spec_category", "SPEC_CATEGORY")):
        counts = collections.Counter(r.get(field) for r in rows if r.get(field))
        print(f"{label}: " + " · ".join(f"{k} {v}" for k, v in counts.most_common()))

    cons = collections.Counter(c for r in rows
                               for c in (r.get("generator_constraints") or []))
    print(f"\nRÀNG BUỘC GENERATOR (cần ≥5 mỗi loại mới kết luận được gì):")
    for k, v in cons.most_common():
        mark = "" if v >= 5 else "   ← quá ít"
        print(f"  {k:30}{v:>4}{mark}")

    print(f"\nTRÙNG Ý — cosine, ngưỡng {NEAR_DUP_COSINE}")
    # Embedder hỏng thì semantic_dedup trả rỗng — giống hệt "không có cặp nào
    # trùng". Phải phân biệt "kiểm xong, sạch" với "không kiểm được", nếu không
    # script này lại báo an toàn giả đúng như thứ nó sinh ra để bắt.
    from evaluation.datasets.make_eval_set import _embedder
    try:
        _embedder()
    except Exception as exc:                          # noqa: BLE001
        raise SystemExit(
            f"  ✗ KHÔNG kiểm được trùng ý: {type(exc).__name__}: {exc}\n"
            f"    Cài sentence-transformers rồi chạy lại. KHÔNG kết luận bộ đề\n"
            f"    sạch khi chưa kiểm được."
        )
    keep, dropped = semantic_dedup([str(r.get("user_query") or "") for r in rows],
                                   report=True)
    if dropped:
        print(f"  ⚠ CÒN {len(dropped)} cặp trùng lọt vào file:")
        for cos, i, j in sorted(dropped, reverse=True)[:8]:
            print(f"     cos={cos:.3f}  {rows[i].get('sample_id')} ~ "
                  f"{rows[j].get('sample_id')}")
            print(f"        “{str(rows[i].get('user_query'))[:74]}”")
        print(f"  -> hạ NEAR_DUP_COSINE rồi sinh lại, hoặc xoá tay các dòng trên")
    else:
        print("  ✓ không còn cặp nào vượt ngưỡng")

    # Cặp SÁT ngưỡng là chỗ đáng nghi nhất: khử trùng chạy ở đúng ngưỡng đó nên
    # nó dồn các bản trùng vừa thoát về sát vạch. Phải nhìn text mới biết.
    import numpy as np
    from evaluation.datasets.make_eval_set import _embedder as _emb
    vectors = np.asarray(_emb().embed_passages(
        [str(r.get("user_query") or "") for r in rows]), dtype=np.float32)
    vectors /= np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    similarity = vectors @ vectors.T
    lo = NEAR_DUP_COSINE - 0.06
    near = sorted(((float(similarity[i, j]), i, j)
                   for i in range(len(rows)) for j in range(i + 1, len(rows))
                   if lo <= similarity[i, j] < NEAR_DUP_COSINE), reverse=True)
    if near:
        print(f"\n  {len(near)} cặp SÁT ngưỡng ({lo:.2f}–{NEAR_DUP_COSINE}) — "
              f"nhìn xem có phải trùng thật không:")
        for cos, i, j in near[:6]:
            print(f"     cos={cos:.3f}  {rows[i].get('sample_id')} ~ "
                  f"{rows[j].get('sample_id')}")
            print(f"        A “{str(rows[i].get('user_query'))[:78]}”")
            print(f"        B “{str(rows[j].get('user_query'))[:78]}”")

    if "--fix" in sys.argv:
        if dropped:
            cleaned = [rows[i] for i in keep]
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                      for r in cleaned) + "\n", encoding="utf-8")
            print(f"\n  ✓ ĐÃ LỌC: {len(rows)} → {len(cleaned)} dòng "
                  f"(bỏ {len(dropped)} bản trùng ở ngưỡng {NEAR_DUP_COSINE})")
            rows = cleaned
        else:
            print("\n  --fix: không có gì để bỏ")

    gold = [r for r in rows if r.get("relevant_chunk_ids")]
    print(f"\nCHUNK VÀNG: {len(gold)}/{len(rows)} dòng · "
          f"{collections.Counter(len(r['relevant_chunk_ids']) for r in gold)}")
    pending = sum(1 for r in rows
                  if r.get("annotation_status") == "synthetic_pending_review")
    print(f"CHƯA DUYỆT: {pending}/{len(rows)} — expected_answer_points và "
          f"forbidden_claims là rubric judge chấm theo")


if __name__ == "__main__":
    main()
