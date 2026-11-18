"""The journal drainer (PRD-018 STORY-009, Section 6.8 Drain, D11, D17, Risk 7).

Two halves. The non-`db` tests drive `journal_drainer.drain_once` / `_run` with a
real `AuditJournal` on `tmp_path`, a recording fake in place of
`database.drain_journal_entry`, a fake-clock breaker and a fake `stop`, so none
of them sleeps or touches storage. The `db` tests (`temp_db` / `faulty_db`, or a
real lifespan) run the real keyed transaction against the libSQL dev server.
`_isolated_audit_buffer` in conftest fails any test that leaves a journal open
or the drainer thread running.
"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import audit_journal, database, journal_drainer
from app.db.audit_journal import AuditJournal
from app.db.database import (
    drain_journal_entry,
    get_audit_log,
    get_connection,
    insert_audit_log,
    list_action_decisions,
)
from app.db.errors import AuditUnavailableError, IntegrityError, StorageUnavailableError
from app.db.journal_drainer import DrainOutcome, drain_once
from app.db.models import ActionDecisionRow, AuditLog
from app.main import app
from app.services import pipeline_executor
from app.services.circuit_breaker import CircuitBreaker
from tests.db_faults import CONNECT_REFUSED, UNIQUE_SESSION_ID, Fault

_LOG = "app.db.journal_drainer"
_REPO = Path(__file__).resolve().parents[1]
_ORIGINAL_TS = "2020-01-02T03:04:05Z"


def _audit(write_id="a" * 32, **overrides) -> AuditLog:
    base = dict(timestamp=_ORIGINAL_TS, user_id="u1", prompt_hash="h", write_id=write_id)
    return AuditLog(**{**base, **overrides})


def _decision(batch="b" * 32, index=0, **overrides) -> ActionDecisionRow:
    base = dict(
        timestamp=_ORIGINAL_TS, audit_id=None, session_id=None, user_id="u1", role="user",
        tool_call_id="call_1", tool_name="run", operation_kind=None, target_preview=None,
        arguments_hash="ah", arguments_preview=None, decision="allow", rule="r", reason="why",
        granted_by=None, classifications="[]", policy_digest="pd", write_id=f"{batch}:{index}",
    )
    return ActionDecisionRow(**{**base, **overrides})


def _count(table: str, write_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE write_id = ?", (write_id,)).fetchone()
        return row["n"]


@pytest.fixture(autouse=True)
def _clean_drainer_state():
    journal_drainer._held_back.clear()
    yield
    journal_drainer._held_back.clear()


@pytest.fixture
def journal(tmp_path):
    j = AuditJournal(str(tmp_path / "buf"), 1 << 20, 2)
    yield j
    j.close()


class _FakeDrain:
    """Stands in for `database.drain_journal_entry`; records every call."""

    def __init__(self, monkeypatch, effects=None):
        self.calls = []
        self.effects = list(effects or [])
        monkeypatch.setattr(database, "drain_journal_entry", self)

    def __call__(self, audit, decisions, *, audit_id=None):
        self.calls.append((audit, decisions, audit_id))
        if self.effects:
            effect = self.effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
        return 100 + len(self.calls)


class _FakeStop:
    """A stop object whose `wait` records its timeout and stops after `limit` waits."""

    def __init__(self, limit):
        self.limit = limit
        self.waits = []

    def is_set(self):
        return len(self.waits) >= self.limit

    def wait(self, timeout):
        self.waits.append(timeout)
        return self.is_set()


# --- non-db: drain_once ------------------------------------------------------


def test_an_empty_journal_neither_drains_nor_touches_the_breaker(journal, monkeypatch):
    fake = _FakeDrain(monkeypatch)
    probes = []
    monkeypatch.setattr(
        database, "_storage_breaker",
        CircuitBreaker("storage", 1, 30, probe=lambda: probes.append(1) or True),
    )
    database._storage_breaker.force_open(30)

    assert drain_once(journal) is DrainOutcome.EMPTY
    assert fake.calls == [] and probes == []


def test_entries_drain_oldest_first_one_per_call_and_the_file_compacts(journal, monkeypatch, caplog):
    fake = _FakeDrain(monkeypatch)
    ids = [f"{i:032d}" for i in range(3)]
    for wid in ids:
        journal.append(_audit(write_id=wid))

    with caplog.at_level(logging.INFO, logger=_LOG):
        outcomes = [drain_once(journal) for _ in range(3)]

    assert outcomes == [DrainOutcome.DRAINED] * 3
    assert [c[0].write_id for c in fake.calls] == ids  # FIFO, one entry per call (AC 1)
    assert journal.pending() == []
    assert journal.path.stat().st_size == 0  # compacted to zero bytes (AC 5)
    assert not journal.path.with_name(journal.path.name + ".checkpoint").exists()
    # AC 5: one structured line per drained entry.
    drained = [r.getMessage() for r in caplog.records if r.getMessage().startswith("journal drained ")]
    assert [m.split()[2] for m in drained] == [f"write_id={w}" for w in ids]
    assert all("user_id=u1" in m for m in drained)


def test_a_decisions_only_entry_is_drained_with_its_audit_id(journal, monkeypatch):
    fake = _FakeDrain(monkeypatch)
    journal.append(None, (_decision(),), audit_id=7, write_id="c" * 32)

    assert drain_once(journal) is DrainOutcome.DRAINED
    audit, decisions, audit_id = fake.calls[0]
    assert audit is None and audit_id == 7 and len(decisions) == 1


def _clocked_breaker(monkeypatch, probe):
    now = [0.0]
    breaker = CircuitBreaker("storage", 1, 30, clock=lambda: now[0], probe=probe)
    monkeypatch.setattr(database, "_storage_breaker", breaker)
    return breaker, now


def test_nothing_is_drained_while_the_breaker_window_is_running(journal, monkeypatch):
    fake = _FakeDrain(monkeypatch)
    probes = []
    breaker, now = _clocked_breaker(monkeypatch, lambda: probes.append(1) or True)
    journal.append(_audit())
    breaker.force_open(10)
    now[0] = 5.0

    assert drain_once(journal) is DrainOutcome.BREAKER_OPEN
    assert fake.calls == [] and probes == []  # no client was touched (AC 3)
    assert journal.pending()[0].write_id == "a" * 32


def test_an_elapsed_window_lets_the_breakers_own_probe_close_it_and_the_same_call_drains(
    journal, monkeypatch
):
    fake = _FakeDrain(monkeypatch)
    probes = []
    breaker, now = _clocked_breaker(monkeypatch, lambda: probes.append(1) or True)
    journal.append(_audit())
    breaker.force_open(10)
    now[0] = 11.0

    assert drain_once(journal) is DrainOutcome.DRAINED  # D-2: idle instance recovers
    assert probes == [1] and breaker.status().state == "closed"
    assert len(fake.calls) == 1


def test_a_failed_probe_leaves_the_entry_first_and_does_not_drain(journal, monkeypatch):
    fake = _FakeDrain(monkeypatch)
    breaker, now = _clocked_breaker(monkeypatch, lambda: False)
    journal.append(_audit())
    breaker.force_open(10)
    now[0] = 11.0

    assert drain_once(journal) is DrainOutcome.BREAKER_OPEN
    assert fake.calls == [] and journal.pending()[0].write_id == "a" * 32


def test_an_unavailable_storage_stops_the_pass_with_the_entry_still_first(journal, monkeypatch):
    _FakeDrain(monkeypatch, [StorageUnavailableError("x", 1)])
    journal.append(_audit(write_id="1" * 32))
    journal.append(_audit(write_id="2" * 32))
    size = journal.path.stat().st_size

    assert drain_once(journal) is DrainOutcome.UNAVAILABLE
    assert [e.write_id for e in journal.pending()] == ["1" * 32, "2" * 32]
    assert journal.path.stat().st_size == size  # nothing marked, nothing compacted (AC 3)
    assert journal_drainer.held_back() == 0


def test_a_refused_entry_is_held_back_and_later_entries_still_drain(journal, monkeypatch, caplog):
    secret = "SECRET-DRIVER-TEXT-AND-SQL"
    fake = _FakeDrain(monkeypatch, [IntegrityError("audit_logs.x", secret)])
    journal.append(_audit(write_id="1" * 32))
    journal.append(_audit(write_id="2" * 32))
    size = journal.path.stat().st_size

    with caplog.at_level(logging.INFO, logger=_LOG):
        assert drain_once(journal) is DrainOutcome.HELD_BACK
        assert drain_once(journal) is DrainOutcome.DRAINED  # B drains past the poison entry
        assert drain_once(journal) is DrainOutcome.EMPTY  # A is skipped for this process

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "write_id=" + "1" * 32 in errors[0].getMessage() and "error=IntegrityError" in errors[0].getMessage()
    assert secret not in caplog.text  # class name only, never driver text (D-3)
    assert [e.write_id for e in journal.pending()] == ["1" * 32]  # never deleted, never marked
    assert journal.path.stat().st_size == size  # the held entry blocks compaction
    assert journal_drainer.held_back() == 1
    assert [c[0].write_id for c in fake.calls] == ["1" * 32, "2" * 32]


def test_the_loop_yields_between_entries_and_idles_when_empty(journal, monkeypatch):
    fake = _FakeDrain(monkeypatch)
    journal.append(_audit(write_id="1" * 32))
    journal.append(_audit(write_id="2" * 32))
    stop = _FakeStop(3)

    journal_drainer._run(journal, stop)

    assert stop.waits == [
        journal_drainer._DRAIN_YIELD_SECONDS,
        journal_drainer._DRAIN_YIELD_SECONDS,
        journal_drainer._DRAIN_IDLE_SECONDS,
    ]
    assert len(fake.calls) == 2  # one drain call per tick (Risk 7)


def test_the_loop_survives_a_crash_in_a_tick(journal, monkeypatch, caplog):
    outcomes = [RuntimeError("boom-detail"), DrainOutcome.EMPTY]

    def flaky(_journal):
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(journal_drainer, "drain_once", flaky)
    stop = _FakeStop(2)

    with caplog.at_level(logging.INFO, logger=_LOG):
        journal_drainer._run(journal, stop)

    assert len(stop.waits) == 2 and outcomes == []  # kept going after the crash
    assert "tick failed error=RuntimeError" in caplog.text
    assert "boom-detail" not in caplog.text


def test_nothing_starts_at_import():
    code = (
        "import app.main, app.db.journal_drainer as d, app.db.audit_journal as j, threading; "
        "print(d.running(), j.current() is None, "
        "any(t.name == 'audit-journal-drainer' for t in threading.enumerate()))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_REPO, env=dict(os.environ), capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["False", "True", "False"]  # AC 4


# --- db: the real keyed transaction ------------------------------------------


def test_drain_inserts_the_audit_row_and_its_decisions_with_the_original_timestamp(temp_db):
    audit = _audit()
    decisions = [_decision(index=0), _decision(index=1)]

    row_id = drain_journal_entry(audit, decisions)

    assert get_audit_log(row_id).timestamp == _ORIGINAL_TS
    rows = list_action_decisions(audit_id=row_id)
    assert len(rows) == 2 and {r.audit_id for r in rows} == {row_id}
    assert {r.write_id for r in rows} == {d.write_id for d in decisions}


def test_drain_of_a_decisions_only_entry_uses_the_given_audit_id(temp_db):
    row_id = insert_audit_log(_audit())

    assert drain_journal_entry(None, [_decision()], audit_id=row_id) == row_id

    assert [r.audit_id for r in list_action_decisions(audit_id=row_id)] == [row_id]


def test_draining_the_same_entry_twice_is_a_no_op(temp_db):
    audit, decisions = _audit(), [_decision()]

    first = drain_journal_entry(audit, decisions)
    second = drain_journal_entry(audit, decisions)

    assert first == second
    assert _count("audit_logs", audit.write_id) == 1
    assert _count("action_decisions", decisions[0].write_id) == 1


def test_a_crash_between_commit_and_checkpoint_replays_as_a_no_op(temp_db, tmp_path, monkeypatch):
    directory = str(tmp_path / "buf")
    a = AuditJournal(directory, 1 << 20, 2)
    a.append(_audit(), (_decision(),))
    monkeypatch.setattr(a, "mark_drained", lambda _wid: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError, match="crash"):
        drain_once(a)  # the unit committed, then the "process died"
    orphan = a.path
    a.close()

    b = AuditJournal(directory, 1 << 20, 2)
    try:
        assert b.adopt() == 1 and len(b.pending()) == 1
        assert drain_once(b) is DrainOutcome.DRAINED
        assert _count("audit_logs", "a" * 32) == 1  # AC 2: no duplicate
        with get_connection() as conn:
            ts = conn.execute("SELECT timestamp FROM audit_logs WHERE write_id = ?", ("a" * 32,)).fetchone()
        assert ts["timestamp"] == _ORIGINAL_TS
        assert not orphan.exists()  # the adopted file drained and was deleted
        assert b.path.stat().st_size == 0
    finally:
        b.close()


def test_a_drain_failure_feeds_the_breaker_and_the_entry_stays_first(faulty_db, journal):
    faulty_db.add(Fault(CONNECT_REFUSED, sql="INSERT INTO AUDIT_LOGS", times=3))
    journal.append(_audit())

    assert drain_once(journal) is DrainOutcome.UNAVAILABLE

    assert database._storage_breaker.status().consecutive_failures == 1
    assert journal.pending()[0].write_id == "a" * 32


def test_a_statement_failure_does_not_feed_the_breaker_and_rolls_the_unit_back(faulty_db, journal):
    faulty_db.add(Fault(UNIQUE_SESSION_ID, sql="INSERT INTO ACTION_DECISIONS"))
    journal.append(_audit(), (_decision(),))

    assert drain_once(journal) is DrainOutcome.HELD_BACK

    assert database._storage_breaker.status().consecutive_failures == 0
    assert _count("audit_logs", "a" * 32) == 0  # the unit rolled back
    assert journal_drainer.held_back() == 1


# --- db: lifespans -----------------------------------------------------------


def _drainer_threads():
    return [t for t in threading.enumerate() if t.name == "audit-journal-drainer" and t.is_alive()]


def test_the_lifespan_opens_adopts_and_drains_then_stops(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    monkeypatch.setattr(journal_drainer, "_DRAIN_IDLE_SECONDS", 0.01)
    orphan = AuditJournal(settings.AUDIT_BUFFER_DIR, 1 << 20, 2)
    orphan.append(_audit(write_id="e" * 32))
    orphan.close()

    with TestClient(app):
        assert audit_journal.current() is not None and journal_drainer.running()
        threads = _drainer_threads()
        assert len(threads) == 1 and threads[0].daemon
        deadline = time.monotonic() + 5
        while _count("audit_logs", "e" * 32) != 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _count("audit_logs", "e" * 32) == 1

    assert not journal_drainer.running() and audit_journal.current() is None
    assert _drainer_threads() == []  # AC 4


def test_an_unwritable_buffer_directory_refuses_startup_naming_the_setting(temp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "AUDIT_BUFFER_DIR", str(blocker / "sub"))

    with pytest.raises(AuditUnavailableError, match="AUDIT_BUFFER_DIR"):
        with TestClient(app):
            pass

    assert not journal_drainer.running() and audit_journal.current() is None


def test_two_lifespans_in_one_process_share_one_journal_and_one_thread(temp_db, tmp_path):
    args = (str(tmp_path / "shared"), 1 << 20, 2)
    journal_drainer.start(*args)
    try:
        first = audit_journal.current()
        journal_drainer.start(*args)
        assert audit_journal.current() is first and len(_drainer_threads()) == 1
        journal_drainer.stop()
        assert journal_drainer.running() and audit_journal.current() is first
    finally:
        journal_drainer.stop()
    assert not journal_drainer.running() and audit_journal.current() is None
    journal_drainer.stop()  # a third stop is a no-op
    assert _drainer_threads() == []


def test_startup_runs_init_db_before_the_journal_and_shutdown_stops_the_executor_first(
    temp_db, monkeypatch
):
    import app.main as main_module

    order = []
    real_init, real_start, real_stop = main_module.init_db, journal_drainer.start, journal_drainer.stop
    monkeypatch.setattr(main_module, "init_db", lambda: (order.append("init_db"), real_init())[1])
    monkeypatch.setattr(journal_drainer, "start", lambda *a: (order.append("journal_start"), real_start(*a))[1])
    monkeypatch.setattr(journal_drainer, "stop", lambda: (order.append("journal_stop"), real_stop())[1])
    monkeypatch.setattr(pipeline_executor, "shutdown", lambda: order.append("pipeline_shutdown"))
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)

    with TestClient(app):
        assert order == ["init_db", "journal_start"]  # D17
    assert order[2:] == ["pipeline_shutdown", "journal_stop"]
