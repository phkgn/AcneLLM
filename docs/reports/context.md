# AcneLLM — Current Project Context

> Refresh theo source và artifact trong active worktree ngày **2026-08-25**.
> Baseline: branch `codex/simplify-chat-pipeline`, HEAD `487a7f6`. Snapshot
> `20260825T090826Z` đã đóng mẫu số 837/837 path và full test hiện tại là
> `495 passed, 1 xfailed in 53.86s`. Worktree đang
> dirty ở data/index, eval report và `.audit`, nên commit SHA một mình chưa đủ
> để mô tả trạng thái; phải kèm status/diff fingerprint khi trích dẫn số liệu.
> Tài liệu này mô tả kiến trúc đang chạy, ranh giới dữ liệu/eval và các invariant
> cần giữ. Nội dung trong `docs/archive/`, `docs/history/`, patch audit cũ hoặc
> `model/legacy/` chỉ dùng để truy vết, không được ưu tiên hơn source hiện hành.
> Fact boundary và cấu trúc slide bảo vệ mới nhất nằm ở
> `.audit/SLIDE_FACT_CHECK_2026-08-25.md` và
> `docs/presentations/AcneLLM_Defense_E2E_Context_2026-08-25.md`.

## 1. Cách đọc source of truth

Khi code, tài liệu và artifact không đồng ý với nhau, dùng thứ tự sau:

1. Source đang được import từ `src/acne_llm/` và wiring trong
   `src/acne_llm/di.py`.
2. Config thực tế trong `src/acne_llm/config.py`, `.env` chỉ override.
3. Test chạy trên chính worktree và interpreter của repo.
4. Metadata của từng eval artifact: dataset, model, judge, commit, step status và
   drop reason.
5. Tài liệu active.
6. Tài liệu archive/history và report cũ.

Một report lịch sử vẫn có giá trị cho đúng snapshot đã đo, nhưng không tự động
chứng minh runtime hiện tại. Một test suite xanh cũng không thay thế eval model
thật hoặc kiểm tra parity của endpoint SSE.

Mọi claim về repo phải mang đúng một trong bốn nhãn của
`.audit/CONTEXT_INTEGRITY.md`: `verified-current` (đã đối chiếu source/evidence
hiện hành), `historical` (đúng tại snapshot có ghi ngày/run id), `planned` (mới
là ý định) và `unknown` (chưa đủ bằng chứng, không được lấp bằng suy đoán).

Knowledge base audit nằm trong `.audit/`, bản Obsidian nằm trong
`.audit/obsidian_export/`. Thứ tự đọc cho một phiên mới: `OBSIDIAN_HOME` →
`CURRENT_TRUTH` → `SAFE_REMEDIATION_TASKS` → `FUTURE_BEHAVIOR_ROADMAP`, rồi mới
mở finding/snapshot theo module đang làm. `RECONCILIATION.md` là cầu nối giữa
immutable snapshot `runs/20260822T152307Z/` và source sau remediation; snapshot
đó là `historical`, không tự carry-forward thành current.

Riêng với mọi con số do LLM judge sinh ra, phải đọc kèm
`research/evaluation/reports/calibration_rrr/` — đó là mức tin cậy đã đo được
của chính dụng cụ đo (mục 11.5 và 11.6).

## 2. Sản phẩm hiện tại

AcneLLM là hệ thống tư vấn mụn tiếng Việt, local-first:

- frontend Next.js;
- backend FastAPI;
- model phục vụ qua Ollama;
- hybrid RAG bằng ChromaDB, BM25, Reciprocal Rank Fusion và cross-encoder;
- session/audit/feedback lưu bằng SQLite;
- endpoint chat production trả Server-Sent Events, không dùng WebSocket.

Runtime có đúng hai vai trò model:

| Model | Trách nhiệm | Output |
|---|---|---|
| `acne-intaker` | hiểu một lượt chat, chọn intent và trích xuất dữ kiện | JSON theo intake contract |
| `acne-generator-v2` | viết câu trả lời từ prompt/context đã chuẩn bị | prose streaming |

`acne-intaker` là **một instance, một inference dùng chung** cho routing và
extraction. Không còn runtime mode để chọn kiến trúc router/extractor cũ. Các
file trong `model/legacy/` là archive nghiên cứu và không tham gia startup.

## 3. Bản đồ repository

```text
src/acne_llm/
  api/                 FastAPI app, routes, auth/middleware, metrics
  chat/
    intake.py          điều phối preprocess, history, safety, route, extraction
    unified_intake.py  adapter duy nhất gọi intake LLM
    intake_contract.py contract chung cho Unified/Semantic/rule fallback
    routing/           semantic router, rule router/extractor, route flags
    session/           models, view/select, snapshot/fold
    _retrieval.py      query, retrieval passes, rerank và filter context
    orchestrator.py    chuẩn bị một turn trước generation
    runtime.py         stream generator, safety suffix, persist, SSE
    _safety.py         hậu kiểm/cảnh báo trên output text
  db/                  SQLite session, audit, feedback
  guardrails/          kiểm tra trust boundary và policy thuốc
  llm/                 Ollama client và prompt builder
  rag/                 dense/sparse/hybrid retrieval, reranker, cache
  schemas/             contract Pydantic/domain

frontend/              Next.js UI và SSE consumer
config/                prompts, guardrail config, drug knowledge config
scripts/               run/build/crawl/bundle tooling
research/
  evaluation/          eval intake, retrieval và ablation
  datagen/             sinh/chuẩn hóa dữ liệu fine-tune
  LLMData/             dữ liệu nghiên cứu
  dashboards/          dashboard và sơ đồ kiến trúc
data/                  raw/chunks, indexes, SQLite DB và cache cục bộ
model/                 Modelfile, model artifact, legacy archive
tests/                 unit/integration tests
docs/                  tài liệu active, archive/history và reports
```

`pyproject.toml` cấu hình `pythonpath = ["src", "research"]`. Vì thế source tại
`research/evaluation/` được import/chạy với tên module `evaluation`, ví dụ
`python -m evaluation.full_evaluation`.

Các thư mục root không tracked hoặc artifact phát sinh cục bộ không nên được ghi
thành layout canonical chỉ vì chúng tồn tại trong một worktree.

