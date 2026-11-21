# FINDINGS / src.chat (phần ngoài `routing/` và `session/`)

Module: `src/acne_llm/chat/` — 11 file, **3.067 LOC** (`__init__.py` 6,
`_intake_parse.py` 394, `_intent_patch.py` 88, `_retrieval.py` 392,
`_safety.py` 371, `confidence_hint.py` 124, `intake.py` 854,
`orchestrator.py` 187, `preprocess.py` 78, `runtime.py` 345,
`unified_intake.py` 228). `routing/` xem `src.chat.routing.md`; `session/` xem
`src.chat.session.md`.

**Quy ước đếm khối:** như các module trước — dataclass = 1 khối, method/property
tách, hàm lồng tách.

**Phép đếm khối (Bước 0):**
`__init__.py` 2 · `preprocess.py` 11 · `_intent_patch.py` 6 ·
`confidence_hint.py` 6 · `orchestrator.py` 6 · `_safety.py` 25 ·
`_retrieval.py` 16 · `_intake_parse.py` 29 · `unified_intake.py` 19 ·
`runtime.py` 5 · `intake.py` 16

→ **141 khối × 8 mục = 1.128 mục.**

Hai tiêu đề gộp (mỗi cái ghi rõ số khối nó phủ): `_safety` 10 bảng term,
`_intake_parse` 10 hằng enum. Xem §6.

---

## `__init__.py`

### [x] docstring `chat/__init__.py:1`
1. in/out: 1 dòng — "Chat-first request runtime used by the streaming web UI". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng — `runtime.stream_chat_sse` là cửa vào của
   `/chat/stream`. {code+doc}
8. deprecated: không. {doc}

### [x] `__all__` (`chat/__init__.py:6`)
1. in/out: 3 tên — `normalize_chat_message`, `prepare_user_text`,
   `preprocess_user_text`. {code}
2-5. không. {code}
6. ai gọi: `import *` = 0 toàn repo. {code}
7. invariant: mặt tiền khai 3 tên, trong đó **hai** thuộc `preprocess` và **một**
   thuộc `routing.rule_normalizer` (đường legacy). Những thứ thật sự được gọi từ
   ngoài — `run_intake`, `prepare_chat_turn`, `stream_chat_sse` — **không** có
   trong `__all__`; caller import đường dẫn đầy đủ. Mặt tiền không mô tả module,
   giống hệt `utils/__init__.py`. {code}
8. deprecated: không đánh dấu, nhưng vô nghĩa. {code}

---

## `preprocess.py`

### [x] docstring `preprocess.py:1-6`
1. in/out: 6 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "intentionally does not remove emoji or medical
   punctuation such as %, /, +, ., :, or parentheses". **Đối chiếu:** 5 regex chỉ
   động tới zero-width, control char, gạch dưới nối từ, dấu câu lặp và khoảng
   trắng. Không regex nào chạm `%`, `/`, `+`, `(`, `)`. Lời khai đúng, và nó quan
   trọng: `_extract_concentrations` phụ thuộc `%` sống sót. {code+doc}
8. deprecated: không. {doc}

### [x] `_ZERO_WIDTH_RE` (`preprocess.py:20`)
1. in/out: regex 4 code point zero-width (`200b`, `200c`, `200d`, `feff`). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `preprocess_user_text:37`, `light_normalize:82`. {code}
7. invariant: **xoá** chứ không thay khoảng trắng — đúng, vì zero-width nằm giữa
   các chữ cái của một từ; thay bằng space sẽ tách từ. Đối lập có chủ ý với
   `_CONTROL_RE` (thay bằng space). {code}
8. deprecated: không. {code}

### [x] `_CONTROL_RE` (`preprocess.py:21`)
1. in/out: regex control char C0 trừ `\t\n\r`, cộng `\x7f`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `preprocess_user_text:38` (thay bằng `" "`),
   `light_normalize:83` (**xoá hẳn**). {code}
7. invariant: hai người gọi dùng hai hành vi thay thế khác nhau cho cùng regex.
   Có lý: `clean_text` cần token tách được cho regex, `raw_for_llm` cần giữ
   nguyên hình dạng câu. Nhưng khác biệt này không được ghi ở đâu. {code}
8. deprecated: không. {code}

### [x] `_WORD_JOINER_RE` (`preprocess.py:22`)
1. in/out: `(?<=\w)_(?=\w)` — gạch dưới **giữa hai ký tự từ**. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `preprocess_user_text:39`. {code}
7. **invariant — lời khai ở nơi khác nói sai về regex này.** Docstring của
   `prepare_user_text:64` viết "word-joiner phía trên còn tách 'BT-Cortin' thành
   mồi cho nó". Tôi chạy thử `preprocess_user_text`:
   `"em dùng BT-Cortin"` → `'em dùng BT-Cortin'` (**không đổi**), còn
   `"em dùng BT_Cortin"` → `'em dùng BT Cortin'`. Regex chỉ khớp gạch **dưới**,
   không khớp gạch **nối**. Lời khai sai về ký tự. {code+doc}
8. deprecated: không. {code}

### [x] `_REPEATED_PUNCT_RE` (`preprocess.py:23`)
1. in/out: `([!?.,])\1{2,}` → thu về 2 ký tự. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `preprocess_user_text:40`. {code}
7. invariant: `"MỤN BỌC!!!!"` thành `"MỤN BỌC!!"` trong `clean_text`, nhưng
   `light_normalize` **không** áp nên `raw_for_llm` giữ nguyên 4 dấu — đúng như
   docstring `rule_normalizer:9-12` mô tả. Hai bản text, hai mức chuẩn hoá, và
   lời khai khớp code. {code+doc}
8. deprecated: không. {code}

### [x] `_WHITESPACE_RE` (`preprocess.py:25`)
1. in/out: `\s+`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `preprocess_user_text:41`. {code}
7. invariant: gộp cả xuống dòng thành một space, nên `clean_text` là **một
   dòng**. Điều này khiến các regex `[^\n]{0,90}` trong `_safety._DOSE_RE` an
   toàn khi chạy trên clean_text — nhưng `_safety` chạy trên **output của
   model**, không phải clean_text, nơi xuống dòng vẫn còn. {code}
8. deprecated: không. {code}

### [x] `PreparedText` (`preprocess.py:27-31`)
1. in/out: dataclass **frozen** 3 trường — `clean_text`, `clean_text_no_accent`,
   `teencode_replaced`. {code}
2. side effect: không. {code}
3. state: immutable. {code}
4. lỗi: không validate. {code}
5. config: không. {code}
6. ai gọi: `prepare_user_text` dựng; `intake.run_intake` đọc. {code}
7. **invariant: `teencode_replaced` luôn là `[]`.** `prepare_user_text:70` gán
   cứng list rỗng, và comment `:53-56` giải thích vì sao bảng teencode bị xoá.
   Trường này chảy tiếp vào `IntakeResult.teencode_replaced` rồi vào
   `AuditEntry.teencode_replaced` và được ghi xuống `audit.db` dưới dạng `"[]"`
   cho **mọi** bản ghi. Một cột DB chỉ chứa một giá trị. Xem Q-01. {code}
8. deprecated: trường chết chưa đánh dấu. {code}

### [x] `preprocess_user_text` (`preprocess.py:34-42`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (`text or ""`). {code}
5. config: 5 regex. {code}
6. ai gọi: `prepare_user_text:66`; export ở `chat/__init__.py`. {code}
7. invariant: thứ tự bắt buộc — NFC **trước** mọi thứ, và `_WHITESPACE_RE` cuối
   cùng để dọn khoảng trắng do `_CONTROL_RE` tạo ra. Kiểm tay 5 bước: đúng thứ tự. {code}
8. deprecated: không. {code}

### [x] `strip_accents` (`preprocess.py:45-49`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `prepare_user_text:69`, `rule_normalizer` (4 chỗ),
   `rule_extractor` (5 chỗ), `llm_router._build_prompt:116`. {code}
7. **invariant: đây là bản bỏ dấu ĐÚNG, và repo có một bản thứ hai SAI.**
   Hàm này NFD-tách dấu **rồi** `replace("đ","d")` — cần thiết vì `đ` (U+0111)
   không phân rã được. `utils/retrieval_query._no_accent` làm cùng việc nhưng
   **thiếu** bước thay `đ`. Đo thật:
   `strip_accents("da đầu")` → `"da dau"`; `_no_accent("da đầu")` → `"da đau"`.
   Hệ quả đo được ở `retrieval_query._NEG_CUES`: cue `"đừng dùng"` viết ASCII
   không khớp được văn bản đã qua `_no_accent`, vì `"đừng dùng"` ra `"đung dung"`
   chứ không `"dung dung"`. Thử 8 câu phủ định: 7 khớp cue, riêng
   `"đừng dùng BHA"` **không khớp cue nào**. Xem Q-02. {code}
8. deprecated: không. {code}

### [x] `prepare_user_text` (`preprocess.py:59-71`)
1. in/out: `(text: str) -> PreparedText`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `intake.run_intake:~226`, `rule_normalizer`, `rule_extractor`. {code}
7. invariant: docstring giải thích việc bỏ mở rộng teencode bằng một lập luận
   train/serve skew — intaker được train trên 110 mẫu teencode thô, nên mở rộng ở
   runtime tạo lệch. Lập luận đúng hạng và kiểm được nếu có tập train; tôi
   **chưa** kiểm con số 110. Vế thứ hai của cùng câu (BT-Cortin) thì sai — xem
   `_WORD_JOINER_RE`. {code+doc}
8. deprecated: không. {code}

### [x] `light_normalize` (`preprocess.py:74-84`)
1. in/out: `(message: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `AttributeError` nếu `message` là None — **khác** `preprocess_user_text`
   vốn có `text or ""`. Bất đối xứng giữa hai hàm cùng file. {code}
5. config: 2 regex. {code}
6. ai gọi: `rule_normalizer.normalize_chat_message:~1868` (dựng `raw_for_llm`). {code}
7. invariant: giữ dấu câu, emoji, emphasis, khoảng trắng — đúng như docstring, và
   đó là thứ đi vào `UserInput.description`, tức thứ model nhìn thấy. {code}
8. deprecated: không. {code}

---

## `_intent_patch.py`

### [x] docstring `_intent_patch.py:1-46`
1. in/out: 46 dòng — **lời khai dài nhất trong toàn repo**. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: bốn phần — LỖI GỐC (intaker fine-tune trên 4.000 dòng,
   200 dòng có lịch sử và **cả 200 đều nhãn `clarify`**, do
   `datagen/intakedata/taxonomy.yaml` chỉ có một case type sinh lịch sử và
   `generator.py::to_record` ném lỗi nếu case khác có lịch sử); VÌ SAO CHẤP NHẬN
   ĐƯỢC (chỉ ngưng tin **riêng** nhãn `clarify`); HƯỚNG SAI RẺ HƠN; và XOÁ FILE
   NÀY KHI (tập train có multi-turn mang nhãn khác). Đây là {doc} — tôi
   **chưa** kiểm hai file `datagen/` được viện dẫn, chúng thuộc phạm vi kiểm kê
   chứ không audit sâu. Ghi lại để phần kiểm kê `datagen/` phải xác nhận hai
   khẳng định đó. Phần kiểm được từ code trong file: phạm vi sửa đúng là hẹp
   (`_REPAIRABLE = "clarify"` duy nhất) — khớp lời khai. {code+doc}
8. deprecated: file tự nêu điều kiện xoá, kèm một dòng lệnh kiểm. Đây là cách
   đánh dấu nợ kỹ thuật tốt nhất tôi gặp trong repo. {doc}

### [x] `CLARIFY_DOWNGRADED` (`_intent_patch.py:~50`)
1. in/out: `"clarify_downgraded"`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `intake.py` (gắn vào `route_flags` khi vá được áp dụng); `_demo`. {code}
7. invariant: comment `:~49` nói mục đích là "để log/trace truy nguyên được" —
   đúng, cờ này là dấu vết duy nhất cho biết intent đã bị sửa. {code}
8. deprecated: không. {code}

### [x] `_REPAIRABLE` (`_intent_patch.py:~53`)
1. in/out: `"clarify"`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `repaired_intent:~67`. {code}
7. invariant: comment `:~52` viết "Nhãn DUY NHẤT được phép sửa. Không nới rộng
   danh sách này" — và `_demo` **có test** cho đúng ràng buộc đó (3 nhãn còn lại
   không đổi kể cả khi có lịch sử). Lời khai được test bảo vệ. {code+test}
8. deprecated: không. {code}

### [x] `_TARGET` (`_intent_patch.py:~54`)
1. in/out: `"advise"`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `repaired_intent:~68`. {code}
7. invariant: hướng sửa là clarify→advise, một chiều. Docstring lập luận đây là
   hướng sai rẻ hơn (ép advise thì generator tự hỏi lại; ép clarify thì người
   dùng bị chặn). Lập luận đúng hạng. {code+doc}
8. deprecated: không. {code}

### [x] `repaired_intent` (`_intent_patch.py:~57-69`)
1. in/out: `(intent: str, has_established_case: bool) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_REPAIRABLE`, `_TARGET`. {code}
6. ai gọi: `intake.run_intake`. {code}
7. invariant: comment `ponytail:` giải thích vì sao là **một** hàm chứ không phải
   predicate + mapper — caller so intent cũ với mới là biết có đổi hay không.
   Code khớp: hàm thuần, trả nguyên bản khi không thuộc diện sửa.
   `has_established_case` do caller tính (`intake._has_established_case`) để
   module này không import ngược — kiểm tay: file không import gì ngoài
   `__future__`. Đúng. {code+comment}
8. deprecated: không. {code}

### [x] `_demo` (`_intent_patch.py:~72-84`)
1. in/out: `() -> None`; 8 assert. {code}
2. side effect: `print("intent patch demo OK")`. {code}
3. state: không. {code}
4. lỗi: `AssertionError` nếu hành vi đổi. {code}
5. config: không. {code}
6. ai gọi: chỉ `if __name__ == "__main__"`. **Không** nằm trong `tests/`, nên
   `pytest` không chạy nó. {code}
7. invariant: đây là "một check chạy được" theo đúng tinh thần — nhưng nó không
   nằm trong suite, nên CI không bảo vệ ranh giới an toàn mà nó kiểm. Chuyển
   thành `tests/test_intent_patch.py` là một dòng. Xem Q-03. {code}
8. deprecated: không. {code}

---

## `confidence_hint.py`

### [x] docstring `confidence_hint.py:1-5`
1. in/out: 5 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Dùng mỗi lượt trong `orchestrator.prepare_chat_turn` bất
   kể intake đi đường LLM hay đường rule fallback". **Đối chiếu:**
   `orchestrator:~143` gọi nó khi `intake.extraction_confidence is not None`, và
   cả hai đường đều điền trường đó. Lời khai đúng. {code+doc}
8. deprecated: không. {doc}

### [x] `_OVERALL_WEIGHTS` (`confidence_hint.py:18-29`)
1. in/out: dict 10 field → trọng số 0.5–1.8. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `overall_confidence:65`. {code}
7. **invariant hỏng — hai field an toàn nhất bị bỏ khỏi điểm tổng.** Comment
   `:17` nói "Field an toàn nặng hơn", và đúng là `is_pregnant`/
   `is_breastfeeding` được 1.8. Nhưng **`products` và `medications` không có
   trong bảng**. Đó lại chính là hai trường mà `medication_safety_refusal` đọc.
   Nghĩa là extractor có thể trích sai tên thuốc với confidence thấp mà điểm tổng
   không hề giảm. Xem Q-04. {code+comment}
8. deprecated: không. {code}

### [x] `_FIELD_LABELS_VI` (`confidence_hint.py:32-45`)
1. in/out: dict **12** field → nhãn tiếng Việt. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `build_confidence_hint:100`. {code}
7. invariant: 12 nhãn, nhưng vòng lặp ở `build_confidence_hint:86-90` chỉ duyệt
   **10** tên — thiếu đúng `products` và `medications`. Hai nhãn
   `"sản phẩm đang dùng"` và `"thuốc đang dùng"` được viết ra và **không bao giờ
   in được**. Chúng là bằng chứng rằng việc bỏ hai field là **sót**, không phải
   quyết định. Xem Q-04. {code}
8. deprecated: 2/12 mục không thể tới. {code}

### [x] `_field_conf` (`confidence_hint.py:48-55`)
1. in/out: `(ec, name) -> float`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `AttributeError` nếu `fr` không có `.confidence` và cũng không có
   `.max_confidence` — không xảy ra với `ExtractionConfidence` thật. {code}
5. config: không. {code}
6. ai gọi: `overall_confidence:66`, `build_confidence_hint:98`. {code}
7. invariant: phân biệt `ListFieldResult` (dùng `max_confidence`) với
   `FieldResult` (dùng `confidence`) bằng `hasattr` thay vì `isinstance` —
   duck typing, nên một object giả có thuộc tính trùng tên sẽ đi nhánh sai. Với
   list, lấy **max** nghĩa là một item chắc chắn che được cả list toàn item mơ hồ. {code}
8. deprecated: không. {code}

### [x] `overall_confidence` (`confidence_hint.py:58-70`)
1. in/out: `(ec) -> float`; trung bình có trọng số, làm tròn 3 chữ số. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (`den > 0` gác chia). {code}
5. config: `_OVERALL_WEIGHTS`. {code}
6. ai gọi: `build_confidence_hint:103` (khi `overall` là None). Grep ngoài file:
   **0 caller** — hàm công khai nhưng chỉ dùng nội bộ. {code}
7. invariant: chỉ tính field có `conf > 0`, docstring giải thích đúng lý do
   ("'không có' khác 'có nhưng không chắc'"). Hệ quả phụ: một lượt chỉ trích được
   **một** field với conf 0.95 sẽ có điểm tổng 0.95 — cao, dù hồ sơ gần như
   trống. Điểm tổng đo **độ chắc**, không đo **độ đầy đủ**, và tên hàm không nói
   rõ điều đó. {code}
8. deprecated: không. {code}

### [x] `build_confidence_hint` (`confidence_hint.py:73-124`)
1. in/out: `(ec, *, field_threshold: float, overall: float | None = None) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. **config: `field_threshold` là tham số bắt buộc, và `orchestrator:~143`
   truyền số cứng `0.6`** — không phải `settings.extract_min_field_conf` (cũng
   0.60). Đây là **chỗ thứ ba** trong repo giữ hằng 0.60 (hai chỗ kia:
   `config.py:225`, `session/view.py:67`). {code}
