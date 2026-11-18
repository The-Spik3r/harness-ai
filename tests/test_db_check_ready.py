"""`database.check_ready()` (PRD-019 STORY-001, D3, D5).

The probe runs on a process-wide executor thread, so every test that blocks a stub
releases its Event in teardown and resets the executor: no `ready-probe` thread or
in-flight future outlives a test, and every wait here is bounded.
"""

import dataclasses
import logging
import threading
import time

import libsql
import pytest

from app.db import database
from app.services.circuit_breaker import CircuitBreaker


def _new_breaker(clock):
    return CircuitBreaker(
        "storage",
        database._BREAKER_FAILURE_THRESHOLD,
        database._BREAKER_OPEN_SECONDS,
        probe=database._probe_fresh_client,
        clock=clock,
    )


class _Stub:
    """A client whose `execute(sql)` records calls, and can raise or block on an Event."""

    def __init__(self, raises=None, block=None):
        self.calls = []
        self.raises = raises
        self.block = block

    def execute(self, sql):
        self.calls.append(sql)
        if self.block is not None:
            self.block.wait(timeout=10)  # bounded: never hangs the run
        if self.raises is not None:
            raise self.raises
        return self

    description = (("1", None, None, None, None, None, None),)  # what `_Cursor` names columns from

    def fetchone(self):
        return (1,)


@pytest.fixture(autouse=True)
def _release_and_reset():
    """Tear down in order: free any blocked probe thread, then drop the executor."""
    events = []
    database._reset_ready_probe_for_tests()
    yield events
    for event in events:
        event.set()
    database._reset_ready_probe_for_tests()


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(database, "_storage_breaker", _new_breaker(lambda: now[0]))
    return now


@pytest.fixture
def spy(monkeypatch):
    """Counts `_shared_client` and `libsql.connect` calls; hands out the stub in use."""
    state = {"shared": 0, "connect": 0, "stub": _Stub()}

    def shared():
        state["shared"] += 1
        return state["stub"]

    def connect(*args, **kwargs):
        state["connect"] += 1
        raise AssertionError("check_ready must not connect directly")

    monkeypatch.setattr(database, "_shared_client", shared)
    monkeypatch.setattr(libsql, "connect", connect)
    return state


def _calls(spy):
    return spy["shared"] + spy["connect"]


def test_breaker_open_returns_breaker_open_with_zero_driver_calls(clock, spy):
    database._storage_breaker.force_open(7.0)

    result = database.check_ready()

    assert result.reason == "breaker_open"
    assert result.breaker == "open"
    assert result.retry_after_seconds == 7
    assert _calls(spy) == 0
    assert database._ready_executor is None


def test_half_open_is_breaker_open_with_retry_after_one(clock, spy, monkeypatch):
    # A probe-less breaker: `before()` flips open -> half_open and returns without a
    # driver call, and nothing else moves it, so `check_ready()` meets a real half_open.
    breaker = CircuitBreaker("storage", database._BREAKER_FAILURE_THRESHOLD, 5.0, clock=lambda: clock[0])
    monkeypatch.setattr(database, "_storage_breaker", breaker)
    breaker.force_open(5.0)
    clock[0] = 10.0
    breaker.before()
    assert breaker.status().state == "half_open"

    result = database.check_ready()

    assert (result.reason, result.breaker, result.retry_after_seconds) == ("breaker_open", "half_open", 1)
    assert _calls(spy) == 0


def test_retry_after_is_at_least_one(clock, spy):
    database._storage_breaker.force_open(5.0)
    clock[0] = 4.9  # 0.1 s left

    assert database.check_ready().retry_after_seconds >= 1


def test_a_hundred_failing_calls_leave_consecutive_failures_unchanged(clock, spy):
    spy["stub"] = _Stub(raises=ValueError("boom"))
    database._storage_breaker.record_failure("x")
    database._storage_breaker.record_failure("x")

    results = [database.check_ready() for _ in range(100)]

    assert {r.reason for r in results} == {"database_unreachable"}
    status = database._storage_breaker.status()
    assert status.consecutive_failures == 2  # PRD-019 D5: /ready never records
    assert status.state == "closed"


