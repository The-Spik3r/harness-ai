"""Everything around the transcript: the session gate, the header, the empty
state, and the layout that holds the rail beside the transcript.

The header is a masthead, not a toolbar: the wordmark sits in the display face
against a hairline rule, and the session facts (who is sending, which model) are
set in the data face on the right — the same split the entries use between
prose and evidence.

**The shell's shape (STORY-019).** A full-width masthead over a row:

    header()                          full width, flex_shrink 0
    shell_body()   flex 1  ->  rail_slot() | transcript_column()
                                                 message_list() / empty_state()
                                                 chat_input()

PRD-008 Section 6.1 fixes the arrangement: "the rail is a fixed-width column at
the left, under the existing masthead, so the header keeps spanning the full
width and stays the one place the session's facts (who is sending, which model)
live."

The composer sits inside the transcript's column rather than in a band beneath
both, which is this story's one departure from Section 6.1's ASCII wireframe.
`transcript_column()` states the measurement that decided it and the reason it
is the better structure; the story's report records it as a deviation.

**The collapse is this module's, not the rail's.** `session_rail()` sets its own
width and scrolls in its own container; it knows nothing about a viewport, which
its closing docstring assigns here by name. So `rail_slot()` wraps it and
animates *around* it: the rail's contents keep their width and never reflow
while the column closes.

**One transition, and it is the collapse.** PRD Section 6.1: "One transition:
the rail's collapse at a narrow viewport, respecting `prefers-reduced-motion`.
Switching sessions does not animate." Nothing in `shell_body()` or below it
carries an animation, and `theme.GLOBAL_CSS`'s reduced-motion block already
neutralises the one transition through its `* { transition-duration: 0.01ms }`
rule — so this module adds no CSS of its own. That is deliberate twice over: the
frontend-design skill warns that "it's easy to generate CSS classes that cancel
each other out... often with paddings/margins between sections", and every rule
here is an inline style prop that Reflex scopes to one element instead.
"""

import reflex as rx

from chat_ui import copy, theme
from chat_ui.components.chat import chat_input, message_list
from chat_ui.components.session_rail import session_rail
from chat_ui.config import MODEL_ALLOWLIST
from chat_ui.state import ChatState

# The rail's collapse. Written inline, as `chat.py` and `login_gate()` below
# already write their durations inline ("background-color 120ms ease"):
# `theme.py`'s stated scope is "every colour and size", and a duration is
# neither. The breakpoint itself *is* a size and *is* in theme.py --
# `SESSION_RAIL_COLLAPSE_W`, declared by STORY-017 with its reasoning intact.
_RAIL_COLLAPSE_MS = "160ms"

# The slot's element id, so the masthead's disclosure can name what it controls.
# On the slot rather than on the rail: `session_rail()` returns `rx.fragment()`
# when this deployment keeps no history, and an `aria-controls` pointing at an
# id that is not in the document would be a broken reference on exactly the
# configuration that has nothing to disclose.
_RAIL_SLOT_ID = "session-rail"


def _rail_is_present() -> bool:
    """Whether `session_rail()` renders anything at all.

    Asked of the *component*, not of the configuration. `shell.py` may not name
    `CHAT_HISTORY_ENABLED` — it is asked exactly once in the whole of
    `chat_ui/`, at the top of `session_rail()` — and it should not want to: the
    question a disclosure control needs answered is "is there a rail to
    reveal", which stays the right question however that rail comes to be
    absent.

    An absent rail is `rx.fragment()` with no children, so the component's own
    output is the answer. Found on screen, not reasoned about: with
    `CHAT_HISTORY_ENABLED=false` at a narrow viewport the masthead showed a
    **Chats** control that revealed a column of nothing — a control for
    nothing, which is precisely the accessory the skill's mirror pass removes.
    """
    return bool(session_rail().children)


def _label(text: str) -> rx.Component:
    return rx.box(
        text,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_TAG,
        letter_spacing="0.08em",
        text_transform="uppercase",
        color=theme.MUTE,
        white_space="nowrap",
    )


