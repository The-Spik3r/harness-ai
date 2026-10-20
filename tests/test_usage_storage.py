"""usage_daily and its two statements (PRD-013 STORY-009, Section 6.5).

The counters only count and report here; no limit is compared (STORY-010).
Rollover is tested by writing an old `window_start` directly, never by sleeping.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.db import database
from app.db.database import (
    admit_usage,
    charge_usage,
    get_connection,
    get_user,
    init_db,
    insert_user,
)
from app.db.errors import MissingRelationError
from app.db.models import (
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_CHAT_MESSAGES_TABLE,
    CREATE_CHAT_SESSIONS_TABLE,
    CREATE_USERS_TABLE,
    UsageAdmission,
    User,
)

_COLUMNS = [
    # (name, pk position, default)
    ("user_id", 1, None),
    ("day", 2, None),
    ("requests", 0, "0"),
    ("input_tokens", 0, "0"),
    ("output_tokens", 0, "0"),
    ("unsplit_tokens", 0, "0"),
    ("window_start", 0, None),
    ("window_requests", 0, "0"),
]


def _db_clock() -> tuple[str, int]:
    with get_connection() as conn:
        day, minute = conn.execute(
            "SELECT date('now'), strftime('%s','now') / 60"
        ).fetchone()
    return day, minute


def _row(user_id: str, day: str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM usage_daily WHERE user_id = ? AND day = ?", (user_id, day)
        ).fetchone()


def _insert_row(user_id, day, requests, window_start, window_requests):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO usage_daily "
            "(user_id, day, requests, window_start, window_requests) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, day, requests, window_start, window_requests),
        )


# --- schema ---------------------------------------------------------------


def test_init_db_creates_usage_daily_with_its_columns(temp_db):
    """AC 2: the PRD 6.5 shape as built -- names in order, the composite key,
    NOT NULL everywhere, and the counter defaults."""
    with get_connection() as conn:
        info = list(conn.execute("PRAGMA table_info(usage_daily)"))

    assert [(r["name"], r["pk"], r["dflt_value"]) for r in info] == _COLUMNS
    assert all(r["notnull"] == 1 for r in info)


def test_init_db_is_idempotent_for_usage_daily(temp_db):
    admit_usage("dana")

    init_db()

    with get_connection() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM usage_daily").fetchone()
    assert count == 1  # the second boot neither failed nor recreated the table


def test_init_db_adds_usage_daily_to_a_pre_usage_database(uninitialized_db, db_connect):
    """A database from before STORY-009 has every other table; init_db() adds
    this one by CREATE and leaves the rest alone."""
    legacy = db_connect(uninitialized_db)
    legacy.execute(CREATE_AUDIT_LOGS_TABLE)
    legacy.execute(CREATE_USERS_TABLE)
    legacy.execute(CREATE_CHAT_SESSIONS_TABLE)
    legacy.execute(CREATE_CHAT_MESSAGES_TABLE)
    legacy.commit()
    insert_user(User(user_id="dana", role="user", token_hash="hash-dana"))

    init_db()

    with get_connection() as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "usage_daily" in tables
    assert get_user("dana").role == "user"


def test_init_db_creates_usage_daily_inside_the_one_bootstrap_session(
    uninitialized_db, monkeypatch
):
    """AC 2: the CREATE rides the same _session() block as the other tables,
    so init_db() still opens exactly one bootstrap connection after the probe."""
    sessions: list[list[str]] = []
    real_get_connection = database.get_connection

    class _Recording:
        def __init__(self, inner):
            self._inner = inner
            self.statements: list[str] = []
            sessions.append(self.statements)

        def execute(self, sql, *args):
            self.statements.append(sql)
            return self._inner.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

    monkeypatch.setattr(database, "get_connection", lambda: _Recording(real_get_connection()))

    init_db()

    holding = [s for s in sessions if any("usage_daily" in sql for sql in s)]
    assert len(holding) == 1
    assert any("CREATE TABLE IF NOT EXISTS audit_logs" in sql for sql in holding[0])


# --- RETURNING, pinned ----------------------------------------------------


def test_upsert_returning_yields_the_admission_row(temp_db):
    """AC 1, pinned: libsql==0.1.11 returns the RETURNING row on the insert
    path and the conflict path, with named columns. A driver bump that stops
    doing so fails here rather than in the gate."""
    with get_connection() as conn:
        first = conn.execute(database._ADMIT_USAGE_SQL, ("dana",)).fetchone()
        second = conn.execute(database._ADMIT_USAGE_SQL, ("dana",)).fetchone()

    assert first is not None and second is not None
    assert first.keys() == ["day", "window_start", "window_requests", "tokens_today"]
    assert first["window_requests"] == 1
    same_minute = second["window_start"] == first["window_start"]
    assert second["window_requests"] == (2 if same_minute else 1)
    assert second["tokens_today"] == 0


def test_admitted_row_persists_after_the_session(temp_db):
    admitted = admit_usage("dana")

    row = _row("dana", admitted.day)
    assert row is not None
    assert row["requests"] == 1


# --- admit ----------------------------------------------------------------


def test_admit_usage_counts_three_attempts_in_one_window(temp_db):
    """AC 3. The three calls almost always share a minute; if a boundary falls
    between them, the rollover rule is asserted over the returned windows
    instead -- never skipped."""
    day_before, minute_before = _db_clock()

    results = [admit_usage("dana") for _ in range(3)]

    _, minute_after = _db_clock()
    assert all(isinstance(r, UsageAdmission) for r in results)
    assert [r.tokens_today for r in results] == [0, 0, 0]
    assert all(r.day == day_before for r in results)
    assert all(isinstance(r.window_start, int) for r in results)
    assert all(minute_before <= r.window_start <= minute_after for r in results)

    windows = [r.window_start for r in results]
    if len(set(windows)) == 1:
        assert [r.window_requests for r in results] == [1, 2, 3]
    else:
        expected = [1]
        for previous, current in zip(windows, windows[1:]):
            expected.append(1 if current != previous else expected[-1] + 1)
        assert [r.window_requests for r in results] == expected

    assert _row("dana", day_before)["requests"] == 3


def test_admit_usage_resets_the_window_on_a_new_minute(temp_db):
    """AC 4: an earlier window_start restarts window_requests at 1, and the
    day's requests keep increasing."""
    day, minute = _db_clock()
    _insert_row("dana", day, requests=7, window_start=minute - 5, window_requests=9)

    first = admit_usage("dana")

    assert first.window_requests == 1
    assert first.window_start > minute - 5
    assert _row("dana", day)["requests"] == 8

    second = admit_usage("dana")
    if second.window_start == first.window_start:
        assert second.window_requests == 2
    assert _row("dana", day)["requests"] == 9


