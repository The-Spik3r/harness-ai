"""The admin console's Usage table (PRD-013 STORY-016, Sections 6.10 and F16).

Four layers, tested in the order the data travels:

1. **Storage.** `usage_snapshot()` reads today's `usage_daily` rows in one
   statement, keeps the break-glass `admin` (no `users` row), and counts only
   today's audit rows with `limit_exceeded` set.
2. **Formatting.** `to_usage_rows()` resolves each budget with
   `usage_limits.limits_for`, the gate's own function, so the table and the gate
   cannot disagree. The unlimited row shows no share.
3. **State.** The usage read is separate from the summary read: it fails under
   its own label, leaves the Register and summary standing, and `sign_out()`
   clears it.
4. **Component.** One plain table with a stated window: no chart, no history
   control, no per-row action.

"Today" is always the database's clock, so the tests read it back from the
database (`_db_clock`) rather than from Python, the `test_usage_storage.py`
rule. Old days are written directly, never waited for.
"""

import ast
import asyncio
import inspect
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

# Repo root, not chat_ui/ -- the test_admin_state.py rule.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.config import settings
from app.db import database
from app.db.database import (
    admit_usage,
    get_connection,
    insert_audit_log,
    insert_user,
    set_user_limits,
    usage_snapshot,
)
from app.db.models import AuditLog, UsageDay, User

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _db_clock() -> tuple[str, str]:
    """Today and yesterday, by the database's clock."""
    with get_connection() as conn:
        today, yesterday = conn.execute(
            "SELECT date('now'), date('now', '-1 day')"
        ).fetchone()
    return today, yesterday


def _insert_day(
    user_id: str,
    day: str,
    requests: int = 1,
    input_tokens: int = 0,
    output_tokens: int = 0,
    unsplit_tokens: int = 0,
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO usage_daily (user_id, day, requests, input_tokens, "
            "output_tokens, unsplit_tokens, window_start, window_requests) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
            (user_id, day, requests, input_tokens, output_tokens, unsplit_tokens),
        )


def _audit(user_id: str, day: str, limit_exceeded, clock: str = "12:00:00") -> None:
    """One audit row stamped on `day`, in the writer's own timestamp format."""
    insert_audit_log(
        AuditLog(
            timestamp=f"{day}T{clock}Z",
            user_id=user_id,
            prompt_hash="h",
            success=True,
            limit_exceeded=limit_exceeded,
        )
    )


class _RecordingConnection:
    """Counts the statements that reach the database, and delegates the rest.

    Copied from `tests/test_db.py:_RecordingConnection` rather than imported:
    test modules do not import each other's helpers.
    """

    def __init__(self, conn, statements):
        self._conn = conn
        self._statements = statements

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, sql, *parameters):
        self._statements.append(sql)
        return self._conn.execute(sql, *parameters)

    def cursor(self):
        return self._conn.cursor()


def _count_statements(monkeypatch) -> list:
    statements: list = []
    real_get_connection = database.get_connection
    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: _RecordingConnection(real_get_connection(), statements),
    )
    return statements


# --------------------------------------------------------------------------
# 1. Storage: usage_snapshot()
# --------------------------------------------------------------------------


def test_usage_snapshot_is_empty_when_nobody_sent_today(temp_db):
    _today, yesterday = _db_clock()
    _insert_day("ana", yesterday, requests=9)

    assert usage_snapshot() == []


def test_usage_snapshot_reads_todays_counters_and_overrides(temp_db):
    today, yesterday = _db_clock()
    insert_user(User(user_id="ana", role="user", token_hash="h-ana"))
    insert_user(User(user_id="bob", role="analyst", token_hash="h-bob"))
    set_user_limits("bob", token_budget_daily=2_000_000, requests_per_minute=7)
    _insert_day("ana", today, requests=3, input_tokens=2140, output_tokens=312)
    _insert_day("bob", today, requests=1, unsplit_tokens=88)
    _insert_day("ana", yesterday, requests=50, input_tokens=99_999)

    assert usage_snapshot() == [
        UsageDay(
            user_id="ana",
            role="user",
            token_budget_daily=None,
            requests_per_minute=None,
            requests=3,
            input_tokens=2140,
            output_tokens=312,
            unsplit_tokens=0,
            denied=0,
        ),
        UsageDay(
            user_id="bob",
            role="analyst",
            token_budget_daily=2_000_000,
            requests_per_minute=7,
            requests=1,
            input_tokens=0,
            output_tokens=0,
            unsplit_tokens=88,
            denied=0,
        ),
    ]


