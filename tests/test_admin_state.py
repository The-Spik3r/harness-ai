"""The console's gate, asserted rather than reviewed.

Three of STORY-003's properties are invisible in a diff and would fail silently
if they regressed: that every refusal produces the *same* message (a second,
more helpful one would be an oracle), that sign-out clears the record from state
rather than hiding it from the view, and that `load()` reads nothing at all
until the gate has passed (PRD-006 Risk 1 — the read is gated, not just the
render). Each is pinned below.

STORY-004 added the load half, and its properties are invisible in a diff for
the same reason: that every read runs on a worker thread rather than the event
loop, that a read failing part-way leaves the previously loaded record exactly
as it was, and that `loading` is cleared on the failure path too. A `grep` for
`asyncio.to_thread` proves none of these; the tests below drive the handler and
observe the thread each read actually ran on.

STORY-005 added the filter and sort half, whose invisible properties are that
`visible_rows` reads no database at all, that an empty verdict selection means
"no verdict filter" rather than "no rows", and that Reflex tracks all five of
the var's dependencies — its tracker fails by returning *none* of them, which
yields a filter that quietly stops updating.

STORY-006 finished the file, and its three additions are invisible in a diff
for the same reason the others are. The four verdicts are asserted against
constructed `AuditLog`s carried through the console's *own* path — the
projection and `load()` — so a register that stopped deriving a verdict fails
here rather than rendering every row as the empty default, and the fifth case
pins PRD-006 Risk 3: a failure that recorded a model is still **fault**. The
no-leak claim is asserted field by field on a fully seeded row, because a
preview smuggled into a differently named field passes every structural check.
And the two filters are applied to rows that genuinely came from a read, with
the recorded call list asserted unchanged across the filtering — which is what
"filtering never re-reads the database" actually claims.
"""

import asyncio
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import reflex as rx

from app.config import settings
from app.db.models import AuditLog
import chat_ui.chat_ui.admin_state as _admin_state_module
from chat_ui.chat_ui.admin_formatting import (
    VERDICT_CLEARED,
    VERDICT_DENIED,
    VERDICT_FAULT,
    VERDICT_HELD,
    to_audit_row,
)
from chat_ui.chat_ui.admin_models import AuditRow
from chat_ui.chat_ui.admin_state import GATE_REFUSED_MESSAGE, AdminState

CONFIGURED_TOKEN = "correct-horse-battery"


