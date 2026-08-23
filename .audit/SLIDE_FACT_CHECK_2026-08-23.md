# AcneLLM slide fact-check ledger — 2026-08-23

This ledger freezes the evidence used by the verified 20-minute presentation. It is not a substitute for the source tree. Claims were accepted in this order: executable code and binary/data artifacts, machine-readable run outputs, then narrative documentation.

## Rules used in the deck

- A target is not reported as a completed corpus unless the final artifact and validation summary agree.
- Audit rows are events, not automatically unique examples.
- A notebook is training intent; `trainer_state.json`, adapter hashes, and exported GGUF files are training artifacts.
- Evaluation results are tied to their protocol model, dataset hash, and execution path. They are not silently generalized to the default deployment.
- T3/ablation generation results do not establish production streaming/SSE parity.

## Verified knowledge-base facts

| Claim used | Verified value | Primary evidence |
|---|---:|---|
| Raw documents | 6,835 unique `doc_id` rows | `data/raw/documents.jsonl` |
| Documents passing default quality threshold | 6,796 with `quality_score >= 0.3` | `data/raw/documents.jsonl`; `scripts/build_kb.py` |
| Final chunks | 24,393 unique `chunk_id` rows | `data/raw/chunks.jsonl` |
| Chroma vector count | 24,393, cosine space | live read of `data/chroma_db` with repository venv |
| BM25 item count | 24,393 `chunk_ids` and 24,393 texts | `data/bm25_index.pkl` |
| Default chunking | size 200, overlap 40, minimum 50 | `scripts/build_kb.py` |

The deck does not repeat an older reference to `src/acne_llm/rag/hybrid.py`; the active hybrid retrieval implementation is `src/acne_llm/rag/retriever.py`.

## Verified Intaker dataset funnel

| Stage | Verified value | Meaning / evidence |
|---|---:|---|
| Raw golden rows | 985 | `data/golden_extraction_gen.jsonl` |
| Final records | 4,000 | `research/datagen/intakedata/output/intake/intake.records.jsonl` |
| Final split | 3,600 train / 400 validation | split JSONL artifacts |
| Final provenance | 836 golden relabel / 3,164 GPT-4o-mini | final `summary.json` and records |
| Final intents | 2,000 advise / 800 knowledge / 700 clarify / 500 reject | final records and `summary.json` |
| Cumulative full-mode audit | 11,980 events | `audit.jsonl`; 4,149 accepts, 7,588 rejects, 239 errors, 4 summary events |
| Purged after earlier acceptance | 149 | 4,149 cumulative accepts minus 4,000 final rows; contamination purge code |
| Final exact evaluation overlap | 0 | final `summary.json` |

Therefore “4,000” means the final accepted corpus, not all candidates generated. The current completion run resumed at 3,995 and added five rows; its 214 rejected attempts are not the cumulative rejection count. Source behavior was checked in `research/datagen/intakedata/pipeline.py`, including evaluation-overlap rejection, bounded attempts, contamination purge, and deterministic 90/10 splitting.

## Verified Intaker training

- Base: `unsloth/Qwen2.5-3B-Instruct-bnb-4bit`; QLoRA rank 16, alpha 32, dropout 0.05; seven projection targets.
- Training intent: max sequence 2,048; batch 8; gradient accumulation 2; effective batch 16; 3 epochs; learning rate `2e-4`.
- Artifact state: 675 total steps; best checkpoint 600; best validation loss 0.030937865; final recorded train loss 0.043163213; runtime 1,160.7614 seconds.
- Export: `model/intaker/Qwen2.5-3B-Instruct.Q4_K_M.gguf`, 1,929,902,592 bytes, SHA-256 `5C4E13D45E53704032A5D98199312E4BD7E4840DC69D8B8F207C2D0AF8C58315`.
- Evidence: `research/notebooks/intaker/finetune_intake_qwen25_3b_q4.ipynb`, checkpoint states inside `model/intaker/qwen25_intake_lora.zip`, `model/intaker/MANIFEST.json`, GGUF hash.

## Verified Generator-v2 dataset funnel

