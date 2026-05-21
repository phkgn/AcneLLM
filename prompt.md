# 🧠 PROMPT — REBUILD **AcneLLM** THEO HƯỚNG **FINE-TUNE LLM + SYNTHETIC DATASET** (BỎ RAG Ở PHA NÀY)

> **Vai trò của bạn (LLM thực thi prompt này):**
> Bạn là một kỹ sư ML/LLM cấp cao. Nhiệm vụ: **tái thiết kế và triển khai lại project `AcneLLM` (đề tài 29 — tư vấn da mụn tiếng Việt, local-first)** theo hướng MỚI dưới đây, **giữ nguyên triết lý "LEGO modular", schema contract, kiến trúc phân tầng, workflow 7 bước, và toàn bộ ý tưởng/pipeline gốc** nhưng **loại bỏ nhánh RAG (crawl → chunk → embed → vectorstore → retriever → reranker) khỏi runtime chính**. Thay vào đó, **xây dựng pipeline DATASET → FINE-TUNE LLM**, trong đó dataset được tạo bằng **LLM-generated synthetic data (LLMData)** kết hợp với dữ liệu có cấu trúc tự tổng hợp, rồi fine-tune một LLM base tiếng Việt.
>
> ⚠️ **RAG là OPTIONAL — giữ interface `RAGProtocol`, giữ stub module, nhưng KHÔNG chạy trong pipeline default, KHÔNG cần crawl, KHÔNG cần ChromaDB ở pha này.** Sau này có thể bật lại bằng cách cắm implementation vào interface đã có — không sửa API, không sửa schema.

---

## 0. BỐI CẢNH & NGUYÊN TẮC BẤT BIẾN (KHÔNG ĐƯỢC THAY ĐỔI)

### 0.1 Context nguồn (project gốc `AcneLLM` — blueprint v1.0)

Project gốc là hệ thống tư vấn da mụn tiếng Việt chạy 100% local, lõi là **LLM + RAG pipeline 7 bước** (Clean → Chunk → Embed → Store → Retrieve hybrid RRF → Rerank → Compose context → LLM JSON). Knowledge base ≥ 20.000 entities crawl từ ~15 domains EN/VN (PubMed, AAD, NICE, DermNet, Vinmec, BVDL, HelloBacsi…). Expose qua **FastAPI** làm backend dùng chung cho web UI (Jinja2 + HTMX + Tailwind CDN) lẫn mobile app.

**Tech stack gốc:** Python 3.11, Ollama (Qwen2.5-7B-Instruct primary), BGE-M3-VI embedding, bge-reranker-v2-m3, ChromaDB, rank_bm25, underthesea, httpx + trafilatura + playwright (crawler), FastAPI 0.115+, Pydantic v2, Jinja2 + HTMX + Tailwind, Typer CLI, loguru, pytest.

**3 pipeline modes gốc:** `llm_only`, `rag_only`, `hybrid` (default).

**Schema contract bất biến** (copy nguyên từ `src/acne_llm/schemas/core.py`):
`VisionLesion`, `VisionOutput`, `UserContext`, `UserInput`, `RetrievedChunk`, `RetrievalOutput`, `Recommendation`, `RedFlag`, `AdviseOutput`.

**Workflow cũ (request `/api/v1/chat` hybrid mode):**
```
UserInput → Pydantic validate → Guardrails pre-check → Build retrieval query
        → Hybrid RAG (dense+sparse→RRF, top-20) → Reranker (top-5)
        → PromptBuilder (system + user + ctx) → Ollama JSON-grammar generate
        → Parse AdviseOutput → Guardrails post-check → Response
```

### 0.2 Ràng buộc BẤT BIẾN (phải giữ)

1. ✅ **Chạy 100% local khi inference** (Ollama hoặc llama.cpp trên cùng máy/LAN).
2. ✅ Phục vụ cả **web client (HTMX)** và **mobile client** qua HTTP JSON.
3. ✅ **Triết lý LEGO modular:** mọi thành phần expose qua `Protocol`, swap được bằng đổi `.env`, không sửa code downstream.
4. ✅ **Contract schema `core.py` TUYỆT ĐỐI KHÔNG ĐỔI** — `UserInput`, `AdviseOutput`, `VisionOutput`, `RetrievedChunk`, `RetrievalOutput`, `Recommendation`, `RedFlag` giữ nguyên field, nguyên type, nguyên default.
5. ✅ **Giữ cấu trúc thư mục `src/acne_llm/`** giống blueprint gốc (crawler/, rag/, llm/, vision/, pipeline/, guardrails/, eval/, api/, schemas/, utils/) — chỉ đổi NỘI DUNG bên trong, không đổi TÊN và VỊ TRÍ module.
6. ✅ **Workflow 7 bước vẫn còn** nhưng được "re-map" sang pipeline fine-tune dataset (xem §3).
7. ✅ **Guardrails y khoa:** không gợi ý retinoid/isotretinoin cho phụ nữ mang thai/cho con bú; severe → bắt buộc recommend gặp bác sĩ; không khuyên tự nặn; không kê liều lượng cụ thể.
8. ✅ **Hỗ trợ 3 mode** trong `UserInput.mode`: `llm_only`, `rag_only`, `hybrid` — nhưng ở pha này **default = `llm_only` (với model đã fine-tune)**, `rag_only` và `hybrid` trả lỗi `501 Not Implemented` lịch sự kèm thông điệp "RAG là module optional, chưa kích hoạt ở phiên bản này" (vẫn giữ route).

