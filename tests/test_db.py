import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
import sqlite3
import threading
from datetime import datetime

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    check_database_reachable,
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
from app.db.errors import (
    DatabaseAuthError,
    DatabaseUnreachableError,
    IntegrityError,
    MissingRelationError,
    StorageError,
)
from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, AuditLog, User


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


def test_add_missing_columns_applies_any_declared_column(uninitialized_db, monkeypatch):
    """The mechanism is proven independently of whichever columns the mapping
    happens to hold today, so this stays meaningful after STORY-009 adds more."""
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

    class _RecordingConnection:
        """Records the SQL passed through, and delegates everything else.

        PRD-007 STORY-006 replaced `sqlite3`'s `set_trace_callback` with this:
        the libSQL connection has no tracing hook (its whole surface is
        close/commit/cursor/execute/executemany/executescript/in_transaction/
        isolation_level/rollback/sync). The claim below is unchanged; only the
        instrument moved, onto the same proxy idiom
        `test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table`
        already uses.
        """

        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self._conn.__exit__(*exc_info)

        def execute(self, sql, *parameters):
            statements.append(sql)
            return self._conn.execute(sql, *parameters)

    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: _RecordingConnection(real_get_connection()),
    )

    init_db()  # temp_db already migrated this database to the current schema

    assert statements, "the proxy captured nothing -- the patch did not take"
    assert not any("ALTER" in sql.upper() for sql in statements), statements


def _create_pre_pii_database(connect, url) -> None:
    """Builds the 14-column audit_logs table exactly as it shipped before PRD-003.

    Takes conftest's `db_connect` rather than calling get_connection() so the
    fixture is the genuine pre-migration shape, unaffected by whatever init_db()
    does today -- and rather than a path, so the database it builds is named the
    same way every other test names one.
    """
    legacy = connect(url)
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


def test_init_db_migrates_pre_pii_database(uninitialized_db, db_connect):
    """A database created before PRD-003 gains the PII columns and keeps its rows.

    CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so without the
    additive migration an upgraded deployment fails every insert with
    "table audit_logs has no column named pii_detected_input".
    """
    _create_pre_pii_database(db_connect, uninitialized_db)

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


def _create_pre_rbac_database(connect, url) -> None:
    """Builds the 17-column audit_logs table exactly as it ships on `main`
    today -- i.e. after PRD-003's PII columns, before this story's role /
    denied_permission columns. This is the correct "pre-RBAC" baseline;
    _create_pre_pii_database fixtures an older, pre-PII shape instead.
    """
    legacy = connect(url)
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


def test_init_db_migrates_pre_rbac_database(uninitialized_db, db_connect):
    """A database created before PRD-005 gains role/denied_permission and
    keeps its rows, with NULL in both new fields (AC2).
    """
    _create_pre_rbac_database(db_connect, uninitialized_db)

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


def test_init_db_migration_is_idempotent_across_repeated_calls(uninitialized_db, db_connect):
    """Reflex calls init_db() on every hot reload; a second ADD COLUMN for an
    existing column raises sqlite3.OperationalError: duplicate column name."""
    _create_pre_pii_database(db_connect, uninitialized_db)

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


def test_top_pii_entities_counts_each_entity_in_a_multi_entity_value(temp_db):
    """One row holding three entities contributes one to each of the three.

    STORY-009 moved this count from a Python loop into a recursive CTE. The
    split is now the database's job, so the case that proves the split happens
    at all is a value with commas in it.
    """
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="m1",
            pii_entities="EMAIL_ADDRESS,PERSON,LOCATION",
        )
    )
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-02T10:00:00Z",
            user_id="a",
            prompt_hash="m2",
            pii_entities="PERSON",
        )
    )

    # PERSON: 2, EMAIL_ADDRESS: 1, LOCATION: 1 -- the two 1s tie and sort by name
    assert top_pii_entities() == ["PERSON", "EMAIL_ADDRESS", "LOCATION"]


