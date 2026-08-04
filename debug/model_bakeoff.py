"""Thi đấu embedder trên ĐÚNG bộ câu hỏi eval, trước khi rebuild 24k chunk.

Rebuild sai model = mất 4 tiếng CPU. Thi đấu trên tập rút gọn mất ~20 phút và
trả lời đúng câu cần trả lời: model nào kéo chunk vàng lên cao hơn.

Tập thi đấu = toàn bộ chunk vàng + POOL_SIZE chunk nhiễu lấy trải đều 24 nguồn.
Recall ở đây CAO HƠN thực tế vì đống cỏ nhỏ hơn — nhưng thứ hạng giữa các model
mới là thứ cần, và nó không đổi theo cỡ đống cỏ.

Chạy:  python debug/model_bakeoff.py
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
POOL_SIZE = 6000
KS = (5, 15, 50)
MODELS = [
    "AITeamVN/Vietnamese_Embedding",   # đang dùng — mốc so sánh
    "BAAI/bge-m3",
    "Alibaba-NLP/gte-multilingual-base",
]


def load_pool() -> tuple[list[dict], list[str], list[str]]:
    """Câu hỏi có chunk vàng + tập chunk (vàng + nhiễu trải đều nguồn)."""
    from acne_llm.rag.vectorstore import ChromaStore

    store = ChromaStore(persist_dir=str(ROOT / "data" / "chroma_db"))
    samples = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    samples = [s for s in samples if s.get("relevant_chunk_ids")]

    gold_ids = sorted({c for s in samples for c in s["relevant_chunk_ids"]})
    got = store.col.get(ids=gold_ids, include=["documents"])
    id2text = dict(zip(got["ids"], got["documents"]))
    missing = [c for c in gold_ids if not id2text.get(c)]
    if missing:
        print(f"  ⚠ {len(missing)} chunk vàng không có trong KB — bỏ qua")

    # nhiễu: trải đều theo nguồn, không random thuần (nguồn lớn sẽ nuốt hết)
    everything = store.col.get(limit=24393, include=["documents", "metadatas"])
    by_source: dict[str, list[tuple[str, str]]] = {}
    for cid, doc, meta in zip(everything["ids"], everything["documents"],
                              everything["metadatas"]):
        if cid in id2text or not doc or len(doc) < 200:
            continue
        by_source.setdefault(str((meta or {}).get("source") or "?"), []).append((cid, doc))
    random.seed(0)
    for v in by_source.values():
        random.shuffle(v)
    noise: list[tuple[str, str]] = []
    while len(noise) < POOL_SIZE and any(by_source.values()):
        for v in by_source.values():
            if v and len(noise) < POOL_SIZE:
                noise.append(v.pop())

    ids = [c for c in gold_ids if id2text.get(c)] + [c for c, _ in noise]
    texts = [id2text[c] for c in gold_ids if id2text.get(c)] + [t for _, t in noise]
    print(f"  {len(samples)} câu hỏi · {len(ids)} chunk "
          f"({len(ids) - len(noise)} vàng + {len(noise)} nhiễu, "
          f"{len(by_source)} nguồn)\n")
    return samples, ids, texts


def score(name: str, samples: list[dict], ids: list[str], texts: list[str]) -> dict:
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    # use_safetensors: repo nào còn pytorch_model.bin thì transformers chặn vì
    # CVE-2025-32434 khi torch < 2.6. bge-m3 có sẵn safetensors, chỉ cần ép chọn.
    model = SentenceTransformer(name, device="cpu", trust_remote_code=True,
                                model_kwargs={"use_safetensors": True})
    P = model.encode(texts, batch_size=16, normalize_embeddings=True,
                     convert_to_numpy=True, show_progress_bar=True)
    passage_s = time.time() - t0
    Q = model.encode([s["user_query"] for s in samples], batch_size=16,
                     normalize_embeddings=True, convert_to_numpy=True)

    index = {c: i for i, c in enumerate(ids)}
    sims = Q @ P.T
    order = np.argsort(-sims, axis=1)
    out = {"model": name, "dim": P.shape[1], "giây": round(passage_s, 1),
           "chunk_mỗi_giây": round(len(texts) / passage_s, 1)}
    for k in KS:
        hit = 0
        for row, sample in zip(order, samples):
            gold = {index[c] for c in sample["relevant_chunk_ids"] if c in index}
            hit += bool(gold & set(row[:k].tolist()))
        out[f"recall@{k}"] = hit / len(samples)
    del model
    return out


CACHE = Path(__file__).with_name("bakeoff_results.json")


def load_cache() -> dict[str, dict]:
    try:
        return {r["model"]: r for r in json.loads(CACHE.read_text(encoding="utf-8"))}
    except Exception:
        return {}


def main() -> None:
    # Mỗi model 568M mất ~48 phút trên CPU. Ghi kết quả ngay khi xong từng model
    # để hỏng ở model sau không đốt lại model trước — chạy lại là tiếp tục.
    #   python debug/model_bakeoff.py                    # tiếp chỗ dở
    #   python debug/model_bakeoff.py BAAI/bge-m3        # chỉ một model
    #   python debug/model_bakeoff.py --lại              # bỏ cache, làm lại
    argv = [a for a in sys.argv[1:] if a != "--lại"]
    done = {} if "--lại" in sys.argv else load_cache()
    wanted = argv or MODELS

    todo = [m for m in wanted if m not in done]
    if done:
        print(f"  đã có sẵn: {', '.join(done)}")
    if not todo:
        print("  không còn gì phải chạy (dùng --lại để làm lại)\n")
    samples, ids, texts = ([], [], [])
    if todo:
        samples, ids, texts = load_pool()

    for name in todo:
        print(f"── {name}")
        try:
            result = score(name, samples, ids, texts)
        except Exception:
            traceback.print_exc()
            print(f"   ↑ {name} hỏng — bỏ qua, các model khác vẫn chạy\n")
            continue
        done[name] = result
        CACHE.write_text(json.dumps(list(done.values()), indent=2, ensure_ascii=False),
                         encoding="utf-8")     # ghi ngay, đừng đợi hết vòng lặp
        print(f"   {result}\n")

    rows = [done[m] for m in wanted if m in done]
    if not rows:
        raise SystemExit("Không model nào chạy được.")

    print(f"\n{'model':36}{'dim':>6}" + "".join(f"{f'R@{k}':>9}" for k in KS)
          + f"{'chunk/s':>10}{'rebuild 24k':>13}")
    for r in rows:
        rebuild = 24393 / r["chunk_mỗi_giây"] / 60
        print(f"{r['model']:36}{r['dim']:>6}"
              + "".join(f"{r[f'recall@{k}']:>9.1%}" for k in KS)
              + f"{r['chunk_mỗi_giây']:>10.1f}{rebuild:>10.0f} ph")

    if len(rows) > 1:
        best = max(rows, key=lambda r: r["recall@5"])
        base = rows[0]
        gain = best["recall@5"] - base["recall@5"]
        print(f"\n=> {best['model']}  R@5 {best['recall@5']:.1%} "
              f"({gain:+.1%} so với model đang dùng)")
        if gain < 0.05:
            print("   Chênh lệch nhỏ. Rebuild có thể không đáng — cân nhắc sửa\n"
                  "   chat_retrieve_top_k trước (rẻ hơn nhiều, đã biết thu lại 6/22).")


if __name__ == "__main__":
    main()
