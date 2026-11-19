import json
import logging
import os
import random
import re
import socket
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Callable,
    Iterator,
    Literal,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
)
from urllib.parse import urlsplit

import libsql

from app.config import settings
from app.db.errors import (
    DatabaseAuthError,
    DatabaseUnreachableError,
    IntegrityError,
    MissingRelationError,
    StorageError,
    StorageUnavailableError,
)
from app.db.models import (
    ACTION_DECISION_VALUES,
    ACTION_DECISIONS_ADDED_COLUMNS,
    AUDIT_LOGS_ADDED_COLUMNS,
    CHAT_MESSAGES_ADDED_COLUMNS,
    CREATE_ACTION_DECISIONS_AUDIT_INDEX,
    CREATE_ACTION_DECISIONS_TABLE,
    CREATE_ACTION_DECISIONS_USER_TS_INDEX,
    CREATE_ACTION_DECISIONS_WRITE_ID_INDEX,
    CREATE_AUDIT_LOGS_DEDUP_INDEX,
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_AUDIT_LOGS_WRITE_ID_INDEX,
    CREATE_CHAT_MESSAGES_SESSION_INDEX,
    CREATE_CHAT_MESSAGES_TABLE,
    CREATE_CHAT_SESSIONS_TABLE,
    CREATE_CHAT_SESSIONS_USER_INDEX,
    CREATE_USAGE_DAILY_TABLE,
    CREATE_USERS_TABLE,
    CREATE_USERS_TOKEN_HASH_INDEX,
    USERS_ADDED_COLUMNS,
    ActionDecisionRow,
    AuditLog,
    ChatSession,
    StoredMessage,
    UsageAdmission,
    UsageDay,
    User,
)
from app.db import audit_journal, storage_counters
from app.db.storage_counters import CounterSnapshot
from app.services.circuit_breaker import BreakerOpen, BreakerStatus, CircuitBreaker

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_client_key: Optional[tuple[str, str]] = None
_client: Optional[Any] = None

#: `time.monotonic()` when the client was last handed out, for the idle gate
#: below. Stamped at acquire rather than when the last statement finished, so a
#: long transaction makes the next call look idler than it really was -- that
#: over-probes slightly and can never under-probe. `monotonic()` and not
#: `time.time()`, so a clock adjustment cannot suppress the probe indefinitely.
_client_used_at: float = 0.0

# PRD-008 STORY-024. How long the client may go without being handed out before
# it is proved rather than trusted. A **floor on how often we check**, not a
# model of the server's timeout, which libSQL publishes no constant for and
# which this repo cannot measure against a hosted endpoint.
#
# Against the local dev server the window was measured rather than guessed: a
# raw client survives a 10 s pause and is dead at 12 s. Five seconds is half of
# that, which is the property worth having -- any pause long enough to kill the
# stream is necessarily long enough to have opened the gate, so an expired
# stream is caught by the probe and never by the caller's statement. A hosted
# endpoint whose window is shorter would not break this: the `_translated()`
# arm still drops the dead client, and the call after it recovers.
#
# The cost is bounded: one extra `SELECT 1` -- ~1-4 ms against the local
# endpoint -- on a call that follows a pause, and nothing at all on a busy path,
# where the gate never opens.
#
# A module constant rather than a setting on purpose: a deployment knob whose
# wrong value silently restores the defect is not a knob worth having.
_IDLE_PROBE_AFTER_SECONDS = 5.0

# PRD-018 D5, Section 6.1 / 6.6. The retry budget of `_unit_of_work()`: how many
# times one storage operation may be run, how long it waits between runs, and how
# long after its first run it may still *start* another.
#
# Small on purpose. A dead stream is replaced on the first rebuild, so the one
# retry that matters is the first; the third attempt is slack for a rebuild that
# itself races a restart. The waits are **full jitter** -- `uniform(0, cap)` --
# so a burst of requests that all lost the same stream do not all come back on
# the same millisecond: at most 50 ms before the second attempt and 200 ms before
# the third, 250 ms of sleeping in the worst case. A budget this small is the
# point (6.6): a storage outage must be answered quickly with a refusal, not
# absorbed into a request that hangs.
#
# **The deadline gates starting an attempt. It cannot cut one already running.**
# The driver has no read timeout (spike F3a), so an attempt that stalls -- a
# contended first write holds ~2.1 s (spike Q3), a connect to a black hole ~21 s
# -- takes the time it takes, and the loop then sees that the deadline has
# passed and raises instead of starting another.
#
# Module constants rather than settings (O6) for the reason `_IDLE_PROBE_AFTER_SECONDS`
# is one: a deployment knob whose wrong value silently restores the defect is not
# a knob worth having.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_CAPS_SECONDS = (0.05, 0.2)
_RETRY_START_DEADLINE_SECONDS = 2.0


def _full_jitter(cap: float) -> float:
    return random.uniform(0.0, cap)


# The three seams of the retry loop, read at call time so a test can drive it with
# a fake clock and no real sleeping -- the mechanism every existing test already
# uses on `_shared_client` / `get_connection`. `_retry_jitter` is handed the
# **cap**, so a test can ask for the worst case (`lambda cap: cap`), for none
# (`0.0`), or record which caps were requested. `_retry_clock` is deliberately not
# `time.monotonic` itself, so a fake clock cannot disturb the idle gate above.
_retry_sleep: Callable[[float], None] = time.sleep
_retry_clock: Callable[[], float] = time.monotonic
_retry_jitter: Callable[[float], float] = _full_jitter

# PRD-018 D6, Section 6.5. The storage circuit breaker's parameters: five
# consecutive *operations* (not attempts) that ended in an infrastructure-class
# failure open it, and it stays open for ten seconds before one probe is let
# through. Constants rather than settings (O6), for the reason
# `_IDLE_PROBE_AFTER_SECONDS` is one. They are the storage instance's arguments,
# never the class's defaults: `CircuitBreaker` is shared with PRD-022 and has none.
_BREAKER_FAILURE_THRESHOLD = 5
_BREAKER_OPEN_SECONDS = 10.0


def _shared_client() -> Any:
    """The process-wide libSQL client, constructed once and reused.

    PRD-007 Section 6 Pattern 1: against a remote endpoint every construction is
    a TCP + TLS handshake, so connection-per-operation would make a single admin
    console load pay ten of them.

    **One client for the whole process, not one per thread.** STORY-006 measured
    both against the local server with eight threads writing concurrently: the
    shared client completed all 200 writes with no error, while a client per
    thread lost 169 of them to `TRANSACTION_TIMEOUT`. Independent clients contend
    for the database's single writer; one client serializes its own callers.
    That is what makes this safe to reach from `chat_ui/chat_ui/admin_state.py`'s
    `asyncio.to_thread(...)` worker threads, and it is why the obvious defensive
    move -- a thread-local client -- is the wrong one here.

    Keyed by URL and token: every test repoints `settings.DATABASE_URL` on the
    constructed `Settings` instance, and a client cached without regard to it
    would serve one test's reads from another test's endpoint.

    **Cached forever is not the same as usable forever (STORY-024).** The stream
    behind this client is server-side state the server expires when it goes
    quiet, and before this story nothing ever set `_client = None` -- so the
    first request after an idle period failed, and so did every request after
    it, until the process was restarted. An idle process was a dead one.

    So a client that has not been handed out for `_IDLE_PROBE_AFTER_SECONDS` is
    **proved before it is lent**, and a dead one is replaced once (`_proved()`).
    Validating here rather than around the caller's statement is what makes the
    recovery safe: it happens before `_session()` opens its transaction, so
    there is no partial work any of this could replay (AC 6). A statement that
    dies mid-transaction is handled the other way, by `_translated()`, which
    invalidates the cache and re-raises without retrying anything.

    A newly built client is not probed -- it has just opened its stream, and
    probing it would put a second statement on the boot path `init_db()`'s guard
    deliberately keeps at one.
    """
    global _client_key, _client, _client_used_at
    key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
    with _client_lock:
        if _client is None or _client_key != key:
            # Not closing the previous client: close() discards uncommitted work
            # (STORY-001 §2.2) and the key only changes under test.
            _client = libsql.connect(key[0], auth_token=key[1])
            _client_key = key
        elif time.monotonic() - _client_used_at >= _IDLE_PROBE_AFTER_SECONDS:
            _client = _proved(_client, key)
        _client_used_at = time.monotonic()
        return _client


def _proved(client: Any, key: tuple[str, str]) -> Any:
    """`client` if its stream still answers, otherwise one replacement.

    **Called with `_client_lock` already held, and it must stay that way.** Two
    threads that discovered a dead client together and rebuilt independently
    would produce the client-per-thread configuration STORY-006 measured losing
    169 of 200 writes to `TRANSACTION_TIMEOUT`. The cost is that the lock is held
    across one round trip on the idle path; those callers would serialize on the
    single client regardless.

    **The statement, not the function.** It issues `SELECT 1` on the raw client
    it was handed -- never through `get_connection()`, which re-enters
    `_shared_client()` and would deadlock on the non-reentrant `_client_lock`,
    and never through `check_database_reachable()`, which is a *boot-time*
    classifier that must keep failing loudly and which
    `tests/test_db.py::test_guard_does_not_run_outside_init_db` pins out of the
    operational path.

    **Any driver failure condemns the client here, which is broader than
    `_is_dead_stream()` on purpose.** A `SELECT 1` cannot fail for a statement
    reason: there is no table to be missing and no constraint to violate. So
    whatever the driver is complaining about, this client is not usable -- and
    a third way of saying "the stream is gone" would still be caught. A
    `ValueError` without the driver's prefix is our own code's and is re-raised
    untouched, exactly as `_translated()` treats one.

    **One replacement, never a loop.** The new client is not probed in turn, so
    an endpoint that is genuinely down surfaces through the caller's own
    statement as a `StorageError` (AC 2) instead of becoming a retry loop
    against a database nobody has fixed yet.
    """
    try:
        client.execute("SELECT 1").fetchone()
    except ValueError as exc:
        if _DRIVER_ERROR not in str(exc):
            raise
        # Dropped, not closed: close() discards uncommitted work rather than
        # flushing it (STORY-001 §2.2), and a dead stream has none to flush.
        return libsql.connect(key[0], auth_token=key[1])
    return client


def _invalidate_client(stale: Optional[Any] = None) -> None:
    """Drops the cached client so the next `_shared_client()` builds a fresh one.

    The recovery half that cannot live in `_shared_client()`: a stream can die
    between the probe and the statement, or during a long transaction, and
    without this the dead client stays cached and the *next* caller fails too.

    Takes `_client_lock` itself, because every mutation of `_client` happens
    under it. `stale` is an identity guard for callers that hold the client they
    found dead -- if another thread has already replaced it, this must not throw
    the good one away. `_translated()` has no client reference to pass (it is
    used standalone in `_add_missing_columns()` and `find_user_by_token_hash()`),
    so it drops whatever is cached; the cost of that rare over-drop is one extra
    construction on the next call, and construction stays serialized under the
    lock, so it is not the client-per-thread configuration either.

    It does not close what it drops, for the reason `_shared_client()` gives.
    """
    global _client_key, _client
    with _client_lock:
        if stale is None or _client is stale:
            _client = None
            _client_key = None


def _probe_fresh_client() -> bool:
    """The breaker's half-open probe: one `SELECT 1` on a brand-new client (PRD-018 6.5).

    Runs under `_client_lock` on a raw `libsql.connect`, never through
    `get_connection()` -- the `_proved()` rule: re-entering `_shared_client()`
    would deadlock on the non-reentrant lock -- and never through
    `check_database_reachable()`, which is the boot-time classifier (D17). On
    success the new client replaces the cached one, so the first request after
    recovery does not pay a second handshake. On a driver failure it returns
    `False` and leaves the cache alone. A `ValueError` without the driver's
    prefix is our own code's and is re-raised, as `_proved()` does.

    Called only by the breaker, which never holds its own lock while it runs the
    probe, so no thread holds both locks (see `CircuitBreaker`).
    """
    global _client_key, _client, _client_used_at
    key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
    with _client_lock:
        try:
            client = libsql.connect(key[0], auth_token=key[1])
            client.execute("SELECT 1").fetchone()
        except ValueError as exc:
            if _DRIVER_ERROR not in str(exc):
                raise
            return False
        _client, _client_key, _client_used_at = client, key, time.monotonic()
        return True


# One per process, matching the one client per process (`_shared_client`): `/query`,
# `/v1` and the chat UI share it in a Reflex deployment. `storage_status()`
# (STORY-012) reads `.status()`. Tests swap it per test
# (`tests/conftest.py::_fresh_storage_breaker`, which builds through
# `_new_storage_breaker()` so the swapped instance counts too).
def _count_breaker_open(frm: str, to: str, cls: str) -> None:
    """`breaker_opens`: every transition into open, a failed probe's re-open included."""
    if to == "open":
        storage_counters.breaker_opened()


def _new_storage_breaker() -> CircuitBreaker:
    """The storage breaker with its counter hook (PRD-018 D16, STORY-012)."""
    return CircuitBreaker(
        "storage",
        _BREAKER_FAILURE_THRESHOLD,
        _BREAKER_OPEN_SECONDS,
        probe=_probe_fresh_client,
        on_transition=_count_breaker_open,
    )


_storage_breaker = _new_storage_breaker()


class _Row:
    """A result row that answers both `row["timestamp"]` and `(count,) = row`.

    libSQL returns plain tuples and offers no `row_factory` hook (STORY-001
    §2.1), but `cursor.description` is populated -- for `SELECT *`, for aliased
    aggregates like `COUNT(*) AS n`, and for `PRAGMA table_info` alike. Mapping
    those names back on is what lets `_row_to_audit_log()`'s 20 named reads, the
    seven `row["n"]` counters and `_add_missing_columns()`'s `row["name"]` stay
    exactly as they were.

    Both a mapping and a sequence, like the `sqlite3.Row` it replaces: callers
    index it by name, and tests unpack it positionally.
    """

    __slots__ = ("_values", "_names")

    def __init__(self, values: tuple, names: dict) -> None:
        self._values = tuple(values)
        self._names = names

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                index = self._names[key]
            except KeyError:
                raise IndexError(f"No item with that key: {key!r}") from None
            return self._values[index]
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> list:
        return list(self._names)

    def __eq__(self, other) -> bool:
        if isinstance(other, _Row):
            return self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __repr__(self) -> str:
        return f"_Row({dict(zip(self._names, self._values))!r})"


class _Cursor:
    """The driver's cursor, made iterable and mapped through `_Row`.

    Two gaps to close (STORY-001 §2.5): the driver's cursor is **not iterable**,
    which `_add_missing_columns()` and four test modules rely on, and its rows
    are bare tuples.

    PRD-018 STORY-002 (D2): each driver call labels a `ValueError` it raises with
    the call's name via `_mark_phase()` and re-raises the same object, exactly as
    `_Connection` does. `__iter__` goes through `fetchall`, so it is covered.
    """

    __slots__ = ("_cursor", "_name_index")

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self._name_index: Optional[dict] = None

    def _names(self) -> dict:
        if self._name_index is None:
            description = self._cursor.description
            self._name_index = (
                {column[0]: index for index, column in enumerate(description)}
                if description
                else {}
            )
        return self._name_index

    def _wrap(self, values):
        return None if values is None else _Row(values, self._names())

    def execute(self, sql: str, *parameters) -> "_Cursor":
        try:
            self._cursor.execute(sql, *parameters)
        except ValueError as exc:
            _mark_phase(exc, "execute")
            raise
        self._name_index = None
        return self

    def fetchone(self) -> Optional[_Row]:
        try:
            values = self._cursor.fetchone()
        except ValueError as exc:
            _mark_phase(exc, "fetchone")
            raise
        return self._wrap(values)

    def fetchall(self) -> list:
        try:
            rows = self._cursor.fetchall()
        except ValueError as exc:
            _mark_phase(exc, "fetchall")
            raise
        return [self._wrap(values) for values in rows]

    def fetchmany(self, *args) -> list:
        try:
            rows = self._cursor.fetchmany(*args)
        except ValueError as exc:
            _mark_phase(exc, "fetchmany")
            raise
        return [self._wrap(values) for values in rows]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self) -> None:
        self._cursor.close()