### 0.3 Thay đổi CỐT LÕI so với blueprint gốc

| Aspect | Gốc (AcneLLM v1.0) | **Mới (AcneLLM-FT v2.0)** |
|---|---|---|
| Nguồn tri thức vào LLM | Inject ngữ cảnh qua RAG runtime | **Nhúng tri thức vào trọng số LLM bằng fine-tune** |
| Crawl 15 domains ≥ 20k chunks | Bắt buộc | **BỎ** — không crawl, không chunk, không embed |
| ChromaDB + BM25 + RRF + Reranker | Bắt buộc runtime | **Stub-out (interface giữ, impl để `NotImplementedError`)** |
| Dataset | Không có (raw chunks) | **Có — `LLMData` synthetic QA + structured mining** |
| Training | Không (prompting only) | **LoRA / QLoRA fine-tune trên base VN LLM** |
| Inference mặc định | `hybrid` (RAG + LLM) | **`llm_only` dùng model đã fine-tune** |
| FastAPI + Web UI + Mobile | Giữ nguyên | **Giữ nguyên 100%** |
| Schema contract | Giữ nguyên | **Giữ nguyên 100%** |
| Roadmap 6 tuần | Crawl → KB → RAG → API → Eval | **Data design → Synth gen → Curation → Fine-tune → API → Eval** |
| RAG | Runtime mặc định | **Optional, có thể cắm lại sau** — để interface chờ sẵn |

---

## 1. INSIGHT & IDEA CỐT LÕI

### 1.1 Tại sao chuyển từ RAG sang Fine-tune?

1. **Crawl + KB là bottleneck vận hành**: cần ~3-5GB HTML thô, robots.txt, rate-limit, dedup MinHash, xử lý JS-heavy bằng Playwright, quality filter VN diacritics. Mỗi lần update data = re-index toàn bộ ChromaDB + BM25 pickle. Không scale tốt cho sinh viên đơn lẻ.
2. **Latency**: hybrid pipeline mất p50 ~8s, p95 ~15s trên CPU do rerank cross-encoder `bge-reranker-v2-m3` (512 tokens x top-20 pairs).
3. **Domain-specific VN**: LLM base (Qwen2.5-7B) chưa được huấn luyện riêng cho **thuật ngữ da liễu tiếng Việt + khuyến nghị an toàn VN**. Fine-tune nhét được đúng persona + kiến thức cô đọng mà RAG phải lặp lại mỗi request qua context.
4. **Deliverable ấn tượng hơn cho khóa luận**: một model `acne-llm-vi:qwen2.5-7b-ft-v1` có thể pull qua Ollama Modelfile, so sánh A/B với base, có curve loss, có eval harness — phong phú hơn một KB tĩnh.
5. **Quyền kiểm soát tốt hơn**: dataset là tài sản của mình, không phụ thuộc robots.txt/Terms of Service của 15 trang; với LLMData (synthetic) thì license rõ ràng (được tạo bởi model offline có ghi log, chỉ dùng cho training academic).

### 1.2 Idea "LLMData": dataset sinh bằng LLM

**LLMData** = synthetic training corpus được sinh bởi một LLM "teacher" mạnh (Claude/GPT-4o/Qwen2.5-72B chạy offline 1 lần duy nhất, có audit log) dựa trên:

- **Seed ontology y khoa** (~500–1.000 entity cô đọng từ blueprint gốc: `active_ingredient`, `medication`, `condition`, `procedure`, `product_class`, `anatomy`) — **gõ tay hoặc tinh chế từ `EntityRecord` schema**, không crawl.
- **Guidelines VN/EN cô đọng thủ công** (AAD acne guideline, NICE NG198, khuyến nghị BVDL) — paraphrase từ memo ngắn, không lưu content gốc có bản quyền.
- **Persona library**: ~30 profile bệnh nhân giả định (tuổi, giới, skin_type, pregnancy, allergies, duration_weeks, acne_type chính).
- **Template QA**: diagnosis, causes, recommendations by severity, safety gating (pregnancy-retinoid), counseling tone VN.

**Output LLMData** = JSONL tuân thủ schema training:
```jsonc
{
  "instruction": "<system prompt cố định>",
  "input": "<UserInput JSON hợp lệ Pydantic>",
  "output": "<AdviseOutput JSON hợp lệ Pydantic>",
  "meta": {
    "teacher_model": "<tên model teacher>",
    "generation_seed": 42,
    "persona_id": "p017",
    "guardrail_flags": ["pregnancy_retinoid_safe"],
    "created_at": "ISO8601"
  }
}
```

Mỗi sample **phải parse được `AdviseOutput` schema** — nếu không, reject ngay khi curate.

### 1.3 Nguyên tắc quality cho LLMData

