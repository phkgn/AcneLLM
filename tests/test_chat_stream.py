from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acne_llm.api.routes import chat
from acne_llm.chat.session import ConversationTurn, get_session_store
from acne_llm.db.session_store import SQLiteSessionStore
from acne_llm.llm.clinical_planner import ClinicalQueryPlanner
from acne_llm.schemas import AdviseOutput, RetrievedChunk, RetrievalOutput
from acne_llm.schemas.clinical import ClinicalQueryPlan, ClinicalRagQueries, NormalizedAcneCase


class _MockLLM:
    model = "mock"

    def __init__(self):
        self.temperatures = []
        self.user_prompts = []

    def stream_text(self, system: str, user: str, temperature: float = 0.3):
        assert "Mô tả người dùng" in user
        self.temperatures.append(temperature)
        self.user_prompts.append(user)
        yield "Xin chào "
        yield "từ stream."

class _MockPrompt:
    def __init__(self):
        self.templates = []
        self.route_metadata = []

    def system_stream(self):
        return "Bạn là AcneLLM."

    def build(self, user, retrieval=None, **kwargs):
        history = kwargs.get("history") or []
        self.templates.append(kwargs.get("template"))
        self.route_metadata.append(kwargs.get("route_metadata") or {})
        return (
            "Bạn là AcneLLM.",
            f"Mô tả người dùng: {user.description}; sex={user.context.sex}; history={len(history)}",
        )


class _MockRetriever:
    def __init__(self):
        self.queries = []
        self.safety_calls = []

    def retrieve(self, query, top_k=8, mode="hybrid"):
        self.queries.append(query)
        return RetrievalOutput(
            query=query,
            chunks=[
                RetrievedChunk(
                    chunk_id="test-chunk",
                    source="test",
                    text="Guideline context about painful pustular acne and when to seek care.",
                    score=0.9,
                    metadata={"title": "test", "source": "test"},
                )
            ],
            retrieval_mode="hybrid",
            num_chunks=1,
            avg_score=0.9,
        )

    def retrieve_safety_pass(self, query, safety_terms, top_k=5):
        self.safety_calls.append((query, list(safety_terms), top_k))
        return RetrievalOutput(
            query=query,
            chunks=[
                RetrievedChunk(
                    chunk_id="safety-chunk",
                    source="NICE",
                    text="Pregnancy and retinoid safety context.",
                    score=0.9,
                    metadata={"title": "safety", "source": "NICE"},
                )
            ],
            retrieval_mode="hybrid",
            num_chunks=1,
            avg_score=0.9,
        )


class _MockContainer:
    rag_ready = False
    retriever = None
    reranker = None
    guardrails = SimpleNamespace(
        pre_check=lambda user: None,
        post_check=lambda output, user: output,
        scope_check=lambda user, has_acne_history=False: (
            AdviseOutput(
                severity="unknown",
                acne_type_primary="unknown",
                causes=["out of scope"],
                confidence=0.0,
                disclaimer="Câu hỏi ngoài phạm vi tư vấn da mụn.",
            )
            if "giải phương trình" in user.description.lower()
            else None
        ),
    )
    clinical_planner = None

    def __init__(self):
        self.llm = _MockLLM()
        self.prompt = _MockPrompt()
        self.settings = SimpleNamespace(
            llm_temperature=0.3,
            chat_max_context_chars=4500,
            chat_retrieve_top_k=8,
            chat_rerank_top_k=3,
            chat_min_citation_score=0.12,
            intent_router_min_confidence=0.80,
            intent_router_tie_margin=0.10,
        )


def _app(container=None):
    app = FastAPI()
    app.state.container = container or _MockContainer()
    app.include_router(chat.router, prefix="/api/v1")
    return app


# Input đủ để pass completeness gate:
# - có lesion (mụn viêm), location cụ thể (cằm), context bù (22 tuổi da dầu)
_SUFFICIENT_MSG = "Tôi 22 tuổi da dầu bị mụn viêm ở cằm"


def test_stream_endpoint_returns_token_and_done_events():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": _SUFFICIENT_MSG})

    assert r.status_code == 200
    body = r.text
    assert body.count('"event": "token"') == 2
    assert "Xin chào" in body
    assert '"event": "done"' in body
    assert '"mode": "llm_only"' in body


def test_stream_endpoint_rejects_overlong_message():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "x" * 4001})

    assert r.status_code == 413


