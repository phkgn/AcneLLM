# AcneLLM Evaluation Harness

Bộ evaluation thống nhất cho 5 conditions S0–S4, **tách biệt hoàn toàn với legacy eval**
(`scripts/eval_*.py`, `src/acne_llm/eval/`). Thiết kế chi tiết: `docs/EVAL_BLUEPRINT.md`.

| ID | Condition | Model | RAG |
|----|-----------|-------|-----|
| S0 | Base only | `qwen25-base-acnesys` (base + cùng SYSTEM prompt) | ✗ |
| S1 | Finetuned only | `acnellm-v2-q4` | ✗ |
| S2 | Base + RAG | `qwen25-base-acnesys` | ✓ |
| S3 | Finetuned + RAG (production) | `acnellm-v2-q4` | ✓ |
| S4 | Extractive (top chunks, không LLM) | — | ✓ |

## Setup một lần

```bash
# 1. Build base model với CÙNG system prompt (kiểm soát confound R1)
python evaluation/scripts/make_base_modelfile.py
ollama pull qwen2.5:7b
ollama create qwen25-base-acnesys -f evaluation/modelfiles/qwen25-base-acnesys/Modelfile

# 2. Sinh seed datasets từ dữ liệu có sẵn
python -m evaluation.datasets.build_seeds
# d8_qrels_seed: 100 queries — TẤT CẢ needs_relabel (nhãn cũ bm25-biased, R2)
# D2/D3/D4/D5/D6/D7 viết theo schema §5.2 blueprint rồi freeze:
python -m evaluation.datasets.registry freeze evaluation/datasets/v1
```

## Sinh silver drafts D2/D3/D4/D5/D6/D7 bằng OpenAI

Generator chỉ ghi vào `evaluation/datasets/drafts/v1/`, luôn gắn
`annotation_status=draft` và **không tự freeze**. Mặc định nó tạo
80/60/80/40/40/40 original cho D2/D3/D4/D5/D6/D7. D3 là 60 hard cases và
không tạo typo. Typo variants là 60/0/16/8/8/8 tương ứng
(D2=60 theo blueprint).
Mỗi query được kiểm tra exact match và overlap 8-gram, cả bản giữ
dấu lẫn bỏ dấu, với train `cleanv3`; mẫu trùng bị loại và ghi vào audit JSONL.

Provider mặc định là OpenAI, đọc `OPENAI_API_KEY` từ `.env`, dùng
`gpt-5.4-mini`, `reasoning_effort=none`, Structured Outputs strict và hard
budget guard `$2.50`. DeepSeek vẫn có thể dùng lại bằng `--provider deepseek`.
Khi `--resume`, generator revalidate các schema reject cũ trước khi gọi API và
chỉ tính cost ceiling trên số original còn thiếu.

```bash
# Xem plan + prompt, không gọi API và không tạo data:
python -m evaluation.datasets.generate_drafts --dry-run

# Sinh count mặc định bằng OpenAI:
python -m evaluation.datasets.generate_drafts --yes

# Bộ v1 mở rộng khuyên dùng, vẫn giữ D2 synthetic ở 80:
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
- `d*.rejected.audit.jsonl`: schema lỗi, duplicate nội bộ hoặc train
  contamination kèm n-gram và dòng nguồn.
- `generation_summary.json`: provider, model, token/cost usage, SHA-256 train,
  count và trạng thái `freeze_performed=false`.
- `contamination_audit.jsonl`: chỉ được tạo bởi `--audit-only` khi tìm thấy lỗi.

Sau review, chỉ copy các row được duyệt sang version dataset đích, đổi
`annotation_status=approved`, chạy `registry validate`, rồi mới freeze. D2/D4
không dùng để tune prompt, threshold hoặc retrieval.

## Tầng 1 — Unit eval per module (trước RAG & LLM)

```bash
# Normalizer (extraction) — delegate sang harness legacy đã kiểm chứng
# (gold 1.000 mẫu + taxonomy projection), output copy về reports/unit/normalizer/
python -m evaluation.unit.eval_normalizer

# Intent router (rule-based) — accuracy, macro-F1, reject-recall, confusion
python -m evaluation.unit.eval_intent_router \
  --dataset evaluation/datasets/v1/t1_intent_seed.jsonl

# Query planner + build_retrieval_query — property-based (P1–P6), không cần gold
python -m evaluation.unit.eval_query_planner \
  --dataset evaluation/datasets/v1/t1_intent_seed.jsonl

# Guardrails: injection detection + scope check (+ OOD nếu --with-ood, cần embedder)
python -m evaluation.unit.eval_guardrails \
  --dataset evaluation/datasets/v1/t1_guardrails_seed.jsonl
```

Seed T1 có sẵn: `t1_intent_seed.jsonl` (24 câu, draft — mở rộng lên 200–300 theo
blueprint §4), `t1_guardrails_seed.jsonl` (20 câu in/out-of-scope + injection).
Ngưỡng pass/fail: `configs/gate.yaml` mục `unit`. Chất lượng end-to-end của query
construction đo ở T2 ablation A4 (constructed vs raw); completeness/clarify đo qua
nhóm clarify trong T4.

## Run ALL-IN-ONE

```bash
# Smoke (10 mẫu/bước — kiểm tra ống nước trước khi chạy thật):
python -m evaluation.run_all --smoke --dataset evaluation/datasets/v1/d1_dev_seed.jsonl

# Full: T1 unit → T2 retrieval+ablation → T3 generation S0–S4 → judge → report → gate
python -m evaluation.run_all

