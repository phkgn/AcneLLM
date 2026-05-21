from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    llm_fallback_model: str = "qwen2.5:3b"
    llm_num_ctx: int = 8192
    llm_temperature: float = 0.3
    ollama_health_timeout: float = 5.0
    ollama_generate_timeout: float = 180.0

    # Embedding
    embedding_model: str = "AITeamVN/Vietnamese_Embedding"
    # LOW-7: Optional multilingual model for mixed VI/EN KB.
    # Set to e.g. "intfloat/multilingual-e5-large" to improve EN retrieval.
    # Leave empty to use embedding_model above (default: Vietnamese-focused).
    embedding_model_multilingual: str = ""
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "gpu"

    # Storage
    chroma_dir: str = "./data/chroma_db"
    bm25_path: str = "./data/bm25_index.pkl"
    docs_jsonl: str = "./data/raw/documents.jsonl"
    chunks_jsonl: str = "./data/raw/chunks.jsonl"

    # Finetune data
    finetune_jsonl: str = "./data/finetune/llm_data.jsonl"
    qa_finetune_jsonl: str = "./data/finetune/qa_finetuning.jsonl"

    # Paths
    prompts_dir: str = "./config/prompts"
    guardrails_yaml: str = "./config/guardrails.yaml"
    seed_sources: str = "./data/seed_sources.yaml"

    # Retrieval
    retrieve_top_k: int = 20
    rerank_top_k: int = 5
    chat_retrieve_top_k: int = 8
    chat_rerank_top_k: int = 3
    chat_max_context_chars: int = 4500
    chat_min_citation_score: float = 0.12
    # Query expansion: gọi Ollama thêm 1 lần để tạo bilingual query
    # Tắt để giảm latency (~8-15s/request). Chỉ bật khi cần debug retrieval EN/VI
    enable_bilingual_query: bool = True
    english_input_notice: bool = True
    query_expansion_temperature: float = 0.1

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["*"]
    api_key: str = ""
    rate_limit_per_minute: int = 60
    metrics_enabled: bool = True

    # Crawler
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    crawl_concurrency: int = 8
    crawl_rate_per_sec: float = 1.0


settings = Settings()
