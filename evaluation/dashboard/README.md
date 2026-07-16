# AcneLLM Eval Dashboard

Dashboard local Next.js 15 cho `evaluation/`; không thay thế production chat UI.

```powershell
npm install
npm run dev
```

Mở `http://127.0.0.1:3100`.

Kiến trúc:

- App Router + TypeScript + Tailwind, các trang Dashboard / Runs / Results / Inspect / Review.
- Node API routes spawn duy nhất các Python command trong whitelist, `shell: false`.
- Job registry nằm ở `.jobs.json`; stdout/stderr được append vào `logs/<jobId>.log`.
- SSE tail dùng `fs.watch` và polling 1 giây để ổn định trên Windows.
- Kill job dùng `taskkill /T /F` trên Windows và `SIGTERM` trên Unix.
- UI chuyển job sang `stopping` ngay khi bấm Kill; backend chỉ chốt `killed`
  sau khi process tree đã dừng.
- File API chỉ resolve path nằm trong `evaluation/` và luôn read-only.
- Status API chỉ trả boolean cho API key, không trả secret.
- Results/Inspect đọc artifact JSON/JSONL hiện có, không tạo metric giả.
- Review đọc seed D1 và draft D2–D7 ở chế độ read-only; approve/edit/reject được lưu riêng
  trong `.dataset-reviews.json` kèm source hash để phát hiện draft bị regenerate.
- Chỉ khi một split không còn pending/needs-edit/stale, trang Review mới cho
  download JSONL đã approved để đưa vào `evaluation/datasets/v1/`.
- App chỉ bind `127.0.0.1:3100`, không có auth vì là công cụ local.
- Giao diện dùng dark theme ấm với accent terracotta để đọc log và review lâu.
- Command `validation_loop` watch
  `evaluation/reports/validation/**/summary.json` và hiển thị verdict/checks trên
  trang Runs lẫn Results.
