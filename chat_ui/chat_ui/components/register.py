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

**The disclosure carries evidence, not a second summary.** Under each row line
sits the five fields PRD-006 Section 10 moves onto disclosure — `error_message`
and `suspicious_pattern` first, because a **fault** row is opened to read the
error and a **denied** row to read the pattern, then `prompt_hash`, the full
User-Agent, and the PII facts. The one in-row PII indicator is **split** here
into its input and output halves, which is the whole point of moving it: the row
answers "was there PII", the disclosure answers "where". Neither preview is
among them and neither is on `AuditRow` to begin with (Risk 2), and
`admin_copy.DETAIL_TIMESTAMP_LABEL` is deliberately not used — `_time_cell`
already sets the absolute stamp under the relative one, and repeating it below
would be the frontend-design skill's "nothing quietly does double duty".

**Open state is `AdminState.open_rows`, keyed on `audit_id`.** Not
`rx.el.details` and not `rx.accordion`, both of which exist in the pinned
build. `rx.foreach` compiles to a `.map()` whose children are keyed by position,
so a DOM-held open flag would reattach an open disclosure to whichever row
landed in that slot once the sort and filter move them — silent wrongness on an
audit surface. `rx.accordion` additionally supplies colour at compile time,
which is the failure `admin_shell.py:_view_link` records for `rx.link`'s Radix
accent and which a source grep cannot see. The membership test is
`Var.contains()`: `in` is not supported on Vars.

**The controls write state; they do not filter.** The verdict chips, the
free-text field and the sort controls call `toggle_verdict`, `set_search` and
`sort_by`, and the narrowing itself is `AdminState.visible_rows` — a
synchronous computed var over rows already in state, so no control on this
surface reaches the database (PRD-006 Section 6). They are built from plain
buttons and one field rather than from a Radix group: the pinned build has no
toggle group, `checkbox_group` is uncontrolled, and `segmented_control`'s only
variants are fills carrying a compile-time accent, which Risk 6 rules out. The
`_control_button` comment block records this in full.

**The three states are chosen upstream of this module.** `_register_body` is an
`rx.match` over `AdminState.register_state`, a computed var that resolves the
precedence in Python — a failed read first, then nothing recorded, then nothing
matching, then the table. It resolves there rather than in nested `rx.cond`s
here because PRD-006 Section 4's hardest requirement is an *ordering* ("a failed
read renders a fault panel — never a silently empty table"), and an ordering
expressed as nesting can only be checked by reading compiled JavaScript, where
one in a state function is a unit test.
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
from chat_ui.admin_state import (
    REGISTER_STATE_EMPTY,
    REGISTER_STATE_FAULT,
    REGISTER_STATE_NO_MATCHES,
    REGISTER_STATE_ROWS,
    SORT_TIMESTAMP,
    SORT_USER,
    SORT_VERDICT,
    AdminState,
)

# The nine columns, in PRD-006 Section 4's order: the stamp margin, then
# timestamp, user_id, verdict, model_used, tokens_used, PII, device, audit_id —
# and a tenth track at the right edge carrying the disclosure control, which is
# a control rather than a column of values.
#
# One constant, used by the column head *and* by every row. Two matching
# template strings would satisfy "the numeric columns align down the full
# window" right up until someone edited one of them; one constant makes the
# alignment true by construction rather than by discipline.
_GRID = (
    f"{theme.STAMP_X} 8.5rem 8rem 5.5rem 9rem 5rem 3.5rem minmax(9rem, 1fr) "
    "5.5rem 2.5rem"
)

# Below this the ten columns crush rather than wrap. The table scrolls
# sideways inside its own container instead of the page doing it. Raised from
# 58rem with the control column: its 2.5rem track plus one 0.75rem column gap.
_MIN_WIDTH = "61.25rem"


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


def _is_open(row):
    """Whether this row's disclosure is open.

    `Var.contains()` and not `in`: the `in` operator is not supported on Vars.
    The set is `audit_id`s, so the answer follows the row through any reorder.
    """
    return AdminState.open_rows.contains(row.audit_id)


