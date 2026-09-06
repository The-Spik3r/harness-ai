"""The session rail: a shelf of conversations, and the spine marking the open one.

The chat's one new surface, and the whole of PRD-008's design budget. Its single
job is stated in PRD Section 6.1 and everything below is measured against it:
*get me back into the right one, and get out of the way*.

**The signature — the spine.** PRD Section 6.1, verbatim: "The active session is
marked by a solid vertical mark in `SPINE` on the left edge of its row, and
nothing else: no fill, no rounded highlight, no bold. It is `RAIL_X` / `GLYPH` /
`SPINE` — the chat's own rail and PRD-006's stamp margin — appearing a third
time, at a third scale. Three surfaces, one structural device, each time encoding
*which one of these is the one*." The three tokens are reused **by name**, never
re-declared at the same values: `theme.py` records that "SESSION_RAIL_MARK_W
beside GLYPH would be a third device wearing the second one's clothes", and
`tests/test_admin_palette.py` already pins `STAMP_X is RAIL_X` by identity for
the register's half of the same claim.

**What this surface refuses.** PRD Section 6.1, verbatim: "The template answer is
the assistant-app sidebar: a dark panel, rounded pill rows, a hover-revealed
kebab menu, relative timestamps under every title, and a bright 'New chat' button
at the top... The chat surface is a light, ruled, hairline record; a dark
pill-shaped panel bolted to its left edge would be the one element on screen
belonging to a different product." So: no panel, no pill, no fill on the active
row, no accent on the control, no icon, and no verdict ink anywhere — "a rail row
is not a verdict and must not borrow one". The only lines drawn are the rail's
own right edge and the hairline between rows. PRD Risk 6 makes each of those a
test rather than a matter of review (STORY-020).

**Nothing here is hover-only.** The rename and delete affordances are real
`<button>`s, present in the DOM and in tab order at every row, which is both the
story's accessibility requirement and half of the kebab-menu refusal above.

**This module reads fields; it does not compute.** `ChatSessionSummary` carries
three, and `activity_info` was humanized in Python precisely because component
functions only ever see Vars and datetime math cannot run at render. The rail
does not sort either: `ChatState.sessions` is `list_for`'s `ORDER BY updated_at
DESC` output and `_promote_session` maintains it, so newest-activity-first is the
state's guarantee, asserted there and not re-derived here.

**Type follows PRD Section 6.1**, verbatim: "`FONT_DISPLAY` at `TEXT_DATA` for
session titles, `FONT_DATA` at `TEXT_TAG` for the activity time. Titles are set in
the display face rather than the body serif because they are *labels on a shelf*,
not prose." `FONT_BODY` appears twice, on the two sentences that are prose — the
empty invitation and the delete confirmation — and nowhere else.

**Three states, and their order is load-bearing.** A read that fails leaves
`sessions` empty *and* `sessions_error` set, so both conditions are true at once
on that path and only the branch order tells them apart. The fault check is
therefore outermost: an empty list rendered for a failed read would say "you have
no chats" to someone who has thirty, which is the conflation PRD-006's register
was warned about for its own empty state.

**No `rx.el.style(theme.GLOBAL_CSS)` here.** `chat_ui.py`'s `index()` already
carries the stylesheet, and a second copy on one page is the mistake PRD-006's
admin components were told not to make. This module depends on it for one thing:
the global `:focus-visible` outline, which is the whole of the keyboard answer
below and which no local `outline` or `box_shadow` may take back.
"""

import reflex as rx

from app.config import settings
from chat_ui import copy, theme
from chat_ui.state import ChatState

# The rail's inner rhythm. Not `theme.py`'s business: STORY-017 declared the
# three tokens the rail is measured by -- its width, its row height and its
# gutter -- and these are paddings expressed in terms of that gutter, the way
# `register.py` sets its own cell padding inline.
_ROW_PAD_Y = "0.45rem"


def _is_active(row) -> rx.Var:
    """Whether this row is the open chat.

    Compared against `ChatState.active_session_id`, which is a client-visible
    var and untrusted (PRD Risk 3) -- but nothing here trusts it. It decides
    which row draws a mark, and the server re-checks ownership on every read
    regardless of what the client sets it to.
    """
    return ChatState.active_session_id == row.session_id


