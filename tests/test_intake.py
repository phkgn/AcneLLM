from types import SimpleNamespace

from acne_llm.chat.intake import run_intake
from acne_llm.chat.routing.intent_router import RouteDecision
from acne_llm.chat.routing.llm_extractor import ExtractorFallback
from acne_llm.chat.routing.llm_router import RouterFallback
from acne_llm.chat.session import ConversationTurn, get_session_store
from acne_llm.db.session_store import SQLiteSessionStore
from acne_llm.guardrails.runner import GuardrailRunner


def _container(
    rag_ready=False,
    session_store=None,
    semantic_router=None,
    llm_router=None,
):
    guardrails = SimpleNamespace(
        pre_check=lambda user: None,
    )
    return SimpleNamespace(
        rag_ready=rag_ready,
        # Runtime doc thang c.session_store; test double tu cap store in-memory.
        session_store=session_store if session_store is not None else get_session_store(),
        guardrails=guardrails,
        llm_router=llm_router,
        semantic_router=semantic_router,
    )


def test_intake_default_preserves_raw_description():
    c = _container()

    result = run_intake(c, "MỤN BỌC!!!!! ở cằm", mode_request="auto")

    assert result.user.description == "MỤN BỌC!!!!! ở cằm"
    assert result.clean_text
    assert result.turn_snapshot is None
    assert result.effective_mode == "llm_only"


def test_intake_folds_prior_snapshot_into_current_self_turn():
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


def test_intake_uses_structured_memory_without_exposing_unreferenced_text_history(tmp_path):
    session_id = "test-intake-container-store"
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
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

    assert second.user.context.age == 22
    assert second.user.context.skin_type == "oily"


def test_intake_soft_scope_followups_select_recent_pair_and_fold_facts(tmp_path):
    session_id = "test-soft-followups"
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
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
        assert result.scope_decision == "in_scope"
        assert result.effective_mode == "hybrid"
        assert result.route_decision.primary_intent == "advise"
        assert result.user.context.age == 36
        assert result.user.context.skin_type is None
        assert len(result.history) <= 6

    assert home.clean_text == "có phương pháp điều trị tại nhà k"
    assert cooking_oil.clean_text == "tôi dùng dầu ăn dc kop"


def test_intake_treats_generic_acne_case_as_soft_llm_only():
    """"tôi bị mụn" van di duong tu van, KHONG bi chan.

    Truoc day cho nay con khang dinh completeness.level == "none" va
    missing_fields == ["lesion_types"] -- module completeness da bi xoa: viec
    quyet dinh hoi hay khong tra ve cho generator, no thay du kien trong va tu hoi.
    `level` cung chua bao gio chan gi, chi chay ra log."""
    c = _container()

    result = run_intake(c, "tôi bị mụn")

    assert result.effective_mode == "llm_only"


def test_intake_extracts_safety_terms_without_clinical_plan_for_knowledge():
    c = _container(rag_ready=True)

    result = run_intake(c, "isotretinoin là gì và vì sao nguy hiểm khi mang thai")

    assert "isotretinoin" in result.safety_terms
    assert any(term in result.safety_terms for term in ("mang thai", "pregnancy"))
    assert result.route_decision.primary_intent == "knowledge"


# ponytail: test_intake_mixed_face_and_genital_scope da xoa o Phase 7.
# Hanh vi van can dung, nhung gio do system prompt lo (Modelfile dong 16:
# "neu tin nhan co ca phan trong va ngoai pham vi thi chi tu van phan trong
# pham vi") -- do la eval prompt-level, khong phai unit test.

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
        assert second.user.context.age is None
        assert second.user.context.skin_type is None
    finally:
        store.delete(session_id)


def test_intake_advise_for_other_person_uses_personal_gate_by_design():
    session_id = "test-other-subject-accepted-contamination"
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
        # query_subject was intentionally removed. All advise turns now use the
        # same memory gate, accepting known "other" contamination.
        assert second.user.context.age == 22
        assert second.turn_snapshot is not None
        assert "bạn tôi bị mụn ở lưng" in second.normalized_query
    finally:
        store.delete(session_id)


def test_intake_greeting_has_no_normalized_snapshot():
    c = _container()

    result = run_intake(c, "xin chào")

    assert result.turn_snapshot is None