def test_usage_snapshot_keeps_the_break_glass_admin(temp_db):
    """The break-glass identity has no users row and is still counted
    (Section 6.6), so the LEFT JOIN must keep it, with no role from SQL."""
    admit_usage("admin")

    (day,) = usage_snapshot()

    assert day.user_id == "admin"
    assert day.role is None
    assert day.token_budget_daily is None
    assert day.requests == 1


def test_usage_snapshot_counts_todays_limit_rows_only(temp_db):
    today, yesterday = _db_clock()
    _insert_day("ana", today)
    _insert_day("cleo", today)
    _audit("ana", today, "tokens", clock="00:00:00")
    _audit("ana", today, "requests", clock="23:59:59")
    _audit("ana", today, None)
    _audit("ana", yesterday, "tokens", clock="23:59:59")
    _audit("bob", today, "tokens")  # no usage row today: not a row of the table

    by_user = {day.user_id: day for day in usage_snapshot()}

    assert set(by_user) == {"ana", "cleo"}
    assert by_user["ana"].denied == 2
    assert by_user["cleo"].denied == 0


def test_usage_snapshot_issues_one_statement(temp_db, monkeypatch):
    """AC 5: one statement, however many users and denials there are."""
    today, _ = _db_clock()
    for user in ("ana", "bob", "cleo"):
        _insert_day(user, today)
        _audit(user, today, "tokens")

    statements = _count_statements(monkeypatch)
    rows = usage_snapshot()

    assert statements, "the proxy captured nothing -- the patch did not take"
    assert len(statements) == 1, statements
    assert len(rows) == 3


def test_usage_snapshot_shares_the_stats_predicate():
    """The same rows /stats counts as `blocked_usage_limits` and the Register
    shows as denied -- interpolated, not retyped."""
    assert database._BLOCKED_USAGE_LIMITS_WHERE in database._USAGE_SNAPSHOT_SQL
    assert "?" not in database._USAGE_SNAPSHOT_SQL


# --------------------------------------------------------------------------
# 2. Formatting: to_usage_rows()
# --------------------------------------------------------------------------

from app.services.identity import Identity, resolve
from app.services.usage_limits import limits_for
from chat_ui.chat_ui.admin_copy import USAGE_BUDGET_UNLIMITED
from chat_ui.chat_ui.admin_formatting import (
    VALUE_ABSENT,
    format_count,
    to_usage_rows,
)
from chat_ui.chat_ui.admin_models import UsageRow


def _day(user_id="ana", role="user", budget=None, rpm=None, *, requests=1,
         input_tokens=0, output_tokens=0, unsplit_tokens=0, denied=0) -> UsageDay:
    return UsageDay(
        user_id=user_id,
        role=role,
        token_budget_daily=budget,
        requests_per_minute=rpm,
        requests=requests,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        unsplit_tokens=unsplit_tokens,
        denied=denied,
    )


@pytest.fixture
def budgets(monkeypatch):
    """`*` limited, `analyst` lower, `admin` unlimited -- the three AC 2 cases."""
    monkeypatch.setattr(
        settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1000000,analyst=5000,admin=unlimited"
    )
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=60")


