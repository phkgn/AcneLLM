# PROMPT — Xây Eval Dashboard (Next.js) cho AcneLLM evaluation harness

> Copy toàn bộ prompt dưới đây vào Claude Code / agent, chạy từ repo root `AcneLLM/`.

---

Bạn là senior fullstack engineer. Xây một **web dashboard Next.js** để chạy, theo dõi
và debug bộ evaluation harness trong folder `evaluation/` của repo này. KHÔNG sửa bất
kỳ file nào trong `evaluation/` (trừ khi nêu rõ), KHÔNG đụng `frontend/` (đó là chat UI
production, chạy port 3000). Dashboard là app MỚI, độc lập.

## 0. Bối cảnh repo (đã xác minh — không cần khám phá lại)

- Harness: `evaluation/` — Python, chạy bằng module CLI từ repo root, Windows,
  venv tại `.venv\Scripts\python.exe` (fallback `python`).
- Các lệnh hợp lệ (WHITELIST — dashboard chỉ được chạy đúng các lệnh này):

| id | Lệnh | Ghi chú |
|----|------|---------|
| `run_all` | `python -m evaluation.run_all [--smoke] [--skip <csv>] [--dataset <path>] [--yes]` | orchestrator T1→T2→T3→judge→report |
| `t1_normalizer` | `python -m evaluation.unit.eval_normalizer` | |
| `t1_intent` | `python -m evaluation.unit.eval_intent_router --dataset evaluation/datasets/v1/t1_intent_seed.jsonl [--limit N]` | |
| `t1_planner` | `python -m evaluation.unit.eval_query_planner --dataset evaluation/datasets/v1/t1_intent_seed.jsonl [--limit N]` | |
| `t1_guardrails` | `python -m evaluation.unit.eval_guardrails --dataset evaluation/datasets/v1/t1_guardrails_seed.jsonl [--limit N]` | |
| `t2_retrieval` | `python -m evaluation.runners.run_retrieval --dataset evaluation/datasets/v1/d8_qrels_seed.jsonl [--modes <csv>] [--raw-query] [--limit N]` | |
| `t3_generation` | `python -m evaluation.runners.run_experiment --experiment evaluation/configs/experiments/main_2x2.yaml [--systems <csv>] [--limit N] --resume` | chạy LÂU (giờ), resume được |
| `judge` | `python -m evaluation.judges.run_judge --run-dir evaluation/reports/main_2x2_t3 --dataset <path> [--pairs <csv>] [--provider deepseek\|openai] [--limit N]` | tốn API $; tự chạy error_classify cho record điểm ≤2 |
| `judge_bias_tests` | `python -m evaluation.judges.bias_tests --run-dir <dir> --dataset <path> [--n N]` | position/length/consistency bias — output `evaluation/reports/judge_bias_tests.json` |
| `report` | `python -m evaluation.analysis.report --run-dir evaluation/reports/main_2x2_t3 --dataset <path>` | |
| `check_gate` | `python -m evaluation.analysis.check_gate [--run-dir <dir>]` | exit 1 nếu fail; output machine-readable `evaluation/reports/gate_check.json` |
| `check_contamination` | `python -m evaluation.datasets.check_contamination --test <path>` | output `<test>.contamination.json`, exit 1 nếu có mẫu flagged |
| `build_seeds` | `python -m evaluation.datasets.build_seeds` | |
| `freeze_datasets` | `python -m evaluation.datasets.registry freeze evaluation/datasets/v1` | |
| `tests` | `python -m pytest evaluation/tests -q` | |
| `validation_loop` | `python -m evaluation.validate.loop --run-dir <dir> --dataset <path> [--repro-subset N] [--strict]` | evaluation validation loop (xem docs/EVAL_VALIDATION_LOOP_PROMPT.md) — watch `evaluation/reports/validation/**/summary.json`; `--repro-subset 0` bỏ qua rerun tốn thời gian |
| `figures_kb` | `python -m evaluation.analysis.figures_kb [--sample 8000] [--pdf]` | A: KB/corpus + B: finetune data |
| `figures_eval` | `python -m evaluation.analysis.figures_eval [--run-dir <dir>] [--pdf]` | C: model/latency + F: eval results |
| `figures_usage` | `python -m evaluation.analysis.figures_usage [--pdf]` | D: anonymized production usage |
| `figures_all` | `python -m evaluation.generate_figures [--sample 8000] [--run-dir <dir>] [--pdf]` | canonical fresh A–F snapshot; không đọc/reuse figure artifacts cũ |

