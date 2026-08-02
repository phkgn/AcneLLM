# Refactor `evaluation/` — về đúng 4 khâu

Không đụng `ablation/`. Chỉ mượn **phương pháp** của nó (oracle substitution),
còn code thì sửa tại chỗ trong `evaluation/`.

**Kết quả:** 33.922 → ~3.900 LOC. Xóa ~26.700 dòng, viết mới ~40 dòng.

---

## Tại sao sửa tại chỗ hợp lý hơn chuyển sang `ablation/`

| | Sửa `evaluation/` | Chuyển `ablation/` |
|---|---:|---:|
| LOC còn lại | ~3.900 | ~1.270 |
| Cần sinh case set mới + review tay | **Không** | Có — việc chặn |
| Intake 3 tầng (schema/intent/extraction) | Giữ | Mất |
| Graded nDCG + 5 mode retrieval | Giữ | Mất |
| Chạy được ngay tuần này | **Có** | Không |

`ablation/` nhỏ hơn 3× nhưng chưa có case set thật (`ablation/data/` chưa tồn tại,
mới chạy 40 case SYNTHETIC), và bỏ mất hai bài đo mà `evaluation/` đã làm tốt.
Sửa tại chỗ đắt hơn 2.600 LOC nhưng chạy được ngay.

---

## Đích: 4 khâu, 4 lệnh

```
python -m evaluation.full_evaluation

[1] preflight    Ollama + model, chroma_db, bm25, dataset, API key
[2] intake       runners.run_intake       → khâu 1
[3] retrieval    runners.run_retrieval    → khâu 2
[4] ablation     runners.run_ablation     → khâu 3 + 4
```

| Khâu | Lệnh | Dataset | Đo gì | LLM chấm |
|---|---|---|---|---|
| 1 | `run_intake` | `intake.val.jsonl` 400 | schema_valid_rate · intent macro-F1 + confusion · per-field P/R/F1 · hallucinated_field_rate · latency | Không |
| 2 | `run_retrieval` | `retrieval_test.jsonl` 100 | recall@k · precision@k · MRR · **graded nDCG** · hit@k × 5 mode | Không |
| 3 | `run_ablation` arm `OOR` | `retrieval_test.jsonl` 100 | điểm tuyệt đối khi input hoàn hảo | Có |
| 4 | `run_ablation` 4 arm | `retrieval_test.jsonl` 100 | Δ vs baseline khi thay từng khâu | Có |

Khâu 3 + 4 chung một lần chạy: `RRR` `ORR` `ROR` `RRO` `OOR` = 500 lượt sinh.

---

## Phase 1 — Thu `full_evaluation.py`: 7 bước → 4 (629 → ~150 LOC)

**Làm trước tiên**, vì phải ngắt mọi tham chiếu tới code sắp xóa.

Bỏ 3 bước: `answer_generation` (thí nghiệm 2×2), `scoring_report`, `figures`.

Bỏ theo:
- dict `results` + `reports/full_evaluation_last.json` — ba nơi lưu cùng một
  trạng thái (`results`, `summary.json`, file kia). Giữ `summary.json`.
- toàn bộ khối cost gate 5 biến bool (dòng 419–476) → 1 câu confirm trước bước [4],
  `--yes` bỏ qua.
- vũ điệu YAML tạm cho `--dataset` (dòng 399–408) — biến mất cùng `run_experiment`.
- 90 dòng điều phối arm (dòng 494–583) → chuyển vào `run_ablation.py` bằng
  `--arms RRR,ORR,ROR,RRO,OOR` (Phase 4).
- `--skip` dùng thẳng step id (`intake,retrieval,ablation`), bỏ bảng dịch
  `generation`↔`answer_generation`.

Giữ: preflight, `summary.json` ghi nguyên tử, marker `[runall] step=n/4`,
fail-soft (bước fail không kéo sập bước sau).

**Verify:** `python -m evaluation.full_evaluation --smoke` → 4/4 bước ra status.

---

## Phase 2 — Gom 2 script vào `evaluation/runners/`

`evaluation/README.md` dòng 3 tuyên bố eval "tách biệt hoàn toàn với
`scripts/eval_*.py`", nhưng `full_evaluation.py` lại `subprocess` gọi thẳng sang
đó. Tuyên bố sai — sửa cho đúng:

