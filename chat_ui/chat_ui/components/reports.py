"""The Reports section: a navigable changelog of the delivery record.

Three pages, one frame:

    reports_frame(content)
      reports_masthead()                  full width
      row:  nav_slot()  |  main column
                             feed()   -- /reports, /reports/{prd}
                             detail() -- /reports/{prd}/{story}

**Built from the chat's own devices, not the mockup's palette.** The approved
layout -- a PRD column with progress, a searchable feed of cards, a detail page
with two disclosures -- is rendered in `theme.py`'s tokens and nothing else, so
the section follows the ground switch and holds the AA floor `tests/test_contrast.py`
already enforces. The PRD column *is* the session rail's shape: `PAPER` against
the main column's `CARD`, one `RULE` hairline, the active row marked by the
`SPINE` bar and nothing more, and the same collapse below
`theme.SESSION_RAIL_COLLAPSE_W` behind a masthead disclosure.

**One status-to-ink mapping.** `STATUS_TONES` below is the only place a status
becomes a colour; every badge on every page reads it. Done is the cleared green,
in progress the held ochre, planned (and blocked) the plain `MUTE` -- inks the
palette already had, each on its own tint.

**Every state is named.** `ReportsState.feed_state` and `detail_state` select one
arm; this module renders them and decides nothing about which applies.

No literal hex, no user-facing string outside `reports_copy`, and no import from
the chat or the console -- the section is public and must not drag either
surface's state onto its pages.
"""

import reflex as rx

from chat_ui import reports_copy, theme
from chat_ui.components.ground_switch import ground_switch
from chat_ui.reports_state import (
    DETAIL_FAULT,
    DETAIL_FOUND,
    DETAIL_MISSING,
    FEED_CARDS,
    FEED_EMPTY,
    FEED_EMPTY_PRD,
    FEED_FAULT,
    FEED_NO_MATCH,
    FEED_PRD_MISSING,
    ROUTE_REPORTS,
    STATUS_ALL,
    ReportsState,
)

# status -> (ink, tint). The one mapping; see the module docstring.
STATUS_TONES: dict[str, tuple[str, str]] = {
    "done": (theme.INK_CLEAR, theme.TINT_CLEAR),
    "in-progress": (theme.INK_HELD, theme.TINT_HELD),
    "planned": (theme.MUTE, theme.HOVER),
    "blocked": (theme.MUTE, theme.HOVER),
}

# A PRD's progress bar, keyed by `PrdNavItem.progress`: the same three tones.
PROGRESS_INKS: dict[str, str] = {
    "complete": STATUS_TONES["done"][0],
    "partial": STATUS_TONES["in-progress"][0],
    "none": STATUS_TONES["planned"][0],
}

_NAV_SLOT_ID = "reports-nav"
_NAV_COLLAPSE_MS = "160ms"


# --- Small shared pieces --------------------------------------------------


def _eyebrow(text) -> rx.Component:
    return rx.box(
        text,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_TAG,
        letter_spacing="0.08em",
        text_transform="uppercase",
        color=theme.MUTE,
        white_space="nowrap",
    )


def _quiet_link(label, href, **props) -> rx.Component:
    """A MUTE link that inks on hover. `_hover` is always passed explicitly:
    `rx.link` otherwise defaults it to Radix's accent colour."""
    return rx.link(
        label,
        href=href,
        underline="none",
        color=theme.MUTE,
        _hover={"color": theme.INK},
        **props,
    )


def _quiet_button(label, on_click) -> rx.Component:
    return rx.el.button(
        label,
        on_click=on_click,
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
    )


def _badge(ink: str, tint: str, label) -> rx.Component:
    return rx.hstack(
        rx.box(width="6px", height="6px", border_radius="1px", background_color=ink, flex_shrink="0"),
        rx.box(label),
        align="center",
        spacing="1",
        padding="0.15rem 0.45rem",
        background_color=tint,
        color=ink,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_TAG,
        font_weight="500",
        white_space="nowrap",
        border_radius=theme.RADIUS,
    )


