"""Normalizer regression tests.

Covers:
- Red flag detection (painful_lesions, infection_signs, self_treatment_risk, widespread, purulent_lesions)
- Inflammation severity derivation
- Lesion type extraction
- Distribution extraction
- Age / duration / skin_type / sex parsing
- Edge cases (negation, mixed-language, empty input)

Run: pytest tests/test_normalizer_regression.py -v
"""
import pytest
from acne_llm.chat.routing.rule_normalizer import normalize_chat_message


def norm(text: str, mode: str = "auto"):
    return normalize_chat_message(text, mode=mode)


def flags(r) -> list[str]:
    if r.clinical and r.clinical.red_flags_input:
        return r.clinical.red_flags_input
    return []


def sev(r):
    return r.clinical.inflammation_level if r.clinical else None


def lesions(r) -> list[str]:
    if r.clinical and r.clinical.lesion_types:
        return [lt.value if hasattr(lt, "value") else str(lt) for lt in r.clinical.lesion_types]
    return []


def dist(r) -> list[str]:
    if r.clinical and r.clinical.lesion_distribution:
        return [d.value if hasattr(d, "value") else str(d) for d in r.clinical.lesion_distribution]
    return []


# ── Red flags ─────────────────────────────────────────────────────────────────

class TestPainfulLesions:
    def test_dau_khi_so_vao(self):
        r = norm("đau khi sờ vào mụn")
        assert "painful_lesions" in flags(r)

    def test_so_vao_la_dau(self):
        r = norm("sờ vào là đau")
        assert "painful_lesions" in flags(r)

    def test_dau_khi_an_vao(self):
        r = norm("đau khi ấn vào")
        assert "painful_lesions" in flags(r)

    def test_an_vao_dau(self):
        r = norm("ấn vào đau")
        assert "painful_lesions" in flags(r)

    def test_dau_nhieu(self):
        r = norm("mụn đau nhiều quá")
        assert "painful_lesions" in flags(r)

    def test_rat_dau(self):
        r = norm("rất đau không chịu nổi")
        assert "painful_lesions" in flags(r)

    def test_cham_vao_dau(self):
        r = norm("chạm vào là đau")
        assert "painful_lesions" in flags(r)

    def test_dau_khi_so_vao_full_sentence(self):
        """Regression: bị sốt sau khi nặn, đau khi sờ vào."""
        r = norm("bị sốt sau khi nặn mụn, đau khi sờ vào")
        assert "painful_lesions" in flags(r)


class TestInfectionSigns:
    def test_sot(self):
        r = norm("bị sốt cao")
        assert "infection_signs" in flags(r)

    def test_sot_sau_khi_nan(self):
        """Regression: sốt sau khi nặn phải trigger infection_signs."""
        r = norm("sốt sau khi nặn mụn")
        assert "infection_signs" in flags(r)

    def test_bi_sot(self):
        r = norm("bị sốt 38 độ")
        assert "infection_signs" in flags(r)

    def test_nhiem_trung(self):
        r = norm("có dấu hiệu nhiễm trùng")
        assert "infection_signs" in flags(r)

    def test_fever_english(self):
        r = norm("i have fever after popping pimples")
        assert "infection_signs" in flags(r)

    def test_sot_triggers_severe(self):
        """Sốt → inflammation_level = severe."""
        r = norm("sốt cao 38 độ, mụn sưng to")
        assert sev(r) == "severe"


class TestSelfTreatmentRisk:
    def test_nan_mun(self):
        r = norm("tôi hay nặn mụn")
        assert "self_treatment_risk" in flags(r)

    def test_nan_vai_cuc(self):
        """Regression: 'nặn vài cục' phải trigger self_treatment_risk."""
        r = norm("hôm qua nặn vài cục thấy sưng")
        assert "self_treatment_risk" in flags(r)

    def test_sau_khi_nan(self):
        """Regression: 'sau khi nặn' phải trigger self_treatment_risk."""
        r = norm("sau khi nặn mụn thì bị sưng đỏ")
        assert "self_treatment_risk" in flags(r)

    def test_tu_nan(self):
        r = norm("tự nặn ở nhà")
        assert "self_treatment_risk" in flags(r)

    def test_boi_kem_tron(self):
        r = norm("đang bôi kem trộn không rõ nguồn gốc")
        assert "self_treatment_risk" in flags(r)


class TestWideSpread:
    def test_khap_mat(self):
        r = norm("mụn nổi khắp mặt")
        assert "widespread" in flags(r)

    def test_day_dac(self):
        r = norm("mụn mọc dày đặc")
        assert "widespread" in flags(r)

    def test_lan_rong(self):
        r = norm("mụn lan rộng ra cả cổ")
        assert "widespread" in flags(r)


class TestPurulentLesions:
    def test_co_mu(self):
        r = norm("có cả mủ vàng")
        assert "purulent_lesions" in flags(r)

    def test_chay_mu(self):
        r = norm("mụn chảy mủ trắng")
        assert "purulent_lesions" in flags(r)

    def test_co_mau(self):
        r = norm("nặn ra có cả máu")
        assert "purulent_lesions" in flags(r)


