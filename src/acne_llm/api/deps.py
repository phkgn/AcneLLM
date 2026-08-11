from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

from ..config import settings

if TYPE_CHECKING:
    from ..di import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def require_admin(request: Request) -> None:
    """Cong rieng cho endpoint lo du lieu nguoi dung (audit log, debug trace).

    Fail CLOSED: khong cau hinh ADMIN_API_KEY thi tu choi, khong phai cho qua.
    Day la khac biet duy nhat so voi APIKeyMiddleware toan cuc -- middleware do
    coi key rong la "tat xac thuc", nen /admin/audit tung mo toang khi .env de
    API_KEY trong.

    Khong dung API_KEY chung: EventSource cua trinh duyet khong gui duoc header
    tuy chinh, nen bat key toan cuc se lam hong /chat/stream.
    """
    expected = getattr(settings, "admin_api_key", "") or ""
    if not expected:
        raise HTTPException(status_code=403, detail="Admin API chua duoc cau hinh")
    supplied = request.headers.get("x-admin-key") or ""
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
