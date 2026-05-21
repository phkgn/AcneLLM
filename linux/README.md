# AcneLLM — Hướng dẫn chạy trên Linux (bỏ qua Crawler)

Folder này chứa hướng dẫn triển khai AcneLLM trên Linux **mà không cần chạy crawler**.  
Knowledge base (dữ liệu, vector index) đã được build sẵn trên Windows — chỉ cần copy sang và chạy thẳng.

---

## Các file trong folder này

| File | Nội dung |
|------|----------|
| `README.md` | File này — tổng quan và chọn hướng đi |
| `setup.md` | Cài đặt môi trường từ đầu (Python, Ollama, deps) |
| `no-crawler.md` | Hướng dẫn copy KB từ Windows sang và bỏ qua bước crawl/build-kb |

---

## Chọn hướng đi phù hợp

### Tình huống 1: Máy Linux mới, chưa có gì
→ Đọc [`setup.md`](setup.md) trước, rồi [`no-crawler.md`](no-crawler.md)

### Tình huống 2: Đã cài Python/Ollama, chỉ cần chạy app
→ Đọc thẳng [`no-crawler.md`](no-crawler.md)

### Tình huống 3: Muốn crawl lại dữ liệu mới trên Linux
→ Đọc [`setup.md`](setup.md) và dùng `./tasks.sh crawl` + `./tasks.sh build-kb` thay vì làm theo `no-crawler.md`

---

## Tóm tắt nhanh (đã có KB sẵn)

```bash
# 1. Cài môi trường
sudo apt install -y python3 python3-venv python3-pip libmecab-dev mecab mecab-ipadic-utf8
python3 -m venv .venv-linux && source .venv-linux/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt && pip install -e .

# 2. Cài Ollama + kéo model
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull qwen2.5:7b

# 3. Copy KB từ Windows (xem no-crawler.md để biết cách)
# — copy data/raw/, data/chroma_db/, data/bm25_index.pkl

# 4. Cấu hình
cp .env.baseline .env   # chỉnh LLM_MODEL nếu cần

# 5. Chạy
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
# Frontend:
cd frontend && npm install && npm run dev
```
