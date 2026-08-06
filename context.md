# AcneLLM — Project Context

Chatbot tư vấn da mụn tiếng Việt. Local-first: LLM chạy qua Ollama, RAG hybrid trên
ChromaDB + BM25. Cloud API (OpenAI/DeepSeek) **chỉ** dùng cho eval judge và datagen,
không nằm trên đường chạy của người dùng.

> Tài liệu này viết lại từ code thực tế (branch `codex/simplify-chat-pipeline`, 2026-08-06),
> không dựa trên bản context cũ. Mọi mục đều trỏ tới file có thật. Xem §14 để biết
> bản cũ sai chỗ nào.

---

## 1. Mindset của repo — đọc phần này trước

Sáu nguyên tắc rút ra từ chính comment trong code, không phải khẩu hiệu. Đọc để hiểu
tại sao code trông như vậy trước khi định "dọn dẹp" nó.

**a. Một đường chuẩn bị duy nhất cho mọi entrypoint.**
`chat/orchestrator.py` là "single preparation path shared by SSE, WebSocket, evaluation,
and debug trace". SSE, WS, `/debug/trace`, eval adapter đều gọi `prepare_chat_turn()`.
Không có đường thứ hai. Hệ quả: `/debug/trace` cho ra **đúng** cái production làm, không
phải mô phỏng lại.

**b. Rule không được tự viết câu trả lời.**
Guardrail quyết **nội dung** (ruling), generator viết **câu chữ**. Refusal không còn
short-circuit trả chuỗi cứng — nó chuyển thành `refuse_user.j2` rồi để LLM diễn đạt,
bản disclaimer cứng được nối lại ở `_safety.get_safety_suffix`
(`chat/orchestrator.py:98-108`, `chat/runtime.py:100-115`).

**c. LLM-first, rule là lưới an toàn — không phải ngược lại.**
Mọi tầng thông minh đều có ladder fallback rõ ràng và fallback **không bao giờ bị gỡ**.
Route: unified LLM → semantic kNN → rule. Extract: unified LLM → rule. Fail ở tầng nào
thì `log_pipeline_stage(..., level="WARNING", fallback=...)` ghi lại, pipeline chạy tiếp.

**d. Đừng trả giá suy luận trước khi biết có cần không.**
Extractor 3B **chỉ** chạy sau khi route ra `advise|knowledge` (`chat/intake.py:737`).
Trước đây nó chạy mọi turn và guardrail phán trên số của nó — nên "ngưng tretinoin rồi"
vẫn ra `medications=['tretinoin']` và bắn safety block. Pre-LLM chỉ cần `description`.

**e. Không đo bằng từ vựng.**
KB 60% Việt / 40% Anh nên mọi phép khớp từ đều thưởng cho đoạn cùng ngôn ngữ với câu hỏi,
bất kể nội dung. `grounding_support` (char-3gram dice) và `forbidden_claims` (khớp chuỗi,
0 lần kích hoạt / 770 dòng) đã bị gỡ khỏi eval vì lý do này. Xem `evaluation/eval_context.md` §6g.

**f. Ngưỡng phải ghi kèm thang đo của nó.**
Nhiều bug lịch sử là tune ngưỡng trên sai thang. `config.py` cố ý mang comment dài giải
thích *score này là xác suất hay logit, đo sau bước nào* — đừng cắt gọn chúng. Xem §11.

---

## 2. Stack thực tế

