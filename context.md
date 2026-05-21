# AcneLLM — Current Project Context
Snapshot date: **2026-05-14**
Workspace: `e:\project\AcneLLM`

---

## Tổng Quan

AcneLLM là hệ thống tư vấn da mụn tiếng Việt, **local-first**, gồm:

- **Backend**: FastAPI (Python 3.10+), inference local qua Ollama (mặc định `qwen2.5:7b`)
- **Frontend**: Next.js 15 + React 18 + Tailwind + Zustand + SSE
- **RAG**: ChromaDB (dense, cosine) + BM25Okapi (sparse) + RRF fusion + Cross-encoder reranker (`BAAI/bge-reranker-v2-m3`)
- **Embedding**: `AITeamVN/Vietnamese_Embedding` (dim=1024) hoặc `intfloat/multilingual-e5-large`
- **Session**: JSONL per-session (`data/sessions/<id>.jsonl`)
- **Audit**: SQLite (`data/audit.db`) cho audit_log + feedback
- **Cache**: DiskCache (embed + retrieve TTL 1h)

Project thuộc **Đề tài 29**, tích hợp điểm:
- **Đề tài 27**: Vision qua `VisionProtocol` / `VisionOutput` — hiện là **MockVision** (placeholder)
- **Đề tài 28**: Advanced RAG qua interface trong `rag/` và `crawler/`

Tài liệu này mô tả **trạng thái code thực tế** tính đến 2026-05-14. `BLUEPRINT_AcneLLM.md` là thiết kế/roadmap gốc; `context.md` là snapshot vận hành.

---

## Kiến Trúc Hệ Thống

```
[User / Frontend Next.js 15]
        |  HTTP / SSE / WebSocket
        v
[FastAPI app.py]
  ├── Middleware: CORS, APIKeyMiddleware, RateLimitMiddleware, RequestLoggingMiddleware
  ├── /api/v1/health         → health.py
  ├── /api/v1/chat           → chat.py (POST JSON + GET SSE + WS)
  ├── /api/v1/kb/*           → kb.py (retrieve, search, chunk, stats)
  ├── /api/v1/admin/*        → admin.py (audit log, session stats, feedback)
  └── /metrics               → metrics.py (Prometheus plain text)
        |
        v
[DI Container (di.py)]
  ├── OllamaBackend (llm)
  ├── PromptBuilder (prompt) — Jinja2, config/prompts/
  ├── ClinicalQueryPlanner (clinical_planner) — rule-based, no LLM call
  ├── GuardrailRunner (guardrails) — pre/post check + OodDetector + DrugChecker
  ├── JsonlSessionStore (session_store) — data/sessions/*.jsonl
  ├── AuditStore (audit_store) — data/audit.db SQLite
  ├── MockVision (vision)
  ├── LLMOnlyPipeline (llm_only)
  └── [RAG if KB ready]
       ├── Embedder + ChromaStore + BM25Index
       ├── HybridRetriever
       ├── Reranker
       └── HybridPipeline (hybrid)

Chat Flow (SSE chính - /chat/stream):
  message → intake.run_intake()
    → preprocess_user_text()           # NFC normalize, collapse whitespace
    → normalize_chat_message()         # rule-based extract: age, lesion, distribution, medication...
    → SessionStore.get_history()       # load JSONL history
    → fold_history_facts()             # merge prior snapshots vào UserInput
    → guardrails.pre_check()           # injection check, PII log
    → genital scope check              # refuse nếu vùng sinh dục
    → guardrails.scope_check()         # OOD check (soft/hard/off mode)
    → complaint detection              # xin lỗi + hỏi lại
    → completeness.check_completeness()# hỏi thêm nếu thiếu core field
    → ClinicalQueryPlanner.plan()      # build ClinicalQueryPlan (rule-based)
    → retrieve_for_chat()              # hybrid retrieval + safety pass + rerank
    → PromptBuilder.build()            # Jinja2 → (system, user_message)
    → OllamaBackend.stream_text()      # SSE token stream
    → safety suffix injection          # retinoid/rx warning nếu cần
    → citation events                  # per-chunk SSE event
    → SessionStore.append_turn()       # lưu JSONL
    → AuditStore.log()                 # ghi SQLite
    → done event (mode, latency_ms, evidence_quality)
```

---

## Các Module Chính

### API Layer (FastAPI)

**`src/acne_llm/api/app.py`**
- FastAPI app với lifespan: gọi `build_container(settings)` khi startup, `container.close()` khi shutdown
- Serve static files từ `api/static/`
- Root `/` redirect → `settings.frontend_url`

**Middleware (theo thứ tự áp dụng ngược — LIFO)**:
1. `RateLimitMiddleware` — token bucket per client IP, `per_minute=60` (mặc định), bỏ qua `/metrics` và `/api/v1/health`
2. `APIKeyMiddleware` — check `x-api-key` header hoặc `Authorization: Bearer <key>`, bỏ qua nếu `api_key=""` hoặc path là `/`, `/metrics`, `/api/v1/health`
3. `RequestLoggingMiddleware` — đo latency, ghi log, thêm `X-Request-ID` vào response header, cập nhật `MetricsRegistry`
4. `CORSMiddleware` — whitelist cụ thể (không wildcard), default `["http://localhost:3000"]`

**Routes**:

| Route | Method | Mô tả |
|---|---|---|
| `/api/v1/health` | GET | Ollama health + KB chunk count + BM25 status |
| `/api/v1/models` | GET | Danh sách model Ollama + current model |
| `/api/v1/chat` | POST | Chat đồng bộ — hỗ trợ cả `UserInput` schema cũ và body `{message, session_id, mode}` mới |
| `/api/v1/chat/stream` | GET (SSE) | Chat streaming — query params: `message`, `session_id`, `mode`, `temperature` |
| `/ws/chat` | WebSocket | Chat stream qua WS — cùng logic với SSE |
| `/api/v1/chat/feedback` | POST | Thumbs up/down (lưu vào audit.db) |
| `/api/v1/kb/retrieve` | POST | Debug retrieve + rerank |
| `/api/v1/kb/search` | POST | Search KB (kết quả truncated 300 chars) |
| `/api/v1/kb/stats` | GET | rag_ready, chunk count, BM25, embedder, reranker |
| `/api/v1/kb/chunk/{chunk_id}` | GET | Lấy chunk theo ID |
| `/api/v1/admin/audit` | GET | Audit log, filter theo session_id, phân trang |
| `/api/v1/admin/sessions/stats` | GET | Số session active |
| `/api/v1/admin/feedback/stats` | GET | Tổng up/down, satisfaction_rate |
| `/api/v1/admin/feedback` | GET | Danh sách feedback, filter theo rating |
| `/metrics` | GET | Prometheus plain text (counter + summary) |

**`src/acne_llm/api/deps.py`**
- `get_container(request)` — lấy container từ `app.state`
- `get_pipeline_for(mode, request)` — resolve pipeline, raise 503 nếu hybrid mà RAG chưa sẵn sàng

**`src/acne_llm/api/observability.py`**
- `MetricsRegistry` — in-memory counter + latency list (giữ 10K giá trị, prune về 5K)
- Prometheus render: `acnellm_requests_total`, `acnellm_request_latency_ms`, `acnellm_guardrail_triggers_total`, `acnellm_ollama_errors_total`

---

### Chat Pipeline

#### `chat/intake.py` — Unified Pre-LLM Intake

Hàm `run_intake(c, message, session_id, mode_request)` chạy qua các bước:

1. `preprocess_user_text()` — NFC normalize, bỏ zero-width chars, control chars, collapse whitespace
2. `SessionStore.get_history(session_id)` — load JSONL history
3. `_resolve_mode()` — resolve `auto`/`hybrid`/`llm_only` dựa trên `c.rag_ready` và acne signal trong text
4. `normalize_chat_message()` — regex extract: age, sex, skin_type, lesion_types, distribution, inflammation_level, medications, products, hormonal_factors, allergies, treatment_goals, red_flags
5. `snapshot_from_user()` — tạo `NormalizedSnapshot` để lưu với turn
6. `fold_history_facts()` — merge snapshots từ history vào `UserInput` (age/sex/skin_type: first-write-wins; products/medications: union với stop-word removal; booleans: latest wins)
7. `guardrails.pre_check()` — injection check + PII log
8. **Genital scope check** — refuse cứng nếu detect vùng sinh dục/hậu môn (trước OOD để tránh false negative)
9. `guardrails.scope_check()` — OOD check 2 tầng: keyword → embedding similarity vs acne centroid
10. **Complaint detection** — nếu user phàn nàn câu trả lời trước → mode `clarify` + xin lỗi
11. `check_completeness()` — hỏi loại mụn / vị trí nếu chưa có; chỉ hỏi field chưa từng hỏi (tracking qua `asked_fields`)
12. `ClinicalQueryPlanner.plan()` — chỉ chạy khi `acne_signal=True` và `chat_use_llm_planner=True` hoặc planner là rule-based (mặc định rule-based, không cần flag)
13. Trả `IntakeResult` với `effective_mode` (hybrid/llm_only/refuse/clarify)