6. ai gọi: `orchestrator.prepare_chat_turn:~143`. {code}
7. invariant: trả chuỗi rỗng khi mọi thứ đều chắc — người gọi kiểm `if conf_hint`
   nên chuỗi rỗng không làm bẩn prompt. Ngưỡng giọng điệu `overall < 0.6` dùng
   **cùng con số** với `field_threshold` nhưng là hằng riêng viết thẳng trong
   thân hàm (`:116`); hai ngưỡng khác nghĩa, trùng giá trị, một cái tham số hoá,
   một cái không. {code}
8. deprecated: không. {code}

---

## `orchestrator.py`

### [x] docstring `orchestrator.py:1`
1. in/out: 1 dòng — "Single preparation path shared by SSE, WebSocket,
   evaluation, and debug trace". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. **invariant khai báo — đây là lời khai quan trọng nhất của cả khoá luận, và
   nó ĐÚNG một nửa.** `prepare_chat_turn` thật sự là đường chuẩn bị duy nhất:
   `runtime.stream_chat_sse` gọi nó, và runner eval cũng gọi nó. Nhưng bước
   **sinh** thì tách đôi: production đi `runtime` → `c.llm.stream_text(...)`,
   còn eval đi `generate_prose` → `c.llm.generate_text(...)`. Hai hàm backend
   khác nhau, và chúng **không** nhận cùng tham số. Xem Q-05. {code+doc}
8. deprecated: không. {doc}

### [x] `_CJK` (`orchestrator.py:20`)
1. in/out: regex dải CJK + Hiragana + Katakana + Hangul. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `normalize_generated_prose:26`. {code}
7. invariant: cắt ký tự Đông Á khỏi output — dấu vết của model nền Qwen thỉnh
   thoảng rơi lại chữ Hán. Nó **không** loại tiếng Việt (Latin có dấu). Việc phải
   có bộ lọc này là một dữ kiện về chất lượng fine-tune đáng đưa vào báo cáo. {code}
8. deprecated: không. {code}

### [x] `normalize_generated_prose` (`orchestrator.py:23-32`)
1. in/out: `(text: str, *, model: str = "?") -> str`. {code}
2. side effect: `logger.warning` khi có cắt. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_CJK`. {code}
6. ai gọi: `generate_prose:~180`. **Chỉ đường non-stream.** {code}
7. **invariant: đường SSE không gọi hàm này.** `runtime.stream_chat_sse` phát
   từng token và không có bước hậu xử lý CJK tương ứng — kiểm bằng grep
   `normalize_generated_prose` trong `runtime.py`: 0 kết quả. Nghĩa là ký tự Hán
   bị cắt trong **eval** nhưng lọt tới **người dùng thật**. Xem Q-05. {code}
8. deprecated: không. {code}

### [x] `PreparedChatTurn` (`orchestrator.py:35-45`)
1. in/out: dataclass 9 trường — `intake`, `route_metadata`, `mode`, `template`,
   `retrieval_query`, `retrieval`, `system_prompt`, `user_prompt`, `prompt_note`. {code}
2. side effect: không. {code}
3. state: mutable (không frozen), và `prepare_chat_turn` **sửa `intake` tại chỗ**
   trước khi đóng gói (`:~64-81`, nhánh `user_override`). {code}
4. lỗi: không validate. {code}
5. config: không. {code}
6. ai gọi: `runtime`, `generate_prose`, runner eval, route debug. {code}
7. invariant: đây là **hợp đồng chung** giữa production và eval. Mọi trường đều
   được tính **một lần** ở `prepare_chat_turn`, nên hai đường không thể lệch ở
   phần chuẩn bị. Chỉ phần sinh mới lệch (Q-05). {code}
8. deprecated: không. {code}

### [x] `prepare_chat_turn` (`orchestrator.py:48-166`)
1. in/out: `(c, message, requested_mode="auto", session_id=None,
   user_override=None, include_analytics=False) -> PreparedChatTurn`. {code}
2. side effect: chạy toàn bộ intake (gọi model, đọc/ghi session), có thể chạy
   retrieval (embed + 2–3 truy vấn Chroma), ghi 1 dòng log RAG. {code}
3. state: **sửa `intake.user`, `intake.confirmed_profile`, `intake.safety_terms`
   tại chỗ** ở nhánh `user_override`. {code}
4. lỗi: `ValueError` từ `run_intake` khi tin nhắn quá dài; lỗi model nổi lên. {code}
5. config: `chat_max_context_chars` (6000). {code}
6. ai gọi: `runtime.stream_chat_sse`, `generate_prose`, runner eval. {code}
7. invariant: `user_override` chỉ được áp khi intent là `advise`/`knowledge`, và
   chỉ **5 trường an toàn** được đưa vào `confirmed_profile` — comment `:~66-67`
   nói rõ "Only confirmed safety facts may influence the prompt". Đây là đường
   mà runner eval bơm hồ sơ vào, nên phạm vi hẹp này chính là thứ giữ cho eval
   không vô tình mạnh hơn production. Chọn template theo 5 nhánh, thứ tự:
   refusal → reject → clarify → knowledge → stream. {code}
8. deprecated: không. {code}

### [x] `generate_prose` (`orchestrator.py:169-186`)
1. in/out: `(c, prepared, temperature=None) -> str`. {code}
2. side effect: một lời gọi Ollama non-stream. {code}
3. state: không. {code}
4. lỗi: nổi lên người gọi. {code}
5. config: `temperature` từ người gọi. {code}
6. ai gọi: docstring nói "T3 eval and the CLI use this helper". {code}
7. **invariant hỏng — đây là gốc của lệch runtime↔eval.**
   `c.llm.generate_text(system, user, temperature=...)` — và
   `ollama_backend.generate_text:222-224` **không nhận `num_predict`**, trong khi
   `stream_text:236-238` **có**. `runtime.py:162-172` dùng điều đó:
   `_stream_num_predict = -1 if _primary_intent == "knowledge" else None`, gác
   bằng `_supports_keyword(c.llm.stream_text, "num_predict")`. Kết quả: câu hỏi
   `knowledge` được sinh **không giới hạn độ dài** ở production, nhưng bị chặn ở
   `settings.llm_num_predict = 2048` khi chạy eval. Cùng prompt, hai trần độ dài.
   Xem Q-05. {code}
8. deprecated: không. {code}

---

## `_safety.py`

### [x] docstring `_safety.py:1`
1. in/out: 1 dòng — "Safety post-check cho chat stream". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng phạm vi — đây là **hậu kiểm trên văn bản model đã
   sinh**, khác `guardrails/runner.py` (tiền kiểm trên đầu vào). Hai tầng khác
   thời điểm, và đó là lý do cả hai cùng tồn tại hợp lý. {code+doc}
8. deprecated: không. {doc}

### [x] **10 bảng term** — `_RETINOID_TERMS`, `_RX_TERMS`, `_RX_RECOMMEND_CONTEXT`,
`_RX_RECOMMEND_CONTEXT_UNI`, `_NEGATION_CONTEXT`, `_NEGATION_CONTEXT_UNI`,
`_ALL_NEGATION`, `_ALL_RX_CONTEXT`, `_GENERIC_DISCLAIMER_ANCHORS`,
`_PREGNANCY_MENTION_TERMS`

> 10 khối. Mục 2/3/4/7 theo nén có khai báo (hằng module, không side effect,
> không lỗi, đều có cặp có-dấu/không-dấu). Mục 1/5/6/8 dưới đây.

1. in/out: đều là `tuple[str, ...]`; `_ALL_NEGATION` và `_ALL_RX_CONTEXT` là
   **phép nối** hai bảng có dấu + không dấu. {code}
5. config: hằng cứng, không có ở `Settings` hay YAML. {code}
6. ai gọi: `_ALL_NEGATION` → `_mentions_positively`; `_ALL_RX_CONTEXT` →
   `_mentions_rx_advice`; `_RETINOID_TERMS`/`_RX_TERMS`/`_PREGNANCY_MENTION_TERMS`
   → `get_safety_suffix`; `_GENERIC_DISCLAIMER_ANCHORS` → nhánh disclaimer chung. {code}
8. deprecated: không. {code}

**Nhận xét riêng — `_RX_RECOMMEND_CONTEXT` quá lỏng:** bảng chứa `"mg"`, `"%"`,
`"dung "`, `"use "`, `"take "`. Trong cửa sổ 200 ký tự quanh tên thuốc, gần như
mọi câu trả lời y khoa tiếng Việt đều chứa ít nhất một trong số đó. Đo ở phiên
trước trên 145 câu trả lời thật: `_mentions_rx_advice` bật trên **22/23** câu có
nhắc thuốc kê đơn — tức nó gần như là "có nhắc tên thuốc" chứ không phải "đang
khuyên dùng". Cảnh báo vẫn đúng hướng (thừa hơn thiếu), nhưng tên hàm và bảng
`RECOMMEND` hứa một phép phân biệt mà nó không thực hiện.

### [x] `_DOSE_RE` (`_safety.py:20-26`)
1. in/out: regex — tên hoạt chất, tối đa 90 ký tự **không xuống dòng**, rồi một
   con số kèm đơn vị (`mg/kg|mg|mcg|%|viên|lần/ngày|ngày|tuần`). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_mentions_specific_dose:45`. {code}
7. invariant: comment `:8-19` (12 dòng) nêu đúng lý do tồn tại — cổng đầu vào
   chỉ thấy thứ **người dùng** nhắc, không thấy được liều mà **model tự sinh**.
   Ví dụ trong comment (`"uống doxycycline 100mg mỗi ngày trong 8 tuần"`) khớp
   được regex này. Ràng buộc `[^\n]{0,90}` là đúng chỗ: model xuống dòng giữa
   tên thuốc và liều thì không khớp — nhưng output SSE **có** xuống dòng
   (Markdown bullet), nên đây là nguồn bỏ sót thật. Đo ở phiên trước: chỉ **3/38**
   câu trả lời bị đánh dấu sai an toàn khớp `_DOSE_RE`. Xem Q-06. {code+comment}
8. deprecated: không. {code}

