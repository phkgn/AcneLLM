# Safe Remediation Task Ledger

This ledger records the bounded remediation run approved on 2026-08-23. The existing audit patches are provenance only and are not applied as a bundle.

## Locked baseline

- Commit: `585333cc68d6e29b666337bdf366c99e00abc9b7`
- Branch: `codex/simplify-chat-pipeline`
- Pre-existing tracked changes outside this remediation unless named below: `.codex/config.toml`, `_to_delete/datasets_MANIFEST_cu.json`, `_to_delete/generated_v3_2_MANIFEST.json`, `data/chroma_db/chroma.sqlite3`, `research/evaluation/full_evaluation.py`, `research/evaluation/reports/judge_cache.sqlite`, and `tests/test_chat_stream.py`.
- Pre-existing untracked areas: `.audit/`, `evaluation/`, `guideline_docs/`, and `research/evaluation/reports/v2_full/`.
- Baseline excluding the broken dirty chat-stream test: `pytest -q --ignore=tests/test_chat_stream.py` -> `503 passed, 1 xfailed`.
- Collection blocker: stale `acne_llm.chat.fallback` import in the dirty `tests/test_chat_stream.py`.

### Preserved evaluation artifacts

| Artifact | SHA-256 |
|---|---|
| `research/evaluation/reports/run_full_v3_2/intake/report.json` | `e75680d5497f5bd6293497bd63a5550fce96cad0068bc7a69b1e5827b67af3de` |
| `research/evaluation/reports/run_full_v3_2/ablation/summary.json` | `dd6c491e2cae6823521c0dc8b6cee83c19b86b97c548c8919bbb7e40623b6d29` |
| `research/evaluation/reports/v2_full/intake/report.json` | `2b78c5c8e703dc171b61bfbe0ec04cd950c6386515e2cec4fbab74df9414432c` |
| `research/evaluation/reports/v2_full/ablation/summary.json` | `9ef9fe1ca5c03a08e5a925152459147aedcebde6742fbb79e656164aab628f90` |

These reports remain historical baselines. This remediation does not rewrite them and does not claim a new full evaluation.

## Provenance patches

- `.audit/patches/A-docs.patch`: **superseded; do not apply wholesale**.
- `.audit/patches/B-comments.patch`: **superseded; do not apply wholesale**.
- `.audit/patches/C-code.patch`: **superseded; behavior-changing; do not apply**.

Useful claims are re-verified against current source and applied as small patches only.

## Tasks

### Task 0 - baseline and test repair

- Status: complete
- Scope: this ledger, roadmap, and source-aligned repair of `tests/test_chat_stream.py`.
- Gate: full pytest collects; baseline behavior outside this file remains green.
- Result: `tests/test_chat_stream.py` is source-aligned and passes `24/24`.

### Task 1 - one runtime LLM Intaker

- Status: complete
- Scope: one `UnifiedIntake` instance, shared router/extractor interfaces, semantic then rule fallback, removal of active legacy intake settings/classes.
- Gate: unified success uses one inference; failure reaches semantic/rule; targeted settings/intake tests and full pytest pass.
- Files: `di.py`, `config.py`, `chat/intake.py`, `chat/unified_intake.py`,
  `chat/intake_contract.py`, `_intake_parse.py`, active env/Docker/docs/logging,
  architecture generator/artifact, and corresponding tests. Dedicated legacy
  router/extractor adapters and their adapter-only tests were removed.
- Result: intake/settings gate `65 passed`; one-instance integration and
  semantic/rule failure paths pass. `model/legacy/**` was not changed.

### Task 2 - truthful metadata and dead rule flag cleanup

- Status: complete
- Scope: correct `turn_type`, remove unused `product_safety_check`, retain nearest-similarity calculation and fold alias behavior.
- Gate: routing/safety probes remain green and normal-path decisions do not change except removal/correction of unused metadata.
- Files: `chat/routing/intent_router.py`, `chat/routing/semantic_router.py`,
  `chat/session/fold.py`, and routing tests.
- Result: metadata now keeps `turn_type="answer"`; unused product metadata flag
  is absent; semantic confidence calculation is unchanged.

### Task 3 - truthful comments, docs, and log names

- Status: complete
- Scope: comments/docstrings/docs/log labels only; regenerate `docs/ARCHITECTURE_TRUTH.md` from resulting runtime truth.
- Gate: no answer-path logic changes; related tests pass.
- Files: comments/docstrings in safety, retrieval, session, extraction, fuzzy
  and chunk filtering; `utils/logging.py`, crawler caller, active config docs,
  `docs/ARCHITECTURE_TRUTH.md`, and the regenerated draw.io source artifact.
- Result: API logs default to `runtime_*`; crawler explicitly retains `crawl_*`.

### Task 4 - test-only in-memory sessions

- Status: complete
- Scope: move `SessionStore/get_session_store` to test helpers; production keeps `SQLiteSessionStore` only.
- Gate: no production caller/export remains; session/intake/chat tests pass.
- Files: removed `chat/session/memory.py`; added `tests/helpers/session_store.py`
  and test-package exports; migrated tests to independent stores.
- Result: targeted combined gate `149 passed`; production import checks confirm
  neither `SessionStore` nor `get_session_store` is exported.

### Task 5 - completion gate

- Status: complete
- Scope: targeted tests, full `pytest -q`, compile/import checks, grep gates, artifact hashes, and final dirty-worktree drift report.
- Full evaluation: explicitly not run; behavior roadmap owns rerun requirements.
- Final full suite: `495 passed, 1 xfailed in 22.73s`.
- Compile/import: `compileall` passed; imports passed with `66` Settings fields.
- Grep: no active legacy intake class/import/config, no dead product flag, and
  semantic/rule fallback symbols remain present.
- Evaluation artifact SHA-256 values still match the locked baseline above.
- Drift: pre-existing dirty paths outside the named remediation scope retain
  the same status set; no commit was created. The only pre-existing dirty file
  intentionally edited was `tests/test_chat_stream.py`.
- Full evaluation: not run.
