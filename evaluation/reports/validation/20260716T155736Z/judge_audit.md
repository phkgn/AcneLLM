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
  "valid_pointwise": 50,
  "parser_failures": 0,
  "faithfulness_rows": 25,
  "invalid_faithfulness_context": 25,
  "pairwise": {
    "pairwise_s0_vs_s1.jsonl": {
      "n": 10,
      "invalid": 0
    },
    "pairwise_s0_vs_s2.jsonl": {
      "n": 10,
      "invalid": 0
    },
    "pairwise_s1_vs_s3.jsonl": {
      "n": 10,
      "invalid": 0
    },
    "pairwise_s2_vs_s3.jsonl": {
      "n": 10,
      "invalid": 0
    }
  },
  "bias": {}
}
```

**Faithfulness in this run is not trustworthy:** judged rows exist but source text is absent from the saved trace. This is an artifact-level validity failure, even though the current source code contains the context-trace fix.