### [x] `_SELF_USE_RE` (`_safety.py:26-30`)
1. in/out: regex `tự (mua|dùng|uống|bôi)` … trong 80 ký tự … tên thuốc. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_mentions_specific_dose:45`. {code}
7. invariant: chỉ có bản **có dấu** (`tự`, `mua về dùng`) — không có biến thể
   không dấu, khác quy ước của mọi bảng term khác trong repo. Output của model
   luôn có dấu nên hiện không sót; nhưng nó là ngoại lệ không được ghi. {code}
8. deprecated: không. {code}

### [x] `_DOSE_WARNING` (`_safety.py:31-36`)
1. in/out: chuỗi cảnh báo tiếng Việt, mở đầu `\n\n⚠️`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `get_safety_suffix` (nhánh liều). {code}
7. invariant: mọi cảnh báo trong file đều bắt đầu bằng `\n\n` để nối vào cuối
   câu trả lời mà không dính chữ. Nhất quán ở cả 6 chuỗi cảnh báo. {code}
8. deprecated: không. {code}

### [x] `_DOSE_ANCHOR` (`_safety.py:37-41`)
1. in/out: tuple 5 cụm neo. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `get_safety_suffix` qua `_already_has_warning`. {code}
7. invariant: dùng để **không nối cảnh báo hai lần** khi model đã tự nói. Cơ chế
   này lặp lại ở cả 6 nhánh cảnh báo — thiết kế nhất quán và đúng: hậu kiểm chỉ
   bổ sung, không lặp. {code}
8. deprecated: không. {code}

### [x] `_mentions_specific_dose` (`_safety.py:44-45`)
1. in/out: `(text: str) -> bool`. {code}
2-4. không. {code}
5. config: 2 regex. {code}
6. ai gọi: `get_safety_suffix`. {code}
7. invariant: `or` giữa hai regex — liều cụ thể **hoặc** tự dùng thuốc. Hai mẫu
   nguy hiểm khác nhau chia một cảnh báo. {code}
8. deprecated: không. {code}

### [x] `_GENERIC_DISCLAIMER_VI` (`_safety.py:~116-120`)
1. in/out: chuỗi disclaimer chung. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `get_safety_suffix`, nhánh cuối. {code}
7. invariant: **chỉ nối khi `not warnings`** — tức khi không có cảnh báo cụ thể
   nào. Đúng thiết kế: cảnh báo cụ thể đã hàm ý "gặp bác sĩ", thêm disclaimer
   chung nữa là nhiễu. Và chỉ khi `len(full_text) > 120`. {code}
8. deprecated: không. {code}

### [x] `_mentions_positively` (`_safety.py:~123-135`)
1. in/out: `(text: str, term: str) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_ALL_NEGATION`, cửa sổ **60 ký tự trước**. {code}
6. ai gọi: `get_safety_suffix` (retinoid), `_mentions_rx_advice`. {code}
7. invariant: quét **mọi** lần xuất hiện của term, trả True ngay khi tìm được
   một lần **không** bị phủ định trong 60 ký tự trước. Đây là hướng an toàn
   đúng: một câu "tránh isotretinoin, nhưng nếu dùng thì…" vẫn bị bắt. Cùng cơ
   chế với `rule_normalizer._positive_mention` nhưng cửa sổ 60 thay vì 30, và
   **không** giới hạn số từ xen giữa — lỏng hơn. Ở hậu kiểm thì lỏng = an toàn
   hơn, ngược với ở trích xuất. {code}
8. deprecated: không. {code}

### [x] `_already_has_warning` (`_safety.py:~138-140`)
1. in/out: `(text: str, anchors: tuple) -> bool`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: **6 nhánh** của `get_safety_suffix`. {code}
7. invariant: khớp chuỗi con thuần, không ranh giới từ — với các neo dài
   (`"chỉ mang tính tham khảo"`) thì an toàn. Rủi ro là **âm tính giả**: model
   paraphrase khác đi thì neo trượt và cảnh báo bị nối thêm dù đã có. Hướng sai
   này (thừa cảnh báo) rẻ hơn hướng ngược. {code}
8. deprecated: không. {code}

### [x] `_mentions_rx_advice` (`_safety.py:~143-153`)
1. in/out: `(text: str, term: str) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_ALL_RX_CONTEXT`, cửa sổ **80 trước + 120 sau**. {code}
6. ai gọi: `get_safety_suffix`, vòng lặp `_RX_TERMS`. {code}
7. invariant: hai tầng — trước hết tìm ngữ cảnh khuyên dùng trong cửa sổ 200 ký
   tự, rồi mới hỏi `_mentions_positively`. Về hình thức là một phép phân biệt
   "nhắc tới" vs "khuyên dùng"; về thực tế bảng ngữ cảnh chứa `"mg"`, `"%"`,
   `"dung "` nên gần như luôn khớp — xem nhận xét ở khối bảng term. {code}
8. deprecated: không. {code}

### [x] `_SELF_PROCEDURE_TERMS` (`_safety.py:~200-210`)
1. in/out: tuple ~24 cụm về tự dùng dụng cụ nặn/chích/rạch. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_advises_self_procedure`. {code}
7. invariant: **mọi mục đều từ 2 từ trở lên** (`"dùng dao"`, `"cây nặn"`,
   `"tự chích"`) — không có token 2–3 ký tự như các bảng đã bị xoá ở
   `intake.py`. Bảng này học được bài học đó. {code}
8. deprecated: không. {code}

### [x] `_SELF_PROCEDURE_WARNING` (`_safety.py:~212-217`)
1. in/out: chuỗi cảnh báo. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `get_safety_suffix`. {code}
7. invariant: comment `:~197-199` nói "luôn chèn dù model có nhắc phòng ngừa hay
   không, vì đây là rủi ro trực tiếp (Critical, S09)" — nhưng code `:~355` vẫn
   gác bằng `not _already_has_warning(...)`. Lời khai nói "luôn", code nói "trừ
   khi đã có neo". Không mâu thuẫn nguy hiểm (neo chính là câu cảnh báo), nhưng
   lời khai mạnh hơn code. {code+comment}
8. deprecated: không. {code}

### [x] `_SELF_PROCEDURE_ANCHOR` (`_safety.py:~218-221`)
1. in/out: tuple 4 neo. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `get_safety_suffix`. {code}
7. invariant: neo lấy nguyên văn từ `_SELF_PROCEDURE_WARNING`, nên nếu model tự
   viết một câu khác nội dung tương đương thì cảnh báo vẫn được nối. Thừa hơn
   thiếu. {code}
8. deprecated: không. {code}

### [x] `_advises_self_procedure` (`_safety.py:~224-227`)
1. in/out: `(text: str) -> bool`. {code}
2-4. không. {code}
5. config: `_SELF_PROCEDURE_TERMS`. {code}
6. ai gọi: `get_safety_suffix`. {code}
7. invariant: khớp chuỗi con, **không** kiểm phủ định — cố ý, vì câu "đừng dùng
   dao để nặn" cũng nên kèm cảnh báo. Đây là nhánh duy nhất trong file **không**
   đi qua `_mentions_positively`, và sự khác biệt đó là đúng. {code}
8. deprecated: không. {code}

### [x] `get_safety_suffix` (`_safety.py:~230-371`)
1. in/out: `(full_text, user, route_flags=None, skip_generic_disclaimer=False,
   recent_turns=None, current_turn_text=None) -> str`; 142 dòng, 7 nhánh cảnh báo. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không raise. {code}
5. config: mọi ngưỡng cứng (`age < 12`, `len(full_text) > 120`). {code}
6. ai gọi: `runtime.py:233` — **một chỗ duy nhất**, và chỉ ở đường SSE. {code}
7. invariant: thứ tự nhánh — thai kỳ/retinoid → thai kỳ chưa rõ → thuốc kê đơn →
   tuổi < 12 → red flag khẩn → đa bệnh → tự thủ thuật → liều cụ thể → disclaimer
   chung. Tám nhánh đầu **cộng dồn** (append), nhánh cuối chỉ chạy khi **không**
   có nhánh nào bật. Nhánh red-flag dùng
   `("urgency_red_flag" in route_flags) and ((_rf & _EMERGENCY_FLAGS) or not _rf)`
   — mệnh đề `or not _rf` là thứ giữ cho cảnh báo vẫn bật khi
   `red_flags_input` rỗng, tức trên **toàn bộ đường unified** (xem Q-07). Nếu
   thiếu mệnh đề đó, cảnh báo khẩn cấp đã chết hoàn toàn ở production. {code}
8. deprecated: không. Tôi định ghi `recent_turns` và `current_turn_text` là tham
   số chết rồi kiểm lại trước khi chốt: `runtime.py:238-239` **có** truyền cả hai
   (`recent_turns=history`, `current_turn_text=message`), và thân hàm dùng chúng
   ở `:218-220` (nén disclaimer chung theo 4 lượt gần nhất) và `:236-237`
   (`_current_mentions_pregnancy` đọc turn HIỆN TẠI, chưa fold — để tránh thai kỳ
   từ lượt cũ kích hoạt cảnh báo ở lượt không liên quan). Cả hai sống và có lý do
   rõ ràng. {code}

---

## `_retrieval.py`

### [x] docstring `_retrieval.py:1`
1. in/out: 1 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "query building, RRF fusion, retrieve + rerank" — đúng ba
   việc, nhưng thiếu hai việc lớn nhất: **cap theo nguồn** và **giữ ô cho
   guideline**. Lời khai hẹp hơn nội dung. {code+doc}
8. deprecated: không. {doc}

### [x] `rrf_fusion` (`_retrieval.py:22-27`)
1. in/out: `(rank_lists, k=60) -> dict[str, float]`. {code}
2-4. không side effect, không state, không lỗi. {code}
5. config: `k=60` cứng. {code}
6. ai gọi: `merge_retrieval_outputs:46`. {code}
7. **invariant: bản sao từng dòng của `rag/retriever.py:76-81`.** Hai hàm cùng
   tên, cùng thân, hai file. Sửa công thức RRF ở một chỗ thì chỗ kia lệch im
   lặng. Xem Q-08. {code}
8. deprecated: không. {code}

### [x] `merge_retrieval_outputs` (`_retrieval.py:30-60`)
1. in/out: `(outputs: list[RetrievalOutput], combined_query: str) -> RetrievalOutput`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `retrieve_for_chat` — 2 chỗ (sau guideline pass, sau safety pass). {code}
7. **invariant quan trọng — hàm này CHUẨN HOÁ LẠI thang điểm.**
   `:48` gán `chunk.score = score / max_score`, đưa điểm RRF về `[0,1]` với đỉnh
   bằng 1.0. Đây là câu trả lời cho câu hỏi lớn nhất mà `src.rag` để lại (Q-08 ở
   file đó): điểm RRF thô ~0.016–0.052 **không** đi thẳng vào các ngưỡng hạ
   nguồn, vì guideline pass chạy cho **mọi** truy vấn và luôn kéo output qua hàm
   này. Xem Q-09 để biết phần còn lại của câu trả lời. {code}
8. deprecated: không. {code}

