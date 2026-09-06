import asyncio
from datetime import datetime, timezone
from typing import Optional

import reflex as rx

from app.db.models import ChatSession, StoredMessage
from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity, resolve
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query
from .models import ChatMessage, ChatSessionSummary
from .copy import (
    LOGIN_INVALID_TOKEN_ERROR,
    LOGIN_TOKEN_REQUIRED_ERROR,
    SESSION_INVALIDATED_ERROR,
    SESSION_ORDER_STALE_NOTICE,
    SESSION_RAIL_SCOPE_TEMPLATE,
    TRANSCRIPT_NOT_LOADED_NOTICE,
    TRANSCRIPT_NOT_SAVED_NOTICE,
)
from .formatting import derive_title, format_activity, format_duplicate_info
from .config import DEFAULT_MODEL

def _to_stored_message(bubble: ChatMessage, session_id: str) -> StoredMessage:
    """One bubble as one `chat_messages` row.

    `ChatMessage` defaults its optional fields to "" and 0 because a Reflex Var
    cannot be None on the wire; every matching column is nullable and means
    *absent*. So every optional field is converted with `or None` -- a
    transcript full of empty strings would restore into bubbles that render an
    empty "Matched pattern" label instead of no label at all.

    `pii_entities` is comma-joined, matching how `app/services/audit_logger.py`
    already persists the same data and what `StoredMessage`'s own docstring asks
    for: "one encoding serves one concept."

    `duplicate_relative_info` and `duplicate_release_info` are dropped, and
    their absence is the schema's decision rather than an oversight --
    `app/db/models.py`: "a stored '2m ago' is wrong the moment it is read back."
    STORY-015 recomputes them from `first_query_at` on load.
    """
    return StoredMessage(
        session_id=session_id,
        kind=bubble.kind,
        content=bubble.content,
        prompt=bubble.prompt or None,
        model_used=bubble.model_used or None,
        tokens_used=bubble.tokens_used or None,
        audit_id=bubble.audit_id or None,
        pii_redacted=bubble.pii_redacted,
        pii_entities=",".join(bubble.pii_entities) or None,
        pattern=bubble.pattern or None,
        required_permission=bubble.required_permission or None,
        first_query_at=bubble.first_query_at or None,
        detail=bubble.detail or None,
    )


def _to_chat_message(row: StoredMessage) -> ChatMessage:
    """One `chat_messages` row as one bubble -- the inverse of
    `_to_stored_message` above, and deliberately adjacent to it.

    Every conversion is that function's read backwards. It writes the optional
    fields with `or None` because the columns mean *absent*; this reads them
    with `or ""` / `or 0` because a Reflex Var cannot be None on the wire.
    `pii_entities` splits on "," and guards the empty case: `"".split(",")` is
    `[""]`, and `app/db/database.py` stores an empty list as NULL precisely so
    this line cannot invent "a phantom entity on a message that had none".

    The two duplicate fields have no column (`app/db/models.py`: "a stored
    '2m ago' is wrong the moment it is read back") and are recomputed here
    through the same `format_duplicate_info` the live duplicate branch calls in
    `_do_send`, so "already sent 2m ago" reads correctly hours later. It is
    called **only** for `kind == "duplicate"`: the function returns
    DUPLICATE_FALLBACK_TEXT rather than "" for an empty timestamp, so running
    every kind through it would put duplicate copy on a user bubble --
    invisible today, because only `render_duplicate` reads those fields, and a
    divergence from the live path all the same.

    `row.created_at` and `row.id` are not mapped: `ChatMessage` has no field for
    either, and `id` is the ordering `list_chat_messages` has already applied.
    """
    relative_info = ""
    release_info = ""
    if row.kind == "duplicate":
        relative_info, release_info = format_duplicate_info(row.first_query_at or "")

    return ChatMessage(
        kind=row.kind,
        content=row.content,
        prompt=row.prompt or "",
        model_used=row.model_used or "",
        tokens_used=row.tokens_used or 0,
        audit_id=row.audit_id or 0,
        pii_redacted=row.pii_redacted,
        pii_entities=row.pii_entities.split(",") if row.pii_entities else [],
        pattern=row.pattern or "",
        required_permission=row.required_permission or "",
        first_query_at=row.first_query_at or "",
        duplicate_relative_info=relative_info,
        duplicate_release_info=release_info,
        detail=row.detail or "",
    )