- Output files cần theo dõi (tất cả append/ghi trong lúc chạy):
  - `evaluation/reports/<experiment>/<system_id>.results.jsonl` — mỗi dòng 1 sample
    `{sample_id, system_id, ok, error, answer, timings_ms:{total}, model_name, run_at}`
  - `evaluation/reports/<experiment>/<system_id>.judged.jsonl` — `{sample_id, pointwise:{correctness, completeness, safety, relevance, fluency, instruction_following}, faithfulness:{n_claims, faithfulness, contradiction_rate, claims[]}, error_class:{codes[], primary_code} (chỉ có khi điểm ≤2)}`
  - `evaluation/reports/<experiment>/pairwise_*_vs_*.jsonl`
  - `evaluation/reports/<experiment>/run_meta.json`, `report.json`, `report.md`
  - `evaluation/reports/unit/{normalizer,intent_router,query_planner,guardrails}/report.json` + `per_sample.jsonl` + `failures.jsonl`
  - `evaluation/reports/retrieval/<timestamp>/summary.json` + `<mode>.per_query.jsonl`
  - `evaluation/reports/run_all_last.json` — kết quả orchestrator lần cuối
  - `evaluation/reports/figures/manifest.json` + `*/manifest.json` — một fresh
    snapshot có chung `generation_id`; generator dựng trong staging rồi thay toàn
    bộ output, nên JSON/PNG/PDF cũ không bao giờ được dùng làm input hoặc để sót.
  - `evaluation/reports/gate_check.json` — `{n_pass, n_total, checks:[{name, actual, threshold, pass}]}` — nguồn DUY NHẤT cho gate badges (dashboard KHÔNG tự tính gate, chỉ chạy lệnh `check_gate` rồi đọc file này)
  - `evaluation/reports/judge_bias_tests.json` — `{position_bias:{flip_rate, pass}, length_bias:{spearman_score_vs_length, pass}, consistency:{exact_agreement, pass}, targets}` — hiển thị banner cảnh báo "judge chưa calibrated" trên trang /results nếu file chưa tồn tại hoặc có mục pass=false
  - `evaluation/datasets/v1/*.contamination.json` — kết quả contamination check
  - `evaluation/reports/judge_cache.sqlite` — KHÔNG đọc, chỉ hiển thị size
  - `evaluation/reports/figures/**/manifest.json` — figure artifacts A–D/F;
    dashboard chỉ render JSON/PNG/PDF do Python generators tạo
- `report.json` per-system fields (bảng /results phải render đúng các cột này): `n, ok_rate, parse_success_rate, vacuous_answer_rate, citation_valid_rate, pregnancy_safety_rate, forbidden_claim_rate, judge_means{6 trục}, faithfulness_mean, latency_ms{p50,mean}, error_pareto[]`; `comparisons.<pair>.{correctness|safety}.{bootstrap:{mean_diff,ci95,significant}, wtl_b_vs_a, cliffs_delta}` + `holm_correction`.
- Ngưỡng pass/fail: `evaluation/configs/gate.yaml` (yaml, keys: retrieval/generation/safety/unit)
- System configs: `evaluation/configs/systems/s0..s4.yaml`; experiment: `evaluation/configs/experiments/*.yaml`
- Datasets: `evaluation/datasets/v1/*.jsonl` (+ `MANIFEST.json` nếu đã freeze)
- Tiến độ 1 run T3 = số dòng trong `results.jsonl` / số dòng dataset jsonl.
- STDOUT của các runner in progress dạng `[s1] 20/300 d2-0019 OK 21540ms` — parse được.

## 1. Kiến trúc bắt buộc

- App mới tại **`evaluation/dashboard/`**: Next.js 15 App Router + TypeScript + Tailwind.
  Port **3100** (`next dev -p 3100`). Chỉ bind localhost, không auth (local tool).
- **API routes (Node runtime, không Edge)** làm backend luôn — không tạo server Python mới:
  - `POST /api/jobs` `{commandId, args}` → validate với whitelist trên (reject mọi thứ
    ngoài whitelist, escape args, cấm shell metachars) → `child_process.spawn` với
    `cwd = repo root`, `env` kế thừa. Lưu registry job in-memory + persist
    `evaluation/dashboard/.jobs.json` (jobId, pid, command, startedAt, status, logFile).
  - Mỗi job: pipe stdout+stderr vào `evaluation/dashboard/logs/<jobId>.log` (tạo folder).
  - `GET /api/jobs` — list jobs + status (running/exit code); `POST /api/jobs/:id/kill`
    → `taskkill /pid <pid> /T /F` trên Windows, `SIGTERM` trên unix.
  - `GET /api/jobs/:id/logs/stream` — **SSE** tail file log: gửi phần mới mỗi khi file
    grow (fs.watch + fallback polling 1s vì fs.watch không tin cậy trên Windows).
  - `GET /api/files?path=` — đọc file BÊN TRONG `evaluation/` only (chặn path traversal,
    resolve + kiểm tra prefix), hỗ trợ `?tail=200` cho jsonl lớn.
  - `GET /api/files/watch?path=` — SSE đẩy nội dung mới của jsonl đang grow
    (dùng chung logic tail-file với logs).
  - `GET /api/status` — preflight giống `evaluation/run_all.py::preflight`: ping
    `http://localhost:11434/api/tags` (models có `acnellm-v2-q4`, `qwen25-base-acnesys`?),
    tồn tại `data/chroma_db`, `data/bm25_index.pkl`, datasets, `DEEPSEEK_API_KEY` trong `.env`
    (chỉ trả bool, KHÔNG trả giá trị key).

