# 🧠 BLUEPRINT — PROJECT **AcneLLM** (Đề tài 29)

> **Mục tiêu tổng:** Xây hệ thống tư vấn da mụn tiếng Việt chạy local, lõi là một **LLM + RAG pipeline 7 bước** hoàn chỉnh, khai thác knowledge base ≥ 20.000 entities crawl từ nguồn y khoa uy tín EN/VN. Expose qua **FastAPI** làm backend dùng chung cho cả web UI lẫn mobile app (đề tài 29 — local-first).

Blueprint này **kế thừa contract schema** và triết lý "LEGO modular" từ prompt `AcneAdvisor` gốc (để sau này ghép được với đề tài 27 vision và đề tài 28 RAG nâng cao), nhưng **đào sâu về phần LLM/RAG/data** — đúng trọng tâm của đề tài 29.

---

## 📑 MỤC LỤC

0. [Bối cảnh & scope](#0-bối-cảnh--scope)
1. [Tech Stack](#1-tech-stack)
2. [Kiến trúc tổng thể](#2-kiến-trúc-tổng-thể)
3. [Đề xuất LLM Ollama tiếng Việt](#3-đề-xuất-llm-ollama-tiếng-việt)
4. [Schema dữ liệu JSON](#4-schema-dữ-liệu-json)
5. [Chiến lược crawl 20k+ entities](#5-chiến-lược-crawl-20k-entities)
6. [RAG pipeline 7 bước](#6-rag-pipeline-7-bước)
7. [FastAPI backend](#7-fastapi-backend)
8. [Cấu trúc thư mục](#8-cấu-trúc-thư-mục)
9. [Roadmap triển khai 6 tuần](#9-roadmap-triển-khai-6-tuần)
10. [Eval & Monitoring](#10-eval--monitoring)
11. [Checklist Done](#11-checklist-done)

---

## 0. Bối cảnh & scope

### 0.1 So sánh với prompt gốc

| Aspect | `AcneAdvisor` (prompt gốc) | **`AcneLLM`** (blueprint này) |
|---|---|---|
| Quy mô KB | ~50 chunks demo | **≥ 20.000 entities** |
| Nguồn dữ liệu | 5 seed URLs | **~15 domains EN/VN + PubMed abstracts** |
| UI | Streamlit | **FastAPI + web UI + JSON API cho mobile** |
| LLM runtime | `llama-cpp-python` primary | **`ollama` primary** (vì dễ deploy, swap model) |
| Retrieval | Dense + BM25 + RRF | **+ Reranker** (bge-reranker-v2-m3) |
| Vision | MockVision | Vẫn giữ interface, nhưng không phải focus |

### 0.2 Ràng buộc cứng

- ✅ **Chạy 100% local** khi inference (Ollama + ChromaDB + FastAPI trên cùng máy hoặc LAN).
- ✅ Phục vụ được cả **web client** (HTML/HTMX) và **mobile client** qua HTTP JSON — chính là kiến trúc đã nhắc ở memory (FastAPI + Ollama expose qua WiFi).
- ✅ **Không finetune** ở pha này — chỉ prompting + RAG.
- ❌ Không gọi OpenAI/Anthropic/Gemini API trong runtime. Chỉ được dùng offline để **làm giàu dataset** (synthetic QA) nếu cần, phải ghi rõ log.
- ✅ Swap được LLM và embedding model bằng cách đổi `.env`, không phải sửa code.

---

## 1. Tech Stack

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python 3.11 | Chuẩn ML hiện tại, type hints cải tiến |
| LLM runtime | **Ollama** (primary) | HTTP API cục bộ `localhost:11434`, swap model 1 lệnh |
| Model LLM chính | **Qwen2.5-7B-Instruct** (Q4_K_M) | Thông thạo tiếng Việt nhất trong nhóm 7B — xem §3 |
| Model fallback | **SeaLLMs-v3-7B-Chat** / **Llama-3.1-8B** | Dự phòng, A/B test |
| Embedding | **`AITeamVN/Vietnamese_Embedding`** (BGE-M3 VI finetune) | Top VN-MTEB, dim 1024 |
| Reranker | **`BAAI/bge-reranker-v2-m3`** | Multilingual, cross-encoder |
| Vector DB | **ChromaDB** (persist local) | Nhẹ, file-based, không cần server |
| Sparse index | **`rank_bm25`** + index đĩa (pickle) | Hybrid search |
| Text segmentation VI | **`underthesea`** + custom recursive splitter | Tokenize đúng tiếng Việt |
| Crawler | **`httpx[http2]` + `trafilatura` + `playwright`** (fallback JS) | Sạch HTML, respect robots |
| Framework API | **FastAPI 0.115+** | Async, OpenAPI docs miễn phí |
| Template engine | **Jinja2** + **HTMX** | UI không cần build step, vẫn interactive |
| Styling | **Tailwind CSS** (CDN) + **Lucide icons** | UI chuyên nghiệp, không cần npm |
| Validation | **Pydantic v2** | Contract giữa các layer |
| Config | **pydantic-settings** + `.env` | 12-factor |
| CLI | **typer** | Crawl / build-kb / eval |
| Logging | **loguru** | JSON log + file rotation |
| Testing | **pytest + pytest-asyncio + httpx.AsyncClient** | Test API end-to-end |
| Queue (optional) | **FastAPI BackgroundTasks** | Đủ cho giai đoạn này, không cần Celery |
| Container | **Docker + docker-compose** | Để bàn giao cho giáo viên dễ |

> ⚠️ **Không dùng LangChain / LlamaIndex**. Viết tay pipeline để học được và dễ customize cho tiếng Việt. Prompt gốc đã nêu rõ lý do này và blueprint tuân thủ.

---

## 2. Kiến trúc tổng thể

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                            ACNELLM — HIGH LEVEL                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─────────────────┐      ┌─────────────────┐      ┌──────────────────────┐
│   Web Browser   │      │   Mobile App    │      │  CLI / Postman /     │
│  (HTMX + TW)    │      │  (đề tài 29)    │      │  External service    │
└────────┬────────┘      └────────┬────────┘      └──────────┬───────────┘
         │  HTTPS/WS               │  HTTP (LAN)             │  HTTP
         └─────────────┬───────────┴─────────────────────────┘
                       │
                       ▼
      ╔══════════════════════════════════════════════════════╗
      ║              FASTAPI APPLICATION LAYER               ║
      ║  /api/v1/chat   /api/v1/retrieve   /api/v1/kb/*      ║
      ║  /ws/chat        /health            /ui (templates)  ║
      ╚════════════════════════╤═════════════════════════════╝
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
       │  GUARDRAILS  │ │   PIPELINE   │ │  OBSERVABIL. │
       │  (pre+post)  │ │  ORCHESTRATOR│ │  (loguru,    │
       │              │ │  3 modes     │ │   metrics)   │
       └──────┬───────┘ └──────┬───────┘ └──────────────┘
                               │
        ┌──────────────────────┼──────────────────────────┐
        ▼                      ▼                          ▼
 ┌─────────────┐   ┌──────────────────────┐    ┌─────────────────┐
 │   VISION    │   │    RAG PIPELINE      │    │       LLM       │
 │ (mock / 27) │   │                      │    │    (Ollama)     │
 │             │   │  ┌────────────────┐  │    │                 │
 │ VisionProto │   │  │ 1. Clean       │  │    │ LLMProtocol     │
 │             │   │  │ 2. Chunk (VI)  │  │    │ - Qwen2.5-7B    │
 └─────────────┘   │  │ 3. Embed       │  │    │ - SeaLLM (fb)   │
                   │  │ 4. Store       │  │    │ - GBNF grammar  │
                   │  │ 5. Retrieve    │  │    │   cho JSON out  │
                   │  │    (hybrid RRF)│  │    └────────┬────────┘
                   │  │ 6. Rerank      │  │             │
                   │  │ 7. Compose ctx │◄─┼─────────────┘
                   │  └───────┬────────┘  │
                   │          │           │
                   │  ┌───────▼────────┐  │
                   │  │  ChromaDB +    │  │
                   │  │  BM25 index    │  │
                   │  │  (persist)     │  │
                   │  └───────┬────────┘  │
                   └──────────┼───────────┘
                              │
                ╔═════════════▼══════════════╗
                ║   OFFLINE DATA PIPELINE    ║
                ║                            ║
                ║  ┌──────────────────────┐  ║
                ║  │ Crawler (httpx +     │  ║
                ║  │ trafilatura + PW)    │  ║
                ║  │    ↓                 │  ║
                ║  │ Normalizer (EN→VI    │  ║
                ║  │  dịch optional)      │  ║
                ║  │    ↓                 │  ║
                ║  │ Validator (Pydantic) │  ║
                ║  │    ↓                 │  ║
                ║  │ data/processed/*.jsonl│  ║
                ║  │ (≥ 20.000 records)   │  ║
                ║  └──────────────────────┘  ║
                ║                            ║
                ║  Nguồn: PubMed · AAD ·     ║
                ║  NICE · DermNet · Vinmec · ║
                ║  BVDL · HelloBacsi · ...   ║
                ╚════════════════════════════╝
```

**Luồng request `/api/v1/chat` (mode hybrid):**

```
User ──► FastAPI route ──► Pydantic validate UserInput
                              │
                              ▼
                        Guardrails pre-check
                              │
                              ▼
                        Build retrieval query
                              │
                              ▼
         ┌────────── Hybrid RAG (dense + sparse → RRF) ──────────┐
         │                                                        │
         │  top-20 chunks ──► Reranker ──► top-5 chunks           │
         └────────────────────────┬───────────────────────────────┘
                                  ▼
                          Prompt Builder
                     (system + user + ctx)
                                  │
                                  ▼
                      Ollama generate (JSON grammar)
                                  │
                                  ▼
                      Parse → AdviseOutput
                                  │
                                  ▼
                       Guardrails post-check
                                  │
                                  ▼
                       JSON response + citations
```

---

## 3. Đề xuất LLM Ollama tiếng Việt

### 3.1 Ma trận so sánh

| Model | Ollama tag | RAM (Q4_K_M) | VN quality | Instruct | JSON mode | Ghi chú |
|---|---|---|---|---|---|---|
| **Qwen2.5-7B-Instruct** ⭐ | `qwen2.5:7b-instruct-q4_K_M` | ~5.5 GB | ★★★★★ | ✅ | ✅ | **Primary.** Tiếng Việt tự nhiên nhất trong nhóm 7B, follow instruction tốt, hỗ trợ tool-use. |
| SeaLLMs-v3-7B-Chat | import qua Modelfile từ GGUF | ~5.5 GB | ★★★★★ | ✅ | ⚠️ prompt | Finetune cho SEA languages, tiếng Việt tự nhiên. Dự phòng. |
| Llama-3.1-8B-Instruct | `llama3.1:8b-instruct-q4_K_M` | ~6 GB | ★★★★ | ✅ | ✅ | Đa ngôn ngữ, mạnh reasoning, VN vẫn ổn. |
| Gemma2-9B-it | `gemma2:9b-instruct-q4_K_M` | ~7 GB | ★★★★ | ✅ | ⚠️ | Nặng hơn, VN tốt nhưng đôi lúc sang tiếng Anh. |
| Aya-Expanse-8B | `aya-expanse:8b` | ~6 GB | ★★★★ | ✅ | ⚠️ | Đa ngôn ngữ của Cohere. |
| Vistral-7B-Chat | import từ GGUF | ~5 GB | ★★★★ | ✅ | ⚠️ | VN-specific của VILM, mạnh nhưng base cũ (Mistral-7B v0.1). |
| PhoGPT-4B-Chat | import từ GGUF | ~3 GB | ★★★ | ✅ | ⚠️ | Nhẹ, chạy được RAM 6GB, backup cho máy yếu. |

### 3.2 Lựa chọn final

**Primary:** `qwen2.5:7b-instruct-q4_K_M` — lý do:

1. **Pretraining đa ngôn ngữ Châu Á** → tiếng Việt tự nhiên, không bị lai từ Hán Việt gượng.
2. **Instruction following mạnh** — quan trọng khi ép output JSON schema.
3. **Built-in JSON mode** qua Ollama (`format: "json"`).
4. **Cập nhật** (Qwen2.5 release 2024) — gần cutoff nhất trong nhóm open weight 7B.

**Cài đặt:**
```bash
# Primary
ollama pull qwen2.5:7b-instruct-q4_K_M

# Fallback nhẹ cho máy 8GB
ollama pull llama3.2:3b-instruct-q4_K_M

# Embedding (tùy chọn chạy qua Ollama thay vì HF)
ollama pull bge-m3  # nếu muốn gọi embedding qua cùng interface
```

### 3.3 Modelfile custom (cho Vistral/SeaLLM nếu cần)

```Dockerfile
# Modelfile.sealmm
FROM ./seallm-v3-7b-chat.Q4_K_M.gguf
TEMPLATE """<|im_start|>system
{{ .System }}<|im_end|>
<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"""
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER num_ctx 8192
PARAMETER stop "<|im_end|>"
SYSTEM "Bạn là trợ lý tư vấn da liễu AcneLLM. Luôn trả lời bằng tiếng Việt."
```
```bash
ollama create seallm-acne -f Modelfile.sealmm
```

---

## 4. Schema dữ liệu JSON

Giữ **toàn bộ schema từ prompt gốc** (`VisionOutput`, `UserInput`, `AdviseOutput`, `Recommendation`, `RedFlag`…) — đây là contract với đề tài 27/28. Blueprint này **mở rộng thêm schema cho KB và crawler**.

### 4.1 KB record schema (mỗi "entity" = 1 record)

```python
# src/acne_llm/schemas/kb.py
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class SourceMeta(BaseModel):
    """Metadata về nguồn gốc."""
    domain: str                    # "vinmec.com"
    source_name: str               # "Vinmec"
    trust_level: Literal["high", "medium", "low"]
    language: Literal["vi", "en"]
    crawled_at: datetime
    robots_allowed: bool = True
    license: Optional[str] = None  # "CC-BY", "public-domain", "copyrighted-fair-use"...


class DocumentRaw(BaseModel):
    """Record gốc sau crawl, trước khi chunk."""
    model_config = ConfigDict(extra="forbid")

    doc_id: str                    # hash-based, stable across runs
    url: HttpUrl
    title: str
    text: str                      # full clean text (markdown-ish)
    html_len: int                  # để monitor crawl quality
    text_len: int
    source: SourceMeta
    categories: list[str] = Field(default_factory=list)  # ["acne", "treatment", ...]
    tags: list[str] = Field(default_factory=list)        # ["isotretinoin", "papule", ...]
    summary: Optional[str] = None                         # LLM-generated 2-3 câu, optional
    quality_score: float = Field(ge=0, le=1, default=0.5) # heuristic: len, noise, structure


class KBChunk(BaseModel):
    """Đơn vị để embed + index. Đây là 'entity' trong target 20k+."""
    model_config = ConfigDict(extra="forbid")

    chunk_id: str                  # f"{doc_id}::{idx:04d}"
    doc_id: str                    # FK về DocumentRaw
    text: str
    text_len: int
    position: int                  # thứ tự trong document
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None

    # Inherited from parent
    url: HttpUrl
    title: str
    source_name: str
    trust_level: Literal["high", "medium", "low"]
    language: Literal["vi", "en"]
    categories: list[str]
    tags: list[str]

    # For hybrid retrieval
    embedding: Optional[list[float]] = None   # 1024 dim BGE-M3


class EntityRecord(BaseModel):
    """
    Entity trích xuất có cấu trúc (bonus layer). 
    Giúp RAG structured: 'isotretinoin là gì?' query thẳng vào entity, không cần chunk.
    """
    entity_id: str
    entity_type: Literal[
        "active_ingredient",  # e.g. benzoyl peroxide
        "medication",         # e.g. isotretinoin
        "condition",          # e.g. acne vulgaris
        "procedure",          # e.g. chemical peel
        "product_class",      # e.g. retinoid
        "anatomy",            # e.g. sebaceous gland
    ]
    name_vi: str
    name_en: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    description: str                             # 1-2 đoạn
    contraindications: list[str] = Field(default_factory=list)
    related_chunk_ids: list[str] = Field(default_factory=list)
    sources: list[HttpUrl] = Field(default_factory=list)
```

### 4.2 File layout của KB (JSONL on disk)

```
data/
├── raw/                          # HTML/PDF gốc (gitignore, ~3-5 GB)
│   └── {source}/{yyyy-mm-dd}/{hash}.html
│
├── processed/
│   ├── documents.jsonl           # ~3.000 - 5.000 DocumentRaw
│   ├── chunks.jsonl              # ≥ 20.000 KBChunk
│   └── entities.jsonl            # ~500 - 2.000 EntityRecord
│
├── chroma_db/                    # persist vector store
│   └── chroma.sqlite3 + parquet
│
├── bm25_index.pkl                # pickle của BM25Okapi
│
└── seed_sources.yaml             # config nguồn crawl
```

### 4.3 Ví dụ 1 record `KBChunk` thực tế

```json
{
  "chunk_id": "vinmec_a1b2c3d4::0003",
  "doc_id": "vinmec_a1b2c3d4",
  "text": "Mụn viêm (papule) là các nốt đỏ, sờ vào hơi cộm, thường không có đầu mủ rõ ràng. Nguyên nhân là do vi khuẩn Cutibacterium acnes xâm nhập vào nang lông bị bít tắc, gây phản ứng viêm. Không nên tự nặn vì dễ để lại sẹo thâm và sẹo rỗ.",
  "text_len": 234,
  "position": 3,
  "prev_chunk_id": "vinmec_a1b2c3d4::0002",
  "next_chunk_id": "vinmec_a1b2c3d4::0004",
  "url": "https://www.vinmec.com/vie/bai-viet/mun-trung-ca-nguyen-nhan-va-cach-dieu-tri-vi",
  "title": "Mụn trứng cá: Nguyên nhân và cách điều trị",
  "source_name": "Vinmec",
  "trust_level": "high",
  "language": "vi",
  "categories": ["acne", "general", "treatment"],
  "tags": ["papule", "c_acnes", "inflammation"],
  "embedding": null
}
```

---

## 5. Chiến lược crawl 20k+ entities

### 5.1 Mục tiêu định lượng

| Pipeline stage | Mục tiêu | Tỷ lệ giữ lại |
|---|---|---|
| URLs seed + sitemap discovery | ~8.000 URLs | 100% |
| Sau fetch thành công | ~6.000 docs | ~75% |
| Sau quality filter (len, noise) | ~3.500 docs | ~58% |
| Sau dedup (MinHash LSH) | ~2.800 docs | ~80% |
| Sau chunking (avg 8 chunks/doc) | **≥ 22.400 chunks** | — |
| + Entity extraction | ~1.000 entities | bonus |

→ **Tổng entity (chunks + entities) ≥ 23.400** → vượt mốc 20k.

### 5.2 Nguồn dữ liệu

**Tiếng Việt (high trust):**
| Domain | Trust | Cách thu | Est. docs |
|---|---|---|---|
| `vinmec.com/vie/bai-viet/` | high | sitemap.xml + category | ~800 |
| `bvdl.org.vn` (BV Da liễu TP.HCM) | high | category crawl | ~200 |
| `dalieu.vn` (BV Da liễu TW) | high | category crawl | ~150 |
| `hellobacsi.com` | medium | sitemap + tag `da lieu` | ~600 |
| `tamanhhospital.vn` | high | category crawl | ~150 |
| `medlatec.vn` | medium | sitemap | ~300 |
| `youmed.vn` | medium | category | ~200 |
| `pharmacity.vn/cam-nang` | medium | category | ~150 |

**Tiếng Anh (high trust):**
| Domain | Trust | Cách thu | Est. docs |
|---|---|---|---|
| `pubmed.ncbi.nlm.nih.gov` | high | **E-utilities API** query `acne[MeSH]` | ~2.000 abstracts |
| `aad.org/public/diseases/acne` | high | full section crawl | ~150 |
| `nice.org.uk/guidance/ng198` | high | guideline pages + PDF | ~50 |
| `dermnetnz.org/topics/acne` | high | topic pages | ~200 |
| `cochranelibrary.com` | high | search `acne`, lấy abstract | ~300 |
| `medlineplus.gov` | high | acne + skin topics | ~80 |
| `mayoclinic.org` | high | acne section | ~100 |
| `clevelandclinic.org/health` | high | skin topics | ~80 |

> **PubMed là nguồn chủ lực để đạt 20k**: 2.000 abstracts × avg 3 chunks = ~6.000 chunks chỉ từ PubMed.

### 5.3 Crawler modules

```
src/acne_llm/crawler/
├── __init__.py
├── base.py              # CrawlerProtocol
├── discovery.py         # sitemap.xml / robots.txt / category pagination
├── fetcher.py           # httpx async + playwright fallback (JS-heavy sites)
├── extractor.py         # trafilatura + readability-lxml fallback
├── normalizer.py        # unicode NFC, whitespace, VN diacritics
├── translator.py        # EN→VI (optional, dùng NLLB-200 local hoặc giữ nguyên EN)
├── dedup.py             # MinHash LSH (datasketch)
├── quality_filter.py    # rules: min_len, noise_ratio, lang detect
└── sources/
    ├── __init__.py
    ├── generic_html.py
    ├── pubmed.py        # chuyên biệt, dùng E-utilities
    └── vinmec.py        # có lộ trình crawl riêng nếu cần
```

### 5.4 Seed config

```yaml
# data/seed_sources.yaml
version: 1
rate_limit_per_domain: 1.0   # req/sec
user_agent: "AcneLLM-Bot/1.0 (student research; contact: khang@...)"
respect_robots: true

sources:
  - name: Vinmec
    domain: vinmec.com
    trust_level: high
    language: vi
    discovery:
      type: sitemap
      sitemap_url: https://www.vinmec.com/sitemap.xml
      filter_path_contains: ["/bai-viet/", "/benh/"]
      filter_keywords: ["mụn", "da", "trứng cá", "viêm nang lông"]
    extractor: trafilatura
    max_pages: 1500

  - name: PubMed
    domain: pubmed.ncbi.nlm.nih.gov
    trust_level: high
    language: en
    discovery:
      type: api
      api: ncbi_eutilities
      query: '(acne[MeSH Terms]) AND (hasabstract[text]) AND ("2010"[Date - Publication] : "3000"[Date - Publication])'
      retmax: 3000
    extractor: pubmed_xml
    max_pages: 3000

  - name: BVDL-HCM
    domain: bvdl.org.vn
    trust_level: high
    language: vi
    discovery:
      type: category
      start_urls:
        - https://www.bvdl.org.vn/chuyen-muc/benh-da-lieu/
      pagination_selector: "a.page-link"
    extractor: trafilatura
    max_pages: 300

  # ... 12 nguồn khác
```

### 5.5 Pipeline crawl (CLI)

```bash
# Bước 1: Discovery - thu thập URL (không fetch content)
python -m scripts.crawl discover --source all --out data/urls.jsonl

# Bước 2: Fetch với rate limit, retry, cache
python -m scripts.crawl fetch --urls data/urls.jsonl --concurrency 8

# Bước 3: Extract + clean
python -m scripts.crawl extract --raw-dir data/raw/ --out data/processed/documents.jsonl

# Bước 4: Dedup
python -m scripts.crawl dedup --in data/processed/documents.jsonl --threshold 0.85

# Bước 5: Report
python -m scripts.crawl report  # in bảng thống kê / nguồn, / ngôn ngữ
```

### 5.6 Ví dụ code fetcher (async + rate limit + retry)

```python
# src/acne_llm/crawler/fetcher.py
import asyncio
from datetime import datetime
from pathlib import Path
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..schemas.kb import SourceMeta


class DomainRateLimiter:
    def __init__(self, rate_per_sec: float = 1.0):
        self._min_interval = 1.0 / rate_per_sec
        self._last: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            last = self._last.get(domain, 0.0)
            wait = self._min_interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[domain] = asyncio.get_event_loop().time()


class AsyncFetcher:
    def __init__(self, user_agent: str, rate_per_sec: float = 1.0):
        self._client = httpx.AsyncClient(
            http2=True,
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
        )
        self._limiter = DomainRateLimiter(rate_per_sec)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=30))
    async def fetch(self, url: str, domain: str) -> tuple[str, int]:
        await self._limiter.acquire(domain)
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.text, resp.status_code

    async def close(self) -> None:
        await self._client.aclose()
```

### 5.7 Quality filter rules

Một `DocumentRaw` được giữ lại nếu:
- `text_len ∈ [500, 50_000]`
- `noise_ratio < 0.4` (tỉ lệ ký tự phi-Unicode chuẩn / tổng)
- `lang_detected == lang_expected` (dùng `fasttext-langdetect`)
- Không phải trang index/redirect (title < 10 từ → reject)
- `title` hoặc `text` chứa ít nhất 1 trong ~30 keyword về mụn/da (whitelist)

---

## 6. RAG pipeline 7 bước

### 6.1 Bước 1 — **Cleaning**

Đầu vào: `DocumentRaw.text`. Đầu ra: text đã chuẩn hóa.

```python
# src/acne_llm/rag/cleaning.py
import re
import unicodedata

BOILERPLATE_PATTERNS = [
    r"(?i)đọc thêm[:\s].+?\n",
    r"(?i)xem thêm[:\s].+?\n",
    r"(?i)nguồn[:\s]https?://\S+",
    r"\n{3,}",                             # nhiều dòng trắng
    r"(?i)quý khách hàng.+?\d{10,11}",     # quảng cáo phòng khám
]

def clean_vi_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)            # VN diacritics standard
    text = re.sub(r"\s+", " ", text)                     # collapse whitespace
    for pat in BOILERPLATE_PATTERNS:
        text = re.sub(pat, " ", text)
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)    # zero-width chars
    return text.strip()
```

### 6.2 Bước 2 — **Chunking** (tiếng Việt aware)

**Chiến lược:** Recursive splitting với separator ưu tiên VN:
1. Paragraph (`\n\n`) → 2. Sentence (`underthesea.sent_tokenize`) → 3. Token window fallback.

**Hyperparameter:**
- `chunk_size = 512 tokens` (đo bằng tokenizer của BGE-M3 ≈ ~350 từ VN)
- `chunk_overlap = 64 tokens`
- `min_chunk_size = 100 tokens` (bỏ chunks quá ngắn)

```python
# src/acne_llm/rag/chunker.py
from underthesea import sent_tokenize
from transformers import AutoTokenizer

class VietnameseChunker:
    def __init__(self, tokenizer_name: str = "AITeamVN/Vietnamese_Embedding",
                 chunk_size: int = 512, overlap: int = 64, min_size: int = 100):
        self.tok = AutoTokenizer.from_pretrained(tokenizer_name)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_size = min_size

    def _token_len(self, text: str) -> int:
        return len(self.tok.encode(text, add_special_tokens=False))

    def chunk(self, text: str) -> list[str]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        buf: list[str] = []
        buf_len = 0

        for para in paragraphs:
            sentences = sent_tokenize(para)
            for sent in sentences:
                slen = self._token_len(sent)
                if buf_len + slen > self.chunk_size and buf:
                    chunks.append(" ".join(buf))
                    # overlap: giữ lại cuối buffer
                    overlap_buf, overlap_len = [], 0
                    for s in reversed(buf):
                        sl = self._token_len(s)
                        if overlap_len + sl > self.overlap:
                            break
                        overlap_buf.insert(0, s)
                        overlap_len += sl
                    buf = overlap_buf
                    buf_len = overlap_len
                buf.append(sent)
                buf_len += slen

        if buf_len >= self.min_size:
            chunks.append(" ".join(buf))
        return chunks
```

### 6.3 Bước 3 — **Embedding**

```python
# src/acne_llm/rag/embedder.py
from sentence_transformers import SentenceTransformer
import numpy as np

class Embedder:
    def __init__(self, model_name: str = "AITeamVN/Vietnamese_Embedding",
                 device: str = "cpu", batch_size: int = 32):
        self.model = SentenceTransformer(model_name, device=device)
        self.batch_size = batch_size
        self.dim = self.model.get_sentence_embedding_dimension()  # 1024

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        # BGE convention: passage prefix không cần với VN finetune này
        return self.model.encode(texts, batch_size=self.batch_size,
                                  normalize_embeddings=True,
                                  show_progress_bar=True)

    def embed_query(self, query: str) -> np.ndarray:
        return self.model.encode([query], normalize_embeddings=True)[0]
```

### 6.4 Bước 4 — **Vector storage** (ChromaDB)

```python
# src/acne_llm/rag/vectorstore.py
import chromadb
from chromadb.config import Settings
from ..schemas.kb import KBChunk

class ChromaStore:
    def __init__(self, persist_dir: str = "./data/chroma_db",
                 collection: str = "acne_kb_vi"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[KBChunk], embeddings: list[list[float]]) -> None:
        self.col.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "url": str(c.url),
                    "source": c.source_name,
                    "trust": c.trust_level,
                    "lang": c.language,
                    "categories": ",".join(c.categories),
                    "tags": ",".join(c.tags),
                }
                for c in chunks
            ],
        )

    def query(self, query_embedding: list[float], top_k: int = 20,
              filters: dict | None = None):
        return self.col.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters or None,
        )
```

### 6.5 Bước 5 — **Retrieval** (Hybrid: dense + sparse → RRF)

```python
# src/acne_llm/rag/retriever.py
from rank_bm25 import BM25Okapi
import underthesea
from ..schemas import RetrievedChunk, RetrievalOutput
from .vectorstore import ChromaStore
from .embedder import Embedder


def rrf_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, doc_id in enumerate(ranks):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + i + 1)
    return scores


class HybridRetriever:
    def __init__(self, store: ChromaStore, embedder: Embedder, bm25_index_path: str):
        self.store = store
        self.embedder = embedder
        self.bm25: BM25Okapi = self._load_bm25(bm25_index_path)

    @staticmethod
    def _tokenize_vi(text: str) -> list[str]:
        return underthesea.word_tokenize(text.lower())

    def retrieve(self, query: str, top_k: int = 20) -> RetrievalOutput:
        # Dense
        q_emb = self.embedder.embed_query(query).tolist()
        dense = self.store.query(q_emb, top_k=top_k * 2)
        dense_ids = dense["ids"][0]

        # Sparse (BM25)
        tokens = self._tokenize_vi(query)
        bm25_scores = self.bm25.get_scores(tokens)
        sparse_ranked = sorted(
            enumerate(bm25_scores), key=lambda x: x[1], reverse=True
        )[: top_k * 2]
        sparse_ids = [self._chunk_ids[i] for i, _ in sparse_ranked]

        # RRF
        fused = rrf_fusion([dense_ids, sparse_ids])
        fused_top = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]

        chunks = [self._build_chunk(cid, score) for cid, score in fused_top]
        return RetrievalOutput(
            query=query,
            chunks=chunks,
            retrieval_mode="hybrid",
            num_chunks=len(chunks),
            avg_score=sum(c.score for c in chunks) / len(chunks) if chunks else 0.0,
        )
```

### 6.6 Bước 6 — **Reranking** (bge-reranker-v2-m3)

```python
# src/acne_llm/rag/reranker.py
from sentence_transformers import CrossEncoder
from ..schemas import RetrievedChunk, RetrievalOutput


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3",
                 device: str = "cpu"):
        self.model = CrossEncoder(model_name, device=device, max_length=512)

    def rerank(self, query: str, retrieval: RetrievalOutput,
               top_k: int = 5) -> RetrievalOutput:
        pairs = [(query, c.text) for c in retrieval.chunks]
        scores = self.model.predict(pairs, show_progress_bar=False)
        ranked = sorted(
            zip(retrieval.chunks, scores), key=lambda x: x[1], reverse=True
        )[:top_k]
        new_chunks = [
            RetrievedChunk(
                chunk_id=c.chunk_id, source=c.source, text=c.text,
                score=float(s), metadata=c.metadata,
            )
            for c, s in ranked
        ]
        return RetrievalOutput(
            query=query, chunks=new_chunks,
            retrieval_mode="rerank", num_chunks=len(new_chunks),
            avg_score=sum(c.score for c in new_chunks) / len(new_chunks)
            if new_chunks else 0.0,
        )
```

### 6.7 Bước 7 — **LLM answer** (compose context + generate)

```python
# src/acne_llm/llm/prompt_builder.py
from jinja2 import Environment, FileSystemLoader
from ..schemas import UserInput, RetrievalOutput


class PromptBuilder:
    def __init__(self, templates_dir: str = "config/prompts"):
        self.env = Environment(loader=FileSystemLoader(templates_dir))

    def build_hybrid(self, user: UserInput, retrieval: RetrievalOutput) -> tuple[str, str]:
        system = self.env.get_template("system.j2").render()
        ctx_blocks = [
            f"[Nguồn {i+1}] {c.metadata.get('source', '?')} — {c.metadata.get('title', '?')}\n"
            f"URL: {c.metadata.get('url', '?')}\n"
            f"{c.text}\n"
            for i, c in enumerate(retrieval.chunks)
        ]
        user_prompt = self.env.get_template("hybrid_user.j2").render(
            description=user.description,
            age=user.context.age,
            skin_type=user.context.skin_type,
            is_pregnant=user.context.is_pregnant,
            is_breastfeeding=user.context.is_breastfeeding,
            current_products=", ".join(user.context.current_products) or "không",
            vision_summary=self._summarize_vision(user.vision),
            retrieved_context="\n---\n".join(ctx_blocks),
        )
        return system, user_prompt
```

```python
# src/acne_llm/llm/ollama_backend.py
import httpx
from ..schemas import AdviseOutput


class OllamaBackend:
    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "qwen2.5:7b-instruct-q4_K_M",
                 num_ctx: int = 8192):
        self._client = httpx.Client(base_url=base_url, timeout=120.0)
        self.model = model
        self.num_ctx = num_ctx

    def generate_json(self, system: str, user: str,
                      schema: dict, temperature: float = 0.3) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,          # Ollama JSON-schema constrained decoding
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
            },
            "stream": False,
        }
        resp = self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
```

### 6.8 Tổng hợp — `HybridPipeline`

```python
# src/acne_llm/pipeline/hybrid.py
import time, json
from ..schemas import UserInput, AdviseOutput
from ..rag.retriever import HybridRetriever
from ..rag.reranker import Reranker
from ..llm.ollama_backend import OllamaBackend
from ..llm.prompt_builder import PromptBuilder
from ..guardrails.runner import GuardrailRunner


class HybridPipeline:
    def __init__(self, retriever: HybridRetriever, reranker: Reranker,
                 llm: OllamaBackend, prompt: PromptBuilder,
                 guardrails: GuardrailRunner):
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.prompt = prompt
        self.guardrails = guardrails

    def run(self, user: UserInput) -> AdviseOutput:
        t0 = time.perf_counter()
        # Pre-guardrails
        self.guardrails.pre_check(user)

        # Retrieve → Rerank
        query = self._build_query(user)
        initial = self.retriever.retrieve(query, top_k=20)
        top = self.reranker.rerank(query, initial, top_k=5)

        # Prompt + LLM
        system, user_prompt = self.prompt.build_hybrid(user, top)
        raw = self.llm.generate_json(system, user_prompt,
                                     schema=AdviseOutput.model_json_schema())
        parsed = AdviseOutput.model_validate_json(raw)
        parsed.latency_ms = int((time.perf_counter() - t0) * 1000)
        parsed.mode = "hybrid"
        parsed.model_name = self.llm.model
        parsed.used_chunks = [c.chunk_id for c in top.chunks]

        # Post-guardrails
        parsed = self.guardrails.post_check(parsed, user)
        return parsed
```

---

## 7. FastAPI backend

### 7.1 Routes

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/` | Web UI (Jinja2 home) |
| `GET` | `/chat` | Web UI chat page (HTMX) |
| `GET` | `/explorer` | Web UI dataset explorer |
| `POST` | `/api/v1/chat` | **Endpoint chính:** UserInput → AdviseOutput |
| `POST` | `/api/v1/chat/stream` | Server-Sent Events streaming |
| `POST` | `/api/v1/retrieve` | RAG-only: query → top-k chunks |
| `GET` | `/api/v1/kb/stats` | Số docs, chunks, phân bố nguồn |
| `POST` | `/api/v1/kb/search` | Search KB (hybrid/dense/sparse toggle) |
| `WS` | `/ws/chat` | WebSocket streaming (alternative) |
| `GET` | `/api/v1/health` | Readiness: Ollama + Chroma ping |
| `GET` | `/api/v1/models` | Danh sách model Ollama available |
| `GET` | `/docs` | OpenAPI (Swagger) — miễn phí từ FastAPI |
| `GET` | `/redoc` | ReDoc |

### 7.2 Skeleton `app.py`

```python
# src/acne_llm/api/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..di import build_container
from .routes import chat, kb, health, ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load models, open DB
    app.state.container = build_container(settings)
    yield
    # Shutdown
    await app.state.container.close()


app = FastAPI(
    title="AcneLLM API",
    version="0.1.0",
    description="Hệ thống tư vấn da mụn tiếng Việt — local RAG + LLM",
    lifespan=lifespan,
)

# CORS cho mobile app (đề tài 29) gọi qua LAN
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # ["http://192.168.x.x:*", ...]
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# Static + templates
app.mount("/static", StaticFiles(directory="src/acne_llm/api/static"), name="static")
templates = Jinja2Templates(directory="src/acne_llm/api/templates")

# Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(kb.router, prefix="/api/v1")
app.include_router(ui.router)  # "/"
```

### 7.3 Route chat chính

```python
# src/acne_llm/api/routes/chat.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from ...schemas import UserInput, AdviseOutput
from ...pipeline.hybrid import HybridPipeline
from ..deps import get_pipeline

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=AdviseOutput)
async def chat(inp: UserInput, pipeline: HybridPipeline = Depends(get_pipeline)):
    try:
        return pipeline.run(inp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")


@router.post("/chat/stream")
async def chat_stream(inp: UserInput, pipeline: HybridPipeline = Depends(get_pipeline)):
    async def gen():
        async for chunk in pipeline.run_stream(inp):
            yield f"data: {chunk}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

### 7.4 Web UI chuyên nghiệp (không cần npm)

**Stack:** Jinja2 + HTMX + Tailwind CDN + Lucide icons + highlight.js cho code block.

**Tab chính:**
1. **💬 Chat** — form mô tả + context (accordion) + nút "Tư vấn" → HTMX `hx-post` → render card AdviseOutput (severity badge, recommendations list, red flags, citation popover).
2. **📚 KB Explorer** — stats dashboard + search bar realtime (HTMX `hx-trigger="keyup changed delay:300ms"`).
3. **⚙️ Settings** — chọn model Ollama, điều chỉnh top_k, temperature (lưu localStorage).
4. **📊 About** — architecture diagram + link `/docs` OpenAPI.

Ví dụ template card kết quả:

```html
<!-- templates/partials/advise_card.html -->
<div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
  <div class="flex items-center gap-3 mb-4">
    <span class="px-3 py-1 rounded-full text-sm font-medium
                 {% if result.severity == 'severe' %}bg-red-100 text-red-800
                 {% elif result.severity == 'moderate' %}bg-amber-100 text-amber-800
                 {% else %}bg-emerald-100 text-emerald-800{% endif %}">
      {{ result.severity | upper }}
    </span>
    <span class="text-slate-500 text-sm">
      Độ tin cậy: {{ "%.0f"|format(result.confidence * 100) }}%
    </span>
  </div>

  <h3 class="font-semibold text-slate-900 mb-2">Chẩn đoán sơ bộ</h3>
  <p class="text-slate-700 mb-4">Loại mụn chính: <strong>{{ result.acne_type_primary }}</strong></p>

  <h3 class="font-semibold text-slate-900 mb-2">Nguyên nhân</h3>
  <ul class="list-disc pl-5 text-slate-700 mb-4">
    {% for cause in result.causes %}<li>{{ cause }}</li>{% endfor %}
  </ul>

  <h3 class="font-semibold text-slate-900 mb-2">Khuyến nghị</h3>
  <ol class="space-y-3 mb-4">
    {% for rec in result.recommendations %}
    <li class="flex gap-3">
      <span class="flex-shrink-0 w-7 h-7 rounded-full bg-indigo-100 text-indigo-700
                   text-sm font-medium flex items-center justify-center">{{ rec.step }}</span>
      <div>
        <p class="text-slate-800">{{ rec.action }}</p>
        {% if rec.rationale %}<p class="text-sm text-slate-500 mt-1">{{ rec.rationale }}</p>{% endif %}
        {% if rec.source_chunk_id %}
        <button class="text-xs text-indigo-600 hover:underline"
                hx-get="/api/v1/kb/chunk/{{ rec.source_chunk_id }}"
                hx-target="#citation-modal">Xem nguồn</button>
        {% endif %}
      </div>
    </li>
    {% endfor %}
  </ol>

  {% if result.red_flags %}
  <div class="rounded-lg border-l-4 border-red-500 bg-red-50 p-4">
    <h4 class="font-semibold text-red-900 mb-2">⚠️ Dấu hiệu cảnh báo</h4>
    {% for flag in result.red_flags %}
    <p class="text-red-800 text-sm">• {{ flag.flag }} — {{ flag.reason }}</p>
    {% endfor %}
  </div>
  {% endif %}

  <p class="text-xs text-slate-400 mt-4 italic">{{ result.disclaimer }}</p>
</div>
```

### 7.5 Dependency injection (DI) đơn giản

```python
# src/acne_llm/di.py
from dataclasses import dataclass
from .rag.embedder import Embedder
from .rag.vectorstore import ChromaStore
from .rag.retriever import HybridRetriever
from .rag.reranker import Reranker
from .llm.ollama_backend import OllamaBackend
from .llm.prompt_builder import PromptBuilder
from .pipeline.hybrid import HybridPipeline
from .guardrails.runner import GuardrailRunner


@dataclass
class Container:
    pipeline: HybridPipeline
    store: ChromaStore
    # ...

    async def close(self):
        pass


def build_container(settings) -> Container:
    embedder = Embedder(settings.embedding_model, device=settings.device)
    store = ChromaStore(settings.chroma_dir)
    retriever = HybridRetriever(store, embedder, settings.bm25_path)
    reranker = Reranker(settings.reranker_model, device=settings.device)
    llm = OllamaBackend(settings.ollama_url, settings.llm_model)
    prompt = PromptBuilder(settings.prompts_dir)
    guardrails = GuardrailRunner(settings.guardrails_yaml)
    pipeline = HybridPipeline(retriever, reranker, llm, prompt, guardrails)
    return Container(pipeline=pipeline, store=store)
```

---

## 8. Cấu trúc thư mục

```
acne_llm/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── Makefile
├── docker-compose.yml           # Ollama + app (bonus)
│
├── config/
│   ├── settings.py              # Pydantic Settings
│   ├── prompts/
│   │   ├── system.j2
│   │   ├── hybrid_user.j2
│   │   └── llm_only_user.j2
│   └── guardrails.yaml
│
├── data/
│   ├── seed_sources.yaml
│   ├── raw/                     # gitignore
│   ├── processed/               # gitignore
│   ├── chroma_db/               # gitignore
│   ├── bm25_index.pkl           # gitignore
│   ├── sample_queries.jsonl     # 50 ground-truth queries
│   └── eval_reports/            # timestamped reports
│
├── src/acne_llm/
│   ├── __init__.py
│   ├── schemas/
│   │   ├── __init__.py          # re-export
│   │   ├── core.py              # VisionOutput, UserInput, AdviseOutput, ...
│   │   └── kb.py                # DocumentRaw, KBChunk, EntityRecord
│   │
│   ├── crawler/
│   │   ├── base.py              # CrawlerProtocol
│   │   ├── discovery.py
│   │   ├── fetcher.py
│   │   ├── extractor.py
│   │   ├── normalizer.py
│   │   ├── dedup.py
│   │   ├── quality_filter.py
│   │   └── sources/
│   │       ├── generic_html.py
│   │       ├── pubmed.py
│   │       └── vinmec.py
│   │
│   ├── rag/
│   │   ├── base.py              # RAGProtocol
│   │   ├── cleaning.py
│   │   ├── chunker.py           # VietnameseChunker
│   │   ├── embedder.py
│   │   ├── vectorstore.py       # ChromaStore
│   │   ├── sparse.py            # BM25 wrapper
│   │   ├── retriever.py         # HybridRetriever (RRF)
│   │   ├── reranker.py
│   │   └── entity_extractor.py  # bonus: trích EntityRecord
│   │
│   ├── llm/
│   │   ├── base.py              # LLMProtocol
│   │   ├── ollama_backend.py
│   │   ├── llama_cpp_backend.py # fallback
│   │   └── prompt_builder.py
│   │
│   ├── vision/
│   │   ├── base.py              # VisionProtocol
│   │   └── mock.py              # Mock đề tài 27
│   │
│   ├── pipeline/
│   │   ├── base.py
│   │   ├── llm_only.py
│   │   ├── rag_only.py
│   │   └── hybrid.py            # ⭐ default
│   │
│   ├── guardrails/
│   │   ├── runner.py
│   │   └── rules.py
│   │
│   ├── eval/
│   │   ├── metrics.py           # Recall@k, MRR, NDCG, format compliance, safety
│   │   ├── judge.py             # LLM-as-judge (dùng chính Qwen)
│   │   └── runner.py
│   │
│   ├── api/
│   │   ├── app.py               # FastAPI entry
│   │   ├── deps.py
│   │   ├── routes/
│   │   │   ├── chat.py
│   │   │   ├── kb.py
│   │   │   ├── health.py
│   │   │   └── ui.py
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── index.html
│   │   │   ├── chat.html
│   │   │   ├── explorer.html
│   │   │   └── partials/
│   │   └── static/
│   │       ├── css/app.css      # Tailwind đã build hoặc CDN
│   │       └── js/app.js
│   │
│   ├── di.py                    # Container
│   ├── utils/
│   │   ├── logging.py
│   │   ├── hashing.py
│   │   └── timer.py
│   └── cli.py                   # typer entry: acne-llm {crawl,build-kb,serve,eval}
│
├── scripts/
│   ├── crawl_all.py             # python -m scripts.crawl_all
│   ├── build_kb.py
│   ├── run_eval.py
│   ├── pull_models.sh           # ollama pull ...
│   └── make_sample_queries.py
│
└── tests/
    ├── conftest.py
    ├── test_schemas.py
    ├── test_chunker.py
    ├── test_cleaning.py
    ├── test_retriever.py
    ├── test_reranker.py
    ├── test_guardrails.py
    ├── test_pipeline_integration.py
    └── test_api.py              # httpx.AsyncClient + test client
```

---

## 9. Roadmap triển khai 6 tuần

> Giả định: 1 sinh viên, ~15-20h/tuần. Có thể nén còn 4 tuần nếu full-time.

### **Tuần 1 — Foundation**
- [ ] Setup repo, venv, `requirements.txt`, `.env.example`, `Makefile`, pre-commit (ruff + mypy).
- [ ] Viết **`schemas/core.py`** (copy từ prompt gốc) + **`schemas/kb.py`** (DocumentRaw, KBChunk, EntityRecord).
- [ ] Viết **Protocols** (`LLMProtocol`, `RAGProtocol`, `VisionProtocol`).
- [ ] Tests cho schema round-trip.
- [ ] Cài Ollama, pull `qwen2.5:7b` + `llama3.2:3b`. Chạy thử `ollama run` bằng tay.
- [ ] **Deliverable:** Repo có structure đầy đủ, `pytest tests/test_schemas.py` pass.

### **Tuần 2 — Crawler + Data**
- [ ] Implement `discovery.py` (sitemap + category).
- [ ] Implement `fetcher.py` (async + rate limit + retry).
- [ ] Implement `extractor.py` (trafilatura + readability fallback).
- [ ] Implement `pubmed.py` (E-utilities để lấy ≥ 2000 abstracts).
- [ ] Implement `normalizer.py`, `dedup.py`, `quality_filter.py`.
- [ ] Viết `data/seed_sources.yaml` với 15 domains.
- [ ] Chạy `python -m scripts.crawl_all` → target ≥ 2.500 `DocumentRaw` valid.
- [ ] **Deliverable:** `data/processed/documents.jsonl` có ≥ 2.500 records, CLI `crawl report` in bảng phân bố.

### **Tuần 3 — Indexing + Retrieval**
- [ ] Implement `cleaning.py` + `VietnameseChunker` + test (chunk size distribution plot).
- [ ] Implement `Embedder` với BGE-M3-VI; benchmark latency trên CPU.
- [ ] Implement `ChromaStore` upsert + query.
- [ ] Implement BM25 index build + persist (`pickle`).
- [ ] Implement `HybridRetriever` + RRF fusion.
- [ ] Chạy `python -m scripts.build_kb` → target **≥ 20.000 chunks** trong Chroma.
- [ ] Implement `Reranker`.
- [ ] Viết `sample_queries.jsonl` (50 case, có ground-truth chunk IDs).
- [ ] **Deliverable:** Notebook `notebooks/retrieval_smoke_test.ipynb` show top-5 cho 10 query mẫu có chất lượng, Recall@10 ≥ 0.7 (sparse), ≥ 0.8 (hybrid + rerank).

### **Tuần 4 — LLM + Pipeline + Guardrails**
- [ ] Implement `OllamaBackend` (chat + stream + JSON schema mode).
- [ ] Viết Jinja2 prompt templates (`system.j2`, `hybrid_user.j2`, `llm_only_user.j2`).
- [ ] Implement `PromptBuilder`.
- [ ] Implement 3 pipelines: `llm_only`, `rag_only`, `hybrid`.
- [ ] Implement `GuardrailRunner` với `guardrails.yaml` (pregnancy, severe, no-popping).
- [ ] Implement `MockVision`.
- [ ] Tests integration cho hybrid pipeline với mock LLM (dùng `MagicMock`) + smoke test với Ollama thật.
- [ ] **Deliverable:** `python -m acne_llm.cli chat "Em bị mụn viêm ở cằm..."` chạy end-to-end, xuất ra `AdviseOutput` hợp lệ.

### **Tuần 5 — FastAPI + Web UI**
- [ ] Setup FastAPI app với lifespan + DI container.
- [ ] Implement routes: `/api/v1/chat`, `/api/v1/chat/stream`, `/api/v1/retrieve`, `/api/v1/kb/*`, `/api/v1/health`.
- [ ] Viết templates (base, chat, explorer) với Tailwind CDN + HTMX.
- [ ] Test `/api/v1/chat` qua Postman + `httpx` test client.
- [ ] Thêm CORS cho mobile app (IP LAN).
- [ ] Viết `docker-compose.yml`: service `ollama` + service `acne-llm` + volume cho Chroma.
- [ ] **Deliverable:** `make serve` hoặc `docker-compose up` → mở `http://localhost:8000` thấy UI chat hoạt động, `http://localhost:8000/docs` thấy OpenAPI.

### **Tuần 6 — Eval + Polish + Docs**
- [ ] Implement `eval/metrics.py`: Recall@k, MRR, NDCG, format compliance, severity accuracy, safety compliance, latency p50/p95.
- [ ] Implement `eval/judge.py` (LLM-as-judge dùng chính Qwen).
- [ ] Chạy full eval với 50 queries × 3 modes → CSV + biểu đồ PNG.
- [ ] Viết **README.md** đầy đủ: architecture diagram ASCII, install steps, demo GIF.
- [ ] Viết báo cáo khoá luận phần kỹ thuật (có thể tái dùng blueprint này).
- [ ] Record video demo 3-5 phút.
- [ ] **Deliverable:** Báo cáo eval + repo bàn giao cho giáo viên.

---

## 10. Eval & Monitoring

### 10.1 Metrics

| Loại | Metric | Target |
|---|---|---|
| Retrieval | Recall@10 (hybrid+rerank) | ≥ 0.85 |
| Retrieval | MRR@10 | ≥ 0.6 |
| Retrieval | NDCG@10 | ≥ 0.75 |
| Output | Format compliance (parse được JSON) | ≥ 95% |
| Output | Severity accuracy vs ground-truth | ≥ 70% |
| Safety | Safety compliance (pregnancy-retinoid, severe-doctor) | **100%** |
| Latency | p50 / p95 (mode hybrid, CPU) | ≤ 8s / 15s |

### 10.2 Logging & observability

- `loguru` JSON logs → `logs/acne-llm.log` (rotating 100MB x10).
- Mỗi request có `request_id`, log: `mode, num_chunks_retrieved, rerank_time_ms, llm_time_ms, total_ms, guardrails_triggered`.
- Optional: tích hợp **Prometheus** counter `/metrics` (FastAPI-Prometheus) cho giai đoạn sau.

---

## 11. Checklist Done

Blueprint coi là hoàn thành khi các lệnh sau **chạy không lỗi trên máy sạch**:

```bash
git clone repo && cd acne_llm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Download LLM
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull llama3.2:3b-instruct-q4_K_M   # fallback

# 2. Crawl (mất 1-3h tùy tốc độ mạng)
make crawl              # hoặc: python -m scripts.crawl_all

# 3. Build KB (mất 30-90 phút với CPU, tùy số chunks)
make build-kb           # hoặc: python -m scripts.build_kb

# 4. Test
pytest -v               # ≥ 25 tests pass

# 5. Run server
make serve              # uvicorn src.acne_llm.api.app:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs

# 6. Eval
make eval N=50          # hoặc: python -m scripts.run_eval --n 50
```

**Deliverables cụ thể:**
- [ ] README.md có ASCII architecture + install guide + demo screenshot
- [ ] `data/processed/documents.jsonl` có ≥ 2.500 documents
- [ ] ChromaDB có **≥ 20.000 chunks**
- [ ] BM25 index build + persist OK
- [ ] ≥ 25 tests pass
- [ ] FastAPI `/docs` hiển thị đủ endpoint
- [ ] Web UI 3 tabs (Chat / Explorer / Settings) hoạt động
- [ ] `/api/v1/chat` trả `AdviseOutput` hợp lệ < 15s cho query thường
- [ ] Guardrails block được case pregnancy + retinoid (có test case)
- [ ] `data/eval_reports/{timestamp}/` có CSV + PNG + summary.md
- [ ] docker-compose up start được cả Ollama + app

---

## 📌 Ghi chú cuối

- **Khi ghép với đề tài 27 (vision):** chỉ cần swap `MockVision` bằng `YOLOCLIPVision` implement `VisionProtocol`. Không sửa pipeline.
- **Khi ghép với đề tài 28 (RAG nâng cao):** swap `HybridRetriever + Reranker` bằng module 28 implement `RAGProtocol`. Không sửa API.
- **Khi mobile app (cùng đề tài 29) cần gọi:** expose port 8000 qua WiFi (`uvicorn --host 0.0.0.0`) hoặc dùng `ngrok`/`tailscale` cho demo.
- **Nếu máy yếu (< 8GB RAM):** đổi `.env` sang `llm_model=llama3.2:3b-instruct-q4_K_M`, vẫn chạy được, chất lượng giảm ~15%.
- **Làm giàu dataset sau này:** có thể sinh synthetic QA từ chunks bằng chính Qwen (offline, ghi log rõ) → fine-tune embedding bằng contrastive learning → tăng Recall thêm 5-10%.

**Nguyên tắc:** chạy được trước — tối ưu sau. Mọi chỗ TODO phải đánh dấu rõ `# TODO(khang): ...` để dễ trace.

---

*Blueprint v1.0 — kế thừa AcneAdvisor, chuyên sâu hoá cho đề tài 29 (LLM + RAG).*