def _spine(row) -> rx.Component:
    """**The signature.** One solid mark in `SPINE`, on the active row only.

    The margin is always there and the mark is not, which is the whole device:
    a column that marked every row would be a column of marks, not the answer to
    *which one of these is the one*. `register.py:_stamp_margin` states the same
    sentence about its own stripe of exceptions.

    `align_self="stretch"` rather than a fixed height: the mark is the row's
    full height, so it reads as a spine on a shelf rather than as a bullet
    beside a title.

    **No `border_radius` at all**, where `register.py:_stamp` softens its 9px
    square by 1px. On a mark that is nine pixels wide and forty-eight tall the
    rounding is invisible, so it buys nothing and costs the one thing worth
    having here: the rail then renders exactly one radius, `theme.RADIUS`, and
    STORY-020's guard against the pill can say so without an exception carved
    into it for the signature itself. The skill's "remove one accessory",
    applied to the accessory on the boldest element.
    """
    return rx.box(
        rx.cond(
            _is_active(row),
            rx.box(
                width=theme.GLYPH,
                align_self="stretch",
                background_color=theme.SPINE,
            ),
            rx.fragment(),
        ),
        width=theme.RAIL_X,
        flex_shrink="0",
        align_self="stretch",
        display="flex",
        align_items="stretch",
        justify_content="flex-start",
    )


def _row_open_button(row) -> rx.Component:
    """The row itself: title over activity time, and the whole of it clickable.

    A real `<button>`, which is the whole of the keyboard answer -- it takes
    focus in document order and fires on both Enter and Space with no key
    handling here, and `theme.GLOBAL_CSS`'s `:focus-visible` rule gives it the
    ring. `type="button"` is explicit for the reason `admin_shell.py`'s sign-out
    records: an unqualified `<button>` defaults to submit.

    **`font_weight` is fixed at 500 for every row, active or not.** Bolding the
    open chat is the first of PRD Section 6.1's four named refusals ("no fill,
    no rounded highlight, no bold"), and it is the one that arrives looking like
    an improvement.

    `_hover` is `HOVER` on every row for the same reason: it is a pointer
    affordance saying *this is clickable*, not a mark saying *this is the one*.
    Giving the active row a permanent `HOVER` ground would be the "rounded
    highlight" refusal minus the rounding.

    The title is truncated with an ellipsis rather than wrapped: `SESSION_RAIL_W`
    is sized for roughly 34 characters and a two-line title would break the row
    rhythm the activity line sits on.
    """
    return rx.el.button(
        rx.box(
            row.title,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            font_weight="500",
            color=theme.INK,
            line_height="1.35",
            width="100%",
            overflow="hidden",
            text_overflow="ellipsis",
            white_space="nowrap",
        ),
        rx.box(
            row.activity_info,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_TAG,
            color=theme.MUTE,
            line_height="1.35",
        ),
        on_click=ChatState.select_session(row.session_id),
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        border_radius=theme.RADIUS,
        padding=f"{_ROW_PAD_Y} 0",
        width="100%",
        min_width="0",
        text_align="left",
        display="block",
        _hover={"background_color": theme.HOVER},
        custom_attrs={"aria-current": rx.cond(_is_active(row), "true", "false")},
    )


def _action_button(label: str, on_click) -> rx.Component:
    """A row's quiet verb. Rename, Delete, Keep chat, Retry — all of them.

    One helper for every control in the rail that is not the row itself, so
    none of them can drift into a fill or an accent one at a time (PRD Risk 6:
    "the drift arrives one reasonable component at a time").

    **No `display` gated on `_hover`.** The kebab menu PRD Section 6.1 refuses
    is exactly this control hidden until the pointer arrives, and hiding it
    would take it out of the tab order for the reader who needs it most.

    Colour moves on hover and nothing else does: `MUTE` to `INK`, both of which
    `tests/test_contrast.py` already clears against `PAPER` and `HOVER`.
    """
    return rx.el.button(
        label,
        on_click=on_click,
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_TAG,
        letter_spacing="0.04em",
        line_height="1",
        color=theme.MUTE,
        _hover={"color": theme.INK},
    )


def _row_actions(row) -> rx.Component:
    """Rename and delete, always present and always focusable.

    Both words are the ones their flows keep: `SESSION_RENAME_LABEL` opens a
    field labelled for renaming, and `SESSION_DELETE_CONFIRM_LABEL` is this
    affordance *and* the confirming button below it -- `copy.py` records that
    the repetition is deliberate ("the affordance, this confirmation and nothing
    else all say Delete. Not Remove").
    """
    return rx.hstack(
        _action_button(
            copy.SESSION_RENAME_LABEL, ChatState.begin_rename(row.session_id, row.title)
        ),
        _action_button(
            copy.SESSION_DELETE_CONFIRM_LABEL, ChatState.ask_delete(row.session_id)
        ),
        spacing="3",
        align="center",
        padding_bottom=_ROW_PAD_Y,
    )


