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


# One threshold table, two spellings. The chat's duplicate card reads
# "2 minutes ago"; the admin register's time column is a monospace cell and
# reads "2m ago" (PRD-006 Section 6.1). They must never drift into two
# different ideas of when an hour becomes a day, so both renderings read the
# same buckets: (upper bound in seconds, divisor, long unit, short unit).
_BUCKETS = (
    (60, 1, "second", "s"),
    (3600, 60, "minute", "m"),
    (86400, 3600, "hour", "h"),
)
_DAY_BUCKET = (86400, "day", "d")


def _bucket(seconds: int) -> tuple[int, str, str]:
    """Returns (count, long unit, short unit) for a positive elapsed span."""
    for limit, divisor, long_unit, short_unit in _BUCKETS:
        if seconds < limit:
            return seconds // divisor, long_unit, short_unit
    divisor, long_unit, short_unit = _DAY_BUCKET
    return seconds // divisor, long_unit, short_unit


def _humanize(seconds: int) -> str:
    if seconds < 1:
        return "just now"
    count, long_unit, _ = _bucket(seconds)
    return f"{count} {long_unit}{'s' if count != 1 else ''} ago"


def humanize_compact(seconds: int) -> str:
    """The same spans as `_humanize`, spelled for a fixed-width column: "2m ago"."""
    if seconds < 1:
        return "just now"
    count, _, short_unit = _bucket(seconds)
    return f"{count}{short_unit} ago"


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
