from acne_llm.chat.normalizer import normalize_chat_message
from acne_llm.chat.preprocess import expand_teencode_for_retrieval, prepare_user_text, preprocess_user_text


def test_preprocess_user_text_light_cleanup():
    assert preprocess_user_text("  tôi    là   nam  ") == "tôi là nam"
    assert preprocess_user_text("mụ\u200bn lưng") == "mụn lưng"
    assert preprocess_user_text("mụn_lưng") == "mụn lưng"
    # gạch nối được giữ: "BT-Cortin", "benzoyl-peroxide" là tên thật
    assert preprocess_user_text("mụn-lưng") == "mụn-lưng"
    assert preprocess_user_text("mụn!!!!! sao????") == "mụn!! sao??"
    assert preprocess_user_text("benzoyl peroxide 5% + BHA/AHA") == "benzoyl peroxide 5% + BHA/AHA"
    assert preprocess_user_text("mụn 😭") == "mụn 😭"


def test_prepare_user_text_leaves_teencode_for_the_model():
    """Model đọc nguyên văn; teencode chỉ được mở rộng ở retrieval query."""
    raw = "BHA 2% ko dc dùng vs sp này sáng tối"
    prepared = prepare_user_text(raw)

    assert prepared.clean_text == raw
    assert prepared.teencode_replaced == []
    assert expand_teencode_for_retrieval(raw) == (
        "BHA 2% không được dùng với sản phẩm này sáng tối"
    )


def test_normalizer_preserves_raw_description_but_extracts_from_clean_text():
    user = normalize_chat_message("  Mình bị mụn_lưng\u200b 3   tháng  ")

    assert user.description == "Mình bị mụn_lưng 3   tháng"
    assert user.context.duration_weeks == 12
    assert user.clinical is not None
    assert "back" in user.clinical.lesion_distribution


def test_normalizer_extracts_core_context_from_free_text():
    user = normalize_chat_message(
        "Em 22 tuổi, da dầu, mụn viêm ở cằm 4 tuần, đang dùng BHA, không mang thai."
    )

    assert user.context.age == 22
    assert user.context.skin_type == "oily"
    assert user.context.duration_weeks == 4
    assert user.context.is_pregnant is False
    assert "BHA" in user.context.current_products
    assert user.clinical is not None
    assert "papule" in user.clinical.lesion_types
    assert "chin" in user.clinical.lesion_distribution
    assert user.clinical.inflammation_level == "moderate"


def test_normalizer_extracts_canonical_frequency_and_concentration():
    user = normalize_chat_message("Da mình dùng BHA 2% sáng tối, AHA 0.025% cách ngày.")

    assert user.clinical is not None
    assert user.clinical.canonical_ingredients == ["salicylic_acid", "glycolic_acid"]
    assert "twice_daily" in user.clinical.usage_frequencies
    assert "every_other_day" in user.clinical.usage_frequencies
    assert 0.02 in user.clinical.concentrations
    assert 0.00025 in user.clinical.concentrations


def test_normalizer_va_alias_is_conservative():
    lower = normalize_chat_message("retinol va niacinamide dùng chung được không")
    upper = normalize_chat_message("Em đang bôi VA buổi tối")

    assert lower.clinical is None
    assert upper.clinical is not None
    assert "tretinoin" in upper.clinical.canonical_ingredients


def test_normalizer_extracts_safety_flags():
    user = normalize_chat_message("Mình đang cho con bú, bị mụn mủ ở má và dùng retinol.")

    assert user.context.is_breastfeeding is True
    assert "retinol" in user.context.current_products
    assert user.clinical is not None
    assert "pustule" in user.clinical.lesion_types
    assert "cheeks" in user.clinical.lesion_distribution


def test_normalizer_extracts_broad_acne_intake_fields():
    user = normalize_chat_message(
        "Tôi là nam 22 tuổi, 3 tháng qua bị mụn_lưng khắp lưng có mủ, chưa dùng sản phẩm nào."
    )

    assert user.context.sex == "male"
    assert user.context.age == 22
    assert user.context.duration_weeks == 12
    assert user.clinical is not None
    assert "back" in user.clinical.lesion_distribution
    assert "pustule" in user.clinical.lesion_types
    assert user.clinical.inflammation_level == "severe"
    assert "widespread" in user.clinical.red_flags_input
    assert "purulent_lesions" in user.clinical.red_flags_input
    assert "no_prior_treatment" in user.clinical.red_flags_input