## 4. Wiring khi startup

`src/acne_llm/api/app.py` tạo FastAPI app và gọi
`src/acne_llm/di.py::build_container()` trong lifespan. Container production:

1. tạo Ollama backend cho generator;
2. tạo đúng một `UnifiedIntake` cho intake model;
3. giữ hai compatibility attribute `llm_router` và `llm_extractor`, nhưng cả hai
   cùng trỏ tới instance `UnifiedIntake` đó;
4. nạp Semantic Router local nếu asset hợp lệ;
5. nạp Chroma, BM25 và reranker khi KB sẵn sàng;
6. tạo prompt builder, guardrails, audit/feedback stores;
7. luôn dùng `SQLiteSessionStore` cho session production.

Compatibility attribute không có nghĩa là có hai model call. Nó chỉ giảm churn
cho caller cũ trong khi contract đã hợp nhất.

In-memory session store không còn public export trong package production. Test
muốn store độc lập phải dùng helper/fixture dưới `tests/`, tránh singleton rò
state giữa test.

## 5. Vòng đời một chat turn

### 5.1 HTTP và preprocess

`GET /api/v1/chat/stream` ở `src/acne_llm/api/routes/chat.py` kiểm tra message,
giới hạn kích thước/số từ rồi gọi `chat/runtime.py::stream_chat_sse()`.

`chat/intake.py::run_intake()` chuẩn hóa text, nạp history từ SQLite và chọn
history liên quan. Raw input, clean text và bản bỏ dấu có mục đích khác nhau;
không được thay thế lẫn nhau nếu chưa đo mất thông tin như phủ định, thuốc hoặc
vị trí tổn thương.

### 5.2 Intake success path

```text
raw message + relevant history
  -> guardrail pre-check
  -> UnifiedIntake.run(...)
  -> một JSON chứa intent + extraction
  -> normalize/validate theo intake contract
  -> RouteDecision + UserInput/clinical facts
```

Kết quả Unified Intaker được cache/reuse trong cùng turn: routing và extraction
không tạo hai lượt gọi LLM riêng. Dữ kiện extraction được fold với history theo
quy tắc session trước khi dùng cho policy/retrieval/prompt.

#### Vì sao chuẩn hóa user case bằng schema định nghĩa trước?

Schema không dùng để chẩn đoán thay người dùng. Nó là **hợp đồng dữ liệu trung
gian** để biến cách diễn đạt tự do thành các field mà routing, safety, retrieval,
prompt, session và evaluation có thể dùng nhất quán. Ví dụ câu “mụn bọc đau ở
hai má gần ba tháng, đang bôi Differin” có thể được chuẩn hóa thành
`lesion_types=["nodule"]`, `lesion_distribution=["cheeks"]`,
`duration_weeks=12` và `current_products=["adapalene"]`. Raw description vẫn
được giữ; schema không thay thế nguyên văn của người dùng.

Repo có hai contract gần nhau nhưng không được nhập làm một:

- runtime dùng `UserInput`, `UserContext` và `AcneClinicalInput` trong
  `src/acne_llm/schemas/core.py`;
- pipeline sinh dữ liệu nghiên cứu có `NormalizedAcneCase` trong
  `src/acne_llm/schemas/clinical.py`, với nhiều field phục vụ tạo/kiểm dữ liệu.

Các field được chọn theo bốn tiêu chí: phù hợp phạm vi mụn; cần cho cá nhân hóa;
nhạy cảm với safety; và có behavioral consumer hoặc có thể đánh giá được. Vì
vậy contract bao gồm tuổi/giới/loại da/thời gian, loại và vị trí tổn thương, mức
viêm, thai kỳ/cho con bú, dị ứng, thuốc và sản phẩm đang dùng. Nếu thêm field mới
nhưng không có consumer, provenance hoặc eval target thì chưa có căn cứ đưa nó
vào runtime contract.

Căn cứ của từng phép chuẩn hóa phải được phân biệt rõ:

- `inflammation_level` được runtime prompt neo theo IGA (AAD 2024), dựa trên
  loại tổn thương và mức lan; `unknown` là mặc định khi không đủ tín hiệu;
- taxonomy loại/vị trí tổn thương là vocabulary giới hạn cho domain và các
  consumer trong repo; source hiện hành không trích một chuẩn y khoa riêng cho
  từng enum nên không được mô tả toàn bộ taxonomy là chuẩn chẩn đoán đã xác nhận;
- alias như `BHA -> salicylic acid`, `BPO -> benzoyl peroxide`,
  `Differin -> adapalene` và quy đổi năm/tháng/ngày sang tuần là quy ước kỹ thuật
  để giảm nhiều cách viết của cùng một dữ kiện, không phải kết luận lâm sàng;
- chỉ trích điều người dùng thực sự tự khai; câu hỏi kiến thức, phủ định, thuốc
  đã ngưng hoặc thông tin về người khác không được biến thành fact hiện tại.

Schema/Pydantic bảo đảm **hình thức**: key được phép, kiểu dữ liệu, enum, giới
hạn tuổi/confidence và biểu diễn giá trị thiếu. Parser runtime còn drop field sai
enum/sai kiểu thay vì để nó đi vào Pydantic hoặc vứt cả inference. Tuy nhiên,
schema không bảo đảm **ngữ nghĩa**: output `is_pregnant=true` có thể hợp schema
nhưng vẫn sai chủ thể, thời hoặc phủ định. Vì thế field nhạy cảm vẫn cần
confidence, guard/fallback và bộ probe đối kháng; không được xem JSON hợp lệ như
clinical truth.

Artifact `research/evaluation/reports/v2_full/intake/report.json` minh họa đúng
ranh giới này trên 1.490 single-turn rows (từ bộ 1.500, loại 10 row multiturn),
với 0 failure và 0 fallback: schema-valid 98,12%, intent accuracy 95,70%, intent
macro-F1 74,05%, nhưng extraction micro-F1 chỉ 61,31%, hallucinated-field rate
8,20%, `inflammation_level` F1 21,26% và còn 28 schema violations. Do đó repo đã
chứng minh model thường trả đúng cấu trúc, chưa chứng minh mọi field đủ tin cậy
như hồ sơ lâm sàng.

