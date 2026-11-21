# AcneLLM

AcneLLM là chatbot tư vấn mụn trứng cá bằng tiếng Việt, chạy local-first với
FastAPI, Next.js, Ollama và RAG hybrid. Runtime dùng hai model có trách nhiệm
tách biệt:

- `acne-intaker`: một lần suy luận để phân loại intent và trích xuất dữ kiện có
  cấu trúc;
- `acne-generator-v2`: sinh câu trả lời dạng streaming.

Đường chạy chính:

```text
GET /api/v1/chat/stream
  -> preprocess + SQLite history + input safety
  -> Unified Intaker (một LLM call dùng chung cho route và extraction)
       nếu lỗi: Semantic Router (embedding local, không LLM)
       nếu tiếp tục lỗi: rule router + rule extractor (không LLM)
  -> chọn mode/template và truy hồi khi cần
  -> Chroma + BM25 -> RRF -> cross-encoder rerank -> lọc context
  -> acne-generator-v2 stream token
  -> output safety suffix/normalization
  -> lưu session SQLite + trả SSE
```

Không còn `INTAKE_MODE`, router model hay extractor model riêng trong runtime.
`model/legacy/` chỉ là archive nghiên cứu, không được nạp khi startup.

Tài liệu kỹ thuật đầy đủ và ranh giới bằng chứng eval nằm tại
[docs/reports/context.md](docs/reports/context.md).

## Cấu trúc repository

```text
src/acne_llm/          code production
  api/                 FastAPI app, routes, middleware
  chat/                intake, routing, session view/fold, orchestration, SSE
  db/                  SQLite session store, audit và feedback
  guardrails/          kiểm tra input có cấu trúc và policy thuốc
  llm/                 Ollama client và prompt builder
  rag/                 Chroma, BM25, hybrid retrieval và reranker

frontend/              giao diện Next.js dùng SSE
config/                prompt Jinja, guardrails và cấu hình dữ liệu thuốc
scripts/               chạy app, build KB, crawl và đóng gói
research/              datagen, evaluation, dashboard và tài liệu nghiên cứu
  evaluation/          harness eval hiện hành (import là `evaluation.*`)
data/                  KB/index/SQLite/cache sinh ra cục bộ
data_samples/          lát cắt mẫu dữ liệu sạch (KB, Intaker, Generator, Eval)
model/                 Modelfile và model artifact
tests/                 unit/integration tests; LLM và retriever được mock
docs/                  tài liệu vận hành, cấu hình và báo cáo
```

`pyproject.toml` đặt `pythonpath = ["src", "research"]`, vì vậy module eval được
chạy bằng `python -m evaluation...` dù source nằm trong `research/evaluation/`.
Các nội dung trong `model/legacy/` chỉ là archive nghiên cứu, không phải mô tả
runtime hiện hành.

## Yêu cầu

- Git và Git LFS
- Python 3.10+
- Ollama
- Node.js 18+ nếu chạy frontend ngoài Docker
- RAM tối thiểu 8 GB, khuyến nghị 16 GB

## Clone và cài backend

```powershell
git clone https://github.com/phkgn/AcneLLM.git
cd AcneLLM
git lfs install
git lfs pull

py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# Chọn một bản torch phù hợp CPU/CUDA trước khi cài dependencies.
pip install "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install -e .
```

`requirements.txt` phục vụ runtime. Crawler, datagen, evaluation và test cần
thêm `requirements-dev.txt`.

## Cấu hình

```powershell
Copy-Item .env.baseline .env
```

`.env` chỉ nên chứa secret và giá trị phụ thuộc máy. Default/tuning canonical
nằm tại `src/acne_llm/config.py`.

```env
OLLAMA_URL=http://localhost:11434
LLM_MODEL=acne-generator-v2
INTAKE_MODEL=acne-intaker
INTAKE_TIMEOUT=120
DEVICE=cpu

# Bảo vệ /api/v1/admin/* và /api/v1/debug/trace; để trống sẽ fail closed.
ADMIN_API_KEY=<secret đủ mạnh>
CORS_ORIGINS=["http://localhost:3000"]

# Chỉ cần khi chạy evaluation có LLM judge.
JUDGE_PROVIDER=deepseek
JUDGE_MODEL=deepseek-v4-pro
```

