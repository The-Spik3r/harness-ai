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

STORY-006 extends this file further: the four verdicts against constructed
`AuditLog`s and STORY-005's filter vars land here once those exist.
"""

import asyncio
import os
import sys
import threading
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

    def __init__(self, monkeypatch, failing=None, on_call=None):
        self._monkeypatch = monkeypatch
        self.failing = failing
        self.on_call = on_call
        self.calls = []
        self.threads = []
        self.kwargs = {}

    def install(self):
        import chat_ui.chat_ui.admin_state as admin_state_mod

        returns = dict(_READ_RETURNS)
        returns["list_audit_logs"] = _logs()
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
    """AC 6, strengthened past STORY-003's version: not merely "rows stay empty"
    but "no read function was entered at all"."""
    state = _state()
    reads = _Reads(monkeypatch).install()

    await _load(state)

    assert reads.calls == []
    assert state.loading is False
    assert state.error == ""
    assert state.last_refreshed == ""