def test_effective_budget_override_role_default_and_unlimited(budgets):
    """AC 2: each row shows its effective budget, and the unlimited row shows
    no share."""
    rows = to_usage_rows(
        [
            _day("admin", role=None, input_tokens=10),
            _day("ana", role="user", budget=2_000_000, input_tokens=10),
            _day("bob", role="analyst", input_tokens=10),
        ]
    )
    by_user = {row.user_id: row for row in rows}

    assert by_user["ana"].budget == "2,000,000"  # per-user override
    assert by_user["bob"].budget == "5,000"  # role default
    assert by_user["admin"].role == "admin"  # break-glass, no users row
    assert by_user["admin"].budget == USAGE_BUDGET_UNLIMITED
    assert by_user["admin"].used == VALUE_ABSENT
    assert not any("%" in value for value in by_user["admin"].model_dump().values())


def test_the_table_and_the_gate_agree(budgets, monkeypatch):
    """The budget shown is `limits_for` of the identity `resolve()` builds --
    for the break-glass token, resolve() itself."""
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "the-break-glass-token")
    cases = [
        (_day("admin", role=None), resolve("the-break-glass-token")),
        (
            _day("ana", role="user", budget=7_000),
            Identity("ana", "user", token_budget_daily=7_000),
        ),
        (_day("bob", role="analyst"), Identity("bob", "analyst")),
        (_day("cleo", role="user"), Identity("cleo", "user")),
    ]

    for day, identity in cases:
        (row,) = to_usage_rows([day])
        expected = limits_for(identity).token_budget_daily
        assert row.budget == (
            USAGE_BUDGET_UNLIMITED if expected is None else format_count(expected)
        ), day.user_id


def test_used_counts_unsplit_tokens(budgets):
    """Used is the gate's tokens_today: input + output + unsplit."""
    (row,) = to_usage_rows(
        [_day(budget=1000, input_tokens=300, output_tokens=100, unsplit_tokens=600)]
    )

    assert row.used == "100.0%"
    assert row.input_tokens == "300"
    assert row.output_tokens == "100"


def test_used_over_budget_is_a_number_not_a_colour(budgets):
    (row,) = to_usage_rows([_day(budget=1000, input_tokens=1042)])

    assert row.used == "104.2%"


def test_rows_are_ordered_by_share_then_unlimited_then_user(budgets):
    """Highest share first; ties keep usage_snapshot()'s user_id order; every
    unlimited row last."""
    rows = to_usage_rows(
        [
            _day("admin", role=None, input_tokens=999_999),
            _day("ana", budget=1000, input_tokens=100),
            _day("bob", budget=1000, input_tokens=900),
            _day("cleo", budget=1000, input_tokens=900),
        ]
    )

    assert [row.user_id for row in rows] == ["bob", "cleo", "ana", "admin"]
    assert [row.used for row in rows] == ["90.0%", "90.0%", "10.0%", VALUE_ABSENT]


def test_an_orphan_row_shows_the_absent_role(budgets):
    """No users row and not the break-glass id: the role is not invented, and
    the budget resolves through `*`."""
    (row,) = to_usage_rows([_day("ghost", role=None)])

    assert row.role == VALUE_ABSENT
    assert row.budget == "1,000,000"


def test_every_usage_row_field_is_a_string(budgets):
    (row,) = to_usage_rows([_day(denied=3, requests=1234)])

    assert isinstance(row, UsageRow)
    assert all(isinstance(value, str) for value in row.model_dump().values())
    assert row.requests == "1,234"
    assert row.denied == "3"


def test_zero_counts_read_zero(budgets):
    """Nothing used is a fact, not an absence."""
    (row,) = to_usage_rows([_day(requests=0)])

    assert (row.requests, row.input_tokens, row.output_tokens, row.denied) == (
        "0",
        "0",
        "0",
        "0",
    )
    assert row.used == "0.0%"


# --------------------------------------------------------------------------
# 3. State: the separate read
# --------------------------------------------------------------------------

import chat_ui.chat_ui.admin_state as admin_state_mod
from app.db.database import SUMMARY_FIGURES, SummarySnapshot
from app.db.errors import StorageError
from chat_ui.chat_ui.admin_copy import READ_LABEL_USAGE
from chat_ui.chat_ui.admin_state import (
    REGISTER_STATE_FAULT,
    SUMMARY_STATE_FAULT,
    USAGE_STATE_EMPTY,
    USAGE_STATE_FAULT,
    USAGE_STATE_ROWS,
    AdminState,
)

