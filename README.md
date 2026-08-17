# AcneLLM

Chatbot tư vấn mụn trứng cá bằng tiếng Việt. Backend FastAPI, hai model chạy local
qua Ollama, RAG hybrid bằng ChromaDB + BM25 + cross-encoder rerank.

Một request đi qua bốn chặng:

```
/chat/stream → intake (guardrails tất định + intaker LLM đọc ý định & trích xuất)
             → retrieval (Chroma + BM25 → RRF → rerank → 5 đoạn)
             → generator LLM (stream từng token)
             → _safety (nối cảnh báo) → SSE
```

Hai model: `acne-intaker` đọc hiểu đầu vào và trả JSON, `acne-generator` viết câu
trả lời. Cả hai đều fine-tune và nạp bằng Modelfile trong `model/`.

## Cấu trúc thư mục

Ranh giới quan trọng nhất: **`src/` là thứ duy nhất Docker copy vào image.** Mọi
thư mục khác là công cụ ngoại tuyến hoặc dữ liệu.

```
src/acne_llm/     code chạy production
  api/            FastAPI routes, middleware, DI container
  chat/           intake, session, orchestrator, runtime SSE, safety suffix
    routing/      3 tầng chọn intent: unified → semantic → rule.
                  KHÔNG phải "fallback" — compute_route_flags chạy mọi request.
  rag/            Chroma, BM25, hybrid retriever, cross-encoder reranker
  llm/            Ollama backend, prompt builder
  guardrails/     cổng tất định DUY NHẤT còn lại: chống chỉ định / tương tác thuốc.
                  Đọc trường có cấu trúc (is_pregnant, age, sex, medications),
                  không khớp chuỗi. Phạm vi & jailbreak nằm ở system prompt.
  db/             SQLite session store + audit log
  crawler/        NGOẠI TUYẾN — không nằm trên đường chạy request nào
config/           prompt .j2, guardrails.yaml, drugs_acne.yaml
frontend/         Next.js, nói chuyện với backend bằng SSE
tests/            502 test, chạy ~7 giây
scripts/          build_kb, crawl, convert dataset, RUN.ps1
data/  model/     artifact sinh ra — chroma, bm25, sqlite, GGUF
research/         NGOẠI TUYẾN — không thứ gì trong đây phục vụ một request
  evaluation/       chấm điểm hệ thống
  datagen/          sinh dữ liệu fine-tune (import lẫn nhau với evaluation)
  LLMData/          dataset thô
  guideline_docs/   PDF guideline gốc
  dashboards/       dashboard HTML + sơ đồ kiến trúc (trước là visualization/)
  dataset_viz/      biểu đồ phân bố dataset (trước là visualize/)
  notebooks/        notebook thăm dò
docs/             tài liệu — đọc docs/README.md trước để biết cái nào có hiệu lực
  docs/archive/     prompt & plan đã xong việc, giữ để truy vết
  docs/reports/     báo cáo dài: context.md, report.md, audit
```

Root có đúng 10 thư mục. Các package trong `research/` import nhau bằng tên
tuyệt đối (`from datagen.x import y`) nên đường dẫn file không khớp tên module —
cố ý, đổi lại thì phải sửa ~40 dòng import. `pyproject.toml` đã có
`pythonpath = ["src", "research"]`; `tasks.sh` tự export `PYTHONPATH`. Chạy tay
thì cần `PYTHONPATH=src:research`.

### Chạy cái gì bằng lệnh nào

`tasks.sh` là cửa chính trên bash/WSL; các `.ps1` là cửa tương đương trên
Windows thuần. Chúng không phải bản sao thừa của nhau — chọn theo shell bạn dùng.

