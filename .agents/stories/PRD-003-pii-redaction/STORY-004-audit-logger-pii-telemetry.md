---
id: STORY-004
prd: PRD-003
slug: audit-logger-pii-telemetry
title: "Audit logger records PII telemetry (raw preview unchanged)"
type: feature
priority: high
complexity: small
phase: "2 - Pipeline Wiring"
status: done
labels: [backend, pii, audit]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-004-audit-logger-pii-telemetry.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-004-audit-logger-pii-telemetry.report.md
commit: 1347e53
depends_on: [STORY-003]
blocks: [STORY-006, STORY-009]
skills: []
created: 2026-07-24
updated: 2026-07-31
---

# STORY-004: Audit logger records PII telemetry (raw preview unchanged)

## Description

As a compliance admin, I want `log_query()` to record whether PII was detected on the input/output and which entity types, while continuing to store the raw, unmasked `prompt_preview`/`response_preview` exactly as before, so I can investigate what was actually attempted (PRD Section 4, User Story 3, RF-7, RF-8).

## Acceptance Criteria

- [ ] Given `log_query()` is called with `pii_detected_input=True`, `pii_detected_output=True`, `pii_entities=["EMAIL_ADDRESS", "PERSON"]`, when the audit row is written, then those values are persisted via the new `AuditLog` columns from [[STORY-003]].
- [ ] Given `log_query()` is called without the new PII arguments (existing call sites), when it runs, then it behaves identically to today — defaults to no PII detected, and `prompt_preview`/`response_preview` are computed from the raw text exactly as before.
- [ ] Given `log_query(prompt=..., response=...)` is called, when the audit row is written, then `prompt_preview`/`response_preview`/`prompt_hash`/`response_hash` are still derived from the **raw** prompt/response passed in — this function must never receive already-redacted text for those fields.
- [ ] Given the existing `tests/test_audit_logger.py` suite, when run, then all existing tests pass unmodified.

## Technical Notes

- Extend `log_query()` in `app/services/audit_logger.py` ([audit_logger.py](../../../app/services/audit_logger.py)) with new optional parameters: `pii_detected_input: bool = False`, `pii_detected_output: bool = False`, `pii_entities: Optional[list[str]] = None`, joined to a string before constructing `AuditLog` (per [[STORY-003]]'s storage format).
- Do **not** change how `prompt_preview`/`response_preview`/`prompt_hash`/`response_hash` are computed (lines 24-31) — this is the explicit "audit log stays raw" decision in PRD Section 9. The caller ([[STORY-006]]'s pipeline change) is responsible for always passing raw text into `log_query`, regardless of what gets returned to the caller or forwarded to OpenRouter.
- This function has no knowledge of Presidio — it only accepts already-computed booleans/entity lists, keeping the adapter boundary in `pii_redactor.py` intact.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-006, STORY-009

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 6 (Changes to existing modules — `app/services/audit_logger.py`), Section 9 (Why the audit log stays raw), User Story 3