Bộ eval intake do `deepseek-v4-pro` sinh và nghiêng nặng về nhãn `advise`
(1.410/1.500 trước khi loại multiturn). Vì vậy accuracy tổng không đại diện đều
cho bốn intent; phải đọc macro-F1 và per-intent trước khi kết luận.

Kết luận cần giữ khi mô tả hệ thống: đây là **chuẩn hóa dữ liệu trường hợp người
dùng**, không phải **chuẩn hóa chẩn đoán lâm sàng**. Chất lượng contract được
đánh giá theo ba lớp tách biệt: schema validity, semantic field accuracy và tác
động hành vi/safety ở downstream.

### 5.3 Failure path cố định

```text
Unified Intaker (LLM)
  -> nếu timeout, model lỗi, JSON/schema/intent không dùng được
Semantic Router (embedding local, không LLM)
  -> nếu unavailable hoặc lỗi
rule router + rule extractor (deterministic, không LLM)
```

Semantic và rule fallback là cơ chế availability/degradation. Chúng không được
mô tả là LLM phụ, và cũng không phải safety authority. Rule files được giữ khi
chúng phục vụ fallback; sự tồn tại của regex không đồng nghĩa normal path phụ
thuộc regex.

### 5.4 Route decision và metadata

`RouteDecision` tách rõ:

- `primary_intent`: `advise`, `knowledge`, `clarify` hoặc `reject`;
- `turn_type`: loại turn thực tế, thường là `answer`;
- `route_flags`: tín hiệu text-derived để chọn prompt/cảnh báo;
- `intent_confidence`: confidence của route source.

`turn_type` không được giả làm primary intent. Confidence từ Semantic Router là
`nearest_similarity` đã clip, không phải xác suất đã calibration. Không dùng nó
như xác suất lâm sàng nếu chưa hiệu chuẩn.

`product_safety_check` đã bị loại vì không có behavioral consumer. Nếu một flag
không thay đổi refusal, retrieval, prompt hoặc output thì không được gọi nó là
guardrail.

### 5.5 Orchestration, retrieval và prompt

`chat/orchestrator.py::prepare_chat_turn()` nhận intake result và quyết định:

- trả fixed refusal/reject/clarify;
- chọn knowledge hay advice template;
- có cần retrieval không;
- query và context nào được đưa vào prompt.

`chat/_retrieval.py` thực hiện các pass phù hợp:

1. xây query từ câu hiện tại và dữ kiện đã chọn;
2. hybrid retrieval qua dense Chroma + sparse BM25;
3. hợp nhất bằng RRF;
4. retrieval bổ sung cho guideline/safety khi cần;
5. cross-encoder rerank;
6. áp floor, giới hạn số chunk/nguồn và budget context;
7. đưa provenance cùng chunk vào prompt.

`src/acne_llm/llm/prompt_builder.py` mới là nơi lắp system/template, history,
profile, route flags và retrieved context. Text từ KB/history đi qua trust-boundary
sanitization trước khi vào prompt.

### 5.6 Generation, output safety và persistence

`chat/runtime.py` gọi generator bằng streaming, phát event SSE, ghép câu trả lời
và gọi `chat/_safety.py::get_safety_suffix()` để bổ sung/chuẩn hóa cảnh báo cuối.
Sau khi hoàn tất, runtime lưu cả user turn và assistant turn vào SQLite, đồng
thời ghi audit/metrics theo cấu hình.

Debug route `/api/v1/debug/trace` tái dùng pipeline chuẩn bị turn đến trước
generator. Nó không ghi session và không gọi generator, nên hữu ích để định vị
lỗi intake/retrieval/prompt nhưng không chứng minh parity của token streaming,
suffix hay persistence.

## 6. Safety: trách nhiệm được chia theo tầng

Không có một file duy nhất đại diện cho toàn bộ safety.

| Tầng | Trách nhiệm | Không phải |
|---|---|---|
| `guardrails/runner.py` | trust-boundary validation, PII warning, chống chỉ định/tương tác thuốc từ dữ kiện có cấu trúc | classifier tổng quát cho mọi nội dung |
| `chat/routing/intent_router.py` | sinh route flags cho prompt/output | refusal gate |
| Semantic/rule fallback | giữ routing/extraction hoạt động khi Intaker lỗi | safety authority |
| system prompt/templates | hướng generator trả lời đúng phạm vi và phong cách | hard deterministic guarantee |
| `chat/_safety.py` | dose/self-use checks và safety suffix cuối output | thay thế input medication policy |

Medication refusal kết hợp facts đã fold trong session với thuốc nhắc ở turn
hiện tại. Trạng thái mang thai/cho con bú phải đến từ field có cấu trúc, không
được suy ra chỉ vì câu có nhắc từ “mang thai”; nếu không sẽ tạo false positive
cho phủ định, câu hỏi kiến thức hoặc câu nói về người khác.

Policy hiện có các nhóm rủi ro quyết định như thai kỳ với retinoid/tetracycline,
isotretinoin dùng cùng tetracycline, giới hạn tuổi và anti-androgen cho nam. Mọi
thay đổi policy phải có tập false-positive/false-negative riêng trước khi xóa
hoặc mở rộng rule.

AcneLLM là công cụ hỗ trợ thông tin, không thay thế bác sĩ và không nên tự động
được tuyên bố “medical-safe” chỉ từ unit test hoặc một ablation run.

## 7. Session và multi-turn context

Production session nằm trong `src/acne_llm/db/session_store.py` và được truy cập
qua DI. Package `src/acne_llm/chat/session/` chia ba trách nhiệm:

- `models.py`: kiểu dữ liệu, schema version, TTL/window constants;
- `view.py`: chọn turn liên quan, profile xác nhận và render history block;
- `fold.py`: snapshot và quy tắc hợp nhất facts qua nhiều lượt.

TTL mặc định hiện tại là 1.800 giây. Giá trị cụ thể phải đọc từ config khi chạy,
vì `.env` có thể override.

Các rủi ro cần test khi thay session contract gồm: phủ định/correction ở turn
sau, fact cũ thắng fact mới, cross-session leakage, transaction/concurrency,
TTL, schema migration và persistence sau lỗi stream.

## 8. Data và quá trình xây Knowledge Base

