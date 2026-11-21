# Phân tích Web Dashboard trong Evaluation Module (AcneLLM)

Tài liệu này giải thích **toàn bộ workflow, use case và function** của web dashboard tại `evaluation/dashboard/` — bằng ngôn ngữ gần gũi, kèm sơ đồ trực quan.

---

## 1. Dashboard này là gì, sinh ra để làm gì?

Hãy tưởng tượng bạn có một "phòng thí nghiệm" đánh giá AcneLLM gồm hàng chục lệnh Python (`full_evaluation`, `run_judge`, `report`, `check_gate`...). Bình thường bạn phải gõ tay từng lệnh trong terminal, tự mở file log, tự đọc file JSON kết quả. Dashboard chính là **phòng điều khiển (control room)** gom tất cả vào một giao diện web:

- Chạy các lệnh eval bằng nút bấm (chỉ lệnh trong **whitelist**, không cho gõ lệnh tùy ý).
- Xem log **real-time** khi lệnh đang chạy, kill lệnh khi cần.
- Đọc kết quả (metrics, so sánh hệ thống, gate pass/fail) từ file JSON/JSONL có sẵn — **không bịa metric**.
- Duyệt (review) dataset 7 bộ dữ liệu do máy sinh ra trước khi "đóng băng" thành bộ test chính thức.
- Chọc thử (probe) semantic router bằng câu hỏi bất kỳ.

Đặc điểm quan trọng:

- Là **Next.js 15 (App Router) + TypeScript + Tailwind**, chạy local tại `127.0.0.1:3100`, không có auth vì chỉ dùng trên máy cá nhân.
- **Read-only với dữ liệu**: Node chỉ đọc artifact do Python tạo ra; mọi việc "tính toán thật" đều do Python làm.
- **An toàn**: mọi lệnh spawn với `shell: false` + argv array (không dính shell injection), mọi path đều bị ép nằm trong `evaluation/`.

---

## 2. Bản đồ tổng thể

```
┌─────────────────────── Trình duyệt (React clients) ───────────────────────┐
│ Overview │ Runs │ Results │ Figures │ Inspect │ Review │ Router Probe     │
└─────┬─────────────────────────────────────────────────────────────────────┘
      │ fetch / SSE (EventSource)
┌─────▼─────────────────── Next.js API routes (Node) ───────────────────────┐
│ /api/status /api/overview /api/meta /api/jobs /api/progress /api/results  │
│ /api/validation /api/files /api/inspect /api/probe/semantic               │
│ /api/datasets/review (+/export)  /api/jobs/[id]/kill  .../logs/stream     │
└─────┬───────────────────────────┬─────────────────────────────────────────┘
      │ spawn (whitelist)         │ đọc file JSON/JSONL
┌─────▼──────────────┐    ┌───────▼────────────────────────────┐
│ Python harness     │───▶│ evaluation/reports/** (artifacts)  │
│ evaluation.full_evaluation │    │ evaluation/datasets/** (data)      │
│ judges, analysis…  │    │ dashboard/logs/<jobId>.log         │
└────────────────────┘    └────────────────────────────────────┘
```

Luồng cốt lõi chỉ có một: **UI → API → spawn Python (ghi log + artifact) → UI đọc lại artifact/log và hiển thị**.

---

## 3. Bảy trang (7 use case chính)

### 3.1 Overview `/` — "Phòng kiểm tra trước chuyến bay"

Component: `DashboardClient.tsx`. Trả lời câu hỏi: *"Máy mình đã sẵn sàng chạy eval chưa, và tình hình chung thế nào?"*

Gồm 4 khối:

1. **Preflight (Runtime readiness)** — gọi `GET /api/status`, kiểm tra 10 dependency: Ollama có chạy không, 2 model (`acnellm-v2-q4`, `qwen25-base-acnesys`) đã có chưa, Chroma DB, BM25 index, các dataset seed kiểm thử module/đánh giá retrieval/sinh câu trả lời batch, và OpenAI judge key. Mỗi mục fail đều kèm **lệnh fix copy được** (ví dụ `ollama serve`). Lưu ý: API chỉ trả *boolean* cho API key, không bao giờ lộ secret.
2. **Quick launch** — 4 nút: `Quick preliminary Bộ chất lượng câu trả lời` (preset 30–140 mẫu, xem mục 5), `Smoke run all` (chạy nhanh với Bộ dev), `Run all full`, `Run harness tests` (pytest).
3. **Jobs đang chạy** — hiển thị PID, thời gian chạy, nút xem log (nhảy sang `/runs?job=...`) và nút Kill.
4. **Regression gates + Last run** — đọc `gate_check.json` (pass/fail từng metric so với ngưỡng trong `gate.yaml`) và `full_evaluation_last.json` (bước nào OK/FAIL ở lần orchestrator gần nhất), kèm dung lượng judge cache.

