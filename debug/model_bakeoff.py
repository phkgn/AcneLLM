"""Thi đấu embedder trên đúng bộ câu hỏi eval, trước khi rebuild 24k chunk.

Giữ TOÀN BỘ 103 câu hỏi — chúng gần như miễn phí (~1 phút). Thời gian nằm ở
việc embed đống cỏ, nên muốn nhanh thì giảm POOL chứ đừng giảm câu hỏi. n=30 đã
hai lần cho ra kết quả không phân giải nổi gì trong dự án này.

Recall tuyệt đối phụ thuộc cỡ đống cỏ (đống nhỏ -> recall cao giả), nên khoá
cache có kèm pool_size. Đổi cỡ là tự động chạy lại, không bao giờ ghép nhầm hai
phép đo khác cỡ.

Ghi kết quả ngay sau mỗi model xong -> hỏng ở model sau không đốt lại model trước.

    python debug/model_bakeoff.py                       # pool 1500, cả 3 model
    python debug/model_bakeoff.py 1500 BAAI/bge-m3      # chỉ 1 model
    python debug/model_bakeoff.py 6000                  # kỹ hơn, chậm hơn
"""
from __future__ import annotations

import json
import random
import sys
import time
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DATASET = ROOT / "evaluation/datasets/eval_set.jsonl"
CACHE = Path(__file__).with_name("bakeoff_results.json")
KS = (5, 15, 50)
MODELS = [
    "AITeamVN/Vietnamese_Embedding",   # đang dùng — mốc so sánh
    "BAAI/bge-m3",
    "Alibaba-NLP/gte-multilingual-base",
]


def load_cache() -> dict[str, dict]:
    try:
        return {f"{r['model']}@{r.get('pool', '?')}": r
                for r in json.loads(CACHE.read_text(encoding="utf-8"))}
    except Exception:
        return {}


def load_pool(pool_size: int):
    from acne_llm.rag.vectorstore import ChromaStore

    store = ChromaStore(persist_dir=str(ROOT / "data" / "chroma_db"))
    samples = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    samples = [s for s in samples if s.get("relevant_chunk_ids")]
    gold_ids = sorted({c for s in samples for c in s["relevant_chunk_ids"]})
    got = store.col.get(ids=gold_ids, include=["documents"])
    keep = {i: d for i, d in zip(got["ids"], got["documents"]) if d}

    everything = store.col.get(limit=24393, include=["documents", "metadatas"])
    by_source: dict[str, list] = {}
    for cid, doc, meta in zip(everything["ids"], everything["documents"],
                              everything["metadatas"]):
        if cid in keep or not doc or len(doc) < 200:
            continue
        by_source.setdefault(str((meta or {}).get("source") or "?"), []).append((cid, doc))
    random.seed(0)
    for v in by_source.values():
        random.shuffle(v)
    noise: list[tuple[str, str]] = []
    while len(noise) < pool_size and any(by_source.values()):
        for v in by_source.values():
            if v and len(noise) < pool_size:
                noise.append(v.pop())

    ids = list(keep) + [c for c, _ in noise]
    texts = list(keep.values()) + [t for _, t in noise]
    print(f"  {len(samples)} câu hỏi · {len(ids)} chunk "
          f"({len(keep)} vàng + {len(noise)} nhiễu, {len(by_source)} nguồn)\n")
    return samples, ids, texts


def score(name: str, samples, ids, texts, pool_size: int) -> dict:
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    # use_safetensors: repo còn pytorch_model.bin bị transformers chặn vì
    # CVE-2025-32434 khi torch < 2.6. bge-m3 có sẵn safetensors, chỉ cần ép chọn.
    model = SentenceTransformer(name, device="cpu", trust_remote_code=True,
                                model_kwargs={"use_safetensors": True})
    P = model.encode(texts, batch_size=16, normalize_embeddings=True,
                     convert_to_numpy=True, show_progress_bar=True)
    passage_s = time.time() - t0
    Q = model.encode([s["user_query"] for s in samples], batch_size=16,
                     normalize_embeddings=True, convert_to_numpy=True)

    index = {c: i for i, c in enumerate(ids)}
    order = np.argsort(-(Q @ P.T), axis=1)
    out = {"model": name, "pool": pool_size, "dim": int(P.shape[1]),
           "giây": round(passage_s, 1),
           "chunk_mỗi_giây": round(len(texts) / passage_s, 1)}
    for k in KS:
        hit = sum(bool({index[c] for c in s["relevant_chunk_ids"] if c in index}
                       & set(row[:k].tolist()))
                  for row, s in zip(order, samples))
        out[f"recall@{k}"] = hit / len(samples)
    del model
    return out


def main() -> None:
    args = sys.argv[1:]
    pool_size = int(args[0]) if args and args[0].isdigit() else 1500
    wanted = [a for a in args if not a.isdigit()] or MODELS

    done = load_cache()
    todo = [m for m in wanted if f"{m}@{pool_size}" not in done]
    if len(todo) < len(wanted):
        print(f"  đã có sẵn ở pool={pool_size}: "
              f"{', '.join(m for m in wanted if m not in todo)}")
    samples, ids, texts = load_pool(pool_size) if todo else ([], [], [])

    for name in todo:
        print(f"── {name}")
        try:
            r = score(name, samples, ids, texts, pool_size)
        except Exception:
            traceback.print_exc()
            print(f"   ↑ {name} hỏng — bỏ qua, model khác vẫn chạy\n")
            continue
        done[f"{name}@{pool_size}"] = r
        CACHE.write_text(json.dumps(list(done.values()), indent=2, ensure_ascii=False),
                         encoding="utf-8")          # ghi ngay, đừng đợi hết vòng
        print(f"   {r}\n")

    rows = [done[f"{m}@{pool_size}"] for m in wanted if f"{m}@{pool_size}" in done]
    if not rows:
        raise SystemExit("Không model nào chạy được.")
    print(f"\nĐỐNG CỎ {pool_size} — chỉ so các dòng CÙNG cỡ đống cỏ\n")
    print(f"{'model':36}{'dim':>6}" + "".join(f"{f'R@{k}':>9}" for k in KS)
          + f"{'chunk/s':>10}{'rebuild 24k':>13}")
    for r in rows:
        print(f"{r['model']:36}{r['dim']:>6}"
              + "".join(f"{r[f'recall@{k}']:>9.1%}" for k in KS)
              + f"{r['chunk_mỗi_giây']:>10.1f}"
              + f"{24393 / r['chunk_mỗi_giây'] / 60:>10.0f} ph")

    if len(rows) > 1:
        best = max(rows, key=lambda r: r["recall@5"])
        gain = best["recall@5"] - rows[0]["recall@5"]
        print(f"\n=> {best['model']}  ({gain:+.1%} R@5 so với model đang dùng)")
        if gain < 0.05:
            print("   Chênh nhỏ — rebuild có thể không đáng. 54% chunk vàng là nguồn")
            print("   tiếng Anh, nên nếu model đa ngữ KHÔNG hơn thì giả thuyết xuyên")
            print("   ngữ sai, và tiền nên đổ vào chỗ khác.")


if __name__ == "__main__":
    main()
