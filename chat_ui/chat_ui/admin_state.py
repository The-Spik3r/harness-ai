"""Session state for the admin console: the token gate, and the record it holds.

Three properties of this module are structural rather than stylistic, and each
one is a PRD-006 requirement that a later edit could quietly remove:

`AdminState` is a **sibling** of `ChatState`, not a substate. PRD-006 Section 4:
"`ChatState` never reads admin state, and no admin page renders a chat
component." It therefore subclasses `rx.State` directly and imports nothing from
`state.py`; subclassing `ChatState` to borrow a field would make the console a
child of the chat and break the separation in one line.

The module is **read-only by construction**. PRD-006 Section 9, verbatim:
"`AdminState` imports only the read functions from `app/db/database.py`.
`insert_audit_log` is not imported, and there is no write path from any admin
page." The ten read functions are imported by name for exactly that reason — a
`from app.db import database` would make `insert_audit_log` reachable as an
attribute and hand back the write path the named imports deny.

The gate is **not an oracle**. Every failure — an empty token, a wrong-length
token, a wrong token of the right length — sets the same message and leaves
`authenticated` False, mirroring `app/middleware/auth.py`, where the
missing-credential arm and the wrong-token arm raise the identical error. Adding
a second, more "helpful" message is the disclosure PRD-006 Section 9 forbids:
"The gate reports that access was refused, not why."
"""

import asyncio
import secrets
from datetime import datetime, timezone

import reflex as rx

from app.config import settings
from app.db.database import (
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_pii_detected_queries,
    count_successful_queries,
    count_unique_users,
    list_audit_logs,
    # Aliased because the state declares fields of these three names. The module
    # global and the class attribute live in different namespaces and Python
    # resolves each correctly, but a reader of `load()` cannot tell which one a
    # bare `top_models` is — and a future edit that moved the read into the
    # class body would silently call a list.
    top_models as read_top_models,
    top_pii_entities as read_top_pii_entities,
    top_users as read_top_users,
)

from .admin_formatting import format_refreshed_at, to_audit_row
from .admin_models import AuditRow

# One message for an empty token, a wrong-length token and a wrong token of the
# right length. PRD-006 Section 9: "an empty, malformed or wrong token produces
# the same message. The gate reports that access was refused, not why."
# Splitting this into three would be the oracle.
# STORY-008 moves this string to admin_copy.py; this module then imports it.
GATE_REFUSED_MESSAGE = "Access refused. That token was not accepted."

# The register's window, and the only ceiling there is: PRD-006 Section 4 puts
# pagination past 100 rows out of scope, and `list_audit_logs` is the only
# listing query. Named so the register can state the cap it renders against the
# true total (Risk 4) rather than re-typing 100.
REGISTER_ROW_LIMIT = 100

# The fault message. Names the read that failed and states that nothing on
# screen changed — a stale register is not a wrong one, and that is the fact the
# admin needs before deciding whether to trust what is displayed. "Refresh" is
# the same word STORY-017's control must carry.
# STORY-008 moves this string to admin_copy.py; this module then imports it.
LOAD_FAILED_MESSAGE = (
    "Could not read {read}. Nothing on screen has changed. Refresh to try "
    "again. ({detail})"
)

