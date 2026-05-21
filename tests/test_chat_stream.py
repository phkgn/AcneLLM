from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acne_llm.api.routes import chat


class _MockLLM:
    model = "mock"

    def stream_text(self, system: str, user: str, temperature: float = 0.3):
        assert "Mô tả người dùng" in user
        yield "Xin chào "
        yield "từ stream."


class _MockContainer:
    rag_ready = False
    retriever = None
    reranker = None
    guardrails = SimpleNamespace(pre_check=lambda user: None)
    llm = _MockLLM()
    settings = SimpleNamespace(
        llm_temperature=0.3,
        chat_max_context_chars=4500,
        chat_retrieve_top_k=8,
        chat_rerank_top_k=3,
        chat_min_citation_score=0.12,
    )


def _app():
    app = FastAPI()
    app.state.container = _MockContainer()
    app.include_router(chat.router, prefix="/api/v1")
    return app


def test_stream_endpoint_returns_token_and_done_events():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "Tôi bị mụn ở cằm"})

    assert r.status_code == 200
    body = r.text
    assert '"event": "token"' in body
    assert "Xin chào" in body
    assert '"event": "done"' in body
    assert '"mode": "llm_only"' in body


def test_stream_endpoint_meta_response_skips_llm():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "xin chào"})

    assert r.status_code == 200
    body = r.text
    assert '"event": "token"' in body
    assert "AcneLLM" in body
    assert '"mode": "meta"' in body


def test_stream_endpoint_refuses_out_of_domain_questions():
    c = TestClient(_app())

    r = c.get("/api/v1/chat/stream", params={"message": "What is the purpose of a in y = ax + b?"})

    assert r.status_code == 200
    body = r.text
    assert "da mụn" in body.lower()
    assert '"mode": "meta"' in body
