"""Hybrid pipeline: RAG (dense+sparse+RRF) -> rerank -> LLM JSON."""
from __future__ import annotations
import json
import re
import time
from typing import TYPE_CHECKING

from loguru import logger

from ..schemas import UserInput, AdviseOutput, RetrievalOutput, RetrievedChunk
from ..schemas.clinical import ClinicalQueryPlan
from ..rag.reranker import Reranker
from ..llm.clinical_planner import ClinicalQueryPlanner
from ..llm.ollama_backend import OllamaBackend
from ..llm.prompt_builder import PromptBuilder
from ..guardrails.runner import GuardrailRunner
from ..utils.chunk_filter import drop_noisy_chunks, drop_query_mismatched_chunks
from ..utils.retrieval_query import build_retrieval_query_from_user
from ..chat.session import ConversationTurn

if TYPE_CHECKING:
    from ..rag.retriever import HybridRetriever


def _safe_parse(raw: str) -> AdviseOutput:
    try:
        return AdviseOutput.model_validate_json(raw)
    except Exception:
        pass
    try:
        data = json.loads(raw)
        return AdviseOutput.model_validate(data)
    except Exception:
        pass
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return AdviseOutput.model_validate_json(m.group())
        except Exception:
            try:
                return AdviseOutput.model_validate(json.loads(m.group()))
            except Exception:
                pass
    logger.warning(f"[safe_parse] All parse attempts failed: {raw[:400]}")
    return AdviseOutput(
        severity="unknown",
        acne_type_primary="unknown",
        causes=["Không thể phân tích phản hồi từ LLM, vui lòng thử lại."],
        confidence=0.1,
    )


def _rrf_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, cid in enumerate(ranks):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
    return scores