def test_admit_usage_is_per_user(temp_db):
    admit_usage("dana")
    admit_usage("dana")

    assert admit_usage("eli").window_requests == 1


def test_admit_usage_on_a_missing_table_raises_missing_relation(uninitialized_db):
    """No local try: _translated() maps the driver error, and the caller
    (STORY-010) decides that the gate fails closed."""
    with pytest.raises(MissingRelationError):
        admit_usage("dana")


# --- charge ---------------------------------------------------------------


def test_charge_usage_accumulates_into_tokens_today(temp_db):
    """AC 5: a split charge and an unsplit charge both count toward the day."""
    admitted = admit_usage("dana")

    assert charge_usage(
        "dana", admitted.day, input_tokens=120, output_tokens=30, unsplit_tokens=0
    ) is True
    assert charge_usage("dana", admitted.day, 0, 0, 150) is True

    assert admit_usage("dana").tokens_today == 300
    row = _row("dana", admitted.day)
    assert (row["input_tokens"], row["output_tokens"], row["unsplit_tokens"]) == (
        120,
        30,
        150,
    )


def test_charge_usage_charges_the_admitted_day_not_today(temp_db):
    """A request admitted before midnight is charged to the day it was
    admitted, whatever the clock says when the charge lands."""
    today = admit_usage("dana").day
    _insert_row("dana", "2000-01-01", requests=1, window_start=0, window_requests=1)

    assert charge_usage("dana", "2000-01-01", 10, 5, 0) is True

    old = _row("dana", "2000-01-01")
    assert (old["input_tokens"], old["output_tokens"]) == (10, 5)
    current = _row("dana", today)
    assert (current["input_tokens"], current["output_tokens"]) == (0, 0)


def test_charge_usage_without_a_row_returns_false_and_creates_none(temp_db):
    assert charge_usage("ghost", "2026-10-18", 1, 1, 1) is False

    with get_connection() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM usage_daily").fetchone()
    assert count == 0
