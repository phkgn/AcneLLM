# FINDINGS / src.utils

Module: `src/acne_llm/utils/` — 8 file, 740 LOC (`__init__.py` 3,
`chunk_filter.py` 182, `fuzzy_match.py` 90, `hashing.py` 9, `logging.py` 229,
`retrieval_query.py` 126, `text_cleaning.py` 89, `timer.py` 12).

**Phép đếm khối (Bước 0):**
- `__init__.py`: `__all__` = **1** (không có docstring)
- `chunk_filter.py`: 1 lời khai + 3 hằng + 6 hàm = **10**
- `fuzzy_match.py`: 1 lời khai + `FuzzyHit` + `_tokens` + `_LENGTH_GATE` +
  `best_match` + `find_in_text` + `_as_tuple` + `classify` = **8**
- `hashing.py`: `stable_hash` + `doc_id_for` = **2** (không có docstring)
- `logging.py`: 1 lời khai + `_CONSOLE_FORMAT` + `_FILE_FORMAT` +
  `PIPELINE_STAGES` + `_compact_log_value` + `log_pipeline_stage` +
  `log_runtime_banner` + `configure_logging` = **8**
- `retrieval_query.py`: 1 lời khai + `_HIGH_PRECISION_ALIASES` + `_NEG_CUES` +
  `_NEG_RE` + `_no_accent` + `_CLAUSE_BOUNDARY` + `_alias_is_negated` +
  `_dedupe` + `_compact_text` + `build_current_turn_query` +
  `extracted_entities_from_user` = **11**
- `text_cleaning.py`: 1 lời khai + `BOILERPLATE_PATTERNS` + `clean_vi_text` +
  `_FT_PATTERNS` + `_FT_COMPILED` + `clean_for_finetuning` = **6**
- `timer.py`: `timed` = **1** (không có docstring)

→ **47 khối × 8 mục = 376 mục.**

---

## `__init__.py`

### [x] `__all__` (`__init__.py:3`)
1. in/out: `["is_noisy_chunk", "drop_noisy_chunks"]`. {code}
2-5. không side effect / state / lỗi / config. {code}
6. ai gọi: `import *` = 0 toàn repo. Người dùng thật import đường dẫn đầy đủ
   (`from ...utils.fuzzy_match import find_in_text`, `from ..utils.logging import ...`). {code}
7. invariant: mặt tiền công khai khai **2** tên, trong khi module thực tế xuất
   ra ít nhất 10 tên đang được dùng từ ngoài. Mặt tiền này không mô tả module. {code}
8. deprecated: không đánh dấu, nhưng vô nghĩa. {code}

---

## `chunk_filter.py`

### [x] docstring `chunk_filter.py:1-5`
1. in/out: 5 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. **invariant khai báo SAI:** "Shared chunk-quality filters used by both
   pipeline/hybrid.py and chat/runtime.py". Không tồn tại `pipeline/hybrid.py`
   trong repo (grep = 0), và người dùng thật là `chat/_retrieval.py`. Lời khai
   trỏ vào một file đã biến mất. Xem Q-01. {code+doc}
8. deprecated: không. {doc}

### [x] `_NOISY_MARKERS` (`chunk_filter.py:13-21`)
1. in/out: tuple 7 chuỗi (`"view source"`, `"module:"`, `"talk:"`, `"/w/index.php?"`, …). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `is_noisy_chunk:59,61`. {code}
7. invariant: toàn bộ 7 marker là dấu vết **Wikipedia/MediaWiki**. KB thật có 24k
   chunk từ NICE/AAD/JID/sách giáo khoa — bộ lọc này chỉ nhắm một nguồn. `"module:"`
   và `"talk:"` đủ ngắn để khớp nhầm tiêu đề tiếng Anh bình thường
   ("Module: Acne pathophysiology"), nhưng chỉ quét `title` và `url` nên rủi ro thấp. {code}
8. deprecated: không. {code}

### [x] `_QUERY_STOP_TERMS` (`chunk_filter.py:23-28`)
1. in/out: set 30 từ dừng tiếng Việt (cả có dấu lẫn không dấu). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_query_terms:43`, `drop_query_mismatched_chunks:127`. {code}
7. invariant: **bản sao thứ hai** của danh sách stopword — `rag/sparse.py:14`
   đã có `_VI_STOPWORDS`, và `_query_terms` gọi `tokenize_vi(remove_stopwords=True)`
   (dùng danh sách kia) rồi **lọc lần nữa** bằng danh sách này. Hai bảng, hai
   nơi bảo trì. {code}
8. deprecated: không. {code}

### [x] `_CONCRETE_QUERY_MARKERS` (`chunk_filter.py:30-36`)
1. in/out: tuple 22 chuỗi — hoạt chất, kem chống nắng, và nhóm thực phẩm. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_has_concrete_query_marker:49`. {code}
7. invariant: đây là **cổng bật** của `drop_query_mismatched_chunks` — không có
   marker nào trong query thì bộ lọc không chạy. Danh sách viết tay 22 mục cho
   một KB 24k chunk: mọi truy vấn cụ thể nằm ngoài 22 mục này đều bỏ qua bộ lọc
   im lặng. `"sữa"`/`"sua"` và `"đường"`/`"duong"` ngắn và khớp trong từ khác
   ("sữa rửa mặt", "đường kẻ"), nên còn bật nhầm. {code}
8. deprecated: không. {code}

### [x] `_query_terms` (`chunk_filter.py:39-44`)
1. in/out: `(query: str) -> set[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_QUERY_STOP_TERMS`. {code}
6. ai gọi: `drop_query_mismatched_chunks:119`. {code}
7. invariant: lọc token `len(term) >= 3` **trước** khi lower, nhưng so
   `term not in _QUERY_STOP_TERMS` cũng trước khi lower — nên stopword viết hoa
   ("Không") lọt qua bộ lọc rồi mới bị hạ về thường trong set comprehension.
   Với tiếng Việt viết thường thì không ảnh hưởng; là bất đối xứng thật. {code}