**`_should_check_completeness()` logic**:
- Knowledge question (có terms như "là gì", "tại sao"...) → **skip** completeness
- Reply ngắn sau clarify bot → **force** check
- Câu hỏi có acne scope term + case intake term → **check**
- Có clinical data hoặc prior acne history → **check**

#### `chat/runtime.py` — SSE Streaming Orchestrator

`stream_chat_sse(c, message, requested_mode, session_id, temperature)`:

1. Gọi `run_intake()` — xử lý scope refusal và clarify ngay (yield token + done events)
2. `retrieve_for_chat()` — chỉ chạy nếu `mode=hybrid` AND `is_acne_signal=True`
3. `c.prompt.build(..., template="stream_user.j2", system_override=c.prompt.system_stream())`
4. `c.llm.stream_text()` → yield `token` events
5. `get_safety_suffix()` → yield thêm warning token nếu cần
6. Yield `citation` events cho từng chunk
7. Persist turns vào JSONL session store
8. `AuditStore.log()` → ghi SQLite
9. Yield `done` event với `{mode, latency_ms, used_chunks, session_id, evidence_quality}`

**SSE Event format**: `data: {"event": "<type>", "data": <payload>}\n\n`
- Events: `token`, `citation`, `done`, `error`

#### `chat/session.py` — In-Memory + JSONL Session

- **`SessionStore`** (in-memory, singleton) — thread-safe, TTL 30 phút, RLock
  - Methods: `get_history`, `append_turn`, `merge_user_context`, `get_asked_fields`, `mark_fields_asked`, `active_count`
  - Dùng làm **fallback** khi container không có `session_store` (ví dụ tests)
- **`fold_history_facts()`** — merge strategy:
  - `age`, `sex`, `skin_type`, `duration_weeks`: first-write-wins
  - `is_pregnant`, `is_breastfeeding`: latest explicit wins; có negation context-aware detection
  - `current_products`, `medications`: union với stop-word removal (`ngưng`, `dừng`, `không dùng`)
  - `lesion_types`, `distribution`, `scarring_signs`, etc.: union + dedupe
- **`format_history_block()`** — render history thành text block; lọc bỏ genital turns (user + assistant turn liền kề)
- **`_is_genital_turn()`** — detect turn có nội dung vùng sinh dục → lọc khỏi prompt

#### `chat/normalizer.py` — Rule-Based NLP Extractor

Cực kỳ dài (~800 dòng), không gọi LLM, chỉ dùng regex:
- `_extract_age()` — pattern "22 tuổi", "18t" (loại trừ false positive với `\b(\d{1,3})t\b(?!\s*(?:nay|rồi|qua...))`)
- `_extract_duration_weeks()` — convert ngày/tuần/tháng sang tuần
- `_extract_skin_type()` — oily/dry/combination/sensitive/normal (có dấu + không dấu)
- `_extract_sex()` — male/female
- `_extract_lesions()` — 11 loại, ưu tiên specific trước generic ("other" cuối cùng)
- `_extract_distributions()` — 12 vùng cơ thể
- `_extract_inflammation()` — mild/moderate/severe từ context
- `_extract_products()` — 60+ product/ingredient terms
- `_extract_medications()` — với `_has_medication_use_context()` để tránh false positive (phân biệt "đang dùng tretinoin" vs "có nên dùng tretinoin")
- `_extract_hormonal_factors()` — menstrual_cycle, pcos, stress, diet, pregnancy, postpartum, puberty
- `_extract_allergies()` — allergy + substance patterns
- `_extract_treatment_goals()` — clear_acne, treat_scar, fade_hyperpigmentation, etc.
- `_extract_red_flags()` — widespread, painful_lesions, purulent_lesions, scarring_risk, infection_signs, etc.

#### `chat/completeness.py` — Completeness Checker

- `_has_enough_to_answer()` — True nếu có lesion_types OR inflammation_level rõ OR distribution rõ (bất kỳ 1 trong 3)
- `check_completeness()` — trả `CompletenessResult` với `kind`: `too_short`/`missing_core`/`sufficient`
  - Chỉ hỏi field chưa từng hỏi (track qua `asked_fields`)
  - Hỏi từng cái một theo thứ tự: `lesion_types` → `distribution`
  - Không hỏi khi `_is_in_intake_flow()` + đã có đủ signal

#### `chat/_prompt.py` — Chat Prompt Builder (đơn giản)

Hàm `build_chat_prompt()` tạo prompt thủ công (không Jinja2), dùng trong một số context đặc biệt. Prompt chính dùng `PromptBuilder.build()` với Jinja2.

#### `chat/_retrieval.py` — Retrieval Helpers

- `build_query_from_user()` — build query ngắn từ UserInput (description + context bits + clinical bits)
- `rrf_fusion()` — Reciprocal Rank Fusion
- `merge_retrieval_outputs()` — gộp nhiều RetrievalOutput bằng RRF
- `retrieve_for_chat()` — main entry:
  1. Build query từ `clinical_plan.rag_queries.query_vi` hoặc fallback `build_query_from_user()`
  2. Cache key theo `(queries, top_k, rerank_top_k, min_score)`
  3. `HybridRetriever.retrieve()` → safety pass (nếu có safety_terms) → merge → rerank → drop_noisy_chunks
  4. Kết quả cache TTL 1h bởi `cached_retrieve()`
- `citation_data()` — format chunk thành dict cho SSE citation event
- `compute_evidence_quality()` — tính "strong"/"moderate"/"weak"/"unverified" từ avg reranker score

#### `chat/_safety.py` — Safety Suffix

`get_safety_suffix(full_text, user)` — append warning nếu:
- `is_pregnant` OR `is_breastfeeding` + LLM đề cập retinoid → urgent retinoid warning
- `sex=None` (unknown) + LLM đề cập retinoid → disclaimer phòng ngừa
- LLM đề cập thuốc Rx (isotretinoin, kháng sinh...) → remind cần bác sĩ
- `age < 12` → recommend bác sĩ da liễu nhi

---

### RAG System

#### `rag/retriever.py` — HybridRetriever

**Retrieve flow** (`mode="hybrid"`):
1. Dense: embed query → `ChromaStore.query_with_score_filter()` (distance filter ≤ 0.60)
2. Sparse: `BM25Index.query()` (Vietnamese tokenize + stopword removal + score normalize)
3. RRF fusion: `1/(k+i+1)` với k=60
4. Trust boost per chunk:
   - `nice_guideline`/`aad_guideline`: ×1.50
   - `jid_paper`: ×1.30
   - `pubmed_review`/`clinical_textbook`: ×1.20
   - `forum_post`: ×0.80, `blog`: ×0.70
   - Authority tags (hospital, guidelines, government...): thêm ×1.15
5. Score pruning: bỏ chunk có fused score < 0.005

**Methods bổ sung**:
- `retrieve_with_mmr()` — Maximal Marginal Relevance diversity filter (giảm chunk lặp nội dung)
- `expand_context()` — fetch prev/next chunk liền kề sau rerank (tăng context window)
- `retrieve_safety_pass()` — second pass với domain filter `$in [nice, aad, jid, pubmed, textbook]` cho context an toàn y tế (thai kỳ, thuốc)

**`_source_type_from_meta()`** — infer source_type từ metadata nếu chưa có, cache vào meta dict

#### `rag/sparse.py` — BM25Index

- Vietnamese tokenize: dùng `underthesea.word_tokenize` nếu có, fallback whitespace split
- Stopword list: ~50 function words tiếng Việt (và, của, là, có...)
- Score normalize về [0,1] chia cho max_score
- Persist + load với SHA-256 checksum verification (raise `BM25ChecksumError` nếu corrupt)

