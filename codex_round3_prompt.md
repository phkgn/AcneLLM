# Vòng 3: Chốt contract prose, xóa đường JSON, điều tra grounding 0.20 + canary 0/3

Bạn là agent tiếp nối vòng 1–2. BẮT BUỘC đọc trước, theo thứ tự:

1. `evaluation/reports/debug_findings_20260717.md` (vòng 1)
2. `evaluation/reports/debug_findings_20260717_round2.md` (vòng 2)
3. `plan_remove_json_path.md` (plan tổng đã được duyệt)

## Quyết định đã chốt (thực thi, không bàn lại)

Người dùng đã quyết **hơn cả hướng (a)** trong memo vòng 2: loại bỏ hoàn toàn
đường JSON khỏi repo. Production chỉ còn SSE prose. Eval chấm prose cho TẤT CẢ
conditions kể cả S3 — không còn "structured metrics cho riêng S3". Căn cứ:

- Frontend chỉ gọi `/api/v1/chat/stream`; `POST /chat` không có traffic người dùng.
- Probe (b) vòng 2 thất bại 3/3: base model không điền structure dù đổi instruction.
- S0/S2 rendered answer từ JSON nghèo thật (131–146 ký tự boilerplate) — hướng (a)
  nguyên bản cũng không cứu được `_flatten_advise`.

## Việc 1 — Thực thi Phase 0–1 của plan: xóa đường JSON

Theo đúng bảng xóa/giữ trong `plan_remove_json_path.md`:

1. Phase 0: tag git `pre-json-removal`; grep lần cuối consumer của `POST /chat`,
   `generate_structured`, `generate_json` trong `notebooks/`, `scripts/`,
   `docker-compose.yml`, dashboard; thêm `LEGACY.md` vào `evaluation/reports/`
   đánh dấu mọi run cũ là đo đường JSON.
2. Phase 1: xóa route `POST /chat` + `_chat_new_body`; `generate_structured()` +
   nhánh `response_format=="structured"`; `_safe_parse` + gửi
   `model_json_schema()` trong `pipeline/hybrid.py` và `llm_only.py`;
   `hybrid_user.j2`, `llm_only_user.j2`; CLI structured (chuyển sang prose);
   `c.llm.generate_json` nếu hết caller. Partial
   `_inline_citation_model_structured.j2` (vòng 2 tạo) cũng xóa theo.
3. GIỮ: class `AdviseOutput` (scope refusal/clarify/session dựng tay);
   toàn bộ SSE + templates prose; flag `inline_citation` (nhánh `model` giờ chỉ
   còn nghĩa với prose partial).
4. Sau xóa: backend smoke tay qua SSE 3–5 câu; xóa/sửa test đường JSON;
   mỗi cụm xóa một commit riêng.

## Việc 2 — Phase 2: T3 adapter đo prose

Viết lại `evaluation/adapters/ollama_batch.py`: gọi đúng đường prose production
(`prepare_chat_turn` với response_format text + template theo route, non-stream
batch call). Record lưu: prose answer, used_chunks, `trace.faithfulness_context`
(giữ cơ chế vòng 1), latency. S4 extractive giữ nguyên. Invariants giữ:
no-fallback, session isolation, run_meta.

Metrics: gỡ `parse_success`/`empty_core_fields`/citation structured khỏi
evaluate_record cho record prose mới (code đọc LEGACY giữ). Grounding +
context-sensitivity + safety text (port pattern check từ structured sang prose
nếu chưa có) là bộ deterministic chính.

Smoke: S0–S4 × 3 case D1 qua adapter mới, xác nhận record/report/gate chạy thông.

## Việc 3 — Điều tra S3 grounding 0.20 + canary 0/3 (chẩn đoán, quan trọng nhất về mặt hiểu biết)

Hai số này nói: model S3 (finetuned+RAG) hầu như không dùng fact trong context.
Cần tìm bottleneck là MODEL hay RETRIEVAL/PROMPT hay METRIC trước khi đổ tiền
regenerate full. Ablation trên D1, ≤ 10 case, Ollama local:

1. **Metric có oan không**: lấy 25 câu S3 bị unsupported trong smoke vòng 2
   (`round2_smoke_20260717T124200Z`), đọc tay từng câu vs context: bao nhiêu %
   thật sự không có trong context, bao nhiêu % là false negative của scorer
   (paraphrase xa, câu ngắn — limitation đã ghi)? Nếu FN cao → ưu tiên sửa
   scorer/threshold (vẫn chỉ trên D1) trước khi kết luận model.
2. **Context có đến được model không**: in prompt đã render của các case đó —
   context đủ dài? bị truncate? đúng chunks liên quan câu hỏi không? (nghi vấn
   retrieval quality — so với swap-context xem chunks "đúng" có thực sự đúng).
3. **Model có chịu đọc không**: ablation prompt trên D1 — biến thể nhấn mạnh
   "chỉ dùng thông tin trong tài liệu, nói rõ nếu tài liệu không đề cập" vs
   baseline. Đo grounding + canary trước/sau. Kèm 1 biến thể chạy S2 (base) cùng
   điều kiện: nếu base grounding cao hơn finetuned → bằng chứng finetune đã dạy
   model tự nói theo training data thay vì đọc context (khớp giả thuyết
   boilerplate 74 mẫu "mặt nạ nghệ" vòng 1–2).
4. Kết luận phân loại bottleneck: metric / retrieval / prompt / model-finetune,
   kèm bằng chứng từng loại. KHÔNG áp fix heuristic vào production trong vòng này
   (đúng khuyến cáo vòng 2) — chỉ đề xuất cho vòng 4.

## Việc 4 — Mở rộng calibration grounding (chuẩn bị khóa gate)

Nhãn tay hiện chỉ 15 câu — quá mỏng để tin threshold 0.50. Mở rộng lên ~60–80 câu
D1 (ưu tiên negation/refutation, số/liều, câu hành động ngắn — đúng danh sách
weakness vòng 2), lưu vào `evaluation/configs/grounding_d1_dev_seed_manual_labels.json`
theo format sẵn có. Re-sweep threshold, báo precision/recall/F1 mới. Nếu
threshold đổi, cập nhật gate provisional + ghi rõ lịch sử đổi.

(Nhãn do bạn tự gán theo entailment đọc tay thì đánh dấu `annotator: agent` —
người dùng sẽ review lại; không claim đây là human gold.)

## Việc 5 — Cập nhật docs

`evaluation/README.md` + `docs/EVAL_BLUEPRINT.md`: T3 = prose batch, bảng metric
mới, đánh dấu mục structured là legacy. Ngắn gọn, đúng hiện trạng code sau Việc 1–2.

## Ràng buộc

- Ollama local: ablation/smoke ≤ 10 case/hệ. KHÔNG chạy full 140 (để vòng 4,
  sau khi bottleneck grounding rõ).
- KHÔNG gọi paid API judge (judge self-consistency + bias tests + full baseline
  là vòng 4, sau khi contract này merge).
- KHÔNG sửa `evaluation/datasets/v1/`; KHÔNG sửa/ghi đè artifact cũ trong
  `evaluation/reports/` (chỉ thêm `LEGACY.md` và run dir mới).
- Tune threshold/prompt chỉ trên D1.
- Test viết-fail-trước cho mọi thay đổi; kết thúc bằng `pytest evaluation/tests -q`
  + test src + `frontend npm run lint` xanh.
- Commit nhỏ, mỗi cụm xóa/feature riêng, message rõ.

## Deliverable

`evaluation/reports/debug_findings_20260717_round3.md`:

1. Việc 1: danh sách đã xóa (file → commit), bằng chứng SSE nguyên vẹn,
   kết quả grep consumer.
2. Việc 2: adapter prose mới — thiết kế, smoke S0–S4×3, record/report mẫu.
3. Việc 3: bảng phân loại bottleneck grounding/canary kèm bằng chứng
   (metric FN rate, prompt render, ablation trước/sau, so sánh S2 vs S3) +
   đề xuất fix cho vòng 4.
4. Việc 4: bảng sweep threshold mới trên ~60–80 nhãn, threshold chốt.
5. Việc 5: diff docs.
6. Danh sách vòng 4: full T3 prose baseline (140), judge self-consistency +
   bias tests + human calibration, fix bottleneck grounding theo kết luận Việc 3,
   audit boilerplate finetune, T4 SSE e2e, relabel D8.