def _toggle_button(row, mark: str, label: str, expanded: str) -> rx.Component:
    """The disclosure control for one row, drawing no chrome of its own.

    A real `<button>`, which is the whole of the keyboard answer: it takes focus
    in document order and fires on both Enter and Space with no key handling
    here, and `theme.GLOBAL_CSS`'s `:focus-visible` rule gives it the ring. No
    local `outline`/`box_shadow` may take that back.

    `type="button"` is explicit for the reason `admin_shell.py`'s sign-out
    records: an unqualified <button> defaults to submit.

    The mark is what the eye gets and `label` is what a screen reader gets —
    the 2.5rem track has no room for DETAIL_TOGGLE_OPEN_LABEL, and a hundred
    repetitions of it down the right edge would compete with the stamp margin,
    which is where this design spends its one measure of boldness.
    """
    return rx.el.button(
        mark,
        on_click=AdminState.toggle_detail(row.audit_id),
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        width="100%",
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        line_height="1",
        color=theme.MUTE,
        _hover={"color": theme.INK},
        custom_attrs={"aria-label": label, "aria-expanded": expanded},
    )


def _disclosure_toggle(row) -> rx.Component:
    """The control in both its states, so it keeps one name across the flow."""
    return rx.box(
        rx.cond(
            _is_open(row),
            _toggle_button(
                row,
                admin_copy.DETAIL_TOGGLE_CLOSE_MARK,
                admin_copy.DETAIL_TOGGLE_CLOSE_LABEL,
                "true",
            ),
            _toggle_button(
                row,
                admin_copy.DETAIL_TOGGLE_OPEN_MARK,
                admin_copy.DETAIL_TOGGLE_OPEN_LABEL,
                "false",
            ),
        ),
        display="flex",
        justify_content="center",
        custom_attrs={"role": "cell"},
    )


def _detail_label(label: str) -> rx.Component:
    """One field's name. The same treatment `_head_cell` gives a signpost,
    because both are labels and neither is data."""
    return rx.box(
        label,
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_MICRO,
        font_weight="600",
        letter_spacing="0.1em",
        text_transform="uppercase",
        color=theme.MUTE,
        padding_top="0.15rem",
    )


def _detail_value(*children) -> rx.Component:
    """One field's value: the data face, wrapping rather than truncating.

    The exact opposite of `_cell`, and deliberately. A row cell truncates to
    protect the alignment a hundred rows are scanned on; below the row line
    there is no alignment to protect, and an `error_message` or a full
    User-Agent cut off at the container edge would be the value this whole
    disclosure exists to show, half-shown.
    """
    return rx.box(
        *children,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.INK,
        line_height="1.5",
        white_space="normal",
        word_break="break-word",
        min_width="0",
    )


def _detail_field(label: str, *value_children) -> rx.Component:
    """One labelled fact: the label, then the value."""
    return rx.fragment(_detail_label(label), _detail_value(*value_children))


def _pii_entities(row) -> rx.Component:
    """The entity types PRD-003 recorded, as words.

    `.length() > 0`, never a bare truthiness test on the list: `rx.cond`
    compiles to JavaScript, where `[]` is truthy, so `rx.cond(row.pii_entities,
    ...)` would render an empty list as though it were populated — a row
    claiming PII types it does not have.

    Plain spaced words, not chips: a chip is a fill, and Risk 6 rules fills out.
    """
    return rx.cond(
        row.pii_entities.length() > 0,
        rx.hstack(
            rx.foreach(row.pii_entities, lambda entity: rx.box(entity)),
            spacing="3",
            wrap="wrap",
        ),
        rx.box(VALUE_ABSENT, color=theme.MUTE),
    )


