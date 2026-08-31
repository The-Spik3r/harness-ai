"""The register: a hundred audit rows, and the stripe of exceptions down them.

The console's one signature surface. PRD-006 Section 6.1 spends the whole
design's boldness here and nowhere else, so everything in this module is either
the stamp margin or is deliberately quiet around it.

**The stamp margin.** A narrow fixed column down the left edge carrying nothing
but the row's verdict as a solid mark in its ink; cleared rows leave it blank.
A hundred rows therefore resolve into a vertical stripe of exceptions — finding
the three denied entries is a glance at an edge, not a read of a table. It is
the chat's rail continued rather than reinvented: `theme.STAMP_X is
theme.RAIL_X` (asserted by identity in `tests/test_admin_palette.py`) and the
mark is the same `theme.GLYPH` square. The shape is **re-declared** here rather
than imported from `components/bubbles.py` — PRD-006 Section 4 forbids an admin
page rendering a chat component, and `admin_copy.py` re-declares the wordmark
for the same reason.

**This module reads fields; it does not compute.** PRD-006 Section 6: the
verdict, the relative time and the formatted device string are computed once in
Python when the row is built (`admin_formatting.to_audit_row`). Component
functions receive Reflex Vars — JS references — so Python control flow cannot
run against them. The two branches here are `rx.match` over a field and
`rx.cond` over a bool field, which are the supported render-time forms, not
computation. The scope line is a `str` field on the state for the same reason:
its thousands separator is Python-side formatting.

**What this surface refuses.** The template answer for an admin screen is a row
of KPI cards over a striped table with a left sidebar and an accent colour.
PRD-006 Section 6.1 rules all of it out: the admin's question is never "what is
the total", it is "which rows are not cleared". So there are no cards, no
fills, no zebra striping, no accent, and no icon — every colour below is a
verdict ink or a ground token from `theme.py`, and the only lines drawn are the
margin's edge, the rule under the column heads and the hairline between rows.
`tests/test_admin_palette.py` globs this file and `tests/test_register.py`
checks the rendered output against the allowed set.

**Type is inverted from the chat.** A register is timestamps, ids, counts and
user agents, with almost no prose — so `FONT_DATA` is the dominant face and its
alignment down a hundred rows is what makes scanning work at all, `FONT_DISPLAY`
sets the verdict tags and column heads, and `FONT_BODY` appears on the scope
line and nowhere else.

The disclosure (STORY-012), the filter and sort controls (STORY-013) and the
three empty states (STORY-014) are not here. `register()` renders the table
unconditionally; STORY-014 is what wraps it in the condition that chooses
between it and an empty state.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_formatting import (
    VALUE_ABSENT,
    VERDICT_CLEARED,
    VERDICT_DENIED,
    VERDICT_FAULT,
    VERDICT_HELD,
)
from chat_ui.admin_state import AdminState

# The nine columns, in PRD-006 Section 4's order: the stamp margin, then
# timestamp, user_id, verdict, model_used, tokens_used, PII, device, audit_id.
#
# One constant, used by the column head *and* by every row. Two matching
# template strings would satisfy "the numeric columns align down the full
# window" right up until someone edited one of them; one constant makes the
# alignment true by construction rather than by discipline.
_GRID = (
    f"{theme.STAMP_X} 8.5rem 8rem 5.5rem 9rem 5rem 3.5rem minmax(9rem, 1fr) 5.5rem"
)

# Below this the nine columns crush rather than wrap. The table scrolls
# sideways inside its own container instead of the page doing it.
_MIN_WIDTH = "58rem"


def _head_cell(label: str, align: str = "left") -> rx.Component:
    """One column head: a signpost, set apart from row data by size and case.

    `TEXT_MICRO` is the step theme.py introduced for exactly this — "register
    column heads — a signpost, never row data".
    """
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_MICRO,
        font_weight="600",
        letter_spacing="0.1em",
        text_transform="uppercase",
        text_align=align,
        color=theme.MUTE,
        custom_attrs={"role": "columnheader"},
    )


def _cell(*children, color: str = theme.INK, **props) -> rx.Component:
    """One row cell, always in the data face so it never reads as prose.

    Truncates rather than wrapping: a long `model_used` that wrapped would push
    its row taller than its neighbours and break the alignment the register is
    scanned on.
    """
    return rx.box(
        *children,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=color,
        overflow="hidden",
        text_overflow="ellipsis",
        white_space="nowrap",
        custom_attrs={"role": "cell"},
        **props,
    )


def _stamp(ink: str) -> rx.Component:
    """The mark itself: a stamped square, the same one the chat's rail carries."""
    return rx.box(
        width=theme.GLYPH,
        height=theme.GLYPH,
        flex_shrink="0",
        border_radius="1px",
        background_color=ink,
    )


