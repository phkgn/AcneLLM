# Dashboard E2E QA — 2026-07-16 23:29:38

## Scope

- Branch: `codex/simplify-chat-pipeline`
- Dashboard: `evaluation/dashboard/`, port 3100
- Flow: 12 bước trong `docs/DASHBOARD_E2E_QA_PROMPT.md`
- Dataset/model quality issues are recorded as known issues, not fixed in this QA.

## Step log — discovery and targeted reruns

| # | Step | Before fix | After fix | Duration | Evidence |
|---:|---|---|---|---:|---|
| 1 | Preflight | FAIL | PASS | 84s | Fresh `run.ps1`; `/`, `/api/status`, Ollama `/api/tags`; count now 19/19 |
| 2 | Tests | PASS | PASS | 2.04s | Job `mrnq9bxv-6de369a0`; SSE `step02-tests.sse.log`; discovery run 61 passed; final suite 65 passed |
| 3 | T1 intent, limit 1 | PASS | PASS | 1.98s | Job `mrnqa1yo-7efa4260`; report/API timestamp changed; `n=1` |
| 4 | T2 sparse retrieval, limit 1 | PASS | PASS | 68.59s | Job `mrnqag9p-4c8ab116`; live SSE; warning present; latest summary `2026-07-16T163418` |
| 5 | T3 S1, one case | FAIL | PASS | 59.86s | Job `mrnqon26-e5f4dedc`; isolated argv, progress `0/1 → 1/1`, ETA `0 ms`; `step05-t3-s1.log` |
| 6 | Kill T3 S0 | PASS | PASS | 56.19s | Job `mrnqr5r4-4556d823`; kill API 3.09s; parent PID 26732 + child Python 6092 + conhost 4328 all dead; no zombie |
| 7 | Judge, limit 1 | PASS | PASS | 3.11s | Job `mrnqsxrb-5e668baf`; `s1.judged.jsonl`; 1 call, estimated cost `$0.00`; `step07-judge.log` |
| 8 | Report | PASS | PASS | 0.28s | Job `mrnqtj8p-7d797524`; `/results?experiment=qa_1case` HTTP 200; S1 `n_attempted=1`, buckets `1/0/0/0/139` |
| 9 | Inspect | PASS | PASS | 2.54s | `/api/inspect`: 1 S1 row with answer, structured, full trace and valid judge; `/inspect` HTTP 200; S0 diff absent because kill occurred before result append |
| 10 | Gate + validation | FAIL | PASS | gate 0.17s; validation 38.46s | Final jobs `mrns0wyk-ff7e936c` and `mrns0xgt-48e85c56`; artifact/API show 10 pass/17 fail/0 missing, `NOT_TRUSTWORTHY`, calibration banner, and no false prompt/config drift |
| 11 | Refresh during running job | PASS | PASS | 45.56s | Job `mrnr3se3-42e3b827`; `/runs?job=...` HTTP 200; registry stayed running; SSE before/after refresh advanced from model init to Chroma/embedder/reranker; then killed cleanly |
| 12 | Path traversal | FAIL | PASS | 0.8s | Both raw and percent-encoded traversal return HTTP 403 with safe JSON; valid in-scope file still returns 200 |

## Defect log

