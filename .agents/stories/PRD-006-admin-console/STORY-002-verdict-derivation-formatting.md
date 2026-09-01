---
id: STORY-002
prd: PRD-006
slug: verdict-derivation-formatting
title: "admin_formatting.py: verdict derivation, relative time, device and shares"
type: technical
priority: high
complexity: medium
phase: "1 - Access and data"
status: done
labels: [ui, formatting, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-002-verdict-derivation-formatting.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-002-verdict-derivation-formatting.report.md
commit: 0fe6c69
depends_on: [STORY-001]
blocks: [STORY-004, STORY-006, STORY-011, STORY-015]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-002: admin_formatting.py: verdict derivation, relative time, device and shares

## Description

As an integrating developer, I want every displayed value on a register row computed once in Python when the row is built, so that components read plain fields instead of computing over Reflex Vars (PRD Section 6, "derived-once row model").

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/admin_formatting.py`, when `derive_verdict(log)` is called with an `AuditLog`, then it returns exactly one of `cleared`, `held`, `denied`, `fault`, following PRD Section 6's table in that precedence: `was_duplicate_blocked` → **held**, `suspicious_pattern is not None` → **denied**, `success = 0` → **fault**, otherwise **cleared**.
- [ ] Given a row that is both duplicate-blocked and pattern-flagged, when the verdict is derived, then the outcome is deterministic and the precedence is stated in a module comment, so two rows with identical fields never render differently.
- [ ] Given an `AuditLog`, when `to_audit_row(log, now)` is called, then it returns a fully-populated `AuditRow` with the relative time ("2m ago"), the absolute timestamp, the truncated and full device strings, the combined PII indicator (`pii_detected_input or pii_detected_output`) and `pii_entities` parsed from its stored TEXT form into `list[str]`.
- [ ] Given `to_audit_row`, when the returned object is inspected, then neither preview value from the source `AuditLog` is present on it.
- [ ] Given `format_share(count, total)`, when `total` is 0, then it returns a defined placeholder rather than raising `ZeroDivisionError`; when `total` is non-zero it returns the share of `total_queries` the summary renders beside each blocked count.
- [ ] Given a failed row that also carries a `model_used` value, when `derive_verdict` runs, then the verdict is still **fault** — the function never branches on `model_used` (Risk 3).

## Technical Notes

- New file `chat_ui/chat_ui/admin_formatting.py`. The precedent is [chat_ui/chat_ui/formatting.py](../../../chat_ui/chat_ui/formatting.py) — `format_duplicate_info` exists there for exactly this reason. PRD Section 6, verbatim: the verdict is "computed once per row in Python when the row is built — never at render time, for the same reason PRD-004 put `format_duplicate_info` in `formatting.py`: component functions receive Reflex Vars, not values."
- Risk 3, verbatim: "The obvious way to separate an upstream failure from an internal one is to check whether a model was recorded — and it is wrong, because the output-side `PiiRedactorError` arm logs one." Record that reasoning in a module comment so the "improvement" is not reintroduced later.
- `pii_entities` arrives as `Optional[str]` from [app/db/models.py](../../../app/db/models.py). Check how [app/routers/admin.py](../../../app/routers/admin.py) already parses it for `AuditQueryEntry` and match that parsing rather than inventing a second format.
- Relative-time formatting already exists for the chat's duplicate card in `formatting.py` (PRD-004 STORY-011) — reuse or lift that helper rather than writing a second implementation with different thresholds.
- The four verdict strings become the register's filter values and the `rx.match` keys in [[STORY-011]]; define them as module constants, not inline literals.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-004, STORY-006, STORY-011, STORY-015

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 6 (verdict derivation table, derived-once row model), Section 12 Phase 1, Risk 3
