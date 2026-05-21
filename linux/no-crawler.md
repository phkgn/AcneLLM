# Chạy AcneLLM trên Linux — Bỏ qua Crawler

Knowledge Base (8,169 documents, 24,113 chunks, vector index ~340 MB) đã được build sẵn trên Windows.  
Chỉ cần **copy 3 thứ** sang Linux là chạy được ngay, không cần crawl hay build lại.

> Yêu cầu: đã hoàn thành [`setup.md`](setup.md) trước.

---

## Những gì cần copy từ Windows sang Linux

| Nguồn (Windows) | Đích (Linux) | Kích thước | Bắt buộc? |
|-----------------|--------------|------------|-----------|
| `data\raw\documents.jsonl` | `data/raw/documents.jsonl` | ~48 MB | Không bắt buộc (chỉ cần nếu muốn rebuild index sau) |
| `data\raw\chunks.jsonl` | `data/raw/chunks.jsonl` | ~37 MB | **Bắt buộc** (build_kb dùng file này) |
| `data\chroma_db\` | `data/chroma_db/` | ~250 MB | **Bắt buộc** (vector index) |
| `data\bm25_index.pkl` | `data/bm25_index.pkl` | ~50 MB | **Bắt buộc** (sparse index) |

> Tổng cần copy: khoảng **335–385 MB**.  
> Không cần copy `data/raw/documents.jsonl` nếu bạn không có kế hoạch crawl thêm hay rebuild index.

---

## Cách 1: Copy qua mạng LAN (scp)

Trên máy **Linux**, chạy lệnh sau để kéo data từ Windows:

```bash
# Thay <WINDOWS_IP> và <USERNAME> cho phù hợp
WINDOWS_IP=192.168.1.x
WIN_USER=YourWindowsUsername
WIN_PROJECT="C:/Users/$WIN_USER/path/to/AcneLLM"

# Tạo thư mục đích
mkdir -p data/raw data/chroma_db

# Copy chunks (bắt buộc)
scp "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/raw/chunks.jsonl" data/raw/

# Copy documents (tuỳ chọn — cần nếu muốn rebuild sau)
scp "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/raw/documents.jsonl" data/raw/

# Copy ChromaDB (cả folder)
scp -r "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/chroma_db/" data/

# Copy BM25 index
scp "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/bm25_index.pkl" data/
```

> **Lưu ý Windows**: Cần bật OpenSSH Server trên Windows.  
> Vào Settings → Apps → Optional Features → Add "OpenSSH Server" → Services → Start "OpenSSH SSH Server"

---

## Cách 2: Copy qua USB / ổ cứng ngoài

Trên Windows, copy các file/folder sau vào USB:
```
data\raw\chunks.jsonl
data\raw\documents.jsonl   ← tuỳ chọn
data\chroma_db\            ← cả folder
data\bm25_index.pkl
```

Trên Linux, giả sử USB mount tại `/media/usb`:
```bash
mkdir -p data/raw data/chroma_db

cp /media/usb/chunks.jsonl data/raw/
cp /media/usb/documents.jsonl data/raw/       # tuỳ chọn
cp -r /media/usb/chroma_db/. data/chroma_db/
cp /media/usb/bm25_index.pkl data/
```

---

## Cách 3: Copy qua rsync (nhanh nhất nếu có SSH)

```bash
WINDOWS_IP=192.168.1.x
WIN_USER=YourWindowsUsername
WIN_PROJECT="/c/Users/$WIN_USER/path/to/AcneLLM"   # đường dẫn kiểu cygwin/ssh

mkdir -p data/raw data/chroma_db

rsync -avz --progress \
    "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/raw/chunks.jsonl" \
    "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/raw/documents.jsonl" \
    data/raw/

rsync -avz --progress \
    "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/chroma_db/" \
    data/chroma_db/

rsync -avz --progress \
    "$WIN_USER@$WINDOWS_IP:$WIN_PROJECT/data/bm25_index.pkl" \
    data/
