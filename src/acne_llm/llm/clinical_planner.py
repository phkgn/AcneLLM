"""LLM-backed clinical intake planner for chat-only acne flows.

The planner turns a free-form patient message into a normalized acne case and
bilingual RAG queries. If the LLM call fails, it falls back to the existing
rule-based chat normalizer so retrieval and downstream prompts still work.
"""
from __future__ import annotations

import json
import re

from loguru import logger

from ..chat.normalizer import normalize_chat_message
from ..schemas import UserInput
from ..schemas.clinical import (
    ClinicalDemographics,
    ClinicalQueryPlan,
    ClinicalRagQueries,
    NormalizedAcneCase,
)
from .ollama_backend import OllamaBackend
from .prompt_builder import PromptBuilder
from .query_expander import detect_language_heuristic


_SYSTEM_PROMPT = (
    "Bạn là bộ chuẩn hóa truy vấn RAG y khoa cho mụn trứng cá. "
    "Nhiệm vụ duy nhất: trích xuất dữ kiện ca bệnh, đánh dấu dữ kiện thiếu, "
    "và tạo truy vấn song ngữ để truy hồi guideline. Không tư vấn điều trị."
)


_LESION_EN = {
    "comedone": "comedones",
    "whitehead": "whiteheads",
    "blackhead": "blackheads",
    "closed_comedone": "closed comedones",
    "papule": "papules inflammatory acne",
    "pustule": "pustules inflammatory acne",
    "nodule": "nodular acne",
    "cyst": "cystic acne",
    "scar": "acne scarring",
    "post_inflammatory_hyperpigmentation": "post inflammatory hyperpigmentation",
    "other": "acne-like lesions",
}

_LESION_VI = {
    "comedone": "mụn nhân",
    "whitehead": "mụn đầu trắng",
    "blackhead": "mụn đầu đen",
    "closed_comedone": "mụn ẩn mụn đầu trắng kín",
    "papule": "sẩn viêm mụn viêm",
    "pustule": "mụn mủ",
    "nodule": "mụn bọc mụn nốt",
    "cyst": "mụn nang",
    "scar": "sẹo mụn",
    "post_inflammatory_hyperpigmentation": "thâm sau mụn",
    "other": "tổn thương giống mụn",
}

_LOCATION_EN = {
    "forehead": "forehead",
    "cheeks": "cheeks",
    "chin": "chin",
    "jawline": "jawline",
    "nose": "nose",
    "around_mouth": "perioral area",
    "back": "back",
    "chest": "chest",
    "shoulders": "shoulders",
    "neck": "neck",
    "t_zone": "T-zone",
    "other": "other distribution",
}

_LOCATION_VI = {
    "forehead": "trán",
    "cheeks": "má",
    "chin": "cằm",
    "jawline": "quai hàm",
    "nose": "mũi",
    "around_mouth": "quanh miệng",
    "back": "lưng",
    "chest": "ngực",
    "shoulders": "vai",
    "neck": "cổ",
    "t_zone": "vùng chữ T",
    "other": "vị trí khác",
}


def _dedupe(items: list[str]) -> list[str]:
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


def _clamp_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _parse_plan(raw: str) -> ClinicalQueryPlan:
    cleaned = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    data = json.loads(cleaned)
    if isinstance(data, dict) and "planner_confidence" in data:
        data["planner_confidence"] = _clamp_confidence(data["planner_confidence"])
    return ClinicalQueryPlan.model_validate(data)


