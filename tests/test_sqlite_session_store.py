import time

from acne_llm.chat.session import ConversationTurn, NormalizedSnapshot
from acne_llm.db.session_store import SQLiteSessionStore


def _db(tmp_path):
    return str(tmp_path / "sessions.db")


def test_sqlite_store_persists_full_history_across_instances(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db)
    for i in range(25):
        store.append_turn("s", ConversationTurn(role="user", content=f"msg-{i}"))

    history = SQLiteSessionStore(db).get_history("s")

    assert len(history) == 25
    assert [t.content for t in history] == [f"msg-{i}" for i in range(25)]


def test_sqlite_store_roundtrips_snapshot_metadata_and_chunks(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db)
    snap = NormalizedSnapshot(
        context={"age": 22},
        clinical={"lesion_distribution": ["chin"]},
        clean_text="tôi 22 tuổi mụn ở cằm",
    )
    store.append_turn(
        "s",
        ConversationTurn(
            role="user",
            content="tôi 22 tuổi mụn ở cằm",
            used_chunks=["c1"],
            normalized_snapshot=snap,
            metadata={"primary_intent": "advise", "route_flags": ["partial_advise"]},
        ),
    )

    turn = SQLiteSessionStore(db).get_history("s")[0]
    assert turn.used_chunks == ["c1"]
    assert turn.metadata["primary_intent"] == "advise"
    assert turn.metadata["route_flags"] == ["partial_advise"]
    assert turn.normalized_snapshot is not None
    assert turn.normalized_snapshot.context["age"] == 22
    assert turn.normalized_snapshot.clinical["lesion_distribution"] == ["chin"]


def test_sqlite_store_ttl_expires_history_and_resets_on_append(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db, ttl=0.2)
    store.append_turn("s", ConversationTurn(role="user", content="old"))
    time.sleep(0.3)

    assert store.get_history("s") == []

    store.append_turn("s", ConversationTurn(role="user", content="new"))
    assert [t.content for t in store.get_history("s")] == ["new"]


def test_sqlite_store_delete(tmp_path):
    # mark_fields_asked / get_asked_fields da bi xoa cung co che "dung hoi lai"
    # (Phase 2). Con lai kiem tra delete that su xoa lich su.
    db = _db(tmp_path)
    store = SQLiteSessionStore(db)
    store.get_or_create("s")
    store.append_turn("s", ConversationTurn(role="user", content="xin chao"))
    assert len(store.get_history("s")) == 1

    store.delete("s")
    assert store.get_history("s") == []


def test_sqlite_store_increment_followup_count(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db)
    store.get_or_create("s")
    store.increment_followup_count("s")
    store.increment_followup_count("s", 2.0)

    sess = store.get_or_create("s")
    assert sess is not None
    assert sess.accumulated_clinical_score == 3.0


def test_sqlite_store_tracks_total_clarify_count(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db)
    store.append_turn("s", ConversationTurn(role="assistant", content="hỏi thêm", mode="clarify"))

    sess = store.get_or_create("s")
    assert sess is not None
    assert sess.total_clarify_count == 1


def test_sqlite_store_get_history_bounded_by_max_turns(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db, max_turns=3)
    for i in range(8):
        store.append_turn("s", ConversationTurn(role="user", content=f"msg-{i}"))

    history = SQLiteSessionStore(db, max_turns=3).get_history("s")
    assert [t.content for t in history] == ["msg-5", "msg-6", "msg-7"]


def test_sqlite_store_merge_user_context_last_write_wins(tmp_path):
    db = _db(tmp_path)
    store = SQLiteSessionStore(db)
    store.get_or_create("s")
    store.merge_user_context("s", {"age": 20})
    store.merge_user_context("s", {"age": 21, "sex": "female"})

    ctx = store.get_user_context("s")
    assert ctx == {"age": 21, "sex": "female"}