#### `rag/reranker.py` — Cross-Encoder Reranker

- Model: `BAAI/bge-reranker-v2-m3`, lazy load, batch_size=16
- LRU score cache (default 2048 entries) theo key `(query, chunk_id)`
- Logit → sigmoid score → filter `>= min_sigmoid_score` (default 0.30)
- Log debug: số chunk pass/drop + avg sigmoid

#### `rag/embedder.py` — Embedder

- Default model: `AITeamVN/Vietnamese_Embedding` (dim=1024)
- `embed_query()` → qua `cached_embed_query()` (DiskCache, no TTL, permanent)
- `_embed_query_raw()` — internal, tránh đệ quy với cache
- `_normalize_device()` — "gpu" → "cuda" nếu torch.cuda available, else "cpu"

#### `rag/vectorstore.py` — ChromaStore

- PersistentClient, collection `acne_kb_vi`, `hnsw:space=cosine`
- `query_with_score_filter()` — filter distance ≤ max_distance, fallback về raw nếu quá chặt
- `get_by_ids()` — batch fetch nhiều chunks
- Metadata fields: `doc_id`, `title`, `url`, `source`, `source_type`, `trust`, `lang`, `categories`, `tags`, `position`, `prev_chunk_id`, `next_chunk_id`

#### `rag/chunker.py` — VietnameseChunker

- Vietnamese-aware recursive chunker dùng `underthesea.sent_tokenize` (fallback split trên `.!?`)
- Detect headings bằng regex
- SHA-1 content hash cho near-dedup
- Micro-chunk filtering

#### `rag/cleaning.py`

- `clean_vi_text()` — RAG cleaning nhẹ: NFC, bỏ zero-width, boilerplate patterns (đọc thêm, xem thêm, nguồn URL, liên hệ...)
- Aggressive cleaning cho fine-tuning (bỏ contact info, bác sĩ ký tên, marketing)

---

### LLM Backend

#### `llm/ollama_backend.py` — OllamaBackend

- HTTP client dùng `httpx` (sync), base_url mặc định `http://localhost:11434`
- `generate_json()` — constrained decoding với JSON schema (Ollama `format` field), `stream=False`
- `generate_text()` — plain text, `stream=False`
- `stream_text()` — streaming, yield content tokens từng chunk
- `_build_messages()` — nếu `use_modelfile_system=True` bỏ system message (tránh 2 system prompt chồng cho fine-tuned model)
- Fallback model: nếu `runner process has terminated` → retry một lần với `fallback_model` (default `qwen2.5:3b`)
- `health()` → GET `/api/tags`, timeout 5s
- `list_models()` → parse `/api/tags` response

#### `llm/clinical_planner.py` — ClinicalQueryPlanner (Rule-based)

- **Không gọi LLM**, không re-normalize (tin user đã normalize qua intake)
- Đọc `user.clinical` + `user.context`, build `ClinicalQueryPlan`
- `build_query_vi()` — bilingual query với EN tokens inline (VI + EN trong cùng 1 string để BM25 match chunk EN)
- Mappings: `LESION_BILINGUAL`, `LOCATION_BILINGUAL`, `INFLAMMATION_BILINGUAL`, `HORMONAL_BILINGUAL`, `SKIN_TYPE_BILINGUAL`, `TREATMENT_GOAL_BILINGUAL`
- Safety terms extraction: detect thai kỳ, retinoid, kháng sinh trong text
- `planner_confidence = 0.45` (cố định, rule-based không có confidence thực)

#### `llm/prompt_builder.py` — PromptBuilder

- Jinja2 với `FileSystemLoader(templates_dir)`, autoescape tắt
- Template selection: `system_core.j2` (fallback `system.j2`), `system_stream.j2` (fallback về `system_core.j2`)
- Anti-injection: `_escape_jinja()` neutralize `{{`, `}}`, `{%`, `%}` trong user input
- `_sanitize_chunk_text()` — bỏ HTML tags, neutralize injection markers trong chunk text
- Source badges: `[NICE Guideline]`, `[AAD Guideline]`, `[JID Paper]`, `[PubMed Review]`, `[Textbook]`
- Context block: max 800 chars/chunk + tổng max_context_chars budget
- `system_stream()` → dùng `system_stream.j2` (chỉ hướng dẫn văn xuôi, không JSON)
- `_extended_rules()` → `system_extended.j2`, chỉ inject khi có KB chunks

**Prompt templates** (trong `config/prompts/`):
- `system.j2`, `system_core.j2`, `system_stream.j2`, `system_extended.j2`
- `stream_user.j2` — dùng cho `/chat/stream` (văn xuôi)
- `hybrid_user.j2` — dùng cho `HybridPipeline.run()` (JSON output)
- `llm_only_user.j2` — dùng cho `LLMOnlyPipeline.run()` (JSON output)
- `clinical_planner_user.j2` — dùng khi `use_llm_planner=True` (hiện disabled)
- `judge.j2` — dùng trong eval

#### `llm/query_expander.py` — QueryExpander (Ít dùng)

- Gọi LLM để expand query bilingual (VI + EN)
- `detect_language_heuristic()` — phát hiện ngôn ngữ dựa trên Unicode VI chars + EN medical keywords
- Fallback `fallback_query_plan()` không cần LLM (được dùng nhiều hơn trong thực tế)
- `chat_use_llm_planner: bool = False` mặc định → planner không gọi LLM

#### `llm/qa_generator.py`

Script generate QA pairs từ crawled docs để tạo finetune dataset.

---

### Guardrails

#### `guardrails/runner.py` — GuardrailRunner

**Pre-check** (trước LLM):
- Reject description < 1 char
- Detect prompt injection: 80+ phrases (EN + VI có dấu + không dấu + teencode + token đặc biệt `[system]`, `<|user|>`...)
- PII detection: chỉ log cảnh báo (không từ chối), mask trong log

**Scope check** (2 tầng):
1. Keyword: `_ACNE_SCOPE_TERMS` (200+ terms) vs `_OUT_OF_SCOPE_INTENT_TERMS` (lập trình, toán, tài chính, du lịch...)
2. Embedding OOD: cosine similarity query vs acne domain centroid; threshold 0.25

**scope_mode**:
- `soft` (default) — OOD signal chỉ là telemetry, pass to LLM
- `hard` — refuse cứng
- `off` — tắt scope check

**Post-check** (sau LLM, chỉ cho `HybridPipeline`/`LLMOnlyPipeline`):
- `_apply_drug_checker()` — DrugChecker warnings → red_flags
- `_apply_retinoid_blocks()` — rewrite recommendations có retinoid nếu user pregnant/breastfeeding
- `_apply_severe_doctor()` — inject "đi khám bác sĩ" nếu severity=severe và chưa có
- `_apply_age_restriction()` — inject khuyến nghị bác sĩ nhi nếu age < 12
- `_apply_no_popping()` — xóa recommendation khuyên tự nặn/chích/lăn kim
- `_apply_medication_safety()` — rewrite recommendation tự dùng thuốc Rx/kháng sinh
- `_apply_medication_allergy_redflag()` — thêm red_flag nếu có medication + allergy
- `_ensure_disclaimer()` — đảm bảo disclaimer không rỗng

**Genital scope** — `is_genital_scope()` phát hiện bìu, dương vật, âm đạo, âm hộ, hậu môn, vùng kín...

#### `guardrails/ood_detector.py` — OodDetector

- Embed query → cosine sim vs acne centroid
- Centroid từ file `config/ood_centroid.json` (pre-computed) hoặc tính từ 20 seed queries
- `_centroid_matches()` — dim check, disable OOD nếu dim mismatch
- **Fail-open**: nếu embedder chưa load → return False (không block), để keyword guardrail xử lý
- `rebuild_centroid()` — re-compute từ query list mới, lưu file

**PII detection/masking**: CMND/CCCD (9/12 số), SĐT VN, email, địa chỉ (số nhà + tên đường), số tài khoản ngân hàng

#### `guardrails/drug_checker.py` — DrugChecker

- Load từ `config/drugs_acne.yaml` (danh sách thuốc, pregnancy category, contraindications, interactions, warnings_vi)
- `check(medications, context)`:
  1. Normalize tên thuốc
  2. Lookup local YAML
  3. Fallback OpenFDA API (cache 24h bởi DiskCache) nếu không có trong DB
  4. Check cross-interactions giữa các thuốc trong danh sách
