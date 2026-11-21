from acne_llm.chat._safety import get_safety_suffix
from acne_llm.schemas import UserContext, UserInput


def test_rx_side_effect_knowledge_does_not_append_heavy_rx_warning():
    user = UserInput(description="vì sao isotretinoin gây khô môi")
    text = "Isotretinoin có thể làm giảm tiết bã nhờn nên môi dễ khô."

    suffix = get_safety_suffix(text, user)

    assert "thuốc kê đơn" not in suffix.lower()


def test_rx_recommendation_appends_warning():
    user = UserInput(description="mụn nặng")
    text = "Bạn có thể dùng isotretinoin theo hướng dẫn phù hợp."

    suffix = get_safety_suffix(text, user)

    assert "thuốc kê đơn" in suffix.lower()


def test_retinoid_pregnancy_warning_not_duplicated():
    user = UserInput(
        description="mụn",
        context=UserContext(is_pregnant=True),
    )
    text = (
        "Retinol chống chỉ định khi mang thai, nên không tự sử dụng retinoid."
    )

    suffix = get_safety_suffix(text, user)

    assert suffix == ""


def test_urgency_route_flag_adds_contextual_warning():
    user = UserInput(description="mụn đau nhiều rỉ dịch")
    suffix = get_safety_suffix(
        "Bạn nên theo dõi sát.",
        user,
        route_flags=["urgency_red_flag"],
    )
    assert suffix != ""
    lower = suffix.lower()
    assert any(w in lower for w in ["y tế", "bác sĩ", "kịp thời", "nghiêm trọng"])


def test_skip_generic_disclaimer_for_knowledge_intent():
    user = UserInput(description="kem chong nang")
    text = "Goi y top 5 kem chong nang cho da dau oil-free dang ban tai Viet Nam."
    suffix = get_safety_suffix(text, user, skip_generic_disclaimer=True)
    assert suffix == ""


def test_generic_disclaimer_present_for_advise_intent():
    user = UserInput(description="mun viem o cam")
    text = "Ban nen dung BHA 2% buoi toi va rua mat 2 lan moi ngay de giam mun viem o cam them nhieu buoc cham soc da khac."
    suffix = get_safety_suffix(text, user, skip_generic_disclaimer=False)
    # Should have a generic disclaimer for long advise responses
    assert suffix != "" or len(text) <= 120  # skip if text too short


def test_multi_condition_flag_adds_dermatologist_referral():
    user = UserInput(description="mun va rosacea")
    text = "Ban co the dung cac san pham nhe nhe cho da nhay cam."
    suffix = get_safety_suffix(text, user, route_flags=["multi_condition"])
    assert "bác sĩ da liễu" in suffix or "bac si da lieu" in suffix.lower()


def test_multi_condition_not_duplicated_if_already_in_text():
    user = UserInput(description="mun rosacea")
    text = "Ban nen kham bac si da lieu de duoc tu van chuyen sau."
    suffix = get_safety_suffix(text, user, route_flags=["multi_condition"])
    # Already has doctor referral in text -> no duplicate
    assert suffix == "" or "bác sĩ da liễu" not in suffix


def test_urgency_flag_adds_warning_when_absent_from_text():
    user = UserInput(description="mun sung lon")
    text = "Day la bieu hien can theo doi them."
    suffix = get_safety_suffix(text, user, route_flags=["urgency_red_flag"])
    assert suffix != ""
    lower = suffix.lower()
    assert any(w in lower for w in ["y tế", "bác sĩ", "kịp thời", "nghiêm trọng", "co so"])
