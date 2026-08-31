"""The summary: nine figures set as a ruled tally sheet, each stating its scope.

The register's counterpart, and deliberately the quieter of the two surfaces.
PRD-006 Section 6.1 spends the console's boldness on the register's stamp
margin; this sheet draws rules and sets type, and nothing else.

**What this surface refuses.** The template answer for an admin summary is a row
of KPI cards — a big number over a small label, a gradient accent, four of them
across the top. The **frontend-design** skill names that pattern directly ("a big
number with a small label, supporting stats, and a gradient accent is the
template answer, only use if that's truly the best option"), and PRD-006 Section
6.1 rules it out here: "the admin's question is never 'what is the total', it is
'which rows are not cleared'." So there are no cards, no fills, no accent colour,
no icons and no charts — `StatsResponse` carries no time dimension, so any trend
line would be invented.

**The indentation is the argument.** `blocked_duplicates` and
`blocked_suspicious` sit indented beneath `total_queries` because they are a
subset of it. PRD-006 Section 6.1, verbatim: "indentation is the honest
structural statement of that relationship — a card grid asserts that all four
numbers are peers, which is false." The indent is therefore spacing and nothing
else: no bracket, no leading mark, no lighter rule, no smaller type. One
accessory removed, per the skill's last instruction.

**Every figure states its scope, and that is not a nicety.** PRD-006 Risk 4: an
all-time `3,180` beside a register showing 100 rows "reads as a contradiction, or
worse, as a filtered view of the same set". So `SUMMARY_SCOPE_ALL_TIME` rides on
each figure and `SUMMARY_SCOPE_NOTE` opens the sheet by naming the difference
between the two windows outright.

**This module reads fields; it does not compute.** Every figure is a
`SummaryFigure` built in `AdminState` (`total_figure`, `blocked_figures`,
`completion_figure`, `who_figures`, `pii_figures`) out of `format_count` and
`format_share`. Both are Python — a thousands separator and a zero-total branch —
and component functions receive Reflex Vars, which is also why a total of 0
renders `SHARE_UNDEFINED` here rather than raising: the division never reaches
this file.

**`figure["items"]`, never `figure.items`.** `SummaryFigure.items` collides with
`ObjectVar.items`, the dict-like method Reflex puts on every object Var, so the
attribute form resolves to a bound method and `rx.foreach` raises
`TypeError: Unsupported type <class 'method'> for LiteralVar` at build time.
The subscript form returns a properly typed `list[str]` Var. Verified against the
pinned `reflex==0.9.6.post1`; `tests/test_summary.py` guards it.

**Type, as the register inverts it.** `FONT_DATA` carries the values, because the
sheet is numbers and they must align down the right edge to be comparable at a
glance. `FONT_DISPLAY` sets the labels and the block headings. `FONT_BODY` is
reserved for the two explanatory lines that state a scope — the sheet's opening
note and the completion figure's note — exactly as it is reserved for the
register's scope line and nowhere else.

**The three states are chosen upstream.** `_sheet_body` is an `rx.match` over
`AdminState.summary_state`, a computed var resolving the precedence in Python: a
failed read first, then nothing recorded, then the figures. It resolves there
rather than in nested `rx.cond`s here for the reason `register.py` records — an
ordering expressed as nesting can only be checked by reading compiled JavaScript,
where one in a state function is a unit test.

Nothing here reaches the chat: this module imports `admin_copy`, `theme` and
`AdminState`, and PRD-006 Section 4's "no admin page renders a chat component"
holds by that list.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import (
    SUMMARY_STATE_EMPTY,
    SUMMARY_STATE_FAULT,
    SUMMARY_STATE_FIGURES,
    AdminState,
)
from chat_ui.components.admin_shell import refreshed_stamp

# The sheet is read down its left edge like the register, and its values are
# compared down its right one. Bounded so a wide window does not strand the
# numbers a screen away from the labels they belong to.
_SHEET_MAX = "44rem"

# The value column. Wide enough for a thousands-separated count and for the
# "13.0% of all queries" line beneath it without either wrapping at the sheet's
# full width. A layout literal, like `register.py:_GRID`'s tracks — only colours
# are token-only.
_VALUE_MIN = "12rem"


def _figure_label(figure) -> rx.Component:
    """The label over its scope: what this figure counts, and over what window.

    Two elements, two jobs — the skill's "a label labels… and nothing quietly
    does double duty". The scope is set smaller and muted because it is the same
    sentence on every figure; it must be readable without becoming a second
    column of noise.
    """
    return rx.box(
        rx.box(
            figure.label,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            font_weight="600",
            color=theme.INK,
        ),
        rx.box(
            figure.scope,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_MICRO,
            color=theme.MUTE,
            margin_top="0.125rem",
        ),
        min_width="0",
    )


def _figure_value(figure) -> rx.Component:
    """The number, and its share of the whole table under it.

    Right-aligned and set in `FONT_DATA` so the counts line up down the sheet —
    the same reason the register's numeric columns are monospaced.

    The share renders only when the figure carries one: `unique_users` has no
    meaningful share of a query count, and an empty slot is quieter than a
    placeholder that means "not applicable". Where a figure *does* carry one and
    the total is 0, `AdminState._share_line` has already put the absence mark
    there rather than a percentage.
    """
    return rx.box(
        rx.box(
            figure.value,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_BODY,
            color=theme.INK,
        ),
        rx.cond(
            figure.share != "",
            rx.box(
                figure.share,
                font_family=theme.FONT_DATA,
                font_size=theme.TEXT_DATA,
                color=theme.MUTE,
                margin_top="0.125rem",
            ),
            rx.fragment(),
        ),
        text_align="right",
        # `flex="1"` rather than a width: on one line it takes the space the
        # label leaves and right-aligns inside it, and when the row wraps on a
        # narrow viewport it takes the full width and stays aligned to the same
        # right edge. Without it a wrapped value keeps its `min_width` and lands
        # stranded in the middle of the row, which reads as a third column.
        flex="1",
        min_width=_VALUE_MIN,
    )


def _rank_line(item) -> rx.Component:
    """One entry of a ranked list.

    A name, not a name and a count: `top_models`, `top_users` and
    `top_pii_entities` all return values only (`app/db/database.py:166-218`
    select the column, not its tally), and rendering a tally the read did not
    return would be inventing evidence on an audit surface.

    Unnumbered, deliberately. The **frontend-design** skill's caution about
    numbered markers applies — they belong to content that "actually is a
    sequence" — and a top-five list is already in rank order by construction. The
    register's `#3180` earns its number because it is the row's real `audit_id`;
    a "1." here would be decoration.
    """
    return rx.box(
        item,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.INK,
    )


def _ranked_items(figure) -> rx.Component:
    """The ranked list under its figure, or the line saying there is none.

    `figure["items"]`, never `figure.items` — see the module docstring; the
    attribute form fails at build time.

    Scalar figures carry an empty `items` and take the same branch as an
    unranked table, which is correct: `RANKED_EMPTY_LABEL` never renders for them
    because `_ranked_items` is only called from the ranked arm below.
    """
    return rx.box(
        rx.cond(
            figure["items"],
            rx.foreach(figure["items"], _rank_line),
            rx.box(
                admin_copy.RANKED_EMPTY_LABEL,
                font_family=theme.FONT_DATA,
                font_size=theme.TEXT_DATA,
                color=theme.MUTE,
            ),
        ),
        margin_top="0.5rem",
        display="flex",
        flex_direction="column",
        gap="0.25rem",
    )


def _figure(figure, indent: str = "0") -> rx.Component:
    """One ruled line of the sheet: label and scope left, value and share right.

    `indent` is how the subset relationship is stated (see the module
    docstring), and it is a padding rather than a component so an indented figure
    and a top-level one are provably the same element with one number changed.

    `wrap="wrap"` is the whole narrow-viewport answer, the same move
    `admin_shell.py:admin_masthead` and `register.py:_filter_strip` make: the
    value drops under the label rather than crushing it, with no breakpoint and
    no new CSS.

    The rule underneath is `RULE_SOFT` — the hairline between rows on the
    register. The heavier `RULE` is reserved for the block divisions, so the
    sheet reads as three groups of figures rather than one long list.
    """
    return rx.box(
        rx.flex(
            _figure_label(figure),
            _figure_value(figure),
            justify="between",
            align="start",
            gap="1.5rem",
            wrap="wrap",
            width="100%",
        ),
        rx.cond(
            figure["items"],
            _ranked_items(figure),
            rx.fragment(),
        ),
        padding="0.75rem 0",
        padding_left=indent,
        border_bottom=f"1px solid {theme.RULE_SOFT}",
        width="100%",
    )


def _indented_figure(figure) -> rx.Component:
    """A figure that is a subset of the one above it.

    `theme.STAMP_X` rather than a fresh literal: it is the register's stamp
    margin width, so the sheet's one indent sits on the same measure the other
    view's left edge does. Spacing only — no bracket, no leading mark, no lighter
    rule, no smaller type.
    """
    return _figure(figure, indent=theme.STAMP_X)


def _figure_note(text: str) -> rx.Component:
    """The sentence under a figure that its label cannot carry on its own.

    Used once, under the completion figure. `FIGURE_COMPLETION_LABEL` states what
    the number counts; this states why it is not an answer rate. Two elements,
    two jobs.

    `FONT_BODY` because it is prose, and PRD-006 Section 6.1 reserves the reading
    face for exactly "the two or three explanatory lines that state a scope".

    It carries **no rule of its own**, where every figure above it does. The note
    is the last thing in its block, and the next block's `border_top` already
    draws that boundary — a hairline here put two lines a few pixels apart doing
    one job. This is the accessory the **frontend-design** skill's last look in
    the mirror takes off.
    """
    return rx.box(
        text,
        font_family=theme.FONT_BODY,
        font_size=theme.TEXT_DATA,
        line_height="1.6",
        color=theme.MUTE,
        max_width=theme.MEASURE,
        padding="0.75rem 0",
        padding_left=theme.STAMP_X,
        width="100%",
    )


def _block(heading: str, *children) -> rx.Component:
    """One of the sheet's three groups, under a heading and a rule.

    A heading, not a card title: PRD-006 Section 6.1 sets the figures "as a ruled
    list, not a grid of cards", so the group is bounded by a rule above it and by
    nothing else — no border, no fill, no radius.

    Set at `TEXT_MICRO` in `FONT_DISPLAY` and tracked out, the same treatment
    `register.py:_head_cell` gives a column head: both are signposts over data,
    and giving them one treatment is what makes them read as the same kind of
    thing across the two views.
    """
    return rx.box(
        rx.box(
            heading,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_MICRO,
            font_weight="600",
            letter_spacing="0.12em",
            text_transform="uppercase",
            color=theme.MUTE,
            padding_bottom="0.5rem",
        ),
        *children,
        border_top=f"1px solid {theme.RULE}",
        padding_top="0.75rem",
        margin_top="2rem",
        width="100%",
    )


def _scope_note() -> rx.Component:
    """The one prose line on the sheet, and PRD-006 Risk 4's direct mitigation.

    It names the difference between the two windows outright, so `3,180` here
    beside 100 rows on the register reads as two scopes rather than as a
    contradiction. It sits above the figures because that is the reading it has
    to prevent, and a note under the sheet arrives after the misreading.
    """
    return rx.box(
        admin_copy.SUMMARY_SCOPE_NOTE,
        font_family=theme.FONT_BODY,
        font_size=theme.TEXT_DATA,
        line_height="1.6",
        color=theme.MUTE,
        max_width=theme.MEASURE,
    )


def _empty_summary() -> rx.Component:
    """Nothing has been recorded, so there is nothing to total.

    The panel is re-declared here rather than imported from
    `register.py:_empty_panel`, for the reason `admin_copy.py` re-declares the
    wordmark and `register.py` re-declares the stamp shape: the two views do not
    reach into each other, and a shared private helper is the first thread of
    that coupling.

    It says why rather than showing nine dashes, and it ends in the action
    available from it — the skill's "an empty screen is an invitation to act".
    The action named is **Refresh**, which is the masthead's control (STORY-017),
    so no second button is declared here to compete with it.

    No card, no illustration, no centring: an empty state is exactly where those
    are the template answer (PRD-006 Risk 6), and the sheet is read down its left
    edge like everything else on this console.
    """
    return rx.box(
        rx.box(
            admin_copy.EMPTY_SUMMARY_TITLE,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            letter_spacing="-0.01em",
            color=theme.INK,
        ),
        rx.box(
            admin_copy.EMPTY_SUMMARY_BODY,
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


def _sheet() -> rx.Component:
    """The nine figures, in PRD-006 Section 6.1's three blocks.

    The order is the section's, not a preference: the counts first, with the two
    blocked figures indented beneath the total they are a subset of; then the
    who/what facts, "because they answer a different kind of question than the
    counts do"; then "PII telemetry closes the sheet".

    The completion figure sits with the counts rather than in a block of its own:
    it is a count of the same rows, and separating it would suggest it measures
    something the other three do not touch.
    """
    return rx.box(
        _block(
            admin_copy.SUMMARY_COUNTS_HEADING,
            _figure(AdminState.total_figure),
            rx.foreach(AdminState.blocked_figures, _indented_figure),
            _figure(AdminState.completion_figure),
            _figure_note(admin_copy.FIGURE_COMPLETION_NOTE),
        ),
        _block(
            admin_copy.SUMMARY_WHO_HEADING,
            rx.foreach(AdminState.who_figures, _figure),
        ),
        _block(
            admin_copy.SUMMARY_PII_HEADING,
            rx.foreach(AdminState.pii_figures, _figure),
        ),
        width="100%",
    )


def _sheet_body() -> rx.Component:
    """The sheet, or the line saying there is nothing to total.

    `rx.match` over `AdminState.summary_state` rather than nested `rx.cond`s, for
    the reason `register.py:_register_body` records: the precedence a failed read
    turns on is then a Python function a unit test can call.

    The fault arm renders **the sheet**, not a panel. `FAULT_MESSAGE_TEMPLATE`
    promises "Nothing on screen has changed", so the figures from the last good
    read stay standing and STORY-017 hangs its panel above them. An empty *sheet*
    under a fault panel would be the misreading PRD-006 Section 4 forbids.

    The default arm is the sheet too, and the direction is deliberate: an
    unrecognised state renders the record rather than a claim of emptiness.
    """
    return rx.match(
        AdminState.summary_state,
        (SUMMARY_STATE_EMPTY, _empty_summary()),
        (SUMMARY_STATE_FAULT, _sheet()),
        (SUMMARY_STATE_FIGURES, _sheet()),
        _sheet(),
    )


def summary() -> rx.Component:
    """The summary view: the scope note over the tally sheet.

    `min_height="0"` on the column and on the scroll container is what makes the
    sheet scroll rather than the page — a flex child will not shrink below its
    content without it, the same requirement `register()` carries.

    The sheet is width-bounded rather than centred: the console is read down its
    left edge, and a centred column would be a card without a border.

    The refreshed stamp sits under the scope note, which is this sheet's
    counterpart to the register's scope column — the same reading order, the same
    line. It is `admin_shell`'s component rather than a second declaration here,
    so the two views state the refresh identically without either reaching into
    the other, and the verb stays the control's.
    """
    return rx.vstack(
        rx.box(
            _scope_note(),
            rx.box(refreshed_stamp(), margin_top="0.35rem"),
            _sheet_body(),
            max_width=_SHEET_MAX,
            width="100%",
        ),
        class_name="hx-scroll",
        overflow_y="auto",
        flex="1",
        min_height="0",
        width="100%",
        spacing="0",
        align="start",
        padding="1.5rem",
    )
