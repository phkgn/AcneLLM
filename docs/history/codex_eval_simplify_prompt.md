# Codex Prompt — Simplify Evaluation Module (final thesis pipeline)

## Bối cảnh

Evaluation module hiện tại có quá nhiều đường eval (T1 unit evals, probe, nhiều preset). Quyết định cuối: pipeline eval chỉ còn **4 khối, 1 orchestrator**:

```
[1] intake_eval (LLM Intaker)  →  [2] rag_eval  →  [3] generator_eval (T3+judge+report, TRỌNG TÂM)
                                                        ↓
                              [4] bottleneck Z → X → W → Y (ceiling analysis, cả 4 arm)
```

Mọi thứ khác: XÓA. Không giữ "để sau", không comment-out.

## Nguyên tắc chung (bắt buộc)

- KHÔNG tạo pipeline mới — tái dùng module hiện có (`run_experiment`, `judges/run_judge`, `analysis/report`, `runners/run_retrieval`, `scripts/eval_unified_intake.py`, `scripts/eval_bottleneck.py`). Chỉ refactor orchestrator + metric + xóa code chết.
- Mọi eval đi qua đúng đường runtime: `prepare_chat_turn` / UnifiedIntake thật. Không eval module fallback.
- Safety metric báo riêng, không bao giờ gộp vào quality score.
- Fail-soft: bước fail ghi FAIL vào summary, chạy tiếp bước độc lập; chỉ preflight fail mới dừng.
- Diff nhỏ nhất có thể đạt yêu cầu. Xóa nhiều hơn thêm.

## Task 1 — Xóa code eval không dùng

Xóa hẳn (code + dataset seed nếu không ai khác dùng + lệnh dashboard + test tương ứng):

- `evaluation/unit/eval_intent_router.py`, `eval_query_planner.py`, `eval_normalizer.py`, `eval_guardrails.py`, `eval_context_sensitivity.py` (toàn bộ `evaluation/unit/`)
- `evaluation/probe/` + trang `/probe` + `app/api/probe/` + `ProbeClient.tsx` trong dashboard
- Command IDs trong dashboard: `t1_normalizer`, `t1_intent`, `t1_planner`, `t1_guardrails`, `probe_semantic`, `preliminary_d2` (preset này bị thay bởi orchestrator mới với `--smoke`)
- `evaluation/dashboard/scripts/run_preliminary_d2.py` (pattern của nó chuyển vào run_all mới)
- Cập nhật `command-ids.ts`, `commands.ts`, `types.ts`, RunsClient catalog, DashboardClient quick-launch, nav (bỏ Probe), tests dashboard tương ứng.

Giữ nguyên: trang Overview/Runs/Results/Figures/Inspect/Review, job/SSE/kill infra, Review workflow D1–D7.

## Task 2 — Nâng `scripts/eval_unified_intake.py` lên 3 tầng metric

Dataset: `datagen/intakedata/output/intake/intake.val.jsonl` (held-out, giữ overlap guard với train).

Output `evaluation/reports/intake_eval/report.json` với 3 tầng:

1. **Format**: `schema_valid_rate` (% parse JSON OK và pass schema: đủ key, đúng type/enum). Báo riêng `parse_fail_rate` và `schema_violation_rate`.
2. **Intent**: accuracy, macro-F1 (advise/knowledge/clarify/reject), `reject_recall` riêng, confusion matrix.
3. **Extraction**: per-field precision/recall/F1 — exact match cho enum/số, fuzzy (dùng `utils/fuzzy_match` sẵn có) cho thuốc/sản phẩm; micro + macro; `hallucinated_field_rate` (điền field không có căn cứ trong input).

Phụ: latency p50/p95 mỗi call.

## Task 3 — Refactor `evaluation/run_all.py` thành orchestrator duy nhất

```
python -m evaluation.run_all [--out DIR] [--smoke] [--limit N] [--skip STEPS] [--yes]

[0] preflight      (Ollama, 2 models, chroma_db, bm25, datasets, judge key)
[1] intake_eval    → scripts/eval_unified_intake.py
[2] rag_eval       → runners/run_retrieval trên d8_qrels (đủ 5 mode ablation)
[3] t3_generation  → run_experiment main_2x2.yaml, S0–S4, --resume mặc định
[4] judge+report   → run_judge (pointwise+pairwise+faithfulness) + analysis/report   [$ confirm]
[5] bottleneck     → eval_bottleneck arm z, x, w, y tuần tự, cùng dataset, cùng output  [$ confirm cho y]
[6] figures        → generate_figures --run-dir <out>
```