### 3.2 Runs `/runs` — "Bàn điều khiển chạy lệnh + xem log"

Component: `RunsClient.tsx` (~1200 dòng, trang phức tạp nhất). Use case: *chọn một lệnh trong catalog, điền tham số, bấm chạy, theo dõi log trực tiếp*.

**Catalog 16 lệnh** (mỗi lệnh một form tham số riêng):

| Nhóm | Lệnh | Chạy gì |
|---|---|---|
| Orchestrator | `full_evaluation` | Toàn pipeline kiểm thử module→report; hỗ trợ `--smoke`, `--skip`, đổi dataset |
| Preset | `preliminary_d2` | Quick run Bộ chất lượng câu trả lời synthetic (mục 5) |
| đánh giá retrieval | `retrieval_eval` | Ablation retrieval: sparse/dense/hybrid/rerank/MMR |
| sinh câu trả lời batch | `answer_generation` | Sinh câu trả lời cho 5 hệ thống năm cấu hình hệ thống, chọn output dir, resume được |
| Judge ($) | `judge` | LLM judge pointwise + pairwise (tốn phí API) |
| Analysis | `report`, `check_gate` | Tổng hợp metric / so gate.yaml |
| Trust | `trust_audit` | Audit data/runtime/invariants/judge + reproducibility |
| Figures | `figures_kb/eval/usage/all` | Sinh biểu đồ (mục 3.4) |
| Khác | `intake_eval`, `bottleneck` (arm z/x/y/w), `tests` | Eval intake, thí nghiệm bottleneck, pytest |

**Theo dõi:**

- Log stream qua **SSE** (`/api/jobs/[id]/logs/stream`): server tail file log bằng `fs.watch` + polling 1 giây (cho ổn định trên Windows), đẩy từng chunk về trình duyệt.
- **Progress bar sinh câu trả lời batch**: gọi `GET /api/progress`, đếm số dòng trong `s*.results.jsonl` so với tổng mẫu, tính % và **ETA** từ thời gian trung bình mỗi mẫu.
- **Validation watch**: theo dõi `reports/validation/**/summary.json` mới nhất, hiển thị verdict TRUSTWORTHY / PARTIAL / NOT_TRUSTWORTHY.
- **Kill job**: UI chuyển sang `stopping` ngay; backend dùng `taskkill /T /F` (Windows) hoặc `SIGTERM` (Unix), chỉ chốt `killed` khi process tree chết thật.

### 3.3 Results `/results` — "Bảng điểm tổng hợp"

Component: `ResultsClient.tsx`. Use case: *sau khi chạy xong, xem hệ thống nào tốt hơn*.

Gọi `GET /api/results?experiment=...` — API gom một lượt 7 nguồn:

- `report.json` + `run_meta.json` của run được chọn (metrics từng system, paired comparisons kèm p-value).
- Unit reports kiểm thử module (normalizer, intent, planner, guardrails).
- Kết quả retrieval đánh giá retrieval mới nhất.
- Gate check, validation summary mới nhất, và kết quả bottleneck.

UI vẽ bảng so sánh năm cấu hình hệ thống theo từng trục metric. Nguyên tắc: **chỉ hiển thị dữ liệu có thật trong artifact** — không có file thì hiện empty state, không tự chế số.

### 3.4 Figures `/figures` — "Xưởng biểu đồ"

Component: `FiguresClient.tsx`. Use case: *sinh và xem toàn bộ hình cho báo cáo/luận văn*.

- 6 nhóm hình: **A** KB & Corpus, **B** Finetune Data, **C** Model & Latency, **D** Usage, **E** Diagrams (Mermaid tĩnh, không cần generate), **F** Eval Results.
- Mỗi nhóm (trừ E) đọc một `manifest.json` do Python generator tạo; mỗi entry là PNG hoặc chart JSON (UI tự vẽ bar/line/scatter/heatmap bằng component riêng).
- Nút "generate/export tất cả" chạy **một job `figures_all`** để cả A–F dùng chung `generation_id`; hỗ trợ xuất PDF vector.
- Quy tắc sạch sẽ: generator luôn compute vào **staging rỗng rồi publish nguyên snapshot** — không trộn hình cũ với hình mới; Next.js không bao giờ đọc trực tiếp Chroma hay DB, chỉ đọc manifest + file hình.

