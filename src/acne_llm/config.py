"""Cấu hình ứng dụng — đọc từ .env hoặc biến môi trường.

Import:
    from acne_llm.config import settings

Quy ước layer config (đọc kỹ trước khi thêm setting mới):
  - Modelfile (model/V2/Q4/Modelfile): CHỈ chứa artifact-level (FROM, TEMPLATE,
    SYSTEM, stop tokens). KHÔNG đặt num_ctx/temperature/top_p ở đây — Python
    cần quyền override per-request.
  - .env: chỉ override các giá trị khác giữa môi trường (URL, secret, path,
    feature flag). Đừng copy nguyên config.py vào đây.
  - config.py (file này): single source of truth cho SCHEMA + DEFAULTS.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LLM ──────────────────────────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "acnellm-v2-q4"
    llm_fallback_model: str = "qwen2.5:3b"
    # num_ctx: window context. Giảm = tiết kiệm VRAM cho KV-cache, fit model GPU.
    llm_num_ctx: int = 4096
    llm_num_predict: int = 1200
    llm_temperature: float = 0.35
    llm_top_p: float = 0.85
    llm_top_k: int = 40
    llm_repeat_penalty: float = 1.1
    llm_repeat_last_n: int = 128
    # keep_alive: giữ model warm trong VRAM.
    # Ollama parse như Go duration:
    #   - int: -1 = vĩnh viễn (đến khi Ollama tắt), 0 = unload ngay, 300 = 300s
    #   - string: BẮT BUỘC có unit — "30m", "1h", "300s" (KHÔNG dùng "-1" string)
    # Trong .env ghi LLM_KEEP_ALIVE=-1 (validator sẽ convert sang int -1).
    llm_keep_alive: str | int = -1
    ollama_health_timeout: float = 5.0
    # 30s đủ cho mọi request khi GPU healthy. Nếu vượt → có vấn đề, không che giấu.
    ollama_generate_timeout: float = 30.0
    # Khi True: không gửi system message qua API — để Modelfile SYSTEM tự xử lý.
    # Bật khi model đã fine-tune với system prompt nhúng sẵn, tránh 2 system prompt chồng.
    llm_use_modelfile_system: bool = False

    @field_validator("llm_num_ctx")
    @classmethod
    def _check_num_ctx(cls, v: int) -> int:
        if not 512 <= v <= 32768:
            raise ValueError(f"llm_num_ctx={v} ngoài phạm vi hợp lý [512, 32768]")
        return v

    @field_validator("llm_keep_alive", mode="before")
    @classmethod
    def _check_keep_alive(cls, v) -> str | int:
        """Normalize về int hoặc string-có-unit.

        Ollama API yêu cầu: int (seconds, -1 = forever) hoặc string có unit
        ("30m", "1h"). String "-1" trần sẽ gây 400 "missing unit in duration".
        """
        if isinstance(v, int):
            return v
        s = str(v).strip().lower()
        # Số (kể cả âm) → convert sang int
        if s.lstrip("-").isdigit():
            return int(s)
        # Có unit → giữ string, Ollama tự parse
        if s.endswith(("s", "m", "h")) and s[:-1].replace(".", "", 1).isdigit():
            return s
        raise ValueError(
            f"llm_keep_alive={v!r} không hợp lệ. Dùng: -1 (forever), 0, "
            f"số giây (300), hoặc string có unit ('30m', '1h')."
        )

    # ── Embedding & Reranker ─────────────────────────────────────────────────
    embedding_model: str = "AITeamVN/Vietnamese_Embedding"
    # Để trống = dùng embedding_model; đặt "intfloat/multilingual-e5-large" cho KB VI+EN.
    embedding_model_multilingual: str = ""
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # device cho embedder + reranker. "cuda" để dùng GPU (cần PyTorch+CUDA build).
    # "cpu" nếu không có GPU hoặc VRAM đã đầy bởi LLM.
    # Lưu ý: "gpu" không phải giá trị PyTorch chuẩn — validator sẽ map → "cuda".
    device: str = "cuda"

    @field_validator("device")
    @classmethod
    def _normalize_device(cls, v: str) -> str:
        s = str(v).strip().lower()
        # Map alias thường gặp
        if s in {"gpu", "nvidia", "cuda:0"}:
            return "cuda"
        if s in {"cpu", "cuda", "mps", "auto"}:
            return s
        # Cho phép "cuda:N"
        if s.startswith("cuda:") and s[5:].isdigit():
            return s
        raise ValueError(f"device={v!r} không hợp lệ (chấp nhận: cpu, cuda, cuda:N, mps, auto)")

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
    # 15 để reranker có đủ candidates — pool 10 sau fusion prune thường còn ~6, quá ít.
    chat_retrieve_top_k: int = 15
    chat_rerank_top_k: int = 3
    # Khi có clinical_plan đầy đủ: giữ nhiều chunk hơn để LLM có đủ context
    chat_rerank_top_k_clinical: int = 5
    # Tổng ký tự context inject vào prompt chat
    chat_max_context_chars: int = 4500
    # Sigmoid score tối thiểu để chunk xuất hiện trong citation (khớp reranker threshold)
    chat_min_citation_score: float = 0.25
    # Pool safety pass (thai kỳ, thuốc kê đơn) — ưu tiên guideline source_types
    chat_safety_top_k: int = 5
    # OOD guard: nếu avg và max sigmoid sau rerank đều < floor → bỏ chunks, trả None.
    # 0.45 = gần random (sigmoid(0) = 0.5), nghĩa là reranker không tin chunk nào liên quan.
    chat_rerank_ood_floor: float = 0.45

    # ── Intent router / optional micro-classifier ────────────────────────────
    # OFF by default: rule-based routing remains the production path unless the
    # operator explicitly enables the small classifier for ambiguous cases.
    intent_router_enabled: bool = False
    intent_router_model: str = "qwen2.5:0.5b"
    intent_router_min_confidence: float = 0.80
    intent_router_tie_margin: float = 0.10
    intent_router_timeout_seconds: float = 15.0
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
