# Code chết — danh sách đã xác minh từng dòng

Cách kiểm: đếm mọi tham chiếu tới tên hàm/class trong `src/`, `tests/`,
`evaluation/`, `scripts/`, `ablation/`, `datagen/`, trừ đi chính dòng `def`/
`class`. Thứ nào còn tham chiếu thì tham chiếu đó được mở ra đọc xem là lời gọi
thật hay chỉ là chuỗi trong log/comment.

**Tổng: 1.423 dòng / 17.440 dòng `src/` = 8,2%.**

Chia làm ba nhóm theo mức độ cần suy nghĩ trước khi xoá.

---

## NHÓM 1 — xoá thẳng, không cần cân nhắc (584 dòng)

Không có caller nào, kể cả trong test, và không mang theo luật nghiệp vụ nào.

### `llm/qa_generator.py` — cả file, 328 dòng

Hai class `QAGenerator` (110-204) và `OllamaQAGenerator` (215-290). **Zero tham
chiếu trong toàn repo**, kể cả test. Đây là tàn dư của thời sinh cặp Q&A từ chunk
để làm dữ liệu fine-tune; việc đó giờ nằm ở `datagen/` và `LLMData/chunk_qa/`.
Cả file là bản sao cũ của một quy trình đã chuyển nhà.

### `rag/retriever.py` — ba hàm, 115 dòng

| Hàm | Dòng | Vì sao chết |
|---|---|---|
| `mmr_select` | 85-122 | chỉ được `retrieve_with_mmr` gọi |
| `retrieve_with_mmr` | 276-289 | không ai gọi |
| `expand_context` | 291-353 | không ai gọi (hai tham chiếu còn lại là chuỗi trong `logger.debug`) |

Đường chạy thật ở `chat/_retrieval.py` chỉ dùng `retrieve()` và
`retrieve_safety_pass()`. Ba hàm này là hai ý tưởng cải thiện RAG — đa dạng hoá
bằng MMR, và mở rộng ngữ cảnh sang chunk kề — được viết xong rồi không nối vào
pipeline. Xoá `mmr_select` thì `import numpy as np` ở dòng 8 cũng đi theo, vì
numpy chỉ được dùng ở đúng ba dòng 100/102/115 bên trong nó.

### Năm file Protocol một-implementation, 27 dòng

`llm/base.py` (7), `rag/base.py` (6), `pipeline/base.py` (6) +
`pipeline/__init__.py` (0), `crawler/base.py` (8).

Không file nào được import, không `isinstance` nào kiểm tra chúng, không type
hint nào dùng chúng. Đây là interface được định nghĩa trước cho một tương lai có
nhiều implementation — tương lai đó không tới, và mỗi implementation vẫn chỉ có
đúng một. Riêng `pipeline/` là một package trống hoàn toàn sau khi bỏ `base.py`.

### `vision/`, 21 dòng + 3 dòng nối dây

`vision/base.py` (6), `vision/mock.py` (15), `vision/__init__.py` (0).
`MockVision` được `di.py` khởi tạo (dòng 21, 339) và gán vào `Container.vision`
(dòng 54) — nhưng **không dòng nào trong repo đọc `c.vision`**, và phương thức
`analyze()` có zero tham chiếu. Đây là chỗ cắm cho tính năng phân tích ảnh da
chưa làm. Giữ một field rỗng trong container để nhắc mình về nó thì không hiệu
quả bằng một dòng trong README.

### Vụn, 93 dòng

| Thứ | Vị trí | Dòng | Ghi chú |
|---|---|---|---|
| `build_retrieval_query` | `utils/retrieval_query.py:69-112` | 44 | bản cũ của `build_current_turn_query`; chỉ bản mới được gọi |
| `invalidate_retrieve_cache` | `cache.py:139-154` | 16 | viết để gọi sau khi rebuild KB, nhưng `scripts/build_kb.py` không gọi |
| `clear_all_caches` | `cache.py:157-166` | 10 | như trên |
| `show_params` | `ollama_backend.py:189-206` | 18 | viết để verify Modelfile có override config không; docstring bảo "gọi lúc boot và log ra" — `di.py` không gọi |
| `_sigmoid` | `reranker.py:12-16` | 5 | tàn dư của bug sigmoid-hai-lần đã sửa; comment dòng 92-100 giải thích rất kỹ vì sao không dùng nữa, rồi để hàm lại |

