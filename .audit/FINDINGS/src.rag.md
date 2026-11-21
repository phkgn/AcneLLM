# FINDINGS / src.rag

Module: `src/acne_llm/rag/` — 8 file, 1.159 LOC (`__init__.py` 0, `chunker.py` 234,
`cleaning.py` 102, `embedder.py` 70, `reranker.py` 160, `retriever.py` 326,
`sparse.py` 117, `vectorstore.py` 150).

**Phép đếm khối (Bước 0)** — đếm bằng `ast` trên chính source, không đếm mắt:
- `__init__.py`: 0 LOC → **1** khối (file rỗng)
- `chunker.py`: 1 lời khai + 16 tên module + 4 thành viên lớp + 1 hàm lồng (`_emit`) = **22**
- `cleaning.py`: 0 lời khai + 6 tên module = **6**
- `embedder.py`: 1 lời khai + 2 tên module + 5 method = **8**
- `reranker.py`: 1 lời khai + 2 tên module + 5 method = **8**
- `retriever.py`: 1 lời khai + 11 tên module + 5 thành viên lớp = **17**
- `sparse.py`: 1 lời khai + 7 tên module + 5 method = **13**
- `vectorstore.py`: 1 lời khai + 1 tên module + 7 method = **9**

→ **84 khối × 8 mục = 672 mục.**

---

## `__init__.py`

### [x] (file rỗng)
1. in/out: 0 LOC. {code}
2-5. side effect / state / lỗi / config: không. {code}
6. ai gọi: đánh dấu package; mọi caller import đường dẫn con
   (`di.py`, `chat/_retrieval.py`, `scripts/build_kb.py`). {code}
7. invariant: không có mặt tiền công khai — giống `llm/` và `guardrails/`,
   khác `db/` và `chat/session/` (hai package đó có `__all__`). Ba kiểu
   `__init__.py` trong cùng một `src/`. {code}
8. deprecated: không. {code}

---

## `cleaning.py`

### [x] `PDF_ARTIFACTS` (`cleaning.py:11-26`)
1. in/out: bảng dịch `str.maketrans` 16 ký tự. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `clean_vi_text:36`, `clean_for_finetuning:90`,
   `research/guideline_docs/pdf_to_text.py:38` (import trực tiếp). {code}
7. invariant: comment `:6-9` nêu ràng buộc **ngoài code** mà không đọc được từ
   code: PDF Việt đời cũ (VN-Times/TCVN3) dùng U+01A3/U+01A2 (chữ "OI" của một
   ngôn ngữ châu Phi) thay cho ư/Ư, và NFC **không** sửa được vì đây là chữ cái
   khác nhau chứ không tương đương chuẩn tắc. Đây là comment chất lượng cao nhất
   tôi gặp trong `src/`. Hệ quả nếu thiếu: "người" → "ngƣời" → BM25 không khớp. {code+comment}
8. deprecated: không. **Nhưng** `utils/text_cleaning.py` là bản sao thiếu đúng
   bảng này (xem `src.utils` Q-09). {code}

### [x] `BOILERPLATE_PATTERNS` (`cleaning.py:22`)
1. in/out: list regex đã compile. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `clean_vi_text`. {code}
7. invariant: trùng tên và nội dung với `utils/text_cleaning.py:11`. Hai bản. {code}
8. deprecated: không. {code}

### [x] `clean_vi_text` (`cleaning.py:32-46`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `PDF_ARTIFACTS`, `BOILERPLATE_PATTERNS`. {code}
6. ai gọi: `scripts/build_kb.py:41,327` (đường build KB thật),
   `tests/test_cleaning.py`. {code}
7. invariant: thứ tự bắt buộc — `normalize("NFC")` **trước** `translate(PDF_ARTIFACTS)`.
   Nếu đảo, NFD sẽ tách ư thành u + dấu và bảng dịch không khớp. Code đúng thứ
   tự (`:35` rồi `:36`), không có comment nào bảo vệ ràng buộc này. Ngoài ra
   `normalize("NFC")` ở đây là thứ giữ cho `utils/retrieval_query.py:_no_accent`
   an toàn về độ dài (xem `src.utils`, khối `_no_accent`). {code}
8. deprecated: không. {code}

### [x] `_FT_PATTERNS` (`cleaning.py:49-80`)
1. in/out: list cặp `(pattern_str, repl)`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_FT_COMPILED`. {code}
7. invariant: định nghĩa dưới dạng chuỗi rồi compile ở dòng sau — khác
   `BOILERPLATE_PATTERNS` vốn compile ngay. Hai kiểu trong một file. {code}
8. deprecated: không. {code}

### [x] `_FT_COMPILED` (`cleaning.py:81`)
1. in/out: list `(compiled, repl)`. {code}
2. side effect: compile lúc import. {code}
3. state: hằng module. {code}
4. lỗi: `re.error` lúc import nếu pattern sai — làm hỏng mọi thứ import
   `rag.cleaning`, kể cả đường chỉ cần `clean_vi_text`. {code}
5. config: `_FT_PATTERNS`. {code}
6. ai gọi: `clean_for_finetuning`. {code}
7. invariant: compile sẵn một lần. {code}
8. deprecated: không. {code}

### [x] `clean_for_finetuning` (`cleaning.py:84-102`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_FT_COMPILED`, `PDF_ARTIFACTS`. {code}
6. ai gọi: **0 chỗ trong `src/`, `scripts/`, `tests/`.** Cần kiểm ở
   `research/LLMData` (nơi sinh dữ liệu fine-tune) — chưa duyệt module đó. Ghi
   lại thành Q-01. {code}
7. invariant: lọc dòng `len(ln.strip()) >= 4` (`:100`) — dòng 1–3 ký tự bị bỏ,
   kể cả dòng chỉ có số mục ("1.", "a)"). Với dữ liệu fine-tune dạng danh sách
   đánh số thì đây là mất cấu trúc. {code}
8. deprecated: không. {code}

---

## `embedder.py`

### [x] docstring `embedder.py:1`
1. in/out: 1 dòng — "Eager-load model at startup for fast inference". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng — `__init__:33-34` gọi `_load()` khi `lazy=False`
   (mặc định). {code+doc}
8. deprecated: không. {doc}

### [x] `_normalize_device` (`embedder.py:7-20`)
1. in/out: `(device: str) -> str`. {code}
2. side effect: `import torch` và `torch.cuda.is_available()`; `logger.warning`
   khi CUDA không có. {code}
3. state: không. {code}
4. lỗi: `except Exception: pass` nuốt mọi lỗi import torch. {code}
5. config: nhận `settings.device` qua `di.py`. {code}
6. ai gọi: `Embedder.__init__:28`. {code}
7. **invariant — bản normalizer thứ hai, và nó hẹp hơn bản thứ nhất:**
   `config.py:139-151` `_normalize_device` (validator) chấp nhận
   `cpu/cuda/cuda:N/mps/auto` và map `gpu/nvidia/cuda:0 → cuda`. Bản ở đây chỉ
   map `gpu → cuda` và trả nguyên `requested` cho mọi giá trị khác — nhưng nó
   **thêm** một việc bản kia không làm được: kiểm CUDA có thật hay không lúc
   chạy và hạ về CPU. Hai hàm cùng tên, hai trách nhiệm khác nhau, không hàm nào
   nêu sự tồn tại của hàm kia. Xem Q-02. {code}
8. deprecated: không. {code}

### [x] `Embedder` (`embedder.py:23-70`)
1. in/out: `Embedder(model_name, device, batch_size, lazy)`. {code}
2. side effect: nạp `SentenceTransformer` (tải model, chiếm RAM/VRAM). {code}
3. state: `_model`, `dim`, `device`, `batch_size`, `model_name`. {code}
4. lỗi: `_load` không bắt gì — model thiếu là `OSError`/`HFValidationError` lúc
   khởi động. `di.py` có bọc. {code}
5. config: `settings.embedding_model`, `settings.device` qua `di.py`. {code}
6. ai gọi: `di.py`; `HybridRetriever.__init__`; `scripts/build_kb.py`. {code}
7. invariant: `model_name` là thuộc tính công khai và `utils/logging.py:123-127`
   đọc nó cho banner khởi động (`getattr(container.embedder, "model_name", ...)`). {code}
8. deprecated: không. {code}

### [x] `Embedder.__init__` (`embedder.py:24-34`)
1. in/out: `(model_name="AITeamVN/Vietnamese_Embedding", device="cpu",
   batch_size=32, lazy=False)`. {code}
2. side effect: nạp model nếu `lazy=False`. {code}
3. state: đặt 5 thuộc tính. {code}
4. lỗi: từ `_load`. {code}
5. config: default `model_name` khớp `config.py:106`; `batch_size=32` **không**
   có field `Settings` tương ứng (khác reranker, vốn có `reranker_batch_size`). {code}
6. ai gọi: `di.py`, `scripts/build_kb.py`, test. {code}
7. invariant: `self.dim = 1024` với comment `# default for BGE-M3`, nhưng model
   mặc định là `AITeamVN/Vietnamese_Embedding`. Giá trị 1024 chỉ là chỗ giữ chỗ
   cho tới khi `_load` hỏi model thật; comment nêu sai model. {code+comment}
8. deprecated: không. {code}

### [x] `Embedder._load` (`embedder.py:36-46`)
1. in/out: `() -> SentenceTransformer`. {code}
2. side effect: tải model, ghi 2 dòng log. {code}
3. state: gán `_model`, `dim`. {code}
4. lỗi: không bắt. {code}
5. config: `self.model_name`, `self.device`. {code}
6. ai gọi: `__init__:34`, `embed_passages:52`, `_embed_query_raw:66`. {code}
7. **invariant — nhánh chết:** `:41` kiểm
   `hasattr(self._model, "get_embedding_dimension")`. `SentenceTransformer`
   không có method tên đó; API thật là `get_sentence_embedding_dimension`, chính
   là nhánh `else` ở `:44`. Nhánh `if` không bao giờ chạy với thư viện hiện tại.
   Vô hại (nhánh else đúng), nhưng là code chết. {code}
8. deprecated: không. {code}