@pytest.fixture
def configured_token(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", CONFIGURED_TOKEN)
    return CONFIGURED_TOKEN


def _state() -> AdminState:
    return AdminState(_reflex_internal_init=True)


def _authenticate(state: AdminState, token: str):
    """Drives the handler directly, as tests/test_chat_state.py:80-84 does."""
    state.token_input = token
    return type(state).event_handlers["authenticate"].fn(state)


def _sign_out(state: AdminState):
    return type(state).event_handlers["sign_out"].fn(state)


async def _load(state: AdminState):
    return await type(state).event_handlers["load"].fn(state)


def _populate(state: AdminState) -> dict:
    """Fills every declared field with a non-default value, and returns the
    defaults each one must be restored to."""
    state.rows = [AuditRow(audit_id=3180, user_id="a.torres", verdict="denied")]
    state.total_recorded = 3180
    state.blocked_duplicates = 12
    state.blocked_suspicious = 3
    state.unique_users = 7
    state.successful_queries = 3100
    state.pii_detected_queries = 412
    state.top_models = ["gpt-4"]
    state.top_users = ["a.torres"]
    state.top_pii_entities = ["EMAIL_ADDRESS"]
    state.last_refreshed = "14:22:07"
    state.loading = True
    state.error = "previous fault"
    return {
        "rows": [],
        "total_recorded": 0,
        "blocked_duplicates": 0,
        "blocked_suspicious": 0,
        "unique_users": 0,
        "successful_queries": 0,
        "pii_detected_queries": 0,
        "top_models": [],
        "top_users": [],
        "top_pii_entities": [],
        "last_refreshed": "",
        "loading": False,
        "error": "",
    }


# ---------------------------------------------------------------------------
# Structure (AC 1)
# ---------------------------------------------------------------------------


def test_admin_state_is_a_sibling_of_chat_state_not_a_substate():
    """PRD-006 Section 4: "ChatState never reads admin state." Subclassing any
    other state would make the console a child of the chat in one line."""
    assert AdminState.__bases__ == (rx.State,)


def test_gate_fields_exist_with_refusing_defaults():
    state = _state()

    assert state.token_input == ""
    assert state.authenticated is False
    assert state.gate_error == ""
    assert state.rows == []


# ---------------------------------------------------------------------------
# The gate (AC 2, AC 3, AC 5)
# ---------------------------------------------------------------------------


def test_correct_token_authenticates_clears_the_error_and_triggers_the_load(
    configured_token,
):
    state = _state()

    returned = _authenticate(state, configured_token)

    assert state.authenticated is True
    assert state.gate_error == ""
    # The secret does not stay resident once `authenticated` is the credential.
    assert state.token_input == ""
    assert returned.fn.__name__ == "load"


@pytest.mark.parametrize(
    "token",
    [
        "",
        "nope",
        "x" * len(CONFIGURED_TOKEN),
    ],
    ids=["empty", "wrong-length", "wrong-same-length"],
)
def test_every_wrong_token_is_refused(configured_token, token):
    state = _state()

    _authenticate(state, token)

    assert state.authenticated is False
    assert state.gate_error == GATE_REFUSED_MESSAGE
    # A refused gate re-renders empty, never repopulated (STORY-009 AC 3).
    assert state.token_input == ""


def test_the_three_refusals_produce_the_identical_message(configured_token):
    """Asserted as equal to each other, not merely as non-empty: a message that
    differed by failure mode would tell an attacker which half they got right."""
    messages = []
    for token in ("", "nope", "x" * len(configured_token)):
        state = _state()
        _authenticate(state, token)
        messages.append(state.gate_error)

    assert len(set(messages)) == 1, messages


def test_non_ascii_token_of_differing_byte_length_is_refused_without_raising(
    configured_token,
):
    """secrets.compare_digest raises TypeError on non-ASCII str operands, and
    this token comes from a browser field — so both sides are encoded first."""
    state = _state()

    _authenticate(state, "ñ" * 12)  # 24 UTF-8 bytes against 21 configured

    assert state.authenticated is False
    assert state.gate_error == GATE_REFUSED_MESSAGE


def test_blank_configured_token_does_not_open_the_console(monkeypatch):
    """ADMIN_TOKEN is required but "" satisfies it, and compare_digest(b"", b"")
    is True — so emptiness on either side refuses before the comparison."""
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    state = _state()

    _authenticate(state, "")

    assert state.authenticated is False
    assert state.gate_error == GATE_REFUSED_MESSAGE


def test_gate_uses_constant_time_comparison(configured_token, monkeypatch):
    """Mirrors tests/test_admin_auth.py:87-108, which spies the same call on the
    API's gate. Both operands must arrive as bytes."""
    import chat_ui.chat_ui.admin_state as admin_state_mod

    calls = []
    original = admin_state_mod.secrets.compare_digest

    def _tracking_compare_digest(a, b):
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(
        admin_state_mod.secrets, "compare_digest", _tracking_compare_digest
    )

    state = _state()
    _authenticate(state, configured_token)

    assert state.authenticated is True
    assert len(calls) == 1
    assert all(isinstance(operand, bytes) for operand in calls[0])


# ---------------------------------------------------------------------------
# Sign-out (AC 4)
# ---------------------------------------------------------------------------


def test_sign_out_clears_the_token_the_rows_and_the_figures(configured_token):
    state = _state()
    _authenticate(state, configured_token)
    defaults = _populate(state)
    state.token_input = "still typed"

    _sign_out(state)

    assert state.authenticated is False
    assert state.token_input == ""
    assert state.gate_error == ""
    for field, default in defaults.items():
        assert getattr(state, field) == default, field


def test_sign_out_clears_every_declared_var(configured_token):
    """The guarantee has to hold for fields that do not exist yet: STORY-004 and
    STORY-005 add more, and a field cleared nowhere is the one that survives a
    sign-out unnoticed."""
    state = _state()
    _authenticate(state, configured_token)
    _populate(state)

    _sign_out(state)

    for name in AdminState.base_vars:
        value = getattr(state, name)
        assert value in ("", 0, False, None) or value == [], (name, value)


# ---------------------------------------------------------------------------
# The read is gated, not just the view (AC 6, Risk 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_on_an_unauthenticated_state_reads_nothing():
    """The /admin/stats-reached-directly case. PRD-006 Risk 1: an unauthenticated
    page has no data in state to leak regardless of what renders."""
    state = _state()

    await _load(state)

    assert state.rows == []
    assert state.loading is False
    assert state.error == ""


@pytest.mark.asyncio
async def test_load_is_still_gated_after_sign_out(configured_token):
    state = _state()
    _authenticate(state, configured_token)
    _populate(state)
    _sign_out(state)

    await _load(state)

    assert state.authenticated is False
    assert state.rows == []


# ---------------------------------------------------------------------------
# Read-only by construction (PRD-006 Section 9)
# ---------------------------------------------------------------------------


def test_admin_state_has_no_write_path_to_the_audit_log():
    """"insert_audit_log is not imported, and there is no write path from any
    admin page." Asserted against the module's namespace, not its source text."""
    import chat_ui.chat_ui.admin_state as admin_state_mod

    assert not hasattr(admin_state_mod, "insert_audit_log")


# ---------------------------------------------------------------------------
# The load path (STORY-004)
# ---------------------------------------------------------------------------

_ORIGINAL_READS = _admin_state_module._READS

_READ_RETURNS = {
    "list_audit_logs": None,  # filled per test with _logs()
    "count_audit_logs": 3180,
    "count_blocked_duplicates": 12,
    "count_blocked_suspicious": 3,
    "count_unique_users": 7,
    "count_successful_queries": 3100,
    "count_pii_detected_queries": 412,
    "top_models": ["gpt-4", "claude"],
    "top_users": ["a.torres"],
    "top_pii_entities": ["EMAIL_ADDRESS"],
}


def _logs() -> list[AuditLog]:
    """Three rows, newest first, of three different verdicts. Both previews are
    populated deliberately: Risk 2 is only tested if there is something to leak."""
    return [
        AuditLog(
            id=3,
            timestamp="2026-08-28T14:00:00+00:00",
            user_id="a.torres",
            prompt_hash="h3",
            prompt_preview="SENTINEL PROMPT TEXT",
            response_preview="SENTINEL RESPONSE TEXT",
            model_used="gpt-4",
            tokens_used=10,
            success=True,
        ),
        AuditLog(
            id=2,
            timestamp="2026-08-28T13:00:00+00:00",
            user_id="b.singh",
            prompt_hash="h2",
            was_duplicate_blocked=True,
            success=True,
        ),
        AuditLog(
            id=1,
            timestamp="2026-08-28T12:00:00+00:00",
            user_id="c.diaz",
            prompt_hash="h1",
            success=False,
            error_message="boom",
        ),
    ]


class _Reads:
    """Replaces `_READS` with stubs that record what ran, and on which thread.

    The thread is the point. AC 1 says "never on the event loop", and no static
    check can show that — only the ident recorded inside the call can.
    """

    def __init__(self, monkeypatch, failing=None, on_call=None, *, logs=None):
        self._monkeypatch = monkeypatch
        self.failing = failing
        self.on_call = on_call
        # Keyword-only, defaulting to `_logs()` — STORY-006 needs `load()` to
        # return its own five constructed rows, and every earlier call site
        # passes nothing and takes the identical path.
        self.logs = logs
        self.calls = []
        self.threads = []
        self.kwargs = {}

    def install(self):
        import chat_ui.chat_ui.admin_state as admin_state_mod

        returns = dict(_READ_RETURNS)
        returns["list_audit_logs"] = _logs() if self.logs is None else list(self.logs)
        # Built from the pristine table, never from `admin_state_mod._READS`: a
        # test that installs twice (fail, then recover) would otherwise wrap its
        # own stubs and lose the real function names the returns are keyed by.
        stubbed = tuple(
            (field, label, self._stub(field, fn.__name__, returns), kwargs)
            for field, label, fn, kwargs in _ORIGINAL_READS
        )
        self._monkeypatch.setattr(admin_state_mod, "_READS", stubbed)
        return self

    def _stub(self, field, name, returns):
        def stub(**kwargs):
            self.calls.append(field)
            self.threads.append(threading.get_ident())
            self.kwargs[field] = kwargs
            if self.on_call is not None:
                self.on_call()
            if self.failing == field:
                raise RuntimeError("db is on fire")
            return returns[name]

        return stub


def _loaded_record(state: AdminState) -> dict:
    """Every field `load()` writes, as a comparable snapshot."""
    return {
        "rows": list(state.rows),
        "total_recorded": state.total_recorded,
        "blocked_duplicates": state.blocked_duplicates,
        "blocked_suspicious": state.blocked_suspicious,
        "unique_users": state.unique_users,
        "successful_queries": state.successful_queries,
        "pii_detected_queries": state.pii_detected_queries,
        "top_models": list(state.top_models),
        "top_users": list(state.top_users),
        "top_pii_entities": list(state.top_pii_entities),
        "last_refreshed": state.last_refreshed,
    }


def test_the_read_table_names_all_ten_database_functions():
    """AC 1 as a structural claim: ten distinct functions, ten distinct fields,
    each field an actual var on the state — a typo would otherwise create a new
    attribute at commit time and lose the read in silence."""
    import chat_ui.chat_ui.admin_state as admin_state_mod

    reads = admin_state_mod._READS
    assert len(reads) == 10
    assert len({field for field, _, _, _ in reads}) == 10
    assert len({fn for _, _, fn, _ in reads}) == 10
    assert {fn.__name__ for _, _, fn, _ in reads} == {
        "list_audit_logs",
        "count_audit_logs",
        "count_blocked_duplicates",
        "count_blocked_suspicious",
        "count_unique_users",
        "count_successful_queries",
        "count_pii_detected_queries",
        "top_models",
        "top_users",
        "top_pii_entities",
    }
    for field, _, _, _ in reads:
        assert field in AdminState.base_vars, field


@pytest.mark.asyncio
async def test_load_runs_all_ten_reads_off_the_event_loop(
    configured_token, monkeypatch
):
    """AC 1. The assertion that matters is the thread ident: a read left on the
    loop would record the caller's own ident here."""
    state = _state()
    _authenticate(state, configured_token)
    reads = _Reads(monkeypatch).install()

    await _load(state)

    assert len(reads.calls) == 10
    assert threading.get_ident() not in reads.threads
    # The register's window is the cap PRD-006 Section 4 fixes, passed as the
    # keyword argument AC 1 names.
    assert reads.kwargs["rows"] == {"limit": 100}


@pytest.mark.asyncio
async def test_load_builds_audit_rows_newest_first_with_the_true_total(
    configured_token, monkeypatch
):
    """AC 2. Order is asserted as *preserved*: `list_audit_logs` already returns
    newest-first, and a sort here would fight STORY-005's computed var."""
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch).install()

    await _load(state)

    assert all(isinstance(row, AuditRow) for row in state.rows)
    assert [row.audit_id for row in state.rows] == [3, 2, 1]
    # Built through to_audit_row, not constructed inline: the verdict and the
    # relative time only exist if the projection ran.
    assert [row.verdict for row in state.rows] == ["cleared", "held", "fault"]
    assert state.rows[0].timestamp_relative != ""
    assert state.total_recorded == 3180
    assert state.blocked_duplicates == 12
    assert state.blocked_suspicious == 3
    assert state.unique_users == 7
    assert state.successful_queries == 3100
    assert state.pii_detected_queries == 412
    assert state.top_models == ["gpt-4", "claude"]
    assert state.top_users == ["a.torres"]
    assert state.top_pii_entities == ["EMAIL_ADDRESS"]


