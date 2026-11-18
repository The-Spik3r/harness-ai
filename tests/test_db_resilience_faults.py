"""PRD-018 STORY-003 (D1, D3, D18): the retry boundary against the real driver.

`tests/test_db_resilience_retry.py` proves the rules with fake clients. These tests
prove them where the failure modes are real: `FaultScript` (`tests/db_faults.py`)
wraps `libsql.connect` over PRD-014's recorder, so a real libSQL server executes
whatever the proxy forwards, and the assertions read the rows it holds.

Every test requests `faulty_db`, so it is a `db` test by fixture closure and needs
no `_DB_NODEIDS` entry.

Which fault models which case is in `tests/db_faults.py`. The one to keep in mind:
DML is not durable before `commit()` (spike Q1), so a response lost on `execute`
is undone by the rollback that follows it, and only a forwarded `commit` whose
response is replaced by an error models "the effect landed".
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import logging

import pytest

from app.db.database import (
    admit_usage,
    create_chat_session,
    find_user_by_token_hash,
    get_chat_session,
    get_connection,
    get_user,
    init_db,
    insert_action_decisions,
    insert_user,
    touch_chat_session,
)
from app.db.errors import StorageError
from app.db.models import ActionDecisionRow, User
from tests.db_faults import (
    CONNECT_REFUSED,
    INVALID_BATON,
    NAMESPACE_SHUTDOWN_503,
    STREAM_EXPIRED,
    Fault,
)

_LOG = "app.db.database"
_BEFORE_FORWARD = [
    pytest.param(STREAM_EXPIRED, id="stream_expired"),
    pytest.param(INVALID_BATON, id="invalid_baton"),
    pytest.param(CONNECT_REFUSED, id="connect_refused"),
]
_TOKEN_HASH = "hash-secret-dana"


def _retry_records(caplog):
    return [r for r in caplog.records if r.name == _LOG]


def _usage_row(user_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM usage_daily WHERE user_id = ?", (user_id,)
        ).fetchone()


def _seed_user():
    insert_user(User(user_id="dana", role="user", token_hash=_TOKEN_HASH))


def _decision(tool_call_id):
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
    )


# --- AC 4: a before-forward failure returns the fault-free result -------------


@pytest.mark.parametrize("text", _BEFORE_FORWARD)
def test_a_read_survives_a_failure_before_the_statement_runs(faulty_db, text):
    _seed_user()
    expected = get_user("dana")
    connects = faulty_db.connects
    prefix = "SELECT * FROM USERS WHERE TOKEN_HASH"
    baseline = faulty_db.forwarded(prefix)
    faulty_db.add(Fault(text, sql=prefix))

    assert find_user_by_token_hash(_TOKEN_HASH) == expected

    assert faulty_db.forwarded(prefix) - baseline == 1  # only the retry reached the server
    assert faulty_db.connects == connects + 1  # on a freshly built client


@pytest.mark.parametrize("text", _BEFORE_FORWARD)
def test_an_idempotent_update_survives_a_failure_before_the_statement_runs(
    faulty_db, text
):
    _seed_user()
    session_id = create_chat_session("dana", "hello")
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
            ("2000-01-01T00:00:00Z", session_id),
        )
    faulty_db.add(Fault(text, sql="UPDATE CHAT_SESSIONS SET UPDATED_AT"))

    assert touch_chat_session(session_id, "dana") is True

    assert get_chat_session(session_id, "dana").updated_at != "2000-01-01T00:00:00Z"


@pytest.mark.parametrize("text", _BEFORE_FORWARD)
def test_an_idempotent_insert_survives_a_failure_before_the_statement_runs(
    faulty_db, text
):
    _seed_user()
    faulty_db.add(Fault(text, sql="INSERT INTO CHAT_SESSIONS"))

    session_id = create_chat_session("dana", "hello")

    with get_connection() as conn:
        rows = conn.execute("SELECT session_id, user_id FROM chat_sessions").fetchall()
    assert [(r["session_id"], r["user_id"]) for r in rows] == [(session_id, "dana")]


@pytest.mark.parametrize("text", _BEFORE_FORWARD)
def test_a_non_idempotent_write_survives_a_failure_before_the_statement_runs(
    faulty_db, text
):
    clean = admit_usage("u-clean")
    faulty_db.add(Fault(text, sql="INSERT INTO USAGE_DAILY"))

    admitted = admit_usage("u-fault")

    assert (admitted.day, admitted.window_requests, admitted.tokens_today) == (
        clean.day,
        clean.window_requests,
        clean.tokens_today,
    )
    assert _usage_row("u-fault")["requests"] == 1  # counted once, not twice
    assert _usage_row("u-clean")["requests"] == 1


def test_a_dead_stream_on_commit_is_not_sent_so_a_counter_is_retried(faulty_db):
    """Orchestrator decision of 2026-11-17: the server dropped the transaction with
    the stream, so the increment did not land and replaying it is safe."""
    faulty_db.add(Fault(STREAM_EXPIRED, op="commit"))

    admit_usage("u-commit")

    assert _usage_row("u-commit")["requests"] == 1
    assert faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 2  # first one rolled back


# --- AC 4: the effect landed and the response was lost -------------------------


def test_a_landed_outcome_unknown_on_a_counter_is_not_replayed(faulty_db, caplog):
    """The commit reached the server; only its answer was lost. `admit_usage` is
    NON_IDEMPOTENT, so it must propagate rather than count the request twice."""
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    with pytest.raises(StorageError):
        admit_usage("u-landed")

    assert _usage_row("u-landed")["requests"] == 1  # moved by exactly one
    assert faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 1
    assert not [r for r in _retry_records(caplog) if "retry op=" in r.getMessage()]


def test_a_lost_execute_response_inside_a_transaction_lands_nothing(faulty_db):
    """Spike Q1: DML is not durable before `commit()`. This is why the landed case
    above uses `commit`: an `execute`/`after` fault is undone by the rollback and
    would pass for any retry rule."""
    faulty_db.add(
        Fault(NAMESPACE_SHUTDOWN_503, sql="INSERT INTO USAGE_DAILY", when="after")
    )

    with pytest.raises(StorageError):
        admit_usage("u-lost")

    assert _usage_row("u-lost") is None
    assert faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 1


# --- replay semantics ----------------------------------------------------------


def test_a_replayed_batch_lands_once_with_ids_in_input_order(faulty_db):
    """Row 2 of attempt 1 fails: nothing of that attempt survives and `ids` starts
    over, so the caller gets exactly three ids, matching exactly three rows."""
    rows = [_decision("call-1"), _decision("call-2"), _decision("call-3")]
    faulty_db.add(Fault(INVALID_BATON, sql="INSERT INTO ACTION_DECISIONS", nth=2))

    ids = insert_action_decisions(rows)

    with get_connection() as conn:
        stored = conn.execute(
            "SELECT id, tool_call_id FROM action_decisions ORDER BY id"
        ).fetchall()
    assert [r["tool_call_id"] for r in stored] == ["call-1", "call-2", "call-3"]
    assert ids == [r["id"] for r in stored]


def test_a_session_created_by_a_lost_commit_is_returned_not_raised(faulty_db):
    """PRD 6.3 row 11 against the real constraint text: the retry re-sends the same
    id, the server says it exists, and that means the first attempt landed."""
    _seed_user()
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))

    session_id = create_chat_session("dana", "hello")

    with get_connection() as conn:
        rows = conn.execute("SELECT session_id, user_id FROM chat_sessions").fetchall()
    assert [(r["session_id"], r["user_id"]) for r in rows] == [(session_id, "dana")]


# --- AC 5: logs and the boot path ------------------------------------------------


def test_one_retry_is_one_info_line_without_sql_or_secrets(faulty_db, caplog):
    caplog.set_level(logging.INFO, logger=_LOG)
    _seed_user()
    faulty_db.add(Fault(INVALID_BATON, sql="SELECT * FROM USERS WHERE TOKEN_HASH"))

    find_user_by_token_hash(_TOKEN_HASH)

    records = _retry_records(caplog)
    assert [r.levelno for r in records] == [logging.INFO]
    assert records[0].getMessage().startswith(
        "retry op=find_user_by_token_hash class=dead_stream attempt=1 detail="
    )
    text = "\n".join(r.getMessage() for r in records)
    assert "SELECT" not in text and "usage_daily" not in text
    assert _TOKEN_HASH not in text


def test_an_exhausted_budget_is_two_info_lines_and_one_warning(faulty_db, caplog):
    caplog.set_level(logging.INFO, logger=_LOG)
    _seed_user()
    faulty_db.add(
        Fault(INVALID_BATON, sql="SELECT * FROM USERS WHERE TOKEN_HASH", times=3)
    )

    with pytest.raises(StorageError):
        find_user_by_token_hash(_TOKEN_HASH)

    records = _retry_records(caplog)
    assert [r.levelno for r in records] == [logging.INFO, logging.INFO, logging.WARNING]
    assert "reason=max_attempts" in records[2].getMessage()
    assert _TOKEN_HASH not in "\n".join(r.getMessage() for r in records)


def test_init_db_still_fails_fast_with_no_retry(faulty_db, caplog):
    """D17: the boot path never meets `_unit_of_work`."""
    caplog.set_level(logging.INFO, logger=_LOG)
    prefix = "CREATE TABLE IF NOT EXISTS AUDIT_LOGS"
    faulty_db.add(Fault(CONNECT_REFUSED, sql=prefix, times=5))

    with pytest.raises(StorageError):
        init_db()

    assert len([c for c in faulty_db.calls if c[1].startswith(prefix)]) == 1
    assert _retry_records(caplog) == []