def _stamp_margin(row) -> rx.Component:
    """The signature. One fixed column, one mark per exception, blank otherwise.

    Cleared rows and the `""` default both render nothing, and that is the
    whole mechanism: a column that marked every row would be a column of marks,
    not a stripe of exceptions.

    `AuditRow.verdict` defaults to the empty string rather than to the cleared
    key — an unpopulated row must not claim it passed — so the default arm is
    required here, not optional.
    """
    return rx.box(
        rx.match(
            row.verdict,
            (VERDICT_HELD, _stamp(theme.INK_HELD)),
            (VERDICT_DENIED, _stamp(theme.INK_DENIED)),
            (VERDICT_FAULT, _stamp(theme.INK_FAULT)),
            (VERDICT_CLEARED, rx.fragment()),
            rx.fragment(),
        ),
        width=theme.STAMP_X,
        flex_shrink="0",
        align_self="stretch",
        display="flex",
        align_items="center",
        justify_content="center",
        # The margin's edge — the one rule this column draws, and the `├─┬──`
        # in PRD-006 Section 6.1's wireframe.
        border_right=f"1px solid {theme.RULE}",
        custom_attrs={"role": "cell"},
    )


def _verdict_tag(row) -> rx.Component:
    """The verdict as a word, beside the same verdict as a mark.

    Four inks, one per outcome, so no two verdicts share a treatment. The case
    split is a second, redundant channel carrying the same fact — it is applied
    here with `text_transform` rather than baked into the constants, because
    `admin_copy` holds one lowercase label per verdict precisely so the word
    cannot arrive in two cases from two constants and leave a later filter chip
    disagreeing with the row.
    """
    return rx.match(
        row.verdict,
        (
            VERDICT_CLEARED,
            _tag(admin_copy.VERDICT_CLEARED_LABEL, theme.INK_CLEAR, exception=False),
        ),
        (VERDICT_HELD, _tag(admin_copy.VERDICT_HELD_LABEL, theme.INK_HELD)),
        (VERDICT_DENIED, _tag(admin_copy.VERDICT_DENIED_LABEL, theme.INK_DENIED)),
        (VERDICT_FAULT, _tag(admin_copy.VERDICT_FAULT_LABEL, theme.INK_FAULT)),
        _tag(VALUE_ABSENT, theme.MUTE, exception=False),
    )


def _tag(label: str, ink: str, exception: bool = True) -> rx.Component:
    """One verdict tag. Exceptions are set in caps; cleared stays lowercase."""
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


def _time_cell(row) -> rx.Component:
    """The relative reading, with the absolute timestamp as evidence under it.

    Both, because PRD-006 Section 4 names the column "timestamp (relative +
    absolute)": the relative one is what an admin scans, the absolute one is
    what they quote. Neither can render blank — `_format_timestamps` writes the
    absent mark into both when the column is NULL or unparseable.
    """
    return rx.box(
        rx.box(
            row.timestamp_relative,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_DATA,
            color=theme.INK,
            overflow="hidden",
            text_overflow="ellipsis",
            white_space="nowrap",
        ),
        rx.box(
            row.timestamp_absolute,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_MICRO,
            color=theme.MUTE,
            overflow="hidden",
            text_overflow="ellipsis",
            white_space="nowrap",
        ),
        min_width="0",
        custom_attrs={"role": "cell"},
    )


