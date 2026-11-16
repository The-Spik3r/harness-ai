"""The Actions view: what agents tried to do, and what the action policy decided.

PRD-016 STORY-019 (F11). One table of the newest decisions, denied first by
default, under a scope line that states the window against the true total, with
a single-select filter (Denied, Flagged, Allowed, All). The operator's question
is "what was stopped, and by which rule", and the table answers it with a tag
and a rule id in a column.

**What this surface refuses.** No chart, no per-day history, no per-row action,
no export, and no second stamp margin: the frontend-design skill, verbatim,
*"Structure is information. Structural devices, numbering, eyebrows, dividers,
labels, should encode something true about the content, not decorate it."* The
Register's stamp margin stays the console's one signature, and the decision
tag already carries the fact on each row. The one structural statement is the
default: the view opens on Denied.

**The filter re-reads the database.** The Register narrows rows it already
holds; this view cannot, because a 500-row window over every decision would
drop old denies behind newer allows, which is the row it exists to find. A chip
writes `AdminState.choose_actions_filter`, which returns the `load_actions`
read for that decision (see the `action_rows` declaration in `admin_state.py`).

**Full text is a `title`.** Target, rule and tool truncate with an ellipsis so
every row keeps one height; the full text is the cell's `title`, and the rule
cell's title is the reason the engine recorded. That is a hover device: a touch
screen has no hover, a known limit (no per-row disclosure is built here).

**An empty view is a sentence, not a grid.** It says what the view lists, why it
is empty (nothing calls the policy engine until PRD-017) and the action,
Refresh, and its title names the filter that is empty.

**This module reads fields; it does not compute.** Every cell is an `ActionRow`
string built by `admin_formatting.to_action_rows`; the state is chosen upstream
by `AdminState.actions_state`, a Python var a unit test can call. Its fault is
its own (`actions_error`), rendered here with `admin_shell.fault_panel`.

**Type and rules are the register's.** The helpers are re-declared rather than
imported from `register.py`: the views do not reach into each other
(`summary.py:_empty_summary` records the rule). Only ground tokens and the
register's three verdict inks are used: `INK_DENIED` for deny, `INK_HELD` for
flag, `INK_CLEAR` for allow.

Nothing here reaches the chat: this module imports `admin_copy`, `theme`,
`AdminState` and the shell's stamp and fault panel, and nothing else.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import (
    ACTIONS_FILTER_ALL,
    ACTIONS_FILTER_ALLOW,
    ACTIONS_FILTER_DENY,
    ACTIONS_FILTER_FLAG,
    ACTIONS_STATE_EMPTY,
    ACTIONS_STATE_FAULT,
    ACTIONS_STATE_ROWS,
    AdminState,
)
from chat_ui.admin_formatting import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_FLAG,
    VALUE_ABSENT,
)
from chat_ui.components.admin_shell import fault_panel, refreshed_stamp

# The nine columns, in the story's order: Time, User, Role, Tool, Operation,
# Target, Rule, Decision, Allowed by. One constant for the head and every row, so
# the columns align by construction (the `register.py:_GRID` rule).
#
# Target is the one flexible track (`1fr`): it is the long, truncating text, and
# the table takes the width of its container so the rules end at the edge. Every
# other track is bounded, so a wide screen stretches Target and not the gap
# between a user and their role (the Usage view's measured failure).
_GRID = (
    "8.5rem minmax(6rem, 10rem) 5rem 7.5rem 5.5rem minmax(12rem, 1fr) "
    "minmax(9rem, 14rem) 5.5rem minmax(8rem, 12rem)"
)

# The tracks at their minimum (8.5 + 6 + 5 + 7.5 + 5.5 + 12 + 9 + 5.5 + 8 =
# 67rem) plus eight 0.75rem column gaps (6rem). Below this the columns would
# crush, so the table scrolls sideways inside its own container instead and the
# page does not.
_MIN_WIDTH = "73rem"

# Each filter as (key, word on screen, ink). The key is the state's, the word is
# `admin_copy`'s, the separation `register.py:_VERDICT_CHIPS` keeps. The inks are
# the verdict inks of the same outcomes; "All" is no outcome, so it takes the
# plain ink.
_FILTER_CHIPS = (
    (ACTIONS_FILTER_DENY, admin_copy.ACTIONS_FILTER_DENIED_LABEL, theme.INK_DENIED),
    (ACTIONS_FILTER_FLAG, admin_copy.ACTIONS_FILTER_FLAGGED_LABEL, theme.INK_HELD),
    (ACTIONS_FILTER_ALLOW, admin_copy.ACTIONS_FILTER_ALLOWED_LABEL, theme.INK_CLEAR),
    (ACTIONS_FILTER_ALL, admin_copy.ACTIONS_FILTER_ALL_LABEL, theme.INK),
)


def _head_cell(label: str, title: str = "") -> rx.Component:
    """One column head, in the register's treatment: a signpost over data.

    `title` carries what a one-word head cannot, once, on hover, instead of on
    every row.
    """
    attrs = {"role": "columnheader"}
    if title:
        attrs["title"] = title
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_MICRO,
        font_weight="600",
        letter_spacing="0.1em",
        text_transform="uppercase",
        color=theme.MUTE,
        custom_attrs=attrs,
    )


def _cell(value, title=None) -> rx.Component:
    """One cell, in the data face. Truncates rather than wrapping, so every row
    keeps one height; `title`, a Var of the row, is the full text on hover."""
    attrs = {"role": "cell"}
    if title is not None:
        attrs["title"] = title
    return rx.box(
        value,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.INK,
        overflow="hidden",
        text_overflow="ellipsis",
        white_space="nowrap",
        custom_attrs=attrs,
    )


def _tag(label: str, ink: str, exception: bool = True) -> rx.Component:
    """One decision tag. Exceptions are set in caps; allowed stays lowercase,
    the `register.py:_tag` treatment, so a tag reads as its chip."""
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_TAG,
        font_weight="600" if exception else "500",
        letter_spacing="0.08em" if exception else "0",
        text_transform="uppercase" if exception else "none",
        color=ink,
        custom_attrs={"role": "cell"},
    )


def _decision_cell(row) -> rx.Component:
    """The decision as a word in its ink. `ActionRow.decision` defaults to ""
    rather than to allow, so the default arm shows the absent mark and never
    claims the call was allowed."""
    return rx.match(
        row.decision,
        (DECISION_DENY, _tag(admin_copy.DECISION_DENY_LABEL, theme.INK_DENIED)),
        (DECISION_FLAG, _tag(admin_copy.DECISION_FLAG_LABEL, theme.INK_HELD)),
        (
            DECISION_ALLOW,
            _tag(admin_copy.DECISION_ALLOW_LABEL, theme.INK_CLEAR, exception=False),
        ),
        _tag(VALUE_ABSENT, theme.MUTE, exception=False),
    )


def _column_head() -> rx.Component:
    """The nine heads, sticky inside the scroll container (the register's
    reason: one scrollbar governs head and rows, so they cannot drift apart)."""
    return rx.box(
        _head_cell(admin_copy.COLUMN_TIME),
        _head_cell(admin_copy.COLUMN_USER),
        _head_cell(admin_copy.COLUMN_ROLE),
        _head_cell(admin_copy.COLUMN_TOOL),
        _head_cell(
            admin_copy.COLUMN_OPERATION, title=admin_copy.COLUMN_OPERATION_TITLE
        ),
        _head_cell(admin_copy.COLUMN_TARGET),
        _head_cell(admin_copy.COLUMN_RULE, title=admin_copy.COLUMN_RULE_TITLE),
        _head_cell(admin_copy.COLUMN_DECISION),
        _head_cell(
            admin_copy.COLUMN_ALLOWED_BY, title=admin_copy.COLUMN_ALLOWED_BY_TITLE
        ),
        display="grid",
        grid_template_columns=_GRID,
        align_items="center",
        column_gap="0.75rem",
        height="2rem",
        padding_right="1.5rem",
        position="sticky",
        top="0",
        z_index="1",
        background_color=theme.PAPER,
        border_bottom=f"1px solid {theme.RULE}",
        custom_attrs={"role": "row"},
    )


def _row(row) -> rx.Component:
    """One decision. No hover tint and no click: the row offers no action, and a
    hover state would promise one."""
    return rx.box(
        _cell(row.timestamp_relative, title=row.timestamp_absolute),
        _cell(row.user_id, title=row.user_id),
        _cell(row.role),
        _cell(row.tool_name, title=row.tool_name),
        _cell(row.operation_kind),
        _cell(row.target, title=row.target),
        _cell(row.rule, title=row.reason),
        _decision_cell(row),
        _cell(row.allowed_by, title=row.allowed_by),
        display="grid",
        grid_template_columns=_GRID,
        align_items="center",
        column_gap="0.75rem",
        min_height=theme.ROW_H,
        padding_right="1.5rem",
        border_bottom=f"1px solid {theme.RULE_SOFT}",
        custom_attrs={"role": "row"},
    )


def _table() -> rx.Component:
    """The heads over the rows. Also the fault arm: the last good rows stay
    standing under the panel that names the failed read, the register's rule."""
    return rx.box(
        _column_head(),
        rx.foreach(AdminState.action_rows, _row),
        width="100%",
        min_width=_MIN_WIDTH,
        custom_attrs={
            "role": "table",
            "aria-label": admin_copy.VIEW_ACTIONS_LABEL,
        },
    )


