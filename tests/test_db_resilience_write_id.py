"""PRD-018 STORY-004 (D4, Section 6.4): idempotent audit writes keyed by `write_id`.

`audit_logs` and `action_decisions` each gain a nullable `write_id TEXT` with a
UNIQUE index. A row that carries one is written with `ON CONFLICT(write_id) DO
NOTHING RETURNING id`; only when that returns no row (a replay) does one `SELECT
id ... WHERE write_id = ?` run on the same connection. `lastrowid` is never read
on the keyed path: after a conflicting DO NOTHING the driver reports 0 or the
previous insert's id (STORY-004 plan probe).

Orchestrator decision (STORY-004): PRD 6.4 first said "SELECT rather than
RETURNING". RETURNING first, SELECT on conflict, keeps the healthy path at one
round trip (PRD Section 11), and `test_returning_with_do_nothing_on_this_driver`
proves the driver behaves that way.

Every test is a `db` test by fixture closure (`temp_db`, `uninitialized_db`,
`faulty_db`), so none needs a `_DB_NODEIDS` entry. Under AUTOINCREMENT a
conflicting DO NOTHING consumes an id, so no test asserts contiguous ids.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import json
import logging
import re

import pytest

from app.db import database
from app.db.database import (
    get_connection,
    init_db,
    insert_action_decisions,
    insert_audit_log,
)
from app.db.errors import StorageError
from app.db.models import (
    ACTION_DECISIONS_ADDED_COLUMNS,
    CREATE_ACTION_DECISIONS_AUDIT_INDEX,
    CREATE_ACTION_DECISIONS_TABLE,
    CREATE_ACTION_DECISIONS_USER_TS_INDEX,
    CREATE_ACTION_DECISIONS_WRITE_ID_INDEX,
    CREATE_AUDIT_LOGS_DEDUP_INDEX,
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_AUDIT_LOGS_WRITE_ID_INDEX,
    ActionDecisionRow,
    AuditLog,
)
from app.models.schemas import ActionDecisionEntry, AuditQueryEntry
from app.services import action_audit
from app.services.action_adapters import ToolCall
from app.services.action_config import BUILT_IN_POLICY
from app.services.action_policy import evaluate
from app.services.audit_logger import _new_write_id, log_query
from app.services.identity import Identity
from tests.db_faults import (
    INVALID_BATON,
    NAMESPACE_SHUTDOWN_503,
    Fault,
)

_HEX = re.compile(r"^[0-9a-f]{32}$")
_AUDIT_INSERT = "INSERT INTO AUDIT_LOGS"
_DECISION_INSERT = "INSERT INTO ACTION_DECISIONS"
_USER = Identity("u", "user")


def _entry(write_id=None, user_id="dana", prompt_hash="h"):
    return AuditLog(
        timestamp="2026-11-17T10:00:00Z",
        user_id=user_id,
        prompt_hash=prompt_hash,
        write_id=write_id,
    )


def _decision(tool_call_id, write_id=None):
    return ActionDecisionRow(
        timestamp="2026-11-17T10:00:00Z",
        audit_id=None,
        session_id=None,
        user_id="dana",
        role="user",
        tool_call_id=tool_call_id,
        tool_name="read_file",
        operation_kind="read",
        target_preview=None,
        arguments_hash="h",
        arguments_preview=None,
        decision="allow",
        rule="r",
        reason="why",
        granted_by=None,
        classifications="[]",
        policy_digest="d",
        write_id=write_id,
    )


def _batch(count, batch=None):
    batch = batch or _new_write_id()
    return [_decision(f"c{i}", f"{batch}:{i}") for i in range(count)]


def _scalar(sql, *params):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchone()[0]


def _audit_count(write_id):
    return _scalar("SELECT COUNT(*) FROM audit_logs WHERE write_id = ?", write_id)


def _audit_id_of(write_id):
    return _scalar("SELECT id FROM audit_logs WHERE write_id = ?", write_id)


def _decision_ids_in_input_order():
    with get_connection() as conn:
        return [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM action_decisions ORDER BY tool_call_id"
            ).fetchall()
        ]


def _decide(tool_call_id, sql):
    call = ToolCall(tool_call_id, "query", json.dumps({"sql": sql}))
    return evaluate(call, _USER, BUILT_IN_POLICY)


# --- AC 1: schema and migration ---------------------------------------------


@pytest.mark.parametrize("table", ["audit_logs", "action_decisions"])
def test_a_fresh_database_has_the_write_id_column_as_nullable_text(temp_db, table):
    with get_connection() as conn:
        info = {r["name"]: r for r in conn.execute(f"PRAGMA table_info({table})")}

    assert info["write_id"]["type"] == "TEXT"
    assert info["write_id"]["notnull"] == 0
    assert info["write_id"]["dflt_value"] is None


@pytest.mark.parametrize(
    ("table", "index"),
    [
        ("audit_logs", "idx_audit_logs_write_id"),
        ("action_decisions", "idx_action_decisions_write_id"),
    ],
)
def test_the_write_id_index_is_unique_on_the_one_column(temp_db, table, index):
    with get_connection() as conn:
        listed = {r["name"]: r for r in conn.execute(f"PRAGMA index_list({table})")}
        columns = [r["name"] for r in conn.execute(f"PRAGMA index_info({index})")]

    assert listed[index]["unique"] == 1
    assert columns == ["write_id"]


class _Recording:
    """A proxy over one connection that records the SQL passed through."""

    def __init__(self, inner, statements):
        self._inner = inner
        self._statements = statements

    def execute(self, sql, *args):
        self._statements.append(sql)
        return self._inner.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)


def _without_write_id(ddl):
    legacy = re.sub(r",\n\s+write_id TEXT[^\n]*", "", ddl)
    assert legacy != ddl, "the CREATE does not declare write_id"
    return legacy


def _build_pre_prd018_database():
    """audit_logs and action_decisions as they shipped before write_id, one row each."""
    with get_connection() as conn:
        conn.execute(_without_write_id(CREATE_AUDIT_LOGS_TABLE))
        conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)
        conn.execute(_without_write_id(CREATE_ACTION_DECISIONS_TABLE))
        conn.execute(CREATE_ACTION_DECISIONS_USER_TS_INDEX)
        conn.execute(CREATE_ACTION_DECISIONS_AUDIT_INDEX)
        conn.execute(
            "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
            ("2026-11-01T09:00:00Z", "ana", "pre018"),
        )
        conn.execute(
            "INSERT INTO action_decisions (timestamp, user_id, role, tool_call_id, "
            "tool_name, arguments_hash, decision, rule, reason, classifications, "
            "policy_digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-11-01T09:00:00Z", "ana", "user", "c0", "t", "h", "allow", "r", "w", "[]", "d"),
        )


def test_init_db_migrates_a_pre_prd018_database(uninitialized_db, monkeypatch):
    """AC 1: both columns are ALTERed in once, nothing is backfilled, a re-run is a no-op."""
    _build_pre_prd018_database()
    statements: list[str] = []
    real = database.get_connection
    monkeypatch.setattr(
        database, "get_connection", lambda: _Recording(real(), statements)
    )

    init_db()

    assert [s for s in statements if "ADD COLUMN" in s.upper()] == [
        "ALTER TABLE audit_logs ADD COLUMN write_id TEXT",
        "ALTER TABLE action_decisions ADD COLUMN write_id TEXT",
    ]
    assert not any(
        s.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for s in statements
    ), statements
    assert statements.index(CREATE_AUDIT_LOGS_WRITE_ID_INDEX) > statements.index(
        "ALTER TABLE audit_logs ADD COLUMN write_id TEXT"
    )
    assert statements.index(CREATE_ACTION_DECISIONS_WRITE_ID_INDEX) > statements.index(
        "ALTER TABLE action_decisions ADD COLUMN write_id TEXT"
    )

    statements.clear()
    init_db()
    assert statements, "the proxy captured nothing -- the patch did not take"
    assert not any("ALTER" in s.upper() for s in statements), statements

    assert _scalar("SELECT write_id FROM audit_logs") is None
    assert _scalar("SELECT write_id FROM action_decisions") is None
    with get_connection() as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"idx_audit_logs_write_id", "idx_action_decisions_write_id"} <= names


def test_the_action_decisions_pass_runs_between_its_table_and_its_write_id_index(
    uninitialized_db, monkeypatch
):
    """The pass needs the table, and the index needs the column the pass may add."""
    statements: list[str] = []
    real = database.get_connection
    monkeypatch.setattr(
        database, "get_connection", lambda: _Recording(real(), statements)
    )

    init_db()

    pragma = statements.index("PRAGMA table_info(action_decisions)")
    assert statements.index(CREATE_ACTION_DECISIONS_TABLE) < pragma
    assert pragma < statements.index(CREATE_ACTION_DECISIONS_WRITE_ID_INDEX)


def test_two_null_write_ids_coexist_in_each_table(temp_db):
    insert_audit_log(_entry())
    insert_audit_log(_entry())
    insert_action_decisions([_decision("c0"), _decision("c1")])

    assert _scalar("SELECT COUNT(*) FROM audit_logs WHERE write_id IS NULL") == 2
    assert _scalar("SELECT COUNT(*) FROM action_decisions WHERE write_id IS NULL") == 2


def test_action_decisions_added_columns_are_declared_in_the_create():
    """Mirrors tests/test_db.py's audit_logs rule: a column in only one place ALTERs a fresh table."""
    for name, ddl in ACTION_DECISIONS_ADDED_COLUMNS.items():
        assert f"{name} {ddl}" in CREATE_ACTION_DECISIONS_TABLE


