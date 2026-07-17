from pathlib import Path

from acne_llm.chat.inline_citations import (
    InlineCitationStripper,
    strip_inline_citations,
    strip_inline_citations_value,
)
from acne_llm.llm.prompt_builder import PromptBuilder
from acne_llm.schemas import RetrievalOutput, RetrievedChunk, UserInput
from evaluation.common import ROOT, load_yaml


PROMPTS = str(Path(__file__).resolve().parents[1] / "config" / "prompts")


def _retrieval() -> RetrievalOutput:
    return RetrievalOutput(
        query="mụn viêm",
        chunks=[
            RetrievedChunk(
                chunk_id="aad_12345678::0001",
                source="AAD",
                text="Benzoyl peroxide có thể hỗ trợ mụn viêm.",
                score=0.9,
                metadata={"title": "Acne guideline", "source": "AAD"},
            )
        ],
    )


def test_inline_citation_off_is_the_prompt_default() -> None:
    prompt = PromptBuilder(PROMPTS)

    _, rendered = prompt.build(UserInput(description="Tôi nên làm gì?"), _retrieval())

    assert "Đặt [N]" not in rendered
    assert "source_chunk_id chỉ lấy" not in rendered
    assert "chunk_ref=" not in rendered


def test_inline_citation_model_restores_legacy_prompt_contract() -> None:
    prompt = PromptBuilder(PROMPTS)

    _, rendered = prompt.build(
        UserInput(description="Tôi nên làm gì?"),
        _retrieval(),
        inline_citation="model",
    )

    assert "Đặt [N]" in rendered
    assert "source_chunk_id" in rendered
    assert "chunk_ref=aad_12345678::0001" in rendered


def test_strip_inline_citations_only_removes_numeric_markers() -> None:
    text = "Dùng BPO [1], nồng độ 0.1% trong 15-20 phút [12]. Theo [AAD]."

    assert strip_inline_citations(text) == (
        "Dùng BPO , nồng độ 0.1% trong 15-20 phút . Theo [AAD]."
    )


def test_streaming_stripper_handles_marker_split_across_tokens() -> None:
    stripper = InlineCitationStripper()
    pieces = ["Dùng BPO [", "1", "] tối", " nay [1", "2]."]

    actual = "".join(stripper.feed(piece) for piece in pieces) + stripper.finish()

    assert actual == "Dùng BPO  tối nay ."


def test_streaming_stripper_flushes_non_marker_bracket_text() -> None:
    stripper = InlineCitationStripper()

    actual = stripper.feed("Theo [AA") + stripper.feed("D]") + stripper.finish()

    assert actual == "Theo [AAD]"


def test_structured_cleaner_preserves_shape_and_named_tags() -> None:
    value = {
        "causes": ["Viêm [1]", "Theo [AAD]"],
        "recommendations": [{"action": "Bôi 0.1% [2]"}],
    }

    assert strip_inline_citations_value(value) == {
        "causes": ["Viêm ", "Theo [AAD]"],
        "recommendations": [{"action": "Bôi 0.1% "}],
    }


def test_eval_system_inline_mode_is_a_string_not_yaml_boolean() -> None:
    for name in ("s2.yaml", "s3.yaml"):
        config = load_yaml(ROOT / "evaluation" / "configs" / "systems" / name)
        assert config["inline_citation"] == "off"
        assert isinstance(config["inline_citation"], str)
