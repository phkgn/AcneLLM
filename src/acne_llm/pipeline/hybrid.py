"""Hybrid pipeline: RAG (dense+sparse+RRF) -> rerank -> LLM JSON."""
from __future__ import annotations
import json
import time

from loguru import logger

from ..schemas import UserInput, AdviseOutput, RetrievalOutput, RetrievedChunk
from ..schemas.clinical import ClinicalQueryPlan
from ..rag.retriever import HybridRetriever, rrf_fusion
from ..rag.reranker import Reranker
from ..llm.clinical_planner import ClinicalQueryPlanner
from ..llm.ollama_backend import OllamaBackend
from ..llm.prompt_builder import PromptBuilder
from ..llm.query_expander import BilingualQueryPlan, QueryExpander, fallback_query_plan
from ..guardrails.runner import GuardrailRunner


def _safe_parse(raw: str) -> AdviseOutput:
    try:
        return AdviseOutput.model_validate_json(raw)
    except Exception:
        try:
            data = json.loads(raw)
            return AdviseOutput.model_validate(data)
        except Exception as e:
            logger.warning(f"parse fail, returning fallback: {e}\n---\n{raw[:500]}")
            return AdviseOutput(
                severity="unknown",
                acne_type_primary="unknown",
                causes=["Khong the phan tich phan hoi tu LLM"],
                confidence=0.1,
            )