class ChatState(rx.State):
    """Session state for the chat surface: the transcript, the composer, and
    who is sending.

    send() is the only consumer of run_query(...) and handles every branch it
    can produce -- four response types, three named exceptions, and a
    catch-all -- appending exactly one typed ChatMessage for each. That
    exhaustiveness is what makes PRD-004's "no silent drops" structural
    rather than aspirational. The call itself runs on a worker thread, so a
    30-second OpenRouter round trip never blocks the Reflex event loop.

    PRD-005 Risk 5: a role read from a Reflex state var is cosmetic, not a
    security boundary -- state vars are serialized to the client and mutable
    by client-originated events. So this class holds no role at all, and its
    only credential is `_token`, a backend-only var (leading underscore):
    Reflex never syncs it to the frontend and no client event can set it.
    login() is the only place that writes it or `user_id`; every send()
    re-derives the Identity -- and so the role -- from `_token` via
    resolve(), fresh, on every call.

    `active_session_id` below is client-visible, and that is deliberate rather
    than an oversight of the paragraph above: the rail has to render which row
    is the active one, which a backend-only var cannot do. It is safe only
    because nothing trusts it. PRD-008 Risk 3: it is untrusted input, so
    `app/services/chat_sessions.py` re-checks ownership on every read against
    the Identity resolved fresh from `_token`, never against the var, and
    POST /query refuses a foreign session with a 403 (STORY-010). Making it a
    backend var would break the rail without adding a boundary; trusting it
    would remove one.
    """

    messages: list[ChatMessage] = []
    input_text: str = ""
    user_id: str = ""
    token_input: str = ""
    login_error: str = ""
    pending: bool = False
    selected_model: str = DEFAULT_MODEL
    sessions: list[ChatSessionSummary] = []
    active_session_id: str = ""
    sessions_error: str = ""
    # The whole count, and deliberately not `len(self.sessions)`: `list_for`
    # caps at `CHAT_SESSION_LIMIT`, so its length can never exceed the limit it
    # was called with and "50 of 50" would be indistinguishable from an account
    # with exactly fifty. `chat_sessions.count` ignores the cap for precisely
    # this reason, and `rail_scope` below is the only reader.
    sessions_total: int = 0

    # --- The rail's presentation state (STORY-018) -----------------------
    # Three vars the rail needs and the database does not: which row is being
    # renamed, what is being typed into it, and which row has asked to be
    # deleted. Reflex has no component-local state, so they live here -- but
    # they are the surface's, not the session's, and nothing outside
    # `session_rail.py` reads them.
    #
    # **Keyed on `session_id`, never on list position.** `rx.foreach` compiles
    # to a `.map()` keyed by index and `_promote_session` reorders this list on
    # every send, so an index-held "row 2 is renaming" would follow whichever
    # chat landed in slot 2. `register.py`'s `open_rows` records the same
    # reasoning; here the list actually reorders, so it bites harder.
    #
    # One `str` rather than a set, because only one row may be in either mode
    # at a time: `begin_rename` and `ask_delete` each clear the other.
    renaming_session_id: str = ""
    rename_draft: str = ""
    confirming_delete_id: str = ""
    # The *turn's* notice slot, and deliberately not `sessions_error` above,
    # which is the *rail's*. One says a bubble is not in the database; the other
    # says the list is stale. Conflating them would make one of the two messages
    # a lie on every failure of the other -- see `_append_and_persist`. Nothing
    # renders it yet, exactly as nothing rendered `sessions_error` when
    # STORY-013 introduced it; STORY-018/019 own the surface.
    transcript_error: str = ""

    _token: str = ""

    @rx.var
    def has_messages(self) -> bool:
        return len(self.messages) > 0

    @rx.var
    def rail_scope(self) -> str:
        """"50 most recent of 212" -- the window, stated against the whole list.

        Empty when nothing is being withheld, and that emptiness is the point:
        PRD-006 Risk 4 is why a cap is never silent, but a scope line on a
        complete list states a window that is not a window. `copy.py` records
        the same rule for the constant -- "a rail that quietly stops at
        CHAT_SESSION_LIMIT would read as a complete list of the user's chats"
        -- and the converse holds, so the line appears only when the two
        numbers actually differ.

        `>=` rather than `!=`: `sessions_total` is read once per load and the
        list is rebuilt on every rename and delete, so the two can disagree by
        a row without the list being capped. Only "more exist than are shown"
        is worth a line.

        The thousands separator is applied here rather than in the component,
        for `admin_state.register_scope`'s reason: components read Vars, and
        formatting a number is Python's job.
        """
        shown = len(self.sessions)
        if self.sessions_total <= shown:
            return ""
        return SESSION_RAIL_SCOPE_TEMPLATE.format(
            shown=f"{shown:,}", total=f"{self.sessions_total:,}"
        )


    @rx.event
    def set_input_text(self, text: str):
        self.input_text = text

    @rx.event
    def set_token_input(self, text: str):
        self.token_input = text

    @rx.event
    def set_selected_model(self, model: str):
        self.selected_model = model

    @rx.event
    async def login(self):
        """Signs in, then loads this identity's session list.

        Async but *not* `background=True`, and the difference is the whole
        reason the rail is populated when the gate clears. A background task
        cannot be called from another handler at all -- Reflex installs
        `_no_chain_background_task` and it must be returned as a follow-up
        event, which lands after this handler has already finished. A plain
        async handler holds the exclusive state lock for its entire duration,
        including across the `await` below, so `self` here is the real state
        and not a StateProxy: mutations are direct and an `async with self`
        would deadlock on a lock this handler already holds. That is the
        opposite of the rule in `_do_send`, which *is* a background task.
        """
        token = self.token_input.strip()
        if not token:
            self.login_error = LOGIN_TOKEN_REQUIRED_ERROR
            return

        identity = resolve(token)
        if identity is None:
            self.login_error = LOGIN_INVALID_TOKEN_ERROR
            return

        self.login_error = ""
        self.token_input = ""
        self._token = token
        self.user_id = identity.user_id

        # The list is ORDER BY updated_at DESC, so the first row is the most
        # recently active chat. Opening it is what makes a reload cost nothing:
        # this handler *is* the page load for a signed-in user, because `_token`
        # is a backend var and no signed-in state survives a refresh. An
        # `on_load` on the chat page would fire with `user_id == ""` every time
        # and have nothing to read.
        await self._load_sessions(identity)
        if self.sessions:
            self.active_session_id = self.sessions[0].session_id
            try:
                self.messages = await self._read_transcript(
                    identity, self.active_session_id
                )
            except Exception:
                # A transcript that will not load is not a failed sign-in,
                # exactly as a rail that will not load is not -- the arm inside
                # `_load_sessions`. The chat opens empty and the composer works.
                self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE

    async def _load_sessions(self, identity: Identity) -> None:
        """Reads the rail: the capped list, and the true total beside it.

        Extracted from `login` so `retry_sessions` cannot drift from it. A
        retry that rebuilt the list slightly differently from the sign-in that
        preceded it would be the rail's own version of the two-notice
        conflation `transcript_error` exists to avoid.

        Not an `@rx.event`: it is called by handlers that already hold the
        exclusive state lock, and an event handler awaited from another handler
        is the mistake `login`'s docstring spells out for background tasks.

        Both arms assign, and that is the contract: on failure the list is
        emptied and `sessions_error` is set, so a caller never has to guess
        which of the two states it is in. `sessions_total` goes to 0 on that
        arm because a count that could not be read is not a count.
        """
        self.sessions_error = ""
        try:
            rows = await asyncio.to_thread(chat_sessions.list_for, identity)
            total = await asyncio.to_thread(chat_sessions.count, identity)
        except ChatSessionError as exc:
            # A rail that will not load is not a failed sign-in. The user is
            # already authenticated by this point and the composer works
            # without a session; only the list is missing.
            self.sessions = []
            self.sessions_total = 0
            self.sessions_error = str(exc)
            return

        # One clock read for the whole list, per format_activity's own
        # docstring: "a rail of thirty rows shares one clock read".
        now = datetime.now(timezone.utc)
        self.sessions = [
            ChatSessionSummary(
                session_id=row.session_id,
                title=row.title,
                activity_info=format_activity(row.updated_at, now),
            )
            for row in rows
        ]
        self.sessions_total = total

    @rx.event
    def logout(self):
        """Ends the session. The transcript goes with it: the header names who
        is sending, so leaving one user's prompts on screen under another's ID
        would misattribute them in a surface people read as a record.

        **The rail goes for the same reason.** A session list is a list of one
        person's subjects -- *Quarterly close reconciliation*, *Payroll
        question* -- and reading it under the next person's ID misattributes
        them exactly as the bubbles would. So `sessions`, `active_session_id`
        and `sessions_error` clear here too.

        **This handler writes nothing, and that is the whole of it.** It calls
        no service, resolves no Identity and is synchronous so that awaiting one
        would take a signature change. `logout()` clears state;
        `delete_session()` deletes rows. Conflating them -- "tidying up" the
        list here by deleting it in the database -- would destroy a user's
        history every time they signed out of a shared machine, which is the
        one thing this story is written to make impossible. The rows survive;
        signing back in lists them again.
        """
        self._token = ""
        self.user_id = ""
        self.token_input = ""
        self.login_error = ""
        self.messages = []
        self.input_text = ""
        self.sessions = []
        self.active_session_id = ""
        self.sessions_error = ""
        self.sessions_total = 0
        # The rail's presentation state goes with the rail. A half-typed rename
        # is one person's words about one person's chat, and an armed delete
        # confirmation naming a chat the next reader cannot see would be the
        # rail's version of the misattribution the docstring above refuses.
        self.renaming_session_id = ""
        self.rename_draft = ""
        self.confirming_delete_id = ""
        # The notice is *about* the transcript being cleared above, so leaving
        # it standing would report a lost turn for a conversation that is no
        # longer on screen. Its rail counterpart, `sessions_error`, clears with
        # `sessions` for the same reason.
        self.transcript_error = ""

    @rx.event
    async def retry_sessions(self):
        """Reads the rail again after a read that failed. AC 6's second half.

        The fault state offers an action rather than only naming the failure
        (frontend-design: "errors don't apologize, and they are never vague
        about what happened"), and this is that action.

        **It re-reads the list and nothing else.** `messages` and
        `active_session_id` are untouched, because the transcript on screen is
        still a real conversation the reader can see -- the distinction
        `select_session` already draws on its own failure arm. A retry that
        also reloaded the transcript would make a failed rail read cost the
        chat, which is the coupling `login` refuses too.

        Plain async, per `select_session`: it holds the exclusive state lock
        across its awaits, so the read and the swap cannot interleave with a
        send.
        """
        identity = resolve(self._token)
        if identity is None:
            self.sessions_error = SESSION_INVALIDATED_ERROR
            return

        await self._load_sessions(identity)

    @rx.event
    def new_chat(self):
        """Opens a blank chat. **Nothing is written, and that is the feature.**

        STORY-013 made creation lazy -- PRD-008 Section 4, verbatim: "a session
        row is written on the first send, never on page load -- an
        opened-and-abandoned tab leaves nothing behind." So starting a chat is
        the act of emptying `active_session_id`, and `_do_send`'s `if not
        session_id:` arm does the rest on the first send. Calling
        `chat_sessions.create` here would put the abandoned-tab row back: click
        this ten times and the rail would grow ten empty chats.

        Two vars are deliberately left alone. `input_text` is the person's
        half-typed text and belongs to them rather than to the chat, which is
        the choice `select_session` already makes; `logout` clears it only
        because the person themselves is leaving. `sessions_error` is the
        rail's slot -- a list that failed to load is still failed after
        starting a new chat.

        The `pending` guard is `select_session`'s, for the sharper half of its
        reason: clearing `messages` under an in-flight send files that send's
        answer into a chat the user has already left.
        """
        if self.pending:
            return
        self.active_session_id = ""
        self.messages = []
        # About the transcript cleared on the line above, so it cannot outlive
        # it -- the reasoning `logout` and `select_session` both record.
        self.transcript_error = ""

    # --- The rail's modes (STORY-018) ------------------------------------
    # Six handlers that write no rows and read no database. They move the rail
    # between its three per-row modes -- reading, renaming, confirming a delete
    # -- and exist because Reflex has no component-local state for
    # `session_rail.py` to hold them in.
    #
    # The two that *open* a mode carry the `pending` guard `new_chat` and
    # `edit_and_resend` carry, and for the milder half of its reason: a rename
    # committed under an in-flight send is fine, but a confirmation armed
    # against a rail that is about to reorder invites a click on the wrong row.
    # The three that close a mode are unguarded, because getting *out* of a
    # mode must never be refused.

    @rx.event
    def begin_rename(self, session_id: str, title: str):
        """Opens the rename field on one row, seeded with its current title.

        Seeded rather than blank: the reader is editing a name, not supplying
        one, and an empty field would read as "type a new name" while the
        thing it is about to replace has scrolled out of view.

        Clears any armed delete, because a row is in one mode or none. The two
        vars are separate rather than one mode enum so that neither can be read
        as the other by a component that forgot to check which.
        """
        if self.pending:
            return
        self.confirming_delete_id = ""
        self.renaming_session_id = session_id
        self.rename_draft = title

    @rx.event
    def set_rename_draft(self, text: str):
        """The field's keystrokes. `set_input_text`'s shape exactly."""
        self.rename_draft = text

    @rx.event
    def commit_rename(self):
        """Closes the field and hands the title to `rename_session`.

        **It validates nothing and writes nothing itself.** `rename_session`
        already owns the empty-title refusal, the ownership re-check against a
        freshly resolved Identity, and the in-place list rebuild that keeps the
        row from moving. Re-checking any of that here would be a second copy of
        a rule that is only correct in one place.

        The field closes before the write is dispatched, not after it lands: a
        rename that fails reports on the rail's own slot, and holding an open
        input over it would leave the reader editing a value the screen has
        already replaced.
        """
        session_id, title = self.renaming_session_id, self.rename_draft
        self.renaming_session_id = ""
        self.rename_draft = ""
        if not session_id:
            return
        return ChatState.rename_session(session_id, title)

    @rx.event
    def cancel_rename(self):
        """Closes the field, discarding the draft. Writes nothing."""
        self.renaming_session_id = ""
        self.rename_draft = ""

    @rx.event
    def ask_delete(self, session_id: str):
        """Arms the confirmation on one row. **Nothing is deleted here.**

        `delete_session` is the confirmed branch and its docstring says so:
        this handler is the question, that one is the answer. Splitting them is
        what lets the confirmation live in the component, where PRD Section 6.1
        can govern how it looks, rather than in an `rx.window_alert` the design
        cannot reach.
        """
        if self.pending:
            return
        self.renaming_session_id = ""
        self.rename_draft = ""
        self.confirming_delete_id = session_id

    @rx.event
    def cancel_delete(self):
        """Walks away from the confirmation. The chat is kept, untouched."""
        self.confirming_delete_id = ""

    @rx.event
    def edit_and_resend(self, prompt: str):
        if self.pending:
            return
        self.input_text = prompt
        return rx.set_focus("chat_input")

    @rx.event
    async def select_session(self, session_id: str):
        """Makes `session_id` the active chat and renders its transcript.

        Plain async, not `background=True`, for the reason `login` states: a
        background task cannot be called from another handler and holds no lock
        across its awaits. Plain async holds the exclusive lock for the whole
        handler, so the read below and the swap after it cannot interleave with
        a send -- which is the other half of the `pending` guard rather than a
        duplicate of it.

        `session_id` arrives from the client and is untrusted (PRD-008 Risk 3).
        It is not validated here and must not be: `chat_sessions` re-checks
        ownership server-side against the freshly resolved Identity, and
        returns [] for a foreign id, an unknown id and history being off alike.
        A caller that could tell those apart would be a caller branching on the
        flag.
        """
        if self.pending:
            # The same refusal `edit_and_resend` applies, and for a sharper
            # reason: `_do_send` is holding a `session_id` in a local and will
            # append the answer to it. Swapping `messages` out from under an
            # in-flight send files that answer in the wrong chat.
            return

        identity = resolve(self._token)
        if identity is None:
            self.sessions_error = SESSION_INVALIDATED_ERROR
            return

        try:
            restored = await self._read_transcript(identity, session_id)
        except Exception:
            # Bare `Exception`, not `ChatSessionError`: a StorageError that
            # escaped the service's wrapping must not empty the screen either.
            # Nothing is assigned on this arm, so `messages` *and*
            # `active_session_id` both stand -- moving the active id to a chat
            # whose transcript is not on screen would leave the rail marking a
            # conversation the reader cannot see.
            self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE
            return

        self.messages = restored
        self.active_session_id = session_id
        self.sessions_error = ""
        # The notice was about the transcript the line above just replaced, so
        # it cannot outlive it -- the reasoning `logout` records for the same
        # var.
        self.transcript_error = ""

    @rx.event
    async def rename_session(self, session_id: str, title: str):
        """Retitles an owned chat, in place, without moving it.

        Plain async, not `background=True`, for the reason `login` and
        `select_session` both state: the handler holds the exclusive state lock
        for its whole duration, so `self` is the real state, mutations are
        direct, and an `async with self` here would deadlock on a lock this
        handler already holds.

        **A rename is not activity.** `database.rename_chat_session` refuses to
        move `updated_at` and records why -- "a rename that bumped the
        timestamp would reorder the rail and move the row the user was looking
        at while they were looking at it". This is the state layer's half of
        that: the row is replaced at its own index, keeping the
        `activity_info` it already had, and nothing re-sorts. Calling `touch`
        here, or recomputing the activity string from a fresh clock, would undo
        the store's care at the last step.

        **Nothing re-derives the title.** `formatting.derive_title` is called
        exactly once per session, inside `chat_sessions.create`, and this
        handler adds no second call site -- which is what makes a rename
        survive the next send rather than being silently reverted by it.

        An empty or whitespace title is refused before any identity work and
        **silently**: the refusal is of the input, not of the system, and the
        existing title standing is the whole feedback. Putting a notice on
        `sessions_error` for a keystroke would report a stale list for
        something that is not about the list.

        `session_id` is untrusted (PRD-008 Risk 3) and is not validated here.
        `chat_sessions.rename` scopes the `WHERE` on the freshly resolved
        Identity and returns `False` for a foreign id, an unknown id and
        history being off alike -- one arm, and a caller that cannot tell them
        apart.
        """
        title = title.strip()
        if not title:
            return

        identity = resolve(self._token)
        if identity is None:
            self.sessions_error = SESSION_INVALIDATED_ERROR
            return

        try:
            renamed = await asyncio.to_thread(
                chat_sessions.rename, identity, session_id, title
            )
        except ChatSessionError as exc:
            self.sessions_error = str(exc)
            return

        if not renamed:
            return

        # Replaced at its index, not moved to the front: the whole list is
        # reassigned because a Reflex list var is replaced rather than mutated
        # in place, but the order is the one it already had.
        self.sessions = [
            ChatSessionSummary(
                session_id=row.session_id,
                title=title,
                activity_info=row.activity_info,
            )
            if row.session_id == session_id
            else row
            for row in self.sessions
        ]
        self.sessions_error = ""

    @rx.event
    async def delete_session(self, session_id: str):
        """Deletes an owned chat and its transcript, then lands somewhere real.

        Plain async and never `background=True`, per `rename_session` above.

        **This is the handler that deletes rows.** `logout()` clears state and
        writes nothing; this one writes and clears nothing else. The two must
        not borrow each other's mechanism, which is why neither calls the
        other's.

        **It asks nothing.** `rx.window_alert` and `rx.alert_dialog` both exist
        in the pinned Reflex, and neither is used: the confirmation is
        STORY-018's component, and a state handler that popped its own dialog
        would put the flow's gate in a layer the component cannot replace. This
        handler *is* the confirmed branch. The words it is confirmed with are
        `copy.SESSION_DELETE_CONFIRM_TEMPLATE`.

        **`audit_logs` is untouched**, because the only write here is
        `chat_sessions.delete`, whose statements name `chat_sessions` and
        `chat_messages` and nothing else (PRD Section 9: the orphaned
        `session_id` on the audit rows "is what preserves the evidence when a
        user tidies their list").

        **Where the screen lands.** `self.sessions` is `list_for`'s output,
        `ORDER BY updated_at DESC`, so after dropping the deleted row index 0
        *is* the next most recent chat -- read from the list already in hand
        rather than re-listed, since a stale row costs a failed read and its
        notice, not a wrong transcript.

        **The one place in this class where a failed read empties the screen.**
        `select_session` leaves the old transcript standing when a read fails,
        because it is still a real conversation the reader could be looking at.
        Here it is not: it belongs to the session just deleted, and landing on
        it is the single outcome this story forbids. So the failure arm clears
        `messages` and reports on the rail's slot.
        """
        if self.pending:
            return

        identity = resolve(self._token)
        if identity is None:
            self.sessions_error = SESSION_INVALIDATED_ERROR
            return

        try:
            deleted = await asyncio.to_thread(
                chat_sessions.delete, identity, session_id
            )
        except ChatSessionError as exc:
            self.sessions_error = str(exc)
            return

        if not deleted:
            # Foreign, unknown, and history-off in one arm -- `rename_session`
            # records the reason. Nothing is mutated, so the rail is unaffected.
            return

        remaining = [row for row in self.sessions if row.session_id != session_id]
        self.sessions = remaining
        self.sessions_error = ""
        # The scope line counts the whole account, not the page, so a delete
        # has to move it or "50 most recent of 212" survives the row it
        # counted. Floored at zero rather than trusted: the total is read once
        # per load and a second tab deleting the same chat would otherwise
        # drive it negative.
        self.sessions_total = max(0, self.sessions_total - 1)
        # The confirmation was about a row that no longer exists. Leaving it
        # set would arm the next chat that lands in the deleted one's place.
        self.confirming_delete_id = ""

        if self.active_session_id != session_id:
            # A chat the reader is not looking at: the rail changes and the
            # transcript on screen does not.
            return

        # The transcript below is replaced or emptied either way, so its notice
        # cannot outlive it.
        self.transcript_error = ""

        if not remaining:
            self.active_session_id = ""
            self.messages = []
            return

        next_id = remaining[0].session_id
        try:
            restored = await self._read_transcript(identity, next_id)
        except Exception:
            self.active_session_id = next_id
            self.messages = []
            self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE
            return

        self.active_session_id = next_id
        self.messages = restored

    def _promote_session(self, row: ChatSession, now: datetime) -> None:
        """Moves this session to the front of the rail, inserting it if new.

        Called under the lock, from `_append_and_persist` only. Sync on purpose:
        it touches no database and its one caller is already inside
        `async with self`.

        The row is the store's, not a locally built one. The title in particular
        must not be re-derived here -- `formatting.derive_title` is "called
        exactly once per session" and "a renamed session must never drift back
        to its first prompt", so the rail shows the title that is stored.
        """
        remaining = [s for s in self.sessions if s.session_id != row.session_id]
        self.sessions = [
            ChatSessionSummary(
                session_id=row.session_id,
                title=row.title,
                activity_info=format_activity(row.updated_at, now),
            ),
            *remaining,
        ]

    async def _read_transcript(
        self, identity: Identity, session_id: str
    ) -> list[ChatMessage]:
        """This session's stored bubbles, in write order, rehydrated.

        **Callable only from a plain async handler**, and the opposite rule to
        `_append_and_persist` below. That is a rule about the handler kind and
        not a list of names: every caller -- `login`, `select_session` and
        `delete_session` -- holds the exclusive state lock for its whole
        duration, so `self` is the real state and an `async with self` here
        would deadlock on a lock the caller already holds. `login`'s own
        docstring records the same rule for the same reason. A fourth caller is
        welcome on the same terms and on no others: a background task must not
        call this. Nothing here mutates state; the caller does that with the
        returned list.

        The order is the store's (`ORDER BY id ASC`) and is not re-sorted: a
        second sort in a second module is a second opinion about the order,
        which the PRD spends a paragraph refusing.

        Raises whatever the read raised. The caller owns the notice, because
        only the caller knows what is on screen to be left alone.
        """
        rows = await asyncio.to_thread(
            chat_sessions.messages_for, identity, session_id
        )
        return [_to_chat_message(row) for row in rows]

    async def _append_and_persist(
        self,
        bubble: ChatMessage,
        identity: Optional[Identity],
        session_id: Optional[str],
    ) -> None:
        """Puts one bubble on screen, then tries to record it. In that order.

        **The order is the story.** PRD-008 Section 6: "the transcript write
        happens after, in the UI layer, and is allowed to fail without taking
        the turn with it." PRD Risk 5 is the failure it is written against: "the
        model answered, the audit row is written, and then the transcript insert
        fails -- a naive implementation raises and the user loses a paid, logged
        answer."

        **Every bubble in `_do_send` goes through here, including the ones that
        cannot be written.** The guard below returns for a send with no
        resolvable identity and for one with no session -- history off, or a
        create that failed. Routing those through the same helper rather than
        leaving them as hand-rolled appends is what makes a ninth outcome added
        later persist by default instead of by remembering.

        **It must not be called from inside `async with self`.** `_do_send` is a
        background task, so `self` is a `StateProxy`, and nesting the context
        raises ImmutableStateError ("Do not nest `async with self` blocks",
        reflex/istate/proxy.py). The lock is opened here, around short
        mutations, with both database calls offloaded between them.

        **Two guarded arms, not one, because one notice cannot be true for
        both.** A failed `append_message` means the turn is not in the database.
        A failed `touch` means it is, and only the ordering is stale. AC 6
        requires the second not to "surface as a lost turn", so it gets its own
        quieter notice on the rail's own error slot instead of borrowing the
        transcript's.

        Both arms catch bare `Exception` rather than `ChatSessionError`. The
        story is explicit: a `StorageError` that escaped wrapping would
        otherwise take the turn down, which is the one outcome this helper
        exists to prevent.
        """
        async with self:
            self.messages.append(bubble)

        if identity is None or not session_id:
            # Nothing to record against: the credential did not resolve, the
            # create failed, or persistence is off. No write, and no notice --
            # AC 7's "no write is attempted, no notice appears", reached without
            # this class ever naming the flag.
            return

        try:
            await asyncio.to_thread(
                chat_sessions.append_message,
                identity,
                session_id,
                _to_stored_message(bubble, session_id),
            )
        except Exception:
            async with self:
                self.transcript_error = TRANSCRIPT_NOT_SAVED_NOTICE
            return

        async with self:
            self.transcript_error = ""

        try:
            await asyncio.to_thread(chat_sessions.touch, identity, session_id)
            # Re-read rather than stamp a timestamp here: `touch` returns a
            # bool, and the row carries both the authoritative `updated_at` and
            # the authoritative title -- which the rail needs on the first send
            # of a new chat, when STORY-013's create left no summary behind. One
            # primary-key read on a path that has just made two writes and a
            # model round trip.
            row = await asyncio.to_thread(chat_sessions.get, identity, session_id)
            if row is not None:
                now = datetime.now(timezone.utc)
                async with self:
                    self._promote_session(row, now)
                    self.sessions_error = ""
        except Exception:
            async with self:
                self.sessions_error = SESSION_ORDER_STALE_NOTICE

    async def _do_send(self, text: str):
        # Claim the in-flight slot first and on its own, so everything that can
        # raise afterwards is inside the try/finally that clears `pending`
        # (PRD-004 Risk 3: a stuck flag locks the composer permanently).
        async with self:
            if not self.user_id.strip():
                return
            text = text.strip()
            if not text:
                return
            if self.pending:
                return
            self.pending = True
            token = self._token

        # PRD-005 Risk 5: re-resolved fresh on every call, never cached --
        # there is no role field anywhere on this class to read one from.
        identity = resolve(token)
        if identity is None:
            # Through the same helper as every other bubble, even though its
            # guard will return before any write: there is no Identity here, so
            # there is no owner to file a row under. One append path, not two.
            await self._append_and_persist(
                ChatMessage(
                    kind="internal_error",
                    content="internal_error",
                    prompt=text,
                    detail=SESSION_INVALIDATED_ERROR,
                ),
                None,
                None,
            )
            async with self:
                self.pending = False
            return

        try:
            async with self:
                self.input_text = ""
                model = self.selected_model
                # Read through the lock into a local, like `model` above: a
                # background task has no exclusive access outside the block.
                session_id = self.active_session_id
                device = None
                try:
                    if (
                        self.router
                        and self.router.headers
                        and self.router.headers.raw_headers
                    ):
                        device = self.router.headers.raw_headers.get("user-agent")
                except Exception:
                    device = None

            # After the lock is released, not inside it: `_append_and_persist`
            # opens its own and the proxy refuses a nested one. `session_id` is
            # "" on the first send of a new chat -- the create below has not run
            # yet, deliberately, so that a slow create never hides what the user
            # typed -- and the helper's guard skips the write for it. STORY-015
            # inherits that: a restored first turn starts at the assistant
            # bubble.
            await self._append_and_persist(
                ChatMessage(kind="user", content=text, prompt=text),
                identity,
                session_id,
            )

            # Lazily, and only on the first send of a chat: PRD-008 Section 4,
            # "a session row is written on the first send, never on page load
            # -- an opened-and-abandoned tab leaves nothing behind." Inside the
            # try/finally opened above, so the new failure mode cannot leave
            # `pending` stuck (PRD-004 Risk 3), and after the user's bubble is
            # on screen, so a slow create never hides what they typed.
            if not session_id:
                try:
                    session_id = await asyncio.to_thread(
                        chat_sessions.create, identity, text, derive_title
                    )
                except ChatSessionError as exc:
                    # A broken rail does not block the composer: the turn is
                    # sent unattached rather than refused.
                    session_id = None
                    async with self:
                        self.sessions_error = str(exc)
                else:
                    # None when history is off -- a value to proceed with, not a
                    # failure, which is how this class stays free of any branch
                    # on CHAT_HISTORY_ENABLED.
                    if session_id:
                        async with self:
                            self.active_session_id = session_id
                            self.sessions_error = ""
                            # A chat that did not exist before this send now
                            # does, and the scope line counts the account
                            # rather than the page -- so the total moves with
                            # the create, exactly as it moves with a delete.
                            # `_promote_session` adds the row itself.
                            self.sessions_total += 1

            try:
                result = await asyncio.to_thread(
                    run_query,
                    identity=identity,
                    prompt=text,
                    device=device,
                    model=model,
                    openrouter_api_key=None,
                    call_openrouter=call_openrouter,
                    # `or None` is defensive, not currently reachable: the
                    # branch above always replaces an empty active_session_id
                    # with either a real id or None. It is kept because
                    # active_session_id is a str var whose unset value is ""
                    # while log_query takes Optional[str], so any future edit
                    # that lets "" through here would silently write an
                    # empty-string conversation id onto audit rows instead of
                    # NULL -- a value that reads as a session but joins to none.
                    session_id=session_id or None,
                )
            except OpenRouterError as exc:
                await self._append_and_persist(
                    ChatMessage(
                        kind="upstream_error",
                        content="upstream_error",
                        prompt=text,
                        detail=str(exc),
                    ),
                    identity,
                    session_id,
                )
                return
            except (DuplicateCheckError, PiiRedactorError) as exc:
                await self._append_and_persist(
                    ChatMessage(
                        kind="internal_error",
                        content="internal_error",
                        prompt=text,
                        detail=str(exc),
                    ),
                    identity,
                    session_id,
                )
                return
            except Exception as exc:
                await self._append_and_persist(
                    ChatMessage(
                        kind="internal_error",
                        content="internal_error",
                        prompt=text,
                        detail=str(exc),
                    ),
                    identity,
                    session_id,
                )
                return

            if isinstance(result, QuerySuccessResponse):
                bubble = ChatMessage(
                    kind="assistant",
                    # The redacted text the pipeline released, and the reason
                    # this field is safe to persist. PRD-008 Section 9: "The raw
                    # upstream text is never written to `chat_messages`."
                    content=result.response,
                    prompt=text,
                    model_used=result.model_used,
                    tokens_used=result.tokens_used,
                    audit_id=result.audit_id,
                    pii_redacted=result.pii_redacted,
                    pii_entities=result.pii_entities_masked,
                )
            elif isinstance(result, QueryBlockedDuplicateResponse):
                relative_info, release_info = format_duplicate_info(
                    result.first_query_at
                )
                bubble = ChatMessage(
                    kind="duplicate",
                    content=result.reason,
                    prompt=text,
                    first_query_at=result.first_query_at,
                    duplicate_relative_info=relative_info,
                    duplicate_release_info=release_info,
                )
            elif isinstance(result, QueryBlockedSuspiciousResponse):
                bubble = ChatMessage(
                    kind="injection",
                    content=result.reason,
                    prompt=text,
                    pattern=result.pattern,
                )
            elif isinstance(result, QueryBlockedForbiddenResponse):
                bubble = ChatMessage(
                    kind="forbidden",
                    content=result.reason,
                    prompt=text,
                    required_permission=result.required_permission,
                )
            else:
                # Unreachable for the current QueryResponse union -- kept so a
                # fifth member added later without updating this chain surfaces
                # as a visible bubble instead of an unhandled exception.
                bubble = ChatMessage(
                    kind="internal_error",
                    content="internal_error",
                    prompt=text,
                    detail=f"Unhandled response type: {type(result).__name__}",
                )

            await self._append_and_persist(bubble, identity, session_id)
        finally:
            async with self:
                self.pending = False

    @rx.event(background=True)
    async def retry_message(self, prompt: str):
        await self._do_send(prompt)

    @rx.event(background=True)
    async def send(self):
        # Read through the lock: a background event has no exclusive access to
        # state outside an `async with self` block.
        async with self:
            text = self.input_text
        await self._do_send(text)