### [x] `_MEDICAL_SAFETY_TERMS` (`_retrieval.py:66-72`)
1. in/out: frozenset ~19 cụm (thai kỳ, cho con bú, retinoid, kháng sinh). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_has_medical_safety_terms`. {code}
7. invariant: comment `:62-65` nêu lý do đo được — safety pass thêm ~50–100 ms
   mỗi request, nên chỉ chạy khi có term y tế **thật**, không chạy với term
   thành phần chung từ cờ `product_safety_check`. Đây là một trong ít quyết định
   trong repo có kèm con số chi phí. {code+comment}
8. deprecated: không. {code}

### [x] `_has_medical_safety_terms` (`_retrieval.py:75-79`)
1. in/out: `(safety_terms: list[str]) -> bool`. {code}
2-4. không. {code}
5. config: `_MEDICAL_SAFETY_TERMS`. {code}
6. ai gọi: `retrieve_for_chat:~272`. {code}
7. invariant: `any(marker in str(t).lower() ...)` — khớp chuỗi con hai chiều lồng
   nhau, nên `"khang sinh"` khớp cả `"thuốc kháng sinh uống"`. Ở đây lỏng là
   đúng: hậu quả duy nhất là chạy thêm một truy vấn Chroma. {code}
8. deprecated: không. {code}

### [x] `_source_key` (`_retrieval.py:84-86`)
1. in/out: `(chunk) -> str`; ưu tiên `url` → `source` → `chunk.source` → `chunk_id`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `cap_per_source:~106`. {code}
7. invariant: rơi về `chunk_id` nghĩa là chunk thiếu metadata sẽ **luôn** được
   coi là nguồn riêng, không bao giờ bị cap. Fail-open — giữ chunk thay vì loại. {code}
8. deprecated: không. {code}

### [x] `cap_per_source` (`_retrieval.py:89-120`)
1. in/out: `(output, max_per_source: int, limit: int) -> RetrievalOutput`. {code}
2. side effect: `logger.debug`. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `chat_max_chunks_per_source` (=1), `chat_rerank_top_k` (=5). {code}
6. ai gọi: `retrieve_for_chat:~301`. {code}
7. invariant: docstring nêu đúng cơ chế và đúng lý do — chunker chồng lấn 40
   token nên hai chunk kề nhau trong cùng bài gần trùng nội dung, near-dedup lúc
   build không bắt được. Cơ chế **spill**: chunk bị cap được giữ làm dự phòng và
   lấp lại nếu chưa đủ `limit`, nên "không bao giờ trả về ít chunk hơn trước" —
   kiểm tay `:114-116`: đúng. {code+doc}
8. deprecated: không. {code}

### [x] `GUIDELINE_SOURCE_TYPES` (`_retrieval.py:125-127`)
1. in/out: frozenset 3 loại. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_is_guideline`. {code}
7. invariant: comment `:123-124` thừa nhận thẳng đây là **bản sao** của
   `HybridRetriever.GUIDELINE_SOURCE_TYPES`, kèm lý do ("để hàm dưới không phải
   có retriever"). Lời khai trung thực; bản sao vẫn là bản sao. Trong chính
   `retrieve_for_chat:~253` thì lại lấy bản của retriever qua `getattr` với
   default là **tuple thứ ba** viết thẳng tại chỗ. Ba nơi giữ cùng danh sách. {code+comment}
8. deprecated: không. {code}

### [x] `_is_guideline` (`_retrieval.py:130-131`)
1. in/out: `(chunk) -> bool`. {code}
2-4. không. {code}
5. config: `GUIDELINE_SOURCE_TYPES`. {code}
6. ai gọi: `ensure_guideline_slot` (2 chỗ). {code}
7. invariant: đọc `metadata["source_type"]` **đã lưu**, không gọi
   `infer_source_type`. Chunk cũ thiếu trường đó sẽ không bao giờ được coi là
   guideline ở đây, dù `rag/retriever._source_type_from_meta` đã suy ra và **ghi
   ngược vào chính dict đó** (`src.rag` Q-17). Vì việc ghi ngược xảy ra trước
   trong cùng request, hàm này **thường** thấy giá trị đã suy ra — nhưng đó là
   phụ thuộc vào side effect của module khác, không phải hợp đồng. {code}
8. deprecated: không. {code}

### [x] `ensure_guideline_slot` (`_retrieval.py:134-186`)
1. in/out: `(output, pool, limit) -> RetrievalOutput | None`. {code}
2. side effect: `logger.debug`. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `limit` = `chat_rerank_top_k`. {code}
6. ai gọi: `retrieve_for_chat` — **3 chỗ** (nhánh không reranker, nhánh thành
   công, nhánh reranker lỗi). {code}
7. **invariant có số đo thật:** docstring nêu đo trên 152 truy vấn — ~760 đoạn
   guideline vào pool, chỉ **16** sống sót ra câu trả lời (2 aad + 14 textbook +
   **0 nice**), trong khi `aad_guideline` là tầng nguồn điểm cao nhất (4,5/5).
   Đây là loại bằng chứng mà chương đánh giá của khoá luận cần. Quyết định đặt
   chữa ở tầng **rerank** thay vì tầng retrieve được rút ra đúng từ số đó. Hai
   chi tiết cẩn thận: (a) nếu `output` là None (OOD guard đã cắt) thì **không**
   bơm guideline — vì lúc đó câu hỏi ngoài phạm vi; (b) tìm ô yếu nhất bằng
   `min(range(...), key=...)` chứ không giả định list đã sắp giảm dần, có comment
   giải thích. Comment `ponytail:` cũng thừa nhận nó phá cap
   `chat_max_chunks_per_source=1` đúng một ô, và chấp nhận có ý thức. {code+doc}
8. deprecated: không. {code}

### [x] `retrieve_for_chat` (`_retrieval.py:189-340`)
1. in/out: `(c, user, route_flags=None, normalized_query=None,
   safety_terms=None) -> RetrievalOutput | None`; 152 dòng. {code}
2. side effect: 1–3 truy vấn Chroma + embed; đọc/ghi DiskCache; nhiều dòng log. {code}
3. state: cache đĩa. {code}
4. lỗi: `try/except Exception` quanh rerank → rơi về `_full_filter`. {code}
5. config: 6 field `Settings` (`chat_min_chunk_score`, `chat_retrieve_top_k`,
   `chat_rerank_top_k`, `chat_guideline_top_k`, `chat_safety_top_k`,
   `chat_max_chunks_per_source`, `chat_rerank_floor`). {code}
6. ai gọi: `orchestrator.prepare_chat_turn:~100` — một chỗ duy nhất. {code}
7. **invariant — khoá cache tự khai giới hạn của chính nó.** `_cache_key` mở đầu
   bằng chuỗi phiên bản `"chat-query-v6"` kèm 6 dòng comment giải thích: khoá chỉ
   gồm query + vài tham số, **không phản ánh code**, nên sửa logic mà quên tăng
   version thì cache trả kết quả cũ và "bạn tưởng như thay đổi không có tác
   dụng". Lịch sử v3→v6 được ghi lại từng bước. Đây là mẫu tốt nhất về quản lý
   cache trong repo — đối lập với `cache.py` nơi cơ chế invalidation theo tag tồn
   tại mà không ai gọi (`src.cache`). {code+comment}
8. deprecated: không. {code}

### [x] `_do_retrieve_and_rerank` (hàm lồng, `_retrieval.py:~228-338`)
1. in/out: `() -> RetrievalOutput | None`. {code}
2. side effect: toàn bộ truy vấn. {code}
3. state: closure bắt `c`, `query`, `top_k`, `min_score`, `settings`,
   `safety_terms`, `effective_rerank_top_k`. {code}
4. lỗi: bắt `Exception` quanh rerank. {code}
5. config: như hàm cha. {code}
6. ai gọi: `cached_retrieve(_do_retrieve_and_rerank, _cache_key)` ở `:~340`. {code}
7. invariant: chuỗi bước — retrieve hybrid → guideline pass (**luôn**) → safety
   pass (**có điều kiện**) → rerank pool `top_k*3` → cap theo nguồn → OOD guard
   mềm → lọc acne/boil → lọc nhiễu → giữ ô guideline. Comment `:~296-298` giải
   thích vì sao cap chạy **trước** OOD guard (để guard tính avg/max trên đúng 5
   chunk). Ba đường thoát đều gọi `ensure_guideline_slot`, nên bất biến "luôn có
   một ô khuyến cáo" đúng ở cả ba. {code+comment}
8. deprecated: không. {code}

### [x] `_noise_filter` (hàm lồng, `_retrieval.py:~232-241`)
1. in/out: `(output) -> RetrievalOutput`. {code}
2. side effect: `logger.debug`. {code}
3. state: closure bắt `min_score`. {code}
4. lỗi: không. {code}
5. config: `chat_min_chunk_score` (0.25). {code}
6. ai gọi: `_full_filter`, nhánh sau rerank. {code}
7. **invariant — đây là nửa còn lại của câu trả lời cho `src.rag` Q-08:**
   dòng cuối là `return (after_noise if ... and after_noise.chunks else output)`
   — nếu bộ lọc `min_score` **xoá sạch**, hàm trả về output **chưa lọc**. Nghĩa
   là ngưỡng 0.25 tự vô hiệu hoá khi nó quá gắt cho thang điểm đang dùng. Cộng
   với việc `merge_retrieval_outputs` đã chuẩn hoá điểm về `[0,1]`, hậu quả mà
   tôi lo ở `src.rag` Q-08 **không xảy ra**. Xem Q-09 — tôi phải đính chính. {code}
8. deprecated: không. {code}

### [x] `_full_filter` (hàm lồng, `_retrieval.py:~243-253`)
1. in/out: `(output, query) -> RetrievalOutput`. {code}
2. side effect: `logger.debug`. {code}
3. state: closure. {code}
4. lỗi: không. {code}
5. config: qua `drop_query_mismatched_chunks`. {code}
6. ai gọi: 2 nhánh không-có-reranker. {code}
7. invariant: cùng mẫu fail-open như `_noise_filter` — lọc xong mà rỗng thì trả
   bản chưa lọc. Chỉ chạy khi reranker vắng mặt hoặc lỗi, tức đường suy giảm. {code}
8. deprecated: không. {code}

### [x] `source_data` (`_retrieval.py:~345-365`)
1. in/out: `(chunk) -> dict` 6 khoá cho sự kiện SSE `source`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `runtime.stream_chat_sse`. {code}
7. invariant: comment 7 dòng giải thích vì sao **gửi toàn văn** thay vì cắt 220
   ký tự — modal "Xem toàn bộ" của frontend không bao giờ nhận đủ, và quan trọng
   hơn: "xem trước bị cắt từng khiến cả người đọc lẫn reviewer kết luận nhầm
   rằng chunk không trả lời được câu hỏi". Kèm số đo (chunk trung vị 836 ký tự,
   max 2178, 5 chunk ≈ 4 KB). Đây là một quyết định **về chính việc đánh giá**,
   đáng nhắc trong phần phương pháp của báo cáo. {code+comment}
8. deprecated: không. {code}

### [x] `compute_evidence_quality` (`_retrieval.py:~370-392`)
1. in/out: `(retrieval) -> str` — `strong`/`moderate`/`weak`/`unverified`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: ngưỡng 0.90 / 0.50 cứng trong thân hàm. {code}
6. ai gọi: `runtime.stream_chat_sse`. {code}
7. invariant: docstring ghi lại đúng một lỗi hiệu chuẩn đã sửa — ngưỡng cũ
   0.65/0.40 được chỉnh khi reranker còn sigmoid **hai lần**, dải điểm bị nén vào
   `[0.500, 0.731]`; trên dải đó 0.40 **không bao giờ đạt tới**, nên nhãn
   `"weak"` là code chết và gần như mọi câu trả lời đều được gắn "Bằng chứng
   tốt". Sau khi bỏ sigmoid thừa, ngưỡng được đặt lại theo xác suất thật. Đây là
   ví dụ rõ nhất trong repo về việc một lỗi ở tầng dưới làm hỏng **nhãn đánh
   giá** ở tầng trên — và nó nhắc rằng mọi báo cáo eval sinh trước lần sửa đó
   đều mang nhãn evidence sai. Xem Q-10. {code+doc}
8. deprecated: không. {code}

---

## `_intake_parse.py`

### [x] docstring `_intake_parse.py:1`
1. in/out: 1 dòng — "Shared parsing and validation helpers for legacy and unified
   intake". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng — `llm_extractor.py` import 7 tên và `unified_intake.py`
   import 8 tên từ đây. Một hợp đồng parse dùng chung cho hai adapter, nên hai
   đường cho cùng kết quả trên cùng JSON. Đây là quyết định kiến trúc tốt. {code+doc}
8. deprecated: không. {doc}

### [x] **10 hằng enum/danh sách khoá** — `_LESION`, `_SKIN`, `_SEX`,
`_INFLAMMATION`, `_DISTRIBUTION`, `_INTENT`, `_CONTEXT_SCALARS`,
`_CONTEXT_LISTS`, `_CLINICAL_SCALARS`, `_CLINICAL_LISTS`

> 10 khối. Mục 2/3/4/7 theo nén có khai báo (hằng module, không side effect,
> không state, không lỗi; tất cả là bản sao **thủ công** của enum trong
> `schemas/core.py`). Mục 1/5/6/8 dưới đây.

1. in/out: 6 `frozenset` enum + 4 `tuple` tên khoá. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_LESION`/`_INFLAMMATION`/`_DISTRIBUTION` → `_to_user_input` và
   `_to_extraction_confidence`; `_SKIN`/`_SEX` → cả hai; `_INTENT` →
   `unified_intake.classify:137`. Bốn tuple `_CONTEXT_*`/`_CLINICAL_*`: grep
   trong file cho thấy chúng chỉ được dùng để dựng `_OLLAMA_JSON_SCHEMA`. {code}
8. deprecated: không. {code}

**Nhận xét riêng:** sáu enum ở đây phải khớp tay với `Literal` trong
`schemas/core.py` **và** với danh sách trong system prompt của intaker
(`model/intaker/Modelfile`). **Ba nơi**, không nơi nào sinh ra từ nơi nào. Thêm
một lesion type phải sửa đủ ba chỗ; sót một thì giá trị mới bị `_lfr` lặng lẽ
loại. Không có test nào so ba danh sách.

### [x] `_DEFAULT_CONF` (`_intake_parse.py:~62`)
1. in/out: hằng float mặc định khi model không kèm confidence. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_coerce_conf`, `_scalar_node`, `_list_nodes`. {code}
7. invariant: dùng khi model trả **value trần** thay vì `{value, confidence}`.
   Nghĩa là một model bỏ qua yêu cầu confidence vẫn cho ra hồ sơ với confidence
   mặc định, không phải 0 — hướng chọn là "tin", không phải "nghi". {code}
8. deprecated: không. {code}

### [x] `_scalar_schema` (`_intake_parse.py:~64`)
1. in/out: hàm/hằng dựng mảnh JSON Schema cho một scalar `{value, confidence}`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `_OLLAMA_JSON_SCHEMA`. {code}
7. invariant: chỉ phục vụ đường legacy — `unified_intake` gọi
   `generate_text(response_format="json")` (JSON mode chung), **không** dùng
   schema này. Comment `unified_intake:~110` giải thích: llama.cpp không parse
   nổi `anyOf`-null lồng nhau nên trả 400. {code+comment}
8. deprecated: chỉ sống ở đường legacy. {code}

### [x] `_list_schema` (`_intake_parse.py:~66`)
1. in/out: mảnh JSON Schema cho list `{value, confidence}`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `_OLLAMA_JSON_SCHEMA`. {code}
7. invariant: như trên. {code}
8. deprecated: như trên. {code}

### [x] `_OLLAMA_JSON_SCHEMA` (`_intake_parse.py:~68`)
1. in/out: dict JSON Schema đầy đủ cho hợp đồng trích xuất. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `llm_extractor._call:79`. **Không** được `unified_intake` dùng. {code}
7. invariant: là hợp đồng chính thức của trích xuất, nhưng đường production
   (unified) **không** ép nó — nó chỉ ép `"json"`. Toàn bộ việc bảo vệ hợp đồng ở
   production do các parser khoan dung bên dưới làm. Xem Q-11. {code}
8. deprecated: không. {code}

### [x] `ExtractorFallback` (`_intake_parse.py:~118-120`)
1. in/out: lớp con `Exception`. {code}
2-3. không. {code}
4. lỗi: chính nó là tín hiệu "phải dùng rule fallback". {code}
5. config: không. {code}
6. ai gọi: raise ở `_extract_json`, `_validate_contract`; bắt ở `intake.py`. {code}
7. invariant: song đối với `RouterFallback` — hai loại fallback cho hai vai của
   cùng một model ở chế độ unified. `UnifiedIntake.run` dịch mọi lỗi thành
   `ExtractorFallback`, `classify` dịch thành `RouterFallback`. {code}
8. deprecated: không. {code}

### [x] `LLMExtractResult` (`_intake_parse.py:123-126`)
1. in/out: dataclass **frozen** 2 trường — `user: UserInput`,
   `confidence: ExtractionConfidence`. {code}
2. side effect: không. {code}
3. state: immutable. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `LLMExtractor.run`, `UnifiedIntake.run`; `intake.py` tiêu thụ. {code}
7. invariant: hai adapter trả **cùng một** kiểu — đó là thứ khiến `intake.py`
   không cần biết mình đang chạy chế độ nào. {code}
8. deprecated: không. {code}

### [x] `_extract_json` (`_intake_parse.py:129-146`)
1. in/out: `(raw: str) -> str`. {code}
2-3. không. {code}
4. lỗi: 2 nhánh `ExtractorFallback`. {code}
5. config: không. {code}
6. ai gọi: `llm_extractor._call` gián tiếp, `unified_intake._infer:117`. {code}
7. invariant: **gần trùng** `llm_router._extract_json`, khác đúng kiểu ngoại lệ
   ném ra và chữ trong thông điệp. Hai bản sao. Xem Q-08. {code}
