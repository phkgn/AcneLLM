# AcneLLM — Codebase Audit, Architecture Review & Refactoring Roadmap

> Tài liệu này CHỈ phân tích, đánh giá và tạo TODO. Không có code, không patch, không refactor trực tiếp, không thay đổi behavior. Mọi nhận định có gắn **Confidence** (High/Medium/Low). Khi chưa đủ bằng chứng, mục được đánh dấu **[Hypothesis]** và không khẳng định là bug.
>
> Phạm vi đã đọc: toàn bộ `src/acne_llm/` (90 file Python, ~17.150 LOC), `README.md`, `context.md`, `docs/*.md`, `di.py`, `config.py`, `chat/intake.py` + `runtime.py` + `_retrieval.py`, `guardrails/`, `rag/retriever.py`, `api/app.py`, `requirements.txt`, `pyproject.toml`, `frontend/src/`, các script root-level và file cấu hình. Một số module sâu (toàn bộ `normalizer.py` 1843 dòng, `crawler/`, `eval/`) được đọc chọn lọc — các nhận định liên quan được hạ confidence tương ứng.

---

## PHASE 1 — Repository Understanding

### 1. Executive Summary

**Mục đích:** AcneLLM là chatbot tư vấn mụn trứng cá tiếng Việt, **local-first** (không phụ thuộc cloud cho luồng chat). LLM chạy qua Ollama (`acnellm-v2-q4`, fine-tune từ Qwen2.5-7B Q4), có thể bật RAG hybrid (ChromaDB dense + BM25 sparse + cross-encoder rerank).

**Bài toán giải quyết:** Tư vấn da mụn an toàn bằng tiếng Việt với (a) trích xuất thông tin lâm sàng rule-based từ ngôn ngữ tự nhiên có dấu/không dấu/teencode, (b) guardrails an toàn y tế (out-of-scope, OOD, PII, vùng sinh dục, tương tác thuốc), (c) RAG trên tài liệu y khoa để giảm hallucination và có citation.

**Các thành phần chính:**

- **API layer** — FastAPI + uvicorn, SSE streaming (`/api/v1/chat/stream`), health, kb, metrics, admin.
- **Chat intake pipeline** — preprocess → normalize → guardrails → intent routing → completeness → clinical plan → retrieve → prompt → stream.
- **RAG** — `HybridRetriever` (dense Chroma + sparse BM25 → RRF fusion → bge-reranker-v2-m3 → chunk filters).
- **Guardrails** — scope/OOD/PII/drug safety.
- **Crawler** — thu thập KB từ web (PubMed, generic HTML, Playwright).
- **Eval** — Hit@k / MRR / NDCG, dataset gen qua DeepSeek/OpenAI.
- **Frontend** — Next.js 15 + Tailwind + Zustand.

**Công nghệ:** Python 3.10+, FastAPI, Pydantic v2 + pydantic-settings, Ollama, sentence-transformers, ChromaDB, rank-bm25, rapidfuzz, underthesea, Jinja2, loguru, diskcache, SQLite (audit), JSONL (session); Next.js/TypeScript/Tailwind/Zustand ở frontend.

**Kiến trúc hiện tại:** Modular monolith Python với dependency-injection container (`di.py`) khởi tạo tất cả thành phần lúc startup; RAG được load lazy/optional (graceful degrade về `llm_only` nếu KB chưa build). Pipeline chat là một orchestrator tuyến tính có nhiều nhánh (fork theo `primary_intent` × `query_subject`).

**Đánh giá tổng quan (Confidence: High):** Đây là codebase **trưởng thành và được tài liệu hoá tốt bất thường** so với một dự án cá nhân/học thuật — `context.md` mô tả chính xác pipeline; có test suite 40 file; có config layering rõ ràng; có audit log + metrics. Điểm yếu chính nằm ở **tích tụ tech debt quanh các "god module" rule-based**, **rác ở thư mục gốc**, và **config drift giữa nhiều nguồn default**.

---

### 2. Architecture Analysis

#### Sơ đồ kiến trúc tổng thể (text)

```
┌──────────────────────────────────────────────────────────────────┐
│ Frontend (Next.js 15 / Zustand / Tailwind)                         │
│   page.tsx → ChatWindow → useSSE → lib/api.ts (EventSource)        │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP SSE (GET /api/v1/chat/stream)
┌───────────────────────────▼──────────────────────────────────────┐
│ API Layer (FastAPI app.py)                                         │
│   Middleware: CORS → RequestLogging → APIKey → RateLimit           │
│   Routers: health · chat · kb · metrics · admin                    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ Container (di.py) injected via app.state
┌───────────────────────────▼──────────────────────────────────────┐
│ Chat Runtime (chat/runtime.py :: stream_chat_sse)                  │
│   orchestrator: SSE event loop + LLM stream + safety suffix        │
└───────────────────────────┬──────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ Intake (chat/intake.py :: run_intake) — DETERMINISTIC pre-LLM      │
│  ① preprocess.prepare_user_text                                    │
│  ② normalizer.normalize_chat_message  +  extraction_confidence     │
│  ③ guardrails.pre_check (scope / OOD / PII / genital)              │
│  ④ intent_router.route_intent                                      │
│  ⑤ fork: advise|knowledge|clarify|reject × self|other|general      │
│  ⑥ session.fold_history_facts + completeness.check_completeness    │
│  ⑦ clinical_planner.plan (RULE-BASED) + build_retrieval_query      │
└───────────┬───────────────────────────────────┬──────────────────┘
            ▼                                    ▼
┌────────────────────────┐         ┌─────────────────────────────────┐
│ RAG (rag/, _retrieval) │         │ LLM (llm/ollama_backend)        │
│  HybridRetriever        │         │  stream_text → tokens           │
│   dense(Chroma)+BM25    │         │  fallback model                 │
│   → RRF → rerank        │         └─────────────────────────────────┘
│   → chunk_filter        │
└────────────┬───────────┘
            ▼
┌──────────────────────────────────────────────────────────────────┐
│ Persistence: JsonlSessionStore (sessions) · AuditStore (SQLite)    │
│              DiskCache (embed/retrieval) · ChromaDB (vectors)       │
└──────────────────────────────────────────────────────────────────┘
```

#### Layers & module map

