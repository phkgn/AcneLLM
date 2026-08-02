# Eval report — 2026-07-17T08:26:44.205560+00:00

## Per-system

| system | n | ok | parse | vacuous | cite_valid | preg_safety | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|
| s0 | 140 | 1.0 | 1.0 | 0.9857 | None | None | None | 3.671 | 4.371 | 16189 |
| s1 | 140 | 1.0 | 1.0 | 0.5 | None | None | None | 3.45 | 4.229 | 19359 |
| s2 | 140 | 1.0 | 1.0 | 1.0 | None | None | 0.4009 | 3.264 | 4.279 | 43989 |
| s3 | 140 | 1.0 | 1.0 | 0.0 | 0.6349 | None | 0.4543 | 3.514 | 4.55 | 79088 |
| s4 | 140 | 1.0 | None | None | 1.0 | None | 0.8431 | 3.221 | 4.321 | 13922 |

## Pre-registered comparisons

### s0:s1 (n=140)
- correctness: delta_mean=-0.221429 CI95=[-0.328571, -0.121429] (SIGNIFICANT) | W/T/L=11/90/39 | wilcoxon_p=6.1e-05
- safety: delta_mean=-0.142857 CI95=[-0.392857, 0.121429] (chưa đủ bằng chứng) | W/T/L=26/77/37 | wilcoxon_p=0.251516
### s0:s2 (n=140)
- correctness: delta_mean=-0.407143 CI95=[-0.507143, -0.307143] (SIGNIFICANT) | W/T/L=7/71/62 | wilcoxon_p=0.0
- safety: delta_mean=-0.092857 CI95=[-0.328571, 0.15] (chưa đủ bằng chứng) | W/T/L=23/81/36 | wilcoxon_p=0.311476
### s1:s3 (n=140)
- correctness: delta_mean=0.064286 CI95=[-0.042857, 0.178571] (chưa đủ bằng chứng) | W/T/L=29/88/23 | wilcoxon_p=0.291809
- safety: delta_mean=0.321429 CI95=[0.092857, 0.557143] (SIGNIFICANT) | W/T/L=42/67/31 | wilcoxon_p=0.013079
### s2:s3 (n=140)
- correctness: delta_mean=0.25 CI95=[0.157143, 0.342857] (SIGNIFICANT) | W/T/L=41/91/8 | wilcoxon_p=2e-06
- safety: delta_mean=0.271429 CI95=[0.1, 0.45] (SIGNIFICANT) | W/T/L=40/78/22 | wilcoxon_p=0.002816

### Holm-corrected (Wilcoxon)
- `s0:s2:correctness`: p=0.0 (ngưỡng 0.00625) → SIGNIFICANT
- `s2:s3:correctness`: p=2e-06 (ngưỡng 0.007143) → SIGNIFICANT
- `s0:s1:correctness`: p=6.1e-05 (ngưỡng 0.008333) → SIGNIFICANT
- `s2:s3:safety`: p=0.002816 (ngưỡng 0.01) → SIGNIFICANT
- `s1:s3:safety`: p=0.013079 (ngưỡng 0.0125) → not significant
- `s0:s1:safety`: p=0.251516 (ngưỡng 0.016667) → not significant
- `s1:s3:correctness`: p=0.291809 (ngưỡng 0.025) → not significant
- `s0:s2:safety`: p=0.311476 (ngưỡng 0.05) → not significant

## Error Pareto per system

- **s0**: E14×17, E18×16, E20×5
- **s1**: E14×19, E18×17, E16×8, E20×5, E15×1
- **s2**: E14×16, E18×16, E20×5, E14_incomplete_answer×1, E18_poor_uncertainty×1, E16×1, E11×1
- **s3**: E13_citation_mismatch×23, E14×6, E18×5, E16×2
- **s4**: E14×6, E18×3, E11×3, E20×1, E13×1