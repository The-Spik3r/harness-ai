"""Pure-Python formatting for the admin register's rows and figures.

Like `formatting.py` does for the chat, everything here runs in the backend
when a row is built, never at component render time: component functions
receive Reflex Vars (JS references), not concrete values, so Python control
flow (`if`, `try`, datetime math) cannot be applied to them. PRD-006 Section 6
states the rule for this surface — the verdict, the relative time and the
formatted device string are "computed once per row in Python when the row is
built". Components read fields; they do not compute.

This module is also the boundary named in PRD-006 Risk 2. `to_audit_row` is
the only thing that reads an `AuditLog` on the console's path, and it names
every field it copies. `prompt_preview` and `response_preview` are not among
them and are not read here at all — which is why there is no `**log.__dict__`
shortcut and no field-copy loop below. A projection that enumerates its fields
is the mitigation; `tests/test_admin_formatting.py` fails if a preview value
reaches the row.

`to_usage_rows` is the Usage table's counterpart (PRD-013 STORY-016): it turns
`UsageDay` counters into `UsageRow`s, resolving each budget with the gate's own
`limits_for`.
"""

from datetime import datetime, timezone
from typing import Optional

from app.db.models import AuditLog, UsageDay

# By name, never the module: `usage_limits` also holds the counter writers
# (`admit`, `charge`), and the console must not be able to reach them
# (PRD-006 Section 9; `tests/test_usage_view.py` asserts the namespace).
from app.services.identity import BREAK_GLASS_ROLE, BREAK_GLASS_USER_ID, Identity
from app.services.usage_limits import limits_for

from .admin_copy import (
    DETAIL_FLAG_NO_LABEL,
    DETAIL_FLAG_YES_LABEL,
    USAGE_BUDGET_UNLIMITED,
)
from .admin_models import AuditRow, UsageRow
from .formatting import humanize_compact

# The register's outcome vocabulary (PRD-006 Section 6). These are values, not
# copy: they are the `rx.match` keys and the filter values downstream, so they
# are constants rather than inline literals in three components.
#
# A single row can satisfy several of these conditions at once, so the order in
# `derive_verdict` is a precedence, not a set of independent flags:
#
#     was_duplicate_blocked   -> held
#     suspicious_pattern      -> denied  (a block, or a pre-PRD-011 row with a
#                                         NULL action; never a flag -- PRD-011 D6)
#     limit_exceeded          -> denied  (a usage-limit refusal, written with
#                                         success=1 -- PRD-013 D6)
#     not success             -> fault
#     otherwise               -> cleared
#
# Fixed here and nowhere else, so two rows with identical fields can never
# render differently.
#
# Not covered, and deliberately left alone: a permission refusal
# (`denied_permission` set, success=1) still reads **cleared**. PRD-013's
# Evidence records it; changing it is outside that PRD.
VERDICT_CLEARED = "cleared"
VERDICT_HELD = "held"
VERDICT_DENIED = "denied"
VERDICT_FAULT = "fault"
VERDICTS = (VERDICT_CLEARED, VERDICT_HELD, VERDICT_DENIED, VERDICT_FAULT)

# What a cell shows when its source column is NULL. One mark for every column,
# so "no value on this row" reads the same everywhere on the register.
VALUE_ABSENT = "—"
# What a share shows when its denominator is 0. Equal to VALUE_ABSENT today but
# a separate constant: a NULL column and an undefined ratio are different
# statements, and `app/routers/admin.py:57` answers the second one with
# "0.0%" — a claim that 0% succeeded when in truth nothing was recorded.
SHARE_UNDEFINED = "—"

# User-Agent strings run past 100 characters and would break the alignment the
# register scans on. The full string is kept on the row for the disclosure.
DEVICE_TRUNCATE_LENGTH = 32
DEVICE_ELLIPSIS = "…"

# Between the two halves of the register's tokens cell, "2,140 / 312". A format
# rather than copy, like DEVICE_ELLIPSIS: the slash is the split itself. Which
# half is which (input first) is stated once, by COLUMN_TOKENS_TITLE on the head.
TOKENS_SPLIT_SEPARATOR = " / "

# The refresh stamp's format. Seconds included deliberately: two refreshes a
# minute apart must produce two visibly different stamps, or the control reads
# as broken. UTC to match the audit table's own timestamps, which
# `app/services/audit_logger.py` writes in UTC — a local-time stamp beside UTC
# row times would be two clocks on one screen.
REFRESHED_AT_FORMAT = "%Y-%m-%d %H:%M:%S UTC"


