import json
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping, Optional
from urllib.parse import urlsplit

import libsql

from app.config import settings
from app.db.errors import (
    DatabaseAuthError,
    DatabaseUnreachableError,
    IntegrityError,
    MissingRelationError,
    StorageError,
)
from app.db.models import (
    AUDIT_LOGS_ADDED_COLUMNS,
    CREATE_AUDIT_LOGS_TABLE,
    CREATE_USERS_TABLE,
    CREATE_USERS_TOKEN_HASH_INDEX,
    AuditLog,
    User,
)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_client_lock = threading.Lock()
_client_key: Optional[tuple[str, str]] = None
_client: Optional[Any] = None


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
    """
    global _client_key, _client
    key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
    with _client_lock:
        if _client is None or _client_key != key:
            # Not closing the previous client: close() discards uncommitted work
            # (STORY-001 §2.2) and the key only changes under test.
            _client = libsql.connect(key[0], auth_token=key[1])
            _client_key = key
        return _client


class _Row:
    """A result row that answers both `row["timestamp"]` and `(count,) = row`.

    libSQL returns plain tuples and offers no `row_factory` hook (STORY-001
    §2.1), but `cursor.description` is populated -- for `SELECT *`, for aliased
    aggregates like `COUNT(*) AS n`, and for `PRAGMA table_info` alike. Mapping
    those names back on is what lets `_row_to_audit_log()`'s 19 named reads, the
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
        self._cursor.execute(sql, *parameters)
        self._name_index = None
        return self

    def fetchone(self) -> Optional[_Row]:
        return self._wrap(self._cursor.fetchone())

    def fetchall(self) -> list:
        return [self._wrap(values) for values in self._cursor.fetchall()]

    def fetchmany(self, *args) -> list:
        return [self._wrap(values) for values in self._cursor.fetchmany(*args)]

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
    """

    __slots__ = ("_client",)

    def __init__(self, client: Any) -> None:
        self._client = client

    def execute(self, sql: str, *parameters) -> _Cursor:
        return _Cursor(self._client.execute(sql, *parameters))

    def cursor(self) -> _Cursor:
        return _Cursor(self._client.cursor())

    def commit(self) -> None:
        self._client.commit()

    def rollback(self) -> None:
        self._client.rollback()

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
        if exc_type is None:
            self._client.commit()
        else:
            self._client.rollback()
        return False


def get_connection() -> _Connection:
    """A transaction handle over the process-wide client.

    Public because thirteen test modules open one directly. The signature is
    unchanged from the `sqlite3` version; only what it hands back moved, and the
    wrapper above exists so that nothing downstream can tell.
    """
    return _Connection(_shared_client())


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


@contextmanager
def _translated() -> Iterator[None]:
    """Driver exceptions in, app.db.errors exceptions out.

    The single seam in the codebase where the driver's failure shape is known.
    STORY-004 wrote this to be rewritten here, and `app/db/errors.py` did not
    have to change.
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
        raise StorageError(message) from exc


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
    """
    if not settings.DB_BOOTSTRAP_ENABLED:
        return

    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)
        conn.execute(CREATE_USERS_TABLE)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)


def _add_missing_columns(conn: _Connection) -> None:
    """Brings a pre-existing audit_logs table up to the current schema.

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
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
        if name in existing:
            continue
        try:
            with _translated():
                conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}")
        except StorageError as exc:
            if not _is_duplicate_column(exc, name):
                raise


def insert_audit_log(entry: AuditLog) -> int:
    with _session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (
                timestamp, user_id, device, prompt_hash, prompt_preview,
                response_hash, response_preview, model_used, tokens_used,
                was_duplicate_blocked, suspicious_pattern, success, error_message,
                pii_detected_input, pii_detected_output, pii_entities,
                role, denied_permission
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
            ),
        )
        return cursor.lastrowid


def find_duplicate_timestamp(prompt_hash: str, since: str) -> Optional[str]:
    with _session() as conn:
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE prompt_hash = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (prompt_hash, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None


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
    )


def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with _session() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_audit_log(row)


def count_audit_logs(user_id: Optional[str] = None) -> int:
    with _session() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM audit_logs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def list_audit_logs(limit: int = 100, user_id: Optional[str] = None) -> list[AuditLog]:
    with _session() as conn:
        if user_id is not None:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE user_id = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_audit_log(row) for row in rows]


def count_blocked_duplicates() -> int:
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE was_duplicate_blocked = 1"
        ).fetchone()
        return row["n"]


def count_blocked_suspicious() -> int:
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE suspicious_pattern IS NOT NULL"
        ).fetchone()
        return row["n"]


def count_unique_users() -> int:
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM audit_logs"
        ).fetchone()
        return row["n"]


def count_successful_queries() -> int:
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE success = 1"
        ).fetchone()
        return row["n"]


def top_models(limit: int = 5) -> list[str]:
    with _session() as conn:
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


def top_users(limit: int = 5) -> list[str]:
    with _session() as conn:
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


def count_pii_detected_queries() -> int:
    with _session() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM audit_logs
            WHERE pii_detected_input = 1 OR pii_detected_output = 1
            """
        ).fetchone()
        return row["n"]


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
    with _session() as conn:
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


# --------------------------------------------------------------------------
# The batched summary read (STORY-010)
# --------------------------------------------------------------------------

#: The ten figures the admin summary is made of, in `_READS`' order.
#:
#: The names are `chat_ui/chat_ui/admin_state.py`'s `_READS` field names on
#: purpose, so its ten `READ_LABEL_*` entries map one-to-one onto them and
#: `len(_READS) == 10` survives the batching (PRD-007 Risk 6).
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
)


@dataclass(frozen=True)
class SummarySnapshot:
    """All ten summary figures, with per-figure failure attribution.

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

    The ten named properties are for callers that want the value or nothing;
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


