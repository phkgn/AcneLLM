# AcneLLM — Project Context

Chatbot tư vấn da mụn tiếng Việt. Local-first: hai model chạy qua Ollama, RAG hybrid trên
ChromaDB + BM25. Cloud API (DeepSeek/OpenAI) **chỉ** dùng cho eval judge và datagen,
không nằm trên đường chạy của người dùng.

> Viết lại từ code thực tế, **2026-08-11**, sau đợt dọn dẹp lớn (`src/` 17.440 → 15.839
> dòng, 507 test xanh). Mọi mục trỏ tới file có thật. §16 liệt kê chính xác cái gì đã
> thay đổi trong đợt đó — đọc nếu bạn quen bản cũ.

---

## 1. Mindset của repo — đọc phần này trước

Sáu nguyên tắc rút ra từ chính comment trong code, không phải khẩu hiệu. Đọc để hiểu
tại sao code trông như vậy trước khi định "dọn dẹp" nó.

**a. Một đường chuẩn bị duy nhất cho mọi entrypoint.**
`chat/orchestrator.py:prepare_chat_turn` là đường duy nhất. SSE, `/debug/trace`, CLI và
eval adapter đều gọi nó. Hệ quả: `/debug/trace` cho ra **đúng** cái production làm, không
phải mô phỏng lại.

**b. Rule không được tự viết câu trả lời.**
Guardrail quyết **nội dung** (ruling), generator viết **câu chữ**. Refusal không
short-circuit trả chuỗi cứng — nó chuyển thành `refuse_user.j2` rồi để LLM diễn đạt, bản
disclaimer cứng được nối lại ở `_safety.get_safety_suffix`.

**c. Model đọc ngữ nghĩa, regex đọc thực thể.**
Đây là ranh giới quan trọng nhất của repo, và nó được rút ra từ một phép đo chứ không
phải sở thích. Tên thuốc là **thực thể**: nó có trong văn bản hoặc không, phủ định không
làm chữ đó biến mất, nên khớp chuỗi là đủ. "Đang mang thai" là **trạng thái**: có phủ
định, có thì, có chủ ngữ — chỉ model đọc được.

Đo trên 13 câu đối kháng, lớp regex thai kỳ cũ sai 3: *"trước em mang thai nhưng giờ sinh
rồi"* → True, *"chị tôi đang mang thai"* → gán cho người dùng. Đo end-to-end ở cổng thuốc
còn tệ hơn: 5/5 câu bị chặn, 4 sai — kể cả *"em không mang thai, dùng tretinoin được
không"*. Toàn bộ lớp đó đã bị gỡ (§16).

**d. LLM-first, rule là lưới an toàn — nhưng lưới phải đặt đúng chỗ.**
Route: unified LLM → semantic kNN → rule. Extract: unified LLM → rule, và rule **chỉ**
chạy khi JSON không parse được. Fail ở tầng nào thì `log_pipeline_stage(..., level=
"WARNING", fallback=...)` ghi lại, pipeline chạy tiếp.

Ngoại lệ cố ý: hai cổng tất định chạy **trước mọi model** — prompt injection và vùng sinh
dục. Ý nghĩa của một cổng cứng nằm ở chỗ nó không thể bị model thuyết phục; nhờ chính
model đánh giá cuộc tấn công vào nó là vô nghĩa.

**e. Đừng trả giá suy luận trước khi biết có cần không.**
Extractor chỉ chạy sau khi route ra `advise|knowledge`. Pre-LLM chỉ cần `description`.

**f. Không đo bằng từ vựng.**
KB 60% Việt / 40% Anh nên mọi phép khớp từ đều thưởng cho đoạn cùng ngôn ngữ với câu hỏi,
bất kể nội dung. `grounding_support` (char-3gram dice) và `forbidden_claims` đã bị gỡ khỏi
eval vì lý do này. Xem `evaluation/eval_context.md` §6g.

**g. Ngưỡng phải ghi kèm thang đo của nó.**
Nhiều bug lịch sử là tune ngưỡng trên sai thang. `config.py` cố ý mang comment dài giải
thích *score này là xác suất hay logit, đo sau bước nào* — đừng cắt gọn chúng. Xem §11.

---

## 2. Stack thực tế

| Layer | Thành phần | Nguồn sự thật |
|---|---|---|
| Generator | `acne-generator` — Qwen2.5-7B-Instruct Q4_K_M + LoRA role | `.env: LLM_MODEL`, `model/generator/Modelfile.full` |
| Fallback generator | `qwen2.5:3b` — chỉ khi runner Ollama chết | `config.py: llm_fallback_model` |
| Unified Intake | `acne-intaker` — Qwen2.5-3B-Instruct Q4_K_M + LoRA, temp 0 | `model/intaker/Modelfile` |
| Router (arm legacy) | `acnellm-intent` | `config.py: router_model` |
| Extractor (arm legacy) | `acne-extractor:1.5b` | `config.py: extractor_model` |
| Semantic router | kNN trên embedding, k=9, OOS distance 0.483609 | `chat/routing/semantic_router.py` |
| Embedding | `AITeamVN/Vietnamese_Embedding` (dim 1024) | `config.py` |
| Reranker | `BAAI/bge-reranker-v2-m3` cross-encoder | `config.py` |
| Vector DB | ChromaDB — **24.393 chunk** | `data/chroma_db/` |
| Sparse | BM25 (`rank-bm25`), pickle + sha256 | `data/bm25_index.pkl` |
| API | FastAPI + uvicorn, **SSE only** | `api/app.py` |
| Frontend | Next.js 15 + Tailwind + Zustand | `frontend/src/` |
| Session | SQLite `data/sessions.db`, TTL 1800s, 6 turn | `db/session_store.py` |
| Audit | SQLite `data/audit.db` | `db/audit.py` |
| Cache | DiskCache 2GB `data/cache` | `cache.py` |
| Config | pydantic-settings | `config.py` |