| Layer | Package | Trách nhiệm |
|---|---|---|
| Presentation | `frontend/src` | UI chat, SSE consumer, citation cards |
| API | `api/` (`app.py`, `routes/`, `observability.py`, `deps.py`) | HTTP, middleware, routing |
| Orchestration | `chat/` (`runtime.py`, `intake.py`) | Điều phối pipeline pre-LLM + streaming |
| NLP/Extraction | `chat/` (`normalizer.py`, `preprocess.py`, `extraction_confidence.py`, `intent_router.py`, `completeness.py`) | Rule-based extraction + routing |
| Domain/Safety | `guardrails/`, `schemas/` | An toàn y tế + data model |
| Retrieval | `rag/`, `chat/_retrieval.py`, `utils/retrieval_query.py`, `utils/chunk_filter.py` | Hybrid retrieval |
| Generation | `llm/` | Ollama backend, prompt builder, clinical planner |
| Data ingestion | `crawler/` | Crawl + clean + dedup KB |
| Persistence | `db/`, `cache.py` | Session, audit, cache |
| Evaluation | `eval/`, `scripts/eval_*` | Metrics + judge |
| Composition | `di.py`, `config.py`, `cli.py` | DI container + settings |

#### Dependency giữa các thành phần (Confidence: High)

- `api/routes/chat.py` → `chat/runtime.py` → `chat/intake.py` → (`guardrails`, `chat/normalizer`, `chat/intent_router`, `chat/completeness`, `chat/session`, `llm/clinical_planner`, `utils/retrieval_query`).
- `runtime` → `chat/_retrieval` → `rag/retriever` → (`rag/vectorstore`, `rag/sparse`, `rag/embedder`, `rag/reranker`).
- Mọi thành phần được khâu lại trong `di.Container`; module nghiệp vụ nhận `Container` (hoặc `settings`) qua tham số — DI tường minh, **không có global singleton bắt buộc** (trừ `get_session_store()` fallback và `cache.init_cache` global — xem mục debt).

**Quan sát kiến trúc (Confidence: High):**

- Tầng `pipeline/` (`HybridPipeline`, `LLMOnlyPipeline`) được `context.md` mô tả là *"legacy wrappers"*. Luồng chat thực tế đi qua `chat/runtime.py` + `chat/_retrieval.py`, **không** qua `pipeline/`. Đây là **hai đường dẫn retrieval song song** — nguồn rủi ro drift (xem Phase 2 & 3).
- `intake.py` là một orchestrator dài (772 dòng) với nhiều `return IntakeResult(...)` lặp lại gần như nguyên khối ở mỗi nhánh refuse — boilerplate trùng lặp cao.

---

### 3. Data Flow Analysis

**Luồng chính: User message → Streamed answer**

1. **Input:** `GET /api/v1/chat/stream?message=...&mode=auto&session_id=...` → `stream_chat_sse`.
2. **Validation (intake):** giới hạn `MAX_MESSAGE_CHARS=4000` và `MAX_MESSAGE_WORDS=500`; vượt → `ValueError`.
3. **Preprocess:** `prepare_user_text` → `clean_text`, `clean_text_no_accent`, `teencode_replaced`.
4. **Normalize:** `normalize_chat_message` → `UserInput` (regex/lexicon rule-based); song song `extract_with_confidence` → `ExtractionConfidence` (kênh phụ cho hedging).
5. **Guardrails pre_check:** scope (acne?), genital region (hard reject), OOD (embedding similarity vs centroid), PII detection.
6. **Routing:** `route_intent` → `RouteDecision(primary_intent, query_subject, confidence, route_flags)`. Có micro-classifier `qwen2.5:0.5b` (theo docs).
7. **Session fold:** chỉ khi `query_subject == "self"` → `fold_history_facts` (last-write-wins scalar, additive list, max-severity), `merge_user_context`.
8. **Completeness:** field có `confidence < threshold` coi như thiếu → đẩy sang `clarify`/hint.
9. **Clinical plan:** rule-based, dựng query RAG (KHÔNG gọi LLM).
10. **Retrieval:** `retrieve_for_chat` (chỉ khi `mode==hybrid` và `rag_signal` và intent ∉ {clarify, reject}) → dense+sparse → RRF → rerank → filter → cache.
11. **Prompt:** chọn template (`stream_user.j2` / `knowledge_user.j2` / `clarify_user.j2`).
12. **Generation:** `llm.stream_text` → token stream; CJK guard strip per-token.
13. **Output:** SSE events `token` → `citation` → `done`; safety suffix + optional partial-advise follow-up question.
14. **Storage:** `append_turn` (user raw + assistant) vào JSONL; `merge_user_context`; `AuditStore.log` (PII-masked nếu phát hiện).

**Luồng phụ:** Crawl (`crawl_all` → `data/raw/documents.jsonl`) → `build_kb` (chunk → embed → Chroma + BM25) → Eval (`eval_rag.py`).

**Quan sát (Confidence: High):** Có **bất đối xứng nội dung lưu vào session**: turn `user` lưu `intake.raw_message` (nguyên văn, có comment F10 giải thích), nhưng `AuditStore` lưu `clean_message` (đã preprocess). Hợp lý theo thiết kế, nhưng cần lưu ý khi join hai nguồn để debug.

---

### 4. Pipeline Analysis

| # | Pipeline | Purpose | Entry point | Input | Output | Failure points | Risk |
|---|---|---|---|---|---|---|---|
| P1 | **Chat inference (SSE)** | Tư vấn realtime | `chat/runtime.py::stream_chat_sse` | message, session_id, mode | SSE token/citation/done | Ollama down, RAG load fail, exception trong stream | **Cao** (đường sống của sản phẩm) |
| P2 | **Intake (pre-LLM)** | Chuẩn hoá + định tuyến + an toàn | `chat/intake.py::run_intake` | raw message + history | `IntakeResult` | Sai routing → trả lời sai nhánh; miss extraction | **Cao** |
| P3 | **Retrieval (RAG)** | Lấy bằng chứng + citation | `chat/_retrieval.py::retrieve_for_chat` | UserInput, clinical_plan | `RetrievalOutput` | Cache key sai → cross-session leak; rerank fail | **Cao** |
| P4 | **KB build (ETL)** | Crawl→chunk→embed→index | `scripts/build_kb.py` | `data/raw/*` | Chroma + `bm25_index.pkl` | OOM khi embed; checksum mismatch | Trung bình |
| P5 | **Crawl** | Thu thập tài liệu | `scripts/crawl_all.py` | seed_sources.yaml | `documents.jsonl` | Site đổi layout, Playwright fail, rate-limit | Trung bình |
| P6 | **Eval (retrieval)** | Hit@k/MRR/NDCG | `scripts/eval_rag.py` | golden jsonl | report | DeepSeek API quota, cần Ollama/embedding | Thấp |
| P7 | **Dataset/finetune gen** | Sinh QA, clinical case | `LLMData/*`, `scripts/build_hybrid_finetune_dataset.py` | chunks | jsonl datasets | API cost, nhãn nhiễu | Thấp |
| P8 | **Audit/Metrics** | Logging + Prometheus | `runtime` + `api/observability` | mọi request | SQLite + `/metrics` | DB lock, disk full | Thấp |
| P9 | **Deployment** | Docker compose stack | `docker-compose.yml` | env + model volume | services | Startup ordering ollama→init→app→frontend | Trung bình |

