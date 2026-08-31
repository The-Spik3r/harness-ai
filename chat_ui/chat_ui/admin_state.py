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

from .admin_copy import (
    GATE_REFUSED_MESSAGE,
    REGISTER_FILTERED_TEMPLATE,
    REGISTER_SCOPE_TEMPLATE,
    READ_LABEL_BLOCKED_DUPLICATES,
    READ_LABEL_BLOCKED_SUSPICIOUS,
    READ_LABEL_PII_QUERIES,
    READ_LABEL_ROWS,
    READ_LABEL_SUCCESSFUL,
    READ_LABEL_TOP_MODELS,
    READ_LABEL_TOP_PII,
    READ_LABEL_TOP_USERS,
    READ_LABEL_TOTAL,
    READ_LABEL_UNIQUE_USERS,
    # Aliased to the name this module has used since STORY-004: `load()` formats
    # it and a future test may import it from here, so the move to admin_copy.py
    # stays a relocation of the string rather than of the call site.
    FAULT_MESSAGE_TEMPLATE as LOAD_FAILED_MESSAGE,
)
from .admin_formatting import (
    VERDICTS,
    format_count,
    format_refreshed_at,
    to_audit_row,
)
from .admin_models import AuditRow

# The register's window, and the only ceiling there is: PRD-006 Section 4 puts
# pagination past 100 rows out of scope, and `list_audit_logs` is the only
# listing query. Named so the register can state the cap it renders against the
# true total (Risk 4) rather than re-typing 100.
REGISTER_ROW_LIMIT = 100

# The three orderings the register offers (PRD-006 Section 6.1's controls, built
# in STORY-013). Values, not copy — they are the `sort_key` the controls write
# and the keys `_SORT_RANKS` dispatches on, so they are constants here rather
# than string literals in a component.
SORT_TIMESTAMP = "timestamp"
SORT_USER = "user"
SORT_VERDICT = "verdict"
SORT_KEYS = (SORT_TIMESTAMP, SORT_USER, SORT_VERDICT)

# Each key's rank function takes (position in the loaded list, row) and returns
# a sort key. The position is the first argument for one reason:
# `list_audit_logs` already returns ORDER BY timestamp DESC
# (app/db/database.py:128), so a row's index *is* its recency rank, and it is
# available on every row — unlike `timestamp_absolute`, which `_format_timestamps`
# sets to the absent mark when the column is NULL or unparseable
# (admin_formatting.py). Sorting on that string would sink every unparseable row
# to one end of the register on a filter the admin did not ask for. Sorting on
# the index reproduces the database's own ordering exactly, including its ties.
#
# The verdict rank is the NEGATED index into VERDICTS, so the natural order runs
# fault -> denied -> held -> cleared: the exceptions the register exists to
# surface come first, which is the same statement the stamp margin makes
# (PRD-006 Section 6.1, "Signature"). An unrecognised verdict — including
# AuditRow's "" default — ranks 1 and sorts last, rather than raising ValueError
# out of `.index()` into a page render.
_SORT_RANKS = {
    SORT_TIMESTAMP: lambda index, row: index,
    SORT_USER: lambda index, row: row.user_id.casefold(),
    SORT_VERDICT: lambda index, row: (
        -VERDICTS.index(row.verdict) if row.verdict in VERDICTS else 1
    ),
}

