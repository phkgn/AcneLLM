# Audit runtime: từ input user đến output LLM

Phạm vi: đường chạy thật của một request `/api/v1/chat/stream` với cấu hình
`.env` hiện tại (`INTAKE_MODE=unified`, `DEVICE=cpu`). Không đọc code crawler/
datagen/eval trừ khi nó nằm trên đường chạy.

---

## 1. Đường đi thật của một lượt chat

```
GET /api/v1/chat/stream?message=...
  └─ 3 lớp BaseHTTPMiddleware (RateLimit → APIKey → RequestLogging)
     └─ routes/chat.py: validate chars/words          (regex nhẹ)
        └─ runtime.stream_chat_sse  (sync generator, chạy trong threadpool)
           └─ orchestrator.prepare_chat_turn
              ├─ intake.run_intake
              │   ├─ prepare_user_text          NFC + strip_accents
              │   ├─ guardrails.pre_check       ~264 cụm injection + PII regex
              │   ├─ _is_acne_scope             quét 420 term
              │   ├─ _is_genital_scope          quét 40 term
              │   ├─ medication_safety_refusal  YAML drug checker
              │   ├─ ★ UnifiedIntake.classify   ── LLM #1 (acne-intaker, JSON)
              │   ├─ compute_route_flags        quét ~8 bảng term
              │   ├─ ★ UnifiedIntake.run        ── cache hit của LLM #1
              │   ├─ pre_check lần 2 + medication_safety lần 2
              │   ├─ build_confirmed_profile + fold_history_facts
              │   └─ medication_safety lần 3
              ├─ retrieve_for_chat  (cache DiskCache TTL 1h)
              │   ├─ ★ embed_query               ── Vietnamese_Embedding, CPU
              │   ├─ Chroma dense (fetch 75) + BM25 (fetch 75) → RRF → top 25
              │   ├─ ★ guideline pass            ── embed + Chroma lần 2 (MỌI query)
              │   ├─ ★ safety pass               ── embed + Chroma lần 3 (có điều kiện)
              │   ├─ ★ reranker.rerank           ── cross-encoder ~30-35 cặp, CPU
              │   ├─ cap_per_source → OOD guard → 3 bộ lọc keyword → guideline slot
              │   └─ → 5 chunk
              └─ prompt.build (Jinja2, sanitize)
           ├─ ★ llm.stream_text                  ── LLM #2 (acne-generator)
           ├─ get_safety_suffix                  quét ~10 bảng term trên output
           ├─ session.append_turn ×2 (SQLite)
           └─ audit.log (SQLite)
```

Năm dấu ★ chiếm gần như toàn bộ latency, và chúng chạy **tuần tự tuyệt đối**.
Mọi thứ còn lại — 420 term quét ba lần, sáu lần `contains_pii`, ba lần
`_extract_safety_terms` — cộng lại vẫn ở mức mili-giây. Đừng tối ưu chúng; đó là
chỗ dễ nhìn thấy chứ không phải chỗ tốn tiền.

Điểm quan trọng nhất của sơ đồ này: **retrieval không bắt đầu được cho tới khi
intaker sinh xong JSON**, dù query dùng để retrieve gần như chỉ là `clean_text`.
Đó là một hàng đợi hai tầng model trên cùng một CPU.

---

## 2. Dead code — đã kiểm chứng bằng grep, không phải suy đoán

### 2.1 Cả một tầng guardrail hậu kiểm không bao giờ chạy

`GuardrailRunner.post_check` và toàn bộ bảy hàm `_apply_*` của nó
(`runner.py:573-826`, ~250 dòng) chỉ có caller trong `tests/`. Runtime nói thẳng
lý do ở `runtime.py:219`: "Streaming text is not an AdviseOutput, so avoid
constructing a dummy object for post_check". Khi output chuyển từ JSON có cấu
trúc sang prose streaming, tầng này mất chỗ bám và không ai xoá.

