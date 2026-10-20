"""The Usage view: what each user has used today, against their budget.

PRD-013 STORY-016 (Section 6.10, F16). One table, today only, under a caption
that states the window. The operator's question is "who is near or over a
budget", and the table answers it with a number in a column and an order.

**What this surface refuses.** No meters, progress bars, sparklines, charts or
accent colours, and no history: the frontend-design skill, verbatim, *"Structure
is information. Structural devices, numbering, eyebrows, dividers, labels,
should encode something true about the content, not decorate it."* A bar beside
"104.2%" would repeat the number in a second, less precise form, and a red row
would be the console's verdict ink spent on something that is not a verdict.
The one structural statement the table makes is its order -- highest share
first -- and the Used head's title says so. PRD-013 Risk 6 fixes the scope:
there is no sort control, no date control and no per-row action. The console's
existing Refresh is the only control that reaches this view.

**The window is stated twice, once for each reader.** `USAGE_CAPTION` ("Today,
UTC") sits above the table beside the refreshed stamp, the register's scope-line
position, and it is also the table's accessible name, so the window is part of
what a screen reader announces rather than a line it may skip (PRD-006 Risk 4).

**This module reads fields; it does not compute.** Every cell is a `UsageRow`
string built by `admin_formatting.to_usage_rows`, including the budget the gate
resolves and the share. The three states are chosen upstream by
`AdminState.usage_state`, a Python var a unit test can call, for the reason
`register.py:_register_body` records.

**Its fault is its own.** The usage read fails under its own label into
`AdminState.usage_error`, so the panel naming it is rendered here, above this
table, with `admin_shell.fault_panel` -- one panel definition and one retry for
the whole console. The page frame's panel still shows a summary fault, because
`admin_page()` renders it on every view.

**Type and rules are the register's.** `TEXT_MICRO` heads in the display face,
`FONT_DATA` cells, a full rule under the head and soft hairlines between rows.
The helpers are re-declared rather than imported from `register.py`: the views
do not reach into each other (`summary.py:_empty_summary` records the rule).

Nothing here reaches the chat: this module imports `admin_copy`, `theme`,
`AdminState` and the shell's stamp and fault panel, and nothing else.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import (
    USAGE_STATE_EMPTY,
    USAGE_STATE_FAULT,
    USAGE_STATE_ROWS,
    AdminState,
)
from chat_ui.components.admin_shell import fault_panel, refreshed_stamp

# The eight columns, in PRD-013 Section 6.10's order: User, Role, Requests,
# Input, Output, Budget, Used, Denied. One constant for the head and every row,
# so the columns align by construction (the `register.py:_GRID` rule).
#
# The numeric tracks are sized to their widest expected value in the data face at
# TEXT_DATA: "999,999,999" for Input and Output, "10,000,000" and "unlimited"
# for Budget, "1,042.0%" for Used. Past that a cell truncates like any register
# cell.
#
# User is bounded (16rem) rather than `1fr`, and the table takes its content
# width (`_table`): with eight short columns, a fraction track stretched the
# table across a wide screen and set a user's role a thousand pixels from their
# name, which is the one comparison a row exists for. Measured at 1920px in the
# STORY-016 E2E pass.
_GRID = "minmax(8rem, 16rem) 6rem 6rem 7rem 7rem 7rem 5.5rem 5rem"

# The tracks' sum (8 + 6 + 6 + 7 + 7 + 7 + 5.5 + 5 = 51.5rem) plus seven
# 0.75rem column gaps (5.25rem). Below this the columns would crush, so the
# table scrolls sideways inside its own container instead.
_MIN_WIDTH = "56.75rem"


def _head_cell(label: str, align: str = "left", title: str = "") -> rx.Component:
    """One column head, in the register's treatment: a signpost over data.

    `title` carries what a one-word head cannot -- what the budget is, what
    Used counts and the order it sets -- once, on hover, instead of on every
    row (the `register.py:_head_cell` precedent).
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
        text_align=align,
        color=theme.MUTE,
        custom_attrs=attrs,
    )