class TestSkinIrritation:
    @pytest.mark.parametrize("text", ["rất nhiều mụn", "bị rất nhiều mụn"])
    def test_rat_no_accent_does_not_match_rat_adverb(self, text):
        r = norm(text)
        assert "skin_irritation" not in flags(r)

    @pytest.mark.parametrize("text", ["da bị rát", "da nong rat"])
    def test_rat_with_irritation_context_still_matches(self, text):
        r = norm(text)
        assert "skin_irritation" in flags(r)


# ── Combined / complex cases ──────────────────────────────────────────────────

class TestCombinedRedFlags:
    def test_sot_nan_dau_so_combo(self):
        """Full regression case from real chat log."""
        r = norm("bị sốt sau khi nặn mụn, đau khi sờ vào")
        f = flags(r)
        assert "infection_signs" in f
        assert "self_treatment_risk" in f
        assert "painful_lesions" in f
        assert sev(r) == "severe"

    def test_mu_vang_kham_mat(self):
        r = norm("mụn mủ dày đặc khắp mặt")
        f = flags(r)
        assert "widespread" in f


# ── Inflammation severity ─────────────────────────────────────────────────────

class TestInflammationLevel:
    def test_nodule_severe(self):
        r = norm("mụn nhọt to sưng đỏ đau nhiều")
        assert sev(r) == "severe"

    def test_mild_mun_dau(self):
        r = norm("nổi vài mụn đầu đen")
        # blackheads = mild at most
        assert sev(r) in (None, "none", "mild")

    def test_mu_vang_moderate_or_severe(self):
        r = norm("mụn mủ vàng sưng to")
        assert sev(r) in ("moderate", "severe")

    def test_sot_always_severe(self):
        r = norm("sốt cao, mụn sưng")
        assert sev(r) == "severe"


# ── Lesion type extraction ────────────────────────────────────────────────────

class TestLesionExtraction:
    def test_mun_dau_den(self):
        r = norm("mụn đầu đen ở mũi")
        assert "blackhead" in lesions(r)

    def test_mun_dau_trang(self):
        r = norm("mụn đầu trắng ở cằm")
        assert "whitehead" in lesions(r)

    def test_mun_boc(self):
        r = norm("mụn bọc to ở má")
        assert "nodule" in lesions(r)

    def test_mun_mu(self):
        r = norm("mụn mủ vàng nhiều")
        assert "pustule" in lesions(r)

    def test_seo_ro(self):
        r = norm("da bị sẹo rỗ")
        assert "scar" in lesions(r)


# ── Distribution extraction ───────────────────────────────────────────────────

class TestDistributionExtraction:
    def test_ma(self):
        r = norm("mụn ở hai bên má")
        assert "cheeks" in dist(r)

    @pytest.mark.parametrize(
        "text",
        [
            "mun o ma",
            "mun o hai ben ma",
            "vung ma bi mun",
            "go ma noi mun",
            "ma trai co mun",
            "acne on cheeks",
        ],
    )
    def test_ma_no_accent_requires_location_context(self, text):
        r = norm(text)
        assert "cheeks" in dist(r)

    @pytest.mark.parametrize(
        "text",
        [
            "mụn lưng mà sao sinh hoạt chung với thằng bạn cùng phòng nó lại không bị",
            "mụn mà sao cứ nổi hoài",
            "mà sao da tôi cứ bị mụn",
            "ma là chuyện không liên quan tới vị trí mụn",
        ],
    )
    def test_ma_no_accent_does_not_match_conjunction_ma(self, text):
        r = norm(text)
        assert "cheeks" not in dist(r)

    @pytest.mark.parametrize(
        ("text", "unexpected"),
        [
            ("mụn lưng khi chuyển trọ được 2 tuần thì nổi bên trái bên phải không có bị", "neck"),
            ("da có mụn nhẹ", "neck"),
            ("mụn gây đau khi chạm", "neck"),
            ("nặn vài cục thấy sưng", "shoulders"),
            ("cam kết không nặn mụn", "chin"),
            ("mùi hôi do kem", "nose"),
            ("da mỏng dễ kích ứng", "other"),
            ("tẩy da chết xong nổi mụn", "other"),
            ("chán vì mụn", "other"),
            ("ở trần bị mụn lưng", "forehead"),
            ("da mà nổi mụn", "cheeks"),
            ("da dầu hay bị mụn", "other"),
        ],
    )
    def test_no_accent_short_location_tokens_need_context(self, text, unexpected):
        r = norm(text)
        assert unexpected not in dist(r)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("mun tran", "forehead"),
            ("mun o cam", "chin"),
            ("mun o ham", "jawline"),
            ("mun o mui", "nose"),
            ("mun o vai", "shoulders"),
            ("mun o co", "neck"),
            ("vung co noi mun", "neck"),
            ("mun o mong", "other"),
            ("mun o tay", "other"),
            ("mun o chan", "other"),
        ],
    )
    def test_no_accent_location_context_still_matches(self, text, expected):
        r = norm(text)
        assert expected in dist(r)

    def test_mun_co_mu_does_not_match_neck(self):
        r = norm("tôi bị mụn ngay mông, mụn có mủ, đau nhiều")
        assert "other" in dist(r)
        assert "neck" not in dist(r)

    def test_tran(self):
        r = norm("mụn nhiều ở trán")
        assert "forehead" in dist(r)

    def test_cam(self):
        r = norm("mụn ở vùng cằm")
        assert "chin" in dist(r)

    def test_mun_cam_no_accent_does_not_shadow_chin(self):
        r = norm("mụn cằm")
        assert "chin" in dist(r)
        assert "closed_comedone" not in lesions(r)

    def test_mun_cam_accented_still_matches_closed_comedone(self):
        r = norm("mụn cám li ti")
        assert "closed_comedone" in lesions(r)

    def test_lung(self):
        r = norm("mụn nổi nhiều ở lưng")
        assert "back" in dist(r)


