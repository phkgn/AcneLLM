"""Dependency injection container."""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Optional

from loguru import logger

from .llm.ollama_backend import OllamaBackend
from .llm.prompt_builder import PromptBuilder
from .chat.fallback.semantic_router import SemanticRouter
from .chat.session import HISTORY_WINDOW_TURNS
from .chat.unified_intake import UnifiedIntake
from .guardrails.runner import GuardrailRunner
from .rag.embedder import Embedder
from .rag.vectorstore import ChromaStore
from .rag.sparse import BM25Index
from .rag.retriever import HybridRetriever
from .rag.reranker import Reranker
from .db.base import DBConnection
from .db.session_store import SQLiteSessionStore
from .db.audit import AuditStore
from .cache import init_cache
from .utils.logging import log_runtime_banner


class Container:
    """Holds all initialized components. RAG fields are None if KB not built."""

    def __init__(
        self,
        settings: object,
        llm: OllamaBackend,
        prompt: PromptBuilder,
        guardrails: GuardrailRunner,
        session_store: SQLiteSessionStore,
        audit_store: AuditStore,
        embedder: Optional[Embedder] = None,
        store: Optional[ChromaStore] = None,
        bm25: Optional[BM25Index] = None,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[Reranker] = None,
        llm_extractor: Optional[object] = None,
        llm_router: Optional[object] = None,
        semantic_router: Optional[SemanticRouter] = None,
    ) -> None:
        self.settings         = settings
        self.llm              = llm
        self.prompt           = prompt
        self.guardrails       = guardrails
        self.session_store    = session_store
        self.audit_store      = audit_store
        self.embedder         = embedder
        self.store            = store
        self.bm25             = bm25
        self.retriever        = retriever
        self.reranker         = reranker
        self.llm_extractor    = llm_extractor
        self.llm_router       = llm_router
        self.semantic_router  = semantic_router

    @property
    def rag_ready(self) -> bool:
        return self.retriever is not None

    async def close(self) -> None:
        try:
            self.llm.close()
        except Exception:
            pass
        try:
            if self.llm_extractor is not None:
                self.llm_extractor.close()
        except Exception:
            pass
        try:
            if self.llm_router is not None:
                self.llm_router.close()
        except Exception:
            pass
        try:
            self.session_store.close()
        except Exception:
            pass


