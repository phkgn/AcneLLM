# Prompt: Technical Audit — AcneLLM baseline (đã hiệu chỉnh theo repo thực tế)

> Phiên bản này đã thay phần "giả thuyết ban đầu" bằng **context xác minh trực tiếp từ
> source code + config** (tính đến lần audit gần nhất). Các mục còn nghi vấn được đánh dấu
> **[VERIFY]**. Agent vẫn phải coi source code + runtime là source of truth và kiểm lại,
> nhưng hãy bắt đầu từ các dữ kiện đã xác nhận bên dưới thay vì phỏng đoán lại từ đầu.

---

## 0. Mục tiêu

Thực hiện một **technical audit end-to-end** của baseline repo AcneLLM (chatbot tư vấn da mụn
tiếng Việt). Hiểu kiến trúc và pipeline THỰC TẾ, chạy test end-to-end nhiều turn, chấm điểm
từng layer độc lập, tìm root cause cho từng lỗi, rồi xuất một **báo cáo HTML** hoàn chỉnh.
**Không sửa/không refactor baseline** trước khi hoàn tất đánh giá (xem mục 10).

---

## 1. Context đã xác minh (CONFIRMED — từ source/config)

Đây là dữ kiện đã đọc trực tiếp trong repo. Agent nên xác nhận nhanh lại, không cần dựng lại từ số 0.

**Ngôn ngữ & mục đích:** chatbot tư vấn/giải đáp da mụn (acne) tiếng Việt.

**Backend:** FastAPI. Entry point `src/acne_llm/api/app.py`. Routes gắn prefix `/api/v1`:
`health`, `chat`, `kb`, `admin`, `metrics` (xem `app.include_router(...)`). API port **8000**
(`API_HOST=0.0.0.0`, `API_PORT=8000`). Endpoint chat là router `chat.router` — **đây là API cần gọi để test end-to-end** (kiểm tra chính xác path + POST/SSE/WebSocket trong `api/routes/chat.py`).

**Frontend:** Next.js, package `acne-llm-frontend`, chạy bằng `next dev`. Gọi backend qua
`API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`
(`frontend/src/config/chatConfig.ts`). **[VERIFY]** port frontend: `next dev` mặc định **3000**;
user từng nói **3001** → xác nhận có override (`-p 3001`/`PORT`) hay không.

**LLM local (Ollama):** `OLLAMA_URL=http://localhost:11434`.
- Model chính: **`acnellm-v2-q4:latest`** (model đã fine-tune + quantize **Q4**, chạy qua Ollama Modelfile).
- Fallback: **`qwen2.5:3b`** → base thuộc **họ Qwen2.5**.
- **`LLM_USE_MODELFILE_SYSTEM=true`** → system prompt đã nhúng trong **Modelfile**, backend **KHÔNG gửi system message qua API** (cơ chế tránh double-system-prompt). Đây là chi tiết kiến trúc quan trọng khi phân tích prompt.
- Generation (theo `.env.baseline`, xác nhận lại default trong `src/acne_llm/config.py`):
  `LLM_NUM_CTX=4096`, `LLM_NUM_PREDICT=1200`, `LLM_TEMPERATURE=0.35` (override per-request qua `?temperature=`),
  `OLLAMA_GENERATE_TIMEOUT=180`. **[VERIFY]** top_p/top_k/repeat_penalty/stop — tìm trong `llm/ollama_backend.py`.

**Embedding:** **`AITeamVN/Vietnamese_Embedding`**, **dim=1024** (embedder chuyên tiếng Việt, KHÔNG phải bge-m3 đa ngôn ngữ — điểm này giải thích hiện tượng tách cụm theo ngôn ngữ trong KB). Device **cpu**.

**Reranker:** cross-encoder **`BAAI/bge-reranker-v2-m3`**, `RERANKER_MIN_SIGMOID=0.30`, batch 16.

**Vector store:** ChromaDB (`CHROMA_DIR=./data/chroma_db`), collection **`acne_kb_vi`**, cosine space,
**16.635 chunks** (đã đếm trực tiếp trong sqlite). BM25 index: `./data/bm25_index.pkl`, `BM25_NORMALIZE=true`.

