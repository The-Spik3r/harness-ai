"""PRD-018 STORY-002 (D2, Section 6.2 as amended 2026-11-17): the failure classifier.

Covers `database._classify(exc, phase)`, the closed `FailureClass` / phase
vocabularies and the per-call phase recording in `_Connection` / `_Cursor` /
`get_connection()`. Fixtures come from the STORY-001 spike
(`.agents/spikes/PRD-018-driver-failure-surface.md`, "Fixture table for
STORY-002") with Verdict V1 applied, plus the strings quoted in `database.py`'s
comments and in `tests/`.

Every test here is non-`db`: fake driver clients stand under the real
`_Connection` / `_Cursor` / `_translated()`, and no storage fixture is requested,
so nothing reaches a database and the module runs with Docker stopped.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import typing

import pytest

from app.db import database
from app.db.database import (
    FailureClass,
    Phase,
    _PHASES,
    _Connection,
    _classify,
    _mark_phase,
    _phase_of,
)
from app.db.errors import IntegrityError, MissingRelationError, StorageError

# --- verbatim fixtures -------------------------------------------------------

# PRD-018 STORY-001 spike: verbatim, via _redacted()
_BATON = "Hrana: `api error: `status=400 Bad Request, body=Received an invalid baton``"
_EXPIRED = (
    'Hrana: `api error: `status=400 Bad Request, body={"message":"The stream has expired '
    'due to inactivity","code":"STREAM_EXPIRED"}``'
)
# spike rows 1-3 (F1 / F2); the host texts are localized, U+FFFD as the driver returned it
_REFUSED = (
    "Hrana: `http error: `error trying to connect: tcp connect error: "
    "Connection refused (os error 111)``"
)
_REFUSED_HOST = (
    "Hrana: `http error: `error trying to connect: tcp connect error: No se puede "
    "establecer una conexi�n ya que el equipo de destino deneg� expresamente "
    "dicha conexi�n. (os error 10061)``"
)
_TIMEOUT_HOST = (
    "Hrana: `http error: `error trying to connect: tcp connect error: Se produjo un "
    "error durante el intento de conexi�n ya que la parte conectada no respondi� "
    "adecuadamente tras un periodo de tiempo, o bien se produjo un error en la "
    "conexi�n establecida ya que el host conectado no ha podido responder. "
    "(os error 10060)``"
)
# spike rows 10 / 11 (F3c, F3d): the restart-window texts stay OUTCOME_UNKNOWN
_NAMESPACE_503 = (
    'Hrana: `api error: `status=503 Service Unavailable, '
    'body={"error":"Namespace store has shutdown"}``'
)
_NAMESPACE_404 = (
    'Hrana: `api error: `status=404 Not Found, '
    'body={"error":"Namespace `default` doesn\'t exist"}``'
)
# database.py:372-379 and spike rows 12-14
_UNIQUE = (
    'Hrana: `stream error: `Error { message: "SQLite error: UNIQUE constraint failed: '
    'users.token_hash", code: "SQLITE_CONSTRAINT" }``'
)
_NO_TABLE = (
    'Hrana: `stream error: `Error { message: "SQLite error: no such table: users", '
    'code: "SQLITE_UNKNOWN" }``'
)
_DUPLICATE_COLUMN_TEXT = (
    'Hrana: `stream error: `Error { message: "SQLite error: duplicate column name: '
    'pii_detected_input", code: "SQLITE_UNKNOWN" }``'
)
# tests/test_db.py:4959-4963 (older spelling; carries both markers)
_OLD_UNREACHABLE = (
    "Hrana: `http error: error sending request for url "
    "(http://127.0.0.1:1/v2/pipeline): client error (Connect): "
    "tcp connect error: Connection refused (os error 111)`"
)
# tests/test_db_isolation_harness.py:474-478 (old spelling, os error 10060)
_OLD_TIMEOUT = (
    "Hrana: `http error: `error sending request for url "
    "(http://127.0.0.1:9/v2/pipeline?authToken=s3cret): client error (Connect): "
    "tcp connect error: A connection attempt failed (os error 10060)``"
)
# database.py comment quote: the elided form carries neither marker
_ELIDED_UNREACHABLE = (
    "Hrana: `http error: error sending request for url "
    "(http://127.0.0.1:1/v2/pipeline): ... Connection refused`"
)
# tests/test_db.py:4119-4122: SQLITE_BUSY is transient, never STATEMENT
_LOCKED = (
    "Hrana: `stream error: `Error { message: \"SQLite error: database "
    'is locked", code: "SQLITE_BUSY" }``'
)
_UNSEEN = "Hrana: `something the classifier has never seen`"  # spike row 15 (synthetic)
_BARE_BATON = "Received an invalid baton"  # tests/test_db.py:4351
_API_ERROR_BOOM = "Hrana: `api error`: boom"  # tests/test_db.py:2602

F = FailureClass

# (message, phase, expected). PRD 6.2 amended 2026-11-17 (orchestrator, spike V1):
# a dead stream on `commit` is NOT_SENT.
_FIXTURES = [
    (_REFUSED, "execute", F.NOT_SENT),  # spike row 1
    (_REFUSED_HOST, "execute", F.NOT_SENT),  # row 2
    (_TIMEOUT_HOST, "execute", F.NOT_SENT),  # row 3: a timeout is indistinguishable
    (_REFUSED, "commit", F.NOT_SENT),  # row 4: connect text wins at any phase
    (_REFUSED, "rollback", F.NOT_SENT),  # row 4
    (_EXPIRED, "execute", F.DEAD_STREAM),  # row 5
    (_EXPIRED, "commit", F.NOT_SENT),  # row 6, V1 applied
    (_BATON, "execute", F.DEAD_STREAM),  # row 7
    (_BATON, "commit", F.NOT_SENT),  # row 8, V1 applied
    (_BATON, "rollback", F.DEAD_STREAM),  # row 9: nothing to replay
    (_EXPIRED, "rollback", F.DEAD_STREAM),
    (_EXPIRED, "fetchone", F.DEAD_STREAM),
    (_EXPIRED, "fetchall", F.DEAD_STREAM),
    (_EXPIRED, "fetchmany", F.DEAD_STREAM),
    (_EXPIRED, "connect", F.DEAD_STREAM),
    (_EXPIRED, None, F.DEAD_STREAM),
    (_BATON, "fetchone", F.DEAD_STREAM),
    (_BATON, "fetchall", F.DEAD_STREAM),
    (_BATON, "fetchmany", F.DEAD_STREAM),
    (_BATON, "connect", F.DEAD_STREAM),
    (_BATON, None, F.DEAD_STREAM),
    (_BARE_BATON, "execute", F.DEAD_STREAM),
    (_NAMESPACE_503, "execute", F.OUTCOME_UNKNOWN),  # row 10
    (_NAMESPACE_503, "commit", F.OUTCOME_UNKNOWN),
    (_NAMESPACE_404, "execute", F.OUTCOME_UNKNOWN),  # row 11
    (_NAMESPACE_404, "commit", F.OUTCOME_UNKNOWN),
    (_UNIQUE, "execute", F.STATEMENT),  # row 12
    (_NO_TABLE, "execute", F.STATEMENT),  # row 13
    (_DUPLICATE_COLUMN_TEXT, "execute", F.STATEMENT),  # row 14
    (_UNSEEN, "execute", F.OUTCOME_UNKNOWN),  # row 15
    (_OLD_UNREACHABLE, "execute", F.NOT_SENT),  # row 16: `client error (Connect)`
    (_OLD_TIMEOUT, "execute", F.NOT_SENT),
    # Orchestrator-accepted deviation: `error sending request` alone is reqwest's
    # generic prefix (it also covers a reset after the request was written), so
    # without `tcp connect error` / `client error (Connect)` it is not NOT_SENT.
    (_ELIDED_UNREACHABLE, "execute", F.OUTCOME_UNKNOWN),
    # Orchestrator-accepted: generic `SQLite error:` / SQLITE_BUSY stays OUTCOME_UNKNOWN.
    (_LOCKED, "execute", F.OUTCOME_UNKNOWN),
    (_API_ERROR_BOOM, "execute", F.OUTCOME_UNKNOWN),
]


@pytest.mark.parametrize("message, phase, expected", _FIXTURES)
@pytest.mark.parametrize("shape", [ValueError, StorageError])
def test_classify_fixture_table(shape, message, phase, expected):
    """AC 1: every verbatim string classifies as expected, as a raw or translated exception."""
    assert _classify(shape(message), phase) is expected


@pytest.mark.parametrize("phase", list(_PHASES) + [None])
def test_an_unrecognised_hrana_text_is_never_not_sent(phase):
    """AC 2: unrecognised `Hrana:` text is OUTCOME_UNKNOWN at every phase, never NOT_SENT."""
    result = _classify(ValueError(_UNSEEN), phase)
    assert result is F.OUTCOME_UNKNOWN
    assert result != F.NOT_SENT


@pytest.mark.parametrize("phase", list(_PHASES) + [None])
def test_only_commit_turns_a_dead_stream_into_not_sent(phase):
    """AC 2 / PRD 6.2 amended 2026-11-17 (spike V1): dead stream on `commit` is NOT_SENT only there."""
    for text in (_EXPIRED, _BATON):
        expected = F.NOT_SENT if phase == "commit" else F.DEAD_STREAM
        assert _classify(ValueError(text), phase) is expected


@pytest.mark.parametrize("text", [_NAMESPACE_503, _NAMESPACE_404, _UNSEEN, _LOCKED])
def test_every_other_commit_failure_stays_outcome_unknown(text):
    """AC 2: a commit failure that is not a dead stream or a connect failure is OUTCOME_UNKNOWN."""
    assert _classify(ValueError(text), "commit") is F.OUTCOME_UNKNOWN


@pytest.mark.parametrize("phase", list(_PHASES) + [None])
def test_statement_failures_are_statement_at_every_phase(phase):
    """AC 3: IntegrityError, MissingRelationError and a duplicate column are STATEMENT, `commit` included."""
    assert _classify(IntegrityError("users.token_hash", _UNIQUE), phase) is F.STATEMENT
    assert _classify(MissingRelationError("users", _NO_TABLE), phase) is F.STATEMENT
    assert _classify(StorageError(_DUPLICATE_COLUMN_TEXT), phase) is F.STATEMENT
    # the type wins even when the text does not parse
    assert _classify(IntegrityError(None, "Hrana: `x`"), phase) is F.STATEMENT


def test_the_vocabularies_are_closed():
    """D2: four failure classes with lower-case string values, seven phases."""
    assert {c.value for c in FailureClass} == {
        "not_sent",
        "dead_stream",
        "outcome_unknown",
        "statement",
    }
    assert FailureClass.NOT_SENT == "not_sent"  # the str mixin
    assert set(_PHASES) == set(typing.get_args(Phase))
    assert set(_PHASES) == {
        "connect",
        "execute",
        "fetchone",
        "fetchall",
        "fetchmany",
        "commit",
        "rollback",
    }


def test_classify_is_pure(monkeypatch):
    """D2: no settings, no client, no I/O. Any settings read would raise on None."""
    monkeypatch.setattr(database, "settings", None)
    for message, phase, expected in _FIXTURES:
        assert _classify(ValueError(message), phase) is expected


# --- phase recording through the real wrappers -------------------------------


class _FakeCursor:
    def __init__(self, original=None):
        self._original = original

    description = (("n",),)

    def execute(self, sql, *parameters):
        if self._original is not None:
            raise self._original

    def fetchone(self):
        if self._original is not None:
            raise self._original
        return (1,)

    def fetchall(self):
        if self._original is not None:
            raise self._original
        return [(1,)]

    def fetchmany(self, *args):
        if self._original is not None:
            raise self._original
        return [(1,)]


class _FakeClient:
    """A driver client that raises one pre-built exception from the chosen calls."""

    def __init__(self, original=None, fail=()):
        self.original = original
        self.fail = set(fail)
        self.executes = []
        self.commits = 0
        self.rollbacks = 0

    def _maybe(self, name):
        if name in self.fail:
            raise self.original

    def execute(self, sql, *parameters):
        self.executes.append(sql)
        self._maybe("execute")
        return _FakeCursor(self.original if "fetch" in self.fail else None)

    def cursor(self):
        return _FakeCursor(self.original if "cursor_execute" in self.fail else None)

    def commit(self):
        self.commits += 1
        self._maybe("commit")

    def rollback(self):
        self.rollbacks += 1
        self._maybe("rollback")


def _assert_same_object(excinfo, original, phase):
    """AC 4: the very object the driver raised, labelled, otherwise untouched."""
    assert excinfo.value is original
    assert _phase_of(original) == phase
    assert str(original) == _EXPIRED
    assert original.args == (_EXPIRED,)


def test_connection_execute_labels_and_reraises_the_same_object():
    """AC 4: `_Connection.execute` -> phase `execute`."""
    original = ValueError(_EXPIRED)
    conn = _Connection(_FakeClient(original, fail={"execute"}))
    with pytest.raises(ValueError) as excinfo:
        conn.execute("SELECT 1")
    _assert_same_object(excinfo, original, "execute")


def test_cursor_execute_labels_and_reraises_the_same_object():
    """AC 4: `_Connection.cursor().execute` -> phase `execute`."""
    original = ValueError(_EXPIRED)
    cursor = _Connection(_FakeClient(original, fail={"cursor_execute"})).cursor()
    with pytest.raises(ValueError) as excinfo:
        cursor.execute("SELECT 1")
    _assert_same_object(excinfo, original, "execute")


@pytest.mark.parametrize(
    "call, phase",
    [
        (lambda c: c.fetchone(), "fetchone"),
        (lambda c: c.fetchall(), "fetchall"),
        (lambda c: c.fetchmany(2), "fetchmany"),
        (lambda c: list(c), "fetchall"),  # iteration goes through fetchall
    ],
)
def test_cursor_fetches_label_and_reraise_the_same_object(call, phase):
    """AC 4: every fetch is a recorded driver call."""
    original = ValueError(_EXPIRED)
    cursor = _Connection(_FakeClient(original, fail={"fetch"})).execute("SELECT 1")
    with pytest.raises(ValueError) as excinfo:
        call(cursor)
    _assert_same_object(excinfo, original, phase)


def test_the_commit_on_exit_is_labelled_commit():
    """AC 4: `__exit__` commits through `commit()`, so the failure is phase `commit`."""
    original = ValueError(_EXPIRED)
    client = _FakeClient(original, fail={"commit"})
    with pytest.raises(ValueError) as excinfo:
        with _Connection(client):
            pass
    _assert_same_object(excinfo, original, "commit")
    assert client.rollbacks == 0


def test_the_rollback_on_exit_is_labelled_rollback_and_keeps_the_body_as_context():
    """AC 4: a failing rollback is phase `rollback`, with the body's exception on `__context__`.

    STORY-003 relies on `__context__` to classify the body's failure too.
    """
    original = ValueError(_EXPIRED)
    client = _FakeClient(original, fail={"rollback"})
    with pytest.raises(ValueError) as excinfo:
        with _Connection(client):
            raise KeyError("body")
    _assert_same_object(excinfo, original, "rollback")
    assert isinstance(excinfo.value.__context__, KeyError)
    assert client.commits == 0


def test_get_connection_labels_a_client_failure_connect(monkeypatch):
    """AC 4: a failure to obtain the client is phase `connect`."""
    original = ValueError(_EXPIRED)

    def _raiser():
        raise original

    monkeypatch.setattr(database, "_shared_client", _raiser)
    with pytest.raises(ValueError) as excinfo:
        database.get_connection()
    _assert_same_object(excinfo, original, "connect")


def test_a_non_value_error_passes_through_unlabelled():
    """Only the driver's `ValueError` is labelled; anything else is untouched."""
    original = RuntimeError("not the driver")
    conn = _Connection(_FakeClient(original, fail={"execute"}))
    with pytest.raises(RuntimeError) as excinfo:
        conn.execute("SELECT 1")
    assert excinfo.value is original
    assert not hasattr(original, "_db_phase")