# One statement, ten named columns -- **not** a client batch, because there is
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
# AC 5 is that all ten agree with the individual functions figure for figure.
#
# **The four parameters bind positionally, in column order**:
#     (row_limit, ranked_limit, ranked_limit, ranked_limit)
# Reordering or inserting a column silently reorders them. Named placeholders
# were not among STORY-001's six verified behaviors, so this does not use them.
#
# `"rows"` is quoted: ROWS is a keyword (window frames) and an unquoted alias
# is a syntax error.
_SUMMARY_SQL = """
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
              'denied_permission', denied_permission))
     FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?)
  ) AS "rows",
  (SELECT COUNT(*) FROM audit_logs) AS total_recorded,
  (SELECT COUNT(*) FROM audit_logs WHERE was_duplicate_blocked = 1)
      AS blocked_duplicates,
  (SELECT COUNT(*) FROM audit_logs WHERE suspicious_pattern IS NOT NULL)
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
       LIMIT ?)) AS top_pii_entities
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
}


def _summary_figure_by_figure(
    row_limit: int, ranked_limit: int, cause: Exception
) -> SummarySnapshot:
    """The ten standalone reads, each guarded, when the one statement failed.

    A dead statement carries no attribution: ten figures fail anonymously and
    the console has nothing to name. That is the blank page Risk 6 describes,
    so the failure path buys the attribution back the only way left -- by
    reading the figures individually and letting each one succeed or fail on
    its own. It costs up to ten round trips, and it is paid **only** when the
    batch is already broken; the success path stays at one.

    `cause` is the statement's own failure. A figure that then reads fine is a
    figure that arrived, so `cause` is not recorded against it. It is used only
    when nothing at all came back -- the database is unreachable, or the table
    is gone -- where every figure carries it, so an outage still reads as an
    outage rather than as ten unrelated coincidences.
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
        # the table is gone. Report the statement's own failure rather than ten
        # copies of a downstream symptom.
        errors = {name: cause for name in SUMMARY_FIGURES}
    return SummarySnapshot(figures=figures, errors=errors)


def summary_snapshot(row_limit: int = 100, ranked_limit: int = 5) -> SummarySnapshot:
    """All ten admin summary figures, in one round trip.

    Two callers ran the same fan-out sequentially: `_READS` in
    `chat_ui/chat_ui/admin_state.py` with ten reads, and `GET /stats` with
    nine. Against a local file that cost nothing; against a remote endpoint it
    is ten round trips per page load (PRD-007 Section 6 Pattern 3).

    This is one statement. Not a client batch -- the driver has none, and its
    multi-statement `execute()` swallows errors (STORY-001 §2.6); see
    `_SUMMARY_SQL` for the whole finding and for the fact that the single
    SELECT measured 1.7 ms against 16.3 ms for the ten it replaces.

    **Attribution rides on column names, not on statements.** Each figure is a
    named column, so the ten `READ_LABEL_*` entries map one-to-one onto them
    and a figure that fails to decode fails alone. If the statement itself
    fails there are no columns to attribute anything to, and the read falls
    back to the ten standalone functions to buy the attribution back.

    `row_limit` and `ranked_limit` are parameters, not constants baked into the
    statement: the callers pass `REGISTER_ROW_LIMIT` and `RANKED_LIMIT`. They
    bind **positionally, in column order** -- see `_SUMMARY_SQL`.
    """
    try:
        with _session() as conn:
            row = conn.execute(
                _SUMMARY_SQL,
                (row_limit, ranked_limit, ranked_limit, ranked_limit),
            ).fetchone()
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
    )


def get_user(user_id: str) -> Optional[User]:
    """Returns the user regardless of active state -- administrative reads
    (CLI list/deactivate) must be able to see a revoked row."""
    with _session() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)


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
    with _session() as conn:
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


def list_users(limit: int = 100) -> list[User]:
    with _session() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_user(row) for row in rows]


def count_active_users() -> int:
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE active = 1"
        ).fetchone()
        return row["n"]


def insert_user(entry: User) -> str:
    """Raises app.db.errors.IntegrityError on a duplicate user_id or token_hash --
    deliberately not caught here; the translation happens at this module's
    boundary but the handling stays with the caller, which needs to tell those two
    cases apart. IntegrityError.constraint carries which constraint failed."""
    created_at = entry.created_at or datetime.now(timezone.utc).strftime(
        _TIMESTAMP_FORMAT
    )
    with _session() as conn:
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
    return entry.user_id


def deactivate_user(user_id: str) -> bool:
    """Revocation is not deletion: audit_logs rows carry a bare user_id with no
    foreign key, so removing the row would orphan the audit trail. Returns False
    when no such user exists, so the CLI can report a typo."""
    with _session() as conn:
        cursor = conn.execute(
            "UPDATE users SET active = 0 WHERE user_id = ?", (user_id,)
        )
        return cursor.rowcount == 1


def set_user_token_hash(user_id: str, token_hash: str) -> bool:
    """Credential rotation (STORY-004 `issue-token`). The old hash stops
    resolving the moment this returns."""
    with _session() as conn:
        cursor = conn.execute(
            "UPDATE users SET token_hash = ? WHERE user_id = ?",
            (token_hash, user_id),
        )
        return cursor.rowcount == 1