## 2. UI — 4 trang

### `/` Dashboard
- Preflight checklist (từ `/api/status`) — mỗi mục ✓/✗ kèm lệnh sửa.
- Nút chạy nhanh: "Smoke run all", "Run all full", "Run tests" + jobs đang chạy
  (spinner, elapsed, nút Kill, link log).
- Tóm tắt lần chạy cuối từ `run_all_last.json` + gate status: chạy lệnh `check_gate`
  rồi đọc `evaluation/reports/gate_check.json` → badge xanh/đỏ per check (KHÔNG tự
  implement lại logic gate trong dashboard — single source of truth là harness).
- Banner judge-calibration: nếu `judge_bias_tests.json` chưa có hoặc pass=false →
  hiển thị "⚠ Điểm judge chưa calibrated" cạnh mọi judge metric.

### `/runs` Chạy & theo dõi
- Form builder cho từng commandId (dropdown system s0–s4, limit, skip, smoke, dataset
  picker từ `evaluation/datasets/v1/`).
- **Live console**: xterm-style box stream SSE log, auto-scroll, filter theo regex,
  highlight dòng `FAIL`/`FALLBACK DETECTED`/`⚠`.
- **Progress bar per system**: đếm dòng `results.jsonl` (SSE watch) / tổng dataset;
  ETA = trung bình `timings_ms.total` × số còn lại.

### `/results` Xem kết quả
- Bảng từ `report.json`: per-system metrics (ok_rate, parse, citation, pregnancy_safety,
  faithfulness, judge means, p50 latency) — cột so sánh S0–S4 cạnh nhau.
- Section comparisons: p-value + Holm significant badge, win/tie/loss.
- Error Pareto bar chart (dùng recharts) per system.
- Unit reports (T1) + retrieval summary (T2): render bảng modes × metrics.

### `/inspect` Debug từng sample
- Chọn experiment + system → load `results.jsonl` (paginate 50), search theo sample_id/text.
- Click 1 sample → panel chi tiết: answer, structured JSON (collapsible), trace
  (normalized_user, retrieved_ids vs final_ids, query), judged scores, error codes.
- Diff view: cùng sample_id giữa 2 system (side-by-side answer).
- Row màu đỏ nếu `ok=false` hoặc có `FALLBACK`.

## 3. Ràng buộc

- KHÔNG được cho phép chạy lệnh tùy ý (không có ô nhập shell command).
- KHÔNG sửa file trong `evaluation/` ngoài `evaluation/dashboard/**` và
  `evaluation/dashboard/logs/**`; `/api/files` là read-only.
- Mọi path Windows-safe (`path.join`, không hardcode `/`).
- Job registry phải sống sót khi refresh trang (đọc lại `.jobs.json`, check pid còn sống).
- Nếu port 3100 bận → in lỗi rõ ràng.
- Thêm `evaluation/dashboard/logs/` và `.jobs.json` vào `.gitignore` (root).
- README ngắn trong `evaluation/dashboard/`: cài (`npm i`), chạy (`npm run dev`),
  kiến trúc 10 dòng.

## 4. Acceptance criteria (tự kiểm tra trước khi kết thúc)

1. `npm run dev -p 3100` chạy được từ `evaluation/dashboard/`.
2. Bấm "Run tests" → thấy log pytest stream live → status ✓ khi exit 0.
3. Chạy `t1_intent --limit 5` từ UI → progress + log live → `/results` hiện report.json mới.
4. Kill job đang chạy hoạt động trên Windows.
5. `/api/files?path=../../.env` bị chặn (path traversal test).
6. Refresh trang giữa lúc job chạy → job vẫn hiển thị running + log tiếp tục stream.
7. Không có warning TypeScript/ESLint mức error.

Thứ tự làm: API jobs + SSE tail (test bằng curl trước) → trang `/runs` → `/` →
`/results` → `/inspect`. Commit nhỏ theo từng bước.