8. deprecated: không. {code}

### [x] `_has_concrete_query_marker` (`chunk_filter.py:47-49`)
1. in/out: `(query: str) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_CONCRETE_QUERY_MARKERS`. {code}
6. ai gọi: `drop_query_mismatched_chunks:117`. {code}
7. invariant: khớp chuỗi con, không ranh giới từ. Xem mục 7 của `_CONCRETE_QUERY_MARKERS`. {code}
8. deprecated: không. {code}

### [x] `is_noisy_chunk` (`chunk_filter.py:52-65`)
1. in/out: `(chunk: RetrievedChunk) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (`chunk.metadata or {}`, `str(...)` bọc mọi truy cập). {code}
5. config: `_NOISY_MARKERS`. {code}
6. ai gọi: `drop_noisy_chunks:82`; export ở `__init__.py`. {code}
7. invariant: nhánh cuối (`:63-64`) là **thừa** — `"talk:"` và `"view source"`
   đều đã có trong `_NOISY_MARKERS`, nên `:59` đã bắt trước khi tới đây. Điều kiện
   `"wikipedia" in source` không nới thêm gì. Code chết, vô hại. {code}
8. deprecated: không. {code}

### [x] `drop_noisy_chunks` (`chunk_filter.py:68-104`)
1. in/out: `(retrieval: RetrievalOutput | None, min_score: float = 0.0) -> RetrievalOutput | None`. {code}
2. side effect: không (dựng object mới). {code}
3. state: không. {code}
4. lỗi: `float(c.score)` raise nếu score không phải số. {code}
5. config: `min_score` từ người gọi — `chat/_retrieval.py` truyền
   `settings.chat_min_chunk_score` (0.25). {code}
6. ai gọi: `chat/_retrieval.py`; export ở `__init__.py`. {code}
7. invariant: trả **chính object cũ** khi không lọc gì (`:85-86`) — docstring
   khai đúng ("avoids unnecessary allocation"). Hệ quả: người gọi không thể dựa
   vào việc kết quả luôn là object mới. `avg_score` tính lại từ chunk còn giữ,
   nên số này không so được với `avg_score` trước lọc. {code}
8. deprecated: không. {code}

### [x] `drop_query_mismatched_chunks` (`chunk_filter.py:107-140`)
1. in/out: `(retrieval, query: str, min_overlap: int = 2) -> RetrievalOutput | None`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `min_overlap` từ người gọi. {code}
6. ai gọi: `chat/_retrieval.py`. {code}
7. invariant: **ba cổng thoát sớm** trước khi lọc (`:115` query rỗng, `:117`
   không có marker cụ thể, `:120` query ít hơn `min_overlap` token). Với truy vấn
   tiếng Việt ngắn ("mụn bọc là gì") sau khi bỏ stopword thường còn 1–2 token, nên
   cổng `:120` cắt phần lớn lưu lượng. Bộ lọc này chạy hiếm hơn tên gọi gợi ý. {code}
8. deprecated: không. {code}

### [x] `drop_acne_boils_mismatched_chunks` (`chunk_filter.py:156-182`)
1. in/out: `(retrieval, query: str) -> RetrievalOutput | None`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: hai bảng term nội tuyến (`:168-169`). {code}
6. ai gọi: `chat/_retrieval.py`. {code}
7. invariant: chỉ bật khi query nói rõ "mụn bọc" **và không** nói "mụn nhọt".
   Comment `:152-154` biện hộ đúng việc giữ hàm này (term 2+ từ, phân biệt lâm
   sàng thật) trong khi hàm anh em `drop_body_region_mismatched_chunks` bị xoá.
   Khác hai hàm trên, hàm này dùng `retrieval.model_copy(update=...)` thay vì
   dựng `RetrievalOutput(...)` mới — ba hàm lọc trong một file, hai cách tạo
   kết quả. {code}
8. deprecated: không. {code}

---

## `fuzzy_match.py`

### [x] docstring `fuzzy_match.py:1-6`
1. in/out: 6 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Chỉ giữ lexicon CANONICAL nhỏ; tầng chuẩn hoá lo biến
   thể, fuzzy lo phần dưới"; "Similarity = confidence"; "Không phụ thuộc LLM.
   Chỉ rapidfuzz (deterministic)". **Đối chiếu:** import chỉ có `rapidfuzz`,
   `dataclasses`, `functools` — lời khai cuối đúng. "Similarity = confidence"
   cũng đúng theo nghĩa đen: `FuzzyHit.similarity` được dùng trực tiếp làm
   confidence ở `chat/routing/rule_extractor.py`. {code+doc}
8. deprecated: không. {doc}

### [x] `FuzzyHit` (`fuzzy_match.py:15-19`)
1. in/out: dataclass frozen — `canonical: str`, `similarity: float`, `query: str`. {code}
2. side effect: không. {code}
3. state: **immutable** (`frozen=True`) — khác mọi dataclass khác trong repo. {code}
4. lỗi: gán lại raise `FrozenInstanceError`. {code}
5. config: không. {code}
6. ai gọi: `best_match:80` dựng; `rule_extractor.py` đọc. {code}
7. invariant: `similarity` là thang `[0,1]` (đã chia 100 ở `:75`), trong khi
   `rapidfuzz.fuzz.ratio` trả `[0,100]`. Phép chia nằm ở `best_match`, không ở
   dataclass — ai dựng `FuzzyHit` trực tiếp có thể đưa vào thang sai mà không ai
   chặn. {code}
8. deprecated: không. {code}

### [x] `_tokens` (`fuzzy_match.py:22-27`)
1. in/out: `(text: str, max_ngram: int = 3) -> list[str]`; sinh mọi n-gram 1..3. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `max_ngram`. {code}
6. ai gọi: `find_in_text:93`. {code}
7. invariant: số n-gram ≈ 3×số từ. Với mô tả dài (mô tả ca 700 ký tự ≈ 150 từ)
   là ~450 n-gram, mỗi cái nhân với số canonical → `best_match` chạy
   450 × |canonicals| lần. Không có cache ở tầng này. {code}
8. deprecated: không. {code}

### [x] `_LENGTH_GATE` (`fuzzy_match.py:31`)
1. in/out: `float = 0.6`. {code}
2-4. không. {code}
5. config: hằng cứng, không có field `Settings`. {code}
6. ai gọi: `best_match:73`. {code}
7. invariant: cổng `min(len)/max(len) >= 0.6` chạy **trước** khi tính điểm, nên
   nó cắt trước cả khi scorer có cơ hội. `"bpo"` (3) vs `"benzoyl peroxide"` (16)
   cho tỉ lệ 0.19 → **không bao giờ khớp** qua đường fuzzy. Viết tắt phải đi
   đường khác (bảng alias ở `retrieval_query.py:11-12` làm việc đó). Nhất quán
   với lời khai "tầng chuẩn hoá lo biến thể". {code}
8. deprecated: không. {code}

### [x] `best_match` (`fuzzy_match.py:34-56`)
1. in/out: `(query, canonicals, *, scorer=fuzz.ratio) -> FuzzyHit | None`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `scorer` keyword-only, mặc định `fuzz.ratio`. Không ai truyền scorer khác. {code}
6. ai gọi: `find_in_text:94`, `classify:90`,
   `research/evaluation/runners/run_intake.py:41`, test. {code}
7. invariant: `best_s` khởi tạo `-1.0` và điều kiện là `s > best_s`, nên
   canonical **đầu tiên** vượt cổng luôn thắng khi hoà điểm. Thứ tự tuple
   canonical vì thế quyết định kết quả khi hoà — không có tie-break xác định
   theo nội dung. {code}
8. deprecated: không. {code}

### [x] `find_in_text` (`fuzzy_match.py:59-81`)
1. in/out: `(text, canonicals, *, accept: float, review: float, max_ngram=3) -> list[FuzzyHit]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `accept`/`review` là keyword bắt buộc — thiếu thì `TypeError`. {code}
5. config: hai ngưỡng do người gọi truyền (`chat/routing/rule_extractor.py:29`). {code}
6. ai gọi: `rule_extractor.py`, test. {code}
7. **invariant hỏng — tầng thứ hai không tồn tại:** docstring `:60-65` khai
   "Two-tier fuzzy match: accept >= auto-include, review <= accept < review =
   review list". Nhưng code lọc `if hit.similarity < review: continue` (`:98-99`)
   rồi **return `[h for h in hits if h.similarity >= accept]`** (`:105`). Mọi hit
   nằm giữa `review` và `accept` được tính, được lưu vào dict, rồi bị vứt ở dòng
   cuối. Không có "review list" nào được trả ra. Tham số `review` chỉ còn tác
   dụng như một tối ưu vi mô (bỏ sớm hit rất thấp). Xem Q-02. {code+doc}