def test_the_healthy_path_is_untouched():
    """The happy path returns rows through `_Row` unchanged."""
    conn = _Connection(_FakeClient())
    assert conn.execute("SELECT 1").fetchone()[0] == 1
    with conn:
        pass


# --- _translated() keeps its contract ----------------------------------------


@pytest.fixture
def _client_sentinel(monkeypatch):
    """Stand-in for the cached client so `_invalidate_client()` is observable and restored."""
    sentinel = object()
    monkeypatch.setattr(database, "_client", sentinel)
    monkeypatch.setattr(database, "_client_key", "sentinel-key")
    return sentinel


def test_translated_reraises_without_a_second_execute(_client_sentinel):
    """AC 4 / PRD 11: one `execute`, the same driver exception as `__cause__`, client invalidated."""
    original = ValueError(_EXPIRED)
    client = _FakeClient(original, fail={"execute"})
    with pytest.raises(StorageError) as excinfo:
        with database._translated():
            with _Connection(client) as conn:
                conn.execute("SELECT 1")
    assert client.executes == ["SELECT 1"]
    assert type(excinfo.value) is StorageError
    assert str(excinfo.value) == _EXPIRED
    assert excinfo.value.__cause__ is original
    assert database._client is None  # STORY-024 AC 6
    assert (
        _classify(excinfo.value, _phase_of(excinfo.value)) is FailureClass.DEAD_STREAM
    )