### [x] `Embedder.embed_passages` (`embedder.py:48-57`)
1. in/out: `(texts: list[str]) -> np.ndarray`. {code}
2. side effect: `show_progress_bar=True` — in tiến trình ra stderr. {code}
3. state: không. {code}
4. lỗi: từ model. {code}
5. config: `self.batch_size`, `normalize_embeddings=True`. {code}
6. ai gọi: `scripts/build_kb.py`. Docstring khai "no cache, dung khi build KB" —
   đúng. {code}
7. invariant: `normalize_embeddings=True` là điều kiện để Chroma
   `hnsw:space=cosine` cho khoảng cách đúng nghĩa. Cả hai đầu (index và query)
   đều normalize — `_embed_query_raw:68` cũng vậy. Nhất quán. {code}
8. deprecated: không. {code}

### [x] `Embedder.embed_query` (`embedder.py:59-62`)
1. in/out: `(query: str) -> np.ndarray`. {code}
2. side effect: đọc/ghi DiskCache qua `cached_embed_query`. {code}
3. state: cache trên đĩa. {code}
4. lỗi: từ tầng cache. {code}
5. config: `cache_dir`, `cache_size_gb` (qua `cache.py`). {code}
6. ai gọi: `retriever.retrieve:110`, `retriever.retrieve_safety_pass:~283`. {code}
7. invariant: import `..cache` **bên trong hàm** (`:61`) chứ không ở đầu file —
   để tránh vòng import (`cache.py` gọi ngược lại `_embed_query_raw`). Ràng buộc
   này chỉ hiện ra ở docstring của `_embed_query_raw` ("tranh de quy"). {code}
8. deprecated: không. {code}

### [x] `Embedder._embed_query_raw` (`embedder.py:64-70`)
1. in/out: `(query: str) -> np.ndarray` (1 vector, không phải ma trận). {code}
2. side effect: nạp model nếu chưa. {code}
3. state: không. {code}
4. lỗi: từ model. {code}
5. config: `normalize_embeddings=True`, `show_progress_bar=False`. {code}
6. ai gọi: `cache.py` (đường cache-miss). {code}
7. invariant: `[0]` ở cuối lấy vector đầu — khác `embed_passages` trả ma trận.
   Hai hàm cùng lớp, hai hình dạng đầu ra. {code}
8. deprecated: không. {code}

---

## `sparse.py`

### [x] docstring `sparse.py:1`
1. in/out: 1 dòng — "BM25 sparse index with persistence, Vietnamese stopwords,
   score normalization". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: cả ba đều có mặt trong code (`save`/`load` + checksum,
   `_VI_STOPWORDS`, tham số `normalize`). {code+doc}
8. deprecated: không. {doc}

### [x] `_vi_word_tokenize` (`sparse.py:8-11`)
1. in/out: `underthesea.word_tokenize` hoặc `None` nếu import hỏng. {code}
2. side effect: import lúc module load. {code}
3. state: hằng module. {code}
4. lỗi: `except Exception` nuốt mọi lỗi import → `None`. {code}
5. config: không — phụ thuộc gói có cài hay không. {code}
6. ai gọi: `tokenize_vi:102`. {code}
7. **invariant có hệ quả lớn:** nếu `underthesea` thiếu, `tokenize_vi` rơi về
   `text.lower().split()` — tách theo khoảng trắng. Tiếng Việt là ngôn ngữ đơn
   âm tiết viết rời, nên "mụn trứng cá" thành 3 token thay vì 1 từ ghép. BM25
   index xây bằng một chế độ và truy vấn bằng chế độ kia sẽ lệch hoàn toàn, và
   **không có gì ghi lại chế độ nào đã dùng lúc build**. Checksum ở `save/load`
   bảo vệ nội dung file, không bảo vệ điều này. Xem Q-03. {code}
8. deprecated: không. {code}

### [x] `_VI_STOPWORDS` (`sparse.py:14-24`)
1. in/out: frozenset ~70 từ. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `tokenize_vi:111`. {code}
7. invariant: 8 mục cuối (`"i","ii","iii","iv","v","a","b","c"`) là số La Mã và
   chữ cái đánh mục. Trong đó `"i"`, `"v"`, `"a"`, `"b"`, `"c"` có độ dài 1 nên
   **đã bị** điều kiện `len(t) > 1` ở cùng dòng loại trước — 5/8 mục thừa. Ngoài
   ra `"không"` nằm trong danh sách: BM25 không phân biệt được "dùng được" và
   "không dùng được". Với câu hỏi y khoa dạng phủ định, đây là mất tín hiệu thật.
   Xem Q-04. {code}
8. deprecated: không. {code}

### [x] `tokenize_vi` (`sparse.py:27-42`)
1. in/out: `(text: str, remove_stopwords: bool = True) -> list[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `except Exception` quanh `_vi_word_tokenize` → rơi về `.split()`.
   Lỗi tokenize **im lặng theo từng câu**, không log. {code}
5. config: `_VI_STOPWORDS`. {code}
6. ai gọi: `BM25Index.build:140`, `BM25Index.query:151`,
   `utils/chunk_filter.py:40,126`. {code}
7. invariant: `query` gọi `tokenize_vi(query)` **không truyền tham số** → dùng
   default `remove_stopwords=True`, khớp với `build`. Hai đầu nhất quán — kiểm
   tay `:140` và `:151`. {code}
8. deprecated: không. {code}

### [x] `BM25ChecksumError` (`sparse.py:45-46`)
1. in/out: lớp con `RuntimeError`, không thân. {code}
2-3. không. {code}
4. lỗi: chính nó là kiểu lỗi. {code}
5. config: không. {code}
6. ai gọi: raise ở `load:172,178`; bắt ở `di.py` (4 lần nhắc tên toàn repo). {code}
7. invariant: kế thừa `RuntimeError` chứ không `Exception` trần — `except
   Exception` ở nơi gọi vẫn bắt được. {code}
8. deprecated: không. {code}

### [x] `_checksum_path` (`sparse.py:49-50`)
1. in/out: `(path: Path) -> Path`; thêm đuôi `.sha256`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `save:165`, `load:170`. {code}
7. invariant: `path.with_suffix(path.suffix + ".sha256")` — với
   `bm25_index.pkl` cho ra `bm25_index.pkl.sha256`. Đúng. Với path **không có**
   đuôi thì `path.suffix` là `""` và kết quả là `name.sha256` — vẫn hợp lệ. {code}
8. deprecated: không. {code}

### [x] `_sha256_file` (`sparse.py:53-58`)
1. in/out: `(path: Path) -> str`. {code}
2. side effect: đọc file theo khối 1 MB. {code}
3. state: không. {code}
4. lỗi: `OSError` nếu file không mở được. {code}
5. config: khối 1 MB cứng. {code}
6. ai gọi: `save:165`, `load:176`. {code}
7. invariant: đọc theo khối nên file 50 MB không nạp hết vào RAM. {code}
8. deprecated: không. {code}

### [x] `BM25Index` (`sparse.py:61-114`)
1. in/out: `BM25Index()` không tham số. {code}
2. side effect: không lúc dựng. {code}
3. state: `bm25`, `chunk_ids`, `texts`. {code}
4. lỗi: `query` trả `[]` khi chưa build. {code}
5. config: không đọc `settings`; `di.py` truyền `settings.bm25_path` vào `load`. {code}
6. ai gọi: `di.py`, `scripts/build_kb.py`, `HybridRetriever`. {code}
7. invariant: `self.texts` được lưu vào pickle nhưng **không đọc lại ở đâu** sau
   khi build — `query` chỉ dùng `self.bm25` và `self.chunk_ids`. Nó làm file
   pickle to gấp nhiều lần cần thiết (toàn văn 24k chunk). Grep `\.texts`:
   chỉ `build`, `save`, `load`. Xem Q-05. {code}
8. deprecated: không. {code}

### [x] `BM25Index.__init__` (`sparse.py:62-65`)
1. in/out: `() -> None`. {code}
2-3. đặt 3 thuộc tính rỗng. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `load:181` (`cls()`), và người dùng trực tiếp. {code}
7. invariant: object dựng xong là **không dùng được** cho tới khi `build` hoặc
   `load`. Không có cờ nào đánh dấu trạng thái đó ngoài `bm25 is None`. {code}
8. deprecated: không. {code}

### [x] `BM25Index.build` (`sparse.py:67-71`)
1. in/out: `(chunk_ids: list[str], texts: list[str]) -> None`. {code}
2. side effect: tokenize toàn bộ corpus, dựng `BM25Okapi`. {code}
3. state: đặt cả 3 thuộc tính. {code}
4. lỗi: không kiểm `len(chunk_ids) == len(texts)` — lệch độ dài thì
   `self.chunk_ids[i]` ở `query:153` có thể `IndexError` hoặc trả **sai id**.
   `ChromaStore.upsert:31-32` thì **có** kiểm đúng ràng buộc tương ứng. Hai nơi,
   một có gác một không. Xem Q-06. {code}
5. config: `remove_stopwords=True` cứng. {code}
6. ai gọi: `scripts/build_kb.py`. {code}
7. invariant: `list(...)` bọc cả hai đầu vào → bản sao, người gọi sửa list sau
   đó không ảnh hưởng index. {code}
8. deprecated: không. {code}

### [x] `BM25Index.query` (`sparse.py:73-88`)
1. in/out: `(query: str, top_k: int = 40, normalize: bool = True) -> list[tuple[str, float]]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: trả `[]` nếu chưa build. {code}
5. config: `top_k`, `normalize` từ người gọi. {code}
6. ai gọi: `retriever.retrieve:129` — truyền `normalize=(mode == "sparse")`. {code}
7. invariant: lọc `if s > 0` **trước** khi normalize, nên chunk điểm 0 bị loại
   hẳn chứ không thành 0.0. Ở chế độ `hybrid`, `normalize=False` — điểm BM25 thô
   (thang không chặn trên) đi vào `rrf_fusion`; nhưng RRF chỉ dùng **thứ hạng**
   nên giá trị không quan trọng ở nhánh đó. Nó **có** quan trọng ở nhánh
   `dense_ids` rỗng (xem `retrieve`, Q-08). {code}
8. deprecated: không. {code}