def model_selector() -> rx.Component:
    """Curated allowlist from config.py (STORY-016) — a free-text model would
    reach OpenRouter and fail in a way the reader cannot act on."""
    return rx.hstack(
        _label(copy.SHELL_MODEL_SLOT_LABEL),
        rx.select(
            MODEL_ALLOWLIST,
            value=ChatState.selected_model,
            on_change=ChatState.set_selected_model,
            size="1",
            variant="surface",
            color_scheme="gray",
            id="model-selector",
        ),
        align="center",
        spacing="2",
    )


def rail_disclosure() -> rx.Component:
    """**Chats** — the control that brings the rail back at a narrow viewport.

    Shown *only* below `theme.SESSION_RAIL_COLLAPSE_W`. At or above it the rail
    is always there, so a control to show it would be a control for nothing —
    and an inert word in the masthead is the accessory the skill's mirror pass
    exists to remove.

    **In the masthead, not above the transcript.** That keeps the header the one
    full-width band (PRD Section 6.1) and it settles the tab order for free:
    document order is masthead → rail → transcript → composer, which is the
    order the story asks for, with no `tabindex` anywhere on the page.

    **The label does not flip.** "Chats" whether the rail is open or closed;
    `aria-expanded` carries the state to a screen reader, and it is the only
    thing that changes. `copy.py` declares exactly one string for this control
    and that is not an oversight — the frontend-design skill's "an action keeps
    the same name through the whole flow" is better served by one word that
    always names the same thing than by a pair that renames it on click.

    **No icon and no glyph.** PRD Section 8 admits no icon set, and a "☰" or a
    "+" would be a user-facing string with no home in `copy.py` — the reason
    `admin_shell.py` records for using `border_left` instead of a "|". And no
    accent: PRD Section 6.1 refuses "a bright 'New chat' button at the top", and
    the same refusal governs the only other control this surface gains.

    **Absent entirely when there is no rail.** With `CHAT_HISTORY_ENABLED=false`
    the rail does not exist at any width, so a control to reveal it would be a
    word in the masthead that reveals a column of nothing. `rx.fragment()`
    rather than a hidden node, for the reason `session_rail()` gives about
    itself: absent, not disabled.

    The divider travels with it, on the wrapper, so the masthead does not keep a
    hairline separating the wordmark from nothing once the control is gone.
    """
    if not _rail_is_present():
        return rx.fragment()

    return rx.box(
        rx.el.button(
            copy.SESSION_RAIL_SHOW_LABEL,
            on_click=ChatState.toggle_rail,
            type="button",
            cursor="pointer",
            background="none",
            border="none",
            padding="0",
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            color=theme.MUTE,
            text_decoration="underline",
            text_underline_offset="3px",
            _hover={"color": theme.INK},
            custom_attrs={
                "aria-expanded": rx.cond(ChatState.rail_expanded, "true", "false"),
                "aria-controls": _RAIL_SLOT_ID,
            },
        ),
        display=rx.breakpoints(
            custom={
                "initial": "flex",
                theme.SESSION_RAIL_COLLAPSE_W: "none",
            }
        ),
        align_items="center",
        padding_left="0.875rem",
        margin_left="0.875rem",
        border_left=f"1px solid {theme.RULE}",
    )


def header() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.box(
                copy.SHELL_HEADER_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.0625rem",
                font_weight="700",
                letter_spacing="0.16em",
                color=theme.INK,
            ),
            rx.hstack(
                rx.box(
                    width="6px",
                    height="6px",
                    border_radius="1px",
                    background_color=theme.INK_CLEAR,
                ),
                _label(copy.SHELL_HEADER_BADGE),
                align="center",
                spacing="2",
                padding_left="0.875rem",
                margin_left="0.875rem",
                border_left=f"1px solid {theme.RULE}",
            ),
            rail_disclosure(),
            align="center",
            spacing="0",
        ),
        rx.hstack(
            model_selector(),
            rx.hstack(
                _label(copy.SHELL_USER_LABEL),
                rx.box(
                    ChatState.user_id,
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_DATA,
                    font_weight="500",
                    color=theme.INK,
                ),
                rx.el.button(
                    copy.SHELL_LOGOUT_LABEL,
                    on_click=ChatState.logout,
                    type="button",
                    cursor="pointer",
                    background="none",
                    border="none",
                    padding="0",
                    font_family=theme.FONT_DISPLAY,
                    font_size=theme.TEXT_DATA,
                    color=theme.MUTE,
                    text_decoration="underline",
                    text_underline_offset="3px",
                    _hover={"color": theme.INK},
                ),
                align="center",
                spacing="2",
                padding_left="1rem",
                margin_left="0.25rem",
                border_left=f"1px solid {theme.RULE}",
            ),
            class_name="hx-header-meta",
            align="center",
            spacing="3",
        ),
        justify="between",
        align="center",
        width="100%",
        flex_wrap="wrap",
        row_gap="0.75rem",
        padding="0.9rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        background_color=theme.CARD,
        flex_shrink="0",
    )