| Việc | bash / WSL | Windows |
|---|---|---|
| Chạy cả hệ thống | `./tasks.sh run-all` | `scripts/RUN.ps1` |
| Build knowledge base | `./tasks.sh build-kb` | `scripts/KB.ps1` |
| Test | `./tasks.sh test` | `pytest` |
| Sinh dữ liệu fine-tune | `python -m datagen.main` | `datagen/RUN.bat` |
| Biểu đồ dataset | `./tasks.sh visualize` | — |
| Eval đầy đủ | `./tasks.sh eval` | `evaluation/e2e.ps1` |
| Tunnel tới Ollama trên RunPod | — | `scripts/runpod.ps1` |
| Đóng gói bàn giao Docker | — | `scripts/prepare_docker_bundle.ps1` |

`./tasks.sh help` liệt kê đủ 26 lệnh con.

## Chạy trọn bộ bằng Docker — khuyến nghị để bàn giao

Gói Compose chạy gateway Nginx, Next.js, FastAPI, Ollama, hai model, ChromaDB và
BM25. Backend/Ollama chỉ nằm trong Docker network; browser dùng một địa chỉ duy
nhất `http://localhost:3000`.

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

## Yêu cầu

- Git + Git LFS
- Python 3.10+
- Ollama
- Node.js 18+ nếu muốn chạy frontend
- RAM tối thiểu 8 GB, khuyến nghị 16 GB

## Clone / pull repo

```powershell
git clone https://github.com/phkgn/AcneLLM.git
cd AcneLLM
git lfs install
git lfs pull
```

Nếu đã có repo local: `git pull && git lfs pull`.

`git lfs pull` là bắt buộc để tải `data/chroma_db/`.

## Cài backend

Torch phải cài **trước và riêng**, vì chọn CPU hay CUDA là quyết định của máy bạn
chứ không phải của file requirements.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# CPU:
pip install "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu
# CUDA: lấy wheel tương ứng ở trang PyTorch

pip install -r requirements.txt
pip install -e .
```

Linux/macOS giống hệt, đổi `py -3.10 -m venv .venv` thành
`python3 -m venv .venv-linux` và activate bằng `source`.

**Hai file requirements:**

- `requirements.txt` — chỉ thứ một request cần. Danh sách này được dò bằng AST
  trên `src/acne_llm/` trừ `crawler/`, nên đừng thêm gói "cho chắc".
- `requirements-dev.txt` — crawler, datagen, evaluation, biểu đồ, pytest.
  Cài thêm khi cần: `pip install -r requirements-dev.txt`

Docker chỉ cài file đầu.

## Cấu hình `.env`

```powershell
Copy-Item .env.baseline .env
```

`.env` chỉ giữ secret và giá trị đổi theo máy. Mọi hằng số tuning có default duy
nhất tại `src/acne_llm/config.py` — đừng chép chúng vào `.env`.

```env
OLLAMA_URL=http://localhost:11434
LLM_MODEL=acne-generator
INTAKE_MODE=unified
INTAKE_MODEL=acne-intaker
DEVICE=cpu

# Khoá cho /api/v1/admin/* và /debug/trace — hai nhóm endpoint lộ toàn văn
# hội thoại người dùng. ĐỂ TRỐNG = TỪ CHỐI TRUY CẬP (fail closed).
ADMIN_API_KEY=<sinh bằng: python -c "import secrets;print(secrets.token_urlsafe(32))">

# Whitelist cụ thể. Đừng dùng "*".
CORS_ORIGINS=["http://localhost:3000"]

# Judge cho eval — không cần để chạy chatbot
JUDGE_PROVIDER=deepseek
JUDGE_MODEL=deepseek-v4-pro
```

Không commit `.env`. Chi tiết từng knob: [docs/config_reference.md](docs/config_reference.md).

Lưu ý `API_KEY` (khoá toàn cục) cố ý để trống: `EventSource` của trình duyệt không
gửi được header tuỳ chỉnh, nên bật nó lên sẽ làm chết `/chat/stream`. Bảo vệ
endpoint nhạy cảm bằng `ADMIN_API_KEY` thay vì khoá toàn bộ API.

## Chuẩn bị model Ollama

```powershell
ollama serve
```

Terminal khác, tạo hai model từ Modelfile:

```powershell
cd model\generator
ollama create acne-generator -f Modelfile.full