def _detail(row) -> rx.Component:
    """The row's record: the five fields `GET /audit` does not return in full.

    Ordered evidence-first. A **fault** row is opened to read its
    `error_message` and a **denied** row to read its `suspicious_pattern`
    (PRD-006 Section 5, story 3), so those are the top two lines and the hash
    follows them.

    The three string fields cannot arrive blank and get no fallback here:
    `admin_formatting._text` already wrote `VALUE_ABSENT` into `prompt_hash`,
    `error_message` and `suspicious_pattern` when their column was NULL, and
    `_truncate_device` did the same for `device_full`. Absence is stated at the
    boundary, which is where this module's "read fields, do not compute" rule
    puts it. Only the entity list and the two booleans need a render-time
    branch, because an empty list and a False have no absent mark to carry.

    `margin_left` plus `border_left` is the one structural move: it continues
    the stamp margin's own edge down through the open disclosure, so the stripe
    of exceptions is never broken by an open row and the record visibly hangs
    off the register's spine. No card, no fill, no background — it sits on the
    same ground as everything else (Risk 6).
    """
    return rx.box(
        rx.box(
            _detail_field(admin_copy.DETAIL_ERROR_LABEL, row.error_message),
            _detail_field(admin_copy.DETAIL_PATTERN_LABEL, row.suspicious_pattern),
            _detail_field(admin_copy.DETAIL_PROMPT_HASH_LABEL, row.prompt_hash),
            _detail_field(admin_copy.DETAIL_DEVICE_LABEL, row.device_full),
            _detail_label(admin_copy.DETAIL_PII_ENTITIES_LABEL),
            _detail_value(_pii_entities(row)),
            # Split from the row's one combined indicator, which is the reason
            # these two moved onto the disclosure at all: the row answers
            # "was there PII", these answer "where".
            _detail_field(
                admin_copy.DETAIL_PII_INPUT_LABEL,
                rx.cond(
                    row.pii_detected_input,
                    admin_copy.DETAIL_PII_PRESENT_LABEL,
                    admin_copy.DETAIL_PII_ABSENT_LABEL,
                ),
            ),
            _detail_field(
                admin_copy.DETAIL_PII_OUTPUT_LABEL,
                rx.cond(
                    row.pii_detected_output,
                    admin_copy.DETAIL_PII_PRESENT_LABEL,
                    admin_copy.DETAIL_PII_ABSENT_LABEL,
                ),
            ),
            display="grid",
            grid_template_columns="9rem minmax(0, 1fr)",
            row_gap="0.5rem",
            column_gap="0.75rem",
            align_items="start",
            custom_attrs={"role": "cell"},
        ),
        margin_left=theme.STAMP_X,
        border_left=f"1px solid {theme.RULE}",
        padding="0.75rem 1.5rem 1rem 0.75rem",
        custom_attrs={"role": "row"},
    )


def _row_line(row) -> rx.Component:
    """One register row: the stamp margin, then the eight columns, then the
    disclosure control.

    `min_height` rather than `height`: the time cell is two lines, and a fixed
    row height would clip the absolute timestamp under it.

    Ten children and no eleventh. `device_full`, `prompt_hash`, `error_message`,
    `pii_entities`, `pii_detected_input`, `pii_detected_output` and
    `suspicious_pattern` are disclosure-only fields on `AuditRow` and are read
    by `_detail`, never here — the row states the verdict, the record states the
    evidence.

    The hairline is not on this box: it belongs to `_row` below, so an open
    disclosure sits inside its row's rule rather than beneath it.
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
        _disclosure_toggle(row),
        display="grid",
        grid_template_columns=_GRID,
        align_items="center",
        column_gap="0.75rem",
        min_height=theme.ROW_H,
        padding_right="1.5rem",
        _hover={"background_color": theme.HOVER},
        custom_attrs={"role": "row"},
    )


def _row(row) -> rx.Component:
    """One row and its record: the line, and the disclosure when it is open.

    `role="rowgroup"` on the wrapper, because a bare div between the
    `role="table"` container and a `role="row"` would break the ARIA table
    structure — a rowgroup holding two rows does not.

    The hairline lives here rather than on the line, so it separates this row
    from the next one rather than separating a row from its own record. `_hover`
    stays on the line for the same reason: hovering must not tint an open
    disclosure, which is being read rather than scanned.
    """
    return rx.box(
        _row_line(row),
        rx.cond(_is_open(row), _detail(row), rx.fragment()),
        border_bottom=f"1px solid {theme.RULE_SOFT}",
        custom_attrs={"role": "rowgroup"},
    )


def _column_head() -> rx.Component:
    """The eight column heads, on the same grid the rows use.

    Sticky inside the scroll container rather than fixed above it: the register
    scrolls on `.hx-scroll`, whose scrollbar is 10px wide, and a head outside
    that container would sit 10px wider than the body and put every column head
    slightly off its column. Inside it, one scrollbar governs both — and the
    heads stay readable through a hundred rows, which is the point of a head.

    The stamp margin gets an empty cell, not a head: a label over a column that
    carries no values would be a label that labels nothing. The disclosure
    column at the other edge gets one for the same reason — it carries a
    control, not values, and the control names itself.
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
        rx.box(),
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


