"""Unit tests for chat/session.py — no external dependencies."""
from __future__ import annotations

import time
import threading

from acne_llm.chat.session import (
    ConversationTurn,
    NormalizedSnapshot,
    SessionStore,
    fold_history_facts,
    format_history_block,
    get_session_store,
    snapshot_from_user,
    select_relevant_history,
)
from acne_llm.chat.normalizer import normalize_chat_message


# ── Helpers ───────────────────────────────────────────────────────────────────

def _turn(role="user", content="mụn viêm ở cằm", mode="hybrid"):
    return ConversationTurn(role=role, content=content, mode=mode)


def test_knowledge_followup_keeps_only_latest_user_turn():
    history = [
        _turn("user", "turn cũ"),
        _turn("assistant", "trả lời cũ"),
        _turn("user", "mụn viêm ở má"),
        _turn("assistant", "trả lời gần nhất"),
    ]

    selected = select_relevant_history(
        "còn mụn nào ngoài mụn này?",
        "knowledge",
        history,
    )

    assert [turn.content for turn in selected] == ["mụn viêm ở má"]


def test_short_v_slang_is_treated_as_explicit_followup():
    history = [_turn("user", "tôi bị mụn viêm"), _turn("assistant", "trả lời")]

    selected = select_relevant_history("v dùng nghệ đi", "advise", history)

    assert selected == history


# ── SessionStore basic operations ────────────────────────────────────────────

class TestGetOrCreate:
    def test_creates_new_session(self):
        store = SessionStore()
        sess = store.get_or_create("sess-1")
        assert sess is not None
        assert sess.session_id == "sess-1"
        assert sess.turns == []

    def test_returns_same_session_on_second_call(self):
        store = SessionStore()
        s1 = store.get_or_create("sess-2")
        s2 = store.get_or_create("sess-2")
        assert s1 is s2

    def test_returns_none_for_falsy_session_id(self):
        store = SessionStore()
        assert store.get_or_create(None) is None
        assert store.get_or_create("") is None
        assert store.get_or_create("   ") is None

    def test_strips_whitespace_from_session_id(self):
        store = SessionStore()
        s1 = store.get_or_create("  abc  ")
        s2 = store.get_or_create("abc")
        assert s1 is s2


class TestAppendTurn:
    def test_appends_single_turn(self):
        store = SessionStore()
        store.get_or_create("s1")
        store.append_turn("s1", _turn("user", "hello"))
        history = store.get_history("s1")
        assert len(history) == 1
        assert history[0].content == "hello"

    def test_appends_multiple_turns_in_order(self):
        store = SessionStore()
        for i in range(3):
            store.append_turn("s2", _turn(content=f"msg{i}"))
        history = store.get_history("s2")
        assert [t.content for t in history] == ["msg0", "msg1", "msg2"]

    def test_noop_when_session_id_none(self):
        store = SessionStore()
        store.append_turn(None, _turn())  # must not raise
        assert store.get_history(None) == []

    def test_auto_creates_session_if_not_exists(self):
        store = SessionStore()
        store.append_turn("new-sess", _turn(content="auto"))
        history = store.get_history("new-sess")
        assert len(history) == 1

    def test_accepts_normalized_snapshot(self):
        store = SessionStore()
        snap = NormalizedSnapshot(context={"age": 22}, clean_text="tôi 22 tuổi")
        store.append_turn("s", ConversationTurn(role="user", content="tôi 22 tuổi", normalized_snapshot=snap))
        assert store.get_history("s")[0].normalized_snapshot.context["age"] == 22


class TestGetHistory:
    def test_returns_empty_for_unknown_session(self):
        store = SessionStore()
        assert store.get_history("ghost") == []

    def test_returns_empty_for_none(self):
        store = SessionStore()
        assert store.get_history(None) == []

    def test_respects_max_turns(self):
        store = SessionStore(max_turns=4)
        for i in range(10):
            store.append_turn("s", _turn(content=f"t{i}"))
        history = store.get_history("s")
        assert len(history) == 4
        # Should be the LAST 4 turns
        assert [t.content for t in history] == ["t6", "t7", "t8", "t9"]

    def test_returns_copy_not_reference(self):
        store = SessionStore()
        store.append_turn("s", _turn(content="original"))
        h = store.get_history("s")
        h.clear()  # mutate the returned list
        assert len(store.get_history("s")) == 1  # store unaffected


class TestTTLExpiry:
    def test_expired_session_returns_empty_history(self):
        store = SessionStore(ttl=0.01)  # 10ms TTL
        store.append_turn("s", _turn(content="old"))
        time.sleep(0.05)
        # Next access should trigger lazy expiry
        assert store.get_history("s") == []

    def test_expired_session_get_or_create_makes_new(self):
        store = SessionStore(ttl=0.01)
        s1 = store.get_or_create("s")
        s1.turns.append(_turn(content="old"))
        time.sleep(0.05)
        s2 = store.get_or_create("s")
        assert s2.turns == []  # fresh session

    def test_active_session_not_expired(self):
        store = SessionStore(ttl=60)
        store.append_turn("s", _turn(content="alive"))
        assert len(store.get_history("s")) == 1


