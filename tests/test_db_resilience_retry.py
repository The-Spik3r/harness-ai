"""PRD-018 STORY-003 (D1, D3, D5, Sections 6.1 and 6.3): `_unit_of_work` and statement kinds.

Covers the retry boundary: the kind x failure-class matrix, the budget (attempts,
full-jitter waits, the start deadline), the fresh client, the rollback-masks-body
rule of `_failure_of()`, the logs, `create_chat_session`'s duplicate-on-retry rule,
and the pin that gives every public storage function a declared kind.

Every test here is non-`db`: fake driver clients stand under the real
`_Connection` / `_Cursor` / `_translated()` / `_session()`, a fake clock and sleep
replace the module seams, and no storage fixture is requested, so nothing reaches
a database and the module runs with Docker stopped (PRD-014's guard would fail any
driver call). The `db` counterpart, against the real server, is
`tests/test_db_resilience_faults.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import inspect
import logging
import re
from pathlib import Path

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    FailureClass,
    StatementKind,
    _PHASES,
    _failure_of,
    _mark_phase,
    _phase_of,
    _retryable,
    _unit_of_work,
)
from app.db.errors import (
    IntegrityError,
    MissingRelationError,
    StorageError,
    StorageUnavailableError,
)
from tests.db_faults import (
    CONNECT_REFUSED,
    INVALID_BATON,
    NAMESPACE_SHUTDOWN_503,
    STREAM_EXPIRED,
    UNIQUE_SESSION_ID,
    UNRECOGNISED,
)

K = StatementKind
F = FailureClass

_UNIQUE = (
    'Hrana: `stream error: `Error { message: "SQLite error: UNIQUE constraint failed: '
    'users.token_hash", code: "SQLITE_CONSTRAINT" }``'
)
_NO_TABLE = (
    'Hrana: `stream error: `Error { message: "SQLite error: no such table: users", '
    'code: "SQLITE_UNKNOWN" }``'
)
_LOG = "app.db.database"


# --- fakes -------------------------------------------------------------------


class _FakeCursor:
    description = (("n",),)

    def __init__(self, client):
        self._client = client

    def fetchone(self):
        self._client._maybe("fetchone")
        return (1,)

    def fetchall(self):
        self._client._maybe("fetchall")
        return [(1,)]


class _Client:
    """A driver client that raises `ValueError(text)` from the ops named in `fail`."""

    def __init__(self, fail=None):
        self.fail = dict(fail or {})
        self.executes = []  # (sql, parameters)
        self.commits = 0
        self.rollbacks = 0

    def _maybe(self, op):
        text = self.fail.get(op)
        if text is not None:
            raise ValueError(text)

    def execute(self, sql, *parameters):
        self.executes.append((sql, parameters))
        self._maybe("execute")
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1
        self._maybe("commit")

    def rollback(self):
        self.rollbacks += 1
        self._maybe("rollback")


class _World:
    """One fake client per attempt, a fake clock, and the retry seams patched.

    `scripts[i]` is the `fail` mapping of the client built for attempt `i + 1`;
    clients after the last script are healthy. `jitter` is handed the cap.
    """

    def __init__(self, monkeypatch, *scripts, jitter=lambda cap: cap):
        self.scripts = list(scripts)
        self.clients = []
        self.invalidations = []
        self.sleeps = []
        self.caps = []
        self.now = 0.0
        self.runs = 0
        self._jitter = jitter
        monkeypatch.setattr(database, "_client", object())
        monkeypatch.setattr(database, "_client_key", "sentinel-key")
        monkeypatch.setattr(database, "_shared_client", self._shared_client)
        real_invalidate = database._invalidate_client

        def spy(stale=None):
            self.invalidations.append(stale)
            real_invalidate(stale)

        monkeypatch.setattr(database, "_invalidate_client", spy)
        monkeypatch.setattr(database, "_retry_sleep", self._sleep)
        monkeypatch.setattr(database, "_retry_clock", lambda: self.now)
        monkeypatch.setattr(database, "_retry_jitter", self._jitter_of)

    def _shared_client(self):
        index = len(self.clients)
        client = _Client(self.scripts[index] if index < len(self.scripts) else {})
        self.clients.append(client)
        return client

    def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def _jitter_of(self, cap):
        self.caps.append(cap)
        return self._jitter(cap)

    def fn(self, advance=0.0):
        """A re-runnable unit body: one execute, one fetchone. `advance` moves the clock."""

        def body(conn):
            self.runs += 1
            self.now += advance
            conn.execute("SELECT 1").fetchone()
            return "ok"

        return body

    def run(self, kind, fn=None, name="op"):
        return _unit_of_work(name, kind, fn or self.fn())

    def invalidated_clients(self):
        return [stale for stale in self.invalidations if stale is not None]


def _records(caplog):
    return [r for r in caplog.records if r.name == _LOG]


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger=_LOG)


# --- AC 1, AC 2: the kind x class matrix -------------------------------------

# name -> (text, failing op, retried for READ, IDEMPOTENT, NON_IDEMPOTENT)
_MATRIX = {
    "not_sent_on_execute": (CONNECT_REFUSED, "execute", True, True, True),
    # Orchestrator decision of 2026-11-17 (PRD 6.2 amended, spike V1): a dead stream
    # on `commit` is NOT_SENT, so a NON_IDEMPOTENT unit IS retried. This supersedes
    # the story's AC 2 wording ("DEAD_STREAM@commit is not retried").
    "dead_stream_on_commit_is_not_sent": (STREAM_EXPIRED, "commit", True, True, True),
    "dead_stream_on_execute": (INVALID_BATON, "execute", True, True, True),
    "dead_stream_on_fetch": (INVALID_BATON, "fetchone", True, True, False),
    "outcome_unknown_on_execute": (NAMESPACE_SHUTDOWN_503, "execute", True, True, False),
    "outcome_unknown_on_commit": (NAMESPACE_SHUTDOWN_503, "commit", True, True, False),
    "unrecognised_text": (UNRECOGNISED, "execute", True, True, False),
    "statement_constraint": (_UNIQUE, "execute", False, False, False),
    "statement_missing_relation": (_NO_TABLE, "execute", False, False, False),
}
_CASES = [
    pytest.param(name, kind, retried, id=f"{name}-{kind.value}")
    for name, (_, _, *flags) in _MATRIX.items()
    for kind, retried in zip((K.READ, K.IDEMPOTENT, K.NON_IDEMPOTENT), flags)
]


@pytest.mark.parametrize("name, kind, retried", _CASES)
def test_the_kind_by_class_matrix(monkeypatch, name, kind, retried):
    """AC 1 / AC 2: each kind retries exactly the classes PRD 6.3 allows."""
    text, op, *_ = _MATRIX[name]
    world = _World(monkeypatch, {op: text})
    if retried:
        assert world.run(kind) == "ok"
        assert world.runs == 2
        assert len(world.clients) == 2
        assert world.sleeps == [0.05]
        return
    with pytest.raises(StorageError) as raised:
        world.run(kind)
    assert world.runs == 1 and len(world.clients) == 1 and world.sleeps == []
    # AC 2: "today's exception type and message" is what `_session()` alone raises.
    direct_world = _World(monkeypatch, {op: text})
    with pytest.raises(StorageError) as direct:
        with database._session() as conn:
            direct_world.fn()(conn)
    if name.startswith("statement"):
        assert type(raised.value) is type(direct.value)
    else:
        # PRD-018 D7 / PRD 6.1 (STORY-005): an infrastructure failure leaves
        # _unit_of_work as StorageUnavailableError raised from today's exception;
        # the message is unchanged.
        assert type(raised.value) is StorageUnavailableError
        assert type(raised.value.__cause__) is type(direct.value)
        assert raised.value.retry_after_seconds == 1
    assert str(raised.value) == str(direct.value) == text
    if name == "statement_constraint":
        assert type(raised.value) is IntegrityError
    if name == "statement_missing_relation":
        assert type(raised.value) is MissingRelationError


def test_a_statement_failure_leaves_the_client_alone(monkeypatch):
    """6.2 rule 2: STATEMENT is never retried and never costs a client."""
    world = _World(monkeypatch, {"execute": _UNIQUE})
    with pytest.raises(IntegrityError):
        world.run(K.READ)
    assert world.invalidations == []


_FAILURES = (F.NOT_SENT, F.DEAD_STREAM, F.OUTCOME_UNKNOWN, F.STATEMENT)


@pytest.mark.parametrize("phase", [None, *_PHASES])
@pytest.mark.parametrize("failure", _FAILURES)
@pytest.mark.parametrize("kind", list(K))
def test_retryable_over_the_whole_table(kind, failure, phase):
    """D3, as an explicit table rather than a restatement of the code."""
    if failure is F.STATEMENT or (
        failure is F.OUTCOME_UNKNOWN and kind is K.NON_IDEMPOTENT
    ):
        expected = False
    elif kind is K.NON_IDEMPOTENT and failure is F.DEAD_STREAM:
        expected = phase == "execute"  # a fetch-phase dead stream is not proof
    else:
        expected = True
    assert _retryable(kind, failure, phase) is expected


# --- AC 1: the budget --------------------------------------------------------


def test_the_budget_constants():
    """D5, Section 6.6: three attempts, 50 ms then 200 ms, a 2 s start deadline."""
    assert database._RETRY_MAX_ATTEMPTS == 3
    assert database._RETRY_BACKOFF_CAPS_SECONDS == (0.05, 0.2)
    assert database._RETRY_START_DEADLINE_SECONDS == 2.0
    assert (
        len(database._RETRY_BACKOFF_CAPS_SECONDS) == database._RETRY_MAX_ATTEMPTS - 1
    )


def test_a_persistent_dead_stream_runs_three_times_and_raises_the_last(monkeypatch):
    world = _World(monkeypatch, *[{"execute": INVALID_BATON}] * 5)
    with pytest.raises(StorageError) as raised:
        world.run(K.READ)
    assert world.runs == 3
    assert len(world.clients) == 3
    assert world.sleeps == [0.05, 0.2]  # worst-case jitter
    assert str(raised.value) == INVALID_BATON
    assert raised.value.__cause__ is not None


def test_full_jitter_is_uniform_up_to_the_cap():
    draws = [database._full_jitter(0.2) for _ in range(1000)]
    assert all(0.0 <= d <= 0.2 for d in draws)
    assert len(set(draws)) > 1


def test_jitter_is_asked_for_the_caps_in_order(monkeypatch):
    world = _World(monkeypatch, *[{"execute": INVALID_BATON}] * 3, jitter=lambda cap: 0.0)
    with pytest.raises(StorageError):
        world.run(K.READ)
    assert world.caps == [0.05, 0.2]
    assert world.sleeps == [0.0, 0.0]


def test_an_attempt_started_inside_the_deadline_is_allowed(monkeypatch):
    """1.99 s into the first attempt with no wait: the second still starts."""
    world = _World(
        monkeypatch, {"execute": INVALID_BATON}, jitter=lambda cap: 0.0
    )
    assert world.run(K.READ, world.fn(advance=1.99)) == "ok"
    assert world.runs == 2


def test_no_attempt_starts_past_the_deadline(monkeypatch, caplog):
    world = _World(
        monkeypatch, {"execute": INVALID_BATON}, jitter=lambda cap: 0.0
    )
    with pytest.raises(StorageError):
        world.run(K.READ, world.fn(advance=2.01), name="slow_op")
    assert world.runs == 1
    warnings = [r for r in _records(caplog) if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "retry exhausted op=slow_op class=dead_stream attempts=1 reason=deadline" in (
        warnings[0].getMessage()
    )


def test_the_start_check_projects_the_wait(monkeypatch):
    """1.96 s + a 50 ms wait would start at 2.01 s: refused, not slept into."""
    world = _World(monkeypatch, {"execute": INVALID_BATON})
    with pytest.raises(StorageError):
        world.run(K.READ, world.fn(advance=1.96))
    assert world.runs == 1
    assert world.sleeps == []


def test_a_stalled_first_attempt_is_never_followed_by_a_retry(monkeypatch):
    """Spike F2: a connect to a black hole takes ~21 s; the deadline cannot cut it
    but must refuse to start another one after it."""
    world = _World(monkeypatch, {"execute": CONNECT_REFUSED})
    with pytest.raises(StorageError):
        world.run(K.READ, world.fn(advance=21.0))
    assert world.runs == 1


# --- fresh client ------------------------------------------------------------


@pytest.mark.parametrize(
    "text, op",
    [
        (CONNECT_REFUSED, "execute"),
        (INVALID_BATON, "execute"),
        (NAMESPACE_SHUTDOWN_503, "execute"),
    ],
    ids=["not_sent", "dead_stream", "outcome_unknown"],
)
def test_every_infrastructure_class_gets_a_fresh_client(monkeypatch, text, op):
    world = _World(monkeypatch, {op: text})
    assert world.run(K.READ) == "ok"
    first, second = world.clients
    assert first is not second
    assert any(stale is first for stale in world.invalidated_clients())
    assert [sql for sql, _ in second.executes] == ["SELECT 1"]


# --- the rollback rule (D-4) -------------------------------------------------


def _masked(body_text, body_op):
    """A client whose body failure is followed by a rollback that dies on a baton."""
    return {body_op: body_text, "rollback": INVALID_BATON}


@pytest.mark.parametrize(
    "script, kind, retried",
    [
        # body OUTCOME_UNKNOWN@execute hidden behind a baton rollback: the baton alone
        # would read as a harmless DEAD_STREAM and replay a landed write
        (_masked(NAMESPACE_SHUTDOWN_503, "execute"), K.NON_IDEMPOTENT, False),
        (_masked(NAMESPACE_SHUTDOWN_503, "execute"), K.READ, True),
        # a tie goes to the body, so its phase decides: execute is proof ...
        (_masked(INVALID_BATON, "execute"), K.NON_IDEMPOTENT, True),
        # ... and a fetch is not
        (_masked(INVALID_BATON, "fetchone"), K.NON_IDEMPOTENT, False),
    ],
    ids=["unknown-non", "unknown-read", "dead-execute-non", "dead-fetch-non"],
)
def test_a_rollback_that_masks_the_body_is_judged_pessimistically(
    monkeypatch, script, kind, retried
):
    world = _World(monkeypatch, script)
    if retried:
        assert world.run(kind) == "ok"
        assert world.runs == 2
        return
    with pytest.raises(StorageError) as raised:
        world.run(kind)
    assert world.runs == 1
    # what propagates is unchanged: the rollback's own error, as before this story
    assert str(raised.value) == INVALID_BATON
    # PRD-018 D7 (STORY-005): the infrastructure failure now propagates as a
    # StorageUnavailableError; the rollback's own error is its __cause__.
    assert _phase_of(raised.value.__cause__) == "rollback"


def test_a_non_driver_body_error_behind_a_dead_rollback_is_outcome_unknown(monkeypatch):
    world = _World(monkeypatch, {"rollback": INVALID_BATON})

    def body(conn):
        world.runs += 1
        raise KeyError("our own bug, mid-block")

    with pytest.raises(StorageError):
        world.run(K.NON_IDEMPOTENT, body)
    assert world.runs == 1  # nothing was proven, so nothing is replayed
    world = _World(monkeypatch, {"rollback": INVALID_BATON})
    assert world.run(K.READ, body_that_fails_once(world)) == "ok"


def body_that_fails_once(world):
    def body(conn):
        world.runs += 1
        if world.runs == 1:
            raise KeyError("our own bug, mid-block")
        return "ok"

    return body


def _driver(text, phase):
    exc = ValueError(text)
    _mark_phase(exc, phase)
    return exc


def test_failure_of_reads_the_nested_translated_shape():
    """`find_user_by_token_hash` nests `_translated()`: the body is a StorageError."""
    inner = StorageError(INVALID_BATON)
    inner.__cause__ = _driver(INVALID_BATON, "execute")
    rollback = _driver(INVALID_BATON, "rollback")
    rollback.__context__ = inner
    outer = StorageError(INVALID_BATON)
    outer.__cause__ = rollback
    assert _failure_of(outer) == (F.DEAD_STREAM, "execute")


def test_failure_of_takes_the_more_pessimistic_and_ties_go_to_the_body():
    rollback = _driver(INVALID_BATON, "rollback")
    rollback.__context__ = _driver(NAMESPACE_SHUTDOWN_503, "execute")
    assert _failure_of(rollback) == (F.OUTCOME_UNKNOWN, "execute")
    tie = _driver(INVALID_BATON, "rollback")
    tie.__context__ = _driver(INVALID_BATON, "fetchone")
    assert _failure_of(tie) == (F.DEAD_STREAM, "fetchone")
    refused = _driver(INVALID_BATON, "rollback")
    refused.__context__ = IntegrityError("users.user_id", _UNIQUE)
    assert _failure_of(refused)[0] is F.STATEMENT


def test_failure_of_without_a_body_or_off_the_rollback_phase_is_plain():
    alone = _driver(INVALID_BATON, "rollback")
    assert _failure_of(alone) == (F.DEAD_STREAM, "rollback")
    execute = _driver(INVALID_BATON, "execute")
    execute.__context__ = _driver(NAMESPACE_SHUTDOWN_503, "execute")
    assert _failure_of(execute) == (F.DEAD_STREAM, "execute")  # context ignored


# --- pass-through ------------------------------------------------------------


def test_our_own_storage_error_is_not_classified_or_retried(monkeypatch, caplog):
    """`append_chat_message`'s ownership refusal carries no `Hrana:` prefix."""
    world = _World(monkeypatch)
    refusal = StorageError("chat session not available for this owner")

    def body(conn):
        world.runs += 1
        raise refusal

    with pytest.raises(StorageError) as raised:
        world.run(K.NON_IDEMPOTENT, body)
    assert raised.value is refusal
    assert world.runs == 1
    assert world.invalidations == []
    assert _records(caplog) == []