class ClinicalQueryPlanner:
    def __init__(self, llm: OllamaBackend, prompt: PromptBuilder):
        self.llm = llm
        self.prompt = prompt

    def plan(self, user: UserInput) -> ClinicalQueryPlan:
        user_prompt = self.prompt.build_clinical_planner(user)
        try:
            raw = self.llm.generate_json(
                _SYSTEM_PROMPT,
                user_prompt,
                schema=ClinicalQueryPlan.model_json_schema(),
                temperature=0.1,
            )
            plan = _parse_plan(raw)
            return self._finalize_plan(plan, user)
        except Exception as e:
            logger.warning(f"Clinical planner failed, using fallback: {e}")
            return self.fallback_plan(user)

    def fallback_plan(self, user: UserInput) -> ClinicalQueryPlan:
        normalized_user = normalize_chat_message(user.description, mode=user.mode)
        source = user if user.clinical or user.context != type(user.context)() else normalized_user
        if not user.clinical:
            source = normalized_user

        ctx = user.context
        fallback_ctx = normalized_user.context
        clinical = source.clinical or normalized_user.clinical

        lesions: list[str] = []
        distribution: list[str] = []
        inflammation = "unknown"
        scarring: list[str] = []
        medication_history: list[str] = []
        hormonal: list[str] = []
        skincare: list[str] = []
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
            goals = list(clinical.treatment_goals)
            red_flags = list(clinical.red_flags_input)

        medication_history.extend(ctx.medications or [])
        skincare.extend(ctx.current_products or fallback_ctx.current_products or [])
        if "scar" in lesions and "sẹo mụn" not in scarring:
            scarring.append("sẹo mụn")
        if "post_inflammatory_hyperpigmentation" in lesions and "thâm sau mụn" not in scarring:
            scarring.append("thâm sau mụn")

        demographics = ClinicalDemographics(
            age=ctx.age if ctx.age is not None else fallback_ctx.age,
            sex=ctx.sex or fallback_ctx.sex or "unknown",
            skin_type=ctx.skin_type or fallback_ctx.skin_type or "unknown",
            is_pregnant=bool(ctx.is_pregnant or fallback_ctx.is_pregnant),
            is_breastfeeding=bool(ctx.is_breastfeeding or fallback_ctx.is_breastfeeding),
        )

        missing = []
        if demographics.age is None:
            missing.append("age")
        if not lesions:
            missing.append("lesion_types")
        if not distribution:
            missing.append("distribution")
        if inflammation == "unknown":
            missing.append("inflammation_level")
        if ctx.duration_weeks is None and fallback_ctx.duration_weeks is None:
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
            treatment_goals=_dedupe(goals),
            red_flags=_dedupe(red_flags),
            missing_info=_dedupe(missing),
        )
        plan = ClinicalQueryPlan(
            detected_language=detect_language_heuristic(user.description),
            normalized_case=case,
            missing_info=case.missing_info,
            safety_terms=self._safety_terms(user, case),
            planner_confidence=0.45,
        )
        return self._finalize_plan(plan, user)

    def _finalize_plan(self, plan: ClinicalQueryPlan, user: UserInput) -> ClinicalQueryPlan:
        query_vi, query_en = self._build_queries(plan)
        if not plan.rag_queries.query_vi:
            plan.rag_queries.query_vi = query_vi
        if not plan.rag_queries.query_en:
            plan.rag_queries.query_en = query_en
        if not plan.detected_language or plan.detected_language == "unknown":
            plan.detected_language = detect_language_heuristic(user.description)
        plan.safety_terms = _dedupe([*plan.safety_terms, *self._safety_terms(user, plan.normalized_case)])
        plan.missing_info = _dedupe([*plan.missing_info, *plan.normalized_case.missing_info])
        return plan

    def _build_queries(self, plan: ClinicalQueryPlan) -> tuple[str, str]:
        case = plan.normalized_case
        has_core = bool(case.lesion_types and case.distribution)
        vi_parts = ["mụn trứng cá guideline"]
        en_parts = ["acne vulgaris guideline management"]

        if not has_core:
            vi_parts.extend(["đánh giá ban đầu", "hỏi thêm triệu chứng", "dấu hiệu cần khám da liễu"])
            en_parts.extend(["initial assessment", "insufficient information", "red flags", "when to see dermatologist"])
        else:
            vi_parts.extend(_LESION_VI.get(x, x) for x in case.lesion_types)
            en_parts.extend(_LESION_EN.get(x, x) for x in case.lesion_types)
            vi_parts.extend(_LOCATION_VI.get(x, x) for x in case.distribution)
            en_parts.extend(_LOCATION_EN.get(x, x) for x in case.distribution)
            if case.inflammation_level != "unknown":
                vi_parts.append(f"mức độ viêm {case.inflammation_level}")
                en_parts.append(f"{case.inflammation_level} inflammation")

        demo = case.demographics
        if demo.skin_type != "unknown":
            vi_parts.append(f"da {demo.skin_type}")
            en_parts.append(f"{demo.skin_type} skin")
        if demo.is_pregnant:
            vi_parts.append("mang thai an toàn thuốc trị mụn")
            en_parts.append("pregnancy acne medication safety")
        if demo.is_breastfeeding:
            vi_parts.append("cho con bú an toàn thuốc trị mụn")
            en_parts.append("breastfeeding acne medication safety")
        if case.hormonal_factors:
            vi_parts.extend(case.hormonal_factors)
            en_parts.append("hormonal acne menstrual flare")
        if case.medication_history or case.skincare_products:
            vi_parts.extend(case.medication_history + case.skincare_products)
            en_parts.extend(case.medication_history + case.skincare_products)
        if case.scarring_signs:
            vi_parts.extend(case.scarring_signs)
            en_parts.append("acne scarring post inflammatory marks")
        if case.red_flags:
            vi_parts.extend(case.red_flags)
            en_parts.append("red flags dermatologist referral")

        return " ".join(_dedupe(vi_parts)), " ".join(_dedupe(en_parts))

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
        if case.demographics.is_pregnant:
            terms.append("pregnancy")
        if case.demographics.is_breastfeeding:
            terms.append("breastfeeding")
        return _dedupe(terms)
