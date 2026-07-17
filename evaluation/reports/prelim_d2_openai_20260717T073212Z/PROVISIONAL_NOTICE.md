# Preliminary Evaluation Notice

Status: PRELIMINARY_SYNTHETIC_ONLY

Mục đích: so sánh định hướng giữa các system và phát hiện lỗi pipeline.

- D2 hiện là synthetic-only; chưa có independent human verification.
- Chưa có human-written hoặc real-user cases.
- D8 bị loại khỏi run này vì pooled retrieval relabel chưa hoàn tất.
- Regression gate bị loại khỏi run này.
- Generation S0–S4 được giữ nguyên từ `prelim_d2_20260716T190345_330Z`;
  chỉ phần judge được chạy lại bằng OpenAI.
- Judge provider/model: `openai/gpt-5-nano-2025-08-07`.
- LLM Judge chưa được calibration với human labels.

Không sử dụng kết quả này làm clinical ground truth, final benchmark,
production-readiness claim hoặc publication claim.
