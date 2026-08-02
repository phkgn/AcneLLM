# Nhiệm vụ Codex: Refactor module `evaluation/` cho runtime Unified Intake

Bạn là agent thực thi. Cập nhật hệ đánh giá để đo **đúng runtime hiện tại** (Unified Intake 3B, `intake_mode`,
script fallback đã ở `chat/fallback/`). Làm **cẩn thận, không để lỗi**, chỉ chạy test — KHÔNG deploy/ollama.

**Đọc trước, bắt buộc:**
1. `docs/EVALUATION_REFACTOR_PLAN.md` — plan chi tiết (làm ĐÚNG theo, đây là nguồn thiết kế).
2. `scripts/eval_extraction.py`, `scripts/eval_semantic_router.py` — eval intake cũ.
3. `evaluation/adapters/_repo.py` — cách build container cho E2E.
4. `src/acne_llm/eval/metrics.py` — hiện chỉ có metric RAG (recall/mrr/ndcg).
5. `src/acne_llm/chat/unified_intake.py` — model đang đo; `evaluation/configs/systems/s3.yaml` — mẫu system config.

---

## Ràng buộc cứng (vi phạm = fail)

1. **KHÔNG deploy/ollama/train.** Chỉ `pytest -q`, `ruff check`, `python -c "import ..."`. Backend model trong test = **mock** (không gọi Ollama thật).
2. **KHÔNG rớt cái đang đúng.** Eval RAG (`eval_rag.py`, `eval_retrieval.py`) và eval normalizer (`scripts/eval/normalizer/`) giữ nguyên, không đổi kết quả.
3. **Đo model, không đo fallback.** Ở `mode=unified`, mọi mẫu bị fallback (reason ≠ `unified_intake`) phải **đếm riêng vào `fallback_rate`** và KHÔNG tính vào metric model. `fallback_rate>0` = cảnh báo runtime chưa sạch, in đậm.
4. **Single-turn/stateless.** Mỗi mẫu 1 request sạch, KHÔNG tái dùng session/history (bài học: session nhiễu làm hỏng confidence). Tắt cache + fallback như pattern `_repo.py` (`fallback_model=None`, `cache_size_gb=0`).
5. **Gold không giao train.** Trước khi tin số liệu extraction, check overlap `user_turn` giữa gold và `intake.train.jsonl` = 0 (tái dùng `user_turn_hash`). KHÔNG dùng `golden_extraction_gen.jsonl` làm gold (đã ở train).
6. **Sau mỗi phase chạy `pytest -q` — phải xanh** rồi mới sang phase sau.

---

## Tiền đề (kiểm trước khi bắt đầu)

Prompt dọn runtime (`codex_runtime_cleanup_prompt.md`) đã chuyển script fallback vào `chat/fallback/` và sửa
import eval. Verify: `grep -rn "chat\.\(llm_extractor\|llm_router\|semantic_router\|intent_router\)" scripts evaluation`
= rỗng (đã trỏ `chat.fallback.*`). Nếu còn sót → sửa nốt trước khi tiếp.

---

## PHASE 1 — Bổ sung metric (`src/acne_llm/eval/metrics.py`) — LÀM TRƯỚC

Thêm hàm thuần (mọi hàm có unit test), giữ nguyên metric RAG cũ:
- `intent_prf(preds, golds) -> {accuracy, macro_f1, per_class_f1}` — chú ý reject/clarify thiểu số.
- `scalar_field_accuracy(preds, golds, field) -> float` (exact-match: age/sex/skin_type/is_pregnant/duration_weeks).
- `list_prf(pred_list, gold_list) -> {precision, recall, f1}` — so theo set enum (lesion_types, lesion_distribution, current_products, medications).
- `enum_validity(values, allowed) -> {valid_rate, hallucinations}`.
- `expected_calibration_error(confidences, correctness, bins=10) -> {ece, bins}` + reliability bins.
- `negation_leak(user_turn, pred_products) -> bool` (tái dùng cue phủ định từ `utils/retrieval_query.py`).
- `canonicalization_hit(user_turn, pred_products) -> bool|None` (differin→adapalene, BHA→salicylic acid…).

Test: `tests/eval/test_metrics.py` — case biên cho từng hàm (list rỗng, toàn sai, calibration hoàn hảo vs lệch).

---

## PHASE 2 — Script eval hợp nhất `scripts/eval_unified_intake.py` (lõi)

Một script đo tất cả trong một lần chạy trên bộ gold:
- **Input gold:** `--gold data/eval/unified_intake_gold.jsonl` (mỗi dòng `{user, intent, context{...}, clinical{...}}`
  hoặc format messages). **Nếu file KHÔNG tồn tại** → in cảnh báo rõ + chạy **intent-only** từ
  `data/intent_classify.test.jsonl` (260, có sẵn) để script vẫn dùng được ngay; extraction metric = "n/a".
