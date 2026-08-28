"""The transcript column and the composer."""

import reflex as rx

from chat_ui import copy, theme
from chat_ui.components.bubbles import (
    render_assistant,
    render_duplicate,
    render_fallback,
    render_injection,
    render_internal_error,
    render_pending_indicator,
    render_upstream_error,
    render_user,
)
from chat_ui.state import ChatState


def message_bubble(message) -> rx.Component:
    """One rx.match over `kind`, one arm per pipeline outcome. A seventh
    outcome later is one new arm, not another level of nesting."""
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
    """The ledger. Entries carry their own bottom padding so the rail runs
    unbroken between them — hence gap 0."""
    return rx.auto_scroll(
        rx.box(
            rx.foreach(ChatState.messages, message_bubble),
            rx.cond(ChatState.pending, render_pending_indicator(), rx.fragment()),
            width="100%",
            max_width=theme.COLUMN_MAX,
            margin="0 auto",
        ),
        class_name="hx-scroll",
        display="flex",
        flex_direction="column",
        gap="0",
        flex="1",
        width="100%",
        padding="2rem 1.5rem 0.5rem",
    )


def chat_input() -> rx.Component:
    """Composer. Locked for the full duration of an in-flight request, which is
    what makes the single in-flight guard in state.py legible to the reader."""
    return rx.box(
        rx.form(
            rx.hstack(
                rx.input(
                    id="chat_input",
                    value=ChatState.input_text,
                    on_change=ChatState.set_input_text,
                    placeholder=copy.COMPOSER_PLACEHOLDER,
                    disabled=ChatState.pending,
                    width="100%",
                    height="2.75rem",
                    font_family=theme.FONT_BODY,
                    font_size=theme.TEXT_BODY,
                    color=theme.INK,
                    background_color="transparent",
                    border="none",
                    box_shadow="none",
                    padding="0 0.25rem",
                    _placeholder={"color": theme.MUTE},
                ),
                rx.el.button(
                    copy.COMPOSER_SEND_LABEL,
                    type="submit",
                    disabled=ChatState.pending,
                    aria_label=copy.COMPOSER_SEND_LABEL,
                    cursor="pointer",
                    flex_shrink="0",
                    height="2rem",
                    padding="0 0.9rem",
                    font_family=theme.FONT_DISPLAY,
                    font_size=theme.TEXT_DATA,
                    font_weight="600",
                    letter_spacing="0.04em",
                    color=theme.PAPER,
                    background_color=theme.INK,
                    border="none",
                    border_radius=theme.RADIUS,
                    transition="background-color 120ms ease, opacity 120ms ease",
                    _hover={"background_color": theme.INK_UPSTREAM},
                    _disabled={"opacity": "0.35", "cursor": "not-allowed"},
                ),
                align="center",
                spacing="2",
                width="100%",
            ),
            on_submit=ChatState.send,
            reset_on_submit=True,
            width="100%",
            max_width=theme.COLUMN_MAX,
            margin="0 auto",
            padding="0.5rem 0.75rem",
            background_color=theme.CARD,
            border=f"1px solid {theme.RULE}",
            border_radius=theme.RADIUS,
        ),
        width="100%",
        flex_shrink="0",
        padding="1rem 1.5rem 1.5rem",
    )