1. **Schema-strict**: validate bằng Pydantic v2 trước khi nhận.
2. **Guardrail-compliant**: mọi sample có `is_pregnant=True` + `severity ∈ {moderate, severe}` **phải không chứa** `retinoid|isotretinoin|tretinoin|adapalene` trong `recommendations[*].action`. Tự động filter.
3. **Diversity**: cover đủ 4 severity × 3 skin_type × {pregnant, non-pregnant} × {adolescent, adult, adult-over-35} — mỗi tổ hợp ≥ 30 samples.
4. **Citation-free** (do không còn RAG): `source_chunk_id = null` ở mọi recommendation; `used_chunks = []`.
5. **Tone VN tự nhiên**: không từ Hán Việt gượng, không dịch máy thô.
6. **No-hallucinated-drug**: chỉ dùng nhóm hoạt chất trong allowlist (`benzoyl_peroxide`, `azelaic_acid`, `niacinamide`, `salicylic_acid`, `adapalene` [non-pregnant], `clindamycin_topical`, `tretinoin` [non-pregnant], `isotretinoin` [severe + non-pregnant + có ghi chú gặp bác sĩ]).

### 1.4 Mục tiêu định lượng dataset

| Stage | Target |
|---|---|
| Seed entities (hand-curated) | 300–500 |
| Persona profiles | 30 |
| QA templates | 20 |
| Raw LLMData sinh ra | ~12.000 samples |
| Sau schema-validate + guardrail filter | ~8.000 samples |
| Sau dedup (MinHash trên `input.description`, threshold 0.85) | ~6.500 samples |
| Sau manual spot-check (1%) | ~6.500 samples |
| **Train/Val/Test split** | **80/10/10** → ~5.200 / 650 / 650 |

---

## 2. TECH STACK MỚI

Giữ stack gốc và **thêm** tầng training:

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Base LLM để fine-tune | **Qwen2.5-7B-Instruct** (HF format) | Cùng model với runtime gốc; sau fine-tune convert sang GGUF + Modelfile cho Ollama |
| Fine-tune framework | **Unsloth** (primary, nhanh, tiết kiệm VRAM) hoặc **HF PEFT + TRL (SFTTrainer)** (fallback) | LoRA rank 16, alpha 32, dropout 0.05, target_modules = all-linear |
| Quantization training | **QLoRA (4-bit NF4)** qua `bitsandbytes` | Chạy được trên GPU 16GB (Colab T4/A100, RTX 4060 Ti 16GB, RTX 3090) |
| Teacher model (sinh LLMData) | **Qwen2.5-72B-Instruct** (Ollama hoặc API offline 1 lần) — hoặc Claude/GPT-4o nếu có budget | Ghi audit log, không commit raw output có PII |
| Dataset format | **ChatML / ShareGPT JSONL** + `datasets` lib | Compatible với TRL SFTTrainer |
| Tokenizer | Cùng tokenizer của Qwen2.5 (BPE) | |
| Eval harness | `lm-eval-harness` style custom + **LLM-as-judge** (dùng chính Qwen2.5-72B) | |
| Convert ra GGUF | `llama.cpp/convert_hf_to_gguf.py` + `quantize` Q4_K_M | |
| Serve | **Ollama** (qua Modelfile import GGUF) | Giữ interface `OllamaBackend` nguyên vẹn |
| Tracking | **Weights & Biases** (optional) hoặc CSV + matplotlib | |

**Giữ nguyên toàn bộ stack cũ** (Python 3.11, FastAPI, Pydantic v2, Jinja2 + HTMX + Tailwind, Typer, loguru, pytest, docker-compose).
**Loại bỏ khỏi runtime** (nhưng import-path vẫn tồn tại dưới dạng stub): ChromaDB client, rank_bm25, sentence-transformers reranker, trafilatura, playwright, httpx async fetcher, datasketch (MinHash), underthesea chunker.

---

## 3. RE-MAP WORKFLOW 7 BƯỚC: TỪ RAG SANG DATASET+FINE-TUNE

Workflow cũ có 7 bước: Clean → Chunk → Embed → Store → Retrieve → Rerank → Compose. Ta **giữ nguyên số bước, giữ nguyên ý tưởng "pipeline modular 7 node"**, nhưng re-assign mỗi bước cho giai đoạn dataset/training:

| # | Bước cũ (RAG) | **Bước mới (Dataset + FT)** | Module (đặt vào đúng folder gốc) |
|---|---|---|---|
| 1 | Clean (boilerplate, NFC, whitespace) | **Seed Curation** — curate 300–500 entities + 30 personas + 20 templates thành YAML/JSONL | `src/acne_llm/dataset/seed_curator.py` (folder MỚI trong structure gốc) |
| 2 | Chunk (VI recursive) | **Prompt Templating** — build prompts cho teacher LLM từ (persona × template × entity) | `src/acne_llm/dataset/prompt_factory.py` |
| 3 | Embed (BGE-M3) | **Synthetic Generation** — gọi teacher LLM sinh `{instruction, input, output}` | `src/acne_llm/dataset/synth_generator.py` |
| 4 | Store (Chroma) | **Schema Validation & Storage** — parse Pydantic `UserInput`/`AdviseOutput`, lưu JSONL | `src/acne_llm/dataset/validator.py` + `data/datasets/*.jsonl` |
| 5 | Retrieve (hybrid RRF) | **Curation & Dedup** — MinHash dedup + guardrail filter + diversity balance | `src/acne_llm/dataset/curator.py` |
| 6 | Rerank (cross-encoder) | **Quality Scoring** — LLM-as-judge chấm điểm 1–5 cho từng sample, giữ ≥ 4 | `src/acne_llm/dataset/scorer.py` |
| 7 | Compose context + LLM | **Fine-tune + Merge + GGUF + Modelfile** — SFT LoRA, merge adapter, quantize, import Ollama | `src/acne_llm/training/trainer.py` + `scripts/train_sft.py` + `scripts/export_gguf.py` |

