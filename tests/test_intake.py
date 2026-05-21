from types import SimpleNamespace

from acne_llm.chat.intake import run_intake
from acne_llm.chat.session import ConversationTurn, get_session_store
from acne_llm.db.jsonl_session_store import JsonlSessionStore
from acne_llm.schemas import AdviseOutput


class _Planner:
    def __init__(self):
        self.calls = 0

    def plan(self, user):
        self.calls += 1
        from acne_llm.schemas.clinical import ClinicalQueryPlan, ClinicalRagQueries

        return ClinicalQueryPlan(rag_queries=ClinicalRagQueries(query_vi=user.description))


def _container(rag_ready=False, scope_refusal=None, session_store=None):
    planner = _Planner()
    guardrails = SimpleNamespace(
        pre_check=lambda user: None,
        scope_check=lambda user: scope_refusal,
    )
    return SimpleNamespace(
        rag_ready=rag_ready,
        guardrails=guardrails,
        clinical_planner=planner,
        session_store=session_store,
    )


def test_intake_preserves_raw_description_and_reuses_clean_snapshot():
    c = _container()

    result = run_intake(c, "MỤN BỌC!!!!! ở cằm", mode_request="auto")

    assert result.user.description == "MỤN BỌC!!!!! ở cằm"
    assert result.clean_text
    assert result.turn_snapshot.clean_text == result.clean_text
    assert result.effective_mode == "llm_only"
    assert c.clinical_planner.calls == 1


def test_intake_folds_prior_snapshot_without_renormalizing_history_text():
    session_id = "test-intake-folds-prior"
    store = get_session_store()
    store.delete(session_id)
    c = _container()

    try:
        first = run_intake(c, "tôi 22 tuổi da dầu", session_id=session_id)
        store.append_turn(
            session_id,
            ConversationTurn(
                role="user",
                content=first.clean_text,
                normalized_snapshot=first.turn_snapshot,
            ),
        )

        second = run_intake(c, "mụn ở cằm", session_id=session_id)

        assert second.user.context.age == 22
        assert second.user.context.skin_type == "oily"
        assert "chin" in (second.user.clinical.lesion_distribution if second.user.clinical else [])
    finally:
        store.delete(session_id)


def test_intake_reads_history_from_container_session_store(tmp_path):
    session_id = "test-intake-container-store"
    store = JsonlSessionStore(str(tmp_path))
    c = _container(session_store=store)

    first = run_intake(c, "tôi 22 tuổi da dầu", session_id=session_id)
    store.append_turn(
        session_id,
        ConversationTurn(
            role="user",
            content=first.clean_text,
            normalized_snapshot=first.turn_snapshot,
        ),
    )

    second = run_intake(c, "mụn ở cằm", session_id=session_id)

    assert len(second.history) == 1
    assert second.user.context.age == 22
    assert second.user.context.skin_type == "oily"


def test_intake_treats_generic_acne_case_as_clarify_when_missing_core_details():
    c = _container()

    result = run_intake(c, "tôi bị mụn")

    assert result.effective_mode == "clarify"
    assert result.completeness is not None
    assert result.completeness.level == "none"
    assert result.completeness.missing_fields == ["distribution"]


def test_intake_returns_hard_scope_refusal():
    refusal = AdviseOutput(
        severity="unknown",
        acne_type_primary="unknown",
        causes=["out"],
        confidence=0,
    )
    c = _container(scope_refusal=refusal)

    result = run_intake(c, "giải phương trình")

    assert result.effective_mode == "refuse"
    assert result.scope_decision == "refuse_hard"
    assert result.scope_refusal is refusal