Hệ quả không chỉ là code chết. Các luật y khoa trong đó — chèn khuyến nghị gặp
bác sĩ khi `severity=severe`, chặn khuyến nghị tự nặn, viết lại khuyến nghị
retinoid cho thai phụ, cảnh báo dị ứng — **hiện chỉ còn tồn tại một phần** ở
`_safety.get_safety_suffix`. Suffix bắt được: retinoid+thai kỳ, thuốc kê đơn,
trẻ <12, red flag khẩn, đa bệnh, tự thủ thuật. Không bắt được: kháng sinh đơn
trị liệu, liều lượng cụ thể trong câu trả lời, tương tác chéo từ DrugChecker.
Nói cách khác, việc bỏ `post_check` đã âm thầm nới ba luật an toàn, và test vẫn
xanh vì test gọi thẳng `post_check`.

`scope_check` / `_scope_refusal_if_out_of_scope` (runner.py:357-472) cũng chỉ có
caller trong test. Kèm theo đó là tầng OOD embedding bên trong nó: `di.py:230`
truyền `enable_ood=False`, nên `self._ood` luôn `None` và nhánh "Tầng 2" chưa
từng thực thi một lần nào trong production. `OodDetector` (234 dòng) chết theo;
chỉ `contains_pii`/`mask_pii` cùng file là còn sống.

### 2.2 Endpoint WebSocket không có client

`frontend/src/lib/api.ts:16` chỉ dựng URL `/chat/stream`. `/ws/chat`
(`chat.py:219-296`, ~78 dòng gồm cầu nối `asyncio.Queue` giữa thread và event
loop, `_parse_sse_frame`, sentinel) không có caller nào ngoài test. Đây là đoạn
phức tạp nhất trong file route và nó phục vụ zero request.

### 2.3 Retrieval có ba hàm cao cấp không ai gọi

`mmr_select` (retriever.py:85), `retrieve_with_mmr` (:276), `expand_context`
(:291) — tổng ~100 dòng, kèm dependency numpy cho MMR. `_retrieval.py` gọi
thẳng `retrieve()` và `retrieve_safety_pass()`, không đụng ba hàm kia.

### 2.4 Teencode: bảng có, regex có, không ai gọi

`preprocess.expand_teencode_for_retrieval` + `_TEENCODE_MAP` + `_TEENCODE_RE`
không có caller. `prepare_user_text` trả `teencode_replaced=[]` cứng. Nhưng
trường rỗng đó vẫn được mang qua `IntakeResult` → `runtime` → `AuditEntry` →
một cột SQLite, mỗi request. Một đường dữ liệu hoàn chỉnh chở hằng số rỗng.

Cùng nhóm: `clean_text_no_accent` được `strip_accents` tính mỗi lượt, truyền vào
`UnifiedIntake.run()`, và dòng đầu tiên của hàm đó là `del clean_text_no_accent`.
Trên đường unified nó chỉ còn phục vụ `_has_allowed_acne_region` và fallback rule.

### 2.5 Phần còn lại (đã verify 0 caller)

| Thứ | Vị trí | Dòng |
|---|---|---|
| `QAGenerator`, `OllamaQAGenerator` | `llm/qa_generator.py` | 328 |
| `MockVision.analyze` + `vision/` | container giữ field, không ai đọc | ~25 |
| 5 Protocol một-implementation | `{llm,rag,pipeline,vision,crawler}/base.py` | ~30 |
| `Reranker._sigmoid` | `reranker.py:12` | 5 |
| `invalidate_retrieve_cache`, `clear_all_caches` | `cache.py` | ~25 |
| `OllamaBackend.show_params` | `ollama_backend.py:189` | 18 |
| `build_retrieval_query` | `utils/retrieval_query.py:69` | ~25 |
| `SessionStore` in-memory | `session.py:103-279` (prod dùng SQLite) | ~180 |
| `get_asked_fields` / `mark_fields_asked` | `session.py` + `db/session_store.py` | ~30 |
| `_is_intake_reply`, `_has_clinical_data`, `_snapshot_has_values` | `intake.py` | ~45 |
| `_extract_concentrations`, `_extract_usage_frequencies`, `_extract_acne_count` | `rule_normalizer.py` | ~60 |

