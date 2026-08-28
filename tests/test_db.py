import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
import sqlite3
from datetime import datetime

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    count_active_users,
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_pii_detected_queries,
    count_successful_queries,
    count_unique_users,
    deactivate_user,
    find_user_by_token_hash,
    get_audit_log,
    get_connection,
    get_user,
    init_db,
    insert_audit_log,
    insert_user,
    list_audit_logs,
    list_users,
    set_user_token_hash,
    top_models,
    top_pii_entities,
    top_users,
)
from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, AuditLog, User


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


def _create_pre_rbac_database(db_path) -> None:
    """Builds the 17-column audit_logs table exactly as it ships on `main`
    today -- i.e. after PRD-003's PII columns, before this story's role /
    denied_permission columns. This is the correct "pre-RBAC" baseline;
    _create_pre_pii_database fixtures an older, pre-PII shape instead.
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
            error_message TEXT,
            pii_detected_input INTEGER NOT NULL DEFAULT 0,
            pii_detected_output INTEGER NOT NULL DEFAULT 0,
            pii_entities TEXT
        )
        """
    )
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-08-20T09:00:00Z", "ana@empresa.com", "xyz789"),
    )
    legacy.commit()
    legacy.close()


def test_init_db_migrates_pre_rbac_database(tmp_path, monkeypatch):
    """A database created before PRD-005 gains role/denied_permission and
    keeps its rows, with NULL in both new fields (AC2).
    """
    db_path = tmp_path / "pre_rbac_audit.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    _create_pre_rbac_database(db_path)

    init_db()

    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    assert {"role", "denied_permission"} <= columns

    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "ana@empresa.com"
    assert preserved.role is None
    assert preserved.denied_permission is None

    insert_audit_log(
        AuditLog(
            timestamp="2026-08-20T09:30:00Z",
            user_id="bob@empresa.com",
            prompt_hash="def000",
            role="user",
            denied_permission="query:byok",
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


def test_role_and_denied_permission_default_to_none(temp_db):
    new_id = insert_audit_log(
        AuditLog(
            timestamp="2026-08-28T12:00:00Z",
            user_id="a",
            prompt_hash="h3",
        )
    )

    fetched = get_audit_log(new_id)

    assert fetched is not None
    assert fetched.role is None
    assert fetched.denied_permission is None


def test_role_and_denied_permission_round_trip(temp_db):
    new_id = insert_audit_log(
        AuditLog(
            timestamp="2026-08-28T12:05:00Z",
            user_id="ana@empresa.com",
            prompt_hash="h4",
            success=True,
            role="user",
            denied_permission="query:byok",
        )
    )

    fetched = get_audit_log(new_id)

    assert fetched is not None
    assert fetched.role == "user"
    assert fetched.denied_permission == "query:byok"

    # And via list_audit_logs, the other read path (AuditQueryEntry's future source).
    entries = list_audit_logs()
    assert entries[0].role == "user"
    assert entries[0].denied_permission == "query:byok"


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
        "role",
        "denied_permission",
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


# --------------------------------------------------------------------------
# PRD-005 STORY-002: users table + CRUD helpers
# --------------------------------------------------------------------------


def test_init_db_creates_users_table(temp_db):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
    assert row is not None


def test_users_schema_matches_expected_columns(temp_db):
    """Pins the identity schema, including the explicit NOT NULL on user_id.

    Outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column hold NULL --
    and more than one row of them -- so dropping that NOT NULL would silently
    allow nameless users in the table that answers "who is this".
    """
    with get_connection() as conn:
        info = list(conn.execute("PRAGMA table_info(users)"))

    columns = {row["name"]: row for row in info}
    assert set(columns) == {
        "user_id",
        "role",
        "token_hash",
        "active",
        "created_at",
    }
    for name, row in columns.items():
        assert row["notnull"] == 1, f"{name} must be NOT NULL"
    assert columns["active"]["dflt_value"] == "1"
    assert columns["user_id"]["pk"] == 1
    assert all(
        columns[name]["pk"] == 0
        for name in ("role", "token_hash", "active", "created_at")
    )


def test_init_db_creates_users_token_hash_index(temp_db):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_users_token_hash'"
        ).fetchone()
    assert row is not None


def test_init_db_is_idempotent_for_users_table(temp_db):
    """init_db() runs on every Reflex hot reload (chat_ui/chat_ui/chat_ui.py:24),
    so a re-issued CREATE must stay a no-op rather than raising."""
    init_db()
    init_db()
    init_db()

    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))

    assert count_active_users() == 1
    with get_connection() as conn:
        index = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_users_token_hash'"
        ).fetchone()
    assert index is not None


def test_init_db_adds_users_table_to_pre_rbac_database(tmp_path, monkeypatch):
    """A new *table* needs no ALTER-based migration: CREATE TABLE IF NOT EXISTS
    reaches an existing database file, unlike a new column. This is why
    _add_missing_columns stays audit_logs-specific."""
    db_path = tmp_path / "pre_rbac.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    _create_pre_pii_database(db_path)  # audit_logs only -- no users table

    init_db()

    with get_connection() as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"audit_logs", "users"} <= tables
    assert count_active_users() == 0

    # The legacy audit row is untouched by the new table.
    assert count_audit_logs() == 1
    assert get_audit_log(1).user_id == "juan@empresa.com"