@pytest.mark.asyncio
async def test_neither_preview_survives_the_read(configured_token, monkeypatch):
    """PRD-006 Risk 2, held across the new read path rather than only at the
    model: the console reads a wider row than it renders, and this is the point
    where the two preview columns would enter state if the projection were
    bypassed."""
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch).install()

    await _load(state)

    assert "SENTINEL" not in repr(state.rows)
    for row in state.rows:
        assert not hasattr(row, "prompt_preview")
        assert not hasattr(row, "response_preview")


@pytest.mark.asyncio
async def test_loading_is_true_for_the_duration_and_false_after(
    configured_token, monkeypatch
):
    """AC 3. Observed from inside the reads themselves — checking it only after
    the fact cannot distinguish "set and cleared" from "never set"."""
    state = _state()
    _authenticate(state, configured_token)
    seen = []
    _Reads(monkeypatch, on_call=lambda: seen.append(state.loading)).install()

    await _load(state)

    assert len(seen) == 10
    assert all(seen), seen
    assert state.loading is False


@pytest.mark.asyncio
async def test_load_stamps_the_time_of_the_read(configured_token, monkeypatch):
    """AC 5."""
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch).install()

    await _load(state)

    assert state.last_refreshed.endswith(" UTC")
    assert state.error == ""