def _rename_field(row) -> rx.Component:
    """The title, become editable in place.

    Set in the face and size of the title it replaces, so renaming does not move
    the row or change its rhythm.

    **Enter commits and blur cancels**, and there is no save button. The three
    are one decision: a save button would have to be *clicked*, and clicking it
    blurs the field first, so a blur that committed would make the cancel button
    commit too and a blur that cancels would make the save button unreachable.
    Enter for the destructive-free commit and blur for the discard is the only
    pairing of the three that has no trap in it. Escape is deliberately not
    bound: the pinned Reflex declares no key-info spec for `on_key_down`, so a
    handler reading `key` would be an unverified API on the one interaction that
    must not silently do nothing.

    An empty title is refused silently by `rename_session`, per its own
    docstring, so there is no error arm here and no string for one.
    """
    return rx.form(
        rx.input(
            value=ChatState.rename_draft,
            on_change=ChatState.set_rename_draft,
            on_blur=ChatState.cancel_rename,
            placeholder=copy.SESSION_RENAME_PLACEHOLDER,
            auto_focus=True,
            class_name="hx-field",
            custom_attrs={
                "autoComplete": "off",
                "autoCorrect": "off",
                "aria-label": copy.SESSION_RENAME_LABEL,
            },
            width="100%",
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            color=theme.INK,
            padding="0",
        ),
        on_submit=ChatState.commit_rename,
        width="100%",
        padding=f"{_ROW_PAD_Y} 0",
    )


def _delete_confirm(row) -> rx.Component:
    """The question, asked in the row it is about, and asked once.

    **Not `rx.alert_dialog` and not `rx.window_alert`**, both of which exist in
    the pinned Reflex. `delete_session`'s docstring reserved this decision for
    this module -- "a state handler that popped its own dialog would put the
    flow's gate in a layer the component cannot replace" -- and a modal would
    arrive with an overlay, a radius and a red destructive button, which is
    three of PRD Risk 6's named drifts in one component. In place, the thing
    being deleted stays on screen while the reader decides.

    The sentence names the chat and says the record is kept, because that is the
    fact a user in an audited system will actually want (PRD Section 9). It is
    the only prose in a row, so it takes `FONT_BODY`.

    **Neither door carries a verdict ink.** A red Delete is good practice
    everywhere else and is refused here: the seven inks mean something in the
    transcript, and PRD Section 6.1 keeps them there. The confirmation's weight
    is that it is a sentence naming the chat, not that it is coloured.

    `copy.SESSION_DELETE_CONFIRM_TEMPLATE.format(title=...)` is given a Var, and
    that is the supported form: Reflex resolves the marker it embeds when the
    result reaches a component, producing the same JS concatenation an f-string
    would. `copy.py` records the same, and it is exercised in
    `tests/test_session_rail.py` rather than assumed.
    """
    return rx.box(
        rx.box(
            copy.SESSION_DELETE_CONFIRM_TEMPLATE.format(title=row.title),
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            line_height="1.5",
            color=theme.INK,
        ),
        rx.hstack(
            _action_button(
                copy.SESSION_DELETE_CONFIRM_LABEL,
                ChatState.delete_session(row.session_id),
            ),
            _action_button(copy.SESSION_DELETE_CANCEL_LABEL, ChatState.cancel_delete),
            spacing="3",
            align="center",
            margin_top="0.4rem",
        ),
        width="100%",
        min_width="0",
        padding=f"{_ROW_PAD_Y} 0",
        custom_attrs={"role": "alertdialog"},
    )


