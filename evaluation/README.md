# AcneLLM Evaluation Harness

Bộ evaluation thống nhất cho 5 cấu hình, **tách biệt hoàn toàn với legacy eval**
(`scripts/eval_*.py`, `src/acne_llm/eval/`). Thiết kế chi tiết: `docs/EVAL_BLUEPRINT.md`.

| Tên hiển thị | ID nội bộ | Model | RAG |
|--------------|-----------|-------|-----|
| Model gốc | `s0` | `acne-generator-base` (base + cùng SYSTEM prompt) | ✗ |
| Model tinh chỉnh | `s1` | `acne-generator` | ✗ |
| Model gốc + RAG | `s2` | `acne-generator-base` | ✓ |
| Model tinh chỉnh + RAG | `s3` | `acne-generator` | ✓ |
| RAG trích xuất (không LLM) | `s4` | — | ✓ |

## Setup một lần

```bash
# 1. Build base model với CÙNG system prompt (kiểm soát confound R1)
python evaluation/scripts/make_base_modelfile.py
ollama pull qwen2.5:7b
ollama create acne-generator-base -f evaluation/modelfiles/acne-generator-base/Modelfile

# 2. Sinh seed datasets từ dữ liệu có sẵn
python -m evaluation.datasets.build_seeds
# retrieval_test: 100 queries — TẤT CẢ needs_relabel (nhãn cũ bm25-biased, R2)
# Các bộ test được human-review theo schema §5.2 blueprint rồi freeze:
python -m evaluation.datasets.registry freeze evaluation/datasets/v1
```

## Sinh silver drafts bằng OpenAI

Generator chỉ ghi vào `evaluation/datasets/drafts/v1/`, luôn gắn
`annotation_status=draft` và **không tự freeze**. Mặc định nó tạo
80/60/80/40/40/40 original cho chất lượng câu trả lời/ca khó/an toàn/nhiều lượt/
ngoài phạm vi/đối kháng. Bộ ca khó có 60 hard cases và
không tạo typo. Typo variants là 60/0/16/8/8/8 tương ứng
(bộ chất lượng câu trả lời = 60 theo blueprint).
Mỗi query được kiểm tra exact match và overlap 8-gram, cả bản giữ
dấu lẫn bỏ dấu, với train `cleanv3`; mẫu trùng bị loại và ghi vào audit JSONL.

Provider mặc định là OpenAI, đọc `OPENAI_API_KEY` từ `.env`, dùng
`gpt-5.4-mini`, `reasoning_effort=none`, Structured Outputs strict và hard
budget guard `$2.50`.
Khi `--resume`, generator revalidate các schema reject cũ trước khi gọi API và
chỉ tính cost ceiling trên số original còn thiếu.

```bash
# Xem plan + prompt, không gọi API và không tạo data:
python -m evaluation.datasets.generate_drafts --dry-run

# Sinh count mặc định bằng OpenAI:
python -m evaluation.datasets.generate_drafts --yes

# Bộ v1 mở rộng khuyên dùng, vẫn giữ answer-quality synthetic ở 80:
python -m evaluation.datasets.generate_drafts \
  --counts d2=80,d3=60,d4=120,d5=60,d6=80,d7=100 \
  --typo-counts d2=60,d3=0,d4=20,d5=12,d6=16,d7=20 \
  --model gpt-5.4-mini --reasoning-effort none \
  --max-cost-usd 2.50 --yes

# Sau khi train data thay đổi, rebuild index và audit lại draft hiện có:
python -m evaluation.datasets.generate_drafts \
  --audit-only --rebuild-ngram-index
```

Artifacts chính:

- `*.draft.jsonl`: mẫu sạch để human review.
- `*.rejected.audit.jsonl`: schema lỗi, duplicate nội bộ hoặc train
  contamination kèm n-gram và dòng nguồn.
- `generation_summary.json`: provider, model, token/cost usage, SHA-256 train,
  count và trạng thái `freeze_performed=false`.
- `contamination_audit.jsonl`: chỉ được tạo bởi `--audit-only` khi tìm thấy lỗi.

Sau review, chỉ copy các row được duyệt sang version dataset đích, đổi
`annotation_status=approved`, chạy `registry validate`, rồi mới freeze. Bộ chất
lượng câu trả lời và bộ an toàn không dùng để tune prompt, threshold hoặc retrieval.

## Chạy toàn bộ đánh giá

