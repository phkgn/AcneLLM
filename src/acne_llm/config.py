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
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LLM ──────────────────────────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "acne-generator"
    llm_fallback_model: str = "qwen2.5:3b"
    # num_ctx: window context. Giảm = tiết kiệm VRAM cho KV-cache, fit model GPU.
    llm_num_ctx: int = 4096 #3072
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
    # Timeout thấp để phép đo latency lộ request chậm thay vì che bằng env override.
    ollama_generate_timeout: float = 30.0
    # Khi True: không gửi system message qua API — để Modelfile SYSTEM tự xử lý.
    # Bật khi model đã fine-tune với system prompt nhúng sẵn, tránh 2 system prompt chồng.
    # Default True: model production acne-generator đã nhúng SYSTEM trong Modelfile.
    llm_use_modelfile_system: bool = True

    # ── Unified intake ──────────────────────────────────────────────────────
    # Unified là runtime mặc định; legacy chỉ giữ lại cho arm A/B.
    intake_mode: Literal["unified", "legacy"] = "unified"
    intake_model: str = "acne-intaker"
    intake_timeout: float = 60.0

    # ── Intake extractor ────────────────────────────────────────────────────
    # Dedicated small-model producer for UserInput + per-field confidence only.
    # Rule modules remain live and are used whenever this path fails.
    extractor_mode: Literal["llm", "rule"] = "llm"
    extractor_model: str = "acne-extractor:1.5b"
    extractor_timeout: float = 20.0

    # ── LLM-first intent router ─────────────────────────────────────────────
    # "llm": generative router primary, semantic then rule as fallbacks.
    # "semantic": disable the generative router for baseline/A-B comparison.
    router_mode: Literal["llm", "semantic"] = "llm"
    router_model: str = "acnellm-intent"
    router_timeout: float = 8.0

    @field_validator("intake_timeout")
    @classmethod
    def _check_intake_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("intake_timeout must be greater than zero")
        return v

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
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # device cho embedder + reranker. "cuda" để dùng GPU (cần PyTorch+CUDA build).
    # "cpu" nếu không có GPU hoặc VRAM đã đầy bởi LLM.
    # Lưu ý: "gpu" không phải giá trị PyTorch chuẩn — validator sẽ map → "cuda".
    device: str = "cpu"

    # ── Semantic intent router ───────────────────────────────────────────────
    # Chỉ train split được index; test split và OOS calibration không bao giờ
    # được đọc bởi runtime.
    semantic_router_train_path: str = "./data/intent_classify.train.jsonl"
    semantic_router_cache_path: str = "./data/intent_router_index.npz"
    semantic_router_k: int = 9
    semantic_router_oos_distance_threshold: float = 0.483609
    semantic_router_ambiguity_margin: float = 0.08

    @field_validator("semantic_router_k")
    @classmethod
    def _check_semantic_router_k(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("semantic_router_k must be in [1,100]")
        return v

    @field_validator(
        "semantic_router_oos_distance_threshold",
        "semantic_router_ambiguity_margin",
    )
    @classmethod
    def _check_semantic_router_thresholds(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("semantic router thresholds must be in [0,1]")
        return v

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
    # Legacy scope-mode API is retained for direct callers/tests. Live soft OOS
    # is owned by the semantic router's nearest-neighbor distance threshold.
    guardrails_scope_mode: str = "soft"

    # ── Retrieval ────────────────────────────────────────────────────────────
    # Giữ lại sau cross-encoder rerank
    rerank_top_k: int = 3
    # Chat dùng pool nhỏ hơn vì latency quan trọng hơn
    # Pool ĐƯA VÀO cross-encoder. Phải LỚN hơn nhiều so với số giữ lại — reranker
    # ton tai de xep lai pool rong; cho no 6 chon 3 thi recall bi chan cung boi
    # retriever va model dat tien chi xao lai 6 mon. 20 -> 5 la ty le thong dung.
    # Truoc day 6/3, trong khi eval s2/s3 chay 15/5 => do mot he, deploy he khac.
    chat_retrieve_top_k: int = 15
    chat_rerank_top_k: int = 5
    # Tổng ký tự context inject vào prompt chat
    chat_max_context_chars: int = 6000
    # Pool safety pass (thai kỳ, thuốc kê đơn) — ưu tiên guideline source_types
    chat_safety_top_k: int = 5
    # Pool guideline pass — chạy cho MỌI truy vấn, dense retrieve giới hạn trong
    # tầng khuyến cáo chính thức (NICE/AAD/clinical_textbook, 973 chunk).
    # Bảo đảm khuyến cáo vào được pool rerank; cross-encoder vẫn quyết định cuối.
    chat_guideline_top_k: int = 5
    # Ngưỡng drop_noisy_chunks, dùng ở chat/_retrieval.py.
    # Field này TỪNG không tồn tại trong khi _retrieval.py đã đọc tên này qua
    # getattr(..., 0.25) → mọi lần tune đều vô tác dụng. Đừng đổi tên rời rạc.
    #
    # CANH BAO: gia tri nay chay tren HAI thang diem khac nhau.
    #  - _noise_filter (SAU reranker): score la sigmoid -> reranker_min_sigmoid=0.50
    #    da cat truoc, nen o nhanh nay no khong con tac dung gi.
    #  - _full_filter (KHONG co reranker): score la fusion*boost, thang hoan toan
    #    khac. 0.25 chi co y nghia o nhanh nay.
    # Giu 0.25 vi nhanh fallback la ly do duy nhat field nay ton tai.
    chat_min_chunk_score: float = 0.25
    # Số chunk tối đa lấy từ CÙNG một tài liệu vào context cuối. Chunker chồng lấn
    # nên hai chunk kề nhau trong một bài gần như trùng nội dung; 1 buộc mỗi ô là
    # một nguồn khác. Tăng lên 2 nếu tài liệu dài bị cắt mất đoạn cần thiết.
    chat_max_chunks_per_source: int = 1
    # OOD guard: nếu KHÔNG chunk nào sau rerank vượt floor → bỏ hết, trả None,
    # để LLM trả lời không dùng RAG thay vì nhét context nhiễu.
    # Ngưỡng MỀM per-chunk: giữ riêng chunk vượt floor khi cả pool yếu.
    #
    # LICH SU NGUONG NAY — doc truoc khi chinh:
    #   0.45 -> "dead code, phai > 0.50" -> 0.58. Ca hai lan deu dua tren gia dinh
    #   score la sigmoid(logit). THUC TE score la XAC SUAT tu CrossEncoder.predict(),
    #   va code con sigmoid lan hai nen moi thu bi nen vao [0.500, 0.731]. Nguong
    #   0.58 duoc chinh theo dai gia do.
    # Sau khi bo sigmoid thua, thang do la xac suat that:
    #   truy van dung chu de -> 0.95-0.999 | truy van lac de -> < 0.1
    # 0.50 = "kha nang lien quan duoi 50%" -> khong dang dua vao context.
    chat_rerank_floor: float = 0.50
    # ── Extraction confidence (rule-based intake) ────────────────────────────
    # Ngưỡng cho tầng confidence bọc quanh normalizer (extraction_confidence.py).
    # Heuristic khởi điểm; golden set (scripts/tune_extraction_thresholds.py) dò lại.
    extract_min_field_conf: float = 0.60  # completeness coi field "đã có" khi ≥ ngưỡng
    route_min_confidence: float = 0.55   # routing dưới ngưỡng → clarify thay vì đoán
    # ── Reranker tuning ──────────────────────────────────────────────────────
    reranker_batch_size: int = 16
    reranker_cache_size: int = 2048
    # Sigmoid threshold loại chunk yếu sau cross-encoder
    # CrossEncoder.predict() tra XAC SUAT [0,1] (da sigmoid san). Truoc day code
    # sigmoid lan hai nen moi diem bi nen vao [0.500, 0.731] va mo ngưỡng theo dai
    # gia do. Sau khi bo sigmoid thua, thang do lai la xac suat that:
    #   bge-reranker-v2-m3: chunk lien quan ~0.95-0.999, chunk lac de tai < 0.1
    # 0.30 = bo chunk ro rang khong lien quan.
    reranker_min_sigmoid: float = 0.30

    # ── Dense retrieval ──────────────────────────────────────────────────────
    # Cosine distance threshold Chroma: 0.60 ≈ similarity 0.40, đủ chặt cho medical
    dense_max_distance: float = 0.60

    # ── Cache (DiskCache) ────────────────────────────────────────────────────
    # Thu muc luu cache tren disk (embedding vectors + retrieval results)
    cache_dir: str = "./data/cache"
    # Dung luong toi da (GB). 0 = tat cache hoan toan.
    cache_size_gb: float = 2.0

    # ── Session store (SQLite) ───────────────────────────────────────────────
    # Thời gian idle tối đa (giây) trước khi session bị xoá.
    session_ttl: float = 1800.0

    # ── Audit log (SQLite) ───────────────────────────────────────────────────
    # SQLite file chỉ dùng cho audit log (tạo tự động nếu chưa có).
    audit_db_path: str = "./data/audit.db"
    # File SQLite chứa session (một file thay cho nhiều .jsonl).
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

    # ── Judge (eval) ─────────────────────────────────────────────────────────
    judge_provider: Literal["openai", "anthropic", "deepseek"] = "openai"
    judge_model: str = "gpt-5.4-mini"

    # ── Crawler ────────────────────────────────────────────────────────────────
    crawl_concurrency: int = 8
    crawl_rate_per_sec: float = 1.0


# Singleton instance — import sẵn để dùng khắp codebase: `from acne_llm.config import settings`
settings = Settings()