# The ten reads, as data: (state field, what to call it in a fault message, the
# read function, its keyword arguments). A table rather than ten hand-written
# awaits because "all ten" is then one countable structure — ten separate
# `await` lines can become nine in a refactor with nothing to notice it, and
# STORY-006 asserts `len(_READS) == 10`. The label is the only user-facing
# string here and moves to admin_copy.py with STORY-008.
#
# Module level, not the class body: three of the field names below are also
# declared as vars on `AdminState`, and inside the class body those declarations
# would shadow the imported functions.
#
# Order is the read order and is deliberate: the rows come first so the slowest
# query fails fast, and `total_recorded` follows them because it is the
# denominator the register states its 100-row cap against.
_READS: tuple[tuple[str, str, object, dict], ...] = (
    ("rows", "the audit rows", list_audit_logs, {"limit": REGISTER_ROW_LIMIT}),
    ("total_recorded", "the recorded total", count_audit_logs, {}),
    ("blocked_duplicates", "the blocked duplicates", count_blocked_duplicates, {}),
    ("blocked_suspicious", "the blocked patterns", count_blocked_suspicious, {}),
    ("unique_users", "the user count", count_unique_users, {}),
    ("successful_queries", "the completed count", count_successful_queries, {}),
    (
        "pii_detected_queries",
        "the PII detection count",
        count_pii_detected_queries,
        {},
    ),
    ("top_models", "the model ranking", read_top_models, {}),
    ("top_users", "the user ranking", read_top_users, {}),
    ("top_pii_entities", "the PII entity ranking", read_top_pii_entities, {}),
)