def test_translated_keeps_the_client_on_a_constraint_failure(_client_sentinel):
    """AC 4 / STORY-024 AC 3 at this layer: IntegrityError, client kept, STATEMENT."""
    original = ValueError(_UNIQUE)
    client = _FakeClient(original, fail={"execute"})
    with pytest.raises(IntegrityError) as excinfo:
        with database._translated():
            with _Connection(client) as conn:
                conn.execute("INSERT")
    assert client.executes == ["INSERT"]
    assert database._client is _client_sentinel
    assert _classify(excinfo.value, _phase_of(excinfo.value)) is FailureClass.STATEMENT


def test_translated_lets_a_non_hrana_value_error_through_untouched(_client_sentinel):
    """PRD 11: a non-`Hrana:` ValueError propagates as the very object."""
    original = ValueError("decode exploded")
    with pytest.raises(ValueError) as excinfo:
        with database._translated():
            raise original
    assert excinfo.value is original


def test_a_commit_phase_baton_is_a_storage_error_classified_not_sent(_client_sentinel):
    """AC 2 / PRD 6.2 amended: dead stream on `commit` -> StorageError, NOT_SENT."""
    original = ValueError(_BATON)
    client = _FakeClient(original, fail={"commit"})
    with pytest.raises(StorageError) as excinfo:
        with database._translated():
            with _Connection(client):
                pass
    assert type(excinfo.value) is StorageError
    assert _phase_of(excinfo.value) == "commit"
    assert _classify(excinfo.value, _phase_of(excinfo.value)) is FailureClass.NOT_SENT


# --- the phase helpers --------------------------------------------------------


def test_phase_of_is_none_without_a_label():
    """`None` means "not raised through the wrapper"."""
    assert _phase_of(ValueError("x")) is None
    assert _phase_of(StorageError("x")) is None


def test_phase_of_reads_through_the_cause():
    """`_translated()` raises `from exc`, so the label is reachable from the StorageError."""
    cause = ValueError(_EXPIRED)
    _mark_phase(cause, "fetchall")
    translated = StorageError(_EXPIRED)
    translated.__cause__ = cause
    assert _phase_of(translated) == "fetchall"


def test_the_first_mark_wins():
    """The innermost (true) call is kept if the same object crosses two sites."""
    exc = ValueError("x")
    _mark_phase(exc, "execute")
    _mark_phase(exc, "commit")
    assert _phase_of(exc) == "execute"
