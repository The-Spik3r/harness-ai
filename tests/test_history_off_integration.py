"""`CHAT_HISTORY_ENABLED=false`, driven through the application rather than the service.

PRD-008 Section 11 lists the off state as a functional requirement, in one
sentence: "`CHAT_HISTORY_ENABLED=false` writes no row, reads no row, renders no
rail, and leaves the chat fully working." Three of those four clauses are about
data, and this module is where they are proven. The fourth -- "renders no rail"
-- is `tests/test_session_rail.py`'s; both halves are needed for PRD Risk 1's
mitigation to be real, and neither substitutes for the other.

**What this claims that `tests/test_chat_sessions.py` does not.** That module
proves the *service* issues no statement with the flag off, function by
function, against a tripwire. This one drives the **application** -- a full send
through `ChatState`, and `POST /query` through `TestClient` -- and asserts the
same absence one layer out, where a caller that branched on the flag, or reached
past the service into `app/db/database.py`, would show up and the service's own
tests would stay green. `app/services/chat_sessions.py` is one module's promise;
this is the promise the deployment actually makes.

**Absence of calls, not absence of rows.** A service that called the database
and discarded the result would satisfy every `COUNT(*) == 0` assertion here and
would still be reading under a flag that says it does not. `_Tripwire` below is
therefore the whole of the read-path section, and it is also what makes the
write assertions mean something: the empty tables are corroboration, not the
evidence.

**Why this module is in-process where `tests/test_two_instance_smoke.py` is
not.** Every flag guard is read at call time from `settings`
(`app/services/chat_sessions.py`, ten functions, ten guards), so `monkeypatch`
reaches all of them without a module reload -- pinned by
`tests/test_chat_sessions.py::test_the_flag_is_read_at_call_time_not_captured_at_import`.
A subprocess would close the environment-variable seam instead, and that seam is
already closed by `tests/test_config.py`'s `CHAT_HISTORY_ENABLED="false"` case;
what a subprocess would *cost* is `_Tripwire`, which cannot observe calls it
cannot reach. The instrument follows the claim.

Running it needs the same local libSQL dev server the rest of the suite uses
(`tests/conftest.py`), and no Turso account. See `_INVARIANTS` at the bottom.
"""

import dataclasses
import os
import uuid

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import (
    count_audit_logs,
    create_chat_session,
    get_audit_log,
    get_connection,
    insert_user,
)
from app.db.models import StoredMessage, User
from app.main import app
from app.services import chat_sessions
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.state import ChatState

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}

client = TestClient(app, headers=_AUTH_HEADERS)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


class _Tripwire:
    """A stand-in for `app.db.database` on which every access is a failure.

    `tests/test_chat_sessions.py:1011`'s, restated rather than imported:
    cross-importing between test modules is not this suite's idiom, and the
    failure message wants to name *this* module's subject -- a read path in the
    application, not a service function.

    `__getattr__` fires on the attribute lookup, which is *before* the call, so
    a result that is never used is still caught. Deliberately not a `Mock`: a
    Mock records and returns another Mock, so the test would have to remember to
    assert `not called` afterwards, and a forgotten assertion is a green test.
    """

    def __getattr__(self, name: str):
        raise AssertionError(
            f"a read path reached database.{name} with CHAT_HISTORY_ENABLED off"
        )


class _Recording:
    """`database.get_connection`'s result, with every statement recorded.

    `tests/test_two_instance_smoke.py:163`'s proxy, itself `tests/test_db.py:967`'s.
    `__enter__`/`__exit__` are not decoration: `app/db/database.py`'s `_session()`
    does `with conn:`, so a proxy without them turns every measured write into an
    `AttributeError` instead of a measurement.
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


def _identity(user_id: str = _AUTH_USER_ID) -> Identity:
    return Identity(user_id=user_id, role="user")


def _make_state(user_id: str = _AUTH_USER_ID, token: str = _AUTH_TOKEN) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    state._token = token
    return state


def _handler(state: ChatState, name: str):
    return type(state).event_handlers[name].fn


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    await _handler(state, "send")(state)  # bypasses the background-task chain guard


def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _count(table: str) -> int:
    with get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _last_audit_row():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return get_audit_log(row["id"])


@pytest.fixture
def history_off(monkeypatch):
    """The flag off, and nothing else.

    Deliberately not the service suite's fixture of the same name, which also
    installs the tripwire. Here the two halves are separate because the write
    tests need a *real* database to count rows on, and installing a tripwire
    would make "no row was written" unobservable.
    """
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)


@pytest.fixture
def tripwired(monkeypatch):
    """The flag off, and `chat_sessions.database` replaced by the tripwire."""
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())


# --------------------------------------------------------------------------
# AC 4 -- a full send writes no transcript, and the rest is unchanged
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_full_send_with_history_off_writes_no_session_and_no_message(
    temp_db, monkeypatch, history_off
):
    """AC 4, driven end to end through the real pipeline.

    Only `call_openrouter` is faked, exactly as `tests/test_chat_state.py` leaves
    it: a faked `run_query` would write no audit row, and "the audit row is
    written as normal" would then be a claim about a stub. PII redaction is left
    real for the same reason.
    """
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

    state = _make_state()
    await _send(state, "what is the retention policy")

    assert _count("chat_sessions") == 0
    assert _count("chat_messages") == 0

    # The audit row is written as normal -- the flag governs the transcript, not
    # the record of what was asked.
    assert count_audit_logs() == 1
    row = _last_audit_row()
    assert row.user_id == _AUTH_USER_ID
    assert row.success is True
    assert row.session_id is None

    # "leaves the chat fully working"
    assert [message.kind for message in state.messages] == ["user", "assistant"]
    assert state.active_session_id == ""
    assert state.transcript_error == ""
    assert state.sessions_error == ""
    assert state.pending is False


def test_post_query_with_history_off_writes_no_transcript_row(
    temp_db, monkeypatch, history_off
):
    """The API ingress never wrote transcript rows and must not start.

    Worth its own test rather than riding on the `ChatState` one above: the two
    ingresses reach `chat_sessions` through different callers, and PRD Section 9
    holds them to the same behaviour.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    response = client.post("/query", json={"prompt": "a question over the API"})

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert _count("chat_sessions") == 0
    assert _count("chat_messages") == 0
    assert count_audit_logs() == 1


