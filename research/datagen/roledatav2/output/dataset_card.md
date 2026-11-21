# AcneLLM ROLE LoRA dataset

- Format: LLaMA-Factory ShareGPT messages (`system`, `user`, `assistant`)
- Training records: 2616
- Split seed: 42
- Generated card date: 2026-08-17
- Anchor SHA-256: `5421f2079acafe303f635ebca33bb5204ab5efde5a0f1324ad10a1cdf73fb5b5`
- Estimated input tokens: 3399048
- Estimated output tokens: 665125

## Training distribution

| Case | Records |
|---|---:|
| B1_grounded_role | 108 |
| B2_missing_answer | 66 |
| B3_irrelevant_chunk | 32 |
| B4_conflicting_docs | 29 |
| B5_depth_anchor | 29 |
| K1_knowledge_anchor | 198 |
| R10_special_population | 281 |
| R1_identity | 120 |
| R2_depth_adaptation | 429 |
| R3_nonjudgment | 273 |
| R4_measured_empathy | 203 |
| R5_natural_clarification | 254 |
| R6_role_boundary | 173 |
| R7_conversation_glue | 100 |
| R8_meta_jailbreak | 126 |
| R9_multiturn | 195 |

## Coverage matrix

| Rule family | Cases |
|---|---|
| Role identity and limits | R1, R6, R8 |
| Audience depth and tone | R2, R3, R4, R5, R7, R9 |
| Special-population safety | R10 |
| Grounding and abstention | B1, B2, B3, B4, B5 |
| Knowledge preservation | K1 |

Token counts are deterministic character-based estimates (approximately four characters per token).