def test_find_user_by_token_hash_returns_active_user(temp_db):
    insert_user(
        User(
            user_id="ana",
            role="user",
            token_hash="hash-ana",
            created_at="2026-08-28T10:00:00Z",
        )
    )

    found = find_user_by_token_hash("hash-ana")

    assert found is not None
    assert found.user_id == "ana"
    assert found.role == "user"
    assert found.active is True
    assert found.created_at == "2026-08-28T10:00:00Z"


def test_find_user_by_token_hash_ignores_deactivated_user(temp_db):
    """Revocation must break credential resolution while leaving the row
    readable administratively -- both halves of AC2 in one assertion set."""
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))
    deactivate_user("ana")

    assert find_user_by_token_hash("hash-ana") is None

    still_there = get_user("ana")
    assert still_there is not None
    assert still_there.active is False


def test_find_user_by_token_hash_unknown_returns_none(temp_db):
    assert find_user_by_token_hash("nope") is None


def test_find_user_by_token_hash_is_exact_not_prefix(temp_db):
    """Guards against anyone turning the `=` into a LIKE: a prefix match would
    let a truncated digest authenticate."""
    insert_user(User(user_id="ana", role="user", token_hash="abc123"))

    assert find_user_by_token_hash("abc") is None
    assert find_user_by_token_hash("abc123") is not None


def test_deactivate_user_retains_the_row(temp_db):
    """Revocation is not deletion: audit_logs rows carry a bare user_id with no
    foreign key, so deleting the user would orphan the audit trail."""
    insert_user(
        User(
            user_id="ana",
            role="user",
            token_hash="hash-ana",
            created_at="2026-08-28T10:00:00Z",
        )
    )

    assert deactivate_user("ana") is True

    revoked = get_user("ana")
    assert revoked is not None
    assert revoked.active is False
    assert revoked.created_at == "2026-08-28T10:00:00Z"
    assert revoked.role == "user"


def test_deactivate_user_unknown_returns_false(temp_db):
    assert deactivate_user("ghost") is False


def test_deactivate_user_is_idempotent(temp_db):
    """rowcount counts matched rows, not changed ones, so a second deactivation
    still reports True. Documented so nobody "fixes" it into False later."""
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))

    assert deactivate_user("ana") is True
    assert deactivate_user("ana") is True
    assert get_user("ana").active is False


def test_count_active_users_empty_returns_zero(temp_db):
    assert count_active_users() == 0


def test_count_active_users_excludes_deactivated(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash="h-ana"))
    insert_user(User(user_id="bob", role="auditor", token_hash="h-bob"))
    insert_user(User(user_id="cleo", role="admin", token_hash="h-cleo"))

    deactivate_user("bob")

    assert count_active_users() == 2
    assert len(list_users()) == 3  # the revoked row is retained


def test_find_user_by_token_hash_uses_the_index(temp_db):
    """AC5: the lookup is on the hot path of every authenticated request, so it
    must not degrade to a table scan as the users table grows."""
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))

    with get_connection() as conn:
        plan = " ".join(
            row["detail"]
            for row in conn.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM users WHERE token_hash = ? AND active = 1",
                ("hash-ana",),
            )
        )

    assert "idx_users_token_hash" in plan, plan
    assert "SCAN" not in plan.upper(), plan


def test_insert_and_read_user_round_trip(temp_db):
    entry = User(
        user_id="ana@empresa.com",
        role="auditor",
        token_hash="a" * 64,
        active=False,
        created_at="2026-08-28T10:30:00Z",
    )

    returned = insert_user(entry)
    fetched = get_user("ana@empresa.com")

    assert returned == "ana@empresa.com"
    assert fetched is not None
    assert fetched.user_id == entry.user_id
    assert fetched.role == entry.role
    assert fetched.token_hash == entry.token_hash
    assert fetched.active is False
    assert fetched.created_at == entry.created_at


def test_insert_user_defaults_created_at_to_utc_now(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))

    created_at = get_user("ana").created_at

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at)
    # Same format as audit_logger.py, so both tables sort and compare alike.
    assert datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")


def test_insert_user_rejects_duplicate_user_id(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash="h-1"))

    with pytest.raises(sqlite3.IntegrityError):
        insert_user(User(user_id="ana", role="admin", token_hash="h-2"))


def test_insert_user_rejects_duplicate_token_hash(temp_db):
    """The index is UNIQUE on purpose: without it, two rows could share a
    credential and the lookup would return an arbitrary winner."""
    insert_user(User(user_id="ana", role="user", token_hash="shared-hash"))

    with pytest.raises(sqlite3.IntegrityError):
        insert_user(User(user_id="bob", role="user", token_hash="shared-hash"))


def test_get_user_missing_returns_none(temp_db):
    assert get_user("ghost") is None


def test_list_users_includes_deactivated(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash="h-ana"))
    insert_user(User(user_id="bob", role="user", token_hash="h-bob"))

    deactivate_user("bob")

    assert len(list_users()) == 2


def test_set_user_token_hash_rotates_the_credential(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash="old-hash"))

    assert set_user_token_hash("ana", "new-hash") is True

    assert find_user_by_token_hash("old-hash") is None
    rotated = find_user_by_token_hash("new-hash")
    assert rotated is not None
    assert rotated.user_id == "ana"


def test_set_user_token_hash_unknown_returns_false(temp_db):
    assert set_user_token_hash("ghost", "hash") is False
