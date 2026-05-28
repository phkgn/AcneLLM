"""Rule-based clinical intake planner for chat-only acne flows.

Planner nhận UserInput đã được normalize bởi normalizer.py — KHÔNG tự normalize lại.
LLM chỉ được gọi 1 lần duy nhất ở bước generate câu trả lời cuối.

Thay đổi so với phiên bản cũ:
- Dùng LESION_BILINGUAL / LOCATION_BILINGUAL (VI + EN inline) — BM25 match chunk EN
  không cần 2 query riêng biệt, không cần language_switch
- build_query_vi() output 1 query duy nhất cho mọi ngôn ngữ
- fallback_plan() không gọi normalize_chat_message nữa — planner tin user đã clean
- safety_terms được nhúng vào query (không còn dead code)
- duration_weeks được append với chronic flag khi >= 12 tuần
- Bỏ prefix cứng "mụn trứng cá guideline" — guideline chunks được ưu tiên qua
  retriever trust boost (source_type), không qua query text
"""
from __future__ import annotations

from loguru import logger

from ..schemas import UserInput
from ..schemas.clinical import (
    ClinicalDemographics,
    ClinicalQueryPlan,
    ClinicalRagQueries,
    NormalizedAcneCase,
)
from ..utils.retrieval_query import build_retrieval_query
from .query_expander import detect_language_heuristic


# ── Bilingual inline mappings ────────────────────────────────────────────────
# Giữ cả VI + EN trong cùng 1 string để BM25 match chunk EN (papule, pustule...)
# mà không cần sinh 2 query riêng biệt.

LESION_BILINGUAL: dict[str, str] = {
    "comedone":        "mụn nhân mụn cám comedone non-inflammatory",
    "whitehead":       "mụn đầu trắng mụn kín whitehead closed pore",
    "blackhead":       "mụn đầu đen lỗ chân lông tắc blackhead open comedone",
    "closed_comedone": "mụn ẩn mụn cám mụn li ti ẩn dưới da closed comedone microcomedone",
    "papule":          "mụn viêm đỏ sẩn viêm papule inflammatory acne",
    "pustule":         "mụn mủ có đầu mủ pustule purulent lesion",
    "nodule":          "mụn bọc cục cứng sâu dưới da nodule nodular acne severe",
    "cyst":            "mụn nang nang mủ cystic acne cyst severe inflammatory",
    "scar":            "sẹo mụn sẹo rỗ sẹo lõm atrophic scar acne scarring post-acne",
    "post_inflammatory_hyperpigmentation":
                       "thâm mụn vết thâm tăng sắc tố PIH post-inflammatory hyperpigmentation dark spot",
    "other":           "mụn trứng cá tổn thương mụn acne lesion",
}

LOCATION_BILINGUAL: dict[str, str] = {
    "forehead":     "trán vùng trán forehead T-zone upper face",
    "cheeks":       "má hai bên má gò má cheeks facial cheeks",
    "chin":         "cằm vùng cằm chin lower face",
    "jawline":      "quai hàm hàm dưới jawline lower jaw",
    "nose":         "mũi cánh mũi sống mũi nose nasal",
    "around_mouth": "quanh miệng vùng miệng mép perioral around mouth",
    "back":         "lưng sau lưng mụn lưng back dorsal acne truncal",
    "chest":        "ngực trước ngực vùng ngực chest truncal acne",
    "shoulders":    "vai bả vai vùng vai shoulders truncal",
    "neck":         "cổ sau gáy vùng cổ neck",
    "t_zone":       "vùng chữ T trán mũi T-zone oily zone",
    "other":        "toàn mặt khắp mặt vị trí khác face widespread",
}

INFLAMMATION_BILINGUAL: dict[str, str] = {
    "mild":     "mức độ nhẹ ít viêm mild acne comedonal non-inflammatory",
    "moderate": "mức độ vừa viêm vừa moderate inflammatory acne papulopustular",
    "severe":   "mức độ nặng viêm nặng severe nodulocystic acne cần khám da liễu",
}

# Mapping hormonal → query term cho RAG
HORMONAL_BILINGUAL: dict[str, str] = {
    "menstrual_cycle": "mụn theo chu kỳ kinh nguyệt hormonal acne menstrual flare premenstrual",
    "pcos":            "mụn nội tiết PCOS buồng trứng đa nang polycystic ovary syndrome androgenic",
    "stress":          "mụn do stress căng thẳng mất ngủ stress-induced acne cortisol",
    "diet":            "mụn do ăn uống sữa đường high glycemic dairy diet acne",
    "pregnancy":       "mụn khi mang thai thai kỳ acne in pregnancy safe treatment",
    "postpartum":      "mụn sau sinh cho con bú postpartum acne breastfeeding safe",
    "puberty":         "mụn tuổi dậy thì tuổi teen teenage acne puberty hormonal",
}