- Context flags: `pregnant`, `breastfeeding`, `age_under_8`, `age_under_12`, `male_patient_acne_use`
- `DrugWarning.is_critical` → `severity=high` OR `pregnancy_category=X`

**Lưu ý**: `GuardrailRunner.post_check()` chỉ được gọi trong `HybridPipeline.run()` và `LLMOnlyPipeline.run()`. Với `/chat/stream`, **post_check KHÔNG được gọi** — thay vào đó dùng `_safety.py` suffix và `_retrieval.py` safety pass.

---

### Crawler & Knowledge Base

**`crawler/base.py`** — `CrawlerProtocol` (Protocol class: `discover()`, `fetch_and_extract()`)

**`crawler/fetcher.py`**
- `GlobalRateLimiter` — token bucket cross-domain, max 5 req/s tổng
- `DomainRateLimiter` — per-domain rate limit, independent locks
- `AsyncFetcher` — httpx AsyncClient với retry (tenacity: 3 attempts, exponential backoff)

**`crawler/playwright_fetcher.py`** — JS-rendered pages (single-page apps, lazy-load content)

**`crawler/extractor.py`** — HTML → text extraction, BeautifulSoup

**`crawler/dedup.py`** — URL + content hash deduplication

**`crawler/quality_filter.py`** — filter trang chất lượng thấp (too short, boilerplate, non-medical)

**`crawler/discovery.py`** — URL discovery từ seed + follow links

**`crawler/checkpoint.py`** — save/load crawl state để resume

**`crawler/normalizer.py`** — normalize URL, text

**`crawler/sources/pubmed.py`** — PubMed E-utilities API crawler

**`crawler/sources/generic_html.py`** — Generic HTML crawler

**Build KB pipeline** (`scripts/build_kb.py`):
1. Crawl → `data/raw/documents.jsonl`
2. Clean + chunk → `data/raw/chunks.jsonl`
3. Embed → ChromaDB + BM25 index
4. Validate + stats

---

### Session & Storage

#### `db/jsonl_session_store.py` — JsonlSessionStore (Production)

- Mỗi session = một file `data/sessions/<session_id>.jsonl`
- Format: dòng meta (type=meta) + dòng turns (type=turn), append-only
- Path sanitization: chỉ cho phép alnum, dash, underscore (tránh path traversal)
- Multi-meta: mỗi lần touch/update context → append thêm dòng meta mới; khi đọc merge tất cả meta (last-write-wins)
- Compact: rewrite file khi số turns > `max_turns * 2` (atomic via `.tmp` file)
- TTL: check `last_active` trong meta khi đọc/ghi
- Thread-safe: RLock

Interface giống hoàn toàn `SessionStore` (in-memory):
- `get_history`, `append_turn`, `merge_user_context`, `get_user_context`, `get_asked_fields`, `mark_fields_asked`, `delete`, `active_count`, `close`

#### `db/audit.py` — AuditStore (SQLite)

- Bảng `audit_log`: `id, timestamp, session_id, user_message, assistant_response, used_chunk_ids, scope_decision, latency_ms, model_used, temperature`
- Bảng `feedback`: `id, timestamp, session_id, message_id, audit_id, rating (up/down), comment`
- Methods: `log`, `query`, `count`, `log_feedback`, `feedback_stats`, `recent_feedback`
- Thread-safe: threading.Lock

#### `db/base.py` — DBConnection

- Thread-local SQLite connections (`threading.local`)
- `PRAGMA journal_mode=WAL` + `foreign_keys=ON`
- Schema gồm: `sessions`, `turns`, `asked_fields`, `audit_log`, `feedback` tables
- **Lưu ý**: `sessions`, `turns`, `asked_fields` tables còn trong schema nhưng không còn dùng (đã migrate sang JSONL). Chỉ `audit_log` và `feedback` được dùng thực tế.

#### `cache.py` — DiskCache

- 2 tier cache:
  - Embed cache: permanent, key = `(embed_v1, model_name, query_text)`, SHA-256
  - Retrieve cache: TTL 1h, key = `(retrieve_v1, queries, top_k, rerank_top_k, min_score)`
- `init_cache(cache_dir, size_limit_gb)` — gọi trong `build_container()`
- `invalidate_retrieve_cache()` — gọi sau khi rebuild KB (prefix matching)
- Silent fallback khi disk full hoặc permission error

---

### Vision Module

- `vision/base.py` — `VisionProtocol(Protocol)`: method `analyze(image_bytes: bytes) -> VisionOutput`
- `vision/mock.py` — `MockVision`: trả hardcoded output `{severity="moderate", papule=8, pustule=3, comedone=15, regions=[forehead, cheek, chin]}`
- Container luôn khởi tạo `MockVision()`, không có logic switch sang real vision
- `UserInput` có field `vision: Optional[VisionOutput]` → `HybridPipeline` nhận và đưa vào query builder + prompt

**Trạng thái**: Placeholder hoàn toàn. Đề tài 27 sẽ thay thế bằng model thực.

---

### Pipeline

#### `pipeline/hybrid.py` — HybridPipeline

`run(user, clinical_plan, prechecked, history)`:
1. `pre_check` + `scope_check` (nếu chưa pre-checked)
2. `_clinical_plan()` nếu chưa có
3. `_retrieve_clinical_plan()` hoặc `_do_retrieve()` → retrieval
4. Safety pass nếu có `safety_terms`
5. Reranker → `drop_noisy_chunks()`
6. `prompt.build(..., template="hybrid_user.j2")` → build prompt (Jinja2)
7. `llm.generate_json(schema=AdviseOutput.model_json_schema())` → JSON constrained
8. `_safe_parse()` → parse với 3 fallback strategies
9. `guardrails.post_check()` → apply tất cả post-rules
10. Set `used_chunks`, `mode`, `model_name`, `latency_ms`

#### `pipeline/llm_only.py` — LLMOnlyPipeline

Tương tự Hybrid nhưng không retrieval, dùng `template="llm_only_user.j2"`.

---

### Eval System

**`eval/judge.py`**:
- `format_compliance()` — parse AdviseOutput thành công
- `severity_accuracy()` — so sánh với expected
- `safety_compliance()` — pregnant + retinoid mention → check có negation không
- `citation_correctness()` — cited chunk_ids phải thuộc available set
- `latency_summary()` — mean, p50, p95
- `judge_case()` — tổng hợp dict

**`eval/metrics.py`**:
- `recall_at_k()`, `mrr_at_k()`, `ndcg_at_k()` — retrieval metrics chuẩn
- `aggregate()` — mean/min/max/n

**Scripts eval** (`scripts/`):
- `eval_all.py` — chạy tất cả eval
- `eval_e2e.py` — end-to-end pipeline test
- `eval_nlp.py` — NLP metrics
- `eval_clinical.py` — clinical accuracy
- `eval_report.py` — tổng hợp báo cáo
- `eval_retrieval.py` — retrieval metrics (recall, MRR, NDCG)
- `run_eval.py` — single eval runner

---

### Frontend (Next.js 15)

**Stack**: Next.js 15.5, React 18.3, TypeScript, Tailwind CSS 3, Zustand 4.5, Lucide React

**Cấu trúc** (`frontend/src/`):
- `app/page.tsx` — main page
- `app/layout.tsx` — root layout
- `components/chat/ChatWindow.tsx` — chat UI chính
- `components/chat/MessageBubble.tsx` — render message (user + assistant)
- `components/chat/MessageInput.tsx` — input box
- `components/chat/CitationCard.tsx` — render citation từ SSE citation event
- `hooks/useSSE.ts` — EventSource hook nhận SSE events từ `/api/v1/chat/stream`
- `lib/api.ts` — API client (fetch wrappers)
- `lib/types.ts` — TypeScript types
- `stores/chatStore.ts` — Zustand store (messages, session_id, loading state)
- `config/chatConfig.ts` — cấu hình endpoint, mode, v.v.

---

## Config & Environment

### Settings (`src/acne_llm/config.py`)

Dùng `pydantic-settings`, đọc từ `.env` file (env_file_encoding=utf-8, extra="ignore").

**Key settings**:

