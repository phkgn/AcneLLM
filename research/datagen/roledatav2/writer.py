"""Writer v2 = writer v1, không sửa gì. Tồn tại để `pipeline.py` import tương đối."""
from __future__ import annotations

from ..roledata.writer import DatasetWriter, append_audit, iter_jsonl

__all__ = ["DatasetWriter", "append_audit", "iter_jsonl"]
