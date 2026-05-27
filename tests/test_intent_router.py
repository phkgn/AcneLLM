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
    assert planner.calls == 0


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

    assert result.effective_mode == "hybrid"
    assert result.route_decision.primary_intent == "advise"
    assert result.route_decision.query_subject == "self"
    assert result.completeness is not None
    assert result.completeness.missing_fields == ["distribution"]
    assert planner.calls == 1


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

    assert second.user.context.skin_type is None
    assert second.route_decision.primary_intent == "knowledge"
    assert second.route_decision.query_subject == "general"
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


def test_classifier_override_preserves_query_subject():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.91, "advise": 0.04},
            confidence=0.91,
            reason_code="micro_knowledge",
        )
    )
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )

    decision = route_intent("ban toi bi mun o cam nen lam gi", _fake_user(), [], settings, classifier)

    assert decision.primary_intent == "knowledge"
    assert decision.query_subject == "other"
    assert decision.source == "micro_model"


def test_classifier_reject_stops_intake_static():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="reject",
            scores={"reject": 0.95, "knowledge": 0.02},
            confidence=0.95,
            reason_code="micro_reject",
        )
    )
    c, planner = _container(classifier=classifier, classifier_enabled=True)

    result = run_intake(c, "giải phương trình bậc hai")

    assert result.effective_mode == "refuse"
    assert result.scope_refusal is not None
    assert result.turn_snapshot is None
    assert result.route_decision.primary_intent == "reject"
    assert planner.calls == 0


def test_urgent_personal_case_bypasses_classifier_override():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.95, "advise": 0.02},
            confidence=0.95,
            reason_code="micro_knowledge",
        )
    )
    c, planner = _container(classifier=classifier, classifier_enabled=True)

    result = run_intake(
        c,
        "tôi bị mụn mủ sưng tấy lan rộng, đau nhiều, sốt, "
        "không cải thiện sau 48h giờ làm sao",
    )

    assert classifier.calls == 0
    assert result.route_decision.primary_intent == "advise"
    assert result.route_decision.query_subject == "self"
    assert result.route_decision.reason_code == "urgent_personal_case"
    assert "urgency_red_flag" in result.route_decision.route_flags
    assert "urgent_personal_case" in result.route_decision.route_flags
    assert planner.calls == 1


def test_urgent_implicit_personal_evaluation_bypasses_classifier():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.95, "advise": 0.02},
            confidence=0.95,
            reason_code="micro_knowledge",
        )
    )
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )
    from acne_llm.chat.normalizer import normalize_chat_message

    message = "mụn mủ đau nhiều sốt có nguy hiểm không"
    user = normalize_chat_message(message)

    decision = route_intent(message, user, [], settings, classifier)

    assert classifier.calls == 0
    assert decision.primary_intent == "advise"
    assert decision.query_subject == "self"
    assert decision.source == "rule"
    assert decision.reason_code == "urgent_personal_case"
    assert "urgent_personal_case" in decision.route_flags


def test_pure_pustule_knowledge_can_use_classifier_without_urgent_hard_rule():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="knowledge",
            scores={"knowledge": 0.95, "advise": 0.02},
            confidence=0.95,
            reason_code="micro_knowledge",
        )
    )
    settings = SimpleNamespace(
        intent_router_enabled=True,
        intent_router_min_confidence=0.8,
        intent_router_tie_margin=0.1,
    )
    from acne_llm.chat.normalizer import normalize_chat_message

    message = "mụn mủ là gì"
    user = normalize_chat_message(message)

    decision = route_intent(message, user, [], settings, classifier)

    assert classifier.calls == 1
    assert decision.primary_intent == "knowledge"
    assert decision.query_subject == "general"
    assert "urgent_personal_case" not in decision.route_flags


def test_clarify_classifier_with_sufficient_self_context_forces_advise():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="clarify",
            scores={"clarify": 0.95, "advise": 0.04},
            confidence=0.95,
            reason_code="micro_clarify",
        )
    )
    c, planner = _container(classifier=classifier, classifier_enabled=True)

    result = run_intake(c, "bị mụn lưng khi chuyển trọ được 2 tuần", session_id="test-force-advise")

    assert result.route_decision.primary_intent == "advise"
    assert result.route_decision.query_subject == "self"
    assert "clarify_loop_break" in result.route_decision.route_flags
    assert "clarify_sufficient_context" in result.route_decision.reason_code
    assert result.effective_mode == "hybrid"
    assert result.turn_snapshot is not None
    assert planner.calls == 1


def test_clarify_loop_hard_stop_for_self_acne_session():
    classifier = _Classifier(
        ClassifierResult(
            primary_intent="clarify",
            scores={"clarify": 0.95, "advise": 0.04},
            confidence=0.95,
            reason_code="micro_clarify",
        )
    )
    store = SessionStore(max_turns=20)
    session_id = "test-clarify-hard-stop"
    c, planner = _container(
        session_store=store,
        classifier=classifier,
        classifier_enabled=True,
    )
    first = run_intake(c, "tôi bị mụn", session_id=session_id)
    store.append_turn(
        session_id,
        ConversationTurn(
            role="user",
            content=first.clean_text,
            normalized_snapshot=first.turn_snapshot,
            metadata=first.route_decision.metadata(),
        ),
    )
    for idx in range(3):
        store.append_turn(
            session_id,
            ConversationTurn(role="assistant", content=f"hỏi thêm {idx}", mode="clarify"),
        )

    result = run_intake(c, "tôi bị gần 2 tuần rồi", session_id=session_id)

    assert result.route_decision.primary_intent == "advise"
    assert "clarify_loop_hard_stop" in result.route_decision.reason_code
    assert result.effective_mode == "hybrid"
    assert planner.calls >= 1


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
