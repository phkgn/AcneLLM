# AcneLLM ROLE LoRA dataset

- Format: LLaMA-Factory ShareGPT messages (`system`, `user`, `assistant`)
- Training records: 2349
- Split seed: 42
- Generated card date: 2026-08-11
- Anchor SHA-256: `722281f002ce584e2c75994ee66e422e691fea453e4cab74ecb1a285b8749c64`
- Estimated input tokens: 2534738
- Estimated output tokens: 526439

## Training distribution

| Case | Records |
|---|---:|
| B1_grounded_role | 297 |
| B2_missing_answer | 113 |
| B3_irrelevant_chunk | 117 |
| B4_conflicting_docs | 65 |
| B5_depth_anchor | 66 |
| K1_knowledge_anchor | 418 |
| R10_special_population | 99 |
| R1_identity | 118 |
| R2_depth_adaptation | 204 |
| R3_nonjudgment | 145 |
| R4_measured_empathy | 70 |
| R5_natural_clarification | 131 |
| R6_role_boundary | 183 |
| R7_conversation_glue | 101 |
| R8_meta_jailbreak | 126 |
| R9_multiturn | 96 |

## Coverage matrix

| Rule family | Cases |
|---|---|
| Role identity and limits | R1, R6, R8 |
| Audience depth and tone | R2, R3, R4, R5, R7, R9 |
| Special-population safety | R10 |
| Grounding and abstention | B1, B2, B3, B4, B5 |
| Knowledge preservation | K1 |

Token counts are deterministic character-based estimates (approximately four characters per token).
