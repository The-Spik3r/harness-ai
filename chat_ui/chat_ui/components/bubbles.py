"""The six ledger entries, one per pipeline outcome.

Design direction (see theme.py): the transcript is an inspection ledger, not a
stream of chat bubbles. Every entry is full width and clamps onto a single
vertical rail; a square glyph and a monospace verdict tag carry the outcome.
Reading the rail top to bottom is the session's compliance history — which is
the one thing PRD-004 exists to make visible.

Everything a renderer needs is precomputed on the ChatMessage in the backend:
`message` is a Reflex Var here (a JS reference), so Python control flow and
datetime maths cannot run at render time.
"""

import reflex as rx

from chat_ui import copy, theme
from chat_ui.state import ChatState


def _glyph(ink: str, filled: bool = True, pulse: bool = False) -> rx.Component:
    """The rail marker. A stamped square is a verdict the harness reached; a
    tally bar is an entry you made — you are the record's subject, not its
    finding."""
    return rx.box(
        class_name="hx-pulse" if pulse else "",
        width=theme.GLYPH,
        height=theme.GLYPH if filled else "3px",
        flex_shrink="0",
        margin_top="0.45rem" if filled else "0.7rem",
        border_radius="1px",
        background_color=ink,
    )


def _rail(ink: str, filled: bool = True, pulse: bool = False) -> rx.Component:
    """One entry's slice of the rail: its glyph, then the spine running down to
    the next entry. Consecutive slices join into a continuous line."""
    return rx.box(
        _glyph(ink, filled=filled, pulse=pulse),
        rx.box(width="1px", flex="1", background_color=theme.SPINE),
        display="flex",
        flex_direction="column",
        align_items="center",
        width=theme.RAIL_X,
        flex_shrink="0",
    )


def _tag(label, ink: str) -> rx.Component:
    return rx.box(
        label,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_TAG,
        font_weight="500",
        letter_spacing="0.13em",
        color=ink,
        margin_bottom="0.35rem",
    )


def _prose(content, lead: bool = False) -> rx.Component:
    return rx.box(
        content,
        font_family=theme.FONT_BODY,
        font_size=theme.TEXT_LEAD if lead else theme.TEXT_BODY,
        line_height="1.6",
        color=theme.INK,
        white_space="pre-wrap",
        overflow_wrap="anywhere",
        max_width=theme.MEASURE,
    )


def _evidence(*children, color: str = theme.MUTE, **props) -> rx.Component:
    """A line of machine fact — an id, a count, a matched pattern. Always set in
    the data face so it never reads as prose."""
    return rx.box(
        *children,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=color,
        overflow_wrap="anywhere",
        **props,
    )


def _action(label: str, on_click, ink: str) -> rx.Component:
    """Every dead end offers the next move. Styled as a rule-bounded control so
    it reads as part of the ledger rather than a product button."""
    # A real <button>: role="button" on a div takes focus but never fires on
    # Enter or Space, so the recovery action would be mouse-only.
    return rx.el.button(
        label,
        on_click=on_click,
        type="button",
        cursor="pointer",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_DATA,
        font_weight="600",
        color=ink,
        background_color=theme.CARD,
        border=f"1px solid {ink}",
        border_radius=theme.RADIUS,
        padding="0.3rem 0.7rem",
        margin_top="0.7rem",
        display="inline-block",
        transition="background-color 120ms ease, border-color 120ms ease",
        _hover={"background_color": f"{ink}14"},
    )


def _entry(rail: rx.Component, *content, **props) -> rx.Component:
    """Shared geometry for every kind: rail cell, then the content column."""
    return rx.box(
        rail,
        rx.box(
            *content,
            flex="1",
            min_width="0",
            padding_bottom="1.5rem",
            **props,
        ),
        class_name="hx-entry",
        display="flex",
        align_items="stretch",
        width="100%",
    )


def _panel(ink: str, tint: str, *children) -> rx.Component:
    """The tinted slab used by the four non-conversational outcomes. The rail
    already carries the signal, so the fill stays at a whisper."""
    return rx.box(
        *children,
        background_color=tint,
        border=f"1px solid {ink}26",
        border_left=f"2px solid {ink}",
        border_radius=theme.RADIUS,
        padding="0.75rem 0.9rem",
        max_width=theme.PANEL_MAX,
    )


# --- The six kinds -------------------------------------------------------


def render_user(message) -> rx.Component:
    """Your own words. No verdict, no panel — you are the record's subject."""
    return _entry(
        _rail(theme.MUTE, filled=False),
        _tag(copy.TAG_USER, theme.MUTE),
        _prose(message.content, lead=True),
    )


