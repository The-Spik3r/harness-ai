"""PRD-022 STORY-010: per-provider breakers, recording rules, providers_status()."""

import ast
import logging
import os
import socket
import threading
from pathlib import Path

import pytest

from app.db import database
from app.services.circuit_breaker import BreakerStatus
from app.services.upstream import health
from app.services.upstream.types import UpstreamError

_LOG = "app.services.circuit_breaker"


@pytest.fixture
def now():
    t = [0.0]
    health.reset(clock=lambda: t[0])
    return t


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger=_LOG)


def _err(kind="timeout", retryable=True, status=None, retry_after=None, text="x"):
    return UpstreamError(
        text,
        kind=kind,
        retryable=retryable,
        upstream_status=status,
        retry_after_seconds=retry_after,
    )


def _fail(name, n, **kw):
    for _ in range(n):
        health.record(name, _err(**kw))


def _st(name):
    return health.breaker(name).status()


def _lines(caplog):
    return [r for r in caplog.records if r.name == _LOG]


# --- breaker() / sync() ---------------------------------------------------------


def test_breaker_is_lazy_closed_and_identity_stable(now):
    b = health.breaker("a")
    assert b is health.breaker("a")
    assert b is not health.breaker("b")
    assert b.status().state == "closed"
    assert (health._BREAKER_FAILURE_THRESHOLD, health._BREAKER_OPEN_SECONDS) == (5, 10.0)
    assert health._PROVIDER_MISCONFIGURED_OPEN_SECONDS == 300


def test_breaker_creation_is_thread_safe(now):
    barrier = threading.Barrier(16)
    seen = []

    def go():
        barrier.wait()
        seen.append(health.breaker("p"))

    threads = [threading.Thread(target=go) for _ in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len({id(b) for b in seen}) == 1


def test_sync_prunes_absent_providers(now):
    keep, drop = health.breaker("keep"), health.breaker("drop")
    _fail("drop", 5)
    health.sync({"keep"})
    assert health.breaker("keep") is keep
    fresh = health.breaker("drop")
    assert fresh is not drop and fresh.status().state == "closed"


# --- record() -------------------------------------------------------------------


def test_success_resets_the_failure_count(now):
    _fail("p", 4)
    health.record("p", None)
    _fail("p", 4)
    assert _st("p").state == "closed"


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": "timeout"},
        {"kind": "transport"},
        {"kind": "status", "status": 503},
        {"kind": None},
    ],
)
def test_record_eligible_faults_open_at_the_fifth_for_ten_seconds(now, kw):
    _fail("p", 4, **kw)
    assert _st("p").state == "closed"
    _fail("p", 1, **kw)
    st = _st("p")
    assert st.state == "open" and st.retry_after_seconds == 10
    assert st.last_failure_class == (kw["kind"] or "unclassified")


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": "status", "retryable": False, "status": 400},
        {"kind": "shape", "retryable": False},
        {"kind": "incompatible", "retryable": False},
        {"kind": "refusal", "retryable": False},
    ],
)
def test_record_non_eligible_faults_never_touch_the_breaker(now, kw):
    _fail("p", 20, **kw)
    assert _st("p").state == "closed" and _st("p").consecutive_failures == 0
    # also from half-open
    _fail("q", 5)
    now[0] = 10.0
    assert health.admit("q").admitted
    _fail("q", 1, **kw)
    assert _st("q").state == "half_open"


def test_misconfigured_opens_at_once_for_300_and_logs_its_kind(now, caplog):
    health.record("p", _err("misconfigured", retryable=False, status=401))
    st = _st("p")
    assert (st.state, st.retry_after_seconds) == ("open", 300)
    assert st.last_failure_class == "misconfigured"
    assert "class=misconfigured" in _lines(caplog)[0].getMessage()


def test_429_retry_after_sets_the_window(now):
    _fail("p", 5, kind="status", status=429, retry_after=30)
    assert _st("p").retry_after_seconds == 30
    _fail("a", 5, kind="status", status=429, retry_after=3)
    assert _st("a").retry_after_seconds == 10
    _fail("b", 5, kind="status", status=429)
    assert _st("b").retry_after_seconds == 10


def test_429_below_threshold_does_not_force_open(now):
    _fail("p", 4, kind="status", status=429, retry_after=30)
    assert _st("p").state == "closed"


def test_a_300s_window_survives_a_429(now):
    health.record("p", _err("misconfigured", retryable=False, status=401))
    health.record("p", _err("status", status=429, retry_after=30))
    assert _st("p").retry_after_seconds == 300


def test_429_then_misconfigured_extends_to_300(now):
    _fail("p", 5, kind="status", status=429, retry_after=30)
    health.record("p", _err("misconfigured", retryable=False, status=403))
    assert _st("p").retry_after_seconds == 300


def test_half_open_trial_429_reopens_for_max_retry_after_and_ten(now):
    _fail("p", 5)
    now[0] = 10.0
    assert health.admit("p").admitted
    health.record("p", _err("status", status=429, retry_after=45))
    st = _st("p")
    assert (st.state, st.retry_after_seconds) == ("open", 45)


