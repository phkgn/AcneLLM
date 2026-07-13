# Normalizer evaluation

Test-set: `scripts\eval\normalizer\testset.jsonl` — **1000** samples

## Multi-label fields

| field | micro-F1 | P | R | macro-F1 | Jaccard | exact | n | cov-gap |
|---|---|---|---|---|---|---|---|---|
| lesion_strict | 0.75 | 0.819 | 0.692 | 0.663 | 0.645 | 0.404 | 819 | 168 |
| lesion_bucket | 0.865 | 0.819 | 0.917 | 0.884 | 0.815 | 0.698 | 819 | 0 |
| distribution | 0.957 | 0.982 | 0.933 | 0.823 | 0.946 | 0.914 | 806 | 5 |
| treatment_goals | 0.524 | 0.636 | 0.446 | 0.335 | 0.346 | 0.195 | 938 | 563 |
| hormonal_factors | 0.655 | 0.744 | 0.585 | 0.424 | 0.5 | 0.474 | 310 | 0 |
| red_flags | 0.217 | 0.148 | 0.408 | 0.076 | 0.13 | 0.075 | 545 | 327 |
| medications | 0.432 | 0.78 | 0.299 | 0.37 | 0.25 | 0.214 | 98 | 0 |

## Scalar fields

| field | accuracy | n |
|---|---|---|
| inflammation | 0.616 | 924 |
| sex | 0.345 | 473 |
| skin_type | 0.79 | 424 |
| is_pregnant | 0.986 | 1000 |
| is_breastfeeding | 0.998 | 1000 |

## Weakest labels (recall, support)

- **lesion_strict**: comedone=0.0(n149), cyst=0.23(n155), pustule=0.65(n342), closed_comedone=0.72(n116), papule=0.84(n332), whitehead=0.86(n80), nodule=0.91(n235), blackhead=1.0(n229)
- **lesion_bucket**: inflammatory=0.87(n383), nodulocystic=0.92(n236), comedonal=0.97(n298)
- **distribution**: forehead=0.83(n151), jawline=0.92(n157), chin=0.94(n530), nose=0.94(n216), cheeks=0.95(n402), back=1.0(n22), chest=1.0(n5)
- **treatment_goals**: fade_hyperpigmentation=0.31(n155), reduce_inflammation=0.32(n453), clear_acne=0.49(n671), treat_scar=0.87(n112)
- **hormonal_factors**: puberty=0.17(n30), stress=0.33(n36), menstrual_cycle=0.53(n134), pregnancy=0.91(n82), postpartum=1.0(n6)
- **red_flags**: severe_inflammation=0.0(n44), scarring_risk=0.49(n221)
- **medications**: benzoyl_peroxide=0.0(n63), salicylic_acid=0.0(n6), adapalene=0.94(n16), clindamycin=1.0(n7), tretinoin=1.0(n6)

## Coverage gaps (gold labels normalizer cannot emit)

- **lesion_strict**: post_inflammatory_hyperpigmentation(129), scar(118)
- **distribution**: neck(5)
- **treatment_goals**: prevent_scarring(224), reduce_blackheads(217), skin_care_routine(194), reduce_comedones(187), safe_for_pregnancy(1)
- **red_flags**: severe_nodular_cystic_acne(200), treatment_failure(139), pregnancy(82), persistent_acne(50), breastfeeding(6), hypertension(1)

## Inflammation confusion (gold → pred)

- gold **moderate**: severe=42, moderate=201, mild=29, unknown=19, none=2
- gold **none**: none=153, unknown=88, moderate=68, mild=9
- gold **severe**: severe=182, moderate=12, unknown=2, mild=1
- gold **mild**: unknown=40, none=15, mild=33, moderate=28

## Caveats

- Gold labels are LLM-generated (silver standard), not verified ground truth.
- Fields with high coverage_gap use a different taxonomy than the normalizer; low scores there reflect vocabulary divergence, not necessarily errors.