| Step | Expected | Actual | Evidence | Class | Root cause | Fix | Regression test | Commit |
|---:|---|---|---|---|---|---|---|---|
| 1 | Ollama count displayed by dashboard matches `/api/tags` model records | UI/API detail said `35 model tags`; Ollama returned 19 records | `/api/status`, Ollama `/api/tags` | DASHBOARD_BUG | Status route counted both raw names and stripped aliases in the same `Set` | Keep alias lookup for readiness but display raw record count | `dashboard/tests/status.test.ts` | `0d549e3` |
| 5 | T3 command honors isolated output directory and explicit resume setting | API ignored `outDir=qa_1case` and `resume=false`; command forced main run plus `--resume` | Job `mrnqcio4-2ccb2a61` command/normalized args | DASHBOARD_BUG | Command builder exposed neither output directory nor resume boolean and hardcoded `--resume` | Added typed output directory, resume control, downstream run-dir selection and progress routing | `dashboard/tests/commands.test.ts`; live job `mrnqon26-e5f4dedc` | `abfb11c` |
| 5 | Resume must reject a run directory created from a different dataset/config | Existing D1 run accepted current D2 experiment and appended `d2-0001` | `main_2x2_t3/s1.results.jsonl`, `run_meta.json` | HARNESS_BUG | `run_experiment` overwrote `run_meta.json` before checking existing metadata compatibility | Validate immutable hashes before capture/write; reject non-resume reuse; merge compatible multi-system metadata | 3 resume-state tests; real D1/D2 mismatch rejected before write | `33e3945` |
| 10 | `/runs` can launch documented `check_gate` on the selected run | API returned HTTP 400: `CommandId không nằm trong whitelist.` | Dashboard POST `/api/jobs`; harness `check_gate --help` succeeds | DASHBOARD_BUG | TypeScript command catalog omitted `check_gate` even though it is in `docs/EVAL_DASHBOARD_PROMPT.md` | Added typed command catalog entry, run-dir field and harness argv | Whitelist/flag regression test; live job produced `gate_check.json` | `f8638ac` |
| 10 | `/results` warns when judge calibration is missing or failing | `judge_bias_tests.json` is missing, but no calibration banner rendered and `/api/meta` exposed no state | Missing artifact; `/results` HTTP 200; `/api/meta` | DASHBOARD_BUG | Results UI never loaded or interpreted `judge_bias_tests.json` despite the documented acceptance rule | Parse calibration artifact in `/api/meta`; render warning when missing/failed | 3 calibration-state tests; Edge headless rendered expected banner | `4c0fb3d` |
| 10 | Gate badges use `gate_check.json` as their only source of truth | Clean harness run reported 2/13 before validation and artifact later contained 10/27, while `/api/results` independently returned 2 pass/7 fail/4 missing | Gate job log, `gate_check.json`, `/api/results` | DASHBOARD_BUG | `lib/gates.ts` reimplemented thresholds and artifact discovery instead of normalizing the harness output | Removed dashboard threshold evaluation; normalize only the harness artifact | `dashboard/tests/gates.test.ts`; final artifact/API both 10/17/0 | `e265039` |
| 10 | Versioning validates hashes for systems that actually produced result artifacts in a partial run | Clean S1 run also recorded a killed S0 attempt, while validation compared its metadata with all experiment systems and reported false prompt/config drift | `qa_clean_1case/run_meta.json`; validation `20260716T171017Z` | HARNESS_BUG | `check_versioning` exact-compared system-specific hashes against the complete S0–S4 runtime snapshot instead of scoping them to `*.results.jsonl` systems | Shared template/judge hashes remain exact; system prompt/config hashes are checked for completed systems only | `test_versioning_scopes_system_hashes_to_completed_partial_run`; validation `20260716T172208Z` now reports only missing MANIFEST | `ab05dff` |
| 12 | Traversal attempts return forbidden without revealing files | Both `../../.env` variants returned HTTP 400 with a safe error body | `curl --path-as-is` against `/api/files` | DASHBOARD_BUG | File route mapped path-policy exceptions to the same generic 400 branch as malformed non-security input | Added typed path-access error and explicit 403 mapping; retained 404/400 for other failures | 2 path tests; both live payloads 403; valid file 200 | `d41cb1e` |

Step 5 cleanup: removed only the accidental `d2-0001` append and restored the prior D1 `run_meta.json`; the old result file is back to 10 rows.

## Final clean rerun