@pytest.mark.asyncio
async def test_a_failed_read_names_it_and_leaves_the_record_untouched(
    configured_token, monkeypatch
):
    """AC 4, and the reason results are collected into locals: the eighth of ten
    reads fails, and not one of the seven that already returned is committed."""
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch).install()
    await _load(state)
    before = _loaded_record(state)

    failing = _Reads(monkeypatch, failing="top_models").install()
    await _load(state)

    assert len(failing.calls) == 8
    assert "the model ranking" in state.error
    assert _loaded_record(state) == before
    assert state.loading is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failing,label",
    [("rows", "the audit rows"), ("top_pii_entities", "the PII entity ranking")],
    ids=["first-read", "last-read"],
)
async def test_every_read_position_faults_the_same_way(
    configured_token, monkeypatch, failing, label
):
    """AC 4 at both ends of the table: the first read failing must not leave a
    half-written state either, and the last one must not slip past the arm."""
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch, failing=failing).install()

    await _load(state)

    assert label in state.error
    assert state.rows == []
    assert state.last_refreshed == ""
    assert state.loading is False


@pytest.mark.asyncio
async def test_a_recovered_read_clears_the_fault(configured_token, monkeypatch):
    """The state STORY-017's retry depends on: a fault panel that never cleared
    would outlive the failure that caused it."""
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch, failing="rows").install()
    await _load(state)
    assert state.error

    _Reads(monkeypatch).install()
    await _load(state)

    assert state.error == ""
    assert len(state.rows) == 3
    assert state.last_refreshed.endswith(" UTC")


@pytest.mark.asyncio
async def test_a_second_concurrent_load_is_refused_by_the_loading_guard(
    configured_token, monkeypatch
):
    """Two loads in flight would race each other's commit and could publish the
    older of two results."""
    state = _state()
    _authenticate(state, configured_token)
    reads = _Reads(monkeypatch).install()

    await asyncio.gather(_load(state), _load(state))

    assert len(reads.calls) == 10
    assert state.loading is False


@pytest.mark.asyncio
async def test_an_unauthenticated_load_calls_none_of_the_ten(monkeypatch):
    """STORY-004 AC 6, strengthened past STORY-003's version: not merely "rows
    stay empty" but "no read function was entered at all".

    Also STORY-006 AC 5 — the `/admin/stats`-reached-without-a-session case, and
    PRD-006 Risk 1's load-bearing half. Both of that AC's halves are stated here
    together: the register is empty *because* nothing was read, not because a
    read returned nothing.
    """
    state = _state()
    reads = _Reads(monkeypatch).install()

    await _load(state)

    assert reads.calls == []
    assert state.rows == []
    assert state.loading is False
    assert state.error == ""
    assert state.last_refreshed == ""


# ---------------------------------------------------------------------------
# STORY-005: the filter and sort vars over the loaded rows
#
# Three of this story's properties are invisible in a diff and would fail
# silently if they regressed. That `visible_rows` performs no database read — a
# var that grew an await would still look correct in review. That an empty
# verdict selection means "no verdict filter" rather than "no rows" — the
# inverted reading empties the register on page load and reads as "nothing
# recorded", the exact misreading PRD-006 Section 4 forbids. And that Reflex
# actually tracks all five dependencies — its tracker's failure mode is a
# console.warn and an EMPTY dependency set, which yields a filter that computes
# once and then never updates again.
#
# STORY-006's block, at the foot of this file, closes the pair these tests
# leave open: the rows filtered here are built by hand, and the no-read claim is
# proved against raising stubs, so neither states the two together.
# ---------------------------------------------------------------------------

