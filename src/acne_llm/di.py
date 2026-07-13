"""Dependency injection container."""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Optional

from loguru import logger

from .llm.ollama_backend import OllamaBackend
from .llm.prompt_builder import PromptBuilder
from .llm.clinical_planner import ClinicalQueryPlanner
from .guardrails.runner import GuardrailRunner
from .rag.embedder import Embedder
from .rag.vectorstore import ChromaStore
from .rag.sparse import BM25Index
from .rag.retriever import HybridRetriever
from .rag.reranker import Reranker
from .vision.mock import MockVision
from .db.base import DBConnection
from .db.jsonl_session_store import JsonlSessionStore
from .db.audit import AuditStore
from .cache import init_cache


class Container:
    """Holds all initialized components. RAG fields are None if KB not built."""

    def __init__(
        self,
        settings: object,
        llm: OllamaBackend,
        prompt: PromptBuilder,
        clinical_planner: ClinicalQueryPlanner,
        guardrails: GuardrailRunner,
        vision: MockVision,
        session_store: JsonlSessionStore,
        audit_store: AuditStore,
        embedder: Optional[Embedder] = None,
        store: Optional[ChromaStore] = None,
        bm25: Optional[BM25Index] = None,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[Reranker] = None,
    ) -> None:
        self.settings         = settings
        self.llm              = llm
        self.prompt           = prompt
        self.clinical_planner = clinical_planner
        self.guardrails       = guardrails
        self.vision           = vision
        self.session_store    = session_store
        self.audit_store      = audit_store
        self.embedder         = embedder
        self.store            = store
        self.bm25             = bm25
        self.retriever        = retriever
        self.reranker         = reranker

    @property
    def rag_ready(self) -> bool:
        return self.retriever is not None

    async def close(self) -> None:
        try:
            self.llm.close()
        except Exception:
            pass
        try:
            self.session_store.close()
        except Exception:
            pass


def build_container(settings) -> Container:
    logger.info("Building DI container...")

    # -- Database ----------------------------------------------------------------
    db_ttl = getattr(settings, "session_ttl", 1800.0)
    db_max_turns = getattr(settings, "session_max_history_turns", 10)
    # Sessions: JSONL (một file per session, dễ đọc/debug)
    sessions_dir  = getattr(settings, "sessions_dir", "./data/sessions")
    session_store = JsonlSessionStore(sessions_dir, ttl=db_ttl, max_turns=db_max_turns)
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
    logger.info(f"Sessions JSONL: {sessions_dir} | Audit SQLite: {audit_db_path}")

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

    # Log effective LLM config — phát hiện sớm config drift giữa .env / config.py / Modelfile.
    logger.info(
        "LLM effective: model={} ctx={} predict={} temp={} top_p={} top_k={} "
        "keep_alive={} use_modelfile_system={}",
        settings.llm_model,
        settings.llm_num_ctx,
        settings.llm_num_predict,
        getattr(settings, "llm_temperature", 0.35),
        getattr(settings, "llm_top_p", 0.85),
        getattr(settings, "llm_top_k", 40),
        getattr(settings, "llm_keep_alive", "-1"),
        getattr(settings, "llm_use_modelfile_system", False),
    )
    # Đọc params Ollama THỰC SỰ áp dụng (Modelfile) — verify không có param
    # nướng sẵn override Python config.
    try:
        modelfile_info = llm.show_params()
        if modelfile_info.get("parameters"):
            logger.info(
                "Modelfile PARAMETER (Ollama-side):\n{}", modelfile_info["parameters"]
            )
        else:
            logger.info("Modelfile không có PARAMETER override (tốt — Python full control)")
    except Exception as e:
        logger.warning(f"Không đọc được Modelfile params: {e}")

    prompt = PromptBuilder(settings.prompts_dir)
    clinical_planner = ClinicalQueryPlanner()
    guardrails = GuardrailRunner(
        settings.guardrails_yaml,
        embedder=None,
        enable_ood=getattr(settings, "guardrails_enable_ood", True),
        ood_threshold=getattr(settings, "guardrails_ood_threshold", 0.25),
        scope_mode=getattr(settings, "guardrails_scope_mode", "soft"),
    )
    logger.info(f"LLM: {settings.llm_model} @ {settings.ollama_url}")

    # -- RAG (chi load neu KB da build) ---------------------------------------
    chroma_dir = Path(settings.chroma_dir)
    bm25_path  = Path(settings.bm25_path)

    chroma_ready = chroma_dir.exists() and any(chroma_dir.iterdir())
    bm25_ready   = bm25_path.exists()

    embedder = store = bm25 = retriever = reranker = None

    if chroma_ready and bm25_ready:
        logger.info("KB detected -- loading RAG components...")
        try:
            store = ChromaStore(persist_dir=str(chroma_dir))
            bm25 = BM25Index.load(str(bm25_path))
        except Exception as e:
            logger.warning(f"Chroma/BM25 load failed: {e} -- falling back to llm_only")
            store = bm25 = None
        else:
            logger.info(
                f"ChromaDB: {store.count()} vectors | BM25: {len(bm25.chunk_ids)} chunks"
            )
            try:
                emb_model = (
                    getattr(settings, "embedding_model_multilingual", "")
                    or settings.embedding_model
                )
                embedder = Embedder(model_name=emb_model, device=settings.device)
            except Exception as e:
                logger.warning(f"Embedder load failed, sparse-only retrieval: {e}")
                embedder = None

            retriever = HybridRetriever(
                store=store,
                embedder=embedder,
                bm25=bm25,
                dense_max_distance=getattr(settings, "dense_max_distance", 0.60),
            )

            if embedder is not None and guardrails.enable_ood:
                _centroid_path = str(
                    Path(settings.guardrails_yaml).parent / "ood_centroid.json"
                )
                from .guardrails.ood_detector import OodDetector as _OodDetector
                guardrails._ood = _OodDetector(
                    embedder=embedder,
                    centroid_path=_centroid_path,
                    ood_threshold=getattr(settings, "guardrails_ood_threshold", 0.25),
                )
                logger.info("[guardrails] OOD detector attached with embedder")

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

            logger.success("RAG ready -- shared chat orchestrator enabled")
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

    return Container(
        settings=settings,
        llm=llm,
        prompt=prompt,
        clinical_planner=clinical_planner,
        guardrails=guardrails,
        vision=MockVision(),
        session_store=session_store,
        audit_store=audit_store,
        embedder=embedder,
        store=store,
        bm25=bm25,
        retriever=retriever,
        reranker=reranker,
    )
