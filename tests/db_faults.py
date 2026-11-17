"""A scripted fault injector for the storage layer (PRD-018 STORY-003, D18).

`FaultScript` wraps `libsql.connect` so every client `database._shared_client()`
builds is a `_FaultyClient`: a proxy over the real client that raises a scripted
`ValueError` from `execute`, `commit` or `rollback`, and otherwise forwards. It is
the harness STORY-004, 005 and 013 reuse; request it through the `faulty_db`
fixture in `tests/conftest.py`.

**A new `ValueError` is raised on every fire, never a wrapper.** The proxy stands
*under* `_Connection`, which labels the phase on whatever `ValueError` it sees, and
under `_translated()`, which classifies by `Hrana:` text. The application cannot tell
a fired fault from the driver (the `_RecordedClient` rule, `tests/conftest.py`).

**What each fault models.** Driver facts are from the STORY-001 spike
(`.agents/spikes/PRD-018-driver-failure-surface.md`); none is re-measured here.

| op / when | what the proxy does | models |
|---|---|---|
| `execute` / `before` | raises, does not forward | `NOT_SENT` (connect text) or `DEAD_STREAM` (baton / expired): the request did not run |
| `execute` / `after` | forwards, then raises | a response lost **inside an open transaction**. `__exit__`'s forwarded rollback undoes the statement (spike Q1: DML is not durable before `commit()`), so nothing lands |
| `commit` / `before` | `real.rollback()`, then raises | a server that dropped the stream and its transaction (spike V1: every dead-stream `commit` landed nothing). The real rollback also releases the write lock, so the retry does not wait ~2.1 s behind it (spike Q3) |
| `commit` / `after` | `real.commit()`, then raises | **the effect landed and the response was lost**: the only honest landed `OUTCOME_UNKNOWN` |
| `rollback` / either | `real.rollback()`, then raises | a dead-stream rollback masking the body's error (spike F4a) |

**Matching.** `execute` faults match by the whitespace-normalised, upper-cased
prefix `sql`; `commit` and `rollback` faults match by occurrence only, except that a
`commit` fault with `follows` set matches only when the last `execute` on that client
started with it (STORY-013: "the commit of `admit_usage`" without counting commits;
every unit commits, so the n-th commit moves whenever a read is added). `nth` is
1-based among the calls a fault matches, counted across every client the script
built, and `times` consecutive matches fail from there. The idle probe's
`SELECT 1` goes through the proxy too, so give an `execute` fault a specific `sql`
prefix rather than the empty one.

**Cursor-level `execute` is forwarded unscripted.** No `database.py` function uses
`conn.cursor()`; add the fault there if one ever does.

**Layering.** `install()` wraps whatever `libsql.connect` is at that moment, which
in a `db` test is PRD-014's recorder, so every forwarded call is still recorded and
a failing test still gets its `libsql diagnostics` section.
"""

import threading
from dataclasses import dataclass
from typing import Literal

import libsql

from app.db import database

# --- captured texts (spike rows; the class each classifies as is in brackets) ---

#: spike row 1 (F1): the request never left. [NOT_SENT]
CONNECT_REFUSED = (
    "Hrana: `http error: `error trying to connect: tcp connect error: "
    "Connection refused (os error 111)``"
)
#: spike rows 5 / 6 (F3a, F5): idle expiry. [DEAD_STREAM; NOT_SENT on `commit`]
STREAM_EXPIRED = (
    'Hrana: `api error: `status=400 Bad Request, body={"message":"The stream has '
    'expired due to inactivity","code":"STREAM_EXPIRED"}``'
)
#: spike rows 7-9 (F4a): the server restarted under an open stream. [DEAD_STREAM]
INVALID_BATON = "Hrana: `api error: `status=400 Bad Request, body=Received an invalid baton``"
#: spike row 10 (F3c): restart window. [OUTCOME_UNKNOWN]
NAMESPACE_SHUTDOWN_503 = (
    'Hrana: `api error: `status=503 Service Unavailable, '
    'body={"error":"Namespace store has shutdown"}``'
)
#: spike row 11 (F3c, F3d): restart window. [OUTCOME_UNKNOWN]
NAMESPACE_MISSING_404 = (
    'Hrana: `api error: `status=404 Not Found, '
    'body={"error":"Namespace `default` doesn\'t exist"}``'
)
#: spike row 15 (synthetic): text the classifier has never seen. [OUTCOME_UNKNOWN]
UNRECOGNISED = "Hrana: `something the classifier has never seen`"
#: the primary-key violation `create_chat_session` can meet on a replay. [STATEMENT]
UNIQUE_SESSION_ID = (
    'Hrana: `stream error: `Error { message: "SQLite error: UNIQUE constraint failed: '
    'chat_sessions.session_id", code: "SQLITE_CONSTRAINT" }``'
)


