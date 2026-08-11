from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from acne_llm.api.routes import chat
from acne_llm.config import settings as _settings

# /debug/trace nam sau cong admin (fail closed). Test nao goi no phai dung
# fixture nay de cap khoa.
_ADMIN_KEY = "test-admin-key"
_ADMIN_HEADERS = {"x-admin-key": _ADMIN_KEY}


@pytest.fixture
def admin_key():
    old = _settings.admin_api_key
    _settings.admin_api_key = _ADMIN_KEY
    yield _ADMIN_HEADERS
    _settings.admin_api_key = old
from acne_llm.chat.fallback.intent_router import RouteDecision
from acne_llm.chat.session import ConversationTurn, get_session_store
from acne_llm.db.session_store import SQLiteSessionStore
from acne_llm.schemas import AdviseOutput, RetrievedChunk, RetrievalOutput


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
        self.guideline_calls = []

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

    def retrieve_safety_pass(self, query, safety_terms, top_k=5, source_types=None):
        # Production dùng CHUNG hàm này cho hai việc: guideline pass (truyền
        # source_types, safety_terms=None, chạy mọi truy vấn) và safety pass thật
        # (truyền safety_terms, chỉ chạy khi có từ khoá y tế). Mock cũ chỉ có một
        # xô nên guideline pass làm hỏng mọi assert về safety_calls — và trước đó
        # thì chữ ký thiếu source_types khiến pass này ném TypeError im lặng,
        # tức là guideline pass CHƯA TỪNG được test nào chạm tới.
        if source_types:
            self.guideline_calls.append((query, tuple(source_types), top_k))
        else:
            self.safety_calls.append((query, list(safety_terms or []), top_k))
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
    )
    clinical_planner = None

    def __init__(self):
        self.llm = _MockLLM()
        self.prompt = _MockPrompt()
        # Runtime doc thang c.session_store (khong con fallback ngam), nen test
        # double phai tu cap store. SessionStore in-memory la test double chinh thuc.
        self.session_store = get_session_store()
        self.settings = SimpleNamespace(
            llm_temperature=0.3,
            chat_max_context_chars=4500,
            chat_retrieve_top_k=8,
            chat_rerank_top_k=3,
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


def test_stream_endpoint_greeting_goes_through_the_model():
    """Lời chào do generator sinh, không còn chuỗi cứng trong runtime."""
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "xin chào"})

    assert r.status_code == 200
    assert '"mode": "llm_only"' in r.text
    assert container.llm.user_prompts


def test_every_turn_reaches_the_generator():
    """Không còn chuỗi cứng nào: chào, ack, cười, xin dừng đều qua model."""
    container = _MockContainer()
    client = TestClient(_app(container))

    for message in ("xin chào", "ok", "hahahaha", "tôi không muốn hỏi nữa"):
        before = len(container.llm.user_prompts)
        r = client.get("/api/v1/chat/stream", params={"message": message})
        assert r.status_code == 200, message
        assert len(container.llm.user_prompts) == before + 1, message


def test_greeting_with_acne_question_still_goes_through_pipeline():
    container = _MockContainer()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "chào bác sĩ, mụn viêm nên dùng gì?"})

    assert r.status_code == 200
    assert container.llm.user_prompts


def test_stream_endpoint_soft_rejects_out_of_domain_with_llm_and_without_rag():
    class _SoftRejectLLM(_MockLLM):
        def stream_text(self, system: str, user: str, temperature: float = 0.3):
            self.temperatures.append(temperature)
            self.user_prompts.append(user)
            yield "Mình hiểu bạn đang hỏi về toán. "
            yield "Mình chỉ chuyên về da mụn; bạn muốn hỏi gì về mụn không?"

    container = _MockContainer()
    container.llm = _SoftRejectLLM()
    container.rag_ready = True
    container.retriever = _MockRetriever()
    container.semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="reject",
            confidence=0.43,
            source="semantic",
            reason_code="semantic_router",
            ambiguity_reason="oos_distance=0.57>threshold=0.40",
        )
    )
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": "Giải phương trình x bình phương cộng 3x cộng 2"})

    assert r.status_code == 200
    body = r.text
    assert "chỉ chuyên về da mụn" in body
    assert '"mode": "llm_only"' in body
    assert '"primary_intent": "reject"' in body
    assert container.prompt.templates[-1] == "reject_user.j2"
    assert container.llm.user_prompts
    assert container.retriever.queries == []
    assert container.retriever.safety_calls == []
    assert container.retriever.guideline_calls == []   # reject thì không retrieve gì cả


