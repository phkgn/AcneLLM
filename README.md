# AcneLLM

Chatbot tư vấn mụn trứng cá bằng tiếng Việt, kết hợp RAG (hybrid BM25 + vector search) với LLM chạy local qua Ollama.

---

## Yêu cầu hệ thống

- Python **3.10+**
- [Ollama](https://ollama.com) đã cài và đang chạy
- RAM tối thiểu **8 GB** (khuyến nghị 16 GB nếu dùng GPU)
- CUDA 11.8+ (tùy chọn, nếu muốn chạy embedding/reranker trên GPU)

---

## Cài đặt

### 1. Clone repo

```bash
git clone <repo-url>
cd AcneLLM
```

### 2. Tạo virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Cài PyTorch

Chọn đúng build theo phần cứng:

```bash
# CPU only
pip install torch>=2.2 --index-url https://download.pytorch.org/whl/cpu

# CUDA 11.8
pip install torch>=2.2 --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1+
pip install torch>=2.2 --index-url https://download.pytorch.org/whl/cu121
```

### 4. Cài dependencies

```bash
pip install -r requirements.txt
```

### 5. Cài Playwright (crawler JS fallback)

```bash
playwright install chromium
```

### 6. Cấu hình môi trường

```bash
cp .env.example .env
```

Mở `.env` và chỉnh các giá trị cần thiết:

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `OLLAMA_URL` | Địa chỉ Ollama server | `http://localhost:11434` |
| `LLM_MODEL` | Model LLM chính | `qwen2.5:7b` |
| `LLM_FALLBACK_MODEL` | Model dự phòng | `qwen2.5:3b` |
| `DEVICE` | `cpu` hoặc `gpu` | `cpu` |
| `API_KEY` | API key bảo vệ endpoint (để trống = không xác thực) | _(trống)_ |

### 7. Pull model Ollama

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
```

---

## Chạy ứng dụng

Knowledge base đã được build sẵn trong thư mục `data/`. Chạy thẳng server:

```bash
python -m acne_llm.cli serve
```

hoặc dùng uvicorn trực tiếp:

```bash
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

API sẽ chạy tại `http://localhost:8000`.

---

## Build lại Knowledge Base (tùy chọn)

Chỉ cần thực hiện nếu muốn cập nhật dữ liệu mới:

```bash
# Crawl dữ liệu mới
python -m acne_llm.crawler.cli crawl

# Build lại vector index + BM25
python scripts/build_kb.py
```

---

## API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/api/v1/chat` | Chat một lượt |
| `POST` | `/api/v1/chat/stream` | Chat streaming (SSE) |
| `WS` | `/ws/chat` | Chat streaming (WebSocket) |
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/kb/stats` | Thống kê knowledge base |
| `GET` | `/metrics` | Prometheus metrics |

### Ví dụ gọi API

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Mụn đầu đen nên dùng gì?"}'
```

---

## Cấu trúc thư mục

```
AcneLLM/
├── src/acne_llm/
│   ├── api/          # FastAPI app, routes, middleware
│   ├── chat/         # Chat runtime, session, intake
│   ├── rag/          # Chunker, embedder, retriever, vectorstore, reranker
│   ├── llm/          # Ollama backend, prompt builder, clinical planner
│   ├── crawler/      # Web crawler, content extractor
│   ├── guardrails/   # OOD detector, drug checker
│   ├── pipeline/     # HybridPipeline, LLMOnlyPipeline
│   └── config.py     # Cấu hình toàn bộ app
├── scripts/
│   └── build_kb.py   # Build vector index + BM25
├── config/
│   ├── prompts/      # Jinja2 prompt templates
│   └── guardrails.yaml
├── data/
│   ├── chroma_db/    # Vector database (346 MB)
│   ├── bm25_index.pkl # BM25 index (50 MB)
│   └── raw/          # Raw documents + chunks
├── tests/
├── .env.example
└── requirements.txt
```

---

## Chạy Tests

```bash
pytest tests/ -v
```

---

## Lưu ý

- Model embedding (`AITeamVN/Vietnamese_Embedding`) và reranker (`BAAI/bge-reranker-v2-m3`) sẽ được tải tự động từ HuggingFace lần đầu chạy (~1-2 GB).
- Nếu dùng GPU, đảm bảo đã cài CUDA đúng phiên bản trước khi cài PyTorch.
- `DEEPSEEK_API_KEY` và `OPENAI_API_KEY` chỉ cần thiết nếu muốn sinh dữ liệu fine-tuning, không cần để chạy chatbot.
