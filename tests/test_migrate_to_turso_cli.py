"""PRD-007 STORY-013 -- `scripts/migrate_to_turso.py`.

The source is the one genuine file in this epic, so `tmp_path` is used for it and
for nothing else: `tests/conftest.py` is explicit that a `Path` must never stand in
for the database URL. The destination is the shared libSQL endpoint, emptied before
every test by the autouse `_never_the_configured_database` fixture.

Sources are built to look like a **real** legacy file, not like `CREATE_AUDIT_LOGS_TABLE`:
the base table is the pre-PII schema and the five `AUDIT_LOGS_ADDED_COLUMNS` are
appended with `ALTER TABLE`, so the column *order* differs from the current DDL
exactly as it does in the repo-root `harness_ai.db`. That difference is what makes
the copy-by-name requirement testable rather than theoretical.
"""

import hashlib
import os
import sqlite3

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.db import database
from app.db.database import (
    find_user_by_token_hash,
    get_audit_log,
    get_connection,
    insert_audit_log,
    insert_user,
)
from app.db.errors import IntegrityError
from app.db.models import (
    AUDIT_LOGS_ADDED_COLUMNS,
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_USERS_TABLE,
    AuditLog,
    User,
)
from scripts import migrate_to_turso as migrate
from scripts.migrate_to_turso import main

