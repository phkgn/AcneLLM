# AcneLLM — Current Project Context

> Xác minh theo source và artifact trong active worktree ngày **2026-08-23**.
> Tài liệu này mô tả kiến trúc đang chạy, ranh giới dữ liệu/eval và các invariant
> cần giữ. Nội dung trong `docs/archive/`, `docs/history/`, patch audit cũ hoặc
> `model/legacy/` chỉ dùng để truy vết, không được ưu tiên hơn source hiện hành.

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
| `acne-generator` | viết câu trả lời từ prompt/context đã chuẩn bị | prose streaming |

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
| Generator | `LLM_MODEL=acne-generator`, context 8192, predict 2048 |
| Intake | `INTAKE_MODEL=acne-intaker`, `INTAKE_TIMEOUT=60` |
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

### 11.2 Artifact `run_full_v3_2`

`research/evaluation/reports/run_full_v3_2/summary.json` ghi rõ:

- preflight: `ok`;
- intake: `skipped`;
- retrieval: `skipped`;
- ablation: `ok`.

Do đó folder này là bằng chứng cho ablation đã chạy, không phải fresh full eval
cho cả ba lane. Các file intake/retrieval cùng folder có thể là artifact tồn dư
từ run trước và không được nhập nhằng với run metadata hiện tại.

Kết luận có thể giữ trong phạm vi ablation đã review:

- trục chất lượng quan sát được: `generator >> intaker >> retriever ≈ 0`;
- oracle intake sửa toàn bộ 8/8 ca refusal safety được phân tích, còn đổi
  generator không sửa các ca đó; đây là tín hiệu mạnh để ưu tiên độ chính xác
  của field thuốc/thai kỳ nhưng không chứng minh mọi safety lỗi đều do intake;
- oracle retrieval cải thiện coverage/sufficiency hơn là relevance/precision;
- so sánh RAG on/off trong run chỉ hỗ trợ kết luận theo điều kiện model/dataset
  của artifact, không đủ để tuyên bố RAG luôn an toàn hơn hoặc luôn vô ích;
- latency của ablation không thay thế đo endpoint SSE production.

Không được kết luận production readiness vì intake và retrieval đã skip, chưa có
parity đầy đủ giữa T4/SSE và generator evaluation, và judge cần calibration người
trước khi dùng số như bằng chứng phòng thủ bên ngoài.

### 11.3 Invariant của eval

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

Roadmap chi tiết và rationale audit nằm trong `.audit/` của worktree. Vì `.audit`
có thể chưa được publish cùng branch, context này tự chứa các invariant quan
trọng và không phụ thuộc vào việc người đọc có thư mục đó.

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
| Retrieval/query/context? | `src/acne_llm/chat/_retrieval.py`, `src/acne_llm/rag/` |
| Prompt được lắp thế nào? | `src/acne_llm/llm/prompt_builder.py`, `config/prompts/` |
| SSE/generator/persist? | `src/acne_llm/chat/runtime.py` |
| Safety nằm ở đâu? | `src/acne_llm/guardrails/runner.py`, `src/acne_llm/chat/_safety.py` |
| Session truth? | `src/acne_llm/chat/session/`, `src/acne_llm/db/session_store.py` |
| Default config? | `src/acne_llm/config.py` |
| KB được build ra sao? | `scripts/build_kb.py` |
| Eval chạy/đo gì? | `research/evaluation/README.md`, runners và artifact `summary.json` |
| Docker surface? | `Dockerfile`, `docker-compose.yml`, `docker-compose.gpu.yml` |

Tóm lại, kiến trúc bề mặt hiện đã thống nhất quanh một Unified Intaker, fallback
không LLM, hybrid RAG có điều kiện, một generator streaming, safety chia trách
nhiệm và SQLite session production. Phần chưa được phép nói chắc nằm ở hiệu năng
model/runtime sau remediation: muốn cập nhật kết luận đó phải tạo artifact eval
mới đúng lane, không sửa câu chữ để thay thế phép đo.
