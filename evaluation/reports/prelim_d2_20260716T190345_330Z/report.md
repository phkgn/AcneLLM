# Eval report — 2026-07-17T04:21:51.952913+00:00

## Per-system

| system | n | ok | parse | vacuous | cite_valid | preg_safety | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|
| s0 | 140 | 1.0 | 1.0 | 0.9857 | None | None | None | 1.493 | 2.357 | 16189 |
| s1 | 140 | 1.0 | 1.0 | 0.5 | None | None | None | 2.707 | 3.679 | 19359 |
| s2 | 140 | 1.0 | 1.0 | 1.0 | None | None | 0.2646 | 1.85 | 2.729 | 43989 |
| s3 | 137 | 1.0 | 1.0 | 0.0 | 0.6393 | None | 0.3881 | 3.182 | 4.051 | 78805 |
| s4 | 0 | 1.0 | None | None | None | None | None | None | None | None |

## Pre-registered comparisons

### s0:s1 (n=140)
- correctness: delta_mean=1.214286 CI95=[1.035714, 1.385714] (SIGNIFICANT) | W/T/L=103/30/7 | wilcoxon_p=0.0
- safety: delta_mean=1.321429 CI95=[1.035714, 1.592857] (SIGNIFICANT) | W/T/L=94/29/17 | wilcoxon_p=0.0
### s0:s2 (n=140)
- correctness: delta_mean=0.357143 CI95=[0.171429, 0.535714] (SIGNIFICANT) | W/T/L=62/56/22 | wilcoxon_p=0.000506
- safety: delta_mean=0.371429 CI95=[0.078571, 0.664286] (SIGNIFICANT) | W/T/L=49/60/31 | wilcoxon_p=0.011692
### s1:s3 (n=137)
- correctness: delta_mean=0.489051 CI95=[0.321168, 0.664234] (SIGNIFICANT) | W/T/L=65/53/19 | wilcoxon_p=0.0
- safety: delta_mean=0.386861 CI95=[0.182482, 0.59854] (SIGNIFICANT) | W/T/L=57/53/27 | wilcoxon_p=0.000349
### s2:s3 (n=137)
- correctness: delta_mean=1.328467 CI95=[1.116788, 1.540146] (SIGNIFICANT) | W/T/L=101/25/11 | wilcoxon_p=0.0
- safety: delta_mean=1.313869 CI95=[1.036496, 1.583942] (SIGNIFICANT) | W/T/L=91/32/14 | wilcoxon_p=0.0

### Holm-corrected (Wilcoxon)
- `s0:s1:correctness`: p=0.0 (ngưỡng 0.00625) → SIGNIFICANT
- `s0:s1:safety`: p=0.0 (ngưỡng 0.007143) → SIGNIFICANT
- `s1:s3:correctness`: p=0.0 (ngưỡng 0.008333) → SIGNIFICANT
- `s2:s3:correctness`: p=0.0 (ngưỡng 0.01) → SIGNIFICANT
- `s2:s3:safety`: p=0.0 (ngưỡng 0.0125) → SIGNIFICANT
- `s1:s3:safety`: p=0.000349 (ngưỡng 0.016667) → SIGNIFICANT
- `s0:s2:correctness`: p=0.000506 (ngưỡng 0.025) → SIGNIFICANT
- `s0:s2:safety`: p=0.011692 (ngưỡng 0.05) → SIGNIFICANT

## Error Pareto per system

- **s0**: E18×108, E14×54, E17×29, E16×2
- **s1**: E18×48, E14×42, E12×3, E16×3, E17×2
- **s2**: E14×107, E18×88, E17×14, E16×6, E12×1, E11×1
- **s3**: E14×25, E13_citation_mismatch×23, E18×22, E16×1, E13×1, E17×1
- **s4**: 