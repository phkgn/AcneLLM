# Eval report — 2026-07-26T12:37:08.845435+00:00

## Retrieval metrics — qrels only

> Dataset: `evaluation/datasets/v1/d8_qrels_seed.jsonl`; n=10; artifact: `E:\project\AcneLLM\evaluation\reports\retrieval\2026-07-26T114442\summary.json`. Không dùng answer text.

| mode | hit@3 | recall@5 | mrr@10 | ndcg@5 | precision@5 | irrelevant@5 | dup_rate | latency_ms_mean |
|---|---|---|---|---|---|---|---|---|
| sparse | 0.7 | 0.15 | 0.3917 | 0.2308 | 0.24 | 0.76 | 0.0 | 97 |
| dense | 0.2 | 0.0375 | 0.0667 | 0.0198 | 0.06 | 0.94 | 0.02 | 429 |
| hybrid | 0.5 | 0.075 | 0.3726 | 0.0978 | 0.12 | 0.88 | 0.04 | 584 |
| hybrid_rerank | 0.4 | 0.1 | 0.2526 | 0.1182 | 0.16 | 0.84 | 0.02 | 12283 |
| hybrid_mmr_rerank | 0.4 | 0.1 | 0.2526 | 0.1182 | 0.16 | 0.84 | 0.02 | 420 |

## Answer metrics — generated responses only

> Grounding dùng mẫu số câu đủ điều kiện; câu hỏi, lời chào và disclaimer chuẩn được loại. Safety được chấm trực tiếp trên prose.

| system | contract | n_judged | n_generated | ok | grounded_sentence_rate | grounded/eligible | refusal_fidelity | preg_safety | forbidden_claim_rate | vi_ratio | answer_chars_p50 | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s0 | prose | 3 | 3 | 0.1765 | None | 0/0 | 0.1765 | None | 0.0 | 1.0 | 275 | None | 2.667 | 3.667 | 28296 |
| s1 | prose | 10 | 10 | 1.0 | None | 0/0 | 1.0 | None | 0.0 | 1.0 | 400 | None | 3.3 | 4.1 | 30704 |
| s2 | prose | 1 | 1 | 0.0526 | None | 0/0 | 0.0526 | None | 0.0 | 1.0 | 54 | None | 3.0 | 5.0 | 20010 |
| s3 | prose | 6 | 7 | 0.5 | 0.4286 | 3/7 | 0.5 | None | 0.0 | 1.0 | 344 | 0.3433 | 3.167 | 3.833 | 41644 |
| s4 | prose | 10 | 10 | 1.0 | 0.9011 | 246/273 | 1.0 | None | 0.0 | 1.0 | 2304 | 0.6133 | 2.5 | 3.4 | 344 |

## Pre-registered comparisons

### s0:s1 (n=3)
### s0:s2 (n=1)
### s1:s3 (n=6)
### s2:s3 (n=1)

## Error Pareto per system

- **s0**: E22_infra×14, E14×2, E20×1
- **s1**: E14×1, E16×1
- **s2**: E22_infra×18
- **s3**: E22_infra×7, E14×1, E16×1
- **s4**: E14×6, E11×3, E18×2, E20×1