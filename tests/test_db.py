import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import sqlite3

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_pii_detected_queries,
    count_successful_queries,
    count_unique_users,
    get_audit_log,
    get_connection,
    init_db,
    insert_audit_log,
    list_audit_logs,
    top_models,
    top_pii_entities,
    top_users,
)
from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, AuditLog


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def test_init_db_creates_table(temp_db):
    init_db()  # calling twice must not raise or duplicate the schema

    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
        ).fetchone()
    assert row is not None


def test_added_columns_declaring_not_null_also_declare_a_default():
    """SQLite rejects ALTER TABLE ... ADD COLUMN NOT NULL without a DEFAULT.

    A violation only surfaces against a database that predates the column, so it
    passes every fresh-database test and breaks on exactly the deployments the
    migration exists to serve.
    """
    for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
        declaration = ddl.upper()
        if "NOT NULL" in declaration:
            assert "DEFAULT" in declaration, (
                f"{name}: NOT NULL requires a DEFAULT -- "
                f"SQLite rejects ADD COLUMN NOT NULL without one"
            )
            assert "DEFAULT NULL" not in declaration, (
                f"{name}: DEFAULT NULL does not satisfy NOT NULL"
            )


def test_add_missing_columns_applies_any_declared_column(tmp_path, monkeypatch):
    """The mechanism is proven independently of whichever columns the mapping
    happens to hold today, so this stays meaningful after STORY-009 adds more."""
    db_path = tmp_path / "synthetic.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    insert_audit_log(
        AuditLog(
            timestamp="2026-08-28T10:00:00Z",
            user_id="ana@empresa.com",
            prompt_hash="abc123",
        )
    )

    # setitem, not setattr: app/db/database.py binds this dict by name at import,
    # so both modules share one object and only in-place mutation is visible.
    monkeypatch.setitem(
        AUDIT_LOGS_ADDED_COLUMNS, "synthetic_flag", "INTEGER NOT NULL DEFAULT 7"
    )

    init_db()

    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
        row = conn.execute(
            "SELECT synthetic_flag FROM audit_logs WHERE id = 1"
        ).fetchone()

    assert "synthetic_flag" in columns
    assert row["synthetic_flag"] == 7  # the pre-existing row took the declared default
    assert count_audit_logs() == 1  # and nothing was lost


def test_init_db_issues_no_alter_when_schema_is_current(temp_db, monkeypatch):
    """A no-op run must not re-issue ALTER: init_db() runs on every Reflex hot
    reload, and a redundant ADD COLUMN is fatal, not merely wasteful."""
    statements: list[str] = []
    real_get_connection = database.get_connection

    def traced() -> sqlite3.Connection:
        conn = real_get_connection()
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(database, "get_connection", traced)

    init_db()  # temp_db already migrated this database to the current schema

    assert statements, "trace callback captured nothing -- the patch did not take"
    assert not any("ALTER" in sql.upper() for sql in statements), statements


def _create_pre_pii_database(db_path) -> None:
    """Builds the 14-column audit_logs table exactly as it shipped before PRD-003.

    Uses raw sqlite3.connect rather than get_connection() so the fixture is the
    genuine pre-migration shape, unaffected by whatever init_db() does today.
    """
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        """
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            device TEXT,
            prompt_hash TEXT NOT NULL,
            prompt_preview TEXT,
            response_hash TEXT,
            response_preview TEXT,
            model_used TEXT,
            tokens_used INTEGER,
            was_duplicate_blocked INTEGER NOT NULL DEFAULT 0,
            suspicious_pattern TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            error_message TEXT
        )
        """
    )
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-07-04T10:30:00Z", "juan@empresa.com", "abc123"),
    )
    legacy.commit()
    legacy.close()


def test_init_db_migrates_pre_pii_database(tmp_path, monkeypatch):
    """A database created before PRD-003 gains the PII columns and keeps its rows.

    CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so without the
    additive migration an upgraded deployment fails every insert with
    "table audit_logs has no column named pii_detected_input".
    """
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    _create_pre_pii_database(db_path)

    init_db()

    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= columns

    # The pre-existing row survives and takes the column defaults.
    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "juan@empresa.com"
    assert preserved.pii_detected_input is False
    assert preserved.pii_entities is None

    # And inserts now work against the upgraded table.
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T11:00:00Z",
            user_id="ana@empresa.com",
            prompt_hash="def456",
            pii_detected_input=True,
            pii_entities="PERSON",
        )
    )
    assert count_audit_logs() == 2


