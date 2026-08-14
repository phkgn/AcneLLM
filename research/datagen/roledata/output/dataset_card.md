# AcneLLM ROLE LoRA dataset

- Format: LLaMA-Factory ShareGPT messages (`system`, `user`, `assistant`)
- Training records: 2945
- Split seed: 42
- Generated card date: 2026-07-22
- Anchor SHA-256: `722281f002ce584e2c75994ee66e422e691fea453e4cab74ecb1a285b8749c64`
- Estimated input tokens: 2803556
- Estimated output tokens: 237223

## Training distribution

| Case | Records |
|---|---:|
| B1_grounded_role | 323 |
| B2_missing_answer | 170 |
| B3_irrelevant_chunk | 111 |
| B4_conflicting_docs | 59 |
| B5_depth_anchor | 59 |
| K1_knowledge_anchor | 408 |
| R10_special_population | 127 |
| R1_identity | 165 |
| R2_depth_adaptation | 289 |
| R3_nonjudgment | 229 |
| R4_measured_empathy | 187 |
| R5_natural_clarification | 187 |
| R6_role_boundary | 212 |
| R7_conversation_glue | 122 |
| R8_meta_jailbreak | 128 |
| R9_multiturn | 169 |

## Coverage matrix

| Rule family | Cases |
|---|---|
| Role identity and limits | R1, R6, R8 |
| Audience depth and tone | R2, R3, R4, R5, R7, R9 |
| Special-population safety | R10 |
| Grounding and abstention | B1, B2, B3, B4, B5 |
| Knowledge preservation | K1 |

Token counts are deterministic character-based estimates (approximately four characters per token).