**RAG (chat):** dense (Chroma, `DENSE_MAX_DISTANCE=0.60`) + BM25 → **RRF fusion** (`pipeline/hybrid.py::_rrf_fusion`)
→ cross-encoder rerank → lọc chunk yếu/nhiễu. Tham số chat: `CHAT_RETRIEVE_TOP_K=6`, `CHAT_RERANK_TOP_K=3`,
`CHAT_MAX_CONTEXT_CHARS=6000`, `CHAT_SAFETY_TOP_K=5` (lượt tìm an toàn riêng cho thai kỳ/thuốc kê đơn),
`CHAT_MIN_CITATION_SCORE=0.25`. Có tùy chọn MMR prefilter (`retrieve_with_mmr`).

**Guardrails:** `GUARDRAILS_ENABLE_OOD=true`, `GUARDRAILS_OOD_THRESHOLD=0.25`, `GUARDRAILS_SCOPE_MODE=soft`
(rule-based; `guardrails/runner.py` + `config/guardrails.yaml`).

**Dữ liệu fine-tune:** JSONL sinh bằng **DeepSeek** (`DEEPSEEK_MODEL=deepseek-chat`; metadata dataset ghi
`gen_model=deepseek-v4-flash`). Bộ chính: `data/finetune/cleanv3_gen.jsonl` (~45.9k record, cặp
`<raw_user_message>` → `<normalized_case>`). Sinh dữ liệu từ chunk crawl (thư mục `LLMData/{chunk_qa,clinical_case,injection_qa}`,
mỗi chunk ~1–2 sample). Judge eval: `o4-mini`.

**Hai chế độ chạy:** `llm_only` và `hybrid` (RAG) — cùng đi qua một đường xử lý trong `chat/orchestrator.py`.

### Điểm mấu chốt cần audit kỹ (mâu thuẫn config ↔ code đã phát hiện)

- **[VERIFY — quan trọng] LLM planner vs rule-based planner.** `.env.baseline` có
  `CHAT_USE_LLM_PLANNER=true`, NHƯNG trong `pipeline/hybrid.py` có comment cho biết
  `use_llm_planner` là **no-op/deprecated** và `ClinicalQueryPlanner` (`llm/clinical_planner.py`) là
  **rule-based**, "LLM chỉ chạy ở bước generate cuối". Agent phải xác định **thực tế runtime**: planner
  đang chạy bằng luật hay bằng LLM → điều này quyết định **một query gọi LLM 1 hay 2 lần**.
- **Chuẩn hóa & lập kế hoạch là rule-based, KHÔNG phải LLM:** `chat/normalizer.py` (regex/keyword,
  ~1900 dòng) trích `NormalizedAcneCase`; `clinical_planner.py` gom ca + dựng 2 query (một "túi từ khóa"
  song ngữ cho retrieve, một câu tự nhiên cho rerank). LLM (`ollama_backend.py`) chỉ sinh JSON `AdviseOutput`
  ở bước cuối. Đừng mặc định mỗi stage NLP là một lần gọi LLM.

### Vẫn cần agent xác minh (chưa chắc từ config)

- **[VERIFY]** Kích thước base model của `acnellm-v2-q4` (**không xác nhận là 7B**). Trên **RTX 3050 Ti 4GB VRAM /
  24GB RAM**, 7B-Q4 (~4.4GB) sát trần VRAM, 3B-Q4 (~2GB) an toàn hơn; fallback là 3B. Chạy
  `ollama show acnellm-v2-q4` để lấy base + params + template + system.
- **[VERIFY]** Phương pháp fine-tune (**QLoRA?**) — tìm script train trong repo (`datagen/`, hoặc script LoRA), config r/alpha/target modules.
- **[VERIFY]** Modelfile của `acnellm-v2-q4` (SYSTEM, TEMPLATE, PARAMETER) — so với chat template Qwen2.5 chuẩn.

---

## 2. Nhiệm vụ 1 — Dựng lại kiến trúc & pipeline THỰC TẾ từ code

Đọc và xác nhận (dùng các file đã nêu làm điểm bắt đầu):

- Entry backend (`api/app.py`) + các route (`api/routes/`), đặc biệt luồng `chat`.
- Cách frontend gọi backend (`chatConfig.ts`), kiểu kết nối (REST/SSE/WebSocket).
- Luồng request từ lúc user nhập tới lúc response ra UI.
- Quản lý session/history: `chat/session.py`, `chat/runtime.py`, `chat/orchestrator.py`.
- Cách gọi model local: `llm/ollama_backend.py` (client, generate_json, params thật, stop, format=json?).
- Với mỗi stage: tên class/function, prompt tương ứng (nếu có), input/output schema (Pydantic:
  `schemas/clinical.py`, `schemas/core.py::AdviseOutput`, `ClinicalQueryPlan`), fallback/retry/exception,
  confidence (`planner_confidence`), thứ tự thực thi, **task nào gọi LLM vs rule-based**, và **số lần gọi LLM / query**.