def test_init_db_migration_is_idempotent_across_repeated_calls(tmp_path, monkeypatch):
    """Reflex calls init_db() on every hot reload; a second ADD COLUMN for an
    existing column raises sqlite3.OperationalError: duplicate column name."""
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    _create_pre_pii_database(db_path)

    init_db()
    init_db()
    init_db()

    with get_connection() as conn:
        columns = [
            row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")
        ]

    assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= set(columns)
    assert len(columns) == len(set(columns)), "a column was added twice"
    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "juan@empresa.com"


def test_insert_and_read_round_trip(temp_db):
    entry = AuditLog(
        timestamp="2026-07-04T10:30:00Z",
        user_id="juan@empresa.com",
        prompt_hash="abc123",
        device="Chrome/Windows",
        prompt_preview="hola mundo",
        response_hash="def456",
        response_preview="respuesta",
        model_used="gpt-4",
        tokens_used=45,
        was_duplicate_blocked=True,
        suspicious_pattern="override",
        success=False,
        error_message="upstream timeout",
        pii_detected_input=True,
        pii_detected_output=True,
        pii_entities="EMAIL_ADDRESS,PERSON",
    )

    new_id = insert_audit_log(entry)
    fetched = get_audit_log(new_id)

    assert fetched is not None
    assert fetched.id == new_id
    assert fetched.timestamp == entry.timestamp
    assert fetched.user_id == entry.user_id
    assert fetched.device == entry.device
    assert fetched.prompt_hash == entry.prompt_hash
    assert fetched.prompt_preview == entry.prompt_preview
    assert fetched.response_hash == entry.response_hash
    assert fetched.response_preview == entry.response_preview
    assert fetched.model_used == entry.model_used
    assert fetched.tokens_used == entry.tokens_used
    assert fetched.was_duplicate_blocked is True
    assert fetched.suspicious_pattern == entry.suspicious_pattern
    assert fetched.success is False
    assert fetched.error_message == entry.error_message
    assert fetched.pii_detected_input is True
    assert fetched.pii_detected_output is True
    assert fetched.pii_entities == "EMAIL_ADDRESS,PERSON"


def test_pii_fields_default_when_not_supplied(temp_db):
    new_id = insert_audit_log(
        AuditLog(
            timestamp="2026-07-31T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
        )
    )

    fetched = get_audit_log(new_id)

    assert fetched is not None
    assert fetched.pii_detected_input is False
    assert fetched.pii_detected_output is False
    assert fetched.pii_entities is None


def test_pii_fields_round_trip_via_list_audit_logs(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-31T11:00:00Z",
            user_id="a",
            prompt_hash="h2",
            pii_detected_input=True,
            pii_detected_output=False,
            pii_entities="PHONE_NUMBER",
        )
    )

    entries = list_audit_logs()

    assert len(entries) == 1
    assert entries[0].pii_detected_input is True
    assert entries[0].pii_detected_output is False
    assert entries[0].pii_entities == "PHONE_NUMBER"


def test_get_audit_log_missing_id_returns_none(temp_db):
    assert get_audit_log(999) is None


def test_schema_has_no_ip_or_location_column(temp_db):
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    expected = {
        "id",
        "timestamp",
        "user_id",
        "device",
        "prompt_hash",
        "prompt_preview",
        "response_hash",
        "response_preview",
        "model_used",
        "tokens_used",
        "was_duplicate_blocked",
        "suspicious_pattern",
        "success",
        "error_message",
        "pii_detected_input",
        "pii_detected_output",
        "pii_entities",
    }
    assert set(columns) == expected
    assert not any("ip" in c.lower() or "location" in c.lower() for c in columns)


def test_count_audit_logs_empty_returns_zero(temp_db):
    assert count_audit_logs() == 0


def test_count_audit_logs_reflects_inserted_rows(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="juan@empresa.com",
                prompt_hash=f"hash{i}",
            )
        )

    assert count_audit_logs() == 3