def test_concurrent_extends_never_shorten(now):
    for _ in range(200):
        health.reset(clock=lambda: 0.0)
        _fail("p", 5)
        barrier = threading.Barrier(2)

        def mis():
            barrier.wait()
            health.record("p", _err("misconfigured", retryable=False, status=401))

        def rl():
            barrier.wait()
            health.record("p", _err("status", status=429, retry_after=30))

        ts = [threading.Thread(target=mis), threading.Thread(target=rl)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert _st("p").retry_after_seconds == 300


# --- admit() --------------------------------------------------------------------


def test_admit_closed_open_and_trial(now):
    assert health.admit("p") == health.Admission(True)
    _fail("p", 5)
    assert health.admit("p") == health.Admission(False, "open", 10)
    now[0] = 4.5
    assert health.admit("p") == health.Admission(False, "open", 6)
    now[0] = 10.0
    assert health.admit("p").admitted
    assert health.admit("p") == health.Admission(False, "half_open_busy", 1)


def test_two_threads_after_the_window_admit_exactly_one(now):
    _fail("p", 5)
    now[0] = 10.0
    barrier = threading.Barrier(2)
    out = []

    def go():
        barrier.wait()
        out.append(health.admit("p"))

    ts = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(a.admitted for a in out) == [False, True]
    assert [a.reason for a in out if not a.admitted] == ["half_open_busy"]


def test_trial_success_closes_and_failure_reopens(now):
    _fail("p", 5)
    now[0] = 10.0
    assert health.admit("p").admitted
    health.record("p", None)
    assert _st("p").state == "closed"
    _fail("p", 5)
    now[0] = 20.0
    assert health.admit("p").admitted
    health.record("p", _err("timeout"))
    assert _st("p").state == "open"


def test_a_silent_trial_is_replaced_after_open_seconds(now):
    _fail("p", 5)
    now[0] = 10.0
    assert health.admit("p").admitted
    assert not health.admit("p").admitted
    now[0] = 20.0
    assert health.admit("p").admitted


def test_fake_clock_end_to_end(now):
    _fail("p", 5, kind="timeout")
    assert health.admit("p") == health.Admission(False, "open", 10)
    now[0] = 10.0
    assert health.admit("p").admitted
    assert health.admit("p").reason == "half_open_busy"
    health.record("p", None)
    assert _st("p").state == "closed"


# --- providers_status() and counters --------------------------------------------


def test_providers_status_shape_no_io_and_pruning(now, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("no I/O in providers_status")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(database, "get_connection", refuse)
    health.breaker("gone")
    _fail("a", 5)
    s = health.providers_status(["a", "b"])
    assert s.instance == f"{socket.gethostname()}:{os.getpid()}"
    assert list(s.providers) == ["a", "b"]
    assert all(isinstance(v, BreakerStatus) for v in s.providers.values())
    assert s.providers["a"].state == "open" and s.providers["b"].state == "closed"
    assert set(health._entries) == {"a", "b"}  # "gone" was pruned


def test_counters(now):
    _fail("p", 5, kind="timeout")  # closed -> open
    _fail("p", 2, kind="shape", retryable=False)
    health.record("p", _err("status", status=429, retry_after=30))  # extension
    s = health.providers_status(["p"]).counters
    assert s.attempts_failed == {"p:timeout": 5, "p:shape": 2, "p:status": 1}
    assert s.breaker_opens == 1  # the extension is not a transition
    now[0] = 30.0
    assert health.admit("p").admitted
    health.record("p", _err("timeout"))  # failed trial: half_open -> open
    assert health.providers_status(["p"]).counters.breaker_opens == 2
    now[0] = 100.0
    health.admit("p")
    health.record("p", None)  # close: not counted
    assert health.providers_status(["p"]).counters.breaker_opens == 2
    # force-open from closed
    health.record("q", _err("misconfigured", retryable=False, status=401))
    assert health.providers_status(["p", "q"]).counters.breaker_opens == 3


def test_skip_and_fallback_counters_and_reset(now):
    health.count_skipped("p", "open")
    health.count_skipped("p", "open")
    health.count_skipped("q", "deadline")
    health.count_fallback_answer()
    c = health.providers_status(["p"]).counters
    assert c.skipped == {"p:open": 2, "q:deadline": 1}
    assert c.fallback_answers == 1
    with pytest.raises(ValueError):
        health.count_skipped("p", "nope")
    health.reset()
    c = health.providers_status([]).counters
    assert (c.attempts_failed, c.skipped, c.fallback_answers, c.breaker_opens) == ({}, {}, 0, 0)


def test_counters_are_not_pruned_with_the_breaker(now):
    _fail("p", 1)
    health.sync([])
    assert health.providers_status([]).counters.attempts_failed == {"p:timeout": 1}


# --- logs -----------------------------------------------------------------------


def test_every_transition_is_one_warning_naming_kind_never_text(now, caplog):
    _fail("p", 5, text="SECRET prompt text")
    now[0] = 10.0
    health.admit("p")
    health.record("p", None)
    lines = _lines(caplog)
    assert [r.levelno for r in lines] == [logging.WARNING] * 3
    assert [r.getMessage() for r in lines] == [
        "breaker name=p from=closed to=open class=timeout",
        "breaker name=p from=open to=half_open class=none",
        "breaker name=p from=half_open to=closed class=none",
    ]
    assert "SECRET" not in caplog.text
    assert "SECRET" not in repr(health.providers_status(["p"]))


# --- purity ---------------------------------------------------------------------


def test_the_module_is_pure():
    source = Path(health.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {"logging", "os", "socket", "threading", "time", "dataclasses", "typing"}
    internal = {"app.services.circuit_breaker", "app.services.upstream.types"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {a.name.split(".")[0] for a in node.names} <= allowed
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module in internal or node.module.split(".")[0] in allowed
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not ({"open", "settings", "httpx", "database", "get_connection"} & (names | attrs))
