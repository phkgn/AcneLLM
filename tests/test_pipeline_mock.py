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
from acne_llm.pipeline.llm_only import LLMOnlyPipeline

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
        rag_queries=ClinicalRagQueries(query_vi="mụn viêm ở cằm inflammatory acne chin guideline"),
        safety_terms=[],
    )

    prompt = PromptBuilder(PROMPTS)
    g = GuardrailRunner(str(CFG))
    pipe = HybridPipeline(retriever, reranker, llm, prompt, g,
                          retrieve_top_k=5, rerank_top_k=3,
                          clinical_planner=clinical_planner,
                          use_llm_planner=True,
                          use_mmr_prefilter=False)

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
    assert retriever.retrieve.call_count == 1
    retrieved_queries = [call.args[0] for call in retriever.retrieve.call_args_list]
    assert "mụn viêm ở cằm inflammatory acne chin guideline" in retrieved_queries
    assert "inflammatory acne chin guideline" in reranker.rerank.call_args.args[0]
    assert out.disclaimer.startswith("Xin lỗi, hiện mình chỉ hỗ trợ tư vấn bằng tiếng Việt")


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


def test_hybrid_pipeline_does_not_backfill_plan_for_other_subject():
    retrieval = RetrievalOutput(
        query="q",
        chunks=[
            RetrievedChunk(
                chunk_id="c1",
                source="S",
                text="Acne care context.",
                score=0.9,
                metadata={"source": "S", "title": "Acne"},
            ),
        ],
    )
    retriever = MagicMock()
    retriever.retrieve.return_value = retrieval
    llm = MagicMock()
    llm.model = "mock"
    llm.generate_json.return_value = AdviseOutput(
        severity="unknown",
        acne_type_primary="unknown",
        causes=["current only"],
        confidence=0.3,
    ).model_dump_json()
    clinical_planner = MagicMock()
    prompt = PromptBuilder(PROMPTS)
    guardrails = GuardrailRunner(str(CFG))
    pipe = HybridPipeline(
        retriever,
        None,
        llm,
        prompt,
        guardrails,
        clinical_planner=clinical_planner,
        use_llm_planner=True,
        use_mmr_prefilter=False,
    )
    user = UserInput(
        description="ban toi bi mun o lung nen lam gi",
        clinical=AcneClinicalInput(lesion_distribution=["back"]),
    )

    out = pipe.run(
        user,
        prechecked=True,
        route_metadata={"primary_intent": "advise", "query_subject": "other"},
    )

    clinical_planner.plan.assert_not_called()
    assert out.mode == "hybrid"
    assert "back" in retriever.retrieve.call_args.args[0]


def test_llm_only_pipeline_soft_scope_calls_llm_for_out_of_scope():
    llm = MagicMock()
    llm.model = "mock"
    mock_out = AdviseOutput(
        severity="unknown",
        acne_type_primary="unknown",
        causes=["handled by llm"],
        confidence=0.2,
    )
    llm.generate_json.return_value = mock_out.model_dump_json()
    prompt = MagicMock()
    prompt.build.return_value = ("system", "user")
    guardrails = GuardrailRunner(str(CFG))
    pipe = LLMOnlyPipeline(llm, prompt, guardrails)

    user = UserInput(description="giải phương trình bậc hai", mode="llm_only")
    out = pipe.run(user)

    llm.generate_json.assert_called_once()
    assert out.mode == "llm_only"
    assert out.model_name == "mock"
