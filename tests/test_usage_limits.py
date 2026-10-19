"""usage_limits: limit resolution and the rate and budget checks (PRD-013 STORY-010).

Sections 6.5-6.7, F9, F11, T7/T8. The acceptance tests stub `admit_usage` and
`charge_usage` at this module's boundary, so "four calls in one minute" is
four calls in one fixed `window_start` and never races a real minute boundary.
One test at the end runs the real statements to prove the wiring.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import inspect
import logging
import re

import pytest

import app.services.usage_limits as usage_limits
from app.config import settings
from app.db.database import get_connection
from app.db.errors import StorageError
from app.db.models import UsageAdmission
from app.services.identity import Identity
from app.services.usage_limits import (
    Admission,
    UsageLimitError,
    UsageLimits,
    UsageRefusal,
    admit,
    charge,
    limits_for,
)

_LOGGER = "app.services.usage_limits"
_DAY = "2026-10-19"
# A fixed unix minute: 2025-02-19T21:20:00Z. Its window closes at 21:21:00Z.
_WINDOW_START = 29_000_000
_WINDOW_END = "2025-02-19T21:21:00Z"
_TIMESTAMP_RE = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"


def _records(caplog):
    return [r for r in caplog.records if r.name == _LOGGER]


def _limits(monkeypatch, *, rpm: str = "*=60", budget: str = "*=1000000") -> None:
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", rpm)
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", budget)


def _usage(window_requests=1, tokens_today=0, day=_DAY, window_start=_WINDOW_START):
    return UsageAdmission(
        day=day,
        window_start=window_start,
        window_requests=window_requests,
        tokens_today=tokens_today,
    )


def _returns(monkeypatch, usage: UsageAdmission) -> None:
    monkeypatch.setattr(usage_limits, "admit_usage", lambda user_id: usage)


@pytest.fixture
def counter(monkeypatch):
    """A fake admit_usage counting per user inside one fixed window."""
    counts: dict[str, int] = {}

    def fake_admit_usage(user_id):
        counts[user_id] = counts.get(user_id, 0) + 1
        return _usage(window_requests=counts[user_id])

    monkeypatch.setattr(usage_limits, "admit_usage", fake_admit_usage)
    return counts


@pytest.fixture
def charges(monkeypatch):
    """A fake charge_usage recording its arguments; it matches a row."""
    calls: list[tuple] = []

    def fake_charge_usage(*args):
        calls.append(args)
        return True

    monkeypatch.setattr(usage_limits, "charge_usage", fake_charge_usage)
    return calls


# --- AC 1: limits_for -----------------------------------------------------


@pytest.fixture
def role_maps(monkeypatch):
    _limits(
        monkeypatch,
        rpm="*=60,admin=120,analyst=30",
        budget="*=1000000,analyst=5000",
    )


def test_limits_for_override_wins_and_the_other_limit_resolves_by_role(role_maps):
    identity = Identity("u1", "analyst", requests_per_minute=7)

    assert limits_for(identity) == UsageLimits(
        token_budget_daily=5000, requests_per_minute=7
    )


def test_limits_for_budget_override_leaves_the_rate_on_the_role(role_maps):
    identity = Identity("u1", "analyst", token_budget_daily=9)

    assert limits_for(identity) == UsageLimits(
        token_budget_daily=9, requests_per_minute=30
    )


def test_limits_for_role_entry_without_override(role_maps):
    assert limits_for(Identity("u1", "analyst")) == UsageLimits(
        token_budget_daily=5000, requests_per_minute=30
    )


def test_limits_for_role_with_no_entry_gets_the_star_values(role_maps):
    assert limits_for(Identity("u1", "nobody")) == UsageLimits(
        token_budget_daily=1000000, requests_per_minute=60
    )


def test_limits_for_each_limit_falls_back_independently(role_maps):
    """`admin` has a rate entry but no budget entry: rate from the role, budget from `*`."""
    assert limits_for(Identity("u1", "admin")) == UsageLimits(
        token_budget_daily=1000000, requests_per_minute=120
    )


def test_limits_for_an_unlimited_role_entry_wins_over_star(monkeypatch):
    """`unlimited` parses to None; a `.get() or` lookup would fall through to `*`."""
    _limits(monkeypatch, rpm="*=60,admin=unlimited", budget="*=1000000,admin=unlimited")

    assert limits_for(Identity("u1", "admin")) == UsageLimits(
        token_budget_daily=None, requests_per_minute=None
    )


def test_limits_for_break_glass_resolves_through_the_admin_role(role_maps):
    """Section 6.6: no users row, so no override, and not exempt."""
    break_glass = Identity("admin", "admin", break_glass=True)

    assert limits_for(break_glass) == limits_for(Identity("someone", "admin"))
    assert limits_for(break_glass).requests_per_minute == 120


def test_limits_for_reads_settings_per_call(monkeypatch):
    _limits(monkeypatch, rpm="*=60")
    assert limits_for(Identity("u1", "user")).requests_per_minute == 60

    _limits(monkeypatch, rpm="*=5")
    assert limits_for(Identity("u1", "user")).requests_per_minute == 5


# --- AC 2: the rate -------------------------------------------------------


def test_admit_refuses_the_fourth_attempt_in_a_minute_at_a_limit_of_three(
    monkeypatch, counter
):
    _limits(monkeypatch, rpm="*=3")
    identity = Identity("u1", "user")

    results = [admit(identity, charges_budget=True) for _ in range(4)]

    assert [r.admitted for r in results] == [True, True, True, False]
    assert all(r.refusal is None for r in results[:3])
    assert results[3].refusal == UsageRefusal(
        limit="requests", maximum=3, actual=4, resets_at=_WINDOW_END
    )
    assert re.fullmatch(_TIMESTAMP_RE, results[3].refusal.resets_at)
    assert all(r.day == _DAY for r in results)


def test_admit_counts_per_user(monkeypatch, counter):
    _limits(monkeypatch, rpm="*=1")

    assert admit(Identity("u1", "user"), charges_budget=True).admitted
    assert admit(Identity("u2", "user"), charges_budget=True).admitted
    assert not admit(Identity("u1", "user"), charges_budget=True).admitted


def test_admit_rate_uses_the_identitys_override(monkeypatch, counter):
    _limits(monkeypatch, rpm="*=60")
    identity = Identity("u1", "user", requests_per_minute=1)

    assert admit(identity, charges_budget=True).admitted
    assert admit(identity, charges_budget=True).refusal.maximum == 1


# --- AC 3: the budget -----------------------------------------------------


@pytest.mark.parametrize("tokens_today", [100, 101])
def test_admit_refuses_at_or_above_the_budget(monkeypatch, tokens_today):
    _limits(monkeypatch, budget="*=100")
    _returns(monkeypatch, _usage(tokens_today=tokens_today))

    result = admit(Identity("u1", "user"), charges_budget=True)

    assert result.refusal == UsageRefusal(
        limit="tokens",
        maximum=100,
        actual=tokens_today,
        resets_at="2026-10-20T00:00:00Z",
    )
    assert result.day == _DAY


def test_admit_budget_resets_at_the_next_month_across_a_month_end(monkeypatch):
    _limits(monkeypatch, budget="*=100")
    _returns(monkeypatch, _usage(tokens_today=100, day="2026-10-31"))

    result = admit(Identity("u1", "user"), charges_budget=True)

    assert result.refusal.resets_at == "2026-11-01T00:00:00Z"


def test_admit_budget_resets_across_a_year_end(monkeypatch):
    _limits(monkeypatch, budget="*=100")
    _returns(monkeypatch, _usage(tokens_today=100, day="2026-12-31"))

    assert admit(Identity("u1", "user"), charges_budget=True).refusal.resets_at == (
        "2027-01-01T00:00:00Z"
    )


def test_admit_below_the_budget_is_admitted(monkeypatch):
    _limits(monkeypatch, budget="*=100")
    _returns(monkeypatch, _usage(tokens_today=99))

    assert admit(Identity("u1", "user"), charges_budget=True).admitted


def test_admit_skips_the_budget_when_it_does_not_charge_it(monkeypatch):
    """BYOK (Decision D8): rate-limited, not budget-checked."""
    _limits(monkeypatch, budget="*=100")
    _returns(monkeypatch, _usage(tokens_today=10_000))

    result = admit(Identity("u1", "user"), charges_budget=False)

    assert result == Admission(day=_DAY)
    assert result.admitted


def test_admit_without_charging_the_budget_is_still_rate_limited(monkeypatch):
    _limits(monkeypatch, rpm="*=3", budget="*=100")
    _returns(monkeypatch, _usage(window_requests=4, tokens_today=10_000))

    result = admit(Identity("u1", "user"), charges_budget=False)

    assert result.refusal.limit == "requests"


# --- AC 4: precedence and unlimited --------------------------------------


def test_admit_reports_the_rate_when_both_limits_are_broken(monkeypatch):
    _limits(monkeypatch, rpm="*=3", budget="*=100")
    _returns(monkeypatch, _usage(window_requests=4, tokens_today=500))

    result = admit(Identity("u1", "user"), charges_budget=True)

    assert result.refusal.limit == "requests"
    assert result.refusal.maximum == 3
    assert result.refusal.actual == 4


def test_an_unlimited_rate_never_refuses(monkeypatch):
    _limits(monkeypatch, rpm="*=unlimited")
    _returns(monkeypatch, _usage(window_requests=10_000))

    assert admit(Identity("u1", "user"), charges_budget=True).admitted


def test_an_unlimited_budget_never_refuses(monkeypatch):
    _limits(monkeypatch, budget="*=unlimited")
    _returns(monkeypatch, _usage(tokens_today=10**12))

    assert admit(Identity("u1", "user"), charges_budget=True).admitted


# --- AC 5: failure rules --------------------------------------------------


def test_admit_fails_closed_on_a_storage_error(monkeypatch):
    error = StorageError("boom")

    def failing(user_id):
        raise error

    monkeypatch.setattr(usage_limits, "admit_usage", failing)

    with pytest.raises(UsageLimitError) as raised:
        admit(Identity("u1", "user"), charges_budget=True)

    assert raised.value.__cause__ is error


def test_charge_fails_open_and_logs_at_error_on_a_storage_error(monkeypatch, caplog):
    def failing(*args):
        raise StorageError("boom")

    monkeypatch.setattr(usage_limits, "charge_usage", failing)

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        assert charge("u1", _DAY, 10, 20, 30) is None

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    message = records[0].getMessage()
    for expected in ("user_id=u1", f"day={_DAY}", "input_tokens=10", "output_tokens=20",
                     "total_tokens=30", "boom"):
        assert expected in message


def test_charge_logs_at_error_when_no_row_matched(monkeypatch, caplog):
    monkeypatch.setattr(usage_limits, "charge_usage", lambda *args: False)

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        assert charge("u1", _DAY, None, None, 30) is None

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert "user_id=u1" in records[0].getMessage()
    assert f"day={_DAY}" in records[0].getMessage()


def test_a_successful_charge_logs_nothing(charges, caplog):
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        charge("u1", _DAY, 10, 20, 30)

    assert _records(caplog) == []


def test_charge_does_not_swallow_errors_that_are_not_storage_errors(monkeypatch):
    def broken(*args):
        raise TypeError("a bug")

    monkeypatch.setattr(usage_limits, "charge_usage", broken)

    with pytest.raises(TypeError):
        charge("u1", _DAY, 10, 20, 30)


# --- F11: charge routing --------------------------------------------------


def test_charge_charges_the_split_when_present(charges):
    charge("u1", _DAY, 10, 20, 30)

    assert charges == [("u1", _DAY, 10, 20, 0)]


def test_charge_charges_total_to_unsplit_without_a_split(charges):
    charge("u1", _DAY, None, None, 30)

    assert charges == [("u1", _DAY, 0, 0, 30)]


@pytest.mark.parametrize("split", [(10, None), (None, 20)])
def test_charge_treats_half_a_split_as_no_split(charges, split):
    charge("u1", _DAY, *split, 30)

    assert charges == [("u1", _DAY, 0, 0, 30)]


# --- shape and boundary ---------------------------------------------------


def test_admission_and_refusal_are_frozen():
    admitted = Admission(day=_DAY)
    refusal = UsageRefusal("requests", 3, 4, _WINDOW_END)

    with pytest.raises(dataclasses.FrozenInstanceError):
        admitted.day = "2026-10-20"
    with pytest.raises(dataclasses.FrozenInstanceError):
        refusal.actual = 5
    assert admitted.admitted is True
    assert Admission(day=_DAY, refusal=refusal).admitted is False


def test_the_module_does_not_read_the_master_switch():
    """The pipeline decides whether to call this module (STORY-011). The
    docstring names the switch to say so; no code reads it."""
    assert "settings.USAGE_LIMITS_ENABLED" not in inspect.getsource(usage_limits)


def test_resets_at_never_reads_the_instance_clock():
    """resets_at comes from the database's window_start and day (Section 6.7)."""
    source = inspect.getsource(usage_limits)
    assert "datetime.now" not in source
    assert "utcnow" not in source


