"""Cong admin phai fail CLOSED khi chua cau hinh khoa."""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from acne_llm.api.routes import admin, chat
from acne_llm.config import settings

KEY = "test-admin-key"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    app.include_router(chat.router, prefix="/api/v1")
    container = MagicMock()
    container.audit_store.query.return_value = []
    container.audit_store.count.return_value = 0
    app.state.container = container
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def restore_key():
    old = settings.admin_api_key
    yield
    settings.admin_api_key = old


def test_admin_denied_when_key_not_configured(restore_key):
    settings.admin_api_key = ""
    assert _client().get("/api/v1/admin/audit").status_code == 403


def test_admin_denied_with_wrong_key(restore_key):
    settings.admin_api_key = KEY
    r = _client().get("/api/v1/admin/audit", headers={"x-admin-key": "sai"})
    assert r.status_code == 401


def test_admin_allowed_with_correct_key(restore_key):
    settings.admin_api_key = KEY
    r = _client().get("/api/v1/admin/audit", headers={"x-admin-key": KEY})
    assert r.status_code == 200


def test_debug_trace_also_gated(restore_key):
    settings.admin_api_key = ""
    r = _client().get("/api/v1/debug/trace", params={"message": "mun"})
    assert r.status_code == 403
