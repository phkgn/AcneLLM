# Eval report — 2026-07-27T20:49:36.909613+00:00

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
| s0 | prose | 140 | 140 | 1.0 | None | 0/0 | 1.0 | None | 0.0 | 1.0 | 929 | None | 2.921 | 2.957 | 45037 |
| s1 | prose | 140 | 140 | 1.0 | None | 0/0 | 1.0 | None | 0.0 | 1.0 | 383 | None | 3.457 | 4.029 | 25032 |
| s2 | prose | 140 | 140 | 1.0 | 0.4371 | 1050/2402 | 1.0 | None | 0.0 | 1.0 | 1126 | 0.3458 | 3.207 | 3.271 | 59333 |
| s3 | prose | 140 | 140 | 1.0 | 0.3578 | 224/626 | 1.0 | None | 0.0 | 1.0 | 427 | 0.2494 | 3.493 | 3.907 | 32297 |
| s4 | prose | 140 | 140 | 1.0 | 0.8934 | 3059/3424 | 1.0 | None | 0.0 | 1.0 | 2255 | 0.8571 | 2.821 | 3.307 | 10139 |

## Pre-registered comparisons

### s0:s1 (n=140)
- correctness: delta_mean=0.535714 CI95=[0.378571, 0.692857] (SIGNIFICANT) | W/T/L=66/57/17 | wilcoxon_p=0.0
- safety: delta_mean=1.071429 CI95=[0.842857, 1.3] (SIGNIFICANT) | W/T/L=83/43/14 | wilcoxon_p=0.0
### s0:s2 (n=140)
- correctness: delta_mean=0.285714 CI95=[0.114286, 0.464286] (SIGNIFICANT) | W/T/L=59/50/31 | wilcoxon_p=0.00254
- safety: delta_mean=0.314286 CI95=[0.057143, 0.571429] (SIGNIFICANT) | W/T/L=61/40/39 | wilcoxon_p=0.029081
### s1:s3 (n=140)
- correctness: delta_mean=0.035714 CI95=[-0.107143, 0.178571] (chưa đủ bằng chứng) | W/T/L=39/68/33 | wilcoxon_p=0.648077
- safety: delta_mean=-0.121429 CI95=[-0.285714, 0.042857] (chưa đủ bằng chứng) | W/T/L=29/75/36 | wilcoxon_p=0.18458
### s2:s3 (n=140)
- correctness: delta_mean=0.285714 CI95=[0.128571, 0.442857] (SIGNIFICANT) | W/T/L=57/55/28 | wilcoxon_p=0.000937
- safety: delta_mean=0.635714 CI95=[0.392857, 0.871429] (SIGNIFICANT) | W/T/L=70/40/30 | wilcoxon_p=2e-06

### Holm-corrected (Wilcoxon)
- `s0:s1:correctness`: p=0.0 (ngưỡng 0.00625) → SIGNIFICANT
- `s0:s1:safety`: p=0.0 (ngưỡng 0.007143) → SIGNIFICANT
- `s2:s3:safety`: p=2e-06 (ngưỡng 0.008333) → SIGNIFICANT
- `s2:s3:correctness`: p=0.000937 (ngưỡng 0.01) → SIGNIFICANT
- `s0:s2:correctness`: p=0.00254 (ngưỡng 0.0125) → SIGNIFICANT
- `s0:s2:safety`: p=0.029081 (ngưỡng 0.016667) → not significant
- `s1:s3:safety`: p=0.18458 (ngưỡng 0.025) → not significant
- `s1:s3:correctness`: p=0.648077 (ngưỡng 0.05) → not significant

## Error Pareto per system

- **s0**: E14×61, E11×31, E18×27, E20×12, E15×12, E16×11, E12×2, E17×1
- **s1**: E14×17, E18×9, E16×7, E11×6, E15×2, E12×1
- **s2**: E14×45, E11×28, E18×28, E15×18, E16×12, E20×10, E12×9, E14 incomplete_answer×1, E18 poor_uncertainty×1, E20 language_format_error×1
- **s3**: E14×21, E18×14, E16×11, E11×7, E15×4, E19×1, E12×1, E20×1
- **s4**: E14×71, E18×28, E20×22, E16×11, E11×9, E15×4, E19×1