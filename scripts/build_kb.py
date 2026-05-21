"""Build Knowledge Base pipeline.

3 bước độc lập, có thể resume từng bước:
  Step 1: chunk  -- documents.jsonl -> chunks.jsonl
  Step 2: embed  -- chunks.jsonl -> ChromaDB (vector index)
  Step 3: bm25   -- chunks.jsonl -> bm25_index.pkl (sparse index)

Chay:
  python scripts/build_kb.py            # chay ca 3 buoc
  python scripts/build_kb.py --step chunk
  python scripts/build_kb.py --step embed
  python scripts/build_kb.py --step bm25
  python scripts/build_kb.py --step embed --batch-size 64
  python scripts/build_kb.py --min-quality 0.3
  python scripts/build_kb.py --force     # rebuild du da co output
  python scripts/build_kb.py --min-chunk-chars 80  # filter short chunks
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

# -- Resolve project root & sys.path -----------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "src").exists():
    ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO", colorize=False,
           format="{time:HH:mm:ss} | {level:<8} | {message}")

from acne_llm.rag.chunker import VietnameseChunker
from acne_llm.rag.cleaning import clean_vi_text
from acne_llm.rag.embedder import Embedder
from acne_llm.rag.sparse import BM25Index
from acne_llm.rag.vectorstore import ChromaStore
from acne_llm.schemas.kb import DocumentRaw, KBChunk

# -- Chunk quality filters ---------------------------------------------------

_ACNE_SIGNALS_VI = re.compile(
    r"mụn|trứng cá|trung ca|bọc|đầu đen|đầu trắng|mủ|sẹo mụn|"
    r"da liễu|da dầu|nhờn|sebum|nang lông|viêm nang|"
    r"benzoyl|salicylic|retinoid|retinol|tretinoin|isotretinoin|adapalene|"
    r"niacinamide|azelaic|comedone|bã nhờn|kháng sinh"
)
_ACNE_SIGNALS_EN = re.compile(
    r"acne|pimple|blackhead|whitehead|comedone|papule|pustule|nodule|cyst(?:ic)?\s*acne|"
    r"sebaceous|sebum|folliculitis|dermatolog|skin barrier|"
    r"benzoyl|salicylic|retinoid|retinol|tretinoin|isotretinoin|adapalene|doxycycline|"
    r"minocycline|clindamycin|spironolactone|azelaic|niacinamide"
)

_OFF_TOPIC_VI = re.compile(
    r"tắm trắng|trắng da toàn thân|làm trắng|trị thâm (?:đầu gối|khuỷu tay|nách|mông|bẹn)|"
    r"rụng tóc|mọc tóc|trị hói|son môi|mascara|nước hoa|trang điểm|makeup|"
    r"giảm cân|tăng cân|ăn kiêng|dinh dưỡng thể hình|"
    r"mang thai.*dinh dưỡng|bà bầu.*ăn|sữa.*trẻ em|tiểu đường|huyết áp|"
    r"trị nám (?:toàn thân|tay|chân)|tàn nhang|lão hóa|nếp nhăn|chống nắng toàn thân"
)
_OFF_TOPIC_EN = re.compile(
    r"skin[-\s]?whitening|skin[-\s]?bleaching|brightening|anti[-\s]?aging|anti[-\s]?wrinkle|"
    r"hair[-\s]?loss|hair[-\s]?growth|weight[-\s]?loss|"
    r"lipstick|mascara|perfume|make[-\s]?up tutorial|"
    r"wart|psoriasis|eczema|melanoma|skin[-\s]?cancer"
)


def _is_acne_chunk(text: str, language: str = "vi") -> bool:
    """HIGH-2: Filter chunks by acne relevance.

    Returns True only if the chunk contains acne-specific signals and
    does NOT contain off-topic content (skincare/beauty not related to acne).
    """
    text_lower = text.lower()

    if language == "vi":
        if not _ACNE_SIGNALS_VI.search(text_lower):
            return False
        if _OFF_TOPIC_VI.search(text_lower):
            return False
    else:
        if not _ACNE_SIGNALS_EN.search(text_lower):
            return False
        if _OFF_TOPIC_EN.search(text_lower):
            return False

    return True

# -- Paths -------------------------------------------------------------------
DOCS_PATH   = ROOT / "data" / "raw" / "documents.jsonl"
CHUNKS_PATH = ROOT / "data" / "raw" / "chunks.jsonl"
CHROMA_DIR  = ROOT / "data" / "chroma_db"
BM25_PATH   = ROOT / "data" / "bm25_index.pkl"


# ============================================================================
# Step 1 -- Chunk
# ============================================================================

def step_chunk(min_quality: float = 0.3, min_chunk_chars: int = 50,
               force: bool = False) -> int:
    """documents.jsonl -> chunks.jsonl"""
    if CHUNKS_PATH.exists() and not force:
        n = sum(1 for _ in open(CHUNKS_PATH, encoding="utf-8"))
        if n > 0:
            logger.info(f"[chunk] chunks.jsonl da ton tai ({n} chunks). Dung --force de build lai.")
            return n
        logger.warning("[chunk] chunks.jsonl dang rong; build lai tu documents.jsonl.")

    if not DOCS_PATH.exists():
        logger.error(f"[chunk] Khong tim thay {DOCS_PATH}")
        sys.exit(1)

    logger.info(f"[chunk] Doc documents tu {DOCS_PATH}")
    docs: list[DocumentRaw] = []
    skipped = 0

    with open(DOCS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                doc = DocumentRaw(**json.loads(line))
                if doc.quality_score < min_quality:
                    skipped += 1
                    continue
                docs.append(doc)
            except Exception as e:
                logger.warning(f"[chunk] Bo qua doc loi: {e}")

    logger.info(f"[chunk] Loaded {len(docs)} docs (bo {skipped} docs quality < {min_quality})")
    if not docs:
        raise RuntimeError(
            f"[chunk] 0 valid documents after filtering. Keeping existing chunks untouched."
        )

    chunker = VietnameseChunker(chunk_size=200, overlap=40, min_size=50)
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CHUNKS_PATH.with_name(f"{CHUNKS_PATH.name}.tmp")

    total = 0
    filtered_short = 0
    filtered_offtopic = 0
    t0 = time.time()

    try:
        with open(tmp_path, "w", encoding="utf-8") as out:
            for idx, doc in enumerate(docs):
                text = clean_vi_text(doc.text)
                if not text:
                    continue

                raw_chunks = chunker.chunk(text)
                n = len(raw_chunks)
                lang = doc.source.language

                for i, chunk_text in enumerate(raw_chunks):
                    # HIGH-2: Filter short chunks
                    if len(chunk_text) < min_chunk_chars:
                        filtered_short += 1
                        continue
                    # HIGH-2: Filter non-acne chunks
                    if not _is_acne_chunk(chunk_text, lang):
                        filtered_offtopic += 1
                        continue

                    chunk = KBChunk(
                        chunk_id=f"{doc.doc_id}::{i:04d}",
                        doc_id=doc.doc_id,
                        text=chunk_text,
                        text_len=len(chunk_text),
                        position=i,
                        prev_chunk_id=f"{doc.doc_id}::{i-1:04d}" if i > 0 else None,
                        next_chunk_id=f"{doc.doc_id}::{i+1:04d}" if i < n - 1 else None,
                        url=doc.url,
                        title=doc.title,
                        source_name=doc.source.source_name,
                        trust_level=doc.source.trust_level,
                        language=doc.source.language,
                        categories=doc.categories,
                        tags=doc.tags,
                    )
                    out.write(chunk.model_dump_json() + "\n")
                    total += 1

                if idx > 0 and idx % 500 == 0:
                    logger.info(f"[chunk] {idx}/{len(docs)} docs processed, {total} chunks...")
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    if total == 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            "[chunk] 0 chunks after filtering. Keeping existing chunks untouched."
        )

    tmp_path.replace(CHUNKS_PATH)

    elapsed = time.time() - t0
    logger.success(f"[chunk] Xong! {total} chunks tu {len(docs)} docs trong {elapsed:.1f}s")
    if filtered_short:
        logger.info(f"[chunk] Filtered: {filtered_short} chunks too short (< {min_chunk_chars} chars)")
    if filtered_offtopic:
        logger.info(f"[chunk] Filtered: {filtered_offtopic} chunks off-topic (non-acne)")
    logger.success(f"[chunk] -> {CHUNKS_PATH}")
    return total


# ============================================================================
# Step 2 -- Embed -> ChromaDB
# ============================================================================

def step_embed(batch_size: int = 32, force: bool = False) -> int:
    """chunks.jsonl -> ChromaDB"""
    if not CHUNKS_PATH.exists():
        logger.error("[embed] chunks.jsonl chua co. Chay --step chunk truoc.")
        sys.exit(1)

    # Count expected chunks to detect incomplete embed (e.g. interrupted mid-run)
    total_expected = sum(1 for line in open(CHUNKS_PATH, encoding="utf-8") if line.strip())
    if total_expected == 0:
        raise RuntimeError("[embed] chunks.jsonl is empty; refusing to build an empty vector index.")

    if force and CHROMA_DIR.exists():
        logger.info(f"[embed] --force: xoa ChromaDB cu tai {CHROMA_DIR}")
        try:
            shutil.rmtree(CHROMA_DIR)
        except Exception as e:
            raise RuntimeError(
                f"[embed] Khong xoa duoc ChromaDB cu ({CHROMA_DIR}). "
                f"Dong API/server dang dung KB roi chay lai. Loi goc: {e}"
            ) from e

    store = ChromaStore(persist_dir=str(CHROMA_DIR))
    existing = store.count()

    if existing > 0 and not force:
        if existing == total_expected:
            logger.info(
                f"[embed] ChromaDB day du {existing}/{total_expected} vectors. "
                f"Dung --force de embed lai."
            )
            return existing
        if existing < total_expected:
            logger.warning(
                f"[embed] ChromaDB co {existing}/{total_expected} vectors -- "
                f"embed bi interrupt truoc do. Tiep tuc embed..."
            )
            # fall through to re-embed (upsert is idempotent)
        else:
            raise RuntimeError(
                f"[embed] ChromaDB co {existing} vectors nhung chunks chi co "
                f"{total_expected}. Index co the bi stale; chay lai voi --force."
            )

    logger.info(f"[embed] Doc chunks tu {CHUNKS_PATH}")
    chunks: list[KBChunk] = []
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(KBChunk(**json.loads(line)))
            except Exception as e:
                logger.warning(f"[embed] Bo qua chunk loi: {e}")

    logger.info(f"[embed] {len(chunks)} chunks can embed")
    if len(chunks) != total_expected:
        raise RuntimeError(
            f"[embed] Only loaded {len(chunks)}/{total_expected} chunks. "
            f"Fix invalid lines in chunks.jsonl before embedding."
        )

    try:
        from config.settings import settings
        emb_model = getattr(settings, "embedding_model_multilingual", "") or settings.embedding_model
        device = settings.device
    except Exception:
        emb_model = "AITeamVN/Vietnamese_Embedding"
        device = "cpu"

    embedder = Embedder(model_name=emb_model, device=device, batch_size=batch_size)

    UPSERT_BATCH = batch_size * 4
    total_done = 0
    t0 = time.time()

    for i in range(0, len(chunks), UPSERT_BATCH):
        batch = chunks[i: i + UPSERT_BATCH]
        texts = [c.text for c in batch]
        batch_num = i // UPSERT_BATCH + 1
        total_batches = (len(chunks) - 1) // UPSERT_BATCH + 1

        logger.info(f"[embed] Batch {batch_num}/{total_batches} ({i} -> {i + len(batch)})...")

        try:
            embs = embedder.embed_passages(texts)
            store.upsert(batch, embs.tolist())
            total_done += len(batch)
        except Exception as e:
            raise RuntimeError(f"[embed] Loi tai batch {batch_num}: {e}") from e

        elapsed = time.time() - t0
        rate = total_done / elapsed if elapsed > 0 else 1
        eta = (len(chunks) - total_done) / rate
        logger.info(f"[embed] {total_done}/{len(chunks)} | {rate:.0f} chunks/s | ETA {eta/60:.1f} phut")

    final = store.count()
    if final != len(chunks):
        raise RuntimeError(
            f"[embed] Incomplete vector index: ChromaDB has {final}/{len(chunks)} vectors."
        )
    logger.success(f"[embed] Xong! ChromaDB co {final} vectors -> {CHROMA_DIR}")
    return final


# ============================================================================
# Step 3 -- BM25 sparse index
# ============================================================================

def step_bm25(force: bool = False) -> int:
    """chunks.jsonl -> bm25_index.pkl"""
    if BM25_PATH.exists() and not force:
        idx = BM25Index.load(str(BM25_PATH))
        n = len(idx.chunk_ids)
        logger.info(f"[bm25] bm25_index.pkl da ton tai ({n} chunks). Dung --force de rebuild.")
        return n

    if not CHUNKS_PATH.exists():
        logger.error("[bm25] chunks.jsonl chua co. Chay --step chunk truoc.")
        sys.exit(1)

    logger.info(f"[bm25] Doc chunks tu {CHUNKS_PATH}")
    chunk_ids: list[str] = []
    texts: list[str] = []

    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
                chunk_ids.append(c["chunk_id"])
                texts.append(c["text"])
            except Exception as e:
                logger.warning(f"[bm25] Bo qua dong loi: {e}")

    logger.info(f"[bm25] Build BM25 tren {len(chunk_ids)} chunks...")
    if not chunk_ids:
        raise RuntimeError("[bm25] chunks.jsonl is empty; refusing to build an empty BM25 index.")
    t0 = time.time()

    idx = BM25Index()
    idx.build(chunk_ids, texts)
    BM25_PATH.parent.mkdir(parents=True, exist_ok=True)
    idx.save(str(BM25_PATH))

    elapsed = time.time() - t0
    logger.success(f"[bm25] Xong! {len(chunk_ids)} chunks trong {elapsed:.1f}s -> {BM25_PATH}")
    return len(chunk_ids)


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build AcneLLM Knowledge Base")
    p.add_argument(
        "--step",
        choices=["chunk", "embed", "bm25", "all"],
        default="all",
        help="Buoc can chay (default: all)",
    )
    p.add_argument(
        "--min-quality",
        type=float,
        default=0.5,
        dest="min_quality",
        help="Loc docs co quality_score < gia tri nay (default: 0.5)",
    )
    p.add_argument(
        "--min-chunk-chars",
        type=int,
        default=50,
        dest="min_chunk_chars",
        help="Loc chunk co do dai < gia tri nay (default: 50)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=32,
        dest="batch_size",
        help="Batch size cho embedding (default: 32)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Rebuild du output da ton tai",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("=" * 60)
    logger.info("AcneLLM -- Build Knowledge Base")
    logger.info(f"  docs    : {DOCS_PATH}")
    logger.info(f"  chunks  : {CHUNKS_PATH}")
    logger.info(f"  chroma  : {CHROMA_DIR}")
    logger.info(f"  bm25    : {BM25_PATH}")
    logger.info(f"  step    : {args.step}")
    logger.info(f"  min-q   : {args.min_quality}")
    logger.info(f"  min-chk : {args.min_chunk_chars}")
    logger.info(f"  force   : {args.force}")
    logger.info("=" * 60)

    t_total = time.time()

    if args.step in ("chunk", "all"):
        n = step_chunk(min_quality=args.min_quality, min_chunk_chars=args.min_chunk_chars, force=args.force)
        logger.info(f"[chunk] => {n} chunks")

    if args.step in ("embed", "all"):
        n = step_embed(batch_size=args.batch_size, force=args.force)
        logger.info(f"[embed] => {n} vectors trong ChromaDB")

    if args.step in ("bm25", "all"):
        n = step_bm25(force=args.force)
        logger.info(f"[bm25] => {n} chunks indexed")

    elapsed = time.time() - t_total
    logger.success(f"Done! Tong thoi gian: {elapsed/60:.1f} phut")


if __name__ == "__main__":
    main()