**Critical files của P1–P3 (tuyệt đối cẩn trọng khi sửa):** `chat/runtime.py`, `chat/intake.py`, `chat/_retrieval.py`, `chat/normalizer.py`, `chat/intent_router.py`, `chat/completeness.py`, `chat/session.py`, `guardrails/runner.py`, `rag/retriever.py`.

---

## PHASE 2 — Code Quality Review

### 5. Folder Structure Review

| Folder/vị trí | Đánh giá | Priority |
|---|---|---|
| `src/acne_llm/` | Cấu trúc package theo layer rất hợp lý, rõ ràng | — (giữ) |
| `chat/` | **Phình to & nhiều trách nhiệm** — `normalizer.py` 1843 dòng, `intake.py` 772 dòng. God-modules. | **High** |
| **Root directory** | **Lộn xộn**: 4 file HTML lớn (`acnellm_pipeline.html` 38KB, `acnellm_trace.html` 54KB, `pipeline_simulator.html` 88KB, `project_pipeline_overview.html` 56KB, `wiki.html` 76KB), `add_boosts.py`, `fix_pronoun.py`, `upload_to_hf.py`, `prompt_simulation_full.md`, `AcneLLM_config_audit.xlsx`, `context.md`. Lẫn artifact, script một lần, tài liệu. | **High** |
| `scripts/` | Nhiều script (audit_*, eval_*, build_*, crawl_*) + lẫn `RUN.ps1`/`RUN.sh`/`KB.ps1`/`run_all.sh`/`tasks.sh` (root) → trùng vai trò runner | **Medium** |
| `data/` | Trộn artifact runtime (`audit.db*`, `sessions/`, `cache/`) với data versioned (`chroma_db/`, golden sets, `eval/`) và **rất nhiều golden_*.jsonl phiên bản** (`golden_extraction`, `_gen`, `_gen_deepseek`, `_v2`, `golden_test30`, `test_golden`, `test_openai`, `test_openai2`) | **Medium** |
| `LLMData/` | Dataset gen tách riêng khỏi `scripts/` và `data/` — vị trí gây nhầm lẫn (vì sao không nằm trong `data/` hay `scripts/`?) | **Medium** |
| `model/` | Chứa GGUF lớn + `V2/`; loại khỏi image (đúng). `.pycache_test/` lạc ở root. | Low |
| `visualize/`, `notebooks/` | Hợp lý nhưng nên gom vào `tools/` hoặc `analysis/` | Low |
| `pipeline/` | Legacy wrappers — tách biệt với luồng thực; gây nhầm "đây là pipeline chính" | **Medium** |
| `tests/` | 40 file, tổ chức phẳng nhưng đặt tên rõ; thiếu phân nhóm unit/integration/e2e | Low |

### 6. Naming Consistency Review (Confidence: High cho các điểm dưới)

- **Trộn ngôn ngữ comment/identifier:** code mix tiếng Việt (có dấu + không dấu) và tiếng Anh không nhất quán — ví dụ comment "Tra None neu RAG chua san sang" (không dấu) bên cạnh "Retrieve + rerank chunks cho chat stream" (có dấu). Docstring lúc VI có dấu, lúc VI không dấu, lúc EN.
- **Module-private dùng dấu gạch dưới không nhất quán:** `chat/_prompt.py`, `_retrieval.py`, `_safety.py`, `_terms.py` (prefix `_`) vs `preprocess.py`, `completeness.py` (cùng tầng, không prefix) — quy ước "internal" không rõ ràng.
- **Tên flag/biến mã hoá theo ticket:** `# S2-B`, `# M3`, `# M7 + M2`, `# F10`, `# Bug #5 fix`, `# FIX 1`, `# FIX 4` rải rác trong `runtime.py`/`_retrieval.py`/`intake.py`. Người mới không tra được ý nghĩa → kiến thức ẩn (tribal knowledge).
- **Config key trùng ý nghĩa, tên khác nhau:** `chat_retrieve_top_k` vs `retrieve_top_k`, `chat_rerank_top_k` vs `rerank_top_k` vs `chat_rerank_top_k_clinical` — hai bộ top_k (một cho chat path, một cho legacy pipeline) dễ nhầm.
- **Tên file runner trùng chức năng:** `tasks.sh`, `scripts/run_all.sh`, `scripts/RUN.sh`, `scripts/RUN.ps1`, `scripts/KB.ps1`.

### 7. Technical Debt Review

| ID | Loại | Vị trí | Mô tả | Ảnh hưởng | Confidence |
|---|---|---|---|---|---|
| TD1 | God module | `chat/normalizer.py` (1843 dòng) | Toàn bộ extraction theo lexicon/regex liệt kê tay; design doc đã đề xuất tách nhưng list khổng lồ vẫn còn nguyên (refactor confidence chỉ "bọc" thêm, không thay thế) | Cao — khó bảo trì, dễ vỡ regex | High |
| TD2 | Lexicon phình | `guardrails/runner.py` `_ACNE_SCOPE_TERMS` (hàng trăm literal) + tương tự trong `intake.py` (`_SAFETY_SIGNAL_TERMS`, `_ALLOWED_ACNE_REGION_TERMS`) | Trùng lặp ý niệm "acne scope terms" ở nhiều nơi; cùng một khái niệm liệt kê nhiều bản | Cao — sửa một nơi dễ quên nơi khác | High |
| TD3 | Đường dẫn song song | `pipeline/hybrid.py` + `llm_only.py` (legacy) vs `chat/runtime.py` + `_retrieval.py` | Hai code path retrieval/generation; legacy vẫn được `di.py` khởi tạo & inject | Cao — drift logic, double maintenance | High |
| TD4 | Script monkey-patch ở root | `add_boosts.py`, `fix_pronoun.py` | Script *sửa source bằng regex replace* (`add_boosts.py` chèn config vào `config.py`; `fix_pronoun.py` thay regex trong `intent_router.py`). Một lần dùng, còn sót lại → cực kỳ nguy hiểm nếu chạy nhầm | Cao (nếu chạy lại) | High |
| TD5 | Hardcode path | `upload_to_hf.py` | `GGUF_PATH = r"E:\project\AcneLLM\..."` hardcode tuyệt đối Windows | Thấp–TB | High |
| TD6 | Artifact lẫn source | Root *.html (5 file, ~310KB), `*.xlsx`, `prompt_simulation_full.md`, `context.md` | Tài liệu/sim/audit nằm chung root với code | TB — nhiễu repo, khó điều hướng | High |
| TD7 | Config drift (default phân tán) | `config.py` vs `di.py` vs `runtime.py` | Cùng một setting có default khác nhau ở nơi khai báo và nơi `getattr(..., default)`: `llm_temperature` = 0.35 (config) nhưng fallback 0.3 (runtime) và 0.35 (di); `llm_use_modelfile_system` = True (config) nhưng `getattr(..., False)` (di) | TB — hành vi phụ thuộc nguồn đọc | High |
| TD8 | Dead/deprecated flag | `CHAT_USE_LLM_PLANNER` | `context.md` ghi rõ DEPRECATED, không còn tác dụng (planner đã rule-based) nhưng vẫn còn trong env | Thấp | High (docs xác nhận) |
| TD9 | Golden set lan man | `data/golden_*.jsonl` (≥8 biến thể) | Nhiều phiên bản golden/test set không rõ cái nào là canonical | TB — eval không reproducible | Medium |
| TD10 | Defensive over-engineering | `intake.py` `_scope_check_compat`, `_supports_keyword`, nhiều `getattr(..., default)`/`hasattr` | Lớp tương thích cho nhiều chữ ký hàm → ám chỉ API nội bộ chưa ổn định | TB | Medium |
| TD11 | Boilerplate trùng | `intake.py` — 4–5 khối `return IntakeResult(...)` gần như giống hệt cho mỗi nhánh refuse | TB — sửa field phải đụng nhiều chỗ | High |
| TD12 | Inline import | `runtime.py` `import re as _re` + `from .extraction_confidence import build_confidence_hint` trong thân vòng/try | Thấp — micro-perf + khó đọc | High |
| TD13 | `.pycache_test/`, `.pytest_cache/` ở root tracked? | root | Thư mục cache lạc; cần kiểm tra gitignore | Thấp | Medium |

