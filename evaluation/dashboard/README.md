# AcneLLM Eval Dashboard

Dashboard local Next.js 15 cho `evaluation/`; không thay thế production chat UI.

```powershell
npm install
npm run dev
```

Mở `http://127.0.0.1:3100`.

Kiến trúc:

- App Router + TypeScript + Tailwind, bốn trang Dashboard / Runs / Results / Inspect.
- Node API routes spawn duy nhất các Python command trong whitelist, `shell: false`.
- Job registry nằm ở `.jobs.json`; stdout/stderr được append vào `logs/<jobId>.log`.
- SSE tail dùng `fs.watch` và polling 1 giây để ổn định trên Windows.
- Kill job dùng `taskkill /T /F` trên Windows và `SIGTERM` trên Unix.
- File API chỉ resolve path nằm trong `evaluation/` và luôn read-only.
- Status API chỉ trả boolean cho API key, không trả secret.
- Results/Inspect đọc artifact JSON/JSONL hiện có, không tạo metric giả.
- App chỉ bind `127.0.0.1:3100`, không có auth vì là công cụ local.