Kiểm tra sự tồn tại THỰC TẾ của các stage (đừng mặc định có/không), đối chiếu với danh sách:
preprocess/normalize (`chat/preprocess.py`, `normalizer.py`), language handling, guardrail (pre/scope/OOD/drug),
intent router (`chat/intent_router.py`), out-of-scope, acne/clinical extraction (normalizer), user-context
resolver & incremental memory (`chat/intake.py`, `session.py`), query rewrite/RAG query construction
(`clinical_planner.py`, `utils/retrieval_query.py`), clarification/`completeness.py`, triage/medication safety
(`guardrails/`), retrieval decision, generation (`prompt_builder.py` + `ollama_backend.py`), post-process
(`guardrails.post_check`, `_inject_english_notice`).

Dựng lại pipeline đúng theo code (sơ đồ tham chiếu — **phải chỉnh cho khớp thực tế**):

```
User → preprocess → intent_router → guardrails(pre/scope/OOD)
     → normalizer (regex → NormalizedAcneCase)
     → clinical_planner (rule-based → query_vi + rerank_query + safety_terms)   [VERIFY: LLM?]
     → hybrid retrieve (dense + BM25 → RRF) → cross-encoder rerank → filter
     → prompt_builder (context + case + history)
     → Ollama acnellm-v2-q4 (JSON AdviseOutput)
     → guardrails.post_check → Frontend
```

---

## 3. Phân tích RAG thật kỹ

**Ingestion/index:** nguồn crawl (`data/seed_sources.yaml`, `crawler/`), `data/raw/documents.jsonl`,
`chunks.jsonl`; cleaning/dedup; chiến lược chunk (size/overlap/theo char-token-câu-đoạn/semantic — xem `rag/chunker.py`);
metadata lưu cùng chunk (đã biết: `doc_id,title,url,source,source_type,trust,lang,categories,tags,position,prev/next_chunk_id`);
ID strategy; embedder (`AITeamVN/Vietnamese_Embedding`, dim 1024, `rag/embedder.py`); có normalize embedding không.

**Retrieval (`rag/retriever.py`, `rag/sparse.py`, `pipeline/hybrid.py`):** BM25 impl; dense impl (Chroma);
cách hợp nhất **RRF** (kiểm tra k, có trộn thẳng điểm khác scale không); top-k mỗi retriever; merge + dedup;
reranker (bge-reranker-v2-m3, ngưỡng sigmoid 0.30); MMR; final top-k; neighbor/prev-next expansion; metadata
filter; query expansion/rewrite; multi-query.

**Rủi ro cần soi (có bằng chứng từ audit KB):** KB tách cụm **theo ngôn ngữ** (embedder chuyên tiếng Việt) —
guideline chất lượng cao (**AAD 278 + NICE 113 ≈ 2,3% KB**) nằm trong vùng tiếng Anh, xa nơi câu hỏi tiếng Việt
rơi vào. → Kiểm tra: query tiếng Việt có kéo được guideline/`source_type∈{aad_guideline,nice_guideline}` lên top-k
không; trust-boost + `CHAT_SAFETY_TOP_K` có thực sự cứu được không. Cùng các lỗi kinh điển: BM25 vs cosine khác
scale, duplicate chiếm top-k, query rewrite mất entity, context quá dài/nhiễu, neighbor expansion gây nhiễu,
retrieval đúng nhưng prompt không ép model dùng, model hallucinate dù context đúng.

**Context construction (`prompt_builder.py`):** format context, separator, có title/metadata không, thứ tự chunk,
token/char budget (`CHAT_MAX_CONTEXT_CHARS=6000`), truncate ở đâu, ưu tiên chunk điểm cao, có lặp không,
prompt có tách rõ: retrieved knowledge / history / user profile / system / current query.

---

## 4. Fine-tuned model & prompting

Lấy prompt/template CUỐI gửi cho `acnellm-v2-q4` (nhớ: **system nằm trong Modelfile**, không qua API).
Đánh giá: system prompt (trong Modelfile), chat template có đúng Qwen2.5 không, có double system không (kiểm
`LLM_USE_MODELFILE_SYSTEM`), prompt injection risk, instruction conflict giữa các stage, prompt quá dài/verbose,
**mismatch giữa distribution lúc fine-tune (cặp raw→normalized_case JSON) và prompt inference** (inference có
đang bơm context RAG + history phức tạp trong khi model được train chủ yếu cho normalize/Q&A?), vị trí history,
độ ổn định JSON/schema ở các bước trung gian.