8. deprecated: không. {code}

### [x] `_coerce_conf` (`_intake_parse.py:149-154`)
1. in/out: `(raw) -> float`. {code}
2-3. không. {code}
4. lỗi: không — sai kiểu trả `_DEFAULT_CONF`. {code}
5. config: `_DEFAULT_CONF`. {code}
6. ai gọi: `_scalar_node`, `_list_nodes`, `unified_intake.classify:144`. {code}
7. invariant: **không** chặn `bool` như `llm_router._coerce_confidence` làm —
   `float(True)` cho 1.0 lọt im lặng. Hai hàm ép confidence trong repo, một cái
   cẩn thận hơn cái kia. Ở đây hậu quả nhẹ (confidence 1.0 cho một trường), ở
   `llm_router` thì đó là confidence của cả lượt. {code}
8. deprecated: không. {code}

### [x] `_scalar_node` (`_intake_parse.py:157-165`)
1. in/out: `(section, key, prefix) -> tuple[Any, float]`. {code}
2-3. không. {code}
4. lỗi: không — thiếu khoá/sai kiểu trả `(None, 0.0)`. {code}
5. config: `_DEFAULT_CONF`. {code}
6. ai gọi: `_enum_fr`, `_int_fr`, `_bool_fr`. {code}
7. **invariant: tham số `prefix` không được dùng trong thân hàm.** Nó được
   truyền xuyên qua **6 hàm** (`_scalar_node`, `_list_nodes`, `_enum_fr`,
   `_int_fr`, `_bool_fr`, `_lfr`) và không hàm nào đọc. Dấu vết của một cơ chế
   thông báo lỗi theo đường dẫn field đã bị gỡ. Xem Q-12. Chấp cả dạng phẳng
   (`"age": 22`) lẫn dạng `{value, confidence}` — docstring gọi là "khoan dung",
   đúng. {code}
8. deprecated: tham số chết. {code}

### [x] `_list_nodes` (`_intake_parse.py:168-183`)
1. in/out: `(section, key, prefix) -> list[tuple[Any, float]]`. {code}
2-3. không. {code}
4. lỗi: không — không phải list thì trả `[]`. {code}
5. config: `_DEFAULT_CONF`. {code}
6. ai gọi: `_lfr`. {code}
7. invariant: item `None` được giữ lại nhưng gán confidence 0.0 (`:182`), rồi
   `_lfr` loại vì không phải `str`. Hai tầng cùng loại một thứ. `prefix` chết. {code}
8. deprecated: tham số chết. {code}

### [x] `_sections` (`_intake_parse.py:186-194`)
1. in/out: `(data) -> tuple[Mapping, Mapping]`. {code}
2-3. không. {code}
4. lỗi: không — thiếu/sai kiểu trả `{}`. {code}
5. config: không. {code}
6. ai gọi: `_to_user_input:295`, `_to_extraction_confidence:~366`. {code}
7. invariant: `clinical` là `null` trong phần lớn JSON của intaker (prompt yêu
   cầu thế cho câu hỏi kiến thức), và hàm này biến `null` thành `{}` — nên mọi
   `_lfr(clinical, ...)` sau đó trả list rỗng thay vì nổ. {code}
8. deprecated: không. {code}

### [x] `_validate_contract` (`_intake_parse.py:197-204`)
1. in/out: `(data) -> None`. {code}
2-3. không. {code}
4. lỗi: `ExtractorFallback` nếu root không phải JSON object. {code}
5. config: không. {code}
6. ai gọi: `llm_extractor.run:62`, `unified_intake._infer:118`,
   `_to_user_input:294`, `_to_extraction_confidence:~365`. {code}
7. invariant: docstring nói thẳng "Only real crash guard left" — mọi thứ dưới
   root do parser khoan dung xử lý, **drop field thay vì vứt cả inference**.
   Đây là một triết lý rõ ràng và được thực thi nhất quán ở 6 hàm `_*_fr`.
   Đánh đổi: một field bị model bịa sai enum sẽ **biến mất im lặng**, không có
   log nào. Xem Q-11. {code+doc}
8. deprecated: không. {code}

### [x] `_enum_fr` (`_intake_parse.py:207-220`)
1. in/out: `(section, key, prefix, allowed) -> FieldResult[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `allowed` từ người gọi. {code}
6. ai gọi: 5 chỗ (sex, skin_type, inflammation_level ×2). {code}
7. invariant: comment `:217` — "Enum hallucinations are explicitly dropped before
   Pydantic validation". Đúng và cần: nếu để lọt, `AcneClinicalInput` sẽ raise
   `ValidationError` giữa stream. Nhưng "drop" nghĩa là **im lặng**: model bịa
   `inflammation_level="rất nặng"` cho ra `unknown`, không phân biệt được với
   "model không biết". {code+comment}
8. deprecated: `prefix` chết. {code}

### [x] `_int_fr` (`_intake_parse.py:223-245`)
1. in/out: `(section, key, prefix, *, maximum=None) -> FieldResult[int]`. {code}
2-3. không. {code}
4. lỗi: không — mọi sai kiểu thành `FieldResult.none()`. {code}
5. config: `maximum=120` cho `age`; không có trần cho `duration_weeks`. {code}
6. ai gọi: age, duration_weeks (mỗi cái 2 lần). {code}
7. invariant: chặn `isinstance(value, bool)` **trước** khi ép int — `int(True)`
   là 1, sẽ thành `age=1` im lặng. Chi tiết đúng mà `_coerce_conf` bỏ sót. Chấp
   `"22"` chuỗi qua `int(float(value))`, nên `"22.7"` thành 22. Không có trần cho
   `duration_weeks` nghĩa là model trả 99999 tuần vẫn qua. {code}
8. deprecated: `prefix` chết. {code}

### [x] `_bool_fr` (`_intake_parse.py:248-259`)
1. in/out: `(section, key, prefix) -> FieldResult[bool]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: bảng chuỗi chấp nhận được viết thẳng trong thân hàm. {code}
6. ai gọi: `is_pregnant`, `is_breastfeeding` (mỗi cái 2 lần). {code}
7. invariant: chấp `"true"/"1"/"yes"/"co"/"có"` và
   `"false"/"0"/"no"/"khong"/"không"` — khoan dung với model trả chuỗi. Trả
   `FieldResult.none()` (chứ không phải False) khi không nhận ra, tức **giữ được
   ba trạng thái** ở tầng confidence. Ba trạng thái đó bị `_to_user_input:~324`
   ép về bool hai trạng thái ngay sau đó. Xem Q-13. {code}
8. deprecated: `prefix` chết. {code}

### [x] `_lfr` (`_intake_parse.py:262-277`)
1. in/out: `(section, key, prefix, allowed=None) -> ListFieldResult[str]`. {code}
2-3. không. {code}
4. lỗi: không — item sai kiểu bị bỏ qua. {code}
5. config: `allowed` tuỳ field. {code}
6. ai gọi: 14 chỗ. Hàm được dùng nhiều nhất file. {code}
7. invariant: dedupe theo giá trị đã chuẩn hoá, **giữ confidence cao nhất** khi
   trùng (`:274-276`). Với `allowed` thì hạ chữ trước khi so; **không** hạ chữ
   khi `allowed is None` (allergies, products, medications, scarring_signs,
   hormonal_factors, treatment_goals) — nên `"BHA"` và `"bha"` là hai mục riêng
   ở đúng những field mà trùng lặp gây hại nhất. Xem Q-14. {code}
8. deprecated: `prefix` chết. {code}

### [x] `_to_user_input` (`_intake_parse.py:293-360`)
1. in/out: `(data, clean_text, mode) -> UserInput`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ExtractorFallback` từ `_validate_contract`; `ValidationError` nếu
   pydantic từ chối (đã được các `_*_fr` chặn trước). {code}
5. config: không. {code}
6. ai gọi: `llm_extractor.run:63`, `unified_intake.run:~166`. {code}
7. **invariant — đường production chỉ điền 6/12 trường lâm sàng, và thực tế chỉ
   3.** Tôi đếm bằng `ast` trên `schemas/core.py` và trên chính lời gọi:
   `AcneClinicalInput` có **12** trường; `_to_user_input` truyền **6**
   (`lesion_types`, `inflammation_level`, `lesion_distribution`, `scarring_signs`,
   `hormonal_factors`, `treatment_goals`); **không** truyền `medication_history`,
   `skincare_products`, `canonical_ingredients`, `usage_frequencies`,
   `concentrations`, `red_flags_input`. Thêm nữa, system prompt của intaker
   (`model/intaker/Modelfile`) quy định "clinical là null hoặc object gồm **đúng**
   lesion_types, inflammation_level, lesion_distribution" — nên 3 trong 6 trường
   được parse cũng luôn rỗng. Kết quả: ở production, **9/12 trường lâm sàng vĩnh
   viễn rỗng**. Comment `:~349-353` giải thích việc bỏ lớp regex "safety net" ở
   đây bằng một phép đo 13 câu đối kháng — lập luận đúng, nhưng nó không nói rằng
   6 trường kia mất theo. Xem Q-15. {code+comment}
8. deprecated: không. {code}

### [x] `_to_extraction_confidence` (`_intake_parse.py:363-394`)
1. in/out: `(data, *, clean_text="") -> ExtractionConfidence` (16 trường). {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: như trên. {code}
5. config: không. {code}
6. ai gọi: `llm_extractor.run:64`, `unified_intake.run:~167`. {code}
7. invariant: `red_flags=ListFieldResult.empty()` **cứng** (`:~393`) — đường LLM
   không bao giờ sinh red flag. Tham số `clean_text` khai keyword-only và
   **không dùng** trong thân hàm — tham số chết thứ hai của file. {code}
8. deprecated: `clean_text` chết. {code}

---

## `unified_intake.py`

### [x] docstring `unified_intake.py:1`
1. in/out: 1 dòng — "One-model adapter for unified intent routing and clinical
   extraction". {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: đúng và là điểm mấu chốt của kiến trúc hiện tại — **một**
   lời gọi model phục vụ **hai** giao diện cũ (`classify` và `run`). {code+doc}
8. deprecated: không. {doc}

### [x] `_RUNTIME_SYSTEM` (`unified_intake.py:25-40`)
1. in/out: chuỗi system prompt 3.322 ký tự, gồm bảng IGA 5 bậc (AAD 2024). {code}
2-4. không. {code}
5. config: hằng cứng trong Python. {code}
6. ai gọi: `_infer:113` (`generate_text(system=...)`). {code}
7. **invariant: chuỗi này KHÔNG tới model, và đó là đúng.** `di.py:151` dựng
   backend với `use_modelfile_system=True`, nên `_build_messages:196` bỏ system
   message. Tôi đã đối chiếu thay vì suy đoán: `model/intaker/Modelfile` SYSTEM
   và hằng này **giống hệt nhau** sau chuẩn hoá khoảng trắng — cùng 3.322 ký tự,
   cùng sha256 `6ee28283b579feb8`. Đây là bản sao có chủ đích để người đọc code
   thấy được hợp đồng. Rủi ro: hai bản phải đồng bộ bằng tay, không test nào
   canh. Xem Q-16. Về nội dung: đây là **nơi duy nhất** trong repo neo
   `inflammation_level` vào thang IGA của AAD 2024, và nó đáng được trích trong
   chương phương pháp. {code}
8. deprecated: không. {code}

### [x] `_MAX_CLEAN_TEXT_CHARS` (`unified_intake.py:42`)
1. in/out: `4_000`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_validated_clean_text:~189`. {code}
7. invariant: trùng số với `intake.MAX_MESSAGE_CHARS = 4000`, nhưng là hằng
   riêng. `run_intake` đã raise nếu vượt, nên cổng ở đây không bao giờ chạm —
   trừ khi ai đó gọi `UnifiedIntake` trực tiếp. Phòng thủ chiều sâu. {code}
8. deprecated: không. {code}

### [x] `_MAX_HISTORY_TURNS` (`unified_intake.py:43`)
1. in/out: `= HISTORY_WINDOW_TURNS` (6). {code}
2-4. không. {code}
5. config: import từ `session.models` — **không** phải hằng riêng. {code}
6. ai gọi: `_validated_followup_history:~205`. {code}
7. invariant: đây là chỗ **duy nhất** trong `chat/` ngoài `prompt_builder` dùng
   lại hằng lịch sử thay vì viết số mới. Đúng cách. Nhưng lưu ý: prompt hệ thống
   nói "tối đa **3** turn lịch sử gần nhất" trong khi hằng này là **6**. Prompt
   và code bất đồng về số lượt. Xem Q-17. {code}
8. deprecated: không. {code}

