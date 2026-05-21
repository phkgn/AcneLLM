from __future__ import annotations
import json
import re
import time

from loguru import logger

from ..schemas import UserInput, AdviseOutput
from ..schemas.clinical import ClinicalQueryPlan
from ..llm.clinical_planner import ClinicalQueryPlanner
from ..llm.ollama_backend import OllamaBackend
from ..llm.prompt_builder import PromptBuilder
from ..guardrails.runner import GuardrailRunner
from ..chat.session import ConversationTurn


def _safe_parse(raw: str) -> AdviseOutput:
    try:
        return AdviseOutput.model_validate_json(raw)
    except Exception:
        pass
    try:
        data = json.loads(raw)
        return AdviseOutput.model_validate(data)
    except Exception:
        pass
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return AdviseOutput.model_validate_json(m.group())
        except Exception:
            try:
                return AdviseOutput.model_validate(json.loads(m.group()))
            except Exception:
                pass
    logger.warning(f"[safe_parse] All parse attempts failed: {raw[:400]}")
    return AdviseOutput(
        severity="unknown",
        acne_type_primary="unknown",
        causes=["Khong the phan tich phan hoi tu LLM -- vui long thu lai."],
        confidence=0.1,
    )


class LLMOnlyPipeline:
    def __init__(self, llm: OllamaBackend, prompt: PromptBuilder,
                 guardrails: GuardrailRunner,
                 clinical_planner: ClinicalQueryPlanner | None = None,
                 use_llm_planner: bool = False):
        self.llm = llm
        self.prompt = prompt
        self.guardrails = guardrails
        self.clinical_planner = clinical_planner
        # Bug C fix: lưu use_llm_planner để _clinical_plan() có thể check
        self.use_llm_planner = use_llm_planner

    def _clinical_plan(self, user: UserInput) -> ClinicalQueryPlan | None:
        if self.clinical_planner is None or not self.use_llm_planner:
            return None
        return self.clinical_planner.plan(user)

    def run(
        self,
        user: UserInput,
        clinical_plan: ClinicalQueryPlan | None = None,
        prechecked: bool = False,
        history: list[ConversationTurn] | None = None,
        route_metadata: dict | None = None,
        completeness_hint: str | None = None,
    ) -> AdviseOutput:
        t0 = time.perf_counter()
        if not prechecked:
            self.guardrails.pre_check(user)
            scope_refusal = self.guardrails.scope_check(user)
            if scope_refusal is not None:
                scope_refusal.model_name = self.llm.model
                scope_refusal.latency_ms = int((time.perf_counter() - t0) * 1000)
                return scope_refusal
        if clinical_plan is None:
            clinical_plan = self._clinical_plan(user)
        sys_p, usr_p = self.prompt.build(
            user,
            None,
            template="llm_only_user.j2",
            clinical_plan=clinical_plan,
            history=history,
            route_metadata=route_metadata,
            completeness_hint=completeness_hint,
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