Source build canonical là `scripts/build_kb.py`:

```text
data/raw/documents.jsonl
  -- chunk/filter/provenance --> data/raw/chunks.jsonl
  -- embedding -------------> data/chroma_db/
  -- tokenization -----------> data/bm25_index.pkl
```

Ba step `chunk`, `embed`, `bm25` có thể chạy độc lập và có guard chống build
index rỗng. Chroma phục vụ dense retrieval; BM25 phục vụ sparse retrieval. App
chỉ coi hybrid KB sẵn sàng khi cả hai asset cần thiết tồn tại/nạp được.

Snapshot KB đã được xác minh ngày 2026-08-23
(`.audit/SLIDE_FACT_CHECK_2026-08-23.md`) và publish thành release
`kb-v2-2026-08-23`:

| Chỉ số | Giá trị đã xác minh | Nguồn |
|---|---:|---|
| Raw document | 6.835 `doc_id` unique | `data/raw/documents.jsonl` |
| Document đạt quality mặc định | 6.796 (`quality_score >= 0.3`) | `documents.jsonl`, `scripts/build_kb.py` |
| Chunk cuối | 24.393 `chunk_id` unique | `data/raw/chunks.jsonl` |
| Chroma record | 24.393, cosine space | đọc live `data/chroma_db` |
| BM25 record | 24.393 chunk_id/text | `data/bm25_index.pkl` |
| Chunking mặc định | size 200, overlap 40, min 50 | `scripts/build_kb.py` |

Đây là số của một snapshot, không phải hằng số của repo: rebuild KB là đổi cả ba
con số index. Implementation hybrid retrieval hiện hành là
`src/acne_llm/rag/retriever.py`; tham chiếu `rag/hybrid.py` trong tài liệu cũ
không còn đúng.

Các bất biến dữ liệu:

- mỗi chunk phải giữ provenance đủ để truy nguồn;
- filter chất lượng/chủ đề xảy ra trước index;
- dense và sparse index phải được build từ cùng snapshot chunks;
- đổi chunking/normalization phải invalidate index/cache liên quan;
- không suy ra số chunk hiện tại từ report cũ, phải đọc live artifact/KB stats;
- raw data, cache, SQLite và GGUF lớn không mặc định là Git source.

## 9. Config contract hiện hành

Default canonical ở `src/acne_llm/config.py`. Các giá trị quan trọng tại thời
điểm xác minh:

| Nhóm | Key/default |
|---|---|
| Generator | `LLM_MODEL=acne-generator-v2`, context 8192, predict 2048 |
| Intake | `INTAKE_MODEL=acne-intaker`, `INTAKE_TIMEOUT=120` |
| Embedding | `AITeamVN/Vietnamese_Embedding` |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Semantic route | k=9, OOS distance=0.483609, ambiguity margin=0.08 |
| Chat retrieval | retrieve 25, rerank 5, guideline 5, safety 5 |
| Context filter | rerank floor 0.50, max context 6000 chars |
| Session | SQLite path `data/sessions.db`, TTL 1800 s |

Runtime intake contract chỉ còn `INTAKE_MODEL` và `INTAKE_TIMEOUT`. Các key
`INTAKE_MODE`, `ROUTER_*`, `EXTRACTOR_*` là legacy và không được đưa trở lại
active env example, Docker, startup log hay config docs.

Không copy mọi default vào `.env`: điều đó tạo hai nguồn truth. `.env` nên giới
hạn ở secret, URL/model và override thực sự phụ thuộc deployment.

Parity gói deploy và gói eval đã được khóa ngày 2026-08-24. Trước đó default là
`acne-generator` dựng từ `Modelfile.full`, tức GGUF round 1 kèm một system prompt
khác — không con số eval nào đo trên nó. Nay toàn bộ default cùng trỏ vào đúng
gói đã được chấm:

| Nơi | Giá trị |
|---|---|
| `config.py::llm_model` | `acne-generator-v2` |
| `docker-compose.yml` (2 chỗ) | `${GENERATOR_MODEL_NAME:-acne-generator-v2}` |
| `docker/ollama-init.sh` | dựng từ `acnellm-role-v2.Q4_K_M.gguf` + `Modelfile` |
| `.env.baseline`, `.env.docker.example` | `acne-generator-v2` |

`model/generator/Modelfile` là biến thể đã được chấm: `FROM
./acnellm-role-v2.Q4_K_M.gguf` và `SYSTEM` khớp `system_prompt.v4.a.txt`
(sha256 `5421f207…`), đúng `generator_system_prompt_sha256` ghi trong protocol
của `v2_full`. `Modelfile.full` giữ lại như artifact round 1, **không** dùng cho
deployment.

Bất biến mới: đổi model generator là phải đổi đồng thời năm chỗ trên và ghi lại
sha của system prompt; lệch một chỗ là runtime chạy một model mà báo cáo mô tả
model khác.

Compose dùng biến `INTAKE_MODEL_NAME` ở tầng orchestration
(`docker-compose.yml`, `docker/ollama-init.sh`) rồi map sang `INTAKE_MODEL` cho
backend. Đổi tên intake model phải sửa cả hai chỗ, nếu không init sẽ pull một
tên còn app đọc một tên khác.

## 10. API và deployment surface

Các route chính:

| Endpoint | Ghi chú |
|---|---|
| `GET /api/v1/chat/stream` | endpoint sản phẩm, SSE |
| `POST /api/v1/chat/feedback` | feedback |
| `GET /api/v1/health` | Ollama/KB readiness |
| `GET /api/v1/models` | model discovery |
| `/api/v1/kb/*` | retrieve/search/stats/chunk inspection |
| `GET /api/v1/debug/trace` | admin-protected, dừng trước generator |
| `/api/v1/admin/*` | audit/session/feedback, admin-protected |
| `GET /metrics` | Prometheus |

`ADMIN_API_KEY` bảo vệ dữ liệu nhạy cảm. Để trống là fail closed cho admin/debug.
`API_KEY` toàn cục mặc định trống vì native browser EventSource không gắn được
custom header; bật nó mà không đổi transport sẽ làm chat SSE thất bại.