def _row(row) -> rx.Component:
    """One register row: the stamp margin, then the eight columns.

    `min_height` rather than `height`: the time cell is two lines, and a fixed
    row height would clip the absolute timestamp under it.

    Nine children and no tenth. `device_full`, `prompt_hash`, `error_message`,
    `pii_entities`, `pii_detected_input`, `pii_detected_output` and
    `suspicious_pattern` are disclosure-only fields on `AuditRow` and belong to
    STORY-012.
    """
    return rx.box(
        _stamp_margin(row),
        _time_cell(row),
        _cell(row.user_id),
        _verdict_tag(row),
        _cell(row.model_used),
        _cell(row.tokens_used, text_align="right"),
        rx.cond(
            row.pii_indicator,
            _cell(admin_copy.PII_INDICATOR_LABEL),
            _cell(VALUE_ABSENT, color=theme.MUTE),
        ),
        _cell(row.device_short),
        # Two children rather than a concatenation: the prefix is a str and
        # audit_id is an int Var, and adjacent children need no Var arithmetic.
        # This is the row's real id — the string a user quotes out of the chat's
        # success footer — so it is a key, not a decoration.
        _cell(admin_copy.AUDIT_ID_PREFIX, row.audit_id, text_align="right"),
        display="grid",
        grid_template_columns=_GRID,
        align_items="center",
        column_gap="0.75rem",
        min_height=theme.ROW_H,
        padding_right="1.5rem",
        border_bottom=f"1px solid {theme.RULE_SOFT}",
        _hover={"background_color": theme.HOVER},
        custom_attrs={"role": "row"},
    )


def _column_head() -> rx.Component:
    """The eight column heads, on the same grid the rows use.

    Sticky inside the scroll container rather than fixed above it: the register
    scrolls on `.hx-scroll`, whose scrollbar is 10px wide, and a head outside
    that container would sit 10px wider than the body and put every column head
    slightly off its column. Inside it, one scrollbar governs both — and the
    heads stay readable through a hundred rows, which is the point of a head.

    The stamp margin gets an empty cell, not a head: a label over a column that
    carries no values would be a label that labels nothing.
    """
    return rx.box(
        rx.box(width=theme.STAMP_X, border_right=f"1px solid {theme.RULE}"),
        _head_cell(admin_copy.COLUMN_TIME),
        _head_cell(admin_copy.COLUMN_USER),
        _head_cell(admin_copy.COLUMN_VERDICT),
        _head_cell(admin_copy.COLUMN_MODEL),
        _head_cell(admin_copy.COLUMN_TOKENS, align="right"),
        _head_cell(admin_copy.COLUMN_PII),
        _head_cell(admin_copy.COLUMN_DEVICE),
        _head_cell(admin_copy.COLUMN_ID, align="right"),
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
        # A full rule under the head against the hairline between rows, so the
        # head reads as the boundary it is.
        border_bottom=f"1px solid {theme.RULE}",
        custom_attrs={"role": "row"},
    )


def _scope_line() -> rx.Component:
    """"100 most recent of 3,180" — the window, stated against the whole record.

    The only place `FONT_BODY` appears on this surface: PRD-006 Section 6.1
    reserves the reading face for the two or three lines that state a scope,
    and everything else here is data or a label.
    """
    return rx.box(
        AdminState.register_scope,
        font_family=theme.FONT_BODY,
        font_size=theme.TEXT_DATA,
        color=theme.MUTE,
    )


def register() -> rx.Component:
    """The register: the scope strip over the scrolling table.

    A strip rather than a bare line because STORY-013 hangs the verdict
    multi-select and the free-text field on its right-hand side, which is where
    PRD-006 Section 6.1's wireframe puts them.

    `min_height="0"` on both the column and the scroll container is what makes
    the table scroll rather than the page: a flex child will not shrink below
    its content without it, so the container would grow past the viewport and
    hand the scrolling to the document instead.

    Not `rx.auto_scroll`, which the chat's transcript uses: that pins the view
    to the newest entry, which is right for a live transcript and wrong for a
    register someone is reading through.
    """
    return rx.vstack(
        rx.box(
            _scope_line(),
            padding="0.75rem 1.5rem",
            border_bottom=f"1px solid {theme.RULE}",
            flex_shrink="0",
            width="100%",
        ),
        rx.box(
            rx.box(
                _column_head(),
                rx.foreach(AdminState.visible_rows, _row),
                min_width=_MIN_WIDTH,
                custom_attrs={"role": "table"},
            ),
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