# --- The filter and sort controls ----------------------------------------
# Every one of them is a plain <button> or a plain field. The pinned build has
# no toggle group at all, `rx.checkbox_group.root` declares neither `value` nor
# `on_change` (so it cannot be driven from `selected_verdicts`), and
# `rx.segmented_control.root(type="multiple")` — which is controlled — has only
# the "classic" and "surface" variants, both of them fills carrying a
# `color_scheme` accent supplied at compile time. That is the failure
# `admin_shell.py:_view_link` records for `rx.link` and this module's docstring
# records for `rx.accordion`: a colour a source grep cannot see. PRD-006 Risk 6
# rules fills and accents out, so the controls are built from the same
# no-chrome button `_toggle_button` already uses.
#
# Its `on_change` would also hand over the whole selection as a list, where
# `AdminState.toggle_verdict` takes one verdict — wiring it would mean adding a
# handler to `admin_state.py`, and the state is STORY-005's, not this story's.


def _control_label(label: str) -> rx.Component:
    """The eyebrow over one cluster of controls.

    `_head_cell`'s treatment without its `role="columnheader"`: both are
    signposts set apart from what they label by size and case, but these label
    controls rather than columns and claiming otherwise would put three
    phantom columns into the table's ARIA structure.
    """
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


def _control_button(
    *children, on_click, color: str, weight: str, attrs: dict, **props
) -> rx.Component:
    """One control in the strip, drawing no chrome of its own.

    The single factory behind the verdict chips, the three sort controls and
    the clear action, so the face and the reset are stated once. A real
    `<button>`, which is the whole of the keyboard answer — it takes focus in
    document order, fires on Enter and Space with no key handling here, and
    takes its ring from `theme.GLOBAL_CSS`'s `:focus-visible`. No local
    `outline` or `box_shadow` may take that back.

    `type="button"` is explicit for the reason `admin_shell.py`'s sign-out
    records: an unqualified <button> defaults to submit.

    `**props` lands after `border`, so a caller's `border_bottom` wins over the
    reset rather than being cancelled by it.
    """
    return rx.el.button(
        *children,
        on_click=on_click,
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        line_height="1.4",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_TAG,
        color=color,
        font_weight=weight,
        custom_attrs=attrs,
        **props,
    )


# Each verdict as (filter value, word on screen, ink). The value is the
# formatter's key and the word is `admin_copy`'s label — the same separation
# `_verdict_tag` keeps, so a chip can never disagree with the row it filters.
# Built in Python because the four verdicts are plain strings, not Vars.
_VERDICT_CHIPS = (
    (VERDICT_CLEARED, admin_copy.VERDICT_CLEARED_LABEL, theme.INK_CLEAR),
    (VERDICT_HELD, admin_copy.VERDICT_HELD_LABEL, theme.INK_HELD),
    (VERDICT_DENIED, admin_copy.VERDICT_DENIED_LABEL, theme.INK_DENIED),
    (VERDICT_FAULT, admin_copy.VERDICT_FAULT_LABEL, theme.INK_FAULT),
)