def test_top_pii_entities_breaks_ties_by_entity_name(temp_db):
    """Equal counts order by entity name -- a chosen rule, not an inherited one.

    The implementation this replaced sorted a dict by count alone, which Python
    resolves stably over insertion order, so ties fell out as "whichever row the
    database returned first". That was incidental and not reproducible across
    instances. STORY-009 pins `ORDER BY COUNT(*) DESC, entity ASC` instead.

    The rows are inserted in a deliberately non-alphabetical order: under the old
    behavior this would have returned them as inserted, so the test fails if row
    order ever decides the outcome again.
    """
    for index, entity in enumerate(("PERSON", "LOCATION", "EMAIL_ADDRESS")):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{index + 1}T10:00:00Z",
                user_id="a",
                prompt_hash=f"t{index}",
                pii_entities=entity,
            )
        )

    # All three tie at 1, so entity name alone decides.
    assert top_pii_entities() == ["EMAIL_ADDRESS", "LOCATION", "PERSON"]


def test_top_pii_entities_counts_repeats_within_one_value(temp_db):
    """A value repeating an entity counts it twice, from that one row.

    The count is over entities, not over rows -- the case a `DISTINCT` or a
    row-counting rewrite would quietly get wrong.
    """
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="r1",
            pii_entities="PERSON,PERSON,EMAIL_ADDRESS",
        )
    )

    # PERSON: 2 and EMAIL_ADDRESS: 1, both out of a single row.
    assert top_pii_entities() == ["PERSON", "EMAIL_ADDRESS"]


def test_top_pii_entities_ignores_rows_without_pii(temp_db):
    """Rows leaving `pii_entities` at NULL contribute nothing -- not None, not "".

    A table with rows but no PII-bearing ones is the other half of the empty
    case; the empty *table* is covered by
    `test_aggregates_on_empty_db_return_zero_or_empty` above.
    """
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="a",
            prompt_hash="n1",
            pii_entities="PERSON",
        )
    )
    for index in range(2):
        insert_audit_log(
            AuditLog(
                timestamp=f"2026-07-0{index + 2}T10:00:00Z",
                user_id="a",
                prompt_hash=f"n{index + 2}",
            )
        )

    assert top_pii_entities() == ["PERSON"]


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


def test_init_db_adds_users_table_to_pre_rbac_database(uninitialized_db, db_connect):
    """A new *table* needs no ALTER-based migration: CREATE TABLE IF NOT EXISTS
    reaches an existing database file, unlike a new column. This is why
    _add_missing_columns stays audit_logs-specific."""
    _create_pre_pii_database(db_connect, uninitialized_db)  # audit_logs only -- no users table

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


def test_find_user_by_token_hash_returns_none_when_users_table_does_not_exist(
    uninitialized_db,
):
    """PRD-007 STORY-002 characterization test.

    Pins the `except sqlite3.OperationalError` arm at app/db/database.py:289:
    a missing `users` table is folded into the same "no match" outcome as an
    unknown credential, rather than escaping to the caller.

    Asserted by return value, never by exception type -- STORY-004 replaces
    the driver's exception with a module-owned one, and this test must keep
    passing across that swap untouched.
    """
    assert find_user_by_token_hash("any-hash") is None


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

    with pytest.raises(IntegrityError) as exc_info:
        insert_user(User(user_id="ana", role="admin", token_hash="h-2"))

    # The module-owned type carries which constraint failed, so a caller can tell
    # this apart from a duplicate token_hash (PRD-007 STORY-004 AC1).
    assert exc_info.value.constraint == "users.user_id"


def test_insert_user_rejects_duplicate_token_hash(temp_db):
    """The index is UNIQUE on purpose: without it, two rows could share a
    credential and the lookup would return an arbitrary winner."""
    insert_user(User(user_id="ana", role="user", token_hash="shared-hash"))

    with pytest.raises(IntegrityError) as exc_info:
        insert_user(User(user_id="bob", role="user", token_hash="shared-hash"))

    assert exc_info.value.constraint == "users.token_hash"