def status_badge(status, label) -> rx.Component:
    """The badge for a status Var, drawn from `STATUS_TONES` and nothing else."""
    return rx.match(
        status,
        *[(key, _badge(ink, tint, label)) for key, (ink, tint) in STATUS_TONES.items()],
        _badge(*STATUS_TONES["planned"], label),
    )


def _state_panel(title, body, action=None, alert: bool = False) -> rx.Component:
    """Empty, no-match, not-found and fault: one shape, different words."""
    return rx.vstack(
        rx.box(
            title,
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_LEAD,
            font_weight="600",
            color=theme.INK,
        ),
        rx.box(
            body,
            font_family=theme.FONT_BODY,
            font_size=theme.TEXT_BODY,
            line_height="1.6",
            color=theme.MUTE,
            max_width=theme.MEASURE,
        ),
        rx.box(action, margin_top="0.25rem") if action is not None else rx.fragment(),
        spacing="1",
        align="start",
        width="100%",
        padding="1.5rem 1.25rem",
        border=f"1px solid {theme.RULE}",
        border_radius=theme.RADIUS,
        background_color=theme.PAPER,
        custom_attrs={"role": "alert"} if alert else {},
    )


# --- Masthead ---------------------------------------------------------------


def nav_disclosure() -> rx.Component:
    """**PRDs** -- brings the navigation column back below the collapse width,
    exactly as `shell.rail_disclosure()` does for the session rail."""
    return rx.box(
        rx.el.button(
            reports_copy.NAV_DISCLOSURE_LABEL,
            on_click=ReportsState.toggle_nav,
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
                "aria-expanded": rx.cond(ReportsState.nav_expanded, "true", "false"),
                "aria-controls": _NAV_SLOT_ID,
            },
        ),
        display=rx.breakpoints(custom={"initial": "flex", theme.SESSION_RAIL_COLLAPSE_W: "none"}),
        align_items="center",
        padding_left="0.875rem",
        margin_left="0.875rem",
        border_left=f"1px solid {theme.RULE}",
    )


def reports_masthead() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.box(
                reports_copy.WORDMARK,
                font_family=theme.FONT_DISPLAY,
                font_size="1.0625rem",
                font_weight="700",
                letter_spacing="0.16em",
                color=theme.INK,
            ),
            rx.box(
                _quiet_link(
                    reports_copy.SECTION_TITLE,
                    ROUTE_REPORTS,
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_TAG,
                    letter_spacing="0.08em",
                    text_transform="uppercase",
                ),
                padding_left="0.875rem",
                margin_left="0.875rem",
                border_left=f"1px solid {theme.RULE}",
            ),
            nav_disclosure(),
            align="center",
            spacing="0",
        ),
        ground_switch(),
        justify="between",
        align="center",
        width="100%",
        padding="0.9rem 1.5rem",
        border_bottom=f"1px solid {theme.RULE}",
        background_color=theme.CARD,
        flex_shrink="0",
    )


# --- Navigation column ------------------------------------------------------


def _spine(active) -> rx.Component:
    """The session rail's signature, reused: a SPINE bar on the active row only."""
    return rx.box(
        rx.cond(
            active,
            rx.box(width="4px", align_self="stretch", background_color=theme.SPINE),
            rx.fragment(),
        ),
        width="0.75rem",
        flex_shrink="0",
        align_self="stretch",
        display="flex",
    )


def _nav_all() -> rx.Component:
    active = ReportsState.active_prd == ""
    return rx.link(
        rx.hstack(
            _spine(active),
            rx.box(
                reports_copy.NAV_ALL_LABEL,
                font_family=theme.FONT_DISPLAY,
                font_size=theme.TEXT_DATA,
                font_weight="600",
                color=theme.INK,
                padding="0.55rem 0",
            ),
            spacing="0",
            align="stretch",
        ),
        href=ReportsState.all_href,
        underline="none",
        display="block",
        border_radius=theme.RADIUS,
        _hover={"background_color": theme.HOVER, "color": theme.INK},
        custom_attrs={"aria-current": rx.cond(active, "page", "false")},
    )


