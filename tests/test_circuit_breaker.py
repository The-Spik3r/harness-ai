"""The reusable circuit breaker, driven with an injected clock (PRD-018 STORY-005).

Pure: no database, no settings, no sleeping. Every threaded test waits only on
events, barriers and joins with a timeout, so a regression fails instead of
hanging the run.
"""

import ast
import dataclasses
import inspect
import json
import logging
import re
import threading
import time
from pathlib import Path

import pytest

from app.services import circuit_breaker
from app.services.circuit_breaker import BreakerOpen, BreakerStatus, CircuitBreaker

_LOG = "app.services.circuit_breaker"


@pytest.fixture
def now():
    return [0.0]


def _breaker(now, threshold=3, open_seconds=10.0, probe=None, name="storage"):
    return CircuitBreaker(
        name, threshold, open_seconds, clock=lambda: now[0], probe=probe
    )


def _open(breaker, failures=3, cls="not_sent"):
    for _ in range(failures):
        breaker.record_failure(cls)


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == _LOG]


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger=_LOG)


# P1 ------------------------------------------------------------------------


@pytest.mark.parametrize("threshold", [3, 5])
def test_opens_after_exactly_the_threshold(now, threshold):
    breaker = _breaker(now, threshold=threshold)
    for _ in range(threshold - 1):
        breaker.record_failure("not_sent")
    assert breaker.status().state == "closed"
    breaker.before()  # still admitted
    breaker.record_failure("not_sent")
    assert breaker.status().state == "open"
    with pytest.raises(BreakerOpen):
        breaker.before()


# P2 ------------------------------------------------------------------------


def test_a_success_resets_the_count(now):
    breaker = _breaker(now, threshold=5)
    _open(breaker, failures=4)
    breaker.record_success()
    assert breaker.status().consecutive_failures == 0
    _open(breaker, failures=4)
    assert breaker.status().state == "closed"


# P3 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "at, expected", [(0.0, 10), (0.8, 10), (9.2, 1), (9.99, 1), (5.0, 5)]
)
def test_before_while_open_rounds_retry_after_up(now, at, expected):
    breaker = _breaker(now)
    _open(breaker)
    now[0] = at
    with pytest.raises(BreakerOpen) as refused:
        breaker.before()
    assert refused.value.retry_after_seconds == expected
    assert refused.value.name == "storage"
    assert breaker.status().retry_after_seconds == expected


# P4 / P5 -------------------------------------------------------------------


def test_half_open_exactly_at_open_seconds_and_the_probe_decides(now):
    calls = []
    breaker = _breaker(now, probe=lambda: calls.append(1) or True)
    _open(breaker)
    now[0] = 9.999
    with pytest.raises(BreakerOpen):
        breaker.before()
    assert calls == []
    now[0] = 10.0
    breaker.before()
    assert calls == [1]
    status = breaker.status()
    assert status.state == "closed" and status.consecutive_failures == 0
    breaker.before()  # admitted again, no second probe
    assert calls == [1]


def test_a_failed_probe_reopens_for_another_window(now):
    breaker = _breaker(now, probe=lambda: False)
    _open(breaker, cls="outcome_unknown")
    now[0] = 12.0
    with pytest.raises(BreakerOpen) as refused:
        breaker.before()
    assert refused.value.retry_after_seconds == 10  # measured from the probe
    status = breaker.status()
    assert status.state == "open"
    assert status.last_failure_class == "outcome_unknown"  # the D2 class stays


def test_a_probe_that_raises_reopens_and_is_not_stuck(now):
    outcomes = [RuntimeError("boom"), True]

    def probe():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    breaker = _breaker(now, probe=probe)
    _open(breaker)
    now[0] = 10.0
    with pytest.raises(RuntimeError):
        breaker.before()
    assert breaker.status().state == "open"
    now[0] = 20.0
    breaker.before()  # probes again
    assert breaker.status().state == "closed"


# P6 ------------------------------------------------------------------------


def test_force_open_opens_immediately(now):
    breaker = _breaker(now)
    breaker.force_open(30)
    status = breaker.status()
    assert status.state == "open" and status.retry_after_seconds == 30
    assert status.consecutive_failures == 0
    with pytest.raises(BreakerOpen) as refused:
        breaker.before()
    assert refused.value.retry_after_seconds == 30


def test_a_force_open_during_a_probe_wins(now):
    holder = []

    def probe():
        holder[0].force_open(30)
        return True

    breaker = _breaker(now, probe=probe)
    holder.append(breaker)
    _open(breaker)
    now[0] = 10.0
    with pytest.raises(BreakerOpen):
        breaker.before()
    assert breaker.status().state == "open"


# P7 ------------------------------------------------------------------------