def derive_verdict(log: AuditLog) -> str:
    """The row's outcome, in PRD-006 Section 6's precedence.

    This function must never branch on `model_used`. PRD-006 Risk 3, verbatim:
    "The obvious way to separate an upstream failure from an internal one is to
    check whether a model was recorded — and it is wrong, because the
    output-side `PiiRedactorError` arm logs one." That arm is
    `app/services/query_pipeline.py:91-93`, which writes
    `model_used=openrouter_result.model_used` together with `success=False`, so
    a model *is* recorded on an internal fault. Splitting **fault** on that
    field would encode the pipeline's statement order into the console and
    break the first time it is reordered. **fault** stays one verdict, and
    `error_message` carries the distinction on disclosure.

    A usage-limit row (PRD-013) is **denied**, after the pattern arm and before
    the success check. Both arms say denied, so their relative order cannot
    change a verdict.
    """
    if log.was_duplicate_blocked:
        return VERDICT_HELD
    # PRD-011 D6: a flag row carries a pattern but the request was not
    # blocked -- it passed the check and went on upstream -- so it falls
    # through to the arms below (a flag row is written with success=1, so
    # **cleared**). A NULL action is a row from before PRD-011, which was a
    # block, so it stays **denied**: the same rule the blocked_suspicious
    # counters use in `app/db/database.py`.
    if log.suspicious_pattern is not None and log.pattern_action != "flag":
        return VERDICT_DENIED
    # PRD-013 D6: a usage-limit refusal is written with success=1 and the limit
    # named in its own column, so without this it would read **cleared**.
    # `is not None` rather than truthiness, matching the `/stats` predicate
    # (`_BLOCKED_USAGE_LIMITS_WHERE` in `app/db/database.py`), so the register
    # and the summary agree on which rows these are.
    if log.limit_exceeded is not None:
        return VERDICT_DENIED
    if not log.success:
        return VERDICT_FAULT
    return VERDICT_CLEARED


def format_share(count: Optional[int], total: Optional[int]) -> str:
    """The share of `total` that `count` represents, as "13.0%".

    Mirrors the number format of `app/routers/admin.py:57` so the console and
    `curl /stats` never disagree on rounding. An absent, zero or negative total
    yields the placeholder instead of a division — the summary renders these
    beside every blocked count, and no figure may raise into a page render.
    """
    if count is None or not total or total < 0:
        return SHARE_UNDEFINED
    return f"{(count / total * 100):.1f}%"


def format_count(value: Optional[int]) -> str:
    """A whole-number figure, thousands-separated: 3180 reads as "3,180".

    Here rather than in a component for the reason at the top of this module.
    PRD-006 Section 6.1's scope line is "100 most recent of 3,180", and the
    separator is `f"{n:,}"` — Python-side formatting, which cannot run against a
    Var. `AdminState.register_scope` calls this when the read completes; the
    register reads the field.

    General rather than a `format_scope`, because the summary's figures are the
    second caller and the register's tokens cell and message count the third
    (PRD-013 STORY-015): a count is a count on every surface.

    0 returns "0", not the absent mark: nothing recorded is a fact, and the same
    distinction `to_audit_row` makes for `tokens_used` below.
    """
    if value is None:
        return VALUE_ABSENT
    return f"{value:,}"


def _text(value: Optional[object]) -> str:
    """A NULL column reads as the absent mark, so the row field stays a plain str."""
    if value is None or value == "":
        return VALUE_ABSENT
    return str(value)


def _flag(value: Optional[bool]) -> str:
    """A recorded boolean, as the word the disclosure shows.

    `False` is "no", a fact. `None` is the absent mark, never "no": the schema
    makes both flags NOT NULL and the mapper coerces them with `bool()`, so it
    does not arrive today, but a row that somehow lacked the value must not be
    shown as having recorded False.
    """
    if value is None:
        return VALUE_ABSENT
    return DETAIL_FLAG_YES_LABEL if value else DETAIL_FLAG_NO_LABEL


def _format_tokens(log: AuditLog) -> str:
    """The register's tokens cell (PRD-013 Section 6.10).

    "2,140 / 312" when the row recorded both halves of the split; the total
    when it recorded only that; the absent mark when it recorded neither. A
    half split falls back to the total: the client sets both or neither, and
    showing one side would imply the other was 0.

    0 tokens is a recorded fact, not a missing value, so every test is against
    None rather than truthiness.
    """
    if log.input_tokens is not None and log.output_tokens is not None:
        return (
            format_count(log.input_tokens)
            + TOKENS_SPLIT_SEPARATOR
            + format_count(log.output_tokens)
        )
    if log.tokens_used is not None:
        return format_count(log.tokens_used)
    return VALUE_ABSENT


def _parse_pii_entities(raw: Optional[str]) -> list[str]:
    """Splits the stored TEXT form written by `app/services/audit_logger.py:43`.

    Comma-separated, no spaces — the same parse `app/routers/admin.py:40` and
    `app/db/database.py:214` already do, rather than a second format.
    """
    if not raw:
        return []
    return [entity for entity in raw.split(",") if entity]


def _truncate_device(device: Optional[str]) -> tuple[str, str]:
    """Returns (in-row device string, full device string)."""
    if not device:
        return VALUE_ABSENT, VALUE_ABSENT
    if len(device) <= DEVICE_TRUNCATE_LENGTH:
        return device, device
    return device[:DEVICE_TRUNCATE_LENGTH] + DEVICE_ELLIPSIS, device


