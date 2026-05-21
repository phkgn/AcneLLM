from __future__ import annotations
import json
import time

from loguru import logger

from ..schemas import UserInput, AdviseOutput
from ..schemas.clinical import ClinicalQueryPlan
from ..llm.clinical_planner import ClinicalQueryPlanner
from ..llm.ollama_backend import OllamaBackend
from ..llm.prompt_builder import PromptBuilder
from ..guardrails.runner import GuardrailRunner


def _safe_parse(raw: str) -> AdviseOutput:
    try:
        return AdviseOutput.model_validate_json(raw)
    except Exception:
        try:
            data = json.loads(raw)
            return AdviseOutput.model_validate(data)
        except Exception as e:
            logger.warning(f"parse fail, returning fallback: {e}\n---\n{raw[:500]}")
            return AdviseOutput(
                severity="unknown",
                acne_type_primary="unknown",
                causes=["Không thể phân tích phản hồi từ LLM"],
                confidence=0.1,
            )


class LLMOnlyPipeline:
    def __init__(self, llm: OllamaBackend, prompt: PromptBuilder,
                 guardrails: GuardrailRunner,
                 clinical_planner: ClinicalQueryPlanner | None = None):
        self.llm = llm
        self.prompt = prompt
        self.guardrails = guardrails
        self.clinical_planner = clinical_planner

    def run(self, user: UserInput) -> AdviseOutput:
        t0 = time.perf_counter()
        self.guardrails.pre_check(user)
        scope_refusal = self.guardrails.scope_check(user)
        if scope_refusal is not None:
            scope_refusal.model_name = self.llm.model
            scope_refusal.latency_ms = int((time.perf_counter() - t0) * 1000)
            return scope_refusal
        clinical_plan: ClinicalQueryPlan | None = None
        if self.clinical_planner is not None:
            clinical_plan = self.clinical_planner.plan(user)
        sys_p, usr_p = self.prompt.build(
            user,
            None,
            template="llm_only_user.j2",
            clinical_plan=clinical_plan,
        )
        total_chars = len(sys_p) + len(usr_p)
        logger.info(f"LLM-only prompt size: system={len(sys_p)} user={len(usr_p)} total={total_chars}")
        raw = self.llm.generate_json(sys_p, usr_p,
                                     schema=AdviseOutput.model_json_schema(),
                                     temperature=0.3)
        parsed = _safe_parse(raw)
        parsed.mode = "llm_only"
        parsed.model_name = self.llm.model
        parsed.latency_ms = int((time.perf_counter() - t0) * 1000)
        return self.guardrails.post_check(parsed, user)