### [x] `BM25Index.save` (`sparse.py:90-95`)
1. in/out: `(path: str) -> None`. {code}
2. side effect: tạo thư mục, ghi pickle, ghi file `.sha256`. {code}
3. state: không. {code}
4. lỗi: `OSError`, `pickle.PicklingError`. {code}
5. config: không. {code}
6. ai gọi: `scripts/build_kb.py`. {code}
7. invariant: ghi pickle **rồi** ghi checksum — nếu tiến trình chết giữa hai
   bước, file pickle tồn tại mà không có checksum, và `load` sẽ raise
   `BM25ChecksumError` với thông điệp "Rebuild BM25 before loading". Fail-closed
   đúng hướng. Không atomic (không ghi ra file tạm rồi rename), nên pickle ghi dở
   cũng cho ra cùng lỗi — vẫn fail-closed. {code}
8. deprecated: không. {code}

### [x] `BM25Index.load` (`sparse.py:97-114`, classmethod)
1. in/out: `(cls, path: str) -> BM25Index`. {code}
2. side effect: đọc 2 file, `pickle.load`. {code}
3. state: dựng instance mới. {code}
4. lỗi: `BM25ChecksumError` khi thiếu checksum hoặc lệch; `OSError`;
   `pickle.UnpicklingError`. {code}
5. config: không. {code}
6. ai gọi: `di.py` (bọc try/except). {code}
7. **invariant — ranh giới tin cậy:** `pickle.load` chạy mã tuỳ ý trong file.
   Checksum bảo vệ **tính toàn vẹn** (file hỏng, ghi dở), **không** bảo vệ trước
   kẻ sửa file — ai ghi được `bm25_index.pkl` thì cũng ghi được
   `bm25_index.pkl.sha256`. Đây là mô hình đe doạ hợp lý cho một file cục bộ do
   chính repo sinh ra, nhưng cần nói rõ trong báo cáo thay vì để checksum trông
   như biện pháp bảo mật. {code}
8. deprecated: không. {code}

---

## `vectorstore.py`

### [x] docstring `vectorstore.py:1`
1. in/out: 1 dòng — "Chroma vector store wrapper". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng, lớp chỉ bọc `chromadb`. {code+doc}
8. deprecated: không. {doc}

### [x] `ChromaStore` (`vectorstore.py:7-150`)
1. in/out: `ChromaStore(persist_dir, collection)`. {code}
2. side effect: tạo thư mục, mở `PersistentClient`, `get_or_create_collection`. {code}
3. state: `client`, `col`. {code}
4. lỗi: `chromadb` raise nếu thư mục hỏng hoặc schema sqlite lệch phiên bản. {code}
5. config: `settings.chroma_dir` qua `di.py`. {code}
6. ai gọi: `di.py`, `scripts/build_kb.py`, `api/routes/kb.py`, `HybridRetriever`. {code}
7. invariant: `metadata={"hnsw:space": "cosine"}` chỉ có tác dụng **khi tạo mới**
   collection; với collection đã tồn tại, `get_or_create` bỏ qua metadata và giữ
   không gian cũ. Nghĩa là mọi lập luận về "distance = 1 − cosine" phụ thuộc vào
   việc collection **ban đầu** được tạo bằng chính dòng này. Không kiểm lại lúc
   mở. Xem Q-07. {code}
8. deprecated: không. {code}

### [x] `ChromaStore.__init__` (`vectorstore.py:8-21`)
1. in/out: `(persist_dir="./data/chroma_db", collection="acne_kb_vi")`. {code}
2. side effect: như trên; `anonymized_telemetry=False`. {code}
3. state: 2 thuộc tính. {code}
4. lỗi: không bắt. {code}
5. config: default `persist_dir` khớp `config.py:154`; tên collection
   `"acne_kb_vi"` là **hằng cứng**, không có field `Settings`. {code}
6. ai gọi: `di.py`, `scripts/build_kb.py`. {code}
7. invariant: `import chromadb` đặt **trong** hàm, không ở đầu file — hoãn chi
   phí import cho ai chỉ cần đọc module. Cùng mẫu với `Embedder._load`. {code}
8. deprecated: không. {code}

### [x] `ChromaStore.upsert` (`vectorstore.py:23-63`)
1. in/out: `(chunks: list[KBChunk], embeddings: list[list[float]], batch_size=512) -> None`. {code}
2. side effect: ghi vào Chroma. {code}
3. state: DB. {code}
4. lỗi: **`ValueError("chunks and embeddings must have the same length")`** —
   gác đúng ràng buộc mà `BM25Index.build` bỏ qua (xem Q-06). {code}
5. config: `batch_size` 512. {code}
6. ai gọi: `scripts/build_kb.py`. {code}
7. invariant: metadata phẳng hoá — `categories` và `tags` bị `",".join(...)`
   thành chuỗi vì Chroma không nhận list. Đây là lý do
   `retriever._split_meta_list` phải tách ngược, và là lý do
   `retriever.retrieve:159` viết `raw_tags.split(",")` thay vì dùng list. Một
   quyết định ở đây tạo ra hai chỗ phải biết về nó. {code}
8. deprecated: không. {code}

### [x] `ChromaStore.count` (`vectorstore.py:65-66`)
1. in/out: `() -> int`. {code}
2. side effect: truy vấn Chroma. {code}
3. state: chỉ đọc. {code}
4. lỗi: từ chromadb. {code}
5. config: không. {code}
6. ai gọi: `query:76` (**mỗi lần truy vấn**), `utils/logging.py:139`,
   `api/routes/kb.py:64`. {code}
7. invariant: `query` gọi `count()` trên **mọi** truy vấn để kẹp `n_results`.
   Với 24.393 chunk, đây là một round-trip DB thừa trên đường nóng của mỗi
   request. Giá trị này gần như không đổi giữa các request. Xem Q-09. {code}
8. deprecated: không. {code}

### [x] `ChromaStore.query` (`vectorstore.py:68-87`)
1. in/out: `(query_embedding, top_k=20, filters=None, include_distances=True)`. {code}
2. side effect: truy vấn Chroma + `count()`. {code}
3. state: chỉ đọc. {code}
4. lỗi: `try/except Exception` quanh phần chuyển vector về list (`:70-74`) —
   nhánh dự phòng làm cùng việc bằng vòng lặp Python. {code}
5. config: không. {code}
6. ai gọi: `query_with_score_filter:102`. **Không ai gọi trực tiếp.** {code}
7. invariant: `n = min(top_k, max(self.col.count(), 1))` — comment `:75` giải
   thích Chroma raise khi `n_results` vượt số chunk. `max(..., 1)` bảo đảm
   `n >= 1` kể cả collection rỗng, khi đó Chroma trả list rỗng thay vì raise. {code}
8. deprecated: không. {code}

### [x] `ChromaStore.query_with_score_filter` (`vectorstore.py:89-137`)
1. in/out: `(query_embedding, top_k=20, max_distance=0.65, filters=None,
   fallback_to_raw=True)`. {code}
2. side effect: qua `query`. {code}
3. state: chỉ đọc. {code}
4. lỗi: `float(dist)` raise nếu distance không parse được. {code}
5. **config — giá trị mặc định thứ ba:** `max_distance=0.65` ở đây,
   `_DENSE_MAX_DISTANCE=0.60` ở `retriever.py:40`, `dense_max_distance=0.60` ở
   `config.py:240`. Đường chính (`retrieve`) truyền tường minh nên dùng 0.60;
   `retrieve_safety_pass` **không** truyền → dùng 0.65. Xem Q-10. {code}
6. ai gọi: `retriever.retrieve:112` (`max_distance=self.dense_max_distance`,
   `fallback_to_raw=False`) và `retriever.retrieve_safety_pass` (không truyền
   tham số nào trong hai). {code}
7. invariant: docstring `:99-100` khai "distance = 1 − cosine_similarity →
   distance < 0.65 ≈ similarity > 0.35" — đúng về đại số, và đúng **chỉ khi**
   collection thật dùng `hnsw:space=cosine` (xem Q-07). {code}
8. deprecated: không. {code}

### [x] `ChromaStore.get_by_id` (`vectorstore.py:139-140`)
1. in/out: `(chunk_id: str)`. {code}
2. side effect: truy vấn Chroma. {code}
3. state: chỉ đọc. {code}
4. lỗi: từ chromadb. {code}
5. config: không. {code}
6. ai gọi: **1 chỗ** — `api/routes/kb.py:80`. Comment `retriever.py:146`
   ("Batch fetch metadata thay vì N lần get_by_id") cho thấy nó **từng** được gọi
   trong vòng lặp retrieve và đã được thay bằng `get_by_ids`. {code}
7. invariant: không `include=`, nên Chroma trả cả `documents` và `metadatas`
   theo mặc định — khác `get_by_ids` vốn khai tường minh. {code}
8. deprecated: không, nhưng chỉ còn một người dùng. {code}

### [x] `ChromaStore.get_by_ids` (`vectorstore.py:143-150`)
1. in/out: `(chunk_ids: list[str]) -> dict`. {code}
2. side effect: truy vấn Chroma. {code}
3. state: chỉ đọc. {code}
4. lỗi: từ chromadb. {code}
5. config: `include=["documents", "metadatas"]`. {code}
6. ai gọi: `retriever.retrieve:150` và `:197`. {code}
7. invariant: trả `{"ids": [], "documents": [], "metadatas": []}` khi input rỗng
   — hình dạng **phẳng**, khác `query` vốn trả list-of-list (`[[...]]`). Người
   gọi ở `retriever.py:151,199` zip trực tiếp không lấy `[0]`, tức đã biết sự
   khác biệt này. Không có gì trong code nêu nó ngoài chính cách dùng. {code}
8. deprecated: không. {code}

---

## `reranker.py`

### [x] docstring `reranker.py:1`
1. in/out: 1 dòng — "Cross-encoder reranker (bge-reranker-v2-m3) voi score
   threshold va normalization". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. **invariant khai báo lỗi thời:** từ "normalization" là tàn dư — comment
   `:84-92` giải thích đã **bỏ** bước sigmoid thừa, và `:93` chỉ còn
   `sigmoid_scores = dict(scores_by_id)`, tức sao chép, không chuẩn hoá gì. {code+doc}
8. deprecated: không. {doc}