def test_the_response_and_the_audit_row_are_what_they_were_with_history_on(
    temp_db, monkeypatch
):
    """AC 4's "the response is unchanged", as one comparison rather than two
    literals.

    The same prompt is sent twice, once under each flag state, and the two
    results are compared field for field. `audit_logs` is emptied in between for
    a reason that would otherwise silently gut the test: the duplicate detector
    would recognise the second send and answer `BLOCKED`, and two responses of
    different kinds would compare unequal for a reason that has nothing to do
    with the flag.

    `dataclasses.asdict` makes the audit comparison one `==` over twenty fields
    rather than twenty assertions, so a column this story never thought about is
    covered too. `id` and `timestamp` are dropped because they are the two
    values that *must* differ between two rows written at two moments.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    prompt = "the same question, asked under both flag states"

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    off_body = client.post("/query", json={"prompt": prompt}).json()
    off_row = dataclasses.asdict(_last_audit_row())

    with get_connection() as conn:
        conn.execute("DELETE FROM audit_logs")

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)
    on_body = client.post("/query", json={"prompt": prompt}).json()
    on_row = dataclasses.asdict(_last_audit_row())

    assert off_body["status"] == "SUCCESS"
    assert {k: v for k, v in off_body.items() if k != "audit_id"} == {
        k: v for k, v in on_body.items() if k != "audit_id"
    }
    assert isinstance(off_body["audit_id"], int)

    volatile = ("id", "timestamp")
    assert {k: v for k, v in off_row.items() if k not in volatile} == {
        k: v for k, v in on_row.items() if k not in volatile
    }


# --------------------------------------------------------------------------
# AC 5 -- the read paths reach the database module for nothing at all
# --------------------------------------------------------------------------


def _seed_a_conversation() -> str:
    """One session with one message, written with the flag on.

    Every read test below seeds first. A tripwire over an empty database proves
    nothing: there would be nothing to read whether or not the guard held.
    """
    session_id = create_chat_session(_AUTH_USER_ID, "A chat from before the flag")
    chat_sessions.append_message(
        _identity(),
        session_id,
        StoredMessage(session_id=session_id, kind="user", content="hola"),
    )
    return session_id


@pytest.mark.asyncio
async def test_login_reads_no_session_and_no_transcript_when_history_is_off(
    temp_db, tripwired
):
    """AC 5 on the path a user takes without asking for anything: signing in."""
    _seed_a_conversation()

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await _handler(state, "login")(state)

    assert state.user_id == _AUTH_USER_ID
    assert state.sessions == []
    assert state.sessions_total == 0
    assert state.messages == []
    assert state.active_session_id == ""
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_selecting_a_session_reads_nothing_when_history_is_off(
    temp_db, monkeypatch
):
    """AC 5 on the explicit read: a session id the client asks to open.

    Seeded before the tripwire is installed, and the id kept -- this is the one
    read path where the caller supplies a real, existing, owned id, so a guard
    that only held for unknown ids would pass everywhere else and fail here.
    """
    session_id = _seed_a_conversation()

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())

    state = _make_state()
    await _handler(state, "select_session")(state, session_id)

    assert state.messages == []
    assert state.transcript_error == ""


@pytest.mark.asyncio
async def test_retry_sessions_reads_nothing_when_history_is_off(temp_db, monkeypatch):
    """AC 5 on the one read a user can trigger repeatedly.

    The rail's fault state offers a retry, and a retry that reached the store
    once per click would be the loudest possible violation of a flag that says
    nothing is read.
    """
    _seed_a_conversation()

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())

    state = _make_state()
    state.sessions_error = "list_for failed: store is down"
    await _handler(state, "retry_sessions")(state)

    assert state.sessions == []
    assert state.sessions_total == 0
    assert state.sessions_error == ""


def test_post_query_consults_no_row_for_a_supplied_session_id_when_history_is_off(
    temp_db, monkeypatch, tripwired
):
    """AC 5's one path outside `ChatState`, and the only one where a regression
    would be silent.

    `app/routers/query.py` asks `chat_sessions.owns()` about every supplied id.
    With the flag off that answer is `True` without a statement -- STORY-010
    AC 7: "the ownership check is a no-op and the id is written to the audit row
    as supplied -- the flag governs the transcript, not the audit column". A
    guard that reached the store here would either 403 a legitimate send or read
    a row under a flag that forbids it, and only the first would be visible.
    """
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    supplied = str(uuid.uuid4())

    response = client.post(
        "/query", json={"prompt": "a question naming a session", "session_id": supplied}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert _last_audit_row().session_id == supplied


@pytest.mark.asyncio
async def test_no_read_path_touches_the_database_module_when_history_is_off(
    temp_db, monkeypatch
):
    """AC 5 over every read path at once.

    The tests above assert what each path returns; this asserts the property for
    all of them together, so a fifth read path added later fails here even if
    nobody remembers to give it a case of its own. The tripwire's
    `AssertionError` names the attribute, so the failure says which call
    appeared rather than only that one did.
    """
    session_id = _seed_a_conversation()

    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())

    signed_in = ChatState(_reflex_internal_init=True)
    signed_in.token_input = _AUTH_TOKEN
    await _handler(signed_in, "login")(signed_in)

    state = _make_state()
    await _handler(state, "select_session")(state, session_id)
    await _handler(state, "retry_sessions")(state)

    assert (
        client.post(
            "/query", json={"prompt": "and one over the API", "session_id": session_id}
        ).status_code
        == 200
    )


# --------------------------------------------------------------------------
# AC 6 -- flipping the flag back resumes persistence, with no migration
# --------------------------------------------------------------------------

#: DDL. None of it may appear on the resumed send: "no restart-time migration"
#: is the claim, and a `CREATE TABLE IF NOT EXISTS` issued lazily on first write
#: would satisfy every other assertion in the test below.
_MIGRATION_VERBS = ("ALTER", "CREATE", "DROP")


@pytest.mark.asyncio
async def test_persistence_resumes_when_the_flag_is_flipped_back(temp_db, monkeypatch):
    """AC 6, in one process and without a restart.

    `init_db()` is deliberately *not* called between the two sends, and nothing
    is rebuilt. That omission is the claim: an implementation that needed a
    migration when the flag came back would have nowhere to run it, and this
    test is the shape of the deployment where an operator flips an environment
    variable and reloads.

    `tests/test_db.py::test_init_db_issues_no_alter_when_schema_is_current` makes
    the steady-state claim for `init_db()`; this makes it for the flag flip,
    which is the path this story is about.
    """
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    off_state = _make_state()
    await _send(off_state, "a turn that is not recorded")
    assert _count("chat_sessions") == 0
    assert _count("chat_messages") == 0

    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)

    statements: list[str] = []
    real_get_connection = chat_state_mod.chat_sessions.database.get_connection
    monkeypatch.setattr(
        chat_state_mod.chat_sessions.database,
        "get_connection",
        lambda: _Recording(real_get_connection(), statements),
    )

    state = _make_state()
    await _send(state, "a turn that is recorded again")

    assert state.active_session_id != ""
    assert state.transcript_error == "", "the resumed send reported an error"
    assert state.sessions_error == ""

    assert _count("chat_sessions") == 1
    restored = chat_sessions.messages_for(_identity(), state.active_session_id)
    assert [message.kind for message in restored] == ["assistant"], [
        message.kind for message in restored
    ]
    assert restored[0].content == "Hi there!"

    offenders = [
        statement
        for statement in statements
        if statement.strip().upper().startswith(_MIGRATION_VERBS)
    ]
    assert offenders == [], f"the resumed send issued a migration: {offenders}"
    assert statements, "the resumed send issued no statement at all"


# --------------------------------------------------------------------------
# AC 8 -- what keeps this offline
# --------------------------------------------------------------------------

#: Constraints this module holds itself to, recorded for the same reason
#: `tests/test_two_instance_smoke.py` records its own:
#:
#:  1. The endpoint comes from `tests/conftest.py` alone, so
#:     `HARNESS_TEST_LIBSQL_URL` redirects this module with the rest of the
#:     suite. Nothing here names a hosted Turso database and no test needs an
#:     account.
#:  2. No `time.sleep`, no polling, and no wall-clock value asserted as a bound.
#:  3. Every "nothing was read" claim is carried by `_Tripwire`, never by an
#:     empty return value alone -- an empty database returns empty either way.
#:  4. Every "nothing was written" claim is carried by a real database with real
#:     rows countable on it, which is why the flag fixture and the tripwire
#:     fixture are separate.
_INVARIANTS = (
    "no hosted database",
    "no sleep",
    "no absence proven by an empty result",
    "no write claim proven against a tripwire",
)