def test_list_audit_logs_orders_newest_first(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-04T10:00:00Z", user_id="a", prompt_hash="h4")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )

    entries = list_audit_logs()

    assert [entry.timestamp for entry in entries] == [
        "2026-07-04T10:00:00Z",
        "2026-07-02T10:00:00Z",
        "2026-07-01T10:00:00Z",
    ]


def test_list_audit_logs_respects_limit(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-03T10:00:00Z", user_id="a", prompt_hash="h3")
    )

    entries = list_audit_logs(limit=2)

    assert len(entries) == 2
    assert [entry.timestamp for entry in entries] == [
        "2026-07-03T10:00:00Z",
        "2026-07-02T10:00:00Z",
    ]


def test_list_audit_logs_fewer_than_limit_returns_all(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )

    entries = list_audit_logs(limit=100)

    assert len(entries) == 2


def test_count_blocked_duplicates_counts_only_flagged_rows(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            was_duplicate_blocked=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            was_duplicate_blocked=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            was_duplicate_blocked=False,
        )
    )

    assert count_blocked_duplicates() == 2


def test_count_blocked_suspicious_counts_only_flagged_rows(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            suspicious_pattern="override",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            suspicious_pattern="admin mode",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            suspicious_pattern=None,
        )
    )

    assert count_blocked_suspicious() == 2


def test_count_unique_users_deduplicates(temp_db):
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id="a", prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="a", prompt_hash="h2")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-03T10:00:00Z", user_id="b", prompt_hash="h3")
    )

    assert count_unique_users() == 2


def test_count_successful_queries_counts_only_success_true(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            success=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            success=False,
        )
    )

    assert count_successful_queries() == 2


def test_top_models_ranked_by_count_desc(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"gpt{i}",
                model_used="gpt-4",
            )
        )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-04T10:00:00Z",
            user_id="a",
            prompt_hash="claude1",
            model_used="claude-3-sonnet",
        )
    )

    assert top_models() == ["gpt-4", "claude-3-sonnet"]


def test_top_models_respects_limit(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"m1-{i}",
                model_used="model-1",
            )
        )
    for i in range(2):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 4}T10:00:00Z",
                user_id="a",
                prompt_hash=f"m2-{i}",
                model_used="model-2",
            )
        )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-06T10:00:00Z",
            user_id="a",
            prompt_hash="m3-0",
            model_used="model-3",
        )
    )

    result = top_models(limit=2)

    assert result == ["model-1", "model-2"]


def test_top_users_ranked_by_count_desc(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"ha{i}",
            )
        )
    insert_audit_log(
        AuditLog(timestamp="2026-07-04T10:00:00Z", user_id="b", prompt_hash="hb1")
    )

    assert top_users() == ["a", "b"]


def test_aggregates_on_empty_db_return_zero_or_empty(temp_db):
    assert count_blocked_duplicates() == 0
    assert count_blocked_suspicious() == 0
    assert count_unique_users() == 0
    assert count_successful_queries() == 0
    assert count_pii_detected_queries() == 0
    assert top_models() == []
    assert top_users() == []
    assert top_pii_entities() == []


def test_count_pii_detected_queries_counts_input_or_output(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            pii_detected_input=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            pii_detected_output=True,
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
        )
    )

    assert count_pii_detected_queries() == 2


def test_top_pii_entities_ranked_by_frequency_desc(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="h1",
            pii_entities="EMAIL_ADDRESS,PERSON",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="h2",
            pii_entities="EMAIL_ADDRESS",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-03T10:00:00Z",
            user_id="a",
            prompt_hash="h3",
            pii_entities="PHONE_NUMBER",
        )
    )

    # EMAIL_ADDRESS: 2, PERSON: 1, PHONE_NUMBER: 1 -- no tie at the top
    assert top_pii_entities()[0] == "EMAIL_ADDRESS"
    assert set(top_pii_entities()) == {"EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"}


def test_top_pii_entities_respects_limit(temp_db):
    for i in range(3):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"e{i}",
                pii_entities="EMAIL_ADDRESS",
            )
        )
    for i in range(2):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{i + 4}T10:00:00Z",
                user_id="a",
                prompt_hash=f"p{i}",
                pii_entities="PERSON",
            )
        )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-06T10:00:00Z",
            user_id="a",
            prompt_hash="l1",
            pii_entities="LOCATION",
        )
    )

    assert top_pii_entities(limit=2) == ["EMAIL_ADDRESS", "PERSON"]