def _legend_row(ink: str, text: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            width=theme.GLYPH,
            height=theme.GLYPH,
            border_radius="1px",
            background_color=ink,
            flex_shrink="0",
            margin_top="0.15rem",
        ),
        rx.box(
            text,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_BODY,
            color=theme.MUTE,
            line_height="1.5",
        ),
        align="start",
        spacing="3",
    )


def empty_state() -> rx.Component:
    """An empty screen is an invitation to act — and here it doubles as the
    legend for the rail the transcript is about to fill."""
    return rx.box(
        rx.vstack(
            rx.box(
                copy.EMPTY_STATE_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.75rem",
                font_weight="600",
                letter_spacing="-0.02em",
                color=theme.INK,
            ),
            rx.box(
                copy.EMPTY_STATE_SUBTITLE,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_LEAD,
                line_height="1.6",
                color=theme.MUTE,
                max_width="34rem",
                margin_top="0.5rem",
            ),
            rx.vstack(
                _legend_row(theme.INK_CLEAR, copy.EMPTY_STATE_PII_FEATURE),
                _legend_row(theme.INK_DENIED, copy.EMPTY_STATE_SECURITY_FEATURE),
                _legend_row(theme.INK_HELD, copy.EMPTY_STATE_DEDUP_FEATURE),
                align_items="start",
                spacing="3",
                margin_top="1.75rem",
                padding_top="1.5rem",
                border_top=f"1px solid {theme.RULE}",
                width="100%",
                max_width="34rem",
            ),
            align_items="start",
            spacing="0",
            width="100%",
            max_width=theme.COLUMN_MAX,
            margin="0 auto",
        ),
        flex="1",
        width="100%",
        padding="3.5rem 1.5rem 2rem",
        overflow_y="auto",
    )