Không commit `.env`. Danh sách knob hiện hành xem
[docs/config_reference.md](docs/config_reference.md).

`API_KEY` toàn cục mặc định để trống vì browser `EventSource` không gửi custom
header. Endpoint admin/debug vẫn được bảo vệ riêng bằng `ADMIN_API_KEY`.

## Chuẩn bị model Ollama

```powershell
ollama serve
```

Ở terminal khác:

```powershell
Set-Location model\generator
ollama create acne-generator-v2 -f Modelfile

Set-Location ..\intaker
ollama create acne-intaker -f Modelfile
```

`ollama list` phải có cả `acne-generator-v2` và `acne-intaker`. GGUF lớn và một
số artifact KB không có đầy đủ trong clone Git thông thường; xem
[docs/DOCKER_QUICKSTART.md](docs/DOCKER_QUICKSTART.md) và
[docs/RELEASE_ARTIFACTS.md](docs/RELEASE_ARTIFACTS.md).

## Chạy hệ thống

### Windows

```powershell
.\scripts\RUN.ps1
```

Script kiểm tra Ollama/model, chạy backend và frontend rồi mở trình duyệt. Có thể
dùng `scripts/runpod.ps1` để tunnel Ollama từ RunPod.

### Thủ công

```powershell
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

```powershell
Set-Location frontend
npm install
npm run dev
```

- UI: <http://localhost:3000>
- OpenAPI: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>

### Docker Compose

Compose dựng Nginx gateway, Next.js, FastAPI, Ollama và bước khởi tạo hai model.

```powershell
Copy-Item .env.docker.example .env.docker
.\scripts\check_docker_assets.ps1

# NVIDIA GPU
docker compose --env-file .env.docker `
  -f docker-compose.yml `
  -f docker-compose.gpu.yml `
  up -d --build

# CPU: docker compose --env-file .env.docker up -d --build
```

Hướng dẫn artifact, bundle, GPU/CPU/LAN và troubleshooting:
[docs/DOCKER_QUICKSTART.md](docs/DOCKER_QUICKSTART.md).

## Knowledge Base và RAG

Pipeline build có ba bước có thể chạy lại độc lập:

```text
data/raw/documents.jsonl
  -> chunk -> data/raw/chunks.jsonl
  -> embed -> data/chroma_db/
  -> bm25  -> data/bm25_index.pkl
```

```powershell
python scripts/build_kb.py --step chunk
python scripts/build_kb.py --step embed
python scripts/build_kb.py --step bm25
# hoặc chạy cả ba:
python scripts/build_kb.py
```

App chỉ bật hybrid RAG khi có cả ChromaDB và BM25 index. Thiếu một trong hai,
backend vẫn có thể chạy ở nhánh không dùng KB và ghi rõ trạng thái readiness.

## API

| Method | Endpoint | Vai trò |
|---|---|---|
| `GET` | `/api/v1/chat/stream` | chat streaming SSE |
| `POST` | `/api/v1/chat/feedback` | lưu phản hồi người dùng |
| `GET` | `/api/v1/health` | health/readiness của Ollama và KB |
| `GET` | `/api/v1/models` | model Ollama hiện có |
| `POST` | `/api/v1/kb/retrieve`, `/api/v1/kb/search` | truy vấn KB trực tiếp |
| `GET` | `/api/v1/kb/stats`, `/api/v1/kb/chunk/{id}` | thống kê/xem chunk |
| `GET` | `/api/v1/debug/trace` | trace đến trước generator, cần admin key |
| `GET` | `/api/v1/admin/*` | audit/session/feedback, cần admin key |
| `GET` | `/metrics` | Prometheus metrics |

Không có WebSocket; frontend dùng SSE.

## Test

> Trên Windows dùng `py -3.10 -m pytest` (hoặc Python trong virtualenv đang kích hoạt `.venv`).

