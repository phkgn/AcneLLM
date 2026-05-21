# AcneLLM — Current Project Context

Snapshot date: **2026-04-24**  
Workspace: `e:\project\AcneLLM`

## Tổng Quan

AcneLLM là hệ thống tư vấn da mụn tiếng Việt, local-first, dùng FastAPI làm backend cho Web UI (Next.js) và mobile client. Runtime inference dùng Ollama local; RAG hoạt động khi đủ vector index ChromaDB và sparse index BM25.

Tài liệu này mô tả **trạng thái repo hiện tại**, không phải toàn bộ mục tiêu ban đầu. `BLUEPRINT_AcneLLM.md` vẫn là thiết kế/roadmap gốc; `CONTEXT.md` là snapshot vận hành để sửa code và bàn giao tiếp mà không hiểu nhầm trạng thái.

Project thuộc Đề tài 29, có điểm tích hợp với:

- Đề tài 27: Vision, qua `VisionProtocol` và `VisionOutput`.
- Đề tài 28: Advanced RAG, qua các interface/protocol trong `rag/` và `crawler/`.

## Tech Stack

| Hạng mục | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.10+ (`pyproject.toml` cho phép `>=3.10`) |
| LLM runtime | Ollama local |
| LLM chính | `qwen2.5:7b` |
| LLM dự phòng | `qwen2.5:3b` |
| Embedding | `AITeamVN/Vietnamese_Embedding` |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Vector store | ChromaDB persistent, collection `acne_kb_vi` |
| Sparse index | `rank_bm25` + `underthesea`, lưu tại `data/bm25_index.pkl` |
| API | FastAPI + Uvicorn |
| Web UI | Next.js 15 + React 18 + TypeScript + Tailwind CSS (separate `frontend/`) |
| Crawler | `httpx`, Playwright fallback, trafilatura, readability-lxml, BeautifulSoup4 |
| Dedup | datasketch MinHash LSH, threshold `0.88` |
| Schema/config | Pydantic v2 + pydantic-settings |
| Prompt | Jinja2 templates |
| CLI/tasks | Typer, `tasks.ps1`, `tasks.sh`, Makefile |
| Logging | loguru |
| Testing | pytest + pytest-asyncio |

## Current Repository Shape

```text
AcneLLM/
├── config/
│   ├── settings.py             # Pydantic settings, reads .env
│   └── prompts/
│       ├── system.j2
│       ├── hybrid_user.j2
│       └── llm_only_user.j2
├── data/
│   ├── seed_sources.yaml       # 30+ configured crawl sources, some disabled
│   ├── sample_queries.jsonl
│   ├── raw/
│   │   ├── documents.jsonl     # Current crawl output: 3,086 documents
│   │   └── chunks.jsonl        # Current chunk output: 21,907 chunks
│   ├── finetune/
│   │   └── llm_data.jsonl      # Current Alpaca-style dataset: 2,574 samples
│   ├── chroma_db/              # Full: 21,907 embeddings
│   ├── bm25_index.pkl          # ~50 MB, 21,907 chunks indexed
│   ├── approved_eval_queries.{jsonl,md}
│   ├── suggested_eval_queries.{jsonl,md}
│   ├── 20260423_*/             # Eval run reports
│   └── logs/
├── frontend/                   # Next.js 15 React TypeScript chat UI
│   ├── src/app/                # layout.tsx, page.tsx, globals.css
│   ├── src/components/chat/    # ChatWindow, MessageBubble, MessageInput, CitationCard
│   ├── src/hooks/useSSE.ts
│   ├── src/lib/api.ts, types.ts
│   ├── src/stores/chatStore.ts
│   ├── package.json
│   └── next.config.ts
├── src/acne_llm/
│   ├── _archive/               # Old pipeline/rag implementations (11 files)
│   ├── api/                    # FastAPI app, routes
│   │   ├── app.py
│   │   ├── deps.py
│   │   ├── routes/
│   │   │   ├── chat.py         # POST /chat, GET /chat/stream (SSE)
│   │   │   ├── health.py
│   │   │   └── kb.py
│   │   └── templates/partials/ # Legacy Jinja2 partial templates
│   ├── chat/                   # NEW: streaming chat engine
│   │   ├── runtime.py          # SSE streaming, safety filters, chat decisions
│   │   └── normalizer.py       # Free-form msg -> structured UserInput
│   ├── crawler/                # Discovery, fetch, extract, normalize, dedup
│   ├── eval/                   # Retrieval metrics
│   ├── guardrails/             # Safety pre/post checks (7 rules now)
│   ├── llm/                    # Ollama client, prompt builder, QA generator, query expander
│   ├── pipeline/               # llm_only, hybrid, rag_only
│   ├── rag/                    # chunker, embedder, Chroma, BM25, retriever, reranker
│   ├── schemas/                # core.py (UserInput, AdviseOutput, etc.), kb.py (KBChunk, EntityRecord, LLMData, QASample, ChatMessage, Intent)
│   ├── utils/
│   ├── vision/                 # VisionProtocol + MockVision
│   ├── cli.py
│   └── di.py                   # Runtime dependency container
├── scripts/
│   ├── crawl_all.py
│   ├── build_kb.py
│   ├── build_qa_dataset.py
│   ├── run_eval.py
│   ├── RUN.ps1                 # Launches all 3 services (Ollama, Backend, Frontend)
│   ├── run_all.sh              # Linux equivalent of RUN.ps1
│   ├── propose_eval_labels.py
│   └── approve_eval_labels.py
├── tests/                      # 17 pytest files
├── LLMData/
│   ├── acne_dataset.jsonl      # Separate prebuilt dataset
│   └── script.py
├── visualize/                  # Dataset charts and report.html
├── linux/                      # Linux venv (separate from .venv)
├── README.md
├── BLUEPRINT_AcneLLM.md
├── tasks.ps1
├── tasks.sh
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env                        # Runtime environment (DEVICE=cpu)
├── .env.example                # Template environment
├── fix.md
├── linux.md
├── prompt.md
└── todo.md
```