### Phân tầng KB theo `source_type` (24.393 chunk)

| source_type | chunk |
|---|---|
| `vi_medical_site` | 12.359 |
| `pubmed_review` | 5.218 |
| `blog` | 3.571 |
| `en_medical_site` | 2.258 |
| `clinical_textbook` | 621 |
| `aad_guideline` | 180 |
| `nice_guideline` | 172 |
| `unknown` | 14 |

Ba loại cuối (`nice_guideline` + `aad_guideline` + `clinical_textbook` = **973 chunk**)
là "tầng khuyến cáo chính thức" mà guideline pass retrieve giới hạn trong đó. Lý do: dense
+ BM25 trên toàn corpus luôn ưu ái bài phổ thông tiếng Việt (12.359 vs 973 — tỉ lệ áp đảo +
trùng token), nên guideline không bao giờ tự vào được top-k dù KB có sẵn.

---

## 3. Cây thư mục thật

```
src/acne_llm/                    15.839 dòng
├── api/                         710
│   ├── app.py                   FastAPI + lifespan → build_container, CORS, middleware
│   ├── deps.py                  get_container, require_admin (fail closed)
│   ├── observability.py         APIKey / RateLimit / RequestLogging, MetricsRegistry
│   └── routes/
│       ├── chat.py              /chat/stream (SSE), /debug/trace 🔒, /chat/feedback
│       ├── admin.py             /admin/* 🔒 — audit log, session stats, feedback
│       ├── kb.py                /kb/retrieve, /kb/search, /kb/stats, /kb/chunk/{id}
│       ├── health.py            /health, /models
│       └── metrics.py           /metrics (Prometheus)
├── chat/                        7.657  ← trái tim hệ thống
│   ├── intake.py                run_intake() — guardrails + route + extract + fold
│   ├── orchestrator.py          prepare_chat_turn() — đường chuẩn bị DUY NHẤT
│   ├── runtime.py               stream_chat_sse() — SSE, persist, audit
│   ├── unified_intake.py        1 inference phục vụ cả classify() lẫn run()
│   ├── _intake_parse.py         parser khoan dung cho JSON của intaker
│   ├── _retrieval.py            retrieve_for_chat() — RRF, guideline pass, OOD guard
│   ├── _safety.py               get_safety_suffix() — tầng hậu kiểm DUY NHẤT
│   ├── session.py               data model + fold_history_facts + format_history_block
│   ├── preprocess.py            NFC, bỏ control char, strip_accents
│   ├── confidence_hint.py       field conf thấp → nhắc model hỏi lại
│   ├── _intent_patch.py         vá clarify→advise (tạm, xem §15)
│   ├── _terms.py                bảng từ khoá dùng chung
│   └── fallback/                CHỈ chạy khi tầng model fail
│       ├── rule_normalizer.py   1.975 dòng — trích xuất bằng regex
│       ├── rule_extractor.py    confidence cho bản rule
│       ├── intent_router.py     route tầng 3 + compute_route_flags (LUÔN chạy)
│       ├── semantic_router.py   route tầng 2 (kNN)
│       ├── llm_router.py        arm legacy
│       └── llm_extractor.py     arm legacy
├── rag/                         1.159
│   ├── retriever.py             HybridRetriever — dense + BM25 + RRF + trust boost
│   ├── reranker.py              cross-encoder, cache (query, chunk_id)
│   ├── embedder.py  vectorstore.py  sparse.py  chunker.py  cleaning.py
├── llm/                         534
│   ├── ollama_backend.py        HTTP client, stream + fallback model
│   └── prompt_builder.py        Jinja2 + sanitize (trust boundary)
├── guardrails/                  545
│   ├── runner.py                pre_check, genital scope, medication_safety_refusal
│   └── pii.py                   contains_pii / mask_pii  (đổi tên từ ood_detector.py)
├── db/                          602    session_store.py (SQLite) · audit.py · base.py
├── utils/                       771    logging (log_pipeline_stage) · retrieval_query · chunk_filter
├── schemas/                     597    core · clinical · extraction · kb
├── crawler/                     2.438  ← NGOẠI TUYẾN, không nằm trên đường chạy request nào
├── cache.py  cli.py  config.py  di.py
```

🔒 = sau `require_admin` (header `x-admin-key`).

`crawler/` nằm trong `src/` vì lịch sử, nhưng không module runtime nào import nó — vì thế
dependency của nó (trafilatura, playwright, bs4…) nằm ở `requirements-dev.txt`, không phải
`requirements.txt`.

---

## 4. Đường chạy một tin nhắn — chi tiết theo code

### 4.1 Entrypoint

`GET /api/v1/chat/stream` → `runtime.stream_chat_sse` → `orchestrator.prepare_chat_turn`
→ `intake.run_intake`. **Không có endpoint WebSocket** — frontend dùng SSE hoàn toàn
(`frontend/src/lib/api.ts`).

### 4.2 `run_intake()` — thứ tự CHÍNH XÁC (`chat/intake.py:211`)