def _nav_item(prd) -> rx.Component:
    active = ReportsState.active_prd == prd.slug
    return rx.link(
        rx.hstack(
            _spine(active),
            rx.vstack(
                rx.box(
                    prd.name,
                    font_family=theme.FONT_DISPLAY,
                    font_size=theme.TEXT_DATA,
                    font_weight="500",
                    line_height="1.35",
                    color=theme.INK,
                ),
                rx.box(
                    rx.box(
                        height="100%",
                        width=prd.bar_width,
                        background_color=rx.match(
                            prd.progress,
                            *PROGRESS_INKS.items(),
                            PROGRESS_INKS["none"],
                        ),
                    ),
                    height="3px",
                    width="100%",
                    background_color=theme.RULE_SOFT,
                    overflow="hidden",
                ),
                rx.box(prd.done_label, font_family=theme.FONT_DATA, font_size=theme.TEXT_TAG, color=theme.MUTE),
                spacing="1",
                align="start",
                width="100%",
                padding="0.55rem 0.5rem 0.55rem 0",
            ),
            spacing="0",
            align="stretch",
        ),
        href=prd.href,
        underline="none",
        display="block",
        border_radius=theme.RADIUS,
        _hover={"background_color": theme.HOVER, "color": theme.INK},
        custom_attrs={"aria-current": rx.cond(active, "page", "false")},
    )


def reports_nav() -> rx.Component:
    return rx.el.nav(
        _nav_all(),
        rx.box(height="1px", background_color=theme.RULE, margin="0.4rem 0"),
        rx.foreach(ReportsState.prds, _nav_item),
        class_name="hx-scroll",
        display="flex",
        flex_direction="column",
        gap="0.15rem",
        width=theme.SESSION_RAIL_W,
        flex_shrink="0",
        height="100%",
        overflow_y="auto",
        overflow_x="hidden",
        padding=theme.SESSION_RAIL_GUTTER,
        background_color=theme.PAPER,
        border_right=f"1px solid {theme.RULE}",
        custom_attrs={"aria-label": reports_copy.NAV_DISCLOSURE_LABEL},
    )


def nav_slot() -> rx.Component:
    """The collapsing column -- `shell.rail_slot()`'s mechanism, unchanged:
    `max-width` and `visibility` on the same breakpoint map, so a collapsed
    column also leaves the tab order."""
    return rx.box(
        reports_nav(),
        id=_NAV_SLOT_ID,
        display="flex",
        flex_shrink="0",
        overflow="hidden",
        height="100%",
        max_width=rx.breakpoints(
            custom={
                "initial": rx.cond(ReportsState.nav_expanded, theme.SESSION_RAIL_W, "0"),
                theme.SESSION_RAIL_COLLAPSE_W: theme.SESSION_RAIL_W,
            }
        ),
        visibility=rx.breakpoints(
            custom={
                "initial": rx.cond(ReportsState.nav_expanded, "visible", "hidden"),
                theme.SESSION_RAIL_COLLAPSE_W: "visible",
            }
        ),
        transition=f"max-width {_NAV_COLLAPSE_MS} ease, visibility {_NAV_COLLAPSE_MS} ease",
    )


def reports_frame(content: rx.Component) -> rx.Component:
    return rx.fragment(
        rx.el.style(theme.GLOBAL_CSS),
        rx.vstack(
            reports_masthead(),
            rx.hstack(
                nav_slot(),
                rx.box(
                    rx.box(content, width="100%", max_width=theme.COLUMN_MAX, margin="0 auto"),
                    class_name="hx-scroll",
                    flex="1",
                    min_width="0",
                    height="100%",
                    overflow_y="auto",
                    padding="1.5rem 1.5rem 3rem",
                    background_color=theme.CARD,
                ),
                spacing="0",
                align="stretch",
                width="100%",
                flex="1",
                min_height="0",
                overflow="hidden",
            ),
            height="100vh",
            width="100%",
            spacing="0",
            background_color=theme.PAPER,
        ),
    )


# --- Feed -------------------------------------------------------------------