class TestDelete:
    def test_delete_removes_session(self):
        store = SessionStore()
        store.append_turn("s", _turn())
        store.delete("s")
        assert store.get_history("s") == []

    def test_delete_noop_for_none(self):
        store = SessionStore()
        store.delete(None)  # must not raise

    def test_delete_noop_for_unknown_session(self):
        store = SessionStore()
        store.delete("ghost")  # must not raise


class TestActiveCount:
    def test_counts_live_sessions(self):
        store = SessionStore(ttl=60)
        store.get_or_create("a")
        store.get_or_create("b")
        assert store.active_count() == 2

    def test_excludes_expired_sessions(self):
        store = SessionStore(ttl=0.01)
        store.get_or_create("old")
        time.sleep(0.05)
        store.get_or_create("new")
        assert store.active_count() == 1


class TestUserContextMerge:
    def test_merge_sets_fields(self):
        store = SessionStore()
        store.get_or_create("s")
        store.merge_user_context("s", {"age": 22, "skin_type": "oily"})
        ctx = store.get_user_context("s")
        assert ctx["age"] == 22
        assert ctx["skin_type"] == "oily"

    def test_latest_explicit_write_wins(self):
        store = SessionStore()
        store.get_or_create("s")
        store.merge_user_context("s", {"age": 22})
        store.merge_user_context("s", {"age": 25})
        assert store.get_user_context("s")["age"] == 25

    def test_noop_for_none_session(self):
        store = SessionStore()
        store.merge_user_context(None, {"age": 22})  # must not raise

    def test_returns_empty_dict_for_unknown_session(self):
        store = SessionStore()
        assert store.get_user_context("ghost") == {}


class TestFollowupCount:
    def test_increment_followup_count_updates_public_session_state(self):
        store = SessionStore()
        store.get_or_create("s")

        store.increment_followup_count("s")
        store.increment_followup_count("s", 2.5)

        sess = store.get_or_create("s")
        assert sess is not None
        assert sess.accumulated_clinical_score == 3.5


class TestFoldHistoryFacts:
    def test_folds_prior_snapshot_into_current_user(self):
        prior = normalize_chat_message("tôi 22 tuổi da dầu")
        current = normalize_chat_message("mụn ở cằm")
        turn = ConversationTurn(
            role="user",
            content="tôi 22 tuổi da dầu",
            normalized_snapshot=snapshot_from_user(prior, "tôi 22 tuổi da dầu"),
        )

        merged = fold_history_facts(current, [turn])

        assert merged.context.age == 22
        assert merged.context.skin_type == "oily"

    def test_newest_prior_snapshot_wins_when_current_missing(self):
        older = ConversationTurn(
            role="user",
            content="tôi 22 tuổi da dầu",
            normalized_snapshot=snapshot_from_user(
                normalize_chat_message("tôi 22 tuổi da dầu"),
                "tôi 22 tuổi da dầu",
            ),
        )
        newer = ConversationTurn(
            role="user",
            content="tôi 23 tuổi da khô",
            normalized_snapshot=snapshot_from_user(
                normalize_chat_message("tôi 23 tuổi da khô"),
                "tôi 23 tuổi da khô",
            ),
        )
        current = normalize_chat_message("mụn ở cằm")

        merged = fold_history_facts(current, [older, newer])

        assert merged.context.age == 23
        assert merged.context.skin_type == "dry"


# ── Thread safety ─────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_appends_no_data_loss(self):
        store = SessionStore(max_turns=200)
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    store.append_turn("shared", _turn(content=f"t{n}-{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # 5 threads × 20 turns = 100 turns, but max_turns=200 so none dropped
        assert len(store.get_history("shared")) == 100


# ── Singleton ─────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_get_session_store_returns_same_instance(self):
        s1 = get_session_store()
        s2 = get_session_store()
        assert s1 is s2


# ── format_history_block ──────────────────────────────────────────────────────

class TestFormatHistoryBlock:
    def test_empty_turns_returns_empty_string(self):
        assert format_history_block([]) == ""

    def test_single_turn_rendered(self):
        turns = [ConversationTurn(role="user", content="mụn ở cằm")]
        block = format_history_block(turns)
        assert "[User]: mụn ở cằm" in block

    def test_assistant_label(self):
        turns = [ConversationTurn(role="assistant", content="BHA phù hợp")]
        block = format_history_block(turns)
        assert "[Assistant]: BHA phù hợp" in block

    def test_respects_char_budget(self):
        # Each turn ~50 chars; budget=100 → only 2 turns max
        turns = [
            ConversationTurn(role="user", content=f"tin nhan so {i} noi ve mun")
            for i in range(10)
        ]
        block = format_history_block(turns, char_budget=100)
        assert len(block) <= 110  # small allowance for label chars

    def test_long_individual_turn_truncated(self):
        long_content = "x" * 500
        turns = [ConversationTurn(role="user", content=long_content)]
        block = format_history_block(turns)
        assert "..." not in block
        assert long_content in block

    def test_chronological_order(self):
        turns = [
            ConversationTurn(role="user", content="tin 1"),
            ConversationTurn(role="assistant", content="tra loi 1"),
            ConversationTurn(role="user", content="tin 2"),
        ]
        block = format_history_block(turns)
        idx2 = block.index("tra loi 1")
        idx3 = block.index("tin 2")
        assert "tin 1" not in block
        assert idx2 < idx3