Cộng lại khoảng **1.400–1.800 dòng xoá được mà không đổi một byte hành vi
production**. Trên tổng 17.4k dòng `src/`, đó là ~10%.

### 2.6 Không chết nhưng là gánh nặng lớn nhất

`chat/routing/rule_normalizer.py` — **1.975 dòng**, gấp đôi file lớn thứ hai.
Nó chỉ chạy khi intaker ném exception. Không đề nghị xoá (fallback an toàn là
đúng), nhưng cần biết: 11% codebase phục vụ nhánh lỗi, và nhánh đó gần như
không được đo. Nếu có metric "tỉ lệ fallback rule" mà nó < 1%, câu hỏi hợp lý
là thay 1.975 dòng regex bằng một fallback thẳng thắn hơn — trả `clarify` và
hỏi lại người dùng.

---

## 3. Rule tệ / logic đáng ngờ

### 3.1 `_contains_any` khớp chuỗi con, và bảng có term 2 ký tự

`runner.py:267`. Chỉ 6 term nằm trong `boundary_aliases` được khớp theo ranh
giới từ; 414 term còn lại dùng `term in text`. Trong bảng có `co` (cổ), `ma`
(má), `cam` (cằm), `mui`, `vai`, `dui`, `sua`, `ken`. Kết quả đo thật:

```
is_acne_scope_text("con chó nhà tôi bị ốm")  → True   (hit: "co" trong "con")
```

Bất kỳ câu nào chứa "con", "công", "cô", "mai", "mang" đều có thể lọt.

Hôm nay tác hại còn nhẹ vì `scope_decision` được set `in_scope` vô điều kiện sau
cổng genital, nên `acne_signal` gần như chỉ để ghi log. Nhưng nó **có** một
đường ảnh hưởng thật: `_has_established_case()` (intake.py:205) gọi
`_is_acne_scope(turn.content)` trên mọi user turn lịch sử. Với false positive
này, gần như mọi session có ≥1 lượt đều được coi là "đã có ca thật", nên bản vá
`_intent_patch` (clarify → advise) **kích hoạt rộng hơn nhiều so với phạm vi mà
docstring của nó tuyên bố**. Bản vá tự nhận là hẹp; điều kiện gác cổng của nó
thì không.

Sửa: một dòng, dùng ranh giới từ cho mọi term.

```python
# runner.py:267 — bỏ luôn boundary_aliases, áp cho tất cả
def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered) for term in terms
    )
```

Cần đo lại: `re.search` 420 lần/câu chậm hơn `in` 420 lần. Nếu thành vấn đề thì
gộp thành **một** regex `|`-join compile sẵn ở module level — cách này vừa đúng
vừa nhanh hơn cả bản hiện tại.

### 3.2 `compute_route_flags` bị gọi thiếu tham số

`intake.py:616` gọi `compute_route_flags(clean_text, history=history)` — bỏ
trống `user`. Bên trong (`intent_router.py:292`):

```python
has_red_flags = bool(user is not None and user.clinical and user.clinical.red_flags_input)
```

Nên `has_red_flags` **luôn False** trên đường chạy thật. Cờ `urgency_red_flag`
chỉ còn sinh ra từ khớp text `_URGENCY_TERMS`; mọi red flag mà intaker trích
được đều không kích hoạt cảnh báo khẩn ở `_safety`. Đây là bug thật, không phải
lựa chọn thiết kế — vị trí gọi nằm *trước* bước extraction nên `user` chưa tồn
tại. Sửa đúng: tính lại cờ sau extraction, hoặc chỉ merge thêm phần cờ phụ
thuộc clinical sau khi có `base_user`.

### 3.3 Ba lần gọi cổng thuốc, hai lần `pre_check`

