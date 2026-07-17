import importlib.util
import inspect
from pathlib import Path

from acne_llm.chat.orchestrator import prepare_chat_turn


ROOT = Path(__file__).resolve().parents[1]


def test_prepare_chat_turn_has_one_prose_contract():
    assert "response_format" not in inspect.signature(prepare_chat_turn).parameters


def test_structured_prompt_templates_are_removed():
    prompts = ROOT / "config" / "prompts"
    assert not (prompts / "hybrid_user.j2").exists()
    assert not (prompts / "llm_only_user.j2").exists()
    assert not (prompts / "_inline_citation_model_structured.j2").exists()


def test_legacy_json_pipeline_modules_are_removed():
    assert importlib.util.find_spec("acne_llm.pipeline.hybrid") is None
    assert importlib.util.find_spec("acne_llm.pipeline.llm_only") is None