def test_stream_endpoint_passes_temperature_param_to_llm():
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get(
        "/api/v1/chat/stream",
        params={"message": _SUFFICIENT_MSG, "temperature": 0.7},
    )

    assert r.status_code == 200
    assert container.llm.temperatures == [0.7]


def test_stream_endpoint_uses_config_temperature_when_param_missing():
    container = _MockContainer()
    container.settings.llm_temperature = 0.42
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": _SUFFICIENT_MSG})

    assert r.status_code == 200
    assert container.llm.temperatures == [0.42]


def test_stream_endpoint_greeting_uses_fixed_reply_without_llm():
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "xin chào"})

    assert r.status_code == 200
    body = r.text
    assert body.count('"event": "token"') == 1
    assert "Chào bạn. Bạn cần hỏi gì về mụn?" in body
    assert '"mode": "llm_only"' in body
    assert container.llm.user_prompts == []


def test_stream_endpoint_exit_does_not_invite_more_questions():
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "tôi không muốn hỏi nữa"})

    assert r.status_code == 200
    assert "Được nhé. Khi nào cần bạn cứ quay lại." in r.text
    assert "Bạn muốn hỏi gì" not in r.text
    assert container.llm.user_prompts == []


def test_ack_and_laughter_use_fixed_replies_without_llm():
    container = _MockContainer()
    client = TestClient(_app(container))

    ack = client.get("/api/v1/chat/stream", params={"message": "ok"})
    laughter = client.get("/api/v1/chat/stream", params={"message": "hahahaha"})

    assert "Ừ nhé." in ack.text
    assert "😄" in laughter.text
    assert container.llm.user_prompts == []


def test_greeting_with_acne_question_still_goes_through_pipeline():
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "chào bác sĩ, mụn viêm nên dùng gì?"})

    assert r.status_code == 200
    assert container.llm.user_prompts


def test_stream_endpoint_refuses_explicit_out_of_domain_without_llm():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "Giải phương trình x bình phương cộng 3x cộng 2"})

    assert r.status_code == 200
    body = r.text
    assert "ngoài phạm vi" in body
    assert '"mode": "refuse"' in body


def test_stream_endpoint_skincare_knowledge_question_goes_to_llm():
    c = TestClient(_app())

    r = c.get(
        "/api/v1/chat/stream",
        params={"message": "sản phẩm nào k gây bít tắc lỗ chân lông"},
    )

    assert r.status_code == 200
    body = r.text
    assert "Xin chào" in body
    assert '"mode": "clarify"' not in body
    assert '"mode": "llm_only"' in body


def test_stream_endpoint_acne_partial_goes_to_llm():
    """Partial acne input is enough for the fine-tuned LLM to answer safely."""
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "Tôi bị mụn ở cằm"})

    assert r.status_code == 200
    body = r.text
    assert '"event": "token"' in body
    assert '"mode": "clarify"' not in body
    assert "Xin chào" in body


def test_stream_endpoint_calls_plan_once():
    """Hot-path SSE omits the analytics-only clinical planner."""
    plan = ClinicalQueryPlan(
        detected_language="vi",
        normalized_case=NormalizedAcneCase(),
        rag_queries=ClinicalRagQueries(query_vi="mụn trứng cá guideline acne guideline"),
        safety_terms=[],
    )
    planner = MagicMock()
    planner.plan.return_value = plan

    container = _MockContainer()
    container.clinical_planner = planner
    app = FastAPI()
    app.state.container = container
    app.include_router(chat.router, prefix="/api/v1")
    c = TestClient(app)

    r = c.get("/api/v1/chat/stream", params={"message": _SUFFICIENT_MSG})

    assert r.status_code == 200
    planner.plan.assert_not_called()
    planner.fallback_plan.assert_not_called()  # fallback_plan không còn được gọi trực tiếp


def test_stream_endpoint_merges_session_context_before_completeness(tmp_path):
    """Context-only prior turn should enrich a short acne follow-up."""
    session_id = "test-session-context-before-completeness"
    container = _MockContainer()
    container.session_store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    c = TestClient(_app(container))

    try:
        first = c.get(
            "/api/v1/chat/stream",
            params={"message": "tôi là nam", "session_id": session_id},
        )
        assert first.status_code == 200
        assert '"mode": "llm_only"' in first.text

        second = c.get(
            "/api/v1/chat/stream",
            params={"message": "mụn ở lưng", "session_id": session_id},
        )

        assert second.status_code == 200
        body = second.text
        assert '"mode": "clarify"' not in body
        assert "Xin chào" in body
        assert '"mode": "llm_only"' in body
        assert "sex=male" in container.llm.user_prompts[-1]
        assert "history=0" in container.llm.user_prompts[-1]
    finally:
        container.session_store.delete(session_id)