Compose có các service: Ollama, init model, backend `acne-llm`, frontend và
Nginx gateway. Backend/Ollama nằm trong network nội bộ; gateway là surface cho
browser. GPU dùng overlay `docker-compose.gpu.yml`; CPU vẫn chạy nhưng inference
có thể rất chậm.

## 11. Evaluation: thiết kế và ranh giới bằng chứng

### 11.1 Ba lane

Harness tracked nằm ở `research/evaluation/`:

1. **Intake eval**: schema/parse, intent classification, extraction field metrics,
   latency; ép không fallback để đo đúng Intaker.
2. **Retrieval eval**: LLM judge chấm relevance, precision, sufficiency, ranking
   và groundedness; không dùng lexical overlap làm proxy chính.
3. **Ablation**: thay/tắt từng khâu bằng arm ba ký tự `[intake][RAG][generator]`,
   với `R`=real, `O`=oracle, `N`=off (chỉ RAG).

Các arm thường dùng:

| Arm | Ý nghĩa |
|---|---|
| `RRR` | hệ thống thật làm baseline |
| `RNR` | tắt RAG |
| `ROR` | oracle retrieval context |
| `ORR` | oracle intake |
| `RRO` | oracle/frontier generator |
| `RNO` | generator mạnh khi tắt RAG |

Safety failure phải báo riêng với quality score. Một row fail safety có thể bị
loại khỏi paired quality comparison; vì vậy không được cộng hoặc suy luận chéo
hai tập bằng chứng như thể cùng sample population.

### 11.2 Artifact chuẩn hiện hành: `v2_full`

`research/evaluation/reports/v2_full/` là report set cuối cùng và canonical.
`summary.json` ghi cả bốn step `ok` (preflight, intake, retrieval, ablation),
chạy từ `2026-08-21T20:14:49Z` đến `2026-08-22T09:56:47Z`. Đây là run đầu tiên
có đủ ba lane thật, khác với các folder chỉ chạy một phần.

Protocol của run: model được chấm là `acne-generator-v2`, frontier reference là
`gpt-5.6-terra`, judge là `gpt-5.6-luna`. Preflight đã cảnh báo judge cache đang
chứa điểm của các judge khác, nên **không được gộp row/cache của `v2_full` với
artifact chấm bằng judge cũ** — khác judge là khác thang điểm.

Intake lane: xem mục 5.2 (1.490/1.500 row single-turn, 0 fallback).

Retrieval lane: 120 case, trong đó 29 case no-context. Context relevance
2,5919/5; precision 0,5344; sufficiency 2,8462/5; ranking quality 0,9365.
Relevance và sufficiency dùng rubric 0–5. Ranking quality là nDCG do judge suy
ra trên context cuối, tức chỉ số của cả pipeline chứ không phải phép đo riêng
của BGE reranker.

Ablation lane: 145 câu hỏi × 6 arm = 870 row, answer quality theo rubric 1–5.
Baseline `RRR` (hệ thật, local) đạt 2,7793/5. Hiệu ứng paired so với `RRR`, đã
loại các row mà một trong hai arm fail safety:

| Arm | Δ so với `RRR` | 95% CI | n paired |
|---|---:|---|---:|
| `RNO` (tắt RAG, generator mạnh) | +0,8214 | [0,6696; 0,9645] | 112 |
| `RRO` (oracle/frontier generator) | +0,7248 | [0,5688; 0,8807] | 109 |
| `ROR` (oracle retrieval) | +0,4118 | [0,2353; 0,5882] | 68 |
| `RNR` (tắt RAG) | +0,0185 | [-0,0833; 0,1204] | 108 |
| `ORR` (oracle intake) | -0,0194 | [-0,1165; 0,0777] | 103 |

Safety failure thô (đếm riêng, không nằm trong paired quality, trên 145 row):
`RRR` 32, `RNR` 26, `ORR` 24, `RRO` 16, `RNO` 13; `ROR` 18 nhưng chỉ trên 100 row
thành công.

Ba bất đối xứng của run được `results.json` ghi thẳng và phải nhắc kèm mỗi khi
trích số:

- `ROR` fail 45/145 row (thiếu oracle context) nên paired n chỉ còn 68; +0,4118
  là hiệu ứng trên tập con dễ hơn, không phải trên toàn bộ 145 câu;
- `RRO`/`RNO` chạy bằng `gpt-5.6-terra` với `temperature_policy =
  temperature_unsupported_three_runs` (provider từ chối `temperature=0`), trong
  khi các arm local dùng `temperature=0`; một phần khoảng cách generator có thể
  đến từ đây;
- `ORR` có 25 case oracle intake với zero field và 1 row failed, nên "oracle
  intake" trong run này không phải intake hoàn hảo cho mọi câu.

Kết luận được phép giữ trong phạm vi run này:

- generator là trục chi phối chất lượng; oracle retrieval có lợi ích thật nhưng
  nhỏ hơn; oracle intake và tắt RAG đều không tách khỏi 0 về mặt chất lượng;
- oracle intake không cải thiện điểm chất lượng nhưng vẫn giảm safety failure
  (32 → 24), nên giá trị của intake nằm ở an toàn/độ đúng field chứ không ở
  điểm answer quality; kết luận cũ theo trục
  `generator >> intaker >> retriever` đã bị `v2_full` thay thế;
- `RNR` gần 0 nghĩa là trong đúng dataset/model này RAG không cải thiện điểm
  quality trung bình; không được đọc thành "RAG vô dụng" hay "RAG luôn an toàn
  hơn", và không được lấy hiệu `RRO − RNO` làm hiệu ứng nhân quả của RAG;
- toàn bộ 145 mẫu generator có `source_provenance=synthetic_deepseek`,
  `annotation_status=synthetic_pending_review`, `generator_model=deepseek-v4-pro`;
  chưa có review người và chưa có base-Qwen control, nên loss giảm khi fine-tune
  không tự chứng minh chất lượng câu trả lời tốt hơn;
- judge chưa được calibration bởi người; latency/quality của lane T3 không thay
  thế đo endpoint SSE production.

Vì vậy `v2_full` chống đỡ được kết luận ở mức component theo đúng protocol đã
ghi. Nó **không** chứng minh T4/SSE parity, cũng không chứng minh clinical
readiness.

### 11.3 Artifact lịch sử `run_full_v3_2`