8. deprecated: không. {code}

### [x] `_as_tuple` (`fuzzy_match.py:84-86`)
1. in/out: `(canonicals: tuple[str, ...]) -> tuple[str, ...]`; chuẩn hoá + bỏ trùng,
   có `@lru_cache(maxsize=256)`. {code}
2. side effect: điền cache. {code}
3. state: cache toàn cục 256 entry. {code}
4. lỗi: `TypeError` nếu truyền list (không hashable) — `lru_cache` yêu cầu
   tham số hashable. Chữ ký khai `tuple` nên đúng hợp đồng, nhưng không có gì
   chặn người gọi truyền list ngoài lỗi runtime. {code}
5. config: `maxsize=256`. {code}
6. ai gọi: `classify:90` — **một chỗ duy nhất**. {code}
7. invariant: `dict.fromkeys(...)` giữ thứ tự, nên kết quả xác định. {code}
8. deprecated: không. {code}

### [x] `classify` (`fuzzy_match.py:89-90`)
1. in/out: `(query, canonicals) -> FuzzyHit | None`. {code}
2. side effect: qua `_as_tuple`. {code}
3. state: không của riêng nó. {code}
4. lỗi: như `_as_tuple`. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ trong production.** Chỉ `tests/test_extraction_fieldresult.py:3`
   import. (Từ "classify" xuất hiện nhiều nơi khác trong repo là
   `intent_classify`, không liên quan.) {code}
7. invariant: đây là bản `best_match` có chuẩn hoá canonical trước. Người dùng
   thật (`rule_extractor.py`) gọi `find_in_text` chứ không gọi hàm này, nên tầng
   chuẩn hoá + cache mà `classify` cung cấp **không** được đường production
   hưởng. Xem Q-03. {code}
8. deprecated: 0 caller production. {code}

---

## `hashing.py`

### [x] `stable_hash` (`hashing.py:4-5`)
1. in/out: `(s: str, length: int = 10) -> str`; sha256 hex cắt `length` ký tự. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `AttributeError` nếu `s` không phải str. {code}
5. config: `length` mặc định 10. {code}
6. ai gọi: **chỉ `doc_id_for:9` trong cùng file.** Không ai ngoài file gọi. {code}
7. invariant: 10 ký tự hex = 40 bit. Với ~24k chunk, xác suất đụng theo nghịch
   lý sinh nhật ≈ 2.6e-4 — chấp nhận được. Nhưng `length` chưa từng được truyền
   khác 10, nên tham số này là điểm mở rộng không ai dùng. {code}
