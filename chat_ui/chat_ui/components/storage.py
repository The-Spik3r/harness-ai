"""The Storage view: the storage circuit breaker, the audit journal and the counters.

PRD-018 STORY-012 (F8, Section 10). The operator's question is "am I looking at
a blip, an outage or a backlog", and the page answers it in the order of the
answer: a one-line verdict in words, then the breaker, the journal, the
counters and the two retry tables.

**What this surface refuses.** The Usage view's restraint, for the same reason:
no meters, bars, sparklines, charts or accent colours, no polling. *"Structure
is information"* (frontend-design): a bar beside "3 of 67,108,864 bytes" would
repeat the number in a less precise form, and a red verdict would spend the
console's verdict ink on something this page states in words. The existing
Refresh is the only control that reaches it.

**This module reads fields; it does not compute.** Every value is a string built
by `admin_formatting.to_storage_view` from `storage_status()`, which reads
memory only (no driver call), so the page answers during an outage.

**Its fault is its own.** The read fails under its own label into
`AdminState.storage_error`, rendered here with `admin_shell.fault_panel`.

The helpers are re-declared rather than imported from other views: the views do
not reach into each other (`summary.py:_empty_summary` records the rule). Nothing
here reaches the chat: this module imports `admin_copy`, `theme`, `AdminState`
and the shell's stamp and fault panel, and nothing else.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import AdminState
from chat_ui.components.admin_shell import fault_panel, refreshed_stamp

# Label over value pairs: a label track, then the value in the data face.
_FACT_GRID = "minmax(10rem, 16rem) 1fr"
# Operation, class, count.
_KEYED_GRID = "minmax(10rem, 18rem) 12rem 6rem"


def _heading(label: str) -> rx.Component:
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


def _facts(heading: str, facts) -> rx.Component:
    return rx.box(
        _heading(heading),
        rx.foreach(facts, _fact),
        width="100%",
        max_width="40rem",
    )


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
        _keyed_cell(row.operation),
        _keyed_cell(row.failure_class),
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
        _head_cell(admin_copy.STORAGE_COLUMN_OPERATION),
        _head_cell(admin_copy.STORAGE_COLUMN_FAILURE_CLASS),
        _head_cell(admin_copy.STORAGE_COLUMN_COUNT, align="right"),
        display="grid",
        grid_template_columns=_KEYED_GRID,
        column_gap="0.75rem",
        height="2rem",
        align_items="center",
        border_bottom=f"1px solid {theme.RULE}",
    )


def _keyed_table(heading: str, title: str, rows) -> rx.Component:
    """One keyed counter map as operation / class / count rows. An empty map is
    an empty table under its heading, the head row saying what it would hold."""
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
    """The one-line verdict, in words, over the held-back sentence when present."""
    return rx.vstack(
        rx.box(
            AdminState.storage_verdict,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            letter_spacing="-0.01em",
            color=theme.INK,
        ),
        rx.cond(
            AdminState.storage_notice != "",
            rx.box(
                AdminState.storage_notice,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_BODY,
                line_height="1.6",
                color=theme.INK,
                max_width=theme.MEASURE,
            ),
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def _caption() -> rx.Component:
    """Which process this describes, over the refreshed stamp (counters are per
    process, so the instance belongs beside the time they were read)."""
    return rx.vstack(
        rx.box(
            AdminState.storage_caption,
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
        _facts(admin_copy.STORAGE_HEADING_BREAKER, AdminState.storage_breaker),
        _facts(admin_copy.STORAGE_HEADING_JOURNAL, AdminState.storage_journal),
        _facts(admin_copy.STORAGE_HEADING_COUNTERS, AdminState.storage_counters),
        _keyed_table(
            admin_copy.STORAGE_HEADING_RETRIES,
            admin_copy.STORAGE_RETRIES_TITLE,
            AdminState.storage_retries,
        ),
        _keyed_table(
            admin_copy.STORAGE_HEADING_EXHAUSTED,
            admin_copy.STORAGE_EXHAUSTED_TITLE,
            AdminState.storage_exhausted,
        ),
        spacing="6",
        align="start",
        width="100%",
        padding="1.5rem 1.5rem 2rem 0",
    )


def storage() -> rx.Component:
    """The Storage view: its own fault panel, the caption, then the scrolling
    body. `min_height="0"` makes the body scroll rather than the page."""
    return rx.vstack(
        fault_panel(AdminState.storage_error),
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