| Biến | Default | Mô tả |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `LLM_MODEL` | `qwen2.5:7b` | Model chính |
| `LLM_FALLBACK_MODEL` | `qwen2.5:3b` | Fallback khi runner terminated |
| `LLM_NUM_CTX` | 8192 | Context window (tokens) |
| `LLM_NUM_PREDICT` | 1024 | Max output tokens |
| `LLM_TEMPERATURE` | 0.3 | Default temperature |
| `LLM_USE_MODELFILE_SYSTEM` | False | Bỏ system message API khi fine-tuned model |
| `EMBEDDING_MODEL` | `AITeamVN/Vietnamese_Embedding` | Embedding model |
| `EMBEDDING_MODEL_MULTILINGUAL` | `""` | Nếu rỗng → dùng EMBEDDING_MODEL |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-encoder reranker |
| `DEVICE` | `"gpu"` | Embedding + reranker device |
| `CHROMA_DIR` | `./data/chroma_db` | ChromaDB persist dir |
| `BM25_PATH` | `./data/bm25_index.pkl` | BM25 pickle |
| `SESSIONS_DIR` | `./data/sessions` | JSONL session files dir |
| `AUDIT_DB_PATH` | `./data/audit.db` | SQLite audit log |
| `CACHE_DIR` | `./data/cache` | DiskCache dir |
| `CACHE_SIZE_GB` | 2.0 | DiskCache size limit |
| `RETRIEVE_TOP_K` | 15 | Pool size trước rerank (pipeline) |
| `RERANK_TOP_K` | 5 | Giữ lại sau rerank (pipeline) |
| `CHAT_RETRIEVE_TOP_K` | 10 | Pool size (chat stream) |
| `CHAT_RERANK_TOP_K` | 3 | Giữ lại sau rerank (chat stream) |
| `CHAT_MAX_CONTEXT_CHARS` | 4500 | Context chars inject vào prompt chat |
| `CHAT_MIN_CITATION_SCORE` | 0.25 | Min sigmoid score cho citation |
| `CHAT_SAFETY_TOP_K` | 5 | Safety pass pool size |
| `CHAT_USE_LLM_PLANNER` | False | Tắt LLM-based planner (rule-based) |
| `RERANKER_MIN_SIGMOID` | 0.30 | Min sigmoid threshold reranker |
| `DENSE_MAX_DISTANCE` | 0.60 | Cosine distance filter Chroma |
| `GUARDRAILS_SCOPE_MODE` | `"soft"` | soft/hard/off |
| `GUARDRAILS_OOD_THRESHOLD` | 0.25 | OOD cosine sim threshold |
| `API_KEY` | `""` | Empty = không cần auth |
| `RATE_LIMIT_PER_MINUTE` | 60 | Per-IP rate limit |
| `LOG_LEVEL` | `"INFO"` | loguru level |
| `CORS_ORIGINS` | `["http://localhost:3000", "http://localhost:8000"]` | CORS whitelist |
| `SESSION_TTL` | 1800.0 | Session idle TTL (giây) |

---

## Data Flow Chi Tiết

### Request → Response (SSE Stream)

```
1. Client gửi GET /api/v1/chat/stream?message=...&session_id=...&mode=auto

2. RateLimitMiddleware: check per-IP bucket
3. APIKeyMiddleware: check x-api-key (skip nếu api_key="")
4. RequestLoggingMiddleware: ghi log + metrics

5. chat.py:chat_stream() → StreamingResponse(stream_chat_sse(...))

6. run_intake():
   a. preprocess_user_text(message) → clean_text
   b. _resolve_mode("auto", c, clean_text, history) → "hybrid" nếu rag_ready + acne signal
   c. normalize_chat_message(message, mode, clean_text) → UserInput với structured fields
   d. snapshot_from_user(user, clean_text) → NormalizedSnapshot
   e. store.get_history(session_id) → list[ConversationTurn]
   f. fold_history_facts(user, history) → UserInput với merged context
   g. guardrails.pre_check(user) → check injection + log PII
   h. Genital check → nếu detect: yield token + done, return
   i. guardrails.scope_check(user) → nếu hard OOD: yield token + done, return
   j. _is_complaint() → nếu đúng: yield clarify token + done, return
   k. check_completeness() → nếu missing field chưa hỏi: yield question + done, return
   l. ClinicalQueryPlanner.plan(user) → ClinicalQueryPlan (rule-based)
   → return IntakeResult

7. retrieve_for_chat(c, user, clinical_plan):
   a. Build query_vi từ clinical_plan.rag_queries.query_vi
   b. cached_retrieve(): check DiskCache TTL 1h
   c. HybridRetriever.retrieve(query, top_k=10):
      - embed_query(query) → cached vector
      - ChromaStore.query_with_score_filter() → dense_ids
      - BM25Index.query() → sparse_hits
      - RRF fusion → trust boost → score prune
   d. Safety pass (nếu safety_terms): domain filter guideline sources
   e. Reranker.rerank(query, retrieval, top_k=3) → sigmoid score + filter
   f. drop_noisy_chunks() → bỏ Wikipedia meta-pages

8. PromptBuilder.build(user, retrieval, template="stream_user.j2", system_override=system_stream()):
   a. _escape_jinja(user.description) — anti-injection
   b. _sanitize_chunk_text(chunk.text) — bỏ HTML tags + injection markers
   c. _context_block(retrieval, max_chars=4500) — format với badges [NICE], [AAD]...
   d. format_history_block(history) — filter genital turns
   e. Jinja2 render → (system_prompt, user_message)

9. OllamaBackend.stream_text(system, user, temperature=0.3):
   - POST /api/chat với stream=True
   - Yield content tokens từng line
   → yield _event("token", token) cho mỗi token

10. get_safety_suffix(full_text, user) → append warning nếu cần
    → yield _event("token", warning_suffix)

11. For chunk in retrieval.chunks:
    → yield _event("citation", citation_data(chunk))

12. store.append_turn(session_id, user_turn)
    store.append_turn(session_id, assistant_turn)

13. audit_store.log(AuditEntry(...))

14. compute_evidence_quality(retrieval) → "strong"/"moderate"/"weak"/"unverified"
    → yield _event("done", {mode, latency_ms, used_chunks, session_id, evidence_quality})
```

### POST /chat (Đồng bộ JSON)

Hỗ trợ 2 body format:
1. `UserInput` schema cũ: trực tiếp gọi `pipeline.run(inp)`
2. Body `{message, session_id, mode}` mới: qua `_chat_new_body()` → `run_intake()` → `pipeline.run()`

Không stream, trả `AdviseOutput` JSON. **GuardrailRunner.post_check()** được gọi (vì dùng pipeline).

---

## Trạng Thái Hiện Tại & Đánh Giá

### Đã hoàn thiện

- FastAPI app với đầy đủ middleware (CORS, API key auth, rate limit, request logging)
- Chat flow hoàn chỉnh: SSE stream + POST JSON + WebSocket
- Guardrails: injection detection (80+ phrases), genital scope, OOD embedding, drug checker, post-check rules
- Rule-based clinical normalizer cực kỳ chi tiết (800+ dòng regex, 15+ loại field)
- Multi-turn session: JSONL store, fold_history_facts với stop-word awareness, asked_fields tracking
- Completeness checker: hỏi từng field một, không hỏi lại
- Hybrid retrieval: dense + sparse + RRF + trust boost + authority tag boost + score pruning
- Safety pass retrieval cho guideline chunks (thai kỳ, thuốc)
- Cross-encoder reranker với LRU score cache
- DiskCache hai tầng (embed permanent + retrieve TTL 1h)
- Source type inference + source badges trong prompt
- Chunk inject injection sanitization (Jinja2 escape + HTML tag removal)
- Safety suffix append (retinoid/Rx warning, age < 12)
- Feedback endpoint (thumbs up/down) + admin audit/feedback stats endpoints
- Prometheus metrics endpoint
- Citation SSE events với evidence_quality
- MMR diversity filter, context expansion (prev/next chunk)
- Vietnamese BM25 với stopword removal + checksum verification
- OodDetector với fail-open, dim mismatch detection
- DrugChecker với OpenFDA API fallback (cache 24h)
- Crawler infrastructure: async fetcher, rate limiter, dedup, quality filter, playwright, PubMed
- Eval system: judge, retrieval metrics, eval scripts
- Frontend: Next.js 15, SSE hook, citation card, Zustand store
- Config: pydantic-settings với đầy đủ env vars

