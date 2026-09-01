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
"""

from datetime import datetime, timezone
from typing import Optional

from app.db.models import AuditLog

from .admin_models import AuditRow
from .formatting import humanize_compact

# The register's outcome vocabulary (PRD-006 Section 6). These are values, not
# copy: they are the `rx.match` keys and the filter values downstream, so they
# are constants rather than inline literals in three components.
#
# A single row can satisfy several of these conditions at once, so the order in
# `derive_verdict` is a precedence, not a set of independent flags:
#
#     was_duplicate_blocked   -> held
#     suspicious_pattern      -> denied
#     not success             -> fault
#     otherwise               -> cleared
#
# Fixed here and nowhere else, so two rows with identical fields can never
# render differently.
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
    """
    if log.was_duplicate_blocked:
        return VERDICT_HELD
    if log.suspicious_pattern is not None:
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

    General rather than a `format_scope`, because the summary's nine figures are
    the second caller (STORY-015) and a count is a count on both sheets.

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
        # 0 tokens is a recorded fact, not a missing value, so this tests
        # against None rather than truthiness.
        tokens_used=str(log.tokens_used) if log.tokens_used is not None else VALUE_ABSENT,
        pii_indicator=bool(log.pii_detected_input or log.pii_detected_output),
        device_short=device_short,
        device_full=device_full,
        prompt_hash=_text(log.prompt_hash),
        error_message=_text(log.error_message),
        pii_entities=_parse_pii_entities(log.pii_entities),
        pii_detected_input=bool(log.pii_detected_input),
        pii_detected_output=bool(log.pii_detected_output),
        suspicious_pattern=_text(log.suspicious_pattern),
    )
