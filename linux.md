# AcneLLM on Linux

Tài liệu này là đường chạy ngắn gọn để deploy và phát triển AcneLLM trên Linux.

## Yêu cầu

- Python 3.10+
- `pip` và `venv`
- Ollama đã cài và đang chạy
- Internet để tải dependency và model

## Cài đặt

```bash
sudo apt update
sudo apt install -y git curl python3 python3-venv python3-pip

git clone <repo-url>
cd AcneLLM

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

cp .env.example .env
```

## Ollama

Nếu chưa có Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Sau đó mở Ollama service:

```bash
ollama serve
```

Trong một terminal khác, kéo model:

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
```

## Chạy ứng dụng

### Crawl dữ liệu

```bash
python -m scripts.crawl_all
```

Crawl riêng PubMed:

```bash
python -m scripts.crawl_all --source PubMed
```

### Build knowledge base

```bash
python -m scripts.build_kb
```

### Chạy API

```bash
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Mở:

- `http://localhost:8000`
- `http://localhost:8000/docs`

### Chạy frontend chat UI

Frontend mới chạy riêng bằng Next.js, giống flow AnimeChatBot:

```bash
./tasks.sh frontend-install
./tasks.sh frontend
```

Mở:

- `http://localhost:3000`

Nếu muốn mở 3 terminal theo kiểu AnimeChatBot:

```bash
./tasks.sh run-all
```

### Eval

```bash
python -m scripts.run_eval --n 20
python -m scripts.run_eval --n 50
```

### Test

```bash
pytest -v
```

## Cài thêm cho phần crawl JS

Nếu bạn dùng `playwright` để crawl các trang render bằng JavaScript:

```bash
playwright install chromium
```

## Lan mode trên Linux

`tasks.ps1 serve-lan` là script PowerShell dành cho Windows, nên trên Linux dùng lệnh này để lấy IP LAN:

```bash
hostname -I | awk '{print $1}'
```

Rồi chạy API:

```bash
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Ví dụ truy cập từ máy khác trong cùng mạng:

```text
http://<IP-LAN>:8000
```

## Lệnh tương đương với `tasks.ps1`

| Windows | Linux |
|---|---|
| `.\tasks.ps1 install` | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e .` |
| `.\tasks.ps1 pull-models` | `ollama pull qwen2.5:7b && ollama pull qwen2.5:3b` |
| `.\tasks.ps1 crawl` | `python -m scripts.crawl_all` |
| `.\tasks.ps1 crawl-pubmed` | `python -m scripts.crawl_all --source PubMed` |
| `.\tasks.ps1 build-kb` | `python -m scripts.build_kb` |
| `.\tasks.ps1 serve` | `uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload` |
| `.\scripts\RUN.ps1` | `./tasks.sh run-all` |
| `.\tasks.ps1 eval 50` | `python -m scripts.run_eval --n 50` |
| `.\tasks.ps1 test` | `pytest -v` |

## Ghi chú

- `tasks.ps1` chỉ dành cho Windows PowerShell, không chạy trực tiếp trên Linux.
- Nếu chạy trong Docker, file `docker-compose.yml` đã có sẵn cả API và Ollama.
- Nếu cần nhẹ máy, đổi `LLM_MODEL` trong `.env` sang model nhỏ hơn.