| Layer | Thành phần | Nguồn sự thật |
|---|---|---|
| Generator | `acne-generator` — Qwen2.5-7B-Instruct Q4_K_M + LoRA role, Ollama | `.env: LLM_MODEL`, `model/qwen25_acne_role_gguf_q4_k_m/Modelfile` |
| Fallback generator | `qwen2.5:3b` | `config.py: llm_fallback_model` |
| Unified Intake | `acne-intaker` — Qwen2.5-3B-Instruct Q4_K_M + LoRA, temp 0, num_ctx 2048 | `model/acne_intake_release/Modelfile` |
| Router (legacy arm) | `acnellm-intent` | `config.py: router_model` |
| Extractor (legacy arm) | `acne-extractor:1.5b` | `config.py: extractor_model` |
| Semantic router | kNN trên embedding, k=9, OOS distance 0.483609 | `chat/fallback/semantic_router.py` |
| Embedding | `AITeamVN/Vietnamese_Embedding` (dim 1024) | `config.py` |
| Reranker | `BAAI/bge-reranker-v2-m3` cross-encoder | `config.py` |
| Vector DB | ChromaDB — **24.393 chunk** | `data/chroma_db/` |
| Sparse | BM25 (`rank-bm25`), pickle + sha256 | `data/bm25_index.pkl` |
| API | FastAPI + uvicorn, SSE + WebSocket | `api/app.py` |
| Frontend | Next.js 15 + Tailwind + Zustand | `frontend/src/` |
| Session | **SQLite** `data/sessions.db`, TTL 1800s, 6 turn | `db/session_store.py` |
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
src/acne_llm/
├── api/
│   ├── app.py                 FastAPI + lifespan → build_container, CORS, middleware
│   ├── observability.py       APIKey / RateLimit / RequestLogging middleware, MetricsRegistry
│   └── routes/
│       ├── chat.py            /chat/stream (SSE), /ws/chat, /debug/trace, /chat/feedback
│       ├── health.py  kb.py  metrics.py  admin.py
├── chat/                      ★ trung tâm của repo
│   ├── orchestrator.py        prepare_chat_turn() — đường chuẩn bị DUY NHẤT; generate_prose()
│   ├── intake.py     (1017 dòng)  run_intake() — guardrail, route, extract, fold, completeness
│   ├── runtime.py             stream_chat_sse() — SSE, persist, audit
│   ├── unified_intake.py      UnifiedIntake — 1 model làm cả route + extract (mặc định)
│   ├── _intake_parse.py       parser khoan dung cho JSON của intaker
│   ├── _retrieval.py          retrieve_for_chat(), RRF merge, cap_per_source, evidence_quality
│   ├── _safety.py             get_safety_suffix()
│   ├── _terms.py              từ khoá dùng chung
│   ├── preprocess.py          prepare_user_text() → PreparedText; strip_accents, light_normalize
│   ├── completeness.py        check_completeness() → CompletenessResult
│   ├── confidence_hint.py     build_confidence_hint() — hedge field confidence thấp
│   ├── session.py    (742)    SessionStore, fold_history_facts, select_relevant_history
│   └── fallback/              ★ mọi thứ ở đây là LƯỚI AN TOÀN, không phải đường chính
│       ├── intent_router.py   route_intent() rule + RouteDecision + compute_route_flags
│       ├── semantic_router.py SemanticRouter — kNN embedding + soft OOS
│       ├── llm_router.py      LLMRouter (arm legacy) + RouterFallback
│       ├── llm_extractor.py   LLMExtractor (arm legacy) + ExtractorFallback
│       ├── rule_extractor.py  extract_with_confidence() → ExtractionConfidence
│       └── rule_normalizer.py (1975 dòng) normalize_chat_message() — rule NLP tiếng Việt
├── rag/
│   ├── retriever.py           HybridRetriever: dense+BM25 → RRF → trust_boost; retrieve_safety_pass
│   ├── vectorstore.py  sparse.py  embedder.py  reranker.py  chunker.py  cleaning.py
├── guardrails/
│   ├── runner.py     (832)    GuardrailRunner: pre_check, scope_check, medication_safety_refusal, post_check
│   ├── ood_detector.py        contains_pii(), mask_pii()
│   └── drug_checker.py
├── llm/
│   ├── ollama_backend.py      OllamaBackend — generate_text / stream_text, response_format
│   ├── prompt_builder.py      PromptBuilder (Jinja2) — context block, known_facts, route guidance
│   ├── language.py  qa_generator.py  base.py
├── schemas/                   core.py (UserInput/AdviseOutput/RetrievedChunk), clinical.py,
│                              extraction.py (ExtractionConfidence), kb.py
├── crawler/                   fetcher, playwright_fetcher, extractor, normalizer, dedup,
│                              quality_filter, discovery, checkpoint, sources/{pubmed,generic_html}
├── db/                        session_store.py (SQLite), audit.py, base.py
├── utils/                     retrieval_query.py, chunk_filter.py, logging.py (log_pipeline_stage),
│                              text_cleaning.py, fuzzy_match.py, hashing.py, timer.py
├── pipeline/                  base.py — wrapper cũ
├── vision/                    stub (MockVision)
├── di.py                      Container + build_container() — wiring toàn hệ
├── config.py                  Settings — SCHEMA + DEFAULTS (nguồn sự thật duy nhất)
└── cache.py                   DiskCache, cached_retrieve

evaluation/          ★ eval 3 khâu đang dùng (xem §12)
ablation/            ★ module ablation độc lập, mới hơn, chồng lấn với evaluation/ (xem §12.3)
datagen/             sinh SFT data cho intaker (intakedata/) và role/generator (roledata/)
scripts/             build_kb.py, crawl_all.py, build_intent_dataset.py, tune_extraction_thresholds.py…
config/prompts/      stream_user.j2, knowledge_user.j2, clarify_user.j2, reject_user.j2, refuse_user.j2
model/               Modelfile + GGUF + LoRA adapter (không commit GGUF)
tests/               41 file pytest
docs/                config_reference.md, config_layout.md, schema_mapping.md, history/ (prompt cũ)
frontend/src/        app/, components/chat/{ChatWindow,MessageBubble,SourceCard,ChunkDetailModal,
                     MessageInput}, hooks/useSSE.ts, stores/chatStore.ts