def test_action_decisions_added_columns_declaring_not_null_also_declare_a_default():
    for name, ddl in ACTION_DECISIONS_ADDED_COLUMNS.items():
        if "NOT NULL" in ddl.upper():
            assert "DEFAULT" in ddl.upper(), name


# --- AC 2: construction -----------------------------------------------------


def test_existing_constructions_still_work_and_default_write_id_to_none():
    audit = AuditLog(timestamp="t", user_id="u", prompt_hash="h")
    positional = ActionDecisionRow(
        "t", None, None, "u", "user", "c", "n", None, None, "h", None,
        "allow", "r", "why", None, "[]", "d",
    )

    assert audit.write_id is None and positional.write_id is None
    # `id` stays the trailing field of each: write_id sits before it.
    assert [f.name for f in dataclasses.fields(AuditLog)][-2:] == ["write_id", "id"]
    assert [f.name for f in dataclasses.fields(ActionDecisionRow)][-2:] == [
        "write_id",
        "id",
    ]


# --- AC 3: a keyed audit insert lands once ----------------------------------


def test_the_same_keyed_entry_twice_is_one_row_and_one_id(temp_db):
    write_id = _new_write_id()

    first = insert_audit_log(_entry(write_id))
    second = insert_audit_log(_entry(write_id))

    assert first == second == _audit_id_of(write_id)
    assert _audit_count(write_id) == 1