→ **Triết lý LEGO modular giữ nguyên**: mỗi bước là 1 class implement 1 protocol, đổi implementation bằng đổi `.env`, không sửa code downstream. Ví dụ có thể swap `synth_generator.py` từ Qwen-72B sang Claude API bằng 1 biến env `TEACHER_PROVIDER`.

**Runtime pipeline mới** (thay cho HybridPipeline cũ — vẫn nằm ở `src/acne_llm/pipeline/`):
```
UserInput → Pydantic validate → Guardrails pre-check
        → PromptBuilder (system + user, KHÔNG CÓ CONTEXT RAG)
        → Ollama generate JSON (model fine-tuned: acne-llm-vi)
        → _safe_parse → AdviseOutput
        → Guardrails post-check → Response
```
Chính là `LLMOnlyPipeline` đã có sẵn trong code gốc — **chỉ đổi model Ollama sang bản fine-tune**. Không code mới ở tầng pipeline runtime.

---

## 4. CẤU TRÚC THƯ MỤC (GIỮ NGUYÊN GỐC + THÊM 2 FOLDER)

Giữ **100%** cấu trúc gốc trong `src/acne_llm/`. Chỉ **thêm** 2 folder mới và **stub** các module RAG/crawler thay vì xóa.

```
acne_llm/
├── README.md
├── requirements.txt              # bỏ chromadb/rank_bm25/trafilatura/playwright, THÊM unsloth/trl/peft/bitsandbytes/datasets
├── pyproject.toml
├── .env.example                  # thêm biến TEACHER_MODEL, TRAIN_*, DATASET_*
├── Makefile                      # thêm target: gen-data, curate, train, export-gguf, pull-ft-model
├── docker-compose.yml
│
├── config/
│   ├── settings.py
│   ├── prompts/
│   │   ├── system.j2             # GIỮ NGUYÊN
│   │   ├── hybrid_user.j2        # GIỮ — nhưng không dùng ở runtime default
│   │   ├── llm_only_user.j2      # GIỮ — default runtime
│   │   └── teacher_synth.j2      # MỚI — prompt gửi teacher LLM để sinh QA
│   ├── guardrails.yaml           # GIỮ NGUYÊN
│   ├── ontology/                 # MỚI
│   │   ├── entities.yaml         # 300–500 entity y khoa curated
│   │   ├── personas.yaml         # 30 persona
│   │   └── templates.yaml        # 20 QA template
│   └── training/
│       ├── lora.yaml             # rank, alpha, target_modules, learning_rate, epochs
│       └── sft.yaml              # batch_size, grad_accum, max_seq_len, warmup
│
├── data/
│   ├── seed_sources.yaml         # GIỮ nhưng KHÔNG DÙNG (để chờ RAG optional sau)
│   ├── raw/                      # RỖNG — gitignore
│   ├── processed/                # RỖNG — gitignore
│   ├── chroma_db/                # RỖNG — gitignore
│   ├── bm25_index.pkl            # KHÔNG build
│   ├── datasets/                 # MỚI
│   │   ├── raw_synth.jsonl       # output bước 3
│   │   ├── validated.jsonl       # sau bước 4
│   │   ├── curated.jsonl         # sau bước 5
│   │   ├── scored.jsonl          # sau bước 6
│   │   ├── train.jsonl           # bước 7 input
│   │   ├── val.jsonl
│   │   └── test.jsonl
│   ├── checkpoints/              # MỚI — LoRA adapter + merged model
│   │   └── acne-llm-vi-v1/
│   ├── gguf/                     # MỚI — model đã quantize
│   │   └── acne-llm-vi-v1-Q4_K_M.gguf
│   ├── Modelfile                 # MỚI — cho ollama create
│   ├── sample_queries.jsonl      # GIỮ — 50 query ground-truth cho eval
│   └── eval_reports/             # GIỮ
│
├── src/acne_llm/
│   ├── __init__.py
│   │
│   ├── schemas/                  # GIỮ NGUYÊN 100%
│   │   ├── core.py               # KHÔNG ĐƯỢC SỬA 1 field
│   │   └── kb.py                 # GIỮ — dù KB không build, schema vẫn compile
│   │
│   ├── crawler/                  # STUB — tất cả raise NotImplementedError("Disabled in FT-mode, enable RAG optional")
│   │   ├── base.py               # Protocol GIỮ
│   │   ├── fetcher.py            # stub
│   │   ├── normalizer.py         # stub
│   │   ├── dedup.py              # stub
│   │   └── sources/pubmed.py     # stub
│   │
│   ├── rag/                      # STUB — interface GIỮ, impl raise NotImplementedError
│   │   ├── base.py               # RAGProtocol GIỮ (quan trọng — contract cho đề tài 28)
│   │   ├── embedder.py           # stub
│   │   ├── vectorstore.py        # stub
│   │   ├── sparse.py             # stub
│   │   ├── retriever.py          # stub — trả RetrievalOutput(chunks=[])
│   │   ├── reranker.py           # stub
│   │   └── cleaning.py           # stub
│   │
│   ├── dataset/                  # MỚI — thay thế vai trò crawler/rag về mặt data
│   │   ├── __init__.py
│   │   ├── base.py               # DatasetBuilderProtocol
│   │   ├── seed_curator.py       # Bước 1 mới
│   │   ├── prompt_factory.py     # Bước 2 mới
│   │   ├── synth_generator.py    # Bước 3 mới — gọi teacher LLM qua Ollama/HTTP
│   │   ├── validator.py          # Bước 4 mới — Pydantic strict
│   │   ├── curator.py            # Bước 5 mới — MinHash + guardrail + diversity
│   │   ├── scorer.py             # Bước 6 mới — LLM-as-judge 1–5
│   │   └── splitter.py           # Bước 7a — train/val/test split stratified
│   │
│   ├── training/                 # MỚI
│   │   ├── __init__.py
│   │   ├── base.py               # TrainerProtocol
│   │   ├── sft_trainer.py        # SFTTrainer wrapper (unsloth/trl)
│   │   ├── lora_config.py
│   │   ├── data_collator.py      # ChatML template cho Qwen2.5
│   │   ├── callbacks.py          # EvalCallback, SaveBestCallback
│   │   └── export_gguf.py        # merge adapter → HF → llama.cpp → GGUF → Modelfile
│   │
│   ├── llm/                      # GIỮ NGUYÊN
│   │   ├── base.py
│   │   ├── ollama_backend.py     # Không đổi — chỉ đổi LLM_MODEL trong .env
│   │   └── prompt_builder.py
│   │
│   ├── vision/                   # GIỮ NGUYÊN
│   ├── guardrails/               # GIỮ NGUYÊN — y chang runner.py và rules
│   │
│   ├── pipeline/                 # GIỮ — default dùng llm_only
│   │   ├── base.py
│   │   ├── llm_only.py           # DEFAULT RUNTIME
│   │   ├── rag_only.py           # stub: raise 501
│   │   └── hybrid.py             # stub: raise 501
│   │
│   ├── eval/                     # MỞ RỘNG
│   │   ├── metrics.py            # THÊM: loss curve parse, perplexity, format compliance, safety, severity acc, BLEU/ROUGE
│   │   ├── judge.py              # GIỮ, extend
│   │   ├── ab_compare.py         # MỚI — so sánh base vs fine-tuned
│   │   └── runner.py
│   │
│   ├── api/                      # GIỮ NGUYÊN app.py / routes / templates
│   │   ├── app.py                # không đổi
│   │   ├── deps.py               # không đổi
│   │   └── routes/
│   │       ├── chat.py           # không đổi — tự chọn pipeline theo user.mode
│   │       ├── kb.py             # trả 501 hoặc trả stats rỗng có flag "rag_disabled=true"
│   │       ├── health.py         # thêm check: model fine-tuned có tồn tại trong Ollama
│   │       └── ui.py
│   │
│   ├── di.py                     # sửa: nếu rag_disabled=true thì không init Chroma/BM25/Reranker
│   ├── cli.py                    # thêm lệnh: gen-data, curate, train, export-gguf, pull-ft
│   └── utils/                    # GIỮ
│
├── scripts/
│   ├── crawl_all.py              # giữ file nhưng chứa `print("RAG disabled"); sys.exit(0)`
│   ├── build_kb.py               # tương tự — dummy exit
│   ├── gen_llmdata.py            # MỚI — orchestrate bước 1→6 của dataset pipeline
│   ├── curate_dataset.py         # MỚI — bước 5–6 tách riêng để re-run
│   ├── train_sft.py              # MỚI — bước 7 training
│   ├── export_gguf.py            # MỚI — merge + quantize + ollama create
│   ├── run_eval.py               # GIỮ, extend
│   └── pull_models.sh            # thêm `ollama pull` teacher model nếu chạy local
│
└── tests/
    ├── conftest.py
    ├── test_schemas.py           # GIỮ — quan trọng, đảm bảo schema không đổi
    ├── test_dataset_validator.py # MỚI
    ├── test_curator.py           # MỚI
    ├── test_prompt_factory.py    # MỚI
    ├── test_training_smoke.py    # MỚI — 1 epoch trên 10 samples
    ├── test_guardrails.py        # GIỮ
    ├── test_pipeline_integration.py  # đổi: chỉ test llm_only; rag_only và hybrid phải raise HTTP 501
    └── test_api.py               # GIỮ nhưng case RAG chuyển thành expect 501
```