```

---

## 4. Đường chạy một tin nhắn — chi tiết theo code

### 4.1 Entrypoint

`GET /api/v1/chat/stream` → `runtime.stream_chat_sse` → `orchestrator.prepare_chat_turn`
→ `intake.run_intake`. WebSocket `/ws/chat` dùng cùng generator, bắc cầu qua
`asyncio.Queue(maxsize=64)` để stream từng frame thay vì buffer (`routes/chat.py:248-290`).

### 4.2 `run_intake()` — thứ tự CHÍNH XÁC (`chat/intake.py:582`)

```
①  Guard độ dài        4000 ký tự / 500 từ → ValueError (route trả 413)
②  prepare_user_text() → clean_text, clean_text_no_accent, teencode_replaced
③  store.get_history(session_id)
④  _resolve_mode()     auto → hybrid nếu c.rag_ready, ngược lại llm_only
⑤  base_user = UserInput(description=light_normalize(raw))     ← CHƯA trích xuất gì
⑥  _extract_safety_terms(clean_text, base_user)   ← map thẳng từ TEXT, không qua extractor
⑦  guardrails.pre_check(base_user)                → reject cứng "pre_check_invalid"
⑧  genital scope                                  → reject cứng, TRỪ mixed scope (có vùng mụn hợp lệ)
⑨  medication_safety_refusal(base_user)  [current_turn]   → refuse cứng
⑩  ROUTE  ─ ladder, xem §5
⑪  compute_route_flags(clean_text, history) → merge vào MỌI đường route
⑫  clarify downgrade: clarify + _has_established_case(history) → advise
⑬  intent == reject   → return ngay (llm_only, history=[], không extract)
⑭  intent == clarify  → select_relevant_history, return (effective_mode="clarify", không extract)
⑮  EXTRACT  ─ chỉ advise|knowledge, xem §6
⑯  guardrails.pre_check(base_user) LẦN 2 — full field sau khi đã trích xuất
⑰  medication_safety_refusal  [post_extract]
⑱  advise only: confirmed_profile ← build_confirmed_profile(threshold ≥ 0.82) → merge vào session
⑲  advise only: fold_history_facts(base_user, history)
⑳  medication_safety_refusal  [session_fold]     ← lần 3, phủ thuốc đã xác nhận từ turn trước
㉑  advise only: check_completeness(user, history, asked_fields, confidence)
㉒  normalized_query = build_current_turn_query(clean_text, selected_history)
    → IntakeResult
```

Ba lần gọi `medication_safety_refusal` là **cố ý**: current turn (trước route, chặn sớm),
post-extract (full field), session-fold (thuốc đã xác nhận ở turn trước). Bỏ bớt lần nào
cũng để lọt một lớp.

### 4.3 `prepare_chat_turn()` (`chat/orchestrator.py:52`)

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
hint = completeness_hint + confidence_hedge(field conf < 0.6)
  ↓
c.prompt.build(user, retrieval, template, history, route_metadata,
               completeness_hint=hint, confirmed_profile=…,
               max_context_chars=chat_max_context_chars)
  → PreparedChatTurn(system_prompt, user_prompt, retrieval, …)
```

`user_override` chỉ được nhận từ caller tin cậy (CLI/eval) và **chỉ** các fact an toàn
mới ảnh hưởng prompt (`orchestrator.py:66-89`).

### 4.4 `stream_chat_sse()` (`chat/runtime.py:60`)

```
prepare_chat_turn()
  → nếu route_flags có "progress_followup": increment_followup_count(session)
  → nếu route_flags có "crisis_signal": yield prefix đồng cảm TRƯỚC khi stream
  → c.llm.stream_text(system, user)   [knowledge: num_predict=-1, không hard-cap]
       ├ strip CJK từng token (guard rò tiếng Trung/Nhật/Hàn)
       └ yield event "token"
  → yield event "source" cho từng chunk (TOÀN VĂN, không cắt 220 ký tự)
  → get_safety_suffix()          → yield "token"   (knowledge bỏ generic disclaimer)
  → completeness.followup_question → yield "token" ĐÚNG MỘT LẦN
       + mark_fields_asked(session, missing_fields)   ← không hỏi lại turn sau
  → sess.append_turn(user: RAW message)  + append_turn(assistant: full text)
  → compute_evidence_quality(retrieval)
  → audit.log(AuditEntry)  — mask_pii nếu pii_detected
  → yield event "done" {mode, latency_ms, used_chunks, evidence_quality,
                        primary_intent, route_flags}
```

Turn `user` lưu **nguyên văn** người gõ, không phải bản đã preprocess (F10).

---

## 5. Routing — ladder ba tầng

