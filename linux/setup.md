# Cài đặt môi trường Linux

Hướng dẫn cài đặt từ đầu trên Ubuntu 22.04 / 24.04.  
Sau khi xong file này, tiếp tục đọc [`no-crawler.md`](no-crawler.md) để chạy app mà không cần crawler.

---

## 1. System dependencies

```bash
sudo apt update && sudo apt install -y \
    git curl build-essential \
    python3 python3-venv python3-pip \
    libssl-dev libffi-dev \
    libmecab-dev mecab mecab-ipadic-utf8
```

> `mecab` là dependency của `underthesea` (NLP tiếng Việt). Thiếu cái này `pip install` sẽ lỗi.

---

## 2. Clone repo

```bash
git clone <repo-url>
cd AcneLLM
```

---

## 3. Tạo môi trường Python

```bash
python3 -m venv .venv-linux
source .venv-linux/bin/activate
pip install --upgrade pip

```

> Mỗi lần mở terminal mới phải chạy lại `source .venv-linux/bin/activate`.

---

## 4. Cài PyTorch

Cài torch **trước** các package khác để tránh conflict version.

### Không có GPU (CPU only) — phổ biến nhất:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### Có GPU NVIDIA — CUDA 12.1:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### Có GPU NVIDIA — CUDA 11.8:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

Kiểm tra:
```bash
python -c "import torch; print('torch:', torch.__version__, '| cuda:', torch.cuda.is_available())"
```

---

## 5. Cài dependencies còn lại

```bash
pip install -r requirements.txt
pip install -e .
```

Quá trình này mất **10–20 phút** lần đầu (chủ yếu do `sentence-transformers`, `transformers`, `chromadb`).

---

## 6. Cài Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Kiểm tra:
```bash
ollama --version
```

Khởi động Ollama service (chạy nền):
```bash
ollama serve &
```

Hoặc dùng systemd (nếu cài qua script trên tự đăng ký):
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

Kéo model:
```bash
# Model chính (7B — cần ~5 GB RAM):
ollama pull qwen2.5:7b

# Model fallback (nhẹ hơn, máy yếu dùng cái này):
ollama pull qwen2.5:3b
```

Kiểm tra Ollama đang chạy:
```bash
curl http://localhost:11434/api/tags
```

---

## 7. Cài Node.js (cho frontend)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version   # phải >= 18
npm --version
```

---

## 8. Kiểm tra tổng thể

```bash
source .venv-linux/bin/activate
python -c "import torch, chromadb, sentence_transformers, underthesea, fastapi; print('OK')"
curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print('Ollama models:', [m['name'] for m in d.get('models',[])])"
node --version
```

Nếu tất cả in ra không lỗi → môi trường sẵn sàng.

---

## Tiếp theo

Đọc [`no-crawler.md`](no-crawler.md) để copy Knowledge Base từ máy Windows sang và chạy app.