class _Connection:
    """A transaction over the shared client, with the old block's semantics.

    `with get_connection() as conn:` still means "a transaction", never "a
    connection lifetime" -- the same thing `with sqlite3.Connection` meant. The
    commit is issued **explicitly** on exit rather than inherited from the
    driver's own context manager, which is PRD-007 Risk 1's mitigation: a write
    that leaves the block uncommitted is lost with no error and no warning
    (STORY-001 §2.2, re-verified by STORY-006).

    **PRD-018 STORY-002 (D2): each driver call labels a `ValueError` it raises
    with the call's name (`_mark_phase`) and re-raises the same object.** Type,
    message, `args` and identity are untouched, so `_translated()` and
    `_is_dead_stream()` behave as before; `_classify()` reads the label through
    `_phase_of()`. `__slots__` is unchanged on purpose: the phase rides on the
    exception, not on the connection, so it stays correct under concurrency and
    nesting. Do not "simplify" this into `raise StorageError(...) from exc`.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Any) -> None:
        self._client = client

    def execute(self, sql: str, *parameters) -> _Cursor:
        try:
            cursor = self._client.execute(sql, *parameters)
        except ValueError as exc:
            _mark_phase(exc, "execute")
            raise
        return _Cursor(cursor)

    def cursor(self) -> _Cursor:
        return _Cursor(self._client.cursor())

    def commit(self) -> None:
        try:
            self._client.commit()
        except ValueError as exc:
            _mark_phase(exc, "commit")
            raise

    def rollback(self) -> None:
        try:
            self._client.rollback()
        except ValueError as exc:
            _mark_phase(exc, "rollback")
            raise

    def close(self) -> None:
        """Deliberately a no-op.

        The client is shared by every caller in the process, so closing it here
        would strand the others -- and `close()` discards uncommitted work rather
        than flushing it (STORY-001 §2.2). Nothing in `app/db/` closes it; the
        process exit does.
        """

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        # Through `self.commit()` / `self.rollback()` so each call is recorded in
        # one place (PRD-018 STORY-002). A rollback that fails while the body is
        # already raising replaces the body's exception, as `with` always did; the
        # body's exception stays on `__context__` for `_failure_of()` to read.
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


def get_connection() -> _Connection:
    """A transaction handle over the process-wide client.

    Public because thirteen test modules open one directly. The signature is
    unchanged from the `sqlite3` version; only what it hands back moved, and the
    wrapper above exists so that nothing downstream can tell.

    PRD-018 STORY-002: a failure to obtain the client is labelled `connect`. That
    covers `libsql.connect` and anything `_proved()` re-raises.
    """
    try:
        client = _shared_client()
    except ValueError as exc:
        _mark_phase(exc, "connect")
        raise
    return _Connection(client)


# The driver states both conditions in the exception message and nowhere else.
# STORY-006 re-verified both patterns against the live endpoint rather than
# assuming them, and they match libSQL's text unchanged:
#   Hrana: `stream error: `Error { message: "SQLite error: UNIQUE constraint
#       failed: users.token_hash", code: "SQLITE_CONSTRAINT" }``
#   Hrana: `stream error: `Error { message: "SQLite error: no such table:
#       users", code: "SQLITE_UNKNOWN" }``
# Matching on the code is not an option: SQLITE_UNKNOWN covers both a missing
# table and a duplicate column, and SQLITE_CONSTRAINT covers both duplicates.
#   Hrana: `stream error: `Error { message: "SQLite error: duplicate column
#       name: pii_detected_input", code: "SQLITE_UNKNOWN" }``
# The third is the one STORY-007 needs, and it is why the second sentence above
# is not a footnote: `no such table` and `duplicate column name` arrive under
# the same SQLITE_UNKNOWN, so only the message separates "another instance
# already added this column" from "the table is gone".
_MISSING_RELATION = re.compile(r"no such table: (\w+)")
_CONSTRAINT = re.compile(r"constraint failed: ([\w.]+)")
_DUPLICATE_COLUMN = re.compile(r"duplicate column name: (\w+)")

# libSQL raises a bare `builtins.ValueError` for every failure -- there is no
# exception hierarchy to catch, and `libsql.Error` is not what gets raised
# (STORY-001 §3.5). Every one of them carries this prefix, including a failure
# to reach the server at all, so it is what separates a driver error from a
# genuine ValueError raised by our own code, which must not be swallowed.
_DRIVER_ERROR = "Hrana:"

# PRD-008 STORY-024. The stream is **server-side** state: HRANA_3_SPEC states
# that HTTP is stateless, so a stream lives on the server and is addressed by a
# baton the client presents on every request. `libsql-server`'s
# `hrana/http/stream.rs` returns `StreamExpired` for a handle it has expired and
# `BatonInvalid` for one it no longer has at all -- which is the same server code
# a hosted Turso endpoint runs, so this is Hrana's behaviour and not the local
# container's. Both mean the same thing operationally: no client holding that
# baton can be talked back into a working stream, and only a new client, which
# opens one with `baton: null`, recovers.
#
#   idle expiry, captured live (PRD-007 STORY-009 report, PRD-008 STORY-014):
#     Hrana: `api error: `status=400 Bad Request,
#       body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
#   after the server restarts, captured by restarting libSQL under a live
#   process (STORY-024) -- note the plain-text body, with no JSON and no `code`
#   field, which is a second reason the classifier reads message text:
#     Hrana: `api error: `status=400 Bad Request, body=Received an invalid baton``
#
# Pinned as literals for the same reason `_MISSING_RELATION` and `_CONSTRAINT`
# are: libSQL raises a bare `ValueError` and there is no type and no code to
# branch on (STORY-001 §3.5). Both spellings of the expiry are listed because
# the message carries the prose and the JSON body carries the code, and a driver
# that stopped quoting one would still quote the other.
_DEAD_STREAM = ("stream has expired", "stream_expired", "invalid baton")


def _is_dead_stream(message: str) -> bool:
    """True when the driver is reporting that the server no longer has the stream.

    Deliberately **narrow**, and narrower than the rule the probe in
    `_shared_client()` applies. This predicate decides whether a *statement*
    failure should discard the process-wide client, and a statement fails for
    statement reasons far more often than for connection ones: a
    `UNIQUE constraint failed` or a `no such table` must leave the client exactly
    where it is (STORY-024 AC 3), because throwing away a working client on a
    constraint violation would turn a correctly refused write into a reconnect.
    """
    haystack = message.lower()
    return any(marker in haystack for marker in _DEAD_STREAM)


def _constraint_of(exc: ValueError) -> Optional[str]:
    match = _CONSTRAINT.search(str(exc))
    return match.group(1) if match is not None else None


def _is_duplicate_column(exc: StorageError, name: str) -> bool:
    """True when the driver is reporting that `name` already exists.

    Narrow on two counts, both deliberate. It reads a `StorageError` -- the
    translated type, not the driver's bare `ValueError` -- so a `ValueError`
    raised by our own code can never reach it. And it requires the driver to
    name *the column we just tried to add*: a duplicate reported for some other
    column means the statement that failed was not the one we think, which is a
    real failure and must reach the caller, as must a permissions problem or an
    unreachable endpoint.
    """
    match = _DUPLICATE_COLUMN.search(str(exc))
    return match is not None and match.group(1) == name


# STORY-008. The credential can travel in the URL itself -- a libSQL endpoint
# accepts `?authToken=...` -- so anything that quotes the URL in a message quotes
# the token unless it is stripped first. `app/config.py:_scheme_of()` solves the
# same problem by quoting the scheme alone; the guard needs one segment more,
# because a message that says "cannot reach the database at libsql://" has not
# told the operator which database.
_AUTH_TOKEN_IN_URL = re.compile(r"(auth_?token=)[^&\s\"'`]+", re.IGNORECASE)
_REDACTED = "***"


def _safe_endpoint(url: str) -> str:
    """`scheme://host[:port]` -- no userinfo, no path, no query, no fragment.

    Everything a message is allowed to say about `DATABASE_URL`. The drop is
    positive rather than subtractive (build from the parts that are safe, never
    "remove the parts that are not"), so a URL shape nobody anticipated cannot
    smuggle a credential through: anything unparseable degrades to the scheme.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return "(unparseable DATABASE_URL)"

    if not parts.scheme:
        return "(unparseable DATABASE_URL)"

    # `hostname` and `port` are the parsed pieces; `netloc` would carry any
    # `user:password@` prefix straight into the message.
    host = parts.hostname or ""
    if not host:
        return f"{parts.scheme}://"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def _redacted(message: str) -> str:
    """Driver text with the credential removed, in both forms it can take.

    Belt and braces, deliberately. The driver formats the endpoint into its own
    `http error:` text, so a token carried in the query string arrives inside a
    message this module did not compose -- and a token configured through
    `TURSO_AUTH_TOKEN` can be echoed back by a server that quotes what it was
    sent. Neither is hypothetical enough to leave to chance: PRD Section 9 says
    the credential is "never logged, never echoed in error messages", and
    `tests/test_config.py:178` already treats the in-URL form as a real case.
    """
    scrubbed = _AUTH_TOKEN_IN_URL.sub(rf"\1{_REDACTED}", message)
    token = settings.TURSO_AUTH_TOKEN.strip()
    if token:
        scrubbed = scrubbed.replace(token, _REDACTED)
    return scrubbed


# The two boot-time failures, told apart by message text for the same reason
# `_MISSING_RELATION` above is: libSQL raises a bare `ValueError` for everything
# and the unreachable case carries **no `code:` field at all** (STORY-006's
# error-surface table), so there is no type and no code to branch on.
#
#   unreachable: `Hrana: `http error: error sending request for url
#       (http://127.0.0.1:1/v2/pipeline): ... Connection refused``  -- verified
#
# The auth case is **not** verified against a live Turso: the suite runs against
# a local libSQL primary, which takes no token and cannot produce a 401, and
# PRD Section 12 makes "no account needed" non-negotiable for the test
# infrastructure. These markers are therefore inference, and the fallback below
# is chosen accordingly. STORY-014's first real deployment is where to confirm
# them -- if the text differs, add the marker; the failure mode of a miss is a
# still-legible unreachable message, not a wrong one.
_AUTH_MARKERS = (
    "401",
    "unauthorized",
    "authentication",
    "auth token",
    "auth_token",
    "authtoken",
    "invalid token",
    "expired token",
    "permission denied",
)


def _classify_startup_failure(exc: Exception, endpoint: str) -> StorageError:
    """Which of the two boot-time failures this is, and what to tell an operator.

    **Unclassified failures fall to unreachable, never to auth.** The asymmetry
    is deliberate: telling an operator the endpoint is unreachable when the token
    was actually rejected costs them one wrong guess before they check the token,
    while telling them the token was rejected during a real outage sends them to
    rotate a credential that was fine.
    """
    detail = _redacted(str(exc))
    haystack = detail.lower()

    if any(marker in haystack for marker in _AUTH_MARKERS):
        return DatabaseAuthError(
            endpoint,
            f"TURSO_AUTH_TOKEN was rejected by the database at {endpoint}. The "
            "endpoint answered; the credential did not authenticate. Check that "
            "TURSO_AUTH_TOKEN matches the database named by DATABASE_URL and has "
            f"not expired. Driver said: {detail}",
        )

    return DatabaseUnreachableError(
        endpoint,
        f"Cannot reach the database at {endpoint}. The application will not "
        "start: PRD-007 removed the local-file fallback deliberately, so there "
        "is nothing to degrade to. Check DATABASE_URL and that the endpoint is "
        f"reachable from this host. Driver said: {detail}",
    )


def check_database_reachable() -> None:
    """One round trip, at boot, so an unreachable database is not a runtime surprise.

    PRD-007 Section 7.7. `_shared_client()` is lazy -- importing this module
    connects to nothing -- so without this the first contact with the database is
    whatever statement happens to run first, and for `insert_audit_log()` that is
    a write the query pipeline treats as fire-and-forget. An audit trail that
    silently stops recording is the failure this exists to prevent.

    Deliberately **not** wrapped in `_translated()`. That helper exists to give
    operational callers the module's error surface, and it re-raises anything
    without the `Hrana:` prefix untouched -- correct there, wrong here, where the
    guard's job is that *every* boot-time failure comes out classified and
    legible rather than as a raw driver `ValueError`.

    One statement, no transaction, no commit: a read needs neither, and
    `_Connection.close()` is already a no-op because the client is shared.
    """
    endpoint = _safe_endpoint(settings.DATABASE_URL)
    try:
        get_connection().execute("SELECT 1").fetchone()
    except Exception as exc:  # noqa: BLE001 -- every failure is classified below
        raise _classify_startup_failure(exc, endpoint) from exc


# Closed vocabulary of `/ready` reasons (PRD-019 Section 7 F1). `check_ready()` never
# returns `draining`: the route adds it from the drain file (STORY-002).
READY_REASONS = ("breaker_open", "database_unreachable", "database_auth", "draining")


@dataclass(frozen=True)
class ReadyCheck:
    """What `check_ready()` found (PRD-019 D3, D5).

    `reason` is None when ready, else one of `READY_REASONS`. `breaker` is the
    state read, or "unknown" when it could not be read. `retry_after_seconds` is
    set only for `breaker_open`, and is at least 1.
    """

    reason: Optional[str]
    breaker: str
    retry_after_seconds: Optional[int] = None


# One probe at a time per process (PRD-019 F1.3). A probe stuck on a blackholed
# endpoint is abandoned, not cancelled, and keeps the slot until the driver returns,
# so a stalled database never piles up statements behind `/ready`.
_ready_lock = threading.Lock()
_ready_executor: Optional[ThreadPoolExecutor] = None
_ready_future: Optional[Future] = None


def check_ready() -> ReadyCheck:
    """Runtime readiness: breaker in memory, then one bounded `SELECT 1` (PRD-019 D3, D5).

    **Zero driver calls while the breaker is not `closed`, and it never moves the
    breaker**: no `before()`, `record_success()` or `record_failure()`, no
    `_unit_of_work`, no retry. A load balancer polling this must not be able to
    open or close PRD-018's breaker. `open` and `half_open` both read as
    `breaker_open`.

    While closed, one statement runs on a single-slot executor under a deadline of
    `READY_DB_TIMEOUT_SECONDS`. A timed-out probe is left in flight (it still holds
    the slot) and later calls answer `database_unreachable` without submitting a
    second statement. Never raises; the detail goes to the log at WARNING, already
    redacted by `_classify_startup_failure`.
    """
    global _ready_executor, _ready_future
    breaker = "unknown"
    try:
        status = _storage_breaker.status()  # in-memory read; read at call time
        breaker = status.state
        if breaker != "closed":
            return ReadyCheck("breaker_open", breaker, max(1, int(status.retry_after_seconds or 1)))

        timeout = settings.READY_DB_TIMEOUT_SECONDS
        with _ready_lock:
            if _ready_future is not None and not _ready_future.done():
                logger.warning("readiness probe skipped: the previous SELECT 1 is still in flight")
                return ReadyCheck("database_unreachable", breaker)
            if _ready_executor is None:
                _ready_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ready-probe")
            future = _ready_executor.submit(lambda: get_connection().execute("SELECT 1").fetchone())
            _ready_future = future

        try:
            future.result(timeout=timeout)
        except FutureTimeout:
            logger.warning("readiness probe exceeded %.2fs; abandoned in flight", timeout)
            return ReadyCheck("database_unreachable", breaker)
        except Exception as exc:  # noqa: BLE001 -- classified below
            classified = _classify_startup_failure(exc, _safe_endpoint(settings.DATABASE_URL))
            logger.warning("readiness probe failed: %s", classified)
            if isinstance(classified, DatabaseAuthError):
                return ReadyCheck("database_auth", breaker)
            return ReadyCheck("database_unreachable", breaker)
        return ReadyCheck(None, breaker)
    except Exception:  # noqa: BLE001 -- the contract is that this never raises
        logger.warning("readiness check failed unexpectedly")
        return ReadyCheck("database_unreachable", breaker)


def _reset_ready_probe_for_tests() -> None:
    """Drop the probe executor and any in-flight future (tests only)."""
    global _ready_executor, _ready_future
    with _ready_lock:
        if _ready_executor is not None:
            _ready_executor.shutdown(wait=False, cancel_futures=True)
        _ready_executor = None
        _ready_future = None


@contextmanager
def _translated() -> Iterator[None]:
    """Driver exceptions in, app.db.errors exceptions out.

    The single seam in the codebase where the driver's failure shape is known.
    STORY-004 wrote this to be rewritten here, and `app/db/errors.py` did not
    have to change.

    **It invalidates a dead stream, and it does not retry one (STORY-024).** By
    the time a statement fails, this generator has already yielded: the caller's
    body has run, possibly inside `_session()`'s open transaction, and a retry
    from here could replay half of it. A partial transaction replayed is a worse
    defect than the one STORY-024 fixes, so the recovery is split -- the *retry*
    lives in `_shared_client()`, before any transaction opens, and what happens
    here is only that the dead client is dropped so the next call rebuilds. This
    call still raises `StorageError`, exactly as it did before.

    **The order of the branches is load-bearing.** Constraint and missing-relation
    are classified first, so a statement-level failure can never reach the
    dead-stream arm and be reclassified: a `UNIQUE constraint failed` is still an
    `IntegrityError` and still leaves the client cached (AC 3).
    """
    try:
        yield
    except ValueError as exc:
        message = str(exc)
        if _DRIVER_ERROR not in message:
            raise
        constraint = _constraint_of(exc)
        if constraint is not None:
            raise IntegrityError(constraint, message) from exc
        relation = _MISSING_RELATION.search(message)
        if relation is not None:
            raise MissingRelationError(relation.group(1), message) from exc
        if _is_dead_stream(message):
            _invalidate_client()
        raise StorageError(message) from exc