# Skin type → query context
SKIN_TYPE_BILINGUAL: dict[str, str] = {
    "oily":        "da dầu nhờn tiết dầu oily skin sebaceous",
    "dry":         "da khô khô căng dry skin moisture barrier",
    "combination": "da hỗn hợp vùng T dầu combination skin",
    "sensitive":   "da nhạy cảm dễ kích ứng sensitive skin reactive",
    "normal":      "da thường normal skin",
}

# Drug nhạy cảm cần safety context khi có trong medication_history
_SENSITIVE_DRUGS = frozenset({
    "isotretinoin", "tretinoin", "retinol", "adapalene",
    "tazarotene", "retinoid", "doxycycline", "minocycline", "tetracycline",
})

# Treatment goal → query expansion
TREATMENT_GOAL_BILINGUAL: dict[str, str] = {
    "clear_acne":               "điều trị mụn trứng cá acne treatment clear skin",
    "treat_scar":               "trị sẹo mụn sẹo rỗ sẹo lõm acne scar treatment atrophic",
    "fade_hyperpigmentation":   "xóa thâm mụn PIH post-inflammatory hyperpigmentation brightening dark spot",
    "reduce_oiliness":          "kiểm soát dầu thu nhỏ lỗ chân lông sebum control pore minimizer",
    "hydration":                "dưỡng ẩm phục hồi hàng rào da moisture barrier repair hydration",
    "reduce_inflammation":      "giảm viêm đỏ anti-inflammatory soothing calming acne",
    "prevent_acne":             "ngăn ngừa mụn tái phát maintenance therapy acne prevention",
    "build_routine":            "xây dựng routine chăm sóc da skincare routine acne prone",
    "product_recommendation":   "sản phẩm trị mụn recommended products acne skincare",
    "see_doctor":               "cần khám da liễu dermatologist referral prescription acne treatment",
}