### [x] `_RERANK_MIN_SIGMOID` (`reranker.py:8`)
1. in/out: `float = 0.30`. {code}
2-4. không. {code}
5. config: default cho `Reranker.__init__`; `di.py` truyền
   `settings.reranker_min_sigmoid` (cũng 0.30) đè lên. Hai nguồn, cùng số. {code}
6. ai gọi: `__init__:16`. {code}
7. invariant: tên biến còn chữ "sigmoid" dù thang đã là xác suất thật — cùng
   tàn dư từ vựng với docstring và với tên tham số `min_sigmoid_score`, tên biến
   `sigmoid_scores`, và các dòng log `"sigmoid>="`. Năm chỗ mang tên sai. {code}
8. deprecated: không. {code}

### [x] `Reranker` (`reranker.py:11-160`)
1. in/out: `Reranker(model_name, device, max_length, lazy, batch_size,
   cache_size, min_sigmoid_score)`. {code}
2. side effect: nạp `CrossEncoder`. {code}
3. state: `_model`, `_score_cache` (OrderedDict LRU). {code}
4. lỗi: `_load` không bắt. {code}
5. config: `settings.reranker_model`, `device`, `reranker_batch_size`,
   `reranker_cache_size`, `reranker_min_sigmoid` — 5 field, nhiều nhất trong
   `rag/`. {code}
6. ai gọi: `di.py`; `chat/_retrieval.py`; `api/routes/kb.py:64`. {code}
7. invariant: `self.device = device` **thô**, không qua `_normalize_device` như
   `Embedder`. Đặt `DEVICE=gpu` thì embedder tự map sang `cuda` và tự hạ về CPU
   nếu không có, còn reranker đưa thẳng `"gpu"` cho `CrossEncoder` — nhưng
   validator `config.py:_normalize_device` đã map `gpu → cuda` trước đó, nên
   trong đường production giá trị luôn hợp lệ. Rủi ro chỉ hiện khi ai đó dựng
   `Reranker` trực tiếp. Xem Q-02. {code}
8. deprecated: không. {code}

### [x] `Reranker.__init__` (`reranker.py:12-27`)
1. in/out: 7 tham số, mọi cái có default. {code}
2. side effect: nạp model khi `lazy=False`. {code}
3. state: 8 thuộc tính. {code}
4. lỗi: từ `_load`. {code}
5. config: xem trên. {code}
6. ai gọi: `di.py`, test. {code}
7. invariant: `_score_cache` là `OrderedDict` **không lock** — reranker dùng
   chung giữa các request đồng thời của FastAPI. `dict`/`OrderedDict` của CPython
   an toàn cho thao tác đơn dưới GIL, nhưng cặp đọc-rồi-ghi ở `_cache_get`
   (`pop` + gán lại) không nguyên tử. Hậu quả xấu nhất là mất một entry cache,
   không sai kết quả. Xem Q-11. {code}
8. deprecated: không. {code}

### [x] `Reranker._load` (`reranker.py:29-36`)
1. in/out: `() -> CrossEncoder`. {code}
2. side effect: tải model, 2 dòng log. {code}
3. state: gán `_model`. {code}
4. lỗi: không bắt. {code}
5. config: `model_name`, `device`, `max_length`. {code}
6. ai gọi: `__init__:27`, `rerank:72`. {code}
7. invariant: `max_length=512` — cặp (query, chunk) dài hơn bị cắt. Chunk mục
   tiêu là 200 token (`chunker` default) nên hiếm khi chạm trần; nhưng
   `retrieve_safety_pass` dựng query tới **1200 ký tự** (`retriever.py:~277`),
   và cặp đó cũng đi qua reranker. Cần kiểm ở `src.chat` xem query nào thực sự
   được đưa vào `rerank`. {code}
8. deprecated: không. {code}

### [x] `Reranker._cache_get` (`reranker.py:38-45`)
1. in/out: `(key: tuple[str, str]) -> float | None`. {code}
2. side effect: `pop` rồi gán lại → đẩy key về cuối (LRU touch). {code}
3. state: sửa `_score_cache`. {code}
4. lỗi: không. {code}
5. config: `cache_size <= 0` → tắt cache. {code}
6. ai gọi: `rerank:65`. {code}
7. invariant: khoá cache là `(query, chunk_id)` — **query đầy đủ**, không băm.
   Với query 1200 ký tự và 2048 entry, cache giữ tới ~2,5 MB chuỗi. Cache chỉ
   trúng khi **cùng một chuỗi query** gặp lại cùng chunk; trong hội thoại thật
   query đổi mỗi lượt, nên tỉ lệ trúng gần 0 trừ khi người dùng gửi lại đúng câu.
   Xem Q-12. {code}
8. deprecated: không. {code}

### [x] `Reranker._cache_put` (`reranker.py:47-53`)
1. in/out: `(key, score: float) -> None`. {code}
2. side effect: chèn + đẩy cuối + đuổi khi vượt `cache_size`. {code}
3. state: sửa `_score_cache`. {code}
4. lỗi: không. {code}
5. config: `cache_size` (2048 từ `settings.reranker_cache_size`). {code}
6. ai gọi: `rerank:82`. {code}
7. invariant: `popitem(last=False)` đuổi phần tử **cũ nhất** — LRU đúng chiều. {code}
8. deprecated: không. {code}

### [x] `Reranker.rerank` (`reranker.py:55-160`)
1. in/out: `(query: str, retrieval: RetrievalOutput, top_k: int = 5) -> RetrievalOutput`. {code}
2. side effect: chạy cross-encoder; ghi **4 dòng** `logger.debug`. {code}
3. state: điền cache. {code}
4. lỗi: `m.predict` raise nếu model hỏng — không bắt; `chat/_retrieval.py` phải
   xử lý. {code}
5. config: `self.min_sigmoid_score`, `self.batch_size`, `top_k` từ người gọi
   (`settings.chat_rerank_top_k` = 5). {code}
6. ai gọi: `chat/_retrieval.py`. {code}
7. **invariant — thứ tự cắt quan trọng và dễ đọc nhầm:** `:111` lấy
   `top_pairs = all_pairs[:top_k]` **trước**, rồi `:113` mới lọc theo ngưỡng.
   Nghĩa là ngưỡng `min_sigmoid_score` chỉ áp cho 5 chunk đầu; nó **không** kéo
   thêm chunk thứ 6 lên khi một trong 5 chunk đầu bị loại. Kết quả có thể ít hơn
   `top_k` dù pool còn chunk vượt ngưỡng. Đây là lựa chọn hợp lý (giữ nguyên
   xếp hạng) nhưng không được ghi ở đâu, và `chat_rerank_floor=0.50` ở tầng trên
   (`config.py:217`) lại là ngưỡng **thứ hai** trên cùng thang. {code}
8. deprecated: comment `:84-92` là bản ghi lịch sử tốt (giải thích bug sigmoid
   hai lần, dải nén `[0.500, 0.731]`, và rằng các ngưỡng 0.30/0.45/0.58 cũ đều
   được chỉnh theo dải sai đó). Đây là {comment} — tôi đã đối chiếu được một nửa:
   code hiện tại đúng là **không** áp sigmoid lần nào (`:93` chỉ copy dict). Nửa
   còn lại (giá trị quan sát 0.718–0.731) là số đo cũ, không kiểm lại được từ
   code. {code+comment}

---

## `chunker.py`

### [x] docstring `chunker.py:1`
1. in/out: 1 dòng — "Vietnamese-aware recursive chunker voi dedup va micro-chunk
   filtering". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "recursive" là cách gọi rộng — code chia theo đoạn → câu
   → từ, ba tầng cố định, không đệ quy thật. Dedup và lọc micro-chunk thì có thật
   (`_emit:` kiểm `min_size`, hash, shingle). {code+doc}
8. deprecated: không. {doc}

### [x] `_vi_sent_tokenize` (`chunker.py:7-10`)
1. in/out: `underthesea.sent_tokenize` hoặc `None`. {code}
2. side effect: import lúc module load. {code}
3. state: hằng module. {code}
4. lỗi: `except Exception` → `None`. {code}
5. config: phụ thuộc gói cài. {code}
6. ai gọi: `_sent_tokenize:91`. {code}
7. invariant: cùng mẫu phụ thuộc tuỳ chọn như `sparse.py:_vi_word_tokenize`, và
   cùng hệ quả: KB được chia câu bằng một trong hai cách mà **không có bản ghi
   nào** nói cách nào đã dùng. Với chunker thì hậu quả nhẹ hơn (ranh giới câu
   lệch), với BM25 thì nặng (xem Q-03). {code}
8. deprecated: không. {code}

### [x] `_HEADING_RE` (`chunker.py:12-15`)
1. in/out: regex nhận diện tiêu đề — markdown `#{1,4}` hoặc dòng bắt đầu bằng
   chữ hoa, 4–61 ký tự, không dấu câu kết thúc. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_is_heading:104`. {code}
7. invariant: lớp ký tự hoa `[A-ZÀÁẢÃẠĂẶÂẦẤĐÊÔƠƯ]` liệt kê **một phần** nguyên
   âm hoa tiếng Việt — thiếu `Ằ Ắ Ẳ Ẵ È É Ẻ Ẽ Ẹ Ì Í Ỉ Ĩ Ị Ò Ó Ỏ Õ Ọ Ồ Ố Ổ Ỗ Ộ Ờ
   Ớ Ở Ỡ Ợ Ù Ú Ủ Ũ Ụ Ừ Ứ Ử Ữ Ự Ỳ Ý Ỷ Ỹ Ỵ` và nhiều nữa. Tiêu đề bắt đầu bằng
   những chữ đó ("Điều trị" lọt vì Đ có; "Ức chế" không lọt vì Ứ thiếu) sẽ bị coi
   là đoạn văn thường. Hệ quả: tiêu đề đó không được gắn vào đoạn sau. Xem Q-13. {code}
8. deprecated: không. {code}

### [x] `_FOOTER_PATTERNS` (`chunker.py:17-49`)
1. in/out: list 30 regex đã compile, `re.IGNORECASE`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_is_footer_chunk:80`. {code}
7. invariant: trộn hai ngôn ngữ (Việt: "hotline", "đặt lịch", "nhắn tin zalo";
   Anh: "newsletter", "privacy policy", "all rights reserved") — hợp lý vì KB có
   cả nguồn Việt lẫn Anh. `r"xem thêm"` và `r"advertisement"` đủ chung để khớp
   trong nội dung thật, nhưng ngưỡng đếm (dưới) hạn chế điều đó. {code}