# Bỏ bước / chạy lại từng phần (mọi bước đều resume-safe):
python -m evaluation.run_all --skip t1,t2          # chỉ generation+judge+report
python -m evaluation.run_all --skip judge,report   # chỉ chạy máy local, chưa tốn API
```

Preflight tự kiểm tra: Ollama chạy + đủ 2 model, KB artifacts, datasets, API key —
thiếu gì in hướng dẫn sửa. 3 việc KHÔNG auto được: **T4 e2e** (restart backend giữa
các condition), **human annotation** (blind export → chấm → import), **relabel qrels
D8** (pooled candidates).

## Workflow chuẩn

```bash
# Smoke test (10 câu, 1 hệ)
python -m evaluation.runners.run_experiment \
  --experiment evaluation/configs/experiments/main_2x2.yaml --systems s1 --limit 10

# Main run T3 (batch/JSON) — resume được, chạy overnight
python -m evaluation.runners.run_experiment \
  --experiment evaluation/configs/experiments/main_2x2.yaml --resume

# T4 e2e qua SSE API (backend chạy trước; runner dừng chờ đổi model giữa conditions)
python -m evaluation.runners.run_experiment \
  --experiment evaluation/configs/experiments/e2e_sse.yaml --resume

# Judge (DeepSeek chính; --provider openai để verify chéo)
python -m evaluation.judges.run_judge \
  --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/d2_test.jsonl \
  --pairs s0:s1,s0:s2,s1:s3,s2:s3

# Human annotation (blind)
python -m evaluation.annotations.export_blind --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/d2_test.jsonl
# → chấm annotation/blind_tasks.csv (KHÔNG mở SECRET_mapping.json) →
python -m evaluation.annotations.import_labels --run-dir evaluation/reports/main_2x2_t3

# Report (bảng chính + Wilcoxon/McNemar/bootstrap + Holm + Pareto lỗi)
python -m evaluation.analysis.report --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/d2_test.jsonl

# Unit tests của harness
pytest evaluation/tests -q

# Bias tests judge (BẮT BUỘC pass trước khi tin điểm judge — chạy trên D1)
python -m evaluation.judges.bias_tests --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/d1_dev_seed.jsonl

# Gate check (exit 1 nếu fail — dùng trong CI)
python -m evaluation.analysis.check_gate

# Contamination check trước khi freeze D2
python -m evaluation.datasets.check_contamination --test evaluation/datasets/v1/d2_test.jsonl

# Validation loop: audit data/runtime/invariants/judge/conflicts
python -m evaluation.validate.loop \
  --run-dir evaluation/reports/main_2x2_t3 \
  --dataset evaluation/datasets/v1/d1_dev_seed.jsonl \
  --repro-subset 0
```

## Validation loop — mức độ đáng tin của một run

`evaluation.validate.loop` không tạo thêm điểm đẹp; nó kiểm tra run có đủ điều kiện
để diễn giải hay không. Output nằm tại
`evaluation/reports/validation/<timestamp>/summary.json` cùng 5 audit Markdown,
`conflicts.jsonl` và `reproducibility.json`.

- `--repro-subset 0`: audit offline, không rerun local model.
- `--repro-subset 20`: chạy lại 20 case cùng seed và so deterministic metrics.
- `--repro-judge`: tùy chọn có chi phí API, dùng để đo variance judge trên rerun.
- `--strict`: WARN/SKIPPED cũng làm command exit non-zero.

Command luôn exit non-zero khi có invariant critical bị FAIL. T3 chỉ là batch
diagnostic; verdict production cần T4 SSE.

## Bất biến (invariants) — vi phạm là kết quả không hợp lệ

1. **Không fallback**: adapter ép `fallback_model=None`, record có `model_name` khác config → lỗi `FALLBACK DETECTED`.
2. **Không đụng data production**: audit/session DB của eval nằm trong thư mục tạm; response cache tắt.
3. **Dataset frozen**: sửa file sau khi freeze → `load_dataset` raise (sha256 MANIFEST).
4. **D2/D4/D8 không dùng để tune** prompt/top-k/threshold/rubric — mọi tuning trên D1 dev.
5. **Judge blind**: không đưa tên model vào prompt judge; pairwise luôn chạy 2 chiều swap.
6. **Mỗi run có `run_meta.json`**: git commit, sha256 BM25, chroma fingerprint, config.

## Cấu trúc

```
evaluation/
├── configs/systems/s0..s4.yaml, experiments/, gate.yaml
├── datasets/registry.py (validate+freeze), build_seeds.py, v1/*.jsonl
├── adapters/ base.py, _repo.py (bridge repo), ollama_batch.py (T3),
│             sse_api.py (T4), extractive.py (S4)
├── runners/run_experiment.py       # resume, retry, trace, run_meta
├── metrics/ retrieval.py (graded nDCG, MAP, noise), deterministic.py (safety, citation)
├── judges/ clients.py (DeepSeek/OpenAI, cache, cost), run_judge.py, prompts/*.md (vi)
├── annotations/ export_blind.py, import_labels.py (blind human eval, calibration)
├── analysis/ stats.py (bootstrap/Wilcoxon/McNemar/Holm/Cliff), error_attribution.py, report.py
├── scripts/make_base_modelfile.py  # sinh Modelfile base + SYSTEM đồng bộ
└── tests/                          # 22 unit tests (stats, metrics, registry)
```

## Ghi chú so với legacy

- `scripts/run_eval.py` tham chiếu `container.hybrid`/`container.llm_only` không tồn tại
  trong `di.py::Container` — harness này dựng pipeline trực tiếp từ components.
- `run_eval_overnight.bat` gọi `scripts/eval_all.py` (không tồn tại); `eval_rag.py` e2e cần
  `judge.j2` (không có trong `config/prompts/`). Bộ mới không phụ thuộc các đường này.
- Legacy giữ nguyên, không sửa; migrate dần khi bộ mới ổn định.