def test_normalizer_extracts_mixed_language_and_treatment_history():
    user = normalize_chat_message(
        "Da mình oily, mụn blackhead ở nose, dùng benzoyl peroxide 5% 2 tháng không đỡ."
    )

    assert user.context.skin_type == "oily"
    assert user.context.duration_weeks == 8
    assert "benzoyl peroxide" in user.context.current_products
    assert user.clinical is not None
    assert "blackhead" in user.clinical.lesion_types
    assert "nose" in user.clinical.lesion_distribution
    assert "treatment_failure" in user.clinical.red_flags_input


def test_normalizer_outputs_schema_safe_comedone_type():
    user = normalize_chat_message("Mình bị mụn cám và nhiều nhân mụn ở vùng chữ T.")

    assert user.clinical is not None
    assert "closed_comedone" in user.clinical.lesion_types


def test_normalizer_extracts_hormonal_and_prescription_terms():
    user = normalize_chat_message(
        "Em nữ bị mụn bọc ở quai hàm trước kỳ kinh, đang uống doxycycline."
    )

    assert user.context.sex == "female"
    assert "doxycycline" in user.context.medications
    assert user.clinical is not None
    assert "nodule" in user.clinical.lesion_types
    assert "jawline" in user.clinical.lesion_distribution
    assert "menstrual_cycle" in user.clinical.hormonal_factors


def test_normalizer_does_not_mark_asked_about_medication_as_current_use():
    user = normalize_chat_message(
        "Em có cần dùng thuốc tránh thai không? Em có nên dùng spironolactone không?"
    )

    assert user.context.medications == []
    assert user.clinical is None


def test_normalizer_keeps_actual_medication_history_only():
    user = normalize_chat_message(
        "Em đã dùng thuốc tránh thai được 3 tháng nhưng mụn không giảm. "
        "Em có nên dùng spironolactone không?"
    )

    assert user.context.medications == ["thuốc tránh thai"]
    assert user.clinical is not None
    assert user.clinical.medication_history == ["thuốc tránh thai"]


def test_normalizer_does_not_mark_recommended_medication_as_current_use():
    user = normalize_chat_message(
        "Có người khuyên em dùng thuốc Accutane, em có nên mua về uống không?"
    )

    assert user.context.medications == []
    assert user.clinical is None


def test_normalizer_does_not_match_product_substrings_inside_medications():
    user = normalize_chat_message("Em đang dùng isotretinoin được 2 tháng.")

    assert user.context.medications == ["isotretinoin"]
    assert "isotretinoin" not in user.context.current_products
    assert "tretinoin" not in user.context.current_products


def test_normalizer_handles_general_acne_and_face_mentions_from_audit():
    user = normalize_chat_message(
        "Em đang mang thai 3 tháng, da mặt bị mụn trứng cá nhẹ, có nhiều dầu. "
        "Em thường đắp mặt nạ giấy sau khi rửa mặt."
    )

    assert user.context.is_pregnant is True
    assert user.context.skin_type == "oily"
    assert "mặt nạ giấy" in user.context.current_products
    assert user.clinical is not None
    assert "other" in user.clinical.lesion_types
    assert "other" in user.clinical.lesion_distribution


def test_normalizer_handles_large_painful_deep_acne_from_audit():
    user = normalize_chat_message(
        "Em bị mụn ở lưng mấy năm rồi, mụn to, đỏ, đau. Em muốn hỏi có cách nào hết nhanh không?"
    )

    assert user.clinical is not None
    assert "back" in user.clinical.lesion_distribution
    assert "nodule" in user.clinical.lesion_types
    assert user.clinical.inflammation_level == "severe"


def test_normalizer_handles_topical_irritation_from_audit():
    user = normalize_chat_message(
        "Em mới dùng Differin gel được 2 tuần, da em bị đỏ, bong tróc và rát. "
        "Em có nên ngưng thuốc không?"
    )

    assert "adapalene" in user.context.current_products
    assert user.clinical is not None
    assert "skin_irritation" in user.clinical.red_flags_input


def test_normalizer_extracts_informal_ada_alias_without_false_red_flag():
    user = normalize_chat_message("toi dung ada 0.1% dc 3 tuan ma da rat")
    assert "adapalene" in user.context.medications

    source_question = normalize_chat_message(
        "Vì sao đầu đen có màu đen, và nguồn nào nói điều đó?"
    )
    assert "purulent_lesions" not in (source_question.clinical.red_flags_input if source_question.clinical else [])
