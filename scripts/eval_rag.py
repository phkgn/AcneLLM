"""Consolidated RAG evaluation: query generation (DeepSeek) + retrieval eval.

PART 1 — Query Generation
    Load chunks from data/raw/chunks.jsonl, filter acne-related, stratified sample
    (85% vi / 15% en), call DeepSeek to generate 1 query per chunk, write
    data/eval/generated_eval_queries.jsonl and .csv.
    Difficulty prompt đã được cải thiện để tránh hard query copy thuật ngữ chunk gốc.

PART 2 — Retrieval Eval
    Load queries JSONL, build HybridRetriever from existing KB (BM25 + Chroma),
    áp dụng pipeline preprocessing y chang production:
      ① prepare_user_text (NFC + teencode expand + no-accent twin)
      ② normalize_chat_message (extract clinical context → UserInput, dual-text)
      ③ build_retrieval_query_from_user (ghép description + context bits như production)
    compute Hit@k / Recall@k / MRR@k / NDCG@k for k in [1,3,5,10],
    print table with breakdowns, save JSON report.
    Targets: hit@3>=0.50, hit@5>=0.65, mrr@10>=0.35, ndcg@5>=0.40.

Usage:
    # Full pipeline (generate then eval):
    python scripts/eval_rag.py

    # Generate only:
    python scripts/eval_rag.py --skip-eval

    # Eval only (use existing queries):
    python scripts/eval_rag.py --skip-gen

    # Dry-run (print sample prompt, no API calls, no eval):
    python scripts/eval_rag.py --dry-run

    # Filter options:
    python scripts/eval_rag.py --lang vi --trust high --n 200

    # Sparse mode:
    python scripts/eval_rag.py --skip-gen --mode sparse

    # End-to-end mode (backend + Ollama answer, DeepSeek judge):
    python scripts/eval_rag.py --skip-gen --mode e2e --queries data/sample_queries.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ─── Project root ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]

# ─── Default paths ─────────────────────────────────────────────────────────────
DEFAULT_CHUNKS   = ROOT / "data" / "raw" / "chunks.jsonl"
DEFAULT_QUERIES  = ROOT / "data" / "eval" / "generated_eval_queries.jsonl"
DEFAULT_OUT      = ROOT / "data" / "eval" / "rag_eval_report.json"

# ─── Targets ──────────────────────────────────────────────────────────────────
_TARGET_HIT3  = 0.50
_TARGET_HIT5  = 0.65
_TARGET_MRR10 = 0.35
_TARGET_NDCG5 = 0.40

# ─── Intent / Difficulty definitions ──────────────────────────────────────────
_INTENTS_VI = [
    ("ask_cause",       "Hoi nguyen nhan gay mun / tinh trang da"),
    ("ask_symptoms",    "Hoi dau hieu nhan biet, trieu chung"),
    ("ask_treatment",   "Hoi cach dieu tri, phuong phap xu ly"),
    ("ask_medication",  "Hoi ve thuoc, hoat chat, thanh phan"),
    ("ask_routine",     "Hoi ve skincare routine, cham soc hang ngay"),
    ("ask_safety",      "Hoi tac dung phu, chong chi dinh, an toan"),
    ("ask_comparison",  "So sanh phuong phap / san pham / hoat chat"),
    ("ask_when_doctor", "Khi nao can gap bac si"),
    ("ask_general",     "Hoi dinh nghia, thong tin chung"),
]
_INTENTS_EN = [
    ("ask_cause",       "Ask about causes of acne / skin condition"),
    ("ask_symptoms",    "Ask about signs and symptoms"),
    ("ask_treatment",   "Ask about treatment methods"),
    ("ask_medication",  "Ask about drugs, active ingredients, compounds"),
    ("ask_routine",     "Ask about skincare routine / daily care"),
    ("ask_safety",      "Ask about side effects, contraindications, safety"),
    ("ask_comparison",  "Compare methods / products / ingredients"),
    ("ask_when_doctor", "When to see a doctor"),
    ("ask_general",     "Ask for definition or general information"),
]
_DIFFICULTIES = ["easy", "medium", "hard"]

_DIFF_VI = {
    "easy":   "Cau hoi ngan gon, tu ngu doi thuong don gian nhu nguoi binh thuong nhan tin cho chatbot. "
              "KHONG dung thuat ngu y khoa. Vi du: 'mun o cam lam sao het', 'da toi hay bi mun co phai do thuc an khong'.",
    "medium": "Cau hoi co them nguyen canh ca nhan cu the (tuoi, tinh trang da, san pham dang dung, bao lau roi) "
              "nhung van dung ngon ngu tu nhien, khong dung thuat ngu chuyen mon. "
              "Vi du: 'minh 22 tuoi da dau bi mun boc o cam duoc 3 thang dung BHA roi ma khong het phai lam sao'.",
    "hard":   "Cau hoi phuc tap nhieu dieu kien hoac nhieu khia canh cung luc, "
              "nhung PHAI dung ngon ngu nguoi dung tu nhien (khong copy thuat ngu trong chunk). "
              "Vi du: 'mun vua giam tren mat lai noi tren lung co phai do thuoc khong va co nen tiep tuc khong', "
              "'dung retinol va BHA cung luc thi da bi bong troc phai ngung ca hai hay chi mot'.",
}
_DIFF_EN = {
    "easy":   "Short, simple question in everyday language like a regular person texting a chatbot. "
              "Do NOT use medical terminology. Example: 'why do I keep getting pimples on my chin', 'is chocolate causing my acne'.",
    "medium": "Question with added personal context (age, skin type, products used, duration) "
              "but still in natural everyday language, no jargon. "
              "Example: 'I'm 22 with oily skin, been using BHA for 3 months but still getting cystic acne on my jawline, what should I do'.",
    "hard":   "Complex multi-condition or multi-aspect question in natural user language "
              "(do NOT copy terminology from the source chunk). "
              "Example: 'my face acne is clearing but now I'm breaking out on my back, could it be my medication', "
              "'I started retinol and BHA together and my skin is peeling badly, should I stop both or just one'.",
}

# ─── Acne keyword sets ─────────────────────────────────────────────────────────
_ACNE_KW_VI = {
    "mun", "trung ca", "da lieu", "comedone", "viem nang", "ba nhon",
    "isotretinoin", "retinoid", "benzoyl", "salicylic", "adapalene",
    "nang long", "nodule", "cyst", "acne", "blackhead", "whitehead",
    "pimple", "sebaceous", "sebum", "tuyen ba", "lo chan long",
    "mun trung ca", "mun boc", "mun dau den", "mun dau trang",
}
_ACNE_KW_EN = {
    "acne", "pimple", "comedone", "blackhead", "whitehead",
    "isotretinoin", "retinoid", "benzoyl", "salicylic", "adapalene",
    "sebaceous", "sebum", "nodule", "cyst", "inflammatory",
    "follicle", "dermatology", "skincare", "tretinoin",
    "clindamycin", "doxycycline", "acne vulgaris",
}
_STRONG_KW_VI = {
    "mun", "trung ca", "comedone", "acne", "mun boc",
    "mun dau den", "mun dau trang", "isotretinoin",
    "retinoid", "adapalene", "benzoyl", "salicylic",
}
_STRONG_KW_EN = {
    "acne", "pimple", "comedone", "blackhead", "whitehead",
    "isotretinoin", "retinoid", "adapalene", "benzoyl",
    "salicylic", "acne vulgaris",
}

# ─── CSV field order ───────────────────────────────────────────────────────────
CSV_FIELDS = [
    "query", "relevant_chunk_ids", "source_name", "trust_level",
    "language", "intent", "difficulty", "chunk_title", "chunk_url", "generated_at",
]


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 HELPERS — Query Generation
# ══════════════════════════════════════════════════════════════════════════════

def _strip_accents(text: str) -> str:
    import unicodedata
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _is_acne_related(chunk: dict) -> bool:
    """Return True if chunk is acne-related: title OR 2+ strong keywords in text."""
    lang = chunk.get("language", "vi")
    title = _strip_accents(chunk.get("title", ""))
    text  = _strip_accents(chunk.get("text", ""))
    kws    = _ACNE_KW_VI    if lang == "vi" else _ACNE_KW_EN
    strong = _STRONG_KW_VI  if lang == "vi" else _STRONG_KW_EN
    if any(kw in title for kw in kws):
        return True
    for kw in strong:
        if text.count(kw) >= 2:
            return True
    return False


def _load_chunks(path: Path, lang_filter: str | None,
                 trust_filter: str | None) -> list[dict]:
    chunks: list[dict] = []
    skipped = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            tlen = c.get("text_len", len(c.get("text", "")))
            if tlen < 300 or tlen > 3000:
                continue
            if lang_filter and c.get("language") != lang_filter:
                continue
            if trust_filter and c.get("trust_level") != trust_filter:
                continue
            if not _is_acne_related(c):
                skipped += 1
                continue
            chunks.append(c)
    print(f"  Off-topic / short chunks filtered: {skipped}")
    return chunks


def _stratified_sample(chunks: list[dict], n: int) -> list[tuple]:
    """85% vi / 15% en, cycling through intents and difficulties."""
    vi_chunks = [c for c in chunks if c.get("language") == "vi"]
    en_chunks = [c for c in chunks if c.get("language") == "en"]
    random.shuffle(vi_chunks)
    random.shuffle(en_chunks)
    n_vi = int(n * 0.85)
    n_en = n - n_vi

    def _pick(pool: list[dict], count: int, intents: list[tuple]) -> list[tuple]:
        result = []
        intent_cycle = (intents * (count // len(intents) + 1))[:count]
        diff_cycle   = (_DIFFICULTIES * (count // len(_DIFFICULTIES) + 1))[:count]
        random.shuffle(diff_cycle)
        for i, chunk in enumerate(pool[:count]):
            il, idesc = intent_cycle[i]
            diff = diff_cycle[i]
            result.append((chunk, il, idesc, diff, chunk.get("language", "vi")))
        return result

    samples = _pick(vi_chunks, n_vi, _INTENTS_VI) + _pick(en_chunks, n_en, _INTENTS_EN)
    random.shuffle(samples)
    return samples


def _build_prompt(chunk: dict, intent_label: str, intent_desc: str,
                  difficulty: str, lang: str) -> str:
    text   = chunk.get("text", "")
    title  = chunk.get("title", "")
    source = chunk.get("source_name", "")
    if lang == "vi":
        lines = [
            "Ban la chuyen gia tao du lieu eval cho chatbot tu van da mun.",
            "",
            "Cho doan noi dung y khoa sau:",
            "---",
            "Tieu de: " + title,
            "Nguon: "   + source,
            "Noi dung:",
            text,
            "---",
            "",
            "Nhiem vu: Tao DUNG 1 cau hoi bang tieng Viet co dau ma doan noi dung tren la cau tra loi phu hop nhat.",
            "",
            "Yeu cau:",
            "- Intent: " + intent_label + " -- " + intent_desc,
            "- Do kho: " + difficulty + " -- " + _DIFF_VI[difficulty],
            "- Phai dung tieng Viet co dau, tu nhien nhu nguoi dung thuc su go vao chatbot",
            "- KHONG copy nguyen van tu noi dung, dien dat lai bang ngon ngu nguoi hoi",
            "- KHONG de cap ten nguon hoac ten bai viet",
            "- Toi da 2 cau",
            "",
            "Chi tra ve JSON sau, khong them bat ky text nao khac:",
            '{"query": "<cau hoi>", "intent": "' + intent_label + '", "difficulty": "' + difficulty + '"}',
        ]
    else:
        lines = [
            "You are an expert at creating eval data for an acne-advice chatbot.",
            "",
            "Given the following medical content:",
            "---",
            "Title: "   + title,
            "Source: "  + source,
            "Content:",
            text,
            "---",
            "",
            "Task: Generate EXACTLY 1 question in English where the above content is the most relevant answer.",
            "",
            "Requirements:",
            "- Intent: " + intent_label + " -- " + intent_desc,
            "- Difficulty: " + difficulty + " -- " + _DIFF_EN[difficulty],
            "- Natural English as if a real user typed it into a chatbot",
            "- Do NOT copy the text verbatim; rephrase in the voice of a questioner",
            "- Do NOT mention the source or article title",
            "- Maximum 2 sentences",
            "",
            "Return ONLY this JSON, no other text:",
            '{"query": "<question>", "intent": "' + intent_label + '", "difficulty": "' + difficulty + '"}',
        ]
    return "\n".join(lines)


def _read_env_credentials() -> tuple[str, str, str]:
    """Read DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL from ROOT/.env."""
    api_key  = ""
    base_url = "https://api.deepseek.com"
    model    = "deepseek-chat"
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if raw_line.startswith("DEEPSEEK_API_KEY="):
                api_key  = raw_line.split("=", 1)[1].strip().strip('"\'')
            elif raw_line.startswith("DEEPSEEK_BASE_URL="):
                base_url = raw_line.split("=", 1)[1].strip().strip('"\'')
            elif raw_line.startswith("DEEPSEEK_MODEL="):
                model    = raw_line.split("=", 1)[1].strip().strip('"\'')
    # Environment variables override .env
    api_key  = os.environ.get("DEEPSEEK_API_KEY",  api_key)
    base_url = os.environ.get("DEEPSEEK_BASE_URL", base_url)
    model    = os.environ.get("DEEPSEEK_MODEL",    model)
    return api_key, base_url, model


def _call_deepseek(prompt: str, api_key: str, base_url: str,
                   model: str, timeout: int = 30, temperature: float = 0.8,
                   max_tokens: int = 256) -> str | None:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"  [API error] {exc}", file=sys.stderr)
        return None


def _parse_response(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        d = json.loads(_extract_json_object(raw))
        if d.get("query") and len(d["query"].strip()) > 10:
            return d
    except Exception:
        pass
    return None


def _extract_json_object(raw: str) -> str:
    """Extract the first plausible JSON object from an LLM response."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return text[start:end + 1]