| Stage | Verified value | Meaning / evidence |
|---|---:|---|
| Target | 3,500 | `research/datagen/roledatav2/config.py` |
| Phase-1 skeletons | 3,335 | `skeletons.jsonl` |
| Accepted role records | 3,077 | `roledata.train.jsonl` |
| Final grouped split | 2,616 train / 246 validation / 215 holdout | split artifacts and `finalize/split.py` |
| Rejected attempts in completion summary | 1,460 | `generation_summary.json`; attempt events, not unique examples |
| Cumulative rejection audit | 3,707 rows / 1,431 unique IDs | `rejected.audit.jsonl` |
| Post-validation failures | 3 `anchor_pair_corpus` failures | `generation_summary.json` |
| Status | incomplete | target shortfall and three remaining gate failures |

Both recorded phase models are `deepseek-v4-flash`. The training corpus exists and was used, but the generation target was not completed. The deck never labels the 3,500 target as achieved.

## Verified Generator-v2 training and artifact drift

- Base: `unsloth/Qwen2.5-7B-Instruct-bnb-4bit`; QLoRA rank 16, alpha 32, dropout 0.05; seven projection targets.
- Current notebook declares max sequence 3,072, batch 1, gradient accumulation 16, learning rate `2e-4`, and 2 epochs.
- Saved trainer state instead records a 3-epoch / 492-step schedule, early stopping at step 450 (epoch 2.746), and best validation loss 0.7477048039 at checkpoint 300.
- The root adapter SHA matches checkpoint 300, not checkpoints 400 or 450. This is reported as notebook/artifact drift, not reconciled by assumption.
- Export evaluated by `v2_full`: `model/generator/acnellm-role-v2.Q4_K_M.gguf`, 4,683,073,568 bytes, SHA-256 `71731A279A82326E134BBA116B142E91BA41F3CA8E2DA4494E9F840FFC7B69E7`.
- Evidence: `research/notebooks/generatorv2/finetune_role_v2_qwen25_T4.ipynb`, `model/generator/qwen25_acne_role_v2_lora/`, adapter files, GGUF hash.

## Verified current runtime

- Dependency injection creates one `UnifiedIntake`; `llm_router` and `llm_extractor` reference the same instance.
- Unified Intake receives the current turn plus selected/compacted raw user/assistant history. Its root `description` preserves the current turn verbatim; the schema is a downstream data contract, not a clinical diagnosis.
- Normal intake order: input preparation, deterministic guardrails, medication gate, Unified Intaker, semantic then rule fallback, extraction reuse/rule fallback, post-extraction medication checks, session fold, normalized query.
- Retrieval: dense Chroma plus BM25, reciprocal-rank fusion, guideline/safety passes, BGE reranking, and at most five context chunks after floor/OOD/noise/source/score filters; zero context is possible.
- Generation: token streaming, optional crisis prefix, CJK stripping, sources, conditional safety suffix, SQLite persistence, audit event, completion event.
- Primary evidence: `src/acne_llm/di.py`, `src/acne_llm/chat/intake.py`, `src/acne_llm/chat/_retrieval.py`, `src/acne_llm/chat/runtime.py`, `src/acne_llm/config.py`.

## Verified `v2_full` evaluation

- Report root: `research/evaluation/reports/v2_full`; all preflight/intake/retrieval/ablation steps are `ok`; run interval 2026-08-21 20:14:49Z to 2026-08-22 09:56:47Z.
- Intaker: 1,490 evaluated single-turn cases from 1,500 rows; 10 multiturn rows excluded; 0 failures and 0 fallbacks; intent accuracy 0.9570; macro-F1 0.7405; extraction micro-F1 0.6131; schema-valid 0.9812; hallucinated-field rate 0.0820. The generated 1,500-row set contains 1,410 `advise` labels before exclusion and records `deepseek:deepseek-v4-pro` as generator.
- Retrieval: 120 cases, including 29 no-context cases; context relevance 2.5919/5; precision 0.5344; sufficiency 2.8462/5; ranking quality 0.9365. Relevance and sufficiency use 0–5 rubrics. Ranking quality is judge-derived nDCG over the final context, so it is a pipeline metric rather than an isolated BGE measurement.
- Ablation: 145 questions × 6 arms = 870 rows. Answer quality uses a 1–5 rubric. RRR local baseline is 2.7793/5. Paired effects versus RRR are: ROR +0.4118, 95% CI [0.2353, 0.5882], n=68; RRO +0.7248, [0.5688, 0.8807], n=109; RNO +0.8214, [0.6696, 0.9645], n=112; RNR +0.0185, [-0.0833, 0.1204], n=108; ORR -0.0194, [-0.1165, 0.0777], n=103. Paired quality excludes rows where either arm safety-failed.
- Raw safety-failure counts are RRR 32, ORR 24, RNR 26, ROR 18 among 100 successful rows, RRO 16, and RNO 13.
- All 145 Generator evaluation samples have `source_provenance=synthetic_deepseek`, `annotation_status=synthetic_pending_review`, and `generator_model=deepseek-v4-pro`.
- There is no base-Qwen control, so declining training loss does not by itself establish that fine-tuning improved answer quality.
- Protocol model: `acne-generator-v2`; frontier reference: `gpt-5.6-terra`; judge: `gpt-5.6-luna`.
- Primary evidence: machine-readable JSON/JSONL files beneath `research/evaluation/reports/v2_full` and the referenced evaluation datasets.

