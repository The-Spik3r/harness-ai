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

        self.sessions_error = ""
        try:
            rows = await asyncio.to_thread(chat_sessions.list_for, identity)
        except ChatSessionError as exc:
            # A rail that will not load is not a failed sign-in. The user is
            # already authenticated by this point and the composer works
            # without a session; only the list is missing.
            self.sessions = []
            self.sessions_error = str(exc)
        else:
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
            # The list is ORDER BY updated_at DESC, so the first row is the
            # most recently active chat. Opening it is what makes a reload cost
            # nothing: this handler *is* the page load for a signed-in user,
            # because `_token` is a backend var and no signed-in state survives
            # a refresh. An `on_load` on the chat page would fire with
            # `user_id == ""` every time and have nothing to read.
            if self.sessions:
                self.active_session_id = self.sessions[0].session_id
                try:
                    self.messages = await self._read_transcript(
                        identity, self.active_session_id
                    )
                except Exception:
                    # A transcript that will not load is not a failed sign-in,
                    # exactly as a rail that will not load is not -- the arm
                    # above. The chat opens empty and the composer works.
                    self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE

    @rx.event
    def logout(self):
        """Ends the session. The transcript goes with it: the header names who
        is sending, so leaving one user's prompts on screen under another's ID
        would misattribute them in a surface people read as a record."""
        self._token = ""
        self.user_id = ""
        self.token_input = ""
        self.login_error = ""
        self.messages = []
        self.input_text = ""
        # The notice is *about* the transcript being cleared on the line above,
        # so leaving it standing would report a lost turn for a conversation
        # that is no longer on screen. STORY-016 clears `sessions`,
        # `active_session_id` and `sessions_error`; this one belongs with
        # `messages`.
        self.transcript_error = ""

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
        `_append_and_persist` below. Both callers (`login` and
        `select_session`) hold the exclusive state lock for their whole
        duration, so `self` is the real state and an `async with self` here
        would deadlock on a lock the caller already holds -- `login`'s own
        docstring records the same rule for the same reason. Nothing here
        mutates state; the caller does that with the returned list.

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