def _empty_actions() -> rx.Component:
    """Nothing recorded for this filter: a sentence, not an empty grid.

    The title names the filter; the body says what the view lists, why it is
    empty (PRD-017) and the action, Refresh, the masthead's control. No card, no
    illustration, no centring -- the register's empty panel, re-declared.
    """
    return rx.box(
        rx.box(
            AdminState.actions_empty_title,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            letter_spacing="-0.01em",
            color=theme.INK,
        ),
        rx.box(
            admin_copy.EMPTY_ACTIONS_BODY,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_BODY,
            line_height="1.6",
            color=theme.MUTE,
            max_width=theme.MEASURE,
            margin_top="0.5rem",
        ),
        padding="3rem 0 2rem",
        width="100%",
    )


def _actions_body() -> rx.Component:
    """The three states, chosen by `AdminState.actions_state`. The default arm is
    the table: an unrecognised state renders the record, never a claim that
    nothing was recorded."""
    return rx.match(
        AdminState.actions_state,
        (ACTIONS_STATE_EMPTY, _empty_actions()),
        (ACTIONS_STATE_FAULT, _table()),
        (ACTIONS_STATE_ROWS, _table()),
        _table(),
    )


def _control_label(label: str) -> rx.Component:
    """The eyebrow over the filter chips (`register.py:_control_label`)."""
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_MICRO,
        font_weight="600",
        letter_spacing="0.1em",
        text_transform="uppercase",
        color=theme.MUTE,
        flex_shrink="0",
    )


