# AcneLLM configuration map

`Settings` currently contains **85 fields** (the brief's earlier count of 77 predates the unified-intake and semantic-router additions). The classification below covers every current field: **71 OPERATIONAL** values are explicit in `.env.baseline`; **14 STRUCTURAL/INTERNAL** values retain typed defaults in `config.py` and remain environment-overridable.

| Field | Class | Runtime group |
|---|---|---|
| `ollama_url` | OPERATIONAL | LLM answer (7B) |
| `llm_model` | OPERATIONAL | LLM answer (7B) |
| `llm_fallback_model` | OPERATIONAL | LLM answer (7B) |
| `llm_num_ctx` | OPERATIONAL | LLM answer (7B) |
| `llm_num_predict` | OPERATIONAL | LLM answer (7B) |
| `llm_temperature` | OPERATIONAL | LLM answer (7B) |
| `llm_top_p` | OPERATIONAL | LLM answer (7B) |
| `llm_top_k` | OPERATIONAL | LLM answer (7B) |
| `llm_repeat_penalty` | OPERATIONAL | LLM answer (7B) |
| `llm_repeat_last_n` | OPERATIONAL | LLM answer (7B) |
| `llm_keep_alive` | OPERATIONAL | LLM answer (7B) |
| `ollama_health_timeout` | OPERATIONAL | LLM answer (7B) |
| `ollama_generate_timeout` | OPERATIONAL | LLM answer (7B) |
| `llm_use_modelfile_system` | OPERATIONAL | LLM answer (7B) |
| `intake_mode` | OPERATIONAL | Unified intake (3B) |
| `intake_model` | OPERATIONAL | Unified intake (3B) |
| `intake_timeout` | OPERATIONAL | Unified intake (3B) |
| `extractor_mode` | OPERATIONAL | Legacy intake adapters |
| `extractor_model` | OPERATIONAL | Legacy intake adapters |
| `extractor_timeout` | OPERATIONAL | Legacy intake adapters |
| `router_mode` | OPERATIONAL | Legacy intake adapters |
| `router_model` | OPERATIONAL | Legacy intake adapters |
| `router_timeout` | OPERATIONAL | Legacy intake adapters |
| `embedding_model` | OPERATIONAL | Embedding / rerank |
| `embedding_model_multilingual` | OPERATIONAL | Embedding / rerank |
| `reranker_model` | OPERATIONAL | Embedding / rerank |
| `device` | OPERATIONAL | Embedding / rerank |
| `semantic_router_train_path` | STRUCTURAL/INTERNAL | Data/index path |
| `semantic_router_cache_path` | STRUCTURAL/INTERNAL | Data/index path |
| `semantic_router_k` | OPERATIONAL | Fallback router |
| `semantic_router_oos_distance_threshold` | OPERATIONAL | Fallback router |
| `semantic_router_ambiguity_margin` | OPERATIONAL | Fallback router |
| `chroma_dir` | STRUCTURAL/INTERNAL | Data/index path |
| `bm25_path` | STRUCTURAL/INTERNAL | Data/index path |
| `docs_jsonl` | STRUCTURAL/INTERNAL | Data path |
| `chunks_jsonl` | STRUCTURAL/INTERNAL | Data path |
| `finetune_jsonl` | STRUCTURAL/INTERNAL | Data path |
| `qa_finetune_jsonl` | STRUCTURAL/INTERNAL | Data path |
| `prompts_dir` | STRUCTURAL/INTERNAL | Prompt path |
| `guardrails_yaml` | STRUCTURAL/INTERNAL | Safety data path |
| `seed_sources` | STRUCTURAL/INTERNAL | Crawler data path |
| `guardrails_scope_mode` | OPERATIONAL | Safety / guardrails |
| `retrieve_top_k` | OPERATIONAL | RAG / retrieval |
| `rerank_top_k` | OPERATIONAL | RAG / retrieval |
| `chat_retrieve_top_k` | OPERATIONAL | RAG / retrieval |
| `chat_rerank_top_k` | OPERATIONAL | RAG / retrieval |
| `chat_rerank_top_k_clinical` | OPERATIONAL | RAG / retrieval |
| `retrieval_source_boosts` | OPERATIONAL | RAG / retrieval |
| `retrieval_trust_boosts` | OPERATIONAL | RAG / retrieval |
| `retrieval_authority_boost` | OPERATIONAL | RAG / retrieval |
| `chat_max_context_chars` | OPERATIONAL | RAG / retrieval |
| `chat_min_citation_score` | OPERATIONAL | RAG / retrieval |
| `inline_citation` | OPERATIONAL | RAG / retrieval |
| `chat_require_citations` | OPERATIONAL | RAG / retrieval, deprecated compatibility |
| `chat_safety_top_k` | OPERATIONAL | RAG / retrieval |
| `chat_rerank_ood_floor` | OPERATIONAL | RAG / retrieval |
| `chat_rerank_keep_floor` | OPERATIONAL | RAG / retrieval |
| `extract_fuzzy_accept` | OPERATIONAL | Intake confidence thresholds |
| `extract_fuzzy_review` | OPERATIONAL | Intake confidence thresholds |
| `extract_min_field_conf` | OPERATIONAL | Intake confidence thresholds |
| `extract_safety_accept` | OPERATIONAL | Intake confidence thresholds |
| `route_min_confidence` | OPERATIONAL | Intake confidence thresholds |
| `reranker_batch_size` | OPERATIONAL | Embedding / rerank |
| `reranker_cache_size` | OPERATIONAL | Embedding / rerank |
| `reranker_min_sigmoid` | OPERATIONAL | Embedding / rerank |
| `dense_max_distance` | OPERATIONAL | RAG / retrieval |
| `bm25_normalize` | OPERATIONAL | RAG / retrieval |
| `english_input_notice` | OPERATIONAL | RAG / retrieval |
| `cache_dir` | STRUCTURAL/INTERNAL | Cache path |
| `cache_size_gb` | OPERATIONAL | Cache / session |
| `session_ttl` | OPERATIONAL | Cache / session |
| `session_history_char_budget` | OPERATIONAL | Cache / session |
| `session_max_history_turns` | OPERATIONAL | Cache / session |
| `audit_db_path` | STRUCTURAL/INTERNAL | Database path |
| `session_db_path` | STRUCTURAL/INTERNAL | Database path |
| `log_level` | OPERATIONAL | Logging |
| `api_host` | OPERATIONAL | API server |
| `api_port` | OPERATIONAL | API server |
| `frontend_url` | OPERATIONAL | API server |
| `cors_origins` | OPERATIONAL | API server |
| `api_key` | OPERATIONAL | API server secret |
| `rate_limit_per_minute` | OPERATIONAL | API server |
| `metrics_enabled` | OPERATIONAL | API server |
| `crawl_concurrency` | OPERATIONAL | Crawler |
| `crawl_rate_per_sec` | OPERATIONAL | Crawler |

## Source-of-truth rules

- Change normal runtime tuning in `.env`; `.env.baseline` documents every supported OPERATIONAL key and its baseline value.
- Keep real secrets only in `.env`. The baseline contains empty placeholders.
- Change STRUCTURAL/INTERNAL defaults in `config.py` only when repository layout or data lineage changes. They can still be overridden by environment variables for exceptional deployments.
- `extractor_*` and `router_*` are retained for `INTAKE_MODE=legacy`; unified mode uses `intake_*`.