---

## NHÓM 2 — xoá được, nhưng phải quyết một chuyện nhỏ (344 dòng)

### Endpoint WebSocket `/ws/chat`, 89 dòng

`api/routes/chat.py:220-296` (`chat_ws`) + `205-216` (`_parse_sse_frame`).

`frontend/src/lib/api.ts:16` là nơi duy nhất frontend dựng URL, và nó dựng
`/chat/stream`. Không client nào gọi `/ws/chat`.

Trớ trêu là đây lại là đoạn code phức tạp nhất trong file: một `asyncio.Queue`
maxsize 64 làm cầu nối giữa sync generator chạy trong thread và async
WebSocket sender, cộng sentinel object, cộng `run_coroutine_threadsafe(...).result()`
cho mỗi token. Comment ở dòng 253-257 kể lại cả một lần sửa bug buffer. Toàn bộ
công đó phục vụ zero request.

**Quyết định cần đưa:** bạn có định làm client WebSocket sau này không. Nếu có,
giữ lại nhưng đánh dấu rõ. Nếu không, `git rm` — lịch sử git vẫn còn nếu cần
lấy lại.

### `SessionStore` in-memory, 177 dòng

`chat/session.py:103-279`. Production dùng `SQLiteSessionStore`
(`db/session_store.py`), và tôi đã kiểm: **`SQLiteSessionStore` không kế thừa
`SessionStore`** — dòng 62 là `class SQLiteSessionStore:` trần. Hai
implementation song song, không chung interface, chỉ chung tên phương thức.

Bản in-memory chỉ còn sống qua `get_session_store()`, được gọi ở
`runtime.py:87` và `intake.py:265` dưới dạng
`getattr(c, "session_store", None) or get_session_store()`. Vì `build_container`
**luôn** set `session_store`, vế phải chưa từng chạy trong production. Nó chỉ
phục vụ `tests/test_session.py`.

**Quyết định cần đưa:** đây là fallback an toàn hay là hai nguồn sự thật? Tôi
nghiêng về vế sau — hai store không chung base class nghĩa là chúng có thể lệch
hành vi mà không ai phát hiện, và đã lệch rồi: `SessionStore.append_turn` tự
populate `intent_label` từ metadata, bản SQLite có làm thế không thì phải mở ra
đọc mới biết. Bỏ fallback, để `get_session_store()` chết theo, và nếu test cần
store nhẹ thì dùng SQLite in-memory (`:memory:`).

### `get_asked_fields` / `mark_fields_asked`, 31 dòng

`db/session_store.py:284-295` và `297-315` (bản trong `SessionStore` đã nằm
trong 177 dòng ở trên). Zero caller trong `src/`, chỉ có
`tests/test_sqlite_session_store.py`.

Chúng từng phục vụ cơ chế "đừng hỏi lại field đã hỏi rồi". `runtime.py:245-249`
ghi rõ lý do bỏ: *"khong can `asked_fields` nua: model doc duoc luot truoc no da
hoi gi"*. Cơ chế bị gỡ, hai phương thức và cột dữ liệu ở lại.

**Quyết định cần đưa:** có xoá luôn cột trong schema SQLite không, hay để đó vì
migration phiền. Để cột lại cũng được, nhưng phương thức thì nên đi.

### Ba helper trong `chat/intake.py`, 47 dòng

| Hàm | Dòng | |
|---|---|---|
| `_has_clinical_data` | 152-165 | 14 |
| `_snapshot_has_values` | 168-190 | 23 |
| `_is_intake_reply` | 193-202 | 10 |

`_has_clinical_data` và `_is_intake_reply` có zero tham chiếu.
`_snapshot_has_values` còn đúng một caller là `_has_established_case`
(intake.py:205) — mà `_has_established_case` chính là điều kiện gác của bản vá
`_intent_patch`. Nên nếu bạn sửa `_has_established_case` theo mục 3.1 của bản
audit runtime, cân nhắc luôn chuỗi này.

