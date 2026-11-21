# Future Behavior Roadmap

These tasks may change answers, parsing, retrieval, safety output, persistence, or evaluation comparability. They are intentionally excluded from the safe remediation run and must be implemented and evaluated independently.

## 1. T4 and SSE parity

Align temperature/seed, streaming, token limits, crisis prefix, safety suffix, and persistence. Preserve the existing T3 lane and add a separate SSE lane.

Required validation: paired T3 versus real SSE cases, stream assembly and cleanup, persisted final text, crisis-prefix and safety-suffix assertions.

## 2. Medication policy

Distinguish medication reported as current history from medication advice or requests. Keep the current medication guardrail until a labeled false-positive dataset supports a replacement.

Required validation: medication false-positive/false-negative dataset, safety review, routing and final-answer safety suites.

## 3. Intake and schema

Evaluate strict JSON, dropped-field telemetry, tri-state fields, clinical mapping, and confidence hedging. Any parser-affecting change is behavior change.

Required validation: rerun the 1,490-sample intake evaluation plus malformed, timeout, unknown-intent, and fallback-path tests.

## 4. Query and RAG

Evaluate accent normalization, negation-safe stopwords, BM25 invariants, score/boost semantics, Unicode headings, and cache invalidation.

Required validation: retrieval evaluation and every affected RAG ablation arm; include negation, paraphrase, multi-intent, and cache-version probes.

## 5. Generation and safety

Evaluate dose regex behavior, urgency rules, and final safety normalization.

Required validation: rerun T3 generator evaluation and a separate T4/SSE safety lane; do not infer production-stream readiness from T3 alone.

## 6. Human evaluation and judge trust

Partially done. Arm `RRR` was fully human-graded on 2026-08-24 (n = 145, one
rater); see `research/evaluation/reports/calibration_rrr/`. All four answer axes
sit below the repository's κ_quad ≥ 0.61 bar, and the two judge-derived safety
flags measured precision 0.50 and 0.42 against the human.

That round is closed at its declared scope — one arm, one rater, four answer
axes. The items below are stated limitations and the next development direction,
not outstanding work blocking the current evidence.

Direction: a second rater on the same sheet for inter-annotator agreement (the
existing `cham_RRR_145.html` is reused as-is); a dermatology professional
re-grading the same rows, which yields a different class of evidence — clinical
correctness — rather than a better version of this one; at least one comparison
arm (`RRO` recommended, pairwise blind) so a paired delta has human backing; and
calibration for the five context axes in `judges/context.py`, never human-checked.

State the measured number precisely: it is agreement between the judge and one
specific rater, not the judge's reliability in general. With a single rater κ is
a point estimate with no interval, and scale stability across people is unknown.

Required validation: report κ, quadratic κ, Gwet AC1 and within-one agreement
together — never κ alone on a single arm, where skewed marginals depress it.

## 7. Session and data contracts

Define snapshot policy, history window, TTL/version handling, audit fields, and schema cleanup before changing persistence behavior.

Required validation: multi-turn, session isolation, restart/persistence, migration, concurrency, and history-window tests.