@pytest.mark.parametrize(
    "error", [KeyError("bug"), ValueError("not the driver's")], ids=["key", "value"]
)
def test_a_non_driver_exception_passes_through_as_the_same_object(monkeypatch, error):
    world = _World(monkeypatch)

    def body(conn):
        world.runs += 1
        raise error

    with pytest.raises(type(error)) as raised:
        world.run(K.READ, body)
    assert raised.value is error
    assert world.runs == 1


# --- AC 5: logs --------------------------------------------------------------


def test_one_info_line_per_retry(monkeypatch, caplog):
    world = _World(monkeypatch, {"execute": INVALID_BATON}, {"execute": INVALID_BATON})
    assert world.run(K.READ, name="get_user") == "ok"
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.INFO, logging.INFO]
    messages = [r.getMessage() for r in records]
    assert re.match(r"^retry op=get_user class=dead_stream attempt=1 detail=", messages[0])
    assert re.match(r"^retry op=get_user class=dead_stream attempt=2 detail=", messages[1])


def test_an_exhausted_budget_logs_one_warning(monkeypatch, caplog):
    world = _World(monkeypatch, *[{"execute": INVALID_BATON}] * 3)
    with pytest.raises(StorageError):
        world.run(K.READ, name="get_user")
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.INFO, logging.INFO, logging.WARNING]
    assert re.match(
        r"^retry exhausted op=get_user class=dead_stream attempts=3 "
        r"reason=max_attempts detail=",
        records[2].getMessage(),
    )