def _normalised(sql: str) -> str:
    return " ".join(str(sql).split()).upper()


@dataclass(frozen=True)
class Fault:
    """One scripted failure. See the module docstring for the semantics table."""

    text: str  # raised as a NEW ValueError(text) each time
    op: Literal["execute", "commit", "rollback"] = "execute"
    sql: str = ""  # execute only: prefix of the normalised SQL
    nth: int = 1  # 1-based, among the calls this fault matches
    times: int = 1  # consecutive matching calls that fail, from `nth`
    when: Literal["before", "after"] = "before"
    follows: str = ""  # commit only: prefix of the last execute on the same client

    def matches(self, op: str, sql: str, last_sql: str = "") -> bool:
        if op != self.op:
            return False
        if op == "commit":
            return _normalised(last_sql).startswith(self.follows.upper())
        return op != "execute" or _normalised(sql).startswith(self.sql.upper())


class FaultScript:
    """The faults to fire and a record of what reached the driver."""

    def __init__(self, *faults: Fault) -> None:
        self._lock = threading.Lock()
        self._faults: list[Fault] = list(faults)
        self._seen: dict[int, int] = {}  # id(fault) -> matches so far
        self.calls: list[tuple[str, str]] = []  # (op, first 60 chars of normalised SQL)
        self.fired: list[Fault] = []
        self.connects = 0
        self._forwarded: list[str] = []  # normalised SQL of executes the real client saw
        self._active = False

    def add(self, *faults: Fault) -> None:
        """Append faults mid-test (after seeding, say)."""
        with self._lock:
            self._faults.extend(faults)

    def clear(self) -> None:
        """Drop every fault and its match counts: the outage is over (STORY-013)."""
        with self._lock:
            self._faults.clear()
            self._seen.clear()

    def forwarded(self, sql_prefix: str) -> int:
        """How many executes starting with `sql_prefix` reached the real client."""
        prefix = sql_prefix.upper()
        with self._lock:
            return sum(1 for sql in self._forwarded if sql.startswith(prefix))

    def _decide(self, op: str, sql: str = "", last_sql: str = "") -> "Fault | None":
        """Record the call and return the fault that fires on it, if any."""
        with self._lock:
            self.calls.append((op, _normalised(sql)[:60]))
            for fault in self._faults:
                if not fault.matches(op, sql, last_sql):
                    continue
                seen = self._seen.get(id(fault), 0) + 1
                self._seen[id(fault)] = seen
                if fault.nth <= seen < fault.nth + fault.times:
                    self.fired.append(fault)
                    return fault
        return None

    def _note_forwarded(self, sql: str) -> None:
        with self._lock:
            self._forwarded.append(_normalised(sql))

    def install(self, monkeypatch) -> None:
        """Wrap the current `libsql.connect` and drop the cached client."""
        previous = libsql.connect
        self._active = True

        def connect(*args, **kwargs):
            real = previous(*args, **kwargs)
            if not self._active:
                return real
            with self._lock:
                self.connects += 1
            return _FaultyClient(real, self)

        monkeypatch.setattr(libsql, "connect", connect)
        database._invalidate_client()

    def uninstall(self) -> None:
        """Stop proxying and drop the cached client, so the next test starts clean."""
        self._active = False
        database._invalidate_client()


class _FaultyClient:
    """Forwards to the real client, raising the script's faults (module docstring)."""

    def __init__(self, real, script: FaultScript) -> None:
        self._real = real
        self._script = script
        self._last_sql = ""  # the last execute on this client, for `Fault.follows`

    def execute(self, sql, *parameters):
        self._last_sql = sql
        fault = self._script._decide("execute", sql)
        if fault is not None and fault.when == "before":
            raise ValueError(fault.text)
        self._script._note_forwarded(sql)
        cursor = self._real.execute(sql, *parameters)
        if fault is not None:
            raise ValueError(fault.text)
        return cursor

    def commit(self):
        fault = self._script._decide("commit", last_sql=self._last_sql)
        if fault is None:
            return self._real.commit()
        if fault.when == "after":
            self._real.commit()  # the effect landed; the response is what was lost
        else:
            self._real.rollback()  # the dropped stream took its transaction with it
        raise ValueError(fault.text)

    def rollback(self):
        fault = self._script._decide("rollback")
        if fault is None:
            return self._real.rollback()
        self._real.rollback()
        raise ValueError(fault.text)

    def __getattr__(self, name):
        return getattr(self._real, name)
