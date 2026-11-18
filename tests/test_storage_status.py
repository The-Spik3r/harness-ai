"""PRD-018 STORY-012 (F8, D16, Section 10): `storage_status()`, the counters, `GET /storage/status`.

Every test here is non-`db`: the conftest guard fails any driver call, so a
passing module is itself evidence that `storage_status()` and the endpoint make
none (AC 1, AC 2). The retry counters ride the fake world of
`tests/test_db_resilience_retry.py`. The role matrix (an identity read) is
`tests/test_rbac.py::test_storage_status_read_matrix`.

Orchestrator rulings under test: refused retries count in `exhausted` (no
separate map); `draining` = drainer running AND breaker closed AND non-held-back
entries; `headroom_bytes` is the admission reserve; `breaker_opens` counts every
transition into open, a failed probe's re-open included.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import socket
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import audit_journal, database, journal_drainer, storage_counters
from app.db.audit_journal import AuditJournal, _JOURNAL_ENTRY_RESERVE_BYTES
from app.db.database import FailureClass, StatementKind, storage_status
from app.db.errors import AuditUnavailableError, StorageUnavailableError
from app.db.models import AuditLog
from app.main import app
from app.services.circuit_breaker import CircuitBreaker
from tests.db_faults import CONNECT_REFUSED, NAMESPACE_SHUTDOWN_503
from tests.test_db_resilience_retry import _UNIQUE, _World

K = StatementKind
F = FailureClass

_JOURNAL_KEYS = {
    "open", "entries", "bytes", "max_bytes", "headroom_bytes", "oldest_timestamp",
    "draining", "adopted_files", "held_back_entries", "held_back_files",
}
_COUNTER_KEYS = {
    "retries", "exhausted", "breaker_opens", "journal_appended", "journal_drained",
    "torn_tail_discarded",
}


@pytest.fixture
def journal(tmp_path):
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    yield opened
    audit_journal.close_journal()


def _audit(write_id="w" * 32) -> AuditLog:
    return AuditLog(
        timestamp="2026-11-17T10:00:00Z", user_id="u1", prompt_hash="h", write_id=write_id
    )


# --- shape (AC 1) --------------------------------------------------------------


def test_instance_and_breaker_are_the_process_and_the_breaker():
    status = storage_status()
    assert status.instance == f"{socket.gethostname()}:{os.getpid()}"
    assert status.breaker == database._storage_breaker.status()


def test_no_journal_is_the_zero_shape_and_never_raises():
    assert audit_journal.current() is None
    view = storage_status().journal
    assert view == database.JournalView(
        open=False,
        entries=0,
        bytes=0,
        max_bytes=settings.AUDIT_BUFFER_MAX_BYTES,
        headroom_bytes=settings.PIPELINE_MAX_WORKERS * _JOURNAL_ENTRY_RESERVE_BYTES,
        oldest_timestamp=None,
        draining=False,
        adopted_files=0,
        held_back_entries=0,
        held_back_files=0,
    )
    assert set(dataclasses.asdict(view)) == _JOURNAL_KEYS


def test_an_open_journal_is_reported_with_the_admission_reserve(journal):
    journal.append(_audit())
    view = storage_status().journal
    assert view.open and view.entries == 1
    assert view.bytes == journal.status().bytes > 0
    assert view.max_bytes == 1 << 20
    # The admission reserve (workers x 64 KiB), not free bytes.
    assert view.headroom_bytes == 2 * _JOURNAL_ENTRY_RESERVE_BYTES
    assert view.oldest_timestamp is not None
    assert view.draining is False  # the drainer thread is not running here
    assert set(dataclasses.asdict(view)) == _JOURNAL_KEYS


def test_the_counters_are_the_snapshot():
    storage_counters.retry("op", "not_sent")
    counters = storage_status().counters
    assert counters.retries == {"op:not_sent": 1}
    assert set(dataclasses.asdict(counters)) == _COUNTER_KEYS


@pytest.mark.parametrize(
    "running, state, held, expected",
    [
        (False, "closed", 0, False),  # thread not running
        (True, "open", 0, False),  # outage: the drainer idles (PRD example)
        (True, "closed", 0, True),
        (True, "closed", 1, False),  # only held-back entries: not work
    ],
)
def test_draining_truth_table(monkeypatch, journal, running, state, held, expected):
    journal.append(_audit())  # one entry
    if state == "open":
        database._storage_breaker.force_open(30)
    # A context, so the patched `running` is undone before the conftest leak
    # guard asks whether a drainer thread is alive.
    with monkeypatch.context() as patched:
        patched.setattr(journal_drainer, "running", lambda: running)
        patched.setattr(journal_drainer, "held_back", lambda: held)
        view = storage_status().journal
    assert view.entries == 1 and view.held_back_entries == held
    assert view.draining is expected


# --- zero driver calls, never `_client_lock` (AC 1, AC 2) ------------------------


def _forbid_driver(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("storage_status() reached the driver")

    monkeypatch.setattr(database.libsql, "connect", boom)
    monkeypatch.setattr(database, "_shared_client", boom)
    monkeypatch.setattr(database, "get_connection", boom)


def test_storage_status_makes_no_driver_call_even_with_the_breaker_open(
    monkeypatch, journal
):
    _forbid_driver(monkeypatch)
    database._storage_breaker.force_open(30)
    journal.append(_audit())
    status = storage_status()
    assert status.breaker.state == "open" and status.journal.entries == 1


def test_storage_status_answers_while_the_client_lock_is_held(monkeypatch):
    """The 21 s stall case: another thread sits inside `_client_lock`."""
    _forbid_driver(monkeypatch)
    answered = []
    with database._client_lock:
        worker = threading.Thread(target=lambda: answered.append(storage_status()))
        worker.start()
        worker.join(timeout=5)
        assert not worker.is_alive(), "storage_status() waited on _client_lock"
    assert len(answered) == 1


# --- the endpoint (AC 2, AC 3) ----------------------------------------------------

client = TestClient(app)
_ADMIN = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


def test_endpoint_returns_every_prd_key_for_the_admin_token(monkeypatch):
    _forbid_driver(monkeypatch)
    response = client.get("/storage/status", headers=_ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"instance", "breaker", "journal", "counters"}
    assert set(body["breaker"]) == {
        "state", "since", "consecutive_failures", "last_failure_class", "retry_after_seconds",
    }
    assert set(body["journal"]) == _JOURNAL_KEYS
    assert set(body["counters"]) == _COUNTER_KEYS
    assert body["breaker"]["state"] == "closed"


def test_endpoint_answers_200_with_the_breaker_open(monkeypatch):
    _forbid_driver(monkeypatch)
    database._storage_breaker.force_open(30)
    response = client.get("/storage/status", headers=_ADMIN)
    assert response.status_code == 200
    breaker = response.json()["breaker"]
    assert breaker["state"] == "open" and breaker["retry_after_seconds"] >= 1
    assert client.get("/health").json() == {"status": "ok"}  # unchanged


def test_endpoint_without_a_token_is_401():
    assert client.get("/storage/status").status_code == 401


# --- one test per counter (AC 5) ----------------------------------------------------


def test_one_retry_counts_once(monkeypatch):
    world = _World(monkeypatch, {"execute": CONNECT_REFUSED})
    assert world.run(K.READ, name="op") == "ok"
    snap = storage_counters.snapshot()
    assert snap.retries == {f"op:{F.NOT_SENT.value}": 1}
    assert snap.exhausted == {}


def test_a_spent_budget_counts_retries_then_one_exhausted(monkeypatch):
    failing = {"execute": CONNECT_REFUSED}
    world = _World(monkeypatch, failing, failing, failing, failing, failing)
    with pytest.raises(StorageUnavailableError):
        world.run(K.READ, name="op")
    snap = storage_counters.snapshot()
    key = f"op:{F.NOT_SENT.value}"
    assert snap.exhausted == {key: 1}
    assert snap.retries == {key: database._RETRY_MAX_ATTEMPTS - 1}


def test_a_refused_retry_counts_in_exhausted_and_not_in_retries(monkeypatch):
    # Orchestrator ruling 1: refused retries share `exhausted` (PRD example).
    world = _World(monkeypatch, {"execute": NAMESPACE_SHUTDOWN_503})
    with pytest.raises(StorageUnavailableError):
        world.run(K.NON_IDEMPOTENT, name="admit_usage")
    snap = storage_counters.snapshot()
    assert snap.exhausted == {f"admit_usage:{F.OUTCOME_UNKNOWN.value}": 1}
    assert snap.retries == {}


def test_a_statement_failure_counts_nothing(monkeypatch):
    world = _World(monkeypatch, {"execute": _UNIQUE})
    with pytest.raises(Exception):
        world.run(K.READ, name="op")
    snap = storage_counters.snapshot()
    assert snap.retries == {} and snap.exhausted == {}


def _hooked_breaker(clock, probe):
    return CircuitBreaker(
        "storage", 2, 10.0, clock=clock, probe=probe,
        on_transition=database._count_breaker_open,
    )


def test_breaker_opens_counts_every_transition_into_open_and_only_those():
    now = [0.0]
    breaker = _hooked_breaker(lambda: now[0], probe=lambda: False)
    breaker.record_failure("not_sent")
    assert storage_counters.snapshot().breaker_opens == 0
    breaker.record_failure("not_sent")  # closed -> open
    assert storage_counters.snapshot().breaker_opens == 1
    with pytest.raises(Exception):
        breaker.before()  # refused while open: no transition
    assert storage_counters.snapshot().breaker_opens == 1
    now[0] = 11.0
    with pytest.raises(Exception):
        breaker.before()  # window elapsed, the probe fails: re-open
    assert storage_counters.snapshot().breaker_opens == 2


def test_the_factory_breaker_carries_the_hook():
    breaker = database._new_storage_breaker()
    breaker.force_open(30)
    assert storage_counters.snapshot().breaker_opens == 1
    # The autouse fixture builds through the factory, so the live one counts too.
    database._storage_breaker.force_open(30)
    assert storage_counters.snapshot().breaker_opens == 2


def test_journal_appended_counts_an_acknowledged_append_only(tmp_path):
    # PRD-020 D13 (STORY-006): five more columns per entry pushed one entry past
    # the old 1000-byte cap; 2000 still holds a few and fills quickly.
    journal = AuditJournal(str(tmp_path / "buf"), 2000, 0)
    try:
        journal.append(_audit(uuid_like()))
        assert storage_counters.snapshot().journal_appended == 1
        with pytest.raises(AuditUnavailableError):
            while True:  # fill to the cap
                journal.append(_audit(uuid_like()))
        appended = storage_counters.snapshot().journal_appended
        assert appended == journal.status().entries  # every acknowledged one, no more
        with pytest.raises(AuditUnavailableError):  # a refused append counts nothing
            journal.append(_audit(uuid_like()))
        assert storage_counters.snapshot().journal_appended == appended
    finally:
        journal.close()


_counter = iter(range(10_000))


def uuid_like() -> str:
    return f"{next(_counter):032d}"


def test_journal_drained_counts_mark_drained_not_an_unknown_id(tmp_path):
    journal = AuditJournal(str(tmp_path / "buf"), 1 << 20, 2)
    try:
        entry = journal.append(_audit())
        with pytest.raises(KeyError):
            journal.mark_drained("nope")
        assert storage_counters.snapshot().journal_drained == 0
        journal.mark_drained(entry.write_id)
        assert storage_counters.snapshot().journal_drained == 1
    finally:
        journal.close()


def _orphan(tmp_path: Path) -> Path:
    directory = tmp_path / "buf"
    first = AuditJournal(str(directory), 1 << 20, 2)
    first.append(_audit("a" * 32))
    path = first.path
    first.close()
    return path


def test_torn_tail_counts_the_discarded_partial_line(tmp_path):
    path = _orphan(tmp_path)
    with open(path, "ab") as handle:
        handle.write(b'{"v":1,"write_id":"zz')  # never acknowledged
    second = AuditJournal(str(path.parent), 1 << 20, 2)
    try:
        assert second.adopt() == 1
        assert storage_counters.snapshot().torn_tail_discarded == 1
    finally:
        second.close()


def test_a_damaged_file_counts_no_torn_tail(tmp_path):
    path = _orphan(tmp_path)
    data = path.read_bytes()
    path.write_bytes(b"not json at all\n" + data)  # corrupt non-last line
    second = AuditJournal(str(path.parent), 1 << 20, 2)
    try:
        assert second.adopt() == 0
        assert storage_counters.snapshot().torn_tail_discarded == 0
    finally:
        second.close()


# --- the pure modules stay pure ------------------------------------------------------


def test_circuit_breaker_knows_neither_database_nor_counters():
    source = (Path(database.__file__).parents[1] / "services" / "circuit_breaker.py").read_text(
        encoding="utf-8"
    )
    assert "storage_counters" not in source
    assert "app.db" not in source
