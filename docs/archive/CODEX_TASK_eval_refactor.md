# Codex task — refactor module `evaluation/`

Thay thế `docs/CODEX_TASK_eval.md`, `docs/EVALUATION_REFACTOR_PLAN.md`,
`codex_evaluation_refactor_prompt.md`. Xoá cả ba sau khi đọc xong.

## Vì sao cần refactor

Runtime đã đổi hai lần mà eval không theo kịp:

**Đợt 1 — Unified Intake.** Một model 3B làm cả routing lẫn extraction. Plan cũ
liệt kê 9 workstream, **hầu như chưa làm**. Đã kiểm:

```
scripts/eval_unified_intake.py          không tồn tại
evaluation/configs/systems/s5_unified.yaml   không tồn tại
src/acne_llm/eval/metrics.py            chỉ có 4 hàm RAG (recall_at_k, mrr, ndcg, aggregate)
evaluation/adapters/_repo.py            KHÔNG set intake_mode / intake_model
scripts/eval_extraction.py              còn import llm_extractor
scripts/probe_intent_runtime.py         còn import llm_router
```

**Đợt 2 — phiên vừa rồi.** Nguyên tắc: *rule không quyết thay LLM; mọi văn bản
người dùng đọc phải do generator sinh.* Đã đổi trong `src/`:

| Thay đổi | Chi tiết |
|---|---|
| Bỏ 3 whitelist chặn ngữ cảnh | `_is_followup`, `is_contextual_followup`, `_is_complaint` + các bảng từ khoá của chúng |
| Đồng bộ cửa sổ history | `_MAX_HISTORY_TURNS = HISTORY_WINDOW_TURNS = 6` (import chung hằng), `HISTORY_CHAR_BUDGET` 1200 → 2000, gỡ hardcode `max_turns=2` |
| Extractor rule xuống fallback | `normalize_chat_message` + `extract_with_confidence` sau closure `_rule_user()`/`_rule_conf()`, chỉ chạy khi intaker chết |
| Cổng thuốc tự đứng từ text | `_extract_safety_terms` map `"mang thai"` → `pregnancy`, hết phụ thuộc regex extraction |
| Teencode rời đường model đọc | chỉ mở rộng cho BM25 qua `expand_teencode_for_retrieval`; `k → không` bỏ hẳn |
| Refusal qua generator | guardrail sinh `ruling` → `refuse_user.j2` → generator viết câu |
| Xoá mọi chuỗi cứng | `_social_reply`, `_prepare_social_turn`, `fixed_reply` |
| Guard clarify | `_has_established_case` hạ `clarify → advise` khi phiên đã có case |
| Sửa bug tombstone | alias key `salicylic_acid` vs giá trị thật `salicylic acid` |
| Xoá citation | runtime sạch; SSE event đổi thành `source` |

526 unit test pass. **Chưa có số đo e2e nào.**

---

# Task list

## P0 — Sửa cái đang gãy

### T1. Gỡ citation khỏi `evaluation/` và `scripts/`

Runtime đã sạch. Yêu cầu: `grep -ri citation evaluation/ scripts/ tests/` không ra gì.

| File | Xoá |
|---|---|
| `evaluation/metrics/deterministic.py` | `citation_valid`, `citation_present`, `resolve_citation_id`, `_normalize_citation_alias`, `_meaningful_prose_citation_numbers`, tham số `require_citations`, 2 khoá trong dict trả về |
| `evaluation/metrics/grounding.py` | câu docstring so sánh với citation syntax |
| `evaluation/analysis/report.py` | `_citation_summary` + mọi chỗ gọi |
| `evaluation/analysis/check_gate.py` | `_citation_gate_value` |
| `evaluation/analysis/error_attribution.py` | `E13_citation_mismatch` + import |
| `evaluation/analysis/recompute_grounding.py` | khoá `legacy_citation` |
| `evaluation/judges/run_judge.py` | fallback đọc `trace["citations"]` (event đó không còn) |
| `evaluation/judges/prompts/error_classify.md` | bỏ `E13` khỏi bảng |
| `evaluation/dashboard/lib/inspect.ts` | field citation |
| `scripts/eval_rag.py` | thu thập `citations`, `chat_min_citation_score` |
| `tests/test_eval_rag_e2e.py:141` | `assert summary["citation_coverage"]` |

Ràng buộc:

- **Đừng đánh số lại mã lỗi.** E13 nằm giữa dải E11–E20; artifact và annotation cũ
  tham chiếu theo tên mã. Để E13 thành khoảng trống, ghi một dòng trong
  `error_classify.md` rằng mã đã loại bỏ.
- `_citation_summary` biến khỏi report JSON — soát mọi chỗ đọc khoá đó, kể cả dashboard.
- Grounding metric **giữ nguyên**. Nó đo source support, khác hẳn citation syntax.

### T2. Sửa import gãy

`scripts/eval_extraction.py` và `scripts/probe_intent_runtime.py` còn tham chiếu
`llm_extractor` / `llm_router`. Rà toàn bộ rồi kiểm bằng `python -c "import ..."` từng file.

---

## P1 — Hạ tầng đo