## KB/RAG Status

**RAG is fully ready.** Both ChromaDB and BM25 index are complete:

| Artifact | Status |
|---|---|
| `data/raw/documents.jsonl` | `3,086` documents |
| `data/raw/chunks.jsonl` | `21,907` chunks |
| `data/chroma_db/` | `21,907` embeddings (chroma.sqlite3 ~232 MB) |
| `data/bm25_index.pkl` | Present (~50 MB, 21,907 chunks indexed) |
| DI `rag_ready` | True — all 3 pipeline modes available |
| `data/finetune/qa_finetuning.jsonl` | Not present (generated by `scripts/build_qa_dataset.py`) |

## Schemas And Public Contract

Main request schema: `UserInput`

- `description: str`
- `context: UserContext`
- `clinical: AcneClinicalInput | None`
- `vision: VisionOutput | None`
- `mode: "llm_only" | "rag_only" | "hybrid"` with schema default `hybrid`

`clinical` is optional and additive. It can carry structured acne intake fields:
`lesion_types`, `lesion_distribution`, `inflammation_level`, `scarring_signs`,
`medication_history`, `hormonal_factors`, `skincare_products`, `treatment_goals`,
and `red_flags_input`.

Main response schema: `AdviseOutput`

- `severity`
- `acne_type_primary`
- `causes`
- `recommendations`
- `red_flags`
- `used_chunks`
- `confidence`
- `disclaimer`
- `mode`
- `model_name`
- `latency_ms`

Additional schemas in `kb.py`:

- `LLMData` — Alpaca-style fine-tuning record
- `Intent` — Literal type with 9 intent categories (`ask_cause`, `ask_symptoms`, `ask_treatment`, `ask_medication`, `ask_routine`, `ask_safety`, `ask_comparison`, `ask_when_doctor`, `ask_general`)
- `ChatMessage` — role/content for chat
- `QASample` — ChatML format for Axolotl/Unsloth fine-tuning
- `EntityRecord` — active ingredient, medication, condition, procedure, product class, anatomy entities

Vision integration exists as an optional field on `UserInput`. `MockVision` is currently wired in DI; a real Đề tài 27 component should implement the same `VisionProtocol`.

## Runtime Pipeline Behavior

### `llm_only`

