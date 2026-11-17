"""PRD-018 STORY-013: the MVP definition, proven at the request level (Section 11, D18).

Everything this module drives is built (STORY-002..012); it adds no application code.
It states, through the real call paths (`/query` over `TestClient`, `run_conversation`,
a `ChatState` send), what PRD Section 6.3 promises:

1. **Statements 1-14 under a blip** (`test_each_statement_...`). One case per statement
   of the Section 6.3 table, plus the two representatives of the refusal-row statement
   (6a the duplicate refusal, 6b the foreign-session refusal). Each case runs the path
   fault-free, then once per class: `DEAD_STREAM` (`INVALID_BATON`) and `NOT_SENT`
   (`CONNECT_REFUSED`), with the fault aimed at that one statement. The response, and the
   rows the run leaves for its user, must equal the fault-free run's. A case asserts that
   the fault fired exactly where intended (a wrong prefix would otherwise pass for free),
   and that the retry ran on a fresh client.
2. **`OUTCOME_UNKNOWN` after the effect landed** (`test_a_landed_...`): never replayed
   for a non-idempotent statement (D3). Modelled as `Fault(op="commit", when="after",
   follows=...)`: DML is not durable before `commit()` (spike Q1), so only a forwarded
   commit whose response is lost has "landed".
3. **An in-flight request across an outage** (`test_an_in_flight_...`): released,
   journaled, then exactly one row with the original `timestamp` and `write_id` after
   the database returns and the journal drains (D11-D13).

**One test is one statement, not one (statement x class).** Each `db` test pays ~3.5 s of
fixture setup (`_reset_database`), so a case runs its baseline and both classes inside one
test, under distinct users in the same database. The class is in every assertion message.
Per-user row footprints are compared, never ids, timestamps or write ids.

Which fault models which case is in `tests/db_faults.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import audit_journal, database, journal_drainer
from app.db.database import create_chat_session, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message, ToolCallSpec
from app.services import query_pipeline
from app.services.circuit_breaker import CircuitBreaker
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult, ToolParams
from app.services.query_pipeline import ActionAuditError
from app.services.storage_faults import STORAGE_UNAVAILABLE_NOT_SENT_DETAIL

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.state import ChatState

from tests.db_faults import (
    CONNECT_REFUSED,
    INVALID_BATON,
    NAMESPACE_SHUTDOWN_503,
    UNIQUE_SESSION_ID,
    Fault,
    FaultScript,
)

_HEX = re.compile(r"^[0-9a-f]{32}$")
_LOG = "app.db.database"

#: Response fields that are per-request by design (PRD-018 D14) or a clock reading, so a
#: fault-free run and a faulted one can never agree on them. The key must still be
#: present: the value is replaced, never dropped (the shape is compared).
_PER_RUN_FIELDS = ("audit_id", "audit_ref", "first_query_at")

_READ = ToolCallSpec("call_r", "read", '{"path": "src/a.py"}')
_SHELL = ToolCallSpec("call_s", "shell", '{"command": "rm -rf /"}')
_TOOL_PARAMS = ToolParams(tools=({"type": "function", "function": {"name": "read"}},), tool_choice=None)

_CLASSES = (("DEAD_STREAM", INVALID_BATON), ("NOT_SENT", CONNECT_REFUSED))


# --- the scripted upstream ------------------------------------------------------


class _Upstream:
    """Answers `content` (or a message count) with calls; records what it was sent.

    The text names how many messages it was handed, so a chat send that lost its
    history (statement 3) changes the answer instead of passing silently.
    """

    def __init__(self, content=None, *calls):
        self.content, self.calls, self.sent = content, calls, 0

    def __call__(self, messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        self.sent += 1
        text = self.content if self.content is not None else f"Hi there! ({len(messages)} messages)"
        return OpenRouterResult(
            response=text, model_used=model, tokens_used=150,
            input_tokens=120, output_tokens=30, tool_calls=self.calls,
            finish_reason="tool_calls" if self.calls else "stop",
        )


@pytest.fixture
def upstream(monkeypatch):
    stub = _Upstream()
    monkeypatch.setattr("app.routers.query.call_openrouter", stub)
    monkeypatch.setattr(chat_state_mod, "call_openrouter", stub)
    return stub


@dataclass(frozen=True)
class _User:
    user_id: str
    token: str


def _new_user(label: str) -> _User:
    user = _User(f"{label}@mvp.test", f"token-{label}")
    insert_user(User(user_id=user.user_id, role="user", token_hash=hash_token(user.token)))
    return user


# --- what a run leaves behind ---------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """What a client saw (`outcome`) and what the database holds for its user."""

    outcome: Any
    footprint: Any


def _footprint(user_id: str) -> dict:
    with get_connection() as conn:
        def rows(sql):
            return conn.execute(sql, (user_id,)).fetchall()

        return {
            "audit_logs": [
                (r["success"], r["was_duplicate_blocked"], r["denied_permission"])
                for r in rows(
                    "SELECT success, was_duplicate_blocked, denied_permission"
                    " FROM audit_logs WHERE user_id = ? ORDER BY id"
                )
            ],
            "usage_daily": [
                (r["requests"], r["input_tokens"], r["output_tokens"], r["unsplit_tokens"])
                for r in rows(
                    "SELECT requests, input_tokens, output_tokens, unsplit_tokens"
                    " FROM usage_daily WHERE user_id = ? ORDER BY day"
                )
            ],
            "chat_sessions": len(rows("SELECT session_id FROM chat_sessions WHERE user_id = ?")),
            "chat_messages": [
                r["kind"]
                for r in rows(
                    "SELECT m.kind FROM chat_messages m JOIN chat_sessions s"
                    " ON s.session_id = m.session_id WHERE s.user_id = ? ORDER BY m.id"
                )
            ],
            "action_decisions": [
                (r["tool_call_id"], r["decision"])
                for r in rows(
                    "SELECT tool_call_id, decision FROM action_decisions"
                    " WHERE user_id = ? ORDER BY id"
                )
            ],
        }


def _http(response) -> tuple:
    """Status, body (per-run fields masked) and `Retry-After` of one response."""
    body = response.json()
    if isinstance(body, dict):
        for field in _PER_RUN_FIELDS:
            if field in body:
                body[field] = "<per-run>"
    return (response.status_code, body, response.headers.get("retry-after"))


def _post(user: _User, **payload):
    client = TestClient(app, headers={"Authorization": f"Bearer {user.token}"})
    return client.post("/query", json=payload)


# --- scenarios: each arms the fault at the PRD's "when" and returns an Observation ---

Arm = Callable[[], None]
Scenario = Callable[[_User, Arm], Awaitable[Observation]]

_PROMPT = "What is 2+2?"


async def _q_success(user, arm):
    arm()
    return Observation([_http(_post(user, prompt=_PROMPT))], _footprint(user.user_id))


async def _q_session(user, arm):
    session_id = create_chat_session(user.user_id, "hello")
    arm()
    return Observation(
        [_http(_post(user, prompt=_PROMPT, session_id=session_id))], _footprint(user.user_id)
    )


async def _q_duplicate_refusal(user, arm):
    first = _http(_post(user, prompt=_PROMPT))
    arm()  # between the two sends: the second is the refusal whose row is written
    second = _http(_post(user, prompt=_PROMPT))
    return Observation([first, second], _footprint(user.user_id))


async def _q_foreign_session(user, arm):
    owner = _new_user(f"owner-of-{user.user_id.split('@')[0]}")
    foreign = create_chat_session(owner.user_id, "not yours")
    arm()
    return Observation(
        [_http(_post(user, prompt=_PROMPT, session_id=foreign))], _footprint(user.user_id)
    )


def _conversation(user, upstream):
    identity = Identity(user.user_id, "user")
    return query_pipeline.run_conversation(
        identity=identity, messages=[Message("user", "list files")], device=None,
        model="gpt-4", openrouter_api_key=None, call_openrouter=upstream, tools=_TOOL_PARAMS,
    )


async def _tools(user, arm):
    arm()
    try:
        result = _conversation(user, _Upstream("", _READ, _SHELL))
        outcome = ("released", result.model_dump(exclude=set(_PER_RUN_FIELDS)))
        assert _HEX.match(result.audit_ref) and result.audit_id is not None
    except ActionAuditError as exc:
        outcome = ("raised", type(exc).__name__)
    return Observation(outcome, _footprint(user.user_id))


def _chat_state(user) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user.user_id
    state._token = user.token
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    await type(state).event_handlers["send"].fn(state)  # bypasses the chain guard


def _chat_outcome(state: ChatState) -> list:
    return [
        [(m.kind, m.content, m.detail) for m in state.messages],
        state.pending,
        state.transcript_error,
        state.sessions_error,
    ]


async def _chat_first(user, arm):
    state = _chat_state(user)
    arm()
    await _send(state, _PROMPT)
    return Observation(_chat_outcome(state), _footprint(user.user_id))


async def _chat_second(user, arm):
    state = _chat_state(user)
    await _send(state, _PROMPT)
    arm()
    await _send(state, "and 3+3?")
    return Observation(_chat_outcome(state), _footprint(user.user_id))


def _released(obs: Observation) -> bool:
    return obs.outcome[0][0] == 200 and obs.outcome[0][1].get("status") == "SUCCESS"


@dataclass(frozen=True)
class Case:
    id: str
    prefix: str  # normalised, upper-cased start of the SQL the fault is aimed at
    nth: int
    scenario: Scenario
    healthy: Callable[[Observation], bool]  # the fault-free run did what the case means
    setup: tuple = ()  # faults that are the scenario's precondition, in every run


def _chat_healthy(obs: Observation) -> bool:
    kinds = [kind for kind, _, _ in obs.outcome[0]]
    return kinds[-2:] == ["user", "assistant"] and obs.outcome[2] == "" and obs.outcome[3] == ""


_CASES = [
    Case("s01_identity", "SELECT * FROM USERS WHERE TOKEN_HASH", 1, _q_success, _released),
    Case("s02_session_owns", "SELECT * FROM CHAT_SESSIONS WHERE SESSION_ID", 1, _q_session, _released),
    Case("s03_history_read", "SELECT * FROM CHAT_MESSAGES", 1, _chat_second, _chat_healthy),
    Case("s04_admit", "INSERT INTO USAGE_DAILY", 1, _q_success, _released),
    Case("s05_duplicate_lookup", "SELECT TIMESTAMP FROM AUDIT_LOGS", 1, _q_success, _released),
    Case(
        "s06a_refusal_row_duplicate", "INSERT INTO AUDIT_LOGS", 1, _q_duplicate_refusal,
        lambda o: o.outcome[1][1].get("status") == "BLOCKED",
    ),
    Case(
        "s06b_refusal_row_foreign_session", "INSERT INTO AUDIT_LOGS", 1, _q_foreign_session,
        lambda o: o.outcome[0][0] == 403,
    ),
    Case("s07_charge", "UPDATE USAGE_DAILY SET INPUT_TOKENS", 1, _q_success, _released),
    Case("s08_success_row", "INSERT INTO AUDIT_LOGS", 1, _q_success, _released),
    Case(
        "s09_decisions_block", "INSERT INTO ACTION_DECISIONS", 2, _tools,
        lambda o: o.outcome[0] == "released" and len(o.footprint["action_decisions"]) == 2,
    ),
    Case(
        "s10_mark_failed", "UPDATE AUDIT_LOGS SET SUCCESS = 0", 1, _tools,
        lambda o: o.outcome == ("raised", "ActionAuditError")
        and o.footprint["audit_logs"][0][0] == 0,
        # The decisions write fails by a constraint (a STATEMENT, never retried), so the
        # pipeline marks the audit row failed: the statement under test.
        setup=(Fault(UNIQUE_SESSION_ID, sql="INSERT INTO ACTION_DECISIONS"),),
    ),
    Case("s11_create_session", "INSERT INTO CHAT_SESSIONS", 1, _chat_first, _chat_healthy),
    Case("s12_append_message", "INSERT INTO CHAT_MESSAGES", 1, _chat_second, _chat_healthy),
    Case("s13_touch", "UPDATE CHAT_SESSIONS SET UPDATED_AT", 1, _chat_second, _chat_healthy),
    Case("s14_session_reread", "SELECT * FROM CHAT_SESSIONS WHERE SESSION_ID", 1, _chat_second, _chat_healthy),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.id)
async def test_each_statement_is_absorbed_when_it_provably_did_not_run(case, faulty_db, upstream):
    """Section 6.3, one statement: a blip on it is invisible to the client (AC 1)."""
    # The tools cases call `run_conversation` with a scripted upstream of their own.
    def run_setup():
        for fault in case.setup:
            faulty_db.add(dataclasses.replace(fault))  # a fresh object: counts are per object

    run_setup()
    baseline = await case.scenario(_new_user(f"{case.id}-base"), lambda: None)
    assert case.healthy(baseline), f"{case.id}: the fault-free run is not the case's scenario: {baseline}"
    assert len(faulty_db.fired) == len(case.setup)

    for klass, text in _CLASSES:
        run_setup()
        fired_before, connects_before = len(faulty_db.fired), faulty_db.connects
        fault = Fault(text, sql=case.prefix, nth=case.nth)

        observed = await case.scenario(
            _new_user(f"{case.id}-{klass.lower()}"),
            lambda: faulty_db.add(dataclasses.replace(fault)),
        )

        fired = faulty_db.fired[fired_before:]
        assert fired == [*case.setup, fault], f"{case.id}/{klass}: the fault did not fire where aimed"
        assert faulty_db.connects > connects_before, f"{case.id}/{klass}: no fresh client was built"
        assert observed.outcome == baseline.outcome, f"{case.id}/{klass}: response differs"
        assert observed.footprint == baseline.footprint, f"{case.id}/{klass}: rows differ"


# --- pure: the two harness additions (Fault.follows, FaultScript.clear) ------------


def test_a_commit_fault_with_follows_matches_only_after_that_statement():
    fault = Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after", follows="insert into usage_daily")

    assert fault.matches("commit", "", "\n  INSERT INTO usage_daily (user_id)\n VALUES (?)")
    assert not fault.matches("commit", "", "SELECT * FROM users")
    assert not fault.matches("commit", "", "")  # a commit with no statement before it
    assert not fault.matches("execute", "INSERT INTO usage_daily", "INSERT INTO usage_daily")


def test_a_commit_fault_without_follows_matches_every_commit():
    fault = Fault(NAMESPACE_SHUTDOWN_503, op="commit")

    assert fault.matches("commit", "", "") and fault.matches("commit", "", "SELECT 1")


def test_follows_counts_only_the_commits_it_matches():
    script = FaultScript(Fault(NAMESPACE_SHUTDOWN_503, op="commit", follows="UPDATE a", nth=2))

    outcomes = [
        script._decide("commit", last_sql=last)
        for last in ("UPDATE a SET x", "INSERT INTO b", "UPDATE a SET y", "UPDATE a SET z")
    ]

    assert [o is not None for o in outcomes] == [False, False, True, False]


def test_clear_ends_the_outage_and_resets_the_counts():
    fault = Fault(CONNECT_REFUSED, sql="SELECT 1", times=5)
    script = FaultScript(fault)
    assert script._decide("execute", "SELECT 1") is fault

    script.clear()

    assert script._decide("execute", "SELECT 1") is None
    assert script.fired == [fault]  # the record of what fired is history, not state
    script.add(Fault(CONNECT_REFUSED, sql="SELECT 1"))
    assert script._decide("execute", "SELECT 1") is not None  # a new outage counts from one


# --- OUTCOME_UNKNOWN after the effect landed (D3, spike Q1) ----------------------


def _landed(prefix: str) -> Fault:
    return Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after", follows=prefix)


def _retry_lines(caplog):
    return [r for r in caplog.records if r.name == _LOG and "retry op=" in r.getMessage()]


def _usage(user_id):
    return _footprint(user_id)["usage_daily"]


def test_a_landed_admit_is_counted_once_and_the_request_fails_closed(faulty_db, upstream, caplog):
    caplog.set_level(logging.INFO, logger=_LOG)
    user = _new_user("landed-admit")
    faulty_db.add(_landed("INSERT INTO USAGE_DAILY"))

    response = _post(user, prompt=_PROMPT)

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_NOT_SENT_DETAIL}
    assert "retry-after" in response.headers
    assert "Hrana" not in response.text and "Namespace" not in response.text  # no driver text
    assert _usage(user.user_id)[0][0] == 1  # counted once: the landed attempt
    assert faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 1  # never replayed
    assert upstream.sent == 0  # nothing left for the model
    assert _footprint(user.user_id)["audit_logs"] == []
    assert _retry_lines(caplog) == []  # OUTCOME_UNKNOWN on a counter is not retried


@pytest.mark.asyncio
async def test_a_landed_charge_is_counted_once_and_the_answer_is_released(faulty_db, upstream):
    baseline = await _q_success(_new_user("landed-charge-base"), lambda: None)
    base_charges = faulty_db.forwarded("UPDATE USAGE_DAILY")
    assert _released(baseline) and base_charges == 1
    user = _new_user("landed-charge")

    observed = await _q_success(user, lambda: faulty_db.add(_landed("UPDATE USAGE_DAILY")))

    assert observed.outcome == baseline.outcome  # charge fails open (PRD 6.3 row 7)
    assert observed.footprint == baseline.footprint  # one attempt, one charge, one audit row
    assert faulty_db.forwarded("UPDATE USAGE_DAILY") - base_charges == 1  # not replayed


@pytest.mark.asyncio
async def test_a_landed_append_is_one_message_not_two(faulty_db, upstream):
    baseline_user = _new_user("landed-append-base")
    before = faulty_db.forwarded("INSERT INTO CHAT_MESSAGES")
    baseline = await _chat_second(baseline_user, lambda: None)
    base_appends = faulty_db.forwarded("INSERT INTO CHAT_MESSAGES") - before
    # Send 1 saves only its assistant bubble (no session yet when the user bubble is
    # shown); send 2 saves both.
    assert base_appends == 3

    before = faulty_db.forwarded("INSERT INTO CHAT_MESSAGES")
    user = _new_user("landed-append")
    observed = await _chat_second(user, lambda: faulty_db.add(_landed("INSERT INTO CHAT_MESSAGES")))

    assert faulty_db.forwarded("INSERT INTO CHAT_MESSAGES") - before == base_appends  # no replay
    assert observed.footprint["chat_messages"] == baseline.footprint["chat_messages"]
    assert [kind for kind, _, _ in observed.outcome[0]] == [kind for kind, _, _ in baseline.outcome[0]]
    # The faulted append is one message after a reload too (nothing duplicated).
    from app.services import chat_sessions

    session = next(
        s for s in chat_sessions.list_for(Identity(user.user_id, "user"))
    )
    stored = chat_sessions.messages_for(Identity(user.user_id, "user"), session.session_id)
    assert [m.kind for m in stored] == baseline.footprint["chat_messages"]


@pytest.mark.asyncio
async def test_a_landed_audit_row_is_replayed_to_the_same_row(faulty_db, upstream):
    """The control: the rule is "the kind decides", not "never retry" (D3, D5)."""
    baseline = await _q_success(_new_user("landed-audit-base"), lambda: None)
    before = faulty_db.forwarded("INSERT INTO AUDIT_LOGS")
    assert before == 1
    user = _new_user("landed-audit")

    observed = await _q_success(user, lambda: faulty_db.add(_landed("INSERT INTO AUDIT_LOGS")))

    assert observed.outcome == baseline.outcome
    assert observed.footprint == baseline.footprint  # exactly one audit row for the user
    assert faulty_db.forwarded("INSERT INTO AUDIT_LOGS") - before == 2  # replayed, keyed


# --- an in-flight request across an outage (AC 3, Section 11 bullet 4) -------------


@pytest.fixture
def journal(tmp_path):
    """The module slot, open under `tmp_path` and always closed (the conftest fails a leak)."""
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 1 << 20, 2)
    yield opened
    audit_journal.close_journal()


@pytest.mark.parametrize("breaker_opened", [False, True], ids=["plain", "breaker_opened"])
def test_an_in_flight_request_across_an_outage_is_journaled_and_drains_to_one_row(
    faulty_db, journal, upstream, monkeypatch, breaker_opened
):
    user = _new_user("outage")
    # The request is past steps 1-4 (identity, admit, duplicate lookup: healthy) when the
    # database goes away: the charge and the audit row both meet a refused connection.
    faulty_db.add(
        Fault(CONNECT_REFUSED, sql="UPDATE USAGE_DAILY", times=20),
        Fault(CONNECT_REFUSED, sql="INSERT INTO AUDIT_LOGS", times=20),
    )

    response = _post(user, prompt=_PROMPT)

    body = response.json()
    assert response.status_code == 200 and body["audit_id"] is None
    assert _HEX.match(body["audit_ref"]) and upstream.sent == 1
    (entry,) = journal.pending()
    assert entry.write_id == body["audit_ref"]
    original_ts = entry.audit.timestamp
    footprint = _footprint(user.user_id)
    assert footprint["audit_logs"] == []  # the row exists only in the journal
    assert footprint["usage_daily"][0][1:] == (0, 0, 0)  # the charge failed open

    faulty_db.clear()  # the database is back
    forwarded = faulty_db.forwarded("INSERT INTO AUDIT_LOGS")
    if breaker_opened:
        now = [0.0]
        breaker = CircuitBreaker(
            "storage", 5, 10.0, clock=lambda: now[0], probe=database._probe_fresh_client
        )
        monkeypatch.setattr(database, "_storage_breaker", breaker)
        breaker.force_open(10)
        now[0] = 5.0
        assert journal_drainer.drain_once(journal) is journal_drainer.DrainOutcome.BREAKER_OPEN
        assert faulty_db.forwarded("INSERT INTO AUDIT_LOGS") == forwarded  # no network while open
        assert len(journal.pending()) == 1
        now[0] = 11.0  # the window is over: the breaker's own probe closes it on this call

    assert journal_drainer.drain_once(journal) is journal_drainer.DrainOutcome.DRAINED

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT timestamp FROM audit_logs WHERE write_id = ?", (body["audit_ref"],)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]
    assert len(rows) == 1 and total == 1
    assert rows[0]["timestamp"] == original_ts  # the event time, not the landing time (6.4)
    assert journal.pending() == []
    assert journal_drainer.drain_once(journal) is journal_drainer.DrainOutcome.EMPTY
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"] == 1