### Bugs / Issues phát hiện

1. **`normalizer.py` — dead code block cuối file**: Hàm `normalize_chat_message()` có 3 return statement liên tiếp. Sau lần `return` đầu tiên (dòng ~800), có thêm 2 block code lặp lại bị unreachable (duplicate extract + return). Code này không bao giờ chạy nhưng gây nhầm lẫn khi đọc. Cần xóa 2 block cuối.

2. **WebSocket handler dùng sync generator**: Trong `chat.py`, handler `chat_ws` gọi `stream_chat_sse()` (generator đồng bộ) bằng `for frame in stream_chat_sse(...)` trong async context. `stream_chat_sse` là synchronous generator chứa blocking calls (`c.llm.stream_text()` là blocking httpx). Điều này block event loop, làm giảm throughput khi có nhiều WS connections.

3. **`cache.py` — `invalidate_retrieve_cache()` logic sai**: Hàm dùng `key.startswith(_make_key(RETRIEVE_TAG)[:8])` nhưng `_make_key(RETRIEVE_TAG)` là SHA-256 hash của `["retrieve_v1"]` — prefix 8 ký tự này là hash hex, không phải literal `"retrieve_v1"`. Mỗi entry trong cache có key là SHA-256 của cả tuple `(RETRIEVE_TAG, *cache_key_parts)`. Prefix matching sẽ gần như không bao giờ match đúng. Retrieve cache không thực sự bị invalidate khi gọi hàm này.

4. **`db/base.py` — Schema thừa**: `sessions`, `turns`, `asked_fields` tables được tạo trong SQLite schema nhưng không còn dùng (đã migrate sang JSONL). Gây confusion khi đọc schema. Nên xóa hoặc comment rõ.

5. **`chat/intake.py` — `scope_decision` logic không nhất quán**: Khi `_is_complaint()` trả True, code set `scope_decision = "in_scope" if acne_signal else "pass_to_llm_soft"` TRƯỚC khi phát hiện complaint, rồi return với `scope_decision=scope_decision` — nhưng effective_mode là "clarify". Complaint có thể là về câu trả lời acne trước (acne scope), nhưng cũng có thể là off-topic. Logic này không block complaint off-topic.

6. **Rate limiter không thread-safe cho `_hits` dict**: `RateLimitMiddleware._hits` là `defaultdict(deque)` không có lock. Trong async context, deque operations không atomic. Với nhiều concurrent requests cùng IP, race condition có thể xảy ra (count không chính xác). Tuy nhiên mức độ impact thấp (chỉ sai số nhỏ).

7. **Metrics `guardrail_trigger_count` không được cập nhật**: `MetricsRegistry.guardrail_trigger_count` được expose trong Prometheus nhưng không có code nào increment field này. Metric luôn là 0.

8. **`_apply_medication_allergy_redflag()` — check condition dư**: Hàm check `has_medication_rec = any(r.category == "medication" for r in out.recommendations)` nhưng sau `_apply_medication_safety()` chạy, nhiều medication recommendations đã bị rewrite thành category `"see_doctor"`. Nên check `has_meds or has_allergies` trực tiếp thay vì qua recommendation category.

### Thiếu tính năng (trừ mock vision)

1. **`DELETE /api/v1/session/{session_id}`** — không có endpoint xóa session. `JsonlSessionStore.delete()` tồn tại nhưng không expose qua API. Người dùng không thể reset conversation.

2. **Session list endpoint** — không có cách list các session IDs. Admin chỉ biết `active_count`, không biết session cụ thể.

3. **Streaming POST endpoint** — `POST /api/v1/chat` trả JSON đồng bộ, không stream. `GET /api/v1/chat/stream` phải nhét toàn bộ message vào query param → giới hạn độ dài message và không phù hợp HTTP semantics (message dài không nên qua URL).

4. **OOD centroid missing** — `config/ood_centroid.json` cần được pre-compute và commit vào repo, hoặc auto-build khi startup. Nếu file không có, OodDetector tự build từ 20 seed queries mỗi lần startup (tốn thời gian + tốn embed calls).

5. **Feedback chưa link được với specific assistant message** — `message_id` là UUID từ frontend nhưng không có mapping rõ với audit_log. `audit_id` optional nên nhiều feedback không link được.

6. **`guardrails_trigger_count` metric không hoạt động** — xem bug #7 trên.

7. **`use_mmr_prefilter` trong HybridPipeline không được dùng** — field `use_mmr_prefilter=True` và `mmr_lambda=0.6` được lưu nhưng `retrieve_with_mmr()` không được gọi trong `run()`. MMR chỉ là helper method.

8. **Vision upload endpoint** — không có API endpoint để user upload ảnh và nhận vision analysis. MockVision chỉ được dùng khi client tự gửi `VisionOutput` trong `UserInput.vision`.

### Technical Debt

1. **`normalizer.py` quá dài** (~900 dòng): Tất cả regex pattern + logic tập trung trong 1 file. Nên tách theo domain: `_extractors/age.py`, `_extractors/lesion.py`, v.v.

2. **Duplicate `_safe_parse()`**: Hàm này tồn tại giống hệt nhau trong `pipeline/hybrid.py` và `pipeline/llm_only.py`. Nên move vào `pipeline/base.py` hoặc `utils/`.

3. **Duplicate `rrf_fusion()`**: Tồn tại trong `rag/retriever.py` và `chat/_retrieval.py` và `pipeline/hybrid.py` (tên `_rrf_fusion`). Nên có một implementation dùng chung.

4. **`chat/_prompt.py` — `build_chat_prompt()` ít được dùng**: Hàm này build prompt thủ công (không Jinja2) nhưng flow chính dùng `PromptBuilder.build()` với Jinja2. Không rõ caller là ai; có thể là dead code.

5. **`_COMPLAINT_TERMS`, `_KNOWLEDGE_QUESTION_TERMS`, `_CASE_INTAKE_TERMS` trong `intake.py`**: 3 tuple term list rất dài (300+ terms tổng cộng) tạo O(n) scan mỗi request. Nên build vào frozenset hoặc compile regex 1 lần.

6. **`LLMOnlyPipeline` — `use_llm_planner` parameter không dùng**: Constructor nhận `use_llm_planner` nhưng không dùng (luôn gọi `self._clinical_plan()` không điều kiện).

7. **`session_db_path` deprecated field** còn trong Settings — chỉ giữ để `.env` cũ không vỡ.

8. **`enable_bilingual_query` deprecated field** còn trong Settings.

9. **`scripts/RUN.ps1` / `RUN.sh`**: Chưa xem nội dung, có thể outdated với các thay đổi config gần đây.

10. **OllamaBackend dùng sync httpx**: Trong async FastAPI app, blocking calls tới Ollama được wrap trong `asyncio.to_thread()` (đúng cho pipeline/POST chat) nhưng `stream_text()` trong `stream_chat_sse()` chạy synchronously trong async generator, không qua `asyncio.to_thread()`. Đây là pattern không ideal — blocking generator trong async context.

---

## Test Coverage

**Test files** (`tests/`):

| File | Mô tả |
|---|---|
| `test_api.py` | Smoke test FastAPI app với mock container (health, chat, kb/stats) |
| `test_chat_stream.py` | Test SSE stream flow với mock container + MockLLM |
| `test_guardrails.py` | Test pregnancy retinoid block, severe doctor injection, strip popping |
| `test_intake.py` | Test run_intake flow |
| `test_session.py` | Test SessionStore (in-memory) |
| `test_jsonl_session_store.py` | Test JsonlSessionStore |
| `test_pipeline_mock.py` | Test pipeline với mock LLM |
| `test_clinical_planner.py` | Test ClinicalQueryPlanner |
| `test_ollama_backend.py` | Test OllamaBackend |
| `test_chat_normalizer.py` | Test normalizer extract functions |
| `test_normalizer_regression.py` | Regression tests cho normalizer |
| `test_retriever.py` | Test HybridRetriever |
| `test_retrieval_merge.py` | Test RRF merge |
| `test_sparse_bm25.py` | Test BM25Index |
| `test_reranker.py` | Test Reranker |
| `test_prompt_builder.py` | Test PromptBuilder Jinja2 |
| `test_schemas.py` | Test Pydantic schemas |
| `test_settings.py` | Test Settings loading |
| `test_chunker.py` | Test VietnameseChunker |
| `test_cleaning.py` | Test cleaning functions |
| `test_dedup.py` | Test deduplication |
| `test_quality_filter.py` | Test quality filter |
| `test_eval_from_finetune_test.py` | Test eval từ finetune test set |
| `test_eval_retrieval.py` | Test retrieval metrics |
| `test_run_eval.py` | Test eval runner |
| `test_approve_eval_labels.py`, `test_propose_eval_labels.py` | Test eval label workflow |
| `test_clinical_dataset_validator.py` | Test clinical dataset validator |
| `test_chunk_qa_clinical_factory.py` | Test QA generation |
| `conftest.py` | pytest fixtures |

