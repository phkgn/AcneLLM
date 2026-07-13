# Normalizer evaluation harness

Measures how well the **rule-based pipeline normalizer**
(`acne_llm.chat.normalizer.normalize_chat_message`) reproduces the structured
`normalized_case` labels shipped in `data/finetune/cleanv3_gen.jsonl`.

## Why it's built this way

The finetune file already pairs every `<raw_user_message>` with a gold
`<normalized_case>`. Those cases are a ready-made evaluation target — **but the
two label spaces do not match 1:1**. Comparing them naively makes a correct
normalizer look broken (e.g. `treatment_goals` scores ~0.15 raw Jaccard purely
because the LLM and the regex use different words for the same intent).

So the harness first **projects both sides into a shared canonical space**
(`taxonomy.py`), drops noise labels (`other`/`none`/`unknown`), and tracks gold
labels the normalizer *cannot emit by design* as a **coverage gap** instead of
counting them as errors.

> ⚠️ **The gold labels are LLM-generated (deepseek) — a _silver_ standard, not
> verified ground truth.** Use this for agreement / regression tracking. For a
> true accuracy figure, hand-verify a subset of `testset.jsonl` first.

## Files

| file | role |
|---|---|
| `taxonomy.py` | canonical label maps + coverage-gap sets (edit this to refine alignment) |
| `build_testset.py` | samples a stratified, seeded test-set from the finetune data |
| `evaluate.py` | runs the normalizer, computes metrics, writes reports |
| `testset.jsonl` | generated test-set (raw + gold + metadata) |
| `reports/` | generated `report.json`, `report.md`, `per_sample.csv`, `worst_cases.jsonl` |

## Run

```bash
# 1) build a 1000-sample stratified test-set (by severity + case_type)
python scripts/eval/normalizer/build_testset.py --n 1000 --seed 42

# 2) evaluate + dump the 40 worst cases for manual review
python scripts/eval/normalizer/evaluate.py --worst 40
```

Requires `pydantic` + `loguru` (already in the project env).

## Metrics

**Multi-label fields** (lesions, distribution, goals, hormonal, red_flags, meds)

- micro **Precision / Recall / F1** — token-level, aggregated over all samples
- **macro-F1** — unweighted mean over labels (surfaces rare-label weakness)
- **mean Jaccard** — per-sample set overlap
- **exact-match rate** — whole set identical
- **weakest labels** — per-label recall + support, to find what to fix
- **coverage gap** — count of gold labels outside the normalizer's vocabulary

Lesions are reported twice: `lesion_strict` (subtype-sensitive) and
`lesion_bucket` (clinical family: comedonal / inflammatory / nodulocystic).

**Scalar fields** (inflammation, sex, skin_type, is_pregnant, is_breastfeeding)

- **accuracy** on samples where gold carries signal
- **confusion matrix** (direction of errors — e.g. moderate↔severe matters more
  than moderate↔mild)

## How to read the results

A **high coverage-gap** number means the low score is mostly *taxonomy
divergence*, not a normalizer defect — fix it by extending `taxonomy.py` (add a
mapping) or accept it as an intentional vocabulary difference. A **low score
with zero coverage gap** (e.g. medications recall, lesion subtypes) is a real
extraction weakness worth patching in `normalizer.py`.

## First-run snapshot (n=1000, seed=42)

| field | micro-F1 | note |
|---|---|---|
| distribution | **0.96** | strong |
| lesion_bucket | **0.86** | strong at family level |
| lesion_strict | 0.75 | comedone-subtype confusion |
| hormonal_factors | 0.66 | ok |
| treatment_goals | 0.52 | 563/938 have coverage gap → taxonomy, not error |
| medications | 0.43 | high precision, **recall 0.30** → real miss |
| red_flags | 0.22 | 327 coverage gap → different taxonomy |

| scalar | accuracy | note |
|---|---|---|
| is_breastfeeding | 0.998 | strong |
| is_pregnant | 0.986 | strong |
| skin_type | 0.748 | good |
| inflammation | 0.539 | over-calls `none`→`moderate`, `moderate`→`severe` |
| sex | 0.006 | **normalizer does not infer gender** from `chị/em`/menstrual cues |

Two genuine, actionable findings the harness surfaces:

1. **Medication recall (0.30)** and **lesion subtypes** — real extraction gaps
   in `normalizer.py` (zero coverage gap, so not a taxonomy artifact).
2. **`sex` ≈ 0 and inflammation over-calling** — behavioral choices: the regex
   normalizer never infers `female` (gold does, aggressively), and it tends to
   read inflammation where gold labels `none`. Decide whether to align the
   normalizer or the label taxonomy.