def _row(row) -> rx.Component:
    """One shelf position: the spine's margin, then the row's one mode.

    Three modes, and a row is in exactly one: confirming a delete, renaming, or
    being a row. `ChatState` keeps both mode vars keyed on `session_id` rather
    than on list position, because `rx.foreach` compiles to a `.map()` keyed by
    index and `_promote_session` reorders this list on every send -- an
    index-held mode would follow whichever chat landed in that slot, and an
    armed delete confirmation that moved to another row is the worst version of
    that bug.

    The hairline is `RULE_SOFT` and there is no other line, no card and no
    radius on the row. `register.py` draws its hundred rows the same way.
    """
    return rx.box(
        _spine(row),
        rx.box(
            rx.cond(
                ChatState.confirming_delete_id == row.session_id,
                _delete_confirm(row),
                rx.cond(
                    ChatState.renaming_session_id == row.session_id,
                    _rename_field(row),
                    rx.fragment(_row_open_button(row), _row_actions(row)),
                ),
            ),
            flex="1",
            min_width="0",
            display="flex",
            flex_direction="column",
            align_items="flex-start",
        ),
        display="flex",
        align_items="stretch",
        width="100%",
        min_height=theme.SESSION_RAIL_ROW_H,
        border_bottom=f"1px solid {theme.RULE_SOFT}",
    )


def _new_chat_control() -> rx.Component:
    """**New chat**, and what it produces is a chat.

    PRD Section 6.1 refuses "a bright 'New chat' button at the top", so this is
    `INK` type on the rail's own `PAPER` inside a hairline, not the composer's
    inverted `INK` fill. It is the one control in the rail that is not a row, so
    it takes a border to say so and nothing more.

    No icon and no "+": PRD Section 8 admits no icon set, and a "+" would be a
    user-facing string with no home in `copy.py` -- the reasoning
    `admin_shell.py` records for using `border_left` instead of a "|".
    """
    return rx.el.button(
        copy.SESSION_NEW_CHAT_LABEL,
        on_click=ChatState.new_chat,
        type="button",
        cursor="pointer",
        width="100%",
        text_align="left",
        padding="0.5rem 0.6rem",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_DATA,
        font_weight="600",
        letter_spacing="0.04em",
        color=theme.INK,
        background="none",
        border=f"1px solid {theme.RULE}",
        border_radius=theme.RADIUS,
        _hover={"background_color": theme.HOVER},
    )


def _scope_line() -> rx.Component:
    """"50 most recent of 212" — the window, stated against the whole shelf.

    PRD-006 Risk 4 is why a cap is never silent, and `copy.py` applies it here:
    "a rail that quietly stops at CHAT_SESSION_LIMIT would read as a complete
    list of the user's chats." `ChatState.rail_scope` returns `""` when nothing
    is being withheld, so the line appears only when there is a window to state
    — a scope on a complete list would state a window that is not one.
    """
    return rx.cond(
        ChatState.rail_scope != "",
        rx.box(
            ChatState.rail_scope,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_TAG,
            color=theme.MUTE,
            padding=f"{_ROW_PAD_Y} 0",
        ),
        rx.fragment(),
    )


def _empty_state() -> rx.Component:
    """No sessions yet — an invitation, never a census.

    PRD Section 6.1: "the empty rail reads as an invitation to start one rather
    than as a report that none exist", which is the frontend-design skill's "an
    empty screen is an invitation to act" applied to this surface. `copy.py`
    names the sentence this pair exists to refuse: "No chats yet."

    It repeats no control. **New chat** is already at the top of the rail, and a
    second button for the same action here would be the skill's "nothing quietly
    does double duty" -- and would also be wrong, since creation is lazy and the
    first chat is made by *sending*, which is what the body says.
    """
    return rx.vstack(
        rx.box(
            copy.SESSION_RAIL_EMPTY_TITLE,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            font_weight="600",
            color=theme.INK,
        ),
        rx.box(
            copy.SESSION_RAIL_EMPTY_BODY,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            line_height="1.5",
            color=theme.MUTE,
        ),
        spacing="1",
        align="start",
        width="100%",
        padding=f"{_ROW_PAD_Y} 0",
    )


def _fault_state() -> rx.Component:
    """A read that failed, named — never a silently empty list.

    The distinction this rail exists to keep: an empty list here would read as
    "you have no chats" to someone who has thirty, which is why the branch order
    in `_body` puts this first.

    **`ChatState.sessions_error` is deliberately not rendered.** It holds
    `str(exc)` from a `ChatSessionError` raised as f"{operation} failed: {exc}",
    so its text is the storage layer describing itself. `copy.py` fixes the rule:
    the rail "renders these two constants and treats `sessions_error` as the
    trigger, not as the text", because the skill's "name things by what people
    control and recognize, never by how the system is built" applies hardest to
    an error.

    The copy does not apologize and it is not vague: it names the read that
    failed, states that the screen did not move, and gives the action. The action
    spells itself with the word its control carries -- `copy.RETRY_LABEL`,
    reused rather than re-declared, the same way `admin_shell.fault_panel` reuses
    the console's own refresh control.

    `role="alert"` for the reason that panel takes it: the list did not change,
    so nothing else on screen announces that the read failed.
    """
    return rx.vstack(
        rx.box(
            copy.SESSION_RAIL_FAULT_TITLE,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            font_weight="600",
            color=theme.INK,
        ),
        rx.box(
            copy.SESSION_RAIL_FAULT_BODY,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            line_height="1.5",
            color=theme.MUTE,
        ),
        rx.box(_action_button(copy.RETRY_LABEL, ChatState.retry_sessions)),
        spacing="1",
        align="start",
        width="100%",
        padding=f"{_ROW_PAD_Y} 0",
        custom_attrs={"role": "alert"},
    )


