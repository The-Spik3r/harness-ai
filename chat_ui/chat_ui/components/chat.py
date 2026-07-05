import reflex as rx

from chat_ui.state import ChatState


def message_bubble(message: dict) -> rx.Component:
    """A single chat bubble, right-aligned for the user, left-aligned otherwise."""
    return rx.cond(
        message["role"] == "user",
        rx.hstack(
            rx.box(
                message["content"],
                background_color="#2563eb",
                color="white",
                padding="0.65rem 1rem",
                border_radius="1rem",
                max_width="70%",
            ),
            rx.avatar(fallback="U", size="2", color_scheme="blue"),
            justify="end",
            width="100%",
        ),
        rx.hstack(
            rx.avatar(fallback="AI", size="2", color_scheme="gray"),
            rx.box(
                message["content"],
                background_color="#f3f4f6",
                color="#111827",
                padding="0.65rem 1rem",
                border_radius="1rem",
                max_width="70%",
            ),
            justify="start",
            width="100%",
        ),
    )


def message_list() -> rx.Component:
    """Scrollable column of chat bubbles, grows to fill available height."""
    return rx.box(
        rx.foreach(ChatState.messages, message_bubble),
        display="flex",
        flex_direction="column",
        gap="0.75rem",
        overflow_y="auto",
        flex="1",
        width="100%",
        padding="1rem",
    )


def chat_input() -> rx.Component:
    """Input bar with a text field and a send button, submitted via Enter or click."""
    return rx.form(
        rx.hstack(
            rx.input(
                value=ChatState.input_text,
                on_change=ChatState.set_input_text,
                placeholder="Message...",
                width="100%",
            ),
            rx.icon_button(
                rx.icon("send", size=18),
                type="submit",
            ),
            width="100%",
            padding="1rem",
        ),
        on_submit=ChatState.send,
        reset_on_submit=True,
        width="100%",
    )