### [x] `_MAX_HISTORY_CONTENT_CHARS` (`unified_intake.py:44`)
1. in/out: `300`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_validated_followup_history:~213`. {code}
7. invariant: trùng số 300 với `llm_router._short_history` và
   `llm_extractor._build_prompt` — ba nơi, ba hằng, cùng giá trị. {code}
8. deprecated: không. {code}

### [x] `_UnifiedContractError` (`unified_intake.py:49-50`)
1. in/out: lớp con `Exception`. {code}
2-3. không. {code}
4. lỗi: tín hiệu nội bộ. {code}
5. config: không. {code}
6. ai gọi: raise ở `_infer` và `_validated_clean_text`; **không** thoát ra ngoài
   lớp — `classify` dịch thành `RouterFallback`, `run` dịch thành
   `ExtractorFallback`. {code}
7. invariant: docstring nói đúng vai — "Internal error translated to the
   interface-specific fallback type". Đây là thứ cho phép một lời gọi model phục
   vụ hai giao diện có hai kiểu lỗi khác nhau. {code}
8. deprecated: không. {code}

### [x] `UnifiedIntake` (`unified_intake.py:53-183`)
1. in/out: `UnifiedIntake(llm, model, timeout)`. {code}
2. side effect: gọi Ollama; giữ cache LRU. {code}
3. state: `_cache` (OrderedDict), `_cache_lock`, `_closed`. {code}
4. lỗi: hai loại fallback tuỳ giao diện. {code}
5. config: `settings.intake_model` (`acne-intaker`), `settings.intake_timeout` (60). {code}
6. ai gọi: `di.py:153`; gán cho **cả** `c.llm_router` và `c.llm_extractor`. {code}
7. invariant: docstring lớp — "Expose one inference through both legacy intake
   interfaces". Đây là lý do tồn tại của cache: `intake.py` gọi `classify()` rồi
   `run()` cho **cùng một** lượt, và không có cache thì đó là hai lần gọi model. {code}
8. deprecated: không. {code}

### [x] `UnifiedIntake._CACHE_SLOTS` (`unified_intake.py:~66`)
1. in/out: `int = 8`. {code}
2-4. không. {code}
5. config: hằng lớp, không ở `Settings`. {code}
6. ai gọi: `_infer:~123`. {code}
7. **invariant: comment 9 dòng phía trên ghi lại một lỗi hiệu năng thật đã sửa.**
   Trước đây cache là **một ô duy nhất** trên instance dùng chung cho mọi request;
   luồng `classify() → run()` trùng ô nên bình thường chỉ gọi model một lần,
   nhưng hai request song song ghi đè ô của nhau **giữa hai bước**, khiến request
   bị đè miss và gọi intaker **lần hai**. "Dưới tải, chi phí intake gấp đôi một
   cách không xác định." Đây là mẫu lỗi khó thấy nhất trong repo và nó được ghi
   lại đúng chỗ. Comment `ponytail:` còn nêu ngưỡng nâng cấp. {code+comment}
8. deprecated: không. {code}

### [x] `UnifiedIntake.__init__` (`unified_intake.py:~78-84`)
1. in/out: `(llm, model: str, timeout: float) -> None`. {code}
2. side effect: không. {code}
3. state: 6 thuộc tính. {code}
4. lỗi: `float(timeout)`. {code}
5. config: từ `di.py`. {code}
6. ai gọi: `di.py:153`. {code}
7. invariant: `self._timeout` gán và không dùng — cùng vấn đề với hai adapter
   legacy (`src.chat.routing` Q-03). Timeout thật ở tầng HTTP. {code}
8. deprecated: không. {code}

### [x] `UnifiedIntake.model` (property, `~86-88`)
1. in/out: `() -> str`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: 0 caller ngoài lớp. {code}
7. invariant: chỉ đọc. {code}
8. deprecated: 0 caller. {code}

### [x] `UnifiedIntake.timeout` (property, `~90-92`)
1. in/out: `() -> float`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: 0 caller. {code}
7. invariant: phơi ra một giá trị mà lớp không dùng. {code}
8. deprecated: 0 caller. {code}

### [x] `UnifiedIntake._infer` (`unified_intake.py:94-132`)
1. in/out: `(clean_text, history) -> dict`. {code}
2. side effect: đọc/ghi cache; **một** lời gọi Ollama khi miss. {code}
3. state: `_cache` dưới `_cache_lock`. {code}
4. lỗi: `_UnifiedContractError` (re-raise) hoặc bọc mọi `Exception`. {code}
5. config: `temperature=0.0`, `response_format="json"`. {code}
6. ai gọi: `classify:136`, `run:~164`. {code}
7. invariant: khoá cache là `(clean_text đã cắt, JSON của lịch sử rút gọn)` —
   phản ánh **đúng** những gì đi vào prompt, nên không thể trúng nhầm. Lock được
   giữ **ngắn** (chỉ quanh đọc/ghi dict), không giữ trong lúc gọi model — nghĩa
   là hai request giống hệt nhau đến cùng lúc vẫn gọi model hai lần rồi cùng ghi
   một kết quả. Đánh đổi đúng: giữ lock qua một lời gọi 60 giây sẽ tệ hơn nhiều. {code}
8. deprecated: không. {code}

### [x] `UnifiedIntake.classify` (`unified_intake.py:134-153`)
1. in/out: `(clean_text, history) -> RouteDecision`. {code}
2. side effect: qua `_infer`. {code}
3. state: không. {code}
4. lỗi: `RouterFallback`. {code}
5. config: `_INTENT`. {code}
6. ai gọi: `intake.run_intake` (tầng 1 của ba tầng router). {code}
7. invariant: comment `:138-139` — "Không có đường tolerant cho intent: không
   route được thì semantic router là lựa chọn duy nhất còn lại". Đây là ngoại lệ
   **có chủ ý** với triết lý khoan dung của `_intake_parse`: mọi field khác được
   drop im lặng, riêng `intent` sai thì cả lượt rơi tầng. Đúng — intent là thứ
   duy nhất không có giá trị mặc định an toàn. `RouteDecision` trả về để
   `route_flags` rỗng (xem `src.chat.routing`). {code+comment}
8. deprecated: không. {code}

### [x] `UnifiedIntake.run` (`unified_intake.py:155-175`)
1. in/out: keyword-only `(clean_text, clean_text_no_accent, mode, history) -> LLMExtractResult`. {code}
2. side effect: qua `_infer` (thường **trúng cache** vì `classify` đã gọi trước). {code}
3. state: không. {code}
4. lỗi: `ExtractorFallback`. {code}
5. config: không. {code}
6. ai gọi: `intake.run_intake`. {code}
7. invariant: `del clean_text_no_accent` ngay dòng đầu (`:163`) — tham số nhận
   rồi **bỏ**, giữ lại chỉ vì chữ ký phải khớp `LLMExtractor.run`. Model unified
   tự hiểu tiếng Việt không dấu (prompt nói thế), nên bản không dấu là thừa. Đây
   là tham số chết **có lý do** và thấy được ngay dòng đầu — khác hẳn `prefix` ở
   `_intake_parse` (chết mà không ai biết). {code}
8. deprecated: tham số giữ cho tương thích chữ ký. {code}

### [x] `UnifiedIntake.close` (`unified_intake.py:177-183`)
1. in/out: `() -> None`. {code}
2. side effect: đóng HTTP client của backend, **một lần**. {code}
3. state: đặt `_closed = True`. {code}
4. lỗi: không bắt. {code}
5. config: không. {code}
6. ai gọi: `di.py:73-79` — **hai lần** ở chế độ unified. {code}
7. invariant: cờ `_closed` khiến lời gọi thứ hai `return` ngay. Idempotent theo
   hợp đồng. Đây là câu trả lời cho `src.chat.routing` Q-04. {code}
8. deprecated: không. {code}

### [x] `_validated_clean_text` (`unified_intake.py:186-192`)
1. in/out: `(clean_text: Any) -> str`. {code}
2-3. không. {code}
4. lỗi: `_UnifiedContractError` nếu rỗng/không phải chuỗi. {code}
5. config: `_MAX_CLEAN_TEXT_CHARS`. {code}
6. ai gọi: `_infer:~101`. {code}
7. invariant: comment `ponytail:` — "cắt thay vì fallback. Input dài quá chỉ mất
   phần đuôi, vẫn tốt hơn vứt cả inference; prompt generator vẫn nhận raw input
   đầy đủ". Lập luận đúng và kiểm được: `orchestrator` truyền
   `intake.user.description` (raw) cho `prompt.build`, không truyền bản cắt. {code+comment}
8. deprecated: không. {code}

### [x] `_turn_field` (`unified_intake.py:195-198`)
1. in/out: `(turn: Any, name: str) -> Any`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `_validated_followup_history` (2 lần). {code}
7. invariant: chấp cả `Mapping` lẫn object có thuộc tính — cùng mẫu với
   `llm_router._short_history`, nhưng ở đây được **tách thành hàm riêng**. Bản
   thứ ba của cùng ý tưởng trong `chat/`. {code}
8. deprecated: không. {code}

### [x] `_validated_followup_history` (`unified_intake.py:201-218`)
1. in/out: `(history: Any) -> list[dict[str, str]]`. {code}
2-3. không. {code}
4. lỗi: không — turn lạ bị bỏ qua. {code}
5. config: `_MAX_HISTORY_TURNS` (6), `_MAX_HISTORY_CONTENT_CHARS` (300). {code}
6. ai gọi: `_infer:~102`. {code}
7. invariant: comment `ponytail:` gọi đây là **trust boundary** — "chỉ role
   user/assistant mới vào prompt", turn lạ (`role="tool"`, content rỗng) bị bỏ
   qua chứ không fallback. Đây là lời khai đúng loại: nó nói rõ đây là ranh giới
   tin cậy, và code thực thi đúng hai điều kiện đó. {code+comment}
8. deprecated: không. {code}

### [x] `_build_user_prompt` (`unified_intake.py:221-228`)
1. in/out: `(clean_text, history) -> str`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `_infer:~114`. {code}
7. invariant: không có lịch sử thì trả **nguyên văn** `clean_text`, không bọc
   JSON — nên phần lớn request gửi đúng câu người dùng gõ, giống hệt dữ liệu
   fine-tune. Có lịch sử thì bọc `FOLLOWUP_HISTORY_JSON` + `CURRENT_TURN`. Hai
   định dạng prompt cho một model; nếu tập train chỉ có một trong hai thì đây là
   nguồn train/serve skew. Cần kiểm khi kiểm kê `datagen/intakedata`. Xem Q-17. {code}
8. deprecated: không. {code}

---

## `runtime.py`

### [x] docstring `runtime.py:1-6`
1. in/out: 6 dòng, có sơ đồ luồng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: luồng `message → intake → retrieve → build_prompt →
   llm.stream_text → safety suffix → SSE → persist → audit`. **Đối chiếu:** đúng
   thứ tự trong `stream_chat_sse`. Đây là lời khai chính xác nhất về kiến trúc
   runtime trong repo. {code+doc}
8. deprecated: không. {doc}

### [x] `_event` (`runtime.py:33-35`)
1. in/out: `(event: str, data) -> str`; định dạng SSE `data: {...}\n\n`. {code}
2-3. không. {code}
4. lỗi: `TypeError` nếu `data` không serialize được. {code}
5. config: `ensure_ascii=False`. {code}
6. ai gọi: ~10 chỗ trong `stream_chat_sse`. {code}
7. invariant: `ensure_ascii=False` giữ tiếng Việt nguyên dạng qua SSE thay vì
   escape `\uXXXX` — cần thiết, và nhất quán với mọi `json.dumps` khác trong
   `chat/`. {code}
8. deprecated: không. {code}

### [x] `_snapshot_for_persistence` (`runtime.py:38-42`)
1. in/out: `(intake) -> NormalizedSnapshot | None`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `stream_chat_sse` khi ghi turn của user. {code}
7. **invariant: chỉ lưu snapshot khi `primary_intent == "advise"`.** Nghĩa là
   một lượt `knowledge` hay `clarify` **không** để lại dữ kiện có cấu trúc trong
   session, nên `fold_history_facts` ở lượt sau không thấy nó, và
   `_has_established_case` cũng không tính nó. Đây là quyết định đúng hướng (câu
   hỏi kiến thức không phải khai báo ca bệnh) nhưng nó không được ghi ở đâu, và
   nó tương tác với `_intent_patch` — vốn nâng `clarify` lên `advise` **dựa
   trên** `_has_established_case`. Hai cơ chế ràng buộc nhau qua một điều kiện
   ngầm. Xem Q-18. {code}
8. deprecated: không. {code}

### [x] `_supports_keyword` (`runtime.py:45-53`)
1. in/out: `(callable_obj, keyword: str) -> bool`. {code}
2. side effect: `inspect.signature` (có cache nội bộ của `inspect`). {code}
3. state: không. {code}
4. lỗi: `except (TypeError, ValueError): return True` — không nội quan được thì
   **giả định là hỗ trợ**. Fail-open. {code}
5. config: không. {code}
6. ai gọi: `stream_chat_sse:166`. {code}
7. invariant: tồn tại **chỉ vì** `stream_text` và `generate_text` có chữ ký khác
   nhau và người viết không chắc backend nào được wire (test dùng backend giả).
   Đây là triệu chứng của Q-05, không phải nguyên nhân. Fail-open nghĩa là backend
   giả không có `num_predict` sẽ nhận kwargs lạ và nổ `TypeError` — trừ khi nó có
   `**kwargs`. {code}
8. deprecated: không. {code}

### [x] `stream_chat_sse` (`runtime.py:56-345`)
1. in/out: generator, yield chuỗi SSE. {code}
2. side effect: gọi model streaming; ghi session (2 turn); ghi audit; nhiều log. {code}
3. state: session DB, audit DB. {code}
4. lỗi: bọc rộng; audit nuốt lỗi (`src.db` Q-04). {code}
5. config: `chat_max_context_chars` gián tiếp; `num_predict=-1` cho knowledge. {code}
6. ai gọi: `api/routes/chat.py`. {code}
7. **invariant — nơi lệch runtime↔eval trở thành cụ thể:** `:162`
   `_stream_num_predict = -1 if _primary_intent == "knowledge" else None`, và
   `:165-168` chỉ truyền khi `_supports_keyword(c.llm.stream_text, "num_predict")`.
   `stream_text` có tham số đó; `generate_text` (đường eval) **không**. Nên câu
   hỏi `knowledge` ở production sinh không giới hạn, còn khi eval thì bị chặn ở
   `llm_num_predict = 2048`. Ngoài ra `:228-229` gỡ cờ `urgency_red_flag` khỏi
   `safety_route_flags` khi intent là `knowledge` và không có
   `urgent_personal_case` — một cổng lọc cảnh báo mà `get_safety_suffix` không
   biết. Xem Q-05. {code}
8. deprecated: không. {code}

---

## `intake.py`

### [x] docstring `intake.py:1-~30`
1. in/out: lời khai đầu file. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: mô tả đường intake dùng chung cho SSE, WS và eval. Đúng —
   `run_intake` là cửa duy nhất, `orchestrator.prepare_chat_turn` gọi nó. {code+doc}
8. deprecated: không. {doc}

### [x] `ScopeDecision` (`intake.py:40`)
1. in/out: `Literal["in_scope","refuse_hard","pass_to_llm_soft"]`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `IntakeResult.scope_decision`; `orchestrator` đọc. {code}
7. invariant: ba giá trị, nhưng grep trong file cho thấy `"pass_to_llm_soft"`
   chỉ được gán ở **một** chỗ (`:559`) còn `"refuse_hard"` ở **bốn** chỗ. Giá trị
   `pass_to_llm_soft` là tàn dư của cơ chế soft-OOS đã chuyển sang
   `SemanticRouter` — comment ở `di.py:~228` xác nhận việc chuyển đó. {code}
8. deprecated: không. {code}

### [x] `EffectiveMode` (`intake.py:41`)
1. in/out: `Literal["hybrid","llm_only","refuse","clarify"]`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `IntakeResult.effective_mode`; `orchestrator:~85,90`. {code}
7. invariant: trộn **hai khái niệm** — `hybrid`/`llm_only` là chế độ *retrieval*,
   còn `refuse`/`clarify` là *kết quả định tuyến*. `_resolve_mode` chỉ trả hai
   giá trị đầu; hai giá trị sau do nhánh khác gán. Một Literal cho hai trục. {code}
8. deprecated: không. {code}

### [x] `MAX_MESSAGE_CHARS` (`intake.py:42`)
1. in/out: `4000`. {code}
2-4. không. {code}
5. config: hằng cứng, không ở `Settings`. {code}
6. ai gọi: `run_intake:~211`. {code}
7. invariant: trùng số với `unified_intake._MAX_CLEAN_TEXT_CHARS`, hai hằng riêng.
   Kiểm ở đây raise `ValueError` → API trả lỗi; kiểm ở kia cắt im lặng. Hai
   chính sách cho cùng một trần. {code}
8. deprecated: không. {code}

### [x] `MAX_MESSAGE_WORDS` (`intake.py:43`)
1. in/out: `500`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `run_intake:~213`. {code}
7. invariant: thông điệp lỗi cho người dùng viết **không dấu**
   ("Tin nhan qua dai ... Vui long rut gon") trong khi mọi chuỗi hướng tới người
   dùng khác trong repo đều có dấu. Lệch nhỏ nhưng người dùng cuối thấy được. {code}
8. deprecated: không. {code}

### [x] `_count_words` (`intake.py:46-47`)
1. in/out: `(text: str) -> int`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `run_intake:~212`. {code}
7. invariant: `len(text.split())` — đếm âm tiết với tiếng Việt, giống
   `VietnameseChunker._tok_len`. Bản sao thứ hai của cùng phép đếm. {code}
8. deprecated: không. {code}

### [x] `IntakeResult` (`intake.py:51-70`)
1. in/out: dataclass **18 trường**. {code}
2. side effect: không. {code}
3. state: mutable — `orchestrator:~64-81` sửa `user`, `confirmed_profile`,
   `safety_terms` tại chỗ. {code}
4. lỗi: không validate. {code}
5. config: không. {code}
6. ai gọi: `run_intake` dựng (nhiều đường thoát); `orchestrator`, `runtime`,
   runner eval đọc. {code}
7. invariant: đây là **hợp đồng lớn nhất** của `chat/` — 18 trường đi từ intake
   sang mọi tầng sau. Ba trường trong đó luôn có giá trị cố định trên đường
   production: `teencode_replaced` luôn `[]` (Q-01), và
   `user.clinical.red_flags_input`/`canonical_ingredients` luôn rỗng (Q-15). {code}
8. deprecated: không. {code}

### [x] `_SAFETY_SIGNAL_TERMS` (`intake.py:~88-93`)
1. in/out: tuple 17 cụm (thai kỳ, retinoid, kháng sinh). {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_extract_safety_terms`, `_profile_safety_terms`. {code}
7. invariant: gần trùng `_retrieval._MEDICAL_SAFETY_TERMS` (19 cụm) — hai bảng,
   hai file, phục vụ hai bước liên tiếp của cùng một luồng. Bảng ở đây **sinh**
   safety terms, bảng kia **quyết định** có chạy safety pass hay không. Lệch một
   mục là một term được sinh mà không kích hoạt pass. {code}