8. deprecated: không. {code}

### [x] `doc_id_for` (`hashing.py:8-9`)
1. in/out: `(source_name: str, url: str) -> str`; `"{source}_{hash10}"`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `AttributeError` nếu tham số không phải str. {code}
5. config: không. {code}
6. ai gọi: `crawler/sources/pubmed.py:70`, `crawler/sources/generic_html.py:328`. {code}
7. invariant: chỉ thay khoảng trắng bằng `_`, **không** bỏ dấu và không bỏ ký tự
   đặc biệt khác — `source_name` tiếng Việt hoặc có dấu `/` sẽ đi thẳng vào
   `doc_id`. Các source hiện tại đặt tên ASCII nên chưa nổ. {code}
8. deprecated: không. {code}

---

## `timer.py`

### [x] `timed` (`timer.py:5-11`)
1. in/out: context manager `timed(label: str = "")`; yield dict `{"ms": 0}`, điền
   `ms` khi thoát. {code}
2. side effect: không. {code}
3. state: dict cục bộ. {code}
4. lỗi: `finally` nên vẫn ghi `ms` khi thân raise. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ toàn repo.** Grep `utils.timer`, `from .timer`, `import timed`
   = 0 kết quả. (Các match của chuỗi "timed" ở nơi khác là `"timed out"` trong
   thông điệp lỗi.) Việc đo thời gian thật do `log_pipeline_stage` làm, bằng
   `time.perf_counter()` truyền tay. {code}
7. invariant: tham số `label` **không được dùng trong thân hàm** — nhận rồi bỏ. {code}
8. deprecated: cả file 12 dòng, 0 caller. Xem Q-04. {code}

---

## `logging.py`

### [x] docstring `logging.py:1`
1. in/out: 1 dòng — "PowerShell-friendly colours + file sink to data/logs/". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng — `_CONSOLE_FORMAT` dùng thẻ màu loguru,
   `configure_logging` mặc định `log_dir="data/logs"`. {code+doc}
8. deprecated: không. {doc}

### [x] `_CONSOLE_FORMAT` (`logging.py:16-20`)
1. in/out: chuỗi format loguru — `HH:mm:ss | LEVEL | message`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `configure_logging:176`. {code}
7. invariant: **không** có `{name}:{line}` — console cố ý gọn hơn file sink. Chú
   thích `:14-15` liệt kê quy ước ký hiệu (✓ KEEP xanh, ✗ SKIP đỏ, ⚠ WARN vàng)
   nhưng format không ánh xạ ký hiệu nào; quy ước đó nằm ở nơi gọi `logger.*`. {code+comment}
8. deprecated: không. {code}

### [x] `_FILE_FORMAT` (`logging.py:22-24`)
1. in/out: chuỗi format — thêm ngày và `{name}:{line}`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `configure_logging:187,206,222`. {code}
7. invariant: dùng cho cả 3 file sink (session log, fallback log, errors.log) —
   nhất quán. {code}
8. deprecated: không. {code}

### [x] `PIPELINE_STAGES` (`logging.py:26-36`)
1. in/out: frozenset 9 chuỗi — INPUT, PREPROCESS, SAFETY, INTAKE, ROUTE,
   EXTRACT, RAG, GENERATE, OUTPUT. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `log_pipeline_stage:66`. {code}
7. invariant: **cả 9 giai đoạn đều có người dùng thật.** Đếm literal trong `src/`:
   EXTRACT 9, ROUTE 9, SAFETY 7, INTAKE 6, GENERATE 5, OUTPUT 4, INPUT 2,
   PREPROCESS 2, RAG 2. Không có giai đoạn chết, và cũng không có lời gọi nào
   dùng tên ngoài danh sách (nếu có sẽ raise ngay — xem `log_pipeline_stage`). {code}
8. deprecated: không. {code}

### [x] `_compact_log_value` (`logging.py:39-53`)
1. in/out: `(value: Any) -> str`. {code}
2. side effect: không. {code}
3. state: không (đệ quy cho Sequence). {code}
4. lỗi: `json.dumps(..., default=str)` cho Mapping nên không raise; nhánh
   Sequence đệ quy **không giới hạn độ sâu** — cấu trúc lồng sâu hoặc tự tham
   chiếu gây `RecursionError`. Không có bảo vệ. {code}
5. config: cắt ở 160 ký tự. {code}
6. ai gọi: `log_pipeline_stage:70` và chính nó (`:48`). {code}
7. invariant: `set` **không** phải `Sequence` nên rơi xuống nhánh `str(value)` —
   thứ tự phần tử của set không xác định, nên cùng một dữ liệu cho ra log khác
   nhau giữa các lần chạy. `Session.asked_fields` là `set` (`chat/session/models.py:111`),
   nhưng field đó đã chết nên chưa gây khác biệt thật. {code}
8. deprecated: không. {code}

### [x] `log_pipeline_stage` (`logging.py:56-79`)
1. in/out: `(session_id, stage, started, *, level="INFO", **fields) -> None`. {code}
2. side effect: ghi một dòng log. {code}
3. state: không. {code}
4. **lỗi: `raise ValueError(f"unknown pipeline stage: {stage}")`** khi tên
   giai đoạn không thuộc `PIPELINE_STAGES` (`:66-67`). Một hàm **ghi log** có thể
   làm nổ pipeline. 36 chỗ gọi trong `src/`; gõ sai tên ở bất kỳ chỗ nào là lỗi
   500 giữa request, không phải một dòng log thiếu. Xem Q-05. {code}
5. config: `level` mặc định INFO. {code}
6. ai gọi: 36 chỗ trong `src/` — hàm được dùng nhiều nhất của module. {code}
7. invariant: `elapsed_ms = max(0.0, (perf_counter() - started) * 1000)` — kẹp
   sàn 0 nên đồng hồ giật không cho ra số âm; `started` phải là `perf_counter()`
   chứ không phải `time.time()`, và không có gì kiểm điều đó. Truyền nhầm
   `time.time()` cho ra một con số ms khổng lồ trông như thật. {code}
