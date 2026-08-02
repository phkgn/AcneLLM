# AcneLLM — Project Context

Chatbot tư vấn da mụn tiếng Việt. Local-first RAG + fine-tuned LLM (Ollama), không phụ thuộc cloud.

---

## Stack

| Layer | Tech |
|---|---|
| LLM | `acnellm-v2-q4` (Qwen2.5-7B Q4 via Ollama), fallback `qwen2.5:3b` |
| Micro-classifier | `qwen2.5:0.5b` (intent routing) |
| Embedding | `AITeamVN/Vietnamese_Embedding` (dim=1024) |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Vector DB | ChromaDB |
| Sparse index | BM25 (rank-bm25) |
| API | FastAPI + uvicorn, SSE streaming |
| Frontend | Next.js 15 + Tailwind + Zustand |
| Session store | JSONL per session (TTL 1800s, max 6 turns) |
| Audit | SQLite via `data/audit.db` |
| Config | pydantic-settings, đọc từ `.env` |

---

## Cấu trúc thư mục

```
src/acne_llm/
├── api/              FastAPI app, routes (chat, health, kb, metrics, admin)
├── chat/             Pipeline intake chính
│   ├── preprocess.py     prepare_user_text() → PreparedText
│   ├── normalizer.py     normalize_chat_message() → UserInput (rule-based NLP)
│   ├── intake.py         run_intake() — orchestrator toàn bộ pipeline
│   ├── intent_router.py  route_intent() → RouteDecision
│   ├── session.py        SessionStore, NormalizedSnapshot, fold_history_facts()
│   ├── runtime.py        stream_chat_sse() — generation + SSE streaming
│   ├── completeness.py   check_completeness()
│   ├── _retrieval.py     retrieve_for_chat()
│   ├── _prompt.py        build_prompt() — chọn template theo intent
│   └── _safety.py        safety context helpers
├── llm/
│   ├── ollama_backend.py  OllamaBackend
│   ├── prompt_builder.py  PromptBuilder (Jinja2)
│   ├── clinical_planner.py ClinicalQueryPlanner
│   └── query_expander.py
├── rag/
│   ├── retriever.py   HybridRetriever (dense + sparse fusion + rerank)
│   ├── vectorstore.py ChromaStore
│   ├── sparse.py      BM25Index
│   ├── embedder.py    Embedder (sentence-transformers)
│   ├── reranker.py    Reranker (cross-encoder)
│   └── chunker.py
├── schemas/
│   ├── core.py        UserInput, UserContext, AdviseOutput, RetrievedChunk, ...
│   └── clinical.py    AcneClinicalInput, ClinicalQueryPlan
├── guardrails/
│   ├── runner.py      GuardrailRunner
│   ├── ood_detector.py OOD detection + PII check
│   └── drug_checker.py
├── crawler/           Web crawler cho knowledge base
├── db/
│   ├── jsonl_session_store.py
│   ├── audit.py       AuditStore (SQLite)
│   └── session_store.py
├── eval/              judge.py, metrics.py (Hit@k, MRR, NDCG)
├── utils/
│   ├── retrieval_query.py  build_retrieval_query_from_user(), extracted_entities_from_user()
│   └── chunk_filter.py     drop_noisy_chunks(), drop_query_mismatched_chunks()
├── pipeline/          HybridPipeline, LLMOnlyPipeline (legacy wrappers)
├── vision/            stub (MockVision)
├── di.py              Container — dependency injection
├── config.py          Settings (pydantic-settings)
└── cache.py

scripts/
├── eval_rag.py        RAG eval: query gen (DeepSeek) + Hit@k/MRR/NDCG
├── build_kb.py        chunk + embed + index → chroma + bm25
├── crawl_all.py       crawl sources → data/raw/documents.jsonl
└── ...

LLMData/
├── chunk_qa/          Sinh QA pairs từ chunks (DeepSeek)
├── clinical_case/     Sinh clinical case scenarios
└── injection_qa/      Adversarial injection test cases

config/
├── prompts/           Jinja2 templates (stream_user, knowledge_user, clarify_user, ...)
├── guardrails.yaml
├── drugs_acne.yaml
└── ood_centroid.json

frontend/src/
├── app/               Next.js App Router
├── components/chat/   ChatWindow, MessageBubble, CitationCard, MessageInput
├── config/chatConfig.ts  API_BASE_URL (NEXT_PUBLIC_API_URL)
├── hooks/useSSE.ts
├── lib/api.ts
└── stores/chatStore.ts (Zustand)
```

---

## Pipeline chat (run_intake)