**Quyết định cần đưa:** xoá hai hàm chắc chắn chết trước, để
`_snapshot_has_values` lại cho tới khi giải quyết xong `_intent_patch`.

---

## NHÓM 3 — 495 dòng, nhưng KHÔNG được xoá mù (đọc kỹ)

Đây là nhóm lớn thứ hai và cũng là nhóm duy nhất mang theo luật an toàn y khoa.

### `post_check` và chín hàm `_apply_*`, 251 dòng

`guardrails/runner.py:573-832`:

| Hàm | Dòng | Luật nó thực thi |
|---|---|---|
| `post_check` | 573-582 | điều phối 8 hàm dưới |
| `_apply_drug_checker` | 584-610 | biến cảnh báo từ `drugs_acne.yaml` + OpenFDA thành red flag |
| `_apply_retinoid_blocks` | 612-647 | thai kỳ/cho bú → viết lại mọi khuyến nghị có retinoid |
| `_apply_severe_doctor` | 649-673 | severity=severe mà chưa khuyên gặp bác sĩ → chèn thêm |
| `_apply_age_restriction` | 675-699 | tuổi <12 → chèn khuyến nghị khám nhi |
| `_apply_no_popping` | 701-717 | **lọc bỏ** mọi khuyến nghị tự nặn/tự peel/tự lăn kim |
| `_apply_medication_safety` | 719-794 | chặn liều cụ thể, chặn kháng sinh đơn trị liệu |
| `_apply_medication_allergy_redflag` | 796-818 | đang dùng thuốc/dị ứng + có khuyến nghị thuốc → red flag |
| `_ensure_disclaimer` | 820-826 | ép có disclaimer |
| `_find_rule_keywords` | 828-832 | helper đọc `guardrails.yaml`, chỉ `_apply_retinoid_blocks` dùng |

Trong `src/` chỉ còn đúng hai tham chiếu tới cái tên `post_check`, và cả hai là
chuỗi văn bản: một comment ở `runtime.py:220` và một chuỗi log ở `runner.py:609`.
Test thì gọi thật — `tests/test_guardrails.py` có 6 chỗ.

**Vì sao nó chết.** Cả nhóm này nhận vào một `AdviseOutput` — object có
`recommendations: list[Recommendation]`, `red_flags`, `severity`. Khi output
chuyển sang prose streaming, không còn object nào để đưa vào. `runtime.py:219`
ghi thẳng: *"Streaming text is not an AdviseOutput, so avoid constructing a dummy
object for post_check"*. Quyết định đúng — dựng object giả để chạy qua một tầng
kiểm tra là tệ hơn.

**Vì sao không được xoá mù.** Bảy luật trên không tự bốc hơi khi output đổi
dạng; chúng chỉ mất chỗ chạy. Bản thay thế là `chat/_safety.py::get_safety_suffix`
— nhưng nó **không phủ hết**. Đối chiếu:

| Luật | Còn ở `get_safety_suffix`? |
|---|---|
| retinoid + thai kỳ | ✅ dòng 212-239 |
| thuốc kê đơn | ✅ dòng 242-257 |
| tuổi <12 | ✅ dòng 260-270 |
| tự nặn/tự thủ thuật | ✅ dòng 311-314 (`_SELF_PROCEDURE_TERMS`) |
| severity=severe → gặp bác sĩ | ⚠️ chỉ khi có cờ `urgency_red_flag` |
| **kháng sinh đơn trị liệu** | ❌ **không có** |
| **liều cụ thể trong câu trả lời** (`dose_re`, dòng 734-740) | ❌ **không có** |
| **tương tác chéo từ DrugChecker** | ❌ chỉ còn ở `medication_safety_refusal` (chặn trước khi sinh), không kiểm tra text đã sinh |

Ba dòng ❌ nghĩa là: nếu model viết ra "uống doxycycline 100mg mỗi ngày" mà không
kèm chữ "bác sĩ", hiện **không có tầng nào bắt được**. `_apply_medication_safety`
có regex đúng cho việc đó (dòng 734-746) và nó đang nằm trong đống code chết.