def rail_slot() -> rx.Component:
    """The column the rail sits in, and the whole of the collapse.

    `session_rail()` keeps its own `width`, `flex_shrink="0"` and `overflow_y`;
    this wrapper animates the space around it, so the rail's rows hold their
    measure while the column closes instead of reflowing to nothing.

    **`visibility`, not `display`, and not `opacity`.** Three properties could
    hide this column and only one of them does the job:

    - `display: none` cannot be transitioned, and the story asks for the
      collapse to *be* the surface's one transition.
    - `opacity: 0` transitions, but leaves every row button and its Rename and
      Delete in the tab order — a reader tabbing through a collapsed rail would
      cross a dozen invisible controls, which is the exact failure the story's
      focus-order criterion is written to catch.
    - `visibility: hidden` transitions **and** takes the subtree out of the tab
      order. It is the only one of the three that satisfies both.

    **Why the wide arm is unconditional.** Above `SESSION_RAIL_COLLAPSE_W` the
    map ignores `rail_expanded` entirely: there is room for both columns, so the
    rail is simply there. The var only decides anything below the breakpoint,
    which is why `rail_disclosure()` is itself absent above it.

    **`max_width`, not `width`, and that is what keeps the flag out of this
    file.** `session_rail()` returns `rx.fragment()` under
    `CHAT_HISTORY_ENABLED=false` — no node at all — so this box then wraps
    nothing. A declared `width` would reserve fifteen rems of blank column for
    it and undo the "absent, not empty" work STORY-018 did; asking the flag here
    to avoid that is not available either, because it may be named exactly once
    in the whole of `chat_ui/`, at the top of `session_rail()`
    (`tests/test_chat_sessions.py`'s allowlist, and
    `test_the_flag_is_named_once_and_only_at_the_surface`).

    So this column states no width of its own. It is a flex item sized by its
    content — the rail's own `SESSION_RAIL_W`, or nothing at all — and the
    breakpoint map only ever supplies a *cap*. An absent rail leaves a column of
    zero, and no configuration question had to be asked twice to get there.
    `max-width` transitions exactly as `width` would, so the collapse is
    unaffected.

    This box therefore declares no padding, no border and no background either:
    everything that could reserve space when the rail is gone is the rail's, and
    goes with it.

    `overflow="hidden"` so the closing column clips its contents rather than
    spilling them across the transcript for the length of the animation.
    """
    return rx.box(
        session_rail(),
        id=_RAIL_SLOT_ID,
        display="flex",
        flex_shrink="0",
        overflow="hidden",
        height="100%",
        max_width=rx.breakpoints(
            custom={
                "initial": rx.cond(ChatState.rail_expanded, theme.SESSION_RAIL_W, "0"),
                theme.SESSION_RAIL_COLLAPSE_W: theme.SESSION_RAIL_W,
            }
        ),
        visibility=rx.breakpoints(
            custom={
                "initial": rx.cond(ChatState.rail_expanded, "visible", "hidden"),
                theme.SESSION_RAIL_COLLAPSE_W: "visible",
            }
        ),
        transition=(
            f"max-width {_RAIL_COLLAPSE_MS} ease, visibility {_RAIL_COLLAPSE_MS} ease"
        ),
    )


def transcript_column() -> rx.Component:
    """The reading column: the transcript, or the invitation to start one.

    `min_width="0"` is not housekeeping — it is the whole of "the page body does
    not scroll horizontally". A flex item defaults to `min-width: auto` and
    refuses to shrink below its content, so one long unbroken token in a bubble
    would push this column wider than the row and take the page sideways with
    it.

    `min_height="0"` is the same rule on the other axis, and it is what makes
    `message_list()`'s `flex="1"` and `overflow-y` resolve against a definite
    height rather than growing the row.

    **No `max_width` here.** PRD Section 6.1's reading measure already lives on
    the two things this column holds — `message_list()` and `empty_state()` each
    set `max_width=theme.COLUMN_MAX, margin="0 auto"` — so the bubbles do not
    stretch into the width reclaimed when the rail collapses. A second clamp at
    this level would be the skill's "nothing quietly does double duty", and two
    centring rules on nested boxes is precisely the cancelling-margins failure
    it warns about.

    **The ground is `CARD`**, against the rail's `PAPER`. PRD Section 6.1 states
    the pairing outright: "The rail is `PAPER` ground against the transcript's
    `CARD`, separated by the existing `RULE`... The grounds do the separating
    that a panel would otherwise do." Until this story the transcript inherited
    `PAPER` from the page, which left the rail's hairline doing all of it —
    the observation STORY-018's report handed forward from the browser.
    `tests/test_contrast.py` already clears `INK` and `MUTE` on `CARD`, so the
    change introduces no new pairing.

    **The composer is in this column, not in a band beneath both.** PRD Section
    6.1's wireframe draws it spanning the full width, and it was built that way
    first and measured on screen: the composer centres its `COLUMN_MAX` on the
    *page* while the transcript centres on this *column*, so with a 15rem rail
    present the two were offset by half the rail — 120px of visible
    misalignment between a prompt and the reply above it.

    Two fixes existed. Padding the full-width band by the rail's width would
    have restated the collapse in a second place, animation included, to
    reproduce a centring this column already does. Moving the composer here
    needs nothing: it inherits the column's width, so it aligns by construction
    and stays aligned through the collapse.

    The second reason is the deciding one, and it is the skill's "structure is
    information". The composer types into *this transcript*: it is scoped to the
    active session exactly as the bubbles above it are. A band stretching under
    the rail says it belongs to the page, which is the one thing about it that
    is not true. Section 6.1's prose puts the rail "at the left, under the
    existing masthead" and says nothing about where the composer stops; the
    departure is from the wireframe's ASCII, not from the direction it sketches,
    and it is recorded in the story's report.
    """
    return rx.box(
        rx.cond(ChatState.has_messages, message_list(), empty_state()),
        chat_input(),
        display="flex",
        flex_direction="column",
        flex="1",
        min_width="0",
        min_height="0",
        height="100%",
        background_color=theme.CARD,
    )


