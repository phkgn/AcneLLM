# FINDINGS / src.cache

Module: `src/acne_llm/cache.py` — 1 file, 141 LOC. Vòng 1, bậc 2 (leaf).
10 symbol + 2 khối lời khai = 12 khối × 8 mục = 96.

---

### [x] `_cache` (module-level singleton)
1. in/out: biến module `Optional[Any]`, giữ instance `diskcache.Cache` hoặc `None`. {code} `[cache.py:20]`
2. side effect: **global state** — là toàn bộ trạng thái của module. {code}
3. state: ghi bởi `init_cache` `[:25-36]`; đọc bởi `get_cache` `[:41]`. {code}
4. lỗi: `None` là trạng thái hợp lệ nghĩa "cache tắt", không phải lỗi. {code}
5. config/env: không trực tiếp; giá trị đến từ `settings.cache_dir` và `settings.cache_size_gb` qua `di.py:110-111`. {code}
6. ai gọi: `init_cache`, `get_cache` trong cùng file. Không ai ngoài đọc trực tiếp. {code}
7. invariant: **không thread-safe** — `init_cache` dùng `global` không khoá; giả định chỉ gọi một lần lúc dựng container. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `init_cache`
1. in/out: `(cache_dir: str, size_limit_gb: float = 2.0) -> None`. {code} `[cache.py:23]`
2. side effect: **tạo thư mục trên đĩa** `[:28]`, mở `diskcache.Cache` `[:29-33]`, ghi log info/warning `[:34,36]`. {code}
3. state: ghi `_cache` toàn cục `[:25]`. Đọc: không. {code}
4. lỗi: bọc `try/except Exception` rộng `[:26,35]` — mọi lỗi (thiếu `diskcache`, đĩa đầy, không quyền ghi) đều **nuốt**, log warning, đặt `_cache = None`. Không ném ra ngoài. {code}
5. config/env: `settings.cache_dir` mặc định `'./data/cache'` `[config.py:244]`, `settings.cache_size_gb` mặc định `2.0` `[config.py:246]`. Eval ép `cache_size_gb = 0.0` `[research/evaluation/adapters/_repo.py:27]` để tắt cache. {code}
6. ai gọi: chỉ `src/acne_llm/di.py:24` (import) và gọi tại `di.py:113` khi `cache_size > 0`. Nó gọi `diskcache.Cache`, `Path.mkdir`. {code}
7. invariant: `import diskcache` nằm **trong hàm** `[:27]` chứ không ở đầu file — đây là chỗ khiến thiếu gói không làm sập app mà chỉ tắt cache. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `get_cache`
1. in/out: `() -> Any | None`, trả `_cache`. {code} `[cache.py:40-41]`
2. side effect: không. {code}
3. state: đọc `_cache`; không ghi. {code}
4. lỗi: không có nhánh lỗi; trả `None` khi chưa init. {code}
5. config/env: không. {code}
6. ai gọi: `cached_embed_query` `[:59]`, `cached_retrieve` `[:100]`. **0 caller ngoài file** — đã grep `src/`, `tests/`, `research/evaluation/`, `scripts/`. {code}
7. invariant: gọi trước `init_cache` trả `None` chứ không ném — mọi consumer phải tự kiểm `None`. {code}
8. deprecated/TODO: không dấu. Là hàm public nhưng chỉ dùng nội bộ. {code}