```
scripts/eval_unified_intake.py  (782)  →  evaluation/runners/run_intake.py
scripts/eval_bottleneck.py     (1118)  →  evaluation/runners/run_ablation.py
```

`git mv`, **không sửa logic**. Đổi call site trong `full_evaluation.py` sang
`-m evaluation.runners.run_intake` cho đồng nhất với `run_retrieval`.

Import closure đã kiểm, cả hai chỉ cần thứ nằm trong danh sách giữ ở dưới.

---

## Phase 3 — Xóa (~26.700 LOC)

Giờ không còn ai gọi. Xóa theo nhóm:

### Thí nghiệm 2×2 — toàn bộ

| Xóa | LOC |
|---|---:|
| `runners/run_experiment.py` | 229 |
| `configs/systems/s0..s4.yaml` (5 file) | — |
| `configs/experiments/*.yaml` (5 file) | — |
| `configs/gate.yaml` | — |
| `judges/run_judge.py` (pointwise + pairwise 2 chiều) | 563 |
| `adapters/base.py`, `ollama_batch.py`, `sse_api.py`, `extractive.py` | 495 |
| `analysis/report.py`, `stats.py`, `error_attribution.py`, `check_gate.py` | 742 |

### Figures — 4 nhóm hình, không nhóm nào thuộc 4 khâu

`analysis/figures_common.py` 514 · `figures_eval.py` 1.073 · `figures_kb.py` 1.143 ·
`figures_usage.py` 429 · `generate_figures.py` 204 = **3.363**

### Validate — không phải khâu nào

`validate/` (12 file, checks + audits + loop) = **2.600**

Code không over-engineered, nhưng nó kiểm invariant của thí nghiệm 2×2 vừa xóa.

### Dataset generation — không phải khâu nào

`datasets/generate_drafts.py` 2.213 · `build_seeds.py` 69 · `check_contamination.py` 91
= **2.373**. Giữ `registry.py` nhưng **trim 92 → ~40**: chỉ còn `load_dataset`
(kiểm sha256 MANIFEST — invariant "dataset frozen" đáng giữ), bỏ `validate_file`,
`freeze_dir`, CLI.

### Còn lại

- `annotations/export_blind.py` + `import_labels.py` — 207
- `analysis/recompute_grounding.py` 116 + `tune_grounding.py` 254
- `dashboard/` (Next.js, 59 file, 9.920 LOC TS/TSX + `node_modules`)
- `evaluation/unit/` + `probe/` — thư mục rỗng, chỉ còn `__pycache__`
- `src/acne_llm/eval/` 131 — `judge.py` 0 import; `metrics.py` là subset chính xác
  của `evaluation/metrics/retrieval.py`. Đổi 2 import trong `tests/test_retriever.py`
  và `tests/test_eval_retrieval.py`.
- `scripts/` legacy sau khi move 2 file: `eval_rag.py` 1.566 (cần `judge.j2` không
  tồn tại) · `eval_retrieval.py` 78 · `eval_extraction.py` 548 ·
  `eval_extraction_quick.py` 105 · `eval_semantic_router.py` 615 ·
  `eval_from_finetune_test.py` 116 · `run_eval.py` 60 · `gen_eval_queries.py` 572 ·
  `gen_golden_set.py` 406 · `probe_crosslingual.py` 167 · `probe_judge.py` 173 ·
  `judge_agreement.py` 377 = **4.783**
- `run_eval_overnight.bat` — gọi `scripts/eval_all.py`, file không tồn tại
- `tests/test_eval_rag_e2e.py`, `test_eval_retrieval.py`,
  `test_eval_from_finetune_test.py`, `test_run_eval.py`

### Dataset

Giữ **`retrieval_test.jsonl`** (100 dòng, `relevant_chunk_ids` + `relevance_grade`
0/1/2, đã relabel xong, `annotation_status: approved`) — khâu 2 và khâu 3/4 đều
dùng. Giữ `MANIFEST.json`.

Xóa 7 bộ còn lại (728 case): `answer_quality_test` 140 · `safety_test` 140 ·
`adversarial_test` 120 · `dev_tuning` 100 · `out_of_scope_test` 96 ·
`multi_turn_test` 72 · `hard_cases_test` 60, cùng `datasets/drafts/`.