@pytest.mark.parametrize(
    "text, op, expected_class",
    [
        (NAMESPACE_SHUTDOWN_503, "execute", "outcome_unknown"),
        (NAMESPACE_SHUTDOWN_503, "commit", "outcome_unknown"),
        (INVALID_BATON, "fetchone", "dead_stream"),
    ],
)
def test_a_refused_retry_on_an_infrastructure_class_logs_one_warning(
    monkeypatch, caplog, text, op, expected_class
):
    """Orchestrator decision 4: a NON_IDEMPOTENT refusal is visible in the logs."""
    world = _World(monkeypatch, {op: text})
    with pytest.raises(StorageError):
        world.run(K.NON_IDEMPOTENT, name="admit_usage")
    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert re.match(
        rf"^retry refused op=admit_usage class={expected_class} "
        r"kind=non_idempotent detail=",
        records[0].getMessage(),
    )


@pytest.mark.parametrize("text", [_UNIQUE, _NO_TABLE], ids=["constraint", "relation"])
def test_a_statement_failure_logs_nothing(monkeypatch, caplog, text):
    world = _World(monkeypatch, {"execute": text})
    with pytest.raises(StorageError):
        world.run(K.NON_IDEMPOTENT)
    assert _records(caplog) == []


def test_logs_carry_neither_the_credential_nor_echoed_sql(monkeypatch, caplog):
    monkeypatch.setattr(settings, "TURSO_AUTH_TOKEN", "s3cr3t-token-value")
    leaking = (
        "Hrana: `api error: `status=503 Service Unavailable, "
        "body=denied for s3cr3t-token-value``"
    )
    echoing = 'Hrana: `stream error: near "SELECT secret_column": syntax error`'
    escaped = 'Hrana: `stream error: near \\"SELECT secret_column\\": syntax error`'
    world = _World(
        monkeypatch, {"execute": leaking}, {"execute": echoing}, {"execute": escaped}
    )
    with pytest.raises(StorageError):
        world.run(K.READ)
    text = "\n".join(r.getMessage() for r in _records(caplog))
    assert "s3cr3t-token-value" not in text
    assert "***" in text
    assert "secret_column" not in text
    assert 'near "<elided>"' in text
    assert "SELECT 1" not in text  # the unit's own SQL never reaches a log