def test_current_knowledge_turn_ignores_richer_personal_turn():
    session_id = "test-current-turn-priority"
    store = get_session_store()
    store.delete(session_id)
    c = _container()
    try:
        first = run_intake(
            c,
            "Tôi da dầu, mụn viêm ở cằm, đang dùng BHA.",
            session_id=session_id,
        )
        store.append_turn(session_id, ConversationTurn(
            role="user", content=first.raw_message, metadata=first.route_decision.metadata()
        ))
        store.append_turn(session_id, ConversationTurn(role="assistant", content="answer"))

        second = run_intake(c, "Retinol là gì?", session_id=session_id)

        assert second.route_decision.primary_intent == "knowledge"
        # ponytail: bỏ referential check bằng keyword -> turn cá nhân tự đứng
        # được vẫn lọt vào query. Sửa khi intaker phát tín hiệu "referential".
        assert second.normalized_query.startswith("Retinol là gì?")
        assert "chin" not in second.normalized_query
    finally:
        store.delete(session_id)


def test_knowledge_followup_uses_only_previous_user_turn():
    session_id = "test-knowledge-followup-user-only"
    store = get_session_store()
    store.delete(session_id)
    c = _container()
    try:
        first = run_intake(c, "Mụn đầu đen là gì?", session_id=session_id)
        store.append_turn(session_id, ConversationTurn(
            role="user", content=first.raw_message, metadata=first.route_decision.metadata()
        ))
        store.append_turn(session_id, ConversationTurn(
            role="assistant", content="Câu trả lời assistant không được đưa vào follow-up knowledge."
        ))

        second = run_intake(c, "Còn loại này có nguy hiểm không?", session_id=session_id)

        assert second.route_decision.primary_intent == "knowledge"
        assert [(turn.role, turn.content) for turn in second.history] == [
            ("user", "Mụn đầu đen là gì?"),
        ]
        assert "Mụn đầu đen là gì?" in second.normalized_query
        assert "Câu trả lời assistant" not in second.normalized_query
    finally:
        store.delete(session_id)


def test_confirmed_product_can_be_removed_by_explicit_correction():
    session_id = "test-confirmed-profile-remove"
    store = get_session_store()
    store.delete(session_id)
    c = _container()
    try:
        first = run_intake(c, "Tôi đang dùng BHA.", session_id=session_id)
        assert "BHA" in first.confirmed_profile["current_products"]

        second = run_intake(c, "Tôi ngưng BHA rồi.", session_id=session_id)
        assert "BHA" not in second.confirmed_profile["current_products"]
        assert "BHA" not in store.get_user_context(session_id)["current_products"]
    finally:
        store.delete(session_id)


def test_medication_correction_tombstones_old_drug_in_fold_and_snapshot():
    session_id = "test-medication-correction-tombstone"
    store = get_session_store()
    store.delete(session_id)
    c = _container()
    try:
        first = run_intake(
            c,
            "Tôi đang mang thai 9 tuần và đang cầm doxycycline trị mụn.",
            session_id=session_id,
        )
        store.append_turn(session_id, ConversationTurn(
            role="user",
            content=first.raw_message,
            normalized_snapshot=first.turn_snapshot,
            metadata=first.route_decision.metadata(),
        ))

        corrected = run_intake(
            c,
            "À không, thuốc tôi đang cầm là minocycline chứ không phải doxycycline.",
            session_id=session_id,
        )

        assert corrected.user.context.is_pregnant is True
        assert "minocycline" in corrected.user.context.medications
        assert "doxycycline" not in corrected.user.context.medications
        assert corrected.turn_snapshot is not None
        assert "doxycycline" not in corrected.turn_snapshot.context["medications"]
    finally:
        store.delete(session_id)


def test_intake_semantic_oos_returns_soft_reject_without_extraction():
    class _MustNotExtract:
        calls = 0

        def run(self, **kwargs):
            self.calls += 1
            raise AssertionError("extractor ran for soft reject")

    extractor = _MustNotExtract()
    semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="reject",
            confidence=0.42,
            source="semantic",
            reason_code="semantic_router",
            ambiguity_reason="oos_distance=0.58>threshold=0.40",
        )
    )
    c = _container(semantic_router=semantic_router)
    c.settings = SimpleNamespace(extractor_mode="llm")
    c.llm_extractor = extractor

    result = run_intake(c, "giải phương trình")

    assert result.effective_mode == "llm_only"
    assert result.scope_decision == "pass_to_llm_soft"
    assert result.scope_refusal is None
    assert result.route_decision.source == "semantic"
    assert result.user.clinical is None
    assert result.history == []
    assert extractor.calls == 0


