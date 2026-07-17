# Plan: Loại bỏ đường JSON khỏi repo + chuyển eval sang prose (LLM judge)

Mục tiêu: production chỉ còn một đường duy nhất (SSE prose). Eval đo đúng cái
người dùng nhận: văn bản tự nhiên model trả ra, chấm bằng LLM judge + metric
deterministic trên text. Xóa toàn bộ code chỉ phục vụ JSON output.

Điều kiện nền đã xác minh:
- Frontend chỉ gọi `/api/v1/chat/stream` (SSE) — `frontend/src/lib/api.ts:16`.
- `POST /chat` không có traffic người dùng; chỉ eval T3 + CLI dùng.
- `AdviseOutput` là schema dùng chung (scope refusal, clarify, session) —
  GIỮ class, chỉ bỏ việc LLM sinh ra nó.

---

## Phase 0 — Chốt trạng thái trước khi đụng dao (nửa buổi)

1. Tag git hiện tại (`pre-json-removal`) để rollback được cả cụm.
2. Grep xác nhận lần cuối không còn consumer nào của `POST /chat` ngoài danh sách
   đã biết: route, CLI, eval adapter, test. Kiểm cả `notebooks/`, `scripts/`,
   `docker-compose.yml`, dashboard.
3. Đánh dấu mọi report cũ trong `evaluation/reports/` là LEGACY-JSON (thêm một
   file `LEGACY.md` ghi rõ: các số này đo đường JSON đã bị loại, không so sánh
   trực tiếp với run prose). KHÔNG xóa, KHÔNG sửa nội dung report cũ.

## Phase 1 — Xóa đường JSON khỏi production (1 buổi)

Xóa:

| File | Phần xóa |
|---|---|
| `src/acne_llm/api/routes/chat.py` | Route `POST /chat` (dòng 20–49) + `_chat_new_body` (52–181) |
| `src/acne_llm/chat/orchestrator.py` | Nhánh `response_format=="structured"` (186–187) + `generate_structured()` (234+) + type `ResponseFormat` nếu chỉ còn "text" |
| `src/acne_llm/cli.py` | Mode structured (16–29) — chuyển CLI sang gọi đường prose |
| `src/acne_llm/pipeline/hybrid.py` | `_safe_parse` (25–50), gửi `model_json_schema()` (286), phần generate JSON |
| `src/acne_llm/pipeline/llm_only.py` | Tương tự |
| `config/prompts/hybrid_user.j2`, `llm_only_user.j2` | Xóa file (template bảo trả JSON) |
| `c.llm.generate_json` | Xóa nếu không còn caller nào khác |

Giữ nguyên:
- `AdviseOutput` class — refactor nhẹ nếu cần: scope refusal/clarify/session vẫn
  dựng object tay.
- Toàn bộ SSE: `stream_chat_sse`, `stream_user.j2`, `knowledge_user.j2`,
  `clarify_user.j2`, `WS /ws/chat`.
- `prepare_chat_turn`, retrieval, guardrails, intake, audit — dùng chung, không đụng.

Sau xóa: chạy backend + frontend smoke tay 3-5 câu chat, xác nhận SSE nguyên vẹn.
Cập nhật test của `src/` (xóa test đường JSON, thêm test SSE nếu thiếu).

## Phase 2 — Viết lại eval adapter: đo prose (1–2 buổi)

Nguyên tắc: S0–S4 GIỮ NGUYÊN thiết kế (ma trận model × RAG + extractive floor) —
chỉ đổi cách generate và cách chấm.

1. `evaluation/adapters/ollama_batch.py` viết lại: gọi đúng đường prose production
   (cùng `prepare_chat_turn` + template `stream_user.j2`, non-stream batch call),
   KHÔNG còn schema JSON. Record lưu: prose answer, used_chunks,
   `trace.faithfulness_context` (giữ fix vòng 1), latency.
2. `evaluation/adapters/extractive.py` (S4): giữ nguyên (đã là text).
3. `evaluation/adapters/sse_api.py` (T4): giữ — giờ T3 và T4 đo cùng hành vi,
   T4 chỉ thêm lớp HTTP/streaming thật.
4. Invariants giữ nguyên: no-fallback, session isolation, run_meta đầy đủ.

## Phase 3 — Cập nhật metrics & report cho prose (1–2 buổi)

Bỏ (không còn đối tượng đo):
- `parse_success`, `empty_core_fields_rate`, citation `chunk_ref` checks.
- Confound structured 2×2 tự biến mất — không cần quyết hướng (a)/(b) nữa.

