# AcneLLM — Tư vấn da mụn tiếng Việt (Đề tài 29)

Hệ thống RAG + LLM chạy **100% local**, dùng Next.js làm web UI và FastAPI làm backend API cho mobile app.

---

## Yêu cầu

| Phần mềm | Phiên bản | Ghi chú |
|---|---|---|
| Python | 3.10+ | đã test 3.10 |
| [Ollama](https://ollama.com) | mới nhất | phải đang chạy khi serve |
| RAM | ≥ 8 GB | 6 GB đủ nếu dùng model 3B |
| Ổ cứng | ≥ 10 GB | models + ChromaDB + raw crawl |

---

## Cài đặt & chạy nhanh

### Windows (PowerShell)

```powershell
# 1. Clone & tạo venv
git clone <repo-url>
cd AcneLLM
.\tasks.ps1 install

# 2. Copy config
cp .env.example .env        # chỉnh OLLAMA_URL nếu cần

# 3. Pull LLM (Ollama phải đang chạy)
.\tasks.ps1 pull-models

# 4. Crawl dữ liệu  (~1-3h, tuỳ tốc độ mạng)
.\tasks.ps1 crawl

# 5. Build knowledge base  (~30-90 phút CPU)
.\tasks.ps1 build-kb

# 6. Chạy server
.\tasks.ps1 serve
```

### Linux / Mac

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env

ollama pull qwen2.5:7b
python -m scripts.crawl_all
python -m scripts.build_kb
uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Sau khi serve:

| URL | Mô tả |
|---|---|
| `http://localhost:3000` | Web UI mới (Next.js) |
| `http://localhost:8000` | Backend API |
| `http://localhost:8000/docs` | OpenAPI (Swagger) |
| `http://localhost:8000/api/v1/chat` | JSON endpoint cho mobile |

---

## tasks.ps1 — tất cả lệnh

```
.\tasks.ps1 install        # cài deps + tạo venv
.\tasks.ps1 pull-models    # pull Ollama models
.\tasks.ps1 crawl          # crawl tất cả nguồn
.\tasks.ps1 crawl-pubmed   # chỉ crawl PubMed
.\tasks.ps1 build-kb       # chunk + embed + index
.\tasks.ps1 serve          # chạy web mới (frontend + backend)
.\tasks.ps1 serve-lan      # chạy backend + in IP LAN cho mobile app
.\tasks.ps1 test           # pytest
.\tasks.ps1 eval           # eval 20 queries (mặc định)
.\tasks.ps1 eval 50        # eval 50 queries
.\tasks.ps1 stats          # thống kê KB + Ollama
.\tasks.ps1 chat           # chat thử qua terminal
.\tasks.ps1 clean-kb       # xoá processed/chroma/bm25
```

---

## API

### `POST /api/v1/chat`

**Request:**
```json
{
  "description": "Em 22 tuổi, da dầu, nổi nhiều mụn viêm ở cằm 4 tuần nay",
  "context": {
    "age": 22,
    "skin_type": "oily",
    "is_pregnant": false,
    "current_products": ["cerave foaming cleanser"]
  },
  "mode": "hybrid"
}
```

`mode`: `hybrid` (mặc định) | `llm_only`

**Response** (`AdviseOutput`):
```json
{
  "severity": "moderate",
  "acne_type_primary": "mụn viêm (papule/pustule)",
  "causes": ["bít tắc nang lông", "vi khuẩn C. acnes"],
  "recommendations": [
    {
      "step": 1,
      "action": "Rửa mặt 2 lần/ngày bằng sữa rửa mặt dịu nhẹ không xà phòng",
      "rationale": "Giữ pH da cân bằng, không kích ứng",
      "source_chunk_id": "vinmec_a1b2::0003",
      "category": "skincare"
    }
  ],
  "red_flags": [],
  "confidence": 0.78,
  "disclaimer": "Thông tin mang tính tham khảo...",
  "mode": "hybrid",
  "latency_ms": 4200
}
```

### Mobile app (đề tài 29)

Dùng `.\tasks.ps1 serve-lan` để lấy IP LAN, rồi gọi:

```
POST http://192.168.x.x:8000/api/v1/chat
```

---

## Kiến trúc

```
User
 │
 ▼
FastAPI ──────────────────────────────────────────────┐
 │                                                    │
 ├─ Guardrails.pre (validate input)                   │
 │                                                    │
 ├─ HybridRetriever                                   │
 │    ├─ Dense: BGE-M3-VI → ChromaDB                  │
 │    ├─ Sparse: BM25 (underthesea tokenizer)          │
 │    └─ RRF fusion → top-20                          │
 │                                                    │
 ├─ Reranker (bge-reranker-v2-m3) → top-5             │
 │                                                    │
 ├─ PromptBuilder (Jinja2)                            │
 │                                                    │
├─ Ollama (Qwen2.5-7B, JSON schema constrained)       │
 │                                                    │
 ├─ Pydantic parse → AdviseOutput                     │
 │                                                    │
 └─ Guardrails.post ──────────────────────────────────┘
      ├─ block retinoid nếu mang thai/cho con bú
      ├─ inject "gặp bác sĩ" nếu severity=severe
      ├─ strip tư vấn tự nặn mụn
      └─ đảm bảo có disclaimer
```

---

## Tech stack

| Thành phần | Lựa chọn |
|---|---|
| LLM | Ollama · Qwen2.5-7B |
| Embedding | AITeamVN/Vietnamese_Embedding (BGE-M3 VN, dim=1024) |
| Reranker | BAAI/bge-reranker-v2-m3 |
| Vector DB | ChromaDB (persist local) |
| Sparse | rank_bm25 + underthesea |
| API | FastAPI + Jinja2 + HTMX + Tailwind CDN |
| Crawler | httpx async + trafilatura + PubMed E-utilities |
| Dedup | MinHash LSH (datasketch) |

---

## Nguồn dữ liệu (15 domains)

**Tiếng Việt (high trust):** Vinmec, BV Da Liễu TP.HCM, BV Da Liễu TW, Tam Anh Hospital, HelloBacsi, Medlatec, Youmed, Pharmacity

**Tiếng Anh (high trust):** PubMed (~2500 abstracts), AAD, DermNet, Mayo Clinic, Cleveland Clinic, MedlinePlus, NICE

Mục tiêu: ≥ 2.500 documents → ≥ **20.000 chunks** sau chunking.

---

## Guardrails (kiểm thử tự động)

| Rule | Hành động |
|---|---|
| Mang thai + retinoid | Rewrite recommendation, inject red flag urgent |
| Cho con bú + retinoid hệ thống | Rewrite, inject red flag |
| Severity = severe | Inject "gặp bác sĩ da liễu" + red flag urgent |
| Tự nặn/cạy mụn | Strip recommendation |
| Không có disclaimer | Inject disclaimer mặc định |

---

## Swap points (LEGO architecture)

| Ghép với đề tài | Việc cần làm |
|---|---|
| 27 — Vision | Implement `VisionProtocol`, swap `vision/mock.py` |
| 28 — RAG nâng cao | Implement `RAGProtocol`, swap `rag/retriever.py` + `reranker.py` |

---

## Máy yếu (< 8 GB RAM)

Đổi model trong `.env`:

```
LLM_MODEL=qwen2.5:7b
```

Rồi `.\tasks.ps1 pull-models`. `qwen2.5:7b` là model mặc định của project hiện tại.

---

## License

Nghiên cứu học thuật. Thông tin y khoa mang tính tham khảo, không thay thế chẩn đoán chuyên khoa.
