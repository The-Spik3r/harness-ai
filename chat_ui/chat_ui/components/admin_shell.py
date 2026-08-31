"""The console's frame: the token gate, the masthead, and the switch between
the two views.

The counterpart to `shell.py`, and a separate module for the same structural
reason `admin_copy.py` is separate from `copy.py`. Three properties below are
PRD-006 requirements rather than style choices, and each is one edit away from
being lost:

**Nothing here reaches the chat.** PRD-006 Section 4: "`ChatState` never reads
admin state, and no admin page renders a chat component." This module imports
`admin_copy`, `theme` and `AdminState` and nothing else — no `copy`, no `state`,
no `components.chat`, no `components.bubbles`. `tests/test_admin_shell.py`
asserts it twice over: once against the source, and once against `sys.modules`
after the import, which catches a transitive import a grep would miss.

**The gate is the second guard, not the only one.** PRD-006 Section 6: "the
pages exist unconditionally; the token check decides what they render. Reflex
has no server-side route guard here, so the guard is the render condition — and
the data is not loaded until it passes." That last clause is the load-bearing
half. `rx.cond` compiles *both* branches into the page and Reflex ships state
deltas independently of what is drawn, so a populated `AdminState.rows` would
reach an unauthenticated browser even while the gate is what renders. It cannot
be populated: `AdminState.load()` returns before setting anything unless
`authenticated` (admin_state.py), which is PRD-006 Risk 1's stated mitigation —
"the read itself is gated, not just the view". Do not relax that check on the
grounds that this module already guards the view; they guard different things.

**Two of the six inks are chat-only.** PRD-006 Section 6.1 keeps the upstream
blue and the plain self ink on the chat surface — `tests/test_admin_palette.py`
names the pair and greps this file for them, so the two are deliberately not
written out here, in prose or in code. The consequence: the gate's submit hovers
to `MUTE` where `shell.py` hovers to the blue. `PAPER` on `MUTE` measures 4.63:1
and is asserted in `tests/test_contrast.py`.

Styling is hairlines and alignment, deliberately. PRD-006 Section 6.1 spends the
console's boldness on the register's stamp margin (STORY-011); the shell draws
four lines and nothing else — the rule between the two views, the rule before
sign out, the hairline under the masthead, and the gate panel's border.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import AdminState

# --- Routes and view keys ------------------------------------------------
# Declared here rather than in admin_copy: these are values, not copy — the
# same line that module's docstring draws for the verdict keys. STORY-010
# imports these to register the pages, so each route string is typed once in
# the codebase and a moved page cannot leave the switch pointing at the old
# path.
#
# `/admin/audit` and `/admin/stats` rather than `/audit` and `/stats`: those two
# belong to app/routers/admin.py and to the Caddyfile's @backend_routes matcher
# (PRD-006 Section 6, routing constraint).
ROUTE_REGISTER = "/admin/audit"
ROUTE_SUMMARY = "/admin/stats"

# Which of the two views a page is. Passed down from the page rather than read
# off the router: the masthead's correctness would otherwise depend on a string
# matching a route registered in a different module, with no test spanning the
# two halves.
VIEW_REGISTER = "register"
VIEW_SUMMARY = "summary"


def admin_gate() -> rx.Component:
    """Full-page form collecting the admin token before either view opens.

    Mirrors `shell.py`'s `user_id_gate()` in structure — a centred panel, a
    controlled field, one error line, one submit — because the console's gate
    and the chat's gate being the same shape is the vocabulary consistency the
    frontend-design skill asks for, not drift.

    The field is not repopulated after a refusal, and that is `AdminState`'s
    doing rather than this component's: `_refuse()` clears `token_input`, and
    the field is controlled by it. No `reset_on_submit` — it would also fire on
    success, where the handler already clears the token itself.
    """
    return rx.center(
        rx.box(
            rx.box(
                admin_copy.CONSOLE_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.0625rem",
                font_weight="700",
                letter_spacing="0.16em",
                color=theme.INK,
            ),
            rx.box(
                admin_copy.GATE_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size="1.5rem",
                font_weight="600",
                letter_spacing="-0.02em",
                color=theme.INK,
                margin_top="1.75rem",
            ),
            rx.box(
                admin_copy.GATE_BODY,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_BODY,
                line_height="1.6",
                color=theme.MUTE,
                margin_top="0.5rem",
            ),
            rx.form(
                rx.input(
                    # The id is not decoration: Radix paints the real <input>
                    # inside its TextField wrapper, so the only way to colour
                    # the text an admin types is the id selector theme.py
                    # carries for it.
                    id="admin_token_input",
                    class_name="hx-field-boxed",
                    # A shared secret typed on a screen the admin may not be
                    # alone in front of. PRD-006 Section 9 keeps the token from
                    # lingering anywhere; masking keeps it off the glass too.
                    type="password",
                    value=AdminState.token_input,
                    on_change=AdminState.set_token_input,
                    placeholder=admin_copy.GATE_PLACEHOLDER,
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
                    AdminState.gate_error != "",
                    rx.box(
                        AdminState.gate_error,
                        font_family=theme.FONT_DATA,
                        font_size=theme.TEXT_DATA,
                        color=theme.INK_DENIED,
                        margin_top="0.5rem",
                    ),
                    rx.fragment(),
                ),
                rx.box(
                    rx.el.button(
                        admin_copy.GATE_SUBMIT_LABEL,
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
                        # MUTE, not the chat's blue, which is chat-only per
                        # PRD-006 Section 6.1. PAPER on MUTE is 4.63:1.
                        _hover={"background_color": theme.MUTE},
                        transition="background-color 120ms ease",
                    ),
                    margin_top="1rem",
                ),
                # Zero-argument handler, as ChatState.submit_user_id is: the
                # form's data is already in state through the controlled field.
                on_submit=AdminState.authenticate,
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


def _view_link(view: str, label: str, href: str, active: str) -> rx.Component:
    """One destination in the two-view switch.

    The active view is set as plain text, not as a link to itself — a control
    that does nothing is the one thing the skill's "let each element do exactly
    one job" rules out, and rendering it as text gives the switch its state
    indication with no underline bar, pill or fill.

    The explicit `_hover` on the link is mandatory, not stylistic: `rx.link`
    runs `props.setdefault("_hover", {"color": color("accent", 8)})` before any
    other prop handling, so omitting it puts Radix's accent colour in the
    masthead — the console has no accent of its own (PRD-006 Section 6.1), and
    the palette test cannot see a colour Radix supplies at compile time.
    """
    if view == active:
        return rx.box(
            label,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            font_weight="600",
            color=theme.INK,
            custom_attrs={"aria-current": "page"},
        )
    return rx.link(
        label,
        href=href,
        underline="none",
        color=theme.MUTE,
        _hover={"color": theme.INK},
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_DATA,
        font_weight="500",
    )


def admin_masthead(active: str) -> rx.Component:
    """The console header: wordmark, the two-view switch, sign out.

    PRD-006 Section 6.1: "one column, no sidebar. The two views are peers
    reached from a rule-separated switch in the header, because there are
    exactly two and a sidebar for two destinations is furniture."

    The rules are `border_left`, the same way `shell.py` states one twice — not
    a "|" character, which would be a user-facing string with no home in
    `admin_copy`, and not `rx.divider()`, which is a component for a line.

    The title is composed in Python because `active` is a plain str, not a Var:
    the same reason PRD-006 Section 6 puts verdict derivation in Python rather
    than at render time.
    """
    view_word = (
        admin_copy.CONSOLE_VIEW_REGISTER
        if active == VIEW_REGISTER
        else admin_copy.CONSOLE_VIEW_SUMMARY
    )
    return rx.hstack(
        rx.box(
            admin_copy.CONSOLE_TITLE + admin_copy.MASTHEAD_SEPARATOR + view_word,
            font_family=theme.FONT_DISPLAY,
            font_size="1.0625rem",
            font_weight="700",
            letter_spacing="0.16em",
            color=theme.INK,
        ),
        rx.hstack(
            rx.hstack(
                _view_link(
                    VIEW_REGISTER,
                    admin_copy.VIEW_REGISTER_LABEL,
                    ROUTE_REGISTER,
                    active,
                ),
                rx.box(
                    _view_link(
                        VIEW_SUMMARY,
                        admin_copy.VIEW_SUMMARY_LABEL,
                        ROUTE_SUMMARY,
                        active,
                    ),
                    padding_left="0.75rem",
                    margin_left="0.75rem",
                    border_left=f"1px solid {theme.RULE}",
                ),
                align="center",
                spacing="0",
            ),
            rx.box(
                rx.el.button(
                    admin_copy.SIGN_OUT_LABEL,
                    on_click=AdminState.sign_out,
                    # Explicit: an unqualified <button> defaults to submit, and
                    # that is the wrong default to inherit for a control whose
                    # job is to end the session.
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
        # The whole narrow-viewport answer: the two clusters wrap onto two rows
        # rather than compressing, and theme.py's hx-header-meta rule spreads
        # the second one. No new CSS.
        flex_wrap="wrap",
        row_gap="0.75rem",
        padding="0.9rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        background_color=theme.CARD,
        flex_shrink="0",
    )


def admin_page(content: rx.Component, active: str) -> rx.Component:
    """The console's page wrapper: the gate, or the masthead over `content`.

    The `rx.cond` is PRD-006 Section 6's "the guard is the render condition".
    It is the second of two guards, not the only one — see the module docstring
    — and each page carries its own instance of it, which is what PRD-006 Risk
    1's "both pages assert the condition independently" asks for.

    This wrapper owns `rx.el.style(theme.GLOBAL_CSS)`, exactly as `chat_ui.py`'s
    `index()` does for the chat: it is what carries :focus-visible, the
    scrollbar rail and the prefers-reduced-motion block onto an admin page,
    which is otherwise not reached by that stylesheet. STORY-010's page
    functions must not inject a second copy.
    """
    return rx.fragment(
        rx.el.style(theme.GLOBAL_CSS),
        rx.cond(
            AdminState.authenticated,
            rx.vstack(
                admin_masthead(active),
                content,
                height="100vh",
                width="100%",
                spacing="0",
                background_color=theme.PAPER,
            ),
            admin_gate(),
        ),
    )