### 3.5 Inspect `/inspect` — "Kính hiển vi soi từng mẫu"

Component: `InspectClient.tsx`. Use case: *tại sao mẫu này sai? Hệ thống trả lời gì, retrieval lấy chunk nào?*

- Danh sách mẫu của một run + system (phân trang 50, tìm kiếm), cờ `flagged` cho mẫu lỗi/fallback.
- Click vào một mẫu: xem câu hỏi, câu trả lời đầy đủ, trace (chunk retrieve/final), judge scores, và **diff với system khác** (tham số `compare`).
- **Chẩn đoán lỗi tự động** (`lib/inspect.ts → sampleErrorCodes`) — gắn mã lỗi cho từng mẫu:
  - `E22_infra` — run lỗi hạ tầng (`ok !== true`); `E22_fallback` — phát hiện câu trả lời fallback.
  - `E21_parse_failure` — LLM không parse được structured output.
  - `E15_unsafe_recommendation` — câu trả lời chứa forbidden claim.
  - `E04_retrieval_miss` — retrieval không lấy được chunk relevant nào; `E06_rerank_or_filter_drop` — retrieve trúng nhưng bị rerank/filter loại mất.

### 3.6 Review `/review` — "Bàn duyệt dataset 7 bộ dữ liệu của con người"

Component: `DatasetReviewClient.tsx` (lớn nhất, ~1245 dòng). Use case: *dataset draft do máy sinh phải qua tay người duyệt trước khi thành bộ test chính thức*.

7 dataset: **Bộ dev** dev, **Bộ chất lượng câu trả lời** main test, **Bộ ca khó** challenge, **Bộ an toàn** safety, **Bộ nhiều lượt** multi-turn, **Bộ ngoài phạm vi** OOD, **Bộ đối kháng** adversarial. Bộ dev đọc từ `datasets/v1/`, còn lại từ `datasets/drafts/v1/`.

**Vòng đời một mẫu:**

```
draft (pending) ──▶ approved ─┐
        │                     ├──▶ khi CẢ split sạch (không còn pending/
        ├──▶ needs_edit ──────┘     needs_edit/stale) ──▶ Export JSONL
        ├──▶ rejected (loại khỏi export)
        └──▶ stale (draft bị regenerate sau khi đã duyệt → phải duyệt lại)
```

Cơ chế đáng chú ý:

- Quyết định lưu vào `.dataset-reviews.json` **kèm SHA-256 hash của dòng gốc** → nếu file draft bị sinh lại, hash lệch, mẫu tự thành `stale`. Không bao giờ sửa trực tiếp file draft.
- Người duyệt được **sửa 12 field** (user_query, expected_answer_points, forbidden_claims, ...); chỉ diff so với gốc mới được lưu.
- **Validation từng dataset**: mỗi D có luật riêng (ví dụ Bộ ca khó phải `difficulty=hard` + ≥3 answer points; Bộ an toàn phải `task_type=safety` + risk high/critical; Bộ ngoài phạm vi/Bộ đối kháng phải `intent_label=reject`). Mẫu còn lỗi thì **không approve được**.
- Ghi file an toàn: write vào `.tmp` → backup file cũ → rename (atomic); các thao tác ghi xếp hàng qua `writeQueue` để tránh race.
- **Export** (`/api/datasets/review/export`): chỉ khi split `readyToExport`, tải về JSONL các mẫu approved (gắn `dataset_version`, `annotation_status`), để copy vào `evaluation/datasets/v1/`. Chưa xong thì trả HTTP 409 kèm thống kê còn thiếu.

### 3.7 Router Probe `/probe` — "Máy chẩn đoán semantic router"

Component: `ProbeClient.tsx`. Use case: *gõ một câu tiếng Việt bất kỳ và xem router phân loại thành intent gì, vì sao*.