`RouteDecision(primary_intent, confidence, source, reason_code, route_flags, turn_type)`.
`primary_intent ∈ {advise, knowledge, clarify, reject}`.

| # | Tầng | Điều kiện dùng | Thất bại → |
|---|---|---|---|
| 1 | `c.llm_router` — **UnifiedIntake** (`acne-intaker`) khi `INTAKE_MODE=unified`, hoặc `LLMRouter` khi legacy | luôn thử trước | `RouterFallback` → tầng 2 |
| 2 | `c.semantic_router` — kNN k=9 trên `data/intent_classify.train.jsonl`, OOS nếu cosine distance > 0.483609, ambiguity margin 0.08 | router LLM fail/thiếu | exception → tầng 3 |
| 3 | `route_intent()` rule (`fallback/intent_router.py`) | hai tầng trên fail | không có tầng 4 |

Chỉ tầng 3 mới cần chạy `normalize_chat_message()` + `extract_with_confidence()` — nên
fallback về rule đắt hơn, không rẻ hơn.

**Hai patch bắt buộc sau khi route (`intake.py:632-673`):**

- `compute_route_flags(clean_text, history)` merge vào **mọi** đường. Unified và semantic
  trả `route_flags=[]`, làm chết im lặng cảnh báo khẩn cấp (`_safety`) và guidance an toàn
  (`prompt_builder`). Cờ là tín hiệu văn bản nên không phụ thuộc router nào thắng.
- **clarify downgrade**: intaker 3B học multi-turn từ 180/180 mẫu đều gán `clarify`, nên
  mọi follow-up có history đều bị kéo về clarify. Khi phiên đã có case thật
  (`_has_established_case`), hạ xuống `advise` + flag `clarify_downgraded`.
  **Gỡ guard này sau khi datagen multi-turn cân lại nhãn.**

`route_flags` sinh ở `compute_route_flags` (`fallback/intent_router.py:285-298`):
`repeated_question`, `emotional_distress`, `crisis_signal`, `product_safety_check`,
`urgency_red_flag`, `progress_followup`, `multi_condition`. Thêm ở nơi khác:
`urgent_personal_case`, `partial_advise`, `low_route_confidence`, `mixed_genital_scope`,
`clarify_downgraded`, `medication_safety_block`, `pre_check_invalid`, `genital_scope`.

---

## 6. Extraction — Unified Intake

`UnifiedIntake` (`chat/unified_intake.py`) là **một inference phục vụ hai interface**:
`classify()` trả `RouteDecision`, `run()` trả `LLMExtractResult`. Cache 1 phần tử theo
`(clean_text, history_json)` nên gọi hai lần chỉ tốn một lượt suy luận.

- Prompt runtime `_RUNTIME_SYSTEM` **trùng byte** với `SYSTEM` trong
  `model/acne_intake_release/Modelfile` và `datagen/intakedata/system_prompt.canonical.txt`.
  Sửa một chỗ phải sửa cả ba, nếu không train/serve lệch nhau.
- Dùng `response_format="json"` (JSON mode) chứ **không** dùng grammar — llama.cpp không
  parse nổi nested `anyOf`-null, trả 400.
- Hậu kiểm duy nhất: parse được JSON object + `_validate_contract`. Sai enum/shape thì
  parser khoan dung ở `_intake_parse.py` **drop field**, không fallback: một field hỏng
  không đáng vứt cả inference.
- `intent` là ngoại lệ — sai enum thì raise, vì không route được thì không còn đường nào.
- History: tối đa 3 turn gần nhất, mỗi turn ≤ 300 ký tự, chỉ role `user`/`assistant`.
  `clean_text` bị cắt ở 4000 ký tự (`ponytail:` cắt thay vì fallback).

Schema trả về: `{intent, confidence, description, context, clinical}`, mọi scalar và mọi
phần tử list đều là `{"value":…, "confidence":0..1}`.

**Enum cứng** (đổi ở đây là đổi cả datagen + Modelfile + eval):
`lesion_types`: comedone, whitehead, blackhead, closed_comedone, papule, pustule, nodule,
cyst, scar, post_inflammatory_hyperpigmentation, other ·
`inflammation_level`: none, mild, moderate, severe, unknown ·
`lesion_distribution`: forehead, cheeks, chin, jawline, nose, around_mouth, back, chest,
shoulders, neck, t_zone, other · `skin_type`: dry, oily, combination, sensitive, normal, unknown.

---

## 7. Retrieval (`chat/_retrieval.py:retrieve_for_chat`)