def _toolbar() -> rx.Component:
    return rx.hstack(
        rx.input(
            id="reports_search_input",
            class_name="hx-field-boxed",
            value=ReportsState.query,
            on_change=ReportsState.set_query,
            debounce_timeout=250,
            placeholder=reports_copy.SEARCH_PLACEHOLDER,
            type="search",
            custom_attrs={"aria-label": reports_copy.SEARCH_LABEL, "autoComplete": "off"},
            flex="1",
            min_width="14rem",
            height="2.25rem",
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_DATA,
            border_radius=theme.RADIUS,
        ),
        rx.el.select(
            rx.el.option(reports_copy.STATUS_FILTER_ALL, value=STATUS_ALL),
            *[rx.el.option(label, value=key) for key, label in reports_copy.STATUS_LABELS.items()],
            value=ReportsState.status_filter,
            on_change=ReportsState.set_status_filter,
            custom_attrs={"aria-label": reports_copy.STATUS_FILTER_LABEL},
            height="2.25rem",
            padding="0 0.6rem",
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_DATA,
            color=theme.INK,
            background_color=theme.CARD,
            border=f"1px solid {theme.RULE}",
            border_radius=theme.RADIUS,
            cursor="pointer",
        ),
        width="100%",
        spacing="2",
        flex_wrap="wrap",
        margin_bottom="1rem",
    )