Phân tách nguồn lỗi rạch ròi: (1) fine-tuned model, (2) prompt, (3) retrieval, (4) context construction,
(5) router, (6) entity extraction/normalizer, (7) conversation memory, (8) rule-based logic, (9) FE/BE integration.
**Không thấy final answer sai rồi kết luận ngay là "model yếu".**

---

## 5. Runtime hiện tại (không phá môi trường)

Kiểm tra trong phạm vi an toàn (không kill/restart/đổi env trừ khi thật cần):
- Ollama có chạy không (`http://localhost:11434`), model nào được load/gọi (`ollama ps`, `ollama show acnellm-v2-q4`).
- Backend (uvicorn FastAPI, port **8000**), frontend (`next dev`, **[VERIFY]** 3000/3001).
- Runtime thường gồm ~3 cửa sổ: (1) Ollama, (2) PowerShell backend/`watchfiles` (hot reload, nơi in DEBUG log
  pipeline: retrieval/rerank/LLM latency — `LOG_LEVEL=DEBUG`), (3) frontend Node.
- Log pipeline nằm ở đâu (`data/logs/`, `logs/`, stdout backend). Ưu tiên dùng runtime đang chạy để test.

---

## 6. Thiết kế test end-to-end

Thiết kế bộ test nhỏ nhưng coverage cao (**8–15 session, mỗi session 2–6 turn**), realistic, dễ lộ lỗi
pipeline; ưu tiên hội thoại nhiều turn. Cover các nhóm (chỉ khi khớp chức năng thật của repo):

