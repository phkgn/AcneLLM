# Codex Prompt — Hoàn thành nốt simplify evaluation (follow-up)

## Trạng thái hiện tại (đã verify)

Monitor UI (`codex_runall_monitor_ui_prompt.md`) đã XONG: run_all.py có 7 bước + summary.json
atomic + marker `[runall]`; dashboard có RunAllMonitor, chip bottleneck, mini-status; 26 tests pass.
KHÔNG đụng lại các phần này trừ chỗ nêu dưới.

`codex_eval_simplify_prompt.md` mới xong phần khung. Còn thiếu 5 việc sau — làm đúng thứ tự.

## Việc 1 — Sửa nội dung thật của bước `intake_eval` (ưu tiên cao nhất)

Hiện bước `intake_eval` trong `evaluation/run_all.py` chạy 4 eval T1 cũ
(`evaluation.unit.eval_normalizer/eval_intent_router/eval_query_planner/eval_guardrails`) — SAI.

1. Nâng `scripts/eval_unified_intake.py` lên 3 tầng metric, output
   `<run_dir>/intake_eval/report.json`:
   - Tầng format: `schema_valid_rate`, `parse_fail_rate`, `schema_violation_rate`.
   - Tầng intent: accuracy, macro-F1 (advise/knowledge/clarify/reject), `reject_recall`, confusion matrix.
   - Tầng extraction: per-field precision/recall/F1 (exact cho enum/số, fuzzy qua
     `acne_llm.utils.fuzzy_match` cho thuốc/sản phẩm), micro+macro, `hallucinated_field_rate`.
   - Latency p50/p95.
   - Giữ nguyên overlap guard với train, dataset mặc định `intake.val.jsonl`, hỗ trợ `--limit`.
2. `run_all.py` bước `intake_eval`: thay 4 lệnh T1 bằng đúng 1 lệnh
   `python scripts/eval_unified_intake.py --output <run_dir>/intake_eval/report.json [--limit N]`.
   Flag `--skip intake` thay cho `--skip t1` (giữ alias `t1` để không vỡ script cũ).

## Việc 2 — Xóa code chết

Xóa hẳn (code + test + wiring):

- `evaluation/unit/` toàn bộ.
- `evaluation/probe/`, `evaluation/dashboard/app/probe/`, `app/api/probe/`, `ProbeClient.tsx`,
  nav item Probe trong `AppShell.tsx`.
- `evaluation/dashboard/scripts/run_preliminary_d2.py` và command `preliminary_d2`
  (Quick preliminary trên Overview thay bằng nút chạy `run_all` với `smoke: true`).
- Trim `command-ids.ts`, `types.ts`, `commands.ts`, RunsClient catalog, DashboardClient,
  tests tương ứng: bỏ `t1_normalizer`, `t1_intent`, `t1_planner`, `t1_guardrails`,
  `probe_semantic`, `preliminary_d2`.
- Dataset seed `t1_intent_seed.jsonl`, `t1_guardrails_seed.jsonl`: giữ file (data không hại),
  chỉ xóa code dùng chúng. Check `/api/status`: bỏ 2 check dataset T1.

Verify: `grep -rn "evaluation.unit\|probe_semantic\|preliminary_d2" --include="*.py" --include="*.ts" --include="*.tsx"`
chỉ còn match trong docs/ và codex_*.md.

## Việc 3 — Wire bước `bottleneck` thật (thay stub)

Trong `run_all.py`, thay `_skip_step(... "not wired yet")` bằng:

1. Chạy tuần tự `scripts/eval_bottleneck.py --arm z → x → w → y`, cùng
   `--dataset` (mặc định d8_qrels) và cùng `--output <run_dir>/bottleneck/results.json`.
2. Trước arm x: nếu dataset thiếu `intent_label` hợp lệ → skip riêng arm x kèm warning
   (script đã validate — bắt exception, không chết cả bước). Arm y nằm sau cost-gate
   confirm chung với judge (`--yes` bỏ qua).
3. Marker per-arm cho UI chip (đã có regex chờ sẵn):
   `[runall] step=6/7 id=bottleneck_z status=start|ok|fail|skipped`.
4. Sau 4 arm: thêm mode `--summarize` vào `eval_bottleneck.py` — đọc results, tính paired
   delta mỗi arm so với Z + bootstrap 95% CI (numpy sẵn có, không thêm dependency),
   safety failures đếm riêng, ghi `<run_dir>/bottleneck/summary.json`.
5. Trạng thái bước: ok nếu z chạy được và không arm nào fail (skipped không tính fail).

## Việc 4 — Wire bước `figures` thật (thay stub)

Thay stub bằng `python -m evaluation.generate_figures --run-dir <run_dir>`.
Fail-soft như các bước khác. Smoke mode: skip (giữ nguyên hành vi hiện tại).

## Việc 5 — d8 review + judge calibration

1. **d8 vào Review**: thêm key `d8` vào `dataset-review-catalog.ts`
   (sourceArea drafts, `d8_qrels_seed.draft.jsonl`, target `d8_qrels_seed.jsonl`) + script nhỏ
   `evaluation/scripts/make_d8_qrels_seed_draft.py` copy d8_qrels hiện tại và thêm
   `intent_label: null`. Validation rule trong `dataset-review.ts`: `intent_label` bắt buộc
   ∈ {advise,knowledge,clarify,reject}, `relevant_chunk_ids` không rỗng, `relevance_grade` là map.
   Lưu ý: d8 không có `expected_answer_points`/`expected_behavior` — nới validator chung cho
   riêng d8 (các rule generic đó chỉ áp cho d1–d7).
2. **Calibration**: `evaluation/judges/calibrate.py` với 2 mode:
   - `--export`: lấy ngẫu nhiên (seed cố định) 50 mẫu đã judge từ `--run-dir`, ghi
     `calibration_sheet.jsonl` (sample_id, query, answer, rubric — KHÔNG kèm điểm judge).
   - `--import <file đã chấm>`: tính Cohen's κ + Spearman human vs judge, ghi
     `evaluation/reports/judge_calibration.json`.
   - `/api/results` đọc thêm file này (readJsonFile như các artifact khác), Results page
     hiển thị κ nếu có.

## Acceptance criteria

1. `python -m evaluation.run_all --smoke --yes` xanh; summary.json có intake_eval chạy
   unified intake thật (không còn t1.*), bottleneck/figures skipped-vì-smoke.
2. Grep ở Việc 2 sạch.
3. `npm run build` + `npm test` pass; pytest evaluation/tests pass.
4. Chip Z/X/W/Y trên monitor đổi trạng thái theo marker per-arm khi chạy bottleneck thật.
5. Thêm test: 3 tầng metric intake (1), bottleneck `--summarize` delta (1), validator d8 (1).
6. Không dependency mới, không endpoint mới, Node không tính metric.

## Không được làm

- Không sửa RunAllMonitor/log-lines/run-all.ts ngoài việc thêm alias skip nếu cần.
- Không đổi schema summary.json (UI đang parse).
- Không tự sinh intent_label bằng LLM — chỉ tạo draft rỗng cho người label qua Review.