```
①  Guard độ dài        4000 ký tự / 500 từ → ValueError (route trả 413)
②  prepare_user_text() → clean_text, clean_text_no_accent
③  store.get_history(session_id)          ← c.session_store, KHÔNG còn fallback ngầm
④  _resolve_mode()     auto → hybrid nếu c.rag_ready, ngược lại llm_only
⑤  base_user = UserInput(description=light_normalize(raw))     ← CHƯA trích xuất gì
⑥  _extract_safety_terms(clean_text, base_user)
       → danh sách CHỦ ĐỀ được nhắc tới. Chỉ dùng cho RETRIEVAL.
         KHÔNG dùng để suy trạng thái — xem §1c.
⑦  guardrails.pre_check(base_user)                → reject cứng "pre_check_invalid"
⑧  genital scope                                  → reject cứng, TRỪ mixed scope
⑨  medication_safety_refusal(base_user)  [current_turn]
       → ở bước này base_user chưa có context, nên chỉ cặp thuốc-thuốc từ text mới chặn được
⑩  ROUTE  ─ ladder, xem §5
⑪  compute_route_flags(clean_text, history) → merge vào MỌI đường route
⑫  clarify downgrade: clarify + _has_established_case(history) → advise
⑬  intent == reject   → return ngay (llm_only, history=[], không extract)
⑭  intent == clarify  → select_relevant_history, return (không extract)
⑮  EXTRACT  ─ chỉ advise|knowledge, xem §6
⑯  red_flags_input ≠ ∅ → gắn LẠI cờ `urgency_red_flag`
       compute_route_flags ở ⑪ chạy TRƯỚC extract nên không thấy clinical. Thiếu bước
       này thì mọi red flag intaker trích được đều không bật cảnh báo khẩn (bug đã sửa).
⑰  guardrails.pre_check(base_user) LẦN 2 — full field sau khi đã trích xuất
⑱  medication_safety_refusal  [post_extract]   ← thai kỳ chặn được ở ĐÂY, không sớm hơn
⑲  advise only: confirmed_profile ← build_confirmed_profile(...) → merge vào session
⑳  advise only: fold_history_facts(base_user, history)
㉑  medication_safety_refusal  [session_fold]  ← thuốc đã xác nhận từ turn trước
㉒  normalized_query = build_current_turn_query(clean_text, selected_history)
    → IntakeResult
```

Ba lần gọi `medication_safety_refusal` là **cố ý**: current turn (chặn sớm cặp thuốc),
post-extract (đủ field, thai kỳ chặn ở đây), session-fold (thuốc xác nhận turn trước).

Đánh đổi mới sau khi gỡ lớp regex: thai kỳ **không còn chặn được trước khi gọi model**.
Vẫn chặn trước retrieval và trước generator, chỉ là tốn một lần inference. Bù lại không
còn chặn nhầm người nói "em không mang thai".

### 4.3 `prepare_chat_turn()` (`chat/orchestrator.py:47`)

```
run_intake()
  ↓
should_retrieve = mode==hybrid ∧ không refusal ∧ effective_mode ∉ {refuse,clarify}
                  ∧ intent ∉ {clarify,reject} ∧ (is_acne_signal ∨ safety_terms ∨ history)
  ↓ nếu true
retrieve_for_chat()   → RetrievalOutput | None
  ↓
chọn template:  scope_refusal|refuse → refuse_user.j2
                reject               → reject_user.j2
                clarify              → clarify_user.j2
                knowledge            → knowledge_user.j2
                mặc định (advise)    → stream_user.j2
  ↓
hint = refusal.disclaimer (nếu có) + confidence_hedge(field conf < 0.6)
  ↓
c.prompt.build(user, retrieval, template, max_context_chars,
               history, prompt_note=hint, confirmed_profile)
  → PreparedChatTurn(system_prompt, user_prompt, retrieval, …)
```

`user_override` chỉ nhận từ caller tin cậy (CLI/eval) và **chỉ** fact an toàn mới ảnh
hưởng prompt.

### 4.4 `stream_chat_sse()` (`chat/runtime.py:58`)

```
prepare_chat_turn()
  → route_flags có "progress_followup": increment_followup_count(session)
  → route_flags có "crisis_signal": yield prefix đồng cảm TRƯỚC khi stream
  → c.llm.stream_text(system, user)   [knowledge: num_predict=-1, không hard-cap]
       ├ strip CJK từng token (guard rò tiếng Trung/Nhật/Hàn)
       └ yield event "token"
  → yield event "source" cho từng chunk (TOÀN VĂN, không cắt 220 ký tự)
  → get_safety_suffix()  → yield "token"
  → sess.append_turn(user: RAW message) + append_turn(assistant: full text)
  → compute_evidence_quality(retrieval)
  → audit.log(AuditEntry)  — mask_pii nếu pii_detected
  → yield event "done" {mode, latency_ms, used_chunks, evidence_quality,
                        primary_intent, route_flags}
```

Turn `user` lưu **nguyên văn** người gõ, không phải bản đã preprocess.

Việc ghi session nằm **sau** bước sinh và cả khối trong `try`: Ollama chết giữa chừng thì
không lượt nào được lưu, session giữ nguyên trạng thái cũ thay vì đọng một câu hỏi không
có trả lời.

---

## 5. Routing — ladder ba tầng

`RouteDecision(primary_intent, confidence, source, reason_code, route_flags, turn_type)`.
`primary_intent ∈ {advise, knowledge, clarify, reject}`.

| # | Tầng | Điều kiện dùng | Thất bại → |
|---|---|---|---|
| 1 | `c.llm_router` — **UnifiedIntake** (`acne-intaker`) khi `INTAKE_MODE=unified` | luôn thử trước | `RouterFallback` → tầng 2 |
| 2 | `c.semantic_router` — kNN k=9, OOS nếu cosine distance > 0.483609, ambiguity margin 0.08 | router LLM fail/thiếu | exception → tầng 3 |
| 3 | `route_intent()` rule (`fallback/intent_router.py`) | hai tầng trên fail | không có tầng 4 |