---

## 5. PIPELINE DATASET CHI TIẾT (7 BƯỚC MỚI)

### Bước 1 — Seed Curation (`dataset/seed_curator.py`)

Đọc 3 file YAML curated:
- `config/ontology/entities.yaml`: 300–500 entity, mỗi entity có `entity_id`, `entity_type`, `name_vi`, `name_en`, `aliases`, `description`, `contraindications` (không cần `related_chunk_ids` nữa). Tuân thủ schema `EntityRecord` đã có (`src/acne_llm/schemas/kb.py`).
- `config/ontology/personas.yaml`: 30 persona với các tổ hợp (age, sex, skin_type, is_pregnant, is_breastfeeding, allergies, duration_weeks).
- `config/ontology/templates.yaml`: 20 template QA (diagnosis, cause-analysis, recommendation-by-severity, safety-advice, lifestyle, when-to-see-doctor, product-comparison…).

Output: trả `list[SeedRecord]` — không ghi file mới, chỉ feed bước 2.

### Bước 2 — Prompt Templating (`dataset/prompt_factory.py`)

Build combinatorial prompts = `persona × template × entity_set`. Có sampling strategy để giữ diversity (không để 1 template × 1 persona lặp quá 3 lần).

Với mỗi combination, render 1 prompt gửi teacher LLM, gồm:
- System: `config/prompts/teacher_synth.j2` (yêu cầu teacher trả DUY NHẤT 1 JSON `{input: UserInput, output: AdviseOutput}` hợp lệ schema, tuân thủ guardrails).
- User: template câu hỏi kèm persona + optional danh sách entity bắt buộc xuất hiện.