```

---

## Kiểm tra data đã copy đủ chưa

```bash
echo "=== Kiểm tra data ==="
ls -lh data/raw/chunks.jsonl       2>/dev/null && echo "✓ chunks.jsonl" || echo "✗ THIẾU chunks.jsonl"
ls -lh data/bm25_index.pkl         2>/dev/null && echo "✓ bm25_index.pkl" || echo "✗ THIẾU bm25_index.pkl"
ls -lh data/chroma_db/chroma.sqlite3 2>/dev/null && echo "✓ chroma_db" || echo "✗ THIẾU chroma_db"
wc -l < data/raw/chunks.jsonl      2>/dev/null | xargs -I{} echo "  chunks count: {}"
```

Output mong đợi:
```
✓ chunks.jsonl
✓ bm25_index.pkl
✓ chroma_db
  chunks count: 24113
```

---

## Cấu hình .env

```bash
cp .env.baseline .env
```

Chỉnh các dòng quan trọng trong `.env`:

```bash
# Model đã pull (thay bằng tên model thực tế đang có trong Ollama)
LLM_MODEL=qwen2.5:7b
LLM_FALLBACK_MODEL=qwen2.5:3b

# CPU (mặc định) hoặc cuda nếu có GPU
DEVICE=cpu

# Giữ nguyên nếu chạy Ollama local
OLLAMA_URL=http://localhost:11434
```

Kiểm tra Ollama có model chưa:
```bash
ollama list
```

Nếu chưa có model:
```bash
ollama pull qwen2.5:7b
```

---

## Chạy Backend

```bash
source .venv-linux/bin/activate

# Đảm bảo Ollama đang chạy:
curl -s http://localhost:11434/api/tags > /dev/null && echo "Ollama OK" || (ollama serve & sleep 3)

# Chạy API:
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Kiểm tra backend:
```bash
curl http://localhost:8000/api/v1/health
```

---

## Chạy Frontend

```bash
cd frontend
npm install
npm run dev
```

Mở trình duyệt: **http://localhost:3000**

---

## Chạy cả 2 cùng lúc (dùng tasks.sh)

```bash
chmod +x tasks.sh
./tasks.sh run-all
```

---

## Không muốn rebuild index — bỏ qua bước nào?

Vì KB đã copy sẵn, bỏ qua hoàn toàn các bước sau:

| Bước | Lệnh | Bỏ qua vì |
|------|------|-----------|
| Crawl dữ liệu | `./tasks.sh crawl` | `documents.jsonl` đã có |
| Build KB | `./tasks.sh build-kb` | `chroma_db` và `bm25_index.pkl` đã có |
| Playwright | `playwright install chromium` | Chỉ cần cho crawler |

> **Nếu sau này muốn crawl thêm dữ liệu mới**, chạy `./tasks.sh crawl` rồi `./tasks.sh build-kb --force` để rebuild index từ `documents.jsonl` mới.

---

## Troubleshooting

### Lỗi `ChromaDB: collection not found`
→ `chroma_db/` bị thiếu hoặc copy không đủ. Kiểm tra lại `data/chroma_db/chroma.sqlite3` tồn tại.

### Lỗi `BM25 index not found`
→ Copy thiếu `data/bm25_index.pkl`. Copy lại từ Windows.

### Lỗi `CUDA out of memory` hoặc model chậm
→ Đổi `DEVICE=cpu` trong `.env` nếu GPU không đủ VRAM.

### Ollama không tìm thấy model
```bash
ollama list          # xem model nào đang có
ollama pull qwen2.5:7b  # kéo model nếu thiếu
```
Sau đó đảm bảo `LLM_MODEL` trong `.env` khớp tên model trong `ollama list`.

### Port 8000 đang bị chiếm
```bash
lsof -ti :8000 | xargs kill -9
```

### `underthesea` lỗi khi import
```bash
sudo apt install -y libmecab-dev mecab mecab-ipadic-utf8
pip install underthesea --force-reinstall
```