# --- real storage ---------------------------------------------------------


def _row(user_id: str, day: str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM usage_daily WHERE user_id = ? AND day = ?", (user_id, day)
        ).fetchone()


def test_admit_and_charge_against_the_real_statements(temp_db, monkeypatch):
    """Wiring: admit counts a row on the database's day, charge routes the split
    and the unsplit total to the right columns, and the next admit's budget
    check sees all three summed. Nothing here depends on the minute."""
    _limits(monkeypatch, rpm="*=1000", budget="*=16")
    identity = Identity("real-user", "user")
    with get_connection() as conn:
        (db_day,) = conn.execute("SELECT date('now')").fetchone()

    first = admit(identity, charges_budget=True)
    assert first.admitted
    assert first.day == db_day

    charge("real-user", first.day, 5, 7, 12)
    charge("real-user", first.day, None, None, 4)

    row = _row("real-user", first.day)
    assert (row["input_tokens"], row["output_tokens"], row["unsplit_tokens"]) == (5, 7, 4)
    assert row["requests"] == 1

    second = admit(identity, charges_budget=True)
    if second.day == first.day:  # not across midnight UTC
        assert second.refusal == UsageRefusal(
            limit="tokens",
            maximum=16,
            actual=16,
            resets_at=usage_limits._next_utc_midnight(first.day),
        )