# The ten reads under the names they carry in `admin_state`'s own namespace —
# the three rankings are imported aliased, so this is not `_READ_RETURNS`' key
# set. Used to prove a negative: that none of them is reachable from the var.
_READ_ATTRIBUTES = (
    "list_audit_logs",
    "count_audit_logs",
    "count_blocked_duplicates",
    "count_blocked_suspicious",
    "count_unique_users",
    "count_successful_queries",
    "count_pii_detected_queries",
    "read_top_models",
    "read_top_users",
    "read_top_pii_entities",
)


def _call(state: AdminState, handler: str, *args):
    return type(state).event_handlers[handler].fn(state, *args)


# Newest first — the order `list_audit_logs` returns. All four verdicts present,
# and `a.torres` appears in three casings so the case-fold is exercised.
_FILTER_ROWS = [
    AuditRow(audit_id=130, user_id="m.silva", verdict="cleared", model_used="gpt-4"),
    AuditRow(audit_id=129, user_id="a.torres", verdict="fault", model_used="claude-3"),
    AuditRow(audit_id=128, user_id="j.rios", verdict="held", model_used="gpt-4"),
    AuditRow(audit_id=127, user_id="a.torres", verdict="denied", model_used="GPT-4"),
    AuditRow(audit_id=126, user_id="A.Torres", verdict="cleared", model_used="gpt-4"),
]


def _loaded(configured_token) -> AdminState:
    state = _state()
    _authenticate(state, configured_token)
    state.rows = list(_FILTER_ROWS)
    return state


def _visible(state: AdminState) -> list[int]:
    return [row.audit_id for row in state.visible_rows]


def test_the_filter_and_sort_state_is_four_plain_vars(configured_token):
    """AC 1. Plain base vars, not computed ones — the controls write them."""
    state = _loaded(configured_token)

    for name in ("selected_verdicts", "search", "sort_key", "sort_descending"):
        assert name in AdminState.base_vars, name
    assert state.selected_verdicts == []
    assert state.search == ""
    assert state.sort_key == ""
    assert state.sort_descending is False


def test_visible_rows_is_a_computed_var_over_the_rows_and_the_filter_state():
    """AC 2, first half. A base var here would mean the register renders a
    snapshot that some handler has to remember to refresh."""
    assert "visible_rows" in AdminState.computed_vars
    assert "visible_rows" not in AdminState.base_vars


def test_visible_rows_tracks_all_five_of_its_dependencies():
    """The silent failure this story is most exposed to.

    `ComputedVar._deps` catches every exception out of Reflex's dependency
    tracker, warns, and returns NO dependencies — leaving a var that computes
    correctly once and then never updates. Nothing in a diff shows it, and the
    filter simply appears not to work. The tracker only sees attributes loaded
    from `self` in the getter's own body, so this test is what pins the rule
    that `visible_rows` reads its five vars itself rather than letting
    `filter_rows` / `sort_rows` reach for them.
    """
    tracked = AdminState.computed_vars["visible_rows"]._deps(objclass=AdminState)[
        AdminState.get_full_name()
    ]

    for name in ("rows", "selected_verdicts", "search", "sort_key", "sort_descending"):
        assert name in tracked, (name, tracked)


def test_evaluating_visible_rows_performs_no_database_read(
    configured_token, monkeypatch
):
    """AC 2, second half — PRD-006 Section 6: "filtering never re-reads the
    database".

    Every one of the ten reads is replaced with a raising stub, then the var is
    evaluated across the filter and sort space. Reading the source proves
    nothing here; entering the var with no reachable read does.
    """

    def boom(*args, **kwargs):
        raise AssertionError("visible_rows performed a database read")

    for name in _READ_ATTRIBUTES:
        monkeypatch.setattr(_admin_state_module, name, boom)
    monkeypatch.setattr(
        _admin_state_module,
        "_READS",
        tuple(
            (field, label, boom, kwargs)
            for field, label, _fn, kwargs in _ORIGINAL_READS
        ),
    )

    state = _loaded(configured_token)
    for verdicts in ([], ["denied"], ["cleared", "fault"]):
        for text in ("", "127", "a.torres", "zzz"):
            for key in ("", "timestamp", "user", "verdict", "unrecognised"):
                for descending in (False, True):
                    state.selected_verdicts = verdicts
                    state.search = text
                    state.sort_key = key
                    state.sort_descending = descending
                    assert isinstance(state.visible_rows, list)
                    assert isinstance(state.filters_active, bool)


def test_an_empty_verdict_selection_passes_every_row(configured_token):
    """AC 6. `row.verdict not in []` is True for every row, so a predicate
    missing the `if verdicts and` guard empties the register the moment the page
    loads — and an empty register reads as "nothing recorded" (STORY-014)."""
    state = _loaded(configured_token)

    assert state.selected_verdicts == []
    assert len(state.visible_rows) == len(_FILTER_ROWS)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("127", [127]),
        ("a.torres", [129, 127, 126]),
        ("A.TORRES", [129, 127, 126]),
        ("claude-3", [129]),
        ("GPT-4", [130, 128, 127, 126]),
        ("  127  ", [127]),
        ("zzz", []),
    ],
)
def test_free_text_matches_user_model_and_id_case_insensitively(
    configured_token, text, expected
):
    """AC 3. `127` isolating audit #127 is PRD Section 5 story 5 — the loop that
    closes on PRD-004's chat success footer, where the user read the id."""
    state = _loaded(configured_token)
    state.search = text

    assert _visible(state) == expected


def test_the_two_filters_compose_as_and(configured_token):
    """AC 4. An OR would widen the register at the exact moment the admin is
    narrowing it."""
    state = _loaded(configured_token)

    state.selected_verdicts = ["denied"]
    denied_only = _visible(state)
    state.selected_verdicts = []
    state.search = "a.torres"
    text_only = _visible(state)
    state.selected_verdicts = ["denied"]
    both = _visible(state)

    assert denied_only == [127]
    assert text_only == [129, 127, 126]
    assert both == [127]
    assert len(both) <= len(denied_only)
    assert len(both) < len(text_only)


def test_the_default_order_is_the_order_list_audit_logs_returned(configured_token):
    """AC 5's default. `sort_key` defaults to "" — not to "timestamp" — because
    sign_out()'s reset() requires a falsy default on every declared var. The two
    must therefore render the identical register."""
    state = _loaded(configured_token)

    assert _visible(state) == [130, 129, 128, 127, 126]

    state.sort_key = "timestamp"
    assert _visible(state) == [130, 129, 128, 127, 126]


def test_each_sort_key_changes_the_ordering(configured_token):
    """AC 5. User sorts A-Z case-insensitively; verdict leads with the
    exceptions the register exists to surface, not alphabetically."""
    state = _loaded(configured_token)
    default = _visible(state)

    state.sort_key = "user"
    assert _visible(state) == [129, 127, 126, 128, 130]
    assert _visible(state) != default

    state.sort_key = "verdict"
    assert [row.verdict for row in state.visible_rows] == [
        "fault",
        "denied",
        "held",
        "cleared",
        "cleared",
    ]
    assert _visible(state) != default


def test_sort_descending_reverses_the_chosen_order(configured_token):
    state = _loaded(configured_token)
    ascending = _visible(state)

    state.sort_descending = True

    assert _visible(state) == list(reversed(ascending))


def test_an_unrecognised_sort_key_or_verdict_degrades_instead_of_raising(
    configured_token,
):
    """No ordering may raise into a page render. An AuditRow's verdict defaults
    to "" — an unpopulated row must sort, not explode."""
    state = _loaded(configured_token)
    state.rows = [*_FILTER_ROWS, AuditRow(audit_id=125, user_id="x", verdict="")]

    state.sort_key = "nonsense"
    assert _visible(state) == [130, 129, 128, 127, 126, 125]

    state.sort_key = "verdict"
    assert _visible(state)[-1] == 125


def test_visible_rows_does_not_reorder_or_alter_the_loaded_rows(configured_token):
    """A computed var that sorted `rows` in place would rewrite the source of
    truth as a side effect of rendering."""
    state = _loaded(configured_token)
    before = [row.audit_id for row in state.rows]

    state.sort_key = "user"
    state.sort_descending = True
    state.search = "torres"
    assert state.visible_rows

    assert [row.audit_id for row in state.rows] == before


def test_the_pure_helpers_return_new_lists():
    """The same guarantee where object identity survives — Reflex re-wraps every
    element of a list var in a fresh MutableProxy on each read, so identity is
    only meaningful off the state."""
    rows = list(_FILTER_ROWS)
    identities = [id(row) for row in rows]

    assert _admin_state_module.filter_rows(rows, [], "") is not rows
    assert _admin_state_module.filter_rows(rows, ["denied"], "torres") is not rows
    assert _admin_state_module.sort_rows(rows, "user", True) is not rows

    assert [row.audit_id for row in rows] == [r.audit_id for r in _FILTER_ROWS]
    assert [id(row) for row in rows] == identities


def test_filters_active_reports_the_filters_and_ignores_the_sort(configured_token):
    """STORY-014's no-matches state is `filters_active and not visible_rows`, so
    a sort counting as an active filter would offer to "clear" an ordering."""
    state = _loaded(configured_token)
    assert state.filters_active is False

    state.sort_key = "user"
    state.sort_descending = True
    assert state.filters_active is False

    state.search = "   "
    assert state.filters_active is False

    state.search = "a.torres"
    assert state.filters_active is True

    state.search = ""
    state.selected_verdicts = ["denied"]
    assert state.filters_active is True


def test_toggle_verdict_adds_removes_and_reassigns(configured_token):
    """Reassignment rather than an in-place append: Reflex marks a var dirty on
    assignment, and a mutated list can leave `visible_rows` on its cached
    value."""
    state = _loaded(configured_token)

    _call(state, "toggle_verdict", "denied")
    assert state.selected_verdicts == ["denied"]

    _call(state, "toggle_verdict", "fault")
    assert state.selected_verdicts == ["denied", "fault"]
    assert _visible(state) == [129, 127]

    _call(state, "toggle_verdict", "denied")
    assert state.selected_verdicts == ["fault"]
    assert _visible(state) == [129]


def test_sort_by_selects_a_key_then_flips_direction_on_repeat(configured_token):
    state = _loaded(configured_token)

    _call(state, "sort_by", "user")
    assert state.sort_key == "user"
    assert state.sort_descending is False

    _call(state, "sort_by", "user")
    assert state.sort_descending is True

    _call(state, "sort_by", "verdict")
    assert state.sort_key == "verdict"
    assert state.sort_descending is False


def test_clear_filters_restores_the_window_without_touching_sort_or_rows(
    configured_token,
):
    """An admin clearing a filter is not asking for a reload."""
    state = _loaded(configured_token)
    state.selected_verdicts = ["denied"]
    state.search = "a.torres"
    state.sort_key = "user"

    _call(state, "clear_filters")

    assert state.selected_verdicts == []
    assert state.search == ""
    assert state.sort_key == "user"
    assert len(state.rows) == len(_FILTER_ROWS)
    assert state.filters_active is False


def test_sign_out_clears_the_filter_and_sort_state_too(configured_token):
    """AC 7. A filter surviving a sign-out is the standing disclosure PRD-006
    Section 9 is about — the next person at the machine sees a register already
    narrowed to a named user."""
    state = _loaded(configured_token)
    state.selected_verdicts = ["denied"]
    state.search = "a.torres"
    state.sort_key = "user"
    state.sort_descending = True

    _sign_out(state)

    assert state.selected_verdicts == []
    assert state.search == ""
    assert state.sort_key == ""
    assert state.sort_descending is False
    assert state.rows == []


def test_the_verdict_vocabulary_is_imported_not_redeclared():
    """PRD-006 Section 6 fixes the four strings in admin_formatting.py so two
    rows with identical fields can never render differently. A second copy here
    is how that drifts."""
    from chat_ui.chat_ui import admin_formatting

    assert _admin_state_module.VERDICTS is admin_formatting.VERDICTS
    source = Path(_admin_state_module.__file__).read_text(encoding="utf-8")
    for verdict in admin_formatting.VERDICTS:
        assert '"' + verdict + '"' not in source, verdict


# ---------------------------------------------------------------------------
# STORY-006: the verdicts, the projection and the filters, from the state's side
#
# `tests/test_admin_formatting.py` already asserts `derive_verdict`'s four arms
# as a unit. These three blocks assert the same properties on the *console's own
# path* — through `to_audit_row`, through `load()`, into `AdminState.rows` and
# out through `visible_rows` — because that is the path a regression breaks
# while the formatting tests stay green: `load()` swapping its row constructor,
# or a preview arriving on a field the projection was supposed to drop.
# ---------------------------------------------------------------------------

# One clock for every projection below, so a relative time can never make a test
# depend on when it ran.
_NOW = datetime(2026, 8, 28, 15, 0, 0, tzinfo=timezone.utc)

# One log per verdict, newest first, and a fifth that is the Risk 3 regression
# guard. `a.torres` carries two of the three faults so a verdict filter and a
# text filter have something to narrow *together* (AC 7).
_VERDICT_LOGS = [
    AuditLog(
        id=205,
        timestamp="2026-08-28T14:50:00+00:00",
        user_id="a.torres",
        prompt_hash="h205",
        was_duplicate_blocked=True,
    ),
    AuditLog(
        id=204,
        timestamp="2026-08-28T14:40:00+00:00",
        user_id="b.singh",
        prompt_hash="h204",
        suspicious_pattern="ignore_instructions",
    ),
    AuditLog(
        id=203,
        timestamp="2026-08-28T14:30:00+00:00",
        user_id="a.torres",
        prompt_hash="h203",
        success=False,
        error_message="upstream timed out",
    ),
    AuditLog(
        id=202,
        timestamp="2026-08-28T14:20:00+00:00",
        user_id="c.diaz",
        prompt_hash="h202",
        model_used="gpt-4",
        tokens_used=180,
    ),
    # The Risk 3 case: a failure that DID record a model. The output-side
    # PiiRedactorError arm (app/services/query_pipeline.py:91-93) writes
    # model_used together with success=False, so splitting **fault** on that
    # field would misclassify this row as something else entirely.
    AuditLog(
        id=201,
        timestamp="2026-08-28T14:10:00+00:00",
        user_id="a.torres",
        prompt_hash="h201",
        model_used="gpt-4",
        tokens_used=42,
        success=False,
        error_message="output redaction failed",
    ),
]

# Imported constants, never re-typed literals: the vocabulary is fixed in
# admin_formatting.py precisely so a second copy cannot drift from it.
_EXPECTED_VERDICTS = [
    VERDICT_HELD,
    VERDICT_DENIED,
    VERDICT_FAULT,
    VERDICT_CLEARED,
    VERDICT_FAULT,
]