- Gọi `POST /api/probe/semantic` → chạy **đồng bộ** `python -m evaluation.probe.semantic_probe --text ... --json` (timeout 180s vì lần đầu phải load model embedding).
- Hiển thị: **verdict intent** (advise/knowledge/clarify/reject), cổng OOS, vote scores, cổng ambiguity, và bảng **k câu train gần nhất** (neighbors) — giúp hiểu router "nghĩ" thế nào.
- Cho **override live**: `k` (mặc định 9), ngưỡng `oos` (0.4836), `margin` (0.08); có `--expect` để kiểm tra pass/fail và **chế độ batch** nhiều dòng.
- API bóc dòng JSON cuối cùng từ stdout (bỏ qua log tạp), map lỗi thành 400/502/504 rõ ràng.

---

## 4. Backend: từng file `lib/` làm gì

### `paths.ts` — Cảnh sát đường dẫn (nền tảng bảo mật)

- `locateRepoRoot()` tự tìm gốc repo (dò file `evaluation/full_evaluation.py` khi đi ngược lên).
- `resolveEvaluationPath()` — chặn path tuyệt đối, null byte, `..`; ép mọi path nằm trong `evaluation/`.
- `assertRealPathInsideEvaluation()` — resolve cả **symlink** để chặn trò symlink trỏ ra ngoài.
- `resolveWhitelistedRepoVisual()` — ngoại lệ duy nhất: 2 file HTML visual ở gốc repo được phép serve.
- `assertSafeName()` — tên chỉ được `[a-zA-Z0-9._-]`.

### `commands.ts` — Nhà máy lệnh whitelist (573 dòng, trái tim bảo mật)

Function chính `buildCommand(commandId, args)`:

1. `commandId` phải nằm trong 20 ID của `command-ids.ts` — không thì ném lỗi.
2. Mỗi tham số qua validator riêng: `optionalLimit` (1–100000), `stringList` so với Set cho phép (systems chỉ s0–s4, retrieval modes 5 giá trị...), `pairList` (dạng `s0:s1`), `datasetPath` (phải là `.jsonl` thật trong `evaluation/datasets/`), `reportRunDir`/`outputRunDir` (phải trong `evaluation/reports/`, realpath-check chống symlink).
3. Regex `FORBIDDEN = /[;&|`$><\r\n]/` chặn ký tự shell trong mọi string; riêng `probeText` nới lỏng (tiếng Việt tự do, tối đa 2000 ký tự, 1 dòng) vì spawn bằng argv + `shell:false` nên metacharacter vô hại.
4. Trả về `{executable, argv, display, normalizedArgs}` — chọn Python trong `.venv` nếu có.

### `jobs.ts` — Quản lý vòng đời process

- Registry giữ trong memory (global, sống qua hot-reload) + persist ra `.jobs.json`.
- `startJob()` — build command, tạo `jobId`, mở log stream `logs/<jobId>.log`, spawn với env tắt màu (`NO_COLOR`, `TERM=dumb`) để log sạch, pipe stdout/stderr vào file, đăng ký handler `close`/`error` để chốt trạng thái.
- `listJobs()` — mỗi lần gọi đều **kiểm tra PID còn sống** (`process.kill(pid, 0)`); job "running" mà PID chết → chuyển `exited` (tự chữa sau khi dashboard restart).
- `killJob()` — chuyển `stopping` → taskkill/SIGTERM → chốt `killed`; nếu kill fail mà process vẫn sống thì trả về `running` và báo lỗi.
- Trạng thái: `running → stopping → killed`, hoặc `running → succeeded/failed/exited`.

### `dataset-review.ts` + `dataset-review-catalog.ts` — Toàn bộ nghiệp vụ review (đã mô tả ở 3.6)

Function chính: `loadReviewItems()` (ghép draft + quyết định), `validateReviewCandidate()` (luật per-dataset), `saveReviewDecision()` (ghi atomic qua queue), `summarizeReview()` (đếm pending/approved/stale, tính `readyToExport`), `exportApprovedDataset()`.

### Các lib nhỏ còn lại

| File | Vai trò |
|---|---|
| `sse.ts` | `createTailStream()` — tail file thành SSE stream: đọc 256KB cuối, rồi fs.watch + poll 1s, heartbeat 15s, xử lý file bị truncate (event `reset`) |
| `catalog.ts` | Liệt kê datasets (`v1/*.jsonl` + số dòng + cờ frozen), systems (YAML configs), experiments, danh sách run trong `reports/` |
| `gates.ts` | `normalizeGateArtifact()` — chuẩn hóa `gate_check.json` thành danh sách check pass/fail + summary |
| `results.ts` | `latestRetrievalResult()` (folder mới nhất theo mtime), `readUnitReports()` (4 report kiểm thử module) |
| `validation.ts` | `latestValidationSummary()` — summary validation mới nhất, lọc theo mốc thời gian |
| `figures.ts` | Định nghĩa 6 nhóm figure + `parseFigureManifest()` validate manifest |
| `inspect.ts` | `sampleErrorCodes()` — gán mã lỗi E04/E06/E15/E21/E22 (xem 3.5) |
| `judge-calibration.ts` | Đọc `judge_bias_tests.json` → judge đã calibrate chưa, check nào fail |
| `preliminary.ts` | Validate limit Quick Run (30–140, mặc định 140) |
| `status.ts` | Gom tên model Ollama (cả tên có tag lẫn không) để tra cứu |
| `files.ts` | Tiện ích đọc JSON/JSONL an toàn (dòng JSONL hỏng do đang ghi dở → bỏ qua), đếm dòng |
| `command-flags.ts`, `command-ids.ts`, `types.ts` | Flag helper, danh sách 20 command ID, type chung (JobRecord, CommandId...) |

---

## 5. Workflow đặc biệt: Quick Preliminary Bộ chất lượng câu trả lời

Preset "một nút chạy cả pipeline nhỏ" (`scripts/run_preliminary_d2.py`), dành cho lúc muốn so sánh nhanh năm cấu hình hệ thống mà chưa cần run chính thức:

```
Bấm nút (limit 30–140 mẫu)
  → tạo run directory riêng: reports/prelim_d2_<timestamp>/
  → preflight → sinh câu trả lời batch generation năm cấu hình hệ thống (dataset answer_quality_test.jsonl)
  → judge pointwise + pairwise (s0:s1, s0:s2, s1:s3, s2:s3)
  → faithfulness (GPT-5 nano mặc định) → report
  → ghi PRELIMINARY_NOTICE: "SYNTHETIC_ONLY — không dùng làm benchmark cuối"
```

Điểm hay: **không phải pipeline thứ hai** — nó gọi đúng các module sinh câu trả lời batch/judge/report của harness chuẩn, chỉ cô lập artifact vào folder riêng và gắn nhãn cảnh báo; bỏ qua Bộ retrieval và regression gate.

---

## 6. Tóm tắt API (cheat sheet)

| Endpoint | Method | Chức năng |
|---|---|---|
| `/api/status` | GET | 10 preflight check (Ollama, models, KB, datasets, judge key) |
| `/api/overview` | GET | full_evaluation_last.json + gates + size judge cache |
| `/api/meta` | GET | Catalog datasets/systems/experiments/runs + judge calibration |
| `/api/jobs` | GET/POST | Liệt kê job / khởi chạy lệnh whitelist |
| `/api/jobs/[id]/kill` | POST | Dừng job (kill process tree) |
| `/api/jobs/[id]/logs/stream` | GET (SSE) | Tail log real-time |
| `/api/progress` | GET | % hoàn thành + ETA của sinh câu trả lời batch theo từng system |
| `/api/results` | GET | Gộp report/units/retrieval/gates/validation/bottleneck |
| `/api/validation` | GET | Validation summary mới nhất |
| `/api/files` | GET | Đọc file read-only trong `evaluation/` (tail, raw PNG/PDF/HTML whitelist + CSP sandbox) |
| `/api/files/watch` | GET (SSE) | Watch một file bất kỳ trong `evaluation/` |
| `/api/inspect` | GET | List mẫu / chi tiết mẫu + error codes + compare 2 system |
| `/api/probe/semantic` | POST | Chạy đồng bộ semantic probe, trả JSON verdict |
| `/api/datasets/review` | GET/POST | List/filter/chi tiết mẫu review / lưu quyết định |
| `/api/datasets/review/export` | GET | Tải JSONL approved (409 nếu chưa duyệt xong) |

---

## 7. Triết lý thiết kế (để nhớ nhanh)

1. **Whitelist mọi thứ** — lệnh, path, tên, tham số; không có chỗ nào cho input tự do chạm shell hay filesystem ngoài `evaluation/`.
2. **Node hiển thị, Python tính toán** — dashboard không bao giờ tự tính metric hay ghi artifact eval; nó chỉ spawn + đọc.
3. **Sự thật nằm trong artifact** — không có file thì hiện empty state, không bịa số.
4. **Con người là cửa cuối của dataset** — draft máy sinh phải qua review + validation + hash chống stale mới được thành bộ test.
5. **Tự chữa lành** — PID check, atomic write + backup, SSE reset khi file truncate, job registry sống qua restart.