def build_container(settings) -> Container:
    # -- Database ----------------------------------------------------------------
    db_ttl = getattr(settings, "session_ttl", 1800.0)
    db_max_turns = HISTORY_WINDOW_TURNS
    # Sessions: SQLite (một file sessions.db thay cho nhiều file JSONL)
    session_db_path = getattr(settings, "session_db_path", "./data/sessions.db")
    session_store = SQLiteSessionStore(session_db_path, ttl=db_ttl, max_turns=db_max_turns)
    # Audit log: vẫn dùng SQLite (cần ORDER BY timestamp, COUNT, etc.)
    audit_db_path = getattr(settings, "audit_db_path", "./data/audit.db")
    try:
        _db_conn = DBConnection(audit_db_path)
    except Exception as exc:
        fallback_audit_db = str(Path(tempfile.gettempdir()) / "acne_llm_audit.db")
        logger.warning(
            "Audit DB unavailable at {}; using temp DB {} ({})",
            audit_db_path,
            fallback_audit_db,
            exc,
        )
        _db_conn = DBConnection(fallback_audit_db)
    audit_store   = AuditStore(_db_conn)
    # -- Cache (DiskCache) --------------------------------------------------------
    cache_dir    = getattr(settings, "cache_dir", "./data/cache")
    cache_size   = getattr(settings, "cache_size_gb", 2.0)
    if cache_size > 0:
        init_cache(cache_dir, size_limit_gb=cache_size)

    # -- LLM ------------------------------------------------------------------
    llm = OllamaBackend(
        base_url=settings.ollama_url,
        model=settings.llm_model,
        fallback_model=settings.llm_fallback_model,
        num_ctx=settings.llm_num_ctx,
        num_predict=settings.llm_num_predict,
        temperature=getattr(settings, "llm_temperature", 0.35),
        top_p=getattr(settings, "llm_top_p", 0.85),
        top_k=getattr(settings, "llm_top_k", 40),
        repeat_penalty=getattr(settings, "llm_repeat_penalty", 1.1),
        repeat_last_n=getattr(settings, "llm_repeat_last_n", 128),
        keep_alive=getattr(settings, "llm_keep_alive", "-1"),
        timeout=settings.ollama_generate_timeout,
        health_timeout=settings.ollama_health_timeout,
        use_modelfile_system=getattr(settings, "llm_use_modelfile_system", False),
    )

    intake_mode = getattr(settings, "intake_mode", "legacy")
    if intake_mode == "unified":
        intake_model = getattr(settings, "intake_model", "acne-intaker")
        intake_timeout = float(getattr(settings, "intake_timeout", 60.0))
        intake_backend = OllamaBackend(
            base_url=settings.ollama_url,
            model=intake_model,
            fallback_model=None,
            num_ctx=min(int(getattr(settings, "llm_num_ctx", 4096)), 4096),
            num_predict=768,
            temperature=0.0,
            top_p=1.0,
            top_k=20,
            repeat_penalty=1.0,
            repeat_last_n=64,
            keep_alive=getattr(settings, "llm_keep_alive", -1),
            timeout=intake_timeout,
            health_timeout=getattr(settings, "ollama_health_timeout", 5.0),
            use_modelfile_system=True,
        )
        unified = UnifiedIntake(
            intake_backend,
            model=intake_model,
            timeout=intake_timeout,
        )
        llm_router = unified
        llm_extractor = unified
        # intake.py is intentionally unchanged and still uses extractor_mode as
        # its interface-presence gate. Unified mode owns both interfaces.
        if getattr(settings, "extractor_mode", "llm") != "llm":
            settings.extractor_mode = "llm"
    else:
        from .chat.fallback.llm_extractor import LLMExtractor
        from .chat.fallback.llm_router import LLMRouter

        llm_router = None
        if getattr(settings, "router_mode", "llm") == "llm":
            router_model = getattr(settings, "router_model", "acnellm-intent")
            router_timeout = float(getattr(settings, "router_timeout", 8.0))
            router_backend = OllamaBackend(
                base_url=settings.ollama_url,
                model=router_model,
                fallback_model=None,
                num_ctx=min(int(getattr(settings, "llm_num_ctx", 4096)), 4096),
                num_predict=48,
                temperature=0.1,
                top_p=0.9,
                top_k=20,
                repeat_penalty=1.05,
                repeat_last_n=64,
                keep_alive=-1,
                timeout=router_timeout,
                health_timeout=getattr(settings, "ollama_health_timeout", 5.0),
                use_modelfile_system=True,
            )
            llm_router = LLMRouter(
                router_backend,
                model=router_model,
                timeout=router_timeout,
            )

        llm_extractor = None
        if getattr(settings, "extractor_mode", "llm") == "llm":
            extractor_model = getattr(
                settings, "extractor_model", "acne-extractor:1.5b"
            )
            extractor_timeout = float(getattr(settings, "extractor_timeout", 20.0))
            extractor_backend = OllamaBackend(
                base_url=settings.ollama_url,
                model=extractor_model,
                fallback_model=None,
                num_ctx=min(int(getattr(settings, "llm_num_ctx", 4096)), 4096),
                num_predict=512,
                temperature=0.0,
                top_p=0.9,
                top_k=20,
                repeat_penalty=1.05,
                repeat_last_n=64,
                keep_alive=getattr(settings, "llm_keep_alive", -1),
                timeout=extractor_timeout,
                health_timeout=getattr(settings, "ollama_health_timeout", 5.0),
                use_modelfile_system=True,
            )
            llm_extractor = LLMExtractor(
                extractor_backend,
                model=extractor_model,
                timeout=extractor_timeout,
            )

    prompt = PromptBuilder(settings.prompts_dir)
    # Soft OOS thuoc ve SemanticRouter/intaker. GuardrailRunner chi con giu cac
    # cong tat dinh (injection, genital, thuoc) nen khong con tham so nao.
    guardrails = GuardrailRunner(settings.guardrails_yaml)
    # -- RAG (chi load neu KB da build) ---------------------------------------
    chroma_dir = Path(settings.chroma_dir)
    bm25_path  = Path(settings.bm25_path)

    chroma_ready = chroma_dir.exists() and any(chroma_dir.iterdir())
    bm25_ready   = bm25_path.exists()

    embedder = store = bm25 = retriever = reranker = None
    semantic_router = None
    semantic_train_path = Path(
        getattr(
            settings,
            "semantic_router_train_path",
            "./data/intent_classify.train.jsonl",
        )
    )
    needs_embedder = semantic_train_path.exists() or (chroma_ready and bm25_ready)
    if needs_embedder:
        try:
            embedder = Embedder(
                model_name=settings.embedding_model,
                device=settings.device,
            )
        except Exception as e:
            logger.warning(
                f"Embedder load failed; semantic router/RAG dense path disabled: {e}"
            )
            embedder = None

    if semantic_train_path.exists() and embedder is not None:
        try:
            semantic_router = SemanticRouter(
                embedder=embedder,
                train_path=semantic_train_path,
                cache_path=getattr(
                    settings,
                    "semantic_router_cache_path",
                    "./data/intent_router_index.npz",
                ),
                k=int(getattr(settings, "semantic_router_k", 9)),
                oos_distance_threshold=float(
                    getattr(
                        settings,
                        "semantic_router_oos_distance_threshold",
                        0.483609,
                    )
                ),
                ambiguity_margin=float(
                    getattr(settings, "semantic_router_ambiguity_margin", 0.08)
                ),
            )
        except Exception as e:
            logger.warning(
                f"Semantic router init failed; legacy rule fallback active: {e}"
            )
            semantic_router = None
    elif not semantic_train_path.exists():
        logger.warning(
            "Semantic router train split missing ({}); legacy rule fallback active",
            semantic_train_path,
        )

    if chroma_ready and bm25_ready:
        try:
            store = ChromaStore(persist_dir=str(chroma_dir))
            bm25 = BM25Index.load(str(bm25_path))
        except Exception as e:
            logger.warning(f"Chroma/BM25 load failed: {e} -- falling back to llm_only")
            store = bm25 = None
        else:
            retriever = HybridRetriever(
                store=store,
                embedder=embedder,
                bm25=bm25,
                dense_max_distance=getattr(settings, "dense_max_distance", 0.60),
            )

            try:
                reranker = Reranker(
                    model_name=settings.reranker_model,
                    device=settings.device,
                    batch_size=settings.reranker_batch_size,
                    cache_size=settings.reranker_cache_size,
                    min_sigmoid_score=getattr(settings, "reranker_min_sigmoid", 0.30),
                )
            except Exception as e:
                logger.warning(f"Reranker load failed, using raw retrieval: {e}")
                reranker = None

    else:
        missing = []
        if not chroma_ready:
            missing.append(f"ChromaDB ({chroma_dir})")
        if not bm25_ready:
            missing.append(f"BM25 ({bm25_path})")
        logger.warning(
            f"KB not ready ({', '.join(missing)}) -- "
            f"only llm_only mode available. "
            f"Run: python scripts/build_kb.py --step embed"
        )

    container = Container(
        settings=settings,
        llm=llm,
        prompt=prompt,
        guardrails=guardrails,
        session_store=session_store,
        audit_store=audit_store,
        embedder=embedder,
        store=store,
        bm25=bm25,
        retriever=retriever,
        reranker=reranker,
        llm_extractor=llm_extractor,
        llm_router=llm_router,
        semantic_router=semantic_router,
    )
    log_runtime_banner(container)
    return container
