"""Smoke test the FastAPI app with a mocked container."""
from unittest.mock import MagicMock
from pathlib import Path

from fastapi.testclient import TestClient

def _build_mock_app():
    from fastapi import FastAPI
    from acne_llm.api.routes import chat, kb, health

    app = FastAPI()

    llm_mock = MagicMock()
    llm_mock.model = "mock"
    llm_mock.health.return_value = True
    llm_mock.list_models.return_value = ["mock"]
    store_mock = MagicMock()
    store_mock.count.return_value = 42

    class C:
        llm = llm_mock
        store = store_mock
        bm25 = None
        embedder = MagicMock(model_name="emb")
        reranker = MagicMock(model_name="rr")
        retriever = MagicMock()
        rag_ready = False
        settings = MagicMock(
            chat_max_context_chars=4500,
            chat_retrieve_top_k=8,
            chat_rerank_top_k=3,
            extract_min_field_conf=0.60,
        )
        from acne_llm.llm.prompt_builder import PromptBuilder
        prompt = PromptBuilder(str(Path(__file__).resolve().parents[1] / "config" / "prompts"))
        guardrails = MagicMock()
        guardrails.pre_check.return_value = None
        guardrails.scope_check.return_value = None
        guardrails.post_check.side_effect = lambda output, user: output
        clinical_planner = None
        session_store = None

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


def test_sync_json_chat_endpoint_is_removed():
    c = TestClient(_build_mock_app())
    r = c.post("/api/v1/chat", json={"description": "Em bị mụn"})
    assert r.status_code in {404, 405}


def test_kb_stats():
    c = TestClient(_build_mock_app())
    r = c.get("/api/v1/kb/stats")
    assert r.status_code == 200
    assert r.json()["total_chunks"] == 42