```
query = intake.normalized_query        ← query CỦA LƯỢT HIỆN TẠI. Planner đã bị gỡ.
cache key = ("chat-query-v5", query, top_k, rerank_top_k, min_score, safety_terms)

① retriever.retrieve(query, top_k=15, mode="hybrid")
      dense (Chroma cosine, distance ≤ 0.60) + BM25 → RRF (k=60) → trust_boost theo source_type
② GUIDELINE PASS — chạy cho MỌI truy vấn
      retrieve_safety_pass(query, safety_terms=None, top_k=5,
                           source_types=(nice_guideline, aad_guideline, clinical_textbook))
      → RRF merge vào pool.  KHÔNG ép chunk nào vào câu trả lời; cross-encoder vẫn quyết.
③ SAFETY PASS — chỉ khi _has_medical_safety_terms() (thai kỳ, isotretinoin, kháng sinh…)
      Generic ingredient term KHÔNG kích hoạt (tiết kiệm ~50-100ms/request)
④ reranker.rerank(query, pool, top_k = chat_rerank_top_k * 3 = 15)
⑤ cap_per_source(max_per_source=1, limit=5)   ← cap SAU rerank, TRƯỚC OOD guard
      chunk bị loại giữ làm spill, lấp lại nếu chưa đủ limit → không bao giờ trả ít hơn
⑥ OOD guard mềm: giữ chunk có score ≥ chat_rerank_floor (0.50)
      không chunk nào đạt → return None → LLM trả lời KHÔNG dùng RAG
⑦ drop_acne_boils_mismatched_chunks → drop_body_region_mismatched_chunks → drop_noisy_chunks
   (KHÔNG dùng keyword-mismatch filter sau reranker — cross-encoder đã score rồi)

Không có reranker → _full_filter (noise + keyword mismatch)
```

`compute_evidence_quality`: avg score ≥ 0.90 → `strong`, ≥ 0.50 → `moderate`,
< 0.50 → `weak`, không retrieval → `unverified`.

⚠️ **Đổi logic retrieval thì PHẢI tăng version trong cache key.** Khoá cache chỉ gom
query + vài tham số, không phản ánh code. Quên tăng → cache trả kết quả cũ và bạn tưởng
thay đổi không có tác dụng. Lịch sử: v3 = thêm guideline pass, v4 = bỏ sigmoid lần hai,
v5 = cap_per_source.

---

## 8. Session & context (`chat/session.py`)

- `SQLiteSessionStore` — `data/sessions.db`, TTL 1800s, giữ 6 turn (`HISTORY_WINDOW_TURNS`).
- `NormalizedSnapshot` chỉ được persist khi `primary_intent == "advise"`
  (`runtime._snapshot_for_persistence`).
- **`select_relevant_history(message, intent, history, flags)`** — không đoán "có phải
  follow-up không" bằng whitelist tiền tố nữa (mọi câu trần thuật đều trượt whitelist và
  làm prompt mất sạch ngữ cảnh):
  - `knowledge` → chỉ **user turn gần nhất**, giữ prose cũ của bot ra ngoài prompt.
  - còn lại → cả cửa sổ 6 turn; `format_history_block()` cắt theo `HISTORY_CHAR_BUDGET=2000`.
  - turn genital luôn bị lọc bỏ.
- **`fold_history_facts(base_user, history)`** — chỉ chạy khi `advise`:
  last-write-wins cho scalar · ADDITIVE cho `lesion_types` / `distribution` / `red_flags` ·
  MAX theo `_SEVERITY_ORDER` cho `inflammation_level` · tôn trọng phủ định
  (`_mentions_stop`, `_NEGATE_PREGNANCY_TERMS`, `_STOP_PRODUCT_TERMS`).
- **`build_confirmed_profile`** — chỉ field có confidence ≥ `max(0.82, extract_min_field_conf)`
  mới được ghi vào profile phiên. Ngưỡng cao hơn ngưỡng completeness vì profile là
  "đã xác nhận + bất biến" trong prompt.
- `mark_fields_asked` / `get_asked_fields` — chống hỏi lại cùng một field.

---

## 9. Guardrails (`guardrails/runner.py`)

| Hàm | Chạy ở đâu | Tính chất |
|---|---|---|
| `pre_check(user)` | intake ⑦ và ⑯ | raise ValueError → reject cứng |
| `is_genital_scope` | intake ⑧ | hard reject, trừ mixed scope |
| `medication_safety_refusal(user, safety_terms)` | intake ⑨ ⑰ ⑳ | trả `AdviseOutput` → refuse |
| `scope_check` | API cũ, giữ cho caller trực tiếp/test | soft |
| `post_check(out, user)` | pipeline non-stream | drug checker, retinoid block, age, no-popping… |

Soft OOS **không** còn ở guardrails (`enable_ood=False` trong `di.py`) — nó thuộc về
`SemanticRouter` (ngưỡng khoảng cách kNN). `contains_pii` / `mask_pii` ở
`guardrails/ood_detector.py`, dùng lúc ghi audit.

