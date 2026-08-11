# PROMPT — E2E QA: chạy thử toàn bộ dashboard + pipeline 1-case, bắt lỗi và debug

> Copy vào Codex, chạy từ repo root `AcneLLM/`. Mục tiêu: chứng minh bằng CHẠY THẬT
> rằng dashboard + harness hoạt động end-to-end, không phải bằng code review.

---

Bạn là QA/debug engineer. Nhiệm vụ: khởi động dashboard, lái toàn bộ workflow qua
dashboard với **1 case duy nhất** (nhanh, rẻ), quan sát từng bước qua UI/API thật,
ghi lại MỌI lỗi gặp được, sửa theo root cause, lặp đến khi cả flow xanh.

## 0. Bối cảnh (đã xác minh — không khám phá lại)

- Dashboard: `evaluation/dashboard/` (Next.js, port 3100, `run.ps1`), 4 trang
  `/`, `/runs`, `/results`, `/inspect`; API `/api/status`, `/api/jobs`,
  `/api/jobs/:id/logs/stream` (SSE), `/api/files`. **Lưu ý đã biết: port 3100 có thể
  đang chạy server CŨ → việc đầu tiên là kill process cũ và start lại.**
- Harness: whitelist lệnh trong `docs/EVAL_DASHBOARD_PROMPT.md` (16 lệnh, gồm
  `trust_audit`). Validation verdict gần nhất: sinh câu trả lời batch NOT_TRUSTWORTHY vì data/judge —
  ĐÓ KHÔNG PHẢI LỖI CẦN SỬA trong QA này; QA này chỉ kiểm tra **cơ chế chạy**, không
  kiểm tra chất lượng model.
- Trạng thái biết trước (không được coi là bug mới): Bộ dev/Bộ retrieval có duplicate và
  `needs_relabel`; judge cần `DEEPSEEK_API_KEY` trong `.env`; sinh câu trả lời batch cần Ollama chạy +
  2 model `acnellm-v2-q4`, `qwen25-base-acnesys`; Ollama generation ~15–55s/câu.

## 1. Kịch bản E2E — chạy qua DASHBOARD (không chạy tay CLI trừ khi debug)

Chuẩn bị: kill server cũ port 3100 → `run.ps1` → mở `http://localhost:3100`.
Mỗi bước dưới đây: bấm từ UI (hoặc gọi API route của dashboard bằng curl nếu UI
chưa có nút), theo dõi log stream live, xác nhận output file xuất hiện và trang
tương ứng render đúng.

| # | Bước qua dashboard | Kiểm tra pass |
|---|---|---|
| 1 | Trang `/` — preflight | Mỗi mục ✓/✗ đúng thực tế (so tay với `python -m evaluation.full_evaluation --smoke --skip t1,t2,t3,judge,report` output); nếu Ollama tắt → hiển thị ✗ kèm lệnh sửa, KHÔNG crash |
| 2 | `/runs` chạy `tests` | pytest stream live, exit ✓, highlight hoạt động |
| 3 | `/runs` chạy `intake_eval` với `--limit 1` | log live, xong → `/results` hiện report Intake mới (kiểm tra timestamp đổi) |
| 4 | `/runs` chạy `retrieval_eval` `--modes sparse --limit 1` | banner cảnh báo needs_relabel hiển thị; summary render |
| 5 | `/runs` chạy `answer_generation` `--systems s1 --limit 1` (không resume, out-dir mới `evaluation/reports/qa_1case`) | progress bar 0→1/1, ETA hiển thị, record có `model_name=acnellm-v2-q4`, không FALLBACK |
| 6 | Giữa lúc 1 job khác đang chạy (chạy lại bước 5 với s0): bấm **Kill** | process chết thật trên Windows (taskkill /T), status=killed, không zombie python |
| 7 | `/runs` chạy `judge` `--limit 1` trên `qa_1case` (nếu có DEEPSEEK_API_KEY; không có → xác nhận job fail có message rõ ràng, không treo) | judged.jsonl xuất hiện, cost log hiển thị |
| 8 | `/runs` chạy `report` trên `qa_1case` | `/results` render bảng per-system + n_attempted/buckets đúng schema mới |
| 9 | `/inspect` chọn qa_1case/s1/sample | thấy answer + structured + trace (context_chunks) + judge scores; diff view với s0 nếu đã chạy bước 6 |
| 10 | `/runs` chạy `check_gate` rồi `trust_audit` trên `qa_1case` | gate badges cập nhật từ `gate_check.json`; validation summary hiện verdict; banner "judge chưa calibrated" hiển thị đúng điều kiện |
| 11 | **Refresh trang giữa lúc 1 job đang chạy** | job vẫn hiện running, log tiếp tục stream (registry persistence) |
| 12 | Path traversal: `GET /api/files?path=../../.env` và `path=..%2F..%2F.env` | bị chặn 403, không lộ nội dung |

## 2. Kỷ luật debug khi gặp lỗi

Mỗi lỗi: ghi vào QA log TRƯỚC khi sửa — {bước, hành vi mong đợi, hành vi thực tế,
log/stack, phân loại: DASHBOARD_BUG / HARNESS_BUG / CONFIG / INFRA / KNOWN_ISSUE,
root cause, fix, test chống tái phát}. Quy tắc:

- Root cause trước, fix sau — không patch triệu chứng (vd: log không stream → xác
  định fs.watch vs polling vs SSE headers vs buffering của Next trước khi đổi code).
- Fix nhỏ nhất; DASHBOARD_BUG sửa trong `evaluation/dashboard/**`; HARNESS_BUG sửa
  trong `evaluation/**` + thêm test vào `evaluation/tests/`; **KHÔNG sửa `src/`**,
  KHÔNG nới lỏng invariant/gate để cho xanh, KHÔNG sửa dataset.
- Sau mỗi fix: chạy lại đúng bước lỗi + bước liền trước; cuối cùng chạy lại TOÀN BỘ
  kịch bản 12 bước một lượt sạch từ đầu (fresh server, out-dir mới) để chứng minh.
- Lỗi thuộc KNOWN_ISSUE (data quality, judge chưa calibrate, Ollama chậm) → ghi
  nhận, không sửa.
- Commit theo từng fix với message `qa(dashboard): <bước> — <root cause>`.

## 3. Deliverables

1. `evaluation/reports/dashboard_qa/<ts>/QA_REPORT.md`: bảng 12 bước × pass/fail
   (trước và sau fix), bảng lỗi đã sửa (phân loại + root cause + commit), danh sách
   KNOWN_ISSUE gặp phải, thời gian từng bước, kết luận "dashboard + harness sẵn sàng
   cho full run hay chưa, còn rủi ro gì".
2. Test tự động mới cho mỗi bug đã sửa (dashboard: thêm vào test suite của app;
   harness: `evaluation/tests/`).
3. `pytest evaluation/tests -q` xanh + lint/build dashboard xanh, chạy ở trạng thái
   cuối.
4. Nếu bước nào không thể pass do phụ thuộc ngoài (thiếu API key, Ollama không có
   model) → đánh dấu BLOCKED kèm đúng 1 dòng hướng dẫn người dùng mở khóa, không
   được im lặng bỏ qua.

Bắt đầu: kill port 3100 → start server → đi tuần tự bước 1→12. Không nhảy bước:
lỗi ở bước N phải sửa xong mới sang N+1 (trừ khi BLOCKED).