# The schema as it shipped before PRD-003's PII telemetry, verbatim from the
# comment in app/db/models.py that explains why AUDIT_LOGS_ADDED_COLUMNS exists.
# Everything after it arrives by ALTER, which is what puts the added columns at
# the end of the real file's column order.
_PRE_PII_AUDIT_LOGS = """
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

_USERS_DDL = CREATE_USERS_TABLE.replace("IF NOT EXISTS ", "")


def _row(audit_id, **overrides):
    """One source row, with the columns a test does not care about filled in."""
    row = {
        "id": audit_id,
        "timestamp": f"2026-07-0{audit_id % 9 + 1}T10:00:00Z",
        "user_id": f"u{audit_id}",
        "device": "laptop",
        "prompt_hash": f"h{audit_id}",
        "prompt_preview": f"prompt {audit_id}",
        "response_hash": f"r{audit_id}",
        "response_preview": f"response {audit_id}",
        "model_used": "gpt-4",
        "tokens_used": 100 + audit_id,
        "was_duplicate_blocked": 0,
        "suspicious_pattern": None,
        "success": 1,
        "error_message": None,
        "pii_detected_input": 0,
        "pii_detected_output": 0,
        "pii_entities": None,
        "role": None,
        "denied_permission": None,
    }
    row.update(overrides)
    return row


def _make_source(tmp_path, rows=(), users=(), omit=(), name="legacy.db"):
    """Builds a legacy `.db` file the way a real one came to exist.

    `omit` drops columns from `AUDIT_LOGS_ADDED_COLUMNS` so a file predating
    PRD-003 or PRD-005 can be reproduced (AC 9). `users=None` omits the table
    entirely, which is what a file older than PRD-005 looks like.
    """
    path = tmp_path / name
    connection = sqlite3.connect(path)
    connection.execute(_PRE_PII_AUDIT_LOGS)
    added = [name for name in AUDIT_LOGS_ADDED_COLUMNS if name not in omit]
    for column in added:
        connection.execute(
            f"ALTER TABLE audit_logs ADD COLUMN {column} "
            f"{AUDIT_LOGS_ADDED_COLUMNS[column]}"
        )

    if users is not None:
        connection.execute(_USERS_DDL)
        connection.execute(
            "CREATE UNIQUE INDEX idx_users_token_hash ON users(token_hash)"
        )
        for user in users:
            connection.execute(
                "INSERT INTO users (user_id, role, token_hash, active, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    user["user_id"],
                    user["role"],
                    user["token_hash"],
                    user.get("active", 1),
                    user.get("created_at", "2026-07-01T00:00:00Z"),
                ),
            )

    for row in rows:
        columns = [name for name in row if name not in omit]
        connection.execute(
            f"INSERT INTO audit_logs ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            tuple(row[name] for name in columns),
        )
    connection.commit()
    connection.close()
    return path


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dest_counts():
    with get_connection() as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("audit_logs", "users")
        }


# --- the DDL parser the column lists come from ----------------------------------


def test_dest_columns_match_the_ddl():
    """The DDL parser is the single source of truth for the column list.

    Pinned against the literal names so a future schema change that breaks the
    "no nested parens, no table constraints" assumption breaks a test rather than
    a migration (see `_ddl_columns`' docstring).
    """
    assert migrate._ddl_columns(CREATE_AUDIT_LOGS_TABLE) == [
        "id", "timestamp", "user_id", "device", "prompt_hash", "prompt_preview",
        "response_hash", "response_preview", "model_used", "tokens_used",
        "was_duplicate_blocked", "suspicious_pattern", "success", "error_message",
        "pii_detected_input", "pii_detected_output", "pii_entities", "role",
        "denied_permission", "session_id",  # session_id: PRD-008 STORY-002
    ]
    assert migrate._ddl_columns(CREATE_USERS_TABLE) == [
        "user_id", "role", "token_hash", "active", "created_at",
    ]
    defaults = migrate._ddl_defaults(CREATE_AUDIT_LOGS_TABLE)
    assert defaults["was_duplicate_blocked"] == 0
    assert defaults["success"] == 1
    assert defaults["pii_detected_input"] == 0
    assert defaults["role"] is None


# --- AC 10's six named cases ----------------------------------------------------


def test_clean_copy_copies_every_row_and_column(temp_db, tmp_path, capsys):
    """AC 1 and AC 3 -- every row, every column, and the counts are reported.

    The source's column order differs from `CREATE_AUDIT_LOGS_TABLE` (the added
    columns are ALTERed on at the end), so a positional copy would pass on counts
    and fail here on values.
    """
    source = _make_source(
        tmp_path,
        rows=[
            _row(1, pii_entities="PERSON,EMAIL_ADDRESS", pii_detected_input=1,
                 role="admin"),
            _row(2, was_duplicate_blocked=1, suspicious_pattern="repeat",
                 success=0, error_message="blocked", denied_permission="audit:read"),
            _row(3),
        ],
        users=[{"user_id": "ana", "role": "admin", "token_hash": "hash-ana"}],
    )

    exit_code = main(["--source", str(source)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert _dest_counts() == {"audit_logs": 3, "users": 1}
    assert "3 audit_logs row(s)" in out
    assert "1 users row(s)" in out
    assert "counts OK" in out and "content OK" in out

    for expected in (1, 2, 3):
        actual = get_audit_log(expected)
        assert actual is not None
        assert actual.user_id == f"u{expected}"
    first = get_audit_log(1)
    assert first.pii_entities == "PERSON,EMAIL_ADDRESS"
    assert first.pii_detected_input is True
    assert first.role == "admin"
    second = get_audit_log(2)
    assert second.was_duplicate_blocked is True
    assert second.success is False
    assert second.denied_permission == "audit:read"


def test_ids_are_preserved_not_regenerated(temp_db, tmp_path):
    """AC 2 -- `GET /audit/{id}` addresses rows by id, so the ids must survive."""
    source = _make_source(tmp_path, rows=[_row(3), _row(7), _row(100)])

    assert main(["--source", str(source)]) == 0

    with get_connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM audit_logs ORDER BY id")]
    assert ids == [3, 7, 100]
    assert get_audit_log(100) is not None
    assert get_audit_log(1) is None  # not renumbered from 1


def test_non_empty_destination_is_refused_without_writing(temp_db, tmp_path, capsys):
    """AC 5 -- refuses outright, and says so on stderr with stdout untouched."""
    insert_audit_log(AuditLog(timestamp="2026-07-01T00:00:00Z", user_id="pre",
                              prompt_hash="pre"))
    before = _dest_counts()
    source = _make_source(tmp_path, rows=[_row(1), _row(2)])

    exit_code = main(["--source", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "audit_logs" in captured.err
    assert "not empty" in captured.err
    assert captured.out == ""  # the error goes to stderr, not stdout
    assert _dest_counts() == before  # nothing was appended


def test_count_mismatch_exits_nonzero_and_names_the_table(
    temp_db, tmp_path, capsys, monkeypatch
):
    """AC 4 -- a short copy is caught, and the message names table and check."""
    real_chunks = migrate._chunks

    def dropping_the_last_chunk(rows, size):
        chunks = list(real_chunks(rows, size))
        return iter(chunks[:-1])

    monkeypatch.setattr(migrate, "_chunks", dropping_the_last_chunk)
    source = _make_source(tmp_path, rows=[_row(1), _row(2), _row(3)])

    exit_code = main(["--source", str(source), "--batch-size", "1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "audit_logs: count check failed" in captured.err
    assert "3 source row(s), 2 destination row(s)" in captured.err
    assert "counts FAILED" in captured.out  # the summary still reports the state


def test_older_schema_source_copies_and_applies_destination_defaults(
    temp_db, tmp_path, capsys
):
    """AC 9 -- a file predating PRD-005 has no `role`/`denied_permission` at all.

    It must copy, not crash, and the two absent columns take the destination's
    own DEFAULT rather than being invented.
    """
    source = _make_source(
        tmp_path,
        rows=[_row(1, pii_entities="PERSON"), _row(2)],
        omit=("role", "denied_permission"),
    )

    exit_code = main(["--source", str(source)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "lacks role, denied_permission" in out
    assert "destination defaults applied" in out
    migrated = get_audit_log(1)
    assert migrated.role is None
    assert migrated.denied_permission is None
    assert migrated.pii_entities == "PERSON"  # the columns it *did* have survived


def test_empty_source_succeeds_and_says_nothing_to_migrate(temp_db, tmp_path, capsys):
    """AC 10 -- an empty source is a successful migration of nothing."""
    source = _make_source(tmp_path, rows=[])

    exit_code = main(["--source", str(source)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert _dest_counts() == {"audit_logs": 0, "users": 0}
    assert "nothing to migrate" in out
    assert "0 audit_logs row(s)" in out


# --- the integrity guarantees the ACs turn on -----------------------------------


def test_source_is_unmodified_after_a_successful_run(temp_db, tmp_path):
    """AC 6 -- the file that is still authoritative is byte-identical."""
    source = _make_source(tmp_path, rows=[_row(1), _row(2)])
    before = _sha256(source)

    assert main(["--source", str(source)]) == 0

    assert _sha256(source) == before


def test_source_is_unmodified_after_a_failed_run_and_nothing_is_committed(
    temp_db, tmp_path, capsys, monkeypatch
):
    """AC 6 on the failure path, plus the rollback the whole policy rests on.

    The copy runs in one transaction, so a failure part-way through must leave the
    destination empty -- that is what makes the non-empty refusal a retry path
    rather than a dead end.
    """
    real_copy = migrate._copy_table

    def copy_then_fail(conn, source, plan, size):
        copied = real_copy(conn, source, plan, size)
        if plan.table == "audit_logs":
            raise migrate.StorageError("simulated failure after the audit copy")
        return copied

    monkeypatch.setattr(migrate, "_copy_table", copy_then_fail)
    source = _make_source(tmp_path, rows=[_row(1), _row(2)])
    before = _sha256(source)

    exit_code = main(["--source", str(source)])

    assert exit_code == 1
    assert "simulated failure" in capsys.readouterr().err
    assert _sha256(source) == before
    assert _dest_counts() == {"audit_logs": 0, "users": 0}  # rolled back


def test_the_source_connection_cannot_write(tmp_path):
    """AC 6's enforcement, not its evidence: `mode=ro` refuses a write outright."""
    source = _make_source(tmp_path, rows=[_row(1)])
    connection = migrate._open_source(source)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM audit_logs")
    finally:
        connection.close()


