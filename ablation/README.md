# `ablation/` — oracle-substitution eval

Replaces `evaluation/` with one question and one method.

**Question.** Which of the three modules — intaker, RAG, generator — is the
bottleneck, how accurate is each one on its own, and how much does each actually
move the final answer at runtime?

**Method.** Replace exactly one module with a perfect version, hold the other two
fixed, and measure what the final answer does. Repeat for every subset.

Nothing here imports `evaluation/`, and no existing dataset is reused. Only
`repo_adapter.py` touches the product code — 4 functions, 3 seams.

---

## The arm matrix

An arm is a 3-character code, one character per module:

| position | module | `R` (real) | `O` (oracle) | `N` (null, optional) |
|---|---|---|---|---|
| 0 | intaker | `run_intake` | `golden_intake` from the case | empty slots |
| 1 | RAG | `retrieve_for_chat` | `golden_context` from the case | no context |
| 2 | generator | product prompt + Ollama | frontier model on the same inputs | empty answer |

Default matrix = the full 2³ factorial over `{R,O}` — 8 arms:

| arm | name | what it answers |
|---|---|---|
| `RRR` | **baseline** | what ships today |
| `ORR` | perfect intaker | headroom in module 1 |
| `ROR` | perfect context | headroom in module 2 |
| `RRO` | perfect generator | headroom in module 3 |
| `OOR` `ORO` `ROO` | pairs | interactions |
| `OOO` | ceiling | total headroom; residual = what the *case set itself* limits |

The brief named `ORR`, `RRO`, `ROR`. The other four cost ~2× and buy exact
attribution instead of additive-by-assumption attribution — see §Shapley below.

Extra arms need no new code: `--arms RRR,NRR,RNR,RRN` adds the degrade arms.

---

## Why the extra arms (the answer to "nên thêm method nào nữa")

Six additions, in priority order. The first four are already implemented.

**1. Baseline arm `RRR`.** Not in the brief, but every delta is meaningless
without it. Implemented.

**2. Full 2³ + Shapley attribution.** Single-oracle deltas do not sum to the
total gap whenever modules interact — a perfect intaker is worth more once the
context is also perfect, so `Δ_intaker + Δ_rag + Δ_gen ≠ score(OOO) − score(RRR)`
and any "module X accounts for Y% of the gap" claim built on them is wrong.
Shapley values over the 8-arm lattice sum to the total gap *exactly*, by
construction. That identity is the sentence worth putting in a report.
Implemented (`report.py §2`), with the 2-way interaction contrasts in §3 —
near-zero interaction is itself a finding: the modules can be fixed
independently.

**3. Degrade arms (`N`).** Oracle substitution measures how much a module *could
still gain*; it cannot tell "this module is already perfect" from "this module is
irrelevant to the task" — both give Δ≈0. Degrading answers that. For the RAG
claim specifically, `RNR` (no context at all) vs `RRR` is the single most direct
evidence that retrieval contributes anything; `ROR` on its own can only say the
current index is imperfect. Implemented as arm codes, off by default.

**4. Observed error propagation.** All of the above measure *potential* on a
constructed case set. This measures *incidence* on the baseline run:
`P(fail | intaker missed a slot)` vs `P(fail | intaker exact)`. Costs zero extra
LLM calls — it is a regrouping of the `RRR` rows. A module with large headroom
but low incidence is a low-priority fix, and that distinction is exactly what
"mức độ ảnh hưởng trong runtime thực tế" means. Implemented (`report.py §5`),
alongside per-stage latency (§6) so the RAG argument can be stated as value per
millisecond.

**4b. Three models, three roles, no overlap.** The case author writes the rubric,
the oracle generator answers under it, the judge scores. Any two of those being
the same model biases a specific number, and each collision biases a different
one: `oracle == judge` is direct self-preference on answers (worst);
`case == oracle` means the oracle answers a rubric phrased in its own words
(inflates generator headroom); `case == judge` means the judge finds its own
evidence passages unusually supportive (inflates RAG headroom, mildest). The
oracle must also be a genuinely stronger tier than the local generator — an
efficiency-tier oracle makes `??O` not a ceiling, and the generator's headroom
reads low for the wrong reason. `frontier.roles()` reports any collision and
`judge.py` prints it on every run.

**5. Judge validation.** *Not implemented — do this before publishing numbers.*
The whole report rests on one LLM judge. Minimum bar: 30–50 answers double-scored
by a human, report Cohen's κ; and re-score a sample with the arm-ordering
shuffled to check position/verbosity bias. The judge here is already blind to the
arm and returns facts rather than a number (coverage/violation/unsupported-claim
counts aggregated in Python), which removes the worst of the drift, but not the
need for agreement evidence.

**6. Generator variance.** Temperature is pinned to 0.0, so a single sample per
cell is defensible. If you unpin it, run n≥3 per cell and report the within-cell
SD — otherwise a Δ of 0.02 is noise wearing a suit.

Deliberately *not* added: a 4th "query rewriter" module, per-arm human preference
ranking, and multi-turn arms. All three are real, all three double the matrix.
Add them when a single-turn number is no longer the thing in doubt.

---

## Metrics

Per answer, produced by a blind judge (`judge.py`):

| field | definition |
|---|---|
| `coverage` | fraction of `must_cover` rubric points present |
| `faithful` | 1 − unsupported claims / total claims, relative to *that arm's own context* |
| `violated` | any `must_not_say` claim present |
| `quality` | `0.7·coverage + 0.3·faithful` |
| `score` | `quality`, forced to 0 if `violated` — headline metric |

