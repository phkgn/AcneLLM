"""Standalone Unified Intake dataset generation pipeline.

The package intentionally does not import the legacy ``datagen`` generators or
``datagen.roledata``.  It only mirrors their proven module boundaries.
"""

from .config import CASE_TYPE_TARGETS, FULL_TARGET, Config, compute_budget
from .schema import build_json_schema, validate_intake_record

__all__ = [
    "CASE_TYPE_TARGETS",
    "FULL_TARGET",
    "Config",
    "build_json_schema",
    "compute_budget",
    "validate_intake_record",
]
