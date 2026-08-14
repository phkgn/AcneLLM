"""The ONLY file in `ablation/` that imports product code.

Everything else in this package talks to the system under test through the three
seams below. If the product refactors, this file changes and nothing else does.

Seams:
    intake_real(message)          -> IntakeState      (module 1 under test)
    intake_from_slots(msg, slots) -> IntakeState      (module 1 replaced by oracle)
    retrieve_real(state)          -> list[str]        (module 2 under test)
    generate_real(state, ctx)     -> str              (module 3 under test)

The product's own orchestrator fuses intake+retrieve+prompt in one call with no
injection point, so the three steps are re-wired here from the same components.
That is deliberate: an ablation harness needs a seam the runtime does not have.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import Any

from .cases import SLOT_KEYS

# Product imports, all confined to this file. Only the pydantic schemas are
# imported at module level; anything that pulls Ollama/Chroma is imported inside
# the function that needs it, so the oracle-only path (and `run.py --dry-run`)
# works on a machine with no model server and no vector store.
from acne_llm.schemas import (
    AcneClinicalInput, RetrievalOutput, RetrievedChunk, UserContext, UserInput,
)

_LESIONS = {"comedone", "whitehead", "blackhead", "closed_comedone", "papule",
            "pustule", "nodule", "cyst", "scar",
            "post_inflammatory_hyperpigmentation", "other"}
_REGIONS = {"forehead", "cheeks", "chin", "jawline", "nose", "around_mouth",
            "back", "chest", "shoulders", "neck", "t_zone", "other"}
_INFLAM = {"none", "mild", "moderate", "severe", "unknown"}
_TEMPLATE = {"knowledge": "knowledge_user.j2", "clarify": "clarify_user.j2",
             "reject": "reject_user.j2", "refuse": "refuse_user.j2"}


@dataclass
class IntakeState:
    """What module 1 hands to modules 2 and 3. `slots` is the scored surface."""
    slots: dict
    query: str
    user: Any                                   # UserInput
    route_flags: list = field(default_factory=list)
    route_metadata: dict = field(default_factory=dict)
    safety_terms: list = field(default_factory=list)
    refused: bool = False


@functools.lru_cache(maxsize=1)
def container():
    from acne_llm.config import settings
    from acne_llm.di import build_container
    return build_container(settings)


# ── module 1 ─────────────────────────────────────────────────────────────────
def intake_real(message: str) -> IntakeState:
    from acne_llm.chat.intake import run_intake
    r = run_intake(container(), message, session_id=None, mode_request="auto")
    rd = r.route_decision
    intent = str((rd.metadata() if rd else {}).get("primary_intent") or "advise")
    if r.scope_refusal is not None or r.effective_mode == "refuse":
        intent = "refuse"
    return IntakeState(
        slots=_slots_from_user(r.user, intent),
        query=r.normalized_query or message,
        user=r.user,
        route_flags=list(rd.route_flags) if rd else [],
        route_metadata=rd.metadata() if rd else {},
        safety_terms=list(r.safety_terms),
        refused=r.scope_refusal is not None or r.effective_mode == "refuse",
    )


def intake_from_slots(message: str, slots: dict) -> IntakeState:
    """Oracle intaker: golden slots in, a state the other two modules accept out."""
    g = dict(slots)
    intent = str(g.get("intent") or "advise")
    user = UserInput(
        description=message,
        context=UserContext(
            age=g.get("age"), sex=g.get("sex"),
            skin_type=g.get("skin_type"), duration_weeks=g.get("duration_weeks"),
            is_pregnant=bool(g.get("is_pregnant")),
            is_breastfeeding=bool(g.get("is_breastfeeding")),
            allergies=list(g.get("allergies") or []),
            medications=list(g.get("medications") or []),
            current_products=list(g.get("current_products") or []),
        ),
        clinical=AcneClinicalInput(
            lesion_types=[x for x in (g.get("lesion_types") or []) if x in _LESIONS],
            lesion_distribution=[x for x in (g.get("lesion_distribution") or []) if x in _REGIONS],
            inflammation_level=(g.get("inflammation_level") or "unknown")
            if (g.get("inflammation_level") or "unknown") in _INFLAM else "unknown",
            medication_history=list(g.get("medications") or []),
            skincare_products=list(g.get("current_products") or []),
            treatment_goals=list(g.get("treatment_goals") or []),
            red_flags_input=list(g.get("red_flags") or []),
        ),
        mode="hybrid",
    )
    safety = []
    if g.get("is_pregnant"):
        safety.append("pregnancy")
    if g.get("is_breastfeeding"):
        safety.append("breastfeeding")
    safety += [str(m).lower() for m in (g.get("medications") or [])]
    # ponytail: oracle query = the golden slot terms + raw message. A separate
    # "oracle query rewriter" would be a 4th module; add it only if the retrieval
    # arm turns out to be query-bound rather than index-bound.
    terms = " ".join(str(x) for k in ("lesion_types", "lesion_distribution",
                                      "medications", "treatment_goals")
                     for x in (g.get(k) or []))
    return IntakeState(
        slots={k: g[k] for k in SLOT_KEYS if k in g},
        query=f"{message} {terms}".strip(),
        user=user,
        route_metadata={"primary_intent": intent},
        safety_terms=list(dict.fromkeys(safety)),
        refused=intent == "refuse",
    )


def _slots_from_user(user, intent: str) -> dict:
    ctx, cl = user.context, (user.clinical or AcneClinicalInput())
    return {
        "intent": intent,
        "age": ctx.age, "sex": ctx.sex, "skin_type": ctx.skin_type,
        "duration_weeks": ctx.duration_weeks,
        "is_pregnant": bool(ctx.is_pregnant),
        "is_breastfeeding": bool(ctx.is_breastfeeding),
        "allergies": list(ctx.allergies), "medications": list(ctx.medications),
        "current_products": list(ctx.current_products),
        "lesion_types": list(cl.lesion_types),
        "inflammation_level": cl.inflammation_level,
        "lesion_distribution": list(cl.lesion_distribution),
        "treatment_goals": list(cl.treatment_goals),
        "red_flags": list(cl.red_flags_input),
    }


# ── module 2 ─────────────────────────────────────────────────────────────────
def _retrieval(state: IntakeState):
    # ponytail: no cache here — run.py already memoises retrieval per (case, arm[0]).
    if state.refused:
        return None
    from acne_llm.chat._retrieval import retrieve_for_chat
    return retrieve_for_chat(
        container(), state.user, route_flags=state.route_flags,
        normalized_query=state.query, safety_terms=state.safety_terms,
    )


def retrieve_real(state: IntakeState) -> list[str]:
    """Passage texts for the generator."""
    out = _retrieval(state)
    return [c.text for c in out.chunks] if out else []


def retrieved_ids(state: IntakeState) -> list[str]:
    """Chunk ids, for recall@k against a golden id list when one exists."""
    out = _retrieval(state)
    return [c.chunk_id for c in out.chunks] if out else []


# ── module 3 ─────────────────────────────────────────────────────────────────
def generate_real(state: IntakeState, contexts: list[str]) -> str:
    c = container()
    retrieval = RetrievalOutput(
        query=state.query,
        chunks=[RetrievedChunk(chunk_id=f"ctx{i}", source="ablation", text=t,
                               score=1.0 - i * 0.01)
                for i, t in enumerate(contexts)],
        retrieval_mode="hybrid", num_chunks=len(contexts),
        avg_score=1.0 if contexts else 0.0,
    ) if contexts else None
    intent = str(state.route_metadata.get("primary_intent") or "advise")
    system, user = c.prompt.build(
        user=state.user, retrieval=retrieval,
        template=_TEMPLATE.get(intent, "stream_user.j2"),
        detected_language="unknown", query_vi="",
        max_context_chars=getattr(c.settings, "chat_max_context_chars", 4500),
        history=[], route_metadata=state.route_metadata,
        completeness_hint="", confirmed_profile={},
    )
    text = c.llm.generate_text(system, user, temperature=0.0)
    return re.sub(r"[一-鿿぀-ゟ゠-ヿ가-힯]+", "", text)


def demo() -> None:
    """Offline check of the oracle path only — no Ollama, no Chroma needed."""
    s = intake_from_slots("bầu 3 tháng, mụn viêm ở cằm", {
        "intent": "advise", "is_pregnant": True, "medications": ["tretinoin"],
        "lesion_types": ["papule", "not_a_lesion"], "lesion_distribution": ["chin"],
        "inflammation_level": "bogus",
    })
    assert s.user.context.is_pregnant is True
    assert s.user.clinical.lesion_types == ["papule"]        # bad literal dropped
    assert s.user.clinical.inflammation_level == "unknown"   # bad literal coerced
    assert "pregnancy" in s.safety_terms and "tretinoin" in s.safety_terms
    assert "chin" in s.query and s.slots["intent"] == "advise"
    assert "not_a_lesion" in s.slots["lesion_types"]         # slots keep gold verbatim
    print("repo_adapter.py OK (oracle path)")


if __name__ == "__main__":
    demo()
