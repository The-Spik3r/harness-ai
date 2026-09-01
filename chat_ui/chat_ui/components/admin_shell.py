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


def refresh_control() -> rx.Component:
    """The console's one read action, and the only place it is declared.

    **One name, three tenses.** `REFRESH_LABEL` here, `REFRESH_IN_FLIGHT_LABEL`
    while the read is out, and `AdminState.refreshed_stamp`'s *Refreshed
    {time}* after it lands — the frontend-design skill's "an action keeps the
    same name through the whole flow", which PRD-006 Section 6.1 applies to this
    control by name. The fault panel's retry is this same function rather than a
    second button, for the reason `register.py:_no_matches` reuses
    `_clear_control()`: one action gets one name, one handler and one
    definition.

    **The handler is bound, never called.** `AdminState.load` is a background
    event (`@rx.event(background=True)`), and Reflex documents that such a
    handler cannot be invoked from another handler — it is triggered by being
    returned, yielded, or, as here, attached to an event trigger. That is why
    `authenticate()` *returns* `AdminState.load` while this passes it to
    `on_click`.

    **`disabled` is the affordance, not the guard.** It locks the control for
    the read's duration (PRD-006 Section 4), and `load()` independently refuses
    a second in-flight read. The lock lifting again is STORY-004's `finally`,
    which clears `loading` on the failing path too — PRD-004 Risk 3, a flag
    stranded True being exactly how a refresh control locks forever.

    The pulsing glyph is the console's **sole** moving element (PRD-006 Section
    6.1). It reuses the chat's `.hx-pulse` class rather than declaring a second
    animation, which is also how `prefers-reduced-motion` is honoured: the
    opt-out is already written in `theme.GLOBAL_CSS`, and this page carries that
    stylesheet through `admin_page()`.
    """
    return rx.el.button(
        rx.cond(
            AdminState.loading,
            rx.hstack(
                rx.box(
                    class_name="hx-pulse",
                    width=theme.GLYPH,
                    height=theme.GLYPH,
                    flex_shrink="0",
                    border_radius="1px",
                    background_color=theme.MUTE,
                ),
                rx.box(admin_copy.REFRESH_IN_FLIGHT_LABEL),
                align="center",
                spacing="2",
            ),
            rx.box(admin_copy.REFRESH_LABEL),
        ),
        on_click=AdminState.load,
        disabled=AdminState.loading,
        # Explicit, like sign out's: an unqualified <button> defaults to submit.
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
        _disabled={"opacity": "0.35", "cursor": "not-allowed"},
    )


def refreshed_stamp() -> rx.Component:
    """*Refreshed 14:22:07* — the line the control produces, wherever a view
    states its scope.

    Declared in the shell because both views carry it and neither may reach into
    the other (`summary.py:_empty_summary` records that rule). The shell is
    their frame rather than a third sibling, so one definition here is what keeps
    the register's line and the summary's line the same line.

    `FONT_DATA`, not the reading face: it is a timestamp, and PRD-006 Section 6.1
    reserves `FONT_BODY` for the two or three lines that state a scope in prose.

    The sentence itself — including the *Not read yet* case before the first
    read — is `AdminState.refreshed_stamp`, composed in Python where the format
    string can run.
    """
    return rx.box(
        AdminState.refreshed_stamp,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.MUTE,
    )


def fault_panel() -> rx.Component:
    """A read that raised, named — never a silently empty table.

    PRD-006 Section 4's requirement, and the half `AdminState.register_state`
    and `AdminState.summary_state` were written to expect: both test `error`
    first and both render *the data* in that arm, so this panel hangs above rows
    and figures that are still standing. `FAULT_MESSAGE_TEMPLATE` promises
    exactly that — "Nothing on screen has changed" — and the promise is only
    true because `load()` commits in one block, so a read that fails on the
    eighth of ten writes nothing.

    The copy names the read that failed and gives the action, and it does not
    apologise: the frontend-design skill's "errors don't apologize, and they are
    never vague about what happened". Every word is `admin_copy`'s, including the
    ten read labels `load()` formats into it.

    The retry is `refresh_control()` itself. A second button with a second label
    for one action is the drift the skill's consistency rule rules out, and
    `register.py:_no_matches` sets the precedent by reusing the filter strip's
    own clear control.

    Rendered on `PAPER` with a hairline under it — no card, no fill, no tint, no
    accent, and **no colour at all**.

    It carried an `INK_FAULT` mark in the register's stamp shape until the
    STORY-017 critique pass, and the mark is gone deliberately. PRD-006 Section
    6.1 spends the console's boldness in one place — the stamp margin, where a
    mark means *this row is an exception* and a hundred rows resolve into a
    stripe of them. The same shape on something that is not a row spends that
    vocabulary somewhere it says nothing new: the words already state that the
    read failed, and the margin's mark is worth less the moment it appears
    outside the margin. Everything around the signature stays hairlines and
    alignment, and this panel is around it.
    """
    return rx.cond(
        AdminState.error != "",
        rx.vstack(
            rx.box(
                admin_copy.FAULT_TITLE,
                font_family=theme.FONT_DISPLAY,
                font_size=theme.TEXT_BODY,
                font_weight="600",
                color=theme.INK,
            ),
            rx.box(
                AdminState.error,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_DATA,
                line_height="1.6",
                color=theme.MUTE,
                max_width=theme.MEASURE,
            ),
            rx.box(refresh_control(), margin_top="0.25rem"),
            spacing="1",
            align="start",
            min_width="0",
            width="100%",
            padding="0.9rem 1.5rem",
            border_bottom=f"1px solid {theme.RULE}",
            flex_shrink="0",
            custom_attrs={"role": "alert"},
        ),
        rx.fragment(),
    )