`medication_safety_refusal` chạy ở intake.py:461 (current turn), :802 (sau
extract), :891 (sau fold). `pre_check` chạy ở :302 và :797. Có lý do được ghi
chú cho từng lần, và mỗi lần đều rẻ. Nhưng ba điểm return riêng biệt cùng dựng
lại một `IntakeResult` gần giống hệt nhau (mỗi khối ~25 dòng) khiến `run_intake`
phình lên 727 dòng với **6 điểm thoát**. Đây là chỗ dễ sinh bug nhất trong repo:
thêm một field vào `IntakeResult` là phải nhớ sửa 6 chỗ, và hiện đã có sự lệch —
ví dụ nhánh :675 (`reject`) trả `safety_terms=[]` và `history=[]` trong khi các
nhánh khác trả đủ.

### 3.4 Reject và clarify vẫn trả tiền một lần sinh đầy đủ

Khi intent = `reject`, runtime vẫn build prompt `reject_user.j2` và gọi
`llm.stream_text` với `num_predict=2048`. Câu trả lời "ngoài phạm vi tư vấn" đã
có sẵn dạng text cứng trong `scope_refusal.disclaimer`. Comment ở
orchestrator.py:113 giải thích lựa chọn này (guardrail quyết nội dung, generator
viết câu chữ) — hợp lý về chất lượng, nhưng nó nghĩa là **jailbreak và câu hỏi
lạc đề tốn đúng bằng một ca tư vấn thật**. Trên CPU đó là 20-40 giây cho một
câu từ chối. Đây cũng là bề mặt DoS rẻ nhất của hệ thống.

### 3.5 Cache một-ô của `UnifiedIntake` hỏng khi có đồng thời

`unified_intake.py:69` giữ `self._cache_key` / `self._cache_value` — **một ô
duy nhất, trên instance dùng chung cho mọi request**. Luồng bình thường:
`classify()` infer rồi ghi ô, `run()` đọc lại → 1 lần gọi model. Với hai request
song song, request B ghi đè ô giữa `classify()` và `run()` của A → A miss → gọi
intaker lần hai. Dưới tải, chi phí intake **gấp đôi một cách không xác định**.

Cách lười nhất và cũng đúng nhất: bỏ cache đi, cho `run_intake` gọi `_infer()`
một lần rồi tự dùng kết quả cho cả routing lẫn extraction. Cái cache này tồn tại
chỉ vì hai interface cũ (`classify`/`run`) được giữ nguyên hình dạng — nó đang
trả giá runtime cho một quyết định về hình dạng API nội bộ.

### 3.6 Hai bộ giá trị mặc định cho cùng một setting

`config.py` khai báo default, rồi code đọc bằng `getattr(settings, name, default)`
với default **khác**:

| Setting | config.py | getattr fallback | Nơi |
|---|---|---|---|
| `chat_retrieve_top_k` | 25 | 8 | `_retrieval.py:200` |
| `chat_rerank_top_k` | 5 | 3 | `_retrieval.py:220,224` |
| `chat_max_context_chars` | 6000 | 4500 | `orchestrator.py:147` |
| `chat_rerank_floor` | 0.50 | 0.58 | `_retrieval.py:311` |
| `llm_temperature` | 0.35 | 0.3 | `runtime.py:121` |

Production luôn có `Settings` đầy đủ nên fallback không kích hoạt — nhưng test,
CLI và mọi caller dùng object settings giả sẽ chạy **một hệ thống khác** với
pool nhỏ hơn 3 lần và ngưỡng OOD cao hơn. Chính file config đã cảnh báo về đúng
loại bẫy này ở dòng 192 (`chat_min_chunk_score` từng không tồn tại trong khi code
đã đọc nó qua getattr). Cái bẫy vẫn còn nguyên, chỉ đổi tên field.

### 3.7 Ba `BaseHTTPMiddleware` bọc quanh một endpoint streaming

`BaseHTTPMiddleware` bọc response trong anyio stream; với SSE nó thêm một chặng
task cho mỗi chunk và làm mất backpressure. Ngoài ra:

- `RequestLoggingMiddleware` đo `latency_ms` = thời gian tới **header đầu tiên**,
  không phải toàn cuộc. Với SSE con số này luôn ~0 → metric `p95` trong
  `/metrics` đang nói dối về latency chat.
- `response.headers["X-Request-ID"] = request_id` (observability.py:93) chạy sau
  khi `call_next` trả về; với StreamingResponse header đã gửi đi rồi. Dòng chết.
- `RateLimitMiddleware._hits` là `defaultdict(deque)` **không bao giờ xoá key**.
  Mỗi IP từng gọi API để lại một entry vĩnh viễn. Rò rỉ chậm nhưng có thật.
- Rate limit theo `request.client.host`: sau reverse proxy thì cả thế giới dùng
  chung một quota.

---

## 4. Hiệu năng — xếp theo mức tiết kiệm thật

**(1) Hai model chạy nối tiếp trên cùng CPU.** Intaker (`num_predict=768`,
JSON) phải xong 100% trước khi câu đầu tiên của generator bắt đầu. Nhưng query
retrieval là `build_current_turn_query(clean_text, selected_history)` — nó chỉ
cần intent để quyết định có kéo history vào hay không. Có thể khởi động
embed + Chroma + BM25 + rerank **song song** với inference của intaker, dùng
`clean_text` làm query; khi intaker trả về, 90% trường hợp query không đổi và ta
đã có sẵn chunk. Tiết kiệm = toàn bộ thời gian retrieval (thường 2-8s trên CPU).

**(2) Cross-encoder chấm 30-35 cặp trên CPU.** `chat_retrieve_top_k=25` +
guideline 5 + safety 5. `bge-reranker-v2-m3` là XLM-R-large (568M), `max_length=512`.
`rerank(top_k=15)` chỉ cắt **sau** khi đã chấm hết pool. Đây gần chắc chắn là
chi phí lớn thứ hai sau LLM. Ba hướng, theo thứ tự lười dần: giảm
`chat_retrieve_top_k` xuống 10-12 (pool 20 thay vì 35); đẩy reranker lên GPU
(`docker-compose.gpu.yml` đã có sẵn); đổi sang `bge-reranker-base` hoặc bản
ONNX int8.

**(3) `DEVICE=cpu`.** Embedder + reranker đều chạy CPU trong khi repo có sẵn
compose GPU. Đây là cái nút một dòng có tỉ lệ lợi/công cao nhất trong toàn bộ
danh sách này.

**(4) Guideline pass chạy cho mọi truy vấn.** `_retrieval.py:262` — thêm một
`embed_query` + một Chroma query có filter, mỗi request, kể cả khi câu hỏi không
liên quan gì tới khuyến cáo. Docstring giải thích rất kỹ *tại sao* cần
(cross-encoder dìm đoạn guideline tiếng Anh), và số liệu đưa ra cũng thẳng thắn:
760 đoạn vào pool, 16 sống sót. Tức là pass này đang bơm ~5 đoạn/query để lấy
0.1 đoạn hữu ích/query. `ensure_guideline_slot` sau đó lại **ép** một đoạn vào ô
cuối bất kể điểm số. Nếu đằng nào cũng ép thì retrieve 5 đoạn rồi vứt 4 là thừa:
lấy `top_k=1` cho pass này là đủ, giảm 4 cặp khỏi cross-encoder.

**(5) Reject/clarify tốn một lần sinh đầy đủ** — xem 3.4.

**(6) Cache intaker hỏng dưới tải** — xem 3.5.

Không đáng động vào: các bảng term, `contains_pii`, `_extract_safety_terms` gọi
ba lần, `json.dumps` mỗi token. Tổng của chúng nhỏ hơn sai số đo của một lần gọi
Ollama.

---

## 5. Bảo mật — hai thứ cần xử lý trước khi deploy