`research/evaluation/reports/run_full_v3_2/summary.json` ghi `preflight: ok`,
`intake: skipped`, `retrieval: skipped`, `ablation: ok`. Folder này chỉ là bằng
chứng cho một lần chạy ablation, và các file intake/retrieval nằm cùng folder là
artifact tồn dư từ run trước. Nó là `historical`: khi mâu thuẫn với `v2_full`
thì `v2_full` thắng. Các folder `full_eval_*`, `v1_round1`, `v2_round2`,
`rescore_*` cũng thuộc nhóm này và mỗi cái gắn với judge/dataset riêng.

### 11.4 Provenance của model và dataset được eval

Ledger `.audit/SLIDE_FACT_CHECK_2026-08-23.md` cố định các con số sau, và đây là
mức chi tiết phải giữ khi trình bày ra ngoài:

- Intaker: corpus cuối 4.000 record (3.600 train / 400 validation), gồm 836
  golden relabel và 3.164 sinh bằng GPT-4o-mini; overlap chính xác với eval set
  bằng 0. "4.000" là corpus sau lọc/purge, không phải số mẫu sinh ra.
- Intaker training: base `unsloth/Qwen2.5-3B-Instruct-bnb-4bit`, QLoRA r16/α32;
  best checkpoint 600, best val loss 0,0309; export
  `model/intaker/Qwen2.5-3B-Instruct.Q4_K_M.gguf`.
- Generator-v2: target 3.500 nhưng chỉ chấp nhận 3.077 record (2.616 train /
  246 validation / 215 holdout) và còn 3 post-validation failure. Trạng thái là
  **chưa hoàn tất**, không được nói đã đạt target.
- Generator-v2 training drift: notebook hiện khai 2 epoch, trainer state lưu
  lịch 3 epoch / 492 step với early stop ở step 450; adapter gốc khớp checkpoint
  300 (best val loss 0,7477). Đây là drift notebook/artifact, phải ghi như
  limitation chứ không "hòa giải" bằng giả định.

### 11.5 Hiệu chuẩn judge bằng người — arm RRR, n = 145

Ngày 2026-08-24 toàn bộ 145 hàng arm `RRR` của `v2_full` được một người chấm tay
theo đúng bốn trục và đúng rubric của `judges/rubrics.py`. Phiếu, file khoá,
script phân tích và kết quả nằm trong
`research/evaluation/reports/calibration_rrr/`.

**Phạm vi đã chốt.** Vòng hiệu chuẩn này khép lại ở đúng phạm vi trên: một arm,
một người chấm, bốn trục answer. Đó là một quyết định phạm vi có chủ đích, không
phải một hạng mục làm dở. Mọi mở rộng — người chấm thứ hai, chuyên gia da liễu
chấm lại, arm đối chứng, năm trục context — được ghi là hạn chế và hướng phát
triển ở cuối mục 11.6, và không được coi là điều kiện để đọc các số dưới đây.

Phiếu cho người xem **đúng những gì judge được xem** trong
`run_ablation.py::_judge_prompt`: câu hỏi, ngữ cảnh người dùng, ý mong đợi, điều
cấm, câu trả lời. Không xem tài liệu retrieval — judge cũng không, theo
`rubrics.BLIND_NOTE`. Không xem điểm judge, để tránh neo.

| Trục | κ | κ_quad | Gwet AC1 | Khớp | Khớp ±1 | Lệch người − judge |
|---|---:|---:|---:|---:|---:|---:|
| `answer_quality` | 0,4653 | 0,5338 | 0,521 | 60,7% | 89,0% | +0,297 |
| `incorrect_content` | 0,4049 | 0,5663 | 0,487 | 60,0% | 88,3% | −0,234 |
| `missing_content` | 0,2126 | 0,4099 | 0,276 | 43,4% | 90,3% | −0,448 |
| `role_tone` | 0,1829 | 0,3188 | 0,599 | 64,1% | 93,1% | −0,228 |

Theo ngưỡng repo tự đặt (κ_quad ≥ 0,61 mới là "đáng kể") thì **cả bốn trục đều
chưa đạt**; artifact `judge_calibration_rrr145.json` liệt kê cả bốn trong
`khong_du_tin_cay`. Kết luận đúng: điểm judge dùng được như tín hiệu và như thang
so sánh giữa các arm, **không** dùng được như phép đo tuyệt đối trích ra ngoài.

Phát biểu chính xác của con số này: đây là **mức đồng thuận giữa judge và một
người chấm cụ thể**, không phải "độ tin cậy của judge" nói chung. Vì chỉ có một
người chấm nên κ là một điểm ước lượng, chưa có khoảng và chưa biết thang có ổn
định giữa người với người hay không.

**Không trích riêng Cohen's κ.** RRR có marginal lệch nặng nên κ bị phạt theo κ
paradox: `role_tone` κ chỉ 0,183 nhưng AC1 0,599 và khớp ±1 bậc 93,1%. Trích cụm
κ + κ_quad + AC1 + khớp ±1, hoặc không trích gì.

Điểm chất lượng tuyệt đối theo người là **3,076/5**, cao hơn judge (2,779) 0,297
bậc. Quan trọng hơn trung bình là hình dạng phân bố:

| Bậc `answer_quality` | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| Người | 12 | 32 | 46 | 43 | 12 |
| Judge | 12 | 34 | **78** | 16 | 5 |

Judge dồn 54% vào bậc 3 và không tách được bậc 3 với bậc 4. Trên
`missing_content` còn nén mạnh hơn: 100/145 hàng (69%) đều bị gán bậc 2. Vì vậy
**độ phân giải thực tế của judge thấp hơn thang danh nghĩa**, và đây là một phần
lý do κ thấp chứ không chỉ do marginal lệch.

### 11.6 Cổng an toàn: judge báo động giả nhiều

`safety_pass` trong `metrics/scorecard.py` gộp bốn thành phần, hai tất định và
hai do judge suy luận. Phiếu người cho phép đo riêng hai thành phần judge:

| Cờ | Judge gắn | Người xác nhận | Precision | Recall |
|---|---:|---:|---:|---:|
| `harmful_incorrect_content` (`incorrect_content ≥ 3`) | 14 | 11 | 0,50 | 0,64 |
| `forbidden_claim` | 19 | 10 | 0,42 | 0,80 |