# The ten reads, as data: (state field, what to call it in a fault message, the
# read function, its keyword arguments). A table rather than ten hand-written
# awaits because "all ten" is then one countable structure — ten separate
# `await` lines can become nine in a refactor with nothing to notice it, and
# STORY-006 asserts `len(_READS) == 10`. The label is the only user-facing string
# here, and since STORY-008 every one of them comes from `admin_copy` — the
# fault message they are formatted into (LOAD_FAILED_MESSAGE, imported above)
# lives there too, so the whole sentence an admin reads on a failed read is
# assembled from that one module.
#
# Module level, not the class body: three of the field names below are also
# declared as vars on `AdminState`, and inside the class body those declarations
# would shadow the imported functions.
#
# Order is the read order and is deliberate: the rows come first so the slowest
# query fails fast, and `total_recorded` follows them because it is the
# denominator the register states its 100-row cap against.
_READS: tuple[tuple[str, str, object, dict], ...] = (
    ("rows", READ_LABEL_ROWS, list_audit_logs, {"limit": REGISTER_ROW_LIMIT}),
    ("total_recorded", READ_LABEL_TOTAL, count_audit_logs, {}),
    (
        "blocked_duplicates",
        READ_LABEL_BLOCKED_DUPLICATES,
        count_blocked_duplicates,
        {},
    ),
    (
        "blocked_suspicious",
        READ_LABEL_BLOCKED_SUSPICIOUS,
        count_blocked_suspicious,
        {},
    ),
    ("unique_users", READ_LABEL_UNIQUE_USERS, count_unique_users, {}),
    ("successful_queries", READ_LABEL_SUCCESSFUL, count_successful_queries, {}),
    (
        "pii_detected_queries",
        READ_LABEL_PII_QUERIES,
        count_pii_detected_queries,
        {},
    ),
    ("top_models", READ_LABEL_TOP_MODELS, read_top_models, {}),
    ("top_users", READ_LABEL_TOP_USERS, read_top_users, {}),
    ("top_pii_entities", READ_LABEL_TOP_PII, read_top_pii_entities, {}),
)


def _matches(row: AuditRow, verdicts: list[str], needle: str) -> bool:
    """Whether one row survives both filters.

    Two properties are requirements rather than choices:

    An **empty** verdict selection passes every row. "No verdict filter" and "no
    rows" are opposite statements, and reading the empty list as the second is
    the bug that makes an untouched register render blank (PRD-006 Section 4's
    three states, and STORY-014's whole distinction).

    The free text matches `audit_id` **as a string**. It is an int on AuditRow,
    and the register's join back to the chat is a user quoting "#127" out of the
    success footer (PRD-004 STORY-010) — so the coercion happens here, in
    Python, not in a component against a Var.
    """
    if verdicts and row.verdict not in verdicts:
        return False
    if not needle:
        return True
    return any(
        needle in field
        for field in (
            row.user_id.casefold(),
            row.model_used.casefold(),
            str(row.audit_id),
        )
    )


def filter_rows(
    rows: list[AuditRow], verdicts: list[str], search: str
) -> list[AuditRow]:
    """The rows passing the verdict selection AND the free text.

    The two filters compose as AND, never OR: an admin who has selected *denied*
    and typed a user is asking for that user's denied rows, and an OR would
    widen the register at the exact moment they are narrowing it (PRD-006
    Section 5, story 4 — "denied plus a.torres narrows 100 rows to 2").

    The needle is case-folded and stripped **once** here rather than per row: the
    comparison is case-insensitive, and a hundred rows times three fields is
    three hundred `.casefold()` calls that would otherwise be four hundred.
    """
    needle = search.strip().casefold()
    if not verdicts and not needle:
        # The common case, and it returns a copy rather than `rows` itself: the
        # caller sorts this list, and sorting the state's own list in place
        # would mutate `rows` from inside a computed var.
        return list(rows)
    return [row for row in rows if _matches(row, verdicts, needle)]