def _dedupe(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _map_lesion(value: str) -> str | None:
    mapping = {
        "whitehead": "whitehead",
        "blackhead": "blackhead",
        "closed_comedone": "closed_comedone",
        "hidden_acne": "closed_comedone",
        "papule": "papule",
        "pustule": "pustule",
        "nodule": "nodule",
        "cyst": "cyst",
        "scar": "scar",
        "post_inflammatory_hyperpigmentation": "post_inflammatory_hyperpigmentation",
        "comedone": "comedone",
        "other": "other",
    }
    return mapping.get(value)


class ClinicalQueryPlanner:
    """Rule-based planner — không gọi LLM, không re-normalize.

    Nhận UserInput đã được normalize bởi intake/runtime.
    Chỉ đọc user.clinical + user.context — không gọi normalize_chat_message.
    """

    def plan(self, user: UserInput) -> ClinicalQueryPlan:
        """Build ClinicalQueryPlan từ UserInput đã normalize."""
        return self._build_plan(user)

    # Giữ alias để không break caller cũ trong pipeline/hybrid.py
    def fallback_plan(self, user: UserInput) -> ClinicalQueryPlan:
        return self._build_plan(user)

    def _build_plan(self, user: UserInput) -> ClinicalQueryPlan:
        """Core logic — KHÔNG gọi normalizer, tin user đã được normalize trước."""
        ctx = user.context
        clinical = user.clinical

        lesions: list[str] = []
        distribution: list[str] = []
        inflammation = "unknown"
        scarring: list[str] = []
        medication_history: list[str] = []
        hormonal: list[str] = []
        skincare: list[str] = []
        canonical_ingredients: list[str] = []
        usage_frequencies: list[str] = []
        concentrations: list[float] = []
        goals: list[str] = []
        red_flags: list[str] = []

        if clinical:
            lesions = [
                mapped for value in clinical.lesion_types
                if (mapped := _map_lesion(str(value)))
            ]
            distribution = list(clinical.lesion_distribution)
            inflammation = clinical.inflammation_level or "unknown"
            scarring = list(clinical.scarring_signs)
            medication_history = list(clinical.medication_history)
            hormonal = list(clinical.hormonal_factors)
            skincare = list(clinical.skincare_products)
            canonical_ingredients = list(clinical.canonical_ingredients)
            usage_frequencies = list(clinical.usage_frequencies)
            concentrations = list(clinical.concentrations)
            goals = list(clinical.treatment_goals)
            red_flags = list(clinical.red_flags_input)

        medication_history.extend(ctx.medications or [])
        skincare.extend(ctx.current_products or [])
        allergies = list(getattr(ctx, "allergies", []) or [])

        # Bug A fix: xoá items đã có trong medication_history khỏi skincare_products
        # (tretinoin, clindamycin, etc. được normalizer extract vào cả 2 lists)
        _med_set = set(m.lower() for m in medication_history)
        skincare = [s for s in skincare if s.lower() not in _med_set]

        if "scar" in lesions and "sẹo mụn" not in scarring:
            scarring.append("sẹo mụn")
        if "post_inflammatory_hyperpigmentation" in lesions and "thâm sau mụn" not in scarring:
            scarring.append("thâm sau mụn")

        demographics = ClinicalDemographics(
            age=ctx.age,
            sex=ctx.sex or "unknown",
            skin_type=ctx.skin_type or "unknown",
            is_pregnant=bool(ctx.is_pregnant),
            is_breastfeeding=bool(ctx.is_breastfeeding),
        )

        missing: list[str] = []
        if demographics.age is None:
            missing.append("age")
        if not lesions:
            missing.append("lesion_types")
        if not distribution:
            missing.append("distribution")
        if inflammation == "unknown":
            missing.append("inflammation_level")
        if ctx.duration_weeks is None:
            missing.append("duration_weeks")

        case = NormalizedAcneCase(
            demographics=demographics,
            lesion_types=_dedupe(lesions),
            distribution=_dedupe(distribution),
            inflammation_level=inflammation,
            scarring_signs=_dedupe(scarring),
            medication_history=_dedupe(medication_history),
            hormonal_factors=_dedupe(hormonal),
            skincare_products=_dedupe(skincare),
            canonical_ingredients=_dedupe(canonical_ingredients),
            usage_frequencies=_dedupe(usage_frequencies),
            concentrations=list(dict.fromkeys(float(x) for x in concentrations)),
            treatment_goals=_dedupe(goals),
            allergies=_dedupe(allergies),
            red_flags=_dedupe(red_flags),
            missing_info=_dedupe(missing),
        )

        safety = self._safety_terms(user, case)
        detected_language = detect_language_heuristic(user.description)
        query_vi = self.build_query_vi(
            case,
            ctx.duration_weeks,
            safety,
            clean_text_normalized=user.description,
        )
        rerank_query = self.build_rerank_query(case, ctx.duration_weeks, user.description)

        plan = ClinicalQueryPlan(
            detected_language=detected_language,
            normalized_case=case,
            rag_queries=ClinicalRagQueries(query_vi=query_vi, rerank_query=rerank_query),
            missing_info=case.missing_info,
            safety_terms=safety,
            planner_confidence=0.45,
        )
        logger.debug(
            "[planner] lang={} query_vi={:.60}... rerank_query={:.60}... missing={}",
            detected_language, query_vi, rerank_query, case.missing_info,
        )
        return plan

    @staticmethod
    def build_query_vi(
        case: NormalizedAcneCase,
        duration_weeks: int | None = None,
        safety_terms: list[str] | None = None,
        clean_text_normalized: str = "",
    ) -> str:
        """Build 1 query VI với EN tokens inline (code-switching).

        Không có prefix cứng — guideline chunks nổi lên qua trust boost trong retriever.
        Safety terms được nhúng trực tiếp để retrieve đúng chunks contraindication.
        """
        compact_query = build_retrieval_query(
            lesions=list(case.lesion_types),
            skin_type=case.demographics.skin_type if case.demographics.skin_type != "unknown" else None,
            canonical_ingredients=list(case.canonical_ingredients),
            clean_text_normalized=clean_text_normalized,
            severity=case.inflammation_level,
            distribution=list(case.distribution),
            products=list(case.skincare_products),
            medications=list(case.medication_history),
            duration_weeks=duration_weeks,
            usage_frequencies=list(case.usage_frequencies),
            concentrations=list(case.concentrations),
            red_flags=list(case.red_flags),
        )
        if compact_query:
            return compact_query

        parts: list[str] = []

        # 1. Severity hint — thay prefix cứng
        infl = case.inflammation_level
        if infl and infl not in ("unknown", "none"):
            parts.append(INFLAMMATION_BILINGUAL.get(infl, ""))

        # 2. Lesion types — VI + EN inline (BM25 match chunk EN)
        parts.extend(
            LESION_BILINGUAL[x] for x in case.lesion_types if x in LESION_BILINGUAL
        )

        # 3. Distribution — VI + EN inline
        parts.extend(
            LOCATION_BILINGUAL[x] for x in case.distribution if x in LOCATION_BILINGUAL
        )

        # 4. Duration — chronic flag khi >= 12 tuần
        if duration_weeks is not None:
            if duration_weeks >= 12:
                parts.append(
                    f"kéo dài {duration_weeks} tuần mụn mãn tính "
                    f"chronic acne treatment-resistant"
                )
            elif duration_weeks >= 4:
                parts.append(f"kéo dài {duration_weeks} tuần")

        # 5. Safety — pregnancy / breastfeeding
        demo = case.demographics
        if demo.is_pregnant:
            parts.append(HORMONAL_BILINGUAL.get("pregnancy", "mang thai pregnancy safe acne treatment"))
        if demo.is_breastfeeding:
            parts.append(HORMONAL_BILINGUAL.get("postpartum", "cho con bú breastfeeding lactation safety"))

        # 6. Drug nhạy cảm trong medication_history
        meds_lower = " ".join(case.medication_history).lower()
        if any(d in meds_lower for d in _SENSITIVE_DRUGS):
            parts.append("retinoid isotretinoin tác dụng phụ side effect contraindication safety monitoring")

        # 7. Hormonal — dùng mapping chi tiết thay vì 1 string cứng
        for hf in case.hormonal_factors:
            term = HORMONAL_BILINGUAL.get(hf)
            if term:
                parts.append(term)

        # 8. Skin type — dùng mapping chi tiết
        st = demo.skin_type
        if st and st != "unknown":
            parts.append(SKIN_TYPE_BILINGUAL.get(st, f"da {st}"))

        # 9. Red flags — phân loại cụ thể hơn
        if case.red_flags:
            if any(f in case.red_flags for f in ("infection_signs", "widespread", "painful_lesions")):
                parts.append("mụn nặng viêm nặng cần khám da liễu ngay severe acne dermatologist urgent referral")
            else:
                parts.append("dấu hiệu cần theo dõi red flags dermatologist referral")

        # 10. Treatment goals — ưu tiên retrieve đúng hướng
        for goal in (case.treatment_goals or []):
            term = TREATMENT_GOAL_BILINGUAL.get(goal)
            if term:
                parts.append(term)

        if case.canonical_ingredients:
            parts.append("canonical ingredients " + " ".join(case.canonical_ingredients))
        if case.usage_frequencies:
            parts.append("frequency " + " ".join(case.usage_frequencies))
        if case.concentrations:
            parts.append("concentration " + " ".join(f"{float(x):.8g}" for x in case.concentrations))

        # 11. Allergies — tránh recommend sản phẩm chứa chất dị ứng
        allergies = case.allergies if hasattr(case, "allergies") else []
        if allergies:
            allergy_str = " ".join(allergies)
            parts.append(f"dị ứng kích ứng {allergy_str} contraindication avoid ingredient allergy")

        # 12. Fallback initial assessment — chỉ khi không có core signal
        if not case.lesion_types and not case.distribution:
            parts.append("đánh giá ban đầu mụn trứng cá acne initial assessment")

        return " ".join(_dedupe(p for p in parts if p))

    @staticmethod
    def build_rerank_query(
        case: NormalizedAcneCase,
        duration_weeks: int | None = None,
        raw_description: str = "",
    ) -> str:
        """Sinh câu tiếng Việt tự nhiên để dùng làm rerank query cho cross-encoder.

        Cross-encoder so sánh (query, chunk_text) — cả 2 phải cùng dạng văn xuôi
        để model cho logit phân tán rộng. Query dạng 'lesions X ; severity Y' gây
        logit âm lớn vì format khác hoàn toàn với chunk text.
        """
        parts: list[str] = []

        # 1. Lesion types → câu mô tả tự nhiên
        lesion_phrases: dict[str, str] = {
            "blackhead":       "mụn đầu đen",
            "whitehead":       "mụn đầu trắng",
            "closed_comedone": "mụn ẩn dưới da",
            "comedone":        "mụn cám mụn nhân",
            "papule":          "mụn viêm đỏ",
            "pustule":         "mụn mủ có đầu",
            "nodule":          "mụn bọc cứng sâu",
            "cyst":            "mụn nang nặng",
            "scar":            "sẹo mụn",
            "post_inflammatory_hyperpigmentation": "thâm sau mụn",
            "other":           "mụn trứng cá",
        }
        lesion_labels = [lesion_phrases[x] for x in case.lesion_types if x in lesion_phrases]
        if lesion_labels:
            parts.append("bị " + ", ".join(lesion_labels))

        # 2. Distribution
        dist_phrases: dict[str, str] = {
            "forehead": "trên trán",
            "cheeks":   "ở má",
            "chin":     "ở cằm",
            "jawline":  "dọc quai hàm",
            "nose":     "ở mũi",
            "around_mouth": "quanh miệng",
            "back":     "ở lưng",
            "chest":    "ở ngực",
            "shoulders": "ở vai",
            "neck":     "ở cổ",
            "t_zone":   "vùng chữ T",
            "other":    "trên mặt",
        }
        dist_labels = [dist_phrases[x] for x in case.distribution if x in dist_phrases]
        if dist_labels:
            parts.append(", ".join(dist_labels))

        # 3. Severity
        sev_map = {
            "mild":     "mức độ nhẹ",
            "moderate": "mức độ vừa",
            "severe":   "mức độ nặng",
        }
        if case.inflammation_level in sev_map:
            parts.append(sev_map[case.inflammation_level])

        # 4. Skin type
        skin_map = {
            "oily":        "da dầu",
            "dry":         "da khô",
            "combination": "da hỗn hợp",
            "sensitive":   "da nhạy cảm",
            "normal":      "da thường",
        }
        st = case.demographics.skin_type
        if st and st != "unknown":
            parts.append(skin_map.get(st, f"da {st}"))

        # 5. Duration
        if duration_weeks is not None:
            if duration_weeks >= 52:
                parts.append(f"bị hơn {duration_weeks // 52} năm")
            elif duration_weeks >= 4:
                parts.append(f"kéo dài {duration_weeks} tuần")
            else:
                parts.append(f"mới bị khoảng {duration_weeks} tuần")

        # 6. Hormonal / special context
        hormonal_phrases: dict[str, str] = {
            "menstrual_cycle": "mụn theo chu kỳ kinh nguyệt",
            "pcos":            "hội chứng buồng trứng đa nang",
            "stress":          "do stress căng thẳng thiếu ngủ",
            "diet":            "liên quan chế độ ăn uống",
            "pregnancy":       "đang mang thai",
            "postpartum":      "sau sinh cho con bú",
            "puberty":         "tuổi dậy thì",
        }
        for hf in case.hormonal_factors:
            phrase = hormonal_phrases.get(hf)
            if phrase:
                parts.append(phrase)

        # 7. Safety
        if case.demographics.is_pregnant:
            parts.append("đang mang thai cần điều trị an toàn")
        if case.demographics.is_breastfeeding:
            parts.append("đang cho con bú cần tránh thuốc nguy hiểm")

        # 8. Products / medications đang dùng
        if case.skincare_products:
            parts.append("đang dùng " + ", ".join(case.skincare_products[:3]))
        if case.medication_history:
            parts.append("đang dùng thuốc " + ", ".join(case.medication_history[:3]))

        # 9. Fallback: dùng raw description nếu không có signal nào
        if not parts:
            return raw_description[:300] if raw_description else "mụn trứng cá điều trị"

        base = " ".join(parts)
        # Append raw description ngắn gọn để giữ ngữ cảnh user gốc
        if raw_description:
            short_desc = raw_description[:150].rsplit(" ", 1)[0]
            return f"{base}. {short_desc}"
        return base

    @staticmethod
    def _safety_terms(user: UserInput, case: NormalizedAcneCase) -> list[str]:
        terms: list[str] = []
        text = user.description.lower()
        for term in (
            "mang thai", "pregnant", "cho con bú", "breastfeeding",
            "isotretinoin", "retinoid", "retinol", "tretinoin", "adapalene", "tazarotene",
            "doxycycline", "minocycline", "tetracycline", "kháng sinh",
        ):
            if term in text:
                terms.append(term)
        terms.extend(
            ingredient for ingredient in case.canonical_ingredients
            if ingredient in {"tretinoin", "salicylic_acid", "glycolic_acid"}
        )
        if case.demographics.is_pregnant:
            terms.append("pregnancy")
        if case.demographics.is_breastfeeding:
            terms.append("breastfeeding")
        return _dedupe(terms)