**Lưu ý:** 588 trong số đó (safety, adversarial, out_of_scope, hard_cases,
multi_turn) hiện **không pipeline nào chạy** — không mất gì thật.
`answer_quality_test` 140 thì đang dùng cho 2×2, mất cùng thí nghiệm đó.

**Verify:** `grep -rn "run_experiment\|run_judge\|evaluation.validate\|figures_\|generate_drafts" --include=*.py .`
→ chỉ còn match trong `docs/`, `ablation/README.md`, `codex_*.md`.
Rồi `pytest evaluation/tests tests -q`.

---

## Phase 4 — Thêm arm `OOR` + đổi sang mã arm 3 ký tự (~40 LOC mới)

### 4a. Mã arm

Bốn arm hiện tại là `z/x/w/y` — chữ cái không nói lên gì, và thêm arm thứ 5 thì
hết chữ hợp lý. Chuyển sang mã 3 ký tự, mỗi ký tự một khâu
`[intaker][rag][generator]`, `R`=thật `O`=oracle:

| Cũ | Mới | Nghĩa |
|---|---|---|
| `z` | `RRR` | baseline — chạy thật cả 3 |
| `x` | `ORR` | intake hoàn hảo |
| `w` | `ROR` | RAG hoàn hảo |
| `y` | `RRO` | generator hoàn hảo (API) |
| — | `OOR` | **mới** — input hoàn hảo, generator thật → **khâu 3** |

Sửa `ARM_LABELS` (dòng 62-67) + `choices=("z","x","w","y")` (dòng 962) + `--arms`
nhận danh sách. Không alias cũ→mới; artifact tháng 7 đằng nào cũng stale (§Phase 5).

### 4b. Arm `OOR`

Hai mảnh đã có sẵn, chỉ là chưa ai bật cùng lúc:

- `_OracleIntake` (dòng 70) — đang dùng cho arm `x`
- `_oracle_retrieval` (dòng 302) — đang dùng cho arm `w`

Trong `_run_arm` (dòng 420), điều kiện hiện là `arm == "x"` / `arm == "w"` / `arm == "y"`.
Đổi thành đọc từng ký tự:

```python
iv, rv, gv = arm            # 'O','O','R'
oracle = _OracleIntake() if iv == "O" else None
...
if rv == "O":  retrieval = _oracle_retrieval(...)
if gv == "O":  answer = _api_chat_once(...)
```

Đây là refactor **thu gọn**: 3 nhánh `if arm ==` rải rác thành 3 phép kiểm ký tự.

### 4c. `--arms` + vòng lặp

Chuyển 90 dòng điều phối từ `full_evaluation.py` (Phase 1) vào đây:
`--arms RRR,ORR,ROR,RRO,OOR` chạy tuần tự, in marker per-arm, skip `ORR` nếu
dataset thiếu `intent_label`, chặn arm sau nếu `RRR` fail. Kiến thức đó thuộc về
script này chứ không phải orchestrator.

**Verify:** `python -m evaluation.runners.run_ablation --arms RRR,OOR --limit 5`

---

## Phase 5 — Sửa 3 lỗi đã tìm thấy

**1. `summary.json` stale — số bottleneck đang tính trên 24% dữ liệu.**
File ghi `paired_n = 24/100` cho cả 3 arm, nhưng `results.json` cho thấy cả 100
item đều `ok: true`, `safety_fail: false` — theo đúng luật ghép cặp của chính nó
(`_paired_summary`, dòng 691-712) phải ghép được 100. Chạy lại `--summarize` sau
mỗi lần chạy arm, và để `full_evaluation` gọi nó tự động (đừng để chạy tay).

**2. `drop_reason` bị nuốt.** `summarize_report` (dòng 866-873) copy `paired_n`,
`dropped_ids`, `quality`, `safety` nhưng quên `drop_reason` — đúng field lẽ ra
giải thích được 76 câu biến đi đâu. Thêm 1 dòng.

**3. Generator lấy từ `.env`, không ghi vào config.** Dòng 430 đọc
`settings.llm_model`. Artifact tháng 7 ghi `generator_model: acnellm-role`; `.env`
nay ghi `acne-generator`. Chạy lại hôm nay ra model khác, không cảnh báo. Thêm
`--model` (mặc định `settings.llm_model`) và ghi vào `run_meta` — invariant #6
trong README yêu cầu điều này.