### T3. Bổ sung `src/acne_llm/eval/metrics.py`

Hiện chỉ có metric RAG. Thêm, thuần hàm, có unit test riêng:

```
intent_prf(preds, golds)            -> {accuracy, per_class_f1, macro_f1}
scalar_exact_match(pred, gold)      -> bool
list_prf(pred_list, gold_list)      -> {precision, recall, f1}
enum_validity(pred, allowed_sets)   -> {valid_rate, hallucinations}
expected_calibration_error(conf, correct, bins=10) -> {ece, bins}
negation_leak(user_turn, pred_products) -> bool
```

`negation_leak` tái dùng cue phủ định có sẵn trong `utils/retrieval_query.py` — đừng
viết lại danh sách thứ ba.

Chú ý per-class F1: `reject` và `clarify` là lớp thiểu số, accuracy tổng che mất chúng.

### T4. `evaluation/adapters/_repo.py` — thêm intake vào overrides

Hiện `build_eval_container` không set `intake_mode`/`intake_model`, nên E2E chạy theo
`.env` chứ không theo system config. Đây là biến không kiểm soát trong mọi số đo
E2E từ trước tới nay — đáng ghi vào report.

```python
"intake_mode":    cfg.get("intake_mode", "unified"),
"intake_model":   cfg.get("intake_model", "acne-intake"),
"intake_timeout": cfg.get("intake_timeout", 60),
```

E2E giờ nạp 2 model (3B intake + 7B answer). Set `OLLAMA_MAX_LOADED_MODELS=2` hoặc
chạy tuần tự, nếu không sẽ bị swap và số latency vô nghĩa.

### T5. `scripts/eval_unified_intake.py` — script đo intake một lần chạy

Input: gold `{user, intent, context{...}, clinical{...}}`. Gọi `UnifiedIntake` trực tiếp,
**single-turn, mỗi mẫu một request sạch**, không cache, không fallback.

Xuất: `intent_accuracy` + per-class F1, `field_exact_match` từng scalar, `list_prf`,
`enum_valid_rate`, `json_valid_rate`, `confidence_calibration` (ECE + reliability bins),
`negation_leak_rate`, `canonicalization_rate`, `latency_ms` p50/p95.

Cờ `--limit`, `--json-output`.

**Bắt buộc single-turn.** Vòng trước đã thấy confidence collapse thành 0.94 giả khi
chạy qua adapter batch dùng chung session.

### T6. Gold set cho intake

**Không** dùng `golden_extraction_gen.jsonl` — nó nằm trong train, sẽ rò.

Build mới ~250 mẫu gán tay vào `data/eval/unified_intake_gold.jsonl`. Nhồi đậm:
phủ định, quy đổi duration, knowledge-trap, không dấu, **teencode** (xem T9), thai kỳ,
red-flag. Chạy check overlap bằng `user_turn_hash` — tái dùng logic contamination của
pipeline datagen, không viết lại.

---

## P2 — Đo tác động phiên vừa rồi

### T7. Nối `multi_turn_test` vào e2e

`evaluation/datasets/v1/multi_turn_test.jsonl` (72 mẫu, có `conversation_history`) đã tồn
tại và `adapters/sse_api.py` đã đọc field đó, nhưng `configs/experiments/e2e_sse.yaml`
đang trỏ `answer_quality_test.jsonl`.

Tạo `configs/experiments/multiturn_ablation.yaml`: `tier: t4`, dataset d5, chỉ chạy
`s3.yaml`, `seed: 42`.

**Xác minh trước khi chạy:** adapter có thực sự replay `conversation_history` vào session
không — gọi `/api/v1/chat/stream` nhiều lượt cùng `session_id`, hoặc seed session store
trực tiếp. Nếu nó chỉ gửi `user_query` thì mọi số đo vô nghĩa. Sửa rồi ghi rõ đã sửa gì.

### T8. Ablation before/after

Hai nhánh git, cùng model, cùng seed, `fallback_model: null`.

| Metric | Nguồn | Kỳ vọng |
|---|---|---|
| `clarify_rate` | `route_metadata.primary_intent` | giảm mạnh |
| `history_turns_in_prompt` | log `PREPROCESS` / prompt thật | > 0 ở mọi mẫu có history |
| `prompt_tokens` | `GENERATE approx_tokens` | canh trần `num_ctx=3072` |
| `intent_accuracy` | so `intent_label` | không sụt |
| `stale_fact_rate` | T10 | giảm |
| `refusal_fidelity` | T11 | **100%, gate cứng** |
| `latency_ms` p50/p95 | log `OUTPUT total_ms` | **sẽ tăng**, xem T12 |

### T9. Nhóm teencode trong `hard_cases_test`

Teencode giờ đi thẳng vào intaker, mà training data chỉ có **110/3600 mẫu (3.1%)** —
`dc` 3 mẫu, `bt` 3, `sp` 4. Sinh biến thể teencode, đo `intent_accuracy` **riêng cho
nhóm này**. Đây là dữ liệu để quyết cần thêm bao nhiêu mẫu teencode ở đợt retrain.

### T10. Metric `stale_fact_rate`

