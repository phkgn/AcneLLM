# Chạy toàn bộ AcneLLM bằng Docker Compose

Gói Docker chạy bốn lớp:

```text
browser :3000
    -> nginx gateway
       -> Next.js frontend :3000 (nội bộ)
       -> FastAPI backend  :8000 (nội bộ)
          -> Ollama        :11434 (nội bộ)
             - acne-generator (Qwen2.5 7B Q4)
             - acne-intaker   (Qwen2.5 3B Q4)
```

Chỉ gateway được publish ra máy host. Backend và Ollama không mở port trực tiếp.
Gateway tắt buffering cho `/api/`, nên SSE vẫn stream token theo thời gian thực.

## 1. Yêu cầu máy

### GPU NVIDIA — khuyến nghị

- Docker Desktop (Windows/macOS) hoặc Docker Engine + Compose v2 (Linux).
- Windows: bật WSL2 backend trong Docker Desktop.
- Linux GPU: cài NVIDIA driver và NVIDIA Container Toolkit.
- VRAM tối thiểu thực dụng 16 GB, khuyến nghị 24 GB.
- RAM 24–32 GB, trống ít nhất 25 GB ổ đĩa.

### CPU — chỉ để thử

Compose mặc định không yêu cầu GPU nên vẫn khởi động trên CPU, nhưng hai model
7B/3B sẽ trả lời rất chậm. Nên có ít nhất 24 GB RAM.

## 2. Artifact bắt buộc

Các file model bị `.gitignore`; clone Git đơn thuần không có chúng. Trước khi gửi
project hoặc chạy trên máy mới, phải có:

```text
model/V2/Q4/Modelfile
model/V2/Q4/Qwen2.5-7B-Instruct.Q4_K_M.gguf
model/acne_intake_release/Modelfile
model/acne_intake_release/Qwen2.5-3B-Instruct.Q4_K_M.gguf
```

RAG cần nguyên thư mục, không chỉ riêng file SQLite:

```text
data/chroma_db/chroma.sqlite3
data/chroma_db/<uuid-segment>/...       # bắt buộc
data/bm25_index.pkl
data/intent_classify.train.jsonl
data/intent_router_index.npz
```

`scripts/check_docker_assets.ps1` sẽ chặn sớm nếu GGUF chỉ là Git LFS pointer,
Chroma thiếu vector segment, Docker chưa được cài hoặc Compose không hợp lệ.

## 3. Tạo cấu hình

Windows PowerShell:

```powershell
Copy-Item .env.docker.example .env.docker
notepad .env.docker
```

Linux/macOS:

```bash
cp .env.docker.example .env.docker
```

Đổi `API_KEY` thành chuỗi dài ngẫu nhiên. Ví dụ PowerShell:

```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
```

Trên Linux, nếu tài khoản không có UID/GID `1000`, cập nhật:

```bash
sed -i "s/HOST_UID=1000/HOST_UID=$(id -u)/" .env.docker
sed -i "s/HOST_GID=1000/HOST_GID=$(id -g)/" .env.docker
```

Không gửi `.env` gốc vì có thể chứa API key judge/datagen. Bundle Docker chỉ cần
`.env.docker`.

## 4. Preflight

Windows:

```powershell
.\scripts\check_docker_assets.ps1
```

Linux/macOS có thể kiểm Compose trực tiếp:

```bash
docker compose --env-file .env.docker config --quiet
```

## 5. Khởi động

### NVIDIA GPU

```powershell
docker compose --env-file .env.docker `
  -f docker-compose.yml `
  -f docker-compose.gpu.yml `
  up -d --build
```

Linux/macOS dùng dấu `\` thay cho backtick PowerShell:

```bash
docker compose --env-file .env.docker \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d --build
```

### CPU

```powershell
docker compose --env-file .env.docker up -d --build
```

Lần đầu sẽ lâu vì Docker build Python/Node dependencies, Ollama import khoảng
6.6 GB GGUF và backend tải embedding/reranker về `data/model_cache/`. Những lần
sau dùng lại cache và named volume `ollama_data`.

Theo dõi:

```powershell
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f ollama-init
docker compose --env-file .env.docker logs -f acne-llm
```

## 6. Kiểm tra

Mở:

- UI: <http://localhost:3000>
- API docs qua gateway: <http://localhost:3000/docs>
- Health: <http://localhost:3000/api/v1/health>

PowerShell:

```powershell
Invoke-RestMethod http://localhost:3000/api/v1/health
```

Kết quả đạt phải có:

```json
{
  "status": "ok",
  "ollama": true,
  "model": "acne-generator",
  "bm25_loaded": true
}
```

`kb_chunks` phải lớn hơn 0. Nếu `status=degraded`, `bm25_loaded=false` hoặc
`kb_chunks=-1`, chưa được coi là khởi động thành công.

## 7. Dừng và cập nhật

Dừng nhưng giữ model/cache/database:

```powershell
docker compose --env-file .env.docker down
```

Build lại sau khi sửa code:

```powershell
docker compose --env-file .env.docker up -d --build
```

Không dùng `down -v` trừ khi muốn xóa Ollama volume và import lại toàn bộ model.

## 8. Tạo thư mục để gửi người khác

Script sau tạo bundle ở thư mục cùng cấp với repo, bỏ `.git`, virtualenv,
`node_modules`, eval reports và model thừa; đồng thời copy đúng hai GGUF cùng
Chroma/BM25 cần cho runtime:

```powershell
.\scripts\prepare_docker_bundle.ps1
```

Output mặc định:

```text
E:\project\AcneLLM-docker-bundle
```

Trong bundle, thay `API_KEY` ở `.env.docker`, chạy preflight rồi chạy Compose.
Thư mục vẫn lớn khoảng 7–9 GB; nên dùng 7-Zip hoặc ổ đĩa/cloud hỗ trợ file lớn.

## 9. Truy cập từ máy khác trong LAN

Mở firewall cho TCP port `APP_PORT` (mặc định 3000), rồi truy cập:

```text
http://<IPv4-của-máy-chạy-Docker>:3000
```

Không cần đổi `NEXT_PUBLIC_API_URL`: browser gọi API cùng origin qua gateway.

## 10. Giới hạn bảo mật

`API_KEY` trong gói này bảo vệ hop gateway → backend; nó không phải màn hình đăng
nhập cho người dùng. Nếu đưa ra Internet, cần thêm HTTPS và authentication ở
gateway/VPN/identity proxy. Không publish trực tiếp port 8000 hoặc 11434.

## 11. Lỗi thường gặp

### `ollama-init` báo thiếu model

Copy đúng hai GGUF/Modelfile ở mục 2. Không fallback sang model public vì như vậy
không còn là cùng AcneLLM runtime.

### Chroma có SQLite nhưng `kb_chunks` lỗi

Bạn chỉ copy `chroma.sqlite3` mà thiếu thư mục UUID chứa HNSW segment. Copy nguyên
`data/chroma_db/` từ máy nguồn.

### Linux báo permission denied trong `data/`

Đặt `HOST_UID=$(id -u)` và `HOST_GID=$(id -g)` trong `.env.docker`, sau đó tạo lại
container:

```bash
docker compose --env-file .env.docker up -d --force-recreate acne-llm
```

### GPU không được nhận

Kiểm tra trước:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Sau đó chạy lại với cả `docker-compose.yml` và `docker-compose.gpu.yml`.

### Backend khởi động lâu

Lần đầu sentence-transformers tải embedding/reranker và load Chroma. Xem log
`acne-llm`; healthcheck dành nhiều phút cho lần tải/khởi tạo đầu tiên trước khi
đánh dấu unhealthy.