@pytest.mark.parametrize(
    "log,expected",
    list(zip(_VERDICT_LOGS, _EXPECTED_VERDICTS)),
    ids=[
        "duplicate-blocked",
        "suspicious-pattern",
        "failed",
        "plain",
        "failed-with-model",
    ],
)
def test_each_constructed_log_reaches_the_row_with_its_verdict(log, expected):
    """AC 4, at the projection the console actually uses."""
    assert to_audit_row(log, _NOW).verdict == expected


@pytest.mark.asyncio
async def test_the_loaded_register_carries_the_four_verdicts_in_order(
    configured_token, monkeypatch
):
    """AC 4, end to end: the same five logs read through `load()`.

    Asserted against the loaded rows rather than against `derive_verdict`, so a
    `load()` that stopped projecting through `to_audit_row` — and therefore
    stopped deriving a verdict at all — fails here rather than shipping a
    register whose every row reads as AuditRow's empty default.
    """
    state = _state()
    _authenticate(state, configured_token)
    _Reads(monkeypatch, logs=_VERDICT_LOGS).install()

    await _load(state)

    assert [row.verdict for row in state.rows] == _EXPECTED_VERDICTS
    assert [row.audit_id for row in state.rows] == [205, 204, 203, 202, 201]


def test_a_failed_row_that_recorded_a_model_is_still_fault():
    """PRD-006 Risk 3, as a regression guard rather than a comment.

    Both rows failed; one recorded a model and one did not. They must carry the
    same verdict — the distinction between an upstream failure and an internal
    one lives in `error_message` on disclosure, not in a fifth verdict.
    """
    without_model = to_audit_row(_VERDICT_LOGS[2], _NOW)
    with_model = to_audit_row(_VERDICT_LOGS[4], _NOW)

    assert with_model.model_used == "gpt-4"
    assert without_model.verdict == with_model.verdict == VERDICT_FAULT


# --- The projection drops both previews (AC 6, Risk 2) ---------------------

_SENTINELS = ("SENTINEL PROMPT TEXT", "SENTINEL RESPONSE TEXT")


def _seeded_log() -> AuditLog:
    """Every displayed column populated, and both previews with it.

    Fully populated deliberately: a no-leak test that walks the row's values
    proves nothing if most of those values are empty defaults.
    """
    return AuditLog(
        id=3181,
        timestamp="2026-08-28T14:00:00+00:00",
        user_id="a.torres",
        device="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        prompt_hash="9f2c1b",
        prompt_preview=_SENTINELS[0],
        response_hash="4d8a7e",
        response_preview=_SENTINELS[1],
        model_used="gpt-4",
        tokens_used=512,
        was_duplicate_blocked=False,
        suspicious_pattern="ignore_instructions",
        success=False,
        error_message="output redaction failed",
        pii_detected_input=True,
        pii_detected_output=True,
        pii_entities="EMAIL_ADDRESS,PHONE_NUMBER",
    )


def test_a_row_built_from_a_seeded_log_carries_neither_preview():
    """AC 6. PRD-006 Risk 2: reading `AuditLog` in-process brings both preview
    columns into the process, one binding away from the screen.

    Asserted three ways, because each catches a different regression: the
    attribute is absent (a field added back), the *declared field* is absent (a
    field added back in a form that leaves `hasattr` ambiguous), and neither
    sentinel appears in any field VALUE (a preview smuggled into a differently
    named field — which the two structural checks would both pass).
    """
    row = to_audit_row(_seeded_log(), _NOW)

    assert not hasattr(row, "prompt_preview")
    assert not hasattr(row, "response_preview")
    # Class-level: pydantic 2.13 deprecates `model_fields` on the instance.
    assert "prompt_preview" not in type(row).model_fields
    assert "response_preview" not in type(row).model_fields

    dumped = row.model_dump()
    # The projection has to have produced something to walk, or the loop below
    # is vacuous and would pass against an empty row.
    assert dumped and dumped["audit_id"] == 3181
    for name, value in dumped.items():
        parts = value if isinstance(value, list) else [value]
        for part in parts:
            for sentinel in _SENTINELS:
                assert sentinel not in str(part), (name, part)


# --- Filtering narrows the loaded rows without a second read (AC 7) --------


@pytest.mark.asyncio
async def test_filtering_the_loaded_register_narrows_it_without_a_second_read(
    configured_token, monkeypatch
):
    """AC 7, as one claim rather than two.

    `test_the_two_filters_compose_as_and` asserts the narrowing against rows
    built by hand, and `test_evaluating_visible_rows_performs_no_database_read`
    asserts the negative against raising stubs. Neither states what PRD-006
    Section 6 actually promises: rows that *did* come from a read, narrowed,
    with the database not touched a second time.
    """
    state = _state()
    _authenticate(state, configured_token)
    reads = _Reads(monkeypatch, logs=_VERDICT_LOGS).install()

    await _load(state)

    assert len(reads.calls) == 10
    calls_after_load = list(reads.calls)

    state.selected_verdicts = [VERDICT_FAULT]
    state.search = "a.torres"

    # The two faults belonging to a.torres — not b.singh's denied row, not
    # a.torres' held row. AND, never OR.
    assert _visible(state) == [203, 201]
    # Compared as a list, not a length: a read appended while another vanished
    # would leave the count intact.
    assert reads.calls == calls_after_load