- Mỗi bước ghi vào `<out>/summary.json`: status OK/FAIL/SKIPPED + duration + lý do skip.
- `--smoke`: limit 10 mẫu mỗi bước, skip bước [5].
- Auto-skip: thiếu judge key → skip [4] phần judge + arm y; dataset thiếu `intent_label` → skip arm x kèm warning rõ (validate sẵn có trong eval_bottleneck).
- Cost gate: 1 câu confirm duy nhất trước [4] (gộp cả arm y); `--yes` bỏ qua.
- Tái dùng pattern `run_step`/`write_summary` từ `run_preliminary_d2.py` trước khi xóa file đó.
- Dashboard: nút "Run all" + `run_all` command giữ ID cũ, trỏ orchestrator mới; thêm arg `smoke`, `limit`, `skip`, `yes` vào form (validator kiểu whitelist như hiện tại, SKIP_STEPS mới = `intake,rag,t3,judge,bottleneck,figures`).

## Task 4 — Data bottleneck: nâng cấp d8_qrels

- Thêm field `intent_label` (advise|knowledge|clarify|reject) vào schema d8_qrels để arm X chạy được. KHÔNG tự sinh label bằng LLM — tạo file draft `evaluation/datasets/drafts/v1/d8_qrels_seed.draft.jsonl` (copy d8 + cột intent_label rỗng) và wire vào trang Review như một dataset key mới `d8` để con người label qua UI (tái dùng toàn bộ review workflow: hash, approve, export).
- Validation rule cho d8 trong `dataset-review.ts`: `intent_label` bắt buộc thuộc 4 giá trị, `relevant_chunk_ids` không rỗng, `relevance_grade` là map.
- `eval_bottleneck.py` giữ nguyên validate arm X (đã đúng).

## Task 5 — Judge calibration

- Thêm script `evaluation/judges/calibrate.py`: lấy ngẫu nhiên 50 mẫu đã judge từ run dir, xuất `calibration_sheet.jsonl` (query + answer + rubric, chưa có điểm judge để tránh anchor), nhận lại file người chấm, tính Cohen's κ + Spearman giữa human và judge, ghi `evaluation/reports/judge_calibration.json`.
- Results page hiển thị κ nếu file tồn tại (thêm vào `/api/results` payload, đọc file như các artifact khác).
- Không tự động hóa phần người chấm — chỉ export/import + tính số.

## Task 6 — Bottleneck cả 4 arm trong orchestrator

- Bước [5] chạy tuần tự `--arm z` → `x` → `w` → `y` vào cùng `--output` (script đã enforce cùng question set qua fingerprint — giữ).
- Sau 4 arm, ghi thêm `bottleneck_summary.json`: paired delta mỗi arm so với Z + bootstrap 95% CI (nếu script chưa có phần tổng hợp delta, thêm vào `eval_bottleneck.py` một mode `--summarize` đọc results và tính).
- Safety failures đếm riêng trong summary.

## Acceptance criteria

1. `python -m evaluation.run_all --smoke --yes` chạy xanh từ đầu tới cuối trên máy dev (bỏ bước 5).
2. `grep -r "eval_intent_router\|probe_semantic\|preliminary_d2" --include="*.py" --include="*.ts"` không còn kết quả (ngoài docs/changelog).
3. Dashboard build sạch (`npm run build`), tests dashboard pass sau khi trim.
4. `evaluation/reports/<out>/summary.json` có đủ 7 bước với status.
5. Arm X từ chối chạy với dataset thiếu intent_label, message hướng dẫn dùng Review page.
6. Không có metric nào được tính trong Node/dashboard — Node chỉ đọc artifact (giữ nguyên triết lý).
7. pytest `evaluation/tests` pass; thêm test tối thiểu cho: parse metric 3 tầng intake (1 test), summary fail-soft của run_all (1 test), bottleneck summarize delta (1 test).

## Không được làm

- Không thêm dependency mới (Python lẫn npm).
- Không đổi schema artifact hiện có (report.json, results.jsonl) — chỉ thêm file mới.
- Không đụng production chat runtime (`src/acne_llm/`) ngoài việc import như hiện tại.
- Không viết config/abstraction "cho tương lai".
