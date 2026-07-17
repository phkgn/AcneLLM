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
  "valid_pointwise": 1,
  "parser_failures": 0,
  "faithfulness_rows": 0,
  "invalid_faithfulness_context": 0,
  "pairwise": {},
  "bias": {}
}
```