def shell_body() -> rx.Component:
    """The middle band: the rail and the transcript, side by side.

    `spacing="0"`, because the separating is already done twice — by the rail's
    right-hand `RULE` hairline and by its `SESSION_RAIL_GUTTER`. A stack gap
    would be a third device competing with both, and `message_list()` sets
    `gap="0"` against the same temptation.

    `flex="1"` with `min_height="0"`: the row takes exactly the height the
    masthead and the composer leave, and its children scroll inside themselves
    instead of growing the page. That is what keeps the rail's overflow in its
    own container with thirty chats in it, and the composer where the reader
    left it.

    `overflow="hidden"` is the row's half of "no horizontal scroll on the body",
    and it is also what lets the slot's width animation clip cleanly instead of
    shoving the transcript sideways for 160ms.
    """
    return rx.hstack(
        rail_slot(),
        transcript_column(),
        spacing="0",
        align="stretch",
        width="100%",
        flex="1",
        min_height="0",
        overflow="hidden",
    )


def login_gate() -> rx.Component:
    """Full-page form collecting the session's access token before the chat
    opens. type="password" keeps the credential off-screen while typed -- the
    risk PRD-005 Risk 5 calls out is a role trusted from the client, not the
    token being visible in the input, but there is no reason to show it
    either."""
    return rx.center(
        rx.box(
            rx.box(
                copy.SHELL_HEADER_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.0625rem",
                font_weight="700",
                letter_spacing="0.16em",
                color=theme.INK,
            ),
            rx.box(
                copy.LOGIN_PROMPT_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.5rem",
                font_weight="600",
                letter_spacing="-0.02em",
                color=theme.INK,
                margin_top="1.75rem",
            ),
            rx.box(
                copy.LOGIN_PROMPT_BODY,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_BODY,
                line_height="1.6",
                color=theme.MUTE,
                margin_top="0.5rem",
            ),
            rx.form(
                rx.input(
                    id="user_id_input",
                    class_name="hx-field-boxed",
                    value=ChatState.token_input,
                    on_change=ChatState.set_token_input,
                    placeholder=copy.LOGIN_TOKEN_PLACEHOLDER,
                    type="password",
                    auto_focus=True,
                    custom_attrs={"autoComplete": "off", "autoCorrect": "off"},
                    width="100%",
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_BODY,
                    height="2.5rem",
                    border_radius=theme.RADIUS,
                    margin_top="1.5rem",
                ),
                rx.cond(
                    ChatState.login_error != "",
                    rx.box(
                        ChatState.login_error,
                        font_family=theme.FONT_DATA,
                        font_size=theme.TEXT_DATA,
                        color=theme.INK_DENIED,
                        margin_top="0.5rem",
                    ),
                    rx.fragment(),
                ),
                rx.box(
                    rx.el.button(
                        copy.LOGIN_SUBMIT_LABEL,
                        type="submit",
                        cursor="pointer",
                        width="100%",
                        height="2.5rem",
                        font_family=theme.FONT_DISPLAY,
                        font_size=theme.TEXT_BODY,
                        font_weight="600",
                        color=theme.PAPER,
                        background_color=theme.INK,
                        border="none",
                        border_radius=theme.RADIUS,
                        _hover={"background_color": theme.INK_UPSTREAM},
                        transition="background-color 120ms ease",
                    ),
                    margin_top="1rem",
                ),
                on_submit=ChatState.login,
                width="100%",
            ),
            width="100%",
            max_width="24rem",
            padding="2.25rem",
            background_color=theme.CARD,
            border=f"1px solid {theme.RULE}",
            border_radius=theme.RADIUS,
        ),
        height="100vh",
        width="100%",
        padding="1.5rem",
    )