Vùng mụn hợp lệ: mặt, trán, má, cằm, mũi, quai hàm, hàm, miệng, lưng, ngực, vai, cổ, gáy.

---

## 10. Prompt (`llm/prompt_builder.py` + `config/prompts/*.j2`)

`PromptBuilder.build()` ráp: context block (cắt theo câu, budget `chat_max_context_chars`)
+ `_known_facts_summary` + `_clinical_summary` + `_route_guidance(route_metadata)` +
`completeness_hint` + `confirmed_profile` + history block.

- `_escape_jinja` / `_sanitize_chunk_text` / `_sanitize_user_description` /
  `sanitize_history_turns`: chunk và text người dùng là **trust boundary** — chống prompt
  injection qua nội dung crawl. Đừng gỡ.
- `known_facts` được inject như "đã xác nhận + bất biến", nên field confidence < 0.6 phải
  đi kèm hedge từ `build_confidence_hint` (`orchestrator.py:120-124`).
- `llm_use_modelfile_system=True` (mặc định): **không** gửi system message qua API, để
  `SYSTEM` trong Modelfile tự lo — tránh hai system prompt chồng nhau.

---

## 11. Config — ba tầng, đừng trộn

| Tầng | Chứa gì | KHÔNG chứa gì |
|---|---|---|
| `model/**/Modelfile` | artifact-level: `FROM`, `TEMPLATE`, `SYSTEM`, stop token | `num_ctx`, `temperature`, `top_p` — Python cần quyền override per-request |
| `.env` | secret + giá trị khác theo máy/lần chạy (URL, path, device, model đang chạy) | hằng số tuning |
| `config.py` | **single source of truth cho SCHEMA + DEFAULTS** | secret |

### Knob quan trọng và thang đo của nó

| Key | Default | Cảnh báo |
|---|---|---|
| `chat_retrieve_top_k` | 15 | pool ĐƯA VÀO cross-encoder. Từng là 6/3 trong khi eval chạy 15/5 → đo một hệ, deploy hệ khác |
| `chat_rerank_top_k` | 5 | giữ lại sau rerank |
| `chat_guideline_top_k` | 5 | guideline pass, chạy mọi truy vấn |
| `chat_safety_top_k` | 5 | chỉ khi có medical safety term |
| `chat_max_chunks_per_source` | 1 | chunker chồng lấn 40 token → 2 chunk kề nhau gần trùng nội dung |
| `chat_max_context_chars` | 6000 | eval oracle dùng lại đúng số này |
| `chat_rerank_floor` | 0.50 | **xác suất thật** từ `CrossEncoder.predict()`. Ngưỡng 0.45→0.58 trước đây tune trên thang bị sigmoid hai lần ([0.500, 0.731]) |
| `reranker_min_sigmoid` | 0.30 | cùng thang xác suất; đúng chủ đề ~0.95-0.999, lạc đề < 0.1 |
| `chat_min_chunk_score` | 0.25 | ⚠️ chạy trên **hai thang khác nhau**: sau reranker là sigmoid (vô tác dụng vì `reranker_min_sigmoid` đã cắt), không reranker là `fusion*boost` — chỉ nhánh fallback mới có ý nghĩa |
| `dense_max_distance` | 0.60 | cosine distance Chroma ≈ similarity 0.40 |
| `extract_min_field_conf` | 0.60 | completeness coi field "đã có" khi ≥ ngưỡng |
| `route_min_confidence` | 0.55 | routing dưới ngưỡng → clarify |
| `llm_keep_alive` | -1 | Ollama parse như Go duration: int hoặc string **có unit**. `"-1"` dạng string → 400 |
| `ollama_generate_timeout` | 30.0 (config) / 300 (.env máy CPU) | thấp cố ý để latency lộ ra thay vì bị che |

Xem thêm `docs/config_layout.md`, `docs/config_reference.md`, `.env.baseline`.

---

## 12. Evaluation

### 12.1 `evaluation/` — 3 khâu (đang dùng)

Giả thiết nền: hệ thống có 3 khâu **intaker → RAG → generator**; câu trả lời dở thì phải
biết lỗi ở khâu nào.

| Khâu | Đo gì | Judge | Lệnh |
|---|---|---|---|
| 1 | intaker rút đúng 15 slot không | không | `python -m evaluation.runners.run_intake` |
| 2 | tài liệu retrieval mang về có dùng được không | có | `python -m evaluation.runners.run_retrieval` |
| 3 | thay/tắt từng khâu, câu trả lời chênh bao nhiêu | có | `python -m evaluation.runners.run_ablation` |

