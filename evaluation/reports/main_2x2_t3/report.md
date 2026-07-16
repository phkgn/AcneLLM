# Eval report — 2026-07-16T15:57:28.682915+00:00

## Per-system

| system | n | ok | parse | vacuous | cite_valid | preg_safety | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|
| s0 | 10 | 1.0 | 1.0 | 1.0 | None | 1.0 | None | 1.0 | 2.8 | 16983 |
| s1 | 10 | 1.0 | 1.0 | 0.8 | None | 1.0 | None | 2.5 | 3.9 | 14973 |
| s2 | 10 | 1.0 | 1.0 | 1.0 | None | 1.0 | 0.0 | 1.8 | 3.0 | 41701 |
| s3 | 10 | 1.0 | 1.0 | 0.2 | 1.0 | 1.0 | 0.0 | 3.8 | 4.3 | 53514 |
| s4 | 10 | 1.0 | None | None | 1.0 | 1.0 | 0.0 | 4.3 | 4.6 | 12589 |

## Pre-registered comparisons

### s0:s1 (n=10)
- correctness: delta_mean=1.5 CI95=[0.8, 2.1] (SIGNIFICANT) | W/T/L=7/3/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=1.1 CI95=[0.5, 1.9] (SIGNIFICANT) | W/T/L=7/3/0 | wilcoxon_p=N/A (n nhỏ)
- pregnancy_safety McNemar: n01=0 n10=0 p=1.0
### s0:s2 (n=10)
- correctness: delta_mean=0.8 CI95=[0.0, 1.8] (chưa đủ bằng chứng) | W/T/L=3/7/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=0.2 CI95=[-0.6, 1.2] (chưa đủ bằng chứng) | W/T/L=1/8/1 | wilcoxon_p=N/A (n nhỏ)
- pregnancy_safety McNemar: n01=0 n10=0 p=1.0
### s1:s3 (n=10)
- correctness: delta_mean=1.3 CI95=[0.6, 2.0] (SIGNIFICANT) | W/T/L=7/3/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=0.4 CI95=[0.0, 0.8] (chưa đủ bằng chứng) | W/T/L=5/4/1 | wilcoxon_p=N/A (n nhỏ)
- pregnancy_safety McNemar: n01=0 n10=0 p=1.0
### s2:s3 (n=10)
- correctness: delta_mean=2.0 CI95=[1.4, 2.6] (SIGNIFICANT) | W/T/L=9/1/0 | wilcoxon_p=N/A (n nhỏ)
- safety: delta_mean=1.3 CI95=[0.7, 2.1] (SIGNIFICANT) | W/T/L=8/2/0 | wilcoxon_p=N/A (n nhỏ)
- pregnancy_safety McNemar: n01=0 n10=0 p=1.0

## Error Pareto per system

- **s0**: 
- **s1**: 
- **s2**: 
- **s3**: 
- **s4**: 