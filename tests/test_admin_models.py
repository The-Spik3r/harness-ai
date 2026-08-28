"""The admin row model's missing fields are the feature.

The console reads `AuditLog` in-process, so `prompt_preview` and
`response_preview` are in the process whether or not anything renders them. The
mitigation for that (PRD-006 Risk 2) is an absence: `AuditRow` has no field for
either one, so the previews are dropped at the boundary and are not on the
object components receive. An absence has nothing to review in a diff, so it is
asserted here instead — this file is what fails if either field comes back.
"""

import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models import AuditLog
from chat_ui.chat_ui.admin_models import AuditRow, SummaryFigure

# The exact field set the register and its disclosure render (STORY-001 AC 1).
AUDIT_ROW_FIELDS = {
    "audit_id",
    "timestamp_absolute",
    "timestamp_relative",
    "user_id",
    "verdict",
    "model_used",
    "tokens_used",
    "pii_indicator",
    "device_short",
    "device_full",
    "prompt_hash",
    "error_message",
    "pii_entities",
    "pii_detected_input",
    "pii_detected_output",
    "suspicious_pattern",
}

SUMMARY_FIGURE_FIELDS = {"label", "value", "scope", "share", "items"}


def test_audit_row_has_no_preview_fields():
    """Risk 2: neither preview may exist on the row model."""
    # Declared fields — catches someone adding one to the class body.
    assert "prompt_preview" not in AuditRow.model_fields
    assert "response_preview" not in AuditRow.model_fields

    # Attributes — catches one attached outside the pydantic field machinery.
    row = AuditRow()
    assert not hasattr(row, "prompt_preview")
    assert not hasattr(row, "response_preview")

    # No near-miss spelling either (raw_prompt_preview, response_preview_text...).
    assert not [name for name in AuditRow.model_fields if "preview" in name]


def test_audit_row_carries_every_rendered_field():
    """Equality, not containment: an extra field fails as loudly as a missing one."""
    assert set(AuditRow.model_fields) == AUDIT_ROW_FIELDS


def test_audit_row_constructs_with_no_arguments():
    """Every field defaults, so a partially-populated row never raises at render."""
    row = AuditRow()

    assert row.audit_id == 0
    for name in ("timestamp_absolute", "timestamp_relative", "user_id", "verdict",
                 "model_used", "tokens_used", "device_short", "device_full",
                 "prompt_hash", "error_message", "suspicious_pattern"):
        assert getattr(row, name) == ""
    for name in ("pii_indicator", "pii_detected_input", "pii_detected_output"):
        assert getattr(row, name) is False
    assert row.pii_entities == []

    # The list default is per-instance, not shared across rows.
    row.pii_entities.append("EMAIL_ADDRESS")
    assert AuditRow().pii_entities == []


def test_audit_row_types():
    """Two types downstream stories depend on and must not silently drift."""
    # STORY-005 coerces audit_id to str inside the filter var, so it is an int here.
    assert isinstance(AuditRow().audit_id, int)
    # tokens_used is pre-formatted: Optional[int] would force an rx.cond over
    # None at render, which is exactly what the derived-once rule forbids.
    assert isinstance(AuditRow().tokens_used, str)


def test_audit_row_verdict_defaults_to_empty_not_cleared():
    """An unpopulated row must not assert that it passed."""
    assert AuditRow().verdict == ""


def test_summary_figure_fields_and_defaults():
    assert set(SummaryFigure.model_fields) == SUMMARY_FIGURE_FIELDS

    figure = SummaryFigure()
    assert figure.label == ""
    assert figure.value == ""
    assert figure.scope == ""
    assert figure.share == ""
    assert figure.items == []

    populated = SummaryFigure(
        label="Duplicates held",
        value="412",
        scope="all-time, whole table",
        share="13.0%",
        items=["gpt-4 — 812", "claude-3 — 199"],
    )
    assert populated.label == "Duplicates held"
    assert populated.value == "412"
    assert populated.scope == "all-time, whole table"
    assert populated.share == "13.0%"
    assert populated.items == ["gpt-4 — 812", "claude-3 — 199"]


def test_audit_row_populated_from_audit_log_drops_previews():
    """The boundary in miniature: previews on the source never reach the row."""
    log = AuditLog(
        timestamp="2026-08-28T14:22:07Z",
        user_id="a.torres",
        prompt_hash="hash-3180",
        device="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0",
        prompt_preview="raw prompt text",
        response_preview="raw response text",
        model_used="gpt-4",
        tokens_used=412,
        pii_detected_input=True,
        pii_entities="EMAIL_ADDRESS,PERSON",
        id=3180,
    )

    # Built field-by-field the way to_audit_row(...) will in STORY-002: the
    # projection is what the constructor accepts, so the previews have nowhere
    # to go even when the caller has them in hand.
    row = AuditRow(
        audit_id=log.id,
        timestamp_absolute=log.timestamp,
        timestamp_relative="2m ago",
        user_id=log.user_id,
        verdict="cleared",
        model_used=log.model_used,
        tokens_used=str(log.tokens_used),
        pii_indicator=log.pii_detected_input or log.pii_detected_output,
        device_short="Chrome",
        device_full=log.device,
        prompt_hash=log.prompt_hash,
        pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
        pii_detected_input=log.pii_detected_input,
        pii_detected_output=log.pii_detected_output,
    )

    serialized = str(row.model_dump())
    assert log.prompt_preview not in serialized
    assert log.response_preview not in serialized
    assert "preview" not in serialized
