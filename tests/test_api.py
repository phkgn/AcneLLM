"""Smoke test the FastAPI app with a mocked container."""
from unittest.mock import MagicMock
from pathlib import Path

from fastapi.testclient import TestClient

from acne_llm.schemas import AdviseOutput, Recommendation


def _build_mock_app():
    from fastapi import FastAPI
    from acne_llm.api.routes import chat, kb, health

    app = FastAPI()

    out = AdviseOutput(
        severity="mild", acne_type_primary="comedone",
        recommendations=[Recommendation(step=1, action="rửa mặt", category="skincare")],
        confidence=0.5, mode="hybrid", model_name="mock",
    )
    hybrid_mock = MagicMock()
    hybrid_mock.run.return_value = out
    llm_mock = MagicMock()
    llm_mock.model = "mock"
    llm_mock.health.return_value = True
    llm_mock.list_models.return_value = ["mock"]
    store_mock = MagicMock()
    store_mock.count.return_value = 42

    class C:
        hybrid = hybrid_mock
        llm_only = hybrid_mock
        llm = llm_mock
        store = store_mock
        bm25 = None
        embedder = MagicMock(model_name="emb")
        reranker = MagicMock(model_name="rr")
        retriever = MagicMock()
        rag_ready = True

    app.state.container = C()
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(kb.router, prefix="/api/v1")
    return app


def test_health_endpoint():
    c = TestClient(_build_mock_app())
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["kb_chunks"] == 42


def test_chat_endpoint():
    c = TestClient(_build_mock_app())
    r = c.post("/api/v1/chat", json={"description": "Em bị mụn"})
    assert r.status_code == 200
    data = r.json()
    assert data["severity"] == "mild"
    assert data["recommendations"][0]["action"] == "rửa mặt"


def test_kb_stats():
    c = TestClient(_build_mock_app())
    r = c.get("/api/v1/kb/stats")
    assert r.status_code == 200
    assert r.json()["total_chunks"] == 42