def test_a_landed_commit_whose_answer_is_lost_is_replayed_to_the_same_row(faulty_db):
    """The honest landed OUTCOME_UNKNOWN: the commit took, the answer was lost."""
    write_id = _new_write_id()
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    returned = insert_audit_log(_entry(write_id))

    assert _audit_count(write_id) == 1
    assert returned == _audit_id_of(write_id)
    assert faulty_db.forwarded(_AUDIT_INSERT) == 2  # the replay did reach the server


def test_a_lost_execute_answer_is_retried_and_lands_once(faulty_db):
    """The AC's literal case: failure after forwarding the first INSERT."""
    write_id = _new_write_id()
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, sql=_AUDIT_INSERT, when="after"))

    returned = insert_audit_log(_entry(write_id))

    assert _audit_count(write_id) == 1
    assert returned == _audit_id_of(write_id)
    assert faulty_db.forwarded(_AUDIT_INSERT) == 2


# --- AC 4: a keyed batch replays from row 1 ---------------------------------


@pytest.mark.parametrize("k", [1, 2, 3])
def test_a_dead_stream_on_row_k_replays_the_keyed_batch_from_row_one(faulty_db, k):
    rows = _batch(3)
    faulty_db.add(Fault(INVALID_BATON, sql=_DECISION_INSERT, nth=k))

    ids = insert_action_decisions(rows)

    assert _scalar("SELECT COUNT(*) FROM action_decisions") == 3
    assert faulty_db.forwarded(_DECISION_INSERT) == (k - 1) + 3
    assert ids == _decision_ids_in_input_order()  # input order, the stored ids


