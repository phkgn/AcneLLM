# Config layout — trạng thái sau refactor evaluation

Tài liệu này mô tả trạng thái đang chạy của repo. Nếu tài liệu và code lệch nhau,
`src/acne_llm/config.py`, `.env.baseline` và các hằng số module là nguồn sự thật.

## Quy tắc ba tầng

| Tầng | Nội dung |
|---|---|
| `.env` | Secret và giá trị thực sự khác giữa máy/lần chạy. |
| `src/acne_llm/config.py` | Schema/default dùng qua nhiều module hoặc cần override. |
| Hằng số module | Giá trị chỉ một module sở hữu và chưa có nhu cầu tune từ ngoài. |

Một giá trị chỉ có một nguồn sở hữu. Hai ngoại lệ có chủ ý trong retriever:

- `dense_max_distance`: config thắng; DI truyền `settings.dense_max_distance` vào
  production. `_DENSE_MAX_DISTANCE = 0.60` chỉ là default cho caller trực tiếp/test.
- Source/trust/authority boosts: module thắng; `_SOURCE_TYPE_BOOST`,
  `_TRUST_LEVEL_BOOST`, `_AUTHORITY_TAG_BOOST` chỉ tồn tại trong
  `src/acne_llm/rag/retriever.py` và không có injection point.

Session history cũng do module sở hữu:

- `HISTORY_CHAR_BUDGET = 2000`
- `HISTORY_WINDOW_TURNS = 6`

## `.env` / `.env.baseline`: 15 key

Brief ghi “16 key”, nhưng danh sách đích mà brief chỉ định chỉ có 15 key. Repo giữ
đúng 15 key đã nêu, không thêm một key giả chỉ để khớp số đếm:

```ini
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
DATAGEN_API_KEY=
API_KEY=
OLLAMA_URL=http://localhost:11434
DEVICE=cpu
LOG_LEVEL=DEBUG
LLM_MODEL=acnellm-role
INTAKE_MODE=unified
INTAKE_MODEL=acne-intake
JUDGE_PROVIDER=openai
JUDGE_MODEL=gpt-5.4-mini
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
CORS_ORIGINS=["*"]
```

`.env.baseline` để trống toàn bộ secret. `.env` local giữ giá trị secret hiện có
và không được commit. `extra="ignore"` vẫn được giữ; `tests/test_env_keys.py`
chặn key mồ côi và typo mà không phá các key datagen đọc trực tiếp.

Các key đã bỏ khỏi `.env`:

- Chết: `GUARDRAILS_ENABLE_OOD`, `GUARDRAILS_OOD_THRESHOLD`, `USER_AGENT`,
  `JUDGE_REASONING_EFFORT`, `MINIMAX_API_KEY`.
- Trùng default: `CHROMA_DIR`, `BM25_PATH`, `DOCS_JSONL`, `CHUNKS_JSONL`,
  `PROMPTS_DIR`, `GUARDRAILS_YAML`, `SEED_SOURCES`, `API_HOST`, `API_PORT`,
  `LLM_FALLBACK_MODEL`, `GUARDRAILS_SCOPE_MODE`.
- Chỉ dùng cho legacy hoặc che latency: `EXTRACTOR_MODE`, `EXTRACTOR_MODEL`,
  `EXTRACTOR_TIMEOUT`, `OLLAMA_GENERATE_TIMEOUT`.

## `Settings`: 70 field

| Nhóm | Số field | Ghi chú |
|---|---:|---|
| LLM | 14 | Timeout generate mặc định 30 giây. |
| Unified intake | 3 | Runtime mặc định `unified` / `acne-intake`. |
| Legacy extractor/router | 6 | Giữ cho A/B, không đưa vào `.env`. |
| Embedding/reranker device | 3 | Không còn multilingual field chết. |
| Semantic router | 5 | Train-only index + thresholds. |
| Storage/finetune/config paths | 9 | Default cố định trong code. |
| Guardrails | 1 | Scope mode legacy. |
| Retrieval | 6 | Production pool `chat_retrieve_top_k=6`. |
| Extraction confidence | 2 | Field/route confidence. |
| Reranker tuning | 3 | Batch/cache/min sigmoid. |
| Dense retrieval | 1 | `dense_max_distance=0.60`. |
| Cache/session/audit/log | 6 | Session history không còn ở config. |
| API | 7 | Host/port/CORS/auth/rate/metrics. |
| Judge | 2 | `openai` + `gpt-5.4-mini`. |
| Crawler | 2 | Concurrency/rate. |
| **Tổng** | **70** | Kiểm bằng `len(Settings.model_fields)`. |

Các field đã xóa hoàn toàn:

```text
retrieve_top_k
chat_rerank_top_k_clinical
extract_fuzzy_accept
extract_fuzzy_review
extract_safety_accept
bm25_normalize
english_input_notice
embedding_model_multilingual
retrieval_source_boosts
retrieval_trust_boosts
retrieval_authority_boost
session_history_char_budget
session_max_history_turns
inline_citation
chat_min_citation_score
chat_require_citations
chat_rerank_ood_floor
chat_rerank_keep_floor
```

Hai rerank floor cuối được thay bằng một field duy nhất:
`chat_rerank_floor = 0.58`.

## Judge và evaluation

Judge Python và dashboard đều để `Settings` quyết định provider/model. Dashboard
không truyền `--provider` hoặc `--model`, nên `.env` không còn bị hardcode CLI đè.
Artifact judge ghi `judge_provider`/`judge_model` thật đã gọi. Arm Y cố định
`gpt-5.6-terra`, khác judge `gpt-5.4-mini`.

## Chốt kiểm tra

```powershell
.\.venv\Scripts\python.exe -c "from acne_llm.config import Settings, settings; print(len(Settings.model_fields), settings.judge_model)"
.\.venv\Scripts\python.exe -m pytest tests/test_env_keys.py -q
```

Kết quả kỳ vọng: `70 gpt-5.4-mini` và test xanh.