def render_assistant(message) -> rx.Component:
    """A cleared exchange: the answer, what was masked, and what it cost."""
    entities = message.pii_entities.join(", ")
    badge_text = rx.cond(
        message.pii_entities.length() == 1,
        copy.PII_BADGE_SINGLE_TEMPLATE.format(entities=entities),
        copy.PII_BADGE_TEMPLATE.format(
            count=message.pii_entities.length(), entities=entities
        ),
    )

    pii_badge = rx.cond(
        message.pii_redacted,
        _evidence(
            badge_text,
            color=theme.INK_CLEAR,
            display="inline-block",
            margin_top="0.7rem",
            padding="0.2rem 0.5rem",
            background_color=theme.TINT_CLEAR,
            border=f"1px solid {theme.INK_CLEAR}26",
            border_radius=theme.RADIUS,
        ),
        rx.fragment(),
    )

    footer = rx.cond(
        message.model_used != "",
        _evidence(
            message.model_used,
            copy.FOOTER_SEPARATOR,
            message.tokens_used,
            " ",
            copy.FOOTER_TOKENS_LABEL,
            copy.FOOTER_SEPARATOR,
            copy.FOOTER_AUDIT_PREFIX,
            message.audit_id,
            margin_top="0.7rem",
            padding_top="0.5rem",
            border_top=f"1px solid {theme.RULE}",
            max_width=theme.MEASURE,
        ),
        rx.fragment(),
    )

    return _entry(
        _rail(theme.INK_CLEAR),
        _tag(copy.TAG_ASSISTANT, theme.INK_CLEAR),
        _prose(message.content),
        pii_badge,
        footer,
    )


def render_duplicate(message) -> rx.Component:
    """Held, not rejected. The relative-time and window lines are precomputed
    by formatting.format_duplicate_info."""
    ink, tint = theme.INK_HELD, theme.TINT_HELD
    return _entry(
        _rail(ink),
        _tag(copy.TAG_DUPLICATE, ink),
        _panel(
            ink,
            tint,
            _prose(message.content),
            rx.cond(
                message.duplicate_relative_info != "",
                _evidence(
                    message.duplicate_relative_info, color=ink, margin_top="0.5rem"
                ),
                _evidence(
                    copy.DUPLICATE_FALLBACK_TEXT, color=ink, margin_top="0.5rem"
                ),
            ),
            rx.cond(
                message.duplicate_release_info != "",
                _evidence(message.duplicate_release_info, color=ink),
                rx.fragment(),
            ),
            rx.box(
                copy.DUPLICATE_CHANGE_NOTICE,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_DATA,
                color=ink,
                margin_top="0.5rem",
            ),
            _action(
                copy.EDIT_AND_RESEND_LABEL,
                ChatState.edit_and_resend(message.prompt),
                ink,
            ),
        ),
    )


def render_injection(message) -> rx.Component:
    """Denied and logged. The matched pattern is shown as evidence, in the data
    face, because it is a rule the harness matched and not a sentence."""
    ink, tint = theme.INK_DENIED, theme.TINT_DENIED
    return _entry(
        _rail(ink),
        _tag(copy.TAG_INJECTION, ink),
        _panel(
            ink,
            tint,
            _prose(message.content),
            rx.cond(
                message.pattern != "",
                _evidence(
                    f"{copy.INJECTION_PATTERN_LABEL}: ",
                    rx.el.span(
                        message.pattern,
                        background_color=f"{ink}1A",
                        padding="0.05rem 0.3rem",
                        border_radius="2px",
                    ),
                    color=ink,
                    margin_top="0.5rem",
                ),
                _evidence(copy.INJECTION_NO_PATTERN, color=ink, margin_top="0.5rem"),
            ),
        ),
    )


def _failure(message, ink: str, tint: str, tag: str, headline: str) -> rx.Component:
    """Shared shape for the two failure kinds: what failed, the raw detail, and
    a way to send the same prompt again."""
    return _entry(
        _rail(ink),
        _tag(tag, ink),
        _panel(
            ink,
            tint,
            _prose(headline),
            rx.cond(
                message.detail != "",
                _evidence(
                    f"{copy.DETAIL_LABEL}: ",
                    message.detail,
                    color=ink,
                    margin_top="0.5rem",
                ),
                rx.fragment(),
            ),
            _action(copy.RETRY_LABEL, ChatState.retry_message(message.prompt), ink),
        ),
    )


def render_upstream_error(message) -> rx.Component:
    """Risk 7: names OpenRouter, so an unreachable model does not read as the
    harness being broken."""
    return _failure(
        message,
        theme.INK_UPSTREAM,
        theme.TINT_UPSTREAM,
        copy.TAG_UPSTREAM,
        copy.UPSTREAM_ERROR_HEADLINE,
    )


def render_internal_error(message) -> rx.Component:
    return _failure(
        message,
        theme.INK_FAULT,
        theme.TINT_FAULT,
        copy.TAG_INTERNAL,
        copy.INTERNAL_ERROR_HEADLINE,
    )


def render_fallback(message) -> rx.Component:
    """The rx.match default. An unrecognised kind still lands on the rail —
    "no silent drops" has to hold for the renderer too, not just for send()."""
    return _entry(
        _rail(theme.MUTE),
        _tag(copy.TAG_UNKNOWN, theme.MUTE),
        _prose(message.content),
    )


def render_pending_indicator() -> rx.Component:
    """In-flight entry. Occupies a real slot on the rail so the transcript does
    not jump when the answer replaces it."""
    return _entry(
        _rail(theme.MUTE, pulse=True),
        _tag(copy.PENDING_TAG, theme.MUTE),
        _evidence(copy.PENDING_INDICATOR_TEXT, class_name="hx-pulse"),
    )