### [x] `_make_key`
1. in/out: `(*parts) -> str`, sha256 hex của `json.dumps(parts, ensure_ascii=False, default=str)`. {code} `[cache.py:44-46]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `default=str` `[:45]` nên object không serialize được vẫn ra chuỗi thay vì ném `TypeError`. {code}
5. config/env: không. {code}
6. ai gọi: `cached_embed_query` `[:62]`, `cached_retrieve` `[:104]`. **0 caller ngoài file.** {code}
7. invariant: `default=str` là con dao hai lưỡi — hai object khác nhau có cùng `repr` sẽ ra **cùng khoá**, tức có thể trả nhầm cache. Không có chỗ nào chặn. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `EMBED_TAG`
1. in/out: hằng `str = "embed_v1"`. {code} `[cache.py:51]`
2. side effect: không. {code}
3. state: đọc bởi `cached_embed_query` `[:62]`; không ghi. {code}
4. lỗi: không. {code}
5. config/env: không — hằng cứng, không đọc `settings`. {code}
6. ai gọi: chỉ trong file. **0 caller ngoài.** {code}
7. invariant: hậu tố `_v1` là cơ chế đánh phiên bản thủ công — đổi thuật toán embed mà quên tăng số là dùng lại vector cũ trong im lặng. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `cached_embed_query`
1. in/out: `(embedder, query: str) -> Any` — trả vector; kiểu vector do embedder quyết, không ép. {code} `[cache.py:54]`
2. side effect: đọc/ghi đĩa qua diskcache; `pickle.loads` `[:67]` và `pickle.dumps` `[:74]`; log debug khi lỗi `[:69,76]`. {code}
3. state: đọc `_cache` qua `get_cache`; ghi entry vào cache đĩa. {code}
4. lỗi: hai khối `try/except Exception` riêng cho đọc `[:69]` và ghi `[:76]` — cả hai nuốt lỗi, log debug, chạy tiếp. Cache hỏng không làm hỏng truy vấn. {code}
5. config/env: gián tiếp qua `init_cache`; không đọc `settings` trực tiếp. {code}
6. ai gọi: `src/acne_llm/rag/embedder.py:61`, `research/evaluation/runners/run_retrieval.py:74`. Nó gọi `embedder._embed_query_raw()` — **truy cập method private của object khác**. {code}
7. invariant: comment `[:74]` khai "no TTL -- embed is deterministic". Giả định ngầm: cùng `(query, model_name)` luôn ra cùng vector. Đúng khi model không đổi; đổi `settings.embedding_model` mà không đổi `EMBED_TAG` là sai kết quả im lặng. {comment}
8. deprecated/TODO: không dấu. {code}

### [x] `RETRIEVE_TTL`
1. in/out: hằng `int = 3600` (giây). {code} `[cache.py:82]`
2. side effect: không. {code}
3. state: đọc bởi `cached_retrieve` `[:130]`. {code}
4. lỗi: không. {code}
5. config/env: **hằng cứng, không đọc `settings`** — không có key nào trong `Settings` điều khiển TTL này. {code}
6. ai gọi: chỉ trong file. **0 caller ngoài.** {code}
7. invariant: docstring đầu file `[:5]` khai "TTL 1 gio -- fresh khi KB update". Giả định: KB không đổi quá một lần mỗi giờ. Không có cơ chế invalidate khi rebuild KB thật. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] `RETRIEVE_TAG`
1. in/out: hằng `str = "retrieve_v1"`. {code} `[cache.py:83]`
2. side effect: không. {code}
3. state: đọc bởi `cached_retrieve` `[:104,130]`. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: chỉ trong file. **0 caller ngoài** — kể cả `scripts/build_kb.py` không gọi `cache.evict(RETRIEVE_TAG)`. {code}
7. invariant: comment `[:86-88]` khai tag dùng để invalidate theo nhóm bằng `cache.evict(tag)` — **cơ chế có, người gọi không có**. {comment}
8. deprecated/TODO: không dấu, nhưng là cơ chế chưa được nối. {code}

### [x] `RETRIEVE_MAX_ENTRY_BYTES`
1. in/out: hằng `int = 8 * 1024 * 1024` (8 MB). {code} `[cache.py:84]`
2. side effect: không. {code}
3. state: đọc bởi `cached_retrieve` `[:124]`. {code}
4. lỗi: không. {code}
5. config/env: hằng cứng. {code}
6. ai gọi: chỉ trong file. **0 caller ngoài.** {code}
7. invariant: entry vượt ngưỡng bị **bỏ qua im lặng** (chỉ log debug `[:125-128]`) — truy vấn đó không bao giờ được cache, và không có metric nào đếm số lần xảy ra. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `cached_retrieve`
1. in/out: `(fn: Callable, cache_key_parts: tuple) -> Any`. `fn` phải là callable không tham số. {code} `[cache.py:91]`
2. side effect: đọc/ghi đĩa; `zlib.compress` level=3 `[:123]`; `pickle` hai chiều; log debug. {code}
3. state: đọc `_cache`; ghi entry kèm `expire` và `tag`. {code}
4. lỗi: ba lớp bảo vệ — `except Exception` khi đọc `[:119]`, `except zlib.error` để tương thích entry cũ chưa nén `[:115-117]`, `except Exception` khi ghi `[:135]`. Cache hỏng luôn degrade về gọi `fn()` thật. {code}
5. config/env: gián tiếp. Khoá cache do caller truyền — `chat/_retrieval.py:14` quyết định gồm những gì. {code}
6. ai gọi: `src/acne_llm/chat/_retrieval.py:14`, `research/evaluation/runners/run_retrieval.py:73`. Nó gọi `fn()`, `_make_key`, `get_cache`. {code}
7. invariant: **caller chịu trách nhiệm đưa đủ tham số vào `cache_key_parts`** — quên một tham số ảnh hưởng kết quả là trả nhầm cache. Docstring `[:96-100]` chỉ nêu ví dụ, không ép. Đây là invariant nguy hiểm nhất của module. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] docstring `cache.py:1-8`
1. in/out: lời khai. {doc}
2. side effect: không. {doc}
3. state: không. {doc}
4. lỗi: không. {doc}
5. config/env: không. {doc}
6. ai gọi: không. {doc}
7. invariant: khai ba điều. (a) "Cache 2 tang: embed_query vĩnh viễn, retrieve TTL 1 giờ" — **khớp code** `[:74]` không TTL, `[:130]` `expire=RETRIEVE_TTL`. (b) "vector khong doi tru khi doi model" — khớp: khoá gồm model name qua `cached_embed_query`. (c) "Tat ca fallback silent neu cache gap loi" — khớp: mọi `except` đều nuốt và chạy tiếp. Lời khai đúng cả ba. {code}
8. deprecated: không. {doc}

### [x] khối `ponytail:` cuối file `[cache.py:139-141]`
1. in/out: lời khai, không phải symbol. {comment}
2. side effect: không. {comment}
3. state: không. {comment}
4. lỗi: không. {comment}
5. config/env: không. {comment}
6. ai gọi: không. {comment}
7. invariant: khai `invalidate_retrieve_cache` và `clear_all_caches` đã xoá vì không caller, kể cả `scripts/build_kb.py`. **Kiểm ngược**: grep hai tên đó trong `src/`, `tests/`, `scripts/` — 0 kết quả. Lời khai khớp code. Hệ quả: rebuild KB **không** xoá cache retrieval; phải `rm -rf data/cache` bằng tay. {code}
8. deprecated: là nợ có chủ ý được ghi lại đúng cách — thuộc diện `ponytail-debt`. {comment}

---

## BƯỚC 4 — TỰ KIỂM

```
file trong module / file đã tick   :  1 / 1
symbol đã liệt kê / đã tick        : 10 / 10  (+2 khối lời khai)
mục 1-8 cần điền / đã điền         : 96 / 96
```
"Chưa rõ" còn lại: **0**.