Gộp lên cấp hàng, giữ nguyên hai thành phần tất định
(`missed_required_refusal`, `pregnancy_safety`):

- hệ thống báo **32** hàng safety fail;
- người xác nhận **24** hàng;
- cả hai cùng báo 20 · chỉ hệ thống báo 12 · chỉ người báo 4.

Nghĩa là số safety failure của `RRR` **cao hơn số người xác nhận khoảng 33%**, và
đồng thời vẫn bỏ sót 4 hàng người thấy có vấn đề. Đây là finding về **dụng cụ
đo**, không phải về hệ thống.

Hệ quả phải giữ khi trích số: kết luận "oracle intake giảm safety failure
32 → 24" chỉ hợp lệ trong thang judge, vì arm `ORR` chưa có phiếu người. Phần
đáng tin nhất của kết luận đó vẫn là thành phần tất định
`missed_required_refusal` 9 → 0. Con số 24 của người trên `RRR` **trùng số** với
24 của `ORR` theo judge — đây là trùng hợp, không được đọc thành "người xác nhận
RRR ngang ORR".

### Hạn chế của vòng hiệu chuẩn và hướng phát triển

Bốn điểm sau là **hạn chế đã biết**, phải nêu kèm mỗi khi trích số hiệu chuẩn;
đồng thời là hướng phát triển tiếp theo, không phải hạng mục còn nợ:

1. **Một người chấm.** Chưa có inter-annotator agreement nên chưa biết bốn trục
   có ổn định giữa hai người hay không. Cách mở rộng rẻ nhất: đưa lại đúng phiếu
   `cham_RRR_145.html` cho người thứ hai, không cần dựng gì mới.
2. **Người chấm không phải chuyên gia da liễu.** Vòng này kiểm được thang rubric
   và tính nhất quán của judge, **không** kiểm được tính đúng đắn lâm sàng. Muốn
   nói tới an toàn lâm sàng thì phải có bác sĩ chấm lại, và đó là một loại bằng
   chứng khác chứ không phải phiên bản tốt hơn của bằng chứng này.
3. **Chỉ arm `RRR`.** Không delta nào giữa các arm có bằng chứng người. Mọi kết
   luận so sánh trong mục 11.2 vẫn đứng trên thang judge.
4. **Năm trục context chưa đối chiếu.** `judges/context.py` chấm
   `context_relevance`, `context_precision`, `context_sufficiency`,
   `ranking_quality`, `groundedness` và chưa trục nào từng được người kiểm.

### 11.7 Invariant của eval

- dataset phải frozen/hash và artifact ghi rõ lineage;
- model/judge/prompt/version phải được ghi trong run metadata;
- đổi judge là đổi thang điểm, không trộn row/cache giữa hai judge;
- judge không thấy tên arm/model nếu điều đó gây bias;
- pairing phải theo sample ID của chính arm và ghi drop reason;
- eval không ghi vào production session/audit DB;
- bước `skipped` hoặc `failed` phải được trình bày đúng trạng thái;
- T3 ablation và T4/SSE production là hai tầng bằng chứng khác nhau.

## 12. Test và lệnh phát triển

Chạy bằng interpreter của repo để tránh nạp sai Chroma/embedding dependency:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Targeted chat pipeline:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_intake.py `
  tests/test_chat_stream.py `
  tests/test_intent_routing.py `
  tests/test_session.py `
  tests/chat -q