**Khâu 2 KHÔNG dùng recall@k trên chunk vàng** — chấm theo danh tính chunk là chấm oan
(nhiều đoạn cùng chủ đề). Judge hỏi thẳng "đoạn này liên quan không, gộp lại đủ trả lời
không" → chạy được trên bất kỳ tập câu hỏi nào, kể cả câu hỏi thật.
`relevant_chunk_ids` giờ chỉ là **cơ chế** bơm context cho arm `ROR`, không còn là **thước đo**.

Arm = 3 ký tự `[intaker][rag][generator]`, `R`=thật · `O`=hoàn hảo · `N`=tắt (chỉ hợp lệ ở RAG).
Mặc định 6 arm: `RRR RNR ROR ORR RRO RNO`.

Chín mặt điểm, không mặt nào đếm từ: `answer_quality`, `role_tone`, `context_relevance`,
`context_precision`, `context_sufficiency`, `ranking_quality` (nDCG trên chính điểm judge),
`groundedness`, `safety_pass`, `refusal_fidelity`. Safety **luôn báo riêng**, không gộp vào
điểm chất lượng. Arm `RNR`/`RNO` có 5 mặt context = `None` (không phải 0).

**Bất biến — vi phạm là kết quả không hợp lệ:** không fallback model · không đụng data
production (audit/session DB trong thư mục tạm, cache tắt) · dataset frozen bằng sha256
`MANIFEST.json` · judge mù (không đưa tên model vào prompt) · generator ghi tường minh vào
artifact · mỗi artifact một dataset + baseline của chính nó.

Dataset: `evaluation/datasets/eval_set.v3.jsonl` (197 dòng) ·
`datagen/intakedata/output/intake/intake.val.jsonl` (400 mẫu held-out).
Checkpoint: `rows.jsonl` append-only + `.fingerprint`; chạy lại cùng lệnh sẽ chạy tiếp.

Thiết kế đầy đủ: **`evaluation/eval_context.md`** — sửa thiết kế thì sửa file đó trước.

### 12.2 Nợ đã biết của eval

- **Judge chưa hiệu chỉnh.** `judges/calibrate.py` có sẵn (Cohen's κ trọng số bậc hai +
  Spearman) nhưng chưa chạy. Không có κ thì con số khâu 2 không phòng thủ được.
- Câu hỏi sinh ngược từ chunk luôn trả lời được từ KB → `ROR − RRR` là **cận trên**.
- Không có số retrieval nội tại → không tuyên bố được "hybrid+rerank hơn BM25 bao nhiêu".
- `answer_quality` vẫn gộp "sai" và "thiếu" (Med-PaLM tách hai trục) — món nợ có ý thức.

### 12.3 `ablation/` — module song song ở root

README của nó nói thẳng: *"Replaces `evaluation/` with one question and one method"*,
không import gì từ `evaluation/`, chỉ chạm product code qua `repo_adapter.py` (4 hàm, 3 seam),
mặc định chạy **đủ lattice 2³ = 8 arm** (thay vì 6). Kết quả trong `ablation/runs/`.

⚠️ Hai module cùng đo một thứ với hai định nghĩa arm khác nhau đang tồn tại song song.
Trước khi trích số vào luận văn, phải quyết định module nào là nguồn sự thật —
số của hai bên **không so trực tiếp được**.

---

## 13. Datagen (`datagen/`)

| Module | Sinh cho | Output |
|---|---|---|
| `datagen/intakedata/` | model `acne-intaker` (extract + route trong 1 call) | `output/intake/intake.{train,val,smoke}.jsonl` (4.000 mẫu mục tiêu, val 400) |
| `datagen/roledata/` | model role/generator | `datagen/output/` |

Mọi record dùng `system_prompt.canonical.txt` **byte-identical** với Modelfile và
`_RUNTIME_SYSTEM` trong `unified_intake.py`. Ghi append-only sau khi qua gate: schema +
enum + negation-leak + empty-discipline (`gates.py`). Phải chọn đúng một mode; không
truyền mode thì không sinh gì. `--yes` bắt buộc với mọi mode tốn phí provider.

```bash
pytest -q datagen/intakedata                             # offline, miễn phí
python -m datagen.intakedata.pipeline --smoke --yes -v   # 1 record/case
python -m datagen.intakedata.pipeline --full --yes -v    # 4.000 record, tốn phí
```

---

## 14. Dev workflow

```bash
./tasks.sh install          # venv + deps (Linux dùng .venv-linux, không đè .venv của Windows)
./tasks.sh serve            # tự start ollama, kill port 8000, uvicorn --reload
./tasks.sh frontend         # next dev :3000
./tasks.sh run-all          # ollama + backend + frontend
./tasks.sh build-kb         # data/raw/documents.jsonl → chroma + bm25
./tasks.sh crawl [Source]   # crawl → data/raw/documents.jsonl (1-3 giờ)
./tasks.sh test             # pytest -v (41 file)
./tasks.sh eval [N]         # python -m evaluation.full_evaluation --limit N
./tasks.sh lint  stats  chat  docker-{build,up,logs,down}  clean-{kb,raw,finetune,logs}
```

