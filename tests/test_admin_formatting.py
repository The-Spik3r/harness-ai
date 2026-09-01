"""The register renders what this module computed, so this is where it is checked.

Every value on a register row is derived once, in Python, when the row is built
(PRD-006 Section 6) — by the time a component sees it, it is a Reflex Var and
nothing here can run. So the verdict precedence, the relative time, the device
truncation and the shares have no second chance downstream, and each is pinned
below. Two of these tests defend decisions rather than behaviour: the verdict
precedence (identical rows must never render differently) and the absence of
any `model_used` branch in `derive_verdict` (PRD-006 Risk 3).
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models import AuditLog
from chat_ui.chat_ui.admin_formatting import (
    DEVICE_TRUNCATE_LENGTH,
    SHARE_UNDEFINED,
    VALUE_ABSENT,
    VERDICT_CLEARED,
    VERDICT_DENIED,
    VERDICT_FAULT,
    VERDICT_HELD,
    VERDICTS,
    derive_verdict,
    format_count,
    format_share,
    to_audit_row,
)

NOW = datetime(2026, 8, 28, 14, 22, 7, tzinfo=timezone.utc)


def make_log(**overrides) -> AuditLog:
    """A cleared row, unless an override says otherwise."""
    fields = {
        "timestamp": "2026-08-28T14:20:07Z",
        "user_id": "a.torres",
        "prompt_hash": "9f2b1c",
        "device": "Mozilla/5.0",
        "model_used": "gpt-4",
        "tokens_used": 412,
        "success": True,
        "id": 3180,
    }
    fields.update(overrides)
    return AuditLog(**fields)


# --- Verdict derivation --------------------------------------------------


def test_each_verdict_derives_from_its_condition():
    """AC 1: PRD-006 Section 6's table, one row at a time."""
    assert derive_verdict(make_log(was_duplicate_blocked=True)) == VERDICT_HELD
    assert derive_verdict(make_log(suspicious_pattern="ignore_instructions")) == VERDICT_DENIED
    assert derive_verdict(make_log(success=False)) == VERDICT_FAULT
    assert derive_verdict(make_log()) == VERDICT_CLEARED


def test_verdict_precedence_is_deterministic_when_conditions_overlap():
    """AC 2: the table is a precedence, not four independent flags.

    Fails if the order is ever rewritten as a dict lookup or a set of
    conditions evaluated in a different sequence.
    """
    both = make_log(was_duplicate_blocked=True, suspicious_pattern="ignore_instructions")
    assert derive_verdict(both) == VERDICT_HELD

    all_three = make_log(
        was_duplicate_blocked=True,
        suspicious_pattern="ignore_instructions",
        success=False,
    )
    assert derive_verdict(all_three) == VERDICT_HELD

    denied_and_failed = make_log(suspicious_pattern="ignore_instructions", success=False)
    assert derive_verdict(denied_and_failed) == VERDICT_DENIED

    # Same fields in, same verdict out — every time.
    assert derive_verdict(both) == derive_verdict(
        make_log(was_duplicate_blocked=True, suspicious_pattern="ignore_instructions")
    )


def test_fault_does_not_branch_on_model_used():
    """AC 6 / Risk 3: a recorded model does not make a failure "upstream".

    `app/services/query_pipeline.py:91-93` logs `model_used` alongside
    `success=False` on the output-side PiiRedactorError arm, so the presence of
    a model cannot separate an internal fault from an upstream one.
    """
    assert derive_verdict(make_log(success=False, model_used="gpt-4")) == VERDICT_FAULT
    assert derive_verdict(make_log(success=False, model_used=None)) == VERDICT_FAULT


def test_verdict_constants_are_the_registers_four():
    """A fifth verdict would need a fifth ink and a new rx.match arm downstream."""
    assert set(VERDICTS) == {"cleared", "held", "denied", "fault"}
    assert len(VERDICTS) == 4


# --- Row projection ------------------------------------------------------


