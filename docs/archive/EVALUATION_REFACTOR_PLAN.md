# Plan refactor module `evaluation/` theo runtime Unified Intake

> Sau khi runtime chuyển sang **Unified Intake 3B** (extract+route 1 call, `intake_mode`, 2 LLM adapter cũ
> vào `chat/legacy/`), module đánh giá phải theo kịp. Plan này liệt kê **tất cả** việc cần làm, theo workstream,
> grounded theo file thật.

---

## 0. Nguyên tắc

- **Không rớt cái đang đúng.** Eval RAG (`eval_rag.py`, `eval_retrieval.py`) và eval normalizer
  (`scripts/eval/normalizer/`) KHÔNG bị ảnh hưởng — giữ nguyên.
- **A/B được:** mọi eval intake phải chạy được cả `legacy` (2 module cũ) lẫn `unified` để so sánh.
- **Single-turn/stateless bắt buộc** khi eval model (bài học: session nhồi context làm hỏng confidence).
- **Data sạch:** KHÔNG dùng `golden_extraction_gen.jsonl` làm gold (đã nằm trong train).

---

## 1. Bản đồ coupling hiện tại (đã khảo sát)

| File eval | Bám runtime cũ ở đâu | Ảnh hưởng |
|---|---|---|
| `scripts/eval_extraction.py` | `from acne_llm.chat.llm_extractor import LLMExtractor`; `from ...intent_router import route_intent`; `settings.extractor_model` (acne-extractor:1.5b); `extractor.run(...)` | **Gãy import** khi llm_extractor → legacy; cần thêm mode unified |
| `scripts/eval_semantic_router.py` | so semantic vs legacy rule router | Thiếu arm cho intent của unified model |
| `evaluation/adapters/_repo.py` | `build_container(settings)`; override `llm_model` (7B) | Chưa set `intake_mode`/`intake_model` → E2E vẫn chạy runtime cũ |
| `evaluation/configs/systems/*.yaml` | định nghĩa system under test (adapter/model) | Chưa có system `unified` |
| `src/acne_llm/eval/metrics.py` | chỉ có `recall_at_k`/`mrr`/`ndcg`/`aggregate` (RAG) | **Thiếu** metric extraction/intent/calibration |
| `scripts/eval_from_finetune_test.py`, `eval_extraction_quick.py` | (kiểm lại import) | Có thể gãy nếu tham chiếu llm_extractor |
| `evaluation/analysis/figures_eval.py`, `dashboard/` | vẽ/hiển thị kết quả | Thêm arm unified (ưu tiên thấp) |

---

## 2. Workstream 1 — Sửa import gãy (LÀM TRƯỚC, nếu không eval crash)

Sau khi `llm_extractor.py`/`llm_router.py` → `chat/legacy/` và parser tách ra `chat/_intake_parse.py`:
- `scripts/eval_extraction.py`:
  - `from acne_llm.chat.legacy.llm_extractor import LLMExtractor`
  - Các helper parse (nếu dùng) → `from acne_llm.chat._intake_parse import ...`
- Rà **toàn bộ** `scripts/` + `evaluation/` bằng: `grep -rn "chat.llm_extractor\|chat.llm_router\|import LLMExtractor\|import LLMRouter"` → sửa hết sang `chat.legacy.*`.
- Chạy `python -c "import <module>"` từng file để xác nhận import OK.

---

## 3. Workstream 2 — Script eval HỢP NHẤT mới `scripts/eval_unified_intake.py` (lõi)

Vì 1 model làm cả 2 việc, tạo **một script đo tất cả trong một lần chạy**:

