# Codex Prompt — Run-All Monitor UI (theo dõi chi tiết run_all trên dashboard)

## Bối cảnh

Tiếp nối `codex_eval_simplify_prompt.md`: `evaluation.run_all` mới chạy 7 bước
([0] preflight → [1] intake → [2] rag → [3] t3 → [4] judge+report → [5] bottleneck → [6] figures).
Hiện dashboard chỉ tail được log thô. Cần: khi chạy run_all, người dùng thấy **đang ở bước nào,
bước nào xong/fail/skip, tiến độ chi tiết của bước nặng** — real-time, không reload.

Nguyên tắc: **tái dùng tối đa infra sẵn có** — SSE `/api/files/watch`, log tail, `/api/progress`,
job registry. Không thêm endpoint mới trừ khi bắt buộc, không thêm dependency.

## Task 1 — Orchestrator ghi trạng thái máy-đọc-được (Python)

Trong `evaluation/run_all.py`:

1. `summary.json` trong `<out>/` ghi **atomic** (tmp + rename) tại MỌI chuyển trạng thái
   (bắt đầu bước, kết thúc bước), không chỉ khi xong:

```json
{
  "run_id": "thesis_20260726_...",
  "out_dir": "evaluation/reports/thesis_...",
  "started_at": "...", "finished_at": null,
  "current_step": "t3_generation",
  "steps": [
    {"id": "preflight", "label": "Preflight", "status": "ok",
     "started_at": "...", "finished_at": "...", "duration_s": 3.1, "detail": ""},
    {"id": "t3_generation", "status": "running", "started_at": "...", ...},
    {"id": "bottleneck", "status": "pending", ...}
  ]
}
```

   `status ∈ pending | running | ok | fail | skipped`. `detail` chứa lý do fail/skip (1 dòng).

2. stdout in marker line trước/sau mỗi bước, vừa cho người đọc vừa cho UI highlight:

```
[runall] step=4/7 id=t3_generation status=start
[runall] step=4/7 id=t3_generation status=ok duration=812.4s
```

3. Không thay đổi hành vi nào khác của orchestrator.

## Task 2 — Wire outDir vào job record (dashboard lib)

- `commands.ts` case `run_all`: thêm arg `outDir` (validate bằng `outputRunDir` sẵn có,
  default `evaluation/reports/thesis_<stamp>` — tái dùng pattern timestamp của
  `preliminaryOutputDir` cũ). Push `--out <dir>` vào argv, ghi vào `normalizedArgs.outDir`.
- Nhờ đó `JobRecord.args.outDir` luôn có → UI biết summary.json nằm đâu. Không cần API mới.

## Task 3 — Component `RunAllMonitor` trong RunsClient

Hiển thị khi job đang chọn có `commandId === "run_all"`, đặt phía trên log pane:

1. **Stepper 7 bước**: đọc `args.outDir` của job → mở SSE
   `/api/files/watch?path=<outDir>/summary.json` (endpoint sẵn có; mỗi event parse lại
   JSON, bỏ qua parse lỗi giữa chừng ghi file). Mỗi bước một hàng:
   icon trạng thái (pending mờ / running spinner + elapsed đếm giây / ok xanh + duration /
   fail đỏ + `detail` / skipped xám + lý do), dùng `Pill`/tone sẵn có trong `ui.tsx`.
2. **Sub-progress cho bước t3_generation**: khi bước này `running`, render lại khối
   progress bars S0–S4 hiện có của RunsClient (đã poll `/api/progress`), truyền
   `experiment=<basename(outDir)>` — không viết lại logic.
3. **Sub-progress cho bước bottleneck**: hiển thị arm hiện tại bằng cách đọc marker
   `[runall] ... id=bottleneck_<arm>` từ log stream đã có (regex trên chunk SSE log,
   không thêm API). 4 chip Z/X/W/Y đổi trạng thái theo marker.
4. Job bị **kill**: stepper giữ nguyên trạng thái cuối từ summary.json, banner
   "Run bị dừng ở bước <current_step>" dựa vào `job.status === "killed"` — orchestrator
   chết không kịp ghi file là chuyện chấp nhận được, UI lấy job status làm nguồn sự thật
   cho trạng thái tổng.

## Task 4 — Nâng log viewer (nhỏ)

- `lineClass()` trong RunsClient: thêm rule — dòng bắt đầu `[runall]` được highlight
  (màu accent), `status=fail` tô đỏ, `status=ok` tô xanh. Chỉ regex, không parse JSON.
- Nút filter "Chỉ hiện marker" (toggle client-side, lọc mảng line đã có trong state).

## Task 5 — Overview gắn mini-status

- Card "Jobs đang chạy" ở DashboardClient: với job run_all đang chạy, hiển thị thêm
  1 dòng `bước 4/7 · t3_generation` — fetch một lần mỗi lần refresh (10s) qua
  `/api/files?path=<outDir>/summary.json` (endpoint sẵn có), parse `current_step`.
  Không mở SSE ở Overview.

## Acceptance criteria

1. Chạy `run_all --smoke --yes` từ dashboard: stepper cập nhật live qua SSE, không reload;
   bước t3 hiện progress bar S0–S4; xong hết stepper toàn ok/skipped.
2. Giả lập fail (skip judge key): bước judge hiện `skipped` + lý do; run tiếp tục, UI đúng.
3. Kill giữa bước: job chuyển killed, banner dừng-ở-bước hiển thị, không crash stepper.
4. Log viewer highlight marker lines; toggle filter hoạt động.
5. Không endpoint mới, không dependency mới, Node không tính metric gì.
6. Tests: 1 test parse summary schema (lib), 1 test lineClass marker, 1 test
   commands.ts sinh `--out` đúng và nằm trong `evaluation/reports/`.
7. `npm run build` + tests dashboard pass.

## Không được làm

- Không WebSocket/polling framework mới — chỉ SSE + poll sẵn có.
- Không lưu state monitor vào file mới nào ngoài `summary.json` đã định nghĩa.
- Không sửa các trang khác ngoài Runs + Overview (mini-status).