**Việc phải làm trước khi xoá:** port ba luật đó sang `get_safety_suffix` dưới
dạng kiểm tra trên text (`full_text`), viết test cho từng luật, chạy xanh, **rồi**
mới xoá 251 dòng. Đây là nửa buổi làm việc, không phải một lệnh `git rm`.

### `scope_check` + `_scope_refusal_if_out_of_scope`, 115 dòng

`runner.py:436-472` và `357-434`. Tham chiếu duy nhất trong `src/` là một comment
ở `intake.py:272`. Test gọi 9 lần.

Chết vì `SemanticRouter` thay thế: `di.py:229` ghi *"Soft OOS moved to
SemanticRouter"*. Việc quyết một câu có ngoài phạm vi hay không giờ do khoảng
cách nearest-neighbor của router quyết, không còn do keyword.

Ở đây không có luật y khoa nào bị mất — chỉ là câu từ chối "ngoài phạm vi tư
vấn da mụn", mà `intake.py` đã tự dựng bản riêng của nó (dòng 409-424 cho
genital, 335-350 cho pre_check). Xoá được, nhưng kiểm lại `guardrails_scope_mode`
trong `config.py:171` — setting đó chỉ còn điều khiển code chết, nên nó cũng nên
đi theo.

### `OodDetector`, 129 dòng

`guardrails/ood_detector.py:106-234`. Class này chết vì một dòng cấu hình:
`di.py:230` truyền `enable_ood=False`, nên `self._ood` **luôn** là `None` và
nhánh "Tầng 2 — embedding OOD check" ở `runner.py:397-416` chưa từng thực thi
một lần nào trong production.

Cẩn thận: file `ood_detector.py` còn chứa `contains_pii` và `mask_pii` — **hai
hàm này đang sống và được gọi mỗi request** (`intake.py` 6 chỗ, `runtime.py:282`).
Xoá class, không xoá file. Kéo theo được: `config/ood_centroid.json` và tham số
`ood_threshold`/`centroid_path` trong constructor `GuardrailRunner`.

---

## Thứ tự làm

1. **Nhóm 1** (584 dòng) — một PR, một buổi sáng, không cần suy nghĩ. Chạy
   `pytest -q` trước và sau, số test pass phải giữ nguyên (trừ test của chính
   code bị xoá — xoá luôn, test cho code chết là lý do code chết sống lâu).
2. **Nhóm 2** (344 dòng) — bốn quyết định nhỏ đã nêu, mỗi cái một commit.
3. **Nhóm 3** (495 dòng) — port ba luật an toàn trước, có test, rồi mới xoá.
   Đừng gộp bước port và bước xoá vào cùng một commit.

Sau cả ba: `src/` từ 17.440 xuống ~16.000 dòng, và ba file bạn mở nhiều nhất
gọn hẳn — `runner.py` 832→466, `retriever.py` 447→332, `chat.py` 326→237
(hoặc 88 nếu bỏ luôn `/debug/trace`).

---

## Hai thứ tôi từng liệt kê nhầm — đã kiểm lại

- **Teencode KHÔNG chết.** `expand_teencode_for_retrieval` được
  `utils/retrieval_query.py:124` gọi trong `build_current_turn_query`, tức là
  đang chạy thật trên đường retrieval để BM25 khớp được "ko"/"vs". Chỉ có trường
  `teencode_replaced` là luôn rỗng (`preprocess.py:77` hardcode `[]`) mà vẫn được
  mang qua 17 chỗ trong `intake.py` → `AuditEntry` → một cột SQLite. Dữ liệu
  chết chứ không phải cơ chế chết. Sửa: bỏ trường, giữ hàm.
- **Năm hàm trong `rule_normalizer.py` KHÔNG chết.** `_extract_acne_count` được
  gọi ở dòng 1725, `_extract_concentrations` ở 1915, `_extract_usage_frequencies`
  ở 1913, `_acne_resolved` ở 1883, `_has_product_use_context` ở 1320. Script AST
  của tôi đếm sai vì không phân biệt được lời gọi trong thân hàm khác. Bỏ khỏi
  danh sách.