_TOKEN = "usage-view-token"


def _figures() -> dict:
    """All thirteen summary figures, as summary_snapshot() returns them."""
    figures = {name: 0 for name in SUMMARY_FIGURES}
    figures.update(
        rows=[
            AuditLog(
                id=1,
                timestamp="2026-10-19T12:00:00Z",
                user_id="ana",
                prompt_hash="h1",
                tokens_used=10,
            )
        ],
        total_recorded=1,
        successful_queries=1,
        unique_users=1,
        top_models=[],
        top_users=["ana"],
        top_pii_entities=[],
    )
    return figures


class _Console:
    """The two reads `load()` makes, replaced: `summary_snapshot` and
    `usage_snapshot`. Each can be told to raise, and each counts its calls."""

    def __init__(self, monkeypatch):
        self.usage = []
        self.usage_raises = None
        self.summary_raises = None
        self.usage_calls = 0
        monkeypatch.setattr(settings, "ADMIN_TOKEN", _TOKEN)
        monkeypatch.setattr(
            settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1000000,admin=unlimited"
        )
        monkeypatch.setattr(admin_state_mod, "summary_snapshot", self._summary)
        monkeypatch.setattr(admin_state_mod, "usage_snapshot", self._usage)

    def _summary(self, row_limit, ranked_limit):
        if self.summary_raises is not None:
            raise self.summary_raises
        return SummarySnapshot(figures=_figures(), errors={})

    def _usage(self):
        self.usage_calls += 1
        if self.usage_raises is not None:
            raise self.usage_raises
        return list(self.usage)


def _signed_in() -> AdminState:
    state = AdminState(_reflex_internal_init=True)
    state.token_input = _TOKEN
    type(state).event_handlers["authenticate"].fn(state)
    assert state.authenticated
    return state


def _load(state: AdminState) -> None:
    asyncio.run(type(state).event_handlers["load"].fn(state))


def _record(state: AdminState) -> dict:
    """What the Register and summary show, for an untouched-ness check."""
    return {
        "rows": list(state.rows),
        "total_recorded": state.total_recorded,
        "unique_users": state.unique_users,
        "top_users": list(state.top_users),
        "last_refreshed": state.last_refreshed,
    }


def test_load_commits_usage_rows(monkeypatch):
    """AC 1: one row per user active today, formatted, in share order."""
    console = _Console(monkeypatch)
    console.usage = [
        _day("ana", input_tokens=100),
        _day("bob", input_tokens=900_000),
    ]
    state = _signed_in()

    _load(state)

    assert [row.user_id for row in state.usage_rows] == ["bob", "ana"]
    assert all(isinstance(row, UsageRow) for row in state.usage_rows)
    assert state.usage_rows[0].used == "90.0%"
    assert state.usage_error == ""
    assert state.usage_state == USAGE_STATE_ROWS


def test_empty_day_is_the_empty_state(monkeypatch):
    """AC 3: nobody today is the empty state, not an empty grid."""
    _Console(monkeypatch)
    state = _signed_in()

    _load(state)

    assert state.usage_rows == []
    assert state.usage_state == USAGE_STATE_EMPTY


def test_a_failed_usage_read_names_itself_and_leaves_the_record(monkeypatch):
    """AC 4: the failure is named under its own label; the Register and summary
    are untouched and do not enter their fault states; the last good usage rows
    stay standing under the fault."""
    console = _Console(monkeypatch)
    console.usage = [_day("ana", input_tokens=10)]
    state = _signed_in()
    _load(state)
    before = _record(state)
    usage_before = list(state.usage_rows)

    console.usage_raises = StorageError("boom")
    _load(state)

    assert READ_LABEL_USAGE in state.usage_error
    assert "boom" in state.usage_error
    assert state.error == ""
    assert state.register_state != REGISTER_STATE_FAULT
    assert state.summary_state != SUMMARY_STATE_FAULT
    assert state.usage_rows == usage_before
    assert state.usage_state == USAGE_STATE_FAULT
    after = _record(state)
    after.pop("last_refreshed")
    before.pop("last_refreshed")
    assert after == before