def _cell(value, align: str = "left") -> rx.Component:
    """One cell, in the data face. Truncates rather than wrapping, so every row
    keeps one height and the columns stay scannable."""
    return rx.box(
        value,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.INK,
        text_align=align,
        overflow="hidden",
        text_overflow="ellipsis",
        white_space="nowrap",
        custom_attrs={"role": "cell"},
    )


def _column_head() -> rx.Component:
    """The eight heads, sticky inside the scroll container (the register's
    reason: one scrollbar governs head and rows, so they cannot drift apart).
    Numeric heads are right-aligned over right-aligned numbers."""
    return rx.box(
        _head_cell(admin_copy.COLUMN_USER),
        _head_cell(admin_copy.COLUMN_ROLE),
        _head_cell(admin_copy.COLUMN_REQUESTS, align="right"),
        _head_cell(admin_copy.COLUMN_INPUT, align="right"),
        _head_cell(admin_copy.COLUMN_OUTPUT, align="right"),
        _head_cell(
            admin_copy.COLUMN_BUDGET,
            align="right",
            title=admin_copy.COLUMN_BUDGET_TITLE,
        ),
        _head_cell(
            admin_copy.COLUMN_USED,
            align="right",
            title=admin_copy.COLUMN_USED_TITLE,
        ),
        _head_cell(
            admin_copy.COLUMN_DENIED,
            align="right",
            title=admin_copy.COLUMN_DENIED_TITLE,
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
    """One user's day. No hover tint and no click: the row offers no action
    (AC 5), and a hover state would promise one."""
    return rx.box(
        _cell(row.user_id),
        _cell(row.role),
        _cell(row.requests, align="right"),
        _cell(row.input_tokens, align="right"),
        _cell(row.output_tokens, align="right"),
        _cell(row.budget, align="right"),
        _cell(row.used, align="right"),
        _cell(row.denied, align="right"),
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
        rx.foreach(AdminState.usage_rows, _row),
        # Content width, so the rules end at the last column (see `_GRID`).
        width="fit-content",
        min_width=_MIN_WIDTH,
        custom_attrs={"role": "table", "aria-label": admin_copy.USAGE_CAPTION},
    )


def _empty_usage() -> rx.Component:
    """Nobody has sent anything today: a sentence, not an empty grid (AC 3).

    The title is the PRD's own sentence; the body says when a row appears and
    names the action, Refresh, which is the masthead's control. No card, no
    illustration, no centring -- the register's empty panel, re-declared.
    """
    return rx.box(
        rx.box(
            admin_copy.EMPTY_USAGE_TITLE,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            letter_spacing="-0.01em",
            color=theme.INK,
        ),
        rx.box(
            admin_copy.EMPTY_USAGE_BODY,
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


def _usage_body() -> rx.Component:
    """The three states, chosen by `AdminState.usage_state`. The default arm is
    the table: an unrecognised state renders the record, never a claim that
    nobody sent anything."""
    return rx.match(
        AdminState.usage_state,
        (USAGE_STATE_EMPTY, _empty_usage()),
        (USAGE_STATE_FAULT, _table()),
        (USAGE_STATE_ROWS, _table()),
        _table(),
    )


def _caption() -> rx.Component:
    """"Today, UTC" over the refreshed stamp -- the window, then when it was
    read. `FONT_BODY` because it states a scope, the one job PRD-006 Section 6.1
    gives the reading face on this console."""
    return rx.vstack(
        rx.box(
            admin_copy.USAGE_CAPTION,
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


def usage() -> rx.Component:
    """The Usage view: its own fault panel, the caption, then the scrolling
    table. `min_height="0"` on the column and the scroll container makes the
    table scroll rather than the page, the `register()` requirement."""
    return rx.vstack(
        fault_panel(AdminState.usage_error),
        _caption(),
        rx.box(
            _usage_body(),
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