```

Evaluation:

```powershell
.\.venv\Scripts\python.exe -m evaluation.full_evaluation --smoke
.\.venv\Scripts\python.exe -m evaluation.full_evaluation
```

`tasks.sh` là facade cho bash/WSL; Windows dùng `scripts/*.ps1` hoặc gọi module
Python trực tiếp. Luôn đọc `./tasks.sh help` thay vì dựa vào số lượng command ghi
trong report cũ.

Không ghi số lượng test cố định vào context. Con số có thể đổi chỉ vì thêm/xóa
test; bằng chứng đúng là output pytest gắn với commit/worktree cụ thể.

## 13. Những thay đổi cần eval lại

Các remediation chỉ sửa wiring/docs/metadata không tác động normal answer path có
thể kiểm bằng unit/integration test. Những thay đổi sau là behavior change và
phải tách thành task/eval lane riêng:

| Nhóm | Ví dụ | Gate cần chạy lại |
|---|---|---|
| T4/SSE parity | temperature, seed, token limit, crisis prefix, suffix, persistence | test endpoint SSE riêng |
| Medication policy | phân biệt đang dùng với hỏi kiến thức, phủ định/người khác | false-positive/negative dataset |
| Intake/schema | strict JSON, tri-state, clinical mapping, confidence hedge | intake eval frozen, gồm bộ 1.490 mẫu khi áp dụng roadmap đó |
| Query/RAG | accent, negation stopword, BM25 invariant, score/boost, Unicode heading, cache | retrieval eval + affected ablation arms |
| Generation/safety | dose regex, urgency, final normalization | generator/T3 + T4/SSE safety |
| Session/data | snapshot, history window, TTL/version, audit/schema | multi-turn, persistence, concurrency |

Roadmap chi tiết và rationale audit nằm trong `.audit/FUTURE_BEHAVIOR_ROADMAP.md`
của worktree. Context này vẫn tự chứa các invariant quan trọng để đọc được khi
không có thư mục đó.

Các artifact lớn phục vụ reproducibility được publish thành GitHub Release thay
vì Git blob, index tại `docs/RELEASE_ARTIFACTS.md`:

| Release | Nội dung |
|---|---|
| `knowledge-2026-08-23` | `audit-run-20260822T152307Z.zip`, vault Obsidian, SHA256SUMS |
| `kb-v2-2026-08-23` | snapshot KB runtime + `kb-v2-MANIFEST.json` |
| `models-v2-2026-08-23` | GGUF/LoRA/Modelfile của Intaker và Generator + manifest hash |

Thứ tự restore: clone branch → verify model release và ghép lại Generator GGUF →
verify KB release và khôi phục `data/` → (tùy chọn) import vault → chạy test và
eval trước khi coi môi trường khôi phục là tương đương.

## 14. Các bẫy kiến trúc cần tránh

1. **Đừng dựng lại hai intake LLM.** `llm_router` và `llm_extractor` chỉ là alias
   compatibility cùng trỏ đến một Unified Intaker.
2. **Đừng gọi similarity là probability.** Semantic confidence chưa calibration.
3. **Đừng gọi mọi regex là guardrail.** Xác định consumer hành vi trước.
4. **Đừng bỏ semantic/rule fallback.** Chúng giữ hệ thống hoạt động khi model hoặc
   JSON lỗi và không tạo thêm LLM call.
5. **Đừng dùng debug trace thay cho SSE eval.** Trace dừng trước generation,
   suffix và persistence.
6. **Đừng dùng report cũ để mô tả worktree mới.** Kiểm step status và git lineage.
7. **Đừng trộn data/index snapshot.** Rebuild/invalidate cả dense, sparse và cache
   khi chunk contract đổi.
8. **Đừng đưa in-memory store vào production.** Production truth là SQLite DI.
9. **Đừng sửa archive để “làm sạch grep”.** Archive/history được phép nói về kiến
   trúc cũ nếu được đánh dấu rõ.
10. **Đừng coi full pytest là full eval.** Chúng trả lời hai câu hỏi khác nhau.
11. **Đừng để deploy lệch eval trở lại.** Parity đã khóa ngày 2026-08-24: mọi
    default đều là `acne-generator-v2` dựng từ `Modelfile` + `acnellm-role-v2`.
    Report cũ hơn ngày đó mô tả `acne-generator` là mặc định — đúng ở thời điểm
    của chúng, `historical`, không phải trạng thái hiện tại.
12. **Đừng coi cờ safety của judge là sự thật.** `harmful_incorrect_content` và
    `forbidden_claim` có precision 0,50 và 0,42 khi đối chiếu người; tách safety
    đo được (refusal routing, pregnancy) khỏi safety do judge suy luận.
13. **Đừng trích riêng Cohen's κ trên arm đơn.** Marginal lệch làm κ tụt giả;
    luôn kèm κ_quad, Gwet AC1 và tỉ lệ khớp ±1 bậc.
14. **Đừng gộp artifact khác judge.** Judge cache có thể chứa điểm của judge cũ;
    đổi judge là đổi thang, phải ghi ra thư mục report mới.

## 15. Checklist xác minh một thay đổi

Trước khi merge một thay đổi pipeline:

1. ghi baseline branch/commit và dirty state;
2. chỉ rõ file/function và normal/fallback path bị ảnh hưởng;
3. xác định input/output contract thay đổi hay không;
4. chạy targeted tests;
5. chạy full pytest bằng repo venv;
6. nếu behavior/model/data đổi, chạy đúng eval lane và artifact mới;
7. kiểm endpoint thật nếu claim liên quan SSE/runtime;
8. ghi model, dataset, judge, config và drop reason;
9. cập nhật README/context nếu invariant public đổi;
10. stage đúng scope, không cuốn theo DB/cache/report hoặc worktree change khác.

## 16. Chỉ mục source of truth

| Câu hỏi | File cần đọc trước |
|---|---|
| App khởi tạo gì? | `src/acne_llm/api/app.py`, `src/acne_llm/di.py` |
| Intake/fallback chạy thế nào? | `src/acne_llm/chat/intake.py`, `unified_intake.py`, `intake_contract.py` |
| Route/flag từ đâu? | `src/acne_llm/chat/routing/` |
| Retrieval/query/context? | `src/acne_llm/chat/_retrieval.py`, `src/acne_llm/rag/retriever.py` |
| Prompt được lắp thế nào? | `src/acne_llm/llm/prompt_builder.py`, `config/prompts/` |
| SSE/generator/persist? | `src/acne_llm/chat/runtime.py` |
| Safety nằm ở đâu? | `src/acne_llm/guardrails/runner.py`, `src/acne_llm/chat/_safety.py` |
| Session truth? | `src/acne_llm/chat/session/`, `src/acne_llm/db/session_store.py` |
| Default config? | `src/acne_llm/config.py` |
| KB được build ra sao? | `scripts/build_kb.py` |
| Eval chạy/đo gì? | `research/evaluation/README.md`, runners và artifact `summary.json` |
| Số eval nào là canonical? | `research/evaluation/reports/v2_full/` |
| Số liệu đã fact-check? | `.audit/SLIDE_FACT_CHECK_2026-08-23.md` |
| Kiến trúc/contract hiện hành theo audit? | `.audit/CURRENT_TRUTH.md`, `docs/ARCHITECTURE_TRUTH.md` |
| Snapshot audit vs source hiện tại? | `.audit/RECONCILIATION.md`, `.audit/STATUS.md` |
| Artifact lớn nằm ở đâu? | `docs/RELEASE_ARTIFACTS.md` |
| Judge có đáng tin không? | `research/evaluation/reports/calibration_rrr/` |
| Docker surface? | `Dockerfile`, `docker-compose.yml`, `docker-compose.gpu.yml` |

Tóm lại, kiến trúc bề mặt hiện đã thống nhất quanh một Unified Intaker, fallback
không LLM, hybrid RAG có điều kiện, một generator streaming, safety chia trách
nhiệm và SQLite session production. Bằng chứng đo lường đã tiến hai bước:
`v2_full` là run đầu tiên có đủ ba lane và đã fact-check; và tới 2026-08-24, toàn
bộ 145 hàng `RRR` đã được người chấm tay, nên lần đầu tiên repo biết **dụng cụ
đo của mình sai lệch bao nhiêu** thay vì chỉ biết kết quả nó trả về.

Phần chưa được phép nói chắc: chưa có eval nào chạy lại sau remediation
`0d9d9dd`; chưa có T4/SSE parity; deployment mặc định vẫn không cùng model với
protocol đã chấm; dữ liệu eval generator còn synthetic pending review; và hiệu
chuẩn người mới phủ **một arm, một người chấm** — chưa có agreement giữa hai
người, chưa có arm nào khác, chưa có trục context nào được đối chiếu. Muốn nâng
cấp các kết luận đó phải tạo artifact mới đúng lane, không sửa câu chữ để thay
thế phép đo.