def test_a_failed_summary_read_still_refreshes_usage(monkeypatch):
    """The reads are independent in both directions: the usage read runs first,
    so the summary's early return cannot skip it."""
    console = _Console(monkeypatch)
    console.summary_raises = StorageError("summary down")
    console.usage = [_day("ana")]
    state = _signed_in()

    _load(state)

    assert state.error
    assert READ_LABEL_USAGE not in state.error
    assert state.usage_error == ""
    assert [row.user_id for row in state.usage_rows] == ["ana"]


def test_a_first_failed_usage_read_is_not_shown_as_empty(monkeypatch):
    """A failed read is never presented as "No one has sent anything today."""
    console = _Console(monkeypatch)
    console.usage_raises = StorageError("boom")
    state = _signed_in()

    _load(state)

    assert state.usage_rows == []
    assert state.usage_state == USAGE_STATE_FAULT


def test_a_recovered_usage_read_clears_its_fault(monkeypatch):
    console = _Console(monkeypatch)
    console.usage_raises = StorageError("boom")
    state = _signed_in()
    _load(state)

    console.usage_raises = None
    console.usage = [_day("ana")]
    _load(state)

    assert state.usage_error == ""
    assert state.usage_state == USAGE_STATE_ROWS


def test_sign_out_clears_the_usage_rows(monkeypatch):
    """AC 4: the usage rows go with the session, like the rest of the record."""
    console = _Console(monkeypatch)
    console.usage = [_day("ana")]
    state = _signed_in()
    _load(state)
    state.usage_error = "a standing fault"
    assert state.usage_rows

    type(state).event_handlers["sign_out"].fn(state)

    assert state.usage_rows == []
    assert state.usage_error == ""


def test_an_unauthenticated_load_reads_no_usage(monkeypatch):
    """PRD-006 Risk 1: the read is gated, not just the view."""
    console = _Console(monkeypatch)
    state = AdminState(_reflex_internal_init=True)

    _load(state)

    assert console.usage_calls == 0
    assert state.usage_rows == []


def test_usage_is_not_a_summary_read():
    """F16: a separate read with its own label, so `_READS` and
    `SUMMARY_FIGURES` stay one-to-one and the summary never carries it."""
    fields = {field for field, *_ in admin_state_mod._READS}
    labels = {label for _, label, *_ in admin_state_mod._READS}

    assert not {"usage", "usage_rows"} & fields
    assert READ_LABEL_USAGE not in labels
    assert len(admin_state_mod._READS) == len(SUMMARY_FIGURES)


def test_the_usage_vars_are_declared_and_the_state_is_computed():
    assert "usage_rows" in AdminState.base_vars
    assert "usage_error" in AdminState.base_vars
    assert "usage_state" not in AdminState.base_vars


# --------------------------------------------------------------------------
# 4. Component: components/usage.py
# --------------------------------------------------------------------------
# The build probe runs in a subprocess with PYTHONPATH set to chat_ui/, which is
# how Reflex imports the app -- the `tests/test_summary.py` reason: doing it
# in-process would put the inner package on sys.path and break other modules.

import json
import subprocess

from chat_ui.chat_ui import admin_copy, theme

REPO_ROOT = Path(__file__).resolve().parents[1]
USAGE_SOURCE_PATH = REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "usage.py"

# Every string the view itself puts on screen.
USAGE_COPY_NAMES = (
    "USAGE_CAPTION",
    "COLUMN_USER",
    "COLUMN_ROLE",
    "COLUMN_REQUESTS",
    "COLUMN_INPUT",
    "COLUMN_OUTPUT",
    "COLUMN_BUDGET",
    "COLUMN_USED",
    "COLUMN_DENIED",
    "COLUMN_BUDGET_TITLE",
    "COLUMN_USED_TITLE",
    "COLUMN_DENIED_TITLE",
    "EMPTY_USAGE_TITLE",
    "EMPTY_USAGE_BODY",
)