def test_no_driver_exception_escapes_app_db(temp_db):
    """PRD-007 STORY-004 AC2: every driver exception is translated at the
    module boundary, so no caller ever sees a sqlite3 type."""
    with get_connection() as conn:
        conn.execute("DROP TABLE audit_logs")

    with pytest.raises(MissingRelationError) as exc_info:
        count_audit_logs()

    raised = exc_info.value
    assert raised.relation == "audit_logs"
    # A subclass of the general failure on purpose: duplicate_checker catches
    # StorageError and must keep catching a missing table, exactly as
    # `except sqlite3.Error` did before the translation existed.
    assert isinstance(raised, StorageError)
    assert not isinstance(raised, sqlite3.Error)


def test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table(
    temp_db, monkeypatch
):
    """The 401 arm is narrow by design (PRD-007 STORY-004, Design Note 3).

    Before the translation it caught every sqlite3.OperationalError, so a locked
    or unreadable database resolved as "no match" -- a real storage outage
    reported as a bad credential. Only a missing `users` table folds into None
    now; anything else must surface. The induced failure is the libSQL driver's
    own shape since STORY-006, which is the point: the arm has to stay narrow
    across a driver swap, not merely across a refactor.

    Mirrors the connection-patching idiom at test_init_db_issues_no_alter... --
    a proxy stands in for the connection so the failure is induced at execute
    time rather than by writing a broken database to disk.
    """

    class _LockedConnection:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self._conn.__exit__(*exc_info)

        def execute(self, *args, **kwargs):
            # The driver's real failure shape, captured from the live endpoint by
            # PRD-007 STORY-006: libSQL raises a bare `builtins.ValueError` whose
            # message is Hrana-wrapped, and `_translated()` recognises it by that
            # wrapper rather than by an exception type there is none of.
            raise ValueError(
                "Hrana: `stream error: `Error { message: \"SQLite error: database "
                'is locked", code: "SQLITE_BUSY" }``'
            )

    real_get_connection = database.get_connection
    monkeypatch.setattr(
        database, "get_connection", lambda: _LockedConnection(real_get_connection())
    )

    with pytest.raises(StorageError) as exc_info:
        find_user_by_token_hash("any-hash")

    assert not isinstance(exc_info.value, MissingRelationError)
    assert "locked" in str(exc_info.value)


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


# PRD-007 STORY-006: the shared client itself
# ---------------------------------------------------------------------------


def test_the_shared_client_is_reused_across_calls(temp_db):
    """PRD-007 Section 6 Pattern 1. Against a remote endpoint every construction
    is a TCP + TLS handshake, so a client built per call would make a single
    admin console load pay ten of them. Asserted by identity, because "it is
    reused" is the whole claim -- a correct-looking module that quietly rebuilds
    passes every other test in this file."""
    first = database._shared_client()

    count_audit_logs()

    assert database._shared_client() is first


def test_the_shared_client_is_rebuilt_when_the_database_url_changes(
    temp_db, monkeypatch
):
    """The cache is keyed on the URL, and it has to be.

    Every fixture in `tests/conftest.py` repoints `settings.DATABASE_URL` on the
    constructed `Settings` instance. A client cached without regard to that
    would keep serving the endpoint it was first built against -- so one test's
    reads would come from another's database, and the whole suite would report
    green while testing one thing.
    """
    first = database._shared_client()

    monkeypatch.setattr(settings, "DATABASE_URL", "http://127.0.0.1:59999")

    assert database._shared_client() is not first


# PRD-007 STORY-007: concurrent init_db()
# ---------------------------------------------------------------------------
#
# The race is the read-then-ALTER pair in `_add_missing_columns()`: two
# instances can both read a column as missing, and the loser's ALTER fails with
# `duplicate column name`. Because init_db() runs at import time, the loser is a
# container that will not boot.
#
# Four of the six tests below are *deterministic* -- they reproduce the loser's
# condition directly rather than hoping an interleave occurs. The two N-thread
# tests at the end are realism, and say so in their own docstrings: on their own
# they would pass whether or not the race ever happened, which is exactly the
# kind of evidence AC7 rejects.


class _DelegatingConnection:
    """Base for the connection proxies below: passes everything through.

    Same idiom as `_RecordingConnection` and `_LockedConnection` above, which
    STORY-006 introduced because the libSQL connection has no
    `set_trace_callback` equivalent to hook instead.
    """

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, sql, *parameters):
        return self._conn.execute(sql, *parameters)


class _StaleReadConnection(_DelegatingConnection):
    """Reports `audit_logs` as having no columns; everything else is real."""

    def execute(self, sql, *parameters):
        if _is_table_info(sql):
            return []
        return self._conn.execute(sql, *parameters)


class _GatedConnection(_DelegatingConnection):
    """Holds the caller at `gate` once its PRAGMA table_info has returned."""

    def __init__(self, conn, gate):
        super().__init__(conn)
        self._gate = gate

    def execute(self, sql, *parameters):
        result = self._conn.execute(sql, *parameters)
        if _is_table_info(sql):
            # Materialise before waiting: the caller must already hold its stale
            # view, and no cursor may stay open across the barrier.
            result = result.fetchall()
            self._gate.wait()
        return result


class _FailingAlterConnection(_DelegatingConnection):
    """Passes everything through but fails every ADD COLUMN."""

    def __init__(self, conn, message):
        super().__init__(conn)
        self._message = message

    def execute(self, sql, *parameters):
        if _is_add_column(sql):
            raise _driver_error(self._message)
        return self._conn.execute(sql, *parameters)


def _is_table_info(sql: str) -> bool:
    return sql.strip().upper().startswith("PRAGMA TABLE_INFO")


def _is_add_column(sql: str) -> bool:
    return "ADD COLUMN" in sql.upper()


def _install(monkeypatch, make_proxy) -> None:
    """Points `database.get_connection` at a proxy over the real connection."""
    real_get_connection = database.get_connection
    monkeypatch.setattr(
        database, "get_connection", lambda: make_proxy(real_get_connection())
    )


def _driver_error(message: str) -> ValueError:
    """The driver's real failure shape, captured from the live endpoint.

    libSQL raises a bare `builtins.ValueError` whose message is Hrana-wrapped,
    and `_translated()` recognises it by that wrapper rather than by an
    exception type there is none of (STORY-001 3.5).
    """
    return ValueError(
        'Hrana: `stream error: `Error { message: "SQLite error: '
        + message
        + '", code: "SQLITE_UNKNOWN" }`'
    )


def _run_concurrently(count, work):
    """Runs `work` in `count` threads released together, and returns failures.

    The barrier is the point: started sequentially the threads would finish one
    after another and the interleave under test would never occur.

    The workers reach the database through `database.get_connection()` like
    everything else. STORY-006 measured a client per thread losing 169 of 200
    writes to TRANSACTION_TIMEOUT, so a test that built its own client would be
    testing a configuration the application does not use.
    """
    start = threading.Barrier(count, timeout=30)
    failures: list = []
    lock = threading.Lock()

    def worker():
        try:
            start.wait()
            work()
        except BaseException as exc:  # noqa: BLE001 -- reported, never swallowed
            with lock:
                failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a worker hung"
    return failures


def test_add_missing_columns_treats_an_existing_column_as_success(
    temp_db, monkeypatch
):
    """The losing instance's exact condition, without needing a race to occur.

    This is the deterministic half of AC7. `temp_db` leaves the schema current,
    and the proxy reports `audit_logs` as having no columns at all -- the stale
    read a loser gets when another instance ALTERs between its PRAGMA and its
    own ALTER. All five ADD COLUMNs therefore fire against a table that already
    has them, and every one of them fails. init_db() must still return.

    The users-table assertion is not incidental: it proves the statements
    *after* the swallowed failures still landed, i.e. that a converging instance
    finishes its migration rather than committing a half-built schema.
    """
    _install(monkeypatch, _StaleReadConnection)

    init_db()  # must not raise

    monkeypatch.undo()
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]
        users = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()

    for name in AUDIT_LOGS_ADDED_COLUMNS:
        assert columns.count(name) == 1, f"{name} present {columns.count(name)} times"
    assert users is not None, "the statements after the swallowed failures were lost"


def test_two_init_db_calls_interleaved_between_read_and_alter_both_succeed(
    uninitialized_db, db_connect, monkeypatch
):
    """The race itself, forced rather than hoped for -- the other half of AC7.

    Both threads are held at a barrier *after* their PRAGMA returns and before
    either ALTERs, so both are guaranteed to act on the same stale view. That is
    precisely the interleave PRAGMA(A) -> PRAGMA(B) -> ALTER(A) -> ALTER(B) that
    Section 6 Pattern 5 describes, and here it happens on every run.

    Two details that keep this safe. The barrier is released only after
    `execute()` has returned, so no thread blocks while the driver holds
    anything -- `_client_lock` guards client *construction*, never execution.
    And the barrier carries a timeout, so a deadlock fails the test instead of
    hanging the suite.
    """
    _create_pre_pii_database(db_connect, uninitialized_db)
    gate = threading.Barrier(2, timeout=30)
    _install(monkeypatch, lambda conn: _GatedConnection(conn, gate))

    failures = _run_concurrently(2, init_db)

    assert not failures, f"a concurrent init_db() raised: {failures}"

    monkeypatch.undo()
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    assert set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)
    assert len(columns) == len(set(columns)), "a column was added twice"
    assert count_audit_logs() == 1
    assert get_audit_log(1).user_id == "juan@empresa.com"


def test_add_missing_columns_propagates_a_failure_that_is_not_a_duplicate_column(
    uninitialized_db, db_connect, monkeypatch
):
    """AC3's second half. "Column already exists" is one specific condition.

    A locked or unreachable database failing an ALTER must still reach the
    caller: a migration that reports success without having run would hide a
    broken schema behind a healthy-looking boot, which is a worse failure than
    the crash this story removes.
    """
    _create_pre_pii_database(db_connect, uninitialized_db)
    _install(
        monkeypatch, lambda conn: _FailingAlterConnection(conn, "database is locked")
    )

    with pytest.raises(StorageError) as exc_info:
        init_db()

    assert not isinstance(exc_info.value, MissingRelationError)
    assert "locked" in str(exc_info.value)


def test_add_missing_columns_propagates_a_duplicate_naming_a_different_column(
    uninitialized_db, db_connect, monkeypatch
):
    """The predicate checks the column name, not merely the phrase.

    A duplicate reported for a column we did not ask for means the statement
    that failed was not the one we think it was. That is why
    `_is_duplicate_column()` takes `name` at all, and this is the test that
    keeps it from decaying into a substring match on "duplicate column name".
    """
    _create_pre_pii_database(db_connect, uninitialized_db)
    _install(
        monkeypatch,
        lambda conn: _FailingAlterConnection(
            conn, "duplicate column name: some_other_column"
        ),
    )

    with pytest.raises(StorageError) as exc_info:
        init_db()

    assert "some_other_column" in str(exc_info.value)


def test_concurrent_init_db_on_an_empty_database_converges(database_url):
    """AC1: N instances booting together on an empty database all return.

    Honest about what it proves, and measured rather than guessed: run against
    the pre-STORY-007 `_add_missing_columns()` this test still passes. On an
    *empty* database `CREATE TABLE IF NOT EXISTS` builds the current schema
    outright, so no ALTER is ever needed and there is no race to lose. It is
    therefore realism, not evidence -- which is the standard AC7 sets. The
    deterministic proof is
    `test_add_missing_columns_treats_an_existing_column_as_success` and
    `test_two_init_db_calls_interleaved_between_read_and_alter_both_succeed`
    above. This one is here because "the whole of init_db(), under real
    concurrency, end to end" is a different claim from either of those, and it
    is the claim the PRD's Risk 3 mitigation names.
    """
    failures = _run_concurrently(8, init_db)

    assert not failures, f"a concurrent init_db() raised: {failures}"

    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]
        users = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        index = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_users_token_hash'"
        ).fetchone()

    assert set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)
    assert len(columns) == len(set(columns)), "a column was added twice"
    assert users is not None
    assert index is not None


