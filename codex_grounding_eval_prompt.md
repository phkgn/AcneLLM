# Nhiệm vụ: Bỏ inline citation, đo grounding bằng metric thay thế (AcneLLM, vòng 2)

Bạn là debugging agent tiếp nối vòng 1. BẮT BUỘC đọc trước:
`evaluation/reports/debug_findings_20260717.md` — vòng 1 đã fix citation resolver,
faithfulness context capture, và làm rõ semantic `empty_core_fields_rate`.

## Quyết định kiến trúc đã chốt (bối cảnh — không bàn lại)

Inline citation `[N]` / `chunk_ref` bị BỎ hoàn toàn khỏi yêu cầu với model. Lý do:

- Model chưa bao giờ học cite: **0/41.849** mẫu finetune
  (`data/finetune/cleanv3/acne_chat_response.train.jsonl`) chứa marker `[n]`.
  Thực tế model chỉ dán một `[1]` decorative cuối answer, thường trỏ nguồn không
  liên quan → citation giả, có hại hơn không có (domain y tế).
- Vòng 1: S3 chỉ 63/140 câu bắt buộc cite là có cite, 7/63 bịa ID; S2 = 0/140.
- UI đã có panel nguồn đầy đủ (tên bài, link, score) độc lập với inline `[N]` —
  minh bạch nguồn không phụ thuộc model cite.
- "Model có dùng context RAG không" từ nay đo bằng metric, không đo bằng citation.

## Việc 1 — Gỡ citation khỏi production pipeline

1. Gỡ instruction cite khỏi templates: `config/prompts/hybrid_user.j2:16`
   (dòng "Đặt [N] ngay sau mỗi claim..."), `stream_user.j2:24`, `knowledge_user.j2:12`.
2. Output cleanup: strip mọi marker `[n]` lạc còn sót trong answer model sinh ra
   (regex cẩn thận: không phá "0.1%", "15-20 phút", số thập phân, khoảng liều).
3. Field `chunk_ref` trong AdviseOutput: giữ field cho tương thích schema nhưng
   không require, không validate là lỗi; ghi chú deprecated.
4. Flag config `inline_citation: off | model` (default `off`; `model` = hành vi cũ
   nguyên vẹn để A/B hoặc rollback).
5. Kiểm tra UI/render không vỡ khi answer không còn `[N]` (panel nguồn vẫn hiển thị).

## Việc 2 — Metric grounding deterministic (thay thế citation trong eval)

Module MỚI phía harness: `evaluation/metrics/grounding.py` (eval-only, KHÔNG nằm
trong production path):

1. Tách answer thành sentences (tiếng Việt: `.` `!` `?` xuống dòng; cẩn thận
   "0.1%", "BS.", số thập phân). Loại disclaimer chuẩn, câu hỏi ngược, câu chào.
2. Chấm mỗi sentence với từng chunk trong `trace.faithfulness_context` /
   `used_chunks` bằng hybrid score:
   - lexical: character n-gram overlap hoặc ROUGE-L trên bản normalize
     (lowercase, bỏ dấu);
   - semantic: cosine embedding — dùng lại embedder sẵn có của repo, không thêm
     dependency;
   - score cuối = max hoặc weighted (chọn, ghi rõ lý do).
3. Output per-record: `grounded_sentence_rate` (% sentence có chunk đỡ trên
   threshold) và danh sách `unsupported_sentences` trong kết quả eval.
   Đây là proxy faithfulness deterministic, chạy miễn phí, bổ sung (không thay thế)
   faithfulness LLM-judge.
4. Threshold: tune CHỈ trên D1 dev — script sweep nhỏ, in bảng threshold vs
   (rate, precision ước lượng bằng đọc tay 10-15 sentence), chọn và ghi số liệu.
5. Tích hợp: `evaluation/metrics/deterministic.py::evaluate_record` (hoặc chỗ hợp
   lý) + cột trong `evaluation/analysis/report.py`.
6. Unit tests (viết fail trước): exact quote → grounded; paraphrase → grounded;
   câu bịa → unsupported; không phá số khi normalize; case myth-rồi-bác-bỏ
   (xem `d2-0028-typo43` vòng 1) → document là known limitation (similarity align
   sai chiều), xfail hoặc assert hành vi + comment.

## Việc 3 — Context-sensitivity tests (đo "model có dùng RAG không" trực tiếp)

Runner mới `evaluation/unit/eval_context_sensitivity.py`, chạy trên D1 dev,
Ollama local, ≤ 10 case, 2 phép thử:

1. **Canary test**: inject một fact đặc trưng, vô hại, dễ nhận diện vào một chunk
   của context (ví dụ một tên hoạt chất giả định kèm chỉ dẫn cụ thể không có trong
   training data). Đo: answer có chứa canary không → `canary_adoption_rate`.
   Model dùng context thật sẽ nhắc canary; model lờ context thì không.
2. **Context-swap test**: cùng câu hỏi, chạy 2 lần — context đúng vs context
   không liên quan (lấy chunks của query khác hẳn). Đo khoảng cách 2 answer
   (embedding cosine + n-gram). Answer gần như y hệt → model lờ context
   (`swap_sensitivity` thấp là red flag).