def test_status_is_a_frozen_plain_value(now, monkeypatch):
    breaker = _breaker(now)
    status = breaker.status()
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.state = "open"
    assert tuple(f.name for f in dataclasses.fields(BreakerStatus)) == (
        "state",
        "since",
        "consecutive_failures",
        "last_failure_class",
        "retry_after_seconds",
    )
    json.dumps(dataclasses.asdict(status))
    for value in dataclasses.astuple(status):
        assert value is None or type(value) in (str, int)
    assert status.retry_after_seconds is None
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", status.since)


def test_half_open_reports_one_second_and_since_changes(now, monkeypatch):
    from datetime import datetime, timezone

    stamps = iter(
        datetime(2026, 1, 1, 0, 0, s, tzinfo=timezone.utc) for s in range(1, 20)
    )
    monkeypatch.setattr(circuit_breaker, "_wall_clock", lambda: next(stamps))
    seen = {}

    def probe():
        seen["status"] = holder[0].status()
        return True

    holder = []
    breaker = _breaker(now, probe=probe)
    holder.append(breaker)
    constructed = breaker.status().since
    _open(breaker)
    opened = breaker.status().since
    assert opened != constructed
    now[0] = 10.0
    breaker.before()
    assert seen["status"].state == "half_open"
    assert seen["status"].retry_after_seconds == 1
    assert breaker.status().since not in (constructed, opened)


# P8 ------------------------------------------------------------------------


def test_the_constructor_is_the_contract_prd_022_relies_on():
    params = inspect.signature(CircuitBreaker).parameters
    assert params["failure_threshold"].default is inspect.Parameter.empty
    assert params["open_seconds"].default is inspect.Parameter.empty
    assert params["clock"].default is time.monotonic
    assert params["probe"].default is None


@pytest.mark.parametrize("threshold, seconds", [(0, 10.0), (3, 0)])
def test_invalid_arguments_name_the_breaker(threshold, seconds):
    with pytest.raises(ValueError, match="'provider-x'"):
        CircuitBreaker("provider-x", threshold, seconds)


# P9 ------------------------------------------------------------------------


def test_every_transition_logs_exactly_one_line(now, caplog):
    outcomes = [True, False]
    breaker = _breaker(now, probe=lambda: outcomes.pop(0))
    breaker.record_failure("not_sent")
    breaker.record_failure("not_sent")
    breaker.record_success()
    breaker.record_success()
    assert _lines(caplog) == []  # nothing below the threshold, no transition
    _open(breaker, failures=3)
    with pytest.raises(BreakerOpen):
        breaker.before()  # refused: no line
    now[0] = 10.0
    breaker.before()  # probe True: half_open then closed
    _open(breaker, failures=3)
    now[0] = 20.0
    with pytest.raises(BreakerOpen):
        breaker.before()  # probe False
    assert _lines(caplog) == [
        "breaker name=storage from=closed to=open class=not_sent",
        "breaker name=storage from=open to=half_open class=none",
        "breaker name=storage from=half_open to=closed class=none",
        "breaker name=storage from=closed to=open class=not_sent",
        "breaker name=storage from=open to=half_open class=none",
        "breaker name=storage from=half_open to=open class=probe",
    ]


def test_force_open_logs_only_when_the_state_changes(now, caplog):
    breaker = _breaker(now)
    breaker.force_open(5)
    breaker.force_open(5)
    assert _lines(caplog) == ["breaker name=storage from=closed to=open class=forced"]


# P10 -----------------------------------------------------------------------


def test_stragglers_do_not_extend_or_close_an_open_breaker(now, caplog):
    breaker = _breaker(now)
    _open(breaker)
    caplog.clear()
    now[0] = 4.0
    breaker.record_failure("dead_stream")
    breaker.record_success()
    assert _lines(caplog) == []
    status = breaker.status()
    assert status.state == "open"
    assert status.retry_after_seconds == 6  # still measured from the first open
    assert status.last_failure_class == "dead_stream"


# P11 -----------------------------------------------------------------------


@pytest.mark.parametrize("probe_result, final_state", [(True, "closed"), (False, "open")])
def test_exactly_one_caller_runs_the_probe_and_the_rest_are_refused(
    now, probe_result, final_state
):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def probe():
        calls.append(1)
        entered.set()
        assert release.wait(timeout=5)
        return probe_result

    breaker = _breaker(now, probe=probe)
    _open(breaker)
    now[0] = 10.0
    barrier = threading.Barrier(8, timeout=5)
    outcomes = []

    def caller():
        barrier.wait()
        try:
            breaker.before()
            outcomes.append("admitted")
        except BreakerOpen:
            outcomes.append("refused")

    threads = [threading.Thread(target=caller) for _ in range(8)]
    for t in threads:
        t.start()
    assert entered.wait(timeout=5)
    # While the probe is still blocked, the seven others finish at once.
    deadline = time.monotonic() + 5
    while len(outcomes) < 7 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert outcomes == ["refused"] * 7
    assert breaker.status().state == "half_open"  # status never blocks behind it
    release.set()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert calls == [1]
    assert sorted(outcomes) == ["admitted"] * (probe_result) + ["refused"] * (
        8 - probe_result
    )
    assert breaker.status().state == final_state


