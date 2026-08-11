"""Ba bug hanh vi sua o Phase 6 -- moi bug mot check nho nhat co the fail."""
from __future__ import annotations

import threading
from types import SimpleNamespace

from acne_llm.chat.fallback.intent_router import RouteDecision
from acne_llm.chat.intake import run_intake
from acne_llm.chat.session import get_session_store
from acne_llm.chat.unified_intake import UnifiedIntake
from acne_llm.guardrails.runner import GuardrailRunner


# ── Bug 2: compute_route_flags goi thieu `user` ──────────────────────────────

class _StubRouter:
    """Gia lap UnifiedIntake.classify: tra intent nhung route_flags RONG.

    Day chinh la cau hinh production (INTAKE_MODE=unified). Duong rule fallback
    khong dinh bug vi `route_intent` co truyen `user` vao compute_route_flags;
    duong unified/semantic thi khong, nen co clinical bi mat im lang.
    """

    def classify(self, clean_text, history):
        return RouteDecision(
            primary_intent="advise",
            confidence=0.95,
            source="llm",
            reason_code="unified_intake",
        )


def test_red_flag_lam_sang_bat_duoc_co_urgency():
    """compute_route_flags chay TRUOC extract nen khong thay clinical.

    Ban cu: tren duong unified, `has_red_flags` luon False -> moi red flag
    intaker trich duoc deu khong bat canh bao khan o _safety.
    """
    c = SimpleNamespace(
        rag_ready=False,
        session_store=get_session_store(),
        guardrails=SimpleNamespace(pre_check=lambda user: None),
        llm_router=_StubRouter(),
        semantic_router=None,
        settings=SimpleNamespace(extractor_mode="rule"),
    )
    # "mụn bọc có mủ" KHONG khop tu nao trong _URGENCY_TERMS (bang do co
    # "mụn mủ" chu khong phai "có mủ"), nen co urgency CHI co the den tu
    # red_flags_input ma extractor sinh ra sau buoc extract.
    result = run_intake(c, "mụn bọc có mủ")

    assert result.user.clinical is not None
    assert result.user.clinical.red_flags_input  # extractor co bat duoc
    assert "urgency_red_flag" in result.route_decision.route_flags


# ── Bug 1: _contains_any khop chuoi con ──────────────────────────────────────

def test_acne_scope_khong_khop_chuoi_con():
    """"co" (co) nam trong "con" -> ban cu tra True cho cau khong lien quan."""
    assert GuardrailRunner.is_acne_scope_text("con chó nhà tôi bị ốm") is False
    assert GuardrailRunner.is_acne_scope_text("mai tôi đi làm") is False
    # ...nhung cau that su ve mun van phai True
    assert GuardrailRunner.is_acne_scope_text("tôi bị mụn ở cằm") is True
    assert GuardrailRunner.is_acne_scope_text("da tôi bị mụn ẩn ở trán") is True


# ── Bug 3: cache mot-o cua UnifiedIntake ─────────────────────────────────────

class _CountingLLM:
    """Dem so lan goi model, tra JSON hop le."""

    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def generate_text(self, system, user, temperature=0.0, response_format=None):
        with self._lock:
            self.calls += 1
        return (
            '{"intent":"knowledge","confidence":0.9,'
            f'"description":{user!r}'.replace("'", '"')
            + ',"context":{},"clinical":null}'
        )


def test_cache_khong_bi_de_boi_request_khac():
    """classify(A) -> classify(B) -> run(A): ban cu mat cache A, goi model 3 lan."""
    llm = _CountingLLM()
    intake = UnifiedIntake(llm, model="test", timeout=5.0)

    intake.classify("cau hoi A", [])
    intake.classify("cau hoi B", [])
    intake.run(clean_text="cau hoi A", clean_text_no_accent="cau hoi A",
               mode="hybrid", history=[])

    # 2 truy van khac nhau -> dung 2 lan goi model, khong phai 3
    assert llm.calls == 2


def test_cache_van_gop_classify_va_run_cung_luot():
    llm = _CountingLLM()
    intake = UnifiedIntake(llm, model="test", timeout=5.0)

    intake.classify("mot cau hoi", [])
    intake.run(clean_text="mot cau hoi", clean_text_no_accent="mot cau hoi",
               mode="hybrid", history=[])

    assert llm.calls == 1
