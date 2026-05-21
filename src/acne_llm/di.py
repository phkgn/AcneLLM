"""Dependency injection container."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from .llm.ollama_backend import OllamaBackend
from .llm.prompt_builder import PromptBuilder
from .llm.clinical_planner import ClinicalQueryPlanner
from .guardrails.runner import GuardrailRunner
from .pipeline.llm_only import LLMOnlyPipeline
from .pipeline.hybrid import HybridPipeline
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
from .chat.intent_router import OllamaIntentClassifier


class Container:
    """Holds all initialized components. RAG fields are None if KB not built."""

    def __init__(
        self,
        settings: object,
        llm: OllamaBackend,
        prompt: PromptBuilder,
        clinical_planner: ClinicalQueryPlanner,
        guardrails: GuardrailRunner,
        llm_only: LLMOnlyPipeline,
        vision: MockVision,
        session_store: JsonlSessionStore,
        audit_store: AuditStore,
        intent_classifier: Optional[OllamaIntentClassifier] = None,
        embedder: Optional[Embedder] = None,
        store: Optional[ChromaStore] = None,
        bm25: Optional[BM25Index] = None,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[Reranker] = None,
        hybrid: Optional[HybridPipeline] = None,
    ) -> None:
        self.settings         = settings
        self.llm              = llm
        self.prompt           = prompt
        self.clinical_planner = clinical_planner
        self.guardrails       = guardrails
        self.llm_only         = llm_only
        self.vision           = vision
        self.session_store    = session_store
        self.audit_store      = audit_store
        self.intent_classifier = intent_classifier
        self.embedder         = embedder
        self.store            = store
        self.bm25             = bm25
        self.retriever        = retriever
        self.reranker         = reranker
        self.hybrid           = hybrid

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
        try:
            if self.intent_classifier is not None:
                self.intent_classifier.close()
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
    _db_conn      = DBConnection(audit_db_path)
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
        timeout=settings.ollama_generate_timeout,
        health_timeout=settings.ollama_health_timeout,
        use_modelfile_system=getattr(settings, "llm_use_modelfile_system", False),
    )
    prompt = PromptBuilder(settings.prompts_dir)
    clinical_planner = ClinicalQueryPlanner()
    guardrails = GuardrailRunner(
        settings.guardrails_yaml,
        embedder=None,
        enable_ood=getattr(settings, "guardrails_enable_ood", True),
        ood_threshold=getattr(settings, "guardrails_ood_threshold", 0.25),
        scope_mode=getattr(settings, "guardrails_scope_mode", "soft"),
    )
    llm_only = LLMOnlyPipeline(
        llm,
        prompt,
        guardrails,
        clinical_planner=clinical_planner,
        use_llm_planner=settings.chat_use_llm_planner,
    )
    logger.info(f"LLM: {settings.llm_model} @ {settings.ollama_url}")

    intent_classifier = None
    if getattr(settings, "intent_router_enabled", False):
        intent_classifier = OllamaIntentClassifier(
            base_url=settings.ollama_url,
            model=getattr(settings, "intent_router_model", "qwen2.5:0.5b"),
            timeout=getattr(settings, "intent_router_timeout_seconds", 5.0),
            num_ctx=getattr(settings, "intent_router_num_ctx", 1024),
            num_predict=getattr(settings, "intent_router_num_predict", 128),
        )
        logger.info(f"Intent router micro-classifier enabled: {settings.intent_router_model}")

    # -- RAG (chi load neu KB da build) ---------------------------------------
    chroma_dir = Path(settings.chroma_dir)
    bm25_path  = Path(settings.bm25_path)

    chroma_ready = chroma_dir.exists() and any(chroma_dir.iterdir())
    bm25_ready   = bm25_path.exists()

    embedder = store = bm25 = retriever = reranker = hybrid = None

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

            hybrid = HybridPipeline(
                retriever=retriever,
                reranker=reranker,
                llm=llm,
                prompt=prompt,
                guardrails=guardrails,
                retrieve_top_k=settings.retrieve_top_k,
                rerank_top_k=settings.rerank_top_k,
                english_input_notice=settings.english_input_notice,
                clinical_planner=clinical_planner,
                use_llm_planner=settings.chat_use_llm_planner,
                use_mmr_prefilter=getattr(settings, "use_mmr_prefilter", True),
                mmr_lambda=getattr(settings, "mmr_lambda", 0.6),
            )
            logger.success("RAG ready -- hybrid pipeline enabled")
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
        llm_only=llm_only,
        vision=MockVision(),
        session_store=session_store,
        audit_store=audit_store,
        intent_classifier=intent_classifier,
        embedder=embedder,
        store=store,
        bm25=bm25,
        retriever=retriever,
        reranker=reranker,
        hybrid=hybrid,
    )