def test_a_landed_keyed_batch_replayed_after_a_lost_commit_stays_n_rows(faulty_db):
    rows = _batch(3)
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    ids = insert_action_decisions(rows)

    assert _scalar("SELECT COUNT(*) FROM action_decisions") == 3  # not 6
    assert ids == _decision_ids_in_input_order()
    assert faulty_db.forwarded(_DECISION_INSERT) == 6


def test_a_replayed_keyed_batch_returns_the_original_ids_in_input_order(temp_db):
    rows = _batch(3)

    first = insert_action_decisions(rows)
    second = insert_action_decisions(rows)

    assert first == second == _decision_ids_in_input_order()


def test_returning_with_do_nothing_on_this_driver(temp_db):
    """PRD 6.4's Assumption, verified on the live driver (orchestrator decision).

    First insert: RETURNING hands back the new id. The conflicting replay, in the
    same transaction and again after the commit: RETURNING yields no row, and the
    SELECT fallback returns the original id. `lastrowid` after a conflict is 0 or
    stale (plan probe), which is why the keyed path never reads it.
    """
    sql = (
        "INSERT INTO action_decisions (timestamp, user_id, role, tool_call_id, "
        "tool_name, arguments_hash, decision, rule, reason, classifications, "
        "policy_digest, write_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(write_id) DO NOTHING RETURNING id"
    )
    params = ("t", "u", "user", "c", "n", "h", "allow", "r", "w", "[]", "d", "probe:0")

    with get_connection() as conn:
        first = conn.execute(sql, params).fetchone()
        assert first is not None
        again = conn.execute(sql, params).fetchone()
        assert again is None  # a conflict returns no row
        in_txn = conn.execute(
            "SELECT id FROM action_decisions WHERE write_id = ?", ("probe:0",)
        ).fetchone()
        assert in_txn["id"] == first["id"]

    with get_connection() as conn:
        after_commit = conn.execute(sql, params).fetchone()
        assert after_commit is None
        fallback = conn.execute(
            "SELECT id FROM action_decisions WHERE write_id = ?", ("probe:0",)
        ).fetchone()
    assert fallback["id"] == first["id"]
    assert _scalar("SELECT COUNT(*) FROM action_decisions") == 1


def test_a_keyed_insert_costs_one_round_trip_on_the_healthy_path(faulty_db):
    """PRD Section 11: RETURNING answers a fresh insert, so no SELECT follows it."""
    insert_audit_log(_entry(_new_write_id()))
    insert_action_decisions(_batch(2))

    selects = [
        sql for op, sql in faulty_db.calls if op == "execute" and "WRITE_ID = ?" in sql
    ]
    assert selects == []


def test_a_replay_falls_back_to_one_select_on_the_same_connection(faulty_db):
    write_id = _new_write_id()
    insert_audit_log(_entry(write_id))

    insert_audit_log(_entry(write_id))

    selects = [
        sql
        for op, sql in faulty_db.calls
        if op == "execute" and sql.startswith("SELECT ID FROM AUDIT_LOGS WHERE WRITE_ID")
    ]
    assert len(selects) == 1


# --- AC 5: minting and the unkeyed path -------------------------------------


