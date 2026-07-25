from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from datagen.intakedata.config import Config
from datagen.intakedata.pipeline import build_parser, run_pipeline
from datagen.intakedata.writer import iter_jsonl


def _context(*, low_conf: bool = False) -> dict[str, Any]:
    confidence = 0.5 if low_conf else 0.95
    return {
        "age": {"value": 22, "confidence": confidence},
        "sex": {"value": "female", "confidence": 0.96},
        "skin_type": {"value": "oily", "confidence": 0.9},
        "is_pregnant": None,
        "is_breastfeeding": None,
        "duration_weeks": {"value": 8, "confidence": 0.88},
        "allergies": [],
        "current_products": [],
        "medications": [],
    }


def _clinical() -> dict[str, Any]:
    return {
        "lesion_types": [{"value": "papule", "confidence": 0.9}],
        "inflammation_level": {"value": "mild", "confidence": 0.82},
        "lesion_distribution": [{"value": "cheeks", "confidence": 0.87}],
    }


class FakeProvider:
    def __init__(self) -> None:
        self.probes = 0
        self.generations = 0
        self.closed = 0

    async def probe(self) -> None:
        self.probes += 1

    async def generate(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.generations += 1
        match = re.search(r"CASE_TYPE:\s*(\S+)", messages[-1]["content"])
        assert match
        case = match.group(1)
        seed_match = re.search(r"SEED:\s*(\{[^\n]+\})", messages[-1]["content"])
        assert seed_match
        seed = json.loads(seed_match.group(1))
        intent = (
            "knowledge"
            if case.startswith("knowledge_")
            else "clarify"
            if case.startswith("clarify_") or case == "glue_greeting_thanks"
            else "reject"
            if case.startswith("reject_")
            else "advise"
        )
        user = ", ".join(seed.get("required_user_cues", [])) + (
            f", mẫu {self.generations}."
        )
        history: list[dict[str, str]] = []
        context = _context(low_conf=case == "advise_ambiguous_lowconf")
        context["age"] = {"value": seed.get("age", 22), "confidence": 0.95}
        context["sex"] = None
        context["skin_type"] = {
            "value": seed.get("skin_type", "oily"),
            "confidence": 0.9,
        }
        context["duration_weeks"] = None
        context["current_products"] = [
            {"value": seed.get("product", "niacinamide"), "confidence": 0.94}
        ]
        clinical: dict[str, Any] | None = {
            "lesion_types": [
                {"value": seed.get("lesion", "papule"), "confidence": 0.9}
            ],
            "inflammation_level": {"value": "mild", "confidence": 0.82},
            "lesion_distribution": [
                {"value": seed.get("distribution", "cheeks"), "confidence": 0.87}
            ],
        }
        if case == "advise_selfreport_simple":
            include = seed["include"]
            context = {
                "age": (
                    {"value": seed["age"], "confidence": 0.95}
                    if "age" in include
                    else None
                ),
                "sex": None,
                "skin_type": (
                    {"value": seed["skin_type"], "confidence": 0.9}
                    if "skin_type" in include
                    else None
                ),
                "is_pregnant": None,
                "is_breastfeeding": None,
                "duration_weeks": None,
                "allergies": [],
                "current_products": [],
                "medications": [],
            }
            if "lesion" in include or "distribution" in include:
                clinical = {
                    "lesion_types": (
                        [{"value": seed["lesion"], "confidence": 0.9}]
                        if "lesion" in include
                        else []
                    ),
                    "inflammation_level": {
                        "value": "unknown",
                        "confidence": 0.5,
                    },
                    "lesion_distribution": (
                        [{"value": seed["distribution"], "confidence": 0.87}]
                        if "distribution" in include
                        else []
                    ),
                }
            else:
                clinical = None
        if case == "advise_selfreport_rich":
            context["sex"] = {"value": seed["sex"], "confidence": 0.95}
            clinical["lesion_types"].append(
                {"value": seed["second_lesion"], "confidence": 0.88}
            )
            clinical["lesion_distribution"].append(
                {"value": seed["second_distribution"], "confidence": 0.86}
            )
            context["duration_weeks"] = {
                "value": seed["duration_weeks"],
                "confidence": 0.9,
            }
        if case == "advise_negation_stopped":
            user = ", ".join(seed["required_user_cues"]) + f", mẫu {self.generations}."
            context["current_products"] = [
                {"value": seed["current_product"], "confidence": 0.94}
            ]
        elif case == "advise_duration_convert":
            user = ", ".join(seed["required_user_cues"]) + f", mẫu {self.generations}."
            context["duration_weeks"] = {
                "value": seed["expected_duration_weeks"],
                "confidence": 0.95,
            }
        elif case == "advise_noaccent":
            user = ", ".join(seed["required_user_cues"]) + f", mau {self.generations}."
        elif case == "advise_mixed_vi_en":
            user = ", ".join(seed["required_user_cues"]) + f", mẫu {self.generations}."
            context["current_products"] = [
                {"value": seed["expected_canonical_product"], "confidence": 0.94}
            ]
        elif case == "advise_ambiguous_lowconf":
            user = ", ".join(seed["required_user_cues"]) + f", mẫu {self.generations}."
            context = {
                "age": None,
                "sex": None,
                "skin_type": None,
                "is_pregnant": None,
                "is_breastfeeding": None,
                "duration_weeks": None,
                "allergies": [],
                "current_products": [],
                "medications": [],
            }
            context[seed["ambiguous_field"]] = {
                "value": seed["ambiguous_value"],
                "confidence": 0.5,
            }
        elif case == "knowledge_product_trap":
            user = f"{seed['questioned_product']} có tốt cho da mụn không?"
        elif case == "knowledge_general":
            user = f"{seed['topic']}?"
        elif case == "knowledge_ingredient_compare":
            user = f"{seed['ingredient_a']} khác {seed['ingredient_b']} thế nào?"
        elif case == "clarify_vague":
            user = seed["vague_turn"]
            context = {}
            clinical = None
        elif case == "clarify_followup_multiturn":
            history = [
                {
                    "role": "user",
                    "content": f"Mình đang dùng {seed['history_topic']}.",
                },
                {
                    "role": "assistant",
                    "content": f"Bạn muốn hỏi điều gì về {seed['history_topic']}?",
                },
            ]
            user = f"{seed['followup']} Mẫu {self.generations}."
            context = {
                "age": None,
                "sex": None,
                "skin_type": None,
                "is_pregnant": None,
                "is_breastfeeding": None,
                "duration_weeks": None,
                "allergies": [],
                "current_products": [
                    {"value": seed["history_topic"], "confidence": 0.9}
                ],
                "medications": [],
            }
            clinical = None
        elif case == "reject_jailbreak_meta":
            user = f"{seed['attack']}. Mẫu {self.generations}."
        elif case == "reject_ood":
            user = f"Hãy giúp mình {seed['topic']}, mẫu {self.generations}."
        elif case == "reject_unsafe_rx":
            user = (
                f"Với {seed['drug']}, mình {seed['unsafe_request']}. "
                f"Mẫu {self.generations}."
            )
        elif case == "glue_greeting_thanks":
            user = seed["glue"]
        if (
            case.startswith(("knowledge_", "reject_"))
            or case == "glue_greeting_thanks"
        ):
            context = {}
            clinical = None

        return {
            "user_turn": user,
            "history": history,
            "assistant_json": {
                "intent": intent,
                "confidence": 0.62 if intent == "clarify" else 0.95,
                "description": user,
                "context": context,
                "clinical": clinical,
            },
        }

    async def close(self) -> None:
        self.closed += 1


def _config(tmp_path: Path) -> Config:
    return Config(
        output_root=tmp_path / "output",
        api_key="test-key",
        concurrency=4,
        max_content_attempts=2,
        max_api_retries=1,
    )


def test_smoke_wiring_resume_and_dedup(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    provider = FakeProvider()
    args = build_parser().parse_args(["--smoke", "--yes", "-v"])
    first = asyncio.run(
        run_pipeline(args, cfg=cfg, provider_factory=lambda _: provider)
    )
    assert first == 0
    records = list(iter_jsonl(cfg.records_path("smoke")))
    assert len(records) == 16
    assert len({record["id"] for record in records}) == 16
    assert {record["meta"]["case_type"] for record in records}.__len__() == 16
    assert all(record["meta"]["judged"] for record in records)
    assert provider.generations == 16

    second = asyncio.run(
        run_pipeline(args, cfg=cfg, provider_factory=lambda _: provider)
    )
    assert second == 0
    assert provider.generations == 16
    assert len(list(iter_jsonl(cfg.records_path("smoke")))) == 16
    assert len(list(iter_jsonl(cfg.train_path))) + len(list(iter_jsonl(cfg.val_path))) == 16

    summary = json.loads(cfg.summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "complete"
    assert summary["full_run_performed"] is False
    assert summary["validation"]["duplicate_ids"] == 0
    assert summary["validation"]["parity_ok"] is True


def test_limit_eight_runs_gate_topup_split_and_resumes(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    provider = FakeProvider()
    args = build_parser().parse_args(
        ["--limit", "8", "--yes", "--no-seed", "-v"]
    )
    first = asyncio.run(
        run_pipeline(args, cfg=cfg, provider_factory=lambda _: provider)
    )
    assert first == 0
    assert provider.generations == 8
    records = list(iter_jsonl(cfg.records_path("limit", 8)))
    assert len(records) == 8
    assert len({record["id"] for record in records}) == 8
    assert len(list(iter_jsonl(cfg.train_path))) == 7
    assert len(list(iter_jsonl(cfg.val_path))) == 1

    second = asyncio.run(
        run_pipeline(args, cfg=cfg, provider_factory=lambda _: provider)
    )
    assert second == 0
    assert provider.generations == 8
    assert len(list(iter_jsonl(cfg.records_path("limit", 8)))) == 8