Giữ / thêm — deterministic trên text:
- `grounded_sentence_rate` + `unsupported_sentences` (module grounding — align
  câu với context bằng n-gram + embedding, threshold tune trên D1).
- Safety pattern check trên prose (thuốc kê đơn không kèm cảnh báo, thai kỳ,
  red-flag terms) — port từ deterministic cũ sang text.
- Language check, độ dài, latency.
- Context-sensitivity: canary test + context-swap (runner mới trên D1, đo model
  có thật sự dùng RAG không).

LLM judge trên prose (trở thành tín hiệu chất lượng CHÍNH):
- `pointwise.md` / `pairwise.md` chấm thẳng prose answer — pipeline judge hiện có
  gần như giữ nguyên (nó vốn đã đọc rendered text).
- Faithfulness (claim_extract → entailment) chấm trên prose + exact context.

Report/gate:
- `evaluation/analysis/report.py`: bỏ cột structured, thêm cột grounding +
  sensitivity; giữ code đọc field cũ cho artifact LEGACY.
- `evaluation/configs/gate.yaml`: viết lại mục generation cho prose
  (ngưỡng provisional, KHÔNG tune trên D2).

## Phase 4 — Judge phải đáng tin (BLOCKING — vì giờ eval phụ thuộc judge nặng hơn)

Bỏ structured metrics nghĩa là LLM judge gánh phần lớn tín hiệu chất lượng.
Judge hiện FAIL bias tests (flip 0.22–0.41, consistency 0.5–0.73) → phần này
là điều kiện chặn, không phải việc phụ:

1. Self-consistency k=3 majority vote + trung bình 2 chiều swap trong
   `evaluation/judges/run_judge.py`.
2. Rerun `evaluation.judges.bias_tests` trên D1 đến khi pass cả 3 chỉ tiêu.
3. Human calibration: `export_blind` ~50 case D1 → chấm tay → `import_labels`
   → kappa judge-vs-human. Không pass thì không diễn giải điểm judge.

## Phase 5 — Baseline mới + kiểm chứng (overnight + 1 buổi)

1. Smoke: `run_all --smoke` trên D1 với adapter prose mới.
2. Full T3 prose trên D2 140 case, S0–S4 (overnight, resume-safe).
3. Judge + report + `validate.loop --repro-subset 20` → phải TRUSTWORTHY.
4. `check_gate` với gate mới.
5. Đây là baseline chính thức thay bộ số JSON cũ. Từ đây mọi so sánh
   trước/sau đều trên prose.

## Phase 6 — Dọn dẹp cuối (sau khi Phase 5 TRUSTWORTHY)

- Xóa metric structured code còn sót (trừ phần đọc LEGACY artifact).
- Xóa test/fixture đường JSON trong evaluation.
- Cập nhật `evaluation/README.md`, `docs/EVAL_BLUEPRINT.md`: T3 = prose batch.
- Gỡ flag `inline_citation` nếu quyết định citation model đã chết hẳn
  (grounding metric thay thế).

---

## Ràng buộc chung

- KHÔNG sửa/xóa `evaluation/datasets/v1/` và `evaluation/reports/` cũ
  (chỉ thêm file LEGACY.md đánh dấu).
- KHÔNG tune threshold/prompt/rubric trên D2 — mọi tuning trên D1 dev.
- Mỗi phase kết thúc bằng `pytest evaluation/tests -q` (và test src) xanh.
- Mỗi xóa lớn là một commit riêng, message ghi rõ — rollback từng phần được.
- Paid API judge chỉ dùng ở Phase 4–5, có budget guard.

## Cái giá phải chấp nhận (nói trước)

1. Toàn bộ số liệu n=140 cũ thành lịch sử — baseline làm lại từ đầu.
2. Mất các check máy-đọc từ JSON (severity, red_flags đủ/thiếu) — thay bằng
   safety pattern trên text (yếu hơn) + judge (đắt hơn).
3. Eval phụ thuộc judge nặng hơn → Phase 4 là bắt buộc, không đi tắt được.

## Việc còn treo sau plan này (không thuộc scope)

- Relabel D8 qrels (T2 vẫn vô nghĩa cho tới khi xong).
- Mở rộng T1 seeds; fix guardrails/normalizer đang fail gate.
- T4 SSE e2e full; audit boilerplate finetune (74 mẫu "mặt nạ nghệ").
