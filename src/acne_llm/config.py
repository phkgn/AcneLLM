"""Cấu hình ứng dụng — đọc từ .env hoặc biến môi trường.

Import:
    from acne_llm.config import settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LLM ──────────────────────────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    llm_fallback_model: str = "qwen2.5:3b"
    llm_num_ctx: int = 8192
    llm_num_predict: int = 2048
    llm_temperature: float = 0.3
    ollama_health_timeout: float = 5.0
    ollama_generate_timeout: float = 180.0
    # Khi True: không gửi system message qua API — để Modelfile SYSTEM tự xử lý.
    # Bật khi model đã fine-tune với system prompt nhúng sẵn, tránh 2 system prompt chồng.
    llm_use_modelfile_system: bool = False

    # ── Embedding & Reranker ─────────────────────────────────────────────────
    embedding_model: str = "AITeamVN/Vietnamese_Embedding"
    # Để trống = dùng embedding_model; đặt "intfloat/multilingual-e5-large" cho KB VI+EN.
    embedding_model_multilingual: str = ""
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "gpu"

    # ── Storage paths ────────────────────────────────────────────────────────
    chroma_dir: str = "./data/chroma_db"
    bm25_path: str = "./data/bm25_index.pkl"
    docs_jsonl: str = "./data/raw/documents.jsonl"
    chunks_jsonl: str = "./data/raw/chunks.jsonl"

    # ── Finetune data ────────────────────────────────────────────────────────
    finetune_jsonl: str = "./data/finetune/llm_data.jsonl"
    qa_finetune_jsonl: str = "./data/finetune/qa_finetuning.jsonl"

    # ── Config paths ─────────────────────────────────────────────────────────
    prompts_dir: str = "./config/prompts"
    guardrails_yaml: str = "./config/guardrails.yaml"
    seed_sources: str = "./data/seed_sources.yaml"

    # ── Guardrails ───────────────────────────────────────────────────────────
    guardrails_enable_ood: bool = True
    # OOD: cosine sim query vs acne centroid. < threshold → out-of-domain refusal.
    # 0.25 = conservative; tăng lên 0.30-0.35 nếu muốn chặt hơn.
    guardrails_ood_threshold: float = 0.25
    # soft: LLM fine-tune tự xử lý out-of-scope | hard: refusal cứng | off: tắt
    guardrails_scope_mode: str = "soft"

    # ── Retrieval ────────────────────────────────────────────────────────────
    # Pool trước rerank (giảm từ 20→15 sau khi có distance filter + fusion pruning)
    retrieve_top_k: int = 15
    # Giữ lại sau cross-encoder rerank
    rerank_top_k: int = 5
    # Chat dùng pool nhỏ hơn vì latency quan trọng hơn
    chat_retrieve_top_k: int = 10
    chat_rerank_top_k: int = 3
    # Tổng ký tự context inject vào prompt chat
    chat_max_context_chars: int = 4500
    # Sigmoid score tối thiểu để chunk xuất hiện trong citation (khớp reranker threshold)
    chat_min_citation_score: float = 0.25
    # Pool safety pass (thai kỳ, thuốc kê đơn) — ưu tiên guideline source_types
    chat_safety_top_k: int = 5
    chat_use_llm_planner: bool = False

    # ── Intent router / optional micro-classifier ────────────────────────────
    # OFF by default: rule-based routing remains the production path unless the
    # operator explicitly enables the small classifier for ambiguous cases.
    intent_router_enabled: bool = False
    intent_router_model: str = "qwen2.5:0.5b"
    intent_router_min_confidence: float = 0.80
    intent_router_tie_margin: float = 0.10
    intent_router_timeout_seconds: float = 5.0
    intent_router_num_ctx: int = 1024
    intent_router_num_predict: int = 128

    # ── Reranker tuning ──────────────────────────────────────────────────────
    reranker_batch_size: int = 16
    reranker_cache_size: int = 2048
    # Sigmoid threshold loại chunk yếu sau cross-encoder
    reranker_min_sigmoid: float = 0.30

    # ── Dense retrieval ──────────────────────────────────────────────────────
    # Cosine distance threshold Chroma: 0.60 ≈ similarity 0.40, đủ chặt cho medical
    dense_max_distance: float = 0.60
    bm25_normalize: bool = True
    # Deprecated — giữ để .env cũ không vỡ
    enable_bilingual_query: bool = False
    english_input_notice: bool = True
    query_expansion_temperature: float = 0.1

    # ── Cache (DiskCache) ────────────────────────────────────────────────────
    # Thu muc luu cache tren disk (embedding vectors + retrieval results)
    cache_dir: str = "./data/cache"
    # Dung luong toi da (GB). 0 = tat cache hoan toan.
    cache_size_gb: float = 2.0

    # ── Session store (JSONL) ────────────────────────────────────────────────
    # Thư mục chứa session files (một .jsonl per session_id, dễ đọc/debug).
    sessions_dir: str = "./data/sessions"
    # Thời gian idle tối đa (giây) trước khi session bị xoá.
    session_ttl: float = 1800.0
    # Giới hạn lịch sử hội thoại inject vào prompt (ký tự). 0 = không giới hạn.
    # 3000 chars ≈ 850 tokens — đủ cho ~8-10 turns ngắn, tránh overflow ctx window.
    session_history_char_budget: int = 3000
    # Số turns tối đa giữ trong memory (0 = không giới hạn). Kết hợp với char budget.
    session_max_history_turns: int = 10

    # ── Audit log (SQLite) ───────────────────────────────────────────────────
    # SQLite file chỉ dùng cho audit log (tạo tự động nếu chưa có).
    audit_db_path: str = "./data/audit.db"
    # Backward-compat alias — không dùng nữa nhưng giữ để .env cũ không vỡ
    session_db_path: str = "./data/sessions.db"

    # ── Logging ──────────────────────────────────────────────────────────────
    # DEBUG để thấy từng bước pipeline trong PowerShell; INFO cho production
    log_level: str = "INFO"

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    # Whitelist cụ thể — không dùng wildcard để tránh CORS leak.
    # Override: CORS_ORIGINS=["https://your-domain.com","http://localhost:3000"]
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    api_key: str = ""
    rate_limit_per_minute: int = 60
    metrics_enabled: bool = True

    # ── Crawler ──────────────────────────────────────────────────────────────
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    crawl_concurrency: int = 8
    crawl_rate_per_sec: float = 1.0


settings = Settings()