8. deprecated: không. {code}

### [x] `_extract_safety_terms` (`intake.py:~96-137`)
1. in/out: `(message: str, user: UserInput) -> list[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_SAFETY_SIGNAL_TERMS`. {code}
6. ai gọi: `run_intake` (2 chỗ). {code}
7. **invariant — comment ở đây là lời khai chất lượng cao nhất trong module.**
   `:~97-105` nói rõ: danh sách này trả lời câu "**văn bản có nhắc tới** chủ đề
   gì", và **chỉ nên dùng cho retrieval**, không dùng để suy **trạng thái**; nó
   khớp chuỗi con, không kiểm phủ định, nên "em không mang thai" cũng sinh
   `"pregnancy"`. Kèm số đo: cổng thuốc từng đọc nó như bằng chứng đang mang thai
   và **chặn nhầm 4/5 câu**; nay đọc thẳng `user.context.is_pregnant`. Đây đúng
   là phép phân biệt mà `rule_normalizer._contains_positive` **không** làm được
   (`src.chat.routing` Q-19). Một file trong repo đã học được bài học mà file kia
   chưa. Lưu ý: hai vòng lặp cuối đọc `user.clinical.canonical_ingredients` và
   `medication_history` — **luôn rỗng** trên đường unified (Q-15), nên hai nhánh
   đó chết ở production. {code+comment}
8. deprecated: không. {code}

### [x] `_profile_safety_terms` (`intake.py:~140-152`)
1. in/out: `(profile: dict) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_SAFETY_SIGNAL_TERMS`. {code}
6. ai gọi: `run_intake` (đường `confirmed_profile`). {code}
7. invariant: bản rút gọn của hàm trên, đọc từ **hồ sơ đã xác nhận** thay vì từ
   text — nên nó **không** mang khiếm khuyết "có nhắc tới ≠ đang là". Đây là
   đường đúng, và nó tồn tại song song với đường kia. {code}
8. deprecated: không. {code}

### [x] `_snapshot_has_values` (`intake.py:~155-171`)
1. in/out: `(snapshot) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `_has_established_case`. {code}
7. invariant: `meaningful_clinical` lọc `value not in (None, "", [], {}, "unknown",
   "none")` — **loại cả `"unknown"`**, nên `inflammation_level="unknown"` (giá trị
   mặc định, luôn có mặt) không tính là dữ kiện. Đây chính là bản vá cho vấn đề
   mà `intent_router._has_any_clinical_fact` **không** vá (`src.chat.routing`
   Q-11). Hai hàm cùng câu hỏi "có dữ kiện lâm sàng chưa", một cái đúng một cái
   sai. {code}
8. deprecated: không. {code}

### [x] `_has_established_case` (`intake.py:~174-186`)
1. in/out: `(history) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `run_intake` (đưa vào `_intent_patch.repaired_intent`). {code}
7. invariant: comment `ponytail:` ghi lại việc bỏ nhánh `_is_acne_scope` — chính
   comment của `_boundary_regex` từng cảnh báo nó làm hàm này "gần như luôn True"
   vì term 2 ký tự (`"co"`, `"ma"`, `"cam"`) khớp mọi câu tiếng Việt. Nay chỉ còn
   nhánh snapshot, tức **dữ liệu đã trích xuất có cấu trúc**. Cùng bài học với
   `_extract_safety_terms`: bỏ khớp chuỗi, dùng dữ liệu có cấu trúc. {code+comment}
8. deprecated: không. {code}