def test_concurrent_init_db_on_a_partially_migrated_database_converges(
    uninitialized_db, db_connect
):
    """AC2: the same, against a table missing a subset of the added columns.

    The pre-PII fixture is the case with real migration work in it -- five
    ALTERs that must each run exactly once across eight instances -- and the
    surviving row is what keeps "additive only" honest under concurrency.

    Same caveat as the test above: realism, not deterministic evidence.
    """
    _create_pre_pii_database(db_connect, uninitialized_db)

    failures = _run_concurrently(8, init_db)

    assert not failures, f"a concurrent init_db() raised: {failures}"

    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    assert set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)
    assert len(columns) == len(set(columns)), "a column was added twice"
    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "juan@empresa.com"
    assert preserved.pii_detected_input is False


# --------------------------------------------------------------------------
# STORY-008 -- the startup guard: fail fast, legibly, and without the token.
# --------------------------------------------------------------------------

#: A closed port on loopback. No DNS lookup and no route to wait on -- the
#: connection is refused immediately, which is the unreachable case the guard is
#: written against, at the lowest wall-clock cost available.
_UNREACHABLE_URL = "http://127.0.0.1:1"

#: Stands in for a real credential the way `tests/test_config.py`'s sentinel
#: does. If it ever reaches a failure message, PRD Section 9 has been broken.
_TOKEN_SENTINEL = "s3cret-turso-token-value"

#: The unreachable message the driver actually produces, recorded verbatim by
#: STORY-006 (report, error-surface table). Note the absent `code:` field, which
#: is why the classifier reads message text and not a code.
_REAL_UNREACHABLE_TEXT = (
    "Hrana: `http error: error sending request for url "
    "(http://127.0.0.1:1/v2/pipeline): client error (Connect): "
    "tcp connect error: Connection refused (os error 111)`"
)


@pytest.fixture
def _restore_shared_client():
    """Drops the process-wide client after a test repoints DATABASE_URL.

    `_shared_client()` keys on `(URL, token)` and rebuilds when either changes,
    so this is belt and braces -- but a test that deliberately points the module
    at a dead endpoint is the last place to rely on a cache invalidating itself.
    """
    yield
    database._client = None
    database._client_key = None


@pytest.mark.parametrize(
    "url, must_not_contain",
    [
        (f"libsql://db-org.turso.io?authToken={_TOKEN_SENTINEL}", _TOKEN_SENTINEL),
        ("https://user:pw@db-org.turso.io/some/path", "pw"),
        ("http://127.0.0.1:8080", "@"),
    ],
)
def test_safe_endpoint_drops_query_userinfo_and_path(url, must_not_contain):
    """AC3, structurally: the only part of DATABASE_URL a message may quote."""
    safe = database._safe_endpoint(url)

    assert must_not_contain not in safe
    assert "?" not in safe and "@" not in safe
    assert "db-org.turso.io" in safe or "127.0.0.1" in safe


def test_safe_endpoint_keeps_the_port_so_the_message_identifies_the_database():
    """AC1 wants the endpoint named. A scheme alone would not tell two apart."""
    assert database._safe_endpoint("http://127.0.0.1:8080") == "http://127.0.0.1:8080"


def test_safe_endpoint_degrades_rather_than_echoing_an_unparseable_url():
    assert "not a url at all" not in database._safe_endpoint("not a url at all")


def test_redacted_removes_a_token_carried_in_driver_text(monkeypatch):
    """Both forms: the query-string parameter and the configured value itself."""
    monkeypatch.setattr(settings, "TURSO_AUTH_TOKEN", _TOKEN_SENTINEL)
    message = (
        f"Hrana: `http error: url (libsql://db.turso.io?authToken={_TOKEN_SENTINEL}) "
        f"rejected the credential {_TOKEN_SENTINEL}`"
    )

    scrubbed = database._redacted(message)

    assert _TOKEN_SENTINEL not in scrubbed
    assert "authToken=***" in scrubbed


@pytest.mark.parametrize(
    "marker",
    ["401", "Unauthorized", "authentication failed", "invalid token", "expired token"],
)
def test_classify_names_the_token_setting_for_an_auth_failure(marker):
    """AC2: an operator sent to the credential, not to the network."""
    error = database._classify_startup_failure(
        ValueError(f"Hrana: `api error: {marker}`"), "libsql://db-org.turso.io"
    )

    assert isinstance(error, DatabaseAuthError)
    assert "TURSO_AUTH_TOKEN" in str(error)
    assert error.endpoint == "libsql://db-org.turso.io"