8. deprecated: không. {code}

### [x] `log_runtime_banner` (`logging.py:82-153`)
1. in/out: `(container: Any) -> None`. {code}
2. side effect: gọi `container.store.count()` (truy vấn Chroma) khi
   `container.rag_ready`; ghi log. {code}
3. state: không. {code}
4. lỗi: `container.store.count()` bọc `try/except Exception` → `"?"`. Nhưng
   `container.settings` ở `:85` **không** bọc — container thiếu `.settings` là
   `AttributeError` lúc khởi động. {code}
5. config: đọc 12 field của `settings`, tất cả qua `getattr(..., default)`. {code}
6. ai gọi: `di.py:343`, cuối `build_container`. Một chỗ duy nhất. {code}
7. invariant: nhãn `"intake 3B"` và `"answer 7B"` là **chuỗi cứng**, không suy ra
   từ model đang chạy. `.env` hiện trỏ `LLM_MODEL=acne-generator-v2` (Qwen2.5-7B
   LoRA) nên "7B" đúng lúc này; đổi model cỡ khác thì banner nói dối. Ngoài ra
   dòng `:150` khai `"cong tat dinh: injection, genital, thuoc"` — **ba** cổng
   tất định, mâu thuẫn với `chat/session/fold.py:3-4` và `guardrails/runner.py:1`
   vốn mỗi bên tự nhận là cổng duy nhất. Xem Q-06. {code+comment}
8. deprecated: comment `:148` ghi "DrugChecker da bi xoa (Phase 5)". {comment}

### [x] `configure_logging` (`logging.py:156-229`)
1. in/out: `(level: str = "INFO", log_dir: str | Path = "data/logs") -> Path`. {code}
2. side effect: tạo thư mục, `logger.remove()` (**xoá mọi sink đang có**), thêm
   3 sink. {code}
3. state: sửa trạng thái toàn cục của loguru. {code}
4. lỗi: `OSError` được bắt ở cả 3 tầng (mkdir, session sink, errors sink), mỗi
   tầng có fallback vào `tempfile.gettempdir()`. Đây là hàm xử lý lỗi cẩn thận
   nhất trong module. {code}
5. config: `settings.log_level` (qua `api/app.py:24`); `.env` đang đặt
   `LOG_LEVEL=DEBUG`. {code}
6. ai gọi: `api/app.py:24` và `scripts/crawl_all.py:85`. {code}
7. invariant: `logger.remove()` ở `:170` xoá cả sink mặc định lẫn bất kỳ sink nào
   người khác đã thêm — gọi hàm này hai lần thì lần sau huỷ lần trước. Không
   idempotent, và không có gì chặn gọi lại. {code}
8. deprecated: tên file log là `f"crawl_{ts}.log"` (`:168`) **kể cả khi chạy API
   server** — tàn dư từ thời module này chỉ phục vụ crawler. Log của server nằm
   trong file tên `crawl_*.log`. Xem Q-07. {code}

---

## `retrieval_query.py`

### [x] docstring `retrieval_query.py:1`
1. in/out: 1 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Compact normalized RAG query and extracted-entity
   helpers" — đúng với 2 hàm công khai. {code+doc}
8. deprecated: không. {doc}

### [x] `_HIGH_PRECISION_ALIASES` (`retrieval_query.py:10-16`)
1. in/out: tuple 5 cặp `(regex, canonical)`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `build_current_turn_query:86`. {code}
7. invariant: mọi pattern dùng `\b...\b` và `re.I` — có ranh giới từ, khác hẳn
   các bảng term khớp chuỗi con ở `chunk_filter.py` và `fold.py`. Đây là bảng
   term được viết cẩn thận nhất trong những gì đã duyệt. `"mụn bọc"` map sang
   `"nodular acne cystic acne acne nodule"` — 3 thuật ngữ Anh trong một chuỗi,
   khớp với bảng term của `drop_acne_boils_mismatched_chunks:168`. {code}
8. deprecated: không. {code}

### [x] `_NEG_CUES` (`retrieval_query.py:21-25`)
1. in/out: tuple 15 cue phủ định, **viết không dấu**. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_alias_is_negated:47`. {code}
7. invariant: không dấu là đúng, vì hàm gọi truyền `current_na` (đã bỏ dấu).
   `"ngung"` là chuỗi con của `"ngung dung"`, `"da ngung"` — ba mục chồng nhau,
   thừa nhưng vô hại. {code}
8. deprecated: không. {code}

### [x] `_NEG_RE` (`retrieval_query.py:27`)
1. in/out: `re.compile(r"\bbo\b(?!\s*(?:sung|qua|vao|di\b))")`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_alias_is_negated:47`. {code}
7. **invariant hỏng — dương tính giả trên chữ không dấu:** comment `:26` khai
   ý định là `"bỏ <sản phẩm>"` = ngừng dùng, loại trừ `bổ sung/bỏ qua/bỏ vào`.
   Nhưng regex chạy trên chuỗi **đã bỏ dấu**, nên `\bbo\b` khớp cả `bơ`, `bò`,
   `bố`, `bỏ`, `bó`, `bọ`. Đo thật:
   `"toi an bo dau phong"` → True, `"me toi nau thit bo"` → True,
   `"toi thich qua bo"` → True, `"bo sung kem"` → False (đúng).
   Hệ quả: câu "tôi ăn bơ và dùng BHA" bị coi là đã ngừng BHA → alias
   `salicylic acid` **không** vào query RAG. Chủ đề ăn uống (bơ, thịt bò, bố mẹ)
   xuất hiện thường xuyên trong mô tả ca mụn. Xem Q-08. {code+comment}