```bash
# Smoke (10 mẫu/bước — kiểm tra ống nước trước khi chạy thật):
python -m evaluation.full_evaluation --smoke --dataset evaluation/datasets/v1/dev_tuning.jsonl

# Full: Intake → RAG → sinh câu trả lời → chấm điểm → báo cáo → quality gate
python -m evaluation.full_evaluation

# Bỏ bước / chạy lại từng phần (mọi bước đều resume-safe):
python -m evaluation.full_evaluation --skip intake,rag
python -m evaluation.full_evaluation --skip scoring        # chỉ chạy máy local, chưa tốn API
```

Preflight tự kiểm tra: Ollama chạy + đủ 2 model, KB artifacts, datasets, API key —
thiếu gì in hướng dẫn sửa. 3 việc KHÔNG auto được: **SSE end-to-end** (restart backend giữa
các condition), **human annotation** (blind export → chấm → import), **relabel qrels
bộ retrieval** (pooled candidates).

## Workflow chuẩn

```bash
# Smoke test (10 câu, 1 hệ)
python -m evaluation.runners.run_experiment \
  --experiment evaluation/configs/experiments/main_2x2.yaml --systems s1 --limit 10

# Sinh câu trả lời prose batch (cùng preparation/prompt production) — resume được
python -m evaluation.runners.run_experiment \
  --experiment evaluation/configs/experiments/main_2x2.yaml --resume

# End-to-end qua SSE API (backend chạy trước; runner dừng chờ đổi model giữa conditions)
python -m evaluation.runners.run_experiment \
  --experiment evaluation/configs/experiments/e2e_sse.yaml --resume

# Judge: provider/model pointwise đọc từ Settings (`.env`), artifact ghi model thật
python -m evaluation.judges.run_judge \
  --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/answer_quality_test.jsonl \
  --faithfulness-model gpt-5-nano-2025-08-07 \
  --pairs s0:s1,s0:s2,s1:s3,s2:s3

# Human annotation (blind)
python -m evaluation.annotations.export_blind --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/answer_quality_test.jsonl
# → chấm annotation/blind_tasks.csv (KHÔNG mở SECRET_mapping.json) →
python -m evaluation.annotations.import_labels --run-dir evaluation/reports/main_2x2_t3

# Report (bảng chính + Wilcoxon/McNemar/bootstrap + Holm + Pareto lỗi)
python -m evaluation.analysis.report --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/answer_quality_test.jsonl

# Unit tests của harness
pytest evaluation/tests -q

# Bias tests judge (BẮT BUỘC pass trước khi tin điểm judge — chạy trên bộ dev)
python -m evaluation.judges.bias_tests --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/dev_tuning.jsonl

# Gate check (exit 1 nếu fail — dùng trong CI)
python -m evaluation.analysis.check_gate

# Contamination check trước khi freeze bộ chất lượng câu trả lời
python -m evaluation.datasets.check_contamination --test evaluation/datasets/v1/answer_quality_test.jsonl

# Validation loop: audit data/runtime/invariants/judge/conflicts
python -m evaluation.validate.loop \
  --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/dev_tuning.jsonl \
  --repro-subset 0
```

## Unified intake và thí nghiệm nút thắt

```bash
# Held-out single-turn; không cache, không fallback, có train-overlap guard
python scripts/eval_unified_intake.py --limit 5

# A/B extraction và router vẫn giữ arm legacy + unified
python scripts/eval_extraction.py --mode unified --limit 5
python scripts/eval_semantic_router.py --include-unified

# Bốn arm phải dùng cùng question set/output để có paired delta
python scripts/eval_bottleneck.py --arm z --limit 5
python scripts/eval_bottleneck.py --arm x --limit 5
python scripts/eval_bottleneck.py --arm y --limit 5
python scripts/eval_bottleneck.py --arm w --limit 5
```

- `z` — **Thực tế (baseline)**: intake thật + RAG thật + generator local.
- `x` — **Intake hoàn hảo**: intake oracle đúng wrapper runtime + RAG thật + generator local.
- `w` — **RAG hoàn hảo**: intake thật + RAG oracle từ qrels + generator local.
- `y` — **Generator mạnh (API)**: intake/RAG thật + API `gpt-5.6-terra`.
- Artifact `reports/bottleneck/results.json` lưu median delta vs baseline, phân phối
  delta từng câu, tăng/giảm/không đổi và số safety failures riêng từng arm.

SSE nhiều lượt dùng `configs/experiments/multiturn_e2e.yaml` với dataset
`multi_turn_test.jsonl`. Dashboard trong `evaluation/dashboard/` đăng ký cả
`intake_eval` và `bottleneck_analysis`; trang Results đọc trực tiếp artifact bốn cấu hình.