def test_stream_endpoint_persists_answer_turns_in_session():
    session_id = "test-session-answer-turns"
    store = get_session_store()
    store.delete(session_id)
    c = TestClient(_app())

    try:
        first = c.get(
            "/api/v1/chat/stream",
            params={"message": "tôi bị mụn ở cằm", "session_id": session_id},
        )

        assert first.status_code == 200
        assert '"mode": "llm_only"' in first.text
        history = store.get_history(session_id)
        assert [turn.role for turn in history] == ["user", "assistant"]
        assert history[0].content == "tôi bị mụn ở cằm"
        assert history[1].mode == "llm_only"
        assert history[0].metadata["primary_intent"] == "advise"
    finally:
        store.delete(session_id)


def test_stream_followup_soft_scope_uses_rag_from_session_history(tmp_path):
    session_id = "test-stream-soft-followup-rag"
    container = _MockContainer()
    container.rag_ready = True
    container.retriever = _MockRetriever()
    container.clinical_planner = ClinicalQueryPlanner()
    container.session_store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    c = TestClient(_app(container))

    first = c.get(
        "/api/v1/chat/stream",
        params={
            "message": "tôi 36 tuổi bị mụn ngay mông, mụn có mủ đau nhiều",
            "session_id": session_id,
        },
    )
    assert first.status_code == 200

    container.retriever.queries.clear()
    second = c.get(
        "/api/v1/chat/stream",
        params={
            "message": "có phương pháp điều trị tại nhà k",
            "session_id": session_id,
        },
    )

    assert second.status_code == 200
    assert container.retriever.queries
    query = container.retriever.queries[-1]
    assert "có phương pháp điều trị tại nhà" in query
    assert "recent context:" in query
    assert "pustule" not in query


def test_stream_safety_terms_trigger_safety_pass_without_clinical_plan():
    container = _MockContainer()
    container.rag_ready = True
    container.retriever = _MockRetriever()
    c = TestClient(_app(container))

    r = c.get(
        "/api/v1/chat/stream",
        params={"message": "isotretinoin có dùng khi mang thai để trị mụn không"},
    )

    assert r.status_code == 200
    assert container.retriever.safety_calls
    safety_terms = container.retriever.safety_calls[-1][1]
    assert "isotretinoin" in safety_terms
    assert any(term in safety_terms for term in ("mang thai", "pregnancy"))


def test_stream_endpoint_routes_templates_by_intent():
    container = _MockContainer()
    c = TestClient(_app(container))

    advise = c.get("/api/v1/chat/stream", params={"message": _SUFFICIENT_MSG})
    knowledge = c.get("/api/v1/chat/stream", params={"message": "tại sao bị mụn bọc"})
    clarify = c.get("/api/v1/chat/stream", params={"message": "tôi không muốn sống vì mụn"})

    assert advise.status_code == 200
    assert knowledge.status_code == 200
    assert clarify.status_code == 200
    assert container.prompt.templates[:3] == [
        "stream_user.j2",
        "knowledge_user.j2",
        "clarify_user.j2",
    ]


def test_stream_knowledge_pustule_question_does_not_append_urgent_suffix():
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "mụn mủ là gì"})

    assert r.status_code == 200
    body = r.text.lower()
    assert "cơ sở y tế" not in body
    assert "nghiêm trọng" not in body
    assert container.prompt.templates[-1] == "knowledge_user.j2"


def test_stream_endpoint_other_subject_metadata_has_no_snapshot():
    session_id = "test-stream-other-subject"
    store = get_session_store()
    store.delete(session_id)
    container = _MockContainer()
    c = TestClient(_app(container))

    try:
        r = c.get(
            "/api/v1/chat/stream",
            params={"message": "bạn tôi bị mụn ở lưng nên làm gì", "session_id": session_id},
        )

        assert r.status_code == 200
        assert container.prompt.route_metadata[-1]["query_subject"] == "non_self"
        history = store.get_history(session_id)
        assert history[0].normalized_snapshot is None
    finally:
        store.delete(session_id)