def _write_csv(records: list[dict], csv_path: Path) -> None:
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=CSV_FIELDS, delimiter=",")
        writer.writeheader()
        for r in records:
            row = {k: r.get(k, "") for k in CSV_FIELDS}
            ids = row["relevant_chunk_ids"]
            row["relevant_chunk_ids"] = "|".join(ids) if isinstance(ids, list) else ids
            writer.writerow(row)
    print(f"  CSV written: {csv_path}")


def run_generation(args: argparse.Namespace) -> None:
    """PART 1: Generate evaluation queries via DeepSeek API."""
    print("\n" + "=" * 65)
    print("  PART 1 — Query Generation")
    print("=" * 65)

    chunks_path = Path(args.chunks)
    out_path    = Path(args.queries)

    print(f"Loading chunks from {chunks_path} ...")
    chunks = _load_chunks(chunks_path, args.lang, args.trust)
    print(f"  Eligible chunks: {len(chunks)}")

    n = args.n
    if len(chunks) < n:
        print(f"  WARNING: only {len(chunks)} eligible chunks — reducing n to {len(chunks)}")
        n = len(chunks)

    samples = _stratified_sample(chunks, n)
    n_vi = sum(1 for s in samples if s[4] == "vi")
    n_en = sum(1 for s in samples if s[4] == "en")
    print(f"  Sampled: {len(samples)}  (vi={n_vi}, en={n_en})")

    if args.dry_run:
        chunk, il, idesc, diff, lang = samples[0]
        prompt = _build_prompt(chunk, il, idesc, diff, lang)
        print("\n=== SAMPLE PROMPT ===")
        print(prompt)
        print("=== END ===\n")
        return

    api_key, base_url, model = _read_env_credentials()
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found in .env or environment", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = out_path.with_suffix(".csv")

    success = 0
    fail    = 0
    seen: set[str] = set()

    print(f"\nGenerating {n} queries  ->  {out_path}")
    print(f"Model: {model} | delay={args.delay}s\n")

    with open(out_path, "w", encoding="utf-8") as fout:
        for i, (chunk, il, idesc, diff, lang) in enumerate(samples, 1):
            chunk_id = chunk["chunk_id"]
            prompt   = _build_prompt(chunk, il, idesc, diff, lang)

            raw    = _call_deepseek(prompt, api_key, base_url, model)
            parsed = _parse_response(raw)

            if not parsed:
                fail += 1
                print(f"[{i:3d}/{n}] FAIL(parse)  {chunk_id}")
                if args.delay > 0:
                    time.sleep(args.delay)
                continue

            query = parsed["query"].strip()
            if query in seen:
                fail += 1
                print(f"[{i:3d}/{n}] FAIL(dup)    {chunk_id}")
                continue
            seen.add(query)

            record = {
                "query":              query,
                "relevant_chunk_ids": [chunk_id],
                "source_name":        chunk.get("source_name", ""),
                "trust_level":        chunk.get("trust_level", ""),
                "language":           lang,
                "intent":             parsed.get("intent", il),
                "difficulty":         parsed.get("difficulty", diff),
                "chunk_title":        chunk.get("title", ""),
                "chunk_url":          chunk.get("url", ""),
                "generated_at":       datetime.now(timezone.utc).isoformat(),
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            fout.flush()
            success += 1

            short_q = query[:65] + ("..." if len(query) > 65 else "")
            tag = f"[{lang}][{diff:<6}][{il}]"
            print(f"[{i:3d}/{n}] OK {tag} {short_q}")

            if args.delay > 0 and i < len(samples):
                time.sleep(args.delay)

    print("\n" + "=" * 65)
    print(f"  Done: {success} generated, {fail} failed")
    print(f"  JSONL: {out_path}")
    print("=" * 65)

    if success > 0:
        records = []
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        _write_csv(records, csv_path)

        intent_cnt = Counter(r["intent"]     for r in records)
        diff_cnt   = Counter(r["difficulty"] for r in records)
        lang_cnt   = Counter(r["language"]   for r in records)
        print("\nIntent distribution:")
        for k, v in sorted(intent_cnt.items()):
            print(f"  {k:<25} {v}")
        print("\nDifficulty distribution:")
        for k, v in sorted(diff_cnt.items()):
            print(f"  {k:<10} {v}")
        print("\nLanguage distribution:")
        for k, v in sorted(lang_cnt.items()):
            print(f"  {k:<5} {v}")


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 HELPERS — Retrieval Eval
# ══════════════════════════════════════════════════════════════════════════════

def _recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def _mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    for i, cid in enumerate(retrieved[:k], 1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def _ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    dcg  = sum(1.0 / math.log2(i + 1) for i, cid in enumerate(retrieved[:k], 1) if cid in relevant)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / idcg if idcg > 0 else 0.0


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


class _BM25TextStore:
    """Minimal Chroma-like shim for sparse-only eval (no Chroma required)."""
    def __init__(self, bm25):
        self._texts = dict(zip(bm25.chunk_ids, bm25.texts))

    def get_by_id(self, chunk_id: str) -> dict:
        text = self._texts.get(chunk_id, "")
        return {
            "documents": [text] if text else [],
            "metadatas": [{"source": "BM25", "title": "", "source_type": "unknown"}],
        }

    def get_by_ids(self, chunk_ids: list[str]) -> dict:
        docs, metas, ids_out = [], [], []
        for cid in chunk_ids:
            text = self._texts.get(cid, "")
            if text:
                ids_out.append(cid)
                docs.append(text)
                metas.append({"source": "BM25", "title": "", "source_type": "unknown"})
        return {"ids": ids_out, "documents": docs, "metadatas": metas}

    def query_with_score_filter(self, *args, **kwargs):
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def count(self) -> int:
        return len(self._texts)


def _build_retriever(mode: str):
    """Build HybridRetriever + Reranker từ KB và settings hiện tại.

    Returns:
        tuple[HybridRetriever, Reranker | None]
    """
    sys.path.insert(0, str(ROOT / "src"))
    from acne_llm.config import settings
    from acne_llm.rag.sparse import BM25Index

    bm25_path = Path(settings.bm25_path)
    if not bm25_path.exists():
        raise FileNotFoundError(
            f"BM25 index not found: {bm25_path}\n"
            f"Run: python scripts/build_kb.py --step embed"
        )
    bm25 = BM25Index.load(str(bm25_path))
    print(f"  BM25 loaded: {len(bm25.chunk_ids)} chunks")

    from acne_llm.rag.vectorstore import ChromaStore
    from acne_llm.rag.retriever  import HybridRetriever

    chroma_dir = Path(settings.chroma_dir)

    if mode == "sparse":
        try:
            store = ChromaStore(persist_dir=str(chroma_dir))
            print(f"  Chroma loaded for sparse hydration: {store.count()} vectors")
        except Exception as e:
            print(f"  Chroma unavailable — using BM25 text store: {e}")
            store = _BM25TextStore(bm25)
        retriever = HybridRetriever(store=store, embedder=None, bm25=bm25)
        return retriever, None  # sparse mode không dùng reranker

    # Hybrid: need Chroma + Embedder
    if not chroma_dir.exists():
        raise FileNotFoundError(
            f"ChromaDB not found: {chroma_dir}\n"
            f"Run: python scripts/build_kb.py --step embed"
        )
    store = ChromaStore(persist_dir=str(chroma_dir))
    print(f"  Chroma loaded: {store.count()} vectors")

    from acne_llm.rag.embedder import Embedder
    emb_model = getattr(settings, "embedding_model_multilingual", "") or settings.embedding_model
    embedder  = Embedder(model_name=emb_model, device=settings.device)
    retriever = HybridRetriever(store=store, embedder=embedder, bm25=bm25)

    # Load reranker y chang production (di.py)
    reranker = None
    reranker_model = getattr(settings, "reranker_model", "")
    if reranker_model:
        try:
            from acne_llm.rag.reranker import Reranker
            reranker = Reranker(
                model_name=reranker_model,
                device=settings.device,
                batch_size=getattr(settings, "reranker_batch_size", 16),
                cache_size=getattr(settings, "reranker_cache_size", 2048),
                min_sigmoid_score=getattr(settings, "reranker_min_sigmoid", 0.30),
            )
            print(f"  Reranker loaded: {reranker_model}")
        except Exception as e:
            print(f"  Reranker load failed, skipping: {e}")
            reranker = None
    else:
        print("  Reranker: not configured (RERANKER_MODEL not set)")

    return retriever, reranker


def _load_query_cases(path: Path) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _print_table(title: str, rows: list[tuple[str, list[float]]], ks: list[int]) -> None:
    """Print a pretty metric table."""
    col_w = 8
    label_w = 20
    header_ks = "".join(f"@{k:>{col_w - 1}}" for k in ks)
    print(f"\n  {title}")
    print(f"  {'Metric':<{label_w}}{header_ks}")
    print(f"  {'-' * label_w}" + "-" * (col_w * len(ks)))
    for label, vals in rows:
        val_str = "".join(f"{v:>{col_w}.3f}" for v in vals)
        print(f"  {label:<{label_w}}{val_str}")


def _breakdown_table(per_query: list[dict], field: str, ks: list[int]) -> dict:
    """Group per_query rows by a metadata field and compute mean metrics."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in per_query:
        key = str(row.get(field, "unknown") or "unknown")
        groups[key].append(row)
    result = {}
    for key, rows in sorted(groups.items()):
        group_metrics: dict[str, float] = {}
        for k in ks:
            group_metrics[f"hit@{k}"]    = _mean([r["metrics"][f"hit@{k}"]    for r in rows])
            group_metrics[f"recall@{k}"] = _mean([r["metrics"][f"recall@{k}"] for r in rows])
            group_metrics[f"mrr@{k}"]    = _mean([r["metrics"][f"mrr@{k}"]    for r in rows])
            group_metrics[f"ndcg@{k}"]   = _mean([r["metrics"][f"ndcg@{k}"]   for r in rows])
        result[key] = {"n": len(rows), "metrics": group_metrics}
    return result


def run_eval(args: argparse.Namespace) -> bool:
    """PART 2: Retrieval evaluation. Returns True if all targets met."""
    print("\n" + "=" * 65)
    print("  PART 2 — Retrieval Evaluation")
    print("=" * 65)

    queries_path = Path(args.queries)
    out_path     = Path(args.out)

    if not queries_path.exists():
        print(f"ERROR: queries file not found: {queries_path}", file=sys.stderr)
        sys.exit(1)

    cases = _load_query_cases(queries_path)

    # Optional filters
    if args.lang:
        cases = [c for c in cases if c.get("language") == args.lang]
    if args.trust:
        cases = [c for c in cases if c.get("trust_level") == args.trust]

    print(f"  Queries loaded: {len(cases)} | mode={args.mode} | top_k={args.top_k}")

    retriever, reranker = _build_retriever(args.mode)

    # Đọc production settings để các tham số retrieval khớp 100% với production.
    # _build_retriever đã insert src vào sys.path nên import được ngay.
    try:
        from acne_llm.config import settings as _prod_settings
        min_score    = float(getattr(_prod_settings, "chat_min_citation_score", 0.25))
        rerank_top_k = int(getattr(_prod_settings, "chat_rerank_top_k", getattr(args, "rerank_top_k", 3)))
        print(f"  Production settings: min_score={min_score}  rerank_top_k={rerank_top_k}")
    except Exception as _se:
        min_score    = 0.25
        rerank_top_k = getattr(args, "rerank_top_k", 3)
        print(f"  Production settings: unavailable ({_se}), using defaults min_score={min_score} rerank_top_k={rerank_top_k}")

    ks = [1, 3, 5, 10]
    per_query: list[dict] = []
    hit_scores:    dict[int, list[float]] = {k: [] for k in ks}
    recall_scores: dict[int, list[float]] = {k: [] for k in ks}
    mrr_scores:    dict[int, list[float]] = {k: [] for k in ks}
    ndcg_scores:   dict[int, list[float]] = {k: [] for k in ks}
    skipped = 0

    # Incremental JSONL result file
    results_path = out_path.parent / "rag_eval_results.jsonl"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_fh = open(results_path, "w", encoding="utf-8")

    # ── Pipeline preprocessing (y chang production intake.py) ──────────────────
    # Bước ①: prepare_user_text — NFC + teencode expand + tạo no-accent twin
    # Bước ②: normalize_chat_message — extract clinical context → UserInput
    #           (nhận cả clean_text lẫn clean_text_no_accent để dual-pattern matching)
    # Bước ③: build_retrieval_query_from_user — ghép structured context + clean_text
    #          ← production (intake.py) luôn gọi hàm này với clean_text_normalized=clean_text,
    #            không dùng user.description thuần.
    # Không dùng ClinicalPlanner (bước ⑦) vì eval query là one-turn knowledge-type,
    # production cũng không gọi planner cho knowledge intent đơn giản.
    try:
        from acne_llm.chat.preprocess import prepare_user_text
        from acne_llm.chat.normalizer import normalize_chat_message
        from acne_llm.utils.retrieval_query import build_retrieval_query_from_user
        _pipeline_preprocess = True
        print("  Pipeline preprocess: ON (① prepare_user_text + ② normalize_chat_message + ③ build_retrieval_query_from_user)")
    except ImportError as _e:
        _pipeline_preprocess = False
        print(f"  Pipeline preprocess: OFF (import failed: {_e})")

    # ── Chunk filters y chang production (_retrieval.py) ────────────────────────
    try:
        from acne_llm.utils.chunk_filter import drop_noisy_chunks, drop_query_mismatched_chunks
        _chunk_filter_available = True
        print("  Chunk filters: ON (drop_noisy_chunks + drop_query_mismatched_chunks)")
    except ImportError as _ef:
        _chunk_filter_available = False
        print(f"  Chunk filters: OFF (import failed: {_ef})")

    def _prepare_query(raw: str) -> str:
        """Mirror đúng production pipeline: ① prepare_user_text → ② normalize → ③ build_retrieval_query_from_user.

        Production (intake.py → run_intake):
          1. prepare_user_text(raw) → PreparedText(clean_text, clean_text_no_accent, teencode_replaced)
          2. normalize_chat_message(raw, mode, clean_text, clean_text_no_accent) → UserInput
          3. build_retrieval_query_from_user(user, clean_text_normalized=clean_text) → query string

        Eval phải làm y chang để query gửi vào retriever khớp với lúc production retrieve.
        """
        if not _pipeline_preprocess:
            return raw
        # Bước ①: preprocess + teencode + tạo no-accent twin
        prepared = prepare_user_text(raw)
        clean_text = prepared.clean_text
        clean_text_no_accent = prepared.clean_text_no_accent
        # Bước ②: extract context/clinical → UserInput
        #   raw truyền vào để light-normalize làm description (giữ emphasis)
        #   clean_text + clean_text_no_accent dùng nội bộ cho dual-pattern regex
        user_input = normalize_chat_message(
            raw,
            mode="hybrid",
            clean_text=clean_text,
            clean_text_no_accent=clean_text_no_accent,
        )
        # Bước ③: build query giàu context y chang production
        #   clean_text_normalized truyền vào để query có text đầy đủ bên cạnh structured parts.
        #   Nếu không extract được gì, hàm trả về chỉ clean_text (giống hành vi cũ).
        return build_retrieval_query_from_user(user_input, clean_text_normalized=clean_text)

    # ── Ground truth expansion via semantic similarity ───────────────────────────
    # Với mỗi chunk gốc, query Chroma bằng embedding của chunk đó → lấy thêm chunk
    # có cosine similarity >= GT_EXPAND_THRESHOLD (chặt, tránh false positive).
    # Chỉ expand nếu tìm được >= GT_EXPAND_MIN_HITS chunk liên quan (kể cả chunk gốc).
    # File .jsonl giữ nguyên — expansion chỉ xảy ra in-memory lúc eval.
    GT_EXPAND_THRESHOLD = 0.90   # cosine similarity >= 0.90 → distance <= 0.10
    GT_EXPAND_MAX_DIST  = 1.0 - GT_EXPAND_THRESHOLD  # = 0.10
    GT_EXPAND_MIN_HITS  = 2      # phải có ít nhất 2 chunk (kể cả gốc) mới dùng expanded set
    GT_EXPAND_TOP_K     = 30     # query Chroma lấy top-30 rồi filter

    _gt_cache: dict[str, set[str]] = {}  # chunk_id → expanded relevant set

    def _expand_ground_truth(seed_ids: set[str]) -> set[str]:
        """Mở rộng ground truth bằng semantic similarity từ Chroma.

        Chỉ hoạt động khi mode=hybrid (có store + embedder). Với sparse mode
        không có embedder nên trả về seed_ids nguyên.
        """
        if args.mode == "sparse":
            return seed_ids

        expanded = set(seed_ids)
        for seed_id in seed_ids:
            if seed_id in _gt_cache:
                expanded |= _gt_cache[seed_id]
                continue

            # Lấy embedding của chunk gốc từ Chroma
            try:
                raw = retriever.store.col.get(
                    ids=[seed_id],
                    include=["embeddings"],
                )
                embeddings = raw.get("embeddings") or []
                if not embeddings or embeddings[0] is None:
                    _gt_cache[seed_id] = {seed_id}
                    continue
                seed_emb = embeddings[0]
            except Exception:
                _gt_cache[seed_id] = {seed_id}
                continue

            # Query Chroma với embedding của chunk gốc
            try:
                result = retriever.store.query(
                    query_embedding=seed_emb,
                    top_k=GT_EXPAND_TOP_K,
                    include_distances=True,
                )
                ids_l   = (result.get("ids")       or [[]])[0]
                dists_l = (result.get("distances")  or [[]])[0]
            except Exception:
                _gt_cache[seed_id] = {seed_id}
                continue

            similar = {
                cid for cid, dist in zip(ids_l, dists_l)
                if float(dist) <= GT_EXPAND_MAX_DIST and cid != seed_id
            }

            # Chỉ dùng expanded set nếu tìm được đủ MIN_HITS (kể cả chunk gốc)
            if len(similar) + 1 >= GT_EXPAND_MIN_HITS:
                full = similar | {seed_id}
            else:
                full = {seed_id}

            _gt_cache[seed_id] = full
            expanded |= full

        return expanded

    print(f"\n  Running {len(cases)} queries...\n")
    try:
        for i, case in enumerate(cases, 1):
            query        = case.get("query", "").strip()
            relevant_ids = set(cid for cid in case.get("relevant_chunk_ids", []) if cid)

            if not query:
                skipped += 1
                continue
            if not relevant_ids:
                skipped += 1
                print(f"  [{i:4d}/{len(cases)}] SKIP (no ground truth): {query[:55]!r}")
                continue

            # Expand ground truth: tìm thêm chunk tương đồng cao (similarity >= 0.90)
            relevant_ids = _expand_ground_truth(relevant_ids)

            # Áp dụng pipeline preprocessing trước khi retrieve
            query = _prepare_query(query)

            t0 = time.perf_counter()
            retrieval = retriever.retrieve(
                query, top_k=args.top_k,
                mode=args.mode if args.mode != "sparse" else "sparse",
            )
            # Rerank + filter y chang production (_retrieval.py → _do_retrieve_and_rerank):
            #   - Nếu có reranker: rerank → filter (cả khi rerank fail thì vẫn filter)
            #   - Nếu không có reranker: filter trực tiếp
            # Lưu ý: production luôn chạy filter dù rerank thành công hay fail.
            if reranker is not None and retrieval.chunks:
                try:
                    retrieval = reranker.rerank(query, retrieval, top_k=rerank_top_k)
                except Exception as _re:
                    pass  # rerank fail → giữ kết quả RRF thô, vẫn filter bên dưới
            # drop_noisy_chunks + drop_query_mismatched_chunks y chang production
            # Áp LUÔN sau rerank (hoặc sau RRF nếu không có reranker), không phân nhánh.
            if _chunk_filter_available and retrieval is not None:
                retrieval = drop_noisy_chunks(retrieval, min_score=min_score)
                if retrieval is not None:
                    retrieval = drop_query_mismatched_chunks(retrieval, query)

            latency_ms = int((time.perf_counter() - t0) * 1000)

            retrieved_ids = [c.chunk_id for c in retrieval.chunks]

            seed_ids = [cid for cid in case.get("relevant_chunk_ids", []) if cid]
            row: dict = {
                "query":            query,
                "relevant":         list(relevant_ids),   # expanded set
                "relevant_seed":    seed_ids,             # chunk gốc từ jsonl
                "relevant_expanded": len(relevant_ids) - len(seed_ids),  # số chunk thêm
                "retrieved":        retrieved_ids,
                "latency_ms":       latency_ms,
                "intent":           case.get("intent", ""),
                "difficulty":       case.get("difficulty", ""),
                "language":         case.get("language", ""),
                "trust_level":      case.get("trust_level", ""),
                "metrics":          {},
            }

            for k in ks:
                r_at_k = _recall_at_k(retrieved_ids, relevant_ids, k)
                m_at_k = _mrr_at_k(retrieved_ids, relevant_ids, k)
                n_at_k = _ndcg_at_k(retrieved_ids, relevant_ids, k)
                hit    = 1.0 if r_at_k > 0 else 0.0

                hit_scores[k].append(hit)
                recall_scores[k].append(r_at_k)
                mrr_scores[k].append(m_at_k)
                ndcg_scores[k].append(n_at_k)

                row["metrics"][f"hit@{k}"]    = round(hit,    4)
                row["metrics"][f"recall@{k}"] = round(r_at_k, 4)
                row["metrics"][f"mrr@{k}"]    = round(m_at_k, 4)
                row["metrics"][f"ndcg@{k}"]   = round(n_at_k, 4)

            per_query.append(row)

            # Flush incrementally so partial results survive crashes
            results_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            results_fh.flush()

            status  = "OK" if row["metrics"]["hit@3"] else "--"
            hits_s  = " ".join(f"h@{k}={row['metrics'][f'hit@{k}']:.0f}" for k in [1, 3, 5])
            mrr_s   = f"mrr@10={row['metrics']['mrr@10']:.3f}"
            ndcg_s  = f"ndcg@5={row['metrics']['ndcg@5']:.3f}"
            lat_s   = f"{latency_ms}ms"
            print(f"  [{i:4d}/{len(cases)}] {status} {hits_s} {mrr_s} {ndcg_s} {lat_s:<7} {query[:45]!r}")

    finally:
        results_fh.close()

    # ── Aggregate summary ──────────────────────────────────────────────────────
    summary: dict = {
        "evaluated":       len(per_query),
        "skipped_no_gt":   skipped,
        "mode":            args.mode,
        "top_k":           args.top_k,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
    }
    for k in ks:
        summary[f"hit@{k}"]    = _mean(hit_scores[k])
        summary[f"recall@{k}"] = _mean(recall_scores[k])
        summary[f"mrr@{k}"]    = _mean(mrr_scores[k])
        summary[f"ndcg@{k}"]   = _mean(ndcg_scores[k])

    # ── Pass/fail checks ───────────────────────────────────────────────────────
    checks = {
        f"hit@3 >= {_TARGET_HIT3}":   summary["hit@3"]  >= _TARGET_HIT3,
        f"hit@5 >= {_TARGET_HIT5}":   summary["hit@5"]  >= _TARGET_HIT5,
        f"mrr@10 >= {_TARGET_MRR10}": summary["mrr@10"] >= _TARGET_MRR10,
        f"ndcg@5 >= {_TARGET_NDCG5}": summary["ndcg@5"] >= _TARGET_NDCG5,
    }
    summary["target_checks"]    = checks
    summary["all_targets_met"]  = all(checks.values())

    # ── Breakdowns by dimension ────────────────────────────────────────────────
    breakdown_intent     = _breakdown_table(per_query, "intent",     ks)
    breakdown_difficulty = _breakdown_table(per_query, "difficulty", ks)
    breakdown_language   = _breakdown_table(per_query, "language",   ks)
    breakdown_trust      = _breakdown_table(per_query, "trust_level", ks)

    # ── Print main table ───────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  RETRIEVAL EVAL REPORT — mode={args.mode} | n={len(per_query)}")
    print("=" * 65)

    metric_rows = [
        ("hit",    [summary[f"hit@{k}"]    for k in ks]),
        ("recall", [summary[f"recall@{k}"] for k in ks]),
        ("mrr",    [summary[f"mrr@{k}"]    for k in ks]),
        ("ndcg",   [summary[f"ndcg@{k}"]   for k in ks]),
    ]
    _print_table("Overall Metrics", metric_rows, ks)

    # ── Print breakdowns ───────────────────────────────────────────────────────
    def _print_breakdown(title: str, breakdown: dict, metric: str = "hit") -> None:
        print(f"\n  -- {title} (hit@3 / hit@5 / mrr@10 / ndcg@5) --")
        for grp, info in breakdown.items():
            m = info["metrics"]
            n_grp = info["n"]
            print(f"    {grp:<20}  n={n_grp:<5}  "
                  f"h@3={m['hit@3']:.3f}  h@5={m['hit@5']:.3f}  "
                  f"mrr@10={m['mrr@10']:.3f}  ndcg@5={m['ndcg@5']:.3f}")

    _print_breakdown("By Intent",      breakdown_intent)
    _print_breakdown("By Difficulty",  breakdown_difficulty)
    _print_breakdown("By Language",    breakdown_language)
    _print_breakdown("By Trust Level", breakdown_trust)

    # ── Target checks ──────────────────────────────────────────────────────────
    print("\n  Target checks:")
    for label, passed in checks.items():
        icon = "PASS" if passed else "FAIL"
        print(f"    [{icon}] {label}")
    overall = "PASS" if summary["all_targets_met"] else "FAIL"
    print(f"\n  Overall: {overall}")
    print("=" * 65 + "\n")

    # ── Save JSON report ───────────────────────────────────────────────────────
    report = {
        "summary":              summary,
        "breakdown_intent":     breakdown_intent,
        "breakdown_difficulty": breakdown_difficulty,
        "breakdown_language":   breakdown_language,
        "breakdown_trust":      breakdown_trust,
        "per_query":            per_query,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Report saved: {out_path}")
    print(f"  Results JSONL: {results_path}")

    return summary["all_targets_met"]


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 HELPERS — End-to-End Backend + DeepSeek Judge Eval
# ══════════════════════════════════════════════════════════════════════════════

_JUDGE_FIELDS = ("accuracy", "safety", "completeness", "tone")


def _post_chat_api(api_url: str, query: str, chat_mode: str, timeout: int) -> dict:
    payload = json.dumps({
        "message": query,
        "mode": chat_mode,
    }).encode("utf-8")
    req = urllib.request.Request(
        api_url.rstrip("/") + "/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _format_chat_answer(payload: dict) -> str:
    """Flatten an AdviseOutput-like response into judge-readable text."""
    if not isinstance(payload, dict):
        return str(payload)

    direct = payload.get("answer") or payload.get("response") or payload.get("text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts: list[str] = []
    disclaimer = payload.get("disclaimer")
    if isinstance(disclaimer, str) and disclaimer.strip():
        parts.append(disclaimer.strip())

    causes = payload.get("causes") or []
    if isinstance(causes, list):
        parts.extend(str(item).strip() for item in causes if str(item).strip())

    recommendations = payload.get("recommendations") or []
    if isinstance(recommendations, list):
        for rec in recommendations:
            if isinstance(rec, dict):
                action = str(rec.get("action", "")).strip()
                rationale = str(rec.get("rationale", "") or "").strip()
                if action and rationale:
                    parts.append(f"{action} ({rationale})")
                elif action:
                    parts.append(action)
            elif str(rec).strip():
                parts.append(str(rec).strip())

    red_flags = payload.get("red_flags") or []
    if isinstance(red_flags, list):
        for flag in red_flags:
            if isinstance(flag, dict):
                text = str(flag.get("flag", "")).strip()
                reason = str(flag.get("reason", "") or "").strip()
                if text and reason:
                    parts.append(f"Canh bao: {text} ({reason})")
                elif text:
                    parts.append(f"Canh bao: {text}")
            elif str(flag).strip():
                parts.append(f"Canh bao: {str(flag).strip()}")

    return "\n".join(parts).strip()


def _build_judge_prompt(question: str, answer: str, expected_scope: str | None = None) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        env = Environment(
            loader=FileSystemLoader(str(ROOT / "config" / "prompts")),
            autoescape=select_autoescape(default=False),
        )
        template = env.get_template("judge.j2")
        return template.render(
            question=question,
            answer=answer,
            expected_scope=expected_scope or "",
        )
    except Exception:
        scope_note = ""
        if expected_scope == "out_of_scope":
            scope_note = "\nThis question is out of scope; a correct answer should refuse politely."
        return (
            "You are grading an acne-advice chatbot. Score accuracy, safety, "
            "completeness, and tone from 1 to 5. Return only JSON with those "
            "four integer fields and a short reasoning string.\n\n"
            f"Question:\n{question}\n\nAnswer:\n{answer}{scope_note}"
        )


def _parse_judge_response(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(_extract_json_object(raw))
    except Exception:
        return None

    parsed: dict = {}
    for field in _JUDGE_FIELDS:
        try:
            value = int(data[field])
        except Exception:
            return None
        if value < 1 or value > 5:
            return None
        parsed[field] = value

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        return None
    parsed["reasoning"] = reasoning.strip()
    return parsed


def _latency_summary_ms(latencies: list[int]) -> dict[str, int | float]:
    if not latencies:
        return {"mean": 0, "p50": 0, "p95": 0, "n": 0}
    values = sorted(latencies)
    p50 = values[len(values) // 2]
    p95 = values[int((len(values) - 1) * 0.95)]
    return {
        "mean": round(sum(values) / len(values), 2),
        "p50": int(p50),
        "p95": int(p95),
        "n": len(values),
    }


def _avg_judge_scores(rows: list[dict]) -> dict[str, float]:
    averages: dict[str, float] = {}
    for field in _JUDGE_FIELDS:
        values = [
            row["judge_scores"][field]
            for row in rows
            if isinstance(row.get("judge_scores"), dict) and field in row["judge_scores"]
        ]
        averages[field] = _mean([float(v) for v in values])
    return averages


def _expected_scope(case: dict) -> str:
    explicit = str(case.get("expected_scope", "") or "").strip()
    if explicit:
        return explicit
    case_type = str(case.get("case_type", "") or "").lower()
    raw_tags = case.get("tags", []) or []
    tags = raw_tags if isinstance(raw_tags, str) else " ".join(str(tag) for tag in raw_tags)
    tags = tags.lower()
    if case_type in {"ood", "out_of_scope"} or "out_of_scope" in tags or "ood" in tags:
        return "out_of_scope"
    return "in_scope"


def run_e2e_eval(args: argparse.Namespace) -> bool:
    """PART 3: Backend /chat generation + optional DeepSeek judge."""
    print("\n" + "=" * 65)
    print("  PART 3 — E2E Backend + DeepSeek Judge Evaluation")
    print("=" * 65)

    queries_path = Path(args.queries)
    out_path = Path(args.out)
    if not queries_path.exists():
        print(f"ERROR: queries file not found: {queries_path}", file=sys.stderr)
        sys.exit(1)

    cases = _load_query_cases(queries_path)
    if args.lang:
        cases = [c for c in cases if c.get("language") == args.lang]
    if args.trust:
        cases = [c for c in cases if c.get("trust_level") == args.trust]

    print(
        f"  Queries loaded: {len(cases)} | api={args.api_url} | "
        f"chat_mode={args.chat_mode} | judge={'off' if args.no_judge else 'DeepSeek'}"
    )

    api_key = base_url = judge_model = ""
    if not args.no_judge:
        api_key, base_url, judge_model = _read_env_credentials()
        if not api_key:
            print("ERROR: DEEPSEEK_API_KEY not found in .env or environment", file=sys.stderr)
            sys.exit(1)
        if args.deepseek_model:
            judge_model = args.deepseek_model

    out_path.parent.mkdir(parents=True, exist_ok=True)
    results_path = out_path.parent / "e2e_eval_results.jsonl"
    per_query: list[dict] = []
    chat_latencies: list[int] = []

    print(f"\n  Running {len(cases)} backend chat requests...\n")
    with open(results_path, "w", encoding="utf-8") as results_fh:
        for i, case in enumerate(cases, 1):
            query = str(case.get("query", "")).strip()
            if not query:
                continue

            row: dict = {
                "query": query,
                "language": case.get("language", ""),
                "intent": case.get("intent", ""),
                "difficulty": case.get("difficulty", ""),
                "trust_level": case.get("trust_level", ""),
                "expected_scope": _expected_scope(case),
                "relevant": [cid for cid in case.get("relevant_chunk_ids", []) if cid],
            }

            try:
                t0 = time.perf_counter()
                chat_payload = _post_chat_api(args.api_url, query, args.chat_mode, args.timeout)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                chat_latencies.append(latency_ms)
                answer = _format_chat_answer(chat_payload)
                used_chunks = chat_payload.get("used_chunks", []) if isinstance(chat_payload, dict) else []

                row.update({
                    "chat_status": "ok",
                    "answer": answer,
                    "raw_response": chat_payload,
                    "used_chunks": used_chunks,
                    "mode_used": chat_payload.get("mode", "") if isinstance(chat_payload, dict) else "",
                    "model_name": chat_payload.get("model_name", "") if isinstance(chat_payload, dict) else "",
                    "latency_ms": latency_ms,
                })
            except Exception as exc:
                row.update({
                    "chat_status": "error",
                    "error": str(exc),
                    "used_chunks": [],
                    "latency_ms": 0,
                })
                per_query.append(row)
                results_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                results_fh.flush()
                print(f"  [{i:4d}/{len(cases)}] CHAT-ERR {str(exc)[:70]}")
                continue

            if args.no_judge:
                row["judge_status"] = "skipped"
            else:
                prompt = _build_judge_prompt(query, row["answer"], row["expected_scope"])
                raw_judge = _call_deepseek(
                    prompt,
                    api_key,
                    base_url,
                    judge_model,
                    timeout=args.timeout,
                    temperature=0.0,
                    max_tokens=512,
                )
                parsed = _parse_judge_response(raw_judge)
                if parsed:
                    row["judge_status"] = "ok"
                    row["judge_scores"] = {field: parsed[field] for field in _JUDGE_FIELDS}
                    row["judge_reasoning"] = parsed["reasoning"]
                else:
                    row["judge_status"] = "error"
                    row["judge_raw"] = raw_judge or ""

                if args.judge_delay > 0 and i < len(cases):
                    time.sleep(args.judge_delay)

            per_query.append(row)
            results_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            results_fh.flush()

            judge_label = row.get("judge_status", "-")
            scores = row.get("judge_scores") or {}
            score_s = (
                " ".join(f"{k}={scores[k]}" for k in _JUDGE_FIELDS)
                if scores else f"judge={judge_label}"
            )
            print(
                f"  [{i:4d}/{len(cases)}] OK {score_s} "
                f"{row['latency_ms']}ms {query[:45]!r}"
            )

    chat_succeeded = sum(1 for row in per_query if row.get("chat_status") == "ok")
    chat_failed = sum(1 for row in per_query if row.get("chat_status") == "error")
    judge_succeeded = sum(1 for row in per_query if row.get("judge_status") == "ok")
    judge_failed = sum(1 for row in per_query if row.get("judge_status") == "error")
    rows_with_chunks = sum(1 for row in per_query if row.get("used_chunks"))
    avg_scores = _avg_judge_scores(per_query)

    if args.no_judge:
        checks = {"chat_failures == 0": chat_failed == 0}
    else:
        checks = {
            "chat_failures == 0": chat_failed == 0,
            "judge_failures == 0": judge_failed == 0,
        }
        checks.update({
            f"avg_{field} >= 4.0": avg_scores[field] >= 4.0
            for field in _JUDGE_FIELDS
        })

    summary = {
        "evaluated": len(per_query),
        "mode": "e2e",
        "api_url": args.api_url,
        "chat_mode": args.chat_mode,
        "judge_enabled": not args.no_judge,
        "judge_model": judge_model if not args.no_judge else "",
        "chat_succeeded": chat_succeeded,
        "judge_succeeded": judge_succeeded,
        "errors": chat_failed + judge_failed,
        "chat_failed": chat_failed,
        "judge_failed": judge_failed,
        "avg_scores": avg_scores,
        "citation_coverage": round(rows_with_chunks / chat_succeeded, 4) if chat_succeeded else 0.0,
        "latency_ms": _latency_summary_ms(chat_latencies),
        "target_checks": checks,
        "all_targets_met": all(checks.values()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print("\n" + "=" * 65)
    print(f"  E2E EVAL REPORT — n={len(per_query)}")
    print("=" * 65)
    print(f"  Chat ok/error : {chat_succeeded}/{chat_failed}")
    if args.no_judge:
        print("  Judge         : skipped")
    else:
        print(f"  Judge ok/error: {judge_succeeded}/{judge_failed}")
        print("  Avg scores    : " + " ".join(f"{k}={v:.3f}" for k, v in avg_scores.items()))
    lat = summary["latency_ms"]
    print(f"  Latency       : mean={lat['mean']}ms p50={lat['p50']}ms p95={lat['p95']}ms")
    print(f"  Citations     : {summary['citation_coverage']:.3f}")
    print("\n  Target checks:")
    for label, passed in checks.items():
        icon = "PASS" if passed else "FAIL"
        print(f"    [{icon}] {label}")
    overall = "PASS" if summary["all_targets_met"] else "FAIL"
    print(f"\n  Overall: {overall}")
    print("=" * 65 + "\n")

    report = {
        "summary": summary,
        "per_query": per_query,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Report saved: {out_path}")
    print(f"  Results JSONL: {results_path}")

    return summary["all_targets_met"]


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolidated RAG eval: query generation (DeepSeek) + retrieval evaluation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ── Paths ──────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--chunks", default=str(DEFAULT_CHUNKS),
        help="Path to chunks.jsonl",
    )
    parser.add_argument(
        "--queries", default=str(DEFAULT_QUERIES),
        help="Path to queries JSONL (output of generation / input to eval)",
    )
    parser.add_argument(
        "--out", default=str(DEFAULT_OUT),
        help="Path for JSON eval report output",
    )

    # ── Generation options ─────────────────────────────────────────────────────
    parser.add_argument(
        "--n", type=int, default=1000,
        help="Number of queries to generate",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds to wait between DeepSeek API calls",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for stratified sampling",
    )

    # ── Shared filters ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--lang", choices=["vi", "en"], default=None,
        help="Filter by language (vi or en)",
    )
    parser.add_argument(
        "--trust", choices=["high", "medium"], default=None,
        help="Filter by trust level (high or medium)",
    )

    # ── Eval options ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--mode", choices=["sparse", "hybrid", "e2e"], default="hybrid",
        help="Eval mode: sparse/hybrid retrieval, or e2e backend + judge",
    )
    parser.add_argument(
        "--top-k", type=int, default=10, dest="top_k",
        help="Number of chunks to retrieve per query (before rerank, default=10 y chang settings.chat_retrieve_top_k production)",
    )
    parser.add_argument(
        "--rerank-top-k", type=int, default=3, dest="rerank_top_k",
        help="Number of chunks to keep after reranking (default: 3, y chang chat_rerank_top_k production)",
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8000",
        help="Backend API base URL for --mode e2e",
    )
    parser.add_argument(
        "--chat-mode", choices=["auto", "hybrid", "llm_only"], default="hybrid",
        help="Chat generation mode sent to backend for --mode e2e",
    )
    parser.add_argument(
        "--timeout", type=int, default=180,
        help="Timeout in seconds for backend chat and DeepSeek judge calls",
    )
    parser.add_argument(
        "--no-judge", action="store_true",
        help="In --mode e2e, call backend only and skip DeepSeek judging",
    )
    parser.add_argument(
        "--judge-delay", type=float, default=0.0,
        help="Seconds to wait between DeepSeek judge calls in --mode e2e",
    )
    parser.add_argument(
        "--deepseek-model", default="",
        help="Override DEEPSEEK_MODEL for e2e judge",
    )

    # ── Control flags ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--skip-gen", action="store_true",
        help="Skip generation, use existing queries file",
    )
    parser.add_argument(
        "--skip-eval", action="store_true",
        help="Skip eval, only generate queries",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print sample prompt only — no API calls, no eval",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    random.seed(args.seed)

    if args.dry_run:
        # dry-run: generation print only, no eval
        run_generation(args)
        return

    if not args.skip_gen:
        run_generation(args)

    if args.skip_eval:
        return

    targets_met = run_e2e_eval(args) if args.mode == "e2e" else run_eval(args)
    sys.exit(0 if targets_met else 1)


if __name__ == "__main__":
    main()
