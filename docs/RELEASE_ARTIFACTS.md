# AcneLLM release artifact index

This page maps the Git source tree to the large, reproducibility-critical artifacts that are intentionally published as GitHub Release assets instead of ordinary Git blobs.

## Source and evaluation evidence

- Branch: [`codex/simplify-chat-pipeline`](https://github.com/phkgn/AcneLLM/tree/codex/simplify-chat-pipeline)
- Runtime remediation commit: `0d9d9dd`
- Architecture/audit knowledge commit: `d9ece72`
- Verified `v2_full` evaluation evidence commit: `96e9f09`
- Verification at publication: `495 passed, 1 xfailed`

The tracked `research/evaluation/reports/v2_full/` directory is the canonical final evaluation report set. Its conclusions remain bounded by the provenance and calibration limitations recorded in those reports; publication is not a medical-readiness claim.

## Knowledge and audit snapshot

Release: [`knowledge-2026-08-23`](https://github.com/phkgn/AcneLLM/releases/tag/knowledge-2026-08-23)

- `audit-run-20260822T152307Z.zip`: complete evidence-bearing audit run.
- `AcneLLMKnowledge-20260823.zip`: generated Obsidian vault handoff.
- `SHA256SUMS-knowledge-2026-08-23.txt`: archive integrity hashes.

## Runtime knowledge base snapshot

Release: [`kb-v2-2026-08-23`](https://github.com/phkgn/AcneLLM/releases/tag/kb-v2-2026-08-23)

- 6,835 source documents.
- 24,393 chunks.
- 24,393 BM25 records.
- 24,393 Chroma records.
- `kb-v2-MANIFEST.json` records byte size and SHA-256 for every payload.

The Chroma database is published as an exact runtime snapshot. It is not committed as immutable source because SQLite metadata may change when the live store is opened.

## Canonical model artifacts

Release: [`models-v2-2026-08-23`](https://github.com/phkgn/AcneLLM/releases/tag/models-v2-2026-08-23)

- Unified Intaker: canonical 3B Q4 GGUF, final LoRA bundle, Ollama Modelfiles and manifest.
- Answer Generator: canonical 7B Q4 GGUF split into three GitHub-compatible parts, final root LoRA adapter, tokenizer, prompts and Modelfile.
- `MODELS-v2-MANIFEST.json` records the hash of every weight or part and the expected hash of the reassembled Generator GGUF.
- `README-model-release.txt` contains the PowerShell reassembly command.

Intermediate checkpoints, optimizer/RNG state, duplicate base-model GGUF files and `model/legacy/` research archives are excluded from the canonical runtime release. They are not required to reproduce current inference behavior.

## Restore order

1. Clone the source branch.
2. Download and verify the model release; reassemble the Generator GGUF.
3. Download and verify the KB release; restore its `data/` paths.
4. Optionally import the Obsidian vault for navigable project knowledge.
5. Run the repository tests and the evaluation commands documented in the tracked reports before treating a restored environment as equivalent.
