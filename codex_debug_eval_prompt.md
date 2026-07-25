# Nhiệm vụ: Tìm nguyên nhân + debug 3 vấn đề trong evaluation pipeline (AcneLLM)

Bạn là debugging agent làm việc trên repo AcneLLM. Đây là hệ RAG tư vấn mụn tiếng Việt,
có evaluation harness tại `evaluation/` so sánh 5 conditions:
S0 = base (qwen25-base-acnesys, không RAG), S1 = finetuned (acnellm-v2-q4, không RAG),
S2 = base + RAG, S3 = finetuned + RAG (production), S4 = extractive (top chunks, không LLM).

Hai run preliminary trên D2 (140 case synthetic) đã lộ ra 3 vấn đề DETERMINISTIC
(không phụ thuộc LLM judge). Nhiệm vụ của bạn: tìm root cause từng vấn đề, phân loại
là **bug của harness/metric** hay **lỗi thật của hệ thống**, và fix nếu là bug code.

## Dữ liệu bằng chứng (đọc trước)

- Run n=140: `evaluation/reports/prelim_d2_openai_20260717T073212Z/`
  (generation tái dùng từ `prelim_d2_20260716T190345_330Z`, rejudge bằng OpenAI)
- Run n=30: `evaluation/reports/prelim_d2_20260717T090819_267Z/`
- Mỗi run có: `s{0..4}.results.jsonl` (raw generation + trace), `s{0..4}.judged.jsonl`
  (điểm + error codes), `report.md` (bảng tổng hợp)
- Metric code: `evaluation/metrics/deterministic.py` (`vacuous_answer`, `citation_valid`,
  `evaluate_record`), error taxonomy: `evaluation/analysis/error_attribution.py`
- Adapter sinh answer: `evaluation/adapters/ollama_batch.py`, bridge repo: `evaluation/adapters/_repo.py`

## Vấn đề 1 — S3 citation mismatch (ưu tiên cao nhất)

Triệu chứng: `cite_valid` của S3 = 0.6349 (n=140) / 0.75 (n=30); lỗi Pareto top của S3
là `E13_citation_mismatch × 23`. Gate yêu cầu ≥ 0.95. S4 (extractive) cite_valid = 1.0
→ chunk pipeline tự nó ổn, nghi vấn nằm ở khâu LLM cite hoặc khâu validate.

Việc cần làm:
1. Lọc các record S3 có `citation_valid == false` (hoặc error `E13`) trong
   `s3.judged.jsonl` / `s3.results.jsonl` của run n=140. Đọc kỹ 10 case: citation
   model trả ra là gì, `used_chunks`/context đưa vào là gì, id format hai bên.
2. Trả lời: mismatch là do (a) model bịa citation id, (b) lệch format id
   (ví dụ `chunk_3` vs `3` vs source-name), (c) harness đưa danh sách chunk vào
   prompt khác với danh sách dùng để validate trong `citation_valid()`, hay
   (d) off-by-one / reorder sau rerank?
3. Nếu là (b)/(c)/(d): fix code (metric hoặc adapter), chạy lại metric trên
   results.jsonl sẵn có (KHÔNG cần re-generate), báo cite_valid trước/sau.
4. Nếu là (a): thống kê tỉ lệ bịa, đề xuất fix prompt/schema, không sửa metric.

## Vấn đề 2 — Faithfulness thấp bất thường ở S2/S3

Triệu chứng: `faithful` S2 = 0.40, S3 = 0.45, trong khi S4 (chỉ trích nguyên văn chunks)
= 0.84. S4 lẽ ra phải ≈ 1.0 vì nó copy nguyên văn từ context → nghi judge chấm sai
hoặc pipeline claim-extract/entailment có bug.

Việc cần làm:
1. Đọc pipeline faithfulness: `evaluation/judges/` (prompts `claim_extract.md`,
   `entailment.md`, client code) — xem context đưa cho entailment có ĐÚNG là
   chunks mà record đó thực sự dùng không.
2. Lấy 10 claim bị chấm "not faithful" của S2/S3 và 5 của S4, so tay claim với chunk:
   judge chấm đúng hay sai?
3. Phân loại: bug harness (context sai/cụt, chunk truncation, claim tách sai) vs
   judge quá khắt vs generation thật sự không bám context. Đặc biệt giải thích
   vì sao S4 chỉ đạt 0.84.
4. Fix những gì là bug code; những gì là judge behavior thì ghi nhận + đề xuất
   sửa prompt, không đổi ngưỡng.

## Vấn đề 3 — Metric `vacuous` có pattern nghi ngờ + S1 vacuous 50%

Triệu chứng (cột `vacuous` trong report.md, n=140): S0 = 0.9857, S1 = 0.5,
S2 = 1.0, S3 = 0.0, S4 = None. Pattern này vô lý theo bất kỳ chiều đọc nào:
nếu là "tỉ lệ vacuous" thì S0/S2 gần như toàn rỗng (mâu thuẫn judge_correct ~3.3-3.7);
nếu là "tỉ lệ non-vacuous (pass)" thì S3 = 0.0 nghĩa là production toàn rỗng
(mâu thuẫn với vacuous S3 có nội dung + citations).

Việc cần làm:
1. Đọc `vacuous_answer()` trong `evaluation/metrics/deterministic.py` + chỗ
   aggregate ra cột report trong `evaluation/analysis/report.py`: xác định chính xác
   semantic và chiều của cột (rate of True? rate of False? None xử lý sao?).
2. Đối chiếu 5 record mỗi system với giá trị metric — tìm chỗ đảo chiều/bug.
3. Sau khi metric đúng: đo lại vacuous rate thật của S1. Nếu S1 thật sự ~50% rỗng,
   đọc 10 answer rỗng của S1, mô tả pattern (trả lời từ chối? JSON rỗng? câu chung
   chung?) và nêu giả thuyết vì sao finetuned model KHÔNG có RAG lại rỗng
   (gợi ý: finetune data luôn có context → model học thói quen im lặng khi thiếu context?).

## Ràng buộc

- KHÔNG re-generate answers (tốn giờ Ollama) — mọi phân tích chạy trên
  `*.results.jsonl` / `*.judged.jsonl` sẵn có. Re-compute metric offline là được.
- KHÔNG gọi API judge trả tiền trừ khi bắt buộc; nếu cần thì ≤ 20 calls.
- KHÔNG sửa datasets trong `evaluation/datasets/v1/` và KHÔNG sửa file trong
  `evaluation/reports/` (immutable evidence). Fix chỉ nằm ở code
  `evaluation/metrics|judges|analysis|adapters`.
- Mỗi fix phải kèm unit test trong `evaluation/tests/` tái hiện bug trước khi fix.
- Tuân thủ invariants trong `evaluation/README.md` mục "Bất biến".

## Deliverable

Viết báo cáo `evaluation/reports/debug_findings_YYYYMMDD.md` gồm, cho từng vấn đề:
1. Root cause (kèm dẫn chứng: file:line, 2-3 record ví dụ cụ thể).
2. Phân loại: harness bug / judge behavior / system defect thật.
3. Fix đã áp dụng (diff tóm tắt) + test đi kèm, hoặc đề xuất nếu ngoài scope.
4. Metric trước/sau khi re-compute trên run n=140.
5. Kết luận: sau các fix, con số nào trong report cũ được phép tin lại, con số nào vẫn phải chờ judge calibration.
