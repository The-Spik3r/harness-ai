"""PRD-018 STORY-011: the duplicate overlay over journaled rows (D12, Risk 6, T4, AC 1-3, 5).

`audit_journal.pending_duplicate` answers `find_duplicate_timestamp`'s question
over this process's journal. `check_duplicate` uses it only when the database
lookup succeeded and found nothing (a failed lookup still fails closed, a found
row wins). The journal predicate `_is_prior_query` is the SQL's WHERE clause
copied by hand, so the parity `db` test enumerates both sides mechanically
(Risk 6): the clause list parsed from the SQL must equal the shapes this file
knows, the predicate's operand count must equal the clause count, and a sweep
over every other `AuditLog` column catches an exclusion only one side has.

Orchestrator ruling R1 (applied in `check_duplicate`): the overlay is read
before the lookup and used only after it found nothing, so a row the drainer
commits after the lookup's read cannot be invisible to both.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import dataclasses
import inspect
import re
import textwrap
import typing
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.db import audit_journal, database, journal_drainer
from app.db.errors import StorageUnavailableError
from app.db.journal_drainer import DrainOutcome, drain_once
from app.db.models import AuditLog
from app.models.messages import Message
from app.models.schemas import QueryBlockedDuplicateResponse
from app.services import duplicate_checker, query_pipeline
from app.services.duplicate_checker import DuplicateCheckError, DuplicateCheckResult, check_duplicate
from app.services.identity import Identity

_TS = "2026-11-16T14:02:13Z"
_SINCE = "2026-11-16T00:00:00Z"
_USER = Identity("dana@overlay.test", "user")


def _audit(**overrides) -> AuditLog:
    base = dict(
        write_id=uuid.uuid4().hex, user_id="u1", dedup_key="k", timestamp=_TS,
        prompt_hash="h", success=True,
    )
    return AuditLog(**{**base, **overrides})


@pytest.fixture
def journal(tmp_path):
    """The module slot, open under `tmp_path` and always closed (the conftest fails a leak)."""
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 8 << 20, 2)
    yield opened
    audit_journal.close_journal()


def _lookup(monkeypatch, answer):
    """`find_duplicate_timestamp` as bound in duplicate_checker: an answer or an exception to raise."""

    def fake(user_id, key, since):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(duplicate_checker, "find_duplicate_timestamp", fake)


# --- the overlay's own answer ----------------------------------------------------


def test_pending_duplicate_is_none_without_an_open_journal():
    assert audit_journal.current() is None
    assert audit_journal.pending_duplicate("u1", "k", _SINCE) is None


def test_pending_duplicate_returns_the_earliest_qualifying_timestamp(journal):
    journal.append(_audit(timestamp="2026-11-16T15:00:00Z"))
    journal.append(_audit(timestamp="2026-11-16T14:02:13Z"))
    journal.append(_audit(timestamp="2026-11-16T13:00:00Z", success=False))  # earlier, excluded

    assert audit_journal.pending_duplicate("u1", "k", _SINCE) == "2026-11-16T14:02:13Z"
    assert audit_journal.pending_duplicate("u1", "other", _SINCE) is None


def test_mark_drained_removes_the_row_from_the_overlay(journal):
    row = _audit()
    journal.append(row)
    assert audit_journal.pending_duplicate("u1", "k", _SINCE) == _TS

    journal.mark_drained(row.write_id)

    assert audit_journal.pending_duplicate("u1", "k", _SINCE) is None  # AC 5


# --- check_duplicate -------------------------------------------------------------


def test_check_duplicate_holds_a_journaled_row_when_the_lookup_found_nothing(journal, monkeypatch):
    _lookup(monkeypatch, None)
    journal.append(_audit(timestamp=_TS))

    result = _check_with_since("u1", "k", monkeypatch)

    assert result == DuplicateCheckResult(is_duplicate=True, first_query_at=_TS)  # AC 1


def _check_with_since(user_id, key, monkeypatch):
    """`check_duplicate` with its 24-hour cutoff pinned before the fixture timestamps."""
    real = audit_journal.pending_duplicate
    monkeypatch.setattr(
        duplicate_checker.audit_journal, "pending_duplicate", lambda u, k, since: real(u, k, _SINCE)
    )
    return check_duplicate(user_id, key)


def test_the_pipeline_blocks_a_resend_held_only_by_the_journal(journal, monkeypatch):
    key = duplicate_checker.dedup_key(_USER.user_id, [Message("user", "hello")])
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    journal.append(_audit(user_id=_USER.user_id, dedup_key=key, timestamp=stamp))
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
    _lookup(monkeypatch, None)
    logged = []
    monkeypatch.setattr(query_pipeline, "log_query", lambda *a, **k: logged.append(k) or None)
    sent = []

    def upstream(*a, **k):
        sent.append(1)
        raise AssertionError("a duplicate must not reach the model")

    result = query_pipeline.run_conversation(
        identity=_USER, messages=[Message("user", "hello")], device=None, model="gpt-4",
        openrouter_api_key=None, call_openrouter=upstream,
    )

    blocked = result.response if hasattr(result, "response") else result
    assert isinstance(blocked, QueryBlockedDuplicateResponse)
    assert blocked.first_query_at == stamp
    assert sent == [] and len(logged) == 1


def test_a_failed_lookup_still_fails_closed_with_a_matching_journal_row(journal, monkeypatch):
    outage = StorageUnavailableError("down", 1)
    _lookup(monkeypatch, outage)
    journal.append(_audit())

    with pytest.raises(DuplicateCheckError) as raised:
        _check_with_since("u1", "k", monkeypatch)

    assert raised.value.__cause__ is outage  # AC 2: the overlay never stands in for the database


def test_the_database_answer_wins_when_the_lookup_found_a_row(journal, monkeypatch):
    _lookup(monkeypatch, "2026-11-16T10:00:00Z")
    journal.append(_audit(timestamp="2026-11-16T14:02:13Z"))

    result = _check_with_since("u1", "k", monkeypatch)

    assert result == DuplicateCheckResult(True, "2026-11-16T10:00:00Z")  # AC 2


def test_a_row_drained_between_the_overlay_read_and_the_lookup_is_still_held(journal, monkeypatch):
    # R1: the drainer commits and unindexes the row while the lookup is in
    # flight; the lookup's read predates the commit, so it answers None.
    row = _audit()
    journal.append(row)

    def racing_lookup(user_id, key, since):
        journal.mark_drained(row.write_id)
        return None

    monkeypatch.setattr(duplicate_checker, "find_duplicate_timestamp", racing_lookup)

    result = _check_with_since("u1", "k", monkeypatch)

    assert result.is_duplicate is True and result.first_query_at == _TS


def test_both_predicates_carry_a_cross_reference():
    assert "_is_prior_query" in inspect.getsource(database.find_duplicate_timestamp)
    comments = inspect.getcomments(audit_journal._is_prior_query)
    assert comments is not None and "find_duplicate_timestamp" in comments


# --- db: parity with the real SQL (Risk 6) ---------------------------------------


def _sql_clauses() -> list[str]:
    (sql,) = re.findall(r'"""(.*?)"""', inspect.getsource(database.find_duplicate_timestamp), re.S)
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    return [c.strip() for c in re.sub(r"\s+", " ", where).strip().split(" AND ")]


# clause -> (row overrides) for a row that violates exactly that clause.
_SHAPES = {
    "user_id = ?": {"user_id": "u2"},
    "dedup_key = ?": {"dedup_key": "OTHER"},
    "timestamp >= ?": {"timestamp": "2026-11-15T23:59:59Z"},
    "success = 1": {"success": False},
    "was_duplicate_blocked = 0": {"was_duplicate_blocked": True},
    "denied_permission IS NULL": {"denied_permission": "query:submit"},
    "(pattern_action IS NULL OR pattern_action <> 'flag')": {"pattern_action": "flag"},
    "limit_exceeded IS NULL": {"limit_exceeded": "daily_tokens"},
}
# Rows that match, or that look like they should not but do, on both sides.
_CONTROLS = [
    {},
    {"timestamp": _SINCE},  # the boundary is included
    {"pattern_action": "block"},
    {"pattern_action": None},
    {"denied_permission": ""},  # '' IS NULL is false: excluded on both sides
]
_SWEEP_SKIP = {"id", "write_id", "timestamp", "user_id", "dedup_key"}


def _sweep_cases() -> list[dict]:
    hints = typing.get_type_hints(AuditLog)
    cases = []
    for field in dataclasses.fields(AuditLog):
        if field.name in _SWEEP_SKIP:
            continue
        hint = hints[field.name]
        optional = type(None) in typing.get_args(hint)
        base = next((a for a in typing.get_args(hint) if a is not type(None)), hint)
        if base is bool:
            values = [True, False]
        elif base is str:
            values = ["", "flag", "block", "x"] + ([None] if optional else [])
        elif base is int:
            values = [0, 1] + ([None] if optional else [])
        else:
            pytest.fail(f"the field sweep has no rule for AuditLog.{field.name}: {hint}")
        cases += [{field.name: v} for v in values]
    return cases


def test_overlay_and_sql_agree_on_every_excluded_row_shape(temp_db, tmp_path):
    clauses = _sql_clauses()
    for clause in clauses:
        assert clause in _SHAPES, f"no shape for clause {clause!r}: add one here and to _is_prior_query"
    assert set(_SHAPES) == set(clauses)

    tree = ast.parse(textwrap.dedent(inspect.getsource(audit_journal._is_prior_query)))
    (ret,) = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
    assert isinstance(ret.value, ast.BoolOp) and isinstance(ret.value.op, ast.And)
    assert len(ret.value.values) == len(clauses), "operand count differs from the SQL's clause count"

    cases = [_SHAPES[c] for c in clauses] + _CONTROLS + _sweep_cases()
    audit_journal.open_journal(str(tmp_path / "buf"), 8 << 20, 2)
    mismatches = []
    try:
        for n, overrides in enumerate(cases):
            key = f"k-{n}"
            overrides = {k: (f"{key}-other" if v == "OTHER" else v) for k, v in overrides.items()}
            row = _audit(**{"user_id": "u1", "dedup_key": key, **overrides})
            database.insert_audit_log(row)
            audit_journal.append(dataclasses.replace(row, write_id=uuid.uuid4().hex))
            # The query is always (u1, key): a row for another user or key must not answer it.
            sql = database.find_duplicate_timestamp("u1", key, _SINCE)
            overlay = audit_journal.pending_duplicate("u1", key, _SINCE)
            if sql != overlay:
                mismatches.append((overrides, sql, overlay))
    finally:
        audit_journal.close_journal()

    assert mismatches == [], f"overlay and SQL disagree (case, sql, overlay): {mismatches}"


# --- db: a drained entry hands the resend to the database (AC 5) -----------------


def test_a_drained_entry_leaves_the_overlay_and_the_database_holds_the_resend(temp_db, tmp_path):
    journal_drainer._held_back.clear()
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    journal = audit_journal.open_journal(str(tmp_path / "buf"), 8 << 20, 2)
    try:
        journal.append(_audit(timestamp=stamp))
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert database.find_duplicate_timestamp("u1", "k", since) is None

        held = check_duplicate("u1", "k")
        assert held == DuplicateCheckResult(True, stamp)  # from the journal

        assert drain_once(journal) == DrainOutcome.DRAINED
        assert audit_journal.pending_duplicate("u1", "k", since) is None

        again = check_duplicate("u1", "k")
        assert again == DuplicateCheckResult(True, stamp)  # now from the database, original timestamp
        assert database.find_duplicate_timestamp("u1", "k", since) == stamp
    finally:
        audit_journal.close_journal()
        journal_drainer._held_back.clear()
