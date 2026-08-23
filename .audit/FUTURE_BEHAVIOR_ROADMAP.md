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

## 6. Session and data contracts

Define snapshot policy, history window, TTL/version handling, audit fields, and schema cleanup before changing persistence behavior.

Required validation: multi-turn, session isolation, restart/persistence, migration, concurrency, and history-window tests.