```powershell
python -m pytest -q
```

Các test pipeline trọng tâm:

```powershell
python -m pytest `
  tests/test_intake.py `
  tests/test_chat_stream.py `
  tests/test_intent_routing.py `
  tests/test_session.py `
  tests/chat -q
```

Không dùng số lượng test cố định trong README vì suite thay đổi theo code; kết
quả xác nhận cho commit phải lấy từ lần chạy pytest tương ứng.

## Evaluation

Harness hiện hành ở `research/evaluation/` và được chạy như module
`evaluation`. Ba lane chính là intake, retrieval và ablation:

```powershell
python -m evaluation.full_evaluation --smoke
python -m evaluation.full_evaluation
```

Eval thật cần Ollama, KB và API key cho judge. Không được coi một run chỉ hoàn
thành ablation là bằng chứng rằng intake, retrieval hay SSE production đã được
đánh giá lại. Xem [research/evaluation/README.md](research/evaluation/README.md)
và phần “Evaluation” trong [context hiện hành](docs/reports/context.md).

## Dữ liệu mẫu và Bằng chứng tái lập

- **Mẫu dữ liệu sạch xem trực tiếp trên GitHub:** xem [data_samples/README.md](data_samples/README.md)
  cùng 4 lát cắt phân tầng (`kb_chunks_sample.jsonl`, `intaker_train_sample.jsonl`,
  `generator_role_sample.jsonl`, `eval_calibration_rrr_sample.jsonl`) và mã băm
  `data_samples/SHA256SUMS.txt`. Để tái tạo cục bộ khi đã có dữ liệu gốc, chạy
  `py -3.10 scripts/export_data_samples.py`.
- **Kết quả đánh giá & hiệu chuẩn người chấm:** báo cáo chuẩn tại
  [research/evaluation/reports/v2_full/](research/evaluation/reports/v2_full/)
  (Intake 1.490 mẫu, Retrieval 120 case, Ablation 145 × 6 arm) và đối chiếu người
  chấm tay 145 hàng arm `RRR` tại
  [research/evaluation/reports/calibration_rrr/](research/evaluation/reports/calibration_rrr/).
- **Artifact nặng & khôi phục môi trường:** GGUF, LoRA adapter, snapshot KB
  (`24.393` chunks) và kho tri thức kiểm toán kèm SHA-256 được phát hành qua 3
  GitHub Releases (`models-v2-2026-08-23`, `kb-v2-2026-08-23`,
  `knowledge-2026-08-23`); xem hướng dẫn chi tiết tại
  [docs/RELEASE_ARTIFACTS.md](docs/RELEASE_ARTIFACTS.md).

## Lệnh tiện ích

Trên bash/WSL dùng `./tasks.sh help`; trên Windows ưu tiên các script `.ps1`.

| Việc | Lệnh |
|---|---|
| Chạy app | `./tasks.sh run-all` hoặc `scripts/RUN.ps1` |
| Build KB | `./tasks.sh build-kb` hoặc `scripts/KB.ps1` |
| Test | `./tasks.sh test` hoặc `python -m pytest` |
| Eval | `./tasks.sh eval` hoặc `python -m evaluation.full_evaluation` |
| Docker | `./tasks.sh docker-up`, `docker-logs`, `docker-down` |

## Ranh giới an toàn và dữ liệu

- Medication guardrail xử lý chống chỉ định/tương tác từ dữ kiện có cấu trúc;
  nó không phải toàn bộ hệ thống safety.
- Route flags chỉ điều khiển prompt/output; chúng không phải cổng từ chối.
- `_safety.py` chuẩn hóa hậu tố/cảnh báo cuối output.
- Semantic/rule routing là fallback khả dụng, không phải safety authority.
- Session production dùng `SQLiteSessionStore`; in-memory store chỉ nằm trong
  test helper.

Không commit `.env`, `data/sessions.db*`, `data/audit.db*`, cache, GGUF hoặc dữ
liệu lớn chưa được quản lý bằng Git LFS.