**Dead code / experimental [Hypothesis]:** `vision/` chỉ có `MockVision` (stub) — đã khai báo trong container nhưng chưa thấy đường dùng thực trong chat flow. Cần xác nhận trước khi coi là dead. `llm/qa_generator.py`, `crawler/sources/pubmed.py` có thể chỉ dùng cho offline scripts — không phải dead nhưng tách biệt runtime.

**TODO/FIXME:** `grep` trong `src/` trả về **0** TODO/FIXME/XXX/HACK — sạch ở mức comment marker (nhưng "debt thật" nằm ở cấu trúc, không phải marker).

### 8. Dependency Review (Confidence: Medium — chưa chạy phân tích import tĩnh đầy đủ)

- **Có thể không dùng ở runtime chat (chỉ scripts/eval):** `openai` (judge/dataset gen), `trafilatura`, `readability-lxml`, `beautifulsoup4`, `lxml`, `tenacity`, `datasketch`, `langdetect`, `playwright`, `ddgs` — đều thuộc crawl/eval. **Đề xuất:** tách thành optional extras (`[crawl]`, `[eval]`) để image runtime nhẹ hơn. **[cần xác minh từng import]**
- **Trùng chức năng tiềm năng:** `langdetect` vs `clinical_planner.detected_language` + `llm/language.py` — có thể có ≥2 cơ chế phát hiện ngôn ngữ. **[Hypothesis]**
- **Nặng & rủi ro vận hành:** `torch`, `sentence-transformers`, `transformers`, `chromadb`, `playwright` — kích thước lớn, nhạy version. `chromadb>=0.5,<2.0` là khoảng rất rộng → rủi ro breaking giữa 0.5 và 1.x. **Đề xuất pin chặt hơn.** (Confidence: High về độ rộng range.)
- **Version conflict tiềm năng:** `transformers>=4.44` + `sentence-transformers>=3.0` + `torch>=2.2` không pin trần → CI có thể kéo bản mới gây vỡ. Lockfile `uv.lock` chỉ 129 bytes (gần như rỗng) → **không có lock thực sự**. (Confidence: High.)

---

## PHASE 3 — Potential Bug Analysis

> Không sửa bug. Chỉ liệt kê bug tiềm năng kèm bằng chứng & độ tin cậy.

---

**BUG-01 — Cross-session/cross-query cache leak qua retrieval cache key**
- Location: `chat/_retrieval.py` → `_cache_key` + `cached_retrieve` (`cache.py`)
- Description: Cache key gồm `(queries, top_k, rerank_top_k, min_score, _clinical_fingerprint, _cache_safety_terms)`. Không gồm `session_id` (cố ý, để share giữa session giống nhau). Fingerprint cố gắng bao mọi field clinical, nhưng nếu một field ảnh hưởng retrieval mà **không** nằm trong fingerprint (vd `allergies`, `treatment_goals`, `red_flags_input`, `scarring_signs`) thì hai user khác nhau có thể nhận cùng cache.
- Evidence: `_clinical_fingerprint` liệt kê thủ công age/sex/skin_type/duration/pregnant/breastfeeding/lesion_types/lesion_distribution/inflammation/hormonal/medications/current_products — **thiếu** allergies, treatment_goals, red_flags_input, scarring_signs.
- Impact: **Medium** (retrieval có thể không phản ánh field bị bỏ sót; không phải PII leak vì chỉ là chunk KB)
- Likelihood: Possible
- Confidence: Medium
- Suggested investigation: So `build_retrieval_query_from_user` xem field nào thực sự vào query; nếu field đó không vào query thì fingerprint thiếu là vô hại.
- Risk of fixing: Medium (đổi cache key làm invalidate cache + có thể giảm hit-rate)

**BUG-02 — `completeness_hint` có thể chưa khởi tạo (UnboundLocalError) [Hypothesis]**
- Location: `chat/runtime.py` mục "2. Completeness hint"
- Description: `completeness_hint` được gán trong nhánh `if completeness is not None and completeness.followup_question:` và các `elif kind==...`. Nếu có code path dùng `completeness_hint` mà biến chưa được khởi tạo ở scope ngoài, sẽ `UnboundLocalError`.
- Evidence: Đoạn đọc được bắt đầu giữa chừng; cần xác nhận có dòng `completeness_hint = None` (hoặc `""`) ở đầu hàm trước khối if. `c.prompt.build(..., completeness_hint=completeness_hint)` được gọi vô điều kiện ở dưới.
- Impact: High (500 error trong stream) **nếu** thật
- Likelihood: Rare (nhánh hiếm)
- Confidence: **Low** — chưa đọc đủ dòng khởi tạo; đánh dấu Hypothesis.
- Suggested investigation: Đọc 5–20 dòng đầu khối completeness trong `runtime.py` để xác nhận có khởi tạo mặc định.
- Risk of fixing: Safe (thêm `completeness_hint = ""` đầu hàm)

**BUG-03 — Word/char limit đo trên `message` gốc, không phải clean_text; lỗi trả ValueError thô**
- Location: `chat/intake.py::run_intake` (đầu hàm) + `runtime.py` bọc `try/except Exception`
- Description: `ValueError("Tin nhắn quá dài...")` raise trong `run_intake`, được `stream_chat_sse` bắt bởi `except Exception` chung → trả message lỗi generic "Đã xảy ra lỗi, vui lòng thử lại." thay vì thông báo "quá dài" thân thiện.
- Evidence: `runtime.py` chỉ có một `except Exception as e:` cuối cùng yield `_event("error", "Đã xảy ra lỗi...")`.
- Impact: Medium (UX: user gửi tin quá dài nhận lỗi sai ngữ cảnh)
- Likelihood: Likely (input dài là phổ biến)
- Confidence: High
- Suggested investigation: Xác nhận `chat.py` route có bắt `ValueError` riêng trước khi vào stream không.
- Risk of fixing: Safe