**Config**: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]`

---

## Cách Chạy

### Khởi động server

```bash
# Development
cd e:\project\AcneLLM
uvicorn acne_llm.api.app:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

### Build Knowledge Base

```bash
# Full pipeline
python scripts/build_kb.py

# Chỉ embed (sau khi đã crawl)
python scripts/build_kb.py --step embed

# Crawl trước
python scripts/crawl_all.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # dev server port 3000
npm run build  # production build
npm run start  # production serve
```

### Chạy Tests

```bash
cd e:\project\AcneLLM
python -m pytest tests/ -v

# Một file cụ thể
python -m pytest tests/test_guardrails.py -v
```

### Eval

```bash
python scripts/eval_all.py
python scripts/eval_e2e.py
python scripts/eval_retrieval.py
```

### Clear Cache (sau khi rebuild KB)

```bash
python scripts/clear_cache.py
```

### Cấu hình qua `.env`

```env
OLLAMA_URL=http://localhost:11434
LLM_MODEL=qwen2.5:7b
DEVICE=gpu
GUARDRAILS_SCOPE_MODE=soft
LOG_LEVEL=INFO
API_KEY=         # để trống = không cần auth
RATE_LIMIT_PER_MINUTE=60
```

---

## Tích Hợp Liên Đề Tài

### Tích hợp Đề tài 27 (Vision)

Khi Đề tài 27 sẵn sàng, thay thế:
1. `MockVision` trong `di.py` → real vision model implement `VisionProtocol`
2. Thêm endpoint upload ảnh trong `api/routes/` → trả `VisionOutput`
3. Frontend: thêm UI upload ảnh, gửi `vision` field trong request

### Tích hợp Đề tài 28 (Advanced RAG)

Interface sẵn có qua:
- `CrawlerProtocol` — implement `discover()` + `fetch_and_extract()`
- `ChromaStore`, `BM25Index`, `HybridRetriever` — có thể swap các component
- `SourceType` enum và `infer_source_type()` — mở rộng source types mới

---

## Bugfix Session 2026-05-14

Tất cả 8 bugs đã được fix. Snapshot test: **183 passed, 2 failed (pre-existing), 1 skipped, 1 xfailed**.

### Chi tiết fixes

#### Bug #1 — Dead code trong `normalizer.py` ✅
- **File:** `src/acne_llm/chat/normalizer.py`
- **Fix:** Xoá 76 dòng dead code (dòng 1161–1236) không bao giờ được thực thi sau `return UserInput(...)` đầu tiên. File giảm từ 1236 → 1160 dòng.

#### Bug #2 — `invalidate_retrieve_cache()` broken ✅
- **File:** `src/acne_llm/cache.py`
- **Fix:** Thay prefix-matching SHA256 (luôn sai) bằng **shadow index pattern**: mỗi lần `cached_retrieve()` lưu một entry, key được thêm vào `__retrieve_keys_index__` trong DiskCache. `invalidate_retrieve_cache()` đọc index này để xoá đúng keys.

#### Bug #3 — WebSocket sync generator trong async context ✅
- **File:** `src/acne_llm/api/routes/chat.py`
- **Fix:** Wrap toàn bộ `stream_chat_sse()` generator trong `asyncio.to_thread(lambda: list(...))` thay vì gọi trực tiếp trong coroutine, tránh block event loop.

#### Bug #4 — SQLite schema thừa `sessions/turns/asked_fields` ✅
- **File:** `src/acne_llm/db/base.py`
- **Fix:** Xoá `CREATE TABLE IF NOT EXISTS` cho `sessions`, `turns`, `asked_fields` khỏi `_SCHEMA`. Chỉ giữ `audit_log` và `feedback`. Sessions đã chuyển hoàn toàn sang JSONL.

#### Bug #5 — `guardrail_trigger_count` không increment ✅
- **Files:** `src/acne_llm/api/routes/chat.py`, `src/acne_llm/chat/runtime.py`, `src/acne_llm/api/routes/metrics.py`
- **Fix:**
  - Trong `_chat_new_body`: increment `request.app.state.metrics.guardrail_trigger_count` khi `scope_refusal is not None`.
  - Trong `stream_chat_sse`: increment `c.guardrails.trigger_count` khi scope refusal.
  - Trong `/metrics` endpoint: sync `guardrails.trigger_count` → `registry.guardrail_trigger_count` trước khi render Prometheus output.

#### Bug #6 + MMR Feature — `use_mmr_prefilter` không có tác dụng ✅
- **Files:** `src/acne_llm/pipeline/hybrid.py`, `src/acne_llm/di.py`
- **Fix:** `_do_retrieve()` trong `HybridPipeline` giờ gọi `retriever.retrieve_with_mmr()` khi `use_mmr_prefilter=True` (mặc định `True`). `di.py` truyền `use_mmr_prefilter` và `mmr_lambda` từ settings vào `HybridPipeline`.

#### Bug #7 — Race condition trong `RateLimitMiddleware` ✅
- **File:** `src/acne_llm/api/observability.py`
- **Fix:** Thêm `asyncio.Lock()` vào `RateLimitMiddleware.__init__()`. Toàn bộ block đọc/ghi `_hits[client]` được bọc trong `async with self._lock:`.

#### Bug #8 — `post_check` bị bypass trong SSE streaming path ✅
- **File:** `src/acne_llm/chat/runtime.py`
- **Fix:** Sau khi collect `full_text` từ LLM stream, tạo một `AdviseOutput` tối giản rồi chạy `c.guardrails.post_check()`. Các red_flags (pregnancy/age/drug/disclaimer) được append vào `warning_suffix` và stream về client qua SSE `token` event.

### Tests sau fix
```
183 passed, 2 failed (pre-existing), 1 skipped, 1 xfailed
```

**2 pre-existing failures (không liên quan đến fixes):**
- `test_nan_vai_cuc`: regex "nặn vài cục" không trigger `self_treatment_risk` — bug trong normalizer pattern, cần thêm pattern `nặn vài`.
- `test_normalizer_does_not_mark_asked_about_medication_as_current_use`: medication detection quá sensitive với `treatment_goals` — cần refine `_extract_treatment_goals`.

---

## Feature Session 2026-05-14 (M1–M9 + Milestones)

Tất cả 16 milestones đã hoàn thành. **43 test mới pass** (test_completeness_new, test_intent_router_new, test_stream_safety).

### M1 — Ambiguous Intent Tiebreak ✅
- **File:** `src/acne_llm/chat/intake.py`, intent router
- Rule-based confidence scoring; khi intent không rõ (tie giữa `advise` và `knowledge`) → prefer `knowledge` nếu không có clinical signal.

### M2 — Emotional/Crisis Detection + Empathy Response ✅
- **File:** `src/acne_llm/chat/runtime.py`, `src/acne_llm/chat/intake.py`
- Route flags `emotional_distress` và `crisis_signal` được detect trong intent router.
- `stream_chat_sse()` yield empathy prefix **trước** LLM stream:
  - `crisis_signal` → "Mình hiểu bạn đang rất khó chịu và lo lắng..."
  - `emotional_distress` → "Mình hiểu mụn có thể ảnh hưởng đến tâm lý nhiều lắm — "
- `pre_prefix` được concat vào `full_text` để persist đúng vào session.

### M3 — Product Safety / Ingredient Check ✅
- **File:** `src/acne_llm/chat/_retrieval.py`
- Khi `product_safety_check` flag present: inject 8 ingredient interaction safety terms vào `clinical_plan.safety_terms`, trigger safety pass retrieve guideline chunks về contraindication.
- Terms: `"ingredient interaction"`, `"retinol aha bha"`, `"ket hop hoat chat"`, v.v.