def _card(card) -> rx.Component:
    return rx.link(
        rx.vstack(
            rx.hstack(
                rx.box(
                    card.prd_id,
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_TAG,
                    color=theme.MUTE,
                    padding="0.1rem 0.4rem",
                    border=f"1px solid {theme.RULE}",
                    border_radius=theme.RADIUS,
                    white_space="nowrap",
                ),
                status_badge(card.status, card.status_label),
                rx.box(card.date_label, font_family=theme.FONT_DATA, font_size=theme.TEXT_TAG, color=theme.MUTE),
                rx.spacer(),
                rx.box(card.commit, font_family=theme.FONT_DATA, font_size=theme.TEXT_TAG, color=theme.MUTE),
                align="center",
                spacing="2",
                width="100%",
                flex_wrap="wrap",
            ),
            rx.box(
                card.heading,
                font_family=theme.FONT_DISPLAY,
                font_size=theme.TEXT_BODY,
                font_weight="600",
                line_height="1.35",
                color=theme.INK,
            ),
            rx.box(
                card.summary,
                font_family=theme.FONT_BODY,
                font_size=theme.TEXT_DATA,
                line_height="1.55",
                color=theme.MUTE,
                overflow="hidden",
                display="-webkit-box",
                style={"WebkitLineClamp": "2", "WebkitBoxOrient": "vertical"},
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        href=card.href,
        underline="none",
        display="block",
        padding="0.8rem 1rem",
        border=f"1px solid {theme.RULE}",
        border_radius=theme.RADIUS,
        background_color=theme.CARD,
        color=theme.INK,
        _hover={"background_color": theme.HOVER, "color": theme.INK},
    )


def feed() -> rx.Component:
    """The feed and its states. Fault first; see `reports_state.py`."""
    return rx.box(
        _toolbar(),
        rx.match(
            ReportsState.feed_state,
            (
                FEED_FAULT,
                _state_panel(
                    reports_copy.FAULT_TITLE,
                    reports_copy.FAULT_BODY,
                    _quiet_button(reports_copy.RETRY_LABEL, ReportsState.load_feed),
                    alert=True,
                ),
            ),
            (FEED_PRD_MISSING, _state_panel(reports_copy.PRD_NOT_FOUND_TITLE, reports_copy.PRD_NOT_FOUND_BODY)),
            (FEED_EMPTY, _state_panel(reports_copy.EMPTY_TITLE, reports_copy.EMPTY_BODY)),
            (FEED_EMPTY_PRD, _state_panel(reports_copy.EMPTY_PRD_TITLE, ReportsState.empty_prd_body)),
            (
                FEED_NO_MATCH,
                _state_panel(
                    reports_copy.NO_MATCH_TITLE,
                    reports_copy.NO_MATCH_BODY,
                    _quiet_button(reports_copy.CLEAR_FILTERS_LABEL, ReportsState.clear_filters),
                ),
            ),
            (
                FEED_CARDS,
                rx.vstack(rx.foreach(ReportsState.cards, _card), spacing="2", width="100%"),
            ),
            rx.fragment(),
        ),
        width="100%",
    )


# --- Detail -----------------------------------------------------------------


def _breadcrumb() -> rx.Component:
    separator = rx.box(reports_copy.BREADCRUMB_SEPARATOR, color=theme.RULE)
    return rx.hstack(
        _quiet_link(reports_copy.BREADCRUMB_ROOT, ROUTE_REPORTS),
        separator,
        _quiet_link(ReportsState.detail.prd_name, ReportsState.detail.prd_href),
        separator,
        rx.box(ReportsState.detail.story_id, color=theme.INK, custom_attrs={"aria-current": "page"}),
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        spacing="2",
        align="center",
        flex_wrap="wrap",
        margin_bottom="1rem",
    )


def _criterion(item) -> rx.Component:
    return rx.hstack(
        rx.box(
            width=theme.GLYPH,
            height=theme.GLYPH,
            flex_shrink="0",
            margin_top="0.4rem",
            border_radius="1px",
            background_color=rx.cond(item.checked, STATUS_TONES["done"][0], "transparent"),
            border=rx.cond(item.checked, "none", f"1px solid {theme.MUTE}"),
        ),
        rx.box(item.text, font_family=theme.FONT_BODY, font_size=theme.TEXT_BODY, line_height="1.55", color=theme.INK),
        align="start",
        spacing="3",
    )


def _disclosure(label, rows) -> rx.Component:
    """Collapsed by default: a native `<details>`, so it opens with the keyboard
    and needs no state."""
    return rx.el.details(
        rx.el.summary(
            label,
            cursor="pointer",
            padding="0.75rem 1rem",
            font_family=theme.FONT_DISPLAY,
            font_size=theme.TEXT_DATA,
            font_weight="600",
            color=theme.INK,
        ),
        rx.box(rows, padding="0 1rem 0.75rem"),
        border=f"1px solid {theme.RULE}",
        border_radius=theme.RADIUS,
        width="100%",
    )


def _file_row(row) -> rx.Component:
    return rx.hstack(
        rx.box(
            row.path,
            flex="1",
            min_width="0",
            overflow="hidden",
            text_overflow="ellipsis",
            white_space="nowrap",
            color=theme.INK,
        ),
        rx.box(row.action, font_size=theme.TEXT_TAG, color=theme.MUTE, padding="0.05rem 0.4rem", background_color=theme.HOVER, border_radius=theme.RADIUS),
        rx.box(row.detail, color=theme.MUTE, white_space="nowrap"),
        align="center",
        spacing="3",
        width="100%",
        padding="0.4rem 0",
        border_top=f"1px solid {theme.RULE_SOFT}",
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
    )


def _validation_row(row) -> rx.Component:
    return rx.hstack(
        rx.box(
            width=theme.GLYPH,
            height=theme.GLYPH,
            flex_shrink="0",
            margin_top="0.3rem",
            border_radius="1px",
            # Pass reads as done; a failed check is the one place the denied ink
            # appears, because a red check is what a failed check is.
            background_color=rx.match(
                row.outcome,
                ("pass", STATUS_TONES["done"][0]),
                ("fail", theme.INK_DENIED),
                theme.RULE,
            ),
        ),
        rx.box(row.check, color=theme.INK, flex="1", min_width="0", overflow_wrap="anywhere"),
        rx.box(row.result, color=theme.MUTE, flex="1", min_width="0", overflow_wrap="anywhere"),
        align="start",
        spacing="3",
        width="100%",
        padding="0.4rem 0",
        border_top=f"1px solid {theme.RULE_SOFT}",
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
    )


def _report_body() -> rx.Component:
    detail = ReportsState.detail
    return rx.cond(
        detail.has_report,
        rx.vstack(
            rx.vstack(
                _eyebrow(reports_copy.SUMMARY_HEADING),
                rx.foreach(
                    detail.summary,
                    lambda p: rx.box(p, font_family=theme.FONT_BODY, font_size=theme.TEXT_BODY, line_height="1.65", color=theme.INK),
                ),
                spacing="3",
                align="start",
                width="100%",
                padding="1rem 1.15rem",
                background_color=theme.PAPER,
                border_radius=theme.RADIUS,
            ),
            rx.cond(
                detail.acceptance,
                rx.vstack(
                    _eyebrow(reports_copy.ACCEPTANCE_HEADING),
                    rx.foreach(detail.acceptance, _criterion),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
                rx.fragment(),
            ),
            _disclosure(detail.files_label, rx.foreach(detail.files, _file_row)),
            _disclosure(detail.validation_label, rx.foreach(detail.validation, _validation_row)),
            spacing="4",
            align="start",
            width="100%",
        ),
        _state_panel(reports_copy.NO_REPORT_TITLE, detail.no_report_body),
    )


def _pager() -> rx.Component:
    detail = ReportsState.detail
    link_props = {"font_family": theme.FONT_DISPLAY, "font_size": theme.TEXT_DATA}
    return rx.hstack(
        rx.box(
            rx.cond(
                detail.prev_href != "",
                rx.link(detail.prev_label, href=detail.prev_href, underline="none", color=theme.INK, _hover={"color": theme.MUTE}, **link_props),
                rx.box(reports_copy.FIRST_STORY, color=theme.MUTE, **link_props),
            ),
            flex="1",
            min_width="0",
        ),
        _quiet_link(detail.view_prd_label, detail.prd_href, flex_shrink="0", **link_props),
        rx.box(
            rx.cond(
                detail.next_href != "",
                rx.link(detail.next_label, href=detail.next_href, underline="none", color=theme.INK, _hover={"color": theme.MUTE}, **link_props),
                rx.box(reports_copy.LAST_STORY, color=theme.MUTE, **link_props),
            ),
            flex="1",
            min_width="0",
            text_align="right",
        ),
        align="start",
        spacing="4",
        width="100%",
        padding_top="1rem",
        margin_top="1.5rem",
        border_top=f"1px solid {theme.RULE}",
    )


def _story() -> rx.Component:
    detail = ReportsState.detail
    return rx.box(
        _breadcrumb(),
        rx.hstack(
            status_badge(detail.status, detail.status_label),
            rx.box(detail.date_label, font_family=theme.FONT_DATA, font_size=theme.TEXT_DATA, color=theme.MUTE),
            rx.spacer(),
            rx.cond(
                detail.commit_url != "",
                rx.link(
                    detail.commit,
                    href=detail.commit_url,
                    is_external=True,
                    color=theme.INK,
                    underline="always",
                    _hover={"color": theme.MUTE},
                    font_family=theme.FONT_DATA,
                    font_size=theme.TEXT_DATA,
                    custom_attrs={"aria-label": detail.commit_link_label},
                ),
                rx.fragment(),
            ),
            align="center",
            spacing="3",
            width="100%",
            margin_bottom="0.6rem",
        ),
        rx.el.h1(
            detail.heading,
            font_family=theme.FONT_DISPLAY,
            font_size="1.5rem",
            font_weight="600",
            letter_spacing="-0.015em",
            line_height="1.25",
            color=theme.INK,
            margin="0",
        ),
        rx.box(
            detail.plan,
            font_family=theme.FONT_DATA,
            font_size=theme.TEXT_TAG,
            color=theme.MUTE,
            overflow_wrap="anywhere",
            margin="0.35rem 0 1.25rem",
        ),
        _report_body(),
        _pager(),
        width="100%",
    )


def detail() -> rx.Component:
    return rx.match(
        ReportsState.detail_state,
        (DETAIL_FOUND, _story()),
        (
            DETAIL_MISSING,
            _state_panel(
                reports_copy.STORY_NOT_FOUND_TITLE,
                reports_copy.STORY_NOT_FOUND_BODY,
                _quiet_link(reports_copy.BACK_TO_REPORTS, ROUTE_REPORTS, font_family=theme.FONT_DISPLAY, font_size=theme.TEXT_DATA),
            ),
        ),
        (
            DETAIL_FAULT,
            _state_panel(
                reports_copy.FAULT_TITLE,
                reports_copy.FAULT_BODY,
                _quiet_button(reports_copy.RETRY_LABEL, ReportsState.load_detail),
                alert=True,
            ),
        ),
        rx.fragment(),
    )


# --- Pages --------------------------------------------------------------------


def reports_feed_page() -> rx.Component:
    return reports_frame(feed())


def reports_detail_page() -> rx.Component:
    return reports_frame(detail())
