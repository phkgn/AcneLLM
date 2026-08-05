# AcneLLM Evaluation — 3 khâu

> Thiết kế đầy đủ: **[`eval_context.md`](eval_context.md)**

Hệ thống có 3 khâu nối tiếp: **intaker → RAG → generator**. Eval làm đúng 2 việc
và không làm gì khác.

| Khâu | Đo gì | Cần LLM chấm | Chạy bằng |
|---|---|---|---|
| 1 | Intaker rút đúng 15 slot không | Không | `runners.run_intake` |
| 2 | Tài liệu retrieval mang về có dùng được không | Có | `runners.run_retrieval` |
| 3 | Thay từng khâu bằng bản hoàn hảo / tắt hẳn, chênh bao nhiêu | Có | `runners.run_ablation` |

**Khâu 2 không dùng recall@k trên chunk vàng.** Chấm theo danh tính chunk là chấm
oan — nhiều đoạn cùng chủ đề, mang về đoạn khác mà vẫn trả lời được thì vẫn bị
tính trượt. Judge hỏi thẳng "đoạn này liên quan không, đủ trả lời không", nên
chạy được trên bất kỳ tập câu hỏi nào kể cả câu hỏi thật, không cần ai gán nhãn.

```bash
python -m evaluation.runners.run_retrieval --limit 30
```

`relevant_chunk_ids` giờ chỉ còn là cơ chế bơm context cho arm `ROR` ở khâu 3.

## Chạy

```bash
# Cả 2 khâu
python -m evaluation.full_evaluation

# Smoke (10 mẫu/bước, kiểm tra ống nước)
python -m evaluation.full_evaluation --smoke

# Bỏ bước
python -m evaluation.full_evaluation --skip intake,retrieval
```

Preflight kiểm: Ollama + model, `data/chroma_db`, `data/bm25_index.pkl`, bộ câu hỏi,
`OPENAI_API_KEY`. Thiếu gì in hướng dẫn sửa. Bước fail không kéo sập bước sau.

## Khâu 2 — mã arm

Arm là **3 ký tự**, mỗi ký tự một khâu `[intaker][rag][generator]`.

`R` = chạy thật · `O` = bản hoàn hảo · `N` = tắt hẳn (chỉ cho RAG).
Không gian đầy đủ 2 × 3 × 2 = 12 arm; mặc định chạy 6:

| Arm | Đọc ra |
|---|---|
| `RRR` | **mốc** — sản phẩm hiện tại |
| `RNR` | RAG có đóng góp gì không |
| `ROR` | retriever còn dư địa bao nhiêu |
| `ORR` | intaker có đáng sửa không |
| `RRO` | generator có phải nút thắt |
| `RNO` | model mạnh có cần RAG không |

```bash
python -m evaluation.runners.run_ablation --arms              # 6 arm mặc định
python -m evaluation.runners.run_ablation --arms RRR,RNR --limit 5
python -m evaluation.runners.run_ablation --summarize --output <results.json>
```

100 câu × 6 arm = 600 lượt sinh + 600 lượt chấm. `summary.json` được sinh lại
**tự động** sau mỗi lần chạy arm — không bao giờ để nó stale so với
`results.json`.

Điểm chấm theo từng câu rồi so với `RRR` bằng paired delta + bootstrap 95% CI.
Ghép cặp **riêng từng arm** với baseline: một arm hỏng không rút mẫu của arm
khác. Mẫu bị loại được ghi kèm `drop_reason`.

Safety failure báo riêng, **không bao giờ** gộp vào điểm chất lượng.

## Không đo bằng từ vựng

KB 60% Việt / 40% Anh nên mọi phép khớp từ đều thưởng cho đoạn cùng ngôn ngữ với
câu hỏi, bất kể nội dung. `grounding_support` (`char_3gram_dice`) và
`forbidden_claims` (khớp chuỗi, 0 lần kích hoạt / 770 dòng) đã bị gỡ. Thay bằng
5 mặt do judge chấm ngữ nghĩa, một lượt gọi mỗi dòng:

| Mặt | Thang |
|---|---|
| `context_relevance` | 0–5, trung bình điểm từng chunk |
| `context_precision` | 0–1, tỉ lệ chunk đạt ≥ 3 |
| `context_sufficiency` | 0–5, gộp lại có đủ trả lời không |
| `ranking_quality` | 0–1, nDCG trên chính điểm judge |
| `groundedness` | 0–5, câu trả lời bám tài liệu hay tự bịa |

`ranking_quality` không cần `relevant_chunk_ids` — thứ tự lý tưởng là điểm judge
sắp giảm dần. `relevant_chunk_ids` giờ chỉ còn là cơ chế bơm context cho `ROR`,
không còn là thước đo.

## Sinh bộ câu hỏi cho khâu 2

```bash
python -m evaluation.datasets.make_eval_set --sample                        # mẫu, không gọi API
python -m evaluation.datasets.make_eval_set --generate --n 100 --policy-n 30
```

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
├── full_evaluation.py       orchestrator 2 khâu
├── common.py                path, jsonl, run_meta, git commit
├── adapters/_repo.py        bridge vào product container
├── judges/
│   ├── clients.py           OpenAI client + cache đĩa + đếm cost
│   ├── context.py           5 mặt context do judge chấm (KHÔNG đếm từ)
│   ├── calibrate.py         Cohen's κ + Spearman người vs judge
│   └── prompts/*.md
├── metrics/
│   ├── classification.py    accuracy, macro-F1, confusion
│   ├── intake.py            intent PRF, ECE, negation leak
│   ├── deterministic.py     pregnancy safety, forbidden claims
│   └── scorecard.py         9 mặt điểm
├── datasets/
│   ├── registry.py          load + validate + sha256 freeze
│   ├── make_eval_set.py     sinh bộ câu hỏi từ chunk thật
│   └── eval_set.jsonl
├── runners/
│   ├── run_intake.py        khâu 1
│   ├── run_retrieval.py     khâu 2 — judge chấm tài liệu
│   └── run_ablation.py      khâu 3
└── tests/                   45 test, không cần mạng
```

## Chưa tự động

**Judge calibration** — `judges/calibrate.py` export 50 mẫu đã judge (không kèm
điểm để tránh anchor), người chấm, rồi import lại tính Cohen's κ + Spearman.
Khâu 2 dựa trên một LLM judge; không có κ thì con số không phòng thủ
được. Chạy trước khi công bố.