## Claims explicitly rejected or constrained

1. **Rejected:** “The Intaker data consists of 4,000 directly generated examples.” Correct: 4,000 is the final corpus after relabeling, synthesis, deduplication, evaluation-overlap control, and a 149-row purge.
2. **Rejected:** “Generator-v2 completed its 3,500-example target.” Correct: 3,077 accepted records, status incomplete.
3. **Rejected:** “3,707 is the current generator rejection count.” Correct: 3,707 is a cumulative audit-row count; the completion summary reports 1,460 rejected attempts.
4. **Rejected:** “The current notebook exactly reproduces the saved Generator-v2 adapter.” Correct: epoch configuration and saved state drift.
5. **Rejected:** “`acne-generator-v2` is the current default Compose model.” Correct: current config/Compose defaults to `acne-generator`, while `v2_full` evaluated `acne-generator-v2`; `docker/ollama-init.sh` builds the former from `Modelfile.full`.
6. **Constrained:** `v2_full` supports component-level conclusions under its recorded protocol. It does not establish production SSE/T4 parity, a direct `RRO − RNO` subtraction is not treated as a causal RAG effect, and synthetic pending-review data plus an uncalibrated LLM judge do not establish clinical readiness.

## Known provenance drift to retain as limitations

- The Intaker summary contains older path strings that omit the current `research/` prefix even though the artifacts are present under `research/datagen/...`.
- Generator-v2 notebook parameters differ from the saved trainer state, but the exported root adapter matches the selected best checkpoint 300; there is no checkpoint-selection mismatch.
- Default deployment model naming/artifact differs from the `v2_full` protocol model.

## Presentation artifact and QA

- Deck: `docs/presentations/AcneLLM_Project_E2E_20min_Scientific_Verified.pptx`
- Slide count: 22; every slide contains speaker notes and a `[Sources]` block.
- Visual QA: all 22 rendered slides inspected at full size after the final edit.
- Automated layout QA: `slides_test.py` passed with `No overflow detected`.
- SHA-256: `DDA6589AD20C1C472C0E87ECFAA860741136EBCA2889285F2A590FE300AED1F8`.
- Revision: the Intaker and Generator-v2 training plots now show numeric loss axes, step ticks, best-validation checkpoints, and final training loss labels.
- Revision: the version-truth slide removes the misleading causal arrows. It labels the v2 artifact as used by the evaluation protocol and explicitly marks the default runtime as not matching that protocol.
- Revision: the limitations slide now states explicitly that Generator-v2 was fine-tuned on 2,616 training samples; the remaining limitation is corpus completion (3,077/3,500) and three post-validation failures.
- Revision: the training-provenance limitation no longer claims a best-checkpoint mismatch. It states the verified facts: current notebook 2 epochs, artifact schedule 3 epochs, and exported adapter matching best checkpoint 300.
- Revision: retrieval and answer-quality scales are corrected to `/5`; the ablation slide includes ROR, paired sample sizes, confidence intervals, paired-filter semantics, and raw safety-failure counts.
- Revision: synthetic evaluation provenance, missing base-model control, and judge calibration are visible limitations.
- Revision: the medication-policy slide is reduced to three real checkpoints, and the runtime/retrieval slides state that context contains at most five chunks.
- Revision: the evaluation-boundary card now states plainly that T3 ablation scores direct non-stream generation and does not cover SSE transport, output safety suffix, SQLite persistence, or event-level processing.
- Final QA: 22/22 slide PNGs inspected; 22/22 notes XML files contain `[Sources]`; all 56 unique repository source paths referenced by the builder exist; `slides_test.py` reports no overflow.
