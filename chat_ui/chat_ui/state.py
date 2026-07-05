import reflex as rx

from app.models.schemas import QueryBlockedDuplicateResponse, QuerySuccessResponse
from app.services.duplicate_checker import DuplicateCheckError
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.query_pipeline import run_query

WELCOME_MESSAGE = {
    "role": "assistant",
    "content": "Hi! Type a message below and press send.",
}


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

    messages: list[dict[str, str]] = [WELCOME_MESSAGE]
    input_text: str = ""
    user_id: str = ""
    user_id_input: str = ""

    @rx.event
    def set_input_text(self, text: str):
        self.input_text = text

    @rx.event
    def set_user_id_input(self, text: str):
        self.user_id_input = text

    @rx.event
    def submit_user_id(self):
        text = self.user_id_input.strip()
        if not text:
            return
        self.user_id = text

    @rx.event(background=True)
    async def send(self):
        async with self:
            if not self.user_id.strip():
                return
            text = self.input_text.strip()
            if not text:
                return
            self.messages.append({"role": "user", "content": text})
            self.input_text = ""
            user_id = self.user_id

        try:
            result = run_query(
                user_id=user_id,
                prompt=text,
                device=None,
                model="gpt-4",
                openrouter_api_key=None,
                call_openrouter=call_openrouter,
            )
        except (DuplicateCheckError, OpenRouterError) as exc:
            async with self:
                self.messages.append({"role": "system", "content": f"Error: {exc}"})
            return

        if isinstance(result, QuerySuccessResponse):
            bubble = {"role": "assistant", "content": result.response}
        elif isinstance(result, QueryBlockedDuplicateResponse):
            bubble = {
                "role": "system",
                "content": f"Blocked — {result.reason} (first sent at {result.first_query_at})",
            }
        else:
            bubble = {"role": "system", "content": f"Blocked — {result.reason}"}

        async with self:
            self.messages.append(bubble)
