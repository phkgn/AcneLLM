# Runtime production vs evaluation

- Run: `E:\project\AcneLLM\evaluation\reports\main_2x2_t3`
- Tier artifact: `t3`
- Dataset: `E:\project\AcneLLM\evaluation\datasets\v1\d1_dev_seed.jsonl`
- T4 artifact present in this run: **no**

| Stage | Production SSE | T4 adapter | T3 batch | Interpretation |
|---|---|---|---|---|
| Request/session | `GET /api/v1/chat/stream`, caller session | same HTTP route; unique eval session per case | no HTTP/session | Only T4 observes API and session behavior. |
| Preprocess/normalize | `prepare_user_text` + `normalize_chat_message` | same through API | same functions through `adapters/_repo.py` | T1/T3 can diagnose extraction but not API behavior. |
| Guardrails/routing | `pre_check` + rule router + reject/clarify forks | same through API | bypassed by `pipeline/hybrid.py` / `llm_only.py` | Router and guardrail conclusions require T4/T1, not T3. |
| Retrieval | production chat top-k/settings | same server path when mode=hybrid | batch config top-15 then rerank top-5 | Retrieval depth is a known T3/T4 difference. |
| Prompt | intent-aware prose templates, chiefly `stream_user.j2` | same production templates | `llm_only_user.j2` / `hybrid_user.j2` JSON contract | T3 format/content quality cannot be presented as user-visible production output. |
| Generation/output | `stream_text`, prose + `[N]` | same SSE token stream | `generate_json`, `AdviseOutput` | T4 is the primary reality check. |
| Trace | server SSE events + debug trace when queried | adapter stores route/citation/session | adapter stores normalized input, output and retrieval context | Missing trace fields invalidate layer attribution. |

## Effective production snapshot

```json
{
  "model": "acnellm-v2-q4:latest",
  "sampling": {
    "temperature": 0.35,
    "top_p": 0.85,
    "top_k": 40,
    "repeat_penalty": 1.1,
    "num_ctx": 3072,
    "num_predict": 1200
  },
  "retrieval": {
    "retrieve_top_k": 6,
    "rerank_top_k": 3,
    "max_context_chars": 6000,
    "require_citations": true
  }
}
```

## Current interpretation

**No T4 result is present.** This run can validate T3 batch plumbing and relative S0-S4 diagnostics, but it cannot establish production chat quality.

## Confirmed differences / warnings

- T3 batch retrieval depth differs from production SSE; T3 cannot be presented as production behavior. Evidence: `['src/acne_llm/config.py', 'evaluation/configs/systems/s3.yaml', 'evaluation/adapters/ollama_batch.py', 'evaluation/adapters/sse_api.py']`

## Runtime validity failures

- S3 model differs from the effective production model. Evidence: `['src/acne_llm/config.py', 'evaluation/configs/systems/s3.yaml']`