Chỉ tầng 3 mới chạy `normalize_chat_message()` + `extract_with_confidence()` — fallback về
rule **đắt hơn**, không rẻ hơn.

**Hai patch bắt buộc sau khi route:**

- `compute_route_flags(clean_text, history)` merge vào **mọi** đường. Unified và semantic
  trả `route_flags=[]`, làm chết im lặng cảnh báo khẩn cấp (`_safety`) và guidance an toàn.
  Cờ là tín hiệu văn bản nên không phụ thuộc router nào thắng.
  ⚠️ Hàm được gọi **không có** `user` (chạy trước extract), nên nhánh clinical bên trong nó
  luôn tắt — bước ⑯ ở §4.2 gắn bù cờ `urgency_red_flag`.
- **clarify downgrade**: intaker học multi-turn từ 200/200 mẫu đều gán `clarify`, nên mọi
  follow-up có history bị kéo về clarify. Khi phiên đã có case thật, hạ xuống `advise` +
  flag `clarify_downgraded`. **Gỡ sau khi datagen multi-turn cân lại nhãn.**

`route_flags` sinh ở `compute_route_flags` (`fallback/intent_router.py:268`):
`repeated_question`, `emotional_distress`, `crisis_signal`, `product_safety_check`,
`urgency_red_flag`, `progress_followup`, `multi_condition`. Thêm ở nơi khác:
`mixed_genital_scope`, `clarify_downgraded`, `medication_safety_block`,
`pre_check_invalid`, `genital_scope`.

---

## 6. Extraction — Unified Intake

`UnifiedIntake` (`chat/unified_intake.py`) là **một inference phục vụ hai interface**:
`classify()` trả `RouteDecision`, `run()` trả `LLMExtractResult`.

- Cache **LRU 8 ô + lock**, khoá `(clean_text, history_json)`. Bản cũ là *một ô duy nhất
  trên instance dùng chung*: hai request song song ghi đè ô của nhau giữa `classify()` và
  `run()`, request bị đè phải gọi intaker lần hai — chi phí intake gấp đôi một cách không
  xác định dưới tải.
- Prompt runtime `_RUNTIME_SYSTEM` **trùng byte** với `SYSTEM` trong `model/intaker/Modelfile`
  và `datagen/intakedata/system_prompt.canonical.txt`. Ba nơi, sửa một là lệch train/serve.
- Dùng `response_format="json"` chứ **không** grammar — llama.cpp không parse nổi nested
  `anyOf`-null, trả 400.
- Hậu kiểm duy nhất: parse được JSON object + `_validate_contract`. Sai enum/shape thì
  parser khoan dung ở `_intake_parse.py` **drop field**, không fallback: một field hỏng
  không đáng vứt cả inference.
- `intent` là ngoại lệ — sai enum thì raise, vì không route được thì không còn đường nào.
- History: tối đa 3 turn gần nhất, mỗi turn ≤ 300 ký tự, chỉ role `user`/`assistant`.

**Không còn lớp regex hỗ trợ.** `_intake_parse.py` từng chạy `_raw_safety_lists()` và
`_raw_safety_overrides()` trên **mỗi lượt** rồi OR vào kết quả model. Đã gỡ — xem §1c và
§16. `rule_normalizer` + `rule_extractor` vẫn còn nguyên nhưng chỉ được gọi khi
`UnifiedIntake` ném `ExtractorFallback`.

Schema trả về: `{intent, confidence, description, context, clinical}`, mọi scalar và mọi
phần tử list đều là `{"value":…, "confidence":0..1}`.

**Enum cứng** (đổi ở đây là đổi cả datagen + Modelfile + eval):
`lesion_types`: comedone, whitehead, blackhead, closed_comedone, papule, pustule, nodule,
cyst, scar, post_inflammatory_hyperpigmentation, other ·
`inflammation_level`: none, mild, moderate, severe, unknown ·
`lesion_distribution`: forehead, cheeks, chin, jawline, nose, around_mouth, back, chest,
shoulders, neck, t_zone, other · `skin_type`: dry, oily, combination, sensitive, normal, unknown.

**Dải confidence** do system prompt của intaker định nghĩa — mọi ngưỡng đọc số này phải
neo theo nó: `0.9–1.0` nêu rõ · `0.6–0.85` suy luận hợp lý · `0.3–0.55` mơ hồ.

---

## 7. Retrieval (`chat/_retrieval.py:187`)

