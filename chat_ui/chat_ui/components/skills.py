"""The Skills view: the skills the MCP gateway offers and the roles holding each.

PRD-023 STORY-018 (F11). The operator's question is "which skills exist and who
holds them", and the page answers it in that order: the configuration digest
the rows came from, then one block per skill (id and version over its
description, tools, required servers and roles). It exists only with
`MCP_ENABLED=true` (D20); with it off the route is not registered and the
masthead has no link.

**What this surface refuses.** The Providers view's restraint: no chart, no
per-skill action, no editing (the config file is the source of truth), no
polling. Skills are stacked blocks, not a table, so there is no fixed width to
scroll at phone width: long ids and tool lists wrap inside their block.

**This module reads fields; it does not compute.** Every value is a string built
by `admin_formatting.to_skills_view` from `mcp_config.get_config().skills` and
`authz.roles_holding`, the reads `GET /skills` serves; no server URL, credential
or instruction text reaches it. Its fault is its own (`skills_error`), rendered
with `admin_shell.fault_panel`.

The helpers are re-declared rather than imported from other views: the views do
not reach into each other (`summary.py:_empty_summary` records the rule). This
module imports `admin_copy`, `theme`, `AdminState` and the shell's stamp and
fault panel, and nothing else.
"""

import reflex as rx

from chat_ui import admin_copy, theme
from chat_ui.admin_state import (
    SKILLS_STATE_EMPTY,
    SKILLS_STATE_FAULT,
    SKILLS_STATE_ROWS,
    AdminState,
)
from chat_ui.components.admin_shell import fault_panel, refreshed_stamp


def _fact(label: str, value) -> rx.Component:
    """A label over its value. Wraps rather than truncates: a tool list is the
    content, and the block has no fixed width."""
    return rx.box(
        rx.box(
            label,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            color=theme.MUTE,
        ),
        rx.box(
            value,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_DATA,
            color=theme.INK,
            overflow_wrap="anywhere",
        ),
        min_height=theme.ROW_H,
        padding_top="0.25rem",
        border_bottom=f"1px solid {theme.RULE_SOFT}",
    )


def _skill(skill) -> rx.Component:
    """One skill: its id and version as the heading over its facts."""
    return rx.box(
        rx.flex(
            rx.box(
                skill.id,
                font_family=theme.FONT_DISPLAY,
                font_size=theme.TEXT_LEAD,
                font_weight="600",
                letter_spacing="-0.01em",
                color=theme.INK,
                overflow_wrap="anywhere",
            ),
            rx.box(
                skill.version,
                font_family=theme.FONT_DATA,
                font_size=theme.TEXT_DATA,
                color=theme.MUTE,
            ),
            align="baseline",
            gap="0.75rem",
            wrap="wrap",
            padding_bottom="0.4rem",
            border_bottom=f"1px solid {theme.RULE}",
        ),
        rx.box(
            skill.description,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_BODY,
            line_height="1.6",
            color=theme.INK,
            max_width=theme.MEASURE,
            padding_top="0.5rem",
        ),
        _fact(admin_copy.SKILLS_LABEL_TOOLS, skill.tools),
        _fact(admin_copy.SKILLS_LABEL_REQUIRES, skill.requires),
        _fact(admin_copy.SKILLS_LABEL_ROLES, skill.roles),
        width="100%",
        max_width="40rem",
        custom_attrs={"role": "group"},
    )


def _empty_skills() -> rx.Component:
    """No skill configured: a sentence, not an empty list. It says what the view
    lists, where skills come from, and the action (Refresh). The Actions view's
    empty panel, re-declared."""
    return rx.box(
        rx.box(
            admin_copy.EMPTY_SKILLS_TITLE,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            letter_spacing="-0.01em",
            color=theme.INK,
        ),
        rx.box(
            admin_copy.EMPTY_SKILLS_BODY,
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


def _list() -> rx.Component:
    return rx.vstack(
        rx.foreach(AdminState.skills_rows, _skill),
        spacing="6",
        align="start",
        width="100%",
        padding="1.5rem 1.5rem 2rem 0",
    )


def _body() -> rx.Component:
    """The three states, chosen by `AdminState.skills_state`. The default arm is
    the list: an unrecognised state renders the record, never a claim that none
    is configured."""
    return rx.match(
        AdminState.skills_state,
        (SKILLS_STATE_EMPTY, _empty_skills()),
        (SKILLS_STATE_FAULT, _list()),
        (SKILLS_STATE_ROWS, _list()),
        _list(),
    )


def _caption() -> rx.Component:
    """The configuration digest the rows were read from, over the refreshed
    stamp."""
    return rx.vstack(
        rx.box(
            AdminState.skills_caption,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_DATA,
            color=theme.MUTE,
            overflow_wrap="anywhere",
        ),
        refreshed_stamp(),
        spacing="1",
        align="start",
        padding="0.75rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        flex_shrink="0",
        width="100%",
    )


def skills() -> rx.Component:
    """The Skills view: its own fault panel, the caption, then the scrolling
    body. `min_height="0"` makes the body scroll rather than the page."""
    return rx.vstack(
        fault_panel(AdminState.skills_error),
        _caption(),
        rx.box(
            _body(),
            class_name="hx-scroll",
            overflow_y="auto",
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