Output: `list[TeacherPrompt]` — mỗi prompt có `prompt_id`, `persona_id`, `template_id`, `entities`, `expected_severity_hint`.

### Bước 3 — Synthetic Generation (`dataset/synth_generator.py`)

Gọi teacher LLM qua Ollama `/api/chat` (hoặc Anthropic/OpenAI API nếu config). Batch size có rate limit. Retry với exponential backoff. Log mọi call vào `data/datasets/generation_audit.jsonl` (prompt_id, teacher_model, tokens_in, tokens_out, cost_usd nếu API, timestamp).

Output: `data/datasets/raw_synth.jsonl` (~12.000 rows).

### Bước 4 — Schema Validation (`dataset/validator.py`)

Với mỗi row:
```python
try:
    inp = UserInput.model_validate(row["input"])
    out = AdviseOutput.model_validate(row["output"])
    row["__valid"] = True
except ValidationError as e:
    row["__valid"] = False
    row["__error"] = str(e)
```
Giữ `__valid=True`, ghi reject vào `data/datasets/rejected_schema.jsonl` kèm lý do. Target pass rate ≥ 70% → nếu < 50% phải sửa `teacher_synth.j2`.

Output: `data/datasets/validated.jsonl` (~8.000 rows).

### Bước 5 — Curation (`dataset/curator.py`)

Ba lớp lọc:
1. **Guardrail hard-filter** — chạy `GuardrailRunner.post_check(output, input)` cho mọi sample; nếu bị flag thì reject (reuse module gốc `guardrails/runner.py`).
2. **MinHash dedup** trên `input.description` + `input.context` tuple, threshold Jaccard 0.85.
3. **Diversity balance** — đảm bảo mỗi tổ hợp (severity × pregnancy × skin_type) có count ≥ 30; oversample thiếu, downsample thừa (cap 500 per cell).

Output: `data/datasets/curated.jsonl` (~6.500 rows).

### Bước 6 — Quality Scoring (`dataset/scorer.py`)

LLM-as-judge (teacher model) chấm điểm 1–5 mỗi sample theo rubric:
- Tính chính xác y khoa (5 đ): có đúng với guideline cô đọng không?
- Tuân thủ schema + guardrails (5 đ).
- Tone tiếng Việt tự nhiên (5 đ).
- Có `recommendations` hợp lý, có `rationale`, có `red_flags` đúng ngữ cảnh (5 đ).

Tính mean 4 tiêu chí, giữ samples `score ≥ 4.0`. Output: `data/datasets/scored.jsonl` (~5.200–6.000 rows).

### Bước 7a — Split (`dataset/splitter.py`)

Stratified split theo `output.severity` → 80/10/10 → `train.jsonl`, `val.jsonl`, `test.jsonl`.

### Bước 7b — Fine-tune (`training/sft_trainer.py` + `scripts/train_sft.py`)

Config (`config/training/lora.yaml` + `sft.yaml`):
```yaml
base_model: Qwen/Qwen2.5-7B-Instruct
load_in_4bit: true
lora:
  r: 16
  alpha: 32
  dropout: 0.05
  target_modules: all-linear
sft:
  max_seq_len: 4096
  learning_rate: 2.0e-4
  num_train_epochs: 3
  per_device_train_batch_size: 2
  gradient_accumulation_steps: 8   # effective bs = 16
  warmup_ratio: 0.03
  lr_scheduler_type: cosine
  optim: paged_adamw_8bit
  eval_strategy: steps
  eval_steps: 100
  save_steps: 200
  logging_steps: 10
  bf16: true
  seed: 42
```
Input format (ChatML qua Qwen2.5 template):
```
<|im_start|>system
{instruction}<|im_end|>
<|im_start|>user
{input_as_json}<|im_end|>
<|im_start|>assistant
{output_as_json}<|im_end|>
```

Callback: eval loss, format compliance rate trên `val.jsonl`, save-best theo format compliance.

Output: `data/checkpoints/acne-llm-vi-v1/` (LoRA adapter).