Always available when Ollama is reachable.

```text
UserInput
  -> GuardrailRunner.pre_check()
  -> PromptBuilder using llm_only_user.j2
  -> OllamaBackend.generate_json()
  -> Pydantic parse into AdviseOutput
  -> GuardrailRunner.post_check()
  -> AdviseOutput
```

### `hybrid`

Requires RAG ready: ChromaDB index + BM25 index must both load successfully.

```text
UserInput
  -> GuardrailRunner.pre_check()
  -> build canonical clinical query from description/context/clinical/vision
  -> QueryExpander creates query_vi + query_en (if ENABLE_BILINGUAL_QUERY)
  -> HybridRetriever.retrieve(query_vi, mode="hybrid")
  -> HybridRetriever.retrieve(query_en, mode="hybrid")
  -> merge/dedup bilingual candidates by chunk_id
     -> dense: Embedder -> ChromaDB cosine query
     -> sparse: BM25 query
     -> RRF fusion + trust boost
  -> Reranker.rerank(query_vi + query_en)
  -> HybridRetriever.expand_context() for prev/next chunks
  -> PromptBuilder using hybrid_user.j2
  -> OllamaBackend.generate_json()
  -> Pydantic parse into AdviseOutput
  -> inject Vietnamese-only notice if detected input language is English
  -> GuardrailRunner.post_check()
  -> AdviseOutput
```

### `rag_only`

Requires RAG ready. It retrieves and reranks chunks, then returns them as `Recommendation` items in an `AdviseOutput`; it does not synthesize with the LLM.

### Chat Streaming Pipeline (new)

The chat UI uses SSE streaming via `GET /api/v1/chat/stream` with a lightweight runtime in `src/acne_llm/chat/`:

```text
Free-form message
  -> Normalizer (chat/normalizer.py) -> structured UserInput
  -> Safety/scope filters (self-harm, chemical harm, injection, non-acne, low-signal, greeting)
  -> Mode resolution (auto: hybrid if RAG ready, else llm_only)
  -> GuardrailRunner.pre_check()
  -> Chat retriever (_retrieve_for_chat): uses chat_retrieve_top_k / chat_rerank_top_k
  -> _build_prompt (simplified inline prompt, no Jinja2)
  -> OllamaBackend.stream_text() -> SSE token events
  -> Citation events per used chunk
  -> Done event with mode, latency, used_chunks, session_id
```

### Important Default/Fallback Detail

- `UserInput.mode` schema default is `hybrid`.
- JSON API `/api/v1/chat` does **not** silently fallback when the client requests `hybrid` or omits `mode`. If RAG is not ready, it returns `503`.
- Streaming API `/api/v1/chat/stream` auto-falls back to `llm_only` if RAG is not ready.
- Bilingual retrieval is hybrid-only; `llm_only` only receives the richer clinical summary in its prompt.

## API Endpoints

### JSON API (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/chat` | Main endpoint: `UserInput` -> `AdviseOutput` |
| `GET` | `/api/v1/chat/stream` | SSE streaming chat for Next.js UI. Query params: `message`, `session_id?`, `mode?` (default `auto`) |
| `GET` | `/api/v1/health` | Ollama/model/KB health summary |
| `GET` | `/api/v1/models` | Ollama model list |
| `POST` | `/api/v1/retrieve` | Direct retrieval + rerank; requires RAG ready |
| `GET` | `/api/v1/kb/stats` | RAG readiness, chunk count, model names |
| `GET` | `/api/v1/kb/chunk/{chunk_id}` | Fetch one chunk from Chroma; requires RAG ready |
| `POST` | `/api/v1/kb/search` | Hybrid search endpoint; requires RAG ready |

### Root

| Method | Path | Notes |
|---|---|---|
| `GET` | `/` | Redirects to `frontend_url` (default `http://localhost:3000`) |

## Data Pipeline

### Crawl

Command:

```powershell
python -m scripts.crawl_all
```

Behavior:

- Reads `data/seed_sources.yaml`.
- Runs enabled PubMed/API and generic HTML sources.
- Uses async HTTP fetcher, optional Playwright fallback, extraction, quality filtering, and MinHash dedup.
- Writes `data/raw/documents.jsonl`.