Gate safety có `refusal_fidelity: 1.0`: một quyết định reject/non-reject sai,
runtime fail hoặc thiếu `trace.primary_intent` đều làm gate fail.

## Validation loop — mức độ đáng tin của một run

`evaluation.validate.loop` không tạo thêm điểm đẹp; nó kiểm tra run có đủ điều kiện
để diễn giải hay không. Output nằm tại
`evaluation/reports/validation/<timestamp>/summary.json` cùng 5 audit Markdown,
`conflicts.jsonl` và `reproducibility.json`.

- `--repro-subset 0`: audit offline, không rerun local model.
- `--repro-subset 20`: chạy lại 20 case cùng seed và so deterministic metrics.
- `--repro-judge`: tùy chọn có chi phí API, dùng để đo variance judge trên rerun.
- `--strict`: WARN/SKIPPED cũng làm command exit non-zero.

Command luôn exit non-zero khi có invariant critical bị FAIL. Bước sinh câu trả lời
dùng non-stream batch call; verdict production đầy đủ vẫn cần SSE end-to-end.

## Bất biến (invariants) — vi phạm là kết quả không hợp lệ

1. **Không fallback**: adapter ép `fallback_model=None`, record có `model_name` khác config → lỗi `FALLBACK DETECTED`.
2. **Không đụng data production**: audit/session DB của eval nằm trong thư mục tạm; response cache tắt.
3. **Dataset frozen**: sửa file sau khi freeze → `load_dataset` raise (sha256 MANIFEST).
4. **Answer-quality/safety/retrieval không dùng để tune** — mọi tuning trên bộ dev.
5. **Judge blind**: không đưa tên model vào prompt judge; pairwise luôn chạy 2 chiều swap.
6. **Mỗi run có `run_meta.json`**: git commit, sha256 BM25, chroma fingerprint, config.

## Cấu trúc

```
evaluation/
├── configs/systems/s0..s4.yaml, experiments/, gate.yaml
├── datasets/registry.py (validate+freeze), build_seeds.py, v1/*.jsonl
├── adapters/ base.py, _repo.py (bridge repo), ollama_batch.py (batch prose),
│             sse_api.py (end-to-end), extractive.py (RAG trích xuất)
├── runners/run_experiment.py       # resume, retry, trace, run_meta
├── metrics/ retrieval.py (graded nDCG, MAP, noise), deterministic.py (grounding, safety, text)
├── judges/ clients.py (OpenAI default, cache, cost), run_judge.py, prompts/*.md (vi)
├── annotations/ export_blind.py, import_labels.py (blind human eval, calibration)
├── analysis/ stats.py (bootstrap/Wilcoxon/McNemar/Holm/Cliff), error_attribution.py, report.py
├── scripts/make_base_modelfile.py  # sinh Modelfile base + SYSTEM đồng bộ
└── tests/                          # 22 unit tests (stats, metrics, registry)
```

## Contract prose và LEGACY

- Production chỉ có `GET /api/v1/chat/stream`; bốn cấu hình có LLM dùng cùng
  `prepare_chat_turn`, route template và retrieval production, sau đó gọi prose
  non-stream để chạy batch. Cấu hình RAG trích xuất vẫn là extractive prose.
- Record prose mới không có metric parse/empty-core/marker structured. Bộ
  deterministic chính là sentence grounding, context sensitivity, safety text,
  forbidden claims, language và latency.
- `AdviseOutput` còn được giữ cho refusal/clarify/session dựng tay, không phải
  output contract của model. Artifact JSON cũ chỉ được đọc dưới nhãn LEGACY;
  xem `evaluation/reports/LEGACY.md`.
- `run_eval_overnight.bat` gọi `scripts/eval_all.py` (không tồn tại); `eval_rag.py` e2e cần
  `judge.j2` (không có trong `config/prompts/`). Bộ mới không phụ thuộc các đường này.
- Không so trực tiếp metric structured của artifact legacy với report prose mới.

| Nhóm metric prose | Áp dụng | Ghi chú mẫu số |
|---|---|---|
| `grounded_sentence_rate` | Các cấu hình có RAG context | Tổng câu grounded / tổng câu đủ điều kiện |
| context sensitivity + canary fact-query | Bộ dev | Canary phải là fact được hỏi trực tiếp, không phải instruction trong context |
| pregnancy safety + forbidden claims | mọi prose | Pattern check trực tiếp trên answer text |
| Vietnamese ratio + answer length | mọi prose | QA ngôn ngữ và phát hiện output bất thường |
| judge correctness/faithfulness | khi có judged artifact hợp lệ | Không chạy paid judge trong smoke |