def test_intake_semantic_clarify_skips_extractor():
    class _MustNotExtract:
        calls = 0

        def run(self, **kwargs):
            self.calls += 1
            raise AssertionError("extractor ran for clarify")

    extractor = _MustNotExtract()
    semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="clarify",
            confidence=0.61,
            source="semantic",
            reason_code="semantic_router",
        )
    )
    c = _container(semantic_router=semantic_router)
    c.settings = SimpleNamespace(extractor_mode="llm")
    c.llm_extractor = extractor

    result = run_intake(c, "da em tệ quá")

    assert result.effective_mode == "clarify"
    assert result.scope_refusal is None
    assert result.user.clinical is None
    assert extractor.calls == 0


def test_intake_advise_runs_extractor_after_router():
    class _FallbackExtractor:
        calls = 0

        def run(self, **kwargs):
            self.calls += 1
            raise ExtractorFallback("test fallback")

    extractor = _FallbackExtractor()
    semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="advise",
            confidence=0.82,
            source="semantic",
            reason_code="semantic_router",
        )
    )
    c = _container(semantic_router=semantic_router)
    c.settings = SimpleNamespace(extractor_mode="llm", extract_min_field_conf=0.60)
    c.llm_extractor = extractor

    result = run_intake(c, "tôi bị mụn viêm ở cằm")

    assert result.route_decision.primary_intent == "advise"
    assert extractor.calls == 1


def test_intake_llm_router_success_skips_semantic_and_receives_history(tmp_path):
    session_id = "test-llm-router-history"
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    store.append_turn(
        session_id,
        ConversationTurn(role="user", content="Mình đang bị mụn viêm ở má."),
    )

    class _LLMRouter:
        def __init__(self):
            self.calls = []

        def classify(self, clean_text, history):
            self.calls.append((clean_text, history))
            return RouteDecision(
                primary_intent="advise",
                confidence=0.95,
                source="llm",
                reason_code="llm_router",
            )

    class _MustNotRun:
        calls = 0

        def classify(self, text):
            self.calls += 1
            raise AssertionError("semantic fallback ran after LLM success")

    llm_router = _LLMRouter()
    semantic_router = _MustNotRun()
    c = _container(
        session_store=store,
        llm_router=llm_router,
        semantic_router=semantic_router,
    )

    try:
        result = run_intake(c, "chin", session_id=session_id)
    finally:
        store.close()

    assert result.route_decision.source == "llm"
    assert llm_router.calls[0][0] == "chin"
    assert llm_router.calls[0][1][0].content == "Mình đang bị mụn viêm ở má."
    assert semantic_router.calls == 0


def test_intake_llm_failure_uses_semantic_fallback():
    class _LLMFails:
        def classify(self, clean_text, history):
            raise RouterFallback("model unavailable")

    semantic_calls = []

    def _semantic(text):
        semantic_calls.append(text)
        return RouteDecision(
            primary_intent="knowledge",
            confidence=0.84,
            source="semantic",
            reason_code="semantic_router",
        )

    c = _container(
        llm_router=_LLMFails(),
        semantic_router=SimpleNamespace(classify=_semantic),
    )

    result = run_intake(c, "Retinol là gì?")

    assert result.route_decision.primary_intent == "knowledge"
    assert result.route_decision.source == "semantic"
    assert semantic_calls == ["Retinol là gì?"]


def test_intake_llm_and_semantic_failure_uses_legacy_rule_fallback():
    llm_router = SimpleNamespace(
        classify=lambda clean_text, history: (_ for _ in ()).throw(
            RouterFallback("model down")
        )
    )
    semantic_router = SimpleNamespace(
        classify=lambda text: (_ for _ in ()).throw(RuntimeError("embedder down"))
    )
    c = _container(llm_router=llm_router, semantic_router=semantic_router)

    result = run_intake(c, "tôi bị mụn viêm ở cằm")

    assert result.route_decision.primary_intent == "advise"
    assert result.route_decision.source == "rule"
    assert result.route_decision.reason_code == "personal_acne_case"