cd ..\intaker
ollama create acne-intaker -f Modelfile
```

Kiểm tra: `ollama list` phải thấy cả `acne-generator` và `acne-intaker`. Thiếu một
trong hai thì `RUN.ps1` dừng ngay với thông báo rõ ràng.

File GGUF lớn không nằm trong Git repo — xem `docs/DOCKER_QUICKSTART.md`.

## Chạy

### Nhanh nhất, Windows

```powershell
.\scripts\RUN.ps1
```

Mở 3 cửa sổ PowerShell: `ollama serve`, backend, frontend — rồi tự mở trình duyệt.
Thêm `-Log` để backend ghi ra file và mở kèm cửa sổ tail log.

Chạy model trên RunPod thay vì máy mình:

```powershell
.\scripts\runpod.ps1          # mở SSH tunnel tới :11434
.\scripts\RUN.ps1             # backend + frontend dùng tunnel đó
.\scripts\runpod.ps1 -Status  # xem tunnel + model trên pod
.\scripts\runpod.ps1 -Stop
```

### Thủ công

```powershell
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

```powershell
cd frontend
npm install
npm run dev
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

Backend không ở `http://localhost:8000` thì tạo `frontend/.env.local` với
`NEXT_PUBLIC_API_URL=...`.

Thử nhanh:

```powershell
curl "http://localhost:8000/api/v1/chat/stream?message=toi%20bi%20mun%20o%20cam"
```

## RAG / Knowledge Base

App chỉ bật RAG khi có đủ **cả hai**:

- `data/chroma_db/`
- `data/bm25_index.pkl`

Thiếu một trong hai thì backend vẫn chạy nhưng log `KB not ready (...) -- only
llm_only mode available` và trả lời không dùng tài liệu.

```powershell
python scripts/build_kb.py --step bm25   # chỉ dựng lại BM25
python scripts/build_kb.py               # rebuild toàn bộ từ raw
```

`data/raw/`, `data/finetune/`, `data/cache/`, GGUF và audit DB không push mặc định.

## API

| Method | Endpoint | Ghi chú |
|---|---|---|
| `GET` | `/api/v1/chat/stream` | Chat streaming SSE — endpoint chính |
| `POST` | `/api/v1/chat/feedback` | Thumbs up/down |
| `GET` | `/api/v1/health` | Health check (Ollama, KB, BM25) |
| `GET` | `/api/v1/models` | Model Ollama đang có |
| `POST` | `/api/v1/kb/retrieve` · `/kb/search` | Truy vấn KB trực tiếp |
| `GET` | `/api/v1/kb/stats` · `/kb/chunk/{id}` | Thống kê / xem một chunk |
| `GET` | `/api/v1/debug/trace` | 🔒 Trace từng stage pipeline, không gọi generator |
| `GET` | `/api/v1/admin/audit` | 🔒 Audit log — **toàn văn hội thoại** |
| `GET` | `/api/v1/admin/sessions/stats` · `/admin/feedback*` | 🔒 |
| `GET` | `/metrics` | Prometheus |
| `GET` | `/docs` | OpenAPI UI |

🔒 = cần header `x-admin-key: <ADMIN_API_KEY>`. Không cấu hình khoá thì trả 403.

Không có endpoint WebSocket. Frontend dùng SSE hoàn toàn.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

507 test, khoảng 10 giây — toàn bộ mock LLM và retriever, không cần Ollama.

Nhóm liên quan pipeline chat:

```powershell
pytest tests/test_intake.py tests/test_chat_stream.py tests/test_chat_normalizer.py `
       tests/test_medication_gates.py tests/test_safety_dose_rule.py `
       tests/test_phase6_bugfixes.py tests/chat/ -q
```

Eval thật (cần Ollama + KB + API key judge) nằm ở `evaluation/`, xem
`evaluation/README.md`.

## Lưu ý khi commit

Không commit `.env`, `data/sessions.db*`, `data/audit.db*`, `data/cache/`,
file `.gguf`, và raw/finetune data lớn chưa đưa vào LFS.

File lớn cần push thì phải qua Git LFS.