- **Chạy model single-turn:** dựng container `intake_mode=unified` (qua helper giống `_repo.py`) HOẶC gọi
  `UnifiedIntake` trực tiếp; mỗi mẫu 1 inference; không cache, không fallback path.
- **Xuất metric (JSON + bảng console):** intent accuracy + per-class F1; field exact-match; list P/R/F1;
  enum_valid_rate + hallucination count; json_valid_rate; ECE + reliability; negation_leak_rate;
  canonicalization_rate; latency p50/p95; **fallback_rate** (guard ràng buộc 3).
- Cờ: `--mode unified|legacy`, `--limit N`, `--json-output reports/unified_intake_eval.json`, `--gold PATH`.
- **Overlap guard:** khi có gold, tự check overlap với `datagen/intakedata/output/intake/intake.train.jsonl`;
  nếu >0 → cảnh báo đỏ + ghi số vào output (số liệu extraction không đáng tin nếu rò).

---

## PHASE 3 — Adapt script cũ (giữ cho A/B, không xoá)

- `scripts/eval_extraction.py`: thêm `--mode unified` (dựng `UnifiedIntake`, đo field từ `.run()`); giữ
  `--mode rule` + `--mode llm` (legacy 1.5b, import `chat.fallback.llm_extractor`). Dùng lại metric Phase 1.
- `scripts/eval_semantic_router.py`: thêm arm `unified` (intent của `UnifiedIntake.classify()` trên
  `intent_classify.test.jsonl`) cạnh semantic + rule; xuất so sánh 3 đường bằng `intent_prf`.

---

## PHASE 4 — E2E adapter + config

- `evaluation/adapters/_repo.py` `build_eval_container`: thêm vào `overrides`:
  `intake_mode` (default "legacy"), `intake_model`, `intake_timeout` — đọc từ config eval. Để E2E chạy được qua runtime unified.
- Tạo `evaluation/configs/systems/s5_unified.yaml` (clone `s3.yaml`, thêm `intake_mode: unified`, `intake_model: acne-intake`).
- Thêm arm so sánh vào một experiment config (mới `evaluation/configs/experiments/unified_vs_legacy.yaml`): s3 (legacy) vs s5 (unified) trên cùng bộ E2E.
- Ghi chú trong config: E2E giờ có 2 model (3B intake + 7B answer); trên máy nhỏ set `OLLAMA_MAX_LOADED_MODELS`/`keep_alive` phù hợp.

---

## PHASE 5 — Test cho code eval

- `tests/eval/test_unified_intake_eval.py`: chạy `eval_unified_intake` với **backend mock** trả JSON cố định
  → metric đúng; **fuzz không-crash:** JSON hỏng/enum lạ/confidence ngoài [0,1] → script không crash,
  đếm vào json_invalid; mock một mẫu fallback → `fallback_rate` phản ánh đúng.
- Regression: test eval RAG + normalizer cũ vẫn xanh.

---

## Ngoài phạm vi Codex (ghi rõ, KHÔNG tự bịa)

- **Bộ gold extraction gán tay (~250)** là việc của người, KHÔNG tự sinh. Script phải chạy được intent-only
  khi thiếu gold (Phase 2). Có thể tạo `scripts/eval/build_gold_template.py` để scaffold khung gold từ
  `intent_classify.test.jsonl` (điền sẵn intent, để trống context/clinical cho người gán) — tiện, không bắt buộc.
- Figures/dashboard (`analysis/figures_eval.py`, `dashboard/`) — ưu tiên thấp, KHÔNG làm trong task này.

---

## Verify cuối (in báo cáo)

- `pytest -q` xanh toàn bộ (repo + eval cũ + eval mới).
- `python -c "import scripts.eval_unified_intake"` OK (hoặc chạy `--help`).
- `grep -rn "chat\.\(llm_extractor\|semantic_router\|intent_router\|llm_router\)" scripts evaluation` = rỗng ngoài fallback.
- `eval_unified_intake.py` chạy được ở chế độ intent-only (không cần gold) với backend mock trong test.

## Definition of Done
- [ ] `metrics.py` có intent/field/list/enum/ECE/negation/canonical + `tests/eval/test_metrics.py` xanh.
- [ ] `scripts/eval_unified_intake.py`: single-turn, no cache/fallback, đủ metric + `fallback_rate` + overlap guard; chạy intent-only khi thiếu gold.
- [ ] `eval_extraction.py` + `eval_semantic_router.py` có arm `unified`, dùng chung metric, giữ A/B.
- [ ] `_repo.py` + `s5_unified.yaml` + `unified_vs_legacy.yaml` cho E2E.
- [ ] Test eval mới + fuzz không-crash xanh; eval RAG/normalizer KHÔNG đổi.
- [ ] Báo cáo: file thêm/sửa, diff tóm tắt, kết quả verify. KHÔNG deploy/ollama/train.