def test_a_long_detail_is_cut(monkeypatch, caplog):
    long_text = "Hrana: `unrecognised " + "x" * 2000 + "`"
    world = _World(monkeypatch, {"execute": long_text})
    world.run(K.READ)
    assert len(_records(caplog)[0].getMessage()) < 800


# --- create_chat_session: the duplicate-on-retry rule ------------------------


def test_a_duplicate_session_id_on_a_retry_is_success(monkeypatch):
    """PRD 6.3 row 11: attempt 1's commit response was lost; attempt 2 finds the row."""
    world = _World(
        monkeypatch,
        {"commit": NAMESPACE_SHUTDOWN_503},
        {"execute": UNIQUE_SESSION_ID},
    )
    session_id = database.create_chat_session("u1", "title")
    first, second = world.clients
    assert first.executes[0][1] == second.executes[0][1]  # same id, same timestamps
    assert session_id == first.executes[0][1][0][0]


def test_a_duplicate_session_id_on_the_first_attempt_is_raised(monkeypatch):
    world = _World(monkeypatch, {"execute": UNIQUE_SESSION_ID})
    with pytest.raises(IntegrityError):
        database.create_chat_session("u1", "title")
    assert len(world.clients) == 1


def test_a_different_constraint_on_a_retry_is_raised(monkeypatch):
    _World(monkeypatch, {"commit": NAMESPACE_SHUTDOWN_503}, {"execute": _UNIQUE})
    with pytest.raises(IntegrityError):
        database.create_chat_session("u1", "title")


