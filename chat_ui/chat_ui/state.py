import asyncio
from datetime import datetime, timezone

import reflex as rx

from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import resolve
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query
from .models import ChatMessage, ChatSessionSummary
from .copy import (
    LOGIN_INVALID_TOKEN_ERROR,
    LOGIN_TOKEN_REQUIRED_ERROR,
    SESSION_INVALIDATED_ERROR,
)
from .formatting import derive_title, format_activity, format_duplicate_info
from .config import DEFAULT_MODEL

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

    @rx.event
    def edit_and_resend(self, prompt: str):
        if self.pending:
            return
        self.input_text = prompt
        return rx.set_focus("chat_input")

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
            async with self:
                self.messages.append(
                    ChatMessage(
                        kind="internal_error",
                        content="internal_error",
                        prompt=text,
                        detail=SESSION_INVALIDATED_ERROR,
                    )
                )
                self.pending = False
            return

        try:
            async with self:
                self.messages.append(
                    ChatMessage(kind="user", content=text, prompt=text)
                )
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
                async with self:
                    self.messages.append(
                        ChatMessage(
                            kind="upstream_error",
                            content="upstream_error",
                            prompt=text,
                            detail=str(exc),
                        )
                    )
                return
            except (DuplicateCheckError, PiiRedactorError) as exc:
                async with self:
                    self.messages.append(
                        ChatMessage(
                            kind="internal_error",
                            content="internal_error",
                            prompt=text,
                            detail=str(exc),
                        )
                    )
                return
            except Exception as exc:
                async with self:
                    self.messages.append(
                        ChatMessage(
                            kind="internal_error",
                            content="internal_error",
                            prompt=text,
                            detail=str(exc),
                        )
                    )
                return

            if isinstance(result, QuerySuccessResponse):
                bubble = ChatMessage(
                    kind="assistant",
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

            async with self:
                self.messages.append(bubble)
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