def admin_masthead(active: str) -> rx.Component:
    """The console header: wordmark, the two-view switch, refresh, sign out.

    PRD-006 Section 6.1: "one column, no sidebar. The two views are peers
    reached from a rule-separated switch in the header, because there are
    exactly two and a sidebar for two destinations is furniture."

    Refresh takes the same rule-separated slot the switch and sign out take, so
    the header reads as three clusters rather than as a toolbar. The line it
    produces — `refreshed_stamp()` — is not here: PRD-006 Section 6.1's wireframe
    puts it at the foot of each view's scope column, beside the window it stamps.

    The rules are `border_left`, the same way `shell.py` states one twice — not
    a "|" character, which would be a user-facing string with no home in
    `admin_copy`, and not `rx.divider()`, which is a component for a line.

    **The wordmark is the wordmark, and nothing else** — STORY-019's cut.

    It read `HARNESS · REGISTER` / `HARNESS · SUMMARY` until the quality-floor
    pass put the rendered page next to PRD-006 Section 6.1. Two clusters to the
    right, the two-view switch already marks the current view: `_view_link`
    renders the active one as plain bold text carrying `aria-current="page"`,
    which is the switch's whole job. So the header named the view **twice, in
    one row** — the frontend-design skill's "let each element do exactly one job
    … nothing quietly does double duty", and an accessory by that skill's own
    definition, since removing it loses no information the screen does not
    already carry. It is worst at a narrow viewport, where the masthead wraps and
    the two namings land on consecutive lines a few pixels apart.

    Cutting the suffix also settles which element owns the fact: the switch does,
    because it is the one that can be acted on. The wordmark now reads `HARNESS`
    on both views and on the gate — one word, one job, stated once.

    `admin_copy.CONSOLE_VIEW_REGISTER`, `CONSOLE_VIEW_SUMMARY` and
    `MASTHEAD_SEPARATOR` stay **declared and unrendered**, deliberately: PRD-006
    Section 15 lists `tests/test_copy.py` among the files that must pass
    unmodified, and that file asserts each of them non-empty by name. Deleting
    them would force an edit to a file this PRD promises not to touch, to remove
    three strings that cost nothing where they sit. `active` is still the
    parameter that drives the switch, so nothing else here changes.
    """
    return rx.hstack(
        rx.box(
            admin_copy.CONSOLE_TITLE,
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
                refresh_control(),
                padding_left="1rem",
                margin_left="0.25rem",
                border_left=f"1px solid {theme.RULE}",
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

    `fault_panel()` sits here, between the masthead and the content, rather than
    inside `register()` and `summary()`. One call site, and each page still
    carries its own instance — which is what PRD-006's "both pages render the
    panel independently" asks for, on the same reasoning the gate condition is
    per-page. It is above the view rather than inside it because a failed read is
    a fact about the whole screen, and an admin should meet it before reaching
    the filter controls. Neither view's `rx.match` arms change: both already
    render their data in the fault arm, which is what leaves the record standing
    underneath this panel.
    """
    return rx.fragment(
        rx.el.style(theme.GLOBAL_CSS),
        rx.cond(
            AdminState.authenticated,
            rx.vstack(
                admin_masthead(active),
                fault_panel(),
                content,
                height="100vh",
                width="100%",
                spacing="0",
                background_color=theme.PAPER,
            ),
            admin_gate(),
        ),
    )
