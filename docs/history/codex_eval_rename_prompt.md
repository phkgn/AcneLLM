# Codex Prompt — Đặt lại tên toàn bộ evaluation cho dễ hiểu

## Mục tiêu

Bỏ hết mã hiệu bí ẩn (D1–D8, T1/T2/T3, S0–S4, "run all"). Tên phải nói thẳng
**dữ liệu đó dùng để đo cái gì** và **bước đó làm gì**. Người mới mở dashboard
phải hiểu ngay không cần đọc tài liệu.

Đây là refactor thuần đổi tên + nhãn UI. KHÔNG đổi logic, KHÔNG đổi metric,
KHÔNG đổi schema artifact.

## Bảng đổi tên dataset

Đổi tên file trong `evaluation/datasets/v1/` và `drafts/v1/` (draft giữ hậu tố `.draft`):

| Cũ | Mới | Đo cái gì |
|---|---|---|
| `d1_dev_seed.jsonl` | `d1_dev_seed.jsonl` | Bộ dev để chỉnh prompt/ngưỡng — không báo cáo metric |
| `d2_test.jsonl` | `d2_test.jsonl` | Bộ test chính: chất lượng câu trả lời tư vấn |
| `d3_challenge.jsonl` | `d3_challenge.jsonl` | Ca khó, phân tích giới hạn |
| `d4_safety.jsonl` | `d4_safety.jsonl` | Tình huống nguy cơ cao, hành vi triage |
| `d5_multiturn.jsonl` | `d5_multiturn.jsonl` | Dùng đúng lịch sử hội thoại |
| `d6_ood.jsonl` | `d6_ood.jsonl` | Ngoài phạm vi → phải từ chối |
| `d7_adversarial.jsonl` | `d7_adversarial.jsonl` | Prompt injection, khai thác |
| `d8_qrels_seed.jsonl` | `d8_qrels_seed.jsonl` | Tìm kiếm tài liệu + nút thắt (có qrels + intent_label) |
| `d8_qrels_seed.draft.jsonl` | `d8_qrels_seed.draft.jsonl` | Draft đang label intent |
| `d2_test.contamination.json` | `d2_test.contamination.json` | — |
| `t1_intent_seed.jsonl`, `t1_guardrails_seed.jsonl` | **XÓA** | Code dùng chúng đã bị gỡ |
| `datagen/.../intake.val.jsonl` | giữ nguyên đường dẫn | Chỉ đổi nhãn hiển thị thành "Intake test (held-out)" |

Các file `*.rejected.audit.jsonl` / `*.recovery.audit.jsonl` đổi prefix theo tên mới tương ứng.

Dùng `git mv` để giữ history. Cập nhật MỌI tham chiếu: `configs/experiments/*.yaml`,
`configs/systems/*.yaml`, `run_all.py`, `scripts/eval_bottleneck.py`,
`dataset-review-catalog.ts`, `status/route.ts`, `commands.ts` (default dataset),
`datasets/MANIFEST.json`, docs trong `docs/`. Artifact cũ trong `reports/` KHÔNG sửa
(là lịch sử) — chấp nhận chúng trỏ tên cũ.

## Bảng đổi tên key review (dashboard)

`DATASET_KEYS` và `DATASET_CONFIG` trong `dataset-review-catalog.ts`:
`d1..d8` → `d1_dev_seed`, `answer_quality`, `hard_cases`, `safety`, `multi_turn`,
`out_of_scope`, `adversarial`, `retrieval`.

Label hiển thị bỏ tiền tố "D1 ·": ví dụ `"Chất lượng câu trả lời"`, `"An toàn"`,
`"Ngoài phạm vi"`, `"Tìm kiếm tài liệu"`.

**Migration bắt buộc**: `.dataset-reviews.json` đang lưu `datasetKey: "d2"`.
Thêm map cũ→mới khi đọc store (`readStore`), ghi lại bằng key mới ở lần save kế tiếp.
Không được làm mất quyết định review đã có.

## Bảng đổi tên command + nhãn UI

`CommandId` trong `types.ts` / `command-ids.ts` / `commands.ts`:

| Cũ | Mới | Nhãn UI (tiếng Việt) |
|---|---|---|
| `run_all` | `full_evaluation` | **Chạy toàn bộ đánh giá** |
| `intake_unified` | `intake_eval` | Đánh giá bộ tiếp nhận (Intake) |
| `t2_retrieval` | `retrieval_eval` | Đánh giá tìm kiếm tài liệu (RAG) |
| `t3_generation` | `answer_generation` | Sinh câu trả lời (4 cấu hình) |
| `judge` | `llm_scoring` | Chấm điểm bằng LLM |
| `report` | `build_report` | Tổng hợp báo cáo |
| `check_gate` | `quality_gate` | Kiểm tra ngưỡng chất lượng |
| `validation_loop` | `trust_audit` | Kiểm định độ tin cậy |
| `bottleneck` | `bottleneck_analysis` | Phân tích nút thắt |
| `figures_*` | giữ id, đổi nhãn | Biểu đồ: Kho tri thức / Kết quả / Sử dụng / Tất cả |
| `tests` | giữ | Chạy test harness |

Bỏ cột "tier" (T1/T2/T3/Judge) trong catalog RunsClient — thay bằng 1 dòng mô tả
người thường đọc được.

## Bước trong run_all + monitor

`STEP_DEFINITIONS` đổi label (giữ id để không vỡ UI parse, TRỪ 2 id dưới):

| id | label mới |
|---|---|
| `preflight` | Kiểm tra môi trường |
| `intake_eval` | Đánh giá Intake |
| `rag_eval` | Đánh giá RAG |
| `t3_generation` → đổi id thành `answer_generation` | Sinh câu trả lời |
| `judge_report` → đổi id thành `scoring_report` | Chấm điểm + báo cáo |
| `bottleneck` | Phân tích nút thắt |
| `figures` | Biểu đồ |

Đổi id thì cập nhật luôn `run-all.ts`, `RunAllMonitor` (chỗ check `t3_generation`),
và marker `[runall] ... id=...`. Test `run-all.test.ts` cập nhật theo.

Flag `--skip` nhận tên mới: `intake,rag,generation,scoring,bottleneck,figures`.

## Nhãn 4 cấu hình hệ thống (S0–S4)

**KHÔNG đổi id** `s0..s4` (tên file artifact `s3.results.jsonl` phụ thuộc vào nó).
Chỉ thêm bảng nhãn hiển thị trong `lib/systems.ts` (file mới, ~10 dòng) đọc từ
`configs/systems/*.yaml` field `name`, và dùng nhãn đó ở Results / Inspect / monitor:
ví dụ "Model gốc", "Model gốc + RAG", "Model tinh chỉnh", "Model tinh chỉnh + RAG".
Nếu YAML chưa có `name` dễ hiểu thì sửa YAML.

## Nhãn arm bottleneck

Z/X/W/Y giữ id trong script, UI hiển thị kèm nghĩa:
- Z → "Thực tế (baseline)"
- X → "Intake hoàn hảo"
- W → "RAG hoàn hảo"
- Y → "Generator mạnh (API)"

## Acceptance criteria

1. `grep -rn "\bd[1-8]_\|t1_\|t2_\|t3_\|run_all\b" --include="*.py" --include="*.ts" --include="*.tsx"`
   không còn match trong code (docs/ và codex_*.md được phép).
2. `npm run build`, `npm test`, `pytest evaluation/tests -q` đều pass.
3. Mở trang Review: 8 tab tên tiếng Việt, quyết định review cũ vẫn còn nguyên (migration OK).
4. Trang Runs: danh sách lệnh không còn chữ T1/T2/T3, mỗi lệnh 1 dòng mô tả dễ hiểu.
5. `python -m evaluation.run_all --smoke --yes` (hoặc tên module giữ `run_all.py`
   nhưng nhãn mới — chọn 1, ghi rõ trong PR) chạy xanh, stepper hiện label tiếng Việt.
6. Không file nào trong `reports/` bị sửa.

## Không được làm

- Không đổi tên field bên trong JSONL (`sample_id`, `task_type`, `relevance_grade`...) —
  chỉ đổi tên file và key UI.
- Không đổi id `s0..s4`, không đổi schema `summary.json` ngoài 2 id bước đã nêu.
- Không thêm dependency, không viết lớp abstraction cho việc đổi tên.