# --- AC 3: every public function has a declared kind -------------------------

# name -> kind, with the PRD 6.3 row it comes from.
_EXPECTED_KINDS = {
    # PRD-018 D4 (STORY-004): IDEMPOTENT when keyed, i.e. every row carries a
    # write_id. The kind is chosen per call; _PER_CALL_KIND pins the exact
    # expression, and an unkeyed call is NON_IDEMPOTENT (tests/
    # test_db_resilience_write_id.py).
    "insert_audit_log": K.IDEMPOTENT,  # rows 6, 8
    # PRD-018 D11 (STORY-009): every journaled row is keyed, so the drain unit is
    # a literal IDEMPOTENT, not _keyed_kind(...).
    "drain_journal_entry": K.IDEMPOTENT,
    "find_duplicate_timestamp": K.READ,  # row 5
    "mark_audit_log_failed": K.IDEMPOTENT,  # row 10
    "get_audit_log": K.READ,  # admin read
    "count_audit_logs": K.READ,
    "list_audit_logs": K.READ,
    "count_blocked_duplicates": K.READ,  # summary reads
    "count_blocked_suspicious": K.READ,
    "count_unique_users": K.READ,
    "count_successful_queries": K.READ,
    "top_models": K.READ,
    "top_users": K.READ,
    "count_pii_detected_queries": K.READ,
    "top_pii_entities": K.READ,
    "sum_input_tokens": K.READ,
    "sum_output_tokens": K.READ,
    "count_blocked_usage_limits": K.READ,
    "summary_snapshot": K.READ,
    "get_user": K.READ,  # CLI read
    "find_user_by_token_hash": K.READ,  # row 1
    "list_users": K.READ,
    "count_active_users": K.READ,
    "insert_user": K.NON_IDEMPOTENT,  # 6.3 prose: a replay could misreport a duplicate
    "deactivate_user": K.IDEMPOTENT,  # 6.3 prose
    "set_user_token_hash": K.IDEMPOTENT,
    "set_user_limits": K.IDEMPOTENT,
    "admit_usage": K.NON_IDEMPOTENT,  # row 4 (O3)
    "charge_usage": K.NON_IDEMPOTENT,  # row 7
    "usage_snapshot": K.READ,
    "create_chat_session": K.IDEMPOTENT,  # row 11
    "get_chat_session": K.READ,  # rows 2, 14
    "list_chat_sessions": K.READ,
    "rename_chat_session": K.IDEMPOTENT,  # 6.3 prose
    "touch_chat_session": K.IDEMPOTENT,  # row 13
    "delete_chat_session": K.IDEMPOTENT,  # 6.3 prose
    "append_chat_message": K.NON_IDEMPOTENT,  # row 12
    "list_chat_messages": K.READ,  # row 3
    "count_chat_sessions": K.READ,
    "insert_action_decisions": K.IDEMPOTENT,  # row 9, when keyed (PRD-018 D4, STORY-004)
    "list_action_decisions": K.READ,
    "count_action_decisions": K.READ,
}
# PRD-018 D4 (STORY-004): the only two units whose kind is an expression, not a
# constant. The expression is pinned verbatim, so neither can drift to a constant
# NON_IDEMPOTENT/IDEMPOTENT, and no other function can join without editing this.
_PER_CALL_KIND = {
    "insert_audit_log": "_keyed_kind([entry.write_id])",
    "insert_action_decisions": "_keyed_kind([row.write_id for row in rows])",
}
# D17: the boot path keeps its direct session and fails fast; `get_connection` is the
# raw transaction handle thirteen test modules open themselves.
# PRD-018 STORY-012: `storage_status` reads memory only (D16), so it runs no unit.
_EXEMPT = {"get_connection", "check_database_reachable", "init_db", "storage_status"}


