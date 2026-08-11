"""Split + export dùng lại nguyên v1: cả hai nhận `cfg` nên chỉ cần truyền Config v2.

`export()` chỉ ghi `{"id", "messages"}` — đúng như v1. Ở v2 điều đó không còn làm
mất tài liệu, vì tài liệu đã nằm trong `messages` từ `generator.to_record`.
"""
from __future__ import annotations

from ...roledata.finalize import split
from ...roledata.finalize.export import export

__all__ = ["export", "split"]