Ghi 2 metric này vào reports/unit/ + thêm vào gate.yaml mục unit với ngưỡng
provisional (đánh dấu rõ là provisional, không tune trên D2).

Lưu ý an toàn: canary chỉ tồn tại trong eval run (thư mục tạm theo invariant #2),
tuyệt đối không ghi vào KB thật.

## Việc 4 — Cập nhật gate/report theo hợp đồng mới

1. `evaluation/configs/gate.yaml`: bỏ/deprecate `citation_valid_rate` cho đường
   prose; thay bằng `grounded_sentence_rate` (provisional threshold).
   Structured S3: `citation_coverage_valid_rate` giữ cho artifact cũ nhưng đánh
   dấu legacy trong report mới.
2. Artifact CŨ vẫn đọc lại được, metric cũ không xóa. Thêm rule khi đọc artifact
   prose cũ: toàn bộ citation chỉ là một `[1]` duy nhất ở cuối → coi như không cite.
3. KHÔNG sửa/ghi đè file nào trong `evaluation/reports/` cũ.

## Việc 5 — Chứng cứ cho quyết định "hợp đồng eval" (KHÔNG tự quyết)

Confound: empty_core_fields_rate S0=0.99, S2=1.0, S1=0.5, S3=0.0 — so sánh 2×2
đang đo lẫn "tuân JSON schema" với "chất lượng nội dung". Hai hướng:
(a) judge mọi condition trên rendered prose, structured metrics chỉ áp cho S3;
(b) sửa prompt để base model cũng điền được structure.

Nhiệm vụ: THU THẬP CHỨNG CỨ, người dùng quyết:

1. Đọc 15 record S0 + 15 record S2: nội dung thật nằm ở đâu (disclaimer?
   rendered text?), chất lượng khi đọc như prose?
2. Xác định rendered answer judge đang chấm build từ field nào
   (`evaluation/adapters/ollama_batch.py` / render code). Rendered text đủ nội dung
   bất kể core fields rỗng → hướng (a) rẻ và sạch. Rendered text cũng nghèo →
   điểm judge S0/S2 đang bị kéo theo, nêu rõ.
3. Probe hướng (b): 1-2 biến thể instruction (few-shot JSON, field description
   rõ hơn) CHỈ trên D1 dev, ≤ 10 case Ollama local. Báo empty-core-fields rate
   trước/sau.
4. Memo ≤ 1 trang: trade-off (a)/(b), khuyến nghị + lý do, những gì phải chạy lại.

## Việc 6 — Smoke test tổng hợp

Generation mới (run dir MỚI, không ghi đè):
`python -m evaluation.runners.run_experiment --experiment
evaluation/configs/experiments/main_2x2.yaml --systems s2,s3,s4 --limit 3
--dataset evaluation/datasets/v1/d1_dev_seed.jsonl` (hoặc tương đương). Xác nhận:

- fix vòng 1 hoạt động: `trace.faithfulness_context` đúng; S4 không cắt giữa câu;
- prompt mới không còn instruction cite; answer không còn `[n]` (kể cả strip);
- `grounded_sentence_rate` + `unsupported_sentences` xuất hiện trong record/report;
- context-sensitivity runner chạy được end-to-end, ra 2 metric;
- flag `inline_citation: model` tái tạo đúng hành vi cũ.

## Ràng buộc

- Ollama local: chỉ smoke/probe/sensitivity ≤ 10 case/hệ. KHÔNG chạy full 140.
- KHÔNG gọi paid API judge.
- KHÔNG sửa `evaluation/datasets/v1/`, KHÔNG sửa/ghi đè `evaluation/reports/` cũ.
- KHÔNG tune threshold/prompt trên D2 — mọi tuning trên D1 dev.
- Không thêm dependency mới.
- Mỗi fix/feature kèm unit test viết-fail-trước. Chạy full
  `pytest evaluation/tests -q` trước khi kết thúc.
- Production code (`src/acne_llm/`) thay đổi tối thiểu, sau flag `inline_citation`,
  rollback bằng 1 dòng config.

## Deliverable

`evaluation/reports/debug_findings_20260717_round2.md`:

1. Việc 1: diff templates + strip logic + flag, bằng chứng UI không vỡ.
2. Việc 2: thiết kế grounding metric, threshold + số liệu sweep D1, tests,
   known limitations.
3. Việc 3: kết quả canary + context-swap trên D1 (con số cụ thể từng case).
4. Việc 4: gate/report mới, rule trailing-[1], recompute trên artifact cũ nếu có.
5. Việc 5: memo trade-off (a)/(b) + số liệu probe.
6. Việc 6: smoke — bằng chứng từng mục pass/fail.
7. Việc còn lại cho vòng 3 (dự kiến: regenerate full T3, judge self-consistency +
   bias tests + human calibration, audit boilerplate finetune — 74 mẫu
   "mặt nạ nghệ" model đang regurgitate off-topic).