def _body() -> rx.Component:
    """The three states, in the one order that keeps them distinct.

    PRD Section 4 lists them: "no sessions yet, sessions listed, and a read that
    failed." A failed read sets `sessions_error` **and** leaves `sessions`
    empty, so the first two conditions are simultaneously true on that path and
    only this order tells them apart. Reversing it is the conflation PRD-006's
    register was warned about, and it is silent when it happens.
    """
    return rx.cond(
        ChatState.sessions_error != "",
        _fault_state(),
        rx.cond(
            ChatState.sessions,
            rx.box(rx.foreach(ChatState.sessions, _row), width="100%"),
            _empty_state(),
        ),
    )


def session_rail() -> rx.Component:
    """The rail — or nothing at all, when this deployment keeps no history.

    **The one place in `chat_ui/` that names `CHAT_HISTORY_ENABLED`, and the
    reason it is allowed to.** PRD Section 6 asks for two things in one
    sentence: "the service returns empty lists and writes nothing, and the rail
    renders as absent. No caller branches on the flag." The second clause
    governs the *data* path, and nothing here violates it — every read still
    goes through `app/services/chat_sessions.py` and still cannot tell "off"
    from "none yet", which is what `list_for`'s docstring protects.

    But absence is not a data answer, and no empty list can produce it. With
    the flag off the service returns `[]`, which is the *invitation* state —
    so a rail that did not ask this question told a user with thirty saved
    chats "Start your first chat", and promised that the next prompt would
    appear here when nothing would ever be written. That was observed on
    screen, not theorised: it is the failure this branch exists to remove.

    So the question is asked exactly once, here, at the surface, where absence
    is the only thing a component can render. It is not asked per row, it is
    not asked in `ChatState` (whose own guard,
    `test_chat_state_never_names_the_history_flag`, still holds and is
    untouched), and it is not laundered through a service accessor to dodge the
    glob — `tests/test_chat_sessions.py`'s allowlist names this file
    deliberately, with the same reasoning recorded beside it.

    An accessor on `chat_sessions` was the first choice and was rejected: it
    would have to take no `Identity`, which breaks
    `test_every_service_function_takes_an_identity_first` — PRD Risk 2's
    "the rule lives in the signature". Punching a hole in the ownership guard
    to make room for a configuration helper is the worse trade.

    Below the branch: `PAPER` against the transcript's `CARD`, separated by one
    `RULE` hairline — PRD Section 6.1's palette for this surface, and no new ink
    of any kind. The grounds do the separating that a panel would otherwise do.

    It scrolls in its own container rather than with the page, so thirty chats
    never push the composer off screen; `hx-scroll` is `theme.py`'s existing
    scrollbar treatment, reused so the rail's scrollbar matches the
    transcript's. The layout around it — where this column sits, its collapse at
    a narrow viewport, and reclaiming its width when this function returns
    nothing — is STORY-019's.
    """
    if not settings.CHAT_HISTORY_ENABLED:
        # Absent, not empty and not disabled. `rx.fragment()` renders no node,
        # so the flex row STORY-019 builds has nothing to lay out and no gap to
        # reserve. A `display: none` box would still be in the DOM for a screen
        # reader to find.
        return rx.fragment()

    return rx.box(
        _new_chat_control(),
        _scope_line(),
        _body(),
        class_name="hx-scroll",
        display="flex",
        flex_direction="column",
        width=theme.SESSION_RAIL_W,
        flex_shrink="0",
        height="100%",
        overflow_y="auto",
        overflow_x="hidden",
        padding=theme.SESSION_RAIL_GUTTER,
        background_color=theme.PAPER,
        border_right=f"1px solid {theme.RULE}",
        custom_attrs={"aria-label": copy.SESSION_RAIL_SHOW_LABEL},
    )
