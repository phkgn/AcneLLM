from pathlib import Path

from acne_llm.guardrails.runner import GuardrailRunner
from acne_llm.guardrails.pii import mask_pii, contains_pii
from acne_llm.schemas import UserInput, UserContext

CFG = Path(__file__).resolve().parents[1] / "config" / "guardrails.yaml"

# Phase 3 xoa 6 test cua post_check + _apply_*.
# Phase 4 xoa cac test cua scope_check va OodDetector -- ca hai tang deu da bi
# go khoi runtime (soft OOS thuoc ve intaker/SemanticRouter).
# Phase 7 xoa test_pre_check_rejects_prompt_injection: blocklist 146 chuoi da bo.
# Chong jailbreak gio o Modelfile system prompt (muc "Chong jailbreak"), con
# sanitize du lieu ngoai vao prompt o prompt_builder._INJECTION_MARKERS.
# Con lai: cong thuoc tat dinh + PII masking + validation rong.


def test_pre_check_rejects_empty_description():
    g = GuardrailRunner(str(CFG))
    try:
        g.pre_check(UserInput(description="   "))
        assert False, "Expected ValueError for empty description"
    except ValueError:
        pass


def test_pre_check_khong_con_chan_van_ban_binh_thuong():
    """Bang cu chan nham tieng Viet sinh hoat ("hay la", "tu bay gio")."""
    g = GuardrailRunner(str(CFG))
    for text in (
        "hãy là bạn thân của em nhé, da em bị mụn",
        "từ bây giờ em nên dùng gì cho da mụn",
        "bây giờ bạn là ai vậy",
    ):
        g.pre_check(UserInput(description=text))  # khong duoc raise


def test_mask_pii_phone():
    text = "Gọi cho tôi theo số 0912345678 để tư vấn"
    masked = mask_pii(text)
    assert "0912345678" not in masked
    assert "[PHONE_MASKED]" in masked


def test_mask_pii_email():
    text = "Email của tôi là user@example.com"
    masked = mask_pii(text)
    assert "user@example.com" not in masked
    assert "[EMAIL_MASKED]" in masked


def test_mask_pii_cmnd():
    text = "CMND số 123456789 được cấp năm 2010"
    masked = mask_pii(text)
    assert "123456789" not in masked
    assert "[ID_MASKED]" in masked


def test_mask_pii_no_change_normal_text():
    text = "Mụn viêm ở cằm, da dầu, 25 tuổi"
    # Không có PII → giữ nguyên
    assert mask_pii(text) == text


def test_contains_pii_true():
    assert contains_pii("Số điện thoại 0987654321")


def test_contains_pii_false():
    assert not contains_pii("Mụn viêm ở cằm, da dầu")


def test_medication_safety_refusal_blocks_pregnancy_and_interaction():
    g = GuardrailRunner(str(CFG))
    user = UserInput(
        description="Tôi có thể dùng hai thuốc này không?",
        context=UserContext(is_pregnant=True, medications=["minocycline"]),
    )

    result = g.medication_safety_refusal(user, ["minocycline", "isotretinoin"])

    assert result is not None
    assert result.model_name == "deterministic-safety"
    assert "Không sử dụng" in result.disclaimer
    assert "thai kỳ" in result.disclaimer


def test_medication_safety_refusal_blocks_generic_retinoid_while_breastfeeding():
    g = GuardrailRunner("config/guardrails.yaml")
    user = UserInput(
        description="em đang cho con bú, dùng retinoid trị mụn được không",
        context=UserContext(is_breastfeeding=True),
    )

    result = g.medication_safety_refusal(
        user,
        ["breastfeeding", "retinoid"],
    )

    assert result is not None
    assert result.model_name == "deterministic-safety"
    assert "Không sử dụng" in result.disclaimer
    assert "cho con bú" in result.disclaimer


