"""The pending entry's progress line and the reasoning block (PRD-021 STORY-012).

`ProgressLine` renders `Thinking . 14 s`: the word is chosen by the server
(`ChatState.progress_word`) and the seconds counter and the 300 ms no-flicker
rule run in the browser (`progress.PROGRESS_TICK_JS`), so the server sends no
per-second deltas. The two text spans are owned by that script: React renders
them once with a constant child and only updates the wrapper's `data-*`
attributes, so it never overwrites the script's text.

The word sits in the only `aria-live` region; the seconds span is a sibling and
`aria-hidden`, so a screen reader hears the word change, not a counter.

Nothing here reads a grant: the pending entry shows what is in `live_text` and
`live_reasoning`, and a reader without the grant simply never has any (PRD-021
Section 6.7).
"""

import reflex as rx

from chat_ui import copy, theme
from chat_ui.progress import PROGRESS_TICK_JS
from chat_ui.state import ChatState


class ProgressLine(rx.el.Div):
    """A div that installs one page-level interval running `hxProgressTick`.

    `add_hooks` is deduplicated per page and runs for the page's life; the tick
    is a no-op while the pending entry is absent (reflex 0.9.6.post1
    `reflex_base/components/component.py`: `add_hooks`, `add_custom_code`,
    `add_imports`).
    """

    def add_imports(self):
        return {"react": ["useEffect"]}

    def add_custom_code(self) -> list[str]:
        return [PROGRESS_TICK_JS]

    def add_hooks(self) -> list[str]:
        return [
            "useEffect(() => {"
            " const id = setInterval(() => hxProgressTick(performance.now(), document), 100);"
            " return () => clearInterval(id); }, []);"
        ]


def progress_line() -> rx.Component:
    return ProgressLine.create(
        rx.el.span(
            copy.PENDING_INDICATOR_TEXT,
            aria_live="polite",
            aria_atomic="true",
            class_name="hx-pulse",
            custom_attrs={"data-hx-word": "1"},
        ),
        rx.el.span("", aria_hidden="true", custom_attrs={"data-hx-secs": "1"}),
        custom_attrs={
            "data-hx-progress": "1",
            "data-sent-at": ChatState.progress_sent_at.to_string(),
            "data-since": ChatState.progress_since.to_string(),
            "data-word": ChatState.progress_word,
        },
        display="flex",
        flex_wrap="wrap",
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.MUTE,
        overflow_wrap="anywhere",
        min_width="0",
        max_width="100%",
    )


def render_reasoning_block(reasoning, open_=True, on_toggle=None, block_id="") -> rx.Component:
    """The model's reasoning, set in the data face under two labels.

    Live (no `on_toggle`): always open, no control. After the answer: a real
    `<button>` toggles it, collapsed by default. The body keeps its line breaks
    and scrolls inside a bounded height, so a long thought cannot push the
    answer off a 360 px screen.
    """
    body = rx.box(
        reasoning,
        id=block_id or None,
        tab_index=0,
        white_space="pre-wrap",
        overflow_wrap="anywhere",
        max_height="14rem",
        overflow_y="auto",
        margin_top="0.35rem",
    )
    children = [
        rx.box(copy.REASONING_LABEL, color=theme.INK),
        rx.box(copy.REASONING_NOT_SAVED),
    ]
    if on_toggle is None:
        children.append(body)
    else:
        children.append(
            rx.el.button(
                rx.cond(open_, copy.REASONING_HIDE, copy.REASONING_SHOW),
                on_click=on_toggle,
                type="button",
                aria_expanded=open_,
                aria_controls=block_id or None,
                cursor="pointer",
                font_family=theme.FONT_DISPLAY,
                font_size=theme.TEXT_DATA,
                font_weight="600",
                color=theme.INK,
                background_color=theme.CARD,
                border=f"1px solid {theme.RULE}",
                border_radius=theme.RADIUS,
                padding="0.2rem 0.6rem",
                margin_top="0.35rem",
            )
        )
        children.append(rx.cond(open_, body, rx.fragment()))
    return rx.box(
        *children,
        font_family=theme.FONT_DATA,
        font_size=theme.TEXT_DATA,
        color=theme.MUTE,
        overflow_wrap="anywhere",
        min_width="0",
        max_width="100%",
        margin_top="0.7rem",
        padding="0.5rem 0.75rem",
        border_left=f"2px solid {theme.RULE}",
    )
