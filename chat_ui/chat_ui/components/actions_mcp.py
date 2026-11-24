"""The Actions view's gateway filters: the surface chips and the unlinked toggle.

PRD-023 STORY-018 (D21). A second strip under the decision chips, built only
with `MCP_ENABLED=true` (D20). Its own module so `components/actions.py` keeps
its one click, the decision chip (`tests/test_actions_view.py` counts it); the
helpers are re-declared, not imported from `actions.py`, as the views do not
reach into each other. Chips are `<button type="button">` with `aria-pressed`,
the decision chips' treatment, in the plain ink: a surface implies no verdict.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import (
    ACTIONS_SURFACE_ALL,
    ACTIONS_SURFACE_MCP,
    ACTIONS_SURFACE_V1,
    AdminState,
)

# The second strip's surface chips (PRD-023 STORY-018): (key, word on screen,
# ink). No verdict is implied by a surface, so every ink is the plain one.
_SURFACE_CHIPS = (
    (ACTIONS_SURFACE_ALL, admin_copy.ACTIONS_SURFACE_ALL_LABEL),
    (ACTIONS_SURFACE_V1, admin_copy.ACTIONS_SURFACE_V1_LABEL),
    (ACTIONS_SURFACE_MCP, admin_copy.ACTIONS_SURFACE_MCP_LABEL),
)


def _control_label(label: str) -> rx.Component:
    """The eyebrow over the chips."""
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


def _surface_chip(key: str, label: str, selected: bool) -> rx.Component:
    """One surface chip: the decision chips' button with the plain ink."""
    return rx.el.button(
        label,
        on_click=AdminState.choose_actions_surface(key),
        type="button",
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        line_height="1.4",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_TAG,
        color=theme.INK if selected else theme.MUTE,
        font_weight="600" if selected else "500",
        border_bottom=(
            f"2px solid {theme.INK}" if selected else "2px solid transparent"
        ),
        padding_bottom="2px",
        _hover={} if selected else {"color": theme.INK},
        custom_attrs={"aria-pressed": "true" if selected else "false"},
    )


def _unlinked_toggle(pressed: bool) -> rx.Component:
    """The "Unlinked gateway calls" toggle: a button with `aria-pressed`, the
    chips' selection marking, so no new control vocabulary."""
    return rx.el.button(
        admin_copy.ACTIONS_UNLINKED_LABEL,
        on_click=AdminState.toggle_actions_unlinked,
        type="button",
        title=admin_copy.ACTIONS_UNLINKED_TITLE,
        cursor="pointer",
        background="none",
        border="none",
        padding="0",
        line_height="1.4",
        font_family=theme.FONT_DISPLAY,
        font_size=theme.TEXT_TAG,
        color=theme.INK_HELD if pressed else theme.MUTE,
        font_weight="600" if pressed else "500",
        border_bottom=(
            f"2px solid {theme.INK_HELD}" if pressed else "2px solid transparent"
        ),
        padding_bottom="2px",
        _hover={} if pressed else {"color": theme.INK},
        custom_attrs={"aria-pressed": "true" if pressed else "false"},
    )


def surface_strip() -> rx.Component:
    """The surface filter and the unlinked toggle (PRD-023 STORY-018), a second
    strip under the decision chips; built only with MCP on. Wraps at phone width
    like the first."""
    return rx.flex(
        _control_label(admin_copy.ACTIONS_SURFACE_LABEL),
        *[
            rx.cond(
                AdminState.actions_surface_selected == key,
                _surface_chip(key, label, True),
                _surface_chip(key, label, False),
            )
            for key, label in _SURFACE_CHIPS
        ],
        rx.cond(
            AdminState.actions_unlinked,
            _unlinked_toggle(True),
            _unlinked_toggle(False),
        ),
        align="center",
        gap="0.75rem",
        wrap="wrap",
        padding="0.5rem 1.5rem",
        flex_shrink="0",
        width="100%",
        border_bottom=f"1px solid {theme.RULE_SOFT}",
        custom_attrs={
            "role": "group",
            "aria-label": admin_copy.ACTIONS_SURFACE_LABEL,
        },
    )