**API_KEY rỗng + CORS `["*"]` + admin router không auth.** `.env` đặt
`API_KEY=` (rỗng) → `APIKeyMiddleware` cho qua tất cả (observability.py:102).
`CORS_ORIGINS=["*"]`. `/api/v1/admin/audit` trả **toàn văn hội thoại của mọi
người dùng**, 500 bản ghi/lần, không cần credential. Cùng nhóm: `/debug/trace`
nhận message tuỳ ý và chạy nguyên pipeline kể cả gọi intaker — vừa lộ prompt nội
bộ vừa là đòn bẩy tính toán miễn phí.

**Secret thật đang nằm trong `.env`.** File không được git track (đã kiểm:
`.gitignore:6`, `git ls-files` không thấy) — tốt. Nhưng OpenAI key và hai
DeepSeek key đang ở dạng plaintext trên đĩa và tôi vừa đọc được chúng khi audit.
Nếu chưa rotate thì nên rotate.

**Phụ:** message đi qua **query string** của GET `/chat/stream`. Mô tả triệu
chứng da liễu — dữ liệu sức khoẻ — sẽ nằm trong access log của mọi proxy trên
đường đi, và trong `RequestLoggingMiddleware` nếu ai đó thêm `request.url` vào
log. Audit store có mask PII, nhưng transport thì không.

---

## 6. Hướng đi

**Bước 0 — đo trước.** `log_pipeline_stage` đã ghi mốc cho từng stage.
Chạy 30 request thật, gom p50 của INPUT/PREPROCESS/SAFETY/ROUTE/EXTRACT/RAG/
GENERATE. Mọi con số ở mục 4 là suy luận từ kiến trúc, không phải đo. Đừng tối
ưu trước khi có bảng đó.

**Bước 1 — xoá (1 PR, không đổi hành vi).** Mục 2. Bỏ `post_check` + 7 `_apply_*`,
`scope_check` + `_scope_refusal_if_out_of_scope` + `OodDetector`, endpoint
`/ws/chat`, `mmr_select`/`retrieve_with_mmr`/`expand_context`, `qa_generator.py`,
`vision/`, 5 file Protocol, teencode, `SessionStore` in-memory, phần còn lại ở
bảng 2.5. Kèm theo xoá test của chúng — test cho code chết là lý do code chết
sống lâu. **Trước khi xoá `post_check`: đối chiếu 7 luật của nó với
`get_safety_suffix` và port lại luật nào chưa có** (ít nhất là kháng sinh đơn trị
liệu). Đừng xoá kèm luật.

**Bước 2 — sửa ba bug thật.** `compute_route_flags` thiếu `user` (3.2);
`_contains_any` khớp chuỗi con (3.1); cache một-ô của `UnifiedIntake` (3.5).
Cả ba đều là diff nhỏ và cả ba đều đang âm thầm đổi hành vi.

**Bước 3 — bịt bảo mật.** Đặt `API_KEY` thật, `CORS_ORIGINS` cụ thể, cho admin
router một dependency auth riêng (đừng dựa vào middleware toàn cục có thể tắt
bằng env rỗng), tắt `/debug/trace` khi không phải dev. Rotate secret.

**Bước 4 — hiệu năng, theo thứ tự.** `DEVICE=cuda` → `chat_retrieve_top_k`
25→12 và guideline `top_k` 5→1 → song song hoá intaker ‖ retrieval → cân nhắc
trả lời cứng cho `reject`. Đo lại sau mỗi bước; ba thay đổi đầu đều là sửa
config hoặc dưới 20 dòng.

**Bước 5 — dọn cấu trúc, chỉ khi vẫn còn động lực.** Gộp 6 điểm return của
`run_intake` thành một (một `IntakeResult` dựng ở cuối, các cổng chỉ set
`refusal` rồi nhảy tới đó). Bỏ mọi `getattr(settings, x, default)` — đọc thẳng
`settings.x`, để `config.py` là nguồn sự thật duy nhất như chính nó tuyên bố ở
dòng 12. Và trả lời câu hỏi về `rule_normalizer.py`: 1.975 dòng cho nhánh
fallback có xứng không, sau khi đã đo được tỉ lệ fallback thực tế.

---

*Ghi chú: bản audit này chỉ đọc, không sửa file nào.*
