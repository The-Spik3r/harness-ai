"""Everything around the transcript: the session gate, the header, and the
empty state.

The header is a masthead, not a toolbar: the wordmark sits in the display face
against a hairline rule, and the session facts (who is sending, which model) are
set in the data face on the right — the same split the entries use between
prose and evidence.
"""

import reflex as rx

from chat_ui import copy, theme
from chat_ui.config import MODEL_ALLOWLIST
from chat_ui.state import ChatState


def _label(text: str) -> rx.Component:
    return rx.box(
        text,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_TAG,
        letter_spacing="0.08em",
        text_transform="uppercase",
        color=theme.MUTE,
        white_space="nowrap",
    )


def model_selector() -> rx.Component:
    """Curated allowlist from config.py (STORY-016) — a free-text model would
    reach OpenRouter and fail in a way the reader cannot act on."""
    return rx.hstack(
        _label(copy.SHELL_MODEL_SLOT_LABEL),
        rx.select(
            MODEL_ALLOWLIST,
            value=ChatState.selected_model,
            on_change=ChatState.set_selected_model,
            size="1",
            variant="surface",
            color_scheme="gray",
            id="model-selector",
        ),
        align="center",
        spacing="2",
    )


def header() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.box(
                copy.SHELL_HEADER_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.0625rem",
                font_weight="700",
                letter_spacing="0.16em",
                color=theme.INK,
            ),
            rx.hstack(
                rx.box(
                    width="6px",
                    height="6px",
                    border_radius="1px",
                    background_color=theme.INK_CLEAR,
                ),
                _label(copy.SHELL_HEADER_BADGE),
                align="center",
                spacing="2",
                padding_left="0.875rem",
                margin_left="0.875rem",
                border_left=f"1px solid {theme.RULE}",
            ),
            align="center",
            spacing="0",
        ),
        rx.hstack(
            model_selector(),
            rx.hstack(
                _label(copy.SHELL_USER_LABEL),
                rx.box(
                    ChatState.user_id,
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_DATA,
                    font_weight="500",
                    color=theme.INK,
                ),
                rx.el.button(
                    copy.SHELL_CHANGE_USER_LABEL,
                    on_click=ChatState.reset_user_id,
                    type="button",
                    cursor="pointer",
                    background="none",
                    border="none",
                    padding="0",
                    font_family=theme.FONT_DISPLAY,
                    font_size=theme.TEXT_DATA,
                    color=theme.MUTE,
                    text_decoration="underline",
                    text_underline_offset="3px",
                    _hover={"color": theme.INK},
                ),
                align="center",
                spacing="2",
                padding_left="1rem",
                margin_left="0.25rem",
                border_left=f"1px solid {theme.RULE}",
            ),
            class_name="hx-header-meta",
            align="center",
            spacing="3",
        ),
        justify="between",
        align="center",
        width="100%",
        flex_wrap="wrap",
        row_gap="0.75rem",
        padding="0.9rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        background_color=theme.CARD,
        flex_shrink="0",
    )


def _legend_row(ink: str, text: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            width=theme.GLYPH,
            height=theme.GLYPH,
            border_radius="1px",
            background_color=ink,
            flex_shrink="0",
            margin_top="0.15rem",
        ),
        rx.box(
            text,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_BODY,
            color=theme.MUTE,
            line_height="1.5",
        ),
        align="start",
        spacing="3",
    )


def empty_state() -> rx.Component:
    """An empty screen is an invitation to act — and here it doubles as the
    legend for the rail the transcript is about to fill."""
    return rx.box(
        rx.vstack(
            rx.box(
                copy.EMPTY_STATE_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.75rem",
                font_weight="600",
                letter_spacing="-0.02em",
                color=theme.INK,
            ),
            rx.box(
                copy.EMPTY_STATE_SUBTITLE,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_LEAD,
                line_height="1.6",
                color=theme.MUTE,
                max_width="34rem",
                margin_top="0.5rem",
            ),
            rx.vstack(
                _legend_row(theme.INK_CLEAR, copy.EMPTY_STATE_PII_FEATURE),
                _legend_row(theme.INK_DENIED, copy.EMPTY_STATE_SECURITY_FEATURE),
                _legend_row(theme.INK_HELD, copy.EMPTY_STATE_DEDUP_FEATURE),
                align_items="start",
                spacing="3",
                margin_top="1.75rem",
                padding_top="1.5rem",
                border_top=f"1px solid {theme.RULE}",
                width="100%",
                max_width="34rem",
            ),
            align_items="start",
            spacing="0",
            width="100%",
            max_width=theme.COLUMN_MAX,
            margin="0 auto",
        ),
        flex="1",
        width="100%",
        padding="3.5rem 1.5rem 2rem",
        overflow_y="auto",
    )


def user_id_gate() -> rx.Component:
    """Full-page form collecting the session's user_id before the chat opens."""
    return rx.center(
        rx.box(
            rx.box(
                copy.SHELL_HEADER_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.0625rem",
                font_weight="700",
                letter_spacing="0.16em",
                color=theme.INK,
            ),
            rx.box(
                copy.USER_ID_PROMPT_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.5rem",
                font_weight="600",
                letter_spacing="-0.02em",
                color=theme.INK,
                margin_top="1.75rem",
            ),
            rx.box(
                copy.USER_ID_PROMPT_BODY,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_BODY,
                line_height="1.6",
                color=theme.MUTE,
                margin_top="0.5rem",
            ),
            rx.form(
                rx.input(
                    id="user_id_input",
                    class_name="hx-field-boxed",
                    value=ChatState.user_id_input,
                    on_change=ChatState.set_user_id_input,
                    placeholder=copy.USER_ID_PLACEHOLDER,
                    auto_focus=True,
                    custom_attrs={"autoComplete": "off", "autoCorrect": "off"},
                    width="100%",
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_BODY,
                    height="2.5rem",
                    border_radius=theme.RADIUS,
                    margin_top="1.5rem",
                ),
                rx.cond(
                    ChatState.user_id_error != "",
                    rx.box(
                        ChatState.user_id_error,
                        font_family=theme.FONT_DATA,
                        font_size=theme.TEXT_DATA,
                        color=theme.INK_DENIED,
                        margin_top="0.5rem",
                    ),
                    rx.fragment(),
                ),
                rx.box(
                    rx.el.button(
                        copy.USER_ID_SUBMIT_LABEL,
                        type="submit",
                        cursor="pointer",
                        width="100%",
                        height="2.5rem",
                        font_family=theme.FONT_DISPLAY,
                        font_size=theme.TEXT_BODY,
                        font_weight="600",
                        color=theme.PAPER,
                        background_color=theme.INK,
                        border="none",
                        border_radius=theme.RADIUS,
                        _hover={"background_color": theme.INK_UPSTREAM},
                        transition="background-color 120ms ease",
                    ),
                    margin_top="1rem",
                ),
                on_submit=ChatState.submit_user_id,
                width="100%",
            ),
            width="100%",
            max_width="24rem",
            padding="2.25rem",
            background_color=theme.CARD,
            border=f"1px solid {theme.RULE}",
            border_radius=theme.RADIUS,
        ),
        height="100vh",
        width="100%",
        padding="1.5rem",
    )
