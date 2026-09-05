"""Pure-Python formatting helpers for chat_ui bubbles and session rows.

These run in the backend when a message is built, never at component render
time: component functions receive Reflex Vars (JS references), not concrete
values, so Python control flow (`if`, `try`, datetime math) cannot be applied
to them. Anything needing real Python is computed here and stored on the
ChatMessage as a plain string field.

PRD-008 added the rail's two, `derive_title` and `format_activity`, which are
the same rule applied to `models.ChatSessionSummary` instead: a title and an
activity time are derived once, in Python, and the row carries the strings.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from .copy import (
    DUPLICATE_FALLBACK_TEXT,
    DUPLICATE_RELATIVE_TIME_TEMPLATE,
    DUPLICATE_UNPARSEABLE_TEMPLATE,
    DUPLICATE_WINDOW_RELEASE_TEMPLATE,
    SESSION_ACTIVITY_UNKNOWN,
    SESSION_UNTITLED_TITLE,
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


# The auto-title cap. A rail row is a label on a shelf, not a sentence, and a
# title long enough to need two lines defeats the scan the rail exists for.
# 48 leaves the CSS ellipsis in STORY-018 as a second line of defence at a
# narrow viewport rather than as the only one -- the truncation a user reads
# should be the one Python decided, which is the same argument
# `admin_formatting.DEVICE_TRUNCATE_LENGTH` makes for the device column.
TITLE_MAX_LENGTH = 48
TITLE_ELLIPSIS = "…"


def derive_title(prompt: str) -> str:
    """The session's auto-title: the first prompt, cut at a word boundary.

    Called exactly once per session, by `app/services/chat_sessions.create`,
    which takes it as an injected parameter so the rule lives here and not in
    `app/`. Nothing caches the result and nothing re-derives it: a rename
    (STORY-016) replaces the title outright, and a renamed session must never
    drift back to its first prompt.

    Four inputs decide the shape of this function, and the naive one-liner
    `prompt[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0]` gets two of them wrong:

      short prompt          -> returned unchanged, and with no ellipsis, because
                               an ellipsis is a claim that something was cut
      long prompt           -> cut at the last space inside the cap
      one unbroken token    -> cut at the cap. There is no boundary inside the
                               cap to cut at, and a naive `rsplit` here returns
                               either the whole 200-character token or nothing,
                               depending on where the leading whitespace fell
      whitespace only       -> SESSION_UNTITLED_TITLE. A blank row in the rail
                               is unclickable and unnameable

    Whitespace is collapsed first, so a pasted multi-line prompt yields one
    line: a newline inside a rail row is not a title, it is a layout bug.
    """
    text = " ".join(prompt.split())
    if not text:
        return SESSION_UNTITLED_TITLE
    if len(text) <= TITLE_MAX_LENGTH:
        return text

    head = text[:TITLE_MAX_LENGTH]
    cut = head.rsplit(" ", 1)[0].rstrip()
    if not cut:
        # No boundary inside the cap -- one long token. Cut it at the cap
        # rather than returning nothing. The collapse above already removes
        # the leading whitespace that is the usual way `rsplit` lands here, so
        # this arm is defence rather than a live path: it is what stops the
        # collapse from being load-bearing for a *non-empty title* two edits
        # from now. `tests/test_formatting.py` calls it directly.
        cut = head
    return cut + TITLE_ELLIPSIS


# One day in seconds, named because `format_activity` branches on it twice.
_ONE_DAY_SECONDS = 86400
_YESTERDAY_TEXT = "yesterday"
_DAYS_AGO_TEMPLATE = "{days} days ago"


def format_activity(updated_at: str, now: Optional[datetime] = None) -> str:
    """The rail's activity time: "2m ago", "yesterday", "3 days ago".

    A **third** spelling of a span already spelled twice, so it composes the
    shared bucket table rather than opening a second one -- the rule the table
    states for itself above: the chat's "2 minutes ago" and the register's
    "2m ago" must never drift into two different ideas of when an hour becomes
    a day. Under a day this *is* `humanize_compact`. Only the day arm is new,
    and only because the rail is the one surface where "yesterday" is more
    useful than a count: a reader choosing between eleven conversations reads
    it faster than "1d ago".

    Recomputed on every load and never stored (PRD-008 Section 6). A persisted
    "2m ago" is wrong the moment it is read back.

    `now` is a parameter so the value is deterministic under test and so a rail
    of thirty rows shares one clock read -- the same reason
    `admin_formatting.to_audit_row` takes one. Degrades to
    SESSION_ACTIVITY_UNKNOWN on a missing or unparseable timestamp rather than
    raising, as `format_duplicate_info` does with
    DUPLICATE_UNPARSEABLE_TEMPLATE: a bad column costs the reading, not the row.
    """
    if not updated_at:
        return SESSION_ACTIVITY_UNKNOWN
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        moved = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        seconds = int((now - moved).total_seconds())
    except Exception:
        return SESSION_ACTIVITY_UNKNOWN

    if seconds < _ONE_DAY_SECONDS:
        # Covers the negative case too: a stored timestamp ahead of the clock
        # reads "just now" rather than a negative count.
        return humanize_compact(seconds)
    days = seconds // _ONE_DAY_SECONDS
    if days == 1:
        return _YESTERDAY_TEXT
    return _DAYS_AGO_TEMPLATE.format(days=days)