def _chip_button(key: str, label: str, ink: str, selected: bool) -> rx.Component:
    """One verdict in the multi-select, in one of its two states.

    The case split is `_tag`'s, applied here the same way and for the same
    reason: `admin_copy` holds one lowercase label per verdict so the word
    cannot arrive in two cases from two constants, and the treatment is what
    marks an exception. A chip therefore reads as the row it isolates.

    **Selection is marked without a fill** (PRD-006 Risk 6, and the story: the
    chips "may carry their verdict ink as text, not as a fill"). Three
    channels, none of them a ground: the verdict's ink replaces the mute, the
    weight steps up, and a 2px rule in that same ink seats under the word.
    `aria-pressed` is the fourth, for a reader that sees no colour at all.
    """
    exception = key != VERDICT_CLEARED
    return _control_button(
        label,
        on_click=AdminState.toggle_verdict(key),
        color=ink if selected else theme.MUTE,
        weight="600" if selected else "500",
        attrs={"aria-pressed": "true" if selected else "false"},
        letter_spacing="0.08em" if exception else "0",
        text_transform="uppercase" if exception else "none",
        border_bottom=(f"2px solid {ink}" if selected else "2px solid transparent"),
        padding_bottom="2px",
        _hover={} if selected else {"color": theme.INK},
    )


def _verdict_filter() -> rx.Component:
    """The verdict multi-select: four chips, any combination of them.

    Both states of every chip are built, because the selected test is a Var and
    the styling branches on it — the `_disclosure_toggle` pattern. `.contains()`
    and not `in`: the `in` operator is not supported on Vars.

    Toggling writes `AdminState.toggle_verdict` and nothing else. The narrowing
    is `visible_rows`, a synchronous computed var over rows already in state, so
    a toggle reaches no database (PRD-006 Section 6).
    """
    return rx.flex(
        _control_label(admin_copy.FILTER_VERDICT_LABEL),
        *[
            rx.cond(
                AdminState.selected_verdicts.contains(key),
                _chip_button(key, label, ink, True),
                _chip_button(key, label, ink, False),
            )
            for key, label, ink in _VERDICT_CHIPS
        ],
        align="center",
        gap="0.75rem",
        wrap="wrap",
    )


def _search_field() -> rx.Component:
    """The free-text filter over `user_id` / `model_used` / `audit_id`.

    This is the register's join back to the chat: the `#127` a user quotes out
    of the success footer (PRD-004 STORY-010) resolves to its row by being typed
    here. The `audit_id` coercion is `admin_state._matches`' — Python-side,
    against an int field, never in this component.

    **Debounced by construction.** `TextFieldRoot.create` wraps the field in
    `DebounceInput` whenever both `value` and `on_change` are given, at the
    core default of 300ms — so `visible_rows` re-evaluates on a pause rather
    than on a keystroke, which is PRD-006 Risk 5's stated mitigation without a
    line of debounce code here. Do not split the field into an uncontrolled one.

    The `id` is not decoration: Radix paints the real `<input>` inside its
    TextField wrapper, so the only way to colour the text an admin types is the
    id selector `theme.py` carries for it — the same reason `admin_gate`'s
    field has one.
    """
    return rx.flex(
        _control_label(admin_copy.FILTER_SEARCH_LABEL),
        rx.input(
            id="register_filter_input",
            class_name="hx-field-boxed",
            value=AdminState.search,
            on_change=AdminState.set_search,
            placeholder=admin_copy.FILTER_SEARCH_PLACEHOLDER,
            custom_attrs={
                "aria-label": admin_copy.FILTER_SEARCH_LABEL,
                "autoComplete": "off",
                "autoCorrect": "off",
            },
            width="13rem",
            height="1.75rem",
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_DATA,
            border_radius=theme.RADIUS,
        ),
        align="center",
        gap="0.5rem",
    )