def test_guideline_pass_chay_cho_moi_truy_van_khong_doi_safety_term():
    """Câu hỏi thường, không từ khoá y tế nào -> vẫn phải đi lấy khuyến cáo.

    Đo trên 152 truy vấn thật: pass này bơm ~760 đoạn guideline vào pool nhưng
    chỉ 16 đoạn sống sót ra câu trả lời. Nếu pass im lặng ngừng chạy thì con số
    đó về 0 mà không test nào kêu — trước bản vá chữ ký mock thì nó ném
    TypeError và bị `except Exception` nuốt mất đúng như vậy.
    """
    container = _MockContainer()
    container.rag_ready = True
    container.retriever = _MockRetriever()
    c = TestClient(_app(container))

    r = c.get("/api/v1/chat/stream", params={"message": _SUFFICIENT_MSG})

    assert r.status_code == 200
    assert container.retriever.guideline_calls, "guideline pass phải chạy"
    _, source_types, _ = container.retriever.guideline_calls[-1]
    assert "nice_guideline" in source_types and "aad_guideline" in source_types
    # Không có từ khoá y tế -> safety pass thật KHÔNG được chạy (nó tốn thêm
    # một lượt embed + query Chroma, ~50-100ms mỗi request).
    assert container.retriever.safety_calls == []


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


def test_duong_advise_khong_con_noi_cau_hoi_cung():
    """Hoi hay khong gio la viec cua generator.

    Ban cu: luat tinh ra mot cau hoi, prompt bao model "KHONG dat cau hoi bo
    sung", roi runtime noi cau cung vao cuoi -> model van hoi, nguoi dung nhan
    HAI cau hoi. Gio khong noi gi ca: model mock khong hoi thi output khong co
    dau hoi nao.""" 
    advise_container = _MockContainer()
    advise_container.semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="advise",
            confidence=0.8,
            source="semantic",
            reason_code="semantic_router",
        )
    )
    advise_response = TestClient(_app(advise_container)).get(
        "/api/v1/chat/stream",
        params={"message": "tôi bị mụn"},
    )

    assert advise_response.status_code == 200
    assert advise_container.prompt.templates[-1] == "stream_user.j2"
    # Mock LLM khong sinh cau hoi -> khong duoc co dau hoi nao chen them.
    assert advise_response.text.count("?") == 0

    class _ClarifyQuestionLLM(_MockLLM):
        def stream_text(self, system: str, user: str, temperature: float = 0.3):
            assert "Mô tả người dùng" in user
            yield "Bạn có thể mô tả rõ hơn?"

    clarify_container = _MockContainer()
    clarify_container.llm = _ClarifyQuestionLLM()
    clarify_container.semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="clarify",
            confidence=0.7,
            source="semantic",
            reason_code="semantic_router",
            ambiguity_reason="vote_margin=0.02<threshold=0.08",
        )
    )
    clarify_response = TestClient(_app(clarify_container)).get(
        "/api/v1/chat/stream",
        params={"message": "da em tệ quá"},
    )

    assert clarify_response.status_code == 200
    assert clarify_container.prompt.templates[-1] == "clarify_user.j2"
    assert clarify_response.text.count("?") == 1


def test_stream_endpoint_does_not_call_retired_clinical_planner():
    """Hot-path SSE must stay independent from the retired clinical planner."""
    planner = MagicMock()

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


def test_stream_followup_soft_scope_uses_rag_from_session_history(tmp_path):
    session_id = "test-stream-soft-followup-rag"
    container = _MockContainer()
    container.rag_ready = True
    container.retriever = _MockRetriever()
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


def test_stream_endpoint_advise_metadata_has_no_subject_and_persists_snapshot():
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
        # `route_metadata` khong con di vao prompt (orchestrator da bo tham so
        # do khi don prompt). Kiem tren SSE metadata -- day moi la thu client
        # thay, va la hop dong that su can giu.
        assert '"primary_intent": "advise"' in r.text
        assert "query_subject" not in r.text
        history = store.get_history(session_id)
        assert history[0].normalized_snapshot is not None
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
def test_debug_trace_exposes_selected_context_query_and_non_authoritative_planner(admin_key):
    container = _MockContainer()
    client = TestClient(_app(container))

    response = client.get(
        "/api/v1/debug/trace",
        params={"message": "Retinol là gì?"},
        headers=admin_key,
    )

    assert response.status_code == 200
    trace = response.json()
    assert trace["stage_7_retrieve"]["query"] == "Retinol là gì?"
    assert trace["stage_7_retrieve"]["selected_context"] == []
    assert trace["stage_7_retrieve"]["confirmed_profile"] == {}


def test_debug_trace_knowledge_followup_matches_user_only_context(tmp_path, admin_key):
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
        headers=admin_key,
    )

    assert response.status_code == 200
    trace = response.json()
    assert trace["stage_7_retrieve"]["selected_context"] == [
        {"role": "user", "content": "Mụn đầu đen là gì?"},
    ]
    assert "Mụn đầu đen là gì?" in trace["stage_7_retrieve"]["query"]
    assert "assistant answer must be excluded" not in trace["stage_8_prompt"]["user_message"]