`score` gates on safety because for a medical assistant a contraindication error
is a failed answer, not a deduction. `quality` is reported next to it so the gate
is visible rather than baked in; `--metric quality` reruns the whole report
ungated if you want to argue about it.

Module-intrinsic, no judge needed:

- **intaker**: per-slot accuracy vs `golden_intake` (Jaccard for list slots,
  exact match for scalars), on the `RRR` arm. `report.py §4`.
- **RAG**: `retrieved_ids()` is exposed for recall@k once cases carry golden
  chunk ids. Not wired into the report — the current case format stores evidence
  as text, not ids.

All deltas use a **paired bootstrap over cases** (B=2000), because every arm runs
on the same cases and the per-case difference is far tighter than the difference
of two means. Unpaired CIs on this design overstate uncertainty by roughly 2–3×.

---

## Run it

```bash
# 0. self-checks (no API key, no Ollama, no Chroma)
PYTHONPATH=src python -c "from ablation import cases,repo_adapter,run,judge,report; \
  [m.demo() for m in (cases,repo_adapter,run,judge,report)]"

# 1. build the case set from scratch
export OPENAI_API_KEY=... DEEPSEEK_API_KEY=...
#   ABLATION_CASE_MODEL   = deepseek-v4-flash   writes cases + rubric
#   ABLATION_ORACLE_MODEL = deepseek-v4-pro     the `??O` arms — must be the strong tier
#   ABLATION_JUDGE_MODEL  = gpt-5.6-luna        different vendor, grades everything
python -m ablation.gen_cases --n 20 --seed 1 --source-dir guideline_docs \
       --out ablation/data/cases.dev.jsonl      # pilot: measure sigma_d first
python -m ablation.gen_cases --n 80 --seed 2 --source-dir guideline_docs \
       --out ablation/data/cases.test.jsonl

# 2. run the matrix (resumable — rerun after a crash, it skips finished cells)
python -m ablation.run --cases ablation/data/cases.jsonl --out ablation/runs/main.jsonl

# 3. judge, blind
python -m ablation.judge --run ablation/runs/main.jsonl

# 4. report
python -m ablation.report --run ablation/runs/main.judged.jsonl
```

Cost control: every frontier call is cached on disk by
`(model, system, user, json_mode)`, so re-running a stage is free. Per case the
matrix costs 2 intakes + 2 retrievals + 8 generations (not 8 of each) — arms
share memoised upstream stages inside `run_case`.

`--dry-run` executes only the arms with no `R` in them: useful for checking the
plumbing with an API key but no model server.

---

## Files

| file | lines-ish | job |
|---|---|---|
| `cases.py` | 130 | case schema, slot vocabulary, loader, slot scoring |
| `gen_cases.py` | 110 | regenerate the case set with the frontier model |
| `repo_adapter.py` | 190 | **the only file importing `acne_llm`** — 3 seams |
| `frontier.py` | 70 | one cached OpenAI call |
| `run.py` | 160 | arm matrix, memoised loop, resumable jsonl |
| `judge.py` | 110 | blind rubric judge → facts; scoring done in Python |
| `report.py` | 230 | bootstrap CIs, Shapley, interactions, propagation, cost |

Each has a `demo()` self-check runnable with no network and no product deps
beyond pydantic.

---

## Case set provenance

`golden_context` is the oracle for RAG. If it is invented by the model, the
`?O?` arms measure nothing real. `gen_cases.py --source-dir DIR` forces passages
to be quoted from files in `DIR` (point it at `guideline_docs/`); without it,
every case is tagged `needs_source_review` and the generator prints a warning.
**Do not publish a number from an unreviewed set.**

Seeds are a fixed product grid (profile × situation × writing style) rather than
free-form prompting, so coverage is auditable and `--seed` reproduces the set.

---

## Migration from `evaluation/`

What the old module did and where it lands:

| old | disposition |
|---|---|
| `runners/`, `full_evaluation.py`, `adapters/`, `configs/experiments` | **replaced** by `run.py` + arm codes |
| `judges/` (client, prompts, cache) | **replaced** by `judge.py` + `frontier.py` |
| `metrics/`, `analysis/report.py`, `analysis/stats.py` | **replaced** by `report.py` |
| `analysis/error_attribution.py` | **replaced and strengthened** — Shapley over the lattice instead of heuristic attribution |
| `datasets/` (registry, v1/, drafts) | **replaced** by `cases.py` + `gen_cases.py`; the v1 files are not migrated on purpose |
| `judges/calibrate.py`, `judges/bias_tests.py` | **no replacement yet** — this is item 5 above. Port or rewrite before publishing. |
| `runners/run_retrieval.py`, `metrics/retrieval.py` | **no replacement** — needs golden chunk ids in the case format. `retrieved_ids()` is the hook. |
| `dashboard/` (Next.js) | **out of scope** — reads the old report artifacts. Either repoint it at `runs/report.md` or drop it. |
| `validate/`, `probe/`, `modelfiles/`, `scripts/` | **unclassified** — these are not eval, they drifted in. Move them to `scripts/` or delete. |

Six repo scripts still import `evaluation`: `scripts/eval_bottleneck.py`,
`eval_semantic_router.py`, `eval_rag.py`, `eval_extraction.py`,
`eval_unified_intake.py`, `judge_agreement.py`. They break the moment
`evaluation/` is deleted.

**Nothing has been deleted.** Suggested order: run the new module on a real case
set, confirm the numbers are sane, port the judge-calibration piece, then delete
`evaluation/` and the five now-redundant `scripts/eval_*.py` in one commit.