def _format_timestamps(raw: Optional[str], now: datetime) -> tuple[str, str]:
    """Returns (relative time, absolute timestamp) for the register's time column.

    Degrades the way `formatting.py:format_duplicate_info` does: a missing or
    unparseable timestamp costs the relative reading, not the row. An
    unparseable value is still shown absolutely — it is evidence.
    """
    if not raw:
        return VALUE_ABSENT, VALUE_ABSENT
    try:
        recorded = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        seconds = int((now - recorded).total_seconds())
        return humanize_compact(seconds), raw
    except Exception:
        return VALUE_ABSENT, raw


def format_refreshed_at(now: Optional[datetime] = None) -> str:
    """The moment of the read, as the stamp the console shows beside refresh.

    Here rather than in `admin_state.py` for the reason at the top of this
    module: it is a rendered string, and components receive Vars, so it is
    computed once in Python when the read completes. STORY-017 renders it.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return now.strftime(REFRESHED_AT_FORMAT)


def to_audit_row(log: AuditLog, now: Optional[datetime] = None) -> AuditRow:
    """Projects one `AuditLog` onto the register's row model.

    `now` is a parameter so the relative time is deterministic under test and
    so a hundred rows share one clock read. Every field is named explicitly;
    neither preview is read (Risk 2).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    relative, absolute = _format_timestamps(log.timestamp, now)
    device_short, device_full = _truncate_device(log.device)

    return AuditRow(
        audit_id=log.id or 0,
        timestamp_absolute=absolute,
        timestamp_relative=relative,
        user_id=log.user_id,
        verdict=derive_verdict(log),
        model_used=_text(log.model_used),
        tokens_used=_format_tokens(log),
        pii_indicator=bool(log.pii_detected_input or log.pii_detected_output),
        device_short=device_short,
        device_full=device_full,
        prompt_hash=_text(log.prompt_hash),
        error_message=_text(log.error_message),
        pii_entities=_parse_pii_entities(log.pii_entities),
        pii_detected_input=bool(log.pii_detected_input),
        pii_detected_output=bool(log.pii_detected_output),
        suspicious_pattern=_text(log.suspicious_pattern),
        pattern_role=_text(log.pattern_role),
        pattern_action=_text(log.pattern_action),
        profile=_text(log.profile),
        # PRD-013 (STORY-015): disclosure-only, the absent mark on every row
        # written before PRD-013.
        ingress=_text(log.ingress),
        message_count=format_count(log.message_count),
        conversation_key=_text(log.conversation_key),
        streamed=_flag(log.streamed),
        has_tool_calls=_flag(log.has_tool_calls),
        limit_exceeded=_text(log.limit_exceeded),
    )


# --- The Usage table (PRD-013 STORY-016) ------------------------------------


def _usage_identity(day: UsageDay) -> Identity:
    """The identity the gate resolves for this counter row's user.

    A user with a `users` row carries that row's role and overrides, exactly as
    `identity.resolve()` builds it. The break-glass `admin` has no `users` row
    (Section 6.6), so it is recognised by its id and given the role `resolve()`
    gives it. Any other row with no `users` row is not expected; its role is
    left empty, which `limits_for` resolves through the `*` entry and the table
    shows as the absent mark rather than inventing one.
    """
    if day.role is None and day.user_id == BREAK_GLASS_USER_ID:
        return Identity(
            user_id=day.user_id, role=BREAK_GLASS_ROLE, break_glass=True
        )
    return Identity(
        user_id=day.user_id,
        role=day.role or "",
        token_budget_daily=day.token_budget_daily,
        requests_per_minute=day.requests_per_minute,
    )


def to_usage_rows(days: list[UsageDay]) -> list[UsageRow]:
    """Today's counters as the Usage table's rows, nearest the budget first.

    **The budget is the gate's.** Each row's budget comes from `limits_for`, the
    function `usage_limits.admit` calls, with settings read per call, so the
    table and the gate cannot disagree and a reconfiguration shows on the next
    Refresh.

    **Used is what the gate compares.** `tokens_today` is input + output +
    unsplit, the same expression `_ADMIT_USAGE_SQL` returns, so a share of 100%
    is exactly the point at which the next request is denied. Input and Output
    show only the split, so they can sum to less; the Used head says so.

    **The order is the one structural statement the table makes**: highest share
    first, then every unlimited row, each group in `usage_snapshot()`'s user_id
    order (the sort is stable). An unlimited row has no share, so `used` is the
    absent mark, never "0.0%".
    """
    measured = []
    for day in days:
        identity = _usage_identity(day)
        budget = limits_for(identity).token_budget_daily
        tokens_today = day.input_tokens + day.output_tokens + day.unsplit_tokens
        share = tokens_today / budget if budget else None
        measured.append((day, identity, budget, tokens_today, share))

    measured.sort(key=lambda entry: (entry[4] is None, -(entry[4] or 0)))

    return [
        UsageRow(
            user_id=day.user_id,
            role=_text(identity.role),
            requests=format_count(day.requests),
            input_tokens=format_count(day.input_tokens),
            output_tokens=format_count(day.output_tokens),
            budget=USAGE_BUDGET_UNLIMITED if budget is None else format_count(budget),
            used=VALUE_ABSENT if budget is None else format_share(tokens_today, budget),
            denied=format_count(day.denied),
        )
        for day, identity, budget, tokens_today, share in measured
    ]