def test_semantic_mode_container_shape_preserves_previous_primary_behavior():
    semantic_router = SimpleNamespace(
        classify=lambda text: RouteDecision(
            primary_intent="knowledge",
            confidence=0.91,
            source="semantic",
            reason_code="semantic_router",
        )
    )
    c = _container(llm_router=None, semantic_router=semantic_router)
    c.settings = SimpleNamespace(router_mode="semantic", extractor_mode="rule")

    result = run_intake(c, "BHA là gì?")

    assert result.route_decision.primary_intent == "knowledge"
    assert result.route_decision.source == "semantic"


def test_cong_muc_van_ban_van_chan_truoc_khi_goi_bat_ky_model_nao():
    """Ranh gioi sau Phase 7: cong cung chi doc DU LIEU CO CAU TRUC.

    Cap isotretinoin + doxycycline van chan duoc truoc moi model vi ten thuoc
    di vao user.context.medications -- truong co cau truc, khong phai van ban.

    Da BO khoi test nay: "mun o vung kin". Vung co the tung duoc coi la thuc
    the, nhung bang 31 term khong ap duoc ngu canh, va escape hatch cua chinh
    no mo ra vi chu "co" trong "mun o biu CO nguy hiem khong". Luat chuyen sang
    Modelfile system prompt dong 16.

    Thai ky cung khong o day: no la trang thai, co phu dinh/thi/chu ngu, nen
    phai doi intaker. Xem test duoi.
    """
    class _MustNotRoute:
        calls = 0

        def classify(self, text):
            self.calls += 1
            raise AssertionError("semantic router ran before hard guardrail")

    class _MustNotExtract:
        calls = 0

        def run(self, **kwargs):
            self.calls += 1
            raise AssertionError("extractor ran before hard guardrail")

    router, extractor = _MustNotRoute(), _MustNotExtract()
    guardrails = GuardrailRunner("config/guardrails.yaml")
    messages = (
        "tôi đang uống isotretinoin và doxycycline trị mụn",  # cap thuoc ky nhau
    )

    for message in messages:
        c = _container(semantic_router=router)
        c.guardrails = guardrails
        c.settings = SimpleNamespace(extractor_mode="llm")
        c.llm_extractor = extractor
        result = run_intake(c, message)

        assert result.effective_mode == "refuse", message
        assert result.scope_decision == "refuse_hard", message
        assert result.scope_refusal is not None, message

    assert router.calls == 0
    assert extractor.calls == 0


def test_thai_ky_chan_sau_khi_intaker_xac_nhan_trang_thai():
    """Doi lai so voi truoc: can mot lan goi intaker, nhung khong con chan nham.

    Ban cu chan ngay tu van ban tho -- va chan ca "em khong mang thai, dung
    tretinoin duoc khong". Gio phai doi model doc ngu nghia xong moi quyet.
    Van chan TRUOC retrieval va TRUOC generator, chi la sau extract.
    """
    class _Intaker:
        def run(self, **kwargs):
            from acne_llm.chat.routing.llm_extractor import LLMExtractResult
            from acne_llm.schemas import UserContext, UserInput
            from acne_llm.schemas.extraction import ExtractionConfidence, FieldResult

            user = UserInput(
                description=kwargs["clean_text"],
                mode=kwargs["mode"],
                context=UserContext(is_pregnant=True, medications=["tretinoin"]),
            )
            conf = ExtractionConfidence(
                is_pregnant=FieldResult.make(True, "llm", confidence=0.93)
            )
            return LLMExtractResult(user=user, confidence=conf)

    c = _container(llm_router=None)
    c.guardrails = GuardrailRunner("config/guardrails.yaml")
    c.settings = SimpleNamespace(extractor_mode="llm")
    c.llm_extractor = _Intaker()

    result = run_intake(c, "em đang mang thai và muốn dùng tretinoin trị mụn")

    assert result.effective_mode == "refuse"
    assert result.scope_decision == "refuse_hard"
    assert "thai kỳ" in result.scope_refusal.disclaimer


# ponytail: test_prompt_injection_hard_refuses da xoa o Phase 7 cung blocklist
# 146 chuoi. Chong jailbreak gio o Modelfile system prompt.