### [x] `_resolve_mode` (`intake.py:~190-201`)
1. in/out: `(requested_mode, c, clean_text="", history=None) -> Literal["hybrid","llm_only"]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `c.rag_ready`. {code}
6. ai gọi: `run_intake:~232`, có truyền cả `clean_text` và `history`. {code}
7. **invariant: `clean_text` và `history` được khai, được truyền, và KHÔNG dùng
   trong thân hàm.** Hàm chỉ nhìn `requested_mode` và `c.rag_ready`. Hai tham số
   chết — và người gọi vẫn tính rồi truyền chúng. Cùng mẫu với
   `intent_router.select_relevant_history` (2/4 tham số chết) và
   `_context_adjust.span_hint`. Xem Q-19. {code}
8. deprecated: hai tham số chết. {code}

### [x] `run_intake` (`intake.py:~204-854`)
1. in/out: `(c, message, session_id=None, mode_request="auto",
   include_analytics=False) -> IntakeResult`; ~650 dòng, **hàm dài nhất repo**. {code}
2. side effect: đọc session, gọi tối đa 3 tầng router, gọi extractor, chạy
   guardrails, ghi ~8 dòng `log_pipeline_stage`. {code}
3. state: đọc `c.session_store`; không ghi (việc ghi do `runtime` làm). {code}
4. lỗi: `ValueError` cho tin nhắn quá dài; mọi lỗi router/extractor được bắt và
   hạ tầng. Có **nhiều đường thoát sớm** trả `IntakeResult` với `scope_refusal`. {code}
5. config: `MAX_MESSAGE_CHARS`, `MAX_MESSAGE_WORDS`,
   `settings.extract_min_field_conf` (qua getattr lồng hai lớp — `src.config` Q-03). {code}
6. ai gọi: `orchestrator.prepare_chat_turn:~55` — cửa duy nhất. {code}
7. invariant: ba tầng router theo đúng thứ tự docstring của `routing/__init__.py`
   — `llm_router.classify` → `semantic_router.classify` → `route_intent`, mỗi
   tầng bọc `try/except` riêng và ghi log `fallback=`. Sau đó
   `compute_route_flags` chạy **không điều kiện** để gắn cờ cho mọi đường. Một
   bản vá đáng chú ý ở `:~672-681`: cờ `urgency_red_flag` được gắn **lại** sau
   khi có `base_user.clinical`, vì `compute_route_flags` chạy trước extract nên
   `has_red_flags` luôn False ở lần gọi đầu — comment "BUG FIX" giải thích đúng.
   Nhưng bản vá đó chỉ có tác dụng khi `red_flags_input` khác rỗng, tức **không
   bao giờ** trên đường unified (Q-15). {code+comment}
8. deprecated: không. {code}

### [x] `_rule_user` (hàm lồng trong `run_intake`)
1. in/out: dựng `UserInput` bằng `normalize_chat_message` khi LLM extractor hỏng. {code}
2. side effect: chạy toàn bộ regex của `rule_normalizer`. {code}
3. state: closure bắt `clean_text`, `clean_text_no_accent`, `mode`. {code}
4. lỗi: `ValidationError` từ pydantic nếu normalizer cho giá trị ngoài enum. {code}
5. config: không. {code}
6. ai gọi: nhánh `except ExtractorFallback` của `run_intake`. {code}
7. invariant: đây là **cửa duy nhất** còn lại vào 2.381 dòng
   `rule_normalizer` + `rule_extractor`. Nó chỉ mở khi intaker ném
   `ExtractorFallback`, tức JSON không parse được. Toàn bộ phân tích ở
   `src.chat.routing` về hai file đó chỉ áp cho nhánh này. {code}
8. deprecated: không. {code}

### [x] `_rule_conf` (hàm lồng trong `run_intake`)
1. in/out: dựng `ExtractionConfidence` bằng `rule_extractor.extract_with_confidence`. {code}
2. side effect: chạy regex + fuzzy. {code}
3. state: closure. {code}
4. lỗi: không. {code}
5. config: ngưỡng fuzzy mặc định của `extract_with_confidence`. {code}
6. ai gọi: cùng nhánh với `_rule_user`. {code}
7. invariant: gọi **song song** với `_rule_user`, nghĩa là toàn bộ extractor
   regex chạy **hai lượt** trên cùng văn bản ở nhánh fallback — một lượt cho
   `UserInput`, một lượt cho `ExtractionConfidence`. Docstring của
   `rule_extractor` thừa nhận thiết kế "gọi lại chính extractor cũ". Chi phí gấp
   đôi chỉ xuất hiện khi intaker đã hỏng, tức lúc hệ đang chậm sẵn. {code}
8. deprecated: không. {code}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — `teencode_replaced` luôn rỗng và vẫn được ghi vào audit DB.**
`preprocess.prepare_user_text:70` gán cứng `[]`; giá trị đi qua
`IntakeResult.teencode_replaced` vào `AuditEntry` và xuống cột
`audit_log.teencode_replaced` dưới dạng `"[]"` cho mọi bản ghi. Comment `:53-56`
giải thích vì sao bảng teencode bị xoá (train/serve skew) nhưng không dọn trường.
Xoá được cả trường lẫn cột. {code}

**Q-02 — repo có hai hàm bỏ dấu, và một trong hai bỏ sót chữ `đ`.**
`preprocess.strip_accents` NFD-tách dấu **rồi** `replace("đ","d")`;
`utils/retrieval_query._no_accent` **thiếu** bước sau. Đo:
`strip_accents("da đầu")` → `"da dau"`, `_no_accent("da đầu")` → `"da đau"`.
Hệ quả đo được: `retrieval_query._NEG_CUES` viết bằng ASCII nên cue `"đừng dùng"`
không khớp nổi văn bản đã qua `_no_accent`. Thử 8 câu phủ định — 7 khớp,
`"đừng dùng BHA"` **không khớp cue nào**. Sửa một dòng: dùng chung
`preprocess.strip_accents`. (Đây là bổ sung cho `src.utils`; tôi đã ghi chú
chéo vào file đó.) {code}

**Q-03 — `_intent_patch._demo` không nằm trong suite test.**
8 assert bảo vệ đúng ranh giới an toàn quan trọng nhất của module (chỉ `clarify`
được sửa), nhưng chúng chỉ chạy khi `python -m ...` trực tiếp. `pytest` không
thấy. Đổi tên file thành `tests/test_intent_patch.py` hoặc thêm một wrapper là
xong. {code}

**Q-04 — hai field an toàn nhất bị bỏ khỏi cơ chế hedging confidence.**
`confidence_hint._OVERALL_WEIGHTS` có 10 field và **không** có `products`/
`medications`; vòng lặp `build_confidence_hint:86-90` cũng duyệt đúng 10 tên đó.
Nhưng `_FIELD_LABELS_VI` **có** nhãn cho cả hai (`"sản phẩm đang dùng"`,
`"thuốc đang dùng"`) — hai nhãn không bao giờ in được. Đó là bằng chứng việc bỏ
sót chứ không phải quyết định. Hậu quả: extractor trích sai tên thuốc với
confidence thấp mà prompt **không** được cảnh báo, trong khi chính hai trường đó
nuôi `medication_safety_refusal`. {code}

**Q-05 — lệch runtime↔eval: đây là nguyên nhân cơ học, đã truy tới dòng.**
`orchestrator` là đường chuẩn bị **duy nhất** (lời khai đúng), nhưng bước **sinh**
tách đôi:
- production: `runtime.stream_chat_sse` → `c.llm.stream_text(...)`, và `:162`
  đặt `num_predict=-1` cho intent `knowledge` (không giới hạn độ dài);
- eval/CLI: `orchestrator.generate_prose` → `c.llm.generate_text(...)`, hàm này
  **không có tham số `num_predict`** (`ollama_backend.py:222-224`), nên bị chặn
  ở `settings.llm_num_predict = 2048`.

Thêm hai lệch phụ cùng nguồn: (a) `normalize_generated_prose` (cắt ký tự CJK)
chỉ chạy ở đường non-stream — grep trong `runtime.py` = 0, nên ký tự Hán bị cắt
khi eval nhưng **lọt tới người dùng thật**; (b) `runtime:228-229` gỡ cờ
`urgency_red_flag` cho intent `knowledge` trước khi gọi `get_safety_suffix`,
đường eval không có bước đó. Ba lệch này phải được nêu trong chương đánh giá,
hoặc sửa trước khi chạy full eval. Cách sửa rẻ nhất cho (a): thêm `num_predict`
vào `generate_text` (một dòng, `_sampling_options` đã nhận sẵn). {code}

**Q-06 — `_DOSE_RE` dùng `[^\n]{0,90}` trong khi output có xuống dòng.**
Model trả lời dạng Markdown bullet, tên thuốc và liều thường nằm hai dòng. Đo ở
phiên trước: chỉ **3/38** câu bị đánh dấu sai an toàn khớp được regex này. Sửa:
đổi `[^\n]` thành `[\s\S]` và giảm cửa sổ, hoặc chuẩn hoá xuống dòng trước khi
hậu kiểm. {code}

**Q-07 — cảnh báo khẩn cấp sống được nhờ một mệnh đề `or not _rf`.**
`_safety:~320`: `"urgency_red_flag" in route_flags and ((_rf & _EMERGENCY_FLAGS)
or not _rf)`. Vì `red_flags_input` **luôn rỗng** trên đường unified (Q-15),
`_rf & _EMERGENCY_FLAGS` luôn rỗng, và chỉ `not _rf` giữ cho nhánh này chạy. Nếu
ai đó "dọn" mệnh đề trông thừa ấy, cảnh báo khẩn cấp chết hoàn toàn ở production
mà mọi test dùng dữ liệu rule vẫn xanh. {code}

**Q-08 — ba bản sao `_extract_json` và hai bản `rrf_fusion`.**
`_intake_parse._extract_json` ≡ `llm_router._extract_json` (khác kiểu ngoại lệ);
`_retrieval.rrf_fusion` ≡ `rag/retriever.rrf_fusion` (giống từng dòng). Sửa công
thức RRF ở một chỗ thì chỗ kia lệch im lặng. {code}

**Q-09 — ĐÍNH CHÍNH `src.rag` Q-08: hậu quả tôi lo KHÔNG xảy ra.**
Ở `src.rag` tôi viết rằng điểm RRF (~0,016–0,052) nằm dưới mọi ngưỡng hạ nguồn
(`chat_min_chunk_score=0.25`, `chat_rerank_floor=0.50`) và kết luận đó là vấn đề
lớn nhất `src.rag` để lại. Đọc `_retrieval.py` cho thấy **hai** cơ chế chặn hậu
quả đó:
1. `merge_retrieval_outputs:48` **chuẩn hoá lại** `score / max_score` → `[0,1]`,
   và guideline pass chạy cho **mọi** truy vấn nên output luôn đi qua đó;
2. `_noise_filter` kết thúc bằng `return (after_noise if ... and
   after_noise.chunks else output)` — lọc mà rỗng thì **trả bản chưa lọc**.

Nghĩa là ngưỡng 0.25 không thể xoá sạch pool. Quan sát về **bốn thang điểm** cùng
chảy vào một trường `score` vẫn đúng và vẫn đáng sửa (nó khiến `avg_score` không
so được giữa các nhánh), nhưng mức nghiêm trọng phải hạ từ "lỗi" xuống "nợ thiết
kế". Tôi đã ghi đính chính này vào `src.rag.md`. {code}

**Q-10 — mọi báo cáo eval sinh trước lần sửa sigmoid đều mang nhãn evidence sai.**
`compute_evidence_quality` docstring ghi rõ: ngưỡng cũ 0.65/0.40 được chỉnh khi
reranker còn sigmoid **hai lần**, dải điểm bị nén vào `[0.500, 0.731]`; trên dải
đó 0.40 không bao giờ đạt tới nên nhãn `"weak"` là code chết và gần như mọi câu
trả lời được gắn "bằng chứng tốt". Với khoá luận: bất kỳ số liệu evidence_quality
nào trong `research/evaluation/reports/` sinh trước commit sửa sigmoid đều không
dùng được. Cần đối chiếu ngày commit với ngày các report khi duyệt
`research/evaluation/`. {code}

**Q-11 — hợp đồng JSON chính thức không được ép ở đường production.**
`_OLLAMA_JSON_SCHEMA` (schema đầy đủ) chỉ dùng bởi `llm_extractor` — đường
legacy. `unified_intake._infer:116` gọi `response_format="json"` (JSON mode
chung), với comment giải thích llama.cpp không parse nổi `anyOf`-null lồng nhau.
Nên ở production, toàn bộ việc bảo vệ hợp đồng do các parser khoan dung làm, và
chúng **drop im lặng**: enum bịa → `unknown`, item sai kiểu → biến mất, không log
nào. Không có cách nào đo được model sai hợp đồng bao nhiêu lần. Đề xuất rẻ:
đếm số field bị drop mỗi lượt và ghi vào `log_pipeline_stage("EXTRACT", ...)`. {code}

**Q-12 — tham số `prefix` chết xuyên 6 hàm của `_intake_parse`.**
`_scalar_node`, `_list_nodes`, `_enum_fr`, `_int_fr`, `_bool_fr`, `_lfr` đều nhận
`prefix` và không hàm nào đọc. Dấu vết của cơ chế báo lỗi theo đường dẫn field đã
gỡ. Cùng với Q-11 thì đây là gợi ý: `prefix` từng phục vụ đúng việc mà Q-11 đang
thiếu. {code}

**Q-13 — `is_pregnant` mất trạng thái thứ ba ngay tại `_to_user_input`.**
`_bool_fr` giữ được ba trạng thái (True/False/không rõ), nhưng `:~324`
`is_pregnant = bool(pregnant.value)` ép về hai, vì `UserContext.is_pregnant` khai
`bool` chứ không `bool | None`. Nên "không nhắc tới" và "nói rõ là không" không
phân biệt được ở tầng schema. Đây là **cùng một khiếm khuyết** với đường rule
(`src.chat.routing` Q-19) nhưng nguyên nhân khác: ở kia là regex phủ định không
phạm vi, ở đây là kiểu dữ liệu. Sửa triệt để phải đổi schema. {code}

**Q-14 — `_lfr` không hạ chữ ở đúng những field dễ trùng nhất.**
Khi `allowed` là None (allergies, products, medications, scarring_signs,
hormonal_factors, treatment_goals) thì dedupe phân biệt hoa-thường, nên `"BHA"`
và `"bha"` thành hai mục. Ba trong sáu field đó đi thẳng vào
`confirmed_profile` và vào cổng thuốc. {code}

**Q-15 — đường production chỉ điền 3/12 trường lâm sàng.**
Đếm bằng `ast`: `AcneClinicalInput` có **12** trường; `_to_user_input` truyền
**6**; và system prompt của intaker quy định `clinical` chỉ gồm **3**
(`lesion_types`, `inflammation_level`, `lesion_distribution`). Sáu trường không
được truyền: `medication_history`, `skincare_products`, `canonical_ingredients`,
`usage_frequencies`, `concentrations`, `red_flags_input`.

Hậu quả dây chuyền, tất cả đều đo được bằng grep:
- `red_flags_input` rỗng → nhánh `urgent_personal_case` (confidence 0.92) của
  `_rule_decision` không bao giờ chạy; bản vá "BUG FIX" ở `intake.py:~676` vô
  tác dụng; cảnh báo khẩn ở `_safety` chỉ sống nhờ `or not _rf` (Q-07).
- `canonical_ingredients` và `medication_history` rỗng → hai vòng lặp cuối của
  `_extract_safety_terms` chết.
- `usage_frequencies`, `concentrations` rỗng → `extracted_entities_from_user`
  ghi khoá rỗng vào audit log mọi bản ghi.
- `fold_history_facts` gộp 12 trường, trong đó 6 luôn rỗng.

Đây là **phát hiện cấu trúc lớn nhất** của module. Cần một quyết định rõ trong
báo cáo: hoặc thu `AcneClinicalInput` về đúng 3 trường mà hệ thật dùng, hoặc mở
rộng prompt intaker để sinh đủ. Trạng thái hiện tại — schema hứa 12, hệ dùng 3 —
là thứ giám khảo sẽ hỏi. {code}

**Q-16 — hai bản system prompt của intaker phải đồng bộ bằng tay.**
`unified_intake._RUNTIME_SYSTEM` và `model/intaker/Modelfile` SYSTEM hiện **giống
hệt** (3.322 ký tự, sha256 `6ee28283b579feb8`), nhưng không có gì canh. Vì
`use_modelfile_system=True`, bản Python **không** được gửi — nên nếu ai sửa nó,
hành vi không đổi và không ai biết là đã lệch. Một test 3 dòng so sha256 là đủ. {code}

**Q-17 — prompt nói 3 lượt lịch sử, code gửi 6.**
`_RUNTIME_SYSTEM` mở đầu: "Đọc turn hiện tại và tối đa **3** turn lịch sử gần
nhất". `_MAX_HISTORY_TURNS = HISTORY_WINDOW_TURNS = 6`. Hai adapter legacy thì
đúng 3 (`[-3:]`). Nếu tập fine-tune chỉ có mẫu ≤ 3 lượt thì đây là train/serve
skew. Ngoài ra `_build_user_prompt` dùng **hai định dạng** (nguyên văn khi không
có lịch sử, bọc `FOLLOWUP_HISTORY_JSON` khi có) — cần kiểm tập train có cả hai
không. Cả hai câu hỏi thuộc phần kiểm kê `research/datagen/intakedata`. {code}

**Q-18 — snapshot chỉ được lưu cho lượt `advise`, và `_intent_patch` phụ thuộc
điều đó.** `runtime._snapshot_for_persistence` trả None trừ khi
`primary_intent == "advise"`. `_has_established_case` chỉ thấy lượt có snapshot.
`_intent_patch` nâng `clarify` → `advise` **dựa trên** `_has_established_case`.
Nên một phiên mở đầu bằng `clarify` không bao giờ tích được ca bệnh để tự thoát
khỏi `clarify` — trừ khi có một lượt `advise` xen vào. Vòng phụ thuộc này không
được ghi ở đâu và đáng kiểm bằng một test hội thoại nhiều lượt. {code}

**Q-19 — tham số chết, tổng hợp toàn `chat/`.**
`_resolve_mode(clean_text, history)` — 2 tham số, được người gọi tính rồi truyền;
`_intake_parse` `prefix` — 6 hàm (Q-12); `_to_extraction_confidence(clean_text)`;
`rule_extractor._context_adjust(span_hint)` và `_scalar(fallback_methods)`;
`intent_router.select_relevant_history(message, route_flags)` — 2/4.
Tổng **13 tham số chết** trong `chat/`. Không cái nào gây lỗi; cùng nhau chúng
làm chữ ký hàm nói dối về thứ hàm thực sự dùng, và đó là thứ người đọc code
(giám khảo) sẽ tin. Ngoại lệ đáng khen: `UnifiedIntake.run` viết
`del clean_text_no_accent` ngay dòng đầu — tham số chết **có khai báo**. {code}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **141**.
- Tiêu đề `### [x]` đếm được: **123**. Chênh lệch do **hai tiêu đề gộp**, mỗi cái
  ghi rõ số khối nó phủ ngay trong tiêu đề:
  - `_safety.py` — **10 bảng term** dưới 1 tiêu đề → +9
  - `_intake_parse.py` — **10 hằng enum** dưới 1 tiêu đề → +9
  - Kiểm: 123 + 9 + 9 = **141**. Khớp.
- Mục: 141 × 8 = **1.128**. Trong đó 20 khối thuộc hai nhóm nén có khai báo
  (20 × 4 = 80 mục phát biểu chung trong hai tiêu đề gộp, 20 × 4 = 80 mục khai
  riêng ở cùng chỗ), 121 khối còn lại viết đủ 8 mục tại chỗ (968 mục).
  Kiểm: 80 + 80 + 968 = **1.128**. Khớp.

**Năm khẳng định đo bằng chạy thật, không đọc mắt:**
1. `preprocess_user_text("em dùng BT-Cortin")` → không đổi;
   `"BT_Cortin"` → `"BT Cortin"` — bác bỏ lời khai trong docstring
   `prepare_user_text` (khối `_WORD_JOINER_RE`).
2. `strip_accents("da đầu")` = `"da dau"` vs `_no_accent("da đầu")` = `"da đau"`;
   và 8 câu phủ định thử với `_NEG_CUES`, `"đừng dùng BHA"` không khớp cue nào (Q-02).
3. So sha256 `model/intaker/Modelfile` SYSTEM với
   `unified_intake._RUNTIME_SYSTEM`: **bằng nhau** (`6ee28283b579feb8`) — điều
   này **bác bỏ** cách tôi viết Q-02 ban đầu ở `src.chat.routing.md`, đã sửa lại
   file đó.
4. Đếm bằng `ast`: `AcneClinicalInput` 12 trường, `_to_user_input` truyền 6,
   liệt kê đủ 6 trường không truyền (Q-15).
5. `grep normalize_generated_prose runtime.py` = 0 → bộ lọc CJK không chạy ở
   đường SSE (Q-05).

**Ba lần tôi định ghi một khẳng định rồi tự bác bỏ trước khi chốt:**
- `get_safety_suffix(recent_turns, current_turn_text)` — tôi định ghi là tham số
  chết; `runtime.py:238-239` có truyền và thân hàm có dùng. Đã sửa tại chỗ.
- `src.rag` Q-08 — tôi đã ghi là vấn đề lớn nhất; `_retrieval` cho thấy hai cơ
  chế chặn hậu quả. Đã hạ mức và ghi đính chính (Q-09).
- `src.chat.routing` Q-02 — tôi đã ghi "prompt không tới model" như một lỗi;
  đối chiếu Modelfile cho thấy đó là thiết kế đúng. Đã sửa file đó.
