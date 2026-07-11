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
from acne_llm.schemas.kb import DocumentRaw, KBChunk, infer_source_type

# -- Chunk quality filters ---------------------------------------------------

# Acne signals — VI: mở rộng thêm thuật ngữ điều trị và da liên quan mụn
_ACNE_SIGNALS_VI = re.compile(
    r"mụn|trứng cá|trung ca|bọc|đầu đen|đầu trắng|mủ|sẹo mụn|sẹo thâm|"
    r"da liễu|da dầu|nhờn|sebum|nang lông|viêm nang|lỗ chân lông|"
    r"benzoyl|salicylic|retinoid|retinol|tretinoin|isotretinoin|adapalene|"
    r"niacinamide|azelaic|comedone|bã nhờn|kháng sinh da|"
    r"doxycyclin|minocyclin|clindamycin|spironolacton|tetracyclin|"
    r"tẩy da chết|bha|aha|pha|exfoliat|peeling|"
    r"viêm da|nhiễm khuẩn da|vi khuẩn da|cutibacterium|propionibacterium"
)
# Acne signals — EN: thêm kháng sinh, kỹ thuật điều trị, vi khuẩn
_ACNE_SIGNALS_EN = re.compile(
    r"acne|pimple|blackhead|whitehead|comedone|papule|pustule|nodule|cyst(?:ic)?\s*acne|"
    r"sebaceous|sebum|folliculitis|dermatolog|skin barrier|"
    r"benzoyl|salicylic|retinoid|retinol|tretinoin|isotretinoin|adapalene|doxycycline|"
    r"minocycline|clindamycin|spironolactone|azelaic|niacinamide|tetracycline|"
    r"cutibacterium|propionibacterium|c\.\s*acnes|p\.\s*acnes|"
    r"comedogenic|non-comedogenic|keratolytic|seborrh|"
    r"aha|bha|chemical\s*exfoliat|peeling|photodynamic|laser.*acne|acne.*laser"
)

# Off-topic — chủ đề hoàn toàn không liên quan mụn
_OFF_TOPIC_VI = re.compile(
    r"tắm trắng|trắng da toàn thân|làm trắng da|trị thâm (?:đầu gối|khuỷu tay|nách|mông|bẹn)|"
    r"rụng tóc|mọc tóc|trị hói|son môi|mascara|nước hoa|trang điểm nền|makeup tutorial|"
    r"giảm cân|tăng cân|ăn kiêng thể hình|dinh dưỡng thể hình|"
    r"mang thai.*dinh dưỡng|bà bầu.*ăn uống|sữa.*trẻ em|tiểu đường|huyết áp cao|"
    r"trị nám (?:toàn thân|tay|chân)|tàn nhang|lão hóa da|nếp nhăn|chống lão hóa|"
    r"chống nắng toàn thân|ung thư da|vảy nến|chàm|tổ đỉa"
)
_OFF_TOPIC_EN = re.compile(
    r"skin[-\s]?whitening|skin[-\s]?bleaching|skin\s*lightening|anti[-\s]?aging|anti[-\s]?wrinkle|"
    r"hair[-\s]?loss|hair[-\s]?growth|alopecia|weight[-\s]?loss|obesity|"
    r"lipstick|mascara|perfume|make[-\s]?up tutorial|foundation makeup|"
    r"wart|psoriasis|eczema|atopic dermatitis|melanoma|skin[-\s]?cancer|rosacea"
)

# Boilerplate patterns — chunk toàn header/footer/navigation, không có nội dung thực
_BOILERPLATE_RE = re.compile(
    r"^(bài viết được (tham vấn|tư vấn|kiểm duyệt) chuyên môn|"
    r"medically reviewed by|written by [a-z\s]+\s*\||fact.?checked by|"
    r"last (updated|reviewed|medically reviewed)[\s:])",
    re.IGNORECASE,
)
# Advertising/navigation noise thường xuất hiện trong chunk ngắn
_AD_NOISE_RE = re.compile(
    r"advertisem[e]?nt|xem thêm:|đọc thêm:|subscribe|newsletter|"
    r"follow us|share this article|click here to|cookie policy|"
    r"all rights reserved|©\s*\d{4}",
    re.IGNORECASE,
)

