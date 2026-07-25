# SMOKE REVIEW V2 — AcneLLM ROLE dataset

- Records smoke đạt inline gate: **18/18**
- Model: `z-ai/glm-5.2-free`; thinking: `disabled`
- Embedder semantic sanity: **0.6643**
- Output train/resume: `E:\project\AcneLLM\datagen\output\v4_role\v4_role.train.jsonl`
- `v4_role.smoke.jsonl` cũ được giữ nguyên; smoke V2 dùng ID train thật.

## Sáu lỗi smoke cũ

1. Xưng hô phụ huynh: validator `vocative_consistency` chạy inline.
2. Code-switch standard: validator `code_switch` chạy inline.
3. Teencode/no-accent: validator `naturalness` yêu cầu câu đủ dài, có động từ và shorthand hợp lệ.
4. B5: pair validator yêu cầu cùng docs, hai depth và hai user khác nhau.
5. Grounding: `semantic_score` lấy từ AITeamVN/Vietnamese_Embedding; preflight abort nếu <= 0.5.
6. Phrase frequency: 8-gram tối đa 5 lần trên generated text.

## Human review — 2026-07-19

- **18/18 chấp nhận được khi đọc tay** đối với mục tiêu ROLE và sáu regression ở trên.
- Hai mẫu R2 chỉ điều chỉnh register/depth: một mẫu cho sinh viên y và một mẫu teencode cho người mới; không lẫn tư vấn điều trị. Regression chính xác `Cô ơi ... mình` được khóa bằng unit test riêng.
- Không còn từ tiếng Anh lạc trong input `standard`; ba augmentation bổ sung (`teencode`, `no_accent`, `typo`) đều đọc hiểu được.
- B5 là đúng một cặp `b5-anchor-0001`: cùng bốn source, hai user khác nhau và hai mức `beginner`/`advanced`.
- B1 từng lộ cụm lỗi `vi khu khuẩn` trong lượt đọc tay. Gate `answer_language_quality` đã được bổ sung, record cùng ID được quarantine rồi regenerate qua pipeline; bản dưới đây là bản đã sửa.
- Semantic grounding khác 0 ở B1/B3/B5; preflight paraphrase đạt **0.6643 > 0.5**. Post-run không có vi phạm phrase-frequency 8-gram trên 106 record.

## Records

| ID | Case | Style | Gate | Semantic max |
|---|---|---|---:|---:|
| `role-r1-000001` | R1_identity | standard | pass | 0.0000 |
| `role-r2-000001` | R2_depth_adaptation | standard | pass | 0.0000 |
| `role-r2-000002` | R2_depth_adaptation | teencode | pass | 0.0000 |
| `role-r3-000001` | R3_nonjudgment | standard | pass | 0.0000 |
| `role-r3-000002` | R3_nonjudgment | no_accent | pass | 0.0000 |
| `role-r4-000001` | R4_measured_empathy | standard | pass | 0.0000 |
| `role-r5-000001` | R5_natural_clarification | standard | pass | 0.0000 |
| `role-r5-000002` | R5_natural_clarification | typo | pass | 0.0000 |
| `role-r6-000001` | R6_role_boundary | standard | pass | 0.0000 |
| `role-r7-000001` | R7_conversation_glue | standard | pass | 0.0000 |
| `role-r8-000001` | R8_meta_jailbreak | standard | pass | 0.0000 |
| `role-r9-000001` | R9_multiturn | standard | pass | 0.0000 |
| `role-b1-000001` | B1_grounded_role | standard | pass | 1.0000 |
| `role-b2-000001` | B2_missing_answer | standard | pass | 0.0000 |
| `role-b3-000001` | B3_irrelevant_chunk | standard | pass | 0.7419 |
| `role-b4-000001` | B4_conflicting_docs | standard | pass | 0.0000 |
| `role-b5-000001` | B5_depth_anchor | standard | pass | 0.8951 |
| `role-b5-000002` | B5_depth_anchor | standard | pass | 0.8271 |

## Post-run

```json
{
  "passed": true,
  "records": 106,
  "unique_ids": 106,
  "schema_errors": [],
  "duplicate_ids": [],
  "phrase_frequency_violations": [],
  "b5_pairs": {
    "passed": true,
    "pass": true,
    "reasons": [],
    "anchor_count": 1,
    "pair_count": 1
  },
  "case_type_counts": {
    "R1": 29,
    "R2": 8,
    "R3": 6,
    "R4": 8,
    "R5": 7,
    "R6": 6,
    "R7": 6,
    "R8": 4,
    "R9": 5,
    "B1": 10,
    "B2": 4,
    "B3": 7,
    "B4": 4,
    "B5": 2
  },
  "input_style_counts": {
    "mixed": 1,
    "no_accent": 9,
    "standard": 82,
    "teencode": 10,
    "typo": 4
  },
  "augmentation_ratio": 0.2264,
  "quota_deficits": {},
  "distribution_warnings": [
    "sample_kind R1: actual=27.4%, expected=7.1%"
  ]
}
```