# PRD-018 STORY-002 (D2, Section 6.2). The one place that sorts a storage failure
# into "did the statement run?". It lives beside `_translated()` because that is
# the seam where the driver's failure shape is known (PRD 6.10, PRD-007 §7.2): no
# module outside `app/db/` learns a driver string. Its caller is `_failure_of()`,
# which `_unit_of_work()` uses.


class FailureClass(str, Enum):
    """What a storage failure says about whether the statement ran (PRD 6.2).

    The values are the names logs and `storage_status()` use.

    - `NOT_SENT`: the request never reached the server; nothing ran.
    - `DEAD_STREAM`: the server no longer has the stream; the statement did not
      run, but the stream must be rebuilt.
    - `OUTCOME_UNKNOWN`: the request may or may not have been applied.
    - `STATEMENT`: the server refused the statement itself (constraint, missing
      relation, duplicate column). Never retried, never counts toward the breaker
      (6.2 rule 2; wired by STORY-003/005).
    """

    NOT_SENT = "not_sent"
    DEAD_STREAM = "dead_stream"
    OUTCOME_UNKNOWN = "outcome_unknown"
    STATEMENT = "statement"


class StatementKind(str, Enum):
    """How safe it is to run a unit of work twice (PRD-018 D3, Section 6.3).

    Declared per public function in `database.py`, at its `_unit_of_work()` call;
    the two audit inserts choose it per call with `_keyed_kind()` (STORY-004).

    - `READ`: changes nothing, so a replay is always safe.
    - `IDEMPOTENT`: a replay lands the same state (a fixed-value UPDATE, a DELETE,
      an INSERT whose duplicate is recognised as the first attempt's).
    - `NON_IDEMPOTENT`: a replay could land the effect twice (a counter increment,
      an INSERT with no key to recognise it by), so it is retried only when the
      failure proves the first attempt did not run.
    """

    READ = "read"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"


Phase = Literal[
    "connect", "execute", "fetchone", "fetchall", "fetchmany", "commit", "rollback"
]
# `fetchmany` is added to the story's six names because `_Cursor.fetchmany` is a
# driver call too, and an unrecorded call would classify with phase `None`.
_PHASES: tuple[str, ...] = (
    "connect",
    "execute",
    "fetchone",
    "fetchall",
    "fetchmany",
    "commit",
    "rollback",
)
_PHASE_ATTRIBUTE = "_db_phase"


def _mark_phase(exc: BaseException, phase: Phase) -> None:
    """Label a driver exception with the call that raised it. First mark wins.

    The innermost (true) call is kept if the same object ever crosses two
    recording sites. The attribute is the **only** change: type, message, `args`
    and identity stay as raised, so `_translated()` and `_is_dead_stream()` behave
    as before (PRD 6.2 last bullet; the PRD-014 `_RecordedClient` same-object rule).
    """
    if getattr(exc, _PHASE_ATTRIBUTE, None) is None:
        setattr(exc, _PHASE_ATTRIBUTE, phase)


def _phase_of(exc: BaseException) -> Optional[str]:
    """The phase `_mark_phase` recorded on `exc`, or on its `__cause__`, else `None`.

    `_translated()` raises `... from exc` in all three arms, so the label on the
    driver's own exception is reachable from the translated one without changing
    `_translated()` (D1). A thread-local was rejected: it goes stale on the happy
    path and can disagree with the exception being classified when
    `_translated()` nests (`find_user_by_token_hash`) or workers share the client.
    `None` means "not raised through the wrapper" (a test proxy, a raw client).
    """
    phase = getattr(exc, _PHASE_ATTRIBUTE, None)
    if phase is None and exc.__cause__ is not None:
        phase = getattr(exc.__cause__, _PHASE_ATTRIBUTE, None)
    return phase


# Lower-case, matched against `message.lower()`. Today's text, captured by
# STORY-001 (spike row F1), surfaces on `execute` because the client is lazy:
#   Hrana: `http error: `error trying to connect: tcp connect error: ...``
# and the older spelling (`tests/test_db.py`, `tests/test_db_isolation_harness.py`):
#   Hrana: `api error: `error sending request for url (...): client error
#       (Connect): tcp connect error: ... (os error 10060)``
# `os error 110` / `10060` / `10061` / `111` all share the `tcp connect error`
# tail. `error sending request` alone is deliberately **not** a marker: it is
# reqwest's generic prefix for any request-level failure, including a connection
# reset after the request was written, and reading it as "never sent" would allow
# a non-idempotent replay, the miss 6.2's first rule forbids.
_CONNECT_FAILURE = ("tcp connect error", "client error (connect)")


def _classify(exc: BaseException, phase: Optional[str]) -> FailureClass:
    """Sort a storage failure into a `FailureClass` (PRD-018 D2, Section 6.2).

    **Pure**: a function of the exception and the phase. No I/O, no settings, no
    client, no logging. Its caller is `_failure_of()`, which `_unit_of_work()`
    uses. It reads `str(exc)`, so the driver's `ValueError` and the
    translated `StorageError` classify alike.

    **Unrecognised text is `OUTCOME_UNKNOWN`, never `NOT_SENT`**: a miss costs a
    retry that was skipped, never a replay that should not have happened. This
    includes the 503 / 404 restart-window texts (spike Recommendation 3),
    `SQLITE_BUSY` and any unrecognised `Hrana:` text.

    **The order is load-bearing**, as in `_translated()`: statement first, so a
    constraint can never be read as infrastructure.

    **A dead stream on `commit` is `NOT_SENT`.** Orchestrator decision of
    2026-11-17, PRD 6.2 amended, spike Verdict V1: DML is not durable before
    `commit()`, and `commit()` with no open transaction is a local no-op, so a
    commit-phase dead stream always means an open transaction that was lost
    (9/9 captures left nothing landed). A reset, a timeout or unrecognised text on
    `commit` stays `OUTCOME_UNKNOWN`. A dead stream on `rollback` is `DEAD_STREAM`
    (spike row 9): there is nothing to replay. `phase=None` is safe because only
    the `commit` rule reads the phase.
    """
    if isinstance(exc, (IntegrityError, MissingRelationError)):
        return FailureClass.STATEMENT
    message = str(exc)
    if (
        _CONSTRAINT.search(message)
        or _MISSING_RELATION.search(message)
        or _DUPLICATE_COLUMN.search(message)
    ):
        return FailureClass.STATEMENT
    if any(marker in message.lower() for marker in _CONNECT_FAILURE):
        return FailureClass.NOT_SENT
    if _is_dead_stream(message):
        if phase == "commit":
            return FailureClass.NOT_SENT
        return FailureClass.DEAD_STREAM
    return FailureClass.OUTCOME_UNKNOWN


# Rank of a failure from "least pessimistic" to "most": what `_failure_of()` takes
# when a rollback masks the body's own error. `STATEMENT` is on top because "never
# retried" is the safe end of the scale.
_FAILURE_RANK = {
    FailureClass.NOT_SENT: 0,
    FailureClass.DEAD_STREAM: 1,
    FailureClass.OUTCOME_UNKNOWN: 2,
    FailureClass.STATEMENT: 3,
}


def _failure_of(exc: BaseException) -> tuple[FailureClass, Optional[str]]:
    """The class and phase `_unit_of_work()` decides on (PRD-018 D3, Section 6.2).

    **The open rule STORY-002 left for this story.** `_Connection.__exit__` rolls
    back when the body raised, and a rollback that fails replaces the body's
    exception (the body's stays on `__context__`). A dead stream makes exactly
    that happen: the body's real failure, say an `OUTCOME_UNKNOWN` mid-write, would
    be read as the rollback's baton text and look like a harmless `DEAD_STREAM`,
    which a `NON_IDEMPOTENT` unit would then replay. So when the phase is
    `rollback` the body's failure is classified too, and **the more pessimistic of
    the two wins**: `NOT_SENT` < `DEAD_STREAM` < `OUTCOME_UNKNOWN` < `STATEMENT`.

    A tie goes to the body, so its phase decides `NON_IDEMPOTENT`'s "`DEAD_STREAM`
    on `execute` only". A body exception that is not a storage failure (our own
    `KeyError` mid-block) proves nothing about what the server did, so it counts
    as `OUTCOME_UNKNOWN`. The exception that propagates is unchanged: this only
    reads, it never replaces.

    Pure: a function of the exception chain. It lives beside `_classify()` because
    it is the same knowledge (PRD 6.10).
    """
    phase = _phase_of(exc)
    result = (_classify(exc, phase), phase)
    if phase != "rollback":
        return result
    driver = exc.__cause__ if exc.__cause__ is not None else exc
    body = driver.__context__
    if body is None:
        return result
    if isinstance(body, StorageError) or (
        isinstance(body, ValueError) and _DRIVER_ERROR in str(body)
    ):
        body_phase = _phase_of(body)
        body_result = (_classify(body, body_phase), body_phase)
    else:
        body_result = (FailureClass.OUTCOME_UNKNOWN, None)
    if _FAILURE_RANK[result[0]] > _FAILURE_RANK[body_result[0]]:
        return result
    return body_result


# PRD-018 D3, Section 6.3: which classes each kind may be retried on.
# `NOT_SENT` covers a dead stream on `commit` too (orchestrator decision, PRD 6.2
# as amended): so a `NON_IDEMPOTENT` unit is retried after one.
_RETRIED_ON: Mapping[StatementKind, frozenset[FailureClass]] = {
    StatementKind.READ: frozenset(
        {
            FailureClass.NOT_SENT,
            FailureClass.DEAD_STREAM,
            FailureClass.OUTCOME_UNKNOWN,
        }
    ),
    StatementKind.IDEMPOTENT: frozenset(
        {
            FailureClass.NOT_SENT,
            FailureClass.DEAD_STREAM,
            FailureClass.OUTCOME_UNKNOWN,
        }
    ),
    StatementKind.NON_IDEMPOTENT: frozenset(
        {FailureClass.NOT_SENT, FailureClass.DEAD_STREAM}
    ),
}


def _retryable(
    kind: StatementKind, failure: FailureClass, phase: Optional[str]
) -> bool:
    """Whether a unit of this kind may be run again after this failure (D3).

    Pure. `STATEMENT` is never retried (the server refused the statement; running
    it again refuses it again). `OUTCOME_UNKNOWN` is retried only when a replay is
    harmless. A `DEAD_STREAM` on a `NON_IDEMPOTENT` unit is proof the statement did
    not run only when it arrived on `execute`: one on a fetch says the statement
    was accepted and its answer was lost.
    """
    if failure not in _RETRIED_ON[kind]:
        return False
    if kind is StatementKind.NON_IDEMPOTENT and failure is FailureClass.DEAD_STREAM:
        return phase == "execute"
    return True


# SQLite's only statement-echoing form in an error is `near "<token>"` on a syntax
# error; the infrastructure texts quote no SQL and no parameters (spike captures).
_STATEMENT_ECHO = re.compile(r'near\s+\\?"[^"\\]*\\?"')


def _retry_detail(exc: BaseException) -> str:
    """The failure text for a retry log line: credential-free, no echoed SQL, short."""
    text = _STATEMENT_ECHO.sub('near "<elided>"', _redacted(str(exc)))
    return text[:500]


@contextmanager
def _session() -> Iterator[_Connection]:
    """`with get_connection() as conn:` plus translation.

    Same commit-on-success, rollback-on-exception, do-not-close semantics as the
    block it replaces -- `with sqlite3.Connection` was a transaction, not a
    closing context manager, and `_Connection` keeps that meaning.
    """
    with _translated():
        conn = get_connection()
        with conn:
            yield conn


_T = TypeVar("_T")


def _unit_of_work(
    name: str, kind: StatementKind, fn: Callable[[_Connection], _T]
) -> _T:
    """Run `fn(conn)` in a fresh `_session()`, again if the failure proves that is safe.

    **The retry boundary of PRD-018 D1.** One attempt is one `_session()`: a new
    `get_connection()`, a new transaction, and `fn` run from its first statement.
    `_translated()` stays the inner seam that translates and drops a dead stream;
    it never retries, because from inside it a replay could repeat half a
    transaction. This is the only place a retry exists.

    **What is retried is decided by `_retryable(kind, class, phase)` (D3).** The
    failure is classified by `_failure_of()`, which also resolves a rollback that
    masked the body's own error. `STATEMENT` failures, and `OUTCOME_UNKNOWN` on a
    `NON_IDEMPOTENT` unit, raise on the first attempt with the exception they
    always raised. Anything that is not a driver failure (our own `StorageError`
    such as `append_chat_message`'s ownership refusal, a `ValueError`, a
    `KeyError`) passes through untouched and unclassified, exactly as
    `_translated()` treats a non-driver `ValueError`.

    **A fresh client for every infrastructure failure**, not only a dead stream:
    `_translated()` already dropped that one, and `NOT_SENT` / `OUTCOME_UNKNOWN`
    leave a client that may be half-dead. It is dropped here, with an identity
    guard so a client another thread already rebuilt is kept, and never inside
    `_translated()` (D1).

    **Budget (D5).** At most `_RETRY_MAX_ATTEMPTS` runs, full-jitter waits, and no
    attempt *started* more than `_RETRY_START_DEADLINE_SECONDS` after the first.
    The deadline cannot cut a call that is already running (there is no driver
    read timeout, spike F3a/Q3); it only refuses to begin another after a stall.
    The last attempt's exception is what propagates as the `__cause__` of a
    `StorageUnavailableError` carrying its message (see Breaker). The start check projects `now + delay`, so the loop never
    sleeps into a start it would then refuse.

    **`fn` must be re-runnable.** Nothing it holds may survive an attempt: values
    that must be the same on every attempt (an id, a timestamp) are minted by the
    caller *before* the unit, and anything accumulated (ids, counts) is created
    inside `fn`.

    **Logs (AC 5).** One INFO line per retry. One WARNING when a retryable failure
    runs out of budget, and one when an infrastructure failure is refused a retry
    (`retry refused`: e.g. `NON_IDEMPOTENT` on `OUTCOME_UNKNOWN`). `STATEMENT`
    failures and our own `StorageError`s log nothing. The text goes through
    `_retry_detail()`: credential-free, no SQL, no parameters. Each retry and
    each final infrastructure failure also bumps a `storage_counters` count
    (PRD-018 D16): `retries` per retry, `exhausted` per operation (refused
    retries included).

    **Breaker (D6, D7).** `_storage_breaker.before()` runs first: open means a
    `StorageUnavailableError` with no client touched. One `record_failure()` per
    *operation* whose final failure is an infrastructure class -- retry budget
    exhausted **or** a retry refused, counted once, never per attempt -- and one
    `record_success()` otherwise. `STATEMENT` failures and our own errors leave
    the count alone. Every infrastructure failure leaves as
    `StorageUnavailableError(str(exc)) from exc`, so it is a `StorageError`
    whose text is unchanged. `retry_after_seconds` is the breaker's remaining
    window once this failure has been recorded, or 1 while it is still closed.

    `init_db()` and `check_database_reachable()` never come here (D17): the boot
    guard keeps failing fast and loudly, with no retry or breaker in front of it.
    """
    breaker = _storage_breaker  # read once: a test may swap the instance
    try:
        breaker.before()
    except BreakerOpen as refused:
        raise StorageUnavailableError(
            f"Storage unavailable: the {refused.name} circuit breaker is open; "
            f"retry after {refused.retry_after_seconds} s.",
            retry_after_seconds=refused.retry_after_seconds,
        ) from refused
    first_started = _retry_clock()
    attempt = 1
    while True:
        stale = None
        try:
            with _session() as conn:
                # `getattr`: a test may install a proxy with no `_client`.
                stale = getattr(conn, "_client", None)
                result = fn(conn)
        except StorageError as exc:
            if _DRIVER_ERROR not in str(exc):
                raise
            failure, phase = _failure_of(exc)
            if failure is not FailureClass.STATEMENT:
                _invalidate_client(stale)
                if _retryable(kind, failure, phase):
                    delay: Optional[float] = None
                    reason: Optional[str] = None
                    if attempt >= _RETRY_MAX_ATTEMPTS:
                        reason = "max_attempts"
                    else:
                        delay = _retry_jitter(_RETRY_BACKOFF_CAPS_SECONDS[attempt - 1])
                        started_by = _retry_clock() + delay - first_started
                        if started_by > _RETRY_START_DEADLINE_SECONDS:
                            reason = "deadline"
                    if reason is None and delay is not None:
                        storage_counters.retry(name, failure.value)
                        logger.info(
                            "retry op=%s class=%s attempt=%d detail=%s",
                            name,
                            failure.value,
                            attempt,
                            _retry_detail(exc),
                        )
                        _retry_sleep(delay)
                        attempt += 1
                        continue
                    logger.warning(
                        "retry exhausted op=%s class=%s attempts=%d reason=%s detail=%s",
                        name,
                        failure.value,
                        attempt,
                        reason,
                        _retry_detail(exc),
                    )
                else:
                    logger.warning(
                        "retry refused op=%s class=%s kind=%s detail=%s",
                        name,
                        failure.value,
                        kind.value,
                        _retry_detail(exc),
                    )
                # One per operation ending in an infrastructure failure (budget spent
                # or retry refused), so it equals the `record_failure` calls (D16).
                storage_counters.exhausted(name, failure.value)
                breaker.record_failure(failure.value)
                retry_after = breaker.status().retry_after_seconds or 1
                raise StorageUnavailableError(
                    str(exc), retry_after_seconds=retry_after
                ) from exc
            raise
        breaker.record_success()
        return result