# Promo tail patterns — paragraph hoặc câu cuối có hotline/SĐT/địa chỉ vật lý
_PROMO_TAIL_RE = re.compile(
    r'\b0[35789]\d{8}\b|'           # SĐT VN thật: 09x, 03x, 07x, 08x (10 số)
    r'1900\s+\d{2}\s+\d{2}\s+\d{2}|'  # 1900 56 56 56 format (MEDLATEC, etc.)
    r'\bhotline\b|'                  # từ "hotline" bất kỳ
    r'(?:tầng|lầu|số nhà)\s+\d+.*(?:đường|phố|quận|phường)|'  # địa chỉ vật lý
    r'(?:địa chỉ|văn phòng|trụ sở)\s*:\s*\d+\s+\w|'           # Địa chỉ: 123 đường
    r'(?:liên hệ|inbox|nhắn tin)\s+(?:để\s+)?(?:được\s+)?(?:tư vấn|đặt lịch)|'
    r'(?:đặt lịch|book lịch|đặt hẹn)\s+(?:tại|online|ngay|qua)|'
    r'(?:mời\s+)?quý khách|'         # boilerplate Vinmec/MEDLATEC
    r'bấm số.*hotline|đặt lịch trực tiếp|'
    r'tải và đặt lịch|ứng dụng myvinmec|'  # Vinmec app CTA
    r'theo dõi lịch và đặt hẹn|'
    r'tổng đài\s+\d|đường dây nóng\s+\d',  # tổng đài 1900..., đường dây nóng 1900...
    re.IGNORECASE,
)

# Sentence-level split: tách theo dấu câu kết thúc
_SENT_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def _trim_promo_tail(text: str) -> str:
    """Xóa mọi câu chứa hotline/SĐT/địa chỉ quảng cáo — bất kể vị trí.

    Xử lý 2 lớp:
    1. Paragraph level: nếu paragraph chứa noise → tách ra từng câu
    2. Sentence level: drop bất kỳ câu nào chứa promo pattern (không chỉ cuối)
    """
    paragraphs = re.split(r'\n{2,}', text)
    result = []
    for para in paragraphs:
        if not para.strip():
            continue
        if _PROMO_TAIL_RE.search(para):
            # Drop từng câu có noise, giữ câu sạch
            sents = _SENT_SPLIT_RE.split(para.strip())
            clean_sents = [s for s in sents if not _PROMO_TAIL_RE.search(s)]
            clean_para = ' '.join(clean_sents).strip()
            if clean_para:
                result.append(clean_para)
        else:
            result.append(para)
    return '\n\n'.join(result).strip()


# Listicle / spa / clinic directory filter — drop toàn bộ doc nếu title là listicle
# địa chỉ, spa, phòng khám, ưu đãi, combo, đặt lịch, review clinic...
# CHÚ Ý: chỉ drop khi title rõ ràng là directory/spa/clinic/promo, KHÔNG drop medical listicle
# (vd: "Top 4 thuốc trị mụn theo bác sĩ" là nội dung y tế hợp lệ)
_LISTICLE_TITLE_RE = re.compile(
    # Top N spa/phòng khám/clinic/địa chỉ/cơ sở/thẩm mỹ — directory listing
    r"top\s+\d+\s+.*(spa|phòng khám|clinic|địa chỉ|cơ sở|thẩm mỹ\s*viện)|"
    # spa/phòng khám/clinic/thẩm mỹ viện + uy tín/tốt nhất/giá rẻ — clinic directory
    r"(spa|phòng khám|clinic|thẩm mỹ viện).*(uy tín|tốt nhất|giá rẻ|chất lượng)|"
    # địa chỉ trị mụn / địa chỉ da liễu — address listing
    r"địa chỉ\s+(trị mụn|da liễu|skin\s*care?)|"
    # bảng giá / giá dịch vụ — price listing
    r"(bảng giá|giá dịch vụ|chi phí điều trị).*(trị mụn|laser|peeling|peel da)|"
    # ưu đãi / combo / voucher — promotional
    r"(ưu đãi|khuyến mãi|combo|voucher|deal).*(mụn|da|skin|laser|peel)|"
    # đặt lịch / đặt hẹn — booking guide
    r"(đặt lịch|book lịch|đặt hẹn)\s+(trị mụn|khám da|điều trị|bệnh viện|phòng khám)|"
    # review phòng khám/spa/clinic
    r"review\s+(phòng khám|spa|clinic|thẩm mỹ)|"
    # hướng dẫn đặt lịch
    r"hướng dẫn\s+đặt lịch\s+",
    re.IGNORECASE,
)

def _is_listicle_doc(title: str) -> bool:
    """Trả True nếu doc là listicle spa/clinic/ưu đãi — không có giá trị y tế."""
    return bool(_LISTICLE_TITLE_RE.search(title))


# CJK detector — phòng crawl nhầm trang zh/ja/ko
_CJK_RE = re.compile(r"[一-鿿㐀-䶿　-〿]")
_CJK_THRESHOLD = 0.20