8. deprecated: không. {code}

### [x] `_no_accent` (`retrieval_query.py:30-34`)
1. in/out: `(text: str) -> str`; NFD rồi bỏ ký tự loại `Mn`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `build_current_turn_query:84`. {code}
7. invariant có điều kiện: `build_current_turn_query` lấy `match.start()` trên
   chuỗi **có dấu** rồi cắt tiền tố trên chuỗi **không dấu**. Việc này chỉ đúng
   khi hai chuỗi cùng độ dài. Đo thật với đầu vào NFC: `len("tôi ngưng BHA
   nhưng vẫn nổi mụn bọc")` = 35 và `len(_no_accent(...))` = 35 — khớp, vì mọi
   chữ Việt có dấu ở NFC là **một** code point. Nhưng nếu đầu vào tới ở dạng
   **NFD** thì `len` = 44 còn `_no_accent` = 35 → chỉ số lệch 9 và
   `_alias_is_negated` đọc sai mệnh đề. Đường production chạy qua
   `rag/cleaning.py:35` (`normalize("NFC")`) nên hiện an toàn; ràng buộc này
   không được ghi ở đâu. {code}
8. deprecated: không. {code}

### [x] `_CLAUSE_BOUNDARY` (`retrieval_query.py:39`)
1. in/out: `re.compile(r"[,.;:]|\bgio\b|\bnhung\b|\bhien\b|\bbay gio\b")`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_alias_is_negated:45`. {code}
7. invariant: nhánh `\bbay gio\b` là **không thể tới** — `\bgio\b` đứng trước
   trong alternation và regex alternation của Python chọn nhánh khớp đầu tiên
   tại vị trí sớm nhất, nên "bay gio" luôn được cắt tại "gio". Vô hại (điểm cắt
   chỉ lệch 4 ký tự về sau), nhưng là nhánh chết. {code}
8. deprecated: không. {code}

### [x] `_alias_is_negated` (`retrieval_query.py:42-47`)
1. in/out: `(text_no_accent_lower: str, start: int) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_NEG_CUES`, `_NEG_RE`, `_CLAUSE_BOUNDARY`. {code}
6. ai gọi: `build_current_turn_query:90`. {code}
7. invariant: chỉ xét mệnh đề **ngay trước** alias — comment `:37-38` khai đúng
   mục đích ("không dùng BHA nữa, giờ dùng differin" chỉ phủ định BHA). Cơ chế
   đúng; nguồn sai duy nhất là `_NEG_RE` (xem khối trên). {code+comment}
8. deprecated: không. {code}

### [x] `_dedupe` (`retrieval_query.py:50-58`)
1. in/out: `(items: list[str]) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `build_current_turn_query:95`. {code}
7. invariant: **bản sao từng dòng** của `chat/session/fold.py:65-74`
   (`_dedupe_values`). Hai hàm giống hệt, hai tên, hai file. {code}
8. deprecated: không. {code}

### [x] `_compact_text` (`retrieval_query.py:61-65`)
1. in/out: `(text: str, max_chars: int = 700) -> str`. {code}
2-3. không. {code}
4. lỗi: không (`text or ""`). {code}
5. config: `max_chars` 700 mặc định; `build_current_turn_query:101` truyền 300
   cho turn trước. {code}
6. ai gọi: `build_current_turn_query:83,101`. {code}
7. invariant: cắt tại ranh giới từ bằng `rsplit(" ", 1)` — nếu 700 ký tự đầu
   không có khoảng trắng nào, `rsplit` trả nguyên chuỗi và kết quả dài đúng 700.
   Không có dấu "..." báo đã cắt, khác `_compact_log_value` (có "..."). {code}
8. deprecated: không. {code}