# Which glyph each ordering shows, as (natural order, reversed). `sort_rows`
# documents `sort_descending = False` as the *natural* order of the chosen key,
# and that order is a different direction for each of the three — so one glyph
# cannot serve all of them and the pair is chosen per key instead:
#
#   timestamp -> natural is newest first, i.e. time descending down the page
#   user      -> natural is A-Z, i.e. ascending
#   verdict   -> natural is fault first, i.e. severity descending
#
# Picked in Python because the keys are plain strings. The alternative — one
# `rx.cond` on `sort_descending` shared by all three — would have to claim that
# A-Z and newest-first point the same way, and they do not.
_SORT_MARKS = {
    SORT_TIMESTAMP: (
        admin_copy.SORT_DESCENDING_MARK,
        admin_copy.SORT_ASCENDING_MARK,
    ),
    SORT_USER: (
        admin_copy.SORT_ASCENDING_MARK,
        admin_copy.SORT_DESCENDING_MARK,
    ),
    SORT_VERDICT: (
        admin_copy.SORT_DESCENDING_MARK,
        admin_copy.SORT_ASCENDING_MARK,
    ),
}

# One label per key in `admin_state.SORT_KEYS`, in the order the controls sit.
_SORT_CONTROLS = (
    (SORT_TIMESTAMP, admin_copy.SORT_TIMESTAMP_LABEL),
    (SORT_USER, admin_copy.SORT_USER_LABEL),
    (SORT_VERDICT, admin_copy.SORT_VERDICT_LABEL),
)


def _is_sorted_by(key: str):
    """Whether this ordering is the one in force.

    The timestamp arm also matches the empty string, and that is required
    rather than defensive: `AdminState.sort_key` defaults to `""` so that
    `sign_out()`'s reset clears it, and `sort_rows` reads `""` as the loaded
    order — which *is* timestamp, newest first. Without this the register's
    default ordering would render with no control marked, and PRD-006 Section
    6.1's "timestamp descending remains the default" would be true of the table
    and invisible on the surface.

    `|`, never Python `or`: `or` short-circuits on the first Var, which is
    truthy, and would silently return it instead of the disjunction.
    """
    if key == SORT_TIMESTAMP:
        return (AdminState.sort_key == key) | (AdminState.sort_key == "")
    return AdminState.sort_key == key


def _sort_button(key: str, label: str, active: bool) -> rx.Component:
    """One ordering, in one of its two states.

    The direction mark rides only on the active control: three marks would say
    three orderings are in force at once, where exactly one ever is. It is a
    second child rather than a concatenation, because the mark comes out of an
    `rx.cond` and is a Var, not a str.
    """
    children = [label]
    if active:
        children.append(
            rx.el.span(
                rx.cond(
                    AdminState.sort_descending,
                    _SORT_MARKS[key][1],
                    _SORT_MARKS[key][0],
                ),
                margin_left="0.25rem",
            )
        )
    return _control_button(
        *children,
        on_click=AdminState.sort_by(key),
        color=theme.INK if active else theme.MUTE,
        weight="600" if active else "500",
        attrs={"aria-pressed": "true" if active else "false"},
        _hover={} if active else {"color": theme.INK},
    )


def _sort_controls() -> rx.Component:
    """The three orderings PRD-006 Section 4 names, as peers.

    `sort_by` is the handler and not a plain setter: choosing the ordering
    already in force reverses it instead of re-setting it, which is what makes
    one control carry both the choice and the direction.
    """
    return rx.flex(
        _control_label(admin_copy.SORT_LABEL),
        *[
            rx.cond(
                _is_sorted_by(key),
                _sort_button(key, label, True),
                _sort_button(key, label, False),
            )
            for key, label in _SORT_CONTROLS
        ],
        align="center",
        gap="0.75rem",
        wrap="wrap",
    )