- Input: bộ gold gán tay (mục 7), mỗi dòng `{messages:[system,user,assistant_gold]}` hoặc `{user, intent, context, clinical}`.
- Chạy model **single-turn** (build_container `intake_mode=unified` HOẶC gọi `UnifiedIntake` trực tiếp), mỗi mẫu 1 inference sạch.
- **Metric xuất ra** (JSON + bảng):
  1. `intent_accuracy` tổng + **per-class F1** (chú ý reject/clarify thiểu số).
  2. `field_exact_match` từng scalar (age/sex/skin_type/is_pregnant/duration_weeks).
  3. `list_precision/recall/F1` cho lesion_types / lesion_distribution / current_products / medications.
  4. `enum_valid_rate` (kỳ vọng ~1.0 nhờ constrained) + đếm enum-hallucination.
  5. `json_valid_rate` (parse được contract).
  6. **`confidence_calibration`**: ECE + reliability bins (đối chiếu conf vs đúng/sai). Đây là chỗ quan trọng — test đã thấy conf collapse khi nhiễu session, nên phải đo trên gọi single-turn.
  7. `negation_leak_rate` (chất đã ngưng lọt current_products/medications).
  8. `canonicalization_rate` (differin→adapalene, BHA→salicylic acid…).
  9. `latency_ms` p50/p95 mỗi request.
- Cờ `--mode unified|legacy` để A/B; `--limit`, `--json-output reports/unified_intake_eval.json`.
- KHÔNG dùng cache, KHÔNG fallback (đo đúng model path) — theo pattern `_repo.py` (`fallback_model=None`, `cache_size_gb=0`).

---

## 4. Workstream 3 — Adapt script cũ (giữ cho A/B, không xoá)

- `scripts/eval_extraction.py`: thêm `--mode unified` → dựng `UnifiedIntake`, đo field metrics từ `.run()`.
  Giữ `--mode rule` (deterministic) + `--mode llm` (legacy 1.5b, import từ `chat.legacy`) để so 3 đường.
- `scripts/eval_semantic_router.py`: thêm arm `unified` — đo intent của `UnifiedIntake.classify()` trên
  `intent_classify.test.jsonl` cạnh semantic + rule. Xuất so sánh 3 đường.
- Cả hai reuse metric mới ở Workstream 5, không tự tính lại.

---

## 5. Workstream 4 — E2E adapter + configs

- `evaluation/adapters/_repo.py` `build_eval_container`: thêm vào `overrides`:
  ```
  "intake_mode":   cfg.get("intake_mode", "legacy"),
  "intake_model":  cfg.get("intake_model"),
  "intake_timeout": cfg.get("intake_timeout", 60),
  ```
  → E2E chạy được qua runtime unified. Lưu ý: E2E giờ có **2 model** (3B intake + 7B answer);
  `llm_model` vẫn là 7B answer, thêm `intake_model` cho 3B.
- Thêm system config `evaluation/configs/systems/s5_unified.yaml` (clone s3, thêm `intake_mode: unified`, `intake_model: acne-intake`).
- Thêm arm vào experiment config (`main_2x2.yaml` hoặc mới `unified_vs_legacy.yaml`): so s3 (legacy) vs s5 (unified) trên cùng bộ E2E.
- Kiểm handoff 3B↔7B khi eval (VRAM): eval batch có thể ép swap — set `OLLAMA_MAX_LOADED_MODELS=2` hoặc chạy tuần tự.

---

## 6. Workstream 5 — Bổ sung `src/acne_llm/eval/metrics.py`

Hiện chỉ có metric RAG. Thêm (thuần hàm, có unit test):
- `intent_prf(preds, golds) -> {accuracy, per_class_f1, macro_f1}`.
- `scalar_exact_match(pred, gold, field) -> bool` + gộp `field_accuracy(...)`.
- `list_prf(pred_list, gold_list) -> {precision, recall, f1}` (so theo set enum).
- `enum_validity(pred, allowed_sets) -> {valid_rate, hallucinations}`.
- `expected_calibration_error(confidences, correctness, bins=10) -> {ece, bins}`.
- `negation_leak(user_turn, pred_products) -> bool` (tái dùng cue phủ định từ `retrieval_query.py`).
- Giữ nguyên metric RAG cũ.

---

## 7. Workstream 6 — Data eval (quan trọng, có ràng buộc)

- **Intent gold:** giữ `data/eval_labels/... intent_classify.test.jsonl` (260) — đã tách khỏi train.
- **Extraction gold (PHẢI build mới ~250, gán tay):** KHÔNG lấy từ `golden_extraction_gen.jsonl`
  (đã nằm trong train → rò). Nhồi đậm: negation, duration-convert, knowledge-trap, no-accent, pregnancy, red-flag.
  Định dạng: `{user, intent, context{...}, clinical{...}}` để `eval_unified_intake.py` chấm exact-match.
- **Unified gold hợp nhất:** ghép intent + extraction gold vào một file `data/eval/unified_intake_gold.jsonl`
  để một lần chạy đo hết.
- Ghi rõ trong README eval: nguồn gold, cam kết không giao với train (chạy check overlap bằng
  `user_turn_hash` như pipeline datagen — tái dùng logic contamination).

---

## 8. Workstream 7 — Harness A/B legacy vs unified

- Script/notebook chạy `eval_unified_intake.py --mode legacy` và `--mode unified` trên **cùng gold**,
  xuất bảng so sánh: intent-acc, per-class F1, field exact-match, list F1, ECE, json-valid, latency p50/p95.
- **Tiêu chí chấp nhận:** unified **không tệ hơn** legacy về intent-acc/field-match, và **latency giảm** (2 call → 1).
- Regression an toàn: chạy `safety_set.jsonl` + ca red-flag/trầm cảm → xác nhận reject + guardrails, model không bịa clinical.

---

## 9. Workstream 8 — Analysis / figures / dashboard (ưu tiên thấp)

- `evaluation/analysis/figures_eval.py`: thêm arm unified vào biểu đồ so sánh; thêm reliability diagram (calibration).
- `evaluation/dashboard/`: thêm cột/field cho intent-F1, field exact-match, ECE nếu muốn hiển thị; không chặn việc chính.

---

## 10. Workstream 9 — Test cho chính code eval

- `tests/eval/test_metrics.py`: unit cho các hàm metric mới (intent_prf, list_prf, ECE, enum_validity) với case biên.
- `tests/eval/test_unified_intake_eval.py`: chạy `eval_unified_intake` với backend mock trả JSON cố định →
  metric đúng; **fuzz**: JSON hỏng/enum lạ → script không crash, đếm vào json_invalid.
- Regression: eval RAG + normalizer test cũ vẫn xanh.

---

## 11. Thứ tự thực thi + Definition of Done

Thứ tự: **WS1 (sửa import) → WS5 (metrics) → WS2 (script hợp nhất) → WS6 (data gold) → WS3 (adapt cũ) → WS4 (E2E/config) → WS7 (A/B) → WS10 (test) → WS8/9 (figures/dashboard)**.

DoD:
- [ ] Không còn import gãy trong `scripts/` + `evaluation/` (grep sạch `chat.llm_extractor`/`chat.llm_router`).
- [ ] `eval_unified_intake.py` chạy, xuất đủ 9 metric, single-turn, không cache/fallback.
- [ ] `metrics.py` có hàm intent/field/list/enum/ECE/negation + unit test xanh.
- [ ] `data/eval/unified_intake_gold.jsonl` build tay, check overlap với train = 0.
- [ ] `_repo.py` + `s5_unified.yaml` cho E2E unified; A/B legacy vs unified ra bảng.
- [ ] eval RAG/normalizer cũ KHÔNG đổi kết quả.
- [ ] Toàn bộ pytest (repo + eval) xanh.

---

## 12. Ghi chú then chốt

- **Confidence eval phải single-turn** — nếu chạy qua adapter batch dùng chung session sẽ tái hiện lỗi 0.94 giả. Mỗi mẫu 1 request sạch.
- **Canonicalization**: đã biết model đôi khi miss (differin→adapalene); đo `canonicalization_rate` để định lượng, quyết định có cần thêm data hay để `retrieval_query.py` lo.
- **Gold không giao train**: bắt buộc check overlap (tái dùng logic contamination của pipeline datagen) trước khi tin số liệu.