### [x] `build_current_turn_query` (`retrieval_query.py:74-109`)
1. in/out: `(clean_text: str, recent_history: list[object] | None = None) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không — mọi truy cập turn qua `getattr(..., default)`. {code}
5. config: bảng alias + ngưỡng 700/300 ký tự. {code}
6. ai gọi: `chat/_retrieval.py` và `chat/intake.py` (12 lần nhắc tên trong repo). {code}
7. invariant: docstring `:78-81` khai "Structured/inferred clinical labels are
   deliberately absent" — đúng, hàm chỉ dùng `clean_text` và bảng alias, không
   đụng `UserInput`. Comment `:68-71` ghi cặp hàm cũ (`build_retrieval_query*`)
   đã bị xoá vì "sinh query từ nhãn lâm sàng suy đoán". Hai lời khai nhất quán
   với code. Nhánh `"nguy hiểm"` ở `:97-98` chèn thêm một câu tiếng Anh cố định
   vào query — bảng term 4 mục viết tay, cùng hạng giòn với các bảng khác. {code+doc}
8. deprecated: không. {code}

### [x] `extracted_entities_from_user` (`retrieval_query.py:112-126`)
1. in/out: `(user: UserInput) -> dict[str, Any]` — 11 khoá. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (`if clinical else` ở mọi khoá lâm sàng). {code}
5. config: không. {code}
6. ai gọi: `chat/runtime.py` (đưa vào `AuditEntry.extracted_entities`). {code}
7. invariant: 11 khoá này là thứ **được ghi vào audit log**; tên khoá ở đây
   (`"lesions"`, `"severity"`, `"distribution"`) **khác** tên field của schema
   (`lesion_types`, `inflammation_level`, `lesion_distribution`). Ai đọc audit
   log phải biết bảng ánh xạ này, và nó không có ở đâu ngoài hàm này. {code}
8. deprecated: không. {code}

---

## `text_cleaning.py`

### [x] docstring `text_cleaning.py:1-5`
1. in/out: 5 dòng — mô tả 2 hàm. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "clean_vi_text — light cleaning for RAG indexing".
   **Sai với thực tế:** việc index KB dùng `acne_llm.rag.cleaning.clean_vi_text`
   (`scripts/build_kb.py:41`), không phải hàm ở đây. {code+doc}
8. deprecated: **cả file chết** — xem Q-09. {code}

### [x] `BOILERPLATE_PATTERNS` (`text_cleaning.py:11-19`)
1. in/out: list regex đã compile. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `clean_vi_text` trong cùng file — tức không ai, vì hàm đó không ai gọi. {code}
7. invariant: trùng tên và nội dung với `rag/cleaning.py:22`. {code}
8. deprecated: chết theo file. {code}

### [x] `clean_vi_text` (`text_cleaning.py:21-34`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `BOILERPLATE_PATTERNS`. {code}
6. ai gọi: **0.** Mọi import `clean_vi_text` trong repo trỏ `acne_llm.rag.cleaning`
   (`scripts/build_kb.py:41`, `tests/test_cleaning.py:1`). Grep `text_cleaning`
   toàn repo = **0 kết quả** ngoài chính file. {code}
7. **invariant nguy hiểm nếu ai đó dùng lại:** `diff` với `rag/cleaning.py` cho
   thấy bản này **thiếu** `PDF_ARTIFACTS` (bảng dịch 16 ký tự) và **thiếu** cả
   hai lời gọi `text.translate(PDF_ARTIFACTS)`. Đó chính là bản vá cho PDF tiếng
   Việt đời cũ (ƣ/Ƣ thay ư/Ư, ký tự Private Use của font Symbol) mà comment
   `rag/cleaning.py:6-9` giải thích: không sửa thì "người" thành "ngƣời" → BM25
   không khớp, embedder mã hoá như từ lạ. File này là bản **trước** khi vá. {code}
8. deprecated: chết. Xem Q-09. {code}

### [x] `_FT_PATTERNS` (`text_cleaning.py:37-67`)
1. in/out: list cặp `(pattern, repl)`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_FT_COMPILED` trong cùng file. {code}
7. invariant: trùng với `rag/cleaning.py:49`. {code}
8. deprecated: chết theo file. {code}

### [x] `_FT_COMPILED` (`text_cleaning.py:69`)
1. in/out: list `(compiled_pattern, repl)`. {code}
2. side effect: compile lúc import. {code}
3. state: hằng module. {code}
4. lỗi: `re.error` lúc import nếu pattern sai. {code}
5. config: `_FT_PATTERNS`. {code}
6. ai gọi: `clean_for_finetuning` — tức không ai. {code}
7. invariant: compile sẵn một lần, đúng cách. {code}
8. deprecated: chết theo file. {code}

### [x] `clean_for_finetuning` (`text_cleaning.py:72-89`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_FT_COMPILED`. {code}
6. ai gọi: **0 chỗ toàn repo.** {code}
7. invariant: cùng thiếu `PDF_ARTIFACTS` như `clean_vi_text` ở trên — nghĩa là
   nếu bộ dữ liệu fine-tune từng được sinh bằng hàm này, nó mang lỗi ƣ/Ƣ. Cần
   kiểm ở `research/LLMData` xem dataset fine-tune dùng đường nào. {code}
8. deprecated: chết. Xem Q-09. {code}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — docstring `chunk_filter.py:1` trỏ vào file không tồn tại.**
"used by both pipeline/hybrid.py and chat/runtime.py" — `pipeline/hybrid.py`
grep = 0. Người dùng thật là `chat/_retrieval.py`. {code+doc}

**Q-02 — `find_in_text` không có tầng "review" như docstring khai.**
`fuzzy_match.py:98-105`: hit giữa `review` và `accept` được tính rồi bị vứt ở
dòng return. "Two-tier" trong docstring không tồn tại trong hành vi. Cần quyết:
sửa docstring, hay trả về hai danh sách như đã hứa (nếu `rule_extractor.py` cần
tầng review). {code+doc}

**Q-03 — `classify` + `_as_tuple` không phục vụ production.**
Chỉ test import. Đường production (`rule_extractor.py`) gọi `find_in_text`, vốn
gọi `best_match` **không** qua `_as_tuple` — nên canonical không được chuẩn hoá
(`strip().lower()`) và không được cache. Nếu lexicon canonical có mục thừa
khoảng trắng hoặc viết hoa, `best_match` so nó nguyên trạng với query đã
`.lower()`. Đáng kiểm ở `src.chat` khi duyệt `rule_extractor.py`. {code}

**Q-04 — `timer.py` (12 dòng) 0 caller.**
`timed` không được gọi ở đâu; `label` còn không được dùng trong thân hàm. Đo
thời gian thật do `log_pipeline_stage` làm. Xoá được. {code}

**Q-05 — `log_pipeline_stage` raise trên tên giai đoạn sai.**
`logging.py:66-67`. Một hàm ghi log có quyền làm hỏng request. 36 chỗ gọi.
Hiện tại cả 36 đều dùng tên hợp lệ (đã đếm literal: 9/9 giai đoạn có người dùng,
không có tên lạ), nên đây là rủi ro chứ chưa phải lỗi. Cần quyết: giữ (fail
fast, bắt lỗi lúc test) hay hạ xuống `logger.warning`. {code}

**Q-06 — thêm một lời khai nữa về "cổng tất định".**
Banner khởi động `logging.py:150` in `"cong tat dinh: injection, genital, thuoc"`
— **ba** cổng. `chat/session/fold.py:3-4` nói `medication_safety_refusal` là cổng
**duy nhất**; `guardrails/runner.py:1` nói chính nó là cổng **duy nhất**. Ba lời
khai, ba nội dung. Đây là câu hỏi lặp lại từ `src.chat.session` Q-08 và
`src.guardrails`; cần một câu trả lời dứt khoát trước khi viết chương kiến trúc. {code+comment}