---

## Phase 6 — Dọn tests + docs

- `evaluation/tests/` 20 file → giữ `test_stats`(nếu còn dùng)/`test_metrics`/
  `test_intake_metrics`/`test_registry`/`test_classification`/`test_grounding`/
  `test_scorecard`/`test_bottleneck_experiment`/`test_eval_unified_intake`.
  Xóa `test_figures_*` (4), `test_validation_*` (2), `test_generate_drafts`,
  `test_generate_figures`, `test_judge_openai`, `test_judge_agreement`,
  `test_recompute_grounding`, `test_tune_grounding`.
- `evaluation/README.md` viết lại — hiện mô tả 5 hệ s0–s4, 7 bước, validation loop,
  human annotation. Còn 4 khâu.
- `codex_*_prompt.md` (20 file ở root) → `docs/history/`; xóa `overnight.log`,
  `run2.log`, `run3.log`.
- `evaluation/reports/` 49 MB, 41 thư mục — 37 là run debug tháng 7
  (`prelim_d2_*`, `round2_smoke_*`, `round3_*`, `qa_*`, `judge_calibration_*`).
  **Artifact thí nghiệm — bạn quyết**, tôi không tự xóa.

---

## Cây còn lại (~3.900 LOC)

```
evaluation/
├── full_evaluation.py           ~150   orchestrator 4 khâu
├── common.py                     113
├── adapters/_repo.py              80   bridge vào product container
├── judges/clients.py             225   OpenAI client + cache + cost
├── metrics/
│   ├── classification.py          75   accuracy, macro-F1, confusion
│   ├── intake.py                 126   intent PRF, ECE, negation leak
│   ├── retrieval.py               94   recall/precision/MRR/graded nDCG
│   ├── deterministic.py           96   pregnancy safety, forbidden claims
│   ├── grounding.py              214   sentence grounding
│   └── scorecard.py               96   5 mặt điểm
├── datasets/
│   ├── registry.py               ~40   chỉ load_dataset + sha256 freeze
│   └── v1/retrieval_test.jsonl         100 dòng, qrels graded
├── runners/
│   ├── run_intake.py             782   khâu 1
│   ├── run_retrieval.py          127   khâu 2
│   └── run_ablation.py         ~1.130  khâu 3 + 4
└── tests/                        ~600
```

---

## Thứ tự chạy

```
1 thu full_evaluation  → verify smoke
2 git mv 2 script      → verify smoke
3 xóa                  → verify grep + pytest
4 arm OOR + mã 3 ký tự → verify --arms RRR,OOR --limit 5
5 sửa 3 bug            → verify --summarize ra paired_n=100
6 dọn tests + docs
```

**Verify sau mỗi phase:**

```bash
pytest evaluation/tests tests -q
python -m evaluation.full_evaluation --smoke
```

Phase 1–3 không cần API key và không tốn tiền. Phase 4 cần 1 lần chạy `--limit 5`.

---

## Hai thứ bỏ, nói rõ để bạn biết

**Quality gate biến mất.** `check_gate.py` + `gate.yaml` bị xóa cùng 2×2. Gate
không phải khâu nào trong 4 khâu. *Ghi chú:* gate hiện tại đằng nào cũng sai
nguồn — `check_gate.py:82-92` đọc `refusal_fidelity` và `forbidden_claim_rate` từ
`report["systems"]["s3"]`, mà `report.json` dựng từ `answer_quality_test`, trong
khi `gate.yaml` chú thích ngưỡng là "trên D4 known patterns". Đang chấm safety
trên bộ D1 mà vẫn ra số, nên không ai thấy.

**Judge calibration.** `judges/calibrate.py` 232 (Cohen's κ + Spearman) và
`bias_tests.py` 147 nằm trong danh sách xóa vì không phải khâu nào. Nhưng khâu 3
và 4 đều dựa trên một LLM judge chưa ai kiểm — không có κ thì con số không phòng
thủ được trước hội đồng. **Đây là thứ duy nhất trong danh sách xóa mà tôi sẽ
tranh luận nên giữ** (+379 LOC). Bạn quyết.
