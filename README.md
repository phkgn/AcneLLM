# AcneLLM

Chatbot tư vấn mụn trứng cá bằng tiếng Việt. Backend dùng FastAPI, LLM chạy local qua
Ollama, có thể bật RAG hybrid bằng ChromaDB + BM25.

## Chạy trọn bộ bằng Docker — khuyến nghị để bàn giao

Gói Compose hiện chạy gateway Nginx, Next.js, FastAPI, Ollama, hai model
`acne-generator` + `acne-intaker`, ChromaDB và BM25. Backend/Ollama chỉ nằm trong
Docker network; browser dùng một địa chỉ duy nhất `http://localhost:3000`.

```powershell
Copy-Item .env.docker.example .env.docker
.\scripts\check_docker_assets.ps1

# NVIDIA GPU
docker compose --env-file .env.docker `
  -f docker-compose.yml `
  -f docker-compose.gpu.yml `
  up -d --build

# CPU (chạy được nhưng LLM rất chậm)
# docker compose --env-file .env.docker up -d --build
```

Hai GGUF và nguyên Chroma vector segment không nằm đầy đủ trong một clone Git
thông thường. Xem danh sách artifact, cách tạo bundle để gửi người khác, hướng dẫn
GPU/CPU/LAN và troubleshooting tại [docs/DOCKER_QUICKSTART.md](docs/DOCKER_QUICKSTART.md).

## Yêu Cầu

- Git + Git LFS
- Python 3.10+
- Ollama
- Node.js 18+ nếu muốn chạy frontend
- RAM tối thiểu 8 GB, khuyến nghị 16 GB

## Clone / Pull Repo

Nếu clone lần đầu:

```powershell
git clone https://github.com/phkgn/AcneLLM.git
cd AcneLLM
git lfs install
git lfs pull
```

Nếu đã có repo local:

```powershell
git pull
git lfs pull
```

`git lfs pull` là bắt buộc để tải `data/chroma_db/` vì ChromaDB đang được lưu bằng
Git LFS.

## Cài Backend

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# Chọn một bản Torch phù hợp máy bạn.
# CPU:
pip install "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu

# Sau đó cài app:
pip install -r requirements.txt
pip install -e .
```

Linux/macOS:

```bash
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install --upgrade pip
pip install "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install -e .
```

Nếu dùng CUDA, thay dòng cài Torch CPU bằng wheel CUDA phù hợp từ trang PyTorch.

## Cấu Hình `.env`

Tạo file `.env` từ mẫu:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

`.env` chỉ giữ secret và giá trị thay đổi theo máy/lần chạy. Các biến tối thiểu
nên kiểm tra:

```env
OLLAMA_URL=http://localhost:11434
LLM_MODEL=acnellm-role
INTAKE_MODE=unified
INTAKE_MODEL=acne-intake
DEVICE=cpu
JUDGE_PROVIDER=openai
JUDGE_MODEL=gpt-5.4-mini
```

Không commit `.env`. Các path, retrieval knob và timeout dùng default duy nhất tại
`src/acne_llm/config.py`; xem `docs/config_layout.md` và
`docs/config_reference.md`. API key judge/datagen không cần để chạy chatbot local.

## Chuẩn Bị Ollama Model

Mở một terminal riêng:

```powershell
ollama serve
```

Terminal khác:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
```

Nếu bạn có file GGUF local và muốn dùng model custom `acnellm-v2-q4`, đặt GGUF cạnh
`model/V2/Q4/Modelfile`, rồi chạy:

```powershell
cd model\V2\Q4
ollama create acnellm-v2-q4 -f Modelfile
```

Sau đó đổi trong `.env`:

```env
LLM_MODEL=acnellm-v2-q4
```

Lưu ý: file GGUF lớn không nằm trong Git repo.

## Chạy Backend

```powershell
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Mở:

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health

Test nhanh:

```powershell
curl "http://localhost:8000/api/v1/chat/stream?message=toi%20bi%20mun%20o%20cam&mode=auto"
```

## Chạy Frontend

```powershell
cd frontend
npm install
npm run dev
```

Mở http://localhost:3000.

Nếu backend không chạy ở `http://localhost:8000`, tạo `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Chạy Nhanh Trên Windows

Sau khi đã cài Python deps, frontend deps và Ollama model:

```powershell
.\scripts\RUN.ps1
```

Script này mở Ollama, backend và frontend ở các cửa sổ PowerShell riêng.

## RAG / Knowledge Base

Repo hiện đã push `data/chroma_db/` qua Git LFS. Tuy nhiên app chỉ bật RAG khi có đủ:

- `data/chroma_db/`
- `data/bm25_index.pkl`

Nếu thiếu `data/bm25_index.pkl`, backend vẫn chạy nhưng sẽ log:

```text
KB not ready (...) -- only llm_only mode available
```

Muốn bật RAG đầy đủ, cần có raw chunks/documents để build BM25:

```powershell
python scripts/build_kb.py --step bm25
```

Hoặc rebuild toàn bộ KB từ raw data:

```powershell
python scripts/build_kb.py
```

Lưu ý: `data/raw/`, `data/finetune/`, `data/cache/`, `data/sessions/`, model GGUF và
audit DB không được push mặc định vì lớn hoặc có thể chứa dữ liệu runtime.

## API Chính

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/v1/chat/stream` | Chat streaming SSE |
| `POST` | `/api/v1/chat/feedback` | Gửi feedback |
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/docs` | OpenAPI UI |
| `GET` | `/metrics` | Prometheus metrics |

## Test

Các test liên quan chat pipeline:

```powershell
pytest tests/test_normalizer_regression.py tests/test_chat_normalizer.py tests/test_intent_router.py tests/test_intent_router_new.py tests/test_intake.py tests/test_chat_stream.py tests/test_stream_safety.py -q
```

Chạy toàn bộ suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Cấu Trúc Chính

```text
src/acne_llm/
  api/          FastAPI routes/app
  chat/         Intake, session, streaming runtime
  rag/          Chroma, BM25, retrieval, reranker
  llm/          Ollama backend, prompt builder, planner
  guardrails/   Scope/OOD/drug safety
  pipeline/     Hybrid and LLM-only pipelines

config/prompts/ Prompt templates
data/chroma_db/ ChromaDB vector index via Git LFS
frontend/       Next.js UI
scripts/        Build/eval/run utilities
```

## Lưu Ý Khi Commit

Không commit:

- `.env`
- `data/sessions/`
- `data/audit.db*`
- `data/cache/`
- model `.gguf`
- raw/finetune data lớn nếu chưa đưa vào LFS hoặc nơi lưu artifact riêng

Các file lớn cần push lên GitHub thì phải dùng Git LFS.