```
query = intake.normalized_query        ← query CỦA LƯỢT HIỆN TẠI. Planner đã bị gỡ.
cache key = ("chat-query-v6", query, top_k, rerank_top_k, min_score, safety_terms)

① retriever.retrieve(query, top_k=25, mode="hybrid")
      dense (Chroma cosine, distance ≤ 0.60) + BM25 → RRF (k=60) → trust_boost theo source_type
② GUIDELINE PASS — chạy cho MỌI truy vấn
      retrieve_safety_pass(query, safety_terms=None, top_k=5,
                           source_types=(nice_guideline, aad_guideline, clinical_textbook))
      → RRF merge vào pool. KHÔNG ép chunk nào vào câu trả lời; cross-encoder vẫn quyết.
③ SAFETY PASS — chỉ khi _has_medical_safety_terms() (thai kỳ, isotretinoin, kháng sinh…)
      Generic ingredient term KHÔNG kích hoạt
④ reranker.rerank(query, pool, top_k = chat_rerank_top_k * 3 = 15)
      ⚠️ rerank chấm HẾT pool rồi mới cắt — pool ~30-35 cặp là chi phí thật
⑤ cap_per_source(max_per_source=1, limit=5)   ← cap SAU rerank, TRƯỚC OOD guard
      chunk bị loại giữ làm spill, lấp lại nếu chưa đủ limit → không bao giờ trả ít hơn
⑥ OOD guard mềm: giữ chunk có score ≥ chat_rerank_floor (0.50)
      không chunk nào đạt → return None → LLM trả lời KHÔNG dùng RAG
⑦ drop_acne_boils_mismatched_chunks → drop_body_region_mismatched_chunks → drop_noisy_chunks
   (KHÔNG dùng keyword-mismatch filter sau reranker — cross-encoder đã score rồi)
⑧ ensure_guideline_slot — nếu top-N cuối không có đoạn khuyến cáo nào thì thay đoạn điểm
   THẤP NHẤT bằng đoạn khuyến cáo tốt nhất còn trong pool

Không có reranker → _full_filter (noise + keyword mismatch)
```

`compute_evidence_quality`: avg ≥ 0.90 → `strong`, ≥ 0.50 → `moderate`, < 0.50 → `weak`,
không retrieval → `unverified`.

⚠️ **Đổi logic retrieval thì PHẢI tăng version trong cache key.** Khoá cache chỉ gom query
+ vài tham số, không phản ánh code. Quên tăng → cache trả kết quả cũ và bạn tưởng thay đổi
không có tác dụng. Lịch sử: v3 guideline pass · v4 bỏ sigmoid lần hai · v5 cap_per_source ·
v6 ensure_guideline_slot.

---

## 8. Session & context (`chat/session.py`)

- `SQLiteSessionStore` — `data/sessions.db`, TTL 1800s, giữ 6 turn (`HISTORY_WINDOW_TURNS`).
  **Nguồn duy nhất trong production**: `runtime`/`intake` đọc thẳng `c.session_store`.
  `SessionStore` in-memory cùng file giờ là **test double**, có ghi rõ trong docstring.
- `NormalizedSnapshot` chỉ persist khi `primary_intent == "advise"`.
- **`select_relevant_history`** — không đoán "có phải follow-up không" bằng whitelist tiền tố:
  - `knowledge` → chỉ **user turn gần nhất**, giữ prose cũ của bot ra ngoài prompt.
  - còn lại → cả cửa sổ 6 turn; `format_history_block()` cắt theo `HISTORY_CHAR_BUDGET=2000`.
  - turn genital luôn bị lọc bỏ.
- **`fold_history_facts`** — chỉ chạy khi `advise`: last-write-wins cho scalar · ADDITIVE cho
  `lesion_types`/`distribution`/`red_flags` · MAX theo `_SEVERITY_ORDER` cho
  `inflammation_level` · tôn trọng phủ định (`_mentions_stop`, `_STOP_PRODUCT_TERMS`).
- **`build_confirmed_profile`** — ngưỡng **theo nhóm trường**, neo vào dải của intaker (§6):

  | Trường | Ngưỡng | Vì sao |
  |---|---|---|
  | `is_pregnant`, `is_breastfeeding` | **không gác** | cổng chỉ nổ khi True; bỏ sót là hướng hỏng nguy hiểm, chặn nhầm chỉ phiền |
  | còn lại | `CONTEXT_FIELD_THRESHOLD = 0.60` | ngữ cảnh; nhớ nhiều hơn thì sát hơn |

  Con số chọn theo **hướng hỏng**, không theo mức quan trọng của trường. Ngưỡng cũ 0.82 nằm
  giữa dải "suy luận" — dữ kiện model đoán ở 0.84 lọt, 0.80 rớt, một ranh giới vô nghĩa còn
  sót từ thang điểm rule.

Ba trường `intent_label` / `intent_confidence` / `turn_type` trên `ConversationTurn` đã bị
xoá: chúng chỉ được **ghi** bởi store in-memory và bản SQLite không khôi phục khi đọc — hai
store lệch nhau mà không ai phát hiện, vì không dòng nào đọc chúng.

---

## 9. Guardrails (`guardrails/runner.py`, 499 dòng)

Chỉ còn **ba cổng**, tất cả đều chạy trước generator:

| Hàm | Chạy ở đâu | Tính chất |
|---|---|---|
| `pre_check(user)` | intake ⑦ và ⑰ | prompt injection → raise → reject cứng |
| `is_genital_scope` | intake ⑧ | hard reject, trừ mixed scope |
| `medication_safety_refusal(user, terms)` | intake ⑨ ⑱ ㉑ | trả `AdviseOutput` → refuse |

`medication_safety_refusal` chặn bốn thứ, tất cả viết thẳng trong hàm:

1. thai kỳ/cho bú + bất kỳ retinoid/tetracycline nào
2. isotretinoin + tetracycline (nguy cơ tăng áp lực nội sọ)
3. tetracycline khi < 8 tuổi · isotretinoin khi < 12 tuổi
4. spironolactone/cyproterone cho nam

Ba nhóm sau từng do `DrugChecker` + `drugs_acne.yaml` lo. Class đó đã bị xoá (§16);
`config/drugs_acne.yaml` **giữ lại** vì `datagen/gates.py` đọc nó để lấy danh sách hoạt chất.

