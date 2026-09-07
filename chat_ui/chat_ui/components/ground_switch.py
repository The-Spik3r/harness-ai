"""The ground toggle: one icon, switching which palette the ledger renders on.

One component, rendered in four places — the chat's masthead and session gate,
the console's masthead and token gate — because it is one control. See
`ground_copy.py` for why its wording is not split across the two copy modules.

**A sun on the light ground, a moon on the dark one.** The icon names the ground
you are on, not the one you would get; the `aria-label` names the one you would
get. That split is deliberate — an icon is read as a status the moment it sits in
a header beside other status, and an icon showing the *destination* inverts on
every glance ("there is a moon, so this is… light?"). The label carries the verb
because a label can, and because a screen reader has no icon to look at.

**It holds no colour, no size and no state.** All three are deliberate.

No colour or size: every rule the control needs is `.hx-ground-toggle` in
`theme.GLOBAL_CSS`, including the icon's dimensions. Lucide strokes its glyphs
with `currentColor`, so the icon inherits the button's colour and the whole
control obeys the palette it is switching, with no branch. That is also why this
module does not import `theme` at all — there is no token to reach for, so there
is no second place a colour or a size could be decided.

No state: `reflex.style.toggle_color_mode` is a *client-side* event. It writes
`localStorage["theme"]` and flips the class on the document element without a
round trip, and `resolved_color_mode` is a frontend Var read out of React
context, not a backend field. So this control works identically on
`login_gate()` and `admin_gate()`, where there is no authenticated `ChatState`
or `AdminState` to hang a preference on — a visitor can set the ground before
signing in, and the choice survives the sign-in, the sign-out and the next
visit.

**On the third state.** Reflex stores three values and the toggle only ever
writes two, which is not an oversight. `system` remains the *default*: until a
reader presses this once, the ground follows the machine, which is what the
pre-paint script resolves. The first press turns that into an explicit choice
and there is no way back to `system` from here — the cost of a control with one
target instead of three. `toggleColorMode` flips `resolvedColorMode`, so that
first press always lands on the opposite of what is actually on screen rather
than on the opposite of the word `system`, which is the one behaviour that would
have made a binary toggle feel broken.
"""

import reflex as rx
from reflex.style import resolved_color_mode, toggle_color_mode

from chat_ui import ground_copy

# The two grounds, as `resolved_color_mode` reports them. Written as literals
# rather than imported from `reflex.style` for the reason
# `tests/test_render_invariants.py` retypes its verdict names: a constant
# imported from the thing under test agrees with itself. `tests/test_ground.py`
# pins them against `reflex.style`, which is where a Reflex upgrade renaming a
# mode would be caught.
MODE_LIGHT = "light"
MODE_DARK = "dark"


def ground_switch() -> rx.Component:
    """The toggle, ready to drop into a header cluster or a gate panel.

    `resolved_color_mode` and not `color_mode`: the icon reports the ground
    actually on screen. With the preference still at `system` the raw var reads
    `"system"`, which is neither a sun nor a moon — an icon chosen from it would
    have to invent a third glyph for a state the control cannot set, or fall
    through to the wrong one.
    """
    return rx.el.button(
        rx.color_mode_cond(
            light=rx.icon("sun"),
            dark=rx.icon("moon"),
        ),
        type="button",
        class_name="hx-ground-toggle",
        # The control's only name. There is no text in it, so this is not a
        # supplement to a visible label -- it is the label.
        custom_attrs={
            "aria-label": rx.cond(
                resolved_color_mode == MODE_LIGHT,
                ground_copy.GROUND_TO_DARK_LABEL,
                ground_copy.GROUND_TO_LIGHT_LABEL,
            )
        },
        on_click=toggle_color_mode,
    )