| # | Result | Final evidence | Duration |
|---:|---|---|---:|
| 1 | PASS | Fresh server; `/api/status` is ready with 10/10 checks; dashboard and Ollama both report 19 model records | 84s |
| 2 | PASS | Dashboard job `mrnra8sz-1cb62648` streamed and exited 0; 64 tests at clean-run time | 1.34s |
| 3 | PASS | Job `mrnraet9-7e107580`; unit report timestamp changed; `n=1`, `intent_macro_f1=1` | 0.64s |
| 4 | PASS | Job `mrnrajqv-fe5c3a3a`; sparse summary `2026-07-16T170210`; `needs_relabel=1` warning present | 47.54s |
| 5 | PASS | Job `mrnrbx8z-0a260622`; isolated `qa_clean_1case`, explicit no-resume, progress 0→1/1; S1 row uses `acnellm-v2-q4`, no fallback | 91.88s |
| 6 | PASS | Job `mrnre5mf-c76241ab` became `killed`; Windows tree termination completed in 3.005s; no S0 result and no zombie Python process | 51.78s total |
| 7 | PASS | Job `mrnrfflp-4bfbe430`; one valid judged row written; cost log `$0.00` | 3.84s |
| 8 | PASS | Job `mrnrfr02-432585ab`; report has `n_attempted=1`, buckets `1/0/0/0/139`; `/results` renders | <1s |
| 9 | PASS | Final `/api/inspect` returns answer, structured payload, full S1 trace and valid pointwise judge scores; no S0 compare because Step 6 killed before append | <1s |
| 10 | PASS | Dashboard jobs `mrns0wyk-ff7e936c` and `mrns0xgt-48e85c56`; non-zero exits correctly surface gate/validation failure; latest validation `20260716T172208Z`; UI/API 10 pass/17 fail/0 missing | 38.63s |
| 11 | PASS | Job `mrnrmw4x-8baf48ad` remained running through page refresh; second SSE connection advanced through model/Chroma/embedder/reranker logs; then killed cleanly | 46.87s |
| 12 | PASS | Raw and percent-encoded traversal both return 403; valid `evaluation/reports/gate_check.json` returns 200 | 0.8s |

All 12 workflow steps pass at the mechanism level. Step 10 is a pass because the dashboard faithfully runs and displays an expected failing scientific verdict; the current metrics themselves are not green.

## Final verification

- `python -m pytest evaluation/tests -q`: **65 passed**.
- Dashboard tests: **10 passed**.
- Dashboard ESLint: pass with zero warnings.
- TypeScript `tsc --noEmit`: pass.
- Next.js production build: pass.
- Fresh development server is running at `http://127.0.0.1:3100`; final `/api/status` is ready.
- Branch remained `codex/simplify-chat-pipeline`; no new branch was created.
- No files under `src/**` and no datasets were modified by the fixes.

## Known issues

- `evaluation/datasets/v1/MANIFEST.json` is missing, so D2 and the other v1 datasets are not frozen.
- D1/D8 contain duplicate-label findings; D8 is still `needs_relabel`.
- Draft/seed rows are not fully human-approved; validation queues 40 targeted review cases.
- `judge_bias_tests.json` is missing, so the judge is not calibrated.
- Local Ollama generation can take tens of seconds per case.
- S1 is `llm_only`, so its trace correctly has no retrieval `context_chunks`; the full trace still renders `normalized_user`, `prepared_clean_text` and `advise_output`.
- The one-case run is smoke-level and underpowered; it cannot establish model quality.
- T3 batch retrieval differs from production SSE depth; no T4 production-SSE verdict was run.
- Gate/validation exit non-zero because current data freeze and judge calibration are not trustworthy; the dashboard correctly surfaces those verdicts without weakening checks.

## Final verdict

**Operational GO, scientific NO-GO.**

The dashboard and harness control path are ready to launch a full run: preflight, job whitelist, live logs, progress, kill, refresh persistence, judge/report/inspect, gate/validation rendering and path security all work end-to-end.

Do not use a full run yet for a trustworthy model decision. First freeze the datasets with `MANIFEST.json`, complete human review, add judge calibration, and run the T4 production-SSE tier. Until then, a full run is useful for exercising infrastructure and producing artifacts, not for claiming model quality or regression safety.