def _clear_control() -> rx.Component:
    """Restores the full window, and appears only when there is one to restore.

    Shown against `filters_active`, which excludes the sort deliberately —
    reordering the register removes no row, so there is nothing for a clear to
    undo. A control rendered against nothing to do is the one thing the
    frontend-design skill's "let each element do exactly one job" rules out, and
    `admin_shell.py:_view_link` already refuses it for the active view.

    The sign-out button's treatment, so a text action reads the same on both
    admin surfaces — the skill's consistency rule, not drift.
    """
    return rx.cond(
        AdminState.filters_active,
        _control_button(
            admin_copy.CLEAR_FILTERS_LABEL,
            on_click=AdminState.clear_filters,
            color=theme.MUTE,
            weight="500",
            attrs={},
            text_decoration="underline",
            text_underline_offset="3px",
            _hover={"color": theme.INK},
        ),
        rx.fragment(),
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


def _filtered_line() -> rx.Component:
    """"12 of 100 shown" — how much of the window survived the filter.

    A **second** scope statement under the first, never a replacement for it.
    The scope line states the window against the whole record; this states the
    filtered set against the window, and collapsing the two would leave the
    window's own line moving every time an admin types (PRD-006 Risk 4).

    So it takes `FONT_BODY` too. Section 6.1 reserves the reading face for "the
    two or three explanatory lines that state a scope", and setting this one in
    a different face would say the two statements are different kinds of thing.

    Shown only while a filter is active: "100 of 100 shown" under an untouched
    register is a line that reports nothing. `filters_active` excludes the sort,
    which is right here for the same reason it is right for the clear action —
    a reorder narrows nothing.

    The sentence itself is `AdminState.register_filtered`, a computed var, for
    the reason the module docstring gives: the template is a Python format
    string over thousands-separated counts, and neither can run against a Var.
    """
    return rx.cond(
        AdminState.filters_active,
        rx.box(
            AdminState.register_filtered,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            color=theme.MUTE,
        ),
        rx.fragment(),
    )


def _filter_strip() -> rx.Component:
    """The scope statements on the left, the controls on the right.

    PRD-006 Section 6.1's wireframe: the verdict filter sits on the scope line
    and the text filter under it. The sort cluster and the clear action join
    that second row — the wireframe places neither, and a third row for three
    words would push the table down for nothing.

    The left column deliberately holds **only** the two scope statements. The
    wireframe's "Refreshed 14:22:07" belongs at the foot of that column and is
    STORY-017's; the slot is left free rather than filled here.

    `wrap="wrap"` on both flex rows is the whole narrow-viewport answer, the
    same move `admin_shell.py:admin_masthead` makes on the header: the clusters
    stack rather than compress, with no new CSS and no breakpoint.
    """
    return rx.flex(
        rx.vstack(
            _scope_line(),
            _filtered_line(),
            spacing="1",
            align="start",
            min_width="0",
        ),
        rx.vstack(
            _verdict_filter(),
            rx.flex(
                _search_field(),
                _sort_controls(),
                _clear_control(),
                align="center",
                gap="1.25rem",
                wrap="wrap",
            ),
            spacing="2",
            align="end",
        ),
        justify="between",
        align="start",
        gap="1.5rem",
        wrap="wrap",
        padding="0.75rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        flex_shrink="0",
        width="100%",
    )


# --- The three states (STORY-014) ----------------------------------------
# PRD-006 Section 4: "Three distinct states: no rows recorded at all, rows
# recorded but none matching the filter, and rows shown." The third is the table
# that was already here; the two that need words are below. The precedence over
# them — and over the failed read that must never be dressed as either — is
# `AdminState.register_state`, resolved in Python (see the module docstring).


def _empty_panel(title: str, *body_children) -> rx.Component:
    """One empty state: a line saying what is true, then the way out.

    AC 6, written as the list of what is absent — no illustration, no card, no
    border, no background, no accent. The panel paints `INK` and `MUTE` on the
    register's own ground and nothing else, which is also what keeps
    `tests/test_register.py::test_no_colour_outside_the_allowed_set` true of the
    surface as a whole. An empty state is exactly where a card and a centred
    icon are the template answer (PRD-006 Risk 6), so neither is here.

    The type is the surface's existing scale: `FONT_DISPLAY` for the title, the
    face that already sets the column heads and verdict tags, and `FONT_BODY`
    for the sentence — the reading face PRD-006 Section 6.1 reserves for
    explanatory lines, which is what both of these are.

    Left-aligned at the table's own inset rather than centred in the container:
    a centred block is a card without a border, and the register is read down
    its left edge.
    """
    return rx.box(
        rx.box(
            title,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            letter_spacing="-0.01em",
            color=theme.INK,
        ),
        rx.box(
            *body_children,
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


def _empty_register() -> rx.Component:
    """Nothing has ever been recorded.

    Deliberately not the no-matches wording: PRD-006 Section 4 wants the two
    distinguishable, and this one blames no filter because there is no filter to
    blame — it is reached only when `rows` is empty, whatever the controls say.

    It ends in the action available from it, per the frontend-design skill's
    "an empty screen is an invitation to act": `EMPTY_REGISTER_BODY` points at
    Refresh, and the control it names is the masthead's, so no second button is
    declared here to compete with it.
    """
    return _empty_panel(
        admin_copy.EMPTY_REGISTER_TITLE,
        admin_copy.EMPTY_REGISTER_BODY,
    )


def _no_matches() -> rx.Component:
    """Rows are loaded; this filter matched none of them.

    PRD-006 Section 6.1 asks for two things and this renders both. The sentence
    names the filter that produced the empty result — `empty_matches_message`, a
    Var, hence a second child of the panel rather than a formatted string. And
    the way out is `_clear_control()` **itself**, not a second button with the
    same job: one name for one action across the strip and the panel is the
    skill's consistency rule, and a second constant is the drift it warns about.

    `_clear_control` is `rx.cond(filters_active, ...)`, whose condition is true
    in this arm by construction — `register_state` returns no-matches only when
    `visible_rows` is empty and `rows` is not, which requires an active filter.
    The guard is left in place rather than bypassed so the control keeps one
    definition instead of two.
    """
    return _empty_panel(
        admin_copy.EMPTY_MATCHES_TITLE,
        AdminState.empty_matches_message,
        rx.box(_clear_control(), margin_top="0.75rem"),
    )


def _table() -> rx.Component:
    """The column heads over the rows — STORY-011's table, now one arm of four.

    It is also the `read_failed` arm, and that is the point of AC 4 rather than
    an omission: `admin_copy.FAULT_MESSAGE_TEMPLATE` promises "Nothing on screen
    has changed", so a failed read leaves the previously loaded rows standing
    and STORY-017 hangs its fault panel above them. An empty *table* under a
    fault panel is correct; an empty *state* under one is the misreading PRD-006
    Section 4 forbids.
    """
    return rx.box(
        _column_head(),
        rx.foreach(AdminState.visible_rows, _row),
        min_width=_MIN_WIDTH,
        custom_attrs={"role": "table"},
    )


def _register_body() -> rx.Component:
    """The three states, chosen by the one var that owns the precedence.

    `rx.match` over `AdminState.register_state` rather than nested `rx.cond`s:
    the ordering AC 4 turns on is then a Python function a unit test can call
    (`tests/test_admin_state.py`), instead of a nesting order verifiable only by
    reading compiled JavaScript.

    The default arm is the table, and the direction is deliberate: an
    unrecognised state renders the record rather than a claim of emptiness.
    """
    return rx.match(
        AdminState.register_state,
        (REGISTER_STATE_EMPTY, _empty_register()),
        (REGISTER_STATE_NO_MATCHES, _no_matches()),
        (REGISTER_STATE_FAULT, _table()),
        (REGISTER_STATE_ROWS, _table()),
        _table(),
    )


def register() -> rx.Component:
    """The register: the filter strip over the scrolling table.

    `min_height="0"` on both the column and the scroll container is what makes
    the table scroll rather than the page: a flex child will not shrink below
    its content without it, so the container would grow past the viewport and
    hand the scrolling to the document instead.

    Not `rx.auto_scroll`, which the chat's transcript uses: that pins the view
    to the newest entry, which is right for a live transcript and wrong for a
    register someone is reading through.

    **The filter strip renders in every state**, including both empty ones. It
    carries the scope statements — which are still true of an empty register —
    and the controls, and taking the controls away in the one state an admin
    needs them to escape would be the dead end the frontend-design skill's
    "an empty screen is an invitation to act" rules out. What changes between
    states is only what is inside the scroll container: `_register_body()`.
    """
    return rx.vstack(
        _filter_strip(),
        rx.box(
            _register_body(),
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
