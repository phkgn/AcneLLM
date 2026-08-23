# AcneLLM Runtime Architecture Truth

Verified against the active source on 2026-08-23. Historical reports and
`model/legacy/**` are evidence/archive, not startup configuration.

## Normal request path

1. `api/routes/chat.py` delegates streaming work to `chat/runtime.py`.
2. `chat/intake.py::run_intake` preprocesses the current turn, loads SQLite
   history, runs hard input checks, then calls the Unified Intaker.
3. `di.py::build_container` creates exactly one `UnifiedIntake`. The temporary
   compatibility attributes `llm_router` and `llm_extractor` point to that same
   object, so a successful advise/knowledge turn reuses one cached inference.
4. `chat/orchestrator.py::prepare_chat_turn` selects retrieval and prompt
   template from the intake result.
5. `chat/runtime.py::stream_chat` streams generator tokens, applies output
   safety normalization, and persists user/assistant turns to SQLite.

## Intake failure chain

The fixed chain is:

```text
Unified Intaker (one LLM)
  -> SemanticRouter (local embeddings, no LLM)
  -> rule router + rule extractor (deterministic, no LLM)
```

Model transport, JSON, or intent failure causes routing to continue at the
semantic tier. A semantic/rule route does not retry a second intake LLM for
extraction; it uses the rule extractor. `model/legacy/**` is not imported by
startup or active runtime.

Runtime configuration exposes only `INTAKE_MODEL` and `INTAKE_TIMEOUT` for
intake. There is no intake mode and no dedicated router/extractor model config.

## Safety responsibilities

- `guardrails/runner.py`: hard input checks, including the medication policy.
- `chat/routing/intent_router.py::compute_route_flags`: text-derived flags used
  by prompt and output handling; this is not a refusal gate.
- `chat/_safety.py::get_safety_suffix`: output-side dose/self-use and other final
  safety normalization.
- Semantic and rule routing are availability fallbacks, not safety authorities.

The removed product-ingredient metadata flag had no behavioral consumer. Medication
safety remains governed by its dedicated input policy and output checks.

## Metadata contract

`RouteDecision.metadata()` keeps two separate facts:

- `primary_intent`: `advise`, `knowledge`, `clarify`, or `reject`.
- `turn_type`: the actual turn type, normally `answer`.

Semantic `confidence` currently carries clipped `nearest_similarity`. It is a
ranking diagnostic, not a calibrated probability.

## Retrieval and generation

`chat/_retrieval.py` builds the query and coordinates hybrid retrieval,
guideline/safety passes, reranking, and chunk filtering. `llm/prompt_builder.py`
builds the selected prompt. The answer generator is separate from the Intaker.

## Session persistence

Production DI always wires `db/session_store.py::SQLiteSessionStore`.
In-memory `SessionStore` lives only under `tests/helpers` and is not exported by
`acne_llm.chat.session`.

## Evaluation boundary

Existing evaluation artifacts remain valid as historical baseline evidence and
for the prior successful Unified path. This remediation does not claim a fresh
full evaluation. Changes listed in `.audit/FUTURE_BEHAVIOR_ROADMAP.md` require
the named intake, retrieval, generator, session, or real-SSE reruns.
