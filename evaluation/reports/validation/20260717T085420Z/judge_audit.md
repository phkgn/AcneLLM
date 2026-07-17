# Judge audit

| Prompt | Exists | Blind model | Length guard | Evidence-only where required |
|---|---|---|---|---|
| `pointwise.md` | yes | PASS | no | n/a/no |
| `pairwise.md` | yes | PASS | yes | n/a/no |
| `claim_extract.md` | yes | PASS | no | n/a/no |
| `entailment.md` | yes | PASS | no | yes |
| `error_classify.md` | yes | PASS | no | n/a/no |

## Rubric risks

- `pointwise.md` deliberately allows standard medical knowledge for correctness, while `entailment.md` forbids external knowledge for groundedness. Mixing those two outputs would be invalid.
- Correctness and completeness partially overlap because expected points affect both; report them as separate axes and retain per-case evidence.
- Pairwise includes an explicit anti-length-bias instruction and is evaluated in both A/B orders; disagreement becomes tie.
- Parser contract: malformed JSON returns `None`; the runner must persist `judge_status=invalid`, never substitute score 0.

## Artifact validation

```json
{
  "valid_pointwise": 700,
  "parser_failures": 0,
  "faithfulness_rows": 416,
  "invalid_faithfulness_context": 0,
  "pairwise": {
    "pairwise_s0_vs_s1.jsonl": {
      "n": 140,
      "invalid": 0
    },
    "pairwise_s0_vs_s2.jsonl": {
      "n": 140,
      "invalid": 0
    },
    "pairwise_s1_vs_s3.jsonl": {
      "n": 140,
      "invalid": 0
    },
    "pairwise_s2_vs_s3.jsonl": {
      "n": 140,
      "invalid": 0
    }
  },
  "bias": {
    "generated_at": "2026-07-17T08:37:45.532404+00:00",
    "judge_provider": "openai",
    "judge_model": "gpt-5-mini-2025-08-07",
    "dataset": "evaluation/datasets/v1/d1_dev_seed.jsonl",
    "requested_n": 30,
    "targets": {
      "position_flip_rate_max": 0.1,
      "length_spearman_abs_max": 0.3,
      "consistency_min": 0.85
    },
    "position_bias": {
      "flip_rate": 0.2222,
      "n": 27,
      "pass": false
    },
    "length_bias": {
      "spearman_score_vs_length": 0.2194,
      "n": 50,
      "pass": true
    },
    "consistency": {
      "exact_agreement": 0.7333,
      "n": 30,
      "pass": false
    },
    "cost_usd": 0.046
  }
}
```