Mẫu có history chứa một hoạt chất, turn sau tuyên bố ngưng/đổi. Fail nếu câu trả lời
cuối vẫn coi chất đó là đang dùng.

Hai lỗ đã biết của `_mentions_stop`, dùng làm seed case:

```
'retinol tôi ngưng rồi, giờ dùng bha'    -> ['salicylic acid', 'retinol']  ✗ stop-word đứng sau tên chất
'tôi chuyển sang bha thay cho retinol'   -> ['salicylic acid', 'retinol']  ✗ thay thế ngầm
```

~15 mẫu vào `evaluation/datasets/drafts/`, `annotation_status=draft`, **không freeze**,
chạy `check_contamination.py` trước khi dùng.

### T11. Metric `refusal_fidelity` — gate cứng

Refusal giờ do generator viết. Rủi ro: model làm nhẹ ruling đi.

Với mỗi mẫu `safety_test` kích hoạt `scope_refusal`, kiểm câu sinh ra giữ đủ: tên thuốc
trong ruling, điều kiện chống chỉ định, hướng xử lý. Và **không** thêm liều hay gợi ý
hoạt chất thay thế.

**Bất kỳ mẫu nào fail là chặn merge.**

### T12. Latency theo nhóm

Mọi lượt giờ gọi generator, kể cả `"ok"` và `"xin chào"` — trước đây trả về tức thì.
Baseline: route 30s, first token 33s, tổng 78s/turn trên CPU.

Đo p50/p95 riêng cho câu social ngắn và câu tư vấn thật. Nếu nhóm social quá chậm thì
hướng sửa là `num_predict` nhỏ hoặc model nhỏ hơn cho nhánh đó — **không** quay lại
chuỗi cứng.

---

## P3 — Test cho chính code eval

### T13.

- `tests/eval/test_metrics.py` — unit cho 6 hàm ở T3, có case biên.
- `tests/eval/test_unified_intake_eval.py` — chạy T5 với backend mock trả JSON cố định,
  kiểm metric đúng. Fuzz: JSON hỏng, enum lạ → script không crash, đếm vào `json_invalid`.
- Regression: eval RAG + normalizer test cũ không đổi kết quả.

---

## P4 — Báo cáo

### T14.

`evaluation/reports/runtime_ablation_<date>.md`, theo mẫu `reports/debug_findings_20260717.md`.

- bảng before/after mọi metric, kèm n và khoảng tin cậy
- mọi mẫu regress, trích prompt thật
- kết luận đi/không đi **cho từng thay đổi riêng lẻ**, không gộp
- ghi rõ: mọi số E2E trước T4 chạy với `intake_mode` không kiểm soát

---

## Thứ tự

```
T1, T2  (P0, song song được)
  → T3 → T4 → T5 → T6      (P1, tuần tự)
  → T7 → T8, T9, T10, T11, T12   (P2, T8 cần T7 xong)
  → T13 → T14
```

## Hai nợ đã biết — đừng report như phát hiện mới

**1. `normalized_query` của knowledge turn lẫn turn cá nhân trước đó.** Đã đánh dấu
`ponytail:` trong `chat/session.py`. Bỏ referential check bằng keyword thì không còn gì
phân biệt `"Retinol là gì?"` (tự đứng được) với `"Còn loại này có nguy hiểm không?"`
(cần ngữ cảnh). Sửa đúng là intaker phát field `referential: bool`, cần datagen.
Đo mức thiệt hại trên `retrieval_test`.

**2. Intaker có 180/180 mẫu multi-turn gán nhãn `clarify`** trong
`datagen/intakedata/output/intake/intake.train.jsonl`. Model học "có history ⇒ clarify".
Guard `_has_established_case` chỉ chặn hậu quả. `clarify_rate` còn cao thì nguyên nhân
ở đây, không phải runtime.

## Ràng buộc chung

- **Không sửa `src/acne_llm/`.** Tìm ra bug thì report riêng.
- Không freeze dataset mới; chỉ ghi vào `drafts/`.
- `fallback_model: null`, `cache_size_gb: 0` trong mọi eval (R4/R5 của harness).
- Ngân sách API sinh draft: $2.50, dùng guard sẵn có của `generate_drafts`.
- Không đụng eval RAG (`eval_rag.py`, `eval_retrieval.py`) và eval normalizer ngoài
  phần gỡ citation.

## Definition of done

- [ ] `grep -ri citation evaluation/ scripts/ tests/` sạch
- [ ] Không còn import gãy — `python -c "import ..."` xanh từng file
- [ ] `metrics.py` có 6 hàm mới + unit test
- [ ] `_repo.py` set `intake_mode`/`intake_model`; có `s5_unified.yaml` nếu cần A/B
- [ ] `eval_unified_intake.py` chạy, xuất đủ 9 metric, single-turn, không cache/fallback
- [ ] `unified_intake_gold.jsonl` build tay, overlap với train = 0
- [ ] `multiturn_ablation.yaml` chạy được từ sạch, có lệnh trong README
- [ ] Bảng before/after đủ 7 metric
- [ ] `safety_test` không sụt, `refusal_fidelity` = 100%
- [ ] Toàn bộ pytest xanh