class HybridPipeline:
    def __init__(self, retriever: HybridRetriever, reranker: Reranker | None,
                 llm: OllamaBackend, prompt: PromptBuilder,
                 guardrails: GuardrailRunner,
                 retrieve_top_k: int = 20, rerank_top_k: int = 5,
                 query_expander: QueryExpander | None = None,
                 enable_bilingual_query: bool = True,
                 english_input_notice: bool = True,
                 clinical_planner: ClinicalQueryPlanner | None = None):
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.prompt = prompt
        self.guardrails = guardrails
        self.retrieve_top_k = retrieve_top_k
        self.rerank_top_k = rerank_top_k
        self.query_expander = query_expander
        self.enable_bilingual_query = enable_bilingual_query
        self.english_input_notice = english_input_notice
        self.clinical_planner = clinical_planner

    def _build_query(self, user: UserInput) -> str:
        """Build a compact clinical query summary for RAG."""
        parts: list[str] = [f"description: {user.description}"]
        c = user.context
        ctx_bits: list[str] = []
        if c.age is not None:
            ctx_bits.append(f"age {c.age}")
        if c.sex:
            ctx_bits.append(f"sex {c.sex}")
        if c.skin_type:
            ctx_bits.append(f"skin type {c.skin_type}")
        if c.is_pregnant:
            ctx_bits.append("mang thai")
        if c.is_breastfeeding:
            ctx_bits.append("cho con bu")
        if c.allergies:
            ctx_bits.append("allergies " + ", ".join(c.allergies))
        if c.current_products:
            ctx_bits.append("current products " + ", ".join(c.current_products))
        if c.medications:
            ctx_bits.append("medications " + ", ".join(c.medications))
        if c.duration_weeks is not None:
            ctx_bits.append(f"duration {c.duration_weeks} weeks")
        if ctx_bits:
            parts.append("context: " + "; ".join(ctx_bits))

        if user.clinical:
            cl = user.clinical
            clinical_bits: list[str] = []
            if cl.lesion_types:
                clinical_bits.append("lesions " + ", ".join(self._expand_lesion_terms(cl.lesion_types)))
            if cl.lesion_distribution:
                clinical_bits.append("distribution " + ", ".join(cl.lesion_distribution))
            if cl.inflammation_level:
                clinical_bits.append(f"inflammation {cl.inflammation_level}")
            if cl.scarring_signs:
                clinical_bits.append("scarring " + ", ".join(cl.scarring_signs))
            if cl.medication_history:
                clinical_bits.append("medication history " + ", ".join(cl.medication_history))
            if cl.hormonal_factors:
                clinical_bits.append("hormonal factors " + ", ".join(cl.hormonal_factors))
            if cl.skincare_products:
                clinical_bits.append("skincare " + ", ".join(cl.skincare_products))
            if cl.treatment_goals:
                clinical_bits.append("goals " + ", ".join(cl.treatment_goals))
            if cl.red_flags_input:
                clinical_bits.append("red flags " + ", ".join(cl.red_flags_input))
            if clinical_bits:
                parts.append("clinical: " + "; ".join(clinical_bits))

        vision_bits: list[str] = []
        if user.vision:
            vision_bits.append(f"vision severity {user.vision.severity_estimate}")
            if user.vision.lesion_counts:
                lesion_terms = self._expand_lesion_terms(user.vision.lesion_counts.keys())
                counts = ", ".join(f"{k}={v}" for k, v in user.vision.lesion_counts.items())
                vision_bits.append(f"vision lesions {counts}; terms {', '.join(lesion_terms)}")
            if user.vision.skin_regions:
                vision_bits.append("vision regions " + ", ".join(user.vision.skin_regions))
            if user.vision.notes:
                vision_bits.append("vision notes " + user.vision.notes)
        if vision_bits:
            parts.append("vision: " + "; ".join(vision_bits))

        return "\n".join(parts)

    @staticmethod
    def _expand_lesion_terms(lesion_types) -> list[str]:
        mapping = {
            "whitehead": "mụn đầu trắng whitehead",
            "blackhead": "mụn đầu đen blackhead",
            "closed_comedone": "mụn ẩn mụn đầu trắng kín closed comedone",
            "hidden_acne": "mụn ẩn closed comedone hidden acne",
            "papule": "mụn viêm papule inflammatory acne",
            "pustule": "mụn mủ pustule",
            "nodule": "mụn bọc mụn nang nodular acne",
            "cyst": "mụn bọc mụn nang cystic acne",
            "scar": "sẹo mụn acne scar",
            "post_inflammatory_hyperpigmentation": "thâm sau mụn post inflammatory hyperpigmentation",
            "comedone": "mụn đầu trắng mụn đầu đen comedone",
        }
        out: list[str] = []
        for t in lesion_types:
            out.append(mapping.get(str(t), str(t)))
        return out

    def _expand_query(self, canonical_query: str) -> BilingualQueryPlan:
        if not self.enable_bilingual_query:
            plan = fallback_query_plan(canonical_query)
            plan.query_en = ""
            return plan
        if self.query_expander is not None:
            return self.query_expander.expand(canonical_query)
        return fallback_query_plan(canonical_query)

    def _retrieve_bilingual(self, plan: BilingualQueryPlan) -> RetrievalOutput:
        queries = [q.strip() for q in [plan.query_vi, plan.query_en] if q and q.strip()]
        if not queries:
            queries = [plan.query_vi or plan.query_en]
        if len(queries) == 1:
            return self.retriever.retrieve(queries[0], top_k=self.retrieve_top_k, mode="hybrid")

        outputs = [
            self.retriever.retrieve(q, top_k=self.retrieve_top_k, mode="hybrid")
            for q in queries
        ]
        return self._merge_retrieval_outputs(outputs, combined_query="\n".join(queries))

    def _retrieve_clinical_plan(self, plan: ClinicalQueryPlan) -> RetrievalOutput:
        query_vi = plan.rag_queries.query_vi
        query_en = plan.rag_queries.query_en if self.enable_bilingual_query else ""
        queries = [q.strip() for q in [query_vi, query_en] if q and q.strip()]
        if not queries:
            fallback = "mụn trứng cá đánh giá ban đầu dấu hiệu cần khám da liễu acne assessment red flags"
            queries = [fallback]
        if len(queries) == 1:
            return self.retriever.retrieve(queries[0], top_k=self.retrieve_top_k, mode="hybrid")
        outputs = [
            self.retriever.retrieve(q, top_k=self.retrieve_top_k, mode="hybrid")
            for q in queries
        ]
        return self._merge_retrieval_outputs(outputs, combined_query="\n".join(queries))

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

        fused = rrf_fusion([[chunk.chunk_id for chunk in output.chunks] for output in outputs])
        chunks = []
        for chunk_id, score in fused.items():
            chunk = by_id[chunk_id]
            chunk.score = float(score)
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
            "Xin lỗi, hiện tôi chỉ hỗ trợ tư vấn bằng tiếng Việt. "
            "Dưới đây là câu trả lời cho câu hỏi của bạn bằng tiếng Việt:"
        )
        if notice not in out.disclaimer:
            out.disclaimer = f"{notice} {out.disclaimer}".strip()
        return out

    def run(self, user: UserInput) -> AdviseOutput:
        t0 = time.perf_counter()
        self.guardrails.pre_check(user)
        scope_refusal = self.guardrails.scope_check(user)
        if scope_refusal is not None:
            scope_refusal.model_name = self.llm.model
            scope_refusal.latency_ms = int((time.perf_counter() - t0) * 1000)
            return scope_refusal

        clinical_plan: ClinicalQueryPlan | None = None
        if self.clinical_planner is not None:
            clinical_plan = self.clinical_planner.plan(user)
            retrieval = self._retrieve_clinical_plan(clinical_plan)
            rerank_query = "\n".join(
                q for q in [
                    clinical_plan.rag_queries.query_vi,
                    clinical_plan.rag_queries.query_en if self.enable_bilingual_query else "",
                ]
                if q and q.strip()
            ) or user.description
            detected_language = clinical_plan.detected_language
            query_vi = clinical_plan.rag_queries.query_vi
            query_en = clinical_plan.rag_queries.query_en if self.enable_bilingual_query else ""
        else:
            canonical_query = self._build_query(user)
            query_plan = self._expand_query(canonical_query)
            retrieval = self._retrieve_bilingual(query_plan)
            rerank_query = "\n".join(
                q for q in [query_plan.query_vi, query_plan.query_en] if q and q.strip()
            ) or canonical_query
            detected_language = query_plan.detected_language
            query_vi = query_plan.query_vi
            query_en = query_plan.query_en
        if self.reranker is not None:
            try:
                top = self.reranker.rerank(rerank_query, retrieval, top_k=self.rerank_top_k)
            except Exception as e:
                logger.warning(f"Reranker unavailable, using retrieved chunks directly: {e}")
                top = retrieval
        else:
            top = retrieval

        # Fix 3: mo rong ngu canh bang cach fetch prev/next chunk lien ke
        # giup LLM co du context khi cau tra loi nam rai tren nhieu chunk
        top = self.retriever.expand_context(top)

        sys_p, usr_p = self.prompt.build(
            user,
            top,
            template="hybrid_user.j2",
            detected_language=detected_language,
            query_vi=query_vi,
            query_en=query_en,
            max_context_chars=6000,
            clinical_plan=clinical_plan,
        )
        total_chars = len(sys_p) + len(usr_p)
        logger.info(f"Hybrid prompt size: system={len(sys_p)} user={len(usr_p)} total={total_chars}")
        schema = AdviseOutput.model_json_schema()
        raw = self.llm.generate_json(sys_p, usr_p, schema=schema, temperature=0.3)
        parsed = _safe_parse(raw)
        parsed = self._inject_english_notice(parsed, detected_language)

        parsed.used_chunks = [c.chunk_id for c in top.chunks]
        parsed.mode = "hybrid"
        parsed.model_name = self.llm.model
        parsed.latency_ms = int((time.perf_counter() - t0) * 1000)

        return self.guardrails.post_check(parsed, user)
