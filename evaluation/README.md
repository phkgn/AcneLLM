# AcneLLM Evaluation — 4 khâu

Hệ thống có 3 khâu nối tiếp: **intaker → RAG → generator**. Eval làm đúng 4 việc
và không làm gì khác.

| Khâu | Đo gì | Cần LLM chấm | Chạy bằng |
|---|---|---|---|
| 1 | Intaker rút đúng 15 slot không | Không | `runners.run_intake` |
| 2 | RAG tìm đúng tài liệu không | Không | `runners.run_retrieval` |
| 3 | Generator viết tốt đến đâu khi input hoàn hảo | Có | `runners.run_ablation` arm `OOR` |
| 4 | Thay từng khâu bằng bản hoàn hảo, chênh bao nhiêu | Có | `runners.run_ablation` 4 arm |

## Chạy

```bash
# Cả 4 khâu
python -m evaluation.full_evaluation

# Smoke (10 mẫu/bước, kiểm tra ống nước)
python -m evaluation.full_evaluation --smoke

# Bỏ bước
python -m evaluation.full_evaluation --skip intake,retrieval
```

Preflight kiểm: Ollama + model, `data/chroma_db`, `data/bm25_index.pkl`, qrels,
`OPENAI_API_KEY`. Thiếu gì in hướng dẫn sửa. Bước fail không kéo sập bước sau.

## Khâu 4 — mã arm

Arm là **3 ký tự**, mỗi ký tự một khâu `[intaker][rag][generator]`.
`R` = chạy thật, `O` = thay bằng bản hoàn hảo (oracle).

| Arm | Nghĩa | Trả lời |
|---|---|---|
| `RRR` | chạy thật cả 3 | mốc so sánh |
| `ORR` | intake hoàn hảo | intaker đang làm mất bao nhiêu điểm |
| `ROR` | RAG hoàn hảo | RAG đang làm mất bao nhiêu điểm |
| `RRO` | generator hoàn hảo (API) | generator đang làm mất bao nhiêu điểm |
| `OOR` | input hoàn hảo, generator thật | **khâu 3** — generator tốt đến đâu khi được cho đủ |

```bash
python -m evaluation.runners.run_ablation --arms              # 5 arm mặc định
python -m evaluation.runners.run_ablation --arms RRR,OOR --limit 5
python -m evaluation.runners.run_ablation --summarize --output <results.json>
```

100 câu × 5 arm = 500 lượt sinh + 500 lượt chấm. `summary.json` được sinh lại
**tự động** sau mỗi lần chạy arm — không bao giờ để nó stale so với
`results.json`.

Điểm chấm theo từng câu rồi so với `RRR` bằng paired delta + bootstrap 95% CI.
Ghép cặp **riêng từng arm** với baseline: một arm hỏng không rút mẫu của arm
khác. Mẫu bị loại được ghi kèm `drop_reason`.

Safety failure báo riêng, **không bao giờ** gộp vào điểm chất lượng.

## Khâu 1 — Intaker

```bash
python -m evaluation.runners.run_intake --limit 5
```

Dataset held-out `datagen/intakedata/output/intake/intake.val.jsonl` (400 mẫu),
không cache, không fallback, có train-overlap guard. Ba tầng metric:

- **Format**: `schema_valid_rate`, `parse_fail_rate`, `schema_violation_rate`
- **Intent**: accuracy, macro-F1 (advise/knowledge/clarify/reject),
  `reject_recall`, confusion matrix
- **Extraction**: per-field precision/recall/F1 (exact cho enum/số, fuzzy cho
  thuốc/sản phẩm), micro + macro, `hallucinated_field_rate`

Kèm latency p50/p95.

## Khâu 2 — RAG

```bash
python -m evaluation.runners.run_retrieval \
  --dataset evaluation/datasets/v1/retrieval_test.jsonl
```

Qrels 100 câu, `relevance_grade` 0–2, đã relabel và approve. Đo `hit@k`,
`recall@k`, `precision@k`, `MRR`, `MAP`, **graded nDCG**, duplicate rate,
irrelevant-context rate trên 5 mode:

`sparse` · `dense` · `hybrid` · `hybrid_rerank` · `hybrid_mmr_rerank` (production)

Thêm `--raw-query` để so query dựng sẵn với query thô (ablation A4).

## Bất biến — vi phạm là kết quả không hợp lệ

1. **Không fallback**: adapter ép `fallback_model=None`; record có `model_name`
   khác config → lỗi.
2. **Không đụng data production**: audit/session DB của eval nằm trong thư mục
   tạm; response cache tắt.
3. **Dataset frozen**: sửa file sau khi freeze → `load_dataset` raise
   (sha256 `MANIFEST.json`).
4. **Judge mù**: không đưa tên model vào prompt judge.
5. **Generator ghi tường minh**: `run_ablation --model` mặc định lấy
   `settings.llm_model` nhưng **ghi vào artifact**. `.env` đổi thì số cũ vẫn
   truy được là chạy trên model nào.
6. **Một dataset + baseline của chính nó mỗi artifact**: `RRR` mới làm mọi so
   sánh cũ vô hiệu, không bao giờ ghép `RRR` mới với generation cũ.

## Cấu trúc

```
evaluation/
├── full_evaluation.py       orchestrator 4 khâu
├── common.py                path, jsonl, run_meta, git commit
├── adapters/_repo.py        bridge vào product container
├── judges/
│   ├── clients.py           OpenAI client + cache đĩa + đếm cost
│   ├── calibrate.py         Cohen's κ + Spearman người vs judge
│   └── prompts/*.md
├── metrics/
│   ├── classification.py    accuracy, macro-F1, confusion
│   ├── intake.py            intent PRF, ECE, negation leak
│   ├── retrieval.py         recall/precision/MRR/MAP/graded nDCG
│   ├── deterministic.py     pregnancy safety, forbidden claims
│   ├── grounding.py         sentence grounding
│   └── scorecard.py         5 mặt điểm
├── datasets/
│   ├── registry.py          load + validate + sha256 freeze
│   └── v1/retrieval_test.jsonl
├── runners/
│   ├── run_intake.py        khâu 1
│   ├── run_retrieval.py     khâu 2
│   └── run_ablation.py      khâu 3 + 4
└── tests/                   42 test, không cần mạng
```

## Chưa tự động

**Judge calibration** — `judges/calibrate.py` export 50 mẫu đã judge (không kèm
điểm để tránh anchor), người chấm, rồi import lại tính Cohen's κ + Spearman.
Khâu 3 và 4 đều dựa trên một LLM judge; không có κ thì con số không phòng thủ
được. Chạy trước khi công bố.
