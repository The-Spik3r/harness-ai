import reflex as rx
from chat_ui.chat_ui import copy


def render_user(message) -> rx.Component:
    """Renders user message bubble (right-aligned, blue)."""
    return rx.hstack(
        rx.box(
            message.content,
            background_color="#2563eb",
            color="white",
            padding="0.65rem 1rem",
            border_radius="1rem",
            max_width="70%",
        ),
        rx.avatar(fallback="U", size="2", color_scheme="blue"),
        justify="end",
        width="100%",
    )


def render_assistant(message) -> rx.Component:
    """Renders successful assistant message bubble (left-aligned, gray), with optional PII badge."""
    count = message.pii_entities.length()
    entities_str = message.pii_entities.join(", ")
    badge_text = rx.cond(
        count == 1,
        copy.PII_BADGE_SINGLE_TEMPLATE.format(entities=entities_str),
        copy.PII_BADGE_TEMPLATE.format(count=count, entities=entities_str),
    )
    pii_badge = rx.cond(
        message.pii_redacted,
        rx.box(
            badge_text,
            font_size="0.75rem",
            color="#4b5563",
            background_color="#e5e7eb",
            padding="0.2rem 0.5rem",
            border_radius="0.375rem",
            margin_top="0.5rem",
        ),
        rx.fragment(),
    )
    return rx.hstack(
        rx.avatar(fallback="AI", size="2", color_scheme="gray"),
        rx.box(
            rx.vstack(
                message.content,
                pii_badge,
                align_items="start",
                spacing="1",
            ),
            background_color="#f3f4f6",
            color="#111827",
            padding="0.65rem 1rem",
            border_radius="1rem",
            max_width="70%",
        ),
        justify="start",
        width="100%",
    )


def render_duplicate(message) -> rx.Component:
    """Renders duplicate block card with benign-nudge styling."""
    return rx.center(
        rx.box(
            rx.vstack(
                rx.text(message.content, weight="medium"),
                rx.cond(
                    message.first_query_at != "",
                    rx.text(f"First sent at: {message.first_query_at}", font_size="0.75rem", color="#78350f"),
                    rx.text("Already submitted recently.", font_size="0.75rem", color="#78350f"),
                ),
                align_items="start",
                spacing="1",
            ),
            background_color="#fef9c3",
            color="#713f12",
            border="1px solid #fde047",
            padding="0.75rem 1rem",
            border_radius="0.75rem",
            max_width="80%",
            font_size="0.875rem",
        ),
        width="100%",
    )


def render_injection(message) -> rx.Component:
    """Renders security event card for prompt injection, displaying matched pattern."""
    return rx.center(
        rx.box(
            rx.vstack(
                rx.text(message.content, weight="bold"),
                rx.cond(
                    message.pattern != "",
                    rx.text(f"Matched pattern: {message.pattern}", font_size="0.75rem", color="#991b1b"),
                    rx.text("Prompt injection detected.", font_size="0.75rem", color="#991b1b"),
                ),
                align_items="start",
                spacing="1",
            ),
            background_color="#fee2e2",
            color="#7f1d1d",
            border="1px solid #fca5a5",
            padding="0.75rem 1rem",
            border_radius="0.75rem",
            max_width="80%",
            font_size="0.875rem",
        ),
        width="100%",
    )


def render_upstream_error(message) -> rx.Component:
    """Renders upstream error card explicitly naming OpenRouter."""
    error_text = rx.cond(
        message.detail != "",
        rx.text(f"{copy.UPSTREAM_ERROR_PREFIX}: {message.detail}", font_size="0.75rem", color="#9a3412"),
        rx.text(copy.UPSTREAM_ERROR_PREFIX, font_size="0.75rem", color="#9a3412"),
    )
    return rx.center(
        rx.box(
            rx.vstack(
                rx.text(message.content, weight="medium"),
                error_text,
                align_items="start",
                spacing="1",
            ),
            background_color="#ffedd5",
            color="#7c2d12",
            border="1px solid #fdba74",
            padding="0.75rem 1rem",
            border_radius="0.75rem",
            max_width="80%",
            font_size="0.875rem",
        ),
        width="100%",
    )


def render_internal_error(message) -> rx.Component:
    """Renders internal error card showing detail."""
    error_text = rx.cond(
        message.detail != "",
        rx.text(f"{copy.INTERNAL_ERROR_PREFIX}: {message.detail}", font_size="0.75rem", color="#831843"),
        rx.text(copy.INTERNAL_ERROR_PREFIX, font_size="0.75rem", color="#831843"),
    )
    return rx.center(
        rx.box(
            rx.vstack(
                rx.text(message.content, weight="medium"),
                error_text,
                align_items="start",
                spacing="1",
            ),
            background_color="#fce7f3",
            color="#831843",
            border="1px solid #fbcfe8",
            padding="0.75rem 1rem",
            border_radius="0.75rem",
            max_width="80%",
            font_size="0.875rem",
        ),
        width="100%",
    )


def render_fallback(message) -> rx.Component:
    """Fallback renderer for unknown kinds, ensuring visible bubble rather than nothing."""
    return rx.center(
        rx.box(
            message.content,
            background_color="#f3f4f6",
            color="#374151",
            padding="0.5rem 1rem",
            border_radius="0.75rem",
            max_width="80%",
            font_size="0.875rem",
        ),
        width="100%",
    )
