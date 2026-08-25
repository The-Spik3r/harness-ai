import reflex as rx

from chat_ui.state import ChatState
from chat_ui.copy import (
    SHELL_HEADER_TITLE,
    SHELL_HEADER_BADGE,
    SHELL_CHANGE_USER_LABEL,
    SHELL_MODEL_SLOT_LABEL,
    EMPTY_STATE_TITLE,
    EMPTY_STATE_SUBTITLE,
    EMPTY_STATE_PII_FEATURE,
    EMPTY_STATE_SECURITY_FEATURE,
    EMPTY_STATE_DEDUP_FEATURE,
)


def model_selector_slot() -> rx.Component:
    """Placeholder slot for model selector component (STORY-016)."""
    return rx.box(
        rx.badge(
            SHELL_MODEL_SLOT_LABEL,
            variant="outline",
            color_scheme="gray",
            size="1",
        ),
        id="model-selector-slot",
    )


def header() -> rx.Component:
    """Header providing harness identity, session user_id, change-user action, and model selector slot."""
    return rx.hstack(
        rx.hstack(
            rx.icon("shield-check", size=22, color="#2563eb"),
            rx.heading(SHELL_HEADER_TITLE, size="4", weight="bold", color="#111827"),
            rx.badge(
                SHELL_HEADER_BADGE,
                variant="surface",
                color_scheme="blue",
                size="1",
            ),
            align="center",
            spacing="2",
        ),
        rx.hstack(
            model_selector_slot(),
            rx.hstack(
                rx.avatar(fallback="U", size="1", color_scheme="blue"),
                rx.text(
                    ChatState.user_id,
                    size="2",
                    weight="medium",
                    color="#374151",
                ),
                rx.button(
                    SHELL_CHANGE_USER_LABEL,
                    size="1",
                    variant="ghost",
                    color_scheme="gray",
                    on_click=ChatState.reset_user_id,
                ),
                align="center",
                spacing="2",
            ),
            align="center",
            spacing="3",
        ),
        justify="between",
        align="center",
        width="100%",
        padding="0.75rem 1.5rem",
        border_bottom="1px solid #e5e7eb",
        background_color="white",
    )


def empty_state() -> rx.Component:
    """Designed empty state shown when a conversation has no messages."""
    return rx.center(
        rx.vstack(
            rx.center(
                rx.icon("shield-check", size=36, color="#2563eb"),
                width="64px",
                height="64px",
                border_radius="1rem",
                background_color="#eff6ff",
                margin_bottom="0.5rem",
            ),
            rx.heading(
                EMPTY_STATE_TITLE,
                size="6",
                weight="bold",
                color="#111827",
            ),
            rx.text(
                EMPTY_STATE_SUBTITLE,
                size="3",
                color="#6b7280",
                max_width="32rem",
                text_align="center",
            ),
            rx.hstack(
                rx.badge(
                    rx.hstack(
                        rx.icon("lock", size=14),
                        rx.text(EMPTY_STATE_PII_FEATURE),
                        align="center",
                        spacing="1",
                    ),
                    variant="soft",
                    color_scheme="purple",
                    size="2",
                ),
                rx.badge(
                    rx.hstack(
                        rx.icon("shield-alert", size=14),
                        rx.text(EMPTY_STATE_SECURITY_FEATURE),
                        align="center",
                        spacing="1",
                    ),
                    variant="soft",
                    color_scheme="red",
                    size="2",
                ),
                rx.badge(
                    rx.hstack(
                        rx.icon("clock", size=14),
                        rx.text(EMPTY_STATE_DEDUP_FEATURE),
                        align="center",
                        spacing="1",
                    ),
                    variant="soft",
                    color_scheme="amber",
                    size="2",
                ),
                spacing="2",
                justify="center",
                flex_wrap="wrap",
                margin_top="1rem",
            ),
            align="center",
            spacing="3",
            padding="2rem",
        ),
        flex="1",
        width="100%",
    )