A. Kiến thức acne cơ bản · B. Advice có context cá nhân (tuổi/giới/loại da/vị trí/tổn thương/thời gian/sản phẩm)
· C. Incremental context (rải thông tin qua nhiều turn) · D. Pronoun/coreference ("cái đó", "nó") ·
E. Topic shift (mặt→lưng/thuốc, kiểm tra contamination) · F. Correcting previous info (đổi doxycycline→minocycline,
kiểm tra update state) · G. Medication safety (retinoid/isotretinoin/tetracycline/thai kỳ — diễn đạt vòng,
thiếu thông tin, bổ sung ở turn sau) · H. Urgent/triage (dấu hiệu cần escalation) · I. Ambiguous ("mụn kiểu này
có sao không") · J. Tiếng Việt informal (viết tắt/không dấu/typo: "toi bi mun quai ham 8 thang r, dung ada ma k het")
· K. Trộn Việt-Anh ("skin purge","closed comedone","PIH","barrier") · L. Out-of-scope · M. Prompt-injection nhẹ
(bảo bỏ qua guideline nội bộ — kiểm instruction hierarchy) · N. Retrieval stress (từ khóa gần nhau, yêu cầu rất cụ thể)
· O. Multi-intent (nguyên nhân + treatment + tương tác thuốc trong 1 message).

---

## 7. Cách chạy & quan sát

Test qua ĐÚNG API mà frontend dùng (POST tới chat endpoint dưới `/api/v1`, kiểm SSE/WS trong `api/routes/chat.py`).
Song song đọc DEBUG log backend/`watchfiles`. Với mỗi turn, ghi nhận các stage **thực sự tồn tại**: input, history
trước request, router/intent, extracted user context + clinical entities (NormalizedAcneCase), safety/triage,
query rewrite, retrieval query (query_vi/rerank_query), BM25/dense/hybrid candidates, reranker result, final chunks,
RAG context vào model, generation prompt (nếu xem an toàn), raw output, final response sau post-process, latency,
exception/fallback/retry (vd fallback sang `qwen2.5:3b`).

Nếu log không đủ, đọc code để reconstruct. **Không instrument/sửa baseline chỉ để test**, trừ khi bất khả kháng;
nếu buộc phải, chỉ thêm log tối thiểu, không đổi behavior, ghi rõ file, revert sạch được.

---

## 8. Chấm điểm từng layer độc lập

Chấm riêng (0–10 hoặc %, kèm evidence): NLP preprocessing (normalize/typo/informal/mixed) · router/intent
(accuracy, multi-intent, context-aware) · user-context extraction (age/sex/skin_type/pregnancy/medication/products/duration)
· clinical extraction (lesion/distribution/inflammation/scarring/medication history/hormonal) · conversation context
(memory/incremental/correction/coreference/topic-shift) · safety/triage (drug combo/thai kỳ/urgent/escalation) ·
query processing (rewrite quality/entity preservation/drift) · retrieval (BM25/dense/RRF/rerank/diversity/relevance,
đặc biệt **guideline reachability cho query tiếng Việt**) · RAG context (precision/recall/dup/noise/order/token
efficiency) · prompting (system/intermediate/generation/clarity/schema stability) · fine-tuned model (instruction
following/dùng context/hallucination/độ trôi chảy tiếng Việt/độ chính xác y khoa/xử lý output có cấu trúc) ·
final response (correctness/completeness/safety/relevance/clarity/personalization/overconfidence).

> Có sẵn harness đo chuẩn hóa: `scripts/eval/normalizer/` (P/R/F1 + confusion) và
> `scripts/visualize/visualize_chromadb.py` (bản đồ KB) — có thể tái sử dụng làm evidence cho layer
> extraction và retrieval.

---

## 9. Root cause cho từng lỗi

Với mỗi lỗi đáng chú ý, viết theo format: **Observed behavior · Evidence (chunk/log/state/schema cụ thể) ·
Root cause · Affected component (file→function) · Impact · Recommended fix.** Không viết chung chung
("RAG chưa tốt"). Phân biệt **Confirmed / Strong evidence / Likely / Hypothesis** — không trình bày giả thuyết như fact.

---

## 10. Không sửa baseline trước khi đánh giá

Chỉ audit + evaluate. **Không** refactor / optimize / đổi prompt / đổi retrieval weight / đổi model / sửa pipeline
trước khi có evidence baseline đầy đủ. Recommendation chỉ đưa ra **sau** khi test xong; **không implement** ở task này.

---

## 11. Báo cáo HTML

Xuất một file `.html` hoàn chỉnh, mở trực tiếp trên browser, UI dark/neutral technical-dashboard, responsive,
HTML/CSS/JS thuần (không build tool; Mermaid offline nếu cần). Gồm:
Executive Summary · Repository Architecture (component map: BE/FE/Ollama/RAG/pipeline) · Actual End-to-End Pipeline
(flow diagram đúng code) · Runtime Architecture (process/port/service) · Fine-tune & Model Integration Analysis
(model `acnellm-v2-q4`, base họ Qwen2.5 **[VERIFY size]**, Q4, Modelfile/template, mismatch) · RAG Deep Dive
(ingestion/chunking/embedding 1024d/BM25/dense/RRF/rerank/context) · Test Methodology · **Test Case Matrix**
(Session ID/Category/turns/expected/actual/pipeline obs/retrieved quality/final quality/Pass·Partial·Fail) ·
Detailed Session Analysis · **Layer-by-Layer Score** (bảng cho từng layer ở mục 8) · **Failure Analysis**
(Severity Critical/High/Medium/Low · Component · Evidence · Root cause · Impact · Reproduction) · What Works Well ·
**Improvement Priority** P0/P1/P2/P3 (mỗi mục: problem · reason · suggested approach · expected impact · complexity/risk)
· **Final Verdict**.

**Final Verdict phải trả lời thẳng:** pipeline có hiệu quả không · NLP có đáng tin không · context handling có tốt không ·
RAG retrieve đúng tài liệu không (đặc biệt guideline cho query tiếng Việt) · model có dùng đúng context không ·
prompting có hợp fine-tuned model không · **`acnellm-v2-q4` (base Qwen2.5, Q4) có phải bottleneck chính không** ·
bottleneck lớn nhất nằm ở đâu · repo đang ở mức demo/prototype/strong prototype/gần production · 3–5 thay đổi impact lớn nhất.

---

## 12. Nguyên tắc đánh giá

Khách quan — không cố khen, không cố chê. Mọi kết luận quan trọng phải dựa trên ≥1 nguồn: source code · config ·
prompt · runtime log · API response · retrieved chunk · reproducible test. Phân biệt Confirmed / Strong evidence /
Likely / Hypothesis. Không suy kiến trúc chỉ từ tên file. Không đánh giá model từ 1–2 câu trả lời. Không đánh giá
retrieval chỉ bằng final answer. Final answer tốt **không** đồng nghĩa pipeline dưới tốt (model có thể tự đúng dù RAG
sai; hoặc retrieval đúng nhưng model dùng context kém). Tách từng layer, tìm đúng bottleneck.

**Đầu ra cuối:** lưu báo cáo thành file `.html` trong thư mục report phù hợp (vd `reports/` hoặc `docs/`),
**không overwrite file quan trọng**, rồi báo lại **đường dẫn chính xác** của file HTML đã tạo.