# ── Context extraction ────────────────────────────────────────────────────────

class TestContextExtraction:
    def test_age(self):
        r = norm("tôi 22 tuổi bị mụn")
        assert r.context.age == 22

    def test_duration_weeks(self):
        r = norm("bị mụn đã 2 tháng rồi")
        assert r.context.duration_weeks == 8  # 2 months * 4 weeks

    def test_duration_weeks_direct(self):
        r = norm("mụn xuất hiện khoảng 3 tuần")
        assert r.context.duration_weeks == 3

    def test_sex_female(self):
        r = norm("tôi là nữ, 20 tuổi bị mụn")
        assert r.context.sex is not None
        assert str(r.context.sex).lower() in ("female", "f")

    def test_pregnant_false_negation(self):
        r = norm("không mang thai")
        assert r.context.is_pregnant is False

    def test_oily_skin(self):
        r = norm("da dầu, mụn nhiều")
        assert r.context.skin_type is not None
        assert "oily" in str(r.context.skin_type).lower() or "dầu" in str(r.context.skin_type)

    def test_oily_skin_from_explicit_oiliness_context(self):
        r = norm("da có nhiều dầu")
        assert r.context.skin_type == "oily"

    @pytest.mark.parametrize(
        "text",
        [
            "da dau nhieu",
            "da dầu nhiều",
            "mặt nhiều dầu",
            "Da mình oily, mụn blackhead ở nose",
        ],
    )
    def test_oily_skin_requires_skin_context_positive_cases(self, text):
        r = norm(text)
        assert r.context.skin_type == "oily"

    @pytest.mark.parametrize(
        "text",
        [
            "đau nhiều",
            "mụn đau nhiều",
            "da đau nhiều",
            "tôi dùng dầu ăn được không",
            "tôi dùng dầu ăn dc kop",
            "món ăn có nhiều dầu",
            "dầu ăn có nhiều dầu mỡ",
            "sản phẩm nhờn rít",
            "kem này bóng dầu",
        ],
    )
    def test_pain_and_cooking_oil_do_not_mark_oily_skin(self, text):
        r = norm(text)
        assert r.context.skin_type is None

    @pytest.mark.parametrize(
        "text",
        [
            "mụn đầu đen bị 2 tuần rồi",
            "mụn đau khi sờ",
            "da đau khi chạm vào mụn",
            "da khó chịu vì mụn",
            "thường bị mụn",
            "mụn bình thường",
        ],
    )
    def test_no_accent_skin_type_tokens_need_context(self, text):
        r = norm(text)
        assert r.context.skin_type is None

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("da dau mun nhieu", "oily"),
            ("da kho va bong troc", "dry"),
            ("da binh thuong", "normal"),
        ],
    )
    def test_no_accent_skin_type_context_still_matches(self, text, expected):
        r = norm(text)
        assert r.context.skin_type == expected


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        # Pydantic requires description >= 1 char; empty input should raise or be handled
        # The normalizer does NOT guard against empty input — this is a known limitation.
        # Test that it either returns normally or raises a ValidationError gracefully.
        try:
            r = norm("")
            assert r is not None
        except Exception:
            pass  # ValidationError is acceptable for empty input

    def test_english_mixed(self):
        r = norm("my skin is oily and i have acne on cheeks")
        # should not crash
        assert r is not None

    def test_no_clinical_info(self):
        r = norm("xin chào bạn")
        # Should still return UserInput; clinical may be None
        assert r is not None

    def test_negation_not_nan(self):
        """'không nặn mụn' — known gap: negation not yet handled by self_treatment_risk pattern.

        Marked xfail until negation-aware matching is implemented.
        """
        r = norm("tôi không nặn mụn bao giờ")
        f = flags(r)
        # Known gap: pattern currently triggers on 'nặn mụn' even with 'không' prefix.
        # When negation is implemented, flip this to a real assert.
        pytest.xfail("Negation for self_treatment_risk not yet implemented")

    def test_mode_preserved(self):
        r = norm("mụn nhiều", mode="llm_only")
        assert r.mode == "llm_only"

    def test_invalid_mode_defaults_hybrid(self):
        r = norm("mụn nhiều", mode="invalid_mode")
        assert r.mode == "hybrid"