def test_a_hot_journal_is_refused_rather_than_recovered(temp_db, tmp_path, capsys):
    """AC 6 -- recovering a journal is a write, so the run stops before it."""
    source = _make_source(tmp_path, rows=[_row(1)])
    (tmp_path / f"{source.name}-wal").write_bytes(b"not empty")

    exit_code = main(["--source", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "un-checkpointed changes" in captured.err
    assert captured.out == ""


def test_token_hashes_transfer_intact_and_the_unique_index_still_holds(
    temp_db, tmp_path
):
    """AC 7 -- a corrupted hash locks a user out; a lost index admits a collision."""
    source = _make_source(
        tmp_path,
        rows=[_row(1)],
        users=[
            {"user_id": "ana", "role": "admin", "token_hash": "hash-ana"},
            {"user_id": "bob", "role": "user", "token_hash": "hash-bob"},
        ],
    )

    assert main(["--source", str(source)]) == 0

    resolved = find_user_by_token_hash("hash-ana")
    assert resolved is not None and resolved.user_id == "ana"
    assert find_user_by_token_hash("hash-bob").role == "user"

    # The index survived the copy: a duplicate token_hash is still a write-time
    # IntegrityError rather than an arbitrary winner at read time.
    with pytest.raises(IntegrityError):
        insert_user(User(user_id="carol", role="user", token_hash="hash-ana"))


def test_added_columns_role_and_denied_permission_read_back_through_get_audit_log(
    temp_db, tmp_path
):
    """AC 8 -- the five AUDIT_LOGS_ADDED_COLUMNS plus role and denied_permission.

    Read back through `get_audit_log()` specifically: it is the `SELECT *` path
    `GET /audit/{id}` serves, and the only one that exercises
    `_row_to_audit_log()`'s bool coercions.
    """
    rows = [
        _row(1, pii_detected_input=1, pii_detected_output=1,
             pii_entities="PERSON,EMAIL_ADDRESS,PHONE_NUMBER", role="auditor",
             denied_permission="audit:export"),
        _row(2),  # every one of the seven at its default
    ]
    source = _make_source(tmp_path, rows=rows)

    assert main(["--source", str(source), "--verify-sample", "0"]) == 0

    rich = get_audit_log(1)
    assert rich.pii_detected_input is True
    assert rich.pii_detected_output is True
    assert rich.pii_entities == "PERSON,EMAIL_ADDRESS,PHONE_NUMBER"
    assert rich.role == "auditor"
    assert rich.denied_permission == "audit:export"

    plain = get_audit_log(2)
    assert plain.pii_detected_input is False
    assert plain.pii_detected_output is False
    assert plain.pii_entities is None
    assert plain.role is None
    assert plain.denied_permission is None


def test_next_natural_insert_does_not_collide_with_preserved_ids(temp_db, tmp_path):
    """The AUTOINCREMENT interaction the story calls out by name.

    A migration that preserves history and then breaks the first new write has
    traded one failure for another.
    """
    source = _make_source(tmp_path, rows=[_row(3), _row(7), _row(100)])

    assert main(["--source", str(source)]) == 0

    new_id = insert_audit_log(
        AuditLog(timestamp="2026-08-01T00:00:00Z", user_id="new", prompt_hash="new")
    )
    assert new_id == 101
    assert get_audit_log(100).user_id == "u100"  # the migrated row is intact


def test_content_verification_holds_when_read_through_a_fresh_client(
    temp_db, tmp_path
):
    """PRD Risk 1 -- a same-client read-back could be served from client state.

    STORY-001 §2.2 required every write to be proved through a *fresh* client, so
    the content comparison is re-run after the shared client is discarded.
    """
    source = _make_source(
        tmp_path,
        rows=[_row(1, pii_entities="PERSON"), _row(2)],
        users=[{"user_id": "ana", "role": "admin", "token_hash": "hash-ana"}],
    )
    assert main(["--source", str(source)]) == 0

    database._client = None
    database._client_key = None

    connection = migrate._open_source(source)
    try:
        plans = {t: migrate._reconcile(connection, t) for t in migrate._TABLES}
        with get_connection() as conn:
            assert migrate._verify_content(connection, conn, plans) == []
            assert migrate._verify_counts(connection, conn, plans)[1] == []
    finally:
        connection.close()


def test_content_mismatch_with_matching_counts_exits_nonzero_and_names_the_column(
    temp_db, tmp_path, capsys, monkeypatch
):
    """AC 3's stated reason for existing -- a count match with corrupted content."""
    real_copy = migrate._copy_table

    def corrupting_copy(conn, source, plan, size):
        copied = real_copy(conn, source, plan, size)
        if plan.table == "audit_logs":
            conn.execute(
                "UPDATE audit_logs SET pii_entities = 'CORRUPTED' WHERE id = 2"
            )
        return copied

    monkeypatch.setattr(migrate, "_copy_table", corrupting_copy)
    source = _make_source(
        tmp_path, rows=[_row(1), _row(2, pii_entities="PERSON"), _row(3)]
    )

    exit_code = main(["--source", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "counts OK" in captured.out  # the counts genuinely match
    assert "content FAILED" in captured.out
    assert "column=pii_entities" in captured.err
    assert "id=2" in captured.err
    assert "'PERSON'" in captured.err and "'CORRUPTED'" in captured.err


def test_batch_size_controls_the_number_of_insert_statements(
    temp_db, tmp_path, monkeypatch
):
    """The story's "batch the inserts" -- one statement per chunk, not per row."""
    statements = []
    real_get_connection = migrate.get_connection

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
        migrate, "get_connection", lambda: _RecordingConnection(real_get_connection())
    )
    source = _make_source(tmp_path, rows=[_row(n) for n in range(1, 6)])

    assert main(["--source", str(source), "--batch-size", "2"]) == 0

    assert statements, "the proxy captured nothing -- the patch did not take"
    inserts = [sql for sql in statements if "INSERT INTO audit_logs" in sql]
    assert len(inserts) == 3  # 5 rows at 2 per statement
    assert _dest_counts()["audit_logs"] == 5


def test_dry_run_writes_nothing(temp_db, tmp_path, capsys):
    """A rehearsal against a real endpoint that cannot change it."""
    source = _make_source(
        tmp_path,
        rows=[_row(1), _row(2)],
        users=[{"user_id": "ana", "role": "admin", "token_hash": "hash-ana"}],
    )

    exit_code = main(["--source", str(source), "--dry-run"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry run -- nothing was written." in out
    assert "audit_logs: 2 row(s)" in out
    assert _dest_counts() == {"audit_logs": 0, "users": 0}


def test_a_source_with_no_users_table_is_migrated_not_refused(
    temp_db, tmp_path, capsys
):
    """A file older than PRD-005 has no `users` table. That is 0 rows, not an error."""
    source = _make_source(tmp_path, rows=[_row(1)], users=None)

    exit_code = main(["--source", str(source)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert _dest_counts() == {"audit_logs": 1, "users": 0}
    assert "0 users row(s)" in out


def test_a_source_with_an_unknown_column_is_refused(temp_db, tmp_path, capsys):
    """A column the current schema cannot hold is a refusal, never a silent drop."""
    source = _make_source(tmp_path, rows=[_row(1)])
    connection = sqlite3.connect(source)
    connection.execute("ALTER TABLE audit_logs ADD COLUMN mystery TEXT")
    connection.commit()
    connection.close()

    exit_code = main(["--source", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "mystery" in captured.err
    assert captured.out == ""
    assert _dest_counts()["audit_logs"] == 0


def test_a_missing_source_file_is_refused(temp_db, tmp_path, capsys):
    exit_code = main(["--source", str(tmp_path / "nope.db")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no such source database" in captured.err
    assert captured.out == ""
