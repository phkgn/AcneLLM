"""Jinja2 prompt builder."""
from __future__ import annotations
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ..schemas import UserInput, RetrievalOutput, VisionOutput
from ..schemas.clinical import ClinicalQueryPlan


def _escape_jinja(value: str) -> str:
    """Neutralise Jinja2 delimiter sequences so user text cannot
    alter template structure or inject instructions at render time.
    """
    return (
        value
        .replace("{{", "{ {")
        .replace("}}", "} }")
        .replace("{%", "{ %")
        .replace("%}", "% }")
        .replace("{#", "{ #")
        .replace("#}", "# }")
    )


class PromptBuilder:
    def __init__(self, templates_dir: str = "config/prompts"):
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True, lstrip_blocks=True,
        )

    def _vision_summary(self, v: VisionOutput | None) -> str:
        if not v:
            return "khong co du lieu hinh anh"
        parts = [f"muc do uoc tinh: {v.severity_estimate}"]
        if v.lesion_counts:
            parts.append("dem ton thuong: " + ", ".join(f"{k}={v2}" for k, v2 in v.lesion_counts.items()))
        if v.skin_regions:
            parts.append("vung: " + ", ".join(v.skin_regions))
        if v.notes:
            parts.append(f"ghi chu: {v.notes}")
        return "; ".join(parts)

    def _context_block(self, retrieval: RetrievalOutput | None, max_chars: int = 6000) -> str:
        if not retrieval or not retrieval.chunks:
            return "(khong co ngu canh tu tri thuc)"
        blocks: list[str] = []
        used_chars = 0
        for i, c in enumerate(retrieval.chunks, 1):
            meta = c.metadata or {}
            header = f"[Nguon {i}] {meta.get('title', '?')} ({meta.get('source', '?')})\nchunk_ref={c.chunk_id}\n"
            text = c.text
            remaining = max_chars - used_chars
            if remaining <= 0:
                break
            # Reserve space for header + separator
            header_len = len(header)
            sep_len = 5  # "\n---\n"
            text_budget = remaining - header_len - sep_len
            if text_budget <= 0:
                break
            if len(text) > text_budget:
                text = text[:text_budget].rsplit(" ", 1)[0].strip() + "..."
            block = header + text
            blocks.append(block)
            used_chars += len(block) + sep_len
        return "\n---\n".join(blocks) if blocks else "(khong co ngu canh tu tri thuc)"

    def _clinical_summary(self, user: UserInput) -> str:
        c = user.clinical
        if not c:
            return "khong co du lieu clinical co cau truc"
        parts: list[str] = []
        if c.lesion_types:
            parts.append("loai ton thuong: " + ", ".join(c.lesion_types))
        if c.lesion_distribution:
            parts.append("phan bo: " + ", ".join(c.lesion_distribution))
        if c.inflammation_level:
            parts.append(f"muc do viem: {c.inflammation_level}")
        if c.scarring_signs:
            parts.append("dau hieu seo/tham: " + ", ".join(c.scarring_signs))
        if c.medication_history:
            parts.append("tien su dung thuoc: " + ", ".join(c.medication_history))
        if c.hormonal_factors:
            parts.append("yeu to noi tiet/khoi phat: " + ", ".join(c.hormonal_factors))
        if c.skincare_products:
            parts.append("san pham cham soc da: " + ", ".join(c.skincare_products))
        if c.treatment_goals:
            parts.append("mong muon dieu tri: " + ", ".join(c.treatment_goals))
        if c.red_flags_input:
            parts.append("red flags tu nguoi dung: " + ", ".join(c.red_flags_input))
        return "; ".join(parts) if parts else "clinical rong"

    def _clinical_plan_summary(self, plan: ClinicalQueryPlan | None) -> str:
        if not plan:
            return "chua co clinical plan"
        return plan.model_dump_json(exclude_none=True)

    def system(self) -> str:
        return self.env.get_template("system.j2").render()

    def build(
        self,
        user: UserInput,
        retrieval: RetrievalOutput | None,
        template: str = "hybrid_user.j2",
        detected_language: str = "unknown",
        query_vi: str = "",
        query_en: str = "",
        max_context_chars: int = 6000,
        clinical_plan: ClinicalQueryPlan | None = None,
    ) -> tuple[str, str]:
        sys_p = self.system()
        # Escape Jinja delimiters in all free-text fields to prevent
        # template-injection via user-controlled input.
        safe_description = _escape_jinja(user.description)
        safe_allergies = _escape_jinja(", ".join(user.context.allergies) or "khong")
        safe_products = _escape_jinja(", ".join(user.context.current_products) or "khong")
        safe_medications = _escape_jinja(", ".join(user.context.medications) or "khong")
        safe_vision = _escape_jinja(self._vision_summary(user.vision))
        safe_clinical = _escape_jinja(self._clinical_summary(user))
        safe_qv = _escape_jinja(query_vi)
        safe_qe = _escape_jinja(query_en)
        safe_context = _escape_jinja(self._context_block(retrieval, max_chars=max_context_chars))
        safe_clinical_plan = _escape_jinja(self._clinical_plan_summary(clinical_plan))

        user_p = self.env.get_template(template).render(
            description=safe_description,
            age=user.context.age,
            sex=user.context.sex,
            skin_type=user.context.skin_type,
            is_pregnant=user.context.is_pregnant,
            is_breastfeeding=user.context.is_breastfeeding,
            allergies=safe_allergies,
            current_products=safe_products,
            medications=safe_medications,
            duration_weeks=user.context.duration_weeks,
            vision_summary=safe_vision,
            clinical_summary=safe_clinical,
            detected_language=detected_language,
            query_vi=safe_qv,
            query_en=safe_qe,
            retrieved_context=safe_context,
            clinical_plan=safe_clinical_plan,
        )
        return sys_p, user_p

    def build_clinical_planner(self, user: UserInput) -> str:
        safe_description = _escape_jinja(user.description)
        safe_allergies = _escape_jinja(", ".join(user.context.allergies) or "khong")
        safe_products = _escape_jinja(", ".join(user.context.current_products) or "khong")
        safe_medications = _escape_jinja(", ".join(user.context.medications) or "khong")
        safe_vision = _escape_jinja(self._vision_summary(user.vision))
        safe_clinical = _escape_jinja(self._clinical_summary(user))

        return self.env.get_template("clinical_planner_user.j2").render(
            description=safe_description,
            age=user.context.age,
            sex=user.context.sex,
            skin_type=user.context.skin_type,
            is_pregnant=user.context.is_pregnant,
            is_breastfeeding=user.context.is_breastfeeding,
            allergies=safe_allergies,
            current_products=safe_products,
            medications=safe_medications,
            duration_weeks=user.context.duration_weeks,
            vision_summary=safe_vision,
            clinical_summary=safe_clinical,
        )