def test_to_audit_row_populates_every_field():
    """AC 3: one AuditLog in, one fully-populated AuditRow out."""
    log = make_log(
        timestamp="2026-08-28T14:20:07Z",
        device="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        pii_detected_input=True,
        pii_entities="EMAIL_ADDRESS,PHONE_NUMBER",
    )
    row = to_audit_row(log, NOW)

    assert row.audit_id == 3180
    assert row.timestamp_relative == "2m ago"
    assert row.timestamp_absolute == "2026-08-28T14:20:07Z"
    assert row.user_id == "a.torres"
    assert row.verdict == VERDICT_CLEARED
    assert row.model_used == "gpt-4"
    assert row.tokens_used == "412"
    assert row.device_full == log.device
    assert row.device_short.endswith("…")
    assert len(row.device_short) == DEVICE_TRUNCATE_LENGTH + 1
    assert log.device.startswith(row.device_short[:-1])
    assert row.pii_entities == ["EMAIL_ADDRESS", "PHONE_NUMBER"]
    assert row.prompt_hash == "9f2b1c"


def test_pii_indicator_combines_both_sides():
    """AC 3: the in-row mark is input OR output; the split survives on disclosure."""
    assert to_audit_row(make_log(pii_detected_input=True), NOW).pii_indicator is True
    assert to_audit_row(make_log(pii_detected_output=True), NOW).pii_indicator is True
    assert to_audit_row(make_log(), NOW).pii_indicator is False

    row = to_audit_row(make_log(pii_detected_output=True), NOW)
    assert row.pii_detected_input is False
    assert row.pii_detected_output is True


def test_to_audit_row_carries_no_preview_value():
    """AC 4 / Risk 2: the previews are dropped at this boundary, not downstream."""
    log = make_log(
        prompt_preview="SECRET-PROMPT-TEXT",
        response_preview="SECRET-RESPONSE-TEXT",
    )
    row = to_audit_row(log, NOW)

    dumped = str(row.model_dump())
    assert "SECRET-PROMPT-TEXT" not in dumped
    assert "SECRET-RESPONSE-TEXT" not in dumped
    assert not hasattr(row, "prompt_preview")
    assert not hasattr(row, "response_preview")


def test_short_device_is_not_truncated():
    """Truncation only when it buys something: a string that fits is left alone."""
    device = "x" * DEVICE_TRUNCATE_LENGTH
    row = to_audit_row(make_log(device=device), NOW)
    assert row.device_short == device
    assert row.device_full == device


def test_null_columns_render_the_absent_mark():
    """Every optional column is a plain str on the row, so nothing renders None."""
    row = to_audit_row(
        make_log(
            device=None,
            model_used=None,
            tokens_used=None,
            error_message=None,
            suspicious_pattern=None,
            pii_entities=None,
        ),
        NOW,
    )

    assert row.model_used == VALUE_ABSENT
    assert row.tokens_used == VALUE_ABSENT
    assert row.device_short == VALUE_ABSENT
    assert row.device_full == VALUE_ABSENT
    assert row.error_message == VALUE_ABSENT
    assert row.suspicious_pattern == VALUE_ABSENT
    assert row.pii_entities == []


def test_tokens_used_zero_is_not_the_absent_mark():
    """0 tokens is a recorded fact; only NULL is missing."""
    assert to_audit_row(make_log(tokens_used=0), NOW).tokens_used == "0"


def test_error_message_reaches_the_row_for_a_fault():
    """The console's clearest gain over `curl /audit`, which drops this field."""
    row = to_audit_row(make_log(success=False, error_message="OpenRouter 502"), NOW)
    assert row.verdict == VERDICT_FAULT
    assert row.error_message == "OpenRouter 502"


def test_to_audit_row_defaults_now_to_the_current_clock():
    """STORY-004 may omit `now`; the row must still carry a relative time."""
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    assert to_audit_row(make_log(timestamp=recent)).timestamp_relative == "5m ago"


# --- Relative time -------------------------------------------------------


