# AcneLLM defense fact-check ledger — 2026-08-25

This ledger refreshes the evidence boundary for the thesis-defense narrative.
It does not rewrite the frozen 2026-08-22 audit or the 2026-08-23 slide ledger.

## Source state

- Branch: `codex/simplify-chat-pipeline`.
- HEAD: `487a7f614e628b804e693992060465fe54275e37`.
- Current immutable capture: `runs/20260825T090826Z/`.
- Scope: 837/837 paths = 833 tracked + 4 non-ignored untracked outside
  `.audit/`.
- Disposition: 589 semantic captures, 205 explicit skips and 42 explicit
  `.audit/**` exclusions to prevent self-recursion.
- Dynamic gate: 590/590 snapshots, 0 SHA-256 mismatches, 590 finding sections,
  10,335 audited blocks, 82,680/82,680 filled items, 0 non-notebook parse errors.
- Worktree is dirty. The snapshot records `commit_push.ps1` and two files under
  `research/evaluation/reports/calibration_rrr/_to_delete/` as untracked. It also
  records the modified Chroma/Judge SQLite artifacts and
  `research/dataset_viz/README.md`; none may be silently presented as a clean
  release state.

The dynamic gate proves static capture completeness for this checkout. It does
not prove dynamic reachability, model readiness, endpoint parity or medical
correctness.

## Verified current code truth

- `src/acne_llm/di.py::build_container` creates one `UnifiedIntake`; the
  `llm_router` and `llm_extractor` interfaces share that instance.
- Intake order is current-turn preparation and deterministic safety checks,
  Unified Intaker, then SemanticRouter and rule-based fallback on failure.
- Runtime reply path is FastAPI `/api/v1/chat/stream` -> `run_intake` ->
  `prepare_chat_turn` -> hybrid retrieval/prompt -> generator stream -> output
  safety -> SQLite persistence/audit.
- Retrieval uses Chroma dense search plus BM25, reciprocal-rank fusion, source
  passes, BGE reranking and final chunk filters; zero context is valid.
- `Settings.llm_model`, Compose, Ollama init and example env files default to
  `acne-generator-v2`; `Settings.intake_timeout` and deploy defaults are 120 s.
- Current test rerun on the repository venv: `495 passed, 1 xfailed in 53.86s`
  on 2026-08-25.
- Real SSE smoke on the current packaged models was not run. Unit/integration
  tests therefore do not close the T4/runtime-parity claim.

## Verified data and model artifacts

| Claim | Current value | Evidence |
|---|---:|---|
| Raw knowledge documents | 6,835 unique `doc_id` | `data/raw/documents.jsonl` |
| Documents above default quality threshold | 6,796 | `quality_score >= 0.3` |
| Final chunks | 24,393 unique `chunk_id` | `data/raw/chunks.jsonl` |
| Chroma collection | 24,393 | live read of `data/chroma_db` with repo venv |
| BM25 records | 24,393 ids + 24,393 texts | `data/bm25_index.pkl` |
| Intaker corpus | 4,000 | 3,600 train + 400 validation |
| Intaker provenance | 836 `golden_relabel` + 3,164 GPT-4o-mini | final records |
| Generator-v2 accepted corpus | 3,077 | 2,616 train + 246 validation + 215 holdout |
| Intaker GGUF | 1,929,902,592 bytes | SHA-256 `5c4e13d4...8c58315` |
| Generator-v2 GGUF | 4,683,073,568 bytes | SHA-256 `71731a27...b69e7` |

`golden_relabel` is a Python schema conversion of historically LLM-generated
labels, not a fresh LLM call and not physician-verified gold data. Generator-v2
has a usable training corpus but did not reach the 3,500 target.

## Historical evaluation that remains citable with its boundary

`research/evaluation/reports/v2_full` completed intake, retrieval and ablation
on 2026-08-22. It was not rerun after remediation; cite it as a frozen protocol
artifact, not as a new current-runtime benchmark.