**Q-07 — log của API server nằm trong file tên `crawl_*.log`.**
`logging.py:168`. `api/app.py:24` gọi `configure_logging` và nhận tên file đó.
Tàn dư từ thời module chỉ phục vụ crawler. Sửa một dòng; đáng sửa vì báo cáo
khoá luận sẽ có ảnh chụp thư mục log. {code}

**Q-08 — `_NEG_RE` bắt nhầm "bơ", "bò", "bố" thành phủ định.**
`retrieval_query.py:27`, chạy trên chuỗi đã bỏ dấu. Đo thật:
`"toi an bo dau phong"` → True, `"me toi nau thit bo"` → True,
`"toi thich qua bo"` → True. Hệ quả: mô tả có nhắc bơ/thịt bò làm alias sản phẩm
trong cùng mệnh đề bị loại khỏi query RAG. Chủ đề ăn uống (sữa, đường, đồ cay,
whey) xuất hiện thường xuyên trong mô tả ca mụn — chính `chunk_filter.py:34-35`
liệt kê chúng làm "marker cụ thể". Cách vá rẻ nhất: giữ dấu cho riêng phép kiểm
này, hoặc đổi `\bbo\b` thành khớp trên bản có dấu `\bbỏ\b`. {code}

**Q-09 — `text_cleaning.py` (89 dòng) là bản sao chết và lỗi thời của
`rag/cleaning.py`.**
Grep `text_cleaning` toàn repo = 0 người dùng. `diff` cho thấy bản này thiếu
`PDF_ARTIFACTS` và hai lời gọi `translate` — tức thiếu đúng bản vá cho PDF tiếng
Việt đời cũ mà `rag/cleaning.py:6-9` giải thích. Đây là bẫy: ai import nhầm
`utils.text_cleaning` thay vì `rag.cleaning` sẽ mất bản vá đó mà không có lỗi
nào. Đề xuất: xoá file. Trước khi xoá, cần kiểm ở `research/LLMData` xem bộ
fine-tune có từng sinh bằng `clean_for_finetuning` của bản này không. {code}

**Q-10 — ba bản sao chức năng trùng nhau trong `utils/` và láng giềng.**
`_dedupe` (`retrieval_query.py:50`) ≡ `_dedupe_values` (`chat/session/fold.py:65`);
`_QUERY_STOP_TERMS` (`chunk_filter.py:23`) chồng lên `_VI_STOPWORDS`
(`rag/sparse.py:14`) và được áp **sau** nó; `text_cleaning.py` ≡ `rag/cleaning.py`.
Ba cặp, ba nơi phải sửa cùng lúc khi đổi một quy tắc. {code}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **47** (1 + 10 + 8 + 2 + 8 + 11 + 6 + 1)
- Khối `### [x]` đếm được: xem `grep -c '^### \[x\]'`
- Mục: 47 × 8 = **376**. Không dùng nén khai báo; mọi khối viết đủ 8 mục.
- Ba khẳng định đo bằng chạy thật chứ không đọc mắt: `_NEG_RE` (Q-08),
  độ dài `_no_accent` NFC vs NFD, và `diff text_cleaning.py rag/cleaning.py` (Q-09).

---

## §7 — BỔ SUNG (thêm sau khi duyệt `src.chat/preprocess.py`)

**Thêm một hệ quả đo được cho Q-08 (`_NEG_RE`) và một lỗi mới của `_no_accent`.**

`chat/preprocess.strip_accents` và `utils/retrieval_query._no_accent` cùng làm
một việc — bỏ dấu tiếng Việt — nhưng bản ở `preprocess` có thêm
`.replace("đ","d").replace("Đ","D")`, còn bản ở đây **không**. Lý do kỹ thuật:
`đ` (U+0111) không phân rã được bằng NFD, nên chỉ NFD-tách-dấu là chưa đủ.

Đo thật:

| đầu vào | `preprocess.strip_accents` | `retrieval_query._no_accent` |
|---|---|---|
| `"da đầu"` | `"da dau"` | `"da đau"` |
| `"đang dùng adapalene"` | `"dang dung adapalene"` | `"đang dung adapalene"` |

Hệ quả đo được ngay trong module này: `_NEG_CUES` được viết bằng ASCII
(`"khong dung"`, `"ngung dung"`, `"dung lai"`…), nên cue nào tương ứng một từ
tiếng Việt bắt đầu bằng `đ` sẽ **không bao giờ khớp**. Thử 8 câu phủ định:

- khớp cue: `"không dùng BHA nữa"`, `"ngừng dùng BHA"`, `"đã ngưng BHA"`,
  `"thôi dùng BHA"`, `"hết dùng BHA"`, `"không xài BHA nữa"` (6/8)
- `"bỏ BHA"` — không cue nào khớp, nhưng `_NEG_RE` bắt được (đó là lý do
  `_NEG_RE` tồn tại riêng)
- **`"đừng dùng BHA"` — không cue nào khớp và `_NEG_RE` cũng không** → alias sản
  phẩm vẫn vào query RAG dù người dùng đã phủ định.

Sửa một dòng: `retrieval_query` dùng chung `chat.preprocess.strip_accents` thay
vì tự định nghĩa `_no_accent`. Lưu ý khi sửa: điều này **thay đổi độ dài chuỗi ở
những chuỗi có `đ`**, và `_alias_is_negated` lấy chỉ số `match.start()` từ chuỗi
**có dấu** rồi cắt trên chuỗi **không dấu** — hiện an toàn vì cả hai cùng độ dài
(xem khối `_no_accent`, mục 7). Thay `đ`→`d` giữ nguyên độ dài 1:1 nên bất biến
đó vẫn đúng; nhưng phải kiểm lại chứ đừng tin.
