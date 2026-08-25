import reflex as rx

from chat_ui.state import ChatState
from chat_ui.copy import (
    USER_ID_PROMPT_TITLE,
    USER_ID_PLACEHOLDER,
    USER_ID_SUBMIT_LABEL,
)
from chat_ui.components.bubbles import (
    render_user,
    render_assistant,
    render_duplicate,
    render_injection,
    render_upstream_error,
    render_internal_error,
    render_fallback,
    render_pending_indicator,
)


def message_bubble(message) -> rx.Component:
    """Dispatches message rendering based on message.kind using rx.match."""
    return rx.match(
        message.kind,
        ("user", render_user(message)),
        ("assistant", render_assistant(message)),
        ("duplicate", render_duplicate(message)),
        ("injection", render_injection(message)),
        ("upstream_error", render_upstream_error(message)),
        ("internal_error", render_internal_error(message)),
        render_fallback(message),
    )


def message_list() -> rx.Component:
    """Scrollable column of chat bubbles, grows to fill available height."""
    return rx.auto_scroll(
        rx.foreach(ChatState.messages, message_bubble),
        rx.cond(
            ChatState.pending,
            render_pending_indicator(),
            rx.fragment(),
        ),
        display="flex",
        flex_direction="column",
        gap="0.75rem",
        flex="1",
        width="100%",
        padding="1rem",
    )


def user_id_prompt() -> rx.Component:
    """Full-page form collecting the session's user_id once, before the chat becomes usable."""
    return rx.center(
        rx.form(
            rx.vstack(
                rx.text(USER_ID_PROMPT_TITLE, size="4", weight="bold"),
                rx.input(
                    value=ChatState.user_id_input,
                    on_change=ChatState.set_user_id_input,
                    placeholder=USER_ID_PLACEHOLDER,
                    width="100%",
                ),
                rx.cond(
                    ChatState.user_id_error != "",
                    rx.text(ChatState.user_id_error, color="red", size="2"),
                    rx.fragment(),
                ),
                rx.button(USER_ID_SUBMIT_LABEL, type="submit"),
                spacing="3",
                width="20rem",
            ),
            on_submit=ChatState.submit_user_id,
        ),
        height="100vh",
        width="100%",
    )


def chat_input() -> rx.Component:
    """Input bar with a text field and a send button, submitted via Enter or click."""
    return rx.form(
        rx.hstack(
            rx.input(
                value=ChatState.input_text,
                on_change=ChatState.set_input_text,
                placeholder="Message...",
                disabled=ChatState.pending,
                width="100%",
            ),
            rx.icon_button(
                rx.icon("send", size=18),
                type="submit",
                disabled=ChatState.pending,
            ),
            width="100%",
            padding="1rem",
        ),
        on_submit=ChatState.send,
        reset_on_submit=True,
        width="100%",
    )
