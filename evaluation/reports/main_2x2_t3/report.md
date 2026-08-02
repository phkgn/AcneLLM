# Eval report — 2026-07-26T18:03:12.341839+00:00

## Retrieval metrics — qrels only

> Dataset: `evaluation/datasets/v1/retrieval_test.jsonl`; n=100; artifact: `E:\project\AcneLLM\evaluation\reports\retrieval\2026-07-26T173708\summary.json`. Không dùng answer text.

| mode | hit@3 | recall@5 | mrr@10 | ndcg@5 | precision@5 | irrelevant@5 | dup_rate | latency_ms_mean |
|---|---|---|---|---|---|---|---|---|
| sparse | 0.5 | 0.1062 | 0.3564 | 0.1715 | 0.17 | 0.83 | 0.0 | 54 |
| dense | 0.08 | 0.0163 | 0.0523 | 0.0152 | 0.026 | 0.954 | 0.01 | 184 |
| hybrid | 0.25 | 0.0475 | 0.2074 | 0.0692 | 0.076 | 0.924 | 0.016 | 247 |
| hybrid_rerank | 0.21 | 0.0563 | 0.1807 | 0.073 | 0.09 | 0.91 | 0.01 | 7187 |
| hybrid_mmr_rerank | 0.21 | 0.0563 | 0.1807 | 0.073 | 0.09 | 0.91 | 0.01 | 259 |

## Answer metrics — generated responses only

> Grounding dùng mẫu số câu đủ điều kiện; câu hỏi, lời chào và disclaimer chuẩn được loại. Safety được chấm trực tiếp trên prose.

| system | contract | n_judged | n_generated | ok | grounded_sentence_rate | grounded/eligible | refusal_fidelity | preg_safety | forbidden_claim_rate | vi_ratio | answer_chars_p50 | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s0 | legacy_structured_json | 0 | 0 | 1.0 | None | 0/0 | None | None | None | None | None | None | None | None | None |
| s1 | legacy_structured_json | 0 | 0 | 1.0 | None | 0/0 | None | None | None | None | None | None | None | None | None |
| s2 | legacy_structured_json | 0 | 0 | 1.0 | None | 0/0 | None | None | None | None | None | None | None | None | None |
| s3 | legacy_structured_json | 0 | 0 | 1.0 | None | 0/0 | None | None | None | None | None | None | None | None | None |
| s4 | prose | 0 | 0 | 1.0 | None | 0/0 | None | None | None | None | None | None | None | None | None |

## LEGACY structured metrics

> Chỉ dùng để đọc artifact JSON cũ; không thuộc contract hoặc gate prose mới.

| system | parse_success | empty_core_fields_rate |
|---|---|---|
| s0 | None | None |
| s1 | None | None |
| s2 | None | None |
| s3 | None | None |

## Pre-registered comparisons

### s0:s1 (n=10)
- correctness: delta_mean=1.5 CI95=[0.8, 2.1] (SIGNIFICANT) | W/T/L=7/3/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=1.1 CI95=[0.5, 1.9] (SIGNIFICANT) | W/T/L=7/3/0 | wilcoxon_p=N/A (n nhỏ)
### s0:s2 (n=10)
- correctness: delta_mean=0.8 CI95=[0.0, 1.8] (chưa đủ bằng chứng) | W/T/L=3/7/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=0.2 CI95=[-0.6, 1.2] (chưa đủ bằng chứng) | W/T/L=1/8/1 | wilcoxon_p=N/A (n nhỏ)
### s1:s3 (n=10)
- correctness: delta_mean=1.3 CI95=[0.6, 2.0] (SIGNIFICANT) | W/T/L=7/3/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=0.4 CI95=[0.0, 0.8] (chưa đủ bằng chứng) | W/T/L=5/4/1 | wilcoxon_p=N/A (n nhỏ)
### s2:s3 (n=10)
- correctness: delta_mean=2.0 CI95=[1.4, 2.6] (SIGNIFICANT) | W/T/L=9/1/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=1.3 CI95=[0.7, 2.1] (SIGNIFICANT) | W/T/L=8/2/0 | wilcoxon_p=N/A (n nhỏ)

## Error Pareto per system

- **s0**: 
- **s1**: 
- **s2**: 
- **s3**: 
- **s4**: 