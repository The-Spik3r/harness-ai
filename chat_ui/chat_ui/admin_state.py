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
page." Today it imports no database function at all — `load()` is a guard and
nothing else (STORY-004 fills in the reads).

The gate is **not an oracle**. Every failure — an empty token, a wrong-length
token, a wrong token of the right length — sets the same message and leaves
`authenticated` False, mirroring `app/middleware/auth.py`, where the
missing-credential arm and the wrong-token arm raise the identical error. Adding
a second, more "helpful" message is the disclosure PRD-006 Section 9 forbids:
"The gate reports that access was refused, not why."
"""

import secrets

import reflex as rx

from app.config import settings

from .admin_models import AuditRow

# One message for an empty token, a wrong-length token and a wrong token of the
# right length. PRD-006 Section 9: "an empty, malformed or wrong token produces
# the same message. The gate reports that access was refused, not why."
# Splitting this into three would be the oracle.
# STORY-008 moves this string to admin_copy.py; this module then imports it.
GATE_REFUSED_MESSAGE = "Access refused. That token was not accepted."


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
        """Loads the register and the summary. The read body is STORY-004.

        The guard is the whole of this method today, and it is the load-bearing
        half of PRD-006 Risk 1: the read itself is gated, not just the view, so
        an unauthenticated page has no data in state to leak regardless of what
        any component chooses to render. STORY-004 adds the reads BELOW this
        guard and must re-assert `self.authenticated` inside its first
        `async with self` block — a background task's read outside the lock can
        be stale, and `sign_out()` may land mid-read.
        """
        if not self.authenticated:
            return
