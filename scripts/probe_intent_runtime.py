#!/usr/bin/env python3
"""Probe Round 4 A/B/C/D through real intake with the local semantic router."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acne_llm.chat.orchestrator import prepare_chat_turn  # noqa: E402
from acne_llm.chat.fallback.llm_extractor import LLMExtractor  # noqa: E402
from acne_llm.chat.fallback.semantic_router import SemanticRouter  # noqa: E402
from acne_llm.chat.session import ConversationTurn  # noqa: E402
from acne_llm.config import Settings  # noqa: E402
from acne_llm.db.session_store import SQLiteSessionStore  # noqa: E402
from acne_llm.guardrails.runner import GuardrailRunner  # noqa: E402
from acne_llm.llm.clinical_planner import ClinicalQueryPlanner  # noqa: E402
from acne_llm.llm.ollama_backend import OllamaBackend  # noqa: E402
from acne_llm.llm.prompt_builder import PromptBuilder  # noqa: E402
from acne_llm.rag.embedder import Embedder  # noqa: E402


CASES = (
    {
        "case": "A",
        "message": (
            "em 22 tuổi da dầu bị mụn viêm 2 bên má gần 2 tháng, "
            "benzoyl peroxide có nên dùng không"
        ),
        "expected_intent": "advise",
        "expected_template": "stream_user.j2",
        "expected_completeness": True,
        "expected_extraction": True,
    },
    {
        "case": "B",
        "message": "benzoyl peroxide với tretinoin khác nhau thế nào",
        "expected_intent": "knowledge",
        "expected_template": "knowledge_user.j2",
        "expected_completeness": False,
        "expected_extraction": True,
    },
    {
        "case": "C",
        "message": "da em dạo này tệ quá",
        "expected_intent": "clarify",
        "expected_template": "clarify_user.j2",
        "expected_completeness": False,
        "expected_extraction": False,
    },
    {
        "case": "D",
        "message": "hôm nay trời mưa có nên đi chơi không",
        "expected_intent": "reject",
        "expected_template": "reject_user.j2",
        "expected_completeness": False,
        "expected_extraction": False,
    },
)


def _build_probe_container(settings: Settings, session_path: str):
    backend = OllamaBackend(
        base_url=settings.ollama_url,
        model=settings.extractor_model,
        fallback_model=None,
        num_ctx=min(settings.llm_num_ctx, 4096),
        num_predict=512,
        temperature=0.0,
        top_p=0.9,
        top_k=20,
        repeat_penalty=1.05,
        repeat_last_n=64,
        keep_alive=settings.llm_keep_alive,
        timeout=settings.extractor_timeout,
        health_timeout=settings.ollama_health_timeout,
        use_modelfile_system=True,
    )
    extractor = LLMExtractor(
        backend,
        model=settings.extractor_model,
        timeout=settings.extractor_timeout,
    )
    session_store = SQLiteSessionStore(
        session_path,
        ttl=settings.session_ttl,
        max_turns=settings.session_max_history_turns,
    )
    guardrails = GuardrailRunner(
        settings.guardrails_yaml,
        embedder=None,
        enable_ood=False,
        scope_mode=settings.guardrails_scope_mode,
    )
    embedding_model = (
        settings.embedding_model_multilingual or settings.embedding_model
    )
    embedder = Embedder(
        model_name=embedding_model,
        device=settings.device,
    )
    semantic_router = SemanticRouter(
        embedder=embedder,
        train_path=settings.semantic_router_train_path,
        cache_path=settings.semantic_router_cache_path,
        k=settings.semantic_router_k,
        oos_distance_threshold=settings.semantic_router_oos_distance_threshold,
        ambiguity_margin=settings.semantic_router_ambiguity_margin,
    )
    container = SimpleNamespace(
        settings=settings,
        rag_ready=False,
        llm_extractor=extractor,
        session_store=session_store,
        clinical_planner=ClinicalQueryPlanner(),
        guardrails=guardrails,
        prompt=PromptBuilder(settings.prompts_dir),
        retriever=None,
        reranker=None,
        embedder=embedder,
        semantic_router=semantic_router,
    )
    return container, extractor, session_store


def _completeness_data(value) -> dict | None:
    if value is None:
        return None
    return {
        "kind": value.kind,
        "level": value.level,
        "missing_fields": list(value.missing_fields),
        "question": value.question,
    }


def _extraction_confidence_data(confidence) -> dict:
    if confidence is None:
        return {}

    def _items(field) -> list[dict]:
        return [
            {
                "value": item.value,
                "confidence": item.confidence,
                "method": item.method,
            }
            for item in field.items
        ]

    inflammation = confidence.inflammation
    return {
        "lesion_types": _items(confidence.lesion_types),
        "distribution": _items(confidence.distribution),
        "inflammation": {
            "value": inflammation.value,
            "confidence": inflammation.confidence,
            "method": inflammation.method,
        },
    }


def run_probe(label: str) -> dict:
    settings = Settings().model_copy(update={"extractor_mode": "llm"})
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="acnellm-intent-round3-") as temp_dir:
        session_path = str(Path(temp_dir) / "sessions.db")
        container, extractor, session_store = _build_probe_container(settings, session_path)
        try:
            for spec in CASES:
                session_id = f"round3-{label}-{spec['case']}"
                prepared = prepare_chat_turn(
                    container,
                    spec["message"],
                    requested_mode="llm_only",
                    session_id=session_id,
                    include_analytics=True,
                )
                intake = prepared.intake
                route = intake.route_decision
                assert route is not None
                result = {
                    **spec,
                    "actual_intent": route.primary_intent,
                    "reason_code": route.reason_code,
                    "ambiguity_reason": route.ambiguity_reason,
                    "route_flags": list(route.route_flags),
                    "route_source": route.source,
                    "effective_mode": intake.effective_mode,
                    "template": prepared.template,
                    "completeness": _completeness_data(intake.completeness),
                    "clinical_plan_built": intake.clinical_plan is not None,
                    "snapshot_built": intake.turn_snapshot is not None,
                    "extraction_ran": intake.extraction_confidence is not None,
                    "extraction_field_confidence": _extraction_confidence_data(
                        intake.extraction_confidence
                    ),
                    "match": (
                        route.primary_intent == spec["expected_intent"]
                        and prepared.template == spec["expected_template"]
                        and (intake.completeness is not None)
                        == spec["expected_completeness"]
                        and (intake.extraction_confidence is not None)
                        == spec["expected_extraction"]
                    ),
                }
                results.append(result)
                session_store.append_turn(
                    session_id,
                    ConversationTurn(
                        role="user",
                        content=intake.clean_text,
                        normalized_snapshot=intake.turn_snapshot,
                    ),
                )
        finally:
            extractor.close()
            session_store.close()
    return {
        "label": label,
        "model": settings.extractor_model,
        "embedding_model": settings.embedding_model,
        "extractor_mode": settings.extractor_mode,
        "semantic_router": {
            "k": settings.semantic_router_k,
            "oos_distance_threshold": settings.semantic_router_oos_distance_threshold,
            "ambiguity_margin": settings.semantic_router_ambiguity_margin,
        },
        "all_match": all(item["match"] for item in results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="probe")
    parser.add_argument("--output", default="")
    parser.add_argument("--assert-expected", action="store_true")
    args = parser.parse_args()

    payload = run_probe(args.label)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Report: {output}")
    if args.assert_expected and not payload["all_match"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