`_contains_any` khớp theo **ranh giới từ**, gộp thành một regex compile sẵn. Bản cũ chỉ áp
ranh giới cho 6 alias, 414 term còn lại dùng `in` — mà bảng có term hai ký tự không dấu
("co", "ma", "cam"), nên `is_acne_scope_text("con chó nhà tôi bị ốm")` trả True. Đo lại trên
4.695 câu thật: sửa đổi kết luận ở 1,2% số câu, phần lớn là sửa đúng.

Soft OOS **không** ở guardrails — nó thuộc về intaker/`SemanticRouter`.
`contains_pii`/`mask_pii` nằm ở `guardrails/pii.py`, dùng lúc ghi audit.

Vùng mụn hợp lệ: mặt, trán, má, cằm, mũi, quai hàm, hàm, miệng, lưng, ngực, vai, cổ, gáy.

---

## 10. Prompt (`llm/prompt_builder.py` + `config/prompts/*.j2`)

`PromptBuilder.build()` ráp bốn khối, xếp ngược thứ hạng (cao nhất xuống cuối):
tài liệu tham khảo → ngữ cảnh gần nhất → dữ kiện an toàn đã xác nhận → tin nhắn hiện tại.

- `_escape_jinja` / `_sanitize_chunk_text` / `_sanitize_user_description` /
  `sanitize_history_turns`: chunk và text người dùng là **trust boundary** — chống prompt
  injection qua nội dung crawl. Đừng gỡ.
- `known_facts` và `route_guidance` **đã bỏ**: SYSTEM không có luật xử lý chúng nên model tự
  đoán. Kênh duy nhất báo "extractor không chắc" giờ là `build_confidence_hint`.
- `llm_use_modelfile_system=True` (mặc định): **không** gửi system message qua API, để
  `SYSTEM` trong Modelfile tự lo — tránh hai system prompt chồng nhau. Nên `sys_p` trả về
  luôn là chuỗi rỗng.

Template: `stream_user.j2` (advise) · `knowledge_user.j2` · `clarify_user.j2` ·
`reject_user.j2` · `refuse_user.j2`. Hai file `*.legacy.j2` giữ cho arm A/B.

---

## 11. Config — ba tầng, đừng trộn

| Tầng | Chứa gì | KHÔNG chứa gì |
|---|---|---|
| `model/**/Modelfile` | artifact-level: `FROM`, `TEMPLATE`, `SYSTEM`, stop token | `num_ctx`, `temperature`, `top_p` — Python cần quyền override per-request |
| `.env` | secret + giá trị khác theo máy/lần chạy | hằng số tuning |
| `config.py` | **single source of truth cho SCHEMA + DEFAULTS** | secret |

### Knob quan trọng và thang đo của nó

| Key | Default | Cảnh báo |
|---|---|---|
| `chat_retrieve_top_k` | 25 | pool ĐƯA VÀO cross-encoder |
| `chat_rerank_top_k` | 5 | giữ lại sau rerank |
| `chat_guideline_top_k` | 5 | guideline pass, chạy mọi truy vấn |
| `chat_safety_top_k` | 5 | chỉ khi có medical safety term |
| `chat_max_chunks_per_source` | 1 | chunker chồng lấn 40 token → 2 chunk kề nhau gần trùng |
| `chat_max_context_chars` | 6000 | eval oracle dùng lại đúng số này |
| `chat_rerank_floor` | 0.50 | **xác suất thật** từ `CrossEncoder.predict()`. Ngưỡng 0.45→0.58 trước đây tune trên thang bị sigmoid hai lần ([0.500, 0.731]) |
| `reranker_min_sigmoid` | 0.30 | cùng thang xác suất; đúng chủ đề ~0.95-0.999, lạc đề < 0.1 |
| `chat_min_chunk_score` | 0.25 | ⚠️ chạy trên **hai thang**: sau reranker vô tác dụng, chỉ nhánh không-reranker mới có nghĩa |
| `dense_max_distance` | 0.60 | cosine distance Chroma ≈ similarity 0.40 |
| `extract_min_field_conf` | 0.60 | ngưỡng trường ngữ cảnh vào `confirmed_profile`. Từng bị `max(0.82, …)` khoá cứng nên **chưa bao giờ có tác dụng** — đã gỡ |
| `route_min_confidence` | 0.55 | routing dưới ngưỡng → clarify |
| `admin_api_key` | `""` | 🔒 khoá cho `/admin/*` + `/debug/trace`. **Rỗng = từ chối** (fail closed) |
| `api_key` | `""` | khoá toàn cục, cố ý để trống: `EventSource` không gửi được header → bật lên là chết `/chat/stream` |
| `cors_origins` | `["localhost:3000", ":8000"]` | đừng dùng `"*"` |
| `llm_keep_alive` | -1 | Ollama parse như Go duration: int hoặc string **có unit**. `"-1"` dạng string → 400 |
| `ollama_generate_timeout` | 30.0 (config) / 300 (.env máy CPU) | thấp cố ý để latency lộ ra |

Mọi `getattr(settings, x, default)` trong code phải có default **trùng** `config.py`.
Từng có 5 chỗ lệch (`chat_retrieve_top_k` 8≠25, `chat_rerank_top_k` 3≠5, …) khiến test chạy
một hệ còn production chạy hệ khác. Đã đồng bộ.

---

## 12. Evaluation

### 12.1 `evaluation/` — 3 khâu

Giả thiết nền: hệ thống có 3 khâu **intaker → RAG → generator**; câu trả lời dở thì phải
biết lỗi ở khâu nào.

