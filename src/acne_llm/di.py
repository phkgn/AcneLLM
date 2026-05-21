"""Dependency injection container.

Build tat ca components: LLM + optional RAG-backed hybrid mode.
RAG chi load neu KB (ChromaDB + BM25) da ton tai.
Neu chua co, chi ho tro llm_only mode.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from .llm.ollama_backend import OllamaBackend
from .llm.prompt_builder import PromptBuilder
from .llm.clinical_planner import ClinicalQueryPlanner
from .llm.query_expander import QueryExpander
from .guardrails.runner import GuardrailRunner
from .pipeline.llm_only import LLMOnlyPipeline
from .pipeline.hybrid import HybridPipeline
from .rag.embedder import Embedder
from .rag.vectorstore import ChromaStore
from .rag.sparse import BM25Index
from .rag.retriever import HybridRetriever
from .rag.reranker import Reranker
from .vision.mock import MockVision


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
        embedder: Optional[Embedder] = None,
        store: Optional[ChromaStore] = None,
        bm25: Optional[BM25Index] = None,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[Reranker] = None,
        hybrid: Optional[HybridPipeline] = None,
    ) -> None:
        self.settings   = settings
        self.llm        = llm
        self.prompt     = prompt
        self.clinical_planner = clinical_planner
        self.guardrails = guardrails
        self.llm_only   = llm_only
        self.vision     = vision
        self.embedder   = embedder
        self.store      = store
        self.bm25       = bm25
        self.retriever  = retriever
        self.reranker   = reranker
        self.hybrid     = hybrid

    @property
    def rag_ready(self) -> bool:
        return self.retriever is not None

    async def close(self) -> None:
        try:
            self.llm.close()
        except Exception:
            pass


def build_container(settings) -> Container:
    logger.info("Building DI container...")

    # -- LLM -----------------------------------------------------------------
    llm = OllamaBackend(
        base_url=settings.ollama_url,
        model=settings.llm_model,
        fallback_model=settings.llm_fallback_model,
        num_ctx=settings.llm_num_ctx,
        timeout=settings.ollama_generate_timeout,
        health_timeout=settings.ollama_health_timeout,
    )
    prompt = PromptBuilder(settings.prompts_dir)
    clinical_planner = ClinicalQueryPlanner(llm=llm, prompt=prompt)
    guardrails = GuardrailRunner(settings.guardrails_yaml)
    llm_only = LLMOnlyPipeline(llm, prompt, guardrails, clinical_planner=clinical_planner)

    logger.info(f"LLM: {settings.llm_model} @ {settings.ollama_url}")

    # -- RAG (chi load neu KB da build) --------------------------------------
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
            logger.info(f"ChromaDB: {store.count()} vectors | BM25: {len(bm25.chunk_ids)} chunks")

            try:
                # LOW-7: Use multilingual model if configured, else default
                emb_model = getattr(settings, "embedding_model_multilingual", "") or settings.embedding_model
                embedder = Embedder(
                    model_name=emb_model,
                    device=settings.device,
                )
            except Exception as e:
                logger.warning(f"Embedder load failed, falling back to sparse-only retrieval: {e}")
                embedder = None

            retriever = HybridRetriever(store=store, embedder=embedder, bm25=bm25)

            try:
                reranker = Reranker(
                    model_name=settings.reranker_model,
                    device=settings.device,
                )
            except Exception as e:
                logger.warning(f"Reranker load failed, using retrieved chunks directly: {e}")
                reranker = None

            query_expander = QueryExpander(
                llm=llm,
                temperature=settings.query_expansion_temperature,
            )

            hybrid = HybridPipeline(
                retriever=retriever, reranker=reranker, llm=llm,
                prompt=prompt, guardrails=guardrails,
                retrieve_top_k=settings.retrieve_top_k,
                rerank_top_k=settings.rerank_top_k,
                query_expander=query_expander,
                enable_bilingual_query=settings.enable_bilingual_query,
                english_input_notice=settings.english_input_notice,
                clinical_planner=clinical_planner,
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
        embedder=embedder,
        store=store,
        bm25=bm25,
        retriever=retriever,
        reranker=reranker,
        hybrid=hybrid,
    )
