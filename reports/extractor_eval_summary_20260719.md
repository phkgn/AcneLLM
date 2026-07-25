# AcneLLM LLM extractor implementation and evaluation — 2026-07-19

## Outcome

The `acne-extractor:1.5b` path is implemented and live behind
`EXTRACTOR_MODE=llm` (the default). It produces `UserInput`,
`ExtractionConfidence`, and `RouteDecision`, and falls back to the unchanged
rule path on transport, JSON, schema, or adapter failure. Existing guardrail,
scope, complaint, reject, session-fold, medication, completeness, and route
override gates remain in their original order.

Contract reliability is good; semantic quality is not yet trustworthy. The
model returned valid contract-shaped JSON for all 985 golden rows, but it often
over-extracted profile/clinical fields and misclassified intent.

## Provenance

- Golden set: `data/golden_extraction_gen.jsonl` (985 rows)
- Model tag: `acne-extractor:1.5b`
- Base: `qwen2.5:1.5b`
- Build source: `model/Modelfile.extractor`
- Full raw-model report: `reports/extractor_eval_full_20260719.json`
- Post-eval deterministic safety floor: `reports/extractor_safety_net_20260719.json`
- Full test suite: `483 passed, 1 xfailed`
- Lint: all changed Python files passed Ruff

## Full golden evaluation

The LLM eval calls the adapter directly and does not substitute rule
predictions when the model fails.

| Metric | Rule | LLM |
|---|---:|---:|
| Rows | 985 | 985 |
| Contract/transport failures | 0 | 0 |
| Primary-intent accuracy | 0.7157 | 0.2558 |
| Query-subject accuracy | 0.7117 | 0.4599 |
| Joint intent+subject accuracy | 0.6142 | 0.2305 |

Selected per-field F1:

| Field | Rule F1 | Raw LLM F1 | Delta |
|---|---:|---:|---:|
| skin_type | 0.7722 | 0.4239 | -0.3483 |
| age | 0.9111 | 0.9214 | +0.0103 |
| duration_weeks | 0.8232 | 0.5507 | -0.2725 |
| inflammation | 0.6618 | 0.4010 | -0.2608 |
| lesions | 0.6755 | 0.3555 | -0.3200 |
| distribution | 0.8978 | 0.3996 | -0.4982 |
| products | 0.6336 | 0.1538 | -0.4798 |
| medications | 0.6301 | 0.2097 | -0.4204 |
| allergies | 0.5217 | 0.1163 | -0.4054 |
| scarring_signs | 0.8607 | 0.0000 | -0.8607 |
| hormonal_factors | 0.7174 | 0.1896 | -0.5278 |
| treatment_goals | 0.4664 | 0.0044 | -0.4620 |

Pregnancy and breastfeeding extraction improved over the legacy rules on this
dataset (`F1=0.4575` and `0.4087`, versus `0.2092` and `0.2182`), but the raw
model dropped medication and allergy recall.

## Safety-net verification

The final runtime additionally unions deterministic raw-text safety matches
with model fields before guardrails. This is a narrow safety path; it does not
call the three replaced producer functions.

Across all 985 rows, the deterministic floor is:

| Field | Precision | Recall | F1 |
|---|---:|---:|---:|
| medications | 0.5000 | 0.8519 | 0.6301 |
| allergies | 0.4248 | 0.6761 | 0.5217 |

Because runtime uses set union, effective medication/allergy recall cannot be
lower than these floors. Explicit first-person pregnancy/breastfeeding matches
also override a model `false`, and raw drug terms continue to feed the existing
deterministic medication-refusal gate.

## Decision

Keep `EXTRACTOR_MODE=llm` as required, even though the rule baseline is better.
Do not treat the current 1.5B semantic output as production-trustworthy: valid
JSON can still be wrong and therefore will not trigger technical fallback. The
next improvement target is model/prompt quality or calibration, especially
personal `advise+self` routing and suppression of unsupported clinical fields;
it is not another guardrail refactor.