Windows: `scripts\RUN.ps1` (mở 3 cửa sổ PowerShell), `scripts\KB.ps1`.

Eval nhanh:

```bash
python -m evaluation.full_evaluation --smoke              # 10 mẫu/bước
python -m evaluation.full_evaluation --skip ablation      # chỉ khâu 1, miễn phí
python -m evaluation.runners.run_ablation --arms RRR,RNR --limit 5
```

Debug pipeline không tốn LLM: `GET /api/v1/debug/trace?message=...` — trả 8 stage
(preprocess → normalize → confidence → guardrails → route → completeness → retrieve →
prompt), read-only, dừng ngay trước bước stream. Dùng `pipeline_simulator.html` để xem.

Endpoint: `/api/v1/chat/stream` · `/ws/chat` · `/api/v1/chat/feedback` ·
`/api/v1/health` · `/api/v1/kb/*` · `/api/v1/admin/*` · `/metrics` · `/docs`.

---

## 15. Bẫy đã biết — đọc trước khi sửa

1. **Cache key retrieval** — đổi logic mà quên tăng `chat-query-vN` → kết quả cũ, tưởng
   thay đổi vô tác dụng.
2. **`chat_min_chunk_score` chạy trên hai thang** — chỉ có nghĩa ở nhánh không reranker.
3. **Score của reranker là xác suất, không phải logit.** Đừng sigmoid lần nữa. Mọi ngưỡng
   tune trước tháng 7 nằm trên thang cũ [0.500, 0.731].
4. **`compute_route_flags` phải merge sau MỌI đường route** — unified/semantic trả `[]`,
   quên merge là chết im lặng cảnh báo khẩn cấp.
5. **Guard `clarify_downgraded` là tạm** — do datagen multi-turn gán 180/180 nhãn clarify.
   Gỡ sau khi cân lại dataset.
6. **`_RUNTIME_SYSTEM` phải trùng byte với Modelfile và `system_prompt.canonical.txt`** —
   ba nơi, sửa một là lệch train/serve.
7. **Extractor chạy SAU route, không phải trước.** Đảo lại sẽ khôi phục bug
   "ngưng tretinoin rồi" vẫn bị safety block.
8. **`known_facts` inject như bất biến** — field confidence thấp bắt buộc phải hedge.
9. **Comment ngưỡng trong `config.py` là tài liệu, không phải rác.** Chúng ghi lại chính
   xác bug nào đã xảy ra vì tune sai thang.
10. **Guideline pass không ép chunk vào câu trả lời** — nó chỉ đảm bảo 973 chunk khuyến cáo
    được cross-encoder *nhìn thấy*. Đừng đổi thành hard-inject.
11. **Marker `ponytail:` trong code** = đơn giản hoá có ý thức, kèm trần chịu đựng và đường
    nâng cấp. Đọc trước khi "sửa cho tử tế".

---

## 16. Bản context.md cũ sai chỗ nào

Bản trước (10/07) mô tả kiến trúc đã không còn tồn tại. Nếu bạn đọc nó ở đâu đó, đây là
danh sách đối chiếu:

| Bản cũ nói | Thực tế |
|---|---|
| `chat/normalizer.py` | → `chat/fallback/rule_normalizer.py`, và chỉ còn là fallback |
| `chat/intent_router.py` | → `chat/fallback/intent_router.py`, tầng 3 của ladder |
| `chat/_prompt.py build_prompt()` | không tồn tại — chọn template ở `orchestrator.py` |
| `llm/clinical_planner.py`, `llm/query_expander.py` | **đã gỡ**. Query retrieval nay là `build_current_turn_query` |
| `CHAT_USE_LLM_PLANNER` | không còn trong `config.py` |
| `db/jsonl_session_store.py`, "JSONL per session" | → `db/session_store.py` SQLite `data/sessions.db` |
| `src/acne_llm/eval/` (judge.py, metrics.py) | → thư mục `evaluation/` ở root |
| `scripts/eval_rag.py`, Hit@k/MRR/NDCG | **đã gỡ** — xem §12.1 tại sao bỏ recall@k |
| Micro-classifier `qwen2.5:0.5b` | → `acne-intaker` 3B (unified) hoặc `acnellm-intent` (legacy) |
| `LLM_MODEL=acnellm-v2-q4` | → `acne-generator` |
| Không nhắc `datagen/`, `ablation/`, semantic router, confirmed_profile, guideline pass | tất cả đều đang chạy |

`README.md` cũng còn vài chỗ lệch: nó ghi `LLM_MODEL=acnellm-role`, `INTAKE_MODEL=acne-intake`
(thiếu `r`), và liệt kê `llm/ ... planner` trong cây thư mục.
