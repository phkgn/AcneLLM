from types import SimpleNamespace

from acne_llm.chat.intent_router import ClassifierResult, route_intent
from acne_llm.chat.intake import run_intake
from acne_llm.chat.session import ConversationTurn, SessionStore


class _Planner:
    def __init__(self):
        self.calls = 0

    def plan(self, user):
        self.calls += 1
        from acne_llm.schemas.clinical import ClinicalQueryPlan, ClinicalRagQueries

        return ClinicalQueryPlan(rag_queries=ClinicalRagQueries(query_vi=user.description))


def _container(session_store=None, classifier=None, classifier_enabled=False):
    planner = _Planner()
    guardrails = SimpleNamespace(
        pre_check=lambda user: None,
        scope_check=lambda user: None,
    )
    settings = SimpleNamespace(
        chat_use_llm_planner=True,
        intent_router_enabled=classifier_enabled,
        intent_router_min_confidence=0.80,
        intent_router_tie_margin=0.10,
    )
    return (
        SimpleNamespace(
            rag_ready=True,
            guardrails=guardrails,
            clinical_planner=planner,
            session_store=session_store or SessionStore(),
            settings=settings,
            intent_classifier=classifier,
        ),
        planner,
    )


def test_product_query_skips_completeness():
    c, planner = _container()

    result = run_intake(c, "top 5 kem chống nắng cho da dầu")

    assert result.effective_mode == "hybrid"
    assert result.route_decision.primary_intent == "knowledge"
    assert result.completeness is None
    assert planner.calls == 1


def test_food_and_drug_knowledge_skip_completeness():
    c, _ = _container()
    food = run_intake(c, "nên ăn mì cay khi bị mụn không?")
    drug = run_intake(c, "vì sao isotretinoin gây khô môi?")

    assert food.route_decision.primary_intent == "knowledge"
    assert food.completeness is None
    assert drug.route_decision.primary_intent == "knowledge"
    assert drug.completeness is None


def test_personal_generic_advise_still_clarifies():
    c, planner = _container()

    result = run_intake(c, "tôi bị mụn phải làm sao")

    assert result.effective_mode == "clarify"
    assert result.route_decision.primary_intent == "advise"
    assert result.completeness is not None
    assert result.completeness.missing_fields == ["distribution"]
    assert planner.calls == 0


def test_partial_advise_with_lesion_and_location_is_sufficient():
    c, planner = _container()

    result = run_intake(c, "mụn viêm ở trán nên làm gì")

    assert result.effective_mode == "hybrid"
    assert result.route_decision.primary_intent == "advise"
    assert "partial_advise" in result.route_decision.route_flags
    assert result.completeness is not None
    assert result.completeness.level == "sufficient"
    assert planner.calls == 1


def test_session_context_product_question_does_not_ask_skin_type_again():
    store = SessionStore()
    session_id = "test-oily-sunscreen"
    c, _ = _container(session_store=store)

    first = run_intake(c, "da tôi dầu", session_id=session_id)
    store.append_turn(
        session_id,
        ConversationTurn(
            role="user",
            content=first.clean_text,
            normalized_snapshot=first.turn_snapshot,
            metadata=first.route_decision.metadata() if first.route_decision else {},
        ),
    )
    second = run_intake(c, "vậy nên dùng kem chống nắng gì?", session_id=session_id)

    assert second.user.context.skin_type == "oily"
    assert second.route_decision.primary_intent == "knowledge"
    assert second.completeness is None


def test_repeated_question_flag_is_set():
    store = SessionStore()
    session_id = "test-repeat"
    c, _ = _container(session_store=store)
    q = "nên ăn mì cay khi bị mụn không?"

    first = run_intake(c, q, session_id=session_id)
    store.append_turn(
        session_id,
        ConversationTurn(
            role="user",
            content=first.clean_text,
            normalized_snapshot=first.turn_snapshot,
            metadata=first.route_decision.metadata(),
        ),
    )
    store.append_turn(session_id, ConversationTurn(role="assistant", content="answer", mode="hybrid"))

    second = run_intake(c, q, session_id=session_id)

    assert second.route_decision.primary_intent == "knowledge"
    assert "repeated_question" in second.route_decision.route_flags


class _Classifier:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = 0

    def classify(self, message, signals):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


def _fake_user(description="mụn"):
    return SimpleNamespace(
        description=description,
        context=SimpleNamespace(
            age=None,
            sex=None,
            skin_type=None,
            current_products=[],
            medications=[],
            duration_weeks=None,
        ),
        clinical=None,
    )


def test_classifier_disabled_is_not_called():
    classifier = _Classifier(
        ClassifierResult(primary_intent="knowledge", confidence=0.99)
    )
    settings = SimpleNamespace(intent_router_enabled=False)

    decision = route_intent("mụn", _fake_user(), [], settings, classifier)

    assert classifier.calls == 0
    assert decision.source == "rule"


def test_classifier_error_falls_back_to_rule():
    classifier = _Classifier(exc=TimeoutError("slow"))
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )
    user = _fake_user()

    decision = route_intent("mụn", user, [], settings, classifier)

    assert classifier.calls == 1
    assert decision.classifier_used
    assert decision.source == "hybrid"
    assert "classifier_error" in decision.reason_code


def test_classifier_low_confidence_falls_back_to_rule():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.55, "advise": 0.45},
            confidence=0.55,
        )
    )
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )
    user = _fake_user()

    decision = route_intent("mụn", user, [], settings, classifier)

    assert decision.classifier_used
    assert decision.source == "hybrid"
    assert "classifier_low_confidence" in decision.reason_code


def test_classifier_high_confidence_is_accepted_for_ambiguous_rule():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.91, "advise": 0.04, "clarify": 0.03, "reject": 0.02},
            confidence=0.91,
            reason_code="micro_knowledge",
        )
    )
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )
    user = _fake_user()

    decision = route_intent("mụn", user, [], settings, classifier)

    assert decision.primary_intent == "knowledge"
    assert decision.source == "micro_model"
    assert decision.reason_code == "micro_knowledge"


def test_classifier_tie_marks_ambiguous_and_keeps_rule():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.84, "advise": 0.80},
            confidence=0.84,
            reason_code="tie",
        )
    )
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )
    user = _fake_user()

    decision = route_intent("mụn", user, [], settings, classifier)

    assert decision.source == "hybrid"
    assert "ambiguous_intent" in decision.route_flags
    assert "classifier_tie" in decision.reason_code