class HybridPipeline:
    def __init__(self, retriever: "HybridRetriever", reranker: Reranker | None,
                 llm: OllamaBackend, prompt: PromptBuilder,
                 guardrails: GuardrailRunner,
                 retrieve_top_k: int = 15, rerank_top_k: int = 5,
                 english_input_notice: bool = True,
                 clinical_planner: ClinicalQueryPlanner | None = None,
                 use_llm_planner: bool | None = None,  # DEPRECATED: no-op, giữ để không vỡ caller cũ
                 use_mmr_prefilter: bool = True,
                 mmr_lambda: float = 0.6):
        # use_llm_planner KHÔNG còn tác dụng: ClinicalQueryPlanner là rule-based,
        # không gọi LLM. Param giữ lại chỉ để tương thích ngược (test/caller cũ
        # truyền kwarg này). Mọi task xử lý là rule-based; LLM chỉ chạy ở generate cuối.
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.prompt = prompt
        self.guardrails = guardrails
        self.retrieve_top_k = retrieve_top_k
        self.rerank_top_k = rerank_top_k
        self.english_input_notice = english_input_notice
        self.clinical_planner = clinical_planner
        self.use_mmr_prefilter = use_mmr_prefilter
        self.mmr_lambda = mmr_lambda

    def _build_query(self, user: UserInput) -> str:
        return build_retrieval_query_from_user(user, clean_text_normalized=user.description)

    @staticmethod
    def _expand_lesion_terms(lesion_types) -> list[str]:
        mapping = {
            "whitehead": "mun dau trang whitehead",
            "blackhead": "mun dau den blackhead",
            "closed_comedone": "mun an mun dau trang kin closed comedone",
            "papule": "mun viem papule inflammatory acne",
            "pustule": "mun mu pustule",
            "nodule": "mun boc mun nang nodular acne",
            "cyst": "mun boc mun nang cystic acne",
            "scar": "seo mun acne scar",
            "post_inflammatory_hyperpigmentation": "tham sau mun post inflammatory hyperpigmentation",
            "comedone": "mun dau trang mun dau den comedone",
        }
        out: list[str] = []
        for t in lesion_types:
            out.append(mapping.get(str(t), str(t)))
        return out

    def _clinical_plan(self, user: UserInput) -> ClinicalQueryPlan | None:
        if self.clinical_planner is None:
            return None
        return self.clinical_planner.plan(user)

    def _do_retrieve(self, query: str) -> RetrievalOutput:
        # Bug #6 fix: goi retrieve_with_mmr khi use_mmr_prefilter=True
        if self.use_mmr_prefilter and hasattr(self.retriever, "retrieve_with_mmr"):
            return self.retriever.retrieve_with_mmr(
                query,
                top_k=self.retrieve_top_k,
                rerank_top_k=self.retrieve_top_k,  # reranker se cat sau
                mode="hybrid",
                mmr_lambda=self.mmr_lambda,
            )
        return self.retriever.retrieve(query, top_k=self.retrieve_top_k, mode="hybrid")

    def _retrieve_clinical_plan(self, plan: ClinicalQueryPlan) -> RetrievalOutput:
        query = plan.rag_queries.query_vi.strip() or (
            "mun trung ca danh gia ban dau dau hieu can kham da lieu acne assessment red flags"
        )
        retrieval = self._do_retrieve(query)

        if plan.safety_terms and hasattr(self.retriever, "retrieve_safety_pass"):
            safety = self.retriever.retrieve_safety_pass(
                query,
                plan.safety_terms,
                top_k=min(self.rerank_top_k + 2, 5),
            )
            if safety.chunks:
                retrieval = self._merge_retrieval_outputs(
                    [retrieval, safety],
                    combined_query=query,
                )
        return retrieval

    @staticmethod
    def _merge_retrieval_outputs(outputs: list[RetrievalOutput], combined_query: str) -> RetrievalOutput:
        by_id: dict[str, RetrievedChunk] = {}
        for output in outputs:
            for chunk in output.chunks:
                if chunk.chunk_id not in by_id:
                    by_id[chunk.chunk_id] = RetrievedChunk(
                        chunk_id=chunk.chunk_id,
                        source=chunk.source,
                        text=chunk.text,
                        score=0.0,
                        metadata=chunk.metadata,
                    )

        fused = _rrf_fusion([[chunk.chunk_id for chunk in output.chunks] for output in outputs])
        max_score = max(fused.values(), default=0.0)
        chunks = []
        for chunk_id, score in fused.items():
            chunk = by_id[chunk_id]
            chunk.score = float(score / max_score) if max_score > 0 else 0.0
            chunks.append(chunk)

        chunks.sort(key=lambda c: c.score, reverse=True)
        avg = sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        return RetrievalOutput(
            query=combined_query,
            chunks=chunks,
            retrieval_mode="hybrid",
            num_chunks=len(chunks),
            avg_score=avg,
        )

    def _inject_english_notice(self, out: AdviseOutput, detected_language: str) -> AdviseOutput:
        if not self.english_input_notice or detected_language != "en":
            return out
        notice = (
            "Xin lỗi, hiện mình chỉ hỗ trợ tư vấn bằng tiếng Việt. "
            "Dưới đây là câu trả lời cho câu hỏi của bạn bằng tiếng Việt:"
        )
        if notice not in out.disclaimer:
            out.disclaimer = f"{notice} {out.disclaimer}".strip()
        return out

    def run(
        self,
        user: UserInput,
        clinical_plan: ClinicalQueryPlan | None = None,
        prechecked: bool = False,
        history: list[ConversationTurn] | None = None,
        route_metadata: dict | None = None,
        completeness_hint: str | None = None,
        safety_terms: list[str] | None = None,
    ) -> AdviseOutput:
        t0 = time.perf_counter()
        if not prechecked:
            self.guardrails.pre_check(user)
            scope_refusal = self.guardrails.scope_check(user)
            if scope_refusal is not None:
                scope_refusal.model_name = self.llm.model
                scope_refusal.latency_ms = int((time.perf_counter() - t0) * 1000)
                return scope_refusal

        can_build_clinical_plan = (
            not route_metadata
            or (
                route_metadata.get("primary_intent") == "advise"
                and route_metadata.get("query_subject", "self") == "self"
            )
        )
        if clinical_plan is None and can_build_clinical_plan:
            clinical_plan = self._clinical_plan(user)
        safety_terms = list(dict.fromkeys(safety_terms or []))
        if clinical_plan is not None and safety_terms:
            clinical_plan.safety_terms = list(dict.fromkeys([
                *clinical_plan.safety_terms,
                *safety_terms,
            ]))

        if clinical_plan is not None:
            retrieval = self._retrieve_clinical_plan(clinical_plan)
            # Dùng rerank_query câu tự nhiên nếu có, fallback về query_vi structured
            rerank_query = (
                clinical_plan.rag_queries.rerank_query
                or clinical_plan.rag_queries.query_vi
                or user.description
            )
            detected_language = clinical_plan.detected_language
            query_vi = clinical_plan.rag_queries.query_vi
        else:
            canonical_query = self._build_query(user)
            retrieval = self._do_retrieve(canonical_query)
            if safety_terms and hasattr(self.retriever, "retrieve_safety_pass"):
                safety = self.retriever.retrieve_safety_pass(
                    canonical_query,
                    safety_terms,
                    top_k=min(self.rerank_top_k + 2, 5),
                )
                if safety.chunks:
                    retrieval = self._merge_retrieval_outputs(
                        [retrieval, safety],
                        combined_query=canonical_query,
                    )
            rerank_query = canonical_query
            detected_language = "unknown"
            query_vi = canonical_query
        logger.info(
            "⑧ RETRIEVE: chunks={} mode={} query={!r:.80}",
            len(retrieval.chunks),
            retrieval.retrieval_mode,
            rerank_query,
        )

        if self.reranker is not None:
            try:
                top = self.reranker.rerank(rerank_query, retrieval, top_k=self.rerank_top_k)
            except Exception as e:
                logger.warning(f"Reranker unavailable, using retrieved chunks directly: {e}")
                top = retrieval
        else:
            top = retrieval

        filtered_top = drop_query_mismatched_chunks(
            drop_noisy_chunks(top, min_score=0.0),
            rerank_query,
        )
        top = filtered_top if filtered_top is not None and filtered_top.chunks else top
        logger.info("⑨ RERANK: top_k={} chunks after filter", len(top.chunks))

        sys_p, usr_p = self.prompt.build(
            user,
            top,
            template="hybrid_user.j2",
            detected_language=detected_language,
            query_vi=query_vi,
            max_context_chars=6000,
            clinical_plan=clinical_plan,
            history=history,
            route_metadata=route_metadata,
            completeness_hint=completeness_hint,
        )
        total_chars = len(sys_p) + len(usr_p)
        logger.info("⑩ PROMPT: system={}c user={}c total={}c", len(sys_p), len(usr_p), total_chars)
        schema = AdviseOutput.model_json_schema()
        logger.info("⑪ LLM: calling {} ...", self.llm.model)
        raw = self.llm.generate_json(sys_p, usr_p, schema=schema)
        parsed = _safe_parse(raw)
        parsed = self._inject_english_notice(parsed, detected_language)

        parsed.used_chunks = [c.chunk_id for c in top.chunks]
        parsed.mode = "hybrid"
        parsed.model_name = self.llm.model
        parsed.latency_ms = int((time.perf_counter() - t0) * 1000)

        result = self.guardrails.post_check(parsed, user)
        logger.info(
            "⑫ DONE: severity={} confidence={:.2f} latency={}ms",
            result.severity,
            result.confidence,
            result.latency_ms,
        )
        return result
