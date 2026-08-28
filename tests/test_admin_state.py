"""The console's gate, asserted rather than reviewed.

Three of STORY-003's properties are invisible in a diff and would fail silently
if they regressed: that every refusal produces the *same* message (a second,
more helpful one would be an oracle), that sign-out clears the record from state
rather than hiding it from the view, and that `load()` reads nothing at all
until the gate has passed (PRD-006 Risk 1 — the read is gated, not just the
render). Each is pinned below.

STORY-006 extends this file: the load path, the fault arm, the four verdicts
and the filter vars land here once STORY-004 and STORY-005 exist. What is here
now is the access half only, because that is what STORY-003 shipped.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import reflex as rx

from app.config import settings
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