def test_log_query_mints_a_hex_write_id_and_still_returns_int(temp_db):
    first = log_query("dana", "hello")
    second = log_query("dana", "hello")

    assert isinstance(first, int) and isinstance(second, int)
    with get_connection() as conn:
        ids = [r["write_id"] for r in conn.execute("SELECT write_id FROM audit_logs")]
    assert len(ids) == 2 and all(_HEX.match(i) for i in ids)
    assert ids[0] != ids[1]


def test_log_query_keeps_one_write_id_across_a_retry(faulty_db):
    """A retry that minted a new key would have left two rows."""
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    audit_id = log_query("dana", "hello")

    assert faulty_db.forwarded(_AUDIT_INSERT) == 2
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM audit_logs WHERE user_id = ?", ("dana",)
        ).fetchall()
    assert [r["id"] for r in rows] == [audit_id]


def test_record_keys_its_rows_batch_colon_index(temp_db):
    decisions = [
        _decide("c0", "SELECT 1"),
        _decide("c1", "SELECT 2"),
        _decide("c2", "SELECT 3"),
    ]

    action_audit.record(decisions, _USER)
    action_audit.record(decisions[:1], _USER)

    with get_connection() as conn:
        keys = [
            r["write_id"]
            for r in conn.execute("SELECT write_id FROM action_decisions ORDER BY id")
        ]
    first_batch = {k.split(":")[0] for k in keys[:3]}
    assert [k.split(":")[1] for k in keys[:3]] == ["0", "1", "2"]
    assert len(first_batch) == 1 and _HEX.match(first_batch.pop())
    assert keys[3].endswith(":0") and keys[3].split(":")[0] != keys[0].split(":")[0]


def test_an_unkeyed_audit_row_is_not_replayed_after_a_landed_commit(faulty_db, caplog):
    caplog.set_level(logging.DEBUG, logger="app.db.database")
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    with pytest.raises(StorageError):
        insert_audit_log(_entry(None, user_id="unkeyed"))

    assert _scalar("SELECT COUNT(*) FROM audit_logs WHERE user_id = ?", "unkeyed") == 1
    assert faulty_db.forwarded(_AUDIT_INSERT) == 1
    refused = [
        r.getMessage()
        for r in caplog.records
        if "retry refused" in r.getMessage() and "insert_audit_log" in r.getMessage()
    ]
    assert len(refused) == 1 and "non_idempotent" in refused[0]


def test_an_unkeyed_batch_is_not_replayed_after_a_landed_commit(faulty_db):
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    with pytest.raises(StorageError):
        insert_action_decisions([_decision("c0"), _decision("c1"), _decision("c2")])

    assert _scalar("SELECT COUNT(*) FROM action_decisions") == 3  # not 6
    assert faulty_db.forwarded(_DECISION_INSERT) == 3


def test_a_keyed_row_with_no_row_to_read_back_fails_closed(temp_db, monkeypatch):
    """The read-back that cannot happen raises our own StorageError, not a TypeError."""

    class _Empty:
        def fetchone(self):
            return None

    class _Conn:
        def execute(self, sql, params=()):
            return _Empty()

    with pytest.raises(StorageError, match="no row for its write_id"):
        database._keyed_row_id(_Conn(), "audit_logs", _Empty(), "w")


# --- Exposure: write_id is not an API field ---------------------------------


def test_write_id_is_not_projected_into_api_responses():
    # STORY-010 adds `audit_ref`, a response field, and still not `write_id`.
    assert "write_id" not in AuditQueryEntry.model_fields
    assert "write_id" not in ActionDecisionEntry.model_fields


def test_both_read_shapes_map_write_id_back(temp_db):
    write_id = _new_write_id()
    audit_id = insert_audit_log(_entry(write_id))

    assert database.get_audit_log(audit_id).write_id == write_id
    assert database.summary_snapshot().rows[0].write_id == write_id
    insert_action_decisions(_batch(1, "b"))
    assert database.list_action_decisions()[0].write_id == "b:0"