def test_a_successful_probe_with_the_breaker_open_keeps_it_open(clock, spy):
    database._storage_breaker.force_open(30.0)

    result = database.check_ready()

    assert result.reason == "breaker_open"
    assert database._storage_breaker.status().state == "open"
    assert spy["stub"].calls == []


def test_a_successful_probe_does_not_reset_the_failure_count(clock, spy):
    for _ in range(3):
        database._storage_breaker.record_failure("x")
    assert database._storage_breaker.status().state == "closed"

    assert database.check_ready().reason is None
    assert database._storage_breaker.status().consecutive_failures == 3  # no record_success


def test_closed_breaker_and_success_is_ready(clock, spy):
    result = database.check_ready()

    assert result.reason is None
    assert result.breaker == "closed"
    assert result.retry_after_seconds is None
    assert spy["stub"].calls == ["SELECT 1"]


def test_deadline_returns_within_timeout_plus_half_a_second(clock, spy, monkeypatch, _release_and_reset):
    monkeypatch.setattr(database.settings, "READY_DB_TIMEOUT_SECONDS", 0.2)
    gate = threading.Event()
    _release_and_reset.append(gate)
    spy["stub"] = _Stub(block=gate)

    started = time.monotonic()
    result = database.check_ready()

    assert time.monotonic() - started < 0.7
    assert result.reason == "database_unreachable"


def test_second_call_while_stuck_does_not_submit(clock, spy, monkeypatch, _release_and_reset):
    monkeypatch.setattr(database.settings, "READY_DB_TIMEOUT_SECONDS", 0.2)
    gate = threading.Event()
    _release_and_reset.append(gate)
    stub = spy["stub"] = _Stub(block=gate)
    assert database.check_ready().reason == "database_unreachable"

    started = time.monotonic()
    second = database.check_ready()

    assert second.reason == "database_unreachable"
    assert time.monotonic() - started < 0.5
    assert stub.calls == ["SELECT 1"]  # still one statement

    gate.set()
    deadline = time.monotonic() + 5
    while not database._ready_future.done() and time.monotonic() < deadline:
        time.sleep(0.01)
    stub.block = None
    assert database.check_ready().reason is None  # the slot recovered
    assert stub.calls == ["SELECT 1", "SELECT 1"]


def test_auth_text_is_classified_database_auth(clock, spy):
    spy["stub"] = _Stub(raises=ValueError("Hrana: http error: 401 Unauthorized"))
    assert database.check_ready().reason == "database_auth"

    spy["stub"] = _Stub(raises=ValueError("connection refused"))
    assert database.check_ready().reason == "database_unreachable"


def test_it_never_raises(clock, spy, monkeypatch):
    class _BrokenBreaker:
        def status(self):
            raise RuntimeError("no status")

    monkeypatch.setattr(database, "_storage_breaker", _BrokenBreaker())
    broken = database.check_ready()
    assert (broken.reason, broken.breaker) == ("database_unreachable", "unknown")

    monkeypatch.setattr(database, "_storage_breaker", _new_breaker(lambda: 0.0))

    def raising():
        raise RuntimeError("client exploded")

    monkeypatch.setattr(database, "_shared_client", raising)
    assert database.check_ready().reason == "database_unreachable"


def test_the_warning_never_carries_the_token(clock, spy, caplog):
    sentinel = "SENTINEL-TOKEN-123"
    spy["stub"] = _Stub(raises=ValueError(f"http error: https://x.turso.io/?auth_token={sentinel}"))

    with caplog.at_level(logging.WARNING, logger=database.logger.name):
        database.check_ready()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert sentinel not in caplog.text


def test_ready_check_is_frozen_and_reasons_are_closed(clock, spy):
    result = database.check_ready()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "x"

    assert database.READY_REASONS == ("breaker_open", "database_unreachable", "database_auth", "draining")
    database._storage_breaker.force_open(3.0)
    assert database.check_ready().reason in database.READY_REASONS


@pytest.mark.db
def test_happy_path_against_the_libsql_dev_server(temp_db):
    result = database.check_ready()

    assert result == database.ReadyCheck(None, "closed", None)
    assert database._storage_breaker.status().consecutive_failures == 0
