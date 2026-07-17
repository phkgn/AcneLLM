# Eval report — 2026-07-17T10:39:03.042496+00:00

## Per-system

| system | n | ok | parse | vacuous | cite_valid | preg_safety | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|
| s0 | 30 | 1.0 | 1.0 | 1.0 | None | None | None | 4.5 | 4.9 | 16249 |
| s1 | 30 | 1.0 | 1.0 | 0.4667 | None | None | None | 4.133 | 4.6 | 17050 |
| s2 | 30 | 1.0 | 1.0 | 1.0 | None | None | 0.4609 | 4.6 | 4.967 | 36459 |
| s3 | 30 | 1.0 | 1.0 | 0.0 | 0.75 | None | 0.4812 | 4.6 | 4.833 | 73844 |
| s4 | 30 | 1.0 | None | None | 1.0 | None | 0.8234 | 4.567 | 4.8 | 13905 |

## Pre-registered comparisons

### s0:s1 (n=30)
- correctness: delta_mean=-0.366667 CI95=[-0.666667, -0.066667] (SIGNIFICANT) | W/T/L=5/11/14 | wilcoxon_p=0.027633
- safety: delta_mean=-0.3 CI95=[-0.5, -0.1] (SIGNIFICANT) | W/T/L=1/19/10 | wilcoxon_p=0.006656
### s0:s2 (n=30)
- correctness: delta_mean=0.1 CI95=[-0.166667, 0.366667] (chưa đủ bằng chứng) | W/T/L=6/19/5 | wilcoxon_p=0.448423
- safety: delta_mean=0.066667 CI95=[-0.066667, 0.2] (chưa đủ bằng chứng) | W/T/L=3/26/1 | wilcoxon_p=N/A (n nhỏ)
### s1:s3 (n=30)
- correctness: delta_mean=0.466667 CI95=[0.166667, 0.766667] (SIGNIFICANT) | W/T/L=14/13/3 | wilcoxon_p=0.006175
- safety: delta_mean=0.233333 CI95=[0.0, 0.466667] (chưa đủ bằng chứng) | W/T/L=11/15/4 | wilcoxon_p=0.070701
### s2:s3 (n=30)
- correctness: delta_mean=0.0 CI95=[-0.2, 0.2] (chưa đủ bằng chứng) | W/T/L=5/20/5 | wilcoxon_p=1.0
- safety: delta_mean=-0.133333 CI95=[-0.266667, -0.033333] (SIGNIFICANT) | W/T/L=0/26/4 | wilcoxon_p=N/A (n nhỏ)

### Holm-corrected (Wilcoxon)
- `s1:s3:correctness`: p=0.006175 (ngưỡng 0.008333) → SIGNIFICANT
- `s0:s1:safety`: p=0.006656 (ngưỡng 0.01) → SIGNIFICANT
- `s0:s1:correctness`: p=0.027633 (ngưỡng 0.0125) → not significant
- `s1:s3:safety`: p=0.070701 (ngưỡng 0.016667) → not significant
- `s0:s2:correctness`: p=0.448423 (ngưỡng 0.025) → not significant
- `s2:s3:correctness`: p=1.0 (ngưỡng 0.05) → not significant

## Error Pareto per system

- **s0**: 
- **s1**: 
- **s2**: 
- **s3**: E13_citation_mismatch×3
- **s4**: 