@dataclass(frozen=True)
class JournalView:
    """The journal as `storage_status()` reports it (PRD-018 Section 10).

    `open` is False when this process opened no journal (the zero shape).
    `headroom_bytes` is the admission reserve (workers x 64 KiB): admission is
    refused once `bytes > max_bytes - headroom_bytes`; it is not free bytes.
    `held_back_*` are entries/files kept on disk that this process will not retry.
    """

    open: bool
    entries: int
    bytes: int
    max_bytes: int
    headroom_bytes: int
    oldest_timestamp: Optional[str]
    draining: bool
    adopted_files: int
    held_back_entries: int
    held_back_files: int


@dataclass(frozen=True)
class StorageStatus:
    """What `GET /storage/status` and the admin Storage view serialize as is."""

    instance: str
    breaker: BreakerStatus
    journal: JournalView
    counters: CounterSnapshot


def storage_status() -> StorageStatus:
    """Breaker, journal and counters of this process (PRD-018 F8, D16).

    **Zero driver calls and never `_client_lock`**: it reads only in-memory state
    (the breaker's lock, the journal's mutex, the drainer's lock and the counter
    lock, none held across a driver call), so it answers during a 21 s stall
    and while the breaker is open. Never raises.

    `draining` is true iff the drainer thread runs AND the breaker is closed AND
    some entry is not held back: while the breaker is open the drainer idles, and
    a held-back entry is never retried by this process.
    """
    from app.db import journal_drainer  # function-local: journal_drainer imports database

    breaker = _storage_breaker.status()  # one read: `breaker` and `draining` agree
    journal = audit_journal.current()
    if journal is None:
        view = JournalView(
            open=False,
            entries=0,
            bytes=0,
            max_bytes=settings.AUDIT_BUFFER_MAX_BYTES,
            headroom_bytes=settings.PIPELINE_MAX_WORKERS
            * audit_journal._JOURNAL_ENTRY_RESERVE_BYTES,
            oldest_timestamp=None,
            draining=False,
            adopted_files=0,
            held_back_entries=0,
            held_back_files=0,
        )
    else:
        snap = journal.status()
        held = journal_drainer.held_back()
        view = JournalView(
            open=True,
            entries=snap.entries,
            bytes=snap.bytes,
            max_bytes=snap.max_bytes,
            headroom_bytes=snap.headroom_bytes,
            oldest_timestamp=snap.oldest_timestamp,
            draining=journal_drainer.running()
            and breaker.state == "closed"
            and snap.entries - held > 0,
            adopted_files=snap.adopted_files,
            held_back_entries=held,
            held_back_files=snap.held_back_files,
        )
    return StorageStatus(
        instance=f"{socket.gethostname()}:{os.getpid()}",
        breaker=breaker,
        journal=view,
        counters=storage_counters.snapshot(),
    )


def init_db() -> None:
    """Create or migrate the schema -- and, first, prove the database answers.

    **The guard lives here rather than in each entry point on purpose.** Every
    boot path already calls this function and no other: `app/main.py`'s lifespan,
    `chat_ui/chat_ui/chat_ui.py` at import time (Reflex's api_transformer never
    runs the FastAPI lifespan), and `scripts/manage_users.py` in each command. A
    guard each caller had to remember to invoke would be forgotten by the fourth
    one, which is precisely the silent gap STORY-008 exists to close.

    `DB_BOOTSTRAP_ENABLED` is the one sanctioned way out, and it exists for the
    Docker builder stage alone: `reflex export` imports `chat_ui.chat_ui`, which
    lands here, and PRD Section 11 requires the build to succeed with no
    reachable database. See the setting's comment in `app/config.py` for why it
    gates the schema work too and not just the probe.

    **One `_session()` block builds the whole schema** -- `audit_logs`, `users`
    and, since PRD-008 STORY-003, the two transcript tables and their indexes.
    One block is one transaction on one connection, so a boot either lands the
    whole shape or none of it, and the added statements cost no extra round
    trip. PRD-008 Risk 7 is about exactly that cost: this function runs at
    import time on every Reflex hot reload, and what the transcript tables add
    there is four `CREATE ... IF NOT EXISTS` no-ops, idempotent by construction.
    The one thing PRD-008 adds that is *not* idempotent by construction is a
    column, `audit_logs.session_id`, and it needed no new code here -- it rides
    `_add_missing_columns()` below, which iterates the mapping it was already
    iterating.

    PRD-009 STORY-002 adds one more column, `audit_logs.dedup_key`, on the same
    path and with no new code in `_add_missing_columns()` either. It also adds
    the first index on `audit_logs`, and that is the one statement in this block
    whose position is load-bearing: on a database created before PRD-009 the
    column does not exist until `_add_missing_columns()` has run, and an index
    on a missing column fails the boot. So it sits on the line after. In steady
    state it is one more `CREATE INDEX IF NOT EXISTS` no-op.

    PRD-010 STORY-010 adds `chat_messages.history_trimmed`, which makes
    `chat_messages` the second table to need a column convergence. So
    `_add_missing_columns()` now takes the table and the mapping to apply and is
    called twice from this block, once per table -- the same guarantee run
    again, not a second mechanism. The `chat_messages` pass sits **after**
    `CREATE_CHAT_MESSAGES_TABLE`, and that position is load-bearing the way the
    dedup index's is, for the opposite reason: on a fresh database the table
    does not exist until that CREATE, and `PRAGMA table_info` against a missing
    table reports no columns, which is indistinguishable from a table missing
    every column -- so a pass placed earlier would try to ALTER a table that is
    not there. In steady state it costs one more `PRAGMA table_info` and issues
    no `ALTER`.

    PRD-011 STORY-009 adds `audit_logs.pattern_role` and
    `audit_logs.pattern_action` on the `session_id`/`dedup_key` path, with no
    new code here: both are nullable with no default, and neither is indexed.

    PRD-012 STORY-011 adds `audit_logs.profile` on the same path, again with
    no new code here: nullable, no default, no backfill, not indexed.

    PRD-013 STORY-002 adds eight `audit_logs` columns on the same path, again
    with no new code here. Six are nullable with no default and no backfill.
    `streamed` and `has_tool_calls` are `NOT NULL DEFAULT 0`, which `ADD
    COLUMN` accepts because the default is non-NULL. None is indexed.

    PRD-013 STORY-008 makes `users` the third table on this path, for the
    per-user limit overrides `token_budget_daily` and `requests_per_minute`.
    The pass sits **after** `CREATE_USERS_TABLE` for the reason the
    `chat_messages` pass gives: on a fresh database there is no table to
    interrogate until that CREATE. Both columns are nullable with no default,
    so every existing user reads NULL -- "use the role's limit".

    PRD-013 STORY-009 adds `usage_daily`, a new table, so it arrives by CREATE
    alone with no added-columns mapping. In steady state it is one more
    `CREATE ... IF NOT EXISTS` no-op in the same transaction. Its position is
    not load-bearing: no other statement in this block reads it.

    PRD-016 STORY-015 adds `action_decisions` and its two indexes (Section
    6.10, D8), a new table, so it too arrives by CREATE alone with no
    added-columns mapping and alters no existing table. No other statement in
    this block reads it, so its position is not load-bearing; the indexes
    follow their table, as every index here does.

    PRD-018 STORY-004 adds `write_id` to `audit_logs` and `action_decisions`
    (D4). The `audit_logs` UNIQUE index sits after that table's pass, for the
    dedup index's reason: on an older database the column does not exist until
    the pass adds it. The `action_decisions` pass sits after its CREATE, for the
    `chat_messages` pass's reason, which makes it the fourth table on this path.
    In steady state the cost is one more `PRAGMA table_info` and two
    `CREATE INDEX IF NOT EXISTS` no-ops.
    """
    if not settings.DB_BOOTSTRAP_ENABLED:
        return

    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)
        conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)
        conn.execute(CREATE_AUDIT_LOGS_WRITE_ID_INDEX)  # after the pass: the column may be new
        conn.execute(CREATE_USERS_TABLE)
        _add_missing_columns(conn, "users", USERS_ADDED_COLUMNS)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)
        conn.execute(CREATE_CHAT_SESSIONS_TABLE)
        conn.execute(CREATE_CHAT_SESSIONS_USER_INDEX)
        conn.execute(CREATE_CHAT_MESSAGES_TABLE)
        _add_missing_columns(conn, "chat_messages", CHAT_MESSAGES_ADDED_COLUMNS)
        conn.execute(CREATE_CHAT_MESSAGES_SESSION_INDEX)
        conn.execute(CREATE_USAGE_DAILY_TABLE)
        conn.execute(CREATE_ACTION_DECISIONS_TABLE)
        _add_missing_columns(conn, "action_decisions", ACTION_DECISIONS_ADDED_COLUMNS)
        conn.execute(CREATE_ACTION_DECISIONS_USER_TS_INDEX)
        conn.execute(CREATE_ACTION_DECISIONS_AUDIT_INDEX)
        conn.execute(CREATE_ACTION_DECISIONS_WRITE_ID_INDEX)


def _add_missing_columns(
    conn: _Connection, table: str, columns: dict[str, str]
) -> None:
    """Brings a pre-existing `table` up to the current schema.

    Additive only: existing rows keep their data and take the column default.
    That constraint is unchanged; what STORY-007 adds is convergence.

    **The read and the write are not atomic, and cannot be made so.**
    `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS` form, so this is the one
    non-idempotent step in `init_db()` -- the rest is `CREATE ... IF NOT EXISTS`
    by construction. Against a shared database, N instances booting together can
    all read the same missing column and all try to add it, and every loser gets
    `duplicate column name`. Since `init_db()` runs at import time
    (`chat_ui/chat_ui/chat_ui.py`, `app/main.py`), that is a container that will
    not boot. So the loser treats that one condition as success and converges.

    Two things this deliberately does not do. It does not drop the pre-check:
    the guard is what makes a steady-state boot issue no `ALTER` at all, which
    `test_init_db_issues_no_alter_when_schema_is_current` asserts and which
    matters because `init_db()` re-runs on every Reflex hot reload. And it does
    not catch broadly -- `_is_duplicate_column()` requires the driver to name
    the column being added, so a permissions failure, an unreachable endpoint or
    a locked database still propagates. Swallowing those would hide a broken
    migration behind a healthy-looking boot.

    The `_translated()` here is not redundant with the one in `_session()`.
    That one converts on the way out of the *whole* block, so a statement
    failing mid-block arrives as the driver's bare `ValueError`; wrapping the
    single `ALTER` is what lets this decide on `app/db/errors.py`'s types rather
    than on the driver's. A re-raised `StorageError` is not a `ValueError`, so
    it passes back out through `_session()` untouched rather than being parsed
    twice.

    **PRD-010 STORY-010 made the table and the mapping parameters**, because
    `chat_messages.history_trimmed` needs exactly the convergence above and
    nothing about it is audit-specific. Four calls rather than one loop over a
    list of tables: `init_db()` has to run the passes at different points in its
    block -- `audit_logs` before `CREATE_AUDIT_LOGS_DEDUP_INDEX`, which reads a
    migrated column, and `chat_messages` and `action_decisions` (PRD-018
    STORY-004) after their CREATE, without which there is no table to
    interrogate on a fresh database. The body
    is unchanged: the same pre-check, the same single tolerated failure, the
    same `PRAGMA` read per table.
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name in existing:
            continue
        try:
            with _translated():
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        except StorageError as exc:
            if not _is_duplicate_column(exc, name):
                raise


# Appended to a keyed insert (PRD-018 D4, STORY-004). `DO NOTHING` makes a replay
# of a landed write a no-op rather than a second row; `RETURNING id` hands back
# the new row's id on the healthy path in the same round trip as the INSERT. On
# a conflict `RETURNING` yields no row, and the caller falls back to one
# `SELECT id ... WHERE write_id = ?` (orchestrator decision, STORY-004).
_ON_WRITE_ID_CONFLICT = " ON CONFLICT(write_id) DO NOTHING RETURNING id"

_INSERT_AUDIT_LOG_SQL = """
            INSERT INTO audit_logs (
                timestamp, user_id, device, prompt_hash, prompt_preview,
                response_hash, response_preview, model_used, tokens_used,
                was_duplicate_blocked, suspicious_pattern, success, error_message,
                pii_detected_input, pii_detected_output, pii_entities,
                role, denied_permission, session_id, dedup_key,
                pattern_role, pattern_action, profile,
                ingress, message_count, input_tokens, output_tokens,
                streamed, has_tool_calls, conversation_key, limit_exceeded,
                ignored_params, write_id,
                provider, upstream_model, provider_trust,
                pii_input_relaxed, usage_estimated,
                streamed_realtime, reasoning_shown,
                stream_redaction_divergence, completion_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _keyed_kind(write_ids: Sequence[Optional[str]]) -> StatementKind:
    """The kind of an audit insert, chosen per call (PRD-018 D4, STORY-004).

    `IDEMPOTENT` only when every row carries a `write_id`: then a replay meets
    `ON CONFLICT(write_id) DO NOTHING` and reads the first attempt's id back.
    One row without a key (a test, a script) makes the whole unit
    `NON_IDEMPOTENT`, because a replay after `OUTCOME_UNKNOWN` would land that
    row twice. Pure. Empty input is `NON_IDEMPOTENT` (no caller passes it:
    `insert_action_decisions([])` returns before the unit).
    """
    if write_ids and all(write_id is not None for write_id in write_ids):
        return StatementKind.IDEMPOTENT
    return StatementKind.NON_IDEMPOTENT


def _keyed_row_id(conn: _Connection, table: str, cursor: _Cursor, write_id: str) -> int:
    """The id of the row a keyed INSERT ... RETURNING id left for `write_id`.

    PRD-018 D4, STORY-004. PRD 6.4 first said "SELECT rather than RETURNING";
    the orchestrator reversed it so the healthy path costs no extra round trip
    (PRD Section 11): `RETURNING id` answers a fresh insert, and only when it
    yields no row -- a conflict, i.e. a replay -- does one `SELECT id ... WHERE
    write_id = ?` run, on the same connection and so inside the same
    transaction. `lastrowid` is never read on this path: after a conflicting
    DO NOTHING the driver reports 0 or the previous insert's id (STORY-004
    probe).
    """
    row = cursor.fetchone()
    if row is None:
        row = conn.execute(
            f"SELECT id FROM {table} WHERE write_id = ?", (write_id,)
        ).fetchone()
    if row is None:
        # Cannot happen: either the insert or an earlier attempt left the row.
        # Failing closed beats handing back a guess. Not driver text, so
        # _unit_of_work does not classify or retry it.
        raise StorageError(f"{table}: no row for its write_id after the insert")
    return row["id"]


def _insert_audit_row(conn: _Connection, entry: AuditLog) -> int:
    """One audit row on `conn`; its id. Keyed by `entry.write_id` when present (D4).

    Keyed: `ON CONFLICT(write_id) DO NOTHING RETURNING id`, then, only when
    that returned no row (a replay), `SELECT id ... WHERE write_id = ?` on the
    same connection (see `_keyed_row_id`), so the id is the row's whichever
    attempt inserted it. `lastrowid` is never read on this path. Unkeyed:
    today's plain INSERT (`write_id` NULL, no `ON CONFLICT`) and `lastrowid`.
    """
    keyed = entry.write_id is not None
    cursor = conn.execute(
        _INSERT_AUDIT_LOG_SQL + (_ON_WRITE_ID_CONFLICT if keyed else ""),
        (
            entry.timestamp,
            entry.user_id,
            entry.device,
            entry.prompt_hash,
            entry.prompt_preview,
            entry.response_hash,
            entry.response_preview,
            entry.model_used,
            entry.tokens_used,
            int(entry.was_duplicate_blocked),
            entry.suspicious_pattern,
            int(entry.success),
            entry.error_message,
            int(entry.pii_detected_input),
            int(entry.pii_detected_output),
            entry.pii_entities,
            entry.role,
            entry.denied_permission,
            entry.session_id,
            entry.dedup_key,
            entry.pattern_role,
            entry.pattern_action,
            entry.profile,
            entry.ingress,
            entry.message_count,
            entry.input_tokens,
            entry.output_tokens,
            int(entry.streamed),
            int(entry.has_tool_calls),
            entry.conversation_key,
            entry.limit_exceeded,
            entry.ignored_params,
            entry.write_id,
            entry.provider,
            entry.upstream_model,
            entry.provider_trust,
            int(entry.pii_input_relaxed),
            int(entry.usage_estimated),
            int(entry.streamed_realtime),
            int(entry.reasoning_shown),
            int(entry.stream_redaction_divergence),
            entry.completion_id,
        ),
    )
    if keyed:
        return _keyed_row_id(conn, "audit_logs", cursor, entry.write_id)
    return cursor.lastrowid


def insert_audit_log(entry: AuditLog) -> int:
    """Write one audit row and return its id.

    **Per-call kind (PRD-018 D4, STORY-004).** A row that carries a `write_id`
    is `IDEMPOTENT`: retried on every infrastructure failure class, and a replay
    of a landed commit meets `ON CONFLICT(write_id) DO NOTHING` and returns the
    same id as the first attempt (`RETURNING id`, or one `SELECT` on conflict;
    PRD 6.4's "SELECT rather than RETURNING" was reversed so the healthy path
    adds no round trip). A row without one is `NON_IDEMPOTENT`, exactly as
    before: an `OUTCOME_UNKNOWN` commit is never replayed, because a second
    INSERT would be a second audit row. `log_query` always keys.
    """

    def _op(conn: _Connection) -> int:
        return _insert_audit_row(conn, entry)

    return _unit_of_work("insert_audit_log", _keyed_kind([entry.write_id]), _op)


def find_duplicate_timestamp(user_id: str, dedup_key: str, since: str) -> Optional[str]:
    def _op(conn: _Connection) -> Optional[str]:
        # PRD-018 D12, Risk 6: audit_journal._is_prior_query is this WHERE
        # clause over the journal's pending rows (the duplicate overlay). Any
        # exclusion added here must be added there, in the same order; the
        # parity test in tests/test_db_resilience_overlay.py fails otherwise.
        # Only a row with a real verdict is a prior query: it reached the model,
        # or a content check blocked it (PRD-009 F4, D1). Failures (success = 0,
        # the output-redaction arm included, T6), policy denials (D1) and
        # duplicate blocks (D3: a blocked row must not chain the window) are
        # excluded. denied_permission is nullable, hence IS NULL, not = ''.
        # Scoped to the caller (PRD-009 F5): another user's row never counts, so
        # nobody can poison a colleague's window (T2); N accounts may each send
        # a prompt once per window, accepted and left to PRD-013 (T1).
        # Matches on dedup_key (PRD-009 STORY-007, Section 6.3), served by
        # idx_audit_logs_dedup. The evidence column is still written but no longer
        # read here: it is what /audit reports (D5). A pre-PRD row has a NULL key
        # and never matches, since NULL = ? is never true -- a one-off gap of at
        # most 24h after deploy, accepted (D6, T8, Risk 3).
        # A pattern *flag* row (PRD-011 D6) is excluded too: it is not a
        # verdict, because the request it records went on to redaction and
        # upstream. The prior query is that request's own success row, which
        # carries the same key. Counting the flag row would make a flagged
        # request that then failed upstream a "duplicate" of an attempt nobody
        # answered. NULL passes -- every row written before PRD-011 -- and a
        # block row passes, as a content verdict (PRD-009 F4).
        # A usage-limit refusal (PRD-013 D6) is excluded too. It is success = 1
        # because a verdict was reached, but the verdict is about the caller's
        # spend, not the prompt, and the prompt never reached the model.
        # Counting it would hold a prompt refused for budget today as a
        # duplicate when it is sent again tomorrow. NULL passes, so every row
        # written before PRD-013 behaves as before (PRD-013 Risk 5).
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE user_id = ? AND dedup_key = ? AND timestamp >= ?
              AND success = 1
              AND was_duplicate_blocked = 0
              AND denied_permission IS NULL
              AND (pattern_action IS NULL OR pattern_action <> 'flag')
              AND limit_exceeded IS NULL
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (user_id, dedup_key, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None

    return _unit_of_work("find_duplicate_timestamp", StatementKind.READ, _op)


def mark_audit_log_failed(audit_id: int, error_message: str) -> None:
    """Flip one audit row to `success = 0` with `error_message` (PRD-017 D8).

    The caller is `query_pipeline` after `action_audit.record()` failed: the
    success row was written first (`record()` needs its id), so a retry would
    be held as a duplicate. `find_duplicate_timestamp` counts only `success = 1`
    rows, so this restores the retry. It touches those two columns of that one
    row and nothing else; an unknown id updates nothing and raises nothing.
    Raises `StorageError` like every function here; the caller treats it as
    best effort.
    """

    def _op(conn: _Connection) -> None:
        conn.execute(
            "UPDATE audit_logs SET success = 0, error_message = ? WHERE id = ?",
            (error_message, audit_id),
        )

    return _unit_of_work("mark_audit_log_failed", StatementKind.IDEMPOTENT, _op)


def _row_to_audit_log(row: Mapping[str, Any]) -> AuditLog:
    """Map one audit row onto `AuditLog`, by column name.

    Annotated as a `Mapping`, not `_Row`, because it takes both: `_Row` for a
    row off the wire, and the plain `dict` `summary_snapshot()` decodes out of
    `json_object(...)` (STORY-010). Every access below is `row["name"]` and
    nothing else, so one mapper serves both shapes -- which is the point. A
    second mapper for the batched path is exactly how the two would drift, and
    AC 5 is that they agree figure for figure.

    The `bool(...)` coercions are load-bearing on the JSON path too: SQLite's
    INTEGER columns come back through `json_object` as 0 and 1.
    """
    return AuditLog(
        id=row["id"],
        timestamp=row["timestamp"],
        user_id=row["user_id"],
        device=row["device"],
        prompt_hash=row["prompt_hash"],
        prompt_preview=row["prompt_preview"],
        response_hash=row["response_hash"],
        response_preview=row["response_preview"],
        model_used=row["model_used"],
        tokens_used=row["tokens_used"],
        was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
        suspicious_pattern=row["suspicious_pattern"],
        success=bool(row["success"]),
        error_message=row["error_message"],
        pii_detected_input=bool(row["pii_detected_input"]),
        pii_detected_output=bool(row["pii_detected_output"]),
        pii_entities=row["pii_entities"],
        role=row["role"],
        denied_permission=row["denied_permission"],
        session_id=row["session_id"],
        dedup_key=row["dedup_key"],
        pattern_role=row["pattern_role"],
        pattern_action=row["pattern_action"],
        profile=row["profile"],
        ingress=row["ingress"],
        message_count=row["message_count"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        streamed=bool(row["streamed"]),
        has_tool_calls=bool(row["has_tool_calls"]),
        conversation_key=row["conversation_key"],
        limit_exceeded=row["limit_exceeded"],
        ignored_params=row["ignored_params"],
        write_id=row["write_id"],
        provider=row["provider"],
        upstream_model=row["upstream_model"],
        provider_trust=row["provider_trust"],
        pii_input_relaxed=bool(row["pii_input_relaxed"]),
        usage_estimated=bool(row["usage_estimated"]),
        streamed_realtime=bool(row["streamed_realtime"]),
        reasoning_shown=bool(row["reasoning_shown"]),
        stream_redaction_divergence=bool(row["stream_redaction_divergence"]),
        completion_id=row["completion_id"],
    )


def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    def _op(conn: _Connection) -> Optional[AuditLog]:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_audit_log(row)

    return _unit_of_work("get_audit_log", StatementKind.READ, _op)


def _audit_filter(
    user_id: Optional[str], completion_id: Optional[str]
) -> tuple[str, list[Any]]:
    """The WHERE clause and bound values of the audit readers.

    PRD-021 F7: `completion_id` is an exact match (no LIKE, no prefix), a bound
    value like `user_id`; the clause text is fixed and no caller text reaches
    the SQL. The two filters combine with AND. With neither, the clause is
    empty and the statements are today's.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if completion_id is not None:
        clauses.append("completion_id = ?")
        params.append(completion_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def count_audit_logs(
    user_id: Optional[str] = None, completion_id: Optional[str] = None
) -> int:
    where, params = _audit_filter(user_id, completion_id)

    def _op(conn: _Connection) -> int:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM audit_logs{where}", tuple(params)
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_audit_logs", StatementKind.READ, _op)


def list_audit_logs(
    limit: int = 100,
    user_id: Optional[str] = None,
    completion_id: Optional[str] = None,
) -> list[AuditLog]:
    where, params = _audit_filter(user_id, completion_id)

    def _op(conn: _Connection) -> list[AuditLog]:
        rows = conn.execute(
            f"SELECT * FROM audit_logs{where} ORDER BY timestamp DESC LIMIT ?",
            tuple(params) + (limit,),
        ).fetchall()
        return [_row_to_audit_log(row) for row in rows]

    return _unit_of_work("list_audit_logs", StatementKind.READ, _op)


def count_blocked_duplicates() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE was_duplicate_blocked = 1"
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_blocked_duplicates", StatementKind.READ, _op)


# PRD-011 D6: what "blocked as suspicious" means, written once and shared by
# `count_blocked_suspicious()` and `_SUMMARY_SQL`'s `blocked_suspicious`, so the
# two figures cannot drift apart. A flag row carries a pattern but was not
# blocked, so it is excluded. A NULL action is a row written before PRD-011,
# and every such row carrying a pattern *was* a block -- so NULL still counts,
# no historical row moves, and none is backfilled (PRD Risk 4). That is the
# whole reason this is not simply `pattern_action = 'block'`.
_BLOCKED_SUSPICIOUS_WHERE = (
    "suspicious_pattern IS NOT NULL"
    " AND (pattern_action IS NULL OR pattern_action = 'block')"
)


def count_blocked_suspicious() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM audit_logs WHERE {_BLOCKED_SUSPICIOUS_WHERE}"
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_blocked_suspicious", StatementKind.READ, _op)


def count_unique_users() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM audit_logs"
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_unique_users", StatementKind.READ, _op)


def count_successful_queries() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE success = 1"
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_successful_queries", StatementKind.READ, _op)


def top_models(limit: int = 5) -> list[str]:
    def _op(conn: _Connection) -> list[str]:
        rows = conn.execute(
            """
            SELECT model_used FROM audit_logs
            WHERE model_used IS NOT NULL
            GROUP BY model_used
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["model_used"] for row in rows]

    return _unit_of_work("top_models", StatementKind.READ, _op)


def top_users(limit: int = 5) -> list[str]:
    def _op(conn: _Connection) -> list[str]:
        rows = conn.execute(
            """
            SELECT user_id FROM audit_logs
            GROUP BY user_id
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["user_id"] for row in rows]

    return _unit_of_work("top_users", StatementKind.READ, _op)


def count_pii_detected_queries() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM audit_logs
            WHERE pii_detected_input = 1 OR pii_detected_output = 1
            """
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_pii_detected_queries", StatementKind.READ, _op)


def top_pii_entities(limit: int = 5) -> list[str]:
    """The most frequent PII entity types, most frequent first.

    `pii_entities` is comma-separated TEXT, not a normalized table, so ranking it
    means splitting it -- and the split belongs in the database. This used to
    read every PII-bearing row and count them in a Python dict, which was free
    against a local file and is the whole PII history over the network against a
    remote one (PRD-007 Section 6 Pattern 4). The recursive CTE peels one entity
    off the front of each value per step, and at most `limit` rows come back.

    **The seed row selects `NULL`, not `''`.** The usual idiom seeds with `''`
    and drops the seed with `WHERE entity <> ''`, which would also drop a genuine
    empty segment -- `"A,,B"` would lose its middle where `"A,,B".split(",")`
    keeps it. `NULL` distinguishes the seed from an empty entity, so this counts
    exactly what the loop it replaces counted.

    **The tie-break is chosen here, not inherited.** The old `sorted(...,
    key=count, reverse=True)` was stable over dict insertion order, so equal
    counts resolved by whichever row the database happened to return first --
    incidental, and not a thing to reproduce across N instances. Equal counts now
    order by entity name (STORY-009).
    """

    def _op(conn: _Connection) -> list[str]:
        rows = conn.execute(
            """
            WITH RECURSIVE split(entity, rest) AS (
                SELECT NULL, pii_entities || ','
                  FROM audit_logs
                 WHERE pii_entities IS NOT NULL
                UNION ALL
                SELECT substr(rest, 1, instr(rest, ',') - 1),
                       substr(rest, instr(rest, ',') + 1)
                  FROM split
                 WHERE rest <> ''
            )
            SELECT entity FROM split
            WHERE entity IS NOT NULL
            GROUP BY entity
            ORDER BY COUNT(*) DESC, entity ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["entity"] for row in rows]

    return _unit_of_work("top_pii_entities", StatementKind.READ, _op)


# PRD-013 Section 6.10: the two token totals are sums over every row with NULL
# as 0. `SUM` alone returns NULL over an empty table or a column that is NULL
# on every row, so the COALESCE is what makes an empty table read 0 rather
# than None. Written once and shared by the standalone functions and
# `_SUMMARY_SQL`, as `_BLOCKED_SUSPICIOUS_WHERE` is, so the batched and
# figure-by-figure reads cannot drift apart.
_SUM_INPUT_TOKENS = "COALESCE(SUM(input_tokens), 0)"
_SUM_OUTPUT_TOKENS = "COALESCE(SUM(output_tokens), 0)"

# PRD-013 Section 6.2: a usage-limit refusal is the only row that names a
# limit, so a non-NULL `limit_exceeded` is the whole definition. 0 until
# STORY-011 writes such rows.
_BLOCKED_USAGE_LIMITS_WHERE = "limit_exceeded IS NOT NULL"


def sum_input_tokens() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            f"SELECT {_SUM_INPUT_TOKENS} AS n FROM audit_logs"
        ).fetchone()
        return row["n"]

    return _unit_of_work("sum_input_tokens", StatementKind.READ, _op)


def sum_output_tokens() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            f"SELECT {_SUM_OUTPUT_TOKENS} AS n FROM audit_logs"
        ).fetchone()
        return row["n"]

    return _unit_of_work("sum_output_tokens", StatementKind.READ, _op)


def count_blocked_usage_limits() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM audit_logs WHERE {_BLOCKED_USAGE_LIMITS_WHERE}"
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_blocked_usage_limits", StatementKind.READ, _op)


# --------------------------------------------------------------------------
# The batched summary read (STORY-010)
# --------------------------------------------------------------------------

#: The thirteen figures the admin summary is made of, in `_READS`' order.
#:
#: The names are `chat_ui/chat_ui/admin_state.py`'s `_READS` field names on
#: purpose, so its `READ_LABEL_*` entries map one-to-one onto them and
#: `len(_READS) == len(SUMMARY_FIGURES)` survives the batching (PRD-007 Risk 6).
#: The first ten are STORY-010's; PRD-013 appended the last three, after every
#: existing figure, so no column and no positional parameter moved.
SUMMARY_FIGURES = (
    "rows",
    "total_recorded",
    "blocked_duplicates",
    "blocked_suspicious",
    "unique_users",
    "successful_queries",
    "pii_detected_queries",
    "top_models",
    "top_users",
    "top_pii_entities",
    "input_tokens",
    "output_tokens",
    "blocked_usage_limits",
)


@dataclass(frozen=True)
class SummarySnapshot:
    """All thirteen summary figures, with per-figure failure attribution.

    **This type exists because one statement is all-or-nothing and the admin
    console is not.** `_READS` gives each figure its own `READ_LABEL_*` so a
    partial failure names the read that broke; collapsing ten reads into one
    result that either arrives or does not would turn ten legible partial
    failures into one blank page, which is PRD-007 Risk 6 exactly.

    So the result is a partition, not a tuple: `figures` holds the figures that
    arrived, each with the type its standalone function returns (`int`,
    `list[str]`, `list[AuditLog]`), and `errors` holds the ones that did not,
    each against its own name. Every name in `SUMMARY_FIGURES` appears in
    exactly one of the two -- asserted below, because a figure silently in
    neither is the blank page arriving by another route.

    The named properties are for callers that want the value or nothing;
    they raise the recorded failure. Callers that want attribution -- STORY-012
    is the one -- read `errors` and never trigger them.
    """

    figures: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        covered = set(self.figures) | set(self.errors)
        if covered != set(SUMMARY_FIGURES) or (set(self.figures) & set(self.errors)):
            raise AssertionError(
                "figures and errors must partition SUMMARY_FIGURES exactly; "
                f"got figures={sorted(self.figures)} errors={sorted(self.errors)}"
            )

    def _figure(self, name: str) -> Any:
        if name in self.errors:
            raise self.errors[name]
        return self.figures[name]

    @property
    def rows(self) -> list:
        return self._figure("rows")

    @property
    def total_recorded(self) -> int:
        return self._figure("total_recorded")

    @property
    def blocked_duplicates(self) -> int:
        return self._figure("blocked_duplicates")

    @property
    def blocked_suspicious(self) -> int:
        return self._figure("blocked_suspicious")

    @property
    def unique_users(self) -> int:
        return self._figure("unique_users")

    @property
    def successful_queries(self) -> int:
        return self._figure("successful_queries")

    @property
    def pii_detected_queries(self) -> int:
        return self._figure("pii_detected_queries")

    @property
    def top_models(self) -> list:
        return self._figure("top_models")

    @property
    def top_users(self) -> list:
        return self._figure("top_users")

    @property
    def top_pii_entities(self) -> list:
        return self._figure("top_pii_entities")

    @property
    def input_tokens(self) -> int:
        return self._figure("input_tokens")

    @property
    def output_tokens(self) -> int:
        return self._figure("output_tokens")

    @property
    def blocked_usage_limits(self) -> int:
        return self._figure("blocked_usage_limits")


# One statement, thirteen named columns -- **not** a client batch, because there is
# no client batch to use. STORY-001 §2.6 pasted the driver's whole surface:
#
#   dir(connection) = ['close','commit','cursor','execute','executemany',
#                      'executescript','in_transaction','isolation_level',
#                      'rollback','sync']
#   has conn.batch: False        has conn.execute_batch: False
#
# `executescript()` returns None, and multi-statement `execute()` is worse than
# unsupported -- it returns only statement 1 and reports success for a batch
# containing `SELECT * FROM no_such_table`. Per-statement results and
# per-statement errors are both unavailable, so Risk 6 cannot be answered with
# a batch API at all. §3.4 recorded the workaround this constant is: one SELECT
# of scalar subqueries, measured at 1.7 ms against 16.3 ms for the ten
# sequential statements, with `cursor.description` giving every figure its own
# column name -- which is what carries the attribution that statements cannot.
#
# Every subquery is its standalone function's predicates copied verbatim, and
# `split` is STORY-009's recursive CTE hoisted to the top so `top_pii_entities`
# can be read from a scalar subquery beside the rest. Copied, not paraphrased:
# AC 5 is that every figure agrees with the individual functions figure for figure.
#
# **The four parameters bind positionally, in column order**:
#     (row_limit, ranked_limit, ranked_limit, ranked_limit)
# Reordering or inserting a column silently reorders them. Named placeholders
# were not among STORY-001's six verified behaviors, so this does not use them.
# PRD-013's three columns (`input_tokens`, `output_tokens`,
# `blocked_usage_limits`) take no parameter and come after every existing one,
# so the tuple did not change (PRD-013 Risk 8). A future column with a `?`
# must also go last, and its value goes at the end of the tuple.
# PRD-015 STORY-007's `ignored_params` is a key in the row's `json_object`, not
# a figure: no `?`, so the tuple is unchanged again. It must be there, though:
# `_row_to_audit_log` reads every key, and a missing one is a KeyError.
# PRD-018 STORY-004's `write_id` is likewise a key, not a figure: no `?`, so the
# tuple is unchanged a third time, and it must be there for the same reason.
#
# `"rows"` is quoted: ROWS is a keyword (window frames) and an unquoted alias
# is a syntax error.
_SUMMARY_SQL = f"""
WITH RECURSIVE split(entity, rest) AS (
    SELECT NULL, pii_entities || ','
      FROM audit_logs
     WHERE pii_entities IS NOT NULL
    UNION ALL
    SELECT substr(rest, 1, instr(rest, ',') - 1),
           substr(rest, instr(rest, ',') + 1)
      FROM split
     WHERE rest <> ''
)
SELECT
  (SELECT json_group_array(json_object(
              'id', id,
              'timestamp', timestamp,
              'user_id', user_id,
              'device', device,
              'prompt_hash', prompt_hash,
              'prompt_preview', prompt_preview,
              'response_hash', response_hash,
              'response_preview', response_preview,
              'model_used', model_used,
              'tokens_used', tokens_used,
              'was_duplicate_blocked', was_duplicate_blocked,
              'suspicious_pattern', suspicious_pattern,
              'success', success,
              'error_message', error_message,
              'pii_detected_input', pii_detected_input,
              'pii_detected_output', pii_detected_output,
              'pii_entities', pii_entities,
              'role', role,
              'denied_permission', denied_permission,
              'session_id', session_id,
              'dedup_key', dedup_key,
              'pattern_role', pattern_role,
              'pattern_action', pattern_action,
              'profile', profile,
              'ingress', ingress,
              'message_count', message_count,
              'input_tokens', input_tokens,
              'output_tokens', output_tokens,
              'streamed', streamed,
              'has_tool_calls', has_tool_calls,
              'conversation_key', conversation_key,
              'limit_exceeded', limit_exceeded,
              'ignored_params', ignored_params,
              'write_id', write_id,
              'provider', provider,
              'upstream_model', upstream_model,
              'provider_trust', provider_trust,
              'pii_input_relaxed', pii_input_relaxed,
              'usage_estimated', usage_estimated,
              'streamed_realtime', streamed_realtime,
              'reasoning_shown', reasoning_shown,
              'stream_redaction_divergence', stream_redaction_divergence,
              'completion_id', completion_id))
     FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?)
  ) AS "rows",
  (SELECT COUNT(*) FROM audit_logs) AS total_recorded,
  (SELECT COUNT(*) FROM audit_logs WHERE was_duplicate_blocked = 1)
      AS blocked_duplicates,
  (SELECT COUNT(*) FROM audit_logs WHERE {_BLOCKED_SUSPICIOUS_WHERE})
      AS blocked_suspicious,
  (SELECT COUNT(DISTINCT user_id) FROM audit_logs) AS unique_users,
  (SELECT COUNT(*) FROM audit_logs WHERE success = 1) AS successful_queries,
  (SELECT COUNT(*) FROM audit_logs
    WHERE pii_detected_input = 1 OR pii_detected_output = 1)
      AS pii_detected_queries,
  (SELECT json_group_array(model_used) FROM (
      SELECT model_used FROM audit_logs
       WHERE model_used IS NOT NULL
       GROUP BY model_used
       ORDER BY COUNT(*) DESC
       LIMIT ?)) AS top_models,
  (SELECT json_group_array(user_id) FROM (
      SELECT user_id FROM audit_logs
       GROUP BY user_id
       ORDER BY COUNT(*) DESC
       LIMIT ?)) AS top_users,
  (SELECT json_group_array(entity) FROM (
      SELECT entity FROM split
       WHERE entity IS NOT NULL
       GROUP BY entity
       ORDER BY COUNT(*) DESC, entity ASC
       LIMIT ?)) AS top_pii_entities,
  (SELECT {_SUM_INPUT_TOKENS} FROM audit_logs) AS input_tokens,
  (SELECT {_SUM_OUTPUT_TOKENS} FROM audit_logs) AS output_tokens,
  (SELECT COUNT(*) FROM audit_logs WHERE {_BLOCKED_USAGE_LIMITS_WHERE})
      AS blocked_usage_limits
"""


def _decode_rows(value: Any) -> list[AuditLog]:
    return [_row_to_audit_log(entry) for entry in json.loads(value)]


def _decode_ranked(value: Any) -> list[str]:
    return list(json.loads(value))


def _decode_count(value: Any) -> int:
    return int(value)


#: One decoder per figure, turning its column into the type the standalone
#: function returns. A module-level dict so each figure's decode can be
#: isolated -- and so a test can break exactly one of them.
_SUMMARY_DECODERS = {
    "rows": _decode_rows,
    "total_recorded": _decode_count,
    "blocked_duplicates": _decode_count,
    "blocked_suspicious": _decode_count,
    "unique_users": _decode_count,
    "successful_queries": _decode_count,
    "pii_detected_queries": _decode_count,
    "top_models": _decode_ranked,
    "top_users": _decode_ranked,
    "top_pii_entities": _decode_ranked,
    "input_tokens": _decode_count,
    "output_tokens": _decode_count,
    "blocked_usage_limits": _decode_count,
}


def _summary_figure_by_figure(
    row_limit: int, ranked_limit: int, cause: Exception
) -> SummarySnapshot:
    """The thirteen standalone reads, each guarded, when the one statement failed.

    A dead statement carries no attribution: every figure fails anonymously and
    the console has nothing to name. That is the blank page Risk 6 describes,
    so the failure path buys the attribution back the only way left -- by
    reading the figures individually and letting each one succeed or fail on
    its own. It costs up to thirteen round trips, and it is paid **only** when the
    batch is already broken; the success path stays at one.

    `cause` is the statement's own failure. A figure that then reads fine is a
    figure that arrived, so `cause` is not recorded against it. It is used only
    when nothing at all came back -- the database is unreachable, or the table
    is gone -- where every figure carries it, so an outage still reads as an
    outage rather than as thirteen unrelated coincidences.
    """
    reads = (
        ("rows", lambda: list_audit_logs(limit=row_limit)),
        ("total_recorded", count_audit_logs),
        ("blocked_duplicates", count_blocked_duplicates),
        ("blocked_suspicious", count_blocked_suspicious),
        ("unique_users", count_unique_users),
        ("successful_queries", count_successful_queries),
        ("pii_detected_queries", count_pii_detected_queries),
        ("top_models", lambda: top_models(limit=ranked_limit)),
        ("top_users", lambda: top_users(limit=ranked_limit)),
        ("top_pii_entities", lambda: top_pii_entities(limit=ranked_limit)),
        ("input_tokens", sum_input_tokens),
        ("output_tokens", sum_output_tokens),
        ("blocked_usage_limits", count_blocked_usage_limits),
    )
    figures: dict = {}
    errors: dict = {}
    for name, read in reads:
        try:
            figures[name] = read()
        except Exception as exc:  # noqa: BLE001 -- attribution is the whole point
            errors[name] = exc
    if not figures:
        # Nothing came back individually either: the database is unreachable or
        # the table is gone. Report the statement's own failure rather than thirteen
        # copies of a downstream symptom.
        errors = {name: cause for name in SUMMARY_FIGURES}
    return SummarySnapshot(figures=figures, errors=errors)


def summary_snapshot(row_limit: int = 100, ranked_limit: int = 5) -> SummarySnapshot:
    """All thirteen admin summary figures, in one round trip.

    Two callers ran the same fan-out sequentially: `_READS` in
    `chat_ui/chat_ui/admin_state.py` with ten reads, and `GET /stats` with
    nine. Against a local file that cost nothing; against a remote endpoint it
    is ten round trips per page load (PRD-007 Section 6 Pattern 3).

    This is one statement. Not a client batch -- the driver has none, and its
    multi-statement `execute()` swallows errors (STORY-001 §2.6); see
    `_SUMMARY_SQL` for the whole finding and for the fact that the single
    SELECT measured 1.7 ms against 16.3 ms for the ten it replaces.

    **Attribution rides on column names, not on statements.** Each figure is a
    named column, so the `READ_LABEL_*` entries map one-to-one onto them
    and a figure that fails to decode fails alone. If the statement itself
    fails there are no columns to attribute anything to, and the read falls
    back to the thirteen standalone functions to buy the attribution back.

    `row_limit` and `ranked_limit` are parameters, not constants baked into the
    statement: the callers pass `REGISTER_ROW_LIMIT` and `RANKED_LIMIT`. They
    bind **positionally, in column order** -- see `_SUMMARY_SQL`.

    The one statement is one `READ` unit (PRD-018 D3). The fallback is outside it,
    so it runs once, after the statement's retry budget is spent; decoding is
    outside it too, so a decode `ValueError` is still one bad figure.
    """

    def _op(conn: _Connection) -> _Row:
        return conn.execute(
            _SUMMARY_SQL,
            (row_limit, ranked_limit, ranked_limit, ranked_limit),
        ).fetchone()

    try:
        row = _unit_of_work("summary_snapshot", StatementKind.READ, _op)
    except StorageError as exc:
        return _summary_figure_by_figure(row_limit, ranked_limit, exc)

    figures: dict = {}
    errors: dict = {}
    for name in SUMMARY_FIGURES:
        try:
            figures[name] = _SUMMARY_DECODERS[name](row[name])
        except Exception as exc:  # noqa: BLE001 -- one bad column is one bad figure
            errors[name] = exc
    return SummarySnapshot(figures=figures, errors=errors)


def _row_to_user(row: _Row) -> User:
    return User(
        user_id=row["user_id"],
        role=row["role"],
        token_hash=row["token_hash"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        token_budget_daily=row["token_budget_daily"],
        requests_per_minute=row["requests_per_minute"],
    )


def get_user(user_id: str) -> Optional[User]:
    """Returns the user regardless of active state -- administrative reads
    (CLI list/deactivate) must be able to see a revoked row."""

    def _op(conn: _Connection) -> Optional[User]:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)

    return _unit_of_work("get_user", StatementKind.READ, _op)


def find_user_by_token_hash(token_hash: str) -> Optional[User]:
    """Active users only. A revoked credential is indistinguishable from an
    unknown one by design -- PRD-005 Section 9 maps both to 401, and separating
    them would be a credential-enumeration oracle.

    A `users` table that hasn't been created yet (init_db() never ran against
    this connection) is folded into the same "no match" outcome rather than
    raised -- callers resolving a credential need a closed door, not a 500.

    That arm catches MissingRelationError and nothing wider (PRD-007 STORY-004):
    a storage failure that is not a missing table surfaces as a 500 rather than
    a silent 401, because a real outage must not read as a bad credential."""

    def _op(conn: _Connection) -> Optional[User]:
        try:
            with _translated():
                row = conn.execute(
                    "SELECT * FROM users WHERE token_hash = ? AND active = 1",
                    (token_hash,),
                ).fetchone()
        except MissingRelationError:
            return None
        if row is None:
            return None
        return _row_to_user(row)

    return _unit_of_work("find_user_by_token_hash", StatementKind.READ, _op)


def list_users(limit: int = 100) -> list[User]:
    def _op(conn: _Connection) -> list[User]:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_user(row) for row in rows]

    return _unit_of_work("list_users", StatementKind.READ, _op)


def count_active_users() -> int:
    def _op(conn: _Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE active = 1"
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_active_users", StatementKind.READ, _op)


def insert_user(entry: User) -> str:
    """Raises app.db.errors.IntegrityError on a duplicate user_id or token_hash --
    deliberately not caught here; the translation happens at this module's
    boundary but the handling stays with the caller, which needs to tell those two
    cases apart. IntegrityError.constraint carries which constraint failed."""
    created_at = entry.created_at or datetime.now(timezone.utc).strftime(
        _TIMESTAMP_FORMAT
    )

    def _op(conn: _Connection) -> None:
        conn.execute(
            """
            INSERT INTO users (user_id, role, token_hash, active, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry.user_id,
                entry.role,
                entry.token_hash,
                int(entry.active),
                created_at,
            ),
        )

    _unit_of_work("insert_user", StatementKind.NON_IDEMPOTENT, _op)
    return entry.user_id


def deactivate_user(user_id: str) -> bool:
    """Revocation is not deletion: audit_logs rows carry a bare user_id with no
    foreign key, so removing the row would orphan the audit trail. Returns False
    when no such user exists, so the CLI can report a typo."""

    def _op(conn: _Connection) -> bool:
        cursor = conn.execute(
            "UPDATE users SET active = 0 WHERE user_id = ?", (user_id,)
        )
        return cursor.rowcount == 1

    return _unit_of_work("deactivate_user", StatementKind.IDEMPOTENT, _op)


def set_user_token_hash(user_id: str, token_hash: str) -> bool:
    """Credential rotation (STORY-004 `issue-token`). The old hash stops
    resolving the moment this returns."""

    def _op(conn: _Connection) -> bool:
        cursor = conn.execute(
            "UPDATE users SET token_hash = ? WHERE user_id = ?",
            (token_hash, user_id),
        )
        return cursor.rowcount == 1

    return _unit_of_work("set_user_token_hash", StatementKind.IDEMPOTENT, _op)


# "Leave this column alone" for set_user_limits(). None cannot mean that,
# because None is a real value there: it writes NULL, "use the role's limit".
_UNCHANGED: Any = object()


def set_user_limits(
    user_id: str,
    *,
    token_budget_daily: Optional[int] = _UNCHANGED,
    requests_per_minute: Optional[int] = _UNCHANGED,
) -> bool:
    """Per-user limit overrides (PRD-013 STORY-008, `manage_users.py
    set-limits`). Only the columns passed are written: an omitted argument
    leaves its column as it is, and `None` clears it to NULL.

    Values are not validated here -- the CLI owns parsing (`default`, `>= 1`).
    Column names come from the fixed pairs below, never from the caller.

    Returns False when no such user exists, so the CLI can report a typo. The
    next resolve() of that user's token sees the change: it already reads the
    row on every request (PRD Section 6.6)."""
    assignments = [
        (column, value)
        for column, value in (
            ("token_budget_daily", token_budget_daily),
            ("requests_per_minute", requests_per_minute),
        )
        if value is not _UNCHANGED
    ]
    if not assignments:
        raise ValueError("set_user_limits() needs at least one limit to set")

    set_clause = ", ".join(f"{column} = ?" for column, _ in assignments)

    def _op(conn: _Connection) -> bool:
        cursor = conn.execute(
            f"UPDATE users SET {set_clause} WHERE user_id = ?",
            (*(value for _, value in assignments), user_id),
        )
        return cursor.rowcount == 1

    return _unit_of_work("set_user_limits", StatementKind.IDEMPOTENT, _op)


# Usage counters (PRD-013 Section 6.5). One statement each, both on the
# (user_id, day) primary key.
#
# **`RETURNING` works on the pinned driver** -- verified by STORY-009, because
# it was not among STORY-001's six behaviors. The admit statement below, run
# verbatim through raw `libsql==0.1.11` against the dev server, twice (the
# second after a server restart):
#
#   insert path:   fetchall() = [('2026-10-18', 29872699, 1, 0)]
#   conflict path: fetchall() = [('2026-10-18', 29872699, 2, 0)]
#   description   = day, window_start, window_requests, tokens_today
#   a fresh client reads the row back after commit(); window_start is an int
#
# So the gate is the one statement, one round trip, and `_Row` reads the four
# columns by name. One thing to know: **`rowcount` is 0 on a RETURNING
# statement**, insert and update alike, so nothing here may branch on it. The
# returned row is the evidence the attempt was counted. (The plain UPDATE in
# _CHARGE_USAGE_SQL reports `rowcount` 1 as STORY-001 found.)
#
# `day` and the window are the database's clock, never Python's: instances
# with skewed clocks share one day and one minute. `strftime` returns TEXT,
# which SQLite coerces for the integer division, so `window_start` is the
# integer unix minute. Both statements bind positionally -- named
# placeholders are not a verified behavior (see the _SUMMARY_SQL comment).
_ADMIT_USAGE_SQL = """
INSERT INTO usage_daily (user_id, day, requests, window_start, window_requests)
VALUES (?, date('now'), 1, strftime('%s','now') / 60, 1)
ON CONFLICT(user_id, day) DO UPDATE SET
    requests = requests + 1,
    window_requests = CASE WHEN window_start = excluded.window_start
                           THEN window_requests + 1 ELSE 1 END,
    window_start = excluded.window_start
RETURNING day, window_start, window_requests,
          input_tokens + output_tokens + unsplit_tokens AS tokens_today
"""

# Binds (input_tokens, output_tokens, unsplit_tokens, user_id, day).
_CHARGE_USAGE_SQL = """
UPDATE usage_daily
   SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?,
       unsplit_tokens = unsplit_tokens + ?
 WHERE user_id = ? AND day = ?
"""


def admit_usage(user_id: str) -> UsageAdmission:
    """Counts one authorized attempt and returns what both limit checks need.

    Atomic: the increment and the read are one statement on the server, so two
    instances admitting the same user at the same moment get two different
    `window_requests` values. One round trip. A new minute resets
    `window_requests` to 1 while `requests` keeps counting the day.

    Compares no limit -- STORY-010's usage_limits does that -- and decides
    nothing on failure: a storage error propagates as `StorageError`, and
    failing closed is the caller's rule (D9)."""

    def _op(conn: _Connection) -> UsageAdmission:
        row = conn.execute(_ADMIT_USAGE_SQL, (user_id,)).fetchone()
        return UsageAdmission(
            day=row["day"],
            window_start=row["window_start"],
            window_requests=row["window_requests"],
            tokens_today=row["tokens_today"],
        )

    return _unit_of_work("admit_usage", StatementKind.NON_IDEMPOTENT, _op)


def charge_usage(
    user_id: str,
    day: str,
    input_tokens: int,
    output_tokens: int,
    unsplit_tokens: int,
) -> bool:
    """Adds one call's reported tokens to the day admit_usage() returned.

    Charging the admitted `day` rather than today means a request that
    straddles midnight is charged to the day it was admitted (PRD Section 6.5).
    `unsplit_tokens` is total_tokens for a call that reported no split.

    Returns False when there is no row for (user_id, day), which a successful
    admit rules out. What to do with it is STORY-012's call (D9: the charge
    fails open)."""

    def _op(conn: _Connection) -> bool:
        cursor = conn.execute(
            _CHARGE_USAGE_SQL,
            (input_tokens, output_tokens, unsplit_tokens, user_id, day),
        )
        return cursor.rowcount == 1

    return _unit_of_work("charge_usage", StatementKind.NON_IDEMPOTENT, _op)


# The admin console's usage table (PRD-013 STORY-016, Section 6.10): one
# statement, and no parameters at all, so the positional-binding caveat on
# _SUMMARY_SQL does not arise.
#
# `usage_daily` drives the query. A user denied today necessarily has a counted
# attempt today, because admit_usage() increments before the limit is compared
# (Section 6.5), so the LEFT JOIN of denials loses nothing -- except a request
# admitted just before 00:00 UTC whose audit row lands just after, which is the
# same midnight straddle Section 6.5 accepts for the charge.
#
# `users` is LEFT JOINed so the break-glass `admin`, which has no users row, is
# kept; its role is resolved in Python (admin_formatting.to_usage_rows), never
# as a SQL COALESCE that would also label any orphan row "admin".
#
# Every "today" is the database's clock, as usage_daily.day is: SQLite
# evaluates 'now' once per statement, so the three uses agree. audit_logs
# stores `timestamp` as _TIMESTAMP_FORMAT ('YYYY-MM-DDTHH:MM:SSZ'), so the
# lexical range [date('now'), date('now','+1 day')) is exactly that UTC day.
# The audit timestamp is the writing instance's clock, so skew can move a
# denial written within seconds of midnight across the boundary.
#
# The denial predicate is _BLOCKED_USAGE_LIMITS_WHERE interpolated, not
# retyped: /stats, the Register's verdict and this table count the same rows.
_USAGE_SNAPSHOT_SQL = f"""
SELECT d.user_id, u.role, u.token_budget_daily, u.requests_per_minute,
       d.requests, d.input_tokens, d.output_tokens, d.unsplit_tokens,
       COALESCE(r.denied, 0) AS denied
  FROM usage_daily AS d
  LEFT JOIN users AS u ON u.user_id = d.user_id
  LEFT JOIN (SELECT user_id, COUNT(*) AS denied
               FROM audit_logs
              WHERE {_BLOCKED_USAGE_LIMITS_WHERE}
                AND timestamp >= date('now')
                AND timestamp < date('now', '+1 day')
              GROUP BY user_id) AS r ON r.user_id = d.user_id
 WHERE d.day = date('now')
 ORDER BY d.user_id
"""


def usage_snapshot() -> list[UsageDay]:
    """Every user's counters for the database's current UTC day, in one statement.

    Read-only, and resolves no limit: the caller does that with
    `usage_limits.limits_for`, so the table and the gate share one rule. Ordered
    by user_id so the caller's sort has a deterministic tie order. A storage
    failure propagates as StorageError; naming it is the caller's job (the
    console's READ_LABEL_USAGE)."""

    def _op(conn: _Connection) -> list[UsageDay]:
        return [
            UsageDay(
                user_id=row["user_id"],
                role=row["role"],
                token_budget_daily=row["token_budget_daily"],
                requests_per_minute=row["requests_per_minute"],
                requests=row["requests"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                unsplit_tokens=row["unsplit_tokens"],
                denied=row["denied"],
            )
            for row in conn.execute(_USAGE_SNAPSHOT_SQL).fetchall()
        ]

    return _unit_of_work("usage_snapshot", StatementKind.READ, _op)


def _row_to_chat_session(row: _Row) -> ChatSession:
    """One `chat_sessions` row as the dataclass STORY-002 declared.

    No coercion, unlike `_row_to_user` above: all five columns are TEXT NOT NULL
    in the DDL, so there is no integer-as-boolean to translate back.
    """
    return ChatSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_chat_session(user_id: str, title: str) -> str:
    """Writes one owned session and returns its new id.

    **The id is minted here, and the signature has no `session_id` parameter at
    all.** A caller-supplied id is a caller-chosen id, and the caller furthest
    up this path is `ChatState.active_session_id` -- a Reflex state var, which
    PRD-008 Risk 3 records is serialized to the client and mutable by
    client-originated events. Accepting one would let a client pick primary
    keys. `uuid.uuid4()` is what PRD Section 4 spells in the schema.

    `created_at` and `updated_at` are written from **one** `now`. Two calls to
    `datetime.now()` can straddle a second boundary, and a brand-new session
    whose two columns disagree would sort below itself in the rail's
    `updated_at DESC` read for a reason no reader could ever reconstruct.

    `user_id` is first and undefaulted, as on all six of these -- PRD Risk 2:
    the rule lives in the signature, so an omission is a `TypeError` here rather
    than a leak at runtime.

    **`IDEMPOTENT` through one rule (PRD-018 Section 6.3 row 11).** If an attempt
    after the first meets this very `session_id` already in the table, the earlier
    attempt landed and its response was lost, so the call returns the id instead of
    raising. Every attempt writes the same id and timestamps, minted above.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
    attempts = 0

    def _op(conn: _Connection) -> None:
        nonlocal attempts
        attempts += 1
        conn.execute(
            """
            INSERT INTO chat_sessions
                (session_id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, title, now, now),
        )

    try:
        _unit_of_work("create_chat_session", StatementKind.IDEMPOTENT, _op)
    except IntegrityError as exc:
        # PRD-018 Section 6.3 row 11, D3. The id and both timestamps were minted
        # above, so every attempt writes the same row. A duplicate `session_id`
        # on an attempt after the first therefore means an earlier attempt landed
        # (its response was lost) and the row is ours: that is success. On the
        # first attempt the same error is a real collision and is raised as ever.
        if attempts > 1 and exc.constraint == "chat_sessions.session_id":
            return session_id
        raise
    return session_id


def get_chat_session(session_id: str, user_id: str) -> Optional[ChatSession]:
    """The owner's session, or None.

    **A session that exists but belongs to someone else returns `None`, exactly
    as a session that does not exist does.** Not an exception, and not an
    exception that tells the two apart: a caller able to distinguish "yours but
    missing" from "someone else's" has a membership oracle over other people's
    session ids. `find_user_by_token_hash` above refuses to be one for
    credentials for the same reason.

    It deliberately does *not* carry that function's `MissingRelationError` arm.
    That arm exists because credential resolution needs a closed door rather
    than a 500; a missing `chat_sessions` table is a broken boot, and folding it
    into "no such session" would render an empty rail on a database that never
    ran `init_db()`.
    """

    def _op(conn: _Connection) -> Optional[ChatSession]:
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return _row_to_chat_session(row)

    return _unit_of_work("get_chat_session", StatementKind.READ, _op)


def list_chat_sessions(user_id: str, limit: int = 50) -> list[ChatSession]:
    """One user's sessions, newest activity first.

    `WHERE user_id = ? ORDER BY updated_at DESC` is `idx_chat_sessions_user_updated`
    read exactly (`app/db/models.py`), which is why the index was declared with
    that column order.

    The limit is a literal default rather than `settings.CHAT_SESSION_LIMIT`.
    No function in this module reads a setting for a limit -- `list_users` and
    `list_audit_logs` both default and let the caller pass one, which
    `app/routers/admin.py` does -- and the flag-and-limit policy belongs to
    `app/services/chat_sessions.py`, where PRD Section 6 also puts the
    `CHAT_HISTORY_ENABLED` short-circuit.

    **Known tie.** `updated_at` is a second-resolution TEXT timestamp, so two
    sessions touched within the same second order arbitrarily -- the defect
    PRD-006 Section 13 already recorded for `audit_logs`. For the rail a tie is
    cosmetic. For a transcript it would not be, which is why `chat_messages` is
    read by `id` and never by time.
    """

    def _op(conn: _Connection) -> list[ChatSession]:
        rows = conn.execute(
            """
            SELECT * FROM chat_sessions
             WHERE user_id = ?
             ORDER BY updated_at DESC
             LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [_row_to_chat_session(row) for row in rows]

    return _unit_of_work("list_chat_sessions", StatementKind.READ, _op)


def rename_chat_session(session_id: str, user_id: str, title: str) -> bool:
    """Retitles an owned session. False when there was no such owned row.

    **`updated_at` is deliberately not touched.** Renaming is not activity: a
    rename that bumped the timestamp would reorder the rail and move the row the
    user was looking at while they were looking at it. The omission is a
    decision, not an oversight.

    The `False` arm covers "no such session" and "someone else's session"
    without distinguishing them -- the zero-row case PRD-007 STORY-006 flagged
    as the one that regresses silently. Note that `rowcount` counts matched rows
    and not changed ones, so renaming to the identical title still returns True:
    the same property `test_deactivate_user_is_idempotent` pins for
    `deactivate_user`.
    """

    def _op(conn: _Connection) -> bool:
        cursor = conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE session_id = ? AND user_id = ?",
            (title, session_id, user_id),
        )
        return cursor.rowcount == 1

    return _unit_of_work("rename_chat_session", StatementKind.IDEMPOTENT, _op)


def touch_chat_session(session_id: str, user_id: str) -> bool:
    """Moves an owned session's `updated_at` to now. False when not owned.

    The send path's reorder, called after the transcript write in PRD Section
    6's diagram, and the only function that writes `updated_at` after creation
    -- `rename_chat_session` above pointedly does not.
    """
    now = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)

    def _op(conn: _Connection) -> bool:
        cursor = conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ? AND user_id = ?",
            (now, session_id, user_id),
        )
        return cursor.rowcount == 1

    return _unit_of_work("touch_chat_session", StatementKind.IDEMPOTENT, _op)


def delete_chat_session(session_id: str, user_id: str) -> bool:
    """Removes an owned session and its messages in one transaction.

    **The message delete is scoped by ownership, not by `session_id`.**
    `chat_messages` carries no `user_id` column, so the obvious
    `DELETE FROM chat_messages WHERE session_id = ?` would destroy a foreign
    owner's transcript while the statement below correctly refused to delete
    their session row -- this function would return False and the messages would
    be gone anyway. The subselect makes both statements answer to one predicate,
    and it is the whole of this story's AC 7.

    **Messages first, session second, one `_session()` block.** One block is one
    transaction (`_Connection.__exit__` commits on clean exit and rolls back on
    exception), so there is no window in which the session is gone and its
    messages are not. STORY-002 declared no foreign key on purpose; *this* is
    the enforcement, and a later story that adds `ON DELETE CASCADE` has to
    replace it rather than simply drop it.

    **`audit_logs` is not touched, by any statement, ever.** PRD Section 9: the
    orphaned `session_id` on those rows is expected, and it is what preserves
    the evidence when a user tidies their list. Deleting a conversation deletes
    a conversation; it does not edit the record of what was asked.

    **`IDEMPOTENT`, with one accepted residual (PRD-018 Section 6.3).** If the
    commit lands and its response is lost (`OUTCOME_UNKNOWN`), the retry finds the
    rows already gone, matches none, and returns `False` for a delete that did
    happen. The stored state is right; the boolean is not. Fixing that needs a
    read-back design, not a retry rule; STORY-014 documents it.
    """

    def _op(conn: _Connection) -> bool:
        conn.execute(
            """
            DELETE FROM chat_messages
             WHERE session_id = ?
               AND session_id IN (
                   SELECT session_id FROM chat_sessions
                    WHERE session_id = ? AND user_id = ?
               )
            """,
            (session_id, session_id, user_id),
        )
        cursor = conn.execute(
            "DELETE FROM chat_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        return cursor.rowcount == 1

    return _unit_of_work("delete_chat_session", StatementKind.IDEMPOTENT, _op)


def _row_to_stored_message(row: _Row) -> StoredMessage:
    """One `chat_messages` row as the dataclass STORY-002 declared.

    **`pii_redacted` is the only coercion, and it is the only one that belongs
    here.** It is `INTEGER NOT NULL DEFAULT 0` in the DDL against a `bool` field,
    the same shape `users.active` has -- so it gets the same `bool()` that
    `_row_to_user` gives that column, and for the same reason.

    `tokens_used`, `audit_id` and `history_trimmed` are pointedly *not* coerced.
    All three are `INTEGER` columns against `Optional[int]` fields, and an
    `int()` around them would turn a genuine `NULL` into `0` -- a lie on a bubble
    that never called a model, and indistinguishable from a real zero-token
    response. On `history_trimmed` (PRD-010) the lie is worse, because both
    values are meaningful and the column is how a reload reproduces the footer:
    `0` says "this send dropped nothing" and `NULL` says "this row was written
    before the feature existed". The driver returns Python integers for INTEGER
    columns already; there is nothing to convert and everything to lose by
    converting.
    """
    return StoredMessage(
        session_id=row["session_id"],
        kind=row["kind"],
        content=row["content"],
        prompt=row["prompt"],
        model_used=row["model_used"],
        tokens_used=row["tokens_used"],
        audit_id=row["audit_id"],
        pii_redacted=bool(row["pii_redacted"]),
        pii_entities=row["pii_entities"],
        pattern=row["pattern"],
        required_permission=row["required_permission"],
        first_query_at=row["first_query_at"],
        detail=row["detail"],
        history_trimmed=row["history_trimmed"],
        created_at=row["created_at"],
        id=row["id"],
    )


def append_chat_message(message: StoredMessage, session_id: str, user_id: str) -> int:
    """Writes one message into an owned session and returns its new `id`.

    **One statement, not two.** The ownership check is the `WHERE EXISTS` on the
    INSERT itself, so the database decides "does this session exist and belong to
    this caller" and "write the row" in a single evaluation. A `get_chat_session`
    followed by an INSERT would be two statements over a table whose id comes
    from `ChatState.active_session_id` -- a Reflex state var, serialized to the
    client and mutable by client-originated events (PRD-008 Risk 3). Between the
    read and the write the session can be deleted or, in a two-instance
    deployment, re-created; one statement has no such window.

    **`session_id` and `user_id` are the parameters, and `message.session_id` is
    never read.** `StoredMessage` carries a `session_id` field of its own, so
    there are two candidate values and only one may win. The parameter wins in
    *both* places -- the column written and the `EXISTS` predicate -- because
    reading one value twice is what makes it impossible to check ownership
    against one session and file the row under another. A caller that hands in a
    `StoredMessage` built for someone else's session gets it written to the
    session they were authorized for, or gets an exception; never a row smuggled
    sideways.

    **A foreign session and an unknown session raise the same exception with the
    same message.** `get_chat_session` returns `None` for both cases so that no
    caller can tell "yours but missing" from "someone else's" -- a distinction
    that is a membership oracle over other people's session ids. AC 6 requires a
    *visible* failure here rather than a `None`, since the return type is the new
    row id and a silent no-op would read as a successful write in STORY-014's
    degraded arm. Visible is not the same as informative: it raises, and it says
    the same thing either way.

    `StorageError` and not a new exception type, and not a builtin: it is the
    class every consumer of `app/db/` already catches, so STORY-014's degraded
    arm reports "the turn was not saved" instead of taking the request down with
    an unhandled `PermissionError`.

    **`rowcount` is checked before `lastrowid` is read, and the order is load-
    bearing.** `lastrowid` after an insert that matched nothing carries over from
    whatever ran before it, so a caller reading it first gets a plausible integer
    for a write that never happened. Raising inside the `with` block also rolls
    the transaction back (`_Connection.__exit__`), so "no row is written" holds
    twice over.

    `created_at` is stamped here when the caller leaves it `None`, the way
    `insert_user` stamps its own; `id` is always the column's, never the
    dataclass's, because `AUTOINCREMENT` is what makes it the transcript's order.

    **`history_trimmed` gets no `or None` and no `int()`** (PRD-010). It is the
    one optional field here where `0` and `NULL` say different things -- "this
    send dropped nothing" against "written before the feature existed" -- so the
    normalization the next paragraph describes for `pii_entities`, where `""`
    and `NULL` mean the same thing, would destroy information here rather than
    tidy it.

    `pii_entities` is normalized: `""` is stored as `NULL`, exactly as
    `app/services/audit_logger.py:45` already stores an empty entity list. The
    difference matters one layer up -- `"".split(",")` is `[""]`, a phantom
    entity on a message that had none, which is what STORY-015 would render.
    Normalizing at the layer that owns the column means no future caller has to
    remember the rule.
    """
    created_at = message.created_at or datetime.now(timezone.utc).strftime(
        _TIMESTAMP_FORMAT
    )

    def _op(conn: _Connection) -> int:
        cursor = conn.execute(
            """
            INSERT INTO chat_messages (
                session_id, kind, content, created_at, prompt, model_used,
                tokens_used, audit_id, pii_redacted, pii_entities, pattern,
                required_permission, first_query_at, detail, history_trimmed
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
             WHERE EXISTS (
                 SELECT 1 FROM chat_sessions
                  WHERE session_id = ? AND user_id = ?
             )
            """,
            (
                session_id,
                message.kind,
                message.content,
                created_at,
                message.prompt,
                message.model_used,
                message.tokens_used,
                message.audit_id,
                int(message.pii_redacted),
                message.pii_entities or None,
                message.pattern,
                message.required_permission,
                message.first_query_at,
                message.detail,
                message.history_trimmed,
                session_id,
                user_id,
            ),
        )
        if cursor.rowcount != 1:
            raise StorageError("chat session not available for this owner")
        return cursor.lastrowid

    return _unit_of_work("append_chat_message", StatementKind.NON_IDEMPOTENT, _op)


def list_chat_messages(session_id: str, user_id: str) -> list[StoredMessage]:
    """One owned session's whole transcript, in the order it was written.

    **`ORDER BY id ASC`, never by a timestamp.** `created_at` is a
    second-resolution TEXT column, so two messages written inside one second tie
    and order arbitrarily -- the defect PRD-006 Section 13 recorded for
    `audit_logs`, and the one `list_chat_sessions` above accepts as cosmetic for
    the rail. It is not cosmetic here: a transcript that reorders itself on
    reload is the same conversation read wrong, which is precisely the bug this
    PRD exists to remove. `AUTOINCREMENT` is the order; `created_at` is
    displayed. `(session_id, id)` is `idx_chat_messages_session_id` read exactly,
    which is why the index was declared with that column order.

    **Ownership is a subselect, because `chat_messages` has no `user_id`
    column.** The obvious `WHERE session_id = ?` would hand a foreign owner's
    transcript to anyone who guessed an id. This is `delete_chat_session`'s
    predicate, reused deliberately: one rule, expressed the same way in the two
    places that reach this table.

    A foreign or unknown session yields `[]` -- not an exception, and not a
    special-cased branch. The empty list falls out of the predicate, which is why
    there is no `if` here to forget. `append_chat_message` raises instead, and the
    asymmetry is intended: a read that finds nothing is an ordinary outcome, a
    write that silently lands nowhere is not.

    **No `limit`, deliberately.** PRD Section 4 caps sessions, not messages
    within one, and a partial transcript is a wrong transcript -- worse than a
    slow one, because nothing on screen says it is partial. If message volume
    ever forces the issue it is a paging design with a visible control, not a
    default argument added here.
    """

    def _op(conn: _Connection) -> list[StoredMessage]:
        rows = conn.execute(
            """
            SELECT * FROM chat_messages
             WHERE session_id = ?
               AND session_id IN (
                   SELECT session_id FROM chat_sessions
                    WHERE session_id = ? AND user_id = ?
               )
             ORDER BY id ASC
            """,
            (session_id, session_id, user_id),
        ).fetchall()
        return [_row_to_stored_message(row) for row in rows]

    return _unit_of_work("list_chat_messages", StatementKind.READ, _op)


def count_chat_sessions(user_id: str) -> int:
    """How many sessions this user has, in total.

    Exists so the rail can state its cap against a true total, the way PRD-006's
    register reports "100 most recent of 3,180". A count is the only honest way
    to say that: `len(list_chat_sessions(...))` can never exceed the limit it was
    called with, so a capped list can report "50 of 50" on an account with two
    hundred sessions and be indistinguishable from one with exactly fifty.

    It therefore ignores `CHAT_SESSION_LIMIT` entirely -- a count that respected
    the display cap could not produce the one number worth printing.

    Sessions, not messages. Nothing caps a transcript (`list_chat_messages`
    above), so there is no second number to report.
    """

    def _op(conn: _Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chat_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row["n"]

    return _unit_of_work("count_chat_sessions", StatementKind.READ, _op)


# --- Action decisions (PRD-016 STORY-015) ---


def _insert_action_decision_rows(
    conn: _Connection, rows: Sequence[ActionDecisionRow]
) -> list[int]:
    """The batch's rows on `conn`; their ids in input order (PRD-018 D4).

    Per row, keyed by `row.write_id` when present: `ON CONFLICT(write_id) DO
    NOTHING RETURNING id`, then only when that returned no row (a replay) a
    `SELECT id ... WHERE write_id = ?` on the same connection (see
    `_keyed_row_id`). `lastrowid` is never read on a keyed row. An unkeyed row
    is today's plain INSERT and `lastrowid`. `ids` is created inside: a retry
    starts the batch over, and a replay must not append a second set of ids.
    Per-row statements keep input order without depending on multi-row
    `RETURNING` ordering, which SQLite does not guarantee.
    """
    ids: list[int] = []
    for row in rows:
        keyed = row.write_id is not None
        cursor = conn.execute(
            """
            INSERT INTO action_decisions (
                timestamp, audit_id, session_id, user_id, role,
                tool_call_id, tool_name, operation_kind, target_preview,
                arguments_hash, arguments_preview, decision, rule, reason,
                granted_by, classifications, policy_digest, write_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            + (_ON_WRITE_ID_CONFLICT if keyed else ""),
            (
                row.timestamp,
                row.audit_id,
                row.session_id,
                row.user_id,
                row.role,
                row.tool_call_id,
                row.tool_name,
                row.operation_kind,
                row.target_preview,
                row.arguments_hash,
                row.arguments_preview,
                row.decision,
                row.rule,
                row.reason,
                row.granted_by,
                row.classifications,
                row.policy_digest,
                row.write_id,
            ),
        )
        if keyed:
            ids.append(_keyed_row_id(conn, "action_decisions", cursor, row.write_id))
        else:
            ids.append(cursor.lastrowid)
    return ids


def insert_action_decisions(rows: Sequence[ActionDecisionRow]) -> list[int]:
    """Write one batch of action decision rows (PRD-016 Section 6.10, F10, D8).

    **One `_session()` block, so one transaction.** Each row is its own
    `INSERT`, and `_Connection.__exit__` rolls back on any exception, so a
    failure on row *k* leaves no row of the batch: all land or none do. One
    statement per row rather than `executemany` (which reports no per-row id)
    or a multi-row `INSERT ... RETURNING id` (whose row order SQLite does not
    guarantee): one statement per row gives the ids in input order.

    An empty `rows` returns `[]` without opening a session: a response with no
    tool calls costs no round trip.

    **Per-call kind (PRD-018 D4, STORY-004).** When every row carries a
    `write_id` the unit is `IDEMPOTENT`: it is retried on every infrastructure
    failure class, always **from row 1** (the whole block is the unit), and a
    row that already landed meets `ON CONFLICT(write_id) DO NOTHING` and reads
    its original id back (`RETURNING id`, or one `SELECT` on conflict; PRD 6.4's
    "SELECT rather than RETURNING" was reversed so the healthy path adds no
    round trip). One unkeyed row makes the unit `NON_IDEMPOTENT`, exactly as
    before: an `OUTCOME_UNKNOWN` commit is never replayed.
    """
    if not rows:
        return []

    def _op(conn: _Connection) -> list[int]:
        return _insert_action_decision_rows(conn, rows)

    return _unit_of_work(
        "insert_action_decisions", _keyed_kind([row.write_id for row in rows]), _op
    )


def drain_journal_entry(
    audit: Optional[AuditLog],
    decisions: Sequence[ActionDecisionRow],
    *,
    audit_id: Optional[int] = None,
) -> int:
    """Replay one journal entry into the database; return the audit row id
    (PRD-018 F6 drain half, D11, STORY-009).

    **One transaction per entry (D11).** The audit row (when there is one) is
    inserted keyed (`ON CONFLICT(write_id) DO NOTHING RETURNING id`, then one
    `SELECT id` on conflict, see `_keyed_row_id`), and every decision is
    rebuilt with `audit_id` set to THAT id and inserted keyed in the same unit.
    The id is always resolved here by `write_id`, never taken from a cache: the
    journal cannot know the id the database will assign. A decisions-only entry
    (`audit is None`) carries the `audit_id` its audit row already has and
    inserts the decisions alone. The audit row keeps its original `timestamp`
    (`_insert_audit_row` writes `entry.timestamp`).

    A replay is a no-op: every row meets `ON CONFLICT DO NOTHING`, so a crash
    between this commit and the journal's checkpoint costs nothing at the next
    boot. The kind is a literal `IDEMPOTENT`, not `_keyed_kind(...)`: the
    journal refuses an unkeyed row at append (`audit_journal._validate`), and a
    hand-built unkeyed call is refused here with `ValueError` before any
    session opens. The rows are rebuilt inside `_op`, so a retried unit starts
    over from the immutable inputs.
    """
    decisions = tuple(decisions)
    if (audit is None) == (audit_id is None):
        raise ValueError("drain_journal_entry needs exactly one of audit or audit_id")
    if audit is not None and not audit.write_id:
        raise ValueError("drain_journal_entry: the audit row needs a write_id")
    if audit is None and not decisions:
        raise ValueError("drain_journal_entry: a decisions-only entry needs decisions")
    if any(not d.write_id for d in decisions):
        raise ValueError("drain_journal_entry: every decision needs a write_id")

    def _op(conn: _Connection) -> int:
        row_id = _insert_audit_row(conn, audit) if audit is not None else audit_id
        if decisions:
            _insert_action_decision_rows(
                conn, [replace(d, audit_id=row_id) for d in decisions]
            )
        return row_id

    return _unit_of_work("drain_journal_entry", StatementKind.IDEMPOTENT, _op)


def _row_to_action_decision_row(row: Mapping[str, Any]) -> ActionDecisionRow:
    """Map one action_decisions row onto `ActionDecisionRow`, by column name."""
    return ActionDecisionRow(
        id=row["id"],
        timestamp=row["timestamp"],
        audit_id=row["audit_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        role=row["role"],
        tool_call_id=row["tool_call_id"],
        tool_name=row["tool_name"],
        operation_kind=row["operation_kind"],
        target_preview=row["target_preview"],
        arguments_hash=row["arguments_hash"],
        arguments_preview=row["arguments_preview"],
        decision=row["decision"],
        rule=row["rule"],
        reason=row["reason"],
        granted_by=row["granted_by"],
        classifications=row["classifications"],
        policy_digest=row["policy_digest"],
        write_id=row["write_id"],
    )


def list_action_decisions(
    limit: int = 100,
    user_id: Optional[str] = None,
    decision: Optional[str] = None,
    audit_id: Optional[int] = None,
) -> list[ActionDecisionRow]:
    """The most recent action decisions, newest first (PRD-016 F10).

    **`ORDER BY id DESC`, never by the timestamp.** `timestamp` is a
    second-resolution TEXT column, and every row of one `record()` call shares
    one, so ordering by it ties arbitrarily (PRD-006 Section 13, as
    `list_chat_messages` documents). `AUTOINCREMENT` is the order.

    `user_id`, `decision` and `audit_id` filter when given and combine with
    AND. The clauses are fixed strings and only the values are bound, so no
    caller text reaches the SQL. `decision` is not validated here: STORY-016's
    router rejects an unknown value with 422, and here one simply matches no
    row. `audit_id` (PRD-017 Section 10) is one request's decisions, by its
    `audit_logs.id`; `idx_action_decisions_audit` serves it, and the router
    rejects a non-integer, zero or negative value with 422.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if decision is not None:
        clauses.append("decision = ?")
        params.append(decision)
    if audit_id is not None:
        clauses.append("audit_id = ?")
        params.append(audit_id)
    where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
    params.append(limit)

    def _op(conn: _Connection) -> list[ActionDecisionRow]:
        rows = conn.execute(
            f"SELECT * FROM action_decisions {where}ORDER BY id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_row_to_action_decision_row(row) for row in rows]

    return _unit_of_work("list_action_decisions", StatementKind.READ, _op)


def count_action_decisions() -> dict[str, int]:
    """How many action decisions of each kind, over the whole table (PRD-016 F10).

    Every decision in `ACTION_DECISION_VALUES` is a key, 0 when it has no
    rows, so an empty table reads `{"allow": 0, "flag": 0, "deny": 0}` --
    what STORY-016's `/stats` reports.
    """
    counts = {value: 0 for value in ACTION_DECISION_VALUES}

    def _op(conn: _Connection) -> list[_Row]:
        return conn.execute(
            "SELECT decision, COUNT(*) AS n FROM action_decisions GROUP BY decision"
        ).fetchall()

    rows = _unit_of_work("count_action_decisions", StatementKind.READ, _op)
    for row in rows:
        counts[row["decision"]] = row["n"]
    return counts