def test_stream_endpoint_persists_self_snapshot_when_safety_clarify_is_overridden():
    session_id = "test-stream-self-clarify-memory"
    store = get_session_store()
    store.delete(session_id)
    container = _MockContainer()
    c = TestClient(_app(container))

    try:
        r = c.get(
            "/api/v1/chat/stream",
            params={"message": "tôi không muốn sống nữa vì mụn viêm ở cằm", "session_id": session_id},
        )

        assert r.status_code == 200
        history = store.get_history(session_id)
        assert history[0].normalized_snapshot is None
        assert history[0].metadata["primary_intent"] == "clarify"
        assert history[1].mode == "clarify"
    finally:
        store.delete(session_id)


def test_batch_prepare_and_stream_share_current_turn_retrieval_query():
    from acne_llm.chat.orchestrator import prepare_chat_turn

    container = _MockContainer()
    container.rag_ready = True
    container.retriever = _MockRetriever()
    client = TestClient(_app(container))
    message = "BHA có hỗ trợ mụn không?"

    stream = client.get("/api/v1/chat/stream", params={"message": message, "mode": "hybrid"})
    stream_query = container.retriever.queries[-1]
    prepare_chat_turn(container, message, requested_mode="hybrid")
    batch_query = container.retriever.queries[-1]

    assert stream.status_code == 200
    assert stream_query == batch_query
    assert stream_query.startswith(message)
    assert "salicylic acid" in stream_query


def test_stream_repairs_missing_inline_citation_marker_without_retry():
    container = _MockContainer()
    container.settings.inline_citation = "model"
    container.rag_ready = True
    container.retriever = _MockRetriever()
    client = TestClient(_app(container))

    response = client.get(
        "/api/v1/chat/stream",
        params={"message": "mụn đầu đen là gì?", "mode": "hybrid"},
    )

    assert response.status_code == 200
    assert '"citation_compliance": true' in response.text
    assert "[1]" in response.text
    assert len(container.llm.user_prompts) == 1


def test_stream_default_off_strips_leftover_marker_but_keeps_citation_event():
    container = _MockContainer()
    container.rag_ready = True
    container.retriever = _MockRetriever()

    def stream_with_split_marker(system: str, user: str, temperature: float = 0.3):
        yield "Khuyến nghị theo nguồn ["
        yield "1"
        yield "]."

    container.llm.stream_text = stream_with_split_marker
    client = TestClient(_app(container))

    response = client.get(
        "/api/v1/chat/stream",
        params={"message": "mụn đầu đen là gì?", "mode": "hybrid"},
    )

    assert response.status_code == 200
    assert "[1]" not in response.text
    assert '"event": "citation"' in response.text
    assert '"citation_compliance": null' in response.text


def test_debug_trace_exposes_selected_context_query_and_non_authoritative_planner():
    container = _MockContainer()
    client = TestClient(_app(container))

    response = client.get("/api/v1/debug/trace", params={"message": "Retinol là gì?"})

    assert response.status_code == 200
    trace = response.json()
    assert trace["stage_7_retrieve"]["query"] == "Retinol là gì?"
    assert trace["stage_7_retrieve"]["selected_context"] == []
    assert trace["stage_7_retrieve"]["confirmed_profile"] == {}


def test_debug_trace_knowledge_followup_matches_user_only_context(tmp_path):
    session_id = "test-debug-knowledge-followup"
    container = _MockContainer()
    container.session_store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    container.session_store.append_turn(
        session_id,
        ConversationTurn(role="user", content="Mụn đầu đen là gì?"),
    )
    container.session_store.append_turn(
        session_id,
        ConversationTurn(role="assistant", content="assistant answer must be excluded"),
    )
    client = TestClient(_app(container))

    response = client.get(
        "/api/v1/debug/trace",
        params={"message": "Còn loại này có nguy hiểm không?", "session_id": session_id},
    )

    assert response.status_code == 200
    trace = response.json()
    assert trace["stage_7_retrieve"]["selected_context"] == [
        {"role": "user", "content": "Mụn đầu đen là gì?"},
    ]
    assert "Mụn đầu đen là gì?" in trace["stage_7_retrieve"]["query"]
    assert "assistant answer must be excluded" not in trace["stage_8_prompt"]["user_message"]
