import asyncio
import reflex as rx

from app.models.schemas import QueryBlockedDuplicateResponse, QuerySuccessResponse
from app.services.duplicate_checker import DuplicateCheckError
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query
from .models import ChatMessage
from .copy import USER_ID_VALIDATION_ERROR
from .formatting import format_duplicate_info
from .config import DEFAULT_MODEL

class ChatState(rx.State):
    """Holds chat messages, the input box's text, and the session's user_id.

    user_id is collected once per session via submit_user_id() (STORY-005).
    send() is a thin wrapper around the shared run_query(...) pipeline
    (STORY-001, PRD-002 Risk 4): it appends the user's message, calls
    run_query(...) in-process (a background event, since the OpenRouter
    call blocks), then appends the resulting bubble — success,
    duplicate-blocked, or suspicious-blocked — using the exact reason
    text run_query(...) returns.
    """

    messages: list[ChatMessage] = []
    input_text: str = ""
    user_id: str = ""
    user_id_input: str = ""
    user_id_error: str = ""
    pending: bool = False
    selected_model: str = DEFAULT_MODEL

    @rx.var
    def has_messages(self) -> bool:
        return len(self.messages) > 0

    @rx.event
    def set_input_text(self, text: str):
        self.input_text = text

    @rx.event
    def set_user_id_input(self, text: str):
        self.user_id_input = text

    @rx.event
    def set_selected_model(self, model: str):
        self.selected_model = model

    @rx.event
    def submit_user_id(self):
        text = self.user_id_input.strip()
        if not text:
            self.user_id_error = USER_ID_VALIDATION_ERROR
            return
        self.user_id_error = ""
        self.user_id = text

    @rx.event
    def reset_user_id(self):
        self.user_id = ""
        self.user_id_input = ""
        self.user_id_error = ""

    @rx.event(background=True)
    async def send(self):
        async with self:
            if not self.user_id.strip():
                return
            text = self.input_text.strip()
            if not text:
                return
            if self.pending:
                return
            self.pending = True
            self.messages.append(ChatMessage(kind="user", content=text, prompt=text))
            self.input_text = ""
            user_id = self.user_id
            model = self.selected_model

        try:
            try:
                result = await asyncio.to_thread(
                    run_query,
                    user_id=user_id,
                    prompt=text,
                    device=None,
                    model=model,
                    openrouter_api_key=None,
                    call_openrouter=call_openrouter,
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
            else:
                bubble = ChatMessage(
                    kind="injection",
                    content=result.reason,
                    prompt=text,
                    pattern=result.pattern,
                )

            async with self:
                self.messages.append(bubble)
        finally:
            async with self:
                self.pending = False