@pytest.mark.parametrize(
    "message",
    [_REAL_UNREACHABLE_TEXT, "Hrana: `something nobody has seen before`"],
)
def test_classify_falls_back_to_unreachable(message):
    """The real driver text, and an unrecognized failure.

    The fallback direction is the assertion: an unclassifiable failure must not
    accuse a credential that may be perfectly good.
    """
    error = database._classify_startup_failure(ValueError(message), "http://127.0.0.1:1")

    assert isinstance(error, DatabaseUnreachableError)
    assert "DATABASE_URL" in str(error)
    assert "http://127.0.0.1:1" in str(error)


@pytest.mark.parametrize("marker", ["401 Unauthorized", "Connection refused"])
def test_no_guard_message_ever_echoes_the_token(marker, monkeypatch):
    """AC3 on both branches, with the token in all three places it can hide: the
    setting, the URL the driver quotes back, and the driver's own text."""
    monkeypatch.setattr(settings, "TURSO_AUTH_TOKEN", _TOKEN_SENTINEL)
    url = f"libsql://db-org.turso.io?authToken={_TOKEN_SENTINEL}"
    driver_text = f"Hrana: `http error: url ({url}) {marker} for {_TOKEN_SENTINEL}`"

    error = database._classify_startup_failure(
        ValueError(driver_text), database._safe_endpoint(url)
    )

    assert _TOKEN_SENTINEL not in str(error)
    assert _TOKEN_SENTINEL not in error.endpoint


def test_init_db_fails_fast_against_an_unreachable_endpoint(
    monkeypatch, _restore_shared_client
):
    """AC1: the boot path raises rather than returning and failing later.

    `http://` passes STORY-005's validator (it is the local-dev scheme), so what
    fails here is this story's guard and not the configuration check -- the
    exception type is the proof.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _UNREACHABLE_URL)
    database._client = None
    database._client_key = None

    with pytest.raises(DatabaseUnreachableError) as exc_info:
        init_db()

    assert "DATABASE_URL" in str(exc_info.value)
    assert "127.0.0.1:1" in str(exc_info.value)


def test_guard_issues_exactly_one_extra_statement(temp_db, monkeypatch):
    """AC5: one round trip, not a handshake-plus-retry loop.

    Same recording-proxy idiom as
    `test_init_db_issues_no_alter_when_schema_is_current`.
    """
    statements: list[str] = []
    real_get_connection = database.get_connection

    class _RecordingConnection:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self._conn.__exit__(*exc_info)

        def execute(self, sql, *parameters):
            statements.append(sql)
            return self._conn.execute(sql, *parameters)

    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: _RecordingConnection(real_get_connection()),
    )

    check_database_reachable()

    assert statements == ["SELECT 1"]


def test_guard_does_not_run_outside_init_db(temp_db, monkeypatch):
    """AC7: startup, not liveness.

    After a successful start the guard must never fire again -- if a later
    version wired a reachability check into the operational path, this booby
    trap would spring on the first ordinary write or read.
    """

    def _explode() -> None:
        raise AssertionError("the guard re-fired outside init_db()")

    monkeypatch.setattr(database, "check_database_reachable", _explode)

    insert_audit_log(
        AuditLog(
            timestamp="2026-09-01T10:00:00Z",
            user_id="ana@empresa.com",
            prompt_hash="abc123",
            prompt_preview="hola",
            model_used="gpt-4",
        )
    )

    assert count_audit_logs() == 1


def test_bootstrap_disabled_skips_the_guard_and_the_schema(
    monkeypatch, _restore_shared_client
):
    """The Docker builder stage's case: import the app with no database at all.

    PRD Section 11 requires the build to succeed without a reachable database,
    and `reflex export` imports `chat_ui.chat_ui`, which calls `init_db()`.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _UNREACHABLE_URL)
    monkeypatch.setattr(settings, "DB_BOOTSTRAP_ENABLED", False)
    database._client = None
    database._client_key = None

    init_db()  # must not raise, and must not have reached the network