class AdminState(rx.State):
    """The console's session: who is through the gate, and what has been read.

    Every field below is declared with an empty default, and that is load
    bearing: `sign_out()` clears the session by restoring these defaults
    (`rx.State.reset()`), so a field given a non-empty default would survive a
    sign-out and become exactly the standing disclosure PRD-006 Section 5's
    eighth story is about.
    """

    # --- Gate -------------------------------------------------------------
    token_input: str = ""
    authenticated: bool = False
    gate_error: str = ""

    # --- The record -------------------------------------------------------
    # Declared here, populated by STORY-004's load(). They are declared in this
    # story because sign_out() must be able to clear them, and a field that does
    # not exist cannot be cleared. These names are the contract STORY-004 writes
    # to and STORY-015 renders from.
    rows: list[AuditRow] = []
    total_recorded: int = 0
    blocked_duplicates: int = 0
    blocked_suspicious: int = 0
    unique_users: int = 0
    successful_queries: int = 0
    pii_detected_queries: int = 0
    top_models: list[str] = []
    top_users: list[str] = []
    top_pii_entities: list[str] = []
    last_refreshed: str = ""
    loading: bool = False
    error: str = ""

    @rx.event
    def set_token_input(self, text: str):
        self.token_input = text

    def _refuse(self):
        """The only place `gate_error` is set to a message.

        Three conditions reach it — no token, no configured token, a token that
        does not match — and they must be indistinguishable from the outside, so
        they share one assignment site rather than three call sites that could
        drift into three messages. The typed token goes with it: a refused gate
        re-renders with an empty field, never a repopulated one.
        """
        self.authenticated = False
        self.gate_error = GATE_REFUSED_MESSAGE
        self.token_input = ""

    @rx.event
    def authenticate(self):
        """Checks the submitted token with `app/middleware/auth.py`'s comparison,
        and refuses every failure identically.

        The bytes encoding is the one difference from `require_admin_token`, and
        it is an encoding change rather than a comparison change:
        `secrets.compare_digest` raises `TypeError` when either `str` operand
        holds a non-ASCII character, and this token arrives from a browser
        field. Encoded, operands of unequal length are handled by
        `compare_digest` itself and cannot raise.
        """
        submitted = self.token_input
        configured = settings.ADMIN_TOKEN or ""
        # Emptiness on either side refuses before the comparison: ADMIN_TOKEN is
        # a required setting but "" satisfies it, and compare_digest(b"", b"") is
        # True — a blank configured token would otherwise open the console. The
        # message is the same as every other refusal, so this adds no oracle.
        if not submitted or not configured:
            self._refuse()
            return
        if not secrets.compare_digest(
            submitted.encode("utf-8"), configured.encode("utf-8")
        ):
            self._refuse()
            return

        self.authenticated = True
        self.gate_error = ""
        # The secret does not stay resident: `authenticated` is the credential
        # from here on (PRD-006 Section 9).
        self.token_input = ""
        # A background task cannot be called from another handler; it is
        # triggered by returning or yielding it.
        return AdminState.load

    @rx.event
    def sign_out(self):
        """Ends the session, and the record goes with it: the token, the loaded
        rows, the summary figures and the last-refreshed stamp are cleared from
        state rather than hidden from the view, because an open browser on a
        shared machine is otherwise a standing disclosure (PRD-006 Section 9).

        `reset()` rather than a list of assignments, deliberately. It restores
        every declared var to its default, so the guarantee also covers the
        fields STORY-004 and STORY-005 add later — a field listed nowhere is the
        one that survives a sign-out unnoticed. Nothing on this surface is meant
        to outlive the session; anything that ever is belongs outside this state.
        """
        self.reset()

    @rx.event(background=True)
    async def load(self):
        """Reads the register and the summary, off the event loop.

        The outer guard is the load-bearing half of PRD-006 Risk 1: the read
        itself is gated, not just the view, so an unauthenticated page has no
        data in state to leak regardless of what any component chooses to
        render. It returns before `loading` is ever set, so an ungated call
        leaves no trace at all.

        Four structural properties below, each a requirement rather than a style
        choice:

        The gate is asserted **twice**. The first check is a read outside the
        lock, which Reflex documents as possibly stale, and `sign_out()` can land
        between `authenticate()` returning this event and the first lock
        acquisition. The second check, inside the lock, is the one that holds.

        Each read is offloaded **per call**. Every function in
        `app/db/database.py` opens its own `sqlite3` connection (see
        `get_connection`), and a connection cannot cross threads — so the thread
        boundary sits around one call, and no connection is hoisted out of it.
        Sequential rather than gathered: ten indexed counts over one small table
        do not need the concurrency, ten simultaneous connections would contend
        with the chat surface's writes, and a gathered failure cannot say which
        of ten reads produced it.

        Every result is collected into a **local** and committed in one block at
        the end. That is what makes the fault arm's "rows and figures untouched"
        true by construction rather than by discipline: there is no instant at
        which some fields are new and others old, so a read that fails on the
        eighth of ten cannot leave a register that half agrees with its summary.

        The `finally` clears `loading` on **both** paths. A flag stranded True
        locks STORY-017's refresh control permanently — PRD-004 Risk 3, the same
        failure the chat's composer already guards against.
        """
        if not self.authenticated:
            return

        async with self:
            # Re-asserted under the lock: the check above may be stale.
            if not self.authenticated:
                return
            # A second in-flight read would race the first one's commit and
            # could publish the older of two results.
            if self.loading:
                return
            self.loading = True
            self.error = ""

        try:
            # One clock read for the whole batch, so the rows' relative times and
            # the refresh stamp cannot disagree by a straggling second.
            now = datetime.now(timezone.utc)
            results: dict[str, object] = {}
            for field, label, read, kwargs in _READS:
                try:
                    results[field] = await asyncio.to_thread(read, **kwargs)
                except Exception as exc:
                    # Catch-all, matching PRD-004's "no silent drops": a read
                    # that fails is a fault naming what failed, never a silently
                    # empty table (PRD-006 Section 4). Nothing has been written
                    # to state at this point, so the previous record stands.
                    async with self:
                        self.error = LOAD_FAILED_MESSAGE.format(
                            read=label, detail=exc
                        )
                    return

            # Order preserved from `list_audit_logs`' ORDER BY timestamp DESC —
            # newest first already. Sorting is STORY-005's computed var, and a
            # sort here would fight it. `to_audit_row` is the only constructor
            # used: it is the projection that drops both previews (Risk 2).
            rows = [to_audit_row(log, now) for log in results.pop("rows")]

            async with self:
                # One commit. Until this block, nothing on screen has moved.
                self.rows = rows
                for field, value in results.items():
                    setattr(self, field, value)
                self.last_refreshed = format_refreshed_at(now)
                # Clears a previous fault, so a recovered read stops showing the
                # panel STORY-017 renders.
                self.error = ""
        finally:
            async with self:
                self.loading = False