def _top_level_functions():
    tree = ast.parse(Path(database.__file__).read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _calls_to(function, name):
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_the_table_covers_the_modules_public_functions():
    """A new public function fails here until it is given a kind."""
    public = {
        name
        for name, obj in vars(database).items()
        if inspect.isfunction(obj)
        and obj.__module__ == database.__name__
        and not name.startswith("_")
    }
    # PRD-018 STORY-009: 41 -> 42 with drain_journal_entry.
    assert len(_EXPECTED_KINDS) == 42
    assert public == set(_EXPECTED_KINDS) | _EXEMPT


def test_every_public_function_runs_one_unit_of_its_own_name_and_kind():
    """AC 3: the call site says what the table says."""
    functions = _top_level_functions()
    for name, kind in _EXPECTED_KINDS.items():
        calls = _calls_to(functions[name], "_unit_of_work")
        assert len(calls) == 1, name
        first, second = calls[0].args[:2]
        assert isinstance(first, ast.Constant) and first.value == name, name
        # PRD-018 D4 (STORY-004): the two audit inserts pin their per-call
        # expression; the other 39 still require the literal StatementKind.X.
        expected = _PER_CALL_KIND.get(name, f"StatementKind.{kind.name}")
        assert ast.unparse(second) == expected, name
    assert set(_PER_CALL_KIND) == {"insert_audit_log", "insert_action_decisions"}
    assert set(_PER_CALL_KIND) <= set(_EXPECTED_KINDS)


@pytest.mark.parametrize(
    ("write_ids", "kind"),
    [
        (["a"], K.IDEMPOTENT),
        (["a:0", "a:1"], K.IDEMPOTENT),
        ([None], K.NON_IDEMPOTENT),
        (["a:0", None], K.NON_IDEMPOTENT),
        ([], K.NON_IDEMPOTENT),
    ],
)
def test_keyed_kind_is_idempotent_only_when_every_row_is_keyed(write_ids, kind):
    """PRD-018 D4 (STORY-004): one unkeyed row makes the whole unit unsafe to replay."""
    assert database._keyed_kind(write_ids) is kind


def test_the_expected_kind_of_a_keyed_unit_is_what_keyed_kind_returns():
    """Ties the table's value to the expression it summarises."""
    assert database._keyed_kind(["x"]) is _EXPECTED_KINDS["insert_audit_log"]
    assert database._keyed_kind(["x:0"]) is _EXPECTED_KINDS["insert_action_decisions"]


def test_nothing_opens_a_session_outside_the_unit_and_the_boot_path():
    """A future function that opens its own session fails here, even a private one."""
    functions = _top_level_functions()
    assert {n for n, f in functions.items() if _calls_to(f, "_session")} == {
        "_unit_of_work",
        "init_db",
    }
    assert {n for n, f in functions.items() if _calls_to(f, "get_connection")} == {
        "_session",
        "check_database_reachable",
    }


def test_the_boot_path_never_meets_the_unit_of_work():
    """D17: `init_db()` and `check_database_reachable()` keep failing fast."""
    functions = _top_level_functions()
    for name in ("init_db", "check_database_reachable"):
        assert _calls_to(functions[name], "_unit_of_work") == [], name