def _chip_button(key: str, label: str, ink: str, selected: bool) -> rx.Component:
    """One filter in its selected or unselected state.

    A real `<button type="button">`, which is the whole keyboard answer: it takes
    focus in order, fires on Enter and Space, and takes its ring from
    `theme.GLOBAL_CSS`'s `:focus-visible`. No local `outline` may take that back.
    Selection is marked without a fill: the ink replaces the mute, the weight
    steps up and a 2px rule in the ink seats under the word; `aria-pressed` is
    the channel for a reader that sees no colour (`register.py:_chip_button`).
    """
    exception = key != ACTIONS_FILTER_ALL
    return rx.el.button(
        label,
        on_click=AdminState.choose_actions_filter(key),
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        line_height="1.4",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_TAG,
        color=ink if selected else theme.MUTE,
        font_weight="600" if selected else "500",
        letter_spacing="0.08em" if exception else "0",
        text_transform="uppercase" if exception else "none",
        border_bottom=f"2px solid {ink}" if selected else "2px solid transparent",
        padding_bottom="2px",
        _hover={} if selected else {"color": theme.INK},
        custom_attrs={"aria-pressed": "true" if selected else "false"},
    )


def _filter_strip() -> rx.Component:
    """The single-select filter. Both states of every chip are built because the
    selected test is a Var; the group is named for a screen reader."""
    return rx.flex(
        _control_label(admin_copy.ACTIONS_FILTER_LABEL),
        *[
            rx.cond(
                AdminState.actions_selected == key,
                _chip_button(key, label, ink, True),
                _chip_button(key, label, ink, False),
            )
            for key, label, ink in _FILTER_CHIPS
        ],
        align="center",
        gap="0.75rem",
        wrap="wrap",
        padding="0.5rem 1.5rem",
        flex_shrink="0",
        width="100%",
        border_bottom=f"1px solid {theme.RULE_SOFT}",
        custom_attrs={
            "role": "group",
            "aria-label": admin_copy.ACTIONS_FILTER_LABEL,
        },
    )


def _caption() -> rx.Component:
    """The window, then when it was read. `FONT_BODY` because it states a scope,
    the one job PRD-006 Section 6.1 gives the reading face on this console."""
    return rx.vstack(
        rx.box(
            AdminState.actions_scope,
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


def actions() -> rx.Component:
    """The Actions view: its own fault panel, the scope line, the filter, then the
    scrolling table. `min_height="0"` on the column and the scroll container
    makes the table scroll rather than the page, the `register()` requirement."""
    return rx.vstack(
        fault_panel(AdminState.actions_error),
        _caption(),
        _filter_strip(),
        rx.box(
            _actions_body(),
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