# The ground tokens: the only colours this view may paint (no verdict ink, no
# tint -- a share is not a verdict).
ALLOWED_COLOURS = {
    token.upper()
    for token in (
        theme.PAPER,
        theme.CARD,
        theme.INK,
        theme.MUTE,
        theme.RULE,
        theme.RULE_SOFT,
    )
}
COLOUR_REFERENCE = re.compile(r"var\(--hx-[a-z0-9-]+\)")

_PROBE = r"""
import json, sys

try:
    import reflex as rx
    from chat_ui.admin_state import AdminState
    from chat_ui.components.usage import (
        usage, _table, _row, _empty_usage, _column_head, _caption, _usage_body,
    )
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

result = {"errors": []}
result["chat_modules_loaded"] = [
    name for name in ("chat_ui.components.chat", "chat_ui.components.bubbles")
    if name in sys.modules
]
factories = {
    "usage": lambda: usage(),
    "table": lambda: _table(),
    "rows": lambda: rx.box(rx.foreach(AdminState.usage_rows, _row)),
    "empty": lambda: _empty_usage(),
    "head": lambda: _column_head(),
    "caption": lambda: _caption(),
    "body": lambda: _usage_body(),
}
for name, factory in factories.items():
    try:
        result[name] = str(factory())
    except Exception as exc:
        result["errors"].append("{} ({}: {})".format(name, type(exc).__name__, exc))
print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"usage probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def usage_source() -> str:
    return USAGE_SOURCE_PATH.read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """The module with every docstring and comment removed, so a guard over it
    tests what the code does, not what the prose says it refuses."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0] = ast.Pass()
    return ast.unparse(tree)


def test_usage_view_builds(probe):
    assert not probe["errors"], probe["errors"]
    assert probe["chat_modules_loaded"] == []


def test_usage_renders_every_column_head_and_the_caption(probe):
    """AC 1: the eight columns and the stated window."""
    assert not probe["errors"], probe["errors"]
    for name in (
        "COLUMN_USER",
        "COLUMN_ROLE",
        "COLUMN_REQUESTS",
        "COLUMN_INPUT",
        "COLUMN_OUTPUT",
        "COLUMN_BUDGET",
        "COLUMN_USED",
        "COLUMN_DENIED",
        "COLUMN_BUDGET_TITLE",
        "COLUMN_USED_TITLE",
        "COLUMN_DENIED_TITLE",
    ):
        assert getattr(admin_copy, name) in probe["head"], name
    assert admin_copy.USAGE_CAPTION in probe["caption"]
    # The window is also the table's accessible name.
    assert admin_copy.USAGE_CAPTION in probe["table"]
    for field in (
        "user_id",
        "role",
        "requests",
        "input_tokens",
        "output_tokens",
        "budget",
        "used",
        "denied",
    ):
        assert field in probe["rows"], field


def test_the_empty_state_says_no_one_has_sent_anything_today(probe, usage_source):
    """AC 3: a sentence, and no grid -- the empty arm is the panel alone."""
    assert not probe["errors"], probe["errors"]
    assert admin_copy.EMPTY_USAGE_TITLE == "No one has sent anything today."
    assert admin_copy.EMPTY_USAGE_TITLE in probe["empty"]
    assert "columnheader" not in probe["empty"]
    assert "grid" not in probe["empty"]
    assert "(USAGE_STATE_EMPTY, _empty_usage())" in usage_source
    assert "(USAGE_STATE_FAULT, _table())" in usage_source
    assert "usage_state" in probe["body"]


def test_the_view_renders_its_own_fault(usage_source, probe):
    """AC 4: the usage fault is rendered on this view, from `usage_error`."""
    assert "fault_panel(AdminState.usage_error)" in usage_source
    assert "usage_error" in probe["usage"]