```
User message
  │
  ① prepare_user_text(raw)
  │   → PreparedText(clean_text, clean_text_no_accent, teencode_replaced)
  │
  ② normalize_chat_message(raw, mode, clean_text, clean_text_no_accent)
  │   → UserInput: lesions, skin_type, severity, distribution,
  │                products, medications, red_flags, age, sex, ...
  │
  ③ guardrails.pre_check(user)  — scope / OOD / PII / genital region
  │
  ④ route_intent(clean_text, user, history)
  │   → RouteDecision(primary_intent, query_subject, confidence, route_flags)
  │   primary_intent: advise | knowledge | clarify | reject
  │   query_subject:  self | other | general
  │
  ⑤ FORK by intent + query_subject
  │
  │  advise + self:
  │    ├── fold_history_facts(history)
  │    ├── check_completeness()
  │    ├── ClinicalQueryPlanner (RULE-BASED — dựng query RAG, KHÔNG gọi LLM)
  │    ├── retrieve_for_chat() → HybridRetriever
  │    └── stream → stream_user.j2
  │
  │  knowledge:
  │    ├── retrieve_for_chat()
  │    └── stream → knowledge_user.j2
  │
  │  clarify + self:
  │    ├── fold_history_facts()
  │    └── stream → clarify_user.j2
  │
  │  reject:  trả về ngay, không gọi LLM
  │
  ⑥ append_turn(session, snapshot)
  │   snapshot=None nếu query_subject != "self"
  │
  ⑦ AuditStore.log(entry)
```

---

## Session & context

- **SessionStore** (`JsonlSessionStore`): JSONL per session, TTL=1800s, max 6 turns
- **NormalizedSnapshot**: facts extracted từ mỗi turn
- **fold_history_facts()**: merge snapshots cũ vào user hiện tại
  - `reversed(snapshots)` → last-write-wins cho scalar fields
  - ADDITIVE cho lesion_types, distribution, red_flags
  - MAX_SEVERITY cho inflammation_level
- **format_history_block()**: sliding window 2000 char, anchor 400 char, truncate assistant 120 char

---

## Intent routing

`RouteDecision` fields:
- `primary_intent`: `advise` | `knowledge` | `clarify` | `reject`
- `query_subject`: `self` | `other` | `general`
- `confidence`: float
- `route_flags`: `repeated_question`, `emotional_distress`, `progress_followup`, `product_safety_check`

Micro-classifier `qwen2.5:0.5b` (`OllamaIntentClassifier`) — fast pre-classification.

---

## Retrieval

`build_retrieval_query_from_user(user, clean_text_normalized)` → query string:
```
lesions papule pustule ; distribution forehead ; severity moderate ; skin_type oily ; text mụn viêm...
```

`HybridRetriever`: dense (Chroma cosine) + sparse (BM25) → RRF fusion → cross-encoder rerank → chunk filters.

Config: `RETRIEVE_TOP_K`, `RERANK_TOP_K`, `CHAT_MIN_CITATION_SCORE`.

---

## Eval

`scripts/eval_rag.py` — 2 chế độ:
- **Part 1** (query gen): DeepSeek sinh queries từ chunks
- **Part 2** (retrieval eval): Hit@k / Recall@k / MRR@k / NDCG@k, k ∈ {1,3,5,10}
  - Pipeline y chang production: `prepare_user_text` → `normalize_chat_message` → `build_retrieval_query_from_user`
  - Targets: hit@3≥0.50, hit@5≥0.65, mrr@10≥0.35, ndcg@5≥0.40

---

## Docker

```bash
docker compose up
# Web UI: http://localhost:3000
# API:    http://localhost:8000
```

Thứ tự: `ollama` → `ollama-init` (load gguf từ `model/V2/Q4/` hoặc pull fallback) → `acne-llm` → `frontend`.

`model/` excluded khỏi image. Ollama load qua volume mount.

---

## Env quan trọng

| Key | Mặc định | Ghi chú |
|---|---|---|
| `LLM_MODEL` | `acnellm-v2-q4` | Ollama model name |
| `LLM_FALLBACK_MODEL` | `qwen2.5:3b` | |
| `INTENT_ROUTER_MODEL` | `qwen2.5:0.5b` | Micro-classifier |
| `EMBEDDING_MODEL` | `AITeamVN/Vietnamese_Embedding` | |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | |
| `CHAT_USE_LLM_PLANNER` | `true` | DEPRECATED — không còn tác dụng; planner là rule-based |
| `DEEPSEEK_API_KEY` | — | Chỉ dùng cho eval/dataset gen |
| `OPENAI_API_KEY` | — | Chỉ dùng cho LLM judge |

Xem `.env.example` để đầy đủ.

---

## Dev workflows

```bash
# Cài deps
./tasks.sh install

# Chạy backend local
./tasks.sh serve

# Chạy frontend local
./tasks.sh frontend

# Chạy qua Docker (full stack)
./tasks.sh docker-up

# Build knowledge base
./tasks.sh build-kb

# Tests
./tasks.sh test

# RAG eval
python scripts/eval_rag.py --skip-gen
```