Current output: `3,086` documents.

### Build KB

Command:

```powershell
python -m scripts.build_kb
```

Steps:

- `--step chunk`: `data/raw/documents.jsonl` -> `data/raw/chunks.jsonl`
- `--step embed`: `data/raw/chunks.jsonl` -> `data/chroma_db/`
- `--step bm25`: `data/raw/chunks.jsonl` -> `data/bm25_index.pkl`

Current output:

- Chunking: `21,907` chunks (done)
- Embedding: `21,907 / 21,907` vectors in ChromaDB (done)
- BM25: built, `21,907` chunks indexed (done)

### Fine-Tuning Data

Configured generator:

```powershell
python -m scripts.build_qa_dataset
```

Configured output path: `data/finetune/qa_finetuning.jsonl`  
Current status: file not present.

Current actual fine-tune files:

- `data/finetune/llm_data.jsonl`: `2,574` Alpaca-style samples with keys `id`, `instruction`, `input`, `output`, `metadata`.
- `LLMData/acne_dataset.jsonl`: separate prebuilt dataset retained in the repo.

### Visualization

Command:

```powershell
.\tasks.ps1 visualize
```

Outputs:

- `visualize/*.png`
- `visualize/report.html`

### Evaluation

Commands:

```powershell
python -m scripts.propose_eval_labels   # Generate suggested labels for eval queries
python -m scripts.approve_eval_labels   # Promote suggested labels to approved
python -m scripts.run_eval <n>          # Run retrieval evaluation
```

Eval data stored in `data/approved_eval_queries.jsonl` and `data/20260423_*/`.

## Dataset Statistics

### Documents (`data/raw/documents.jsonl`)

- Total: **3,086**
- Language: `1,332 vi`, `1,754 en`
- Trust: `1,311 high`, `1,775 medium`
- Average text length: about `5,949.8` characters per document
- Average quality score: `0.703`

Top document sources:

| Source | Documents |
|---|---:|
| PubMed | 991 |
| HelloBacsi | 620 |
| Healthline-Acne | 283 |
| VnExpress-SucKhoe | 198 |
| Wikipedia-Acne-EN | 171 |
| TuoiTre-SucKhoe | 149 |
| Youmed | 128 |
| INCIDecoder-AcneIngredients | 120 |
| WebMD-Acne | 99 |
| Medlatec | 78 |

### Chunks (`data/raw/chunks.jsonl`)

- Total: **21,907**
- Language: `15,166 vi`, `6,741 en`
- Trust: `3,251 high`, `18,656 medium`
- Average chunk length: about `907.2` characters

Top chunk sources:

| Source | Chunks |
|---|---:|
| HelloBacsi | 10,312 |
| Healthline-Acne | 1,967 |
| PubMed | 1,693 |
| Youmed | 1,354 |
| SheIs-VN | 1,120 |
| INCIDecoder-AcneIngredients | 1,088 |
| Wikipedia-Acne-EN | 1,045 |
| Medlatec | 675 |
| WebMD-Acne | 622 |
| VnExpress-SucKhoe | 621 |

## Guardrails

Configured safety behavior in `guardrails/runner.py` and `config/guardrails.yaml` (7 rules):

1. Pregnancy + retinoid block/rewrite.
2. Breastfeeding + retinoid block/rewrite.
3. Severe acne must recommend seeing a dermatologist.
4. Children under 12 must see a pediatric dermatologist.
5. Remove advice encouraging popping/picking acne.
6. Warn about drug interactions/allergies when output recommends medications.
7. Ensure a minimum medical disclaimer.

The chat runtime (`chat/runtime.py`) additionally implements:
- Self-harm detection (redirects to emergency resources)
- Chemical harm detection (blocks H2SO4/acid discussion)
- Context contradiction detection (e.g. "male" + "pregnant")
- Prompt injection rejection
- Non-acne scope soft redirect
- Low-signal message redirect
- Greeting/identity/thanks canned responses

## Dependency Injection

`src/acne_llm/di.py` builds a `Container` at FastAPI startup:

- Always built: `OllamaBackend`, `PromptBuilder`, `GuardrailRunner`, `LLMOnlyPipeline`, `MockVision`.
- Built only when KB artifacts are ready: `Embedder`, `ChromaStore`, `BM25Index`, `HybridRetriever`, `Reranker`, `QueryExpander`, `HybridPipeline`, `RAGOnlyPipeline`.

RAG readiness checks:

- `data/chroma_db/` exists and is non-empty.
- `data/bm25_index.pkl` exists.
- Components load without exception.
- `Container.rag_ready` property returns `self.retriever is not None`.

FastAPI routes access the container through `request.app.state.container`.

## Commands

### Windows PowerShell

```powershell
.\tasks.ps1 install
.\tasks.ps1 pull-models
.\tasks.ps1 crawl
.\tasks.ps1 crawl-pubmed
.\tasks.ps1 build-dataset
.\tasks.ps1 build-dataset-resume
.\tasks.ps1 build-kb
.\tasks.ps1 visualize
.\tasks.ps1 serve
.\tasks.ps1 serve-lan
.\tasks.ps1 test
.\tasks.ps1 eval 50
.\tasks.ps1 stats
.\tasks.ps1 chat
```

### Linux/macOS

```bash
make install
make pull-models
make crawl
make build-dataset
make serve
make eval N=50
make test
# or via tasks.sh:
bash tasks.sh install
bash tasks.sh serve
bash tasks.sh run-all       # Starts Ollama + Backend + Frontend
bash tasks.sh frontend-install
```

### Multi-service launcher (all platforms)

```powershell
# Windows
.\scripts\RUN.ps1           # Starts Ollama, Backend, Frontend concurrently

# Linux/macOS
bash scripts/run_all.sh
```

### Docker

```powershell
docker-compose up -d
```

Note: Docker Compose uses different model names (`qwen3:4b` / `qwen3:1.7b`) than the main configuration (`qwen2.5:7b` / `qwen2.5:3b`).

## Main Environment Settings

```env
# LLM
OLLAMA_URL=http://localhost:11434
LLM_MODEL=qwen2.5:7b
LLM_FALLBACK_MODEL=qwen2.5:3b
LLM_NUM_CTX=8192
LLM_TEMPERATURE=0.3

# Embedding / Reranker
EMBEDDING_MODEL=AITeamVN/Vietnamese_Embedding
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
DEVICE=gpu

# Storage
CHROMA_DIR=./data/chroma_db
BM25_PATH=./data/bm25_index.pkl
DOCS_JSONL=./data/raw/documents.jsonl
CHUNKS_JSONL=./data/raw/chunks.jsonl

# Paths
PROMPTS_DIR=./config/prompts
GUARDRAILS_YAML=./config/guardrails.yaml
SEED_SOURCES=./data/seed_sources.yaml

# Retrieval (structured API)
RETRIEVE_TOP_K=20
RERANK_TOP_K=5

# Retrieval (chat streaming)
CHAT_RETRIEVE_TOP_K=8
CHAT_RERANK_TOP_K=3
CHAT_MAX_CONTEXT_CHARS=4500
CHAT_MIN_CITATION_SCORE=0.12

# Query expansion
ENABLE_BILINGUAL_QUERY=true
ENGLISH_INPUT_NOTICE=true
QUERY_EXPANSION_TEMPERATURE=0.1

# API
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=["*"]

# Crawler
USER_AGENT=AcneLLM-Bot/1.0 (student research)
CRAWL_CONCURRENCY=8
CRAWL_RATE_PER_SEC=1.0
```

## Testing

```powershell
python -m pytest -q
```

Current: **64 passed** (17 test files, up from 11 files / 42 passed previously).

## Known Current Issues

- Git repo initialized but has **zero commits** — all files are untracked.
- `data/finetune/qa_finetuning.jsonl` not yet generated.
- Docker Compose uses different Ollama models (`qwen3:4b` / `qwen3:1.7b`) vs the main config (`qwen2.5:7b` / `qwen2.5:3b`).
- Legacy Jinja2 SSR partial templates in `api/templates/partials/` still present but the old Web UI routes (`/ui/chat`, `/ui/search`, `/explorer`, `/about`) have been removed in favor of the Next.js frontend.