def test_no_chart_no_history_no_row_action(probe, usage_source):
    """AC 5: no chart, no history control, no per-row action -- asserted against
    the code (docstrings and comments stripped) and against a rendered row."""
    assert not probe["errors"], probe["errors"]
    code = _code_only(usage_source).lower()
    for forbidden in (
        "recharts",
        "chart",
        "sparkline",
        "progress",
        "meter",
        "on_click",
        "rx.el.button",
        "rx.button",
        "rx.select",
        "rx.input",
        "date",
        "history",
        "_hover",
        "rx.link",
    ):
        assert forbidden not in code, forbidden
    for rendered in (probe["rows"], probe["table"]):
        assert "onClick" not in rendered
        assert ":hover" not in rendered
    # No usage-specific event handler exists on the state either.
    handlers = set(AdminState.event_handlers)
    assert not {name for name in handlers if "usage" in name}, handlers


def test_only_ground_colours(probe, usage_source):
    """No verdict ink, no tint, no literal colour: the share is a number in a
    column, not a coloured state (frontend-design, PRD 6.10)."""
    assert not probe["errors"], probe["errors"]
    found = {c.upper() for c in COLOUR_REFERENCE.findall(probe["table"])}
    assert found, "collector found nothing; the subset check below would be vacuous"
    assert found <= ALLOWED_COLOURS, sorted(found - ALLOWED_COLOURS)
    assert not re.findall(r"#[0-9a-fA-F]{3,6}\b", usage_source)
    for name in ("INK_CLEAR", "INK_HELD", "INK_DENIED", "INK_FAULT", "TINT_"):
        assert name not in usage_source, name
    rendered = probe["table"].lower()
    for card_property in ("boxshadow", "borderradius"):
        assert card_property not in rendered, card_property


@pytest.mark.parametrize("name", USAGE_COPY_NAMES)
def test_every_string_is_read_from_admin_copy(usage_source, name):
    assert f"admin_copy.{name}" in usage_source, name
    # Over the code only: the docstrings quote some of these on purpose.
    code = _code_only(usage_source)
    value = getattr(admin_copy, name)
    assert f'"{value}"' not in code, name
    assert f"'{value}'" not in code, name


@pytest.mark.parametrize(
    "forbidden",
    (
        "components.chat",
        "components.bubbles",
        "bubbles",
        "components.register",
        "components.summary",
        "chat_ui.state",
    ),
)
def test_usage_imports_nothing_from_the_chat_or_the_other_views(usage_source, forbidden):
    import_lines = [
        line
        for line in usage_source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not [line for line in import_lines if forbidden in line], forbidden


def test_the_table_scrolls_in_its_own_container(usage_source):
    """390px: the table scrolls sideways inside `.hx-scroll`, never the page."""
    assert 'class_name="hx-scroll"' in usage_source
    assert 'overflow_x="auto"' in usage_source
    assert "min_width=_MIN_WIDTH" in usage_source


def test_the_view_switch_takes_its_own_row_at_phone_width():
    """E2E finding (390px): three views made the masthead's meta cluster 30px
    wider than the screen and pushed the sign-out control off the edge. The
    admin masthead's cluster wraps, the switch takes a row of its own, and the
    control that starts the next row drops its leading rule."""
    css = theme.GLOBAL_CSS
    narrow = css[css.index("@media (max-width: 40rem)"):]
    assert ".hx-view-switch {" in narrow
    assert "flex-basis: 100%" in narrow
    assert ".hx-view-switch + *" in narrow
    shell = (REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "admin_shell.py").read_text(encoding="utf-8")
    assert 'class_name="hx-view-switch"' in shell
    # The chat header is not touched: the class is the console's alone.
    chat_shell = (REPO_ROOT / "chat_ui" / "chat_ui" / "components" / "shell.py").read_text(encoding="utf-8")
    assert "hx-view-switch" not in chat_shell