| Khâu | Đo gì | Judge | Lệnh |
|---|---|---|---|
| 1 | intaker rút đúng 15 slot không | không | `python -m evaluation.runners.run_intake` |
| 2 | tài liệu retrieval mang về có dùng được không | có | `python -m evaluation.runners.run_retrieval` |
| 3 | thay/tắt từng khâu, câu trả lời chênh bao nhiêu | có | `python -m evaluation.runners.run_ablation` |

**Khâu 2 KHÔNG dùng recall@k trên chunk vàng** — chấm theo danh tính chunk là chấm oan.
Judge hỏi thẳng "đoạn này liên quan không, gộp lại đủ trả lời không".

Arm = 3 ký tự `[intaker][rag][generator]`, `R`=thật · `O`=hoàn hảo · `N`=tắt.
Mặc định 6 arm: `RRR RNR ROR ORR RRO RNO`.

Chín mặt điểm, không mặt nào đếm từ. Safety **luôn báo riêng**.

**Bộ đề mới — `intake_pregnancy_probe.jsonl`.** 41 câu đối kháng cho riêng `is_pregnant`:
phủ định, thì quá khứ, ngôi thứ ba, tự đính chính, giả định, câu hỏi kiến thức, diễn đạt
gián tiếp. 37% dương tính, so với bộ cũ mà `run_intake.py:52` ghi là *0 dòng
`is_pregnant=True` trên 400*. Sinh lại bằng
`python -m evaluation.datasets.make_pregnancy_probe`.

Đây là bằng chứng đi kèm quyết định gỡ lớp regex thai kỳ: sau khi gỡ, **không còn gì đỡ
phía sau intaker** ở trường đó. Nhìn `accuracy_khi_co_khai` và `bo_trong`.

### 12.2 Nợ đã biết của eval

- **Judge chưa hiệu chỉnh.** `judges/calibrate.py` có sẵn nhưng chưa chạy.
- Câu hỏi sinh ngược từ chunk luôn trả lời được từ KB → `ROR − RRR` là **cận trên**.
- Không có số retrieval nội tại.
- `answer_quality` vẫn gộp "sai" và "thiếu" — món nợ có ý thức.

### 12.3 `ablation/` — module song song ở root

Không import gì từ `evaluation/`, chạm product code qua `repo_adapter.py`, chạy đủ lattice
2³ = 8 arm. ⚠️ Hai module cùng đo một thứ với hai định nghĩa arm khác nhau — trước khi trích
số vào luận văn phải chọn một làm nguồn sự thật.

---

## 13. Datagen (`datagen/`)

| Module | Sinh cho | Output |
|---|---|---|
| `datagen/intakedata/` | `acne-intaker` | `output/intake/intake.{train,val,smoke}.jsonl` |
| `datagen/roledata/` | generator, v1 | `datagen/roledata/output/` |
| `datagen/roledatav2/` | generator, v2 — thêm `len_chars` + `min_points` | `datagen/roledatav2/output/` |

Mọi record dùng `system_prompt.canonical.txt` **byte-identical** với Modelfile và
`_RUNTIME_SYSTEM`. Ghi append-only sau khi qua gate. `--yes` bắt buộc với mọi mode tốn phí.

Pipeline **resume được**: `slots` chỉ sinh từ `counts[case]+1` tới target, output append-only.
Chạy lại không làm lại phần đã có.

⚠️ **Gate `phrase_frequency` xung đột với taxonomy.** Nó cấm một cụm 14 từ lặp quá 8 lần
trên toàn corpus, trong khi taxonomy bắt model luôn xưng danh, luôn khuyên gặp bác sĩ,
luôn nói "không phải bác sĩ". Đo trên corpus v2 (2.763 mẫu): 98,02% cụm 14-gram chỉ xuất
hiện **một lần** — tập rất đa dạng — nhưng 248 cụm chạm trần, và chúng chính là các câu bắt
buộc đó. Kết quả: 63% số lần bị loại là do gate này, 749 slot bỏ cuộc sau 4-8 lần thử.

Nâng cap chỉ là vá tuyến tính. Hướng đúng: miễn trừ phần boilerplate bắt buộc khỏi gate.

---

## 14. Dev workflow

```bash
./tasks.sh install          # venv + deps (Linux dùng .venv-linux)
./tasks.sh serve            # tự start ollama, kill port 8000, uvicorn --reload
./tasks.sh frontend         # next dev :3000
./tasks.sh build-kb         # data/raw/documents.jsonl → chroma + bm25
./tasks.sh test             # pytest
./tasks.sh lint  stats  chat  docker-{build,up,logs,down}
```

Windows:

```powershell
.\scripts\RUN.ps1            # 3 cửa sổ: ollama serve, backend, frontend
.\scripts\RUN.ps1 -Log       # + cửa sổ tail log backend
.\scripts\runpod.ps1         # SSH tunnel tới Ollama trên pod
.\scripts\runpod.ps1 -Status | -Stop
.\scripts\KB.ps1
```

`RUN.ps1` là **local thuần**, không biết gì về RunPod. Hai script không giẫm chân nhau:
`RUN.ps1` không tự giết tunnel, `runpod.ps1` không tự giết Ollama local.

Test: `pytest -q` → **507 passed, ~10 giây**, toàn bộ mock LLM/retriever, không cần Ollama.

Debug pipeline không tốn generator: `GET /api/v1/debug/trace?message=...` với header
`x-admin-key`. Read-only, dừng ngay trước bước stream. **Vẫn gọi intaker** (một lần).

---

## 15. Bẫy đã biết — đọc trước khi sửa

1. **Cache key retrieval** — đổi logic mà quên tăng `chat-query-vN` → kết quả cũ, tưởng
   thay đổi vô tác dụng.
