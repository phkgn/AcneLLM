from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from ..di import Container


def get_container(request: Request) -> Container:
    return request.app.state.container