### Bước 7c — Export (`training/export_gguf.py` + `scripts/export_gguf.py`)

```
1. Merge LoRA adapter vào base → HF format → data/checkpoints/acne-llm-vi-v1/merged/
2. python llama.cpp/convert_hf_to_gguf.py → data/gguf/acne-llm-vi-v1-F16.gguf
3. ./llama.cpp/quantize F16 → Q4_K_M → data/gguf/acne-llm-vi-v1-Q4_K_M.gguf
4. Render data/Modelfile:
     FROM ./data/gguf/acne-llm-vi-v1-Q4_K_M.gguf
     TEMPLATE "<ChatML template>"
     PARAMETER temperature 0.3
     PARAMETER num_ctx 8192
     PARAMETER stop "<|im_end|>"
     SYSTEM "Bạn là AcneLLM, trợ lý tư vấn da mụn bằng tiếng Việt..."
5. ollama create acne-llm-vi:v1 -f data/Modelfile
```

Sau bước này, chỉ cần đổi `.env`: `LLM_MODEL=acne-llm-vi:v1` — toàn bộ FastAPI + Web UI + Mobile hoạt động nguyên vẹn.

---

## 6. RUNTIME PIPELINE (ĐƠN GIẢN HÓA)

Ở `src/acne_llm/di.py`, thêm flag `rag_enabled` (default `False`, đọc từ `.env` `RAG_ENABLED=false`). Nếu false:
- Không khởi tạo `Embedder`, `ChromaStore`, `BM25Index`, `HybridRetriever`, `Reranker`.
- `Container.hybrid` = None, `Container.rag_only` = None.
- `routes/chat.py` dispatch theo `user.mode`:
  - `llm_only` → `container.llm_only.run(user)` — dùng **model `acne-llm-vi:v1` đã fine-tune**.
  - `rag_only` / `hybrid` → raise `HTTPException(501, "RAG mode chưa kích hoạt ở phiên bản fine-tune. Vui lòng dùng mode='llm_only'.")`.

Schema, guardrails, vision interface, web UI giữ nguyên không đổi.

---

## 7. EVALUATION & MONITORING

### 7.1 Metrics (giữ và mở rộng)

| Loại | Metric | Target |
|---|---|---|
| Training | Train loss (curve giảm smooth) | qualitative |
| Training | Val loss < train loss + 0.15 | hạn chế overfit |
| Training | Format compliance trên `val.jsonl` | ≥ 95% (parse AdviseOutput OK) |
| Runtime | Format compliance trên 50 query live | ≥ 97% |
| Runtime | Severity accuracy vs ground-truth | **≥ 75% (tăng từ ≥ 70% của RAG)** |
| Runtime | Safety compliance (pregnancy-retinoid, severe-see-doctor) | **100%** |
| Runtime | Latency p50 / p95 (CPU) | **≤ 4s / 8s (giảm mạnh vì bỏ rerank)** |
| A/B | `acne-llm-vi:v1` vs base `qwen2.5:7b-instruct` trên test set | Win-rate ≥ 60% theo LLM-as-judge |

### 7.2 Logging

`loguru` JSON log vẫn như cũ. Thêm:
- `training/callbacks.py` dump train/val loss mỗi step vào `data/eval_reports/train_log.jsonl`.
- `eval/ab_compare.py` xuất CSV + PNG so sánh.

---

## 8. ROADMAP 6 TUẦN (RE-MAP)

| Tuần | Nội dung | Deliverable |
|---|---|---|
| **1** | Scaffold repo theo structure mới; stub hết crawler/rag; lock schema `core.py`; viết `entities.yaml`, `personas.yaml`, `templates.yaml` draft. | Repo compile, `pytest tests/test_schemas.py` pass. |
| **2** | Bước 1+2+3 dataset: seed_curator, prompt_factory, synth_generator. Sinh **raw_synth.jsonl ≥ 12.000 rows** dùng Qwen2.5-72B qua Ollama (hoặc API nếu budget). | `data/datasets/raw_synth.jsonl` + audit log. |
| **3** | Bước 4+5+6: validator, curator (MinHash + guardrail + diversity), scorer (LLM-judge). | `data/datasets/scored.jsonl` ≥ 5.200 rows, eval báo cáo phân bố. |
| **4** | Bước 7 training: SFT LoRA Qwen2.5-7B trên train.jsonl. Eval val.jsonl mỗi 100 step. | `data/checkpoints/acne-llm-vi-v1/` + curve PNG. |
| **5** | Export GGUF Q4_K_M + Modelfile + `ollama create acne-llm-vi:v1`. Wire vào `.env` + `di.py`. Chạy FastAPI + Web UI end-to-end. | `make serve` hoạt động với model FT, `/api/v1/chat` trả AdviseOutput hợp lệ < 8s. |
| **6** | Eval: format compliance, severity acc, safety, latency, A/B vs base. Viết README mới + báo cáo. | Báo cáo eval PDF + video demo 5 phút. |

---

## 9. CHECKLIST DONE (PHIÊN BẢN MỚI)

