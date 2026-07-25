# Config reference — 70 field / 15 env key

Reference này phản ánh `src/acne_llm/config.py` sau refactor. Giá trị trong
`.env` có thể override field tương ứng; bảng dưới ghi default trong code.

## LLM (14)

| Field | Default |
|---|---|
| `ollama_url` | `http://localhost:11434` |
| `llm_model` | `acnellm-role` |
| `llm_fallback_model` | `qwen2.5:3b` |
| `llm_num_ctx` | `3072` |
| `llm_num_predict` | `1200` |
| `llm_temperature` | `0.35` |
| `llm_top_p` | `0.85` |
| `llm_top_k` | `40` |
| `llm_repeat_penalty` | `1.1` |
| `llm_repeat_last_n` | `128` |
| `llm_keep_alive` | `-1` |
| `ollama_health_timeout` | `5.0` |
| `ollama_generate_timeout` | `30.0` |
| `llm_use_modelfile_system` | `True` |

## Intake (9)

| Field | Default | Vai trò |
|---|---|---|
| `intake_mode` | `unified` | `unified` hoặc arm `legacy`. |
| `intake_model` | `acne-intake` | Router + extractor hợp nhất. |
| `intake_timeout` | `60.0` | Timeout unified intake. |
| `extractor_mode` | `llm` | Legacy A/B. |
| `extractor_model` | `acne-extractor:1.5b` | Legacy A/B. |
| `extractor_timeout` | `20.0` | Legacy A/B. |
| `router_mode` | `llm` | Legacy generative/semantic A/B. |
| `router_model` | `acnellm-intent` | Legacy A/B. |
| `router_timeout` | `8.0` | Legacy A/B. |

## Embedding và semantic router (8)

| Field | Default |
|---|---|
| `embedding_model` | `AITeamVN/Vietnamese_Embedding` |
| `reranker_model` | `BAAI/bge-reranker-v2-m3` |
| `device` | `cpu` |
| `semantic_router_train_path` | `./data/intent_classify.train.jsonl` |
| `semantic_router_cache_path` | `./data/intent_router_index.npz` |
| `semantic_router_k` | `9` |
| `semantic_router_oos_distance_threshold` | `0.483609` |
| `semantic_router_ambiguity_margin` | `0.08` |

## Paths (9)

| Field | Default |
|---|---|
| `chroma_dir` | `./data/chroma_db` |
| `bm25_path` | `./data/bm25_index.pkl` |
| `docs_jsonl` | `./data/raw/documents.jsonl` |
| `chunks_jsonl` | `./data/raw/chunks.jsonl` |
| `finetune_jsonl` | `./data/finetune/llm_data.jsonl` |
| `qa_finetune_jsonl` | `./data/finetune/qa_finetuning.jsonl` |
| `prompts_dir` | `./config/prompts` |
| `guardrails_yaml` | `./config/guardrails.yaml` |
| `seed_sources` | `./data/seed_sources.yaml` |

## Guardrails, retrieval và ranking (13)

| Field | Default | Ghi chú |
|---|---|---|
| `guardrails_scope_mode` | `soft` | API legacy; semantic router sở hữu soft OOS live. |
| `rerank_top_k` | `3` | Non-chat caller. |
| `chat_retrieve_top_k` | `6` | Pool production và default eval. |
| `chat_rerank_top_k` | `3` | Chunk cuối vào prompt. |
| `chat_max_context_chars` | `6000` | Budget tài liệu. |
| `chat_safety_top_k` | `5` | Safety retrieval pass. |
| `chat_rerank_floor` | `0.58` | Floor chung, phải lớn hơn sigmoid random `0.50`. |
| `extract_min_field_conf` | `0.60` | Confidence field intake. |
| `route_min_confidence` | `0.55` | Dưới ngưỡng thì clarify. |
| `reranker_batch_size` | `16` | Batch cross-encoder. |
| `reranker_cache_size` | `2048` | Cache reranker. |
| `reranker_min_sigmoid` | `0.30` | Loại chunk yếu. |
| `dense_max_distance` | `0.60` | Config thắng; DI truyền vào retriever. |

Boost source/trust/authority không phải setting. Nguồn duy nhất là các hằng số
trong `src/acne_llm/rag/retriever.py`.

## Runtime storage, API, judge, crawler (17)

| Field | Default |
|---|---|
| `cache_dir` | `./data/cache` |
| `cache_size_gb` | `2.0` |
| `session_ttl` | `1800.0` |
| `audit_db_path` | `./data/audit.db` |
| `session_db_path` | `./data/sessions.db` |
| `log_level` | `INFO` |
| `api_host` | `0.0.0.0` |
| `api_port` | `8000` |
| `frontend_url` | `http://localhost:3000` |
| `cors_origins` | localhost frontend + backend |
| `api_key` | rỗng |
| `rate_limit_per_minute` | `60` |
| `metrics_enabled` | `True` |
| `judge_provider` | `openai` |
| `judge_model` | `gpt-5.4-mini` |
| `crawl_concurrency` | `8` |
| `crawl_rate_per_sec` | `1.0` |

## Hằng số module có chủ sở hữu rõ ràng

| Hằng số | Nguồn | Giá trị |
|---|---|---|
| `HISTORY_CHAR_BUDGET` | `chat/session.py` | `2000` |
| `HISTORY_WINDOW_TURNS` | `chat/session.py` | `6` |
| `_SOURCE_TYPE_BOOST` | `rag/retriever.py` | bảng 9 loại nguồn |
| `_TRUST_LEVEL_BOOST` | `rag/retriever.py` | high `1.4`, medium `1.0`, low `0.7` |
| `_AUTHORITY_TAG_BOOST` | `rag/retriever.py` | `1.15` |
| `_DENSE_MAX_DISTANCE` | `rag/retriever.py` | `0.60`, default caller trực tiếp/test |

## Env key hợp lệ

`.env` hiện có đúng 15 key: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`,
`DATAGEN_API_KEY`, `API_KEY`, `OLLAMA_URL`, `DEVICE`, `LOG_LEVEL`, `LLM_MODEL`,
`INTAKE_MODE`, `INTAKE_MODEL`, `JUDGE_PROVIDER`, `JUDGE_MODEL`,
`DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `CORS_ORIGINS`.

Brief nói 16 nhưng chỉ liệt kê 15 key mục tiêu. Repo ưu tiên danh sách tường minh;
không có field/key nào bị giữ lại chỉ để làm đủ số đếm.