2. **`chat_min_chunk_score` chạy trên hai thang** — chỉ có nghĩa ở nhánh không reranker.
3. **Score của reranker là xác suất, không phải logit.** Đừng sigmoid lần nữa.
4. **`compute_route_flags` chạy TRƯỚC extract** nên không thấy clinical. Cờ phụ thuộc
   clinical phải gắn bù sau (bước ⑯). Quên là mọi red flag im lặng.
5. **Guard `clarify_downgraded` là tạm** — do datagen multi-turn gán 200/200 nhãn clarify.
6. **`_RUNTIME_SYSTEM` phải trùng byte với Modelfile và `system_prompt.canonical.txt`** —
   ba nơi, sửa một là lệch train/serve.
7. **Extractor chạy SAU route, không phải trước.**
8. **Đừng đưa regex trở lại đường trích xuất.** Nếu thấy cần "một lưới an toàn cho thai kỳ",
   đọc §1c trước — lưới cũ sai 4/5 và đã bị gỡ có bằng chứng.
9. **`mentioned_terms` ≠ trạng thái.** `_extract_safety_terms` trả lời "văn bản có nhắc tới
   chủ đề gì" và chỉ dùng cho retrieval. Cổng an toàn phải đọc `user.context`.
10. **Comment ngưỡng trong `config.py` là tài liệu, không phải rác.**
11. **Guideline pass không ép chunk vào câu trả lời** — chỉ đảm bảo 973 chunk khuyến cáo
    được cross-encoder *nhìn thấy*.
12. **Marker `ponytail:` trong code** = đơn giản hoá có ý thức, kèm trần chịu đựng và đường
    nâng cấp. Đọc trước khi "sửa cho tử tế".

---

## 16. Đợt dọn dẹp 2026-08 — cái gì đã biến mất

`src/` 17.440 → 15.839 dòng. 507 test xanh trước và sau. Nếu bạn nhớ bản cũ, đây là bảng
đối chiếu.

| Đã xoá | Vì sao |
|---|---|
| `guardrails.post_check` + 9 hàm `_apply_*` (251 dòng) | nhận `AdviseOutput`; output chuyển sang prose streaming nên không còn object để đưa vào. Chỉ test gọi |
| `scope_check` + `_scope_refusal_if_out_of_scope` (115) | soft OOS đã thuộc về intaker/SemanticRouter |
| `OodDetector` (129) | `di.py` truyền `enable_ood=False` — chưa từng chạy trong production. File đổi tên `ood_detector.py` → `pii.py` |
| `DrugChecker` + OpenFDA (358) | ba luật duy nhất nó còn đóng góp giờ viết thẳng trong `medication_safety_refusal`. Kèm bỏ một HTTP call đồng bộ 5s trong cổng an toàn |
| Endpoint `/ws/chat` + `_parse_sse_frame` (89) | frontend chỉ dùng SSE, không client nào gọi |
| `llm/qa_generator.py` (328) | 0 tham chiếu; việc này đã chuyển sang `datagen/` |
| `mmr_select`, `retrieve_with_mmr`, `expand_context` (115) | không nối vào pipeline. Kéo theo `import numpy` khỏi `retriever.py` |
| 5 file Protocol + `pipeline/` + `vision/` (48) | interface một implementation |
| `SessionStore` in-memory — **giữ lại** | 45 test dùng làm fixture. Nhưng fallback ngầm trong production đã bỏ |
| `build_retrieval_query`, teencode expansion | teencode chết theo khi caller cuối cùng biến mất |
| `get_asked_fields` / `mark_fields_asked` | cơ chế "đừng hỏi lại" đã gỡ ở runtime |
| `guardrails_scope_mode`, `config/ood_centroid.json` | chỉ điều khiển code chết |

**Ba bug hành vi đã sửa:**

1. `compute_route_flags` gọi thiếu `user` → `has_red_flags` luôn False trên đường unified.
2. `_contains_any` khớp chuỗi con với term 2 ký tự → `"con chó"` bị tính là câu hỏi về mụn.
3. `UnifiedIntake` cache một-ô dùng chung → intaker chạy gấp đôi dưới tải.

**Hai lỗi over-block đã sửa:**

- Cặp `benzoyl peroxide + tretinoin` bị `DrugChecker` liệt là `interactions`, mà
  `interactions_triggered` là điều kiện **chặn** — nên phác đồ chuẩn sáng BPO / tối
  tretinoin bị từ chối tư vấn.
- `"pregnancy" in mentioned_terms` bị coi là bằng chứng đang mang thai → 4/5 câu bị chặn
  sai (§1c).

**Một luật được giữ lại có chủ đích:** regex liều lượng (`dose_re` + `self_use_re`) được
port từ `_apply_medication_safety` sang `_safety.get_safety_suffix`. Đây là luật duy nhất
trong tầng hậu kiểm cũ mà `get_safety_suffix` chưa có, và nó bắt mẫu nguy hiểm nhất: model
tự sinh ra một liều cụ thể mà người dùng chưa hề hỏi. Xem `tests/test_safety_dose_rule.py`.

**Hai luật bị bỏ có chủ đích:** kháng sinh đơn trị liệu và tương tác chéo trên text.
Cả hai là luật đúng nhưng chưa đo được model có vi phạm thật không. Nếu eval cho thấy có,
chúng phải quay lại.

**Bảo mật:** `/admin/*` và `/debug/trace` từng mở toang khi `API_KEY` rỗng — middleware cũ
coi khoá rỗng là "tắt xác thực". Nay có `require_admin` gắn ở cấp router, **fail closed**.