**BUG-04 — `except Exception` nuốt lỗi giữa stream sau khi đã yield token**
- Location: `chat/runtime.py` khối `try/except` bao toàn bộ `stream_chat_sse`
- Description: Nếu lỗi xảy ra **sau khi** đã yield một số token (vd lỗi khi persist session, audit, hoặc rerank lazy), client đã nhận nội dung một phần rồi nhận thêm event `error` + `done(mode=error)`. Trạng thái UI có thể không nhất quán (đã hiển thị answer dở + báo lỗi).
- Evidence: `append_turn`/`audit.log` nằm trong cùng try; bất kỳ exception nào sau vòng token đều rơi vào except chung.
- Impact: Medium
- Likelihood: Possible
- Confidence: Medium
- Suggested investigation: Tách persist/audit ra ngoài try chính hoặc bọc try riêng (best-effort).
- Risk of fixing: Medium (thay đổi luồng xử lý lỗi)

**BUG-05 — Token overflow: prompt chars không được kiểm tra so với `num_ctx`**
- Location: `runtime.py` build prompt + `llm_num_ctx=4096`
- Description: `max_context_chars=4500` cho RAG context, cộng system + history (sliding window 2000 char) + user. Ước lượng `prompt_chars / 3.5 ≈ tokens`. Với `num_ctx=4096`, prompt lớn + `num_predict=1200` có thể vượt context window → Ollama tự cắt (truncate) phần đầu (thường là system/safety instructions) **âm thầm**.
- Evidence: `config.py` `llm_num_ctx=4096`, `llm_num_predict=1200`; `chat_max_context_chars` default 4500; history block tới 2000 char; không thấy guard so tổng với num_ctx.
- Impact: **High** (mất system/safety prompt do truncate → trả lời kém an toàn hoặc lệch)
- Likelihood: Possible→Likely khi RAG context đầy + history dài
- Confidence: Medium
- Suggested investigation: Log `prompt_tokens` thực từ Ollama response và so với num_ctx; cân nhắc tăng num_ctx hoặc siết context budget.
- Risk of fixing: Medium (đụng cấu hình sinh)

**BUG-06 — CJK strip per-token có thể cắt nhầm ranh giới ký tự / từ hợp lệ [Hypothesis]**
- Location: `runtime.py` `_CJK_RE.sub("", token)`
- Description: Strip mọi ký tự CJK trong từng token để chống model lẫn tiếng Trung. Nếu nội dung hợp lệ có ký tự CJK (vd tên hoạt chất, trích dẫn) sẽ bị xoá; ngoài ra strip per-token có thể để lại khoảng trắng/đứt mạch.
- Evidence: Có `logger.warning("CJK guard: stripped ...")` → cơ chế thực sự hoạt động và đã từng kích hoạt.
- Impact: Low–Medium
- Likelihood: Rare cho tiếng Việt thuần
- Confidence: Low
- Risk of fixing: Caution (đây là safety guard có chủ đích)