def _repetition_ratio(text: str) -> float:
    """Tỉ lệ từ lặp lại — cao → chunk là boilerplate lặp lại."""
    words = text.lower().split()
    if len(words) < 15:
        return 0.0
    return 1.0 - len(set(words)) / len(words)


def _is_acne_chunk(text: str, language: str = "vi") -> bool:
    """Trả True nếu chunk có tín hiệu acne và không phải off-topic/boilerplate.

    Các bộ lọc theo thứ tự từ nhanh đến chậm:
    1. CJK dominant → drop
    2. Boilerplate header → drop
    3. Ad/navigation noise trong chunk ngắn → drop
    4. Quá nhiều từ lặp (repetition > 0.72) → drop
    5. Không có acne signal → drop
    6. Off-topic dominant → drop
    """
    # 1. CJK
    if len(_CJK_RE.findall(text)) / max(len(text), 1) > _CJK_THRESHOLD:
        return False

    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # 2. Boilerplate header (chunk bắt đầu bằng "bài viết được tham vấn...")
    if _BOILERPLATE_RE.match(text_stripped[:120]):
        return False

    # 3. Ad/navigation noise trong chunk ngắn (<600 chars)
    if len(text_stripped) < 600 and _AD_NOISE_RE.search(text_lower):
        return False

    # 4. Repetition (lặp câu/cụm từ — thường là boilerplate)
    if _repetition_ratio(text) > 0.72:
        return False

    # 5. Acne signal check
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

    # dedup=False: intra-doc near-dup disabled; cross-doc dedup handled in Phase 2
    chunker = VietnameseChunker(chunk_size=200, overlap=40, min_size=50, dedup=False)
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CHUNKS_PATH.with_name(f"{CHUNKS_PATH.name}.tmp")

    # Near-dup shingling: top-K word fingerprint, O(n)
    _SHINGLE_TOP_K   = 20   # số từ phổ biến nhất làm fingerprint
    _SHINGLE_MIN_WORDS = 60  # chỉ áp dụng với chunk đủ dài

    def _shingle_key(text: str) -> frozenset:
        words = re.sub(r"\s+", " ", text.lower()).split()
        cnt: dict[str, int] = {}
        for w in words:
            cnt[w] = cnt.get(w, 0) + 1
        top = sorted(cnt, key=lambda w: -cnt[w])[:_SHINGLE_TOP_K]
        return frozenset(top)

    filtered_short    = 0
    filtered_offtopic = 0
    filtered_lang     = 0
    filtered_dup      = 0
    filtered_listicle = 0
    t0 = time.time()

    # ── Bước 1: Thu thập chunk thô theo từng doc, filter content, CHƯA gán link ──
    # Mỗi phần tử: (doc, list[chunk_text_đã_pass_filter])
    # Giữ nguyên thứ tự trong doc để rebuild position/prev/next sau.

    # Dùng dict doc_id -> list[chunk_text] để dedup cross-doc sau
    doc_chunks: list[tuple[object, list[str]]] = []  # (doc, [chunk_text, ...])

    try:
        for idx, doc in enumerate(docs):
            # Doc-level listicle / spa / clinic filter (title-based)
            if _is_listicle_doc(doc.title):
                filtered_listicle += 1
                continue

            text = clean_vi_text(doc.text)
            if not text:
                continue

            # Trim paragraph cuối có hotline/SĐT/địa chỉ trước khi chunk
            text = _trim_promo_tail(text)
            if not text:
                continue

            raw_chunks = chunker.chunk(text)
            lang = doc.source.language

            # Drop ngôn ngữ không hợp lệ theo field
            if lang not in ("vi", "en"):
                filtered_lang += len(raw_chunks)
                continue

            kept_texts: list[str] = []
            for chunk_text in raw_chunks:
                if len(chunk_text) < min_chunk_chars:
                    filtered_short += 1
                    continue
                if not _is_acne_chunk(chunk_text, lang):
                    filtered_offtopic += 1
                    continue
                kept_texts.append(chunk_text)

            if kept_texts:
                doc_chunks.append((doc, kept_texts))

            if idx > 0 and idx % 500 == 0:
                n_so_far = sum(len(ct) for _, ct in doc_chunks)
                logger.info(f"[chunk] {idx}/{len(docs)} docs, {n_so_far} chunks qua filter...")

    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    logger.info(f"[chunk] Filtered: {filtered_listicle} docs listicle/spa/clinic (title filter)")

    # ── Bước 2: Cross-doc dedup (exact + near-dup shingling) ─────────────────────
    # Ưu tiên trust_level cao hơn: sắp xếp doc theo trust trước
    _TRUST_ORDER = {"high": 0, "medium": 1, "low": 2}
    doc_chunks.sort(key=lambda x: _TRUST_ORDER.get(x[0].source.trust_level or "low", 2))

    seen_texts:    dict[str, str]      = {}   # norm_text -> chunk_id đã giữ
    seen_shingles: dict[frozenset, str] = {}  # shingle_key -> chunk_id đã giữ

    # doc_id -> list[chunk_text đã qua dedup], giữ thứ tự trong doc
    deduped_by_doc: dict[str, tuple[object, list[str]]] = {}

    for doc, texts in doc_chunks:
        kept: list[str] = []
        for chunk_text in texts:
            norm = re.sub(r"\s+", " ", chunk_text.strip())

            if norm in seen_texts:
                filtered_dup += 1
                logger.debug(f"[chunk] EXACT-DUP dropped from {doc.doc_id}")
                continue

            words = norm.split()
            if len(words) >= _SHINGLE_MIN_WORDS:
                key = _shingle_key(norm)
                if key in seen_shingles:
                    filtered_dup += 1
                    logger.debug(f"[chunk] NEAR-DUP dropped from {doc.doc_id} (~{seen_shingles[key]})")
                    continue
                seen_shingles[key] = f"{doc.doc_id}::?"

            seen_texts[norm] = doc.doc_id
            kept.append(chunk_text)

        if kept:
            deduped_by_doc[doc.doc_id] = (doc, kept)

    # ── Bước 3: Rebuild position + prev_chunk_id + next_chunk_id ─────────────────
    # Đây là bước fix lỗi gốc: gán link SAU khi đã biết đủ chunk nào còn lại
    all_chunks: list[KBChunk] = []

    for doc_id, (doc, texts) in deduped_by_doc.items():
        n = len(texts)
        source_type = (
            doc.source.source_type
            if doc.source.source_type != "unknown"
            else infer_source_type(
                source_name=doc.source.source_name,
                domain=doc.source.domain,
                url=doc.url,
                tags=doc.tags,
                categories=doc.categories,
            )
        )
        for pos, chunk_text in enumerate(texts):
            chunk_id      = f"{doc_id}::{pos:04d}"
            prev_chunk_id = f"{doc_id}::{pos-1:04d}" if pos > 0 else None
            next_chunk_id = f"{doc_id}::{pos+1:04d}" if pos < n - 1 else None

            all_chunks.append(KBChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                text=chunk_text,
                text_len=len(chunk_text),
                position=pos,
                prev_chunk_id=prev_chunk_id,
                next_chunk_id=next_chunk_id,
                url=doc.url,
                title=doc.title,
                source_name=doc.source.source_name,
                source_type=source_type,
                trust_level=doc.source.trust_level,
                language=doc.source.language,
                categories=doc.categories,
                tags=doc.tags,
            ))

    total = len(all_chunks)

    if total == 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            "[chunk] 0 chunks after filtering. Keeping existing chunks untouched."
        )

    try:
        with open(tmp_path, "w", encoding="utf-8") as out:
            for chunk in all_chunks:
                out.write(chunk.model_dump_json() + "\n")
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    tmp_path.replace(CHUNKS_PATH)

    elapsed = time.time() - t0
    logger.success(f"[chunk] Xong! {total} chunks tu {len(docs)} docs trong {elapsed:.1f}s")
    logger.info(f"[chunk] position/prev/next da duoc rebuild sau filter — khong con broken links")
    if filtered_short:
        logger.info(f"[chunk] Filtered: {filtered_short} chunks too short (< {min_chunk_chars} chars)")
    if filtered_offtopic:
        logger.info(f"[chunk] Filtered: {filtered_offtopic} chunks off-topic / boilerplate / noise")
    if filtered_lang:
        logger.info(f"[chunk] Filtered: {filtered_lang} chunks non-vi/en language")
    if filtered_dup:
        logger.info(f"[chunk] Filtered: {filtered_dup} chunks duplicate (exact + near-dup)")
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
        from acne_llm.config import settings
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
    p.add_argument("--step", choices=["chunk", "embed", "bm25", "all"], default="all",
                   help="Buoc can chay (default: all)")
    p.add_argument("--min-quality", type=float, default=0.5, dest="min_quality",
                   help="Loc docs co quality_score < gia tri nay (default: 0.5)")
    p.add_argument("--min-chunk-chars", type=int, default=50, dest="min_chunk_chars",
                   help="Loc chunk co do dai < gia tri nay (default: 50)")
    p.add_argument("--batch-size", type=int, default=32, dest="batch_size",
                   help="Batch size cho embedding (default: 32)")
    p.add_argument("--force", action="store_true", help="Rebuild du output da ton tai")
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