```bash
git clone <repo> && cd acne_llm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Pull base + teacher (teacher chỉ cần 1 lần khi sinh data)
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull qwen2.5:72b-instruct-q4_K_M   # teacher — optional nếu dùng API

# 2. Sinh LLMData (bước 1→6)
make gen-data            # python -m scripts.gen_llmdata
# → data/datasets/scored.jsonl ≥ 5.200 rows

# 3. Train (bước 7a+7b)
make train               # python -m scripts.train_sft
# → data/checkpoints/acne-llm-vi-v1/

# 4. Export + tạo Ollama model (bước 7c)
make export-gguf         # python -m scripts.export_gguf
# → ollama list | grep acne-llm-vi

# 5. Wire .env: LLM_MODEL=acne-llm-vi:v1

# 6. Test
pytest -v                # ≥ 20 tests pass; RAG tests = expected 501

# 7. Serve
make serve               # http://localhost:8000 — UI chat hoạt động với model FT

# 8. Eval + A/B
make eval N=50
```

**Deliverables cụ thể:**
- [ ] Structure thư mục khớp blueprint gốc (crawler/, rag/, llm/, vision/, pipeline/, guardrails/, eval/, api/, schemas/) — **có thêm** `dataset/` và `training/`.
- [ ] Schema `core.py` KHÔNG bị sửa 1 field nào.
- [ ] `config/ontology/{entities,personas,templates}.yaml` ≥ (300, 30, 20) records.
- [ ] `data/datasets/scored.jsonl` ≥ 5.200 samples, dedup + guardrail-compliant + score ≥ 4.0.
- [ ] LoRA adapter + merged HF + GGUF Q4_K_M tồn tại.
- [ ] `ollama list` hiển thị `acne-llm-vi:v1`.
- [ ] FastAPI `/api/v1/chat` với `mode=llm_only` trả `AdviseOutput` hợp lệ < 8s p95.
- [ ] `/api/v1/chat` với `mode=rag_only|hybrid` trả HTTP 501 kèm thông điệp lịch sự.
- [ ] Web UI 3 tabs vẫn hoạt động (Chat chạy thực, Explorer hiển thị "RAG disabled", Settings cho chọn model Ollama).
- [ ] Test guardrails: case pregnancy + retinoid block PASS.
- [ ] Eval report: format compliance ≥ 95%, safety 100%, A/B vs base win-rate ≥ 60%.
- [ ] README mới mô tả rõ "RAG là optional, có thể kích hoạt sau bằng cách implement `RAGProtocol`".

---

## 10. RAG OPTIONAL — HƯỚNG DẪN KÍCH HOẠT LẠI SAU

Khi cần bật RAG (ví dụ ghép đề tài 28 RAG nâng cao):

1. Implement đầy đủ `src/acne_llm/rag/embedder.py`, `vectorstore.py`, `sparse.py`, `retriever.py`, `reranker.py` theo **đúng signature cũ trong blueprint gốc**.
2. Implement `src/acne_llm/crawler/*` hoặc import dataset KB đã có sẵn vào `data/processed/chunks.jsonl` + build ChromaDB + BM25.
3. Đổi `.env`: `RAG_ENABLED=true`.
4. `di.py` sẽ tự khởi tạo `HybridRetriever + Reranker`, và `HybridPipeline` hoạt động trở lại.
5. FastAPI không cần thay đổi — `routes/chat.py` tự dispatch theo `user.mode`.

Toàn bộ schema contract, guardrails, prompt templates, web UI không phải sửa 1 dòng.

---

## 🎯 TÓM TẮT YÊU CẦU CUỐI CÙNG CHO NGƯỜI THỰC THI PROMPT

1. **Giữ nguyên** structure thư mục, schema `core.py`, triết lý LEGO modular, 3 pipeline modes, guardrails y khoa, FastAPI + HTMX + Tailwind UI, Ollama backend, Jinja2 prompts, Pydantic v2, Typer CLI, docker-compose.
2. **Loại bỏ khỏi runtime default**: crawler, ChromaDB, BM25, embedder, reranker — chuyển thành **stub raise `NotImplementedError`** với thông điệp rõ ràng. **Không xóa file**, giữ interface `Protocol` để sau cắm lại.
3. **Thêm 2 tầng mới**: `src/acne_llm/dataset/` (7 bước build LLMData) và `src/acne_llm/training/` (SFT LoRA + export GGUF).
4. **Re-map workflow 7 bước** từ (Clean→Chunk→Embed→Store→Retrieve→Rerank→Compose) sang (Seed→PromptTemplate→SynthGen→Validate→Curate→Score→Fine-tune) — **giữ ý tưởng 7-node pipeline**.
5. Runtime mặc định = `llm_only` với model `acne-llm-vi:v1` đã fine-tune qua Ollama Modelfile.
6. RAG = **optional**, kích hoạt bằng `RAG_ENABLED=true` + implement 5 module đã có signature sẵn.
7. Mọi sample dataset phải **parse được schema `AdviseOutput`** + **pass guardrails** trước khi đưa vào train.
8. Báo cáo cuối cùng phải có: curve loss, format compliance %, safety %, latency p50/p95, A/B win-rate vs base, demo video.

**Bắt đầu bằng việc scaffold repo theo §4, lock schema theo §0.2, rồi tuần tự đi qua §5 → §6 → §7 → §8 theo roadmap.**
