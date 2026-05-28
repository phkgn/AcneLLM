from types import SimpleNamespace

from acne_llm.chat.intake import _force_advise_route, run_intake
from acne_llm.chat.intent_router import RouteDecision
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


def test_intake_soft_scope_followups_fold_history_and_build_plan(tmp_path):
    session_id = "test-soft-followups"
    store = JsonlSessionStore(str(tmp_path))
    c = _container(rag_ready=True, session_store=store)

    first = run_intake(
        c,
        "tôi 36 tuổi bị mụn ngay mông, mụn có mủ đau nhiều",
        session_id=session_id,
    )
    store.append_turn(
        session_id,
        ConversationTurn(
            role="user",
            content=first.clean_text,
            normalized_snapshot=first.turn_snapshot,
            metadata=first.route_decision.metadata(),
        ),
    )
    store.append_turn(
        session_id,
        ConversationTurn(role="assistant", content="answer", mode="hybrid"),
    )

    home = run_intake(c, "có phương pháp điều trị tại nhà k", session_id=session_id)
    cooking_oil = run_intake(c, "tôi dùng dầu ăn dc kop", session_id=session_id)

    for result in (home, cooking_oil):
        assert result.scope_decision == "pass_to_llm_soft"
        assert result.effective_mode == "hybrid"
        assert result.route_decision.primary_intent == "advise"
        assert result.route_decision.query_subject == "self"
        assert result.route_decision.reason_code == "short_followup_in_session"
        assert result.clinical_plan is not None
        assert result.user.context.age == 36
        assert result.user.context.skin_type is None
        assert result.user.clinical is not None
        assert "pustule" in result.user.clinical.lesion_types
        assert "other" in result.user.clinical.lesion_distribution

    assert home.clean_text == "có phương pháp điều trị tại nhà không"
    assert cooking_oil.clean_text == "tôi dùng dầu ăn được không"


def test_intake_treats_generic_acne_case_as_soft_missing_core_hint():
    c = _container()

    result = run_intake(c, "tôi bị mụn")

    assert result.effective_mode == "llm_only"
    assert result.completeness is not None
    assert result.completeness.level == "none"
    assert result.completeness.missing_fields == ["distribution"]


def test_intake_extracts_safety_terms_without_clinical_plan_for_knowledge():
    c = _container(rag_ready=True)

    result = run_intake(c, "isotretinoin là gì và vì sao nguy hiểm khi mang thai")

    assert "isotretinoin" in result.safety_terms
    assert any(term in result.safety_terms for term in ("mang thai", "pregnancy"))
    assert result.route_decision.primary_intent == "knowledge"
    assert result.clinical_plan is None


def test_intake_mixed_face_and_genital_scope_is_not_hard_rejected():
    c = _container()

    result = run_intake(c, "tôi bị mụn ở mặt và vùng kín")

    assert result.scope_refusal is None
    assert result.route_decision is not None
    assert "mixed_genital_scope" in result.route_decision.route_flags


def test_force_advise_route_returns_new_decision_without_mutating_original():
    original = RouteDecision(
        primary_intent="clarify",
        confidence=0.4,
        query_subject="self",
        turn_type="clarify",
        route_flags=["existing"],
        reason_code="needs_more",
    )

    updated = _force_advise_route(original, "clarify_loop_hard_stop")

    assert original.primary_intent == "clarify"
    assert original.turn_type == "clarify"
    assert updated.primary_intent == "advise"
    assert updated.turn_type == "answer"
    assert "clarify_loop_break" in updated.route_flags


def test_intake_does_not_fold_self_history_into_general_knowledge():
    session_id = "test-knowledge-no-fold"
    store = get_session_store()
    store.delete(session_id)
    c = _container()

    try:
        first = run_intake(c, "tôi 22 tuổi da dầu bị mụn ở cằm", session_id=session_id)
        store.append_turn(
            session_id,
            ConversationTurn(
                role="user",
                content=first.clean_text,
                normalized_snapshot=first.turn_snapshot,
                metadata=first.route_decision.metadata(),
            ),
        )

        second = run_intake(c, "tại sao bị mụn bọc?", session_id=session_id)

        assert second.route_decision.primary_intent == "knowledge"
        assert second.route_decision.query_subject == "general"
        assert second.user.context.age is None
        assert second.user.context.skin_type is None
        assert second.completeness is None
        assert second.clinical_plan is None
    finally:
        store.delete(session_id)


def test_intake_other_subject_is_current_turn_only_and_no_snapshot():
    session_id = "test-other-subject-no-fold"
    store = get_session_store()
    store.delete(session_id)
    c = _container()

    try:
        first = run_intake(c, "tôi 22 tuổi da dầu bị mụn ở cằm", session_id=session_id)
        store.append_turn(
            session_id,
            ConversationTurn(
                role="user",
                content=first.clean_text,
                normalized_snapshot=first.turn_snapshot,
                metadata=first.route_decision.metadata(),
            ),
        )

        second = run_intake(c, "bạn tôi bị mụn ở lưng nên làm gì", session_id=session_id)

        assert second.route_decision.primary_intent == "advise"
        assert second.route_decision.query_subject == "other"
        assert second.user.context.age is None
        assert second.turn_snapshot is None
        assert second.completeness is None
        assert second.clinical_plan is None
        assert "back" in second.normalized_query
        assert "chin" not in second.normalized_query
    finally:
        store.delete(session_id)


def test_intake_greeting_has_no_normalized_snapshot():
    c = _container()

    result = run_intake(c, "xin chào")

    assert result.route_decision.query_subject == "general"
    assert result.turn_snapshot is None


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