- Intake: 1,490 single-turn cases; schema-valid 0.9812; intent accuracy 0.9570;
  macro-F1 0.7405; extraction micro-F1 0.6131; inflammation F1 0.2126;
  hallucinated-field rate 0.0820.
- Retrieval: 120 cases; 29 no-context; relevance 2.5919/5; precision 0.5344;
  sufficiency 2.8462/5; ranking quality 0.9365.
- Ablation: 145 questions x 6 arms. RRR answer quality 2.7793/5.
  RRO vs RRR +0.7248, 95% CI [0.5688, 0.8807]; ROR vs RRR +0.4118,
  [0.2353, 0.5882]; RNR vs RRR +0.0185, [-0.0833, 0.1204]; ORR vs RRR
  -0.0194, [-0.1165, 0.0777].
- Raw safety-failure counts include RRR 32, ORR 24 and RRO 16.

The strongest supported interpretation is that the local generator is the
largest observed answer-quality bottleneck, real retrieval underuses the value
available from better context, and intake contributes to safety routing more
than to prose quality. The design does not establish universal causality.

## Human calibration boundary

The 2026-08-24 calibration covers all 145 RRR rows with one non-clinician
rater. Quadratic kappa is 0.5338 for answer quality, 0.5663 for incorrect
content, 0.4099 for missing content and 0.3188 for role/tone; all are below the
repository bar of 0.61. Judge safety precision is 0.50 for harmful incorrect
content and 0.4211 for forbidden claims.

Therefore judge scores are useful as a directional cross-arm signal, not a
clinically validated absolute scale. No inter-rater agreement, dermatologist
review, human paired arm delta or human calibration of the five context axes is
available.

## Claims allowed in the defense

- AcneLLM is an end-to-end, local-first research prototype with traceable data,
  model, runtime and evaluation artifacts.
- The architecture separates structured intake, retrieval, generation and
  safety so bottlenecks can be measured independently.
- Current evidence locates engineering bottlenecks and supports a reproducible
  prototype claim.

## Claims not allowed

- Production-ready, clinically safe, medically correct, diagnostic or
  prescriptive system.
- Fine-tuning effectiveness versus the base model; no base-model control exists.
- Current T4/SSE parity inferred from T3 ablation or pytest.
- RAG is useless; the observed result is that current real retrieval is weak
  while oracle context improves quality.
- The 4,000 Intaker rows are all directly generated or medically gold-labeled.

## Current presentation artifacts

- Current 16-slide defense deck requested on 2026-08-25:
  `docs/presentations/AcneLLM_Defense_16slides_E2E_20260825.pptx`.
- 16-slide deck SHA-256:
  `AE5D0893EBE8E9A6BF4BBA0AE42392722B5B8DE58BA2AF09E63121971650E077`.
- Slide-by-slide context:
  `docs/presentations/AcneLLM_Defense_16slides_CONTEXT.md`.
- Context SHA-256:
  `CB6C6D541D2048E7A8C2A575AF92319B562E87535C9EE4C339C00812A1831FDF`.
- On-disk verification: 16 slides, 16 speaker-note sections, 16/16
  `[Sources]` blocks, 16/16 `[Context nói]` blocks and `slides_test.py` PASS
  with no overflow.

- Reviewed deck: `docs/presentations/AcneLLM_KhoaLuan_20min_DaDuyet.pptx`.
- Deck SHA-256: `3D98187C97EA2102969007BB1C37E92DCB3FEF41A9F17907B80E92237E7B21FE`.
- Script: `docs/presentations/AcneLLM_KhoaLuan_20min_DaDuyet_SPEAKER_SCRIPT.md`.
- Script SHA-256: `82148C0B1ADD5D5C6138BC3DA47D1D65050D8BFD35565B6A7F6BBE67C5DD136C`.
- Current structure: 22 main slides + 2 appendix slides.

The expanded 22-slide alternative remains in
`docs/presentations/AcneLLM_Defense_E2E_Context_2026-08-25.md`. The current
compact delivery follows the user's explicit 16-slide structure; it does not
replace or mutate the older reviewed 24-slide deck.
