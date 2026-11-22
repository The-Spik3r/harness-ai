"""The Providers view: one circuit breaker per upstream provider and the fallback counters.

PRD-022 STORY-016 (F9). The operator's question is "which provider is down and
is the chain covering for it", and the page answers it in the order of the
answer: a one-line verdict in words naming any provider that is not closed, then
one block per provider, the counters, and the two keyed tables.

**What this surface refuses.** The Storage view's restraint, for the same
reason: no meters, bars, sparklines, charts or accent colours, no polling. A
breaker state is a word ("closed", "open", "half_open"); a coloured dot beside
it would repeat the word in a less precise form. The existing Refresh is the
only control that reaches it.

**Access.** The console has no per-permission switch: this view sits behind the
same admin-token gate as Storage and is filled by the same `authenticated`
early return in `AdminState.load()`. No role check is added for it.

**This module reads fields; it does not compute.** Every value is a string built
by `admin_formatting.to_providers_view` from `health.providers_status()`, which
reads memory only, so the page answers during a database outage. Only a failure
kind or a skip reason is ever shown, never message text (PRD-022 T10).

**Its fault is its own.** The read fails under its own label into
`AdminState.providers_error`, rendered here with `admin_shell.fault_panel`.

The helpers are re-declared rather than imported from other views: the views do
not reach into each other (`summary.py:_empty_summary` records the rule). This
module imports `admin_copy`, `theme`, `AdminState` and the shell's stamp and
fault panel, and nothing else.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import AdminState
from chat_ui.components.admin_shell import fault_panel, refreshed_stamp

# Label over value pairs: a label track, then the value in the data face.
_FACT_GRID = "minmax(10rem, 16rem) 1fr"
# Provider, kind or reason, count.
_KEYED_GRID = "minmax(10rem, 18rem) 12rem 6rem"


def _heading(label) -> rx.Component:
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_MICRO,
        font_weight="600",
        letter_spacing="0.1em",
        text_transform="uppercase",
        color=theme.MUTE,
        padding_bottom="0.4rem",
        border_bottom=f"1px solid {theme.RULE}",
        custom_attrs={"role": "heading", "aria-level": "2"},
    )


def _fact(fact) -> rx.Component:
    return rx.box(
        rx.box(
            fact.label,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            color=theme.MUTE,
        ),
        rx.box(
            fact.value,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_DATA,
            color=theme.INK,
            overflow_wrap="anywhere",
        ),
        display="grid",
        grid_template_columns=_FACT_GRID,
        column_gap="0.75rem",
        align_items="baseline",
        min_height=theme.ROW_H,
        border_bottom=f"1px solid {theme.RULE_SOFT}",
    )


def _facts(heading, facts) -> rx.Component:
    return rx.box(
        _heading(heading),
        rx.foreach(facts, _fact),
        width="100%",
        max_width="40rem",
    )


def _card(card) -> rx.Component:
    """One provider: its name as the heading over its breaker facts."""
    return _facts(card.name, card.facts)


def _keyed_cell(value, align: str = "left") -> rx.Component:
    return rx.box(
        value,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.INK,
        text_align=align,
        overflow="hidden",
        text_overflow="ellipsis",
        white_space="nowrap",
    )


def _keyed_row(row) -> rx.Component:
    return rx.box(
        _keyed_cell(row.provider),
        _keyed_cell(row.reason),
        _keyed_cell(row.count, align="right"),
        display="grid",
        grid_template_columns=_KEYED_GRID,
        column_gap="0.75rem",
        align_items="center",
        min_height=theme.ROW_H,
        border_bottom=f"1px solid {theme.RULE_SOFT}",
    )


def _head_cell(label: str, align: str = "left") -> rx.Component:
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_MICRO,
        font_weight="600",
        letter_spacing="0.1em",
        text_transform="uppercase",
        text_align=align,
        color=theme.MUTE,
    )


def _keyed_head() -> rx.Component:
    return rx.box(
        _head_cell(admin_copy.PROVIDERS_COLUMN_PROVIDER),
        _head_cell(admin_copy.PROVIDERS_COLUMN_REASON),
        _head_cell(admin_copy.PROVIDERS_COLUMN_COUNT, align="right"),
        display="grid",
        grid_template_columns=_KEYED_GRID,
        column_gap="0.75rem",
        height="2rem",
        align_items="center",
        border_bottom=f"1px solid {theme.RULE}",
    )


def _keyed_table(heading: str, title: str, rows) -> rx.Component:
    """One keyed counter map as provider / kind / count rows. An empty map is an
    empty table under its heading, the head row saying what it would hold."""
    return rx.box(
        _heading(heading),
        rx.box(
            _keyed_head(),
            rx.foreach(rows, _keyed_row),
            width="fit-content",
            min_width="30rem",
            custom_attrs={"role": "table", "aria-label": title},
        ),
        overflow_x="auto",
        width="100%",
    )


def _verdict() -> rx.Component:
    """The one-line verdict, in words, naming any provider that is not closed."""
    return rx.box(
        AdminState.providers_verdict,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_LEAD,
        font_weight="600",
        letter_spacing="-0.01em",
        color=theme.INK,
    )


def _caption() -> rx.Component:
    """Which process this describes, over the refreshed stamp (counters are per
    process, so the instance belongs beside the time they were read)."""
    return rx.vstack(
        rx.box(
            AdminState.providers_caption,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            color=theme.MUTE,
        ),
        refreshed_stamp(),
        spacing="1",
        align="start",
        padding="0.75rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        flex_shrink="0",
        width="100%",
    )


def _body() -> rx.Component:
    return rx.vstack(
        _verdict(),
        rx.foreach(AdminState.providers_cards, _card),
        _facts(admin_copy.PROVIDERS_HEADING_COUNTERS, AdminState.providers_counters),
        _keyed_table(
            admin_copy.PROVIDERS_HEADING_FAILED,
            admin_copy.PROVIDERS_FAILED_TITLE,
            AdminState.providers_failed,
        ),
        _keyed_table(
            admin_copy.PROVIDERS_HEADING_SKIPPED,
            admin_copy.PROVIDERS_SKIPPED_TITLE,
            AdminState.providers_skipped,
        ),
        spacing="6",
        align="start",
        width="100%",
        padding="1.5rem 1.5rem 2rem 0",
    )


def providers() -> rx.Component:
    """The Providers view: its own fault panel, the caption, then the scrolling
    body. `min_height="0"` makes the body scroll rather than the page."""
    return rx.vstack(
        fault_panel(AdminState.providers_error),
        _caption(),
        rx.box(
            _body(),
            class_name="hx-scroll",
            overflow_y="auto",
            overflow_x="auto",
            flex="1",
            min_height="0",
            width="100%",
            padding_left="1.5rem",
        ),
        spacing="0",
        flex="1",
        min_height="0",
        width="100%",
    )
