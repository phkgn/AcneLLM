import sqlite3

from acne_llm.db.audit import AuditEntry, AuditStore
from acne_llm.db.base import DBConnection


def test_audit_logs_normalized_fields(tmp_path):
    db = DBConnection(str(tmp_path / "audit.db"))
    store = AuditStore(db)

    store.log(AuditEntry(
        user_message="mụn ở cằm",
        assistant_response="ok",
        used_chunk_ids=["c1"],
        normalized_query="lesions nodule ; text mụn ở cằm",
        extracted_entities={"lesions": ["nodule"], "canonical_ingredients": ["salicylic_acid"]},
        pii_detected=True,
        teencode_replaced=["k"],
        citation_compliance=False,
    ))

    rows = store.query(limit=1)

    assert rows[0]["normalized_query"] == "lesions nodule ; text mụn ở cằm"
    assert rows[0]["extracted_entities"]["lesions"] == ["nodule"]
    assert rows[0]["pii_detected"] is True
    assert rows[0]["teencode_replaced"] == ["k"]
    assert rows[0]["citation_compliance"] is False


def test_audit_schema_migrates_existing_database(tmp_path):
    db_path = tmp_path / "old_audit.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE audit_log (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               timestamp REAL NOT NULL,
               session_id TEXT,
               user_message TEXT NOT NULL,
               assistant_response TEXT NOT NULL,
               used_chunk_ids TEXT NOT NULL DEFAULT '[]',
               scope_decision TEXT NOT NULL DEFAULT '',
               latency_ms INTEGER NOT NULL DEFAULT 0,
               model_used TEXT NOT NULL DEFAULT '',
               temperature REAL
            )"""
        )

    db = DBConnection(str(db_path))
    store = AuditStore(db)
    store.log(AuditEntry(user_message="x", assistant_response="y"))

    row = store.query(limit=1)[0]
    assert row["normalized_query"] == ""
    assert row["extracted_entities"] == {}
    assert row["teencode_replaced"] == []
    assert row["citation_compliance"] is None