**BUG-07 — Routing dựa lexicon: false negative ở long-tail (sai luồng)**
- Location: `chat/intent_router.py`, `guardrails/runner.py` (`_ACNE_SCOPE_TERMS`), `intake._is_acne_scope`
- Description: Toàn bộ scope/intent dựa khớp chuỗi. Câu mới/viết sai/teencode lạ không khớp → `acne_signal=False` → auto-downgrade về `llm_only` (bỏ RAG) hoặc refuse sai. Design doc chính thức thừa nhận "phủ kém ở đuôi".
- Evidence: `design doc` mục 1 + danh sách literal khổng lồ; `_resolve_mode` downgrade hybrid→llm_only khi `not is_acne_scope_text`.
- Impact: Medium (giảm chất lượng/độ an toàn tư vấn, không crash)
- Likelihood: Likely (long-tail input tiếng Việt rất đa dạng)
- Confidence: High
- Suggested investigation: Đo recall scope trên golden set thực; cân nhắc embedding-KNN scope (nhánh #13 trong design doc, chưa làm).
- Risk of fixing: High (đụng routing = đụng tim hệ thống)

**BUG-08 — `mask_pii`/`contains_pii` chạy 2 lần và có thể không nhất quán [Hypothesis]**
- Location: `intake.py` set `pii_detected=contains_pii(clean_text)` ở mỗi return; `runtime.py` lại `mask_pii(clean_message)` chỉ khi `pii_detected`.
- Description: PII detect trên `clean_text` (đã preprocess) nhưng session lưu `raw_message` (chưa mask). Nếu raw chứa PII (sđt/email) mà preprocess làm biến dạng → `contains_pii(clean_text)` có thể False → **raw PII vẫn ghi vào JSONL session không mask**.
- Evidence: `append_turn(role="user", content=intake.raw_message)` (comment F10: lưu nguyên văn) + audit dùng `clean_message`/mask.
- Impact: **High** (PII lưu trữ không mask trong session JSONL)
- Likelihood: Possible
- Confidence: Medium
- Suggested investigation: Kiểm tra `prepare_user_text` có giữ nguyên số điện thoại/email không; kiểm tra chính sách lưu PII trong session store.
- Risk of fixing: Medium (đụng nội dung lưu lịch sử = ảnh hưởng fold/normalize trên history)

**BUG-09 — RRF fusion chuẩn hoá `score / max_score` có thể ZeroDivision đã chặn nhưng mất thông tin tuyệt đối**
- Location: `_retrieval.py::merge_retrieval_outputs`
- Description: `chunk.score = score / max_score` chuẩn hoá về [0,1]. Vì `min_score`/`chat_min_citation_score` lọc theo score, sau khi chuẩn hoá theo max của *từng request*, ngưỡng citation tuyệt đối mất ý nghĩa so sánh giữa request (một chunk yếu trong request toàn chunk yếu vẫn được score≈1.0).
- Evidence: `max_score = max(fused.values(), default=0.0)`; `min_score` so với score đã chuẩn hoá ở `drop_noisy_chunks`.
- Impact: Medium (citation gate không nhất quán → chunk kém vẫn cite)
- Likelihood: Possible
- Confidence: Medium
- Risk of fixing: Medium

**BUG-10 — Clarify-loop hard stop dùng `total_clarify_count` từ session có thể đếm sai khi history bị TTL/cắt**
- Location: `intake.py::_session_clarify_count` + `_history_clarify_count`
- Description: `max(history_count, session.total_clarify_count)`. Session JSONL có TTL=1800s và max 6 turns; history bị cắt → `history_count` thấp, phải dựa `total_clarify_count`. Nếu store không cập nhật field này nhất quán, vòng clarify có thể không bao giờ break (hỏi mãi) hoặc break quá sớm.
- Evidence: `hasattr(session, "total_clarify_count")` + fallback → ám chỉ field optional, không chắc luôn tồn tại.
- Impact: Medium (UX: hỏi lại lặp vô hạn)
- Likelihood: Possible
- Confidence: Low–Medium
- Risk of fixing: Medium

**BUG-11 — Concurrency: JSONL session store + DiskCache + SQLite audit dưới tải đồng thời**
- Location: `db/jsonl_session_store.py`, `cache.py`, `db/audit.py`
- Description: SSE là long-lived; nhiều request cùng `session_id` (user gửi nhanh, refresh) có thể đọc-ghi JSONL đồng thời → race trên append/rewrite file. SQLite ghi đồng thời có thể `database is locked`.
- Evidence: Session lưu "một file per session" (append + rewrite khi cắt turns); audit có WAL files (`audit.db-wal`, `audit.db-shm` tồn tại → WAL bật, tốt) nhưng JSONL không có khoá rõ.
- Impact: Medium–High (mất turn, file corrupt)
- Likelihood: Possible (sản phẩm tư vấn ít concurrent/session, nhưng tồn tại)
- Confidence: Low (chưa đọc lock impl trong jsonl_session_store)
- Suggested investigation: Đọc `jsonl_session_store.py` xem có file lock / atomic write.
- Risk of fixing: Medium

**BUG-12 — `effective_temperature` cho knowledge nâng lên ≥0.5 + `num_predict=-1` (không cap) → câu trả lời dài/lan man, chi phí token**
- Location: `runtime.py` `_knowledge_temp = max(_default_temp, 0.5)` + `_stream_num_predict = -1`
- Description: Knowledge intent bỏ giới hạn output và tăng temp. Kết hợp num_ctx 4096 → dễ chạm trần context khi đang stream dài, hoặc model lặp.
- Impact: Low–Medium
- Likelihood: Possible
- Confidence: Medium
- Risk of fixing: Caution (đã có chủ đích để tránh cắt sớm)

**BUG-13 — Genital-scope hard reject dựa khớp chuỗi → false positive/negative trên thuật ngữ y khoa hợp lệ [Hypothesis]**
- Location: `intake.py` genital check + `GuardrailRunner.is_genital_scope`
- Description: Hard reject ngay nếu `is_genital_scope` true và không mixed. Khớp chuỗi có thể chặn nhầm câu hợp lệ (vd "mụn ở vùng cằm gần..." chứa token nhạy cảm) hoặc bỏ sót biến thể.
- Impact: Medium (refuse sai)
- Likelihood: Possible
- Confidence: Low
- Risk of fixing: High (safety-critical)

**BUG-14 — Security: API key middleware + rate limit có thể bị tắt nếu `settings.api_key` rỗng [Hypothesis]**
- Location: `api/app.py` `APIKeyMiddleware(api_key=settings.api_key)`; `.env.example` `API_KEY=` (rỗng)
- Description: Nếu `api_key` rỗng và middleware "no key → allow all", endpoint chat public. Cần xác nhận hành vi khi key rỗng.
- Impact: High nếu deploy public không set key
- Likelihood: Possible
- Confidence: Low (chưa đọc `observability.py`)
- Suggested investigation: Đọc `APIKeyMiddleware` xử lý key rỗng.
- Risk of fixing: Safe (chỉ siết)

**Database bugs (Confidence: Medium):** Chưa thấy index tường minh trên `audit.db` (cần `ORDER BY timestamp` theo context.md) — **[cần đọc `db/audit.py` schema]**. Missing index → admin queries chậm khi log lớn. Orphan data: session JSONL hết TTL nhưng file có thể không được dọn (cần xác nhận cleanup job).

**Deployment risks (Confidence: Medium):** `docker-compose` ordering ollama→ollama-init→acne-llm→frontend; nếu `depends_on` không kèm healthcheck, `acne-llm` có thể start trước khi model load xong → first request timeout (`ollama_generate_timeout=30s`). Config drift giữa `.env`, `.env.baseline`, `.env.example`, `config.py`, `Modelfile` (xem TD7) là rủi ro version drift thực tế.

---

## PHASE 4 — Refactoring Opportunities

| # | Current State | Proposed Improvement | Benefits | Risks | Effort | Safety |
|---|---|---|---|---|---|---|
| R1 | `normalizer.py` 1843 dòng, lexicon + regex + logic trộn | Tách thành `normalizer/` package: `lexicon.py` (data), `extractors/` (per-field), `assemble.py`. Giữ `normalize_chat_message` signature như cũ | Dễ test từng field, giảm rủi ro sửa | Vỡ extraction → sai routing | L | CAUTION |
| R2 | `_ACNE_SCOPE_TERMS` + safety terms trùng ở `guardrails` & `intake` | Gom về một module `domain/lexicon.py` (single source) | Hết drift, sửa một nơi | Import cycle | M | CAUTION |
| R3 | `pipeline/` legacy song song với `chat/runtime` | Xác minh không dùng → đánh dấu deprecated rõ ràng, ngừng inject trong `di.py` (không xoá vội) | Giảm double-maintenance, hết nhầm lẫn | Một số test/script có thể phụ thuộc | M | CAUTION |
| R4 | `intake.py` 5 khối `return IntakeResult(...)` refuse trùng | Factory `_refuse_result(...)` gom field chung | Bớt boilerplate, sửa field 1 chỗ | Sai sót khi gom | S | SAFE |
| R5 | Default config phân tán (`getattr(..., default)` lệch `config.py`) | Bỏ default trong `getattr`, để Settings là single source; log effective config (đã có một phần) | Hết config drift TD7 | Lộ ra chỗ trước đây dựa default ẩn | M | CAUTION |
| R6 | Script monkey-patch ở root | Xoá `add_boosts.py`, `fix_pronoun.py` (đã hoàn thành nhiệm vụ); chuyển `upload_to_hf.py`→`scripts/` + dùng env path | Tránh chạy nhầm phá source | — | S | SAFE (sau khi xác nhận đã apply) |
| R7 | Artifact HTML/xlsx/sim ở root | Chuyển vào `docs/` hoặc `analysis/`; thêm `.gitignore` cho artifact generate được | Repo gọn | Link tham chiếu gãy | S | SAFE |
| R8 | Logging: format string lẫn f-string + loguru positional (`{}`) lẫn lộn | Chuẩn hoá một style loguru, thêm `extra={session_id}` thay vì `sid_short` thủ công | Log nhất quán, query được | — | M | SAFE |
| R9 | Error handling: 1 `except Exception` khổng lồ trong stream | Tách try theo giai đoạn (intake / retrieve / generate / persist) + map ValueError→message thân thiện | Lỗi đúng ngữ cảnh (BUG-03/04) | Đổi luồng lỗi | M | CAUTION |
| R10 | Testing: 40 file phẳng, một số phụ thuộc data nội bộ chưa ship | Đánh dấu `@pytest.mark.integration`, tách unit thuần; thêm CI gate cho subset chat pipeline | CI ổn định, chạy nhanh subset | — | M | SAFE |
| R11 | Dependencies gộp chung | Tách `[crawl]`/`[eval]` extras; sinh lock thực (`uv lock`/`pip-compile`) | Image runtime nhẹ, reproducible | Quên import optional | M | SAFE |
| R12 | Ticket-coded comments (S2-B, M3, F10...) | Map sang ADR/CHANGELOG hoặc giải thích ý nghĩa | Giảm tribal knowledge | — | S | SAFE |

---

## PHASE 5 — Cleanup TODO Roadmap

### High Impact

- [ ] **TD4/R6 — Xử lý script monkey-patch root.** *Benefit:* loại nguy cơ chạy nhầm phá source. *Risk:* phải xác nhận thay đổi đã được apply vào `config.py`/`intent_router.py`. *Effort:* S. *Safety:* SAFE (sau xác nhận).
- [ ] **TD7/R5 — Hợp nhất default config về `Settings`.** *Benefit:* hết config drift (temperature/use_modelfile_system). *Risk:* lộ default ẩn. *Effort:* M. *Safety:* CAUTION.
- [ ] **BUG-03/BUG-04/R9 — Tách error handling trong stream + ValueError→message.** *Benefit:* UX lỗi đúng ngữ cảnh, không nuốt lỗi. *Risk:* đổi luồng lỗi. *Effort:* M. *Safety:* CAUTION.
- [ ] **BUG-08 — Rà soát PII trong session JSONL (raw lưu không mask).** *Benefit:* compliance/an toàn dữ liệu. *Risk:* đụng nội dung history. *Effort:* M. *Safety:* CAUTION.
- [ ] **BUG-05 — Kiểm tra token budget vs num_ctx, log prompt_tokens thực.** *Benefit:* tránh truncate system/safety âm thầm. *Risk:* đụng config sinh. *Effort:* M. *Safety:* CAUTION.

### Medium Impact

- [ ] **TD3/R3 — Đánh dấu `pipeline/` legacy, ngừng inject.** *Benefit:* hết double path. *Risk:* test phụ thuộc. *Effort:* M. *Safety:* CAUTION.
- [ ] **TD2/R2 — Gom lexicon scope/safety về một module.** *Benefit:* hết drift lexicon. *Risk:* import cycle. *Effort:* M. *Safety:* CAUTION.
- [ ] **BUG-01 — Bổ sung/đối soát field trong cache fingerprint.** *Benefit:* retrieval chính xác. *Risk:* invalidate cache. *Effort:* S. *Safety:* CAUTION.
- [ ] **TD11/R4 — Factory cho IntakeResult refuse.** *Benefit:* bớt boilerplate. *Risk:* sai field. *Effort:* S. *Safety:* SAFE.
- [ ] **TD9/R11 — Chuẩn hoá golden sets + sinh lockfile thực.** *Benefit:* eval reproducible. *Risk:* —. *Effort:* M. *Safety:* SAFE.
- [ ] **BUG-11 — Kiểm tra atomic write/lock cho JSONL session.** *Benefit:* tránh corrupt dưới tải. *Risk:* —. *Effort:* M. *Safety:* SAFE.

### Low Impact

- [ ] **TD6/R7 — Dọn artifact HTML/xlsx khỏi root.** *Effort:* S. *Safety:* SAFE.
- [ ] **R8/R12 — Chuẩn hoá logging + giải mã ticket comments.** *Effort:* S–M. *Safety:* SAFE.
- [ ] **TD5 — `upload_to_hf.py` dùng env path.** *Effort:* S. *Safety:* SAFE.
- [ ] **TD8 — Gỡ flag `CHAT_USE_LLM_PLANNER` deprecated.** *Effort:* S. *Safety:* SAFE.
- [ ] **TD12 — Đưa inline import lên đầu module.** *Effort:* S. *Safety:* SAFE.
- [ ] **R10 — Phân nhóm test unit/integration + CI subset.** *Effort:* M. *Safety:* SAFE.

---

## PHASE 6 — Priority Ranking

### Top 10 Technical Debts
1. TD1 — `normalizer.py` god module (1843 dòng)
2. TD3 — Hai code path retrieval (`pipeline/` legacy vs `chat/runtime`)
3. TD2 — Lexicon scope/safety trùng lặp nhiều nơi
4. TD7 — Config drift (default phân tán, lệch nhau)
5. TD4 — Script monkey-patch source ở root
6. TD11 — Boilerplate `IntakeResult` refuse
7. TD9 — Golden/test set lan man + `uv.lock` rỗng
8. TD10 — Lớp tương thích phòng thủ (`_supports_keyword`, `_scope_check_compat`)
9. TD6 — Artifact lẫn source ở root
10. TD8 — Flag deprecated còn sót

### Top 10 Refactoring Opportunities
1. R1 — Tách `normalizer` thành package per-field
2. R3 — Cô lập/deprecate `pipeline/` legacy
3. R5 — Hợp nhất config defaults về Settings
4. R2 — Single-source lexicon domain
5. R9 — Tách error handling theo giai đoạn
6. R11 — Optional extras + lockfile thực
7. R4 — Factory IntakeResult
8. R10 — Phân tầng test + CI gate
9. R8 — Chuẩn hoá logging
10. R6/R7 — Dọn root (scripts + artifacts)

### Top 10 Potential Bugs (theo Impact × Likelihood × Confidence)
1. BUG-08 — PII raw lưu session không mask (High/Possible/Med)
2. BUG-05 — Token overflow vs num_ctx truncate safety prompt (High/Possible/Med)
3. BUG-07 — Routing long-tail false negative → sai luồng (Med/Likely/High)
4. BUG-03 — Tin nhắn quá dài → lỗi generic sai ngữ cảnh (Med/Likely/High)
5. BUG-01 — Cache fingerprint thiếu field (Med/Possible/Med)
6. BUG-04 — `except Exception` nuốt lỗi giữa stream (Med/Possible/Med)
7. BUG-11 — Race condition JSONL/SQLite dưới tải (Med-High/Possible/Low)
8. BUG-09 — RRF normalize làm citation gate mất nghĩa tuyệt đối (Med/Possible/Med)
9. BUG-10 — Clarify-loop counter có thể sai (Med/Possible/Low-Med)
10. BUG-14 — API key rỗng có thể mở public endpoint (High/Possible/Low) **[Hypothesis]**

### Top 10 Highest ROI Improvements (Impact × Risk thấp × Maintainability gain)
1. R4 — Factory IntakeResult (S, SAFE, giảm debt ngay)
2. R6 — Xoá script monkey-patch (S, SAFE, loại rủi ro lớn)
3. R7 — Dọn artifact root (S, SAFE)
4. BUG-03 fix — map ValueError→message (S, SAFE-ish)
5. TD8 — gỡ flag deprecated (S, SAFE)
6. R12 — giải mã ticket comments / ADR (S, SAFE)
7. R11 — lockfile thực (M, SAFE, reproducibility lớn)
8. R10 — CI subset chat pipeline (M, SAFE)
9. R5 — hợp nhất config defaults (M, CAUTION, ngăn lớp lỗi tương lai)
10. BUG-05 investigation — log prompt_tokens (M, SAFE chỉ log)

---

## PHASE 7 — Final Verdict

### Strengths
- **Tài liệu xuất sắc** (`context.md` mô tả pipeline chính xác đến từng bước; README đầy đủ; docs/ có design rationale + ADR-style).
- **Kiến trúc phân lớp rõ ràng** với DI container tường minh; graceful degrade (RAG optional → llm_only).
- **An toàn y tế được coi trọng**: nhiều tầng guardrail (scope, OOD, genital, drug, PII mask, safety suffix), phù hợp domain nhạy cảm.
- **Tách bạch deterministic intake vs generation** — dễ test, reproducible (rule-based planner, không LLM trong query building).
- **Có observability** (audit SQLite, Prometheus metrics, logging giàu thông tin theo từng bước ①–⑦).
- **Test suite đáng kể** (40 file, bao phủ normalizer/router/intake/stream/guardrails/retrieval).
- **Xử lý secret đúng**: `.env` không tracked, `.env.baseline`/`.env.example` chỉ chứa key rỗng/placeholder; không thấy secret thật trong git.

### Weaknesses
- **God modules rule-based** (`normalizer.py` 1843, `guardrails` lexicon hàng trăm literal) → khó bảo trì, phủ kém long-tail (chính design doc thừa nhận).
- **Hai code path song song** (`pipeline/` legacy vs `chat/runtime`) → drift.
- **Config drift** giữa nhiều nguồn default.
- **Root directory lộn xộn** (script monkey-patch nguy hiểm, artifact HTML/xlsx lẫn code).
- **Error handling thô** trong stream (một `except Exception` bao tất cả).
- **Routing/scope brittle** do khớp chuỗi.
- **Reproducibility yếu** ở phần lock dependency (`uv.lock` ~rỗng) và golden sets phân mảnh.

### Architecture Health Score (0–10)

| Hạng mục | Điểm | Ghi chú |
|---|---:|---|
| Architecture | 7.5 | Phân lớp tốt, DI rõ; trừ điểm vì code path song song |
| Maintainability | 5.5 | God modules + lexicon trùng kéo xuống |
| Readability | 6.5 | Tốt ở orchestration; trừ vì comment ticket-coded + mix ngôn ngữ |
| Scalability | 6.0 | JSONL session + SQLite + DiskCache ổn cho local, hạn chế đa-instance/concurrency |
| Reliability | 6.0 | Graceful degrade tốt; trừ vì error handling thô + token-budget chưa kiểm soát |
| Security | 6.5 | Secret handling tốt, có guardrail/PII; cần xác nhận API key rỗng & PII session |
| Testing | 6.5 | Bao phủ rộng; trừ vì phụ thuộc data nội bộ + chưa phân tầng/CI gate |
| Documentation | 8.5 | Điểm sáng nhất của dự án |

**Tổng quan (trung bình ~6.6/10):** Codebase **lành mạnh ở mức tốt**, đặc biệt cho một dự án domain-specific; nợ kỹ thuật tập trung và **dọn được mà không cần đập đi xây lại**.

### Refactoring Recommendation

➡️ **Nên tái cấu trúc từng phần (incremental refactor).** Không cần đại tu lớn. Ưu tiên: (1) dọn rác root + bỏ default config phân tán (ROI cao, rủi ro thấp), (2) cô lập `pipeline/` legacy, (3) tách `normalizer` có test bảo vệ. **KHÔNG** nên tái cấu trúc lớn vì hệ thống đang hoạt động và phần lớn vấn đề là cục bộ.

### Important Warning — Module/flow KHÔNG được sửa khi chưa hiểu rõ dependency & chưa có test bảo vệ

> Các thành phần sau là **safety-critical hoặc tim của pipeline**. Đụng vào mà thiếu test coverage tương ứng có nguy cơ làm hỏng chất lượng/độ an toàn tư vấn:

1. **`guardrails/runner.py` + `ood_detector.py` + genital/scope checks** — sai một dấu → refuse nhầm hoặc bỏ lọt nội dung ngoài phạm vi y tế. Safety-critical.
2. **`chat/intent_router.py` + `_resolve_mode`** — điều khiển toàn bộ nhánh xử lý + bật/tắt RAG. Sai → trả lời sai loại.
3. **`chat/normalizer.py` + `extraction_confidence.py`** — đầu vào của routing & completeness; vỡ extraction lan ra toàn pipeline.
4. **`chat/_retrieval.py` cache key + RRF fusion** — đụng cache key sai có thể gây cross-context retrieval.
5. **`chat/runtime.py` SSE stream loop + safety suffix + CJK guard** — đụng vào dễ tạo trạng thái UI/an toàn không nhất quán giữa stream.
6. **`chat/session.py` fold_history_facts + JSONL store** — sai merge rule → "nhớ" sai facts của user qua các turn.
7. **`config.py` validators (`keep_alive`, `num_ctx`)** — sai → Ollama 400 / OOM lúc startup.

> Trước khi chạm các mục trên: bổ sung test đặc tả hành vi hiện tại (characterization tests), rồi mới refactor để giữ behavior bất biến.

---

### Giả định & giới hạn của audit này (minh bạch về độ tin cậy)

- **Chưa đọc toàn văn:** toàn bộ `normalizer.py` (1843 dòng), `intent_router.py`, `completeness.py`, `session.py`, `db/jsonl_session_store.py`, `db/audit.py` schema, `api/observability.py`, `crawler/`, `eval/`. Các bug liên quan (BUG-02, 08, 10, 11, 13, 14) vì thế ở mức **Low–Medium confidence** và một số gắn **[Hypothesis]** — cần đọc thêm để khẳng định.
- **Chưa chạy** test suite, eval, hay phân tích import tĩnh (vì môi trường thiếu Ollama/embedding model như chính docs ghi nhận). Nhận định về dependency unused là **để điều tra**, không phải kết luận.
- **Ưu tiên hiểu đúng hơn đề xuất:** ở những chỗ chưa chắc, tài liệu ghi rõ "cần investigate" thay vì khẳng định.