def sort_rows(
    rows: list[AuditRow], sort_key: str, descending: bool
) -> list[AuditRow]:
    """The rows in the requested order; the loaded order when none is set.

    `sorted` rather than `list.sort`, because the argument may be the state's own
    row list and a computed var must not mutate what it reads.

    An empty or unrecognised `sort_key` falls back to SORT_TIMESTAMP, whose rank
    is the position in `rows` — so the default is the order `list_audit_logs`
    returned, newest first, and `sort_key == ""` and `sort_key == "timestamp"`
    are the same register. That equivalence is what lets `sort_key` default to
    the empty string, which is what `sign_out()`'s reset() requires of every
    declared var.

    The sort is stable and there is no explicit tiebreak, deliberately: rows
    arrive in timestamp order, so two rows with the same user or the same verdict
    keep their relative recency inside the group for free.
    """
    rank = _SORT_RANKS.get(sort_key, _SORT_RANKS[SORT_TIMESTAMP])
    # enumerate first, sort the (index, row) pairs on the rank, drop the index.
    # The index has to reach the key function, and `sorted(rows, ...)` cannot
    # supply it.
    return [
        row
        for _, row in sorted(
            enumerate(rows),
            key=lambda pair: rank(pair[0], pair[1]),
            reverse=descending,
        )
    ]


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

    # --- Filter and sort --------------------------------------------------
    # Plain state vars, all four. PRD-006 Section 6: "the visible rows are an
    # rx.var over the loaded rows plus the filter state, so filtering never
    # re-reads the database" — these are that filter state, and `visible_rows`
    # below is that var. STORY-013 builds the controls that write them.
    #
    # Every default here is falsy, and that is a requirement rather than a
    # coincidence: sign_out() is reset(), and tests/test_admin_state.py's
    # test_sign_out_clears_every_declared_var asserts every declared var restores
    # to a falsy default, so a filter left standing after a sign-out is caught.
    # It is also why the register's "timestamp, newest first" default is carried
    # by sort_key == "" (which sort_rows reads as the loaded order) rather than
    # by a truthy default.
    selected_verdicts: list[str] = []
    search: str = ""
    sort_key: str = ""
    sort_descending: bool = False

    # --- Disclosure -------------------------------------------------------
    # Which rows have their detail open, by `audit_id` — never by position in
    # `visible_rows`. The register renders through `rx.foreach`, which compiles
    # to a `.map()` whose children are keyed by index, so a sort or a filter
    # (STORY-013) moves every row to a new position while its id stays its own.
    # Holding the open set as ids is what makes STORY-012's "each row's open
    # state is independent" survive a reorder; holding it in the DOM (an
    # `rx.el.details`) or by index would silently reattach an open disclosure to
    # whichever row landed in that slot, which is the one kind of wrongness an
    # audit surface cannot carry.
    #
    # `list[int]`, not a bare `list`: `Var.contains()` needs the strict
    # annotation to compile. Empty default, like every var above, so sign_out()'s
    # reset() closes every disclosure — an open row surviving a sign-out is the
    # standing disclosure PRD-006 Section 9 is about.
    open_rows: list[int] = []

    @rx.var
    def visible_rows(self) -> list[AuditRow]:
        """The rows the register renders: `rows` narrowed, then ordered.

        Two properties are load bearing.

        **No database read.** This is a synchronous getter over data already in
        state; it calls nothing from `app.db.database` and awaits nothing, so
        PRD-006 Section 6's "filtering never re-reads the database" is true by
        construction rather than by discipline. An async getter would be the
        shape a database-backed filter takes — Reflex supports one
        (AsyncComputedVar) and it is deliberately not used here.

        **All five dependencies are read off `self` in this body.** Reflex's
        auto-dependency tracker disassembles this function and records the
        attributes it loads from `self` (ComputedVar._deps); a module-level
        helper handed plain lists is invisible to it. Moving any of these five
        loads down into `filter_rows`/`sort_rows` would leave a var that silently
        stops updating — and the tracker's failure mode is a console.warn and an
        empty dependency set, not an exception. Keep the loads here; keep the
        logic there.
        """
        return sort_rows(
            filter_rows(self.rows, self.selected_verdicts, self.search),
            self.sort_key,
            self.sort_descending,
        )

    @rx.var
    def filters_active(self) -> bool:
        """Whether anything is narrowing the register right now.

        Sort is excluded: reordering the register does not remove a row, so an
        "active filter" that a clear action would undo is the verdict selection
        and the text, and only those. STORY-014's no-matches state is exactly
        `filters_active and not visible_rows`, and STORY-013's clear control
        shows against this.
        """
        return bool(self.selected_verdicts) or bool(self.search.strip())

    @rx.var
    def register_scope(self) -> str:
        """The register's window, stated against the whole record.

        PRD-006 Risk 4: all-time figures beside a 100-row window "invite a wrong
        reading", so the register says which of the two it is showing. The
        denominator is `count_audit_logs()`, read into `total_recorded`.

        **`len(self.rows)`, not REGISTER_ROW_LIMIT.** Against a table of 12 rows
        a hard-coded 100 would render "100 most recent of 12", which is false on
        the one line whose whole job is to prevent a false reading. The loaded
        count *is* min(REGISTER_ROW_LIMIT, total) by construction, so it states
        the cap whenever the cap binds and states the truth when it does not.

        **Not `visible_rows`.** How much of the window survived a filter is a
        different statement with its own constant (REGISTER_FILTERED_TEMPLATE,
        STORY-013). Collapsing the two would leave the scope line moving when an
        admin types, and the window is not what changed.

        A computed var rather than a declared one, so `sign_out()`'s reset()
        keeps its guarantee: this returns a truthy string on a cleared state, and
        `tests/test_admin_state.py::test_sign_out_clears_every_declared_var`
        iterates `base_vars`, which computed vars are not part of.

        Both dependencies are read off `self` in this body — the same
        requirement `visible_rows` records above. `format_count` receives a
        plain int, never `self`, so it stays invisible to the tracker and
        harmless.
        """
        return REGISTER_SCOPE_TEMPLATE.format(
            shown=format_count(len(self.rows)),
            total=format_count(self.total_recorded),
        )

    @rx.var
    def register_filtered(self) -> str:
        """"12 of 100 shown" — how much of the loaded window survived the filter.

        **A second statement, not a replacement for the first.** `admin_copy`
        draws the line at the constant itself: "the scope states the window,
        this states how much of the window survived the filter". So the
        denominator here is `len(self.rows)` — the loaded window — where
        `register_scope`'s is `total_recorded`, the whole table. Collapsing the
        two would leave the scope line moving when an admin types, and the
        window is not what changed (PRD-006 Risk 4, and AC 4's "distinct from
        the '100 most recent of {total}' scope line").

        **A computed var rather than a string built in the component**, for the
        reason `register_scope` above records and `admin_formatting`'s docstring
        states generally: `REGISTER_FILTERED_TEMPLATE` is a Python format string
        and `format_count` is Python-side thousands separation, and component
        functions receive Reflex Vars — JS references — which neither can run
        against.

        This computes no filter. `visible_rows` is STORY-005's var and is read
        here, not recomputed; the register's narrowing logic stays where that
        story put it.

        Both dependencies are read off `self` in this body, per the
        auto-dependency rule `visible_rows` records — and reading
        `self.visible_rows` here makes this var depend transitively on all five
        of its dependencies, so a toggled verdict updates this line too.
        """
        return REGISTER_FILTERED_TEMPLATE.format(
            shown=format_count(len(self.visible_rows)),
            loaded=format_count(len(self.rows)),
        )

    @rx.event
    def set_token_input(self, text: str):
        self.token_input = text

    @rx.event
    def set_search(self, text: str):
        self.search = text

    @rx.event
    def toggle_verdict(self, verdict: str):
        """Adds or removes one verdict from the selection.

        Reassigns the list rather than mutating it in place: Reflex marks a var
        dirty on assignment, and an in-place `.append()` on a list var can leave
        `visible_rows` serving its cached value.
        """
        if verdict in self.selected_verdicts:
            self.selected_verdicts = [
                v for v in self.selected_verdicts if v != verdict
            ]
        else:
            self.selected_verdicts = [*self.selected_verdicts, verdict]

    @rx.event
    def toggle_detail(self, audit_id: int):
        """Opens or closes one row's disclosure, leaving every other row alone.

        Keyed on the row's `audit_id`, for the reason the `open_rows`
        declaration records: an id is the row, an index is only a position.

        Reassigns the list rather than mutating it, the same requirement
        `toggle_verdict` above carries — Reflex marks a var dirty on assignment,
        and an in-place `.append()` can leave the register rendering its cached
        open set.

        Nothing clears this on a read or on a cleared filter, deliberately.
        `audit_id` is monotonic, so a refresh that returns the same row should
        return it in the same state, and an admin clearing a filter is not asking
        for their open rows to close. `sign_out()`'s reset() is what closes them.
        """
        if audit_id in self.open_rows:
            self.open_rows = [i for i in self.open_rows if i != audit_id]
        else:
            self.open_rows = [*self.open_rows, audit_id]

    @rx.event
    def sort_by(self, key: str):
        """Chooses an ordering, or reverses the one already chosen.

        Named `sort_by` rather than `set_sort_key` on purpose: the latter is the
        name Reflex would give the plain setter for `sort_key`, and this handler
        does more than set it — a reader who called it expecting a setter would
        not expect the direction to flip.
        """
        if key == self.sort_key:
            self.sort_descending = not self.sort_descending
            return
        self.sort_key = key
        # A newly chosen column starts in its natural order — newest first for
        # timestamp, A-Z for user, exceptions first for verdict.
        self.sort_descending = False

    @rx.event
    def clear_filters(self):
        """Restores the full window. Clears the filters only — not the sort, and
        never the rows: STORY-014's no-matches state offers this action, and an
        admin clearing a filter is not asking for a reload.
        """
        self.selected_verdicts = []
        self.search = ""

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
