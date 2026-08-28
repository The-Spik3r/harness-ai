"""Pure-Python formatting helpers for chat_ui bubbles.

These run in the backend when a message is built, never at component render
time: component functions receive Reflex Vars (JS references), not concrete
values, so Python control flow (`if`, `try`, datetime math) cannot be applied
to them. Anything needing real Python is computed here and stored on the
ChatMessage as a plain string field.
"""

from datetime import datetime, timedelta, timezone

from .copy import (
    DUPLICATE_FALLBACK_TEXT,
    DUPLICATE_RELATIVE_TIME_TEMPLATE,
    DUPLICATE_UNPARSEABLE_TEMPLATE,
    DUPLICATE_WINDOW_RELEASE_TEMPLATE,
)


def _humanize(seconds: int) -> str:
    if seconds < 1:
        return "just now"
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''} ago"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = seconds // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


def format_duplicate_info(first_query_at: str) -> tuple[str, str]:
    """Returns (relative-time line, 24h-window-release line) for a duplicate block.

    Falls back to a plain notice when first_query_at is missing or unparseable,
    so a bad timestamp degrades the card instead of dropping it.
    """
    if not first_query_at:
        return DUPLICATE_FALLBACK_TEXT, ""
    try:
        dt = datetime.fromisoformat(first_query_at.replace("Z", "+00:00"))
        seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
        release_str = (dt + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

        main_text = DUPLICATE_RELATIVE_TIME_TEMPLATE.format(
            relative=_humanize(seconds), absolute=first_query_at
        )
        release_text = DUPLICATE_WINDOW_RELEASE_TEMPLATE.format(release=release_str)
        return main_text, release_text
    except Exception:
        return DUPLICATE_UNPARSEABLE_TEMPLATE.format(absolute=first_query_at), ""
