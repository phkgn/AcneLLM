# Metric audit

| Metric | Measures | Input | Layer | Vietnamese/length sensitivity | Reference/context need | Class |
|---|---|---|---|---|---|---|
| parse_success | JSON fallback detection | structured output | T3 parser | no | no | screening |
| vacuous_answer | empty structured answer | AdviseOutput fields | T3 generation | yes | no | screening |
| citation_valid | citation target is in used context | answer + used_chunks | generation/metric | no | needs context ids | deterministic |
| pregnancy_safety | unsafe risk-term mention | answer + pregnancy flag | safety | yes | no | screening |
| forbidden_claims | literal forbidden phrase hit | answer + dataset labels | safety/data | yes | no | screening |
| vietnamese_ratio | CJK-character proxy | answer text | format | yes | no | screening |
| faithfulness | supported claims / claims | answer + real context | generation/grounding | yes | requires context | judge |
| judge axes | 1-5 rubric dimensions | query/context/expected/answer | generation | yes | expected points | judge |
| hit@k / MRR / nDCG | retrieval ranking | qrels + ranked ids | retrieval | no | requires valid qrels | standard IR |
| latency | wall-clock duration | timings_ms | runtime | no | no | operational |

## Validity notes

- `pregnancy_safety`, `vacuous_answer`, `forbidden_claims` and `vietnamese_ratio` are screening heuristics, not clinical-quality metrics.
- Retrieval metrics are reference-only until D8 qrels are relabeled from pooled candidates; current D8 is BM25-biased.
- Faithfulness requires the exact text shown to the model. Chunk IDs alone are insufficient evidence.
- Runtime failures, judge failures, metric failures and skipped cases must never be converted to numeric zero or included in clean means.
- Thresholds in `evaluation/configs/gate.yaml` are regression gates, not proof of clinical adequacy.
