"""Integration test with mock LLM + mock retriever, no Ollama/Chroma needed."""
from unittest.mock import MagicMock
from pathlib import Path

from acne_llm.schemas import (
    UserInput, UserContext, AcneClinicalInput, AdviseOutput, Recommendation,
    RetrievalOutput, RetrievedChunk,
)
from acne_llm.schemas.clinical import ClinicalQueryPlan, ClinicalRagQueries, NormalizedAcneCase
from acne_llm.llm.prompt_builder import PromptBuilder
from acne_llm.guardrails.runner import GuardrailRunner
from acne_llm.pipeline.hybrid import HybridPipeline

CFG = Path(__file__).resolve().parents[1] / "config" / "guardrails.yaml"
PROMPTS = str(Path(__file__).resolve().parents[1] / "config" / "prompts")


def test_hybrid_pipeline_end_to_end_with_mocks():
    retrieval = RetrievalOutput(
        query="q", chunks=[
            RetrievedChunk(chunk_id="c1", source="Vinmec", text="Mun viem do C. acnes.",
                           score=0.9, metadata={"source": "Vinmec", "title": "Mun trung ca", "url": "u"}),
        ],
    )
    retriever = MagicMock()
    retriever.retrieve.return_value = retrieval
    retriever.expand_context.return_value = retrieval  # Fix 3: mock expand_context
    reranker = MagicMock()
    reranker.rerank.return_value = retrieval

    llm = MagicMock()
    llm.model = "mock"
    mock_out = AdviseOutput(
        severity="moderate",
        acne_type_primary="papule",
        causes=["C. acnes"],
        recommendations=[Recommendation(step=1, action="Rua mat 2 lan/ngay",
                                        category="skincare")],
        confidence=0.7,
    )
    llm.generate_json.return_value = mock_out.model_dump_json()
    clinical_planner = MagicMock()
    clinical_planner.plan.return_value = ClinicalQueryPlan(
        detected_language="en",
        normalized_case=NormalizedAcneCase(
            lesion_types=["papule"],
            distribution=["chin"],
            inflammation_level="moderate",
        ),
        rag_queries=ClinicalRagQueries(
            query_vi="mụn viêm ở cằm guideline",
            query_en="inflammatory acne on chin guideline",
        ),
        safety_terms=[],
    )

    prompt = PromptBuilder(PROMPTS)
    g = GuardrailRunner(str(CFG))
    pipe = HybridPipeline(retriever, reranker, llm, prompt, g,
                          retrieve_top_k=5, rerank_top_k=3,
                          query_expander=None,
                          enable_bilingual_query=True,
                          clinical_planner=clinical_planner)

    user = UserInput(description="Em bi mun o cam",
                     context=UserContext(age=22, skin_type="oily"),
                     clinical=AcneClinicalInput(
                         lesion_types=["papule", "hidden_acne"],
                         lesion_distribution=["chin"],
                     ))
    out = pipe.run(user)
    assert out.severity == "moderate"
    assert out.mode == "hybrid"
    assert out.model_name == "mock"
    assert "c1" in out.used_chunks
    assert out.latency_ms >= 0
    assert retriever.retrieve.call_count == 2
    retrieved_queries = [call.args[0] for call in retriever.retrieve.call_args_list]
    assert "mụn viêm ở cằm guideline" in retrieved_queries
    assert "inflammatory acne on chin guideline" in retrieved_queries
    assert "inflammatory acne on chin guideline" in reranker.rerank.call_args.args[0]
    assert out.disclaimer.startswith("Xin lỗi, hiện tôi chỉ hỗ trợ tư vấn bằng tiếng Việt")


def test_bilingual_retrieval_merge_deduplicates_and_boosts():
    vi = RetrievalOutput(
        query="mụn viêm",
        chunks=[
            RetrievedChunk(chunk_id="shared", source="A", text="vi", score=0.4, metadata={}),
            RetrievedChunk(chunk_id="vi_only", source="A", text="vi only", score=0.5, metadata={}),
        ],
    )
    en = RetrievalOutput(
        query="inflammatory acne",
        chunks=[
            RetrievedChunk(chunk_id="shared", source="A", text="en", score=0.6, metadata={}),
            RetrievedChunk(chunk_id="en_only", source="B", text="en only", score=0.55, metadata={}),
        ],
    )
    merged = HybridPipeline._merge_retrieval_outputs([vi, en], "combined")
    ids = [c.chunk_id for c in merged.chunks]
    assert ids.count("shared") == 1
    assert set(ids) == {"shared", "vi_only", "en_only"}
    shared = next(c for c in merged.chunks if c.chunk_id == "shared")
    en_only = next(c for c in merged.chunks if c.chunk_id == "en_only")
    assert shared.score > en_only.score