@pytest.mark.parametrize(
    "elapsed_seconds,expected",
    [
        (0, "just now"),
        (1, "1s ago"),
        (45, "45s ago"),
        (60, "1m ago"),
        (120, "2m ago"),
        (3600, "1h ago"),
        (7200, "2h ago"),
        (86400, "1d ago"),
        (172800, "2d ago"),
    ],
)
def test_relative_time_compact_at_every_boundary(elapsed_seconds, expected):
    """The register's time column is fixed-width; the chat's thresholds are reused.

    Same unit boundaries as `tests/test_copy.py` pins for the long spelling —
    one threshold table in `formatting.py`, two renderings.
    """
    recorded = (NOW - timedelta(seconds=elapsed_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert to_audit_row(make_log(timestamp=recorded), NOW).timestamp_relative == expected


def test_future_timestamp_reads_as_just_now():
    """Clock skew between writer and reader must not print a negative span."""
    ahead = (NOW + timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert to_audit_row(make_log(timestamp=ahead), NOW).timestamp_relative == "just now"


def test_missing_and_unparseable_timestamp_degrade():
    """A bad timestamp costs the relative reading, not the row."""
    missing = to_audit_row(make_log(timestamp=""), NOW)
    assert missing.timestamp_relative == VALUE_ABSENT
    assert missing.timestamp_absolute == VALUE_ABSENT

    # The unparseable value is still shown — it is evidence.
    bad = to_audit_row(make_log(timestamp="not-a-timestamp"), NOW)
    assert bad.timestamp_relative == VALUE_ABSENT
    assert bad.timestamp_absolute == "not-a-timestamp"


def test_naive_now_degrades_instead_of_raising():
    """A caller passing a naive datetime gets a placeholder, never a page fault."""
    row = to_audit_row(make_log(), datetime(2026, 8, 28, 14, 22, 7))
    assert row.timestamp_relative == VALUE_ABSENT
    assert row.timestamp_absolute == "2026-08-28T14:20:07Z"


# --- Shares --------------------------------------------------------------


def test_format_share_placeholder_and_value():
    """AC 5: an empty table has no share, and saying "0.0%" would claim it does."""
    assert format_share(3, 0) == SHARE_UNDEFINED
    assert format_share(13, 100) == "13.0%"
    assert format_share(1, 3) == "33.3%"
    assert format_share(0, 100) == "0.0%"


def test_format_share_never_raises_on_a_bad_denominator():
    """Every summary figure renders; none of them may raise into the page."""
    assert format_share(3, None) == SHARE_UNDEFINED
    assert format_share(3, -1) == SHARE_UNDEFINED
    assert format_share(None, 100) == SHARE_UNDEFINED


def test_format_share_matches_the_stats_router_number_format():
    """The console and `curl /stats` must not disagree on rounding."""
    successful, total = 267, 3180
    assert format_share(successful, total) == f"{(successful / total * 100):.1f}%"


# ---------------------------------------------------------------------------
# format_count — the scope line's separator (STORY-011)
# ---------------------------------------------------------------------------


def test_format_count_separates_thousands():
    """PRD-006 Section 6.1's scope line reads "100 most recent of 3,180".

    Here rather than in the register for the reason at the top of the module:
    `f"{n:,}"` is Python-side formatting and cannot run against a Var.
    """
    assert format_count(3180) == "3,180"
    assert format_count(1234567) == "1,234,567"


def test_format_count_leaves_small_numbers_alone():
    assert format_count(999) == "999"
    assert format_count(12) == "12"


def test_format_count_reads_zero_as_a_count_not_an_absence():
    """Zero recorded rows is a fact, and the same distinction `to_audit_row`
    makes for `tokens_used`: 0 tokens is a value, a NULL column is not."""
    assert format_count(0) == "0"


def test_format_count_never_raises_on_a_missing_figure():
    """No figure may raise into a page render."""
    assert format_count(None) == VALUE_ABSENT
