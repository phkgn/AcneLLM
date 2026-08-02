# Dataset audit

- Target: `E:\project\AcneLLM\evaluation\datasets\v1\d2_test.jsonl`
- Directory: `E:\project\AcneLLM\evaluation\datasets\v1`

| File | Rows | Schema errors | Approved | Frozen | Exact dup | Near dup | Contradictions |
|---|---:|---:|---:|---|---:|---:|---:|
| `d1_dev_seed.jsonl` | 100 | 0 | 0 | no | 20 | 20 | 0 |
| `d2_test.jsonl` | 140 | 0 | 140 | no | 0 | 0 | 0 |
| `d3_challenge.jsonl` | 60 | 0 | 60 | no | 0 | 0 | 0 |
| `d4_safety.jsonl` | 140 | 0 | 140 | no | 0 | 0 | 0 |
| `d5_multiturn.jsonl` | 72 | 0 | 72 | no | 0 | 0 | 0 |
| `d6_ood.jsonl` | 96 | 0 | 96 | no | 0 | 0 | 0 |
| `d7_adversarial.jsonl` | 120 | 0 | 120 | no | 0 | 0 | 0 |
| `d8_qrels_seed.jsonl` | 100 | 0 | 0 | no | 20 | 20 | 0 |
| `t1_guardrails_seed.jsonl` | 20 | 0 | 0 | no | 0 | 0 | 0 |
| `t1_intent_seed.jsonl` | 24 | 0 | 0 | no | 0 | 0 | 0 |

## Train contamination

- Status: **CHECKED**
- Train: `E:\project\AcneLLM\data\finetune\clean\acne_chat_response.train.jsonl`
- n-gram / threshold: `8` / `0.5`
- `d1_dev_seed.jsonl`: 2 flagged — d1-0003, d1-0023
- `d8_qrels_seed.jsonl`: 2 flagged — d8-0003, d8-0023
- `t1_intent_seed.jsonl`: 2 flagged — t1i-0010, t1i-0023

## Cross-split leakage

- No verbatim target-query leakage found across v1 files.

## Human review queue

- `d2-0019` — Missing-information query has overly specific expected points. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d2_test.jsonl`
- `d2-0049` — Missing-information query has overly specific expected points. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d2_test.jsonl`
- `d3-0041` — Missing-information query has overly specific expected points. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d3_challenge.jsonl`
- `d7-0001` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0002` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0006` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0011` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0012` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0019` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0020` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0025` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0027` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0033` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0038` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0039` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0041` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0045` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0049` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0054` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0055` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0059` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0067` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0070` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0073` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0075` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0078` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0079` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0085` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0086` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0095` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0098` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0100` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0073-typo3` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0012-typo8` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0067-typo9` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `d7-0001-typo10` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\d7_adversarial.jsonl`
- `t1g-0006` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_guardrails_seed.jsonl`
- `t1g-0010` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_guardrails_seed.jsonl`
- `t1g-0014` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_guardrails_seed.jsonl`
- `t1i-0010` — Router keyword bait; verify label from semantics, not trigger words. Evidence: `E:\project\AcneLLM\evaluation\datasets\v1\t1_intent_seed.jsonl`

## Interpretation rule

Synthetic generation provenance is acceptable only after human approval and SHA-256 freeze. D8 remains a reference-only retrieval set while its labels are `needs_relabel`.
