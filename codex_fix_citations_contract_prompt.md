# Nhiệm vụ: Fix citation pipeline + làm rõ confound structured-output (AcneLLM, vòng 2)

Bạn là debugging agent tiếp nối vòng 1. BẮT BUỘC đọc trước:
`evaluation/reports/debug_findings_20260717.md` — vòng 1 đã fix citation resolver,
faithfulness context capture, và làm rõ semantic `empty_core_fields_rate`.

Vòng 2 xử lý 3 việc mà vòng 1 lộ ra nhưng chưa làm:

## Việc 1 — S2 (base + RAG) có 0/140 record chứa citation

Bằng chứng: `citation_coverage_valid_rate` của S2 = 0.0 trong run
`evaluation/reports/prelim_d2_openai_20260717T073212Z/`; không record nào trong
`s2.results.jsonl` có citation trong structured output.

Base model mà KHÔNG BAO GIỜ cite (0/140, không phải hiếm khi) thì nghi vấn số một
là prompt/config/parse, không phải khả năng model. Cần xác định:

1. So sánh config `evaluation/configs/systems/s2.yaml` với `s3.yaml`: khác gì về
   prompt template, schema, options?
2. Trace luồng render: `src/acne_llm/pipeline/hybrid.py` + `config/prompts/hybrid_user.j2`
   — S2 có nhận cùng instruction cite `chunk_ref` như S3 không? In thử prompt đã render
   của 2-3 case S2 (tái dựng offline từ trace/used_chunks nếu được, hoặc render lại
   template với cùng input — không cần gọi model).
3. Kiểm tra khâu parse: raw response của S2 trong `s2.results.jsonl` có chứa citation
   dạng nào đó (ordinal, tên nguồn trong text) mà parser bỏ qua không? Đọc 10 raw
   response.
4. Phân loại: (a) prompt cho S2 thiếu instruction cite, (b) parser drop citations,
   (c) base model thật sự lờ instruction. Fix nếu là (a)/(b). Nếu là (c), báo cáo
   kèm bằng chứng raw text.

## Việc 2 — Ép citation đúng bằng schema (diệt nhóm "bịa ID" một cách deterministic)

Vòng 1 phân loại 7/63 record S3 là system defect thật: bịa ID, sai index, sai source,
`unknown`. Prompt đã lộ canonical id qua `chunk_ref=<canonical-id>`
(`config/prompts/hybrid_user.j2:14`).

Việc cần làm:
1. Tìm chỗ định nghĩa JSON schema cho AdviseOutput (structured output constraint gửi
   Ollama) — xem field citation/`chunk_ref` hiện là free string hay có constraint.
2. Implement: khi build request, inject `enum` các canonical id của chunks trong
   context vào schema của citation field (per-request dynamic schema). Model vật lý
   không thể trả ID ngoài danh sách.
3. Nếu Ollama structured output không hỗ trợ enum per-request, fallback: post-process
   normalize + reject-and-retry một lần khi citation ngoài danh sách. Ghi rõ chọn
   đường nào và vì sao.
4. Cẩn thận: thay đổi này thuộc PRODUCTION pipeline (`src/acne_llm/`), không phải
   harness. Giữ thay đổi nhỏ nhất có thể, có flag/config bật tắt để so sánh A/B sau.
5. Unit test: schema build đúng enum từ used_chunks; post-processor reject ID lạ.

## Việc 3 — Chứng cứ cho quyết định "hợp đồng eval" (KHÔNG tự quyết)

Confound đã phát hiện: empty_core_fields_rate S0=0.99, S2=1.0, S1=0.5, S3=0.0.
So sánh 2×2 hiện đo lẫn "tuân JSON schema" với "chất lượng nội dung". Có 2 hướng:
(a) judge mọi condition trên rendered prose, structured metrics chỉ áp cho S3;
(b) sửa prompt để base model cũng điền được structure.

Nhiệm vụ của bạn là THU THẬP CHỨNG CỨ, người dùng sẽ quyết:

1. Đọc 15 record S0 + 15 record S2 (đủ cả empty và non-empty nếu có): nội dung thật
   nằm ở đâu (disclaimer? rendered text?), chất lượng ra sao khi đọc như prose?
2. Xác định: rendered answer mà judge đang chấm được build từ field nào
   (`evaluation/adapters/ollama_batch.py` / render code)? Nếu rendered text đã chứa
   đủ nội dung bất kể core fields rỗng → hướng (a) rẻ và sạch. Nếu rendered text
   cũng nghèo khi core fields rỗng → điểm judge của S0/S2 đang bị kéo theo, cần nêu rõ.
3. Ước lượng chi phí hướng (b): thử render lại prompt S0 với 1-2 biến thể instruction
   (few-shot JSON example, field description rõ hơn) — CHỈ trên D1 dev (10 case,
   Ollama local, cho phép), TUYỆT ĐỐI không dùng D2. Báo empty-core-fields rate
   trước/sau trên 10 case đó.
4. Viết memo ngắn (≤1 trang) trong deliverable: trade-off (a) vs (b), khuyến nghị
   kèm lý do, những gì phải chạy lại theo mỗi hướng.

## Việc 4 — Smoke test adapter fixes vòng 1

Vòng 1 đã sửa `ollama_batch.py` (capture `faithfulness_context`) và `extractive.py`
(sentence truncation) nhưng chưa có generation nào dùng chúng.

Chạy smoke: `python -m evaluation.runners.run_experiment --experiment
evaluation/configs/experiments/main_2x2.yaml --systems s3,s4 --limit 3
--dataset evaluation/datasets/v1/d1_dev_seed.jsonl` (hoặc cách tương đương,
output vào run dir mới — KHÔNG ghi đè run cũ). Xác nhận:
- record mới có `trace.faithfulness_context` đúng là rendered context;
- S4 answer không còn cắt giữa câu;
- resolver citation mới chạy trên record mới không lỗi.

## Ràng buộc (giữ nguyên từ vòng 1)

- Ollama local: chỉ dùng cho smoke ≤ 10 case/hệ và probe D1 ở Việc 3. KHÔNG chạy full 140.
- KHÔNG gọi paid API judge.
- KHÔNG sửa `evaluation/datasets/v1/` và KHÔNG sửa/ghi đè `evaluation/reports/` cũ
  (run smoke mới được tạo thư mục mới).
- KHÔNG tune prompt/threshold dựa trên D2 — mọi probe prompt chỉ trên D1 dev.
- Mỗi fix kèm unit test tái hiện bug/hành vi trước fix. Chạy full
  `pytest evaluation/tests -q` trước khi kết thúc.
- Thay đổi production code (`src/acne_llm/`) phải tối thiểu và có flag tắt được.

## Deliverable

`evaluation/reports/debug_findings_20260717_round2.md`:
1. Việc 1: root cause S2 zero-citation (file:line + 3 record ví dụ), phân loại, fix + số trước/sau nếu recompute được offline.
2. Việc 2: cơ chế enforce đã chọn (enum schema hay retry), diff tóm tắt, test.
3. Việc 3: memo trade-off (a)/(b) + số liệu probe D1.
4. Việc 4: kết quả smoke, xác nhận từng fix vòng 1 hoạt động trên generation mới.
5. Danh sách việc còn lại cho vòng 3 (dự kiến: regenerate full T3, judge self-consistency + bias tests, human calibration).
