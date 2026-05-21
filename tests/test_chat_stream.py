from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acne_llm.api.routes import chat
from acne_llm.chat.session import get_session_store
from acne_llm.db.jsonl_session_store import JsonlSessionStore
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
    def system_stream(self):
        return "Bạn là AcneLLM."

    def build(self, user, retrieval=None, **kwargs):
        history = kwargs.get("history") or []
        return (
            "Bạn là AcneLLM.",
            f"Mô tả người dùng: {user.description}; sex={user.context.sex}; history={len(history)}",
        )


class _MockContainer:
    rag_ready = False
    retriever = None
    reranker = None
    guardrails = SimpleNamespace(pre_check=lambda user: None)
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
            chat_use_llm_planner=False,
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


def test_stream_endpoint_greeting_goes_to_llm():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "xin chào"})

    assert r.status_code == 200
    body = r.text
    assert body.count('"event": "token"') == 2
    assert "Xin chào" in body
    assert '"mode": "llm_only"' in body


def test_stream_endpoint_sends_out_of_domain_questions_to_llm():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "What is the purpose of a in y = ax + b?"})

    assert r.status_code == 200
    body = r.text
    assert "Xin chào" in body
    assert '"mode": "llm_only"' in body


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
    """Sau refactor: runtime gọi planner.plan() — đây là rule-based, không LLM."""
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
    container.settings.chat_use_llm_planner = True
    app = FastAPI()
    app.state.container = container
    app.include_router(chat.router, prefix="/api/v1")
    c = TestClient(app)

    # Input đủ để pass completeness gate → planner.plan() sẽ được gọi
    r = c.get("/api/v1/chat/stream", params={"message": _SUFFICIENT_MSG})

    assert r.status_code == 200
    planner.plan.assert_called_once()        # plan() được gọi đúng 1 lần
    planner.fallback_plan.assert_not_called()  # fallback_plan không còn được gọi trực tiếp


def test_stream_endpoint_merges_session_context_before_completeness(tmp_path):
    """Context-only prior turn should enrich a short acne follow-up."""
    session_id = "test-session-context-before-completeness"
    container = _MockContainer()
    container.session_store = JsonlSessionStore(str(tmp_path))
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
        assert "history=2" in container.llm.user_prompts[-1]
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