# P12 -----------------------------------------------------------------------


def _race_for_the_trial(breaker, count=8):
    barrier = threading.Barrier(count, timeout=5)
    outcomes = []

    def caller():
        barrier.wait()
        try:
            breaker.before()
            outcomes.append("admitted")
        except BreakerOpen:
            outcomes.append("refused")

    threads = [threading.Thread(target=caller) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    return outcomes


def test_without_a_probe_one_live_caller_is_the_trial(now):
    breaker = _breaker(now)
    _open(breaker)
    now[0] = 10.0
    outcomes = _race_for_the_trial(breaker)
    assert outcomes.count("admitted") == 1 and outcomes.count("refused") == 7
    with pytest.raises(BreakerOpen):
        breaker.before()  # still the trial's turn
    breaker.record_success()
    assert breaker.status().state == "closed"
    breaker.before()


def test_without_a_probe_a_failed_trial_reopens(now):
    breaker = _breaker(now)
    _open(breaker)
    now[0] = 10.0
    breaker.before()
    breaker.record_failure("x")
    status = breaker.status()
    assert status.state == "open" and status.last_failure_class == "x"
    with pytest.raises(BreakerOpen) as refused:
        breaker.before()
    assert refused.value.retry_after_seconds == 10


def test_without_a_probe_a_silent_trial_is_replaced_after_a_window(now):
    breaker = _breaker(now)
    _open(breaker)
    now[0] = 10.0
    breaker.before()  # the trial, which never reports
    now[0] = 19.9
    with pytest.raises(BreakerOpen):
        breaker.before()
    now[0] = 20.0
    breaker.before()  # lease expired: a new trial
    with pytest.raises(BreakerOpen):
        breaker.before()


# P13 -----------------------------------------------------------------------


def test_the_module_is_pure():
    source = Path(circuit_breaker.__file__).read_text(encoding="utf-8")
    allowed = {"logging", "math", "threading", "time", "dataclasses", "datetime", "typing"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert {a.name.split(".")[0] for a in node.names} <= allowed
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] in allowed
    # code, not prose: the docstring may say "settings" without importing any
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Attribute)}
    assert not ({"open", "socket", "settings"} & (names | attrs))


# --- PRD-018 STORY-012: the generic transition hook -----------------------------


def test_on_transition_gets_from_to_class_after_the_lock_is_released(now):
    seen = []

    def hook(frm, to, cls):
        # The lock is free here: a status() read would deadlock if it were held.
        seen.append((frm, to, cls, breaker.status().state))

    breaker = CircuitBreaker(
        "storage", 2, 10.0, clock=lambda: now[0], on_transition=hook
    )
    _open(breaker, failures=2)
    assert seen == [("closed", "open", "not_sent", "open")]


def test_a_raising_on_transition_hook_leaves_the_breaker_working(now, caplog):
    def hook(frm, to, cls):
        raise RuntimeError("hook bug")

    breaker = CircuitBreaker("storage", 2, 10.0, clock=lambda: now[0], on_transition=hook)
    with caplog.at_level(logging.ERROR, logger=_LOG):
        _open(breaker, failures=2)
    assert breaker.status().state == "open"
    with pytest.raises(BreakerOpen):
        breaker.before()
    assert any("on_transition hook failed" in r.getMessage() for r in caplog.records)


# --- PRD-022 STORY-010: additive provider-breaker support ------------------------


def test_half_open_refusal_carries_its_state(now):
    breaker = _breaker(now)
    _open(breaker)
    with pytest.raises(BreakerOpen) as opened:
        breaker.before()
    assert opened.value.state == "open"
    now[0] = 10.0
    breaker.before()  # the trial (probe=None)
    with pytest.raises(BreakerOpen) as busy:
        breaker.before()
    assert busy.value.state == "half_open"
    assert BreakerOpen("x", 1).state == "open"  # the PRD-018 default


def test_force_open_names_the_failure_class(now, caplog):
    breaker = _breaker(now)
    breaker.force_open(5, failure_class="misconfigured")
    assert _lines(caplog) == [
        "breaker name=storage from=closed to=open class=misconfigured"
    ]


def test_transition_log_level_overrides_and_the_default_is_unchanged(now, caplog):
    def levels(**kw):
        caplog.clear()
        breaker = CircuitBreaker("p", 1, 10.0, clock=lambda: now[0], **kw)
        breaker.record_failure("timeout")  # closed -> open
        now[0] += 10.0
        breaker.before()  # open -> half_open
        breaker.record_success()  # half_open -> closed
        return [r.levelno for r in caplog.records if r.name == _LOG]

    assert levels() == [logging.WARNING, logging.INFO, logging.INFO]
    assert levels(transition_log_level=logging.WARNING) == [logging.WARNING] * 3