8. deprecated: không. {code}

### [x] `_FOOTER_THRESHOLD_SHORT` (`chunker.py:50`)
1. in/out: `int = 1`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_is_footer_chunk:82`. {code}
7. invariant: chunk **dưới 120 từ** chỉ cần **1** khớp là bị vứt. Một chunk
   ngắn nói "xem thêm hướng dẫn của NICE" mất trắng. Đánh đổi có ý thức (chunk
   ngắn ít giá trị) nhưng không có comment nào nói vậy. {code}
8. deprecated: không. {code}

### [x] `_FOOTER_THRESHOLD_LONG` (`chunker.py:51`)
1. in/out: `int = 3`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_is_footer_chunk:83`. {code}
7. invariant: chunk dài cần 3 khớp — bảo vệ nội dung thật khỏi một lần nhắc
   "hotline". Hai ngưỡng cho hai độ dài là thiết kế đúng hướng. {code}
8. deprecated: không. {code}

### [x] `_FOOD_DOMAIN_RE` (`chunker.py:53-60`)
1. in/out: regex bắt ngữ cảnh ẩm thực của cụm "trứng cá". {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_is_food_domain:87`. {code}
7. invariant: đây là bộ lọc đồng âm — "mụn trứng cá" (acne) và "trứng cá" (trứng
   của cá, caviar) trùng cụm. Mọi nhánh của regex đều đòi **ngữ cảnh nấu nướng**
   ("trứng cá hồi", "cháo trứng cá", "món ăn ... trứng cá"), nên không bắt nhầm
   văn bản y khoa. Là bảng term được thiết kế cẩn thận, khác hẳn các bảng khớp
   chuỗi con ở `chunk_filter.py` và `fold.py`. {code}
8. deprecated: không. {code}

### [x] `_NEAR_DUP_SHINGLE_N` (`chunker.py:62`)
1. in/out: `int = 4`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_shingle_set:66`. {code}
7. invariant: shingle **theo ký tự** (`norm[i:i+4]`), không theo từ — hợp với
   tiếng Việt không cần tokenizer, nhưng làm hai văn bản khác nhau về nội dung mà
   giống về phân bố ký tự có Jaccard cao giả tạo. Ngưỡng 0.90 bù lại. {code}
8. deprecated: không. {code}

### [x] `_NEAR_DUP_THRESHOLD` (`chunker.py:63`)
1. in/out: `float = 0.90`. {code}
2-4. không. {code}
5. config: hằng cứng, không có field `Settings`. {code}
6. ai gọi: `chunk._emit` (`:~152`). {code}
7. invariant: 0.90 trên Jaccard của 4-gram ký tự là ngưỡng **rất cao** — chỉ bắt
   bản sao gần như y hệt. Chunk chồng lấn 40 token trên 200 (overlap mặc định)
   cho Jaccard ~0.2, nên overlap cố ý không bị dedup nhầm. Hai hằng nhất quán. {code}
8. deprecated: không. {code}

### [x] `_shingle_set` (`chunker.py:66-68`)
1. in/out: `(text: str, n: int = 4) -> set[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (`range` âm cho set rỗng khi text < n). {code}
5. config: `_NEAR_DUP_SHINGLE_N`. {code}
6. ai gọi: `_emit` (2 lần: dựng cho candidate, so với `seen_shingles`). {code}
7. invariant: chuẩn hoá khoảng trắng + lower trước khi cắt. Với chunk 200 từ
   (~1200 ký tự) cho ra ~1200 shingle — set này được **giữ lại toàn bộ** trong
   `seen_shingles` cho mọi chunk của tài liệu. Xem Q-14. {code}
8. deprecated: không. {code}

### [x] `_jaccard` (`chunker.py:71-77`)
1. in/out: `(s1: set, s2: set) -> float`. {code}
2-3. không. {code}
4. lỗi: trả 0.0 khi một set rỗng. {code}
5. config: không. {code}
6. ai gọi: `_emit`. {code}
7. invariant: `if union else 0.0` ở `:77` là nhánh chết — `union == 0` chỉ khi cả
   hai set rỗng, đã bị `:73` chặn trước. {code}
8. deprecated: không. {code}

### [x] `_is_footer_chunk` (`chunker.py:79-84`)
1. in/out: `(text: str, word_count: int) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: hai ngưỡng. {code}
6. ai gọi: `_emit`. {code}
7. invariant: chạy **cả 30** regex trên mọi candidate để đếm, không thoát sớm
   khi đã đủ ngưỡng. Với KB 24k chunk là 720k lần `search`. Chỉ chạy lúc build. {code}
8. deprecated: không. {code}

### [x] `_is_food_domain` (`chunker.py:86-88`)
1. in/out: `(text: str) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_FOOD_DOMAIN_RE`. {code}
6. ai gọi: `_emit`. {code}
7. invariant: loại **cả chunk** khi khớp — không cắt riêng đoạn ẩm thực. Một bài
   vừa nói về mụn vừa có một câu về trứng cá hồi sẽ mất cả chunk đó. {code}
8. deprecated: không. {code}

### [x] `_sent_tokenize` (`chunker.py:90-97`)
1. in/out: `(text: str) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: `except Exception: pass` rồi rơi xuống regex — nuốt im lặng. {code}
5. config: `_vi_sent_tokenize`. {code}
6. ai gọi: `chunk` (`:~176`). {code}
7. invariant: fallback `re.split(r"(?<=[.!?])\s+")` không xử lý viết tắt
   ("TS.", "BS.", "0.5 mg") — mỗi dấu chấm thành ranh giới câu. Với văn bản y
   khoa đầy nồng độ ("0.1%", "2.5 mg") thì phân mảnh nặng. Chỉ xảy ra khi
   `underthesea` vắng mặt. {code}
8. deprecated: không. {code}

### [x] `_is_heading` (`chunker.py:100-106`)
1. in/out: `(text: str) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_HEADING_RE`. {code}
6. ai gọi: `chunk` (`:~131`). {code}
7. invariant: ba cổng — dài > 120 loại, có `[.!?]` kèm khoảng trắng loại, rồi
   mới `_HEADING_RE.match`. Cổng thứ hai dùng `re.search(r"[.!?]\s")` nên tiêu đề
   kết thúc bằng dấu chấm **không có khoảng trắng sau** vẫn lọt. {code}
8. deprecated: không. {code}

### [x] `_content_hash` (`chunker.py:109-111`)
1. in/out: `(text: str) -> str`; sha1 16 ký tự hex. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `_emit`. {code}
7. invariant: sha1 chứ không sha256 — dùng cho dedup nội bộ, không cho bảo mật,
   nên chấp nhận được. 16 hex = 64 bit; với 24k chunk xác suất đụng ~1e-11.
   Lưu ý repo có **hai** hàm băm nội dung: hàm này và
   `utils/hashing.py:stable_hash` (sha256, 10 ký tự). {code}
8. deprecated: không. {code}

### [x] `VietnameseChunker` (`chunker.py:114-234`)
1. in/out: `VietnameseChunker(chunk_size=200, overlap=40, min_size=50, dedup=True)`. {code}
2. side effect: `logger.debug` mỗi lần vứt chunk. {code}
3. state: 4 thuộc tính; `dedup` bị `chunk_with_stats` sửa (xem dưới). {code}
4. lỗi: không raise. {code}
5. config: **không có field `Settings` nào** cho 4 tham số này —
   `scripts/build_kb.py` là nơi duy nhất dựng, với giá trị của riêng nó. Kích
   thước chunk của KB 24.393 chunk vì thế không nằm trong `.env`. {code}
6. ai gọi: `scripts/build_kb.py`. {code}
7. invariant: `chunk_size`/`overlap`/`min_size` đo bằng **từ** (`_tok_len` =
   `len(text.split())`), không phải token của model. `llm_num_ctx=8192` và
   `chat_max_context_chars=6000` đo bằng đơn vị khác. Ba đơn vị đo trong một
   đường ống. {code}
8. deprecated: không. {code}

### [x] `VietnameseChunker.__init__` (`chunker.py:115-119`)
1. in/out: 4 tham số, không annotation kiểu. {code}
2. side effect: không. {code}
3. state: 4 thuộc tính. {code}
4. lỗi: không kiểm `overlap < chunk_size` — đặt `overlap=300, chunk_size=200`
   khiến vòng lặp overlap ở `:~205` giữ lại toàn bộ buffer và chunk không tiến
   được. Không có gác. {code}
5. config: xem trên. {code}
6. ai gọi: `scripts/build_kb.py`, test. {code}
7. invariant: đây là hàm duy nhất trong `rag/` **không** có type hint. {code}
8. deprecated: không. {code}

### [x] `VietnameseChunker._tok_len` (`chunker.py:121-123`, staticmethod)
1. in/out: `(text: str) -> int`; `len(text.split())`. {code}
2-3. không. {code}
4. lỗi: `AttributeError` nếu không phải str. {code}
5. config: không. {code}
6. ai gọi: 6 chỗ trong `chunk` và `chunk_with_stats`. {code}
7. invariant: đếm **từ tách bởi khoảng trắng**, tức âm tiết trong tiếng Việt.
   "mụn trứng cá" = 3. Ước lượng token của LLM sẽ khác; comment
   `chat/session/models.py:65` ("~570 tokens" cho 2000 ký tự) dùng một hệ quy đổi
   khác nữa. {code}
8. deprecated: không. {code}

### [x] `VietnameseChunker.chunk` (`chunker.py:125-217`)
1. in/out: `(text: str) -> list[str]`. {code}
2. side effect: `logger.debug` cho mỗi chunk bị vứt. {code}
3. state: `seen_hashes`, `seen_shingles` cục bộ **mỗi lần gọi** — dedup chỉ
   trong phạm vi một tài liệu, không xuyên tài liệu. {code}
4. lỗi: trả `[]` cho text rỗng. {code}
5. config: 4 thuộc tính instance. {code}
6. ai gọi: `scripts/build_kb.py`, `chunk_with_stats`. {code}
7. invariant: gom tiêu đề vào đoạn **kế tiếp** (`:~135`), và buffer **không**
   bắc qua ranh giới đoạn (`:~215`, có comment nói rõ). Overlap được cắt từ đuôi
   buffer **trước** khi flush (`:~203`), nên chunk sau mang phần cuối chunk trước
   — đúng ý overlap. Hai tiêu đề liên tiếp: tiêu đề trước được emit như một
   candidate riêng (`:~133`) và gần như chắc chắn bị `min_size=50` loại. {code}
8. deprecated: không. {code}

### [x] `_emit` (nested trong `chunk`, `chunker.py:~145-165`)
1. in/out: `(candidate: str) -> None`; thêm vào `chunks` nếu qua hết cổng. {code}
2. side effect: sửa `chunks`, `seen_hashes`, `seen_shingles`; ghi log. {code}
3. state: closure trên 3 biến của `chunk`. {code}
4. lỗi: không. {code}
5. config: `self.min_size`, `self.dedup`, `_NEAR_DUP_THRESHOLD`. {code}
6. ai gọi: 4 chỗ trong `chunk`. {code}
7. invariant: **thứ tự cổng**: `min_size` → footer → food-domain → exact-dedup →
   near-dedup. Đặt `min_size` trước là đúng (rẻ nhất); near-dedup cuối cùng là
   đắt nhất. `seen_hashes.add` và `seen_shingles.append` chỉ chạy khi
   `self.dedup` True, nên với `dedup=False` hai cấu trúc này rỗng và mọi so sánh
   bị bỏ qua — nhất quán. {code}
8. deprecated: không. {code}

### [x] `VietnameseChunker.chunk_with_stats` (`chunker.py:219-234`)
1. in/out: `(text: str) -> tuple[list[str], dict]`. {code}
2. side effect: chạy `chunk` **hai lần** trên cùng văn bản. {code}
3. **state — rò rỉ:** `:220-223` lưu `before = self.dedup`, đặt `False`, chạy,
   rồi `self.dedup = before` — **nhưng dòng ngay sau đó ghi đè
   `self.dedup = True`**. Nghĩa là gọi hàm này trên một chunker dựng với
   `dedup=False` sẽ **bật dedup vĩnh viễn** cho object đó. Xem Q-15. {code}
4. lỗi: không. {code}
5. config: `self.dedup`. {code}
6. ai gọi: **0 chỗ toàn repo.** Grep `chunk_with_stats` = chỉ dòng định nghĩa. {code}
7. invariant: chi phí gấp đôi `chunk` (tokenize + dedup toàn bộ hai lượt) để
   lấy 6 con số thống kê mà không ai đọc. {code}
8. deprecated: 0 caller. Xem Q-15. {code}

---

## `retriever.py`

### [x] docstring `retriever.py:1-6`
1. in/out: 6 dòng lời khai. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Ba bảng boost chỉ có nguồn sự thật tại module này. Riêng
   `dense_max_distance` thuộc config vì production DI luôn truyền Settings."
   **Đối chiếu:** grep `_SOURCE_TYPE_BOOST`, `_TRUST_LEVEL_BOOST`,
   `_AUTHORITY_TAG_BOOST` — cả ba chỉ xuất hiện trong file này. Lời khai đúng.
   Câu thứ hai cũng đúng: `di.py` truyền `settings.dense_max_distance`. {code+doc}
8. deprecated: không. {doc}

### [x] `_SOURCE_TYPE_BOOST` (`retriever.py:23-33`)
1. in/out: dict 9 loại nguồn → hệ số 0.70–1.60. {code}
2-4. không. {code}
5. config: hằng cứng, không có field `Settings`. {code}
6. ai gọi: `_trust_boost:73`. {code}
7. invariant: comment `:19-22` nêu **trần cứng ~1.67** và lý do: boost nhân vào
   score **trước** khi tính `relative_threshold = max_score * 0.30`; vượt 1.67
   thì mọi chunk chỉ có mặt ở một trong hai list bị cắt sạch, tức vô hiệu hoá
   hybrid retrieval. Kiểm số: chunk ở cả hai list rank 0 được
   2/61 ≈ 0.0328; chunk chỉ một list rank 0 được 1/61 ≈ 0.0164 — đúng tỉ lệ 2:1,
   nên hệ số boost > 2/0.30... thực ra ngưỡng cắt là 0.30 × max. Với max được
   boost 1.60 → 0.0328×1.60 = 0.0525, ngưỡng = 0.0157; chunk một-list không boost
   = 0.0164 > 0.0157, vừa đủ sống. Boost 1.70 cho ngưỡng 0.0167 > 0.0164 → chết.
   **Con số 1.67 trong comment kiểm được và đúng.** Đây là comment tốt nhất trong
   module. {code+comment}
8. deprecated: không. {code}

### [x] `_TRUST_LEVEL_BOOST` (`retriever.py:36`)
1. in/out: `{"high": 1.4, "medium": 1.0, "low": 0.7}`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_trust_boost:75` — **chỉ khi** `_source_type_from_meta` trả
   `"unknown"`. {code}
7. invariant: comment `:35` gọi đây là "fallback cho chunks cũ chưa có
   source_type". Vì `_source_type_from_meta` còn **suy ra** source_type từ
   tên/domain/url/tag, nhánh này chỉ chạy khi cả metadata lẫn suy luận đều thất
   bại. Tần suất thật cần đo trên KB — không đọc được từ code. {code+comment}
8. deprecated: không. {code}

### [x] `_AUTHORITY_TAG_BOOST` (`retriever.py:38`)
1. in/out: `float = 1.15`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `retrieve:~163`. {code}
7. invariant: **nhân chồng** lên `_trust_boost` — một chunk `nice_guideline` có
   tag "guidelines" được 1.60 × 1.15 = **1.84**, vượt trần 1.67 mà comment
   `:19-22` cảnh báo. Theo chính lập luận đó, chunk một-list không boost bị cắt
   khi có mặt chunk như vậy trong pool. Comment nói về trần của **một** bảng, còn
   code nhân **hai** bảng. Xem Q-16. {code+comment}
8. deprecated: không. {code}

### [x] `_DENSE_MAX_DISTANCE` (`retriever.py:40`)
1. in/out: `float = 0.60`. {code}
2-4. không. {code}
5. config: default của `HybridRetriever.__init__`; `di.py` đè bằng
   `settings.dense_max_distance` (cũng 0.60). {code}
6. ai gọi: `HybridRetriever.__init__:88`. {code}
7. invariant: comment `:39` khai đúng vai trò ("default đồng bộ cho caller trực
   tiếp và test"). Nhưng đây là giá trị **thứ hai** trong ba —
   `vectorstore.query_with_score_filter` mặc định 0.65 (Q-10). {code+comment}
8. deprecated: không. {code}

### [x] `_MIN_FUSION_SCORE` (`retriever.py:41`)
1. in/out: `float = 0.005`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `retrieve:~172,185`. {code}
7. invariant: sàn tuyệt đối. Với RRF thuần (không boost), chunk hạng 0 được
   0.0164 và hạng ~200 được 1/260 ≈ 0.0038 < 0.005 — nên sàn này chỉ chạm khi
   pool rất sâu. Ở nhánh `dense_ids` rỗng (điểm BM25 thô, thang 0–30) thì
   0.005 là vô nghĩa. Xem Q-08. {code}
8. deprecated: không. {code}

### [x] `_MIN_FUSION_SCORE_RELATIVE` (`retriever.py:42`)
1. in/out: `float = 0.30`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `retrieve:~173`, và trong dòng log `:~183`. {code}
7. invariant: là hằng quyết định trần boost 1.67 (xem `_SOURCE_TYPE_BOOST`).
   Comment `:22` nói đúng: "Muốn vượt phải hạ `_MIN_FUSION_SCORE_RELATIVE`".
   Hai hằng ràng buộc nhau và điều đó **có** được ghi lại — hiếm trong repo này. {code+comment}
8. deprecated: không. {code}

### [x] `_split_meta_list` (`retriever.py:45-51`)
1. in/out: `(value) -> list[str]`; nhận str hoặc list. {code}
2-3. không. {code}
4. lỗi: trả `[]` cho mọi kiểu khác. {code}
5. config: không. {code}
6. ai gọi: `_source_type_from_meta:62,63`. {code}
7. invariant: tồn tại vì `ChromaStore.upsert:55-56` phẳng hoá list thành chuỗi
   `","`-join. Hàm này là chiều ngược lại. Nhưng `retrieve:~159` **không** dùng
   nó — chỗ đó tự viết `raw_tags.split(",")`. Hai cách tách cùng một trường
   trong cùng một file. {code}
8. deprecated: không. {code}

### [x] `_source_type_from_meta` (`retriever.py:54-66`)
1. in/out: `(meta: dict) -> str`. {code}
2. **side effect: sửa `meta` tại chỗ** — `:65` gán `meta["source_type"] = inferred`.
   Hàm tên "from_meta" ghi ngược vào meta. {code}
3. state: sửa dict của người gọi (chính là metadata sẽ đi vào `RetrievedChunk`). {code}
4. lỗi: không. {code}
5. config: `infer_source_type` từ `schemas/kb.py`. {code}
6. ai gọi: `_trust_boost:70`, `retrieve:~218`, `retrieve_safety_pass:~300`. {code}
7. invariant: việc ghi ngược **có ích** — nó khiến lần gọi sau trên cùng dict
   không phải suy luận lại, và khiến `RetrievedChunk.metadata` mang source_type
   đã suy ra. Nhưng nó cũng nghĩa là dict metadata mà Chroma trả về bị thay đổi,
   và nếu Chroma cache object đó thì thay đổi lan ra ngoài phạm vi request. Không
   có comment nào nói về side effect này. Xem Q-17. {code}
8. deprecated: không. {code}

### [x] `_trust_boost` (`retriever.py:69-74`)
1. in/out: `(meta: dict) -> float`. {code}
2. side effect: gián tiếp qua `_source_type_from_meta`. {code}
3. state: gián tiếp. {code}
4. lỗi: không. {code}
5. config: hai bảng boost. {code}
6. ai gọi: `retrieve:~161`. {code}
7. invariant: `_SOURCE_TYPE_BOOST.get(source_type, 1.0)` — loại nguồn lạ được
   hệ số **trung tính** 1.0, không phải bị phạt. Kết hợp với `"unknown": 1.00`
   trong bảng, nghĩa là không biết nguồn ≡ nguồn Việt phổ thông
   (`vi_medical_site: 1.00`). {code}
8. deprecated: không. {code}

### [x] `rrf_fusion` (`retriever.py:76-81`)
1. in/out: `(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `k=60` **hằng cứng**, không có field `Settings`, và không caller nào
   truyền khác. {code}
6. ai gọi: `retrieve:~154`; test. {code}
7. invariant: công thức RRF chuẩn `1/(k + rank + 1)`. Với `k=60` (giá trị của
   Cormack 2009) và top-45 (`fetch_k = min(15*3, 60)`), khoảng điểm là
   1/61 = 0.0164 đến 1/105 = 0.0095 — **biên độ 1.7×**. Thứ hạng gần nhau gần
   như không phân biệt được, và boost 1.6× đủ để đảo hoàn toàn thứ tự dense.
   Đó chính là ý đồ (comment `:16-18`), nhưng nó cũng nghĩa là bảng boost, chứ
   không phải RRF, quyết định thứ tự vào reranker. {code}
8. deprecated: không. {code}

### [x] `HybridRetriever` (`retriever.py:84-326`)
1. in/out: `HybridRetriever(store, embedder, bm25, dense_max_distance)`. {code}
2. side effect: qua các thành phần. {code}
3. state: 4 thuộc tính, không đổi sau khi dựng. {code}
4. lỗi: `retrieve` bắt lỗi dense và rơi về sparse; không bắt lỗi sparse. {code}
5. config: `settings.dense_max_distance`. {code}
6. ai gọi: `di.py`; `chat/_retrieval.py`. {code}
7. invariant: `embedder` khai `Embedder | None` và `bm25` khai `BM25Index | None`
   — cả hai có thể vắng. Nếu **cả hai** vắng, `retrieve` trả `RetrievalOutput`
   rỗng chứ không raise. `di.py` dùng cờ `rag_ready` để biết. {code}
8. deprecated: không. {code}

### [x] `HybridRetriever.__init__` (`retriever.py:85-95`)
1. in/out: 4 tham số. {code}
2. side effect: không. {code}
3. state: 4 thuộc tính. {code}
4. lỗi: không. {code}
5. config: `dense_max_distance` mặc định `_DENSE_MAX_DISTANCE`. {code}
6. ai gọi: `di.py`, test. {code}
7. invariant: `store` là tham số **bắt buộc** dù `retrieve` ở chế độ `sparse`
   không cần nó — trừ nhánh `get_by_ids` để lấy text, vốn **luôn** cần. Nên
   BM25-only vẫn phụ thuộc Chroma để lấy nội dung chunk. {code}
8. deprecated: không. {code}

### [x] `HybridRetriever.retrieve` (`retriever.py:97-232`)
1. in/out: `(query: str, top_k=15, mode="hybrid", domain_filter=None) -> RetrievalOutput`. {code}
2. side effect: truy vấn Chroma + BM25; `_source_type_from_meta` sửa metadata;
   6 dòng `logger.debug`. {code}
3. state: không của instance. {code}
4. lỗi: dense bọc `try/except Exception` → `logger.warning` + sparse-only; hai
   lần `get_by_ids` bọc `try/except` → `logger.debug` và bỏ qua (chunk mất text
   sẽ bị `if not text: continue` loại im lặng). {code}
5. config: `self.dense_max_distance`; `fetch_k = min(top_k * 3, 60)` cứng. {code}
6. ai gọi: `chat/_retrieval.py`. {code}
7. **invariant — `score` mang bốn ý nghĩa khác nhau tuỳ nhánh:**
   - `mode="dense"`: `1.0/(i+1)` → 1.0, 0.5, 0.33… (thang thứ hạng)
   - `mode="sparse"`: BM25 chuẩn hoá → [0, 1]
   - `mode="hybrid"` có dense: RRF × boost → **~0.016–0.052**
   - `mode="hybrid"` không có dense: **BM25 thô** × boost (thang không chặn trên,
     vì `:129` truyền `normalize=(mode == "sparse")` = False)
   Bốn thang này cùng chảy vào cùng một `RetrievedChunk.score` và cùng đi qua
   các ngưỡng hạ nguồn (`chat_min_chunk_score = 0.25`, `chat_rerank_floor = 0.50`).
   Với nhánh hybrid-có-dense, **mọi** score đều < 0.25. Đây là hệ quả cần kiểm
   ở `chat/_retrieval.py`; ghi lại thành Q-08. {code}
8. deprecated: ba comment `# FIX:` / `# FIX 2:` (`:146`, `:169`) là ghi chú sửa
   lỗi còn sót lại trong code production. {comment}

### [x] `HybridRetriever.GUIDELINE_SOURCE_TYPES` (`retriever.py:238`)
1. in/out: tuple 3 loại — `nice_guideline`, `aad_guideline`, `clinical_textbook`. {code}
2-4. không. {code}
5. config: hằng lớp. {code}
6. ai gọi: `chat/_retrieval.py` (truyền vào `retrieve_safety_pass`). {code}
7. invariant: comment `:235-237` nêu con số kiểm được: hẹp hơn
   `SAFETY_SOURCE_TYPES` vì bỏ `pubmed_review` ("4825 chunk abstract PubMed
   trong corpus web sẽ áp đảo") và `jid_paper`; còn lại "973 chunk". Hai con số
   này là {comment} — không đọc được từ code, phải đo trên Chroma. Nhưng chúng
   khớp với comment `config.py:186-189` ("973 chunk"), nên ít nhất **nhất quán
   giữa hai nơi**. {code+comment}
8. deprecated: không. {code}

### [x] `HybridRetriever.SAFETY_SOURCE_TYPES` (`retriever.py:241-242`)
1. in/out: tuple 5 loại (thêm `jid_paper`, `pubmed_review`). {code}
2-4. không. {code}
5. config: hằng lớp; là **default** của `retrieve_safety_pass`. {code}
6. ai gọi: `retrieve_safety_pass:~289`. {code}
7. invariant: comment `:239-240` nêu lý do rộng hơn ("dữ liệu thai kỳ / tương
   tác thuốc hay nằm trong nghiên cứu gốc chứ không chỉ trong khuyến cáo") — lập
   luận lâm sàng hợp lý, và code khớp. {code+comment}
8. deprecated: không. {code}

### [x] `HybridRetriever.retrieve_safety_pass` (`retriever.py:244-326`)
1. in/out: `(query, safety_terms=None, top_k=5, source_types=None) -> RetrievalOutput`. {code}
2. side effect: 1–2 truy vấn Chroma; `_source_type_from_meta` sửa metadata;
   log. {code}
3. state: không. {code}
4. lỗi: mọi truy vấn bọc `try/except Exception` → trả `_EMPTY`. Đây là hàm chịu
   lỗi tốt nhất trong module. {code}
5. **config: không truyền `max_distance` cho `query_with_score_filter`** →
   nhận default **0.65** thay vì 0.60 của đường chính; và không truyền
   `fallback_to_raw` → nhận **True** thay vì False. Hai khác biệt so với
   `retrieve:112-117`. Xem Q-10. {code}
6. ai gọi: `chat/_retrieval.py`, hai chế độ (guideline pass chạy cho **mọi**
   truy vấn; safety pass khi có `safety_terms`). {code}
7. invariant: sau khi truy vấn có filter, nếu `ids` rỗng thì `:~294` truy vấn lại
   **không filter**, rồi `:~302` vẫn loại mọi chunk có `source_type` ngoài danh
   sách. Thoạt nhìn là vô ích, nhưng **không phải**: `_source_type_from_meta`
   biết **suy ra** source_type từ tên/domain/url/tag, còn bộ lọc `$in` của Chroma
   chỉ đọc trường `source_type` đã lưu. Chunk thiếu trường đó trong metadata sẽ
   trượt filter Chroma nhưng qua được kiểm Python. Nhánh dự phòng vì thế cứu được
   đúng nhóm chunk cũ chưa gắn nhãn. Không có comment nào nói điều này. {code}
8. deprecated: docstring `:~262-264` giải thích thay đổi so với bản cũ ("trước
   đây hàm bắt buộc có safety_terms nên guideline chỉ lọt vào pool khi truy vấn
   tình cờ nhắc thuốc kê đơn") — lời khai lịch sử, khớp với chữ ký hiện tại
   (`safety_terms` có default None). {code+doc}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — `clean_for_finetuning` (`cleaning.py:84`) không có caller trong
`src/`, `scripts/`, `tests/`.** Phải kiểm `research/LLMData` (chưa duyệt) xem bộ
dữ liệu fine-tune của `acne-generator-v2` có đi qua hàm này không. Quan trọng vì
bản song sinh chết ở `utils/text_cleaning.py` **thiếu** `PDF_ARTIFACTS`
(`src.utils` Q-09) — nếu dataset fine-tune từng sinh bằng bản kia thì nó mang lỗi
ƣ/Ƣ. {code}

**Q-02 — ba nơi chuẩn hoá `device`, ba hành vi.**
`config.py:139-151` (validator: map alias, chấp nhận `cuda:N/mps/auto`),
`rag/embedder.py:7-20` (map `gpu → cuda`, **kiểm CUDA thật** và hạ về CPU),
`rag/reranker.py:18` (`self.device = device`, không chuẩn hoá gì). Hệ quả thật:
đặt `DEVICE=cuda` trên máy không có GPU thì embedder tự hạ về CPU còn reranker
vẫn đưa `"cuda"` cho `CrossEncoder` → lỗi lúc nạp model. Đường production hiện
đặt `DEVICE=cpu` nên chưa nổ. {code}

**Q-03 — `underthesea` là phụ thuộc tuỳ chọn nhưng quyết định chất lượng BM25,
và không có bản ghi nào nói lúc build đã dùng chế độ nào.**
`sparse.py:8-11` + `chunker.py:7-10`. Thiếu gói → tách theo khoảng trắng. Index
xây bằng một chế độ và truy vấn bằng chế độ kia sẽ lệch. File `.sha256` bảo vệ
nội dung pickle, không bảo vệ điều này. Đề xuất rẻ nhất: ghi cờ
`tokenizer="underthesea"|"whitespace"` vào chính pickle và kiểm lúc `load`. {code}

**Q-04 — `"không"` nằm trong `_VI_STOPWORDS`.**
`sparse.py:19`. BM25 không phân biệt "dùng được" và "không dùng được". Với câu
hỏi y khoa dạng phủ định ("bà bầu **không** được dùng gì") đây là mất tín hiệu
thật. 5/8 mục cuối của danh sách (`i, v, a, b, c`) còn thừa vì đã bị
`len(t) > 1` loại. {code}

**Q-05 — `BM25Index.texts` được lưu vào pickle nhưng không bao giờ đọc lại.**
`sparse.py:65,69,93,110`. Grep `\.texts` chỉ ra `build`/`save`/`load`. Nó chứa
toàn văn 24.393 chunk — phần lớn kích thước file `bm25_index.pkl` là dữ liệu
chết. {code}

**Q-06 — `BM25Index.build` không kiểm `len(chunk_ids) == len(texts)`.**
`sparse.py:67-71`. `ChromaStore.upsert:31-32` **có** kiểm ràng buộc tương ứng và
raise `ValueError`. Nếu hai list lệch, `query:153` trả **sai chunk_id** — không
lỗi, chỉ sai kết quả. Một dòng `if` là đủ. {code}

**Q-07 — `hnsw:space=cosine` chỉ áp lúc tạo collection.**
`vectorstore.py:17-21`. Với collection đã tồn tại, `get_or_create_collection`
giữ không gian cũ và bỏ qua metadata. Mọi lập luận về "distance = 1 − cosine"
(`:99-100`, `config.py:239`) phụ thuộc vào việc `data/chroma_db` được tạo bằng
chính dòng này. Với khoá luận: nên kiểm một lần
(`col.metadata` / `col.configuration_json`) và ghi kết quả vào báo cáo. {code}

**Q-08 — `RetrievedChunk.score` có bốn thang, và thang của đường chính nằm dưới
mọi ngưỡng hạ nguồn.**
`retriever.retrieve` trả: dense `1/(i+1)` ∈ (0,1]; sparse chuẩn hoá [0,1];
hybrid-có-dense RRF×boost ≈ **0.016–0.052**; hybrid-không-dense BM25 thô (không
chặn trên). Trong khi `config.py:200` đặt `chat_min_chunk_score = 0.25` và
`config.py:217` đặt `chat_rerank_floor = 0.50`. Với nhánh hybrid-có-dense, mọi
score < 0.25. Comment `config.py:194-199` **đã biết** điều này — nó nói 0.25 chỉ
có nghĩa ở nhánh `_full_filter` (không reranker) — nhưng nhánh đó cũng nhận score
RRF nếu dense sống. Cần dựng lại toàn bộ chuỗi ngưỡng khi duyệt
`chat/_retrieval.py`; đây là câu hỏi lớn nhất mà `src.rag` để lại cho `src.chat`. {code+comment}

**Q-09 — `ChromaStore.query` gọi `count()` trên mọi truy vấn.**
`vectorstore.py:76`. Một round-trip DB thừa trên đường nóng, cho một giá trị
gần như bất biến giữa các request. Cache trong instance là đủ. {code}

**Q-10 — `retrieve_safety_pass` có cổng khoảng cách lỏng hơn và bật fallback,
khác đường chính.**
`retrieve` truyền `max_distance=self.dense_max_distance` (0.60) và
`fallback_to_raw=False`; `retrieve_safety_pass` không truyền cái nào → 0.65 và
True. Nghĩa là pass an toàn/khuyến cáo — chạy cho **mọi** truy vấn — nhận chunk
xa hơn và có thể rơi về kết quả **chưa lọc khoảng cách**. Comment
`vectorstore.py:118-120` nói rõ "Chat retrieval disables this so a bad dense
match cannot bypass the distance gate", nhưng pass thứ hai của chính chat lại
không tắt. Xem Q-08 — hai câu hỏi này phải trả lời cùng nhau. {code+comment}

**Q-11 — `Reranker._score_cache` dùng chung giữa request đồng thời, không lock.**
`reranker.py:23`. Hậu quả xấu nhất là mất/đè một entry, không sai kết quả (giá
trị được tính lại). Ghi lại để không ai "sửa" thành cấu trúc phức tạp hơn mà
không có lý do đo được. {code}

**Q-12 — khoá cache reranker là `(query_đầy_đủ, chunk_id)`, gần như không bao giờ
trúng.**
`reranker.py:64`. Trong hội thoại thật, query đổi mỗi lượt (nó gồm cả
`recent context:` từ `build_current_turn_query`), nên cache 2048 entry chỉ trúng
khi người dùng gửi lại **đúng cùng một chuỗi**. Nơi nó thật sự trúng là **eval**:
cùng 145 câu chạy qua nhiều arm. Đáng đo tỉ lệ trúng trước khi giữ hay bỏ. {code}

**Q-13 — `_HEADING_RE` thiếu phần lớn nguyên âm hoa tiếng Việt.**
`chunker.py:13`. Lớp `[A-ZÀÁẢÃẠĂẶÂẦẤĐÊÔƠƯ]` không có `Ứ Ổ Ộ Ệ È É Ò Ó Ù Ú Ì Í`…
Tiêu đề bắt đầu bằng những chữ đó không được nhận diện, nên không được gắn vào
đoạn kế tiếp. Ảnh hưởng chất lượng chunk của KB đã build. Sửa bằng
`re.match(r"[^\W\d_]", s)` + `s[0].isupper()` thay cho lớp liệt kê tay. {code}

**Q-14 — dedup near-duplicate là O(n²) trên mỗi tài liệu, giữ toàn bộ shingle set.**
`chunker.py:~150`. Tài liệu 100 chunk → 4.950 phép Jaccard, mỗi phép trên hai set
~1.200 phần tử. Chỉ chạy lúc build KB nên chấp nhận được; ghi lại để không ai
gọi `chunk()` trên đường nóng. {code}

**Q-15 — `chunk_with_stats` rò rỉ state và không có caller.**
`chunker.py:220-224`: `self.dedup = before` bị ghi đè ngay bởi `self.dedup = True`,
nên object dựng với `dedup=False` bị bật dedup vĩnh viễn sau một lần gọi. Hàm
này 0 caller toàn repo. Xoá được; nếu giữ thì phải sửa hai dòng. {code}

**Q-16 — trần boost 1.67 bị chính code vượt qua.**
Comment `retriever.py:19-22` chứng minh trần ~1.67 cho `_SOURCE_TYPE_BOOST`
(tôi đã kiểm lại số và nó đúng). Nhưng `retrieve:~163` **nhân thêm**
`_AUTHORITY_TAG_BOOST = 1.15` → chunk NICE có tag "guidelines" đạt
1.60 × 1.15 = **1.84 > 1.67**. Theo chính lập luận của comment, khi pool có
chunk như vậy thì mọi chunk chỉ-một-list bị cắt sạch, tức hybrid retrieval bị vô
hiệu hoá cho truy vấn đó. Cần đo tần suất tag "guidelines" trên KB trước khi
quyết định hạ `_AUTHORITY_TAG_BOOST` hay hạ `_MIN_FUSION_SCORE_RELATIVE`. {code+comment}

**Q-17 — `_source_type_from_meta` sửa dict metadata tại chỗ.**
`retriever.py:65`. Hàm tên "from_meta" ghi ngược vào `meta`. Có ích (nhớ kết quả
suy luận), nhưng dict đó đến từ Chroma và đi tiếp vào `RetrievedChunk.metadata`
rồi vào audit log. Nghĩa là `source_type` trong audit log có thể là giá trị **suy
ra lúc chạy**, không phải giá trị lưu trong KB — hai thứ không phân biệt được khi
đọc log về sau. {code}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **84** (1 + 22 + 6 + 8 + 8 + 17 + 13 + 9), đếm bằng
  `ast` trên source chứ không đếm mắt.
- Khối `### [x]` đếm được: xem `grep -c '^### \[x\]'`.
- Mục: 84 × 8 = **672**. Không dùng nén khai báo; mọi khối viết đủ 8 mục.
- Hai khẳng định đo bằng tính lại chứ không đọc mắt: trần boost 1.67
  (`_SOURCE_TYPE_BOOST`, và phần bác bỏ ở Q-16), và dải điểm RRF 0.0095–0.0164
  dùng trong Q-08.

---

## §7 — ĐÍNH CHÍNH (thêm sau khi duyệt `src.chat`)

**Q-08 ở trên đã được hạ mức.** Tôi viết rằng điểm RRF (~0,016–0,052) nằm dưới
mọi ngưỡng hạ nguồn (`chat_min_chunk_score = 0.25`, `chat_rerank_floor = 0.50`)
và gọi đó là câu hỏi lớn nhất `src.rag` để lại. Khi duyệt
`chat/_retrieval.py` tôi tìm thấy **hai** cơ chế chặn hậu quả đó:

1. `_retrieval.merge_retrieval_outputs:48` **chuẩn hoá lại** điểm
   (`score / max_score` → `[0,1]`), và guideline pass chạy cho **mọi** truy vấn
   (`_retrieval:~250`), nên output của `HybridRetriever.retrieve` gần như luôn đi
   qua bước chuẩn hoá này trước khi gặp bất kỳ ngưỡng nào.
2. `_retrieval._noise_filter` kết thúc bằng
   `return (after_noise if after_noise is not None and after_noise.chunks else output)`
   — nếu bộ lọc `min_score` xoá sạch thì hàm trả về **bản chưa lọc**. Ngưỡng
   0.25 vì thế không thể làm rỗng pool.

Phần **vẫn đúng** của Q-08: `RetrievedChunk.score` mang bốn ý nghĩa khác nhau
tuỳ nhánh của `retrieve()`, và `avg_score` do đó không so sánh được giữa các
nhánh hay giữa các lần chạy eval khác chế độ. Đó là nợ thiết kế đáng sửa, không
phải lỗi đang cắn. Mức nghiêm trọng: **hạ từ "lỗi" xuống "nợ thiết kế"**.