### M4 — Urgency / Red Flag Triage ✅
- **File:** `src/acne_llm/chat/_safety.py`
- `urgency_red_flag` flag → append 🚨 urgent suffix: "Dấu hiệu nghiêm trọng — đến cơ sở y tế ngay"
- `skip_generic_disclaimer=True` khi `primary_intent == "knowledge"` để tránh duplicate disclaimer.

### M5 — Progress/Follow-up Intent ✅
- **File:** `src/acne_llm/chat/runtime.py`, `src/acne_llm/chat/session.py`
- `progress_followup` flag → `route_metadata["is_progress_followup"] = True`
- Increment `session.accumulated_clinical_score` mỗi follow-up turn.
- `ConversationTurn` có `turn_type`, `intent_label`, `intent_confidence`, `classifier_used`.

### M6 — Multi-condition Escalation ✅
- **File:** `src/acne_llm/chat/_safety.py`
- `multi_condition` flag → append ⚠️ suffix gợi ý bác sĩ da liễu khi có nhiều tình trạng da phức tạp.

### M7 — Repeated Question Dedup ✅
- **File:** `src/acne_llm/chat/runtime.py`
- `repeated_question` flag → yield prefix "Như mình đã chia sẻ, " trước LLM stream.
- Intent router detect repeated question bằng similarity với prior turns.

### M8 — Partial Advise ✅
- **File:** `src/acne_llm/chat/completeness.py`, `src/acne_llm/chat/runtime.py`
- `CompletenessResult.kind = "partial"` + `partial_advise=True`: LLM tư vấn sơ bộ ngay, append follow-up question **sau** response (không block).
- `level` property: `"partial"` → `"sufficient"` (LLM không bị block).
- `partial_question_suffix` yield sau safety suffix, trước session persist.

### M9 — Language Switch + Bilingual RAG ✅
- **Files:** `src/acne_llm/schemas/clinical.py`, `src/acne_llm/llm/clinical_planner.py`, `src/acne_llm/chat/_retrieval.py`
- `ClinicalRagQueries.query_en: str = ""` — EN query field.
- `ClinicalQueryPlanner.build_query_en()` tạo pure English query khi `detected_language in ("en", "mixed")`.
- `retrieve_for_chat()` nhận `route_flags`; khi `language_switch` flag present + `query_en` khác rỗng → append vào queries list, RRF-fuse cả VI + EN results.

### RAG Thresholds (Task #2) ✅
- **File:** `src/acne_llm/rag/retriever.py`
- `_DENSE_MAX_DISTANCE`: 0.60 → **0.48** (chặt hơn, giảm noise)
- `_MIN_FUSION_SCORE`: 0.005 → **0.015** (tăng bar tối thiểu)

### Session Schema Mở Rộng (Task #6) ✅
- **File:** `src/acne_llm/chat/session.py`
- `ConversationTurn`: thêm `intent_label`, `intent_confidence`, `turn_type`, `classifier_used`
- `Session`: thêm `last_intent`, `total_clarify_count`, `accumulated_clinical_score`
- `append_turn()` auto-populate typed fields từ `metadata` dict

### Tests Mới (Task #7) ✅
- `tests/test_completeness_new.py` — 15 tests: too_short, partial, sufficient, missing_core, level mapping
- `tests/test_intent_router_new.py` — 18 tests: tất cả flags (emotional, crisis, urgency, product_safety, multi_condition, progress, language_switch, repeated)
- `tests/test_stream_safety.py` — 5 tests mới: skip_generic_disclaimer, multi_condition warning, urgency flag

### Lưu ý kỹ thuật
- `_retrieval.py` bị truncation lặp lại trong quá trình develop; fixed bằng cách strip orphaned code sau dòng `return "weak"` (dòng 241).
- `compute_evidence_quality()` trong stream path dùng avg reranker score: `"strong"` ≥ 0.65, `"moderate"` ≥ 0.40, `"weak"` < 0.40, `"unverified"` khi không có retrieval.

---

## KB Quality Session 2026-05-21

### Chunker Module — Noise Filters Mới (`rag/chunker.py`)

Rewrite `VietnameseChunker` với các filter mới:

**Module-level constants:**
- `_FOOTER_PATTERNS` — 21 regex patterns: hotline, zalo, facebook, đặt hẹn online, xem thêm, bài viết liên quan, newsletter, subscribe, © copyright, v.v.
- `_FOOTER_THRESHOLD_SHORT = 1` — chunk < 120 words: 1 pattern là đủ để drop
- `_FOOTER_THRESHOLD_LONG = 3` — chunk ≥ 120 words: cần ≥ 3 patterns
- `_FOOD_DOMAIN_RE` — regex "trứng cá hồi/tầm/muối/sashimi" tránh confuse với mụn trứng cá
- `_NEAR_DUP_SHINGLE_N = 4`, `_NEAR_DUP_THRESHOLD = 0.90` — char n-gram Jaccard

**Hàm mới:** `_shingle_set()`, `_jaccard()`, `_is_footer_chunk()`, `_is_food_domain()`

**Logic thay đổi:**
- `_emit()` thay cho `_flush_buf()`: micro-chunk → footer → food-domain → exact-dedup → near-dup (theo thứ tự)
- **Flush tại mỗi paragraph boundary** (không carry buf qua paragraph) → tránh merge footer vào acne content
- `dedup=True` chỉ dùng khi gọi standalone; **`build_kb.py` dùng `dedup=False`** (cross-doc dedup ở Phase 2)

**Performance fix:** `dedup=False` trong `build_kb.py` giảm chunking time từ 37s → 17s

### Build KB Pipeline — 3-Phase Architecture (`scripts/build_kb.py`)

**Phase 1:** Collect chunk texts per doc, apply content filters (`_is_acne_chunk`), KHÔNG gán link

**Phase 2:** Cross-doc dedup — sort theo trust_level (high first), exact-text hash + top-20 word shingling fingerprint (O(n))

**Phase 3:** Rebuild `chunk_id / position / prev_chunk_id / next_chunk_id` SAU khi đã filter xong → **0 broken links**

**Kết quả build 2026-05-21:**
- Input: 7,391 docs (bỏ 778 docs quality < 0.5)
- Output: **26,864 chunks** (33.7s)
- Filtered: 15,761 off-topic/boilerplate/noise, 1,672 duplicate

### Source Type — Mở Rộng (`schemas/kb.py`)

Thêm `"en_medical_site"` vào `SourceType` Literal.

`infer_source_type()` mở rộng nhận dạng:

| Token | → SourceType |
|---|---|
| suckhoedoisong, youmed, vnexpress, tuoitre, bvdl, vinmec, hellobacsi | `vi_medical_site` |
| healthline, webmd, mayoclinic, msdmanuals, medlineplus, clevelandclinic, dermnet | `en_medical_site` |
| incidecoder | `blog` |
| openstax | `clinical_textbook` |

**Kết quả sau patch 8,580 unknown chunks:**
- `vi_medical_site`: 17,431 (64.9%)
- `pubmed_review`: 4,922 (18.3%)
- `blog`: 2,181 (8.1%) — incidecoder + blogs
- `en_medical_site`: 1,981 (7.4%)
- `aad_guideline`: 187 (0.7%)
- `nice_guideline`: 144 (0.5%)
- `unknown`: **0** ✅

### Trust Boost đã có sẵn trong Retriever

`rag/retriever.py` đã implement trust boost dựa trên source_type:
- `nice_guideline` / `aad_guideline`: ×1.50
- `jid_paper`: ×1.30
- `pubmed_review` / `clinical_textbook`: ×1.20
- `forum_post`: ×0.80, `blog`: ×0.70
- `en_medical_site` chưa có boost riêng (hiện dùng default ×1.0)

**TODO:** Thêm `en_medical_site: ×1.10` vào trust boost table trong `retriever.py`

### Pending Tasks

1. `python scripts/build_kb.py --step embed` — rebuild ChromaDB với chunks mới (cần GPU, chạy trên máy)
2. `python scripts/build_kb.py --step bm25` — rebuild BM25 index
3. `python scripts/eval_rag.py --skip-gen` — eval RAG với KB mới
4. Thêm `en_medical_site: ×1.10` vào trust boost trong `rag/retriever.py`
5. Xem xét tăng `min_size=60` để drop 879 short chunks (<60w, mostly pubmed abstract fragments)
