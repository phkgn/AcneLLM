import json
import time

from acne_llm.chat.session import ConversationTurn, NormalizedSnapshot
from acne_llm.db.jsonl_session_store import JsonlSessionStore


def test_jsonl_store_persists_full_history_across_instances(tmp_path):
    store = JsonlSessionStore(str(tmp_path))
    for i in range(25):
        store.append_turn("s", ConversationTurn(role="user", content=f"msg-{i}"))

    reloaded = JsonlSessionStore(str(tmp_path))
    history = reloaded.get_history("s")

    assert len(history) == 25
    assert [turn.content for turn in history] == [f"msg-{i}" for i in range(25)]


def test_jsonl_store_roundtrips_normalized_snapshot_and_used_chunks(tmp_path):
    store = JsonlSessionStore(str(tmp_path))
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
            metadata={
                "primary_intent": "advise",
                "intent_confidence": 0.82,
                "route_flags": ["partial_advise"],
            },
        ),
    )

    turn = JsonlSessionStore(str(tmp_path)).get_history("s")[0]
    assert turn.used_chunks == ["c1"]
    assert turn.metadata["primary_intent"] == "advise"
    assert turn.metadata["route_flags"] == ["partial_advise"]
    assert turn.normalized_snapshot is not None
    assert turn.normalized_snapshot.context["age"] == 22
    assert turn.normalized_snapshot.clinical["lesion_distribution"] == ["chin"]


def test_jsonl_store_ttl_expires_history_and_resets_on_append(tmp_path):
    store = JsonlSessionStore(str(tmp_path), ttl=0.2)
    store.append_turn("s", ConversationTurn(role="user", content="old"))
    time.sleep(0.3)

    assert store.get_history("s") == []

    store.append_turn("s", ConversationTurn(role="user", content="new"))
    history = store.get_history("s")
    assert [turn.content for turn in history] == ["new"]


def test_jsonl_store_asked_fields_and_delete(tmp_path):
    store = JsonlSessionStore(str(tmp_path))
    store.get_or_create("s")
    store.mark_fields_asked("s", ["duration_weeks", "distribution"])
    store.mark_fields_asked("s", ["distribution"])

    assert store.get_asked_fields("s") == {"duration_weeks", "distribution"}

    store.delete("s")
    assert store.get_history("s") == []
    assert store.get_asked_fields("s") == set()


def test_jsonl_store_increment_followup_count(tmp_path):
    store = JsonlSessionStore(str(tmp_path))
    store.get_or_create("s")

    store.increment_followup_count("s")
    store.increment_followup_count("s", 2.0)

    sess = store.get_or_create("s")
    assert sess is not None
    assert sess.accumulated_clinical_score == 3.0


def test_jsonl_store_tracks_total_clarify_count(tmp_path):
    store = JsonlSessionStore(str(tmp_path))
    store.append_turn("s", ConversationTurn(role="assistant", content="hỏi thêm", mode="clarify"))

    sess = store.get_or_create("s")
    assert sess is not None
    assert sess.total_clarify_count == 1


def test_jsonl_store_compacts_when_explicitly_bounded(tmp_path):
    store = JsonlSessionStore(str(tmp_path), max_turns=3)
    for i in range(8):
        store.append_turn("s", ConversationTurn(role="user", content=f"msg-{i}"))

    history = JsonlSessionStore(str(tmp_path), max_turns=3).get_history("s")
    assert [turn.content for turn in history] == ["msg-5", "msg-6", "msg-7"]


def test_jsonl_store_resets_pre_v2_session_state(tmp_path):
    path = tmp_path / "legacy.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"type": "meta", "last_active": time.time(), "user_context": {"age": 99}}),
            json.dumps({"type": "turn", "role": "user", "content": "legacy"}),
        ]),
        encoding="utf-8",
    )

    store = JsonlSessionStore(str(tmp_path))

    assert store.get_history("legacy") == []
    session = store.get_or_create("legacy")
    assert session is not None
    assert session.schema_version == 2
    assert session.user_context == {}